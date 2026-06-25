from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import KisOrderValidationLog, OrderLog
from app.main import app
from app.routes.agent_chat import get_agent_chat_orchestrator_service
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService
from app.services.agent_chat_tool_executor import AgentChatToolExecutor
from app.tests.test_target_aware_risk_service import _service


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    def orchestrator_service():
        return AgentChatOrchestratorService(
            intent_router=AgentChatIntentRouterService(settings=_router_settings()),
            tool_executor=AgentChatToolExecutor(
                target_aware_risk_service=_service(),
            ),
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_agent_chat_orchestrator_service] = (
        orchestrator_service
    )
    try:
        yield TestClient(app), db_session
    finally:
        app.dependency_overrides.clear()


def test_agent_chat_recognizes_new_entry_risk_question(client):
    test_client, db_session = client

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "지금 신규 진입 가능해?",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["intent"]["category"] == "strategy_entry_risk_query"
    assert body["selected_tools"][0]["tool_name"] == "strategy_entry_risk_evaluate"
    assert body["answer"]["answer_type"] == "strategy_risk_answer"
    assert "safe" in body["answer"]["text"]
    assert body["result_cards"][0]["card_type"] == "strategy_entry_risk"
    assert db_session.query(OrderLog).count() == 0


def test_agent_chat_recognizes_daily_loss_limit_question(client):
    test_client, _ = client

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "오늘 손실 한도 괜찮아?",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["intent"]["category"] == "strategy_loss_limit_query"
    assert body["selected_tools"][0]["tool_name"] == "strategy_risk_state_lookup"
    assert body["answer"]["answer_type"] == "strategy_risk_answer"


def test_agent_chat_risk_tool_never_submits_or_validates(client):
    test_client, db_session = client

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "보통형이면 얼마까지 주문 가능해?",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert body["intent"]["category"] == "strategy_order_sizing_query"
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["validation_called"] is False
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0


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
