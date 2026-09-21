from __future__ import annotations

import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, PositionLifecycle, TradeRunLog
from app.main import app
from app.services.kis_position_lifecycle_service import (
    HOLD,
    REVIEW_SELL,
    SELL_READY,
    KisPositionLifecycleService,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.scheduler_service import SchedulerService
from app.services.automation_scheduler_service import AutomationSchedulerService


NOW = datetime(2026, 7, 30, 1, 0, tzinfo=UTC)
KST = ZoneInfo("Asia/Seoul")


class FakeClient:
    def __init__(
        self,
        *,
        positions: list[dict] | None = None,
        open_orders: list[dict] | None = None,
    ):
        self.positions = positions or []
        self.open_orders = open_orders or []
        self.list_positions_calls = 0
        self.list_open_orders_calls = 0
        self.submit_order_calls = []
        self.submit_domestic_cash_order_calls = []
        self.settings = SimpleNamespace(
            kis_enabled=True,
            kis_real_order_enabled=True,
            kis_confirmation_phrase="I UNDERSTAND THIS WILL PLACE A REAL KIS ORDER",
        )

    def list_positions(self):
        self.list_positions_calls += 1
        return self.positions

    def list_open_orders(self):
        self.list_open_orders_calls += 1
        return self.open_orders

    def submit_order(self, *args, **kwargs):
        self.submit_order_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("position lifecycle must not submit orders directly")

    def submit_domestic_cash_order(self, **kwargs):
        self.submit_domestic_cash_order_calls.append(dict(kwargs))
        raise AssertionError("position lifecycle must not submit orders directly")


class FakeSessionService:
    def __init__(self, *, is_open: bool = True, entry_allowed: bool = True):
        self.is_open = is_open
        self.entry_allowed = entry_allowed

    def get_session_status(self, market: str, *, now: datetime | None = None):
        return {
            "market": market,
            "timezone": "Asia/Seoul",
            "is_market_open": self.is_open,
            "is_entry_allowed_now": self.entry_allowed,
            "is_near_close": self.is_open and not self.entry_allowed,
            "closure_reason": None if self.is_open else "outside_regular_hours",
            "regular_open": "09:00",
            "regular_close": "15:30",
            "effective_close": "15:30",
            "no_new_entry_after": "14:00",
        }


class FakeSellService:
    def __init__(self, result: dict):
        self.result = result
        self.calls = 0

    def run_once(self, db, *, now=None):
        self.calls += 1
        return dict(self.result)


class TimeoutAfterOrderSellService:
    def __init__(self):
        self.calls = 0

    def run_once(self, db, *, now=None):
        self.calls += 1
        order = OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="sell",
            order_type="market",
            qty=1,
            requested_qty=1,
            internal_status=InternalOrderStatus.FAILED.value,
            response_payload=json.dumps(
                {
                    "source": "kis_limited_auto_stop_loss",
                    "broker_submit_called": True,
                    "manual_submit_called": True,
                }
            ),
        )
        db.add(order)
        db.commit()
        raise TimeoutError("broker timeout")


def test_filled_buy_sync_creates_lifecycle_and_disables_buy(db_session):
    runtime = RuntimeSettingService()
    runtime.update_settings(
        db_session,
        {
            "kis_live_auto_buy_enabled": True,
            "kis_limited_auto_buy_enabled": True,
            "kis_scheduler_buy_enabled": True,
            "kis_scheduler_allow_limited_auto_buy": True,
            "strategy_auto_buy_scheduler_enabled": True,
        },
    )
    order = _filled_buy_order(db_session)

    result = KisPositionLifecycleService(FakeClient()).sync_filled_buy(
        db_session,
        order,
        now=NOW,
    )

    lifecycle = db_session.query(PositionLifecycle).one()
    settings = runtime.get_settings(db_session)
    assert result["created"] is True
    assert lifecycle.symbol == "005930"
    assert lifecycle.entry_order_id == order.id
    assert lifecycle.entry_price == 100.0
    assert lifecycle.cost_basis == 100.0
    assert lifecycle.quantity == 1.0
    assert lifecycle.status == "open"
    assert settings["kis_live_auto_buy_enabled"] is False
    assert settings["kis_limited_auto_buy_enabled"] is False
    assert settings["kis_scheduler_buy_enabled"] is False
    assert settings["kis_scheduler_allow_limited_auto_buy"] is False
    assert settings["strategy_auto_buy_scheduler_enabled"] is False


def test_filled_buy_sync_blocks_duplicate_lifecycle(db_session):
    order = _filled_buy_order(db_session)
    service = KisPositionLifecycleService(FakeClient())

    first = service.sync_filled_buy(db_session, order, now=NOW)
    second = service.sync_filled_buy(db_session, order, now=NOW)

    assert first["created"] is True
    assert second["created"] is False
    assert second["reason"] == "lifecycle_already_exists"
    assert db_session.query(PositionLifecycle).count() == 1


def test_non_reviewed_filled_buy_does_not_create_lifecycle(db_session):
    order = _filled_buy_order(db_session, reviewed=False)

    result = KisPositionLifecycleService(FakeClient()).sync_filled_buy(
        db_session,
        order,
        now=NOW,
    )

    assert result["created"] is False
    assert result["reason"] == "entry_order_not_reviewed_buy"
    assert db_session.query(PositionLifecycle).count() == 0


def test_position_management_status_exposes_scheduler_gate(db_session):
    service = KisPositionLifecycleService()

    default_status = service.status(db_session)

    assert default_status["scheduler_enabled"] is False
    assert default_status["kis_scheduler_enabled"] is False
    assert default_status["kis_position_lifecycle_scheduler_enabled"] is False
    assert default_status["scheduler_execution_allowed"] is False
    assert default_status["blocking_reasons"] == [
        "scheduler_enabled_false",
        "kis_scheduler_enabled_false",
        "kis_position_lifecycle_scheduler_enabled_false",
    ]

    RuntimeSettingService().update_settings(
        db_session,
        {
            "scheduler_enabled": True,
            "kis_scheduler_enabled": True,
            "kis_position_lifecycle_scheduler_enabled": True,
        },
    )

    enabled_status = service.status(db_session)

    assert enabled_status["scheduler_enabled"] is True
    assert enabled_status["kis_scheduler_enabled"] is True
    assert enabled_status["kis_position_lifecycle_scheduler_enabled"] is True
    assert enabled_status["scheduler_execution_allowed"] is True
    assert enabled_status["blocking_reasons"] == []
    assert enabled_status["scheduler"]["scheduler_execution_allowed"] is True

def test_position_missing_closes_lifecycle(db_session):
    lifecycle = _open_lifecycle(db_session)

    result = KisPositionLifecycleService(
        FakeClient(positions=[]),
    ).preflight_once(db_session, now=NOW)

    db_session.refresh(lifecycle)
    item = result["items"][0]
    assert lifecycle.status == "closed"
    assert item["result"] == "closed"
    assert item["reason"] == "broker_position_not_found"


def test_position_missing_does_not_submit_to_broker(db_session):
    _open_lifecycle(db_session)
    client = FakeClient(positions=[])
    sell_service = FakeSellService({"real_order_submitted": True})

    result = KisPositionLifecycleService(
        client,
        limited_auto_sell_service=sell_service,
    ).run_once(db_session, now=NOW)

    item = result["items"][0]
    assert item["reason"] == "broker_position_not_found"
    assert item["real_order_submitted"] is False
    assert sell_service.calls == 0
    assert client.submit_order_calls == []
    assert client.submit_domestic_cash_order_calls == []

def test_normal_held_position_records_hold_log(db_session):
    _open_lifecycle(db_session)

    result = KisPositionLifecycleService(
        FakeClient(positions=[_position(current_price=101.0)]),
    ).preflight_once(db_session, now=NOW)

    item = result["items"][0]
    run = db_session.query(TradeRunLog).one()
    payload = json.loads(run.response_payload)
    assert item["action"] == HOLD
    assert item["reason"] == "no_exit_condition"
    assert payload["operation_log"] == {
        "symbol": "005930",
        "entry_price": 100.0,
        "current_price": 101.0,
        "unrealized_pl": 1.0,
        "unrealized_pl_pct": 0.01,
        "stop_loss_threshold": 98.0,
        "action": HOLD,
        "reason": "no_exit_condition",
        "order_id": None,
    }


def test_stop_loss_evaluates_sell_ready_without_preflight_submit(db_session):
    _open_lifecycle(db_session)
    sell_service = FakeSellService({"real_order_submitted": True})

    result = KisPositionLifecycleService(
        FakeClient(positions=[_position(current_price=97.0)]),
        limited_auto_sell_service=sell_service,
    ).preflight_once(db_session, now=NOW)

    item = result["items"][0]
    assert item["action"] == SELL_READY
    assert item["reason"] == "stop_loss_triggered"
    assert item["real_order_submitted"] is False
    assert sell_service.calls == 0


def test_weak_trend_returns_review_sell_only(db_session):
    _open_lifecycle(db_session)

    result = KisPositionLifecycleService(
        FakeClient(positions=[_position(current_price=101.0, weak_trend=True)]),
    ).preflight_once(db_session, now=NOW)

    item = result["items"][0]
    assert item["action"] == REVIEW_SELL
    assert item["reason"] == "weak_trend_triggered"
    assert item["real_order_submitted"] is False


def test_duplicate_sell_order_blocks_stop_loss_submit(db_session):
    _open_lifecycle(db_session)
    _sell_order(db_session, status=InternalOrderStatus.SUBMITTED.value)
    sell_service = FakeSellService({"real_order_submitted": True})

    result = KisPositionLifecycleService(
        FakeClient(positions=[_position(current_price=97.0)]),
        limited_auto_sell_service=sell_service,
    ).run_once(db_session, now=NOW)

    item = result["items"][0]
    assert item["action"] == HOLD
    assert item["reason"] == "duplicate_open_sell_order"
    assert item["real_order_submitted"] is False
    assert sell_service.calls == 0


def test_daily_sell_limit_blocks_stop_loss_submit(db_session):
    RuntimeSettingService().update_settings(
        db_session,
        {"kis_limited_auto_sell_max_orders_per_day": 1},
    )
    _open_lifecycle(db_session)
    _sell_order(db_session, status=InternalOrderStatus.FILLED.value)
    sell_service = FakeSellService({"real_order_submitted": True})

    result = KisPositionLifecycleService(
        FakeClient(positions=[_position(current_price=97.0)]),
        limited_auto_sell_service=sell_service,
    ).run_once(db_session, now=NOW)

    item = result["items"][0]
    assert item["action"] == HOLD
    assert item["reason"] == "daily_auto_sell_limit_reached"
    assert sell_service.calls == 0


def test_stop_loss_sell_submit_exactly_once(db_session):
    lifecycle = _open_lifecycle(db_session)
    sell_service = FakeSellService(
        {
            "real_order_submitted": True,
            "broker_submit_called": True,
            "manual_submit_called": True,
            "order_id": 77,
            "order_log_id": 77,
            "reason": "stop_loss_auto_sell_submitted",
        }
    )
    client = FakeClient(positions=[_position(current_price=97.0)])
    service = KisPositionLifecycleService(
        client,
        limited_auto_sell_service=sell_service,
    )

    first = service.run_once(db_session, now=NOW)
    second = service.run_once(db_session, now=NOW)

    db_session.refresh(lifecycle)
    assert first["items"][0]["real_order_submitted"] is True
    assert second["items"][0]["reason"] == "duplicate_open_sell_order"
    assert lifecycle.status == "closing"
    assert lifecycle.exit_order_id == 77
    assert sell_service.calls == 1
    assert client.submit_order_calls == []
    assert client.submit_domestic_cash_order_calls == []


def test_broker_timeout_after_order_locks_lifecycle_against_duplicate_sell(db_session):
    lifecycle = _open_lifecycle(db_session)
    sell_service = TimeoutAfterOrderSellService()
    service = KisPositionLifecycleService(
        FakeClient(positions=[_position(current_price=97.0)]),
        limited_auto_sell_service=sell_service,
    )

    first = service.run_once(db_session, now=NOW)
    second = service.run_once(db_session, now=NOW)

    db_session.refresh(lifecycle)
    assert first["items"][0]["result"] == "error"
    assert first["items"][0]["broker_submit_called"] is True
    assert second["items"][0]["reason"] == "duplicate_open_sell_order"
    assert lifecycle.status == "closing"
    assert lifecycle.exit_order_id is not None
    assert sell_service.calls == 1



