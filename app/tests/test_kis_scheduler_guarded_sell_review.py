from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, TradeRunLog
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


def test_empty_review_returns_safe_empty_summary(client, db_session):
    response = client.get("/kis/scheduler/guarded-sell/review")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "kis_scheduler_guarded_sell_review"
    assert body["review_only"] is True
    assert body["sell_only"] is True
    assert body["buy_execution_allowed"] is False
    assert body["summary"]["total_attempts"] == 0
    assert body["summary"]["sell_only_invariant_ok"] is True
    assert body["summary"]["no_direct_scheduler_submit_invariant_ok"] is True
    assert body["recent_attempts"] == []
    assert body["submitted_sells"] == []
    assert body["blocked_attempts"] == []
    assert db_session.query(OrderLog).count() == 0


def test_review_aggregates_blocked_scheduler_guarded_sell_attempts(client, db_session):
    _seed_attempt(db_session, result="blocked", reason="scheduler_sell_disabled")
    _seed_attempt(db_session, result="blocked", reason="runtime_dry_run_true")

    body = client.get("/kis/scheduler/guarded-sell/review").json()

    assert body["summary"]["total_attempts"] == 2
    assert body["summary"]["blocked_count"] == 2
    assert body["summary"]["scheduler_sell_disabled_block_count"] == 1
    assert body["summary"]["dry_run_block_count"] == 1
    assert len(body["blocked_attempts"]) == 2


def test_review_aggregates_submitted_scheduler_guarded_sell_attempts(client, db_session):
    _seed_attempt(db_session, result="submitted", create_order=True)

    body = client.get("/kis/scheduler/guarded-sell/review").json()

    assert body["summary"]["submitted_count"] == 1
    assert body["summary"]["blocked_count"] == 0
    assert body["summary"]["stop_loss_submit_count"] == 1
    assert body["submitted_sells"][0]["symbol"] == "005930"
    assert body["submitted_sells"][0]["trigger"] == "stop_loss"
    assert body["submitted_sells"][0]["source"] == "kis_limited_auto_stop_loss"
    assert body["submitted_sells"][0]["source_type"] == "guarded_stop_loss_auto_sell"


def test_review_correlates_submitted_attempt_with_order_log(client, db_session):
    order = _seed_order(db_session, symbol="005930", kis_odno="ODNO-1")
    _seed_attempt(db_session, result="submitted", order_id=order.id)

    body = client.get("/kis/scheduler/guarded-sell/review").json()

    submitted = body["submitted_sells"][0]
    assert submitted["order_id"] == order.id
    assert submitted["broker_order_id"] == "BRK-005930"
    assert submitted["kis_odno"] == "ODNO-1"
    assert submitted["internal_status"] == InternalOrderStatus.SUBMITTED.value
    assert body["diagnostics"]["correlated_order_count"] == 1


def test_review_reports_top_block_reasons(client, db_session):
    _seed_attempt(db_session, result="blocked", reason="scheduler_real_orders_disabled")
    _seed_attempt(db_session, result="blocked", reason="scheduler_real_orders_disabled")
    _seed_attempt(db_session, result="blocked", reason="duplicate_open_sell_order")

    body = client.get("/kis/scheduler/guarded-sell/review").json()

    top = body["top_block_reasons"][0]
    assert top["reason"] == "scheduler_real_orders_disabled"
    assert top["label"] == "Scheduler real orders disabled"
    assert top["count"] >= 2


def test_review_reports_daily_usage(client, db_session):
    _seed_attempt(
        db_session,
        result="submitted",
        symbol="005930",
        trigger="stop_loss",
        order_id=101,
        daily_limit={"max_orders_per_day": 3, "daily_limit_remaining": 2},
    )
    _seed_attempt(
        db_session,
        result="submitted",
        symbol="035420",
        trigger="take_profit",
        order_id=102,
        daily_limit={"max_orders_per_day": 3, "daily_limit_remaining": 1},
    )

    body = client.get("/kis/scheduler/guarded-sell/review").json()

    usage = body["daily_usage"][0]
    assert usage["submitted_sell_count"] == 2
    assert usage["symbols"] == ["005930", "035420"]
    assert usage["triggers"] == ["stop_loss", "take_profit"]
    assert usage["daily_limit"] == 3
    assert usage["limit_exceeded"] is False
    assert body["summary"]["max_daily_sell_count_observed"] == 2


def test_review_filters_by_symbol(client, db_session):
    _seed_attempt(db_session, result="blocked", symbol="005930")
    _seed_attempt(db_session, result="submitted", symbol="035420", order_id=55)

    body = client.get("/kis/scheduler/guarded-sell/review?symbol=035420").json()

    assert body["summary"]["total_attempts"] == 1
    assert body["recent_attempts"][0]["symbol"] == "035420"
    assert body["summary"]["submitted_count"] == 1


