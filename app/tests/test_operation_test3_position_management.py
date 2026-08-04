from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, PositionLifecycle, RuntimeSetting, TradeRunLog
from app.main import app
from app.services.operation_test3_position_management_service import (
    HOLD,
    REVIEW,
    SELL_READY,
    TAKE_PROFIT_READY,
    BUY_FLAGS,
    OperationTest3PositionManagementService,
)
from app.services.runtime_setting_service import RuntimeSettingService

NOW = datetime(2026, 8, 4, 1, 0, tzinfo=UTC)


class FakeClient:
    def __init__(
        self,
        *,
        positions=None,
        positions_sequence=None,
        open_orders=None,
        kis_enabled=True,
        kis_real_order_enabled=True,
    ):
        self.positions = positions if positions is not None else []
        self.positions_sequence = list(positions_sequence or [])
        self.open_orders = open_orders or []
        self.list_positions_calls = 0
        self.list_open_orders_calls = 0
        self.settings = SimpleNamespace(
            kis_enabled=kis_enabled,
            kis_real_order_enabled=kis_real_order_enabled,
            kis_confirmation_phrase="I UNDERSTAND THIS WILL PLACE A REAL KIS ORDER",
        )

    def list_positions(self):
        self.list_positions_calls += 1
        if self.positions_sequence:
            if len(self.positions_sequence) > 1:
                return self.positions_sequence.pop(0)
            return self.positions_sequence[0]
        return self.positions

    def list_open_orders(self):
        self.list_open_orders_calls += 1
        return self.open_orders


class OpenSessionService:
    def get_session_status(self, market, **kwargs):
        return {
            "market": market,
            "timezone": "Asia/Seoul",
            "is_market_open": True,
            "is_entry_allowed_now": True,
            "is_holiday": False,
            "closure_reason": None,
        }


class ClosedSessionService:
    def get_session_status(self, market, **kwargs):
        return {
            "market": market,
            "timezone": "Asia/Seoul",
            "is_market_open": False,
            "is_entry_allowed_now": False,
            "is_holiday": False,
            "closure_reason": "market_closed",
        }


