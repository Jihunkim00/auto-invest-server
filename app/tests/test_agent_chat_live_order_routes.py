from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import AgentChatOrderAction, OrderLog
from app.main import app
from app.routes.agent_chat import (
    get_agent_chat_live_order_service,
    get_agent_chat_orchestrator_service,
)
from app.schemas.agent_chat import AgentChatConversationCreateRequest
from app.schemas.agent_chat_orchestrator import AgentChatIntent, AgentChatIntentCategory
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_live_order_service import AgentChatLiveOrderService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService
from app.services.agent_chat_service import AgentChatService
from app.services.runtime_setting_service import RuntimeSettingService

from app.tests.test_agent_chat_live_order_service import (
    _Calls,
    _FakeKisClient,
    _FakeManualOrderService,
    _FakeValidationService,
)


@pytest.fixture()
def client(db_session):
    calls = _Calls()

    def override_get_db():
        yield db_session

    def live_order_service():
        return _live_order_service(calls)

    def orchestrator_service():
        return AgentChatOrchestratorService(
            intent_router=AgentChatIntentRouterService(settings=_router_settings()),
            kis_client_factory=lambda db: _FakeKisClient(),
            live_order_service=_live_order_service(calls),
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_agent_chat_live_order_service] = live_order_service
    app.dependency_overrides[get_agent_chat_orchestrator_service] = orchestrator_service
    try:
        yield TestClient(app), db_session, calls
    finally:
        app.dependency_overrides.clear()


def test_chat_send_live_order_request_returns_pending_action(client):
    test_client, db_session, calls = client
    _enable_chat_live_order(db_session)

    response = test_client.post(
        "/agent/chat/send",
        json={
            "conversation_key": None,
            "message": "005930 buy now 1",
            "context": {"default_market": "KR", "default_provider": "kis"},
            "auto_create_conversation": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["category"] == "live_order_request"
    assert body["answer"]["answer_type"] == "live_order_confirmation_required"
    assert body["live_order_action"]["status"] == "pending_confirmation"
    assert body["live_order_action"]["symbol"] == "005930"
    assert "confirm_live_order" in body["available_actions"]
    assert "cancel_live_order" in body["available_actions"]
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["validation_called"] is False
    assert body["safety"]["broker_submit_called"] is False
    assert body["safety"]["manual_submit_called"] is False
    assert db_session.query(AgentChatOrderAction).count() == 1
    assert db_session.query(OrderLog).count() == 0
    assert calls.validation == 0
    assert calls.manual_submit == 0


def test_chat_send_default_settings_do_not_create_pending_action(client):
    test_client, db_session, calls = client

    response = test_client.post(
        "/agent/chat/send",
        json={
            "conversation_key": None,
            "message": "005930 buy now 1",
            "context": {"default_market": "KR", "default_provider": "kis"},
            "auto_create_conversation": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["category"] == "live_order_request"
    assert body.get("live_order_action") is None
    assert body["answer"]["answer_type"] == "blocked"
    assert body["safety"]["real_order_submitted"] is False
    assert db_session.query(AgentChatOrderAction).count() == 0
    assert db_session.query(OrderLog).count() == 0
    assert calls.validation == 0
    assert calls.manual_submit == 0


def test_confirm_endpoint_submits_via_live_order_service(monkeypatch, client):
    test_client, db_session, calls = client
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    _enable_chat_live_order(db_session, dry_run=False)
    conversation_key = AgentChatService().create_conversation(
        db_session,
        request=AgentChatConversationCreateRequest(title="route confirm"),
    )["conversation"]["conversation_key"]
    service = _live_order_service(calls)
    action = service.prepare(
        db_session,
        intent=AgentChatIntent(
            category=AgentChatIntentCategory.LIVE_ORDER_REQUEST,
            market="KR",
            provider="kis",
            symbol="005930",
            side="buy",
            quantity=1,
        ),
        conversation_key=conversation_key,
        user_message_id=None,
    )["action"]

    response = test_client.post(
        f"/agent/chat/live-orders/{action['action_id']}/confirm",
        json={
            "confirmation": True,
            "confirmation_token": action["confirmation_token"],
            "user_acknowledged_live_order": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "submitted"
    assert body["safety"]["real_order_submitted"] is True
    assert calls.validation == 1
    assert calls.manual_submit == 1


def _enable_chat_live_order(db_session, *, dry_run: bool = True):
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": dry_run,
            "kill_switch": False,
            "agent_chat_live_order_enabled": True,
            "agent_chat_live_order_kis_enabled": True,
            "agent_chat_live_order_buy_enabled": True,
            "agent_chat_live_order_max_notional_pct": 1.0,
            "agent_chat_live_order_max_notional_krw": 1000000,
        },
    )


def _live_order_service(calls: _Calls) -> AgentChatLiveOrderService:
    return AgentChatLiveOrderService(
        kis_client_factory=lambda db: _FakeKisClient(),
        validation_service_factory=lambda client: _FakeValidationService(calls),
        manual_order_service_factory=lambda client: _FakeManualOrderService(calls),
    )


def _router_settings():
    return type(
        "Settings",
        (),
        {
            "openai_api_key": None,
            "agent_chat_model": "test-agent-router",
            "agent_chat_reasoning_effort": "low",
            "agent_chat_temperature": None,
            "agent_chat_timeout_seconds": 1.0,
            "agent_chat_fallback_enabled": True,
        },
    )()


def _settings(**overrides) -> Settings:
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
