from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.routes.operation_test4 import get_operation_test4_service

from datetime import UTC, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

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
    assert settings["operation_test4_stop_loss_enabled"] is False
    assert settings["operation_test4_take_profit_enabled"] is False


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


def test_active_monitor_pending_exit_submits_sell_only_once_across_ticks(db_session, tmp_path):
    service, _, sell_service = _prepare_position(
        db_session,
        tmp_path,
        sell_status="PENDING",
    )

    first = service.run_active_cycle_once(db_session, now=NOW)
    second = service.run_active_cycle_once(db_session, now=NOW)
    cycle = db_session.query(OperationTest4Cycle).one()

    assert first["close"]["reason"] == "exit_pending"
    assert second["result"] == "reconciled"
    assert sell_service.calls == 1
    assert cycle.status == "exit_submitted"

def test_operation_test4_scheduler_slots_are_exact():
    assert SchedulerService().operation_test4_slots == [
        ("09:35", 9, 35),
        ("11:30", 11, 30),
        ("13:30", 13, 30),
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

def test_active_cycle_monitor_reconciles_pending_without_entry_scan(
    db_session,
    tmp_path,
):
    service, _, _ = make_service(
        tmp_path,
        manual_service=FakeManualOrderService(status="PENDING"),
    )
    service.order_sync_service = EchoOrderSync()
    arm_for_entry(db_session, service)
    entry = service.entry_run_once(
        db_session,
        confirm_live=True,
        confirmation=ENTRY_CONFIRMATION,
        now=NOW,
    )
    assert entry["reason"] == "entry_submitted"
    calls_before = len(service.manual_order_service.calls)
    service.candidate_provider = lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("active monitor must not run an entry scan")
    )

    result = service.run_active_cycle_once(db_session, now=NOW)

    assert result["result"] == "reconciled"
    assert len(service.manual_order_service.calls) == calls_before


def test_active_cycle_monitor_holds_position_without_sell(db_session, tmp_path):
    service, _, sell_service = _prepare_position(
        db_session,
        tmp_path,
        current_price=20_000,
    )

    result = service.run_active_cycle_once(db_session, now=NOW)

    assert result["reason"] == "HOLD"
    assert sell_service.calls == 0


def test_active_monitor_recovers_persisted_ready_claim_to_safe_mode(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)
    arm_for_entry(db_session, service)
    cycle = OperationTest4Cycle(
        cycle_key="test4-ready-claim",
        operation_test="test4",
        provider="kis",
        market="KR",
        symbol="000001",
        status="entry_ready",
        started_at=NOW.replace(tzinfo=None),
    )
    db_session.add(cycle)
    db_session.commit()

    result = service.run_active_cycle_once(db_session, now=NOW)
    settings = RuntimeSettingService().get_settings(db_session)

    assert result["reason"] == "entry_ready_recovery_required"
    assert cycle.status == "review_required"
    assert cycle.manual_review_required is True
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True
    assert settings["operation_test4_enabled"] is False
    assert settings["operation_test4_stop_loss_enabled"] is False
    assert settings["operation_test4_take_profit_enabled"] is False

def test_disabled_operation_test4_active_monitor_does_not_create_client_or_service(
    db_session,
    monkeypatch,
):
    calls = {"client": 0, "service": 0}

    def fail_client(*args, **kwargs):
        calls["client"] += 1
        raise AssertionError("disabled Test4 monitor must not create a client")

    class FakeService:
        def __init__(self, *args, **kwargs):
            calls["service"] += 1

    monkeypatch.setattr("app.services.scheduler_service.KisClient", fail_client)
    monkeypatch.setattr("app.services.scheduler_service.OperationTest4Service", FakeService)

    result = SchedulerService()._run_operation_test4_active_monitor_with_db(db_session)

    assert result is None
    assert calls == {"client": 0, "service": 0}


