from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, TradeRunLog
from app.main import app


class _FakeClient:
    def __init__(self, *, settings=None):
        self.settings = settings or SimpleNamespace(
            kis_enabled=True,
            kis_real_order_enabled=True,
            kis_scheduler_enabled=False,
            kis_scheduler_dry_run=True,
            kis_scheduler_allow_real_orders=False,
            kr_scheduler_enabled=False,
            kr_scheduler_allow_real_orders=False,
        )
        self.submit_calls = 0

    def get_account_balance(self):
        return {
            "provider": "kis",
            "market": "KR",
            "cash": 3_000_000,
            "total_asset_value": 10_000_000,
        }

    def list_positions(self):
        return []

    def list_open_orders(self):
        return []

    def submit_order(self, *args, **kwargs):
        self.submit_calls += 1
        pytest.fail("scheduler readiness must not use broker submit paths")

    def submit_domestic_cash_order(self, *args, **kwargs):
        self.submit_calls += 1
        pytest.fail("scheduler readiness must not use broker submit paths")

    def submit_market_buy(self, *args, **kwargs):
        self.submit_calls += 1
        pytest.fail("scheduler readiness must not use broker submit paths")

    def submit_market_sell(self, *args, **kwargs):
        self.submit_calls += 1
        pytest.fail("scheduler readiness must not use broker submit paths")


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_default_readiness_keeps_real_orders_disabled(
    monkeypatch,
    client,
):
    fake = _patch_client(monkeypatch)

    response = client.get("/kis/scheduler/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "kis"
    assert body["market"] == "KR"
    assert body["mode"] == "kis_scheduler_readiness"
    assert body["readiness_only"] is True
    assert body["scheduler_real_orders_enabled"] is False
    assert body["real_order_submit_allowed"] is False
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["summary"]["scheduler_real_orders_enabled"] is False
    assert body["summary"]["real_order_submit_allowed"] is False
    assert body["safety"]["scheduler_real_orders_enabled"] is False
    assert fake.submit_calls == 0


def test_missing_scheduler_config_defaults_to_disabled_without_runtime_mutation(
    monkeypatch,
    client,
    db_session,
):
    _patch_client(monkeypatch)

    response = client.get("/kis/scheduler/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["readiness_status"] == "DISABLED"
    assert "scheduler_config_missing" in body["block_reasons"]
    assert body["diagnostics"]["runtime_settings_missing"] is True
    assert db_session.query(RuntimeSetting).count() == 0


def test_kill_switch_shows_blocked(monkeypatch, client, db_session):
    _patch_client(monkeypatch)
    _runtime(db_session, kill_switch=True)

    body = client.get("/kis/scheduler/readiness").json()

    assert body["summary"]["readiness_status"] == "BLOCKED"
    assert body["summary"]["primary_block_reason"] == "kill_switch_enabled"
    assert "kill_switch_enabled" in body["block_reasons"]


def test_dry_run_true_shows_readiness_only(monkeypatch, client, db_session):
    _patch_client(monkeypatch)
    _runtime(db_session, dry_run=True)

    body = client.get("/kis/scheduler/readiness").json()

    assert body["readiness_only"] is True
    assert body["safety"]["dry_run"] is True
    assert body["safety"]["real_order_submitted"] is False
    assert "runtime_dry_run_true" in body["block_reasons"]


def test_allow_real_orders_false_blocks_real_order_readiness(
    monkeypatch,
    client,
    db_session,
):
    _patch_client(monkeypatch)
    _runtime(db_session, kis_scheduler_allow_real_orders=False)

    body = client.get("/kis/scheduler/readiness").json()

    assert body["summary"]["kis_scheduler_allow_real_orders"] is False
    assert body["summary"]["real_order_submit_allowed"] is False
    assert "kis_scheduler_allow_real_orders_false" in body["block_reasons"]
    assert "runtime_kis_scheduler_allow_real_orders_false" in body["block_reasons"]


def test_limited_auto_buy_module_status_is_included(
    monkeypatch,
    client,
    db_session,
):
    _patch_client(monkeypatch)
    _patch_open_market(monkeypatch)
    _runtime(db_session)

    body = client.get("/kis/scheduler/readiness").json()

    module = body["modules"]["limited_auto_buy"]
    assert module["available"] is True
    assert module["status_endpoint"] == "/kis/limited-auto-buy/status"
    assert module["auto_buy_execution_enabled"] is False
    assert module["ready_for_scheduler_real_order"] is False
    assert module["daily_limit_remaining"] == 1


def test_limited_auto_sell_module_status_is_included(
    monkeypatch,
    client,
    db_session,
):
    _patch_client(monkeypatch)
    _patch_open_market(monkeypatch)
    _runtime(db_session)

    body = client.get("/kis/scheduler/readiness").json()

    module = body["modules"]["limited_auto_sell"]
    assert module["available"] is True
    assert module["status_endpoint"] == "/kis/limited-auto-sell/status"
    assert module["stop_loss_execution_enabled"] is False
    assert module["take_profit_execution_enabled"] is False
    assert module["ready_for_scheduler_real_order"] is False
    assert module["daily_limit_remaining"] == 1


def test_unknown_market_session_blocks_real_order_readiness(
    monkeypatch,
    client,
    db_session,
):
    _patch_client(monkeypatch)
    _runtime(db_session)

    def raise_session(self, market, **kwargs):
        raise RuntimeError("session unavailable")

    monkeypatch.setattr(
        "app.services.market_session_service.MarketSessionService.get_session_status",
        raise_session,
    )

    body = client.get("/kis/scheduler/readiness").json()

    assert body["summary"]["readiness_status"] == "BLOCKED"
    assert "unknown_market_session" in body["block_reasons"]
    assert body["diagnostics"]["market_session_unknown"] is True


def test_recent_scheduler_runs_are_serialized_safely(
    monkeypatch,
    client,
    db_session,
):
    _patch_client(monkeypatch)
    _runtime(db_session)
    db_session.add(
        TradeRunLog(
            run_key="kis_scheduler_test",
            trigger_source="kis_scheduler_live",
            symbol="005930",
            mode="kis_scheduler_live_once",
            stage="done",
            result="blocked",
            reason="kis_scheduler_live_disabled",
            request_payload=json.dumps({"real_order_submitted": False}),
            response_payload=json.dumps(
                {
                    "action": "hold",
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                    "block_reasons": ["kis_scheduler_live_disabled"],
                }
            ),
        )
    )
    db_session.commit()

    body = client.get("/kis/scheduler/readiness").json()

    assert len(body["recent_runs"]) == 1
    run = body["recent_runs"][0]
    assert run["trigger_source"] == "kis_scheduler_live"
    assert run["mode"] == "kis_scheduler_live_once"
    assert run["result"] == "blocked"
    assert run["symbol"] == "005930"
    assert run["real_order_submitted"] is False
    assert run["broker_submit_called"] is False
    assert run["manual_submit_called"] is False
    assert run["block_reasons"] == ["kis_scheduler_live_disabled"]


def test_endpoint_does_not_create_order_log(monkeypatch, client, db_session):
    _patch_client(monkeypatch)
    _runtime(db_session)

    before = db_session.query(OrderLog).count()
    response = client.get("/kis/scheduler/readiness")
    after = db_session.query(OrderLog).count()

    assert response.status_code == 200
    assert before == 0
    assert after == 0


def test_endpoint_does_not_call_broker_or_manual_submit(
    monkeypatch,
    client,
    db_session,
):
    fake = _patch_client(monkeypatch)
    _runtime(db_session)
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("manual path must not run"),
    )

    body = client.get("/kis/scheduler/readiness").json()

    assert body["manual_submit_called"] is False
    assert body["broker_submit_called"] is False
    assert body["real_order_submitted"] is False
    assert fake.submit_calls == 0


def _patch_client(monkeypatch, fake: _FakeClient | None = None) -> _FakeClient:
    fake = fake or _FakeClient()
    monkeypatch.setattr("app.routes.kis._client", lambda db: fake)
    return fake


def _patch_open_market(monkeypatch):
    monkeypatch.setattr(
        "app.services.market_session_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: {
            "market": market,
            "timezone": "Asia/Seoul",
            "is_market_open": True,
            "is_entry_allowed_now": True,
            "is_near_close": False,
            "is_holiday": False,
            "closure_reason": None,
            "effective_close": "15:30",
            "no_new_entry_after": "15:00",
            "enabled_for_scheduler": False,
        },
    )


def _runtime(db_session, **overrides):
    db_session.query(RuntimeSetting).delete()
    values = {
        "dry_run": True,
        "kill_switch": False,
        "scheduler_enabled": False,
        "kis_live_auto_buy_enabled": False,
        "kis_live_auto_sell_enabled": False,
        "kis_limited_auto_buy_enabled": False,
        "kis_limited_auto_sell_enabled": False,
        "kis_limited_auto_sell_stop_loss_enabled": False,
        "kis_limited_auto_sell_take_profit_enabled": False,
        "kis_limited_auto_buy_readiness_enabled": True,
        "kis_limited_auto_buy_max_orders_per_day": 1,
        "kis_limited_auto_sell_max_orders_per_day": 1,
        "kis_scheduler_live_enabled": False,
        "kis_scheduler_allow_real_orders": False,
        "kis_scheduler_allow_limited_auto_buy": False,
        "kis_scheduler_allow_limited_auto_sell": False,
    }
    values.update(overrides)
    db_session.add(RuntimeSetting(**values))
    db_session.commit()
