from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, TradeRunLog
from app.main import app
from app.services.kis_scheduler_live_service import MODE, KisSchedulerLiveService


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "kis_enabled": True,
        "kis_env": "prod",
        "kis_app_key": "real-app-key",
        "kis_app_secret": "real-app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_base_url": "https://openapi.koreainvestment.com:9443",
        "kis_real_order_enabled": True,
        "kis_scheduler_allow_real_orders": False,
        "kr_scheduler_allow_real_orders": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _FakeClient:
    def __init__(self, *, settings=None):
        self.settings = settings or SimpleNamespace(
            kis_enabled=True,
            kis_real_order_enabled=True,
            kis_scheduler_allow_real_orders=False,
            kr_scheduler_allow_real_orders=False,
        )


class _FakeLimitedService:
    def __init__(self, result):
        self.result = result
        self.calls = 0
        self.kwargs = []

    def run_once(self, db_session, **kwargs):
        self.calls += 1
        self.kwargs.append(kwargs)
        return self.result


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_scheduler_live_endpoint_defaults_block_no_submit(
    monkeypatch,
    client,
    db_session,
):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("scheduler must not submit by default"),
    )

    response = client.post("/kis/scheduler/run-live-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == MODE
    assert body["result"] == "blocked"
    assert body["reason"] == "kis_scheduler_live_disabled"
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert db_session.query(OrderLog).count() == 0


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("kis_scheduler_live_enabled", False, "kis_scheduler_live_disabled"),
        ("kis_scheduler_allow_real_orders", False, "kis_scheduler_real_orders_disabled"),
        ("dry_run", True, "runtime_dry_run_true"),
        ("kill_switch", True, "kill_switch_enabled"),
    ],
)
def test_scheduler_live_gates_block_before_child_services(
    db_session,
    field,
    value,
    reason,
):
    _enable_runtime(db_session, **{field: value})
    sell = _FakeLimitedService(_blocked_child("sell"))
    buy = _FakeLimitedService(_blocked_child("buy"))

    result = _service(sell=sell, buy=buy).run_once(db_session)

    assert result["result"] == "blocked"
    assert result["reason"] == reason
    assert result["real_order_submitted"] is False
    assert sell.calls == 0
    assert buy.calls == 0


def test_scheduler_live_requires_a_limited_path_enabled(db_session):
    _enable_runtime(
        db_session,
        kis_scheduler_allow_limited_auto_buy=False,
        kis_scheduler_allow_limited_auto_sell=False,
    )
    sell = _FakeLimitedService(_blocked_child("sell"))
    buy = _FakeLimitedService(_blocked_child("buy"))

    result = _service(sell=sell, buy=buy).run_once(db_session)

    assert result["reason"] == "scheduler_limited_auto_paths_disabled"
    assert sell.calls == 0
    assert buy.calls == 0


def test_scheduler_live_tries_sell_before_buy_and_stops_after_submit(db_session):
    _enable_runtime(db_session)
    sell = _FakeLimitedService(_submitted_child("sell", order_id=11))
    buy = _FakeLimitedService(_submitted_child("buy", order_id=12))

    result = _service(sell=sell, buy=buy).run_once(db_session)

    assert result["result"] == "submitted"
    assert result["action"] == "sell"
    assert result["order_id"] == 11
    assert sell.calls == 1
    assert buy.calls == 0
    assert result["real_order_submitted"] is True
    assert db_session.query(TradeRunLog).filter(TradeRunLog.mode == MODE).count() == 1


def test_scheduler_live_runs_buy_after_sell_no_action(db_session):
    _enable_runtime(db_session)
    sell = _FakeLimitedService(_blocked_child("sell", reason="no_stop_loss_candidate"))
    buy = _FakeLimitedService(_submitted_child("buy", order_id=22))

    result = _service(sell=sell, buy=buy).run_once(db_session)

    assert result["result"] == "submitted"
    assert result["action"] == "buy"
    assert result["order_id"] == 22
    assert sell.calls == 1
    assert buy.calls == 1
    assert buy.kwargs[0]["scheduler_context"] is True


