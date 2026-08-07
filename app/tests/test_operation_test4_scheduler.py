from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.db.models import OperationTest4Cycle, OrderLog
from app.services.operation_test4_service import (
    ENTRY_CONFIRMATION,
    OperationTest4Service,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.scheduler_service import SchedulerService
from app.tests.test_operation_test4_entry import (
    NOW,
    FakeManualOrderService,
    arm_for_entry,
    make_service,
)


class FakeSellService:
    def __init__(self, state, *, status="FILLED"):
        self.state = state
        self.status = status
        self.calls = 0

    def run_once(self, db, *, now=None):
        self.calls += 1
        row = OrderLog(
            broker="kis",
            market="KR",
            symbol="000001",
            side="sell",
            order_type="market",
            qty=5,
            requested_qty=5,
            filled_qty=5 if self.status == "FILLED" else 0,
            remaining_qty=0 if self.status == "FILLED" else 5,
            avg_fill_price=19_000 if self.status == "FILLED" else None,
            internal_status=self.status,
            broker_order_id="KIS-TEST4-EXIT",
            kis_odno="KIS-TEST4-EXIT",
            request_payload='{"operation_test":"test4","order_source":"operation_test4_auto_stop_loss"}',
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        if self.status == "FILLED":
            self.state["positions"] = []
            self.state["open_orders"] = []
        return {
            "real_order_submitted": True,
            "broker_submit_called": True,
            "manual_submit_called": True,
            "order_id": row.id,
            "order_log_id": row.id,
            "internal_status": self.status,
            "source_metadata": {
                "mode": "operation_test4_live",
                "order_source": "operation_test4_auto_stop_loss",
                "audit_source_context": "operation_test4_position_management",
            },
        }


class EchoOrderSync:
    def sync_order(self, db, order_id):
        return db.get(OrderLog, order_id)


def _prepare_position(db_session, tmp_path, *, current_price=19_000, sell_status="FILLED"):
    service, _, state = make_service(
        tmp_path,
        manual_service=FakeManualOrderService(status="FILLED"),
    )
    arm_for_entry(db_session, service)
    entry = service.entry_run_once(
        db_session,
        confirm_live=True,
        confirmation=ENTRY_CONFIRMATION,
        now=NOW,
    )
    assert entry["reason"] == "entry_submitted"
    state["positions"] = [
        {
            "symbol": "000001",
            "qty": 5,
            "avg_entry_price": 20_000,
            "current_price": current_price,
        }
    ]
    sell_service = FakeSellService(state, status=sell_status)
    service.limited_auto_sell_service = sell_service
    service.order_sync_service = EchoOrderSync()
    return service, state, sell_service


def test_stop_loss_reuses_guarded_sell_service_and_completes_cycle(db_session, tmp_path):
    service, state, sell_service = _prepare_position(db_session, tmp_path)

    result = service.run_scheduler_once(db_session, slot_label="10:00", now=NOW)
    cycle = db_session.query(OperationTest4Cycle).one()
    settings = RuntimeSettingService().get_settings(db_session)

    assert sell_service.calls == 1
    assert result["close"]["closed"] is True
    assert cycle.status == "completed"
    assert state["positions"] == []
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True
    assert settings["operation_test4_enabled"] is False


def test_take_profit_uses_same_single_sell_path(db_session, tmp_path):
    service, state, sell_service = _prepare_position(
        db_session,
        tmp_path,
        current_price=21_000,
    )

    result = service.run_scheduler_once(db_session, slot_label="12:00", now=NOW)

    assert sell_service.calls == 1
    assert result["reason"] == "take_profit_triggered"
    assert result["close"]["closed"] is True


def test_open_sell_order_blocks_duplicate_sell(db_session, tmp_path):
    service, state, sell_service = _prepare_position(db_session, tmp_path)
    state["open_orders"] = [{"symbol": "000001", "side": "sell", "status": "pending"}]

    result = service.run_scheduler_once(db_session, slot_label="14:30", now=NOW)

    assert result["reason"] == "duplicate_open_sell_order"
    assert sell_service.calls == 0


def test_pending_exit_is_only_synced_then_filled_closes_cycle(db_session, tmp_path):
    service, state, sell_service = _prepare_position(
        db_session,
        tmp_path,
        sell_status="PENDING",
    )

    submitted = service.run_scheduler_once(db_session, slot_label="10:00", now=NOW)
    cycle = db_session.query(OperationTest4Cycle).one()
    assert submitted["close"]["reason"] == "exit_pending"
    assert cycle.status == "exit_submitted"
    assert sell_service.calls == 1

    order = db_session.get(OrderLog, cycle.exit_order_id)
    order.internal_status = "FILLED"
    order.filled_qty = 5
    order.remaining_qty = 0
    order.avg_fill_price = 19_000
    state["positions"] = []
    state["open_orders"] = []
    db_session.commit()

    reconciled = service.reconcile_once(db_session, now=NOW)

    assert reconciled["cycle"]["status"] == "completed"
    assert sell_service.calls == 1


def test_operation_test4_scheduler_slots_are_exact():
    assert SchedulerService().operation_test4_slots == [
        ("09:35", 9, 35),
        ("10:00", 10, 0),
        ("12:00", 12, 0),
        ("14:30", 14, 30),
    ]


def test_disabled_operation_test4_scheduler_does_not_create_client_or_service(
    db_session,
    monkeypatch,
):
    calls = {"client": 0, "service": 0}

    def fail_client(*args, **kwargs):
        calls["client"] += 1
        raise AssertionError("disabled Test4 scheduler must not create a client")

    class FakeService:
        def __init__(self, *args, **kwargs):
            calls["service"] += 1

    monkeypatch.setattr("app.services.scheduler_service.KisClient", fail_client)
    monkeypatch.setattr("app.services.scheduler_service.OperationTest4Service", FakeService)

    result = SchedulerService()._run_operation_test4_with_db(
        db_session,
        slot_name="09:35",
    )

    assert result is None
    assert calls == {"client": 0, "service": 0}


def test_enabled_operation_test4_scheduler_calls_only_test4_service(
    db_session,
    monkeypatch,
):
    RuntimeSettingService().update_settings(
        db_session,
        {
            "operation_test4_scheduler_enabled": True,
            "operation_test4_enabled": True,
        },
    )
    calls = {"client": 0, "service": 0, "run": 0}

    class FakeService:
        def __init__(self, client, *, runtime_settings):
            calls["service"] += 1

        def run_scheduler_once(self, db, *, slot_label, now=None):
            calls["run"] += 1
            return {"slot_label": slot_label, "result": "hold"}

    monkeypatch.setattr(
        "app.services.scheduler_service.KisClient",
        lambda *args, **kwargs: calls.__setitem__("client", calls["client"] + 1) or object(),
    )
    monkeypatch.setattr("app.services.scheduler_service.OperationTest4Service", FakeService)

    result = SchedulerService()._run_operation_test4_with_db(
        db_session,
        slot_name="09:35",
    )

    assert result == {"slot_label": "09:35", "result": "hold"}
    assert calls == {"client": 1, "service": 1, "run": 1}