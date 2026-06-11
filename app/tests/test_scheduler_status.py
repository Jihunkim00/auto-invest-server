from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app


def _settings(**overrides):
    defaults = {
        "dry_run": False,
        "default_symbol": "ABC",
        "kis_enabled": True,
        "kis_real_order_enabled": True,
        "kis_scheduler_enabled": False,
        "kis_scheduler_dry_run": True,
        "kis_scheduler_allow_real_orders": False,
        "kis_scheduler_configured_allow_real_orders": False,
        "kr_scheduler_enabled": False,
        "kr_scheduler_allow_real_orders": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_scheduler_status_returns_operation_mode_and_summary(client):
    response = client.get("/scheduler/status")

    assert response.status_code == 200
    body = response.json()
    assert body["current_operation_mode"] == "safe_mode"
    assert body["user_friendly_summary"]
    assert body["risk_summary"]["warning_level"] == "safe"
    assert body["live_order_possible"] is False
    assert body["live_buy_possible"] is False
    assert body["live_sell_possible"] is False
    assert "US" in body["next_run"]
    assert "KR" in body["next_run"]
    assert body["warning_message"] == "No scheduler live buy or sell automation is armed."
    assert body["global"]["scheduler_enabled"] is False
    assert body["global"]["dry_run"] is True
    assert body["global"]["kill_switch"] is False
    assert body["alpaca"]["market"] == "US"
    assert body["alpaca"]["timezone"] == "America/New_York"
    assert body["alpaca"]["no_new_entry_after"] == "15:45"
    assert body["kis"]["market"] == "KR"
    assert body["kis"]["timezone"] == "Asia/Seoul"
    assert body["kis"]["kr_no_new_entry_after"] == "14:50"
    assert body["kis"]["warning_level"] == "safe"


def test_scheduler_status_returns_sell_only_mode_summary(monkeypatch, client):
    settings = _settings(kis_enabled=True, kis_real_order_enabled=True)
    monkeypatch.setattr("app.routes.scheduler.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.runtime_setting_service.get_settings", lambda: settings)

    client.post(
        "/ops/settings/apply-preset",
        json={"preset": "kis_sell_only_automation"},
    )
    response = client.get("/scheduler/status")

    assert response.status_code == 200
    body = response.json()
    assert body["current_operation_mode"] == "kis_sell_only_automation"
    assert (
        body["user_friendly_summary"]
        == "KIS sell-only live automation is armed. Auto-buy is disabled."
    )
    assert body["risk_summary"]["live_sell_armed"] is True
    assert body["risk_summary"]["live_buy_armed"] is False
    assert body["live_order_possible"] is True
    assert body["live_sell_possible"] is True
    assert body["live_buy_possible"] is False
    assert body["daily_live_order_remaining"] == 1
    assert "LIVE SELL ARMED" in body["warning_message"]
    assert body["KR"]["current_operation_mode"] == "kis_sell_only_automation"
    assert body["kis"]["scheduler_enabled"] is True
    assert body["kis"]["live_sell_possible"] is True
    assert body["kis"]["live_buy_possible"] is False
    assert body["kis"]["warning_level"] == "armed_sell_only"