def test_scheduler_live_daily_max_blocks(db_session):
    _enable_runtime(db_session)
    _seed_limited_order(db_session)
    sell = _FakeLimitedService(_submitted_child("sell"))
    buy = _FakeLimitedService(_submitted_child("buy"))

    result = _service(sell=sell, buy=buy).run_once(db_session)

    assert result["reason"] == "scheduler_daily_live_order_limit_reached"
    assert sell.calls == 0
    assert buy.calls == 0


def test_scheduler_live_status_exposes_disabled_defaults(db_session):
    service = _service()

    status = service.status(db_session)

    assert status["mode"] == MODE
    assert status["kis_scheduler_live_enabled"] is False
    assert status["kis_scheduler_allow_real_orders"] is False
    assert status["kis_scheduler_allow_limited_auto_buy"] is False
    assert status["kis_scheduler_allow_limited_auto_sell"] is False
    assert status["live_scheduler_ready"] is False


def _service(*, sell=None, buy=None, client=None):
    return KisSchedulerLiveService(
        client or _FakeClient(),
        limited_auto_sell_service=sell or _FakeLimitedService(_blocked_child("sell")),
        limited_auto_buy_service=buy or _FakeLimitedService(_blocked_child("buy")),
    )


def _enable_runtime(db_session, **overrides):
    db_session.query(RuntimeSetting).delete()
    values = {
        "scheduler_enabled": True,
        "kis_scheduler_enabled": True,
        "dry_run": False,
        "kill_switch": False,
        "kis_scheduler_live_enabled": True,
        "kis_scheduler_allow_real_orders": True,
        "kis_scheduler_configured_allow_real_orders": True,
        "kis_scheduler_allow_limited_auto_buy": True,
        "kis_scheduler_allow_limited_auto_sell": True,
        "kis_scheduler_sell_enabled": True,
        "kis_scheduler_buy_enabled": False,
        "kis_scheduler_dry_run": False,
        "kis_live_auto_sell_enabled": True,
        "kis_limited_auto_stop_loss_enabled": True,
        "kis_limited_auto_take_profit_enabled": False,
        "kis_limited_auto_sell_stop_loss_enabled": True,
        "kis_limited_auto_sell_take_profit_enabled": False,
        "kis_scheduler_max_live_orders_per_day": 1,
        "kis_scheduler_live_requires_dry_run_false": True,
        "kis_scheduler_live_respect_kill_switch": True,
    }
    values.update(overrides)
    db_session.add(RuntimeSetting(**values))
    db_session.commit()


def _blocked_child(side, *, reason="blocked"):
    return {
        "status": "ok",
        "mode": f"limited_auto_{side}",
        "result": "blocked",
        "action": "hold",
        "reason": reason,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
    }


def _submitted_child(side, *, order_id=101):
    return {
        "status": "ok",
        "mode": f"limited_auto_{side}",
        "result": "submitted",
        "action": side,
        "reason": f"limited_auto_{side}_submitted",
        "symbol": "005930",
        "order_id": order_id,
        "real_order_submitted": True,
        "broker_submit_called": True,
        "manual_submit_called": False,
    }


def _seed_limited_order(db_session):
    row = OrderLog(
        broker="kis",
        market="KR",
        symbol="005930",
        side="buy",
        order_type="market",
        qty=1,
        requested_qty=1,
        internal_status=InternalOrderStatus.SUBMITTED.value,
        broker_order_id="SCHED-TODAY",
        kis_odno="SCHED-TODAY",
        submitted_at=datetime.now(UTC).replace(tzinfo=None),
        request_payload=json.dumps({"mode": "limited_auto_buy"}),
        response_payload=json.dumps({"mode": "limited_auto_buy"}),
    )
    db_session.add(row)
    db_session.commit()
