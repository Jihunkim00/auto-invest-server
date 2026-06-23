from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import AgentChatStrategyAction, OrderLog
from app.main import app
from app.routes.agent_chat import get_agent_chat_orchestrator_service
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService
from app.services.strategy_profile_service import StrategyProfileService


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    def orchestrator_service():
        return AgentChatOrchestratorService(
            intent_router=AgentChatIntentRouterService(settings=_router_settings()),
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_agent_chat_orchestrator_service] = orchestrator_service
    try:
        yield TestClient(app), db_session
    finally:
        app.dependency_overrides.clear()


def test_agent_chat_recognizes_safe_change_request_and_creates_pending_action(client):
    test_client, db_session = client

    response = test_client.post(
        "/agent/chat/send",
        json={"message": "안정형으로 바꿔줘", "auto_create_conversation": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["category"] == "strategy_profile_change_request"
    assert body["strategy_action"]["requested_profile"] == "safe"
    assert body["strategy_action"]["status"] == "pending_confirmation"
    assert body["answer"]["answer_type"] == "strategy_profile_change_confirmation_required"
    assert body["safety"]["setting_changed"] is False
    assert StrategyProfileService().active_profile(db_session).profile_name == "safe"
    assert db_session.query(AgentChatStrategyAction).count() == 1
    assert db_session.query(OrderLog).count() == 0


def test_agent_chat_aggressive_change_response_includes_risk_warning(client):
    test_client, _ = client

    response = test_client.post(
        "/agent/chat/send",
        json={"message": "고수익형으로 바꾸고 싶어", "auto_create_conversation": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["strategy_action"]["requested_profile"] == "aggressive"
    assert "손실 변동성" in body["answer"]["text"]
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["validation_called"] is False


def test_agent_chat_monthly_target_recommends_balanced(client):
    test_client, _ = client

    response = test_client.post(
        "/agent/chat/send",
        json={"message": "월 3~5프로 목표면 어떤 프로필이야?", "auto_create_conversation": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["category"] == "strategy_profile_recommendation"
    assert body["intent"]["requested_profile"] == "balanced"
    assert "보통형" in body["answer"]["text"]
    assert body["result_cards"][0]["card_type"] == "strategy_profile"


def test_agent_chat_monthly_five_or_more_maps_to_aggressive(client):
    test_client, _ = client

    response = test_client.post(
        "/agent/chat/send",
        json={"message": "월 5프로 이상 목표로 해줘", "auto_create_conversation": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["category"] == "strategy_profile_change_request"
    assert body["intent"]["requested_profile"] == "aggressive"
    assert body["strategy_action"]["requested_profile"] == "aggressive"


def test_agent_chat_profile_query_and_compare_return_strategy_answers(client):
    test_client, db_session = client
    StrategyProfileService().apply_preset(
        db_session,
        profile_name="balanced",
        confirm_operator_ack=True,
        source="settings_ui",
    )

    current = test_client.post(
        "/agent/chat/send",
        json={"message": "현재 전략 뭐야?", "auto_create_conversation": True},
    )
    compare = test_client.post(
        "/agent/chat/send",
        json={"message": "고수익형이랑 보통형 차이 알려줘", "auto_create_conversation": True},
    )

    assert current.status_code == 200
    assert current.json()["intent"]["category"] == "strategy_profile_query"
    assert "보통형" in current.json()["answer"]["text"]
    assert current.json()["safety"]["real_order_submitted"] is False
    assert compare.status_code == 200
    assert compare.json()["intent"]["category"] == "strategy_profile_compare"
    assert "안정형" in compare.json()["answer"]["text"]
    assert "고수익형" in compare.json()["answer"]["text"]


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

