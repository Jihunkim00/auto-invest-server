from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.db.models import PositionLifecycle, TradeRunLog
from app.services.operation_test3_position_management_service import (
    SCHEDULER_TRIGGER_SOURCE,
    operation_test3_scheduler_gate,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.scheduler_service import SchedulerService
from app.tests.test_operation_test3_position_management import (
    FakeClient,
    _enable_live_settings,
    _open_lifecycle,
    _position,
)

NOW = datetime(2026, 8, 4, 1, 0, tzinfo=UTC)


def test_scheduler_gate_ignores_common_scheduler_flags():
    gate = operation_test3_scheduler_gate(
        {
            "scheduler_enabled": False,
            "kis_scheduler_enabled": False,
            "kis_position_lifecycle_scheduler_enabled": False,
            "operation_test3_scheduler_enabled": True,
        }
    )

    assert gate["scheduler_execution_allowed"] is True
    assert gate["independent_of_common_scheduler"] is True
    assert gate["ignored_common_scheduler_flags"] == {
        "scheduler_enabled": False,
        "kis_scheduler_enabled": False,
        "kis_position_lifecycle_scheduler_enabled": False,
    }


def test_test3_scheduler_false_does_not_create_client_or_service(monkeypatch, db_session):
    _open_lifecycle(db_session)
    RuntimeSettingService().update_settings(
        db_session,
        {"operation_test3_scheduler_enabled": False},
    )
    calls = {"client": 0, "service": 0}

    def fake_client(*args, **kwargs):
        calls["client"] += 1
        raise AssertionError("client should not be created when test3 scheduler is off")

    class FakeService:
        def __init__(self, *args, **kwargs):
            calls["service"] += 1

    monkeypatch.setattr("app.services.scheduler_service.KisClient", fake_client)
    monkeypatch.setattr("app.services.scheduler_service.OperationTest3PositionManagementService", FakeService)

    result = SchedulerService()._run_operation_test3_position_management_with_db(
        db_session,
        slot_name="10:00",
    )

    assert result is None
    assert calls == {"client": 0, "service": 0}


def test_no_active_lifecycle_does_not_create_client_or_service(monkeypatch, db_session):
    RuntimeSettingService().update_settings(
        db_session,
        {"operation_test3_scheduler_enabled": True},
    )
    calls = {"client": 0, "service": 0}

    def fake_client(*args, **kwargs):
        calls["client"] += 1
        raise AssertionError("client should not be created without active lifecycle")

    class FakeService:
        def __init__(self, *args, **kwargs):
            calls["service"] += 1

    monkeypatch.setattr("app.services.scheduler_service.KisClient", fake_client)
    monkeypatch.setattr("app.services.scheduler_service.OperationTest3PositionManagementService", FakeService)

    result = SchedulerService()._run_operation_test3_position_management_with_db(
        db_session,
        slot_name="10:00",
    )

    assert result is None
    assert calls == {"client": 0, "service": 0}


def test_common_scheduler_false_still_runs_test3_service(monkeypatch, db_session):
    _open_lifecycle(db_session)
    RuntimeSettingService().update_settings(
        db_session,
        {
            "scheduler_enabled": False,
            "kis_scheduler_enabled": False,
            "kis_position_lifecycle_scheduler_enabled": False,
            "operation_test3_scheduler_enabled": True,
        },
    )
    calls = {"client": 0, "service": 0, "run": 0}

    def fake_client(*args, **kwargs):
        calls["client"] += 1
        return object()

    class FakeService:
        def __init__(self, client, *, runtime_settings):
            calls["service"] += 1
            self.client = client
            self.runtime_settings = runtime_settings

        def run_once(self, db, **kwargs):
            calls["run"] += 1
            return {"mode": "operation_test3_position_management_run", "kwargs": kwargs}

    monkeypatch.setattr("app.services.scheduler_service.KisClient", fake_client)
    monkeypatch.setattr("app.services.scheduler_service.OperationTest3PositionManagementService", FakeService)

    result = SchedulerService()._run_operation_test3_position_management_with_db(
        db_session,
        slot_name="12:00",
    )

    assert result["kwargs"] == {
        "slot_label": "12:00",
        "trigger_source": SCHEDULER_TRIGGER_SOURCE,
    }
    assert calls == {"client": 1, "service": 1, "run": 1}


def test_scheduler_slots_are_dedicated_kst_times():
    scheduler = SchedulerService()

    assert scheduler.operation_test3_position_management_slots == [
        ("10:00", 10, 0),
        ("12:00", 12, 0),
        ("14:30", 14, 30),
    ]


def test_scheduler_hold_result_records_trade_run_log(monkeypatch, db_session):
    _open_lifecycle(db_session)
    _enable_live_settings(db_session, operation_test3_scheduler_enabled=True)

    monkeypatch.setattr(
        "app.services.scheduler_service.KisClient",
        lambda *args, **kwargs: FakeClient(positions=[_position(101.0)]),
    )

    result = SchedulerService()._run_operation_test3_position_management_with_db(
        db_session,
        slot_name="14:30",
    )

    run = db_session.query(TradeRunLog).filter(TradeRunLog.mode == "op_test3_pm_run").one()
    payload = json.loads(run.response_payload)
    assert result["result"] == "hold"
    assert result["reason"] == "no_exit_condition"
    assert run.trigger_source == SCHEDULER_TRIGGER_SOURCE
    assert payload["metadata"]["operation_test"] == "test3"
    assert payload["metadata"]["scheduler_slot"] == "14:30"
    assert payload["metadata"]["sell_only"] is True
    assert payload["metadata"]["buy_execution_allowed"] is False


def test_test3_scheduler_does_not_call_other_scheduler_services(monkeypatch, db_session):
    _open_lifecycle(db_session)
    RuntimeSettingService().update_settings(
        db_session,
        {"operation_test3_scheduler_enabled": True},
    )
    calls = {"test3": 0}

    class FakeOperationTest3Service:
        def __init__(self, *args, **kwargs):
            pass

        def run_once(self, db, **kwargs):
            calls["test3"] += 1
            return {"result": "ok", "kwargs": kwargs}

    def fail_other(*args, **kwargs):
        raise AssertionError("non-test3 scheduler path must not run")

    scheduler = SchedulerService()
    monkeypatch.setattr("app.services.scheduler_service.KisClient", lambda *args, **kwargs: object())
    monkeypatch.setattr("app.services.scheduler_service.OperationTest3PositionManagementService", FakeOperationTest3Service)
    monkeypatch.setattr("app.services.scheduler_service.KisSchedulerSimulationService", fail_other)
    monkeypatch.setattr("app.services.scheduler_service.KisSchedulerLiveService", fail_other)
    monkeypatch.setattr("app.services.scheduler_service.WatchlistRunService", fail_other)

    result = scheduler._run_operation_test3_position_management_with_db(
        db_session,
        slot_name="10:00",
    )

    assert result["result"] == "ok"
    assert calls == {"test3": 1}


def test_scheduler_method_leaves_buy_flags_false(db_session, monkeypatch):
    _open_lifecycle(db_session)
    RuntimeSettingService().update_settings(
        db_session,
        {
            "operation_test3_scheduler_enabled": True,
            "kis_live_auto_buy_enabled": True,
            "kis_limited_auto_buy_enabled": True,
            "kis_scheduler_buy_enabled": True,
            "kis_scheduler_allow_limited_auto_buy": True,
            "strategy_auto_buy_scheduler_enabled": True,
            "strategy_live_auto_buy_scheduler_enabled": True,
            "auto_buy_live_phase1_enabled": True,
            "auto_buy_live_phase1_allow_real_orders": True,
        },
    )
    monkeypatch.setattr(
        "app.services.scheduler_service.KisClient",
        lambda *args, **kwargs: FakeClient(positions=[_position(101.0)]),
    )

    SchedulerService()._run_operation_test3_position_management_with_db(
        db_session,
        slot_name="10:00",
    )

    settings = RuntimeSettingService().get_settings(db_session)
    assert settings["kis_live_auto_buy_enabled"] is False
    assert settings["kis_limited_auto_buy_enabled"] is False
    assert settings["kis_scheduler_buy_enabled"] is False
    assert settings["kis_scheduler_allow_limited_auto_buy"] is False
    assert settings["strategy_auto_buy_scheduler_enabled"] is False
    assert settings["strategy_live_auto_buy_scheduler_enabled"] is False
    assert settings["auto_buy_live_phase1_enabled"] is False
    assert settings["auto_buy_live_phase1_allow_real_orders"] is False