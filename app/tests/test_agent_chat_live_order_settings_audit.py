from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import AgentChatLiveOrderSettingsAudit
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
        "kis_access_token": "secret-access-token",
        "kis_approval_key": "secret-approval-key",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_preset_writes_sanitized_settings_audit(monkeypatch, client):
    test_client, db_session = client
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": False,
            "agent_chat_live_order_enabled": False,
            "agent_chat_live_order_buy_enabled": False,
        },
    )

    response = test_client.post(
        "/agent/chat/live-orders/settings/preset",
        json={"preset": "chat_confirmed_buy_only", "confirm_operator_ack": True},
    )

    assert response.status_code == 200
    body = response.json()
    row = db_session.get(AgentChatLiveOrderSettingsAudit, body["audit_id"])
    assert row is not None
    assert row.changed_by == "operator_ui"
    assert row.source == "agent_chat_live_order_settings"
    assert row.preset == "chat_confirmed_buy_only"
    assert row.confirm_operator_ack is True

    before = json.loads(row.before_snapshot_json)
    after = json.loads(row.after_snapshot_json)
    request_payload = json.loads(row.request_payload_json)
    safety = json.loads(row.safety_json)
    assert before["agent_chat_live_order_buy_enabled"] is False
    assert after["agent_chat_live_order_buy_enabled"] is True
    assert after["agent_chat_live_order_sell_enabled"] is False
    assert request_payload["preset"] == "chat_confirmed_buy_only"
    assert request_payload["confirm_operator_ack"] is True
    assert safety["real_order_submitted"] is False
    assert safety["validation_called"] is False
    assert safety["broker_submit_called"] is False
    assert safety["manual_submit_called"] is False
    assert safety["scheduler_changed"] is False

    raw = "\n".join(
        [
            row.before_snapshot_json,
            row.after_snapshot_json,
            row.request_payload_json,
            row.safety_json,
        ]
    )
    assert "real-app-secret" not in raw
    assert "secret-access-token" not in raw
    assert "secret-approval-key" not in raw


def test_missing_ack_does_not_write_audit(client):
    test_client, db_session = client

    response = test_client.post(
        "/agent/chat/live-orders/settings/preset",
        json={"preset": "chat_confirmed_full_guarded", "confirm_operator_ack": False},
    )

    assert response.status_code == 409
    assert db_session.query(AgentChatLiveOrderSettingsAudit).count() == 0
