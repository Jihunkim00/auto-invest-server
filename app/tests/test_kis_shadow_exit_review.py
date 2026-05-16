import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.main import app


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_exit_shadow_review_returns_ok_and_is_read_only(client, db_session):
    _add_shadow_run(db_session, decision="would_sell", trigger="stop_loss")
    before = _counts(db_session)

    response = client.get("/kis/exit-shadow/review")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "shadow_exit_review"
    assert body["review_window_days"] == 30
    assert body["safety"]["read_only"] is True
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["broker_submit_called"] is False
    assert body["safety"]["manual_submit_called"] is False
    assert body["safety"]["auto_buy_enabled"] is False
    assert body["safety"]["auto_sell_enabled"] is False
    assert body["safety"]["scheduler_real_order_enabled"] is False
    assert _counts(db_session) == before


def test_exit_shadow_review_summarizes_decisions_and_triggers(
    client, db_session
):
    _add_shadow_run(
        db_session,
        run_key="shadow-stop-loss",
        symbol="005930",
        decision="would_sell",
        action="sell",
        trigger="stop_loss",
        unrealized_pl=-2880,
        unrealized_pl_pct=-0.02,
    )
    _add_shadow_run(
        db_session,
        run_key="shadow-hold",
        symbol="000660",
        decision="hold",
        action="hold",
        trigger="none",
        selected_candidate=False,
    )
    _add_shadow_run(
        db_session,
        run_key="shadow-review",
        symbol="035420",
        decision="manual_review",
        action="hold",
        trigger="manual_review",
        trigger_source="insufficient_cost_basis",
        cost_basis=None,
        unrealized_pl_pct=None,
        risk_flags=["insufficient_cost_basis", "manual_review_required"],
    )

    response = client.get("/kis/exit-shadow/review?limit=10&days=30")

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["total_shadow_runs"] == 3
    assert summary["would_sell_count"] == 1
    assert summary["hold_count"] == 1
    assert summary["manual_review_count"] == 1
    assert summary["no_candidate_count"] == 1
    assert summary["stop_loss_count"] == 1
    assert summary["take_profit_count"] == 0
    assert summary["manual_review_trigger_count"] == 1
    assert summary["insufficient_cost_basis_count"] == 1
    assert summary["unique_symbols_evaluated"] == 3
    assert summary["would_sell_rate"] == pytest.approx(1 / 3)
    assert summary["manual_review_rate"] == pytest.approx(1 / 3)
    assert summary["average_unrealized_pl_pct_for_would_sell"] == pytest.approx(
        -0.02
    )
    assert summary["min_unrealized_pl_pct_for_would_sell"] == pytest.approx(-0.02)
    assert summary["max_unrealized_pl_pct_for_would_sell"] == pytest.approx(-0.02)
    assert summary["no_submit_invariant_ok"] is True


def test_exit_shadow_review_recent_decisions_parse_shadow_logs(
    client, db_session
):
    run = _add_shadow_run(
        db_session,
        run_key="shadow-take-profit",
        signal_id=11,
        symbol="005930",
        decision="would_sell",
        action="sell",
        trigger="take_profit",
        unrealized_pl=2500,
        unrealized_pl_pct=0.031,
        current_value=10310,
        suggested_quantity=1,
    )

    response = client.get("/kis/exit-shadow/review")

    assert response.status_code == 200
    item = response.json()["recent_decisions"][0]
    assert item["run_id"] == run.id
    assert item["run_key"] == "shadow-take-profit"
    assert item["signal_id"] == 11
    assert item["symbol"] == "005930"
    assert item["decision"] == "would_sell"
    assert item["action"] == "sell"
    assert item["trigger"] == "take_profit"
    assert item["trigger_source"] == "cost_basis_pl_pct"
    assert item["unrealized_pl"] == pytest.approx(2500)
    assert item["unrealized_pl_pct"] == pytest.approx(0.031)
    assert item["cost_basis"] == pytest.approx(10000)
    assert item["current_value"] == pytest.approx(10310)
    assert item["suggested_quantity"] == pytest.approx(1)
    assert item["real_order_submitted"] is False
    assert item["broker_submit_called"] is False
    assert item["manual_submit_called"] is False
    assert item["linked_manual_order_id"] is None
    assert item["linked_manual_order_status"] is None


def test_exit_shadow_review_handles_missing_cost_basis_and_percent(
    client, db_session
):
    _add_shadow_run(
        db_session,
        decision="manual_review",
        action="hold",
        trigger="manual_review",
        trigger_source="insufficient_cost_basis",
        cost_basis=None,
        current_value=10200,
        unrealized_pl=200,
        unrealized_pl_pct=None,
        risk_flags=["insufficient_cost_basis"],
    )

    response = client.get("/kis/exit-shadow/review")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["insufficient_cost_basis_count"] == 1
    item = body["recent_decisions"][0]
    assert item["cost_basis"] is None
    assert item["unrealized_pl_pct"] is None
    assert item["current_value"] == pytest.approx(10200)


