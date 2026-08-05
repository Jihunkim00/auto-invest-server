from __future__ import annotations

from app.db.models import OrderLog, PositionLifecycle, RuntimeSetting, SignalLog, TradeRunLog
from app.services.operation_test3_position_management_service import BUY_FLAGS
from app.services.runtime_setting_service import RuntimeSettingService
from app.tests.test_operation_test3_position_management import (
    FakeClient,
    FakeSellService,
    NOW,
    _enable_live_settings,
    _open_lifecycle,
    _position,
    _service,
)


def _checks_by_key(payload: dict) -> dict[str, dict]:
    return {item["key"]: item for item in payload["checks"]}


def test_live_readiness_safe_monitoring_state_is_blocked_and_read_only(db_session):
    lifecycle = _open_lifecycle(db_session)
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": True,
            "kill_switch": True,
            "operation_test3_enabled": True,
            "operation_test3_scheduler_enabled": True,
            "operation_test3_position_management_enabled": True,
            "operation_test3_allow_real_orders": False,
            "operation_test3_stop_loss_enabled": True,
            "operation_test3_take_profit_enabled": False,
            **{key: False for key in BUY_FLAGS},
        },
    )
    before_counts = {
        "runtime": db_session.query(RuntimeSetting).count(),
        "lifecycle": db_session.query(PositionLifecycle).count(),
        "orders": db_session.query(OrderLog).count(),
        "signals": db_session.query(SignalLog).count(),
        "runs": db_session.query(TradeRunLog).count(),
    }
    before_lifecycle = (
        lifecycle.status,
        lifecycle.manual_review_required,
        lifecycle.exit_reason,
        lifecycle.last_price,
        lifecycle.last_evaluated_at,
    )
    client = FakeClient(positions=[_position(99.0)])
    sell = FakeSellService()

    result = _service(client, sell).live_readiness(db_session, now=NOW)

    db_session.refresh(lifecycle)
    assert result["mode"] == "operation_test3_live_readiness"
    assert result["read_only"] is True
    assert result["status"] == "blocked"
    assert result["live_ready"] is False
    assert {"dry_run_true", "kill_switch_enabled", "operation_test3_real_orders_disabled"}.issubset(
        set(result["blocking_reasons"])
    )
    checks = _checks_by_key(result)
    assert checks["take_profit_disabled"]["passed"] is True
    assert checks["take_profit_disabled"]["blocking"] is False
    assert checks["all_buy_flags_false"]["passed"] is True
    assert result["safety"] == {
        "read_only": True,
        "preflight_only": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "buy_service_called": False,
    }
    assert result["broker_submit_called"] is False
    assert result["manual_submit_called"] is False
    assert result["buy_service_called"] is False
    assert sell.calls == 0
    assert client.list_positions_calls == 1
    assert client.list_open_orders_calls == 1
    assert before_counts == {
        "runtime": db_session.query(RuntimeSetting).count(),
        "lifecycle": db_session.query(PositionLifecycle).count(),
        "orders": db_session.query(OrderLog).count(),
        "signals": db_session.query(SignalLog).count(),
        "runs": db_session.query(TradeRunLog).count(),
    }
    assert before_lifecycle == (
        lifecycle.status,
        lifecycle.manual_review_required,
        lifecycle.exit_reason,
        lifecycle.last_price,
        lifecycle.last_evaluated_at,
    )


def test_live_readiness_transient_position_read_success_can_be_ready(db_session):
    lifecycle = _open_lifecycle(db_session)
    _enable_live_settings(db_session, operation_test3_scheduler_enabled=True)
    client = FakeClient(positions_sequence=[TimeoutError("temporary"), [_position(99.0)]])

    result = _service(client, FakeSellService()).live_readiness(db_session, now=NOW)

    assert result["status"] == "ready"
    assert result["live_ready"] is True
    assert result["symbol"] == lifecycle.symbol
    assert result["lifecycle_id"] == lifecycle.id
    assert result["entry_order_id"] == lifecycle.entry_order_id
    assert result["quantity"] == lifecycle.quantity
    assert result["blocking_reasons"] == []
    assert result["review_reasons"] == []
    assert result["broker_position_read"]["attempt_count"] == 2
    assert result["broker_position_read"]["retry_attempted"] is True
    assert result["broker_position_read"]["retry_succeeded"] is True
    assert result["broker_position_read"]["final_status"] == "ok"
    checks = _checks_by_key(result)
    for key in [
        "operation_test3_enabled",
        "operation_test3_scheduler_enabled",
        "operation_test3_position_management_enabled",
        "operation_test3_allow_real_orders",
        "dry_run_false",
        "kill_switch_false",
        "kis_enabled",
        "kis_real_order_enabled",
        "active_lifecycle_exactly_one",
        "lifecycle_status_open",
        "broker_positions_readable",
        "broker_position_exactly_one",
        "lifecycle_broker_symbol_match",
        "lifecycle_broker_quantity_match",
        "valid_cost_basis",
        "no_broker_open_sell_order",
        "no_local_pending_sell_order",
        "daily_sell_limit_available",
        "market_session_sell_allowed",
        "all_buy_flags_false",
        "stop_loss_enabled",
    ]:
        assert checks[key]["passed"] is True


def test_live_readiness_double_position_read_failure_requires_review_without_logs(db_session):
    _open_lifecycle(db_session)
    _enable_live_settings(db_session, operation_test3_scheduler_enabled=True)
    client = FakeClient(positions_sequence=[TimeoutError("temporary"), RuntimeError("still down")])
    before_runs = db_session.query(TradeRunLog).count()

    result = _service(client, FakeSellService()).live_readiness(db_session, now=NOW)

    assert result["status"] == "review_required"
    assert result["live_ready"] is False
    assert "broker_positions_unavailable" in result["review_reasons"]
    assert result["broker_position_read"]["attempt_count"] == 2
    assert result["broker_position_read"]["retry_attempted"] is True
    assert result["broker_position_read"]["retry_succeeded"] is False
    assert result["broker_position_read"]["final_status"] == "unavailable"
    assert result["broker_submit_called"] is False
    assert db_session.query(TradeRunLog).count() == before_runs


def test_live_readiness_reports_lifecycle_broker_mismatch_checks(db_session):
    _open_lifecycle(db_session)
    _enable_live_settings(db_session, operation_test3_scheduler_enabled=True)

    result = _service(
        FakeClient(positions=[_position(99.0, symbol="005930")]),
        FakeSellService(),
    ).live_readiness(db_session, now=NOW)

    checks = _checks_by_key(result)
    assert result["status"] == "review_required"
    assert result["live_ready"] is False
    assert "broker_position_symbol_mismatch" in result["review_reasons"]
    assert checks["lifecycle_broker_symbol_match"]["passed"] is False
    assert checks["lifecycle_broker_quantity_match"]["passed"] is True
    assert checks["broker_position_exactly_one"]["passed"] is True


def test_live_readiness_does_not_clear_non_transient_manual_review(db_session):
    lifecycle = _open_lifecycle(
        db_session,
        manual_review_required=True,
        exit_reason="sell_submit_uncertain_manual_review_required",
    )
    _enable_live_settings(db_session, operation_test3_scheduler_enabled=True)

    result = _service(FakeClient(positions=[_position(99.0)]), FakeSellService()).live_readiness(
        db_session,
        now=NOW,
    )

    db_session.refresh(lifecycle)
    assert result["status"] == "review_required"
    assert "manual_review_required" in result["review_reasons"]
    assert lifecycle.manual_review_required is True
    assert lifecycle.exit_reason == "sell_submit_uncertain_manual_review_required"