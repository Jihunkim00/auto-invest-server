from __future__ import annotations

import json
from datetime import UTC, datetime
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


NOW = datetime(2026, 7, 30, 1, 0, tzinfo=UTC)


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