def test_exit_shadow_review_reports_malformed_submit_flags(
    client, db_session
):
    _add_shadow_run(
        db_session,
        decision="would_sell",
        trigger="stop_loss",
        malformed_submit_flags=True,
    )

    response = client.get("/kis/exit-shadow/review")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["no_submit_invariant_ok"] is False
    assert body["safety"]["no_submit_invariant_ok"] is False
    assert "historical_shadow_record_has_submit_flag_true" in body["safety"][
        "warnings"
    ]
    assert body["recent_decisions"][0]["real_order_submitted"] is True
    assert body["recent_decisions"][0]["no_submit_invariant_ok"] is False


def test_exit_shadow_review_leaves_manual_link_null_without_reliable_match(
    client, db_session
):
    _add_shadow_run(db_session, run_key="shadow-unmatched", symbol="005930")
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="sell",
            order_type="market",
            qty=1,
            internal_status="SUBMITTED",
            request_payload=json.dumps({"mode": "manual_live"}),
        )
    )
    db_session.commit()

    response = client.get("/kis/exit-shadow/review")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["manual_sell_followed_count"] == 0
    assert body["summary"]["manual_sell_followed_rate"] == 0
    assert body["summary"]["unmatched_shadow_would_sell_count"] == 1
    assert body["recent_decisions"][0]["linked_manual_order_id"] is None
    assert body["linked_manual_orders"] == []


def test_exit_shadow_review_detects_clear_manual_sell_follow_through(
    client, db_session
):
    run = _add_shadow_run(
        db_session,
        run_key="shadow-linked",
        symbol="005930",
        decision="would_sell",
        trigger="take_profit",
        unrealized_pl_pct=0.031,
    )
    order = _add_shadow_linked_manual_sell(
        db_session,
        symbol="005930",
        run_key=run.run_key,
        trigger="take_profit",
    )

    response = client.get("/kis/exit-shadow/review")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["manual_sell_followed_count"] == 1
    assert body["summary"]["manual_sell_followed_rate"] == pytest.approx(1.0)
    assert body["summary"]["unmatched_shadow_would_sell_count"] == 0
    item = body["recent_decisions"][0]
    assert item["linked_manual_order_id"] == order.id
    assert item["linked_manual_order_status"] == "PARTIALLY_FILLED"
    assert body["linked_manual_orders"][0]["order_id"] == order.id
    assert body["linked_manual_orders"][0]["status"] == "PARTIALLY_FILLED"
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["broker_submit_called"] is False
    assert body["safety"]["manual_submit_called"] is False