def test_lifecycle_scheduler_global_gate_false_skips_client_and_service(
    monkeypatch,
    db_session,
):
    RuntimeSettingService().update_settings(
        db_session,
        {
            "scheduler_enabled": False,
            "kis_scheduler_enabled": True,
            "kis_position_lifecycle_scheduler_enabled": True,
        },
    )
    calls = {"client": 0, "service": 0}

    def fake_client(*args, **kwargs):
        calls["client"] += 1
        raise AssertionError("KIS client must not be created when gate is blocked")

    def fake_service(*args, **kwargs):
        calls["service"] += 1
        raise AssertionError("lifecycle service must not be created when gate is blocked")

    monkeypatch.setattr("app.services.scheduler_service.KisClient", fake_client)
    monkeypatch.setattr(
        "app.services.scheduler_service.KisPositionLifecycleService",
        fake_service,
    )

    result = SchedulerService()._run_position_lifecycle_management_with_db(
        db_session,
        slot_name="position_management_midday",
        trigger_source="position_management_scheduler",
    )

    payload = json.loads(result.response_payload)
    assert result.result == "skipped"
    assert result.reason == "scheduler_enabled_false"
    assert payload["blocking_reasons"] == ["scheduler_enabled_false"]
    assert calls == {"client": 0, "service": 0}


def test_lifecycle_scheduler_flag_false_skips_client_and_service(
    monkeypatch,
    db_session,
):
    RuntimeSettingService().update_settings(
        db_session,
        {
            "scheduler_enabled": True,
            "kis_scheduler_enabled": True,
            "kis_position_lifecycle_scheduler_enabled": False,
        },
    )
    calls = {"client": 0, "service": 0}

    def fake_client(*args, **kwargs):
        calls["client"] += 1
        raise AssertionError("KIS client must not be created when gate is blocked")

    def fake_service(*args, **kwargs):
        calls["service"] += 1
        raise AssertionError("lifecycle service must not be created when gate is blocked")

    monkeypatch.setattr("app.services.scheduler_service.KisClient", fake_client)
    monkeypatch.setattr(
        "app.services.scheduler_service.KisPositionLifecycleService",
        fake_service,
    )

    result = SchedulerService()._run_position_lifecycle_management_with_db(
        db_session,
        slot_name="position_management_midday",
        trigger_source="position_management_scheduler",
    )

    payload = json.loads(result.response_payload)
    assert result.result == "skipped"
    assert result.reason == "kis_position_lifecycle_scheduler_enabled_false"
    assert payload["blocking_reasons"] == [
        "kis_position_lifecycle_scheduler_enabled_false"
    ]
    assert calls == {"client": 0, "service": 0}


def test_lifecycle_scheduler_all_gates_true_open_lifecycle_runs_service_once(
    monkeypatch,
    db_session,
):
    RuntimeSettingService().update_settings(
        db_session,
        {
            "scheduler_enabled": True,
            "kis_scheduler_enabled": True,
            "kis_position_lifecycle_scheduler_enabled": True,
        },
    )
    _open_lifecycle(db_session)
    calls = {"client": 0, "service": 0, "has_manageable_position": 0, "run_once": 0}

    def fake_client(*args, **kwargs):
        calls["client"] += 1
        return object()

    class FakeLifecycleManagementService:
        def __init__(self, client, *, runtime_settings):
            calls["service"] += 1
            self.client = client
            self.runtime_settings = runtime_settings

        def has_manageable_position(self, db):
            calls["has_manageable_position"] += 1
            return bool(
                db.query(PositionLifecycle)
                .filter(PositionLifecycle.status.in_(["open", "closing"]))
                .count()
            )

        def run_once(self, db, **kwargs):
            calls["run_once"] += 1
            return {"mode": "kis_position_management_run", "kwargs": kwargs}

    monkeypatch.setattr("app.services.scheduler_service.KisClient", fake_client)
    monkeypatch.setattr(
        "app.services.scheduler_service.KisPositionLifecycleService",
        FakeLifecycleManagementService,
    )

    result = SchedulerService()._run_position_lifecycle_management_with_db(
        db_session,
        slot_name="position_management_midday",
        trigger_source="position_management_scheduler",
    )

    assert result["mode"] == "kis_position_management_run"
    assert result["kwargs"] == {
        "trigger_source": "position_management_scheduler",
        "scheduler_slot": "position_management_midday",
    }
    assert calls == {
        "client": 1,
        "service": 1,
        "has_manageable_position": 1,
        "run_once": 1,
    }

def test_scheduler_position_management_slots_and_buy_preemption(
    monkeypatch,
    db_session,
):
    _open_lifecycle(db_session)
    RuntimeSettingService().update_settings(db_session, {'automation_mode': 'test'})
    scheduler = SchedulerService()
    scheduler.strategy_auto_buy_scheduler_service = SimpleNamespace(
        run_dry_run_once=lambda *args, **kwargs: pytest.fail(
            "buy scheduler must not analyze candidates while lifecycle is open"
        )
    )
    monkeypatch.setattr(
        "app.services.scheduler_service.SessionLocal",
        lambda: db_session,
    )

    result = scheduler._run_strategy_auto_buy_dry_run_scheduled_once(
        "strategy_auto_buy_dry_run_before_close"
    )

    assert scheduler.position_lifecycle_management_slots == [
        ("position_management_open_phase", 10, 0),
        ("position_management_midday", 12, 0),
        ("position_management_before_close", 14, 30),
    ]
    assert result.reason == "position_management_priority_buy_skipped"
    settings = RuntimeSettingService().get_settings(db_session)
    assert settings["kis_scheduler_buy_enabled"] is False
    assert settings["kis_scheduler_allow_limited_auto_buy"] is False