def test_enabled_operation_test4_active_monitor_calls_active_cycle_service(
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

        def run_active_cycle_once(self, db):
            calls["run"] += 1
            return {"result": "hold"}

    monkeypatch.setattr(
        "app.services.scheduler_service.KisClient",
        lambda *args, **kwargs: calls.__setitem__("client", calls["client"] + 1) or object(),
    )
    monkeypatch.setattr("app.services.scheduler_service.OperationTest4Service", FakeService)

    result = SchedulerService()._run_operation_test4_active_monitor_with_db(db_session)

    assert result == {"result": "hold"}
    assert calls == {"client": 1, "service": 1, "run": 1}


def _kst_now(day: int, hour: int, minute: int) -> datetime:
    return datetime(
        2026,
        8,
        day,
        hour,
        minute,
        tzinfo=ZoneInfo("Asia/Seoul"),
    ).astimezone(UTC)


def _fresh_watchlist_for_same_day(*args, **kwargs):
    return {
        "fresh": True,
        "count": 50,
        "configured_count": 50,
        "selected_count": 50,
        "symbols": [{"symbol": f"{index:06d}"} for index in range(1, 51)],
    }


def _fresh_possible_order_for_same_day(service, now):
    service.possible_order_provider = lambda **kwargs: {
        "raw_status": "ok",
        "symbol": kwargs["symbol"],
        "order_type": "market",
        "reference_price": kwargs["order_price"],
        "orderable_cash": 1_000_000,
        "orderable_quantity": 100,
        "queried_at": now.isoformat(),
        "error": None,
    }


def test_arm_today_route_arms_safe_state_before_first_entry_slot(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)
    RuntimeSettingService().update_settings(
        db_session,
        {"dry_run": False, "kill_switch": True},
    )
    service.now_provider = lambda: _kst_now(10, 8, 30)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_operation_test4_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/app/operation-test4/scheduler/arm-today",
            json={
                "confirm": True,
                "confirmation": "ARM TEST4 TODAY",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "armed"
    assert body["arm_mode"] == "same_day"
    assert body["target_trading_date"] == "2026-08-10"
    assert body["next_entry_slot_kst"] == "09:35"
    assert body["master_scheduler_enabled"] is False
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["runtime"]["dry_run"] is False
    assert body["runtime"]["kill_switch"] is True
    assert body["runtime"]["operation_test4_scheduler_enabled"] is True
    assert body["runtime"]["operation_test4_enabled"] is False
    assert body["runtime"]["operation_test4_allow_real_entry"] is False
    assert body["runtime"]["operation_test4_allow_real_exit"] is False
    assert body["runtime"]["operation_test4_entry_enabled"] is False
    assert body["runtime"]["operation_test4_position_management_enabled"] is False
    assert service.manual_order_service.calls == []
    assert db_session.query(OrderLog).count() == 0


def test_arm_today_after_first_entry_slot_is_blocked_without_mutation(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)
    result = service.arm_today(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 TODAY",
        now=_kst_now(10, 9, 35),
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "same_day_arm_window_closed"
    assert "09:35" in result["detail"]
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    runtime = RuntimeSettingService().get_settings(db_session)
    assert runtime["operation_test4_scheduler_enabled"] is False
    assert runtime["scheduler_enabled"] is False
    assert service.manual_order_service.calls == []
    assert db_session.query(OrderLog).count() == 0


@pytest.mark.parametrize("day", [8, 17])
def test_arm_today_non_trading_day_is_blocked_without_order(db_session, tmp_path, day):
    service, _, _ = make_service(tmp_path)
    result = service.arm_today(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 TODAY",
        now=_kst_now(day, 8, 30),
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "not_a_valid_kr_trading_day"
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert service.manual_order_service.calls == []
    assert db_session.query(OrderLog).count() == 0


@pytest.mark.parametrize("blocker", ["position", "open_order", "active_cycle"])
def test_arm_today_blocks_existing_positions_orders_or_cycle(
    db_session,
    tmp_path,
    blocker,
):
    account_state = {
        "fetch_success": True,
        "equity": 1_000_000,
        "orderable_cash": 1_000_000,
        "positions": [{"symbol": "005930", "qty": 1}] if blocker == "position" else [],
        "open_orders": [{"symbol": "005930", "side": "buy"}] if blocker == "open_order" else [],
    }
    service, _, _ = make_service(tmp_path, account_state=account_state)
    if blocker == "active_cycle":
        db_session.add(
            OperationTest4Cycle(
                cycle_key="test4-arm-today-active",
                operation_test="test4",
                provider="kis",
                market="KR",
                symbol="000001",
                status="entry_pending",
            )
        )
        db_session.commit()

    result = service.arm_today(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 TODAY",
        now=_kst_now(10, 8, 30),
    )

    assert result["status"] == "blocked"
    assert result["reason"] in {
        "position_exists",
        "open_order_exists",
        "active_cycle_exists",
    }
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert service.manual_order_service.calls == []
    assert db_session.query(OrderLog).count() == 0


def test_arm_today_uses_existing_conflict_policy(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)
    RuntimeSettingService().update_settings(
        db_session,
        {"operation_test3_scheduler_enabled": True},
    )

    result = service.arm_today(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 TODAY",
        now=_kst_now(10, 8, 30),
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "other_scheduler_live_flags_enabled"
    assert "operation_test3_scheduler_enabled" in result["blocking_reasons"]
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert service.manual_order_service.calls == []
    assert db_session.query(OrderLog).count() == 0


def test_arm_today_reuses_existing_09_35_scheduler_and_guarded_submit_once(
    db_session,
    tmp_path,
):
    service, _, _ = make_service(tmp_path)
    armed = service.arm_today(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 TODAY",
        now=_kst_now(10, 8, 30),
    )
    assert armed["status"] == "armed"
    assert service.enable_live(
        db_session,
        confirm_live=True,
        confirmation="ENABLE TEST4 FULL CYCLE",
        now=_kst_now(10, 8, 30),
    )["status"] == "live_enabled"

    service._load_watchlist = _fresh_watchlist_for_same_day
    now = _kst_now(10, 9, 35)
    _fresh_possible_order_for_same_day(service, now)
    result = service.run_scheduler_once(
        db_session,
        slot_label="09:35",
        now=now,
    )

    cycle = db_session.query(OperationTest4Cycle).one()
    assert result["action"] == "BUY_READY"
    assert result["reason"] == "entry_submitted"
    assert result["real_order_submitted"] is True
    assert result["broker_submit_called"] is True
    assert result.get("target_trading_date_expired") is not True
    assert len(service.manual_order_service.calls) == 1
    assert cycle.status == "entry_pending"


def test_arm_only_scheduler_never_opens_global_guards_or_submits(
    db_session,
    tmp_path,
):
    service, _, _ = make_service(tmp_path)
    RuntimeSettingService().update_settings(
        db_session,
        {"dry_run": False, "kill_switch": True},
    )
    armed = service.arm_today(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 TODAY",
        now=_kst_now(10, 8, 30),
    )
    assert armed["status"] == "armed"
    service._load_watchlist = _fresh_watchlist_for_same_day
    now = _kst_now(10, 9, 35)
    _fresh_possible_order_for_same_day(service, now)

    result = service.run_scheduler_once(
        db_session,
        slot_label="09:35",
        now=now,
    )
    runtime = RuntimeSettingService().get_settings(db_session)

    assert result["reason"] == "operation_test4_live_arm_incomplete"
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert runtime["dry_run"] is False
    assert runtime["kill_switch"] is True
    assert runtime["operation_test4_enabled"] is False
    assert service.manual_order_service.calls == []
    assert db_session.query(OperationTest4Cycle).count() == 0
