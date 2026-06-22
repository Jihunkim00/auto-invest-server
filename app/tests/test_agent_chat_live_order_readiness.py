from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import AgentChatOrderAction, KisOrderValidationLog, OrderLog, RuntimeSetting
from app.main import app
from app.services.runtime_setting_service import RuntimeSettingService


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "kis_enabled": False,
        "kis_real_order_enabled": False,
        "kis_env": "prod",
        "kis_app_key": "real-app-key",
        "kis_app_secret": "real-app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_base_url": "https://openapi.koreainvestment.com:9443",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        return TestClient(app)
    finally:
        pass


def test_default_readiness_is_blocked_and_read_only(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=False, kis_real_order_enabled=False),
    )
    client = _client(db_session)
    try:
        response = client.get("/agent/chat/live-orders/readiness")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    checks = {item["key"]: item for item in body["checks"]}
    assert body["status"] == "blocked"
    assert body["ready"] is False
    assert body["ready_for_chat_confirmed_live_order"] is False
    assert checks["dry_run"]["ok"] is False
    assert checks["agent_chat_live_order_enabled"]["ok"] is False
    assert checks["kis_enabled"]["ok"] is False
    assert body["safety"]["read_only"] is True
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["validation_called"] is False
    assert body["safety"]["manual_submit_called"] is False
    assert db_session.query(RuntimeSetting).count() == 0
    assert db_session.query(AgentChatOrderAction).count() == 0
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0


def test_readiness_reports_limits_and_daily_remaining(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": False,
            "agent_chat_live_order_enabled": True,
            "agent_chat_live_order_kis_enabled": True,
            "agent_chat_live_order_buy_enabled": True,
            "agent_chat_live_order_max_orders_per_day": 1,
            "agent_chat_live_order_max_notional_krw": 50000,
            "agent_chat_live_order_max_notional_pct": 0.03,
        },
    )
    now = datetime.now(UTC)
    db_session.add(
        AgentChatOrderAction(
            conversation_key="conv-1",
            action_type="chat_confirmed_live_order",
            provider="kis",
            market="KR",
            symbol="005930",
            side="buy",
            order_type="market",
            quantity=1,
            status="submitted",
            scope_hash="abc",
            confirmation_phrase="005930 buy 1 confirm",
            expires_at=(now + timedelta(minutes=5)).replace(tzinfo=None),
            submitted_at=now.replace(tzinfo=None),
        )
    )
    db_session.commit()
    client = _client(db_session)
    try:
        response = client.get("/agent/chat/live-orders/readiness")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    checks = {item["key"]: item for item in body["checks"]}
    assert body["limits"]["max_orders_per_day"] == 1
    assert body["limits"]["orders_used_today"] == 1
    assert body["limits"]["orders_remaining_today"] == 0
    assert checks["agent_chat_live_order_daily_remaining"]["ok"] is False
    assert body["capabilities"]["buy_enabled"] is True
    assert body["capabilities"]["sell_enabled"] is False
    assert body["runtime"]["kis_enabled"] is True
    assert body["runtime"]["kis_real_order_enabled"] is True
