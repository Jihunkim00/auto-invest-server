import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import KisShadowExitReviewQueueState, OrderLog, SignalLog, TradeRunLog
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


def test_exit_shadow_review_queue_returns_ok_and_is_read_only(client, db_session):
    _add_shadow_run(db_session, decision="would_sell", trigger="stop_loss")
    before = _counts(db_session)

    response = client.get("/kis/exit-shadow/review-queue")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "shadow_exit_review_queue"
    assert body["safety"]["read_only"] is True
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["broker_submit_called"] is False
    assert body["safety"]["manual_submit_called"] is False
    assert body["safety"]["auto_buy_enabled"] is False
    assert body["safety"]["auto_sell_enabled"] is False
    assert body["safety"]["scheduler_real_order_enabled"] is False
    assert _counts(db_session) == before


def test_exit_shadow_review_queue_includes_actionable_decisions_and_groups_repeats(
    client, db_session
):
    _add_shadow_run(
        db_session,
        run_key="shadow-stop-loss-1",
        symbol="005930",
        decision="would_sell",
        trigger="stop_loss",
        unrealized_pl=-2880,
        unrealized_pl_pct=-0.02,
        minutes_ago=8,
    )
    _add_shadow_run(
        db_session,
        run_key="shadow-stop-loss-2",
        symbol="005930",
        decision="would_sell",
        trigger="stop_loss",
        unrealized_pl=-3300,
        unrealized_pl_pct=-0.023,
        minutes_ago=2,
    )
    _add_shadow_run(
        db_session,
        run_key="shadow-review",
        symbol="035420",
        decision="manual_review",
        action="hold",
        trigger="manual_review",
        trigger_source="insufficient_cost_basis",
        risk_flags=["insufficient_cost_basis", "manual_review_required"],
        minutes_ago=1,
    )
    _add_shadow_run(
        db_session,
        run_key="shadow-hold",
        symbol="000660",
        decision="hold",
        action="hold",
        trigger="none",
        risk_flags=["no_exit_condition"],
    )

    response = client.get("/kis/exit-shadow/review-queue?limit=10")

    assert response.status_code == 200
    body = response.json()
    items = body["items"]
    assert body["summary"]["open_count"] == 2
    assert body["summary"]["would_sell_open_count"] == 1
    assert body["summary"]["manual_review_open_count"] == 1
    assert body["summary"]["repeated_symbol_count"] == 1
    assert {item["symbol"] for item in items} == {"005930", "035420"}

    stop_loss = next(item for item in items if item["symbol"] == "005930")
    assert stop_loss["queue_id"] == "005930:stop_loss:cost_basis_pl_pct"
    assert stop_loss["decision"] == "would_sell"
    assert stop_loss["action"] == "sell"
    assert stop_loss["severity"] == "urgent"
    assert stop_loss["occurrence_count"] == 2
    assert stop_loss["latest_unrealized_pl"] == pytest.approx(-3300)
    assert stop_loss["latest_unrealized_pl_pct"] == pytest.approx(-0.023)
    assert stop_loss["source_run_key"] == "shadow-stop-loss-2"
    assert stop_loss["real_order_submitted"] is False
    assert stop_loss["broker_submit_called"] is False
    assert stop_loss["manual_submit_called"] is False

    manual_review = next(item for item in items if item["symbol"] == "035420")
    assert manual_review["queue_id"] == "035420:manual_review:insufficient_cost_basis"
    assert manual_review["decision"] == "manual_review"
    assert manual_review["status"] == "open"


def test_exit_shadow_review_queue_mark_reviewed_and_dismiss_update_local_state_only(
    client, db_session
):
    _add_shadow_run(db_session, symbol="005930", trigger="stop_loss")
    _add_shadow_run(
        db_session,
        symbol="035420",
        decision="manual_review",
        action="hold",
        trigger="manual_review",
        trigger_source="insufficient_cost_basis",
    )

    before = _counts(db_session)
    reviewed = client.post(
        "/kis/exit-shadow/review-queue/005930:stop_loss:cost_basis_pl_pct/mark-reviewed",
        json={"operator_note": "Reviewed account 12345678 phone 010-1234-5678"},
    )
    dismissed = client.post(
        "/kis/exit-shadow/review-queue/035420:manual_review:insufficient_cost_basis/dismiss",
        json={"note": "Dismiss duplicate alert"},
    )

    assert reviewed.status_code == 200
    assert dismissed.status_code == 200
    assert reviewed.json()["item"]["status"] == "reviewed"
    assert dismissed.json()["item"]["status"] == "dismissed"
    assert "12345678" not in reviewed.json()["item"]["operator_note"]
    assert "010-1234-5678" not in reviewed.json()["item"]["operator_note"]
    assert _counts(db_session) == {
        **before,
        "queue_state": before["queue_state"] + 2,
    }

    response = client.get("/kis/exit-shadow/review-queue")
    body = response.json()
    assert body["summary"]["open_count"] == 0
    assert body["summary"]["reviewed_count"] == 1
    assert body["summary"]["dismissed_count"] == 1
    statuses = {item["symbol"]: item["status"] for item in body["items"]}
    assert statuses == {"005930": "reviewed", "035420": "dismissed"}