class FakeSellService:
    def __init__(self, *, status=InternalOrderStatus.SUBMITTED.value, result=None, raise_after_order=False):
        self.status = status
        self.result = result
        self.raise_after_order = raise_after_order
        self.calls = 0

    def run_once(self, db, *, now=None):
        self.calls += 1
        if self.result is not None:
            return dict(self.result)
        order = OrderLog(
            broker="kis",
            market="KR",
            symbol="009240",
            side="sell",
            order_type="market",
            qty=1,
            requested_qty=1,
            internal_status=self.status,
            request_payload=json.dumps({"source": "operation_test3_fake_sell"}),
            response_payload=json.dumps({"source": "operation_test3_fake_sell"}),
            created_at=now or NOW,
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        if self.raise_after_order:
            raise TimeoutError("uncertain result")
        return {
            "result": "filled" if self.status == InternalOrderStatus.FILLED.value else "submitted",
            "reason": "fake_sell_result",
            "real_order_submitted": self.status not in {
                InternalOrderStatus.REJECTED.value,
                InternalOrderStatus.CANCELED.value,
            },
            "broker_submit_called": True,
            "manual_submit_called": True,
            "order_id": order.id,
            "order_log_id": order.id,
            "internal_status": self.status,
        }


def test_default_runtime_flags_are_safe_and_read_only(db_session):
    settings = RuntimeSettingService().get_settings_read_only(db_session)

    assert db_session.query(RuntimeSetting).count() == 0
    assert settings["operation_test3_enabled"] is False
    assert settings["operation_test3_scheduler_enabled"] is False
    assert settings["operation_test3_allow_real_orders"] is False
    assert settings["operation_test3_position_management_enabled"] is False
    assert settings["operation_test3_stop_loss_enabled"] is True
    assert settings["operation_test3_take_profit_enabled"] is False
    assert settings["operation_test3_max_sell_orders_per_day"] == 1


def test_no_active_lifecycle_skips_without_broker_submit(db_session):
    sell = FakeSellService()
    result = _service(FakeClient(positions=[]), sell).run_once(db_session, now=NOW)

    assert result["result"] == "skipped"
    assert result["reason"] == "no_open_lifecycle"
    assert result["broker_submit_called"] is False
    assert sell.calls == 0


def test_lifecycle_presence_forces_all_buy_flags_false(db_session):
    RuntimeSettingService().update_settings(db_session, {key: True for key in BUY_FLAGS})
    _open_lifecycle(db_session)

    _service(FakeClient(positions=[_position(101.0)]), FakeSellService()).preflight_once(db_session, now=NOW)

    settings = RuntimeSettingService().get_settings(db_session)
    assert all(settings[key] is False for key in BUY_FLAGS)


def test_hold_when_stop_loss_not_reached(db_session):
    _open_lifecycle(db_session)
    sell = FakeSellService()

    result = _service(FakeClient(positions=[_position(99.0)]), sell).run_once(db_session, now=NOW)

    assert result["action"] == HOLD
    assert result["reason"] == "no_exit_condition"
    assert result["broker_submit_called"] is False
    assert sell.calls == 0


def test_stop_loss_reached_with_live_flags_off_blocks_without_sell_call(db_session):
    _open_lifecycle(db_session)
    sell = FakeSellService()

    result = _service(FakeClient(positions=[_position(97.0)]), sell).run_once(db_session, now=NOW)

    assert result["action"] == SELL_READY
    assert result["result"] == "blocked"
    assert "operation_test3_disabled" in result["block_reasons"]
    assert result["broker_submit_called"] is False
    assert sell.calls == 0


def test_stop_loss_reached_with_all_gates_pass_sells_once_and_closes_to_closing(db_session):
    lifecycle = _open_lifecycle(db_session)
    _enable_live_settings(db_session)
    sell = FakeSellService(status=InternalOrderStatus.SUBMITTED.value)

    result = _service(FakeClient(positions=[_position(97.0)]), sell).run_once(db_session, now=NOW)

    db_session.refresh(lifecycle)
    assert result["result"] == "submitted"
    assert result["trigger"] == "stop_loss"
    assert result["broker_submit_called"] is True
    assert sell.calls == 1
    assert lifecycle.status == "closing"
    assert lifecycle.exit_order_id is not None
    assert lifecycle.exit_order_status == InternalOrderStatus.SUBMITTED.value


def test_take_profit_off_stays_hold_without_sell_call(db_session):
    _open_lifecycle(db_session)
    _enable_live_settings(db_session, operation_test3_take_profit_enabled=False)
    sell = FakeSellService()

    result = _service(FakeClient(positions=[_position(103.0)]), sell).run_once(db_session, now=NOW)

    assert result["action"] == HOLD
    assert result["take_profit_triggered"] is True
    assert result["reason"] == "take_profit_execution_disabled"
    assert result["broker_submit_called"] is False
    assert sell.calls == 0


def test_take_profit_on_with_all_gates_pass_uses_existing_sell_path(db_session):
    lifecycle = _open_lifecycle(db_session)
    _enable_live_settings(db_session, operation_test3_take_profit_enabled=True)
    sell = FakeSellService(status=InternalOrderStatus.ACCEPTED.value)

    result = _service(FakeClient(positions=[_position(103.0)]), sell).run_once(db_session, now=NOW)

    db_session.refresh(lifecycle)
    assert result["action"] == TAKE_PROFIT_READY
    assert result["trigger"] == "take_profit"
    assert result["result"] == "submitted"
    assert result["execution_path"] == "KisLimitedAutoSellService"
    assert sell.calls == 1
    assert lifecycle.status == "closing"


def test_stop_loss_priority_when_both_triggers_are_true(monkeypatch, db_session):
    import app.services.operation_test3_position_management_service as module

    _open_lifecycle(db_session)
    _enable_live_settings(db_session, operation_test3_take_profit_enabled=True)
    monkeypatch.setattr(module, "_take_profit_threshold_price", lambda lifecycle: 97.0)
    sell = FakeSellService(status=InternalOrderStatus.SUBMITTED.value)

    result = _service(FakeClient(positions=[_position(97.0)]), sell).run_once(db_session, now=NOW)

    assert result["trigger"] == "stop_loss"
    assert result["take_profit_triggered_ignored"] is True
    assert sell.calls == 1

@pytest.mark.parametrize(
    ("settings_patch", "expected_reason"),
    [
        ({"dry_run": True}, "dry_run_true"),
        ({"kill_switch": True}, "kill_switch_enabled"),
    ],
)
def test_global_runtime_safety_gates_block_sell(db_session, settings_patch, expected_reason):
    _open_lifecycle(db_session)
    _enable_live_settings(db_session, **settings_patch)
    sell = FakeSellService()

    result = _service(FakeClient(positions=[_position(97.0)]), sell).run_once(db_session, now=NOW)

    assert expected_reason in result["block_reasons"]
    assert result["broker_submit_called"] is False
    assert sell.calls == 0


def test_kis_real_order_disabled_blocks_sell(db_session):
    _open_lifecycle(db_session)
    _enable_live_settings(db_session)
    sell = FakeSellService()

    result = _service(
        FakeClient(positions=[_position(97.0)], kis_real_order_enabled=False),
        sell,
    ).run_once(db_session, now=NOW)

    assert "kis_real_order_disabled" in result["block_reasons"]
    assert result["broker_submit_called"] is False
    assert sell.calls == 0


def test_closed_market_blocks_sell(db_session):
    _open_lifecycle(db_session)
    _enable_live_settings(db_session)
    sell = FakeSellService()

    result = _service(
        FakeClient(positions=[_position(97.0)]),
        sell,
        session_service=ClosedSessionService(),
    ).run_once(db_session, now=NOW)

    assert "sell_session_not_allowed" in result["block_reasons"]
    assert result["broker_submit_called"] is False
    assert sell.calls == 0


def test_broker_open_sell_order_blocks_sell(db_session):
    lifecycle = _open_lifecycle(db_session)
    _enable_live_settings(db_session)
    sell = FakeSellService()
    client = FakeClient(
        positions=[_position(97.0)],
        open_orders=[{"symbol": lifecycle.symbol, "side": "sell", "qty": 1}],
    )

    result = _service(client, sell).run_once(db_session, now=NOW)

    db_session.refresh(lifecycle)
    assert "broker_open_sell_order_exists" in result["block_reasons"]
    assert result["broker_submit_called"] is False
    assert lifecycle.status == "closing"
    assert sell.calls == 0


def test_local_pending_sell_order_blocks_sell(db_session):
    lifecycle = _open_lifecycle(db_session)
    _enable_live_settings(db_session)
    order = _sell_order(db_session, status=InternalOrderStatus.PENDING.value)
    sell = FakeSellService()

    result = _service(FakeClient(positions=[_position(97.0)]), sell).run_once(db_session, now=NOW)

    db_session.refresh(lifecycle)
    assert "local_pending_sell_order_exists" in result["block_reasons"]
    assert result["broker_submit_called"] is False
    assert lifecycle.status == "closing"
    assert lifecycle.exit_order_id == order.id
    assert sell.calls == 0


def test_invalid_cost_basis_requires_review_without_sell(db_session):
    lifecycle = _open_lifecycle(db_session, entry_price=0.0, cost_basis=0.0)
    _enable_live_settings(db_session)
    sell = FakeSellService()

    result = _service(FakeClient(positions=[_position(97.0)]), sell).run_once(db_session, now=NOW)

    db_session.refresh(lifecycle)
    assert result["action"] == REVIEW
    assert result["manual_review_required"] is True
    assert lifecycle.manual_review_required is True
    assert sell.calls == 0


def test_symbol_mismatch_blocks_without_sell(db_session):
    _open_lifecycle(db_session)
    _enable_live_settings(db_session)
    sell = FakeSellService()

    result = _service(FakeClient(positions=[_position(97.0, symbol="005930")]), sell).run_once(db_session, now=NOW)

    assert result["action"] == REVIEW
    assert "broker_position_symbol_mismatch" in result["block_reasons"]
    assert sell.calls == 0


def test_quantity_mismatch_blocks_without_sell(db_session):
    _open_lifecycle(db_session)
    _enable_live_settings(db_session)
    sell = FakeSellService()

    result = _service(FakeClient(positions=[_position(97.0, qty=2)]), sell).run_once(db_session, now=NOW)

    assert result["action"] == REVIEW
    assert "broker_position_quantity_mismatch" in result["block_reasons"]
    assert sell.calls == 0


def test_daily_sell_limit_blocks_without_sell(db_session):
    _open_lifecycle(db_session)
    _enable_live_settings(db_session)
    _sell_order(db_session, status=InternalOrderStatus.FILLED.value)
    sell = FakeSellService()

    result = _service(FakeClient(positions=[_position(97.0)]), sell).run_once(db_session, now=NOW)

    assert "daily_sell_limit_reached" in result["block_reasons"]
    assert result["broker_submit_called"] is False
    assert sell.calls == 0


def test_same_slot_duplicate_blocks_second_execution(db_session):
    _open_lifecycle(db_session)
    _enable_live_settings(db_session)
    sell = FakeSellService(status=InternalOrderStatus.REJECTED.value)
    service = _service(FakeClient(positions=[_position(97.0)]), sell)

    first = service.run_once(db_session, slot_label="10:00", now=NOW)
    second = service.run_once(db_session, slot_label="10:00", now=NOW)

    assert first["broker_submit_called"] is True
    assert second["result"] == "skipped"
    assert second["reason"] == "scheduler_slot_already_ran"
    assert second["broker_submit_called"] is False
    assert sell.calls == 1


def test_submitted_sell_moves_lifecycle_to_closing(db_session):
    lifecycle = _open_lifecycle(db_session)
    _enable_live_settings(db_session)

    result = _service(
        FakeClient(positions=[_position(97.0)]),
        FakeSellService(status=InternalOrderStatus.PARTIALLY_FILLED.value),
    ).run_once(db_session, now=NOW)

    db_session.refresh(lifecycle)
    assert result["result"] == "submitted"
    assert lifecycle.status == "closing"
    assert lifecycle.exit_order_status == InternalOrderStatus.PARTIALLY_FILLED.value


def test_filled_sell_closes_only_after_broker_position_zero(db_session):
    lifecycle = _open_lifecycle(db_session)
    _enable_live_settings(db_session)
    client = FakeClient(positions_sequence=[[_position(97.0)], []])

    result = _service(client, FakeSellService(status=InternalOrderStatus.FILLED.value)).run_once(db_session, now=NOW)

    db_session.refresh(lifecycle)
    assert result["result"] == "filled"
    assert lifecycle.status == "closed"
    assert lifecycle.closed_at is not None
    assert lifecycle.manual_review_required is False


def test_rejected_sell_reopens_lifecycle_and_requires_review(db_session):
    lifecycle = _open_lifecycle(db_session)
    _enable_live_settings(db_session)

    result = _service(
        FakeClient(positions=[_position(97.0)]),
        FakeSellService(status=InternalOrderStatus.REJECTED.value),
    ).run_once(db_session, now=NOW)

    db_session.refresh(lifecycle)
    assert result["result"] == "manual_review"
    assert lifecycle.status == "open"
    assert lifecycle.manual_review_required is True
    assert lifecycle.exit_order_status == InternalOrderStatus.REJECTED.value


def test_uncertain_response_locks_against_retry(db_session):
    lifecycle = _open_lifecycle(db_session)
    _enable_live_settings(db_session)
    sell = FakeSellService(status=InternalOrderStatus.REQUESTED.value, raise_after_order=True)
    service = _service(FakeClient(positions=[_position(97.0)]), sell)

    first = service.run_once(db_session, now=NOW)
    second = service.run_once(db_session, now=NOW)

    db_session.refresh(lifecycle)
    assert first["result"] == "manual_review"
    assert lifecycle.status == "closing"
    assert lifecycle.manual_review_required is True
    assert second["reason"] == "exit_order_already_pending"
    assert second["broker_submit_called"] is False
    assert sell.calls == 1


def test_status_and_preflight_never_call_sell_path(db_session):
    _open_lifecycle(db_session)
    sell = FakeSellService()
    service = _service(FakeClient(positions=[_position(97.0)]), sell)

    status = service.status(db_session)
    preflight = service.preflight_once(db_session, now=NOW)

    assert status["broker_submit_called"] is False
    assert preflight["broker_submit_called"] is False
    assert sell.calls == 0

def test_facade_routes_delegate_and_enable_does_not_run(monkeypatch, db_session):
    calls = []

    def override_get_db():
        yield db_session

    def fake_status(self, db):
        calls.append(("status", {}))
        return {"status": "ok", "broker_submit_called": False}

    def fake_preflight(self, db, slot_label=None, **kwargs):
        calls.append(("preflight", {"slot_label": slot_label, **kwargs}))
        return {"mode": "operation_test3_position_management_preflight", "broker_submit_called": False}

    def fake_run(self, db, slot_label=None, **kwargs):
        calls.append(("run", {"slot_label": slot_label, **kwargs}))
        return {"mode": "operation_test3_position_management_run", "broker_submit_called": False}

    def fake_enable(self, db, *, confirm_live, confirmation):
        calls.append(("enable", {"confirm_live": confirm_live, "confirmation": confirmation}))
        return {"status": "enabled", "immediate_order_execution": False, "broker_submit_called": False}

    def fake_disable(self, db):
        calls.append(("disable", {}))
        return {"status": "disabled", "broker_submit_called": False}

    monkeypatch.setattr(OperationTest3PositionManagementService, "status", fake_status)
    monkeypatch.setattr(OperationTest3PositionManagementService, "preflight_once", fake_preflight)
    monkeypatch.setattr(OperationTest3PositionManagementService, "run_once", fake_run)
    monkeypatch.setattr(OperationTest3PositionManagementService, "enable", fake_enable)
    monkeypatch.setattr(OperationTest3PositionManagementService, "disable", fake_disable)
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as http:
            status = http.get("/app/operation-test3/status")
            preflight = http.post(
                "/app/operation-test3/position-management/preflight-once",
                json={"slot_label": "10:00"},
            )
            run = http.post(
                "/app/operation-test3/position-management/run-once",
                json={"slot_label": "14:30", "include_raw": True},
            )
            enable = http.post(
                "/app/operation-test3/position-management/enable",
                json={
                    "confirm_live": True,
                    "confirmation": "ENABLE TEST3 POSITION MANAGEMENT",
                },
            )
            disable = http.post("/app/operation-test3/disable")
    finally:
        app.dependency_overrides.clear()

    assert status.status_code == 200
    assert preflight.status_code == 200
    assert run.status_code == 200
    assert enable.status_code == 200
    assert enable.json()["immediate_order_execution"] is False
    assert disable.status_code == 200
    assert calls == [
        ("status", {}),
        ("preflight", {"slot_label": "10:00"}),
        ("run", {"slot_label": "14:30", "include_raw": True}),
        (
            "enable",
            {
                "confirm_live": True,
                "confirmation": "ENABLE TEST3 POSITION MANAGEMENT",
            },
        ),
        ("disable", {}),
    ]


def _service(client: FakeClient, sell: FakeSellService, *, session_service=None):
    return OperationTest3PositionManagementService(
        client,
        limited_auto_sell_service=sell,
        session_service=session_service or OpenSessionService(),
    )


def _enable_live_settings(db_session, **overrides):
    values = {
        "dry_run": False,
        "kill_switch": False,
        "operation_test3_enabled": True,
        "operation_test3_position_management_enabled": True,
        "operation_test3_allow_real_orders": True,
        "operation_test3_stop_loss_enabled": True,
        "operation_test3_take_profit_enabled": False,
        "operation_test3_max_sell_orders_per_day": 1,
    }
    values.update(overrides)
    return RuntimeSettingService().update_settings(db_session, values)


def _open_lifecycle(
    db_session,
    *,
    symbol="009240",
    entry_price=100.0,
    cost_basis=100.0,
    quantity=1.0,
    status="open",
    stop_loss_threshold_pct=2.0,
    take_profit_threshold_pct=2.0,
) -> PositionLifecycle:
    order = OrderLog(
        broker="kis",
        market="KR",
        symbol=symbol,
        side="buy",
        order_type="market",
        qty=quantity,
        requested_qty=quantity,
        filled_qty=quantity,
        remaining_qty=0,
        avg_fill_price=entry_price,
        filled_avg_price=entry_price,
        notional=entry_price * quantity,
        internal_status=InternalOrderStatus.FILLED.value,
        created_at=NOW,
        filled_at=NOW,
    )
    db_session.add(order)
    db_session.commit()
    lifecycle = PositionLifecycle(
        symbol=symbol,
        entry_order_id=order.id,
        entry_price=entry_price,
        cost_basis=cost_basis,
        quantity=quantity,
        status=status,
        opened_at=NOW,
        last_price=entry_price,
        unrealized_pl=0.0,
        unrealized_pl_pct=0.0,
        max_price_since_entry=entry_price,
        stop_loss_threshold_pct=stop_loss_threshold_pct,
        take_profit_threshold_pct=take_profit_threshold_pct,
        manual_review_required=False,
    )
    db_session.add(lifecycle)
    db_session.commit()
    db_session.refresh(lifecycle)
    return lifecycle


def _position(price: float, *, symbol="009240", qty=1.0) -> dict:
    return {
        "symbol": symbol,
        "qty": qty,
        "current_price": price,
        "avg_entry_price": 100.0,
        "cost_basis": 100.0 * qty,
    }


def _sell_order(db_session, *, status: str) -> OrderLog:
    order = OrderLog(
        broker="kis",
        market="KR",
        symbol="009240",
        side="sell",
        order_type="market",
        qty=1,
        requested_qty=1,
        internal_status=status,
        request_payload=json.dumps({"source": "operation_test3_fake_existing"}),
        response_payload=json.dumps({"source": "operation_test3_fake_existing"}),
        created_at=NOW,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order