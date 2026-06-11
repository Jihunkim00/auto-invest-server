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

    assert settings["dry_run"] is True
    assert settings["kill_switch"] is False
    assert settings["kis_scheduler_enabled"] is False
    assert settings["kis_scheduler_dry_run"] is True
    assert settings["kis_scheduler_live_enabled"] is False
    assert settings["kis_scheduler_allow_real_orders"] is False
    assert settings["kis_scheduler_configured_allow_real_orders"] is False
    assert settings["kis_scheduler_sell_enabled"] is False
    assert settings["kis_scheduler_buy_enabled"] is False
    assert settings["kis_scheduler_allow_limited_auto_sell"] is False
    assert settings["kis_scheduler_allow_limited_auto_buy"] is False
    assert settings["kis_live_auto_sell_enabled"] is False
    assert settings["kis_live_auto_buy_enabled"] is False
    assert settings["kis_limited_auto_buy_enabled"] is False
    assert settings["kis_limited_auto_stop_loss_enabled"] is False
    assert settings["kis_limited_auto_sell_stop_loss_enabled"] is False
    assert settings["kis_limited_auto_take_profit_enabled"] is False
    assert settings["kis_limited_auto_sell_take_profit_enabled"] is False
    assert settings["kis_limited_auto_sell_allow_take_profit_trigger"] is False
    assert settings["kis_scheduler_max_live_orders_per_day"] == 1
    assert settings["kis_limited_auto_sell_max_orders_per_day"] == 1
    assert settings["kis_limited_auto_sell_max_notional_pct"] == 0.03
    assert settings["kis_live_auto_max_orders_per_day"] == 1
    assert settings["kis_live_auto_max_notional_pct"] == 0.03
    assert settings["max_trades_per_day"] == 3
    assert settings["per_symbol_daily_entry_limit"] == 1
    assert settings["per_slot_new_entry_limit"] == 1
    assert settings["max_open_positions"] == 3


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


def test_safe_mode_preset_disables_all_live_flags(client):
    client.put(
        "/ops/settings",
        json={
            "dry_run": False,
            "scheduler_enabled": True,
            "kis_scheduler_enabled": True,
            "kis_scheduler_dry_run": False,
            "kis_scheduler_live_enabled": True,
            "kis_scheduler_allow_real_orders": True,
            "kis_scheduler_configured_allow_real_orders": True,
            "kis_scheduler_sell_enabled": True,
            "kis_scheduler_buy_enabled": True,
            "kis_scheduler_allow_limited_auto_sell": True,
            "kis_scheduler_allow_limited_auto_buy": True,
            "kis_live_auto_sell_enabled": True,
            "kis_live_auto_buy_enabled": True,
            "kis_limited_auto_buy_enabled": True,
            "kis_limited_auto_stop_loss_enabled": True,
            "kis_limited_auto_take_profit_enabled": True,
        },
    )

    response = client.post(
        "/ops/settings/apply-preset",
        json={"preset": "safe_mode", "confirm_dangerous": False},
    )

    assert response.status_code == 200
    body = response.json()
    settings = body["settings"]
    assert body["applied"] is True
    assert settings["dry_run"] is True
    assert settings["scheduler_enabled"] is False
    for key in (
        "kis_scheduler_enabled",
        "kis_scheduler_live_enabled",
        "kis_scheduler_allow_real_orders",
        "kis_scheduler_configured_allow_real_orders",
        "kis_scheduler_sell_enabled",
        "kis_scheduler_buy_enabled",
        "kis_scheduler_allow_limited_auto_sell",
        "kis_scheduler_allow_limited_auto_buy",
        "kis_live_auto_sell_enabled",
        "kis_live_auto_buy_enabled",
        "kis_limited_auto_buy_enabled",
        "kis_limited_auto_stop_loss_enabled",
        "kis_limited_auto_sell_stop_loss_enabled",
        "kis_limited_auto_take_profit_enabled",
        "kis_limited_auto_sell_take_profit_enabled",
    ):
        assert settings[key] is False
    assert body["risk_summary"]["live_sell_armed"] is False
    assert body["risk_summary"]["live_buy_armed"] is False


def test_dry_run_simulation_preset_disables_real_orders(client):
    response = client.post(
        "/ops/settings/apply-preset",
        json={"preset": "dry_run_simulation"},
    )

    settings = response.json()["settings"]
    assert settings["dry_run"] is True
    assert settings["scheduler_enabled"] is True
    assert settings["kis_scheduler_enabled"] is True
    assert settings["kis_scheduler_dry_run"] is True
    assert settings["kis_scheduler_live_enabled"] is False
    assert settings["kis_scheduler_allow_real_orders"] is False
    assert settings["kis_scheduler_buy_enabled"] is False
    assert settings["kis_live_auto_buy_enabled"] is False


