from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.main import app
from app.services.runtime_setting_service import RuntimeSettingService


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
        "kis_scheduler_enabled": False,
        "kis_scheduler_dry_run": True,
        "kis_scheduler_allow_real_orders": False,
        "kr_scheduler_enabled": False,
        "kr_scheduler_allow_real_orders": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_ops_settings_defaults_remain_safe(db_session):
    settings = RuntimeSettingService().get_settings(db_session)

    assert settings["kis_scheduler_enabled"] is False
    assert settings["kis_scheduler_dry_run"] is True
    assert settings["kis_scheduler_allow_real_orders"] is False
    assert settings["kis_scheduler_configured_allow_real_orders"] is False
    assert settings["kis_scheduler_sell_enabled"] is False
    assert settings["kis_live_auto_sell_enabled"] is False
    assert settings["kis_limited_auto_stop_loss_enabled"] is False
    assert settings["kis_limited_auto_sell_stop_loss_enabled"] is False
    assert settings["kis_limited_auto_take_profit_enabled"] is False
    assert settings["kis_limited_auto_sell_take_profit_enabled"] is False


def test_ops_settings_persists_kis_scheduler_sell_fields(client):
    response = client.put(
        "/ops/settings",
        json={
            "dry_run": False,
            "kill_switch": False,
            "scheduler_enabled": True,
            "kis_scheduler_enabled": True,
            "kis_scheduler_dry_run": False,
            "kis_scheduler_allow_real_orders": True,
            "kis_scheduler_configured_allow_real_orders": True,
            "kis_scheduler_sell_enabled": True,
            "kis_live_auto_sell_enabled": True,
        },
    )

    assert response.status_code == 200
    body = response.json()["settings"]
    assert body["kis_scheduler_enabled"] is True
    assert body["kis_scheduler_dry_run"] is False
    assert body["kis_scheduler_allow_real_orders"] is True
    assert body["kis_scheduler_configured_allow_real_orders"] is True
    assert body["kis_scheduler_sell_enabled"] is True
    assert body["kis_live_auto_sell_enabled"] is True

    get_body = client.get("/ops/settings").json()
    assert get_body["kis_scheduler_enabled"] is True
    assert get_body["kis_scheduler_dry_run"] is False
    assert get_body["kis_scheduler_allow_real_orders"] is True
    assert get_body["kis_scheduler_configured_allow_real_orders"] is True
    assert get_body["kis_scheduler_sell_enabled"] is True
    assert get_body["kis_live_auto_sell_enabled"] is True


def test_ops_settings_syncs_stop_loss_aliases(client):
    response = client.put(
        "/ops/settings",
        json={"kis_limited_auto_stop_loss_enabled": True},
    )

    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["kis_limited_auto_stop_loss_enabled"] is True
    assert settings["kis_limited_auto_sell_stop_loss_enabled"] is True

    get_body = client.get("/ops/settings").json()
    assert get_body["kis_limited_auto_stop_loss_enabled"] is True
    assert get_body["kis_limited_auto_sell_stop_loss_enabled"] is True


def test_ops_settings_syncs_reverse_stop_loss_alias(client):
    response = client.put(
        "/ops/settings",
        json={"kis_limited_auto_sell_stop_loss_enabled": True},
    )

    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["kis_limited_auto_stop_loss_enabled"] is True
    assert settings["kis_limited_auto_sell_stop_loss_enabled"] is True


def test_ops_settings_syncs_take_profit_aliases(client):
    response = client.put(
        "/ops/settings",
        json={"kis_limited_auto_take_profit_enabled": True},
    )

    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["kis_limited_auto_take_profit_enabled"] is True
    assert settings["kis_limited_auto_sell_take_profit_enabled"] is True


def test_ops_settings_syncs_reverse_take_profit_alias(client):
    response = client.put(
        "/ops/settings",
        json={"kis_limited_auto_sell_take_profit_enabled": True},
    )

    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["kis_limited_auto_take_profit_enabled"] is True
    assert settings["kis_limited_auto_sell_take_profit_enabled"] is True


def test_guarded_sell_status_uses_persisted_ops_settings(monkeypatch, client):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())

    response = client.put(
        "/ops/settings",
        json={
            "dry_run": False,
            "kill_switch": False,
            "scheduler_enabled": True,
            "kis_scheduler_enabled": True,
            "kis_scheduler_dry_run": False,
            "kis_scheduler_allow_real_orders": True,
            "kis_scheduler_configured_allow_real_orders": True,
            "kis_scheduler_sell_enabled": True,
            "kis_live_auto_sell_enabled": True,
            "kis_limited_auto_stop_loss_enabled": True,
        },
    )
    assert response.status_code == 200

    status = client.get("/kis/scheduler/guarded-sell/status").json()

    assert "kis_scheduler_disabled" not in status["block_reasons"]
    assert "kis_scheduler_dry_run_true" not in status["block_reasons"]
    assert "scheduler_sell_trigger_disabled" not in status["block_reasons"]
    assert status["checks"]["kis_scheduler_enabled"] is True
    assert status["checks"]["kis_scheduler_dry_run"] is False
    assert status["checks"]["sell_trigger_enabled"] is True
