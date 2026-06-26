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


def test_ops_settings_toggles_strategy_auto_buy_scheduler_only(client):
    response = client.put(
        "/ops/settings",
        json={
            "dry_run": False,
            "kill_switch": True,
            "strategy_live_auto_buy_enabled": True,
            "strategy_live_auto_buy_requires_operator_confirm": False,
        },
    )
    assert response.status_code == 200
    before = response.json()["settings"]

    enabled = client.put(
        "/ops/settings",
        json={"strategy_auto_buy_scheduler_enabled": True},
    )

    assert enabled.status_code == 200
    settings = enabled.json()["settings"]
    assert settings["strategy_auto_buy_scheduler_enabled"] is True
    assert settings["strategy_auto_buy_scheduler_dry_run_only"] is True
    assert settings["strategy_auto_buy_scheduler_allow_live_orders"] is False
    assert settings["dry_run"] == before["dry_run"]
    assert settings["kill_switch"] == before["kill_switch"]
    assert settings["strategy_live_auto_buy_enabled"] == before[
        "strategy_live_auto_buy_enabled"
    ]
    assert settings["strategy_live_auto_buy_requires_operator_confirm"] == before[
        "strategy_live_auto_buy_requires_operator_confirm"
    ]

    disabled = client.put(
        "/ops/settings",
        json={"strategy_auto_buy_scheduler_enabled": False},
    )

    assert disabled.status_code == 200
    settings = disabled.json()["settings"]
    assert settings["strategy_auto_buy_scheduler_enabled"] is False
    assert settings["strategy_auto_buy_scheduler_dry_run_only"] is True
    assert settings["strategy_auto_buy_scheduler_allow_live_orders"] is False
    assert settings["dry_run"] == before["dry_run"]
    assert settings["kill_switch"] == before["kill_switch"]
    assert settings["strategy_live_auto_buy_enabled"] == before[
        "strategy_live_auto_buy_enabled"
    ]
    assert settings["strategy_live_auto_buy_requires_operator_confirm"] == before[
        "strategy_live_auto_buy_requires_operator_confirm"
    ]


def test_ops_settings_ignores_strategy_auto_buy_scheduler_live_order_attempt(client):
    response = client.put(
        "/ops/settings",
        json={
            "strategy_auto_buy_scheduler_enabled": True,
            "strategy_auto_buy_scheduler_allow_live_orders": True,
            "kis_real_order_enabled": True,
        },
    )

    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["strategy_auto_buy_scheduler_enabled"] is True
    assert settings["strategy_auto_buy_scheduler_dry_run_only"] is True
    assert settings["strategy_auto_buy_scheduler_allow_live_orders"] is False
    assert "kis_real_order_enabled" not in settings


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
    assert body["preset_scope"] == "global"
    assert body["affected_brokers"] == ["alpaca", "kis"]
    assert body["affected_markets"] == ["US", "KR"]
    assert "changed_keys" in body
    assert "unchanged_keys" in body


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
    assert body["preset_scope"] == "kis"
    assert body["affected_brokers"] == ["kis"]
    assert body["affected_markets"] == ["KR"]
    assert "kis_scheduler_buy_enabled" in body["changed_keys"] or (
        "kis_scheduler_buy_enabled" in body["unchanged_keys"]
    )


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
    assert body["preset_scope"] == "kis"
    assert body["affected_brokers"] == ["kis"]
    assert body["affected_markets"] == ["KR"]
    assert body["changed_keys"] == []


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
        "global_safety",
        "alpaca_us_trading",
        "kis_kr_trading",
        "schedule",
        "risk_limits",
        "exit_rules",
        "advanced_diagnostics",
    }.issubset(groups)
    flat_items = {item["key"]: item for item in body["items"]}
    assert flat_items["current_operation_mode"]["group"] == "global_safety"
    assert flat_items["kr_scheduler_mode"]["value_type"] == "enum"
    assert flat_items["max_live_orders_per_day"]["group"] == "risk_limits"
    assert flat_items["stop_loss_enabled"]["group"] == "exit_rules"
    for item in body["items"]:
        assert item["scope"] in {"global", "alpaca", "kis"}
        assert "market" in item
        assert "broker" in item
        assert "timezone" in item
        assert item["automation_scope"] in {
            "manual",
            "scheduler",
            "manual_and_scheduler",
            "diagnostics",
        }
        assert isinstance(item["affects"], list)


def test_settings_catalog_exposes_broker_scoped_cutoffs(client):
    body = client.get("/ops/settings/catalog").json()
    flat_items = {item["key"]: item for item in body["items"]}

    kr_cutoff = flat_items["kr_no_new_entry_after"]
    assert kr_cutoff["current_value"] == "14:50"
    assert kr_cutoff["scope"] == "kis"
    assert kr_cutoff["market"] == "KR"
    assert kr_cutoff["broker"] == "kis"
    assert kr_cutoff["timezone"] == "Asia/Seoul"
    assert kr_cutoff["automation_scope"] == "scheduler"

    us_cutoff = flat_items["us_no_new_entry_after"]
    assert us_cutoff["current_value"] == "15:45"
    assert us_cutoff["scope"] == "alpaca"
    assert us_cutoff["market"] == "US"
    assert us_cutoff["broker"] == "alpaca"
    assert us_cutoff["timezone"] == "America/New_York"
    assert us_cutoff["read_only"] is True
    assert us_cutoff["derived"] is True

    deprecated = flat_items["no_new_entry_after"]
    assert deprecated["deprecated"] is True
    assert deprecated["replacement_key"] == "kr_no_new_entry_after"


def test_kr_no_new_entry_after_maps_to_kis_limited_auto_buy_cutoff(client):
    response = client.put(
        "/ops/settings",
        json={"kr_no_new_entry_after": "14:40"},
    )

    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["kr_no_new_entry_after"] == "14:40"
    assert settings["no_new_entry_after"] == "14:40"
    assert settings["kis_limited_auto_buy_no_new_entry_after"] == "14:40"


def test_deprecated_no_new_entry_after_maps_to_kr_with_warning(client):
    response = client.put(
        "/ops/settings",
        json={"no_new_entry_after": "14:35"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["settings"]["kr_no_new_entry_after"] == "14:35"
    assert body["settings"]["kis_limited_auto_buy_no_new_entry_after"] == "14:35"
    assert body["deprecation_warnings"][0]["key"] == "no_new_entry_after"
    assert body["deprecation_warnings"][0]["replacement_key"] == (
        "kr_no_new_entry_after"
    )


def test_us_no_new_entry_after_is_derived_read_only(client):
    settings = client.get("/ops/settings").json()
    assert settings["us_no_new_entry_after"] == "15:45"
    assert settings["us_no_new_entry_after_read_only"] is True
    assert settings["us_no_new_entry_after_derived"] is True

    response = client.put(
        "/ops/settings",
        json={"us_no_new_entry_after": "15:40"},
    )

    assert response.status_code == 422
    assert "read-only/derived" in response.json()["detail"]