def test_position_management_routes_delegate_without_direct_submit(
    monkeypatch,
    db_session,
):
    calls = []

    def override_get_db():
        yield db_session

    def fake_status(self, db):
        calls.append(("status", {}))
        return {
            "status": "ok",
            "sell_only": True,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
        }

    def fake_preflight_once(self, db, **kwargs):
        calls.append(("preflight", kwargs))
        return {
            "mode": "kis_position_management_preflight",
            "preflight_only": True,
            "sell_only": True,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
        }

    def fake_run_once(self, db, **kwargs):
        calls.append(("run", kwargs))
        return {
            "mode": "kis_position_management_run",
            "sell_only": True,
            "buy_execution_allowed": False,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
        }

    monkeypatch.setattr(KisPositionLifecycleService, "status", fake_status)
    monkeypatch.setattr(
        KisPositionLifecycleService,
        "preflight_once",
        fake_preflight_once,
    )
    monkeypatch.setattr(KisPositionLifecycleService, "run_once", fake_run_once)

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as http:
            status = http.get("/kis/position-management/status")
            preflight = http.post(
                "/kis/position-management/preflight-once",
                json={
                    "trigger_source": "route_test_preflight",
                    "scheduler_slot": "10:00",
                },
            )
            run = http.post(
                "/kis/position-management/run-once",
                json={
                    "trigger_source": "route_test_run",
                    "scheduler_slot": "14:30",
                    "include_raw": True,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert status.status_code == 200
    assert status.json()["sell_only"] is True
    assert preflight.status_code == 200
    assert preflight.json()["preflight_only"] is True
    assert run.status_code == 200
    assert run.json()["buy_execution_allowed"] is False
    assert calls == [
        ("status", {}),
        (
            "preflight",
            {
                "trigger_source": "route_test_preflight",
                "scheduler_slot": "10:00",
            },
        ),
        (
            "run",
            {
                "trigger_source": "route_test_run",
                "scheduler_slot": "14:30",
                "include_raw": True,
            },
        ),
    ]


def _filled_buy_order(db_session, *, reviewed: bool = True) -> OrderLog:
    request_payload = {
        "provider": "kis",
        "market": "KR",
        "mode": "manual_live",
        "symbol": "005930",
        "side": "buy",
        "qty": 1,
        "reason": "operator reviewed limited auto buy" if reviewed else "manual buy",
    }
    if reviewed:
        request_payload.update(
            {
                "source": "kis_limited_auto_buy",
                "source_type": "operator_reviewed_limited_auto_buy",
                "source_context": "operator_reviewed_limited_auto_buy",
                "operator_action_source": "operator_reviewed_limited_auto_buy",
                "source_metadata": {
                    "mode": "kis_limited_auto_buy_execute_reviewed",
                    "source_endpoint": "/kis/limited-auto-buy/execute-reviewed-once",
                    "source_type": "operator_reviewed_limited_auto_buy",
                },
            }
        )
    order = OrderLog(
        broker="kis",
        market="KR",
        symbol="005930",
        side="buy",
        order_type="market",
        qty=1,
        requested_qty=1,
        filled_qty=1,
        remaining_qty=0,
        avg_fill_price=100.0,
        filled_avg_price=100.0,
        notional=100.0,
        internal_status=InternalOrderStatus.FILLED.value,
        filled_at=NOW,
        request_payload=json.dumps(request_payload),
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def _open_lifecycle(db_session) -> PositionLifecycle:
    order = _filled_buy_order(db_session)
    result = KisPositionLifecycleService(FakeClient()).sync_filled_buy(
        db_session,
        order,
        now=NOW,
    )
    lifecycle_id = result["lifecycle"]["id"]
    return db_session.get(PositionLifecycle, lifecycle_id)


def _set_entry_kst(db_session, lifecycle: PositionLifecycle, value: datetime) -> None:
    value_utc = value.astimezone(UTC).replace(tzinfo=None)
    order = db_session.get(OrderLog, lifecycle.entry_order_id)
    order.filled_at = value_utc
    lifecycle.opened_at = value_utc
    lifecycle.last_evaluated_at = None
    db_session.commit()


def _monitor_service(client: FakeClient, *, is_open: bool = True, entry_allowed: bool = True):
    return KisPositionLifecycleService(
        client,
        session_service=FakeSessionService(
            is_open=is_open,
            entry_allowed=entry_allowed,
        ),
    )



def _scheduler_monitor_for_test(db_session, monkeypatch, client):
    import app.services.automation_scheduler_service as scheduler_module

    runtime = RuntimeSettingService()
    runtime.update_settings(
        db_session,
        {
            "scheduler_enabled": True,
            "position_management_scheduler_enabled": False,
            "automation_profile_scheduler_enabled": False,
            "dry_run": True,
        },
    )
    db_session.close = lambda: None
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(scheduler_module, "KisClient", lambda *args, **kwargs: client)
    monkeypatch.setattr(
        scheduler_module, "KisAuthManager", lambda *args, **kwargs: object()
    )
    monkeypatch.setattr(
        scheduler_module.AutomationExecutionAuthorityService,
        "snapshot",
        lambda self, db: {"scheduler_allowed": True, "automation_mode": "test"},
    )
    scheduler = AutomationSchedulerService()
    scheduler.runtime_settings = runtime
    return scheduler, runtime


def test_position_exit_monitor_routes_sell_only_through_guarded_exit(
    db_session,
    monkeypatch,
):
    import app.services.automation_scheduler_service as scheduler_module

    runtime = RuntimeSettingService()
    runtime.update_settings(
        db_session,
        {
            "scheduler_enabled": True,
            "position_management_scheduler_enabled": False,
            "automation_profile_scheduler_enabled": False,
            "dry_run": True,
        },
    )
    client = FakeClient(positions=[_position(current_price=100.0)])
    db_session.close = lambda: None
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(scheduler_module, "KisClient", lambda *args, **kwargs: client)
    monkeypatch.setattr(scheduler_module, "KisAuthManager", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        scheduler_module.AutomationExecutionAuthorityService,
        "snapshot",
        lambda self, db: {"scheduler_allowed": True, "automation_mode": "test"},
    )

    class ReadOnlyMonitor:
        def __init__(self, *args, **kwargs):
            pass

        def run_due_management_once(self, db, **kwargs):
            return {
                "status": "checked",
                "reason": "position_exit_checks_completed",
                "items": [
                    {
                        "symbol": "005930",
                        "action": "SELL",
                        "status": "checked",
                        "exit_check_due": True,
                        "execution_action": "NOT_ATTEMPTED",
                        "real_order_submitted": False,
                        "broker_submit_called": False,
                    },
                    {
                        "symbol": "000660",
                        "action": "HOLD",
                        "status": "checked",
                        "exit_check_due": True,
                        "execution_action": "NOT_ATTEMPTED",
                        "real_order_submitted": False,
                        "broker_submit_called": False,
                    },
                ],
                "real_order_submitted": False,
                "broker_submit_called": False,
            }

        def record_monitor_execution_result(
            self,
            db,
            item,
            *,
            execution_action,
            execution_reason,
            execution_result,
        ):
            item["recommended_action"] = "SELL"
            item["execution_action"] = execution_action
            item["execution_reason"] = execution_reason
            item["guarded_live_exit"] = execution_result
            item["real_order_submitted"] = bool(execution_result.get("submitted"))
            item["broker_submit_called"] = bool(
                execution_result.get("broker_submit_called")
            )

    class FakeGuardedExit:
        def __init__(self):
            self.calls = []

        def run_scheduler_once(self, db, *, scheduler_slot, symbol, now):
            self.calls.append(
                {"scheduler_slot": scheduler_slot, "symbol": symbol, "now": now}
            )
            return {
                "status": "blocked",
                "action": "blocked",
                "block_reason": "dry_run_enabled",
                "submitted": False,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "safety": {"broker_submit_called": False},
            }

    monkeypatch.setattr(scheduler_module, "KisPositionLifecycleService", ReadOnlyMonitor)
    scheduler = AutomationSchedulerService()
    scheduler.runtime_settings = runtime
    guarded = FakeGuardedExit()
    monkeypatch.setattr(
        scheduler,
        "_profile_guarded_live_auto_exit_service",
        lambda db: guarded,
    )

    result = scheduler._run_position_exit_monitor_once(
        datetime(2026, 7, 30, 0, 0, tzinfo=UTC),
    )

    assert result["monitor_independent_of_buy_scheduler"] is True
    assert result["monitor_execution_mode"] == "guarded_live_exit"
    assert result["buy_execution_allowed"] is False
    assert result["sell_only"] is True
    assert result["position_exit_monitor_active"] is True
    assert result["position_exit_monitor_state"] == "active"
    assert result["held_position_count"] == 1
    assert result["position_state_known"] is True
    assert runtime.get_settings_read_only(db_session)["position_management_scheduler_enabled"] is False
    assert guarded.calls[0]["symbol"] == "005930"
    assert len(guarded.calls) == 1
    sell_item, hold_item = result["items"]
    assert sell_item["action"] == "SELL"
    assert sell_item["recommended_action"] == "SELL"
    assert sell_item["execution_action"] == "BLOCKED_DRY_RUN"
    assert sell_item["real_order_submitted"] is False
    assert sell_item["broker_submit_called"] is False
    assert hold_item["execution_action"] == "NOT_ATTEMPTED"
    assert hold_item["real_order_submitted"] is False
    assert hold_item["broker_submit_called"] is False
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False


def test_position_exit_monitor_ignores_legacy_switch_for_due_overnight_holding(
    db_session,
    monkeypatch,
):
    import app.services.automation_scheduler_service as scheduler_module

    lifecycle_row = _open_lifecycle(db_session)
    _set_entry_kst(
        db_session,
        lifecycle_row,
        datetime(2026, 7, 29, 13, 37, tzinfo=KST),
    )
    client = FakeClient(positions=[_position(current_price=97.0)])
    scheduler, runtime = _scheduler_monitor_for_test(db_session, monkeypatch, client)

    class FakeGuardedExit:
        def __init__(self):
            self.calls = []

        def run_scheduler_once(self, db, *, scheduler_slot, symbol, now):
            self.calls.append((scheduler_slot, symbol, now))
            return {
                "status": "blocked",
                "block_reason": "dry_run_enabled",
                "submitted": False,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "safety": {"broker_submit_called": False},
            }

    guarded = FakeGuardedExit()
    monkeypatch.setattr(
        scheduler,
        "_profile_guarded_live_auto_exit_service",
        lambda db: guarded,
    )

    result = scheduler._run_position_exit_monitor_once(
        datetime(2026, 7, 30, 9, 0, tzinfo=KST),
    )

    assert runtime.get_settings_read_only(db_session)[
        "position_management_scheduler_enabled"
    ] is False
    assert result["status"] == "checked"
    assert result["position_exit_monitor_active"] is True
    assert result["held_position_count"] == 1
    assert result["position_state_known"] is True
    assert result["due_count"] == 1
    assert result["items"][0]["action"] == "SELL"
    assert result["items"][0]["execution_action"] == "BLOCKED_DRY_RUN"
    assert guarded.calls and guarded.calls[0][1] == "005930"
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert client.submit_order_calls == []
    assert client.submit_domestic_cash_order_calls == []


def test_position_exit_monitor_without_positions_is_idle_when_legacy_switch_is_off(
    db_session,
    monkeypatch,
):
    import app.services.automation_scheduler_service as scheduler_module

    client = FakeClient(positions=[])
    scheduler, _runtime = _scheduler_monitor_for_test(db_session, monkeypatch, client)
    lifecycle_calls = []

    def forbidden_lifecycle(*args, **kwargs):
        lifecycle_calls.append((args, kwargs))
        raise AssertionError("no-position poll must not evaluate lifecycle strategies")

    monkeypatch.setattr(
        scheduler_module, "KisPositionLifecycleService", forbidden_lifecycle
    )

    result = scheduler._run_position_exit_monitor_once(
        datetime(2026, 7, 30, 9, 0, tzinfo=KST),
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "no_position"
    assert result["position_exit_monitor_active"] is False
    assert result["position_exit_monitor_state"] == "idle"
    assert result["held_position_count"] == 0
    assert result["position_state_known"] is True
    assert result["sell_only"] is True
    assert result["buy_execution_allowed"] is False
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert lifecycle_calls == []
    assert client.list_positions_calls == 1
    assert client.submit_order_calls == []
    assert client.submit_domestic_cash_order_calls == []

    status = scheduler.runtime_status()
    assert status["position_exit_monitor_active"] is False
    assert status["position_exit_monitor_state"] == "idle"
    assert status["held_position_count"] == 0
    assert status["position_state_known"] is True
    assert status["position_exit_interval_minutes"] == 30
    assert status["poll_interval_seconds"] == 20


def test_position_exit_monitor_snapshot_failure_is_unknown_not_no_position(
    db_session,
    monkeypatch,
):
    import app.services.automation_scheduler_service as scheduler_module

    client = FakeClient()

    def fail_position_snapshot():
        client.list_positions_calls += 1
        raise TimeoutError("KIS balance unavailable")

    client.list_positions = fail_position_snapshot
    scheduler, _runtime = _scheduler_monitor_for_test(db_session, monkeypatch, client)
    monkeypatch.setattr(
        scheduler_module,
        "KisPositionLifecycleService",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("unavailable snapshot must not reach lifecycle evaluation")
        ),
    )

    result = scheduler._run_position_exit_monitor_once(
        datetime(2026, 7, 30, 9, 0, tzinfo=KST),
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "broker_position_snapshot_unavailable"
    assert result["position_exit_monitor_active"] is False
    assert result["position_exit_monitor_state"] == "unknown"
    assert result["held_position_count"] is None
    assert result["position_state_known"] is False
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["reason"] != "no_position"
    assert client.submit_order_calls == []
    assert client.submit_domestic_cash_order_calls == []


def test_position_exit_monitor_returns_idle_on_next_poll_after_last_position_is_sold(
    db_session,
    monkeypatch,
):
    import app.services.automation_scheduler_service as scheduler_module

    client = FakeClient(positions=[_position(current_price=100.0)])
    scheduler, _runtime = _scheduler_monitor_for_test(db_session, monkeypatch, client)
    evaluations = []

    class NotDueLifecycle:
        def __init__(self, *args, **kwargs):
            pass

        def run_due_management_once(self, db, **kwargs):
            evaluations.append(kwargs)
            return {"status": "skipped", "reason": "not_due_yet", "items": []}

    monkeypatch.setattr(
        scheduler_module, "KisPositionLifecycleService", NotDueLifecycle
    )
    first = scheduler._run_position_exit_monitor_once(
        datetime(2026, 7, 30, 9, 0, tzinfo=KST),
    )
    assert first["position_exit_monitor_active"] is True
    assert first["held_position_count"] == 1
    assert len(evaluations) == 1

    client.positions = []
    second = scheduler._run_position_exit_monitor_once(
        datetime(2026, 7, 30, 9, 0, 20, tzinfo=KST),
    )

    assert second["status"] == "skipped"
    assert second["reason"] == "no_position"
    assert second["position_exit_monitor_active"] is False
    assert second["position_exit_monitor_state"] == "idle"
    assert second["held_position_count"] == 0
    assert second["position_state_known"] is True
    assert len(evaluations) == 1
    assert client.list_positions_calls == 2
    assert client.submit_order_calls == []
    assert client.submit_domestic_cash_order_calls == []


def test_position_exit_monitor_guarded_sell_is_not_retried_before_next_interval(
    db_session,
    monkeypatch,
):
    import app.services.automation_scheduler_service as scheduler_module

    lifecycle_row = _open_lifecycle(db_session)
    _set_entry_kst(
        db_session,
        lifecycle_row,
        datetime(2026, 7, 30, 13, 37, tzinfo=KST),
    )
    client = FakeClient(positions=[_position(current_price=97.0)])
    lifecycle = _monitor_service(client, entry_allowed=False)
    runtime = RuntimeSettingService()
    runtime.update_settings(
        db_session,
        {
            "scheduler_enabled": True,
            "position_management_scheduler_enabled": True,
            "automation_profile_scheduler_enabled": False,
            "dry_run": True,
        },
    )
    db_session.close = lambda: None
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(scheduler_module, "KisClient", lambda *args, **kwargs: client)
    monkeypatch.setattr(scheduler_module, "KisAuthManager", lambda *args, **kwargs: object())
    monkeypatch.setattr(scheduler_module, "KisPositionLifecycleService", lambda *args, **kwargs: lifecycle)
    monkeypatch.setattr(
        scheduler_module.AutomationExecutionAuthorityService,
        "snapshot",
        lambda self, db: {"scheduler_allowed": True, "automation_mode": "test"},
    )

    class FakeGuardedExit:
        def __init__(self):
            self.calls = []

        def run_scheduler_once(self, db, *, scheduler_slot, symbol, now):
            self.calls.append((scheduler_slot, symbol, now))
            return {
                "status": "blocked",
                "block_reason": "dry_run_enabled",
                "submitted": False,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "safety": {"broker_submit_called": False},
            }

    guarded = FakeGuardedExit()
    scheduler = AutomationSchedulerService()
    scheduler.runtime_settings = runtime
    monkeypatch.setattr(
        scheduler,
        "_profile_guarded_live_auto_exit_service",
        lambda db: guarded,
    )

    first = scheduler._run_position_exit_monitor_once(
        datetime(2026, 7, 30, 14, 7, tzinfo=KST),
    )
    second = scheduler._run_position_exit_monitor_once(
        datetime(2026, 7, 30, 14, 7, 20, tzinfo=KST),
    )

    assert first["items"][0]["recommended_action"] == "SELL"
    assert first["summary"]["sell_ready_count"] == 1
    assert first["summary"]["sell_recommendation_count"] == 1
    assert first["items"][0]["entry_cutoff_ignored_for_sell"] is True
    assert first["items"][0]["execution_action"] == "BLOCKED_DRY_RUN"
    assert second["reason"] == "not_due_yet"
    assert len(guarded.calls) == 1
    assert guarded.calls[0][1] == "005930"
    assert client.submit_order_calls == []
    assert client.submit_domestic_cash_order_calls == []
    log = (
        db_session.query(TradeRunLog)
        .filter(TradeRunLog.trigger_source == "position_exit_monitor")
        .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
        .first()
    )
    payload = json.loads(log.response_payload)
    assert payload["recommended_action"] == "SELL"
    assert payload["execution_action"] == "BLOCKED_DRY_RUN"
    assert payload["guarded_live_exit"]["block_reason"] == "dry_run_enabled"
    assert payload["broker_submit_called"] is False

def test_broker_only_holding_bootstrap_uses_observation_time_fallback(db_session):
    client = FakeClient(
        positions=[
            {
                "symbol": "005930",
                "qty": 5,
                "avg_entry_price": 100.0,
                "cost_basis": 500.0,
                "current_price": 101.0,
            }
        ]
    )
    service = _monitor_service(client)
    observed_at = datetime(2026, 7, 30, 10, 0, tzinfo=KST)

    first = service.run_due_management_once(db_session, now=observed_at)

    assert first["reason"] == "not_due_yet"
    assert first["items"][0]["entry_time_source"] == (
        "broker_position_first_observed_at_fallback"
    )
    assert first["items"][0]["next_exit_check_at"].startswith(
        "2026-07-30T10:30:"
    )
    lifecycle = db_session.query(PositionLifecycle).one()
    assert lifecycle.entry_source == "broker_position_snapshot"
    assert lifecycle.entry_time_source == "broker_position_first_observed_at_fallback"
    assert lifecycle.entry_order_id < 0
    assert lifecycle.opened_at == observed_at.astimezone(UTC).replace(tzinfo=None)
    assert lifecycle.entry_price == 100.0
    assert lifecycle.cost_basis == 500.0
    assert lifecycle.quantity == 5
    assert client.submit_order_calls == []
    assert client.submit_domestic_cash_order_calls == []

    before_due = service.run_due_management_once(
        db_session,
        now=datetime(2026, 7, 30, 10, 29, 59, tzinfo=KST),
    )
    assert before_due["reason"] == "not_due_yet"
    assert db_session.query(PositionLifecycle).count() == 1

    due = service.run_due_management_once(
        db_session,
        now=datetime(2026, 7, 30, 10, 30, tzinfo=KST),
    )
    assert due["status"] == "checked"
    assert due["items"][0]["action"] == HOLD
    assert due["items"][0]["entry_time_source"] == (
        "broker_position_first_observed_at_fallback"
    )
    assert db_session.query(PositionLifecycle).count() == 1
    assert client.submit_order_calls == []


def test_broker_only_holding_discovered_after_close_is_due_next_day_at_nine(db_session):
    client = FakeClient(positions=[_position(current_price=100.0)])
    after_close = KisPositionLifecycleService(
        client, session_service=FakeSessionService(is_open=False)
    )
    discovered = after_close.run_due_management_once(
        db_session,
        now=datetime(2026, 7, 29, 16, 0, tzinfo=KST),
    )
    assert discovered["reason"] == "market_closed"
    lifecycle = db_session.query(PositionLifecycle).one()
    assert lifecycle.entry_source == "broker_position_snapshot"
    assert lifecycle.entry_time_source == "broker_position_first_observed_at_fallback"

    next_session = _monitor_service(client).run_due_management_once(
        db_session,
        now=datetime(2026, 7, 30, 9, 0, tzinfo=KST),
    )
    assert next_session["status"] == "checked"
    assert next_session["items"][0]["exit_check_due"] is True
    assert next_session["items"][0]["current_time"].startswith(
        "2026-07-30T09:00:"
    )
    assert next_session["items"][0]["entry_time_source"] == (
        "broker_position_first_observed_at_fallback"
    )
    assert next_session["items"][0]["next_exit_check_at"].startswith(
        "2026-07-30T09:30:"
    )


def test_broker_only_holding_without_entry_data_is_reported_and_skipped(db_session):
    client = FakeClient(
        positions=[
            {
                "symbol": "005930",
                "qty": 5,
                "current_price": 101.0,
            }
        ]
    )
    result = _monitor_service(client).run_due_management_once(
        db_session, now=datetime(2026, 7, 30, 10, 0, tzinfo=KST)
    )

    assert result["reason"] == "broker_position_entry_data_unavailable"
    assert result["unmanaged_positions"] == [
        {
            "symbol": "005930",
            "status": "skipped",
            "reason": "broker_position_entry_data_unavailable",
            "entry_source": "broker_position_snapshot",
            "real_order_submitted": False,
            "broker_submit_called": False,
        }
    ]
    assert db_session.query(PositionLifecycle).count() == 0
    assert client.submit_order_calls == []
    assert client.submit_domestic_cash_order_calls == []


def test_overnight_position_is_due_at_korean_market_open(db_session):
    lifecycle = _open_lifecycle(db_session)
    _set_entry_kst(
        db_session,
        lifecycle,
        datetime(2026, 7, 29, 14, 0, tzinfo=KST),
    )
    client = FakeClient(positions=[_position(current_price=100.0)])

    result = _monitor_service(client).run_due_management_once(
        db_session,
        now=datetime(2026, 7, 30, 0, 0, tzinfo=UTC),
    )

    item = result["items"][0]
    assert result["status"] == "checked"
    assert item["action"] == HOLD
    assert item["exit_check_due"] is True
    assert item["current_time"].startswith("2026-07-30T09:00:")
    assert item["entry_time_source"] == "order.filled_at"
    assert item["next_exit_check_at"].startswith("2026-07-30T09:30:")


def test_same_day_fill_is_not_checked_before_thirty_minutes(db_session):
    lifecycle = _open_lifecycle(db_session)
    _set_entry_kst(
        db_session,
        lifecycle,
        datetime(2026, 7, 30, 11, 17, tzinfo=KST),
    )
    client = FakeClient(positions=[_position(current_price=100.0)])

    result = _monitor_service(client).run_due_management_once(
        db_session,
        now=datetime(2026, 7, 30, 2, 46, tzinfo=UTC),
    )

    assert result["reason"] == "not_due_yet"
    assert result["items"][0]["next_exit_check_at"].startswith("2026-07-30T11:47:")
    assert client.list_positions_calls == 1
    assert db_session.query(TradeRunLog).filter(
        TradeRunLog.trigger_source == "position_exit_monitor"
    ).count() == 0


def test_same_day_fill_checks_at_thirty_minutes_and_keeps_fill_anchored_cadence(db_session):
    lifecycle = _open_lifecycle(db_session)
    _set_entry_kst(
        db_session,
        lifecycle,
        datetime(2026, 7, 30, 11, 17, tzinfo=KST),
    )
    client = FakeClient(positions=[_position(current_price=100.0)])
    service = _monitor_service(client)

    first = service.run_due_management_once(
        db_session,
        now=datetime(2026, 7, 30, 2, 47, tzinfo=UTC),
    )
    assert first["items"][0]["action"] == HOLD
    assert first["items"][0]["minutes_since_entry"] == 30
    assert first["items"][0]["next_exit_check_at"].startswith("2026-07-30T12:17:")

    early = service.run_due_management_once(
        db_session,
        now=datetime(2026, 7, 30, 3, 16, tzinfo=UTC),
    )
    assert early["reason"] == "not_due_yet"

    second = service.run_due_management_once(
        db_session,
        now=datetime(2026, 7, 30, 3, 17, tzinfo=UTC),
    )
    assert second["items"][0]["action"] == HOLD
    assert second["items"][0]["next_exit_check_at"].startswith("2026-07-30T12:47:")
    assert db_session.query(TradeRunLog).filter(
        TradeRunLog.trigger_source == "position_exit_monitor"
    ).count() == 2


def test_position_monitor_holds_after_buy_cutoff_without_submission(db_session):
    lifecycle = _open_lifecycle(db_session)
    _set_entry_kst(
        db_session,
        lifecycle,
        datetime(2026, 7, 30, 13, 30, tzinfo=KST),
    )
    client = FakeClient(positions=[_position(current_price=100.0)])

    result = _monitor_service(
        client,
        entry_allowed=False,
    ).run_due_management_once(
        db_session,
        now=datetime(2026, 7, 30, 5, 0, tzinfo=UTC),
    )

    item = result["items"][0]
    assert item["action"] == HOLD
    assert item["entry_cutoff_ignored_for_sell"] is True
    assert result["buy_execution_allowed"] is False
    assert item["real_order_submitted"] is False
    assert item["broker_submit_called"] is False
    assert client.submit_order_calls == []
    assert client.submit_domestic_cash_order_calls == []


def test_position_monitor_returns_sell_after_buy_cutoff_in_dry_run(db_session):
    lifecycle = _open_lifecycle(db_session)
    _set_entry_kst(
        db_session,
        lifecycle,
        datetime(2026, 7, 30, 13, 30, tzinfo=KST),
    )
    client = FakeClient(positions=[_position(current_price=97.0)])

    result = _monitor_service(
        client,
        entry_allowed=False,
    ).run_due_management_once(
        db_session,
        now=datetime(2026, 7, 30, 5, 0, tzinfo=UTC),
    )

    item = result["items"][0]
    assert item["action"] == "SELL"
    assert item["exit_reason"] == "stop_loss_triggered"
    assert item["entry_cutoff_ignored_for_sell"] is True
    assert item["real_order_submitted"] is False
    assert item["broker_submit_called"] is False
    assert client.submit_order_calls == []
    assert client.submit_domestic_cash_order_calls == []


def test_market_closed_skips_due_position_without_order_reads_or_submit(db_session):
    lifecycle = _open_lifecycle(db_session)
    _set_entry_kst(
        db_session,
        lifecycle,
        datetime(2026, 7, 29, 14, 0, tzinfo=KST),
    )
    client = FakeClient(positions=[_position(current_price=97.0)])

    result = _monitor_service(client, is_open=False).run_due_management_once(
        db_session,
        now=datetime(2026, 7, 30, 0, 0, tzinfo=UTC),
    )

    assert result["reason"] == "market_closed"
    assert result["items"][0]["reason"] == "market_closed"
    assert client.list_positions_calls == 1
    assert client.list_open_orders_calls == 0
    assert client.submit_order_calls == []
    assert client.submit_domestic_cash_order_calls == []


def test_no_position_returns_safe_skip(db_session):
    client = FakeClient()

    result = _monitor_service(client).run_due_management_once(
        db_session,
        now=NOW,
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "no_position"
    assert result["buy_execution_allowed"] is False
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert client.submit_order_calls == []


def test_monitor_duplicate_invocation_and_pending_partial_sell_do_not_submit_twice(db_session):
    lifecycle = _open_lifecycle(db_session)
    _set_entry_kst(
        db_session,
        lifecycle,
        datetime(2026, 7, 30, 11, 17, tzinfo=KST),
    )
    client = FakeClient(positions=[_position(current_price=97.0)])
    service = _monitor_service(client)

    first = service.run_due_management_once(
        db_session,
        now=datetime(2026, 7, 30, 2, 47, tzinfo=UTC),
    )
    duplicate = service.run_due_management_once(
        db_session,
        now=datetime(2026, 7, 30, 2, 47, tzinfo=UTC),
    )
    assert first["items"][0]["action"] == "SELL"
    assert duplicate["reason"] == "not_due_yet"
    assert client.submit_order_calls == []
    assert client.submit_domestic_cash_order_calls == []

    pending = OrderLog(
        broker="kis",
        market="KR",
        symbol="005930",
        side="sell",
        order_type="market",
        qty=1,
        requested_qty=1,
        filled_qty=0.5,
        remaining_qty=0.5,
        internal_status=InternalOrderStatus.PARTIALLY_FILLED.value,
    )
    db_session.add(pending)
    lifecycle.status = "closing"
    lifecycle.exit_order_id = pending.id
    db_session.commit()
    waiting = service.run_due_management_once(
        db_session,
        now=datetime(2026, 7, 30, 3, 17, tzinfo=UTC),
    )
    assert waiting["items"][0]["reason"] == "duplicate_open_sell_order"
    assert client.submit_order_calls == []
    assert client.submit_domestic_cash_order_calls == []


def _position(
    *,
    current_price: float,
    weak_trend: bool = False,
    sell_pressure: bool = False,
) -> dict:
    payload = {
        "symbol": "005930",
        "qty": 1,
        "current_price": current_price,
        "avg_entry_price": 100.0,
        "cost_basis": 100.0,
    }
    if weak_trend:
        payload["weak_trend_triggered"] = True
    if sell_pressure:
        payload["sell_pressure_triggered"] = True
    return payload


def _sell_order(db_session, *, status: str) -> OrderLog:
    order = OrderLog(
        broker="kis",
        market="KR",
        symbol="005930",
        side="sell",
        order_type="market",
        qty=1,
        requested_qty=1,
        internal_status=status,
        request_payload=json.dumps({"source": "kis_limited_auto_stop_loss"}),
        response_payload=json.dumps({"source": "kis_limited_auto_stop_loss"}),
        created_at=NOW,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order