def test_exit_shadow_review_queue_state_survives_regeneration(client, db_session):
    _add_shadow_run(db_session, symbol="005930", trigger="take_profit")
    client.post(
        "/kis/exit-shadow/review-queue/005930:take_profit:cost_basis_pl_pct/mark-reviewed",
        json={"operator_note": "handled"},
    )
    _add_shadow_run(
        db_session,
        run_key="shadow-repeat-after-review",
        symbol="005930",
        trigger="take_profit",
        unrealized_pl=3000,
        unrealized_pl_pct=0.04,
    )

    response = client.get("/kis/exit-shadow/review-queue")

    item = response.json()["items"][0]
    assert item["queue_id"] == "005930:take_profit:cost_basis_pl_pct"
    assert item["occurrence_count"] == 2
    assert item["status"] == "reviewed"
    assert item["operator_note"] == "handled"
    assert response.json()["summary"]["reviewed_count"] == 1


def test_exit_shadow_review_queue_manual_sell_linking(client, db_session):
    run = _add_shadow_run(
        db_session,
        run_key="shadow-linked",
        symbol="005930",
        trigger="take_profit",
        unrealized_pl_pct=0.031,
    )
    order = _add_shadow_linked_manual_sell(
        db_session,
        symbol="005930",
        run_key=run.run_key,
        trigger="take_profit",
    )

    response = client.get("/kis/exit-shadow/review-queue")

    item = response.json()["items"][0]
    assert item["linked_manual_order_id"] == order.id
    assert item["linked_manual_order_status"] == "PARTIALLY_FILLED"
    assert item["linked_manual_order_filled_quantity"] == pytest.approx(1)
    assert item["linked_manual_order_average_fill_price"] == pytest.approx(5200)


def test_exit_shadow_review_queue_leaves_manual_link_null_without_reliable_match(
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

    response = client.get("/kis/exit-shadow/review-queue")

    item = response.json()["items"][0]
    assert item["linked_manual_order_id"] is None
    assert item["linked_manual_order_status"] is None


def test_exit_shadow_review_queue_does_not_call_broker_or_manual_submit(
    monkeypatch, client, db_session
):
    _add_shadow_run(db_session)
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_order",
        lambda *args, **kwargs: pytest.fail("queue must not call submit_order"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("queue must not call KIS cash submit"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("queue must not call manual submit"),
    )

    get_response = client.get("/kis/exit-shadow/review-queue")
    mark_response = client.post(
        "/kis/exit-shadow/review-queue/005930:stop_loss:cost_basis_pl_pct/mark-reviewed",
        json={"operator_note": "reviewed"},
    )
    dismiss_response = client.post(
        "/kis/exit-shadow/review-queue/005930:stop_loss:cost_basis_pl_pct/dismiss",
        json={"operator_note": "dismissed"},
    )

    assert get_response.status_code == 200
    assert mark_response.status_code == 200
    assert dismiss_response.status_code == 200


def _counts(db_session):
    return {
        "runs": db_session.query(TradeRunLog).count(),
        "signals": db_session.query(SignalLog).count(),
        "orders": db_session.query(OrderLog).count(),
        "queue_state": db_session.query(KisShadowExitReviewQueueState).count(),
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
    current_price: float | None = 4900,
    unrealized_pl: float | None = -200,
    unrealized_pl_pct: float | None = -0.02,
    suggested_quantity: float | None = 2,
    risk_flags: list[str] | None = None,
    minutes_ago: int = 0,
) -> TradeRunLog:
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=minutes_ago)
    candidate = {
        "symbol": symbol,
        "side": "sell",
        "quantity_available": suggested_quantity,
        "suggested_quantity": suggested_quantity,
        "trigger": trigger,
        "trigger_source": trigger_source,
        "current_price": current_price,
        "cost_basis": cost_basis,
        "current_value": current_value,
        "unrealized_pl": unrealized_pl,
        "unrealized_pl_pct": unrealized_pl_pct,
        "reason": "Shadow decision only.",
        "risk_flags": risk_flags
        if risk_flags is not None
        else [f"{trigger}_triggered" if trigger in {"stop_loss", "take_profit"} else trigger],
        "gating_notes": ["shadow_exit_only", "no_broker_submit"],
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "audit_metadata": {
            "source": "kis_exit_shadow_decision",
            "source_type": "dry_run_sell_simulation",
            "exit_trigger": trigger,
            "trigger_source": trigger_source,
            "shadow_real_order_submitted": False,
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
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "auto_buy_enabled": False,
        "auto_sell_enabled": False,
        "scheduler_real_order_enabled": False,
        "candidate": candidate,
        "candidates": [candidate],
        "candidates_evaluated": [candidate],
        "risk_flags": ["shadow_exit_only"] + candidate["risk_flags"],
        "gating_notes": ["shadow_exit_only", "no_broker_submit"],
        "created_at": now.isoformat(),
    }
    row = TradeRunLog(
        run_key=run_key,
        trigger_source="shadow_exit",
        symbol=symbol,
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