def test_review_respects_limit_days_and_result_filters(client, db_session):
    _seed_attempt(db_session, result="blocked", symbol="005930", created_days_ago=40)
    _seed_attempt(db_session, result="blocked", symbol="035420", created_days_ago=2)
    _seed_attempt(db_session, result="submitted", symbol="000660", order_id=77)

    body = client.get(
        "/kis/scheduler/guarded-sell/review?days=30&limit=1&result=blocked"
    ).json()

    assert body["summary"]["total_attempts"] == 1
    assert body["recent_attempts"][0]["result"] == "blocked"
    assert body["recent_attempts"][0]["symbol"] == "035420"
    assert body["diagnostics"]["source_row_count"] == 2


def test_review_detects_buy_execution_allowed_violation(client, db_session):
    _seed_attempt(
        db_session,
        result="blocked",
        response_overrides={"buy_execution_allowed": True},
    )

    body = client.get("/kis/scheduler/guarded-sell/review").json()

    assert body["summary"]["sell_only_invariant_ok"] is False
    assert "scheduler_guarded_sell_buy_execution_allowed" in _violation_reasons(body)


def test_review_detects_action_buy_violation(client, db_session):
    _seed_attempt(db_session, result="blocked", action="buy")

    body = client.get("/kis/scheduler/guarded-sell/review").json()

    assert body["summary"]["sell_only_invariant_ok"] is False
    assert "scheduler_guarded_sell_action_buy" in _violation_reasons(body)


def test_review_detects_blocked_attempt_with_real_order_submitted(client, db_session):
    _seed_attempt(
        db_session,
        result="blocked",
        response_overrides={"real_order_submitted": True},
    )

    body = client.get("/kis/scheduler/guarded-sell/review").json()

    assert "blocked_attempt_real_order_submitted" in _violation_reasons(body)


def test_review_detects_submitted_attempt_missing_order_id(client, db_session):
    _seed_attempt(db_session, result="submitted", order_id=None)

    body = client.get("/kis/scheduler/guarded-sell/review").json()

    assert body["summary"]["submitted_rows_have_order_ids"] is False
    assert "submitted_attempt_missing_order_id" in _violation_reasons(body)


def test_review_detects_submitted_attempt_while_dry_run(client, db_session):
    _seed_attempt(
        db_session,
        result="submitted",
        order_id=123,
        checks_overrides={"dry_run": True},
        safety_overrides={"dry_run": True},
    )

    body = client.get("/kis/scheduler/guarded-sell/review").json()

    assert "submitted_attempt_while_dry_run" in _violation_reasons(body)


def test_review_detects_scheduler_sell_disabled_but_submitted(client, db_session):
    _seed_attempt(
        db_session,
        result="submitted",
        order_id=123,
        checks_overrides={"kis_scheduler_sell_enabled": False},
        safety_overrides={"kis_scheduler_sell_enabled": False},
    )

    body = client.get("/kis/scheduler/guarded-sell/review").json()

    assert "submitted_attempt_scheduler_sell_disabled" in _violation_reasons(body)


def test_review_detects_daily_limit_exceeded(client, db_session):
    _seed_attempt(
        db_session,
        result="submitted",
        symbol="005930",
        order_id=1,
        daily_limit={"max_orders_per_day": 1, "daily_limit_remaining": 0},
    )
    _seed_attempt(
        db_session,
        result="submitted",
        symbol="035420",
        order_id=2,
        daily_limit={"max_orders_per_day": 1, "daily_limit_remaining": 0},
    )

    body = client.get("/kis/scheduler/guarded-sell/review").json()

    assert body["daily_usage"][0]["limit_exceeded"] is True
    assert "submitted_sell_daily_limit_exceeded" in _violation_reasons(body)


def test_include_raw_false_hides_raw_payload(client, db_session):
    _seed_attempt(db_session, result="blocked")

    body = client.get("/kis/scheduler/guarded-sell/review?include_raw=false").json()

    assert "raw_payload" not in body["recent_attempts"][0]


def test_include_raw_true_includes_raw_payload(client, db_session):
    _seed_attempt(db_session, result="blocked")

    body = client.get("/kis/scheduler/guarded-sell/review?include_raw=true").json()

    assert body["recent_attempts"][0]["raw_payload"]["provider"] == "kis"


def test_review_endpoint_does_not_create_order_log(client, db_session):
    _seed_attempt(db_session, result="blocked")
    before = db_session.query(OrderLog).count()

    response = client.get("/kis/scheduler/guarded-sell/review")

    assert response.status_code == 200
    assert db_session.query(OrderLog).count() == before
    assert response.json()["order_log_created"] is False


def test_review_endpoint_does_not_call_broker_or_manual_submit(
    monkeypatch,
    client,
    db_session,
):
    _seed_attempt(db_session, result="blocked")
    monkeypatch.setattr(
        "app.routes.kis._client",
        lambda db: pytest.fail("review endpoint must not create a broker client"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("manual path must not run"),
    )

    body = client.get("/kis/scheduler/guarded-sell/review").json()

    assert body["review_only"] is True
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False


def _seed_attempt(
    db_session,
    *,
    result: str,
    symbol: str = "005930",
    company_name: str = "Samsung Electronics",
    trigger: str = "stop_loss",
    action: str | None = None,
    reason: str | None = None,
    order_id: int | None = 123,
    create_order: bool = False,
    daily_limit: dict | None = None,
    checks_overrides: dict | None = None,
    safety_overrides: dict | None = None,
    response_overrides: dict | None = None,
    created_days_ago: int = 1,
) -> TradeRunLog:
    if create_order:
        order = _seed_order(db_session, symbol=symbol)
        order_id = order.id
    submitted = result == "submitted"
    primary_reason = reason or (
        "stop_loss_auto_sell_submitted" if submitted else "scheduler_sell_disabled"
    )
    checks = {
        "kis_scheduler_allow_real_orders": True,
        "configured_kis_scheduler_allow_real_orders": True,
        "kis_scheduler_sell_enabled": True,
        "dry_run": False,
        "kill_switch": False,
        "kis_real_order_enabled": True,
        "kis_live_auto_sell_enabled": True,
        "kis_limited_auto_stop_loss_enabled": trigger == "stop_loss",
        "kis_limited_auto_take_profit_enabled": trigger == "take_profit",
    }
    checks.update(checks_overrides or {})
    safety = {
        "scheduler_sell_only": True,
        "sell_only": True,
        "buy_execution_allowed": False,
        "scheduler_buy_execution_blocked": True,
        "no_direct_broker_submit_from_scheduler": True,
        "no_direct_manual_submit_from_scheduler": True,
        "existing_limited_auto_sell_path_reused": True,
        "limited_auto_buy_not_called_in_submit_mode": True,
        "scheduler_real_orders_enabled": True,
        "dry_run": checks["dry_run"],
        "kill_switch": checks["kill_switch"],
        "kis_real_order_enabled": checks["kis_real_order_enabled"],
        "kis_live_auto_sell_enabled": checks["kis_live_auto_sell_enabled"],
        "kis_scheduler_allow_real_orders": checks["kis_scheduler_allow_real_orders"],
        "kis_scheduler_sell_enabled": checks["kis_scheduler_sell_enabled"],
        "real_order_submitted": submitted,
        "broker_submit_called": submitted,
        "manual_submit_called": submitted,
    }
    safety.update(safety_overrides or {})
    daily = daily_limit or {
        "max_orders_per_day": 1,
        "submitted_count_today": 1 if submitted else 0,
        "daily_limit_remaining": 0 if submitted else 1,
        "daily_limit_reached": submitted,
    }
    sell_result = None
    block_reasons = [] if submitted else [primary_reason]
    if submitted:
        sell_result = {
            "result": "submitted",
            "action": "sell",
            "reason": primary_reason,
            "source": "kis_limited_auto_stop_loss",
            "source_type": "guarded_stop_loss_auto_sell",
            "mode": "kis_limited_auto_stop_loss_run",
            "trigger_source": "kis_limited_auto_sell",
            "symbol": symbol,
            "company_name": company_name,
            "quantity": 1,
            "current_price": 70000,
            "estimated_notional": 70000,
            "trigger": trigger,
            "order_id": order_id,
            "order_log_id": order_id,
            "broker_order_id": f"BRK-{symbol}",
            "kis_odno": f"ODNO-{symbol}",
            "runtime_safety_snapshot": {
                "dry_run": checks["dry_run"],
                "kill_switch": checks["kill_switch"],
                "kis_scheduler_sell_enabled": checks["kis_scheduler_sell_enabled"],
                "kis_scheduler_allow_real_orders": checks[
                    "kis_scheduler_allow_real_orders"
                ],
            },
            "market_session_snapshot": {"sell_session_allowed": True},
            "duplicate_order_check": {"duplicate_open_sell_order": False},
            "daily_limit": daily,
            "validation_summary": {"validated_for_submission": True},
            "validation_called": True,
            "real_order_submitted": True,
            "broker_submit_called": True,
            "manual_submit_called": True,
        }
    payload = {
        "provider": "kis",
        "market": "KR",
        "mode": "kis_scheduler_guarded_sell",
        "source": "kis_scheduler_guarded_sell",
        "source_type": "scheduler_guarded_sell_execution",
        "trigger_source": "scheduler_guarded_sell",
        "requested_trigger_source": "scheduler",
        "slot_label": "position_management",
        "sell_only": True,
        "scheduler_sell_only": True,
        "buy_execution_allowed": False,
        "scheduler_buy_execution_blocked": True,
        "scheduler_real_orders_enabled": True,
        "real_order_submit_allowed": submitted,
        "result": result,
        "action": action or ("sell" if submitted else "hold"),
        "reason": primary_reason,
        "primary_block_reason": None if submitted else primary_reason,
        "summary": {
            "result": result,
            "action": action or ("sell" if submitted else "hold"),
            "primary_block_reason": None if submitted else primary_reason,
            "sell_only": True,
            "buy_execution_allowed": False,
            "scheduler_real_orders_enabled": True,
            "scheduler_sell_enabled": checks["kis_scheduler_sell_enabled"],
            "daily_limit_remaining": daily["daily_limit_remaining"],
            "symbol": symbol if submitted else None,
            "quantity": 1 if submitted else None,
            "trigger": trigger if submitted else None,
            "order_id": order_id if submitted else None,
            "broker_order_id": f"BRK-{symbol}" if submitted else None,
            "kis_odno": f"ODNO-{symbol}" if submitted else None,
        },
        "sell_result": sell_result,
        "buy_result": {
            "result": "skipped",
            "action": "hold",
            "reason": "buy_scheduler_execution_disabled",
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "validation_called": False,
        },
        "block_reasons": block_reasons,
        "safety": safety,
        "checks": checks,
        "daily_limit": daily,
        "duplicate_order_check": {"duplicate_open_sell_order": False},
        "market_session_check": {"sell_session_allowed": True},
        "real_order_submitted": submitted,
        "broker_submit_called": submitted,
        "manual_submit_called": submitted,
        "order_id": order_id if submitted else None,
        "order_log_id": order_id if submitted else None,
        "broker_order_id": f"BRK-{symbol}" if submitted else None,
        "kis_odno": f"ODNO-{symbol}" if submitted else None,
        "symbol": symbol,
        "company_name": company_name,
        "quantity": 1 if submitted else None,
        "trigger": trigger if submitted else None,
    }
    payload.update(response_overrides or {})
    created_at = (datetime.now(UTC) - timedelta(days=created_days_ago)).replace(
        tzinfo=None
    )
    row = TradeRunLog(
        run_key=f"scheduler-guarded-sell-review-{symbol}-{created_days_ago}-{result}",
        trigger_source="scheduler_guarded_sell",
        symbol=symbol,
        mode="kis_scheduler_guarded_sell",
        stage="done",
        result=result,
        reason=primary_reason,
        order_id=order_id if submitted else None,
        request_payload=json.dumps(
            {
                "mode": "kis_scheduler_guarded_sell",
                "trigger_source": "scheduler_guarded_sell",
                "slot_label": "position_management",
            }
        ),
        response_payload=json.dumps(payload),
        created_at=created_at,
    )
    db_session.add(row)
    db_session.commit()
    return row


def _seed_order(
    db_session,
    *,
    symbol: str,
    kis_odno: str | None = None,
) -> OrderLog:
    row = OrderLog(
        broker="kis",
        market="KR",
        symbol=symbol,
        side="sell",
        order_type="market",
        qty=1,
        requested_qty=1,
        internal_status=InternalOrderStatus.SUBMITTED.value,
        broker_status="submitted",
        broker_order_id=f"BRK-{symbol}",
        kis_odno=kis_odno or f"ODNO-{symbol}",
        submitted_at=datetime.now(UTC).replace(tzinfo=None),
        request_payload=json.dumps(
            {
                "mode": "kis_limited_auto_stop_loss_run",
                "source": "kis_limited_auto_stop_loss",
                "source_type": "guarded_stop_loss_auto_sell",
                "trigger_source": "kis_limited_auto_sell",
                "validation_called": True,
            }
        ),
        response_payload=json.dumps(
            {
                "mode": "kis_limited_auto_stop_loss_run",
                "source": "kis_limited_auto_stop_loss",
                "source_type": "guarded_stop_loss_auto_sell",
                "real_order_submitted": True,
                "broker_submit_called": True,
                "manual_submit_called": True,
            }
        ),
        created_at=(datetime.now(UTC) - timedelta(days=1)).replace(tzinfo=None),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _violation_reasons(body: dict) -> list[str]:
    return [item["reason"] for item in body["safety_violations"]]
