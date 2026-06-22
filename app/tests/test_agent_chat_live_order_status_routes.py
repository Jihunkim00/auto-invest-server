from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.routes.agent_chat import get_agent_chat_live_order_service
from app.schemas.agent_chat import AgentChatConversationCreateRequest
from app.schemas.agent_chat_live_order import AgentChatLiveOrderCancelRequest
from app.schemas.agent_chat_orchestrator import AgentChatIntent, AgentChatIntentCategory
from app.services.agent_chat_live_order_service import AgentChatLiveOrderService
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
        return _service(calls)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_agent_chat_live_order_service] = live_order_service
    try:
        yield TestClient(app), db_session
    finally:
        app.dependency_overrides.clear()


def test_get_action_returns_sanitized_status_payload(client):
    test_client, db_session = client
    _enable(db_session)
    action = _prepare(_service(_Calls()), db_session, "route-get")

    response = test_client.get(f"/agent/chat/live-orders/{action['action_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["action_id"] == action["action_id"]
    assert body["conversation_key"]
    assert body["status"] == "pending_confirmation"
    assert body["safety_controls"]["agent_chat_live_order_enabled"] is True
    assert body["audit"]["requested_by"] == "agent_chat"
    assert body["confirmation_phrase"] is None
    assert "appsecret" not in str(body).lower()


def test_recent_actions_filters_by_status_and_conversation(client):
    test_client, db_session = client
    _enable(db_session)
    service = _service(_Calls())
    pending = _prepare(service, db_session, "route-recent-pending")
    cancelled = _prepare(service, db_session, "route-recent-cancelled")
    service.cancel(
        db_session,
        action_id=cancelled["action_id"],
        request=AgentChatLiveOrderCancelRequest(reason="test"),
    )

    response = test_client.get(
        "/agent/chat/live-orders/recent",
        params={"status": "cancelled", "conversation_key": cancelled["conversation_key"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["actions"][0]["action_id"] == cancelled["action_id"]
    assert body["actions"][0]["status"] == "cancelled"
    assert body["actions"][0]["action_id"] != pending["action_id"]


def _service(calls: _Calls) -> AgentChatLiveOrderService:
    return AgentChatLiveOrderService(
        kis_client_factory=lambda db: _FakeKisClient(),
        validation_service_factory=lambda client: _FakeValidationService(calls),
        manual_order_service_factory=lambda client: _FakeManualOrderService(calls),
    )


def _prepare(service: AgentChatLiveOrderService, db_session, title: str) -> dict:
    conversation_key = AgentChatService().create_conversation(
        db_session,
        request=AgentChatConversationCreateRequest(title=title),
    )["conversation"]["conversation_key"]
    return service.prepare(
        db_session,
        intent=AgentChatIntent(
            category=AgentChatIntentCategory.LIVE_ORDER_REQUEST,
            market="KR",
            provider="kis",
            symbol="005930",
            symbol_name="Samsung Electronics",
            side="buy",
            quantity=1,
        ),
        conversation_key=conversation_key,
        user_message_id=10,
    )["action"]


def _enable(db_session):
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": True,
            "kill_switch": False,
            "agent_chat_live_order_enabled": True,
            "agent_chat_live_order_kis_enabled": True,
            "agent_chat_live_order_buy_enabled": True,
            "agent_chat_live_order_max_orders_per_day": 3,
            "agent_chat_live_order_max_notional_pct": 1.0,
            "agent_chat_live_order_max_notional_krw": 1000000,
        },
    )
