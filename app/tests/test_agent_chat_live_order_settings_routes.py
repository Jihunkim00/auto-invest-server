from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import AgentChatOrderAction, KisOrderValidationLog, OrderLog
from app.main import app
from app.services.runtime_setting_service import RuntimeSettingService


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), db_session
    finally:
        app.dependency_overrides.clear()


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "kis_enabled": True,
        "kis_real_order_enabled": True,
        "kis_env": "prod",
        "kis_app_key": "real-app-key",
        "kis_app_secret": "real-app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_base_url": "https://openapi.koreainvestment.com:9443",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_safe_off_preset_disables_chat_live_order_flags(monkeypatch, client):
    test_client, db_session = client
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": False,
            "kill_switch": True,
            "agent_chat_live_order_enabled": True,
            "agent_chat_live_order_kis_enabled": True,
            "agent_chat_live_order_buy_enabled": True,
            "agent_chat_live_order_sell_enabled": True,
            "agent_chat_live_order_requires_confirm": True,
        },
    )

    response = test_client.post(
        "/agent/chat/live-orders/settings/preset",
        json={"preset": "safe_off", "confirm_operator_ack": True},
    )

    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["dry_run"] is False
    assert settings["kill_switch"] is True
    assert settings["agent_chat_live_order_enabled"] is False
    assert settings["agent_chat_live_order_kis_enabled"] is False
    assert settings["agent_chat_live_order_buy_enabled"] is False
    assert settings["agent_chat_live_order_sell_enabled"] is False
    assert settings["agent_chat_live_order_requires_confirm"] is True


@pytest.mark.parametrize(
    ("preset", "buy_enabled", "sell_enabled"),
    [
        ("chat_confirmed_test", False, False),
        ("chat_confirmed_buy_only", True, False),
        ("chat_confirmed_sell_only", False, True),
        ("chat_confirmed_full_guarded", True, True),
    ],
)
def test_chat_live_order_presets_apply_guarded_flags(
    monkeypatch,
    client,
    preset,
    buy_enabled,
    sell_enabled,
):
    test_client, db_session = client
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": False,
            "kill_switch": True,
            "kis_scheduler_live_enabled": True,
            "kis_scheduler_allow_real_orders": True,
            "kis_scheduler_buy_enabled": True,
        },
    )

    response = test_client.post(
        "/agent/chat/live-orders/settings/preset",
        json={"preset": preset, "confirm_operator_ack": True},
    )

    assert response.status_code == 200
    body = response.json()
    settings = body["settings"]
    assert settings["dry_run"] is False
    assert settings["kill_switch"] is True
    assert settings["kis_scheduler_live_enabled"] is True
    assert settings["kis_scheduler_allow_real_orders"] is True
    assert settings["kis_scheduler_buy_enabled"] is True
    assert settings["agent_chat_live_order_enabled"] is True
    assert settings["agent_chat_live_order_kis_enabled"] is True
    assert settings["agent_chat_live_order_buy_enabled"] is buy_enabled
    assert settings["agent_chat_live_order_sell_enabled"] is sell_enabled
    assert settings["agent_chat_live_order_requires_confirm"] is True
    assert settings["agent_chat_live_order_max_orders_per_day"] == 1
    assert settings["agent_chat_live_order_max_notional_krw"] == 50000
    assert settings["agent_chat_live_order_max_notional_pct"] == 0.03
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["validation_called"] is False
    assert body["safety"]["manual_submit_called"] is False
    assert body["safety"]["scheduler_changed"] is False
    assert db_session.query(AgentChatOrderAction).count() == 0
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0


def test_preset_requires_operator_ack_and_does_not_change_settings(client):
    test_client, db_session = client
    before = RuntimeSettingService().get_settings(db_session)

    response = test_client.post(
        "/agent/chat/live-orders/settings/preset",
        json={"preset": "chat_confirmed_buy_only", "confirm_operator_ack": False},
    )

    assert response.status_code == 409
    after = RuntimeSettingService().get_settings(db_session)
    assert after["agent_chat_live_order_enabled"] == before["agent_chat_live_order_enabled"]
    assert after["agent_chat_live_order_buy_enabled"] == before["agent_chat_live_order_buy_enabled"]


def test_settings_update_rejects_forbidden_fields(client):
    test_client, db_session = client
    before = RuntimeSettingService().get_settings(db_session)

    response = test_client.put(
        "/agent/chat/live-orders/settings",
        json={"confirm_operator_ack": True, "dry_run": False},
    )

    assert response.status_code == 422
    after = RuntimeSettingService().get_settings(db_session)
    assert after["dry_run"] == before["dry_run"]


def test_settings_update_allows_only_chat_live_order_namespace(client):
    test_client, db_session = client

    response = test_client.put(
        "/agent/chat/live-orders/settings",
        json={
            "confirm_operator_ack": True,
            "agent_chat_live_order_enabled": True,
            "agent_chat_live_order_kis_enabled": True,
            "agent_chat_live_order_buy_enabled": True,
            "agent_chat_live_order_max_orders_per_day": 2,
            "agent_chat_live_order_max_notional_krw": 75000,
            "agent_chat_live_order_max_notional_pct": 0.05,
        },
    )

    assert response.status_code == 200
    body = response.json()
    settings = body["settings"]
    assert settings["agent_chat_live_order_enabled"] is True
    assert settings["agent_chat_live_order_kis_enabled"] is True
    assert settings["agent_chat_live_order_buy_enabled"] is True
    assert settings["agent_chat_live_order_sell_enabled"] is False
    assert settings["agent_chat_live_order_max_orders_per_day"] == 2
    assert settings["agent_chat_live_order_max_notional_krw"] == 75000
    assert settings["agent_chat_live_order_max_notional_pct"] == 0.05
    assert set(body["changed_keys"]).issuperset(
        {
            "agent_chat_live_order_enabled",
            "agent_chat_live_order_kis_enabled",
            "agent_chat_live_order_buy_enabled",
            "agent_chat_live_order_max_orders_per_day",
            "agent_chat_live_order_max_notional_krw",
            "agent_chat_live_order_max_notional_pct",
        }
    )
