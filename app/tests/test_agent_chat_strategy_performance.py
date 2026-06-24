from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import AgentChatStrategyAction, OrderLog
from app.main import app
from app.routes.agent_chat import get_agent_chat_orchestrator_service
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService
from app.services.agent_chat_tool_executor import AgentChatToolExecutor
from app.services.strategy_performance_service import StrategyPerformanceService


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    def orchestrator_service():
        performance = StrategyPerformanceService(
            position_loader=lambda db, provider, market: [],
        )
        return AgentChatOrchestratorService(
            intent_router=AgentChatIntentRouterService(settings=_router_settings()),
            tool_executor=AgentChatToolExecutor(
                strategy_performance_service=performance,
            ),
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_agent_chat_orchestrator_service] = orchestrator_service
    try:
        yield TestClient(app), db_session
    finally:
        app.dependency_overrides.clear()


def test_agent_chat_recognizes_monthly_performance(client):
    test_client, db_session = client

    response = test_client.post(
        "/agent/chat/send",
        json={"message": "이번 달 수익률 어때?", "auto_create_conversation": True},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["intent"]["category"] == "strategy_monthly_performance_query"
    assert body["answer"]["answer_type"] == "strategy_performance_answer"
    assert body["result_cards"][0]["card_type"] == "strategy_monthly_performance"
    assert body["safety"]["real_order_submitted"] is False
    assert db_session.query(OrderLog).count() == 0


def test_agent_chat_recognizes_daily_performance(client):
    test_client, _ = client

    response = test_client.post(
        "/agent/chat/send",
        json={"message": "오늘 손익 보여줘", "auto_create_conversation": True},
    )

    body = response.json()
    assert body["intent"]["category"] == "strategy_daily_performance_query"
    assert "실현손익" in body["answer"]["text"]
    assert body["safety"]["validation_called"] is False


def test_agent_chat_target_progress_includes_requested_profile_without_change(
    client,
):
    test_client, db_session = client

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "고수익형 목표까지 얼마나 남았어?",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert body["intent"]["category"] == "strategy_target_progress_query"
    assert body["intent"]["requested_profile"] == "aggressive"
    assert "고수익형" in body["answer"]["text"]
    assert db_session.query(AgentChatStrategyAction).count() == 0
    assert db_session.query(OrderLog).count() == 0


def test_agent_chat_trade_performance_does_not_submit_or_change_profile(client):
    test_client, db_session = client

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "어떤 거래가 제일 손실이 컸어?",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert body["intent"]["category"] == "strategy_trade_performance_query"
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["setting_changed"] is False
    assert body["safety"]["scheduler_changed"] is False
    assert db_session.query(AgentChatStrategyAction).count() == 0


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