def test_manual_live_trading_preset_disables_scheduler_live_orders(client):
    client.put(
        "/ops/settings",
        json={
            "scheduler_enabled": True,
            "kis_scheduler_enabled": True,
            "kis_scheduler_live_enabled": True,
            "kis_scheduler_allow_real_orders": True,
            "kis_scheduler_configured_allow_real_orders": True,
            "kis_scheduler_buy_enabled": True,
            "kis_scheduler_sell_enabled": True,
            "kis_live_auto_buy_enabled": True,
            "kis_live_auto_sell_enabled": True,
        },
    )

    response = client.post(
        "/ops/settings/apply-preset",
        json={"preset": "manual_live_trading"},
    )

    settings = response.json()["settings"]
    assert settings["dry_run"] is False
    assert settings["kis_scheduler_live_enabled"] is False
    assert settings["kis_scheduler_allow_real_orders"] is False
    assert settings["kis_scheduler_configured_allow_real_orders"] is False
    assert settings["kis_scheduler_buy_enabled"] is False
    assert settings["kis_scheduler_sell_enabled"] is False
    assert settings["kis_live_auto_buy_enabled"] is False
    assert settings["kis_live_auto_sell_enabled"] is False


def test_kis_sell_only_automation_preset_arms_sell_not_buy(monkeypatch, client):
    monkeypatch.setattr(
        "app.services.runtime_setting_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )

    response = client.post(
        "/ops/settings/apply-preset",
        json={"preset": "kis_sell_only_automation"},
    )

    body = response.json()
    settings = body["settings"]
    assert body["applied"] is True
    assert settings["dry_run"] is False
    assert settings["kis_scheduler_sell_enabled"] is True
    assert settings["kis_scheduler_buy_enabled"] is False
    assert settings["kis_scheduler_allow_limited_auto_sell"] is True
    assert settings["kis_scheduler_allow_limited_auto_buy"] is False
    assert settings["kis_live_auto_sell_enabled"] is True
    assert settings["kis_live_auto_buy_enabled"] is False
    assert body["risk_summary"]["live_sell_armed"] is True
    assert body["risk_summary"]["live_buy_armed"] is False
    assert body["warning_level"] == "armed_sell_only"


def test_full_live_test_mode_requires_confirmation(client):
    response = client.post(
        "/ops/settings/apply-preset",
        json={"preset": "full_live_test_mode", "confirm_dangerous": False},
    )

    body = response.json()
    assert body["applied"] is False
    assert body["requires_confirmation"] is True
    assert body["warning_level"] == "dangerous_mixed"
    assert body["settings"]["kis_scheduler_buy_enabled"] is False


def test_full_live_test_mode_sets_buy_and_sell_after_confirmation(
    monkeypatch,
    client,
):
    monkeypatch.setattr(
        "app.services.runtime_setting_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )

    response = client.post(
        "/ops/settings/apply-preset",
        json={"preset": "full_live_test_mode", "confirm_dangerous": True},
    )

    body = response.json()
    assert body["applied"] is True
    assert body["settings"]["kis_scheduler_buy_enabled"] is True
    assert body["settings"]["kis_scheduler_sell_enabled"] is True
    assert body["settings"]["kis_live_auto_buy_enabled"] is True
    assert body["settings"]["kis_live_auto_sell_enabled"] is True
    assert body["risk_summary"]["live_buy_armed"] is True
    assert body["risk_summary"]["live_sell_armed"] is True
    assert body["warning_level"] == "dangerous_mixed"


def test_settings_catalog_returns_grouped_metadata(client):
    response = client.get("/ops/settings/catalog")

    assert response.status_code == 200
    body = response.json()
    groups = {item["key"]: item for item in body["groups"]}
    assert {
        "operation_mode",
        "schedule",
        "risk_limits",
        "exit_rules",
        "advanced",
    }.issubset(groups)
    flat_items = {item["key"]: item for item in body["items"]}
    assert flat_items["current_operation_mode"]["group"] == "operation_mode"
    assert flat_items["kr_scheduler_mode"]["value_type"] == "enum"
    assert flat_items["max_live_orders_per_day"]["group"] == "risk_limits"
    assert flat_items["stop_loss_enabled"]["group"] == "exit_rules"