def test_exit_shadow_review_does_not_call_broker_or_manual_submit(
    monkeypatch, client, db_session
):
    _add_shadow_run(db_session)
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_order",
        lambda *args, **kwargs: pytest.fail("review must not call submit_order"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("review must not call KIS cash submit"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("review must not call manual submit"),
    )

    response = client.get("/kis/exit-shadow/review")

    assert response.status_code == 200
    assert response.json()["safety"]["read_only"] is True


def test_exit_shadow_review_symbol_filter(client, db_session):
    _add_shadow_run(db_session, symbol="005930", run_key="shadow-samsung")
    _add_shadow_run(db_session, symbol="000660", run_key="shadow-hynix")

    response = client.get("/kis/exit-shadow/review?symbol=000660")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total_shadow_runs"] == 1
    assert body["recent_decisions"][0]["symbol"] == "000660"


def _counts(db_session):
    return {
        "runs": db_session.query(TradeRunLog).count(),
        "signals": db_session.query(SignalLog).count(),
        "orders": db_session.query(OrderLog).count(),
    }


def _add_shadow_run(
    db_session,
    *,
    run_key: str = "shadow-run",
    signal_id: int | None = None,
    symbol: str = "005930",
    decision: str = "would_sell",
    action: str = "sell",
    trigger: str = "stop_loss",
    trigger_source: str = "cost_basis_pl_pct",
    cost_basis: float | None = 10000,
    current_value: float | None = 9800,
    unrealized_pl: float | None = -200,
    unrealized_pl_pct: float | None = -0.02,
    suggested_quantity: float | None = 2,
    risk_flags: list[str] | None = None,
    selected_candidate: bool = True,
    malformed_submit_flags: bool = False,
) -> TradeRunLog:
    now = datetime.now(UTC).replace(microsecond=0)
    candidate = {
        "symbol": symbol,
        "side": "sell",
        "quantity_available": suggested_quantity,
        "suggested_quantity": suggested_quantity,
        "trigger": trigger,
        "trigger_source": trigger_source,
        "current_price": 4900,
        "cost_basis": cost_basis,
        "current_value": current_value,
        "unrealized_pl": unrealized_pl,
        "unrealized_pl_pct": unrealized_pl_pct,
        "reason": "Shadow decision only.",
        "risk_flags": risk_flags
        if risk_flags is not None
        else [f"{trigger}_triggered" if trigger in {"stop_loss", "take_profit"} else trigger],
        "gating_notes": ["shadow_exit_only", "no_broker_submit"],
        "real_order_submitted": malformed_submit_flags,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "real_order_submit_allowed": False,
        "manual_confirm_required": True,
        "audit_metadata": {
            "source": "kis_exit_shadow_decision",
            "source_type": "dry_run_sell_simulation",
            "exit_trigger": trigger,
            "trigger_source": trigger_source,
            "shadow_real_order_submitted": malformed_submit_flags,
            "shadow_broker_submit_called": False,
            "shadow_manual_submit_called": False,
        },
    }
    payload = {
        "status": "ok",
        "provider": "kis",
        "market": "KR",
        "mode": "shadow_exit_dry_run",
        "source": "kis_exit_shadow_decision",
        "source_type": "dry_run_sell_simulation",
        "trigger_source": "shadow_exit",
        "decision": decision,
        "action": action,
        "result": decision,
        "reason": "would_sell_stop_loss"
        if decision == "would_sell"
        else "manual_review_required"
        if decision == "manual_review"
        else "no_exit_condition",
        "dry_run": True,
        "simulated": True,
        "real_order_submitted": malformed_submit_flags,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "real_order_submit_allowed": False,
        "auto_buy_enabled": False,
        "auto_sell_enabled": False,
        "scheduler_real_order_enabled": False,
        "candidate": candidate if selected_candidate else None,
        "candidates": [candidate] if selected_candidate else [],
        "candidates_evaluated": [candidate],
        "risk_flags": ["shadow_exit_only"] + candidate["risk_flags"],
        "gating_notes": ["shadow_exit_only", "no_broker_submit"],
        "created_at": now.isoformat(),
    }
    row = TradeRunLog(
        run_key=run_key,
        trigger_source="shadow_exit",
        symbol=symbol if selected_candidate else "WATCHLIST",
        mode="shadow_exit_dry_run",
        stage="done",
        result=decision,
        reason=payload["reason"],
        signal_id=signal_id,
        order_id=None,
        request_payload=json.dumps(
            {
                "provider": "kis",
                "market": "KR",
                "mode": "shadow_exit_dry_run",
                "source": "kis_exit_shadow_decision",
                "source_type": "dry_run_sell_simulation",
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        ),
        response_payload=json.dumps(payload),
        created_at=now.replace(tzinfo=None),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _add_shadow_linked_manual_sell(
    db_session,
    *,
    symbol: str,
    run_key: str,
    trigger: str,
) -> OrderLog:
    metadata = {
        "source": "kis_exit_shadow_decision",
        "source_type": "dry_run_sell_simulation",
        "shadow_decision_run_key": run_key,
        "shadow_decision_checked_at": datetime.now(UTC).isoformat(),
        "exit_trigger": trigger,
        "trigger_source": "cost_basis_pl_pct",
        "unrealized_pl_pct": 0.031,
        "manual_confirm_required": True,
        "auto_sell_enabled": False,
        "scheduler_real_order_enabled": False,
        "real_order_submit_allowed": False,
        "shadow_real_order_submitted": False,
        "shadow_broker_submit_called": False,
        "shadow_manual_submit_called": False,
    }
    payload = {
        "provider": "kis",
        "market": "KR",
        "mode": "manual_live",
        "source": "kis_exit_shadow_decision",
        "source_type": "dry_run_sell_simulation",
        "source_metadata": metadata,
        "real_order_submitted": True,
        "broker_submit_called": True,
        "manual_submit_called": True,
    }
    row = OrderLog(
        broker="kis",
        market="KR",
        symbol=symbol,
        side="sell",
        order_type="market",
        qty=2,
        requested_qty=2,
        filled_qty=1,
        remaining_qty=1,
        avg_fill_price=5200,
        internal_status="PARTIALLY_FILLED",
        broker_status="partial",
        broker_order_status="partial",
        broker_order_id="0001234567",
        kis_odno="0001234567",
        request_payload=json.dumps(payload),
        response_payload=json.dumps(payload),
        created_at=(datetime.now(UTC) + timedelta(minutes=1)).replace(tzinfo=None),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row
