from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import AgentChatOrderAction, KisOrderValidationLog, OrderLog
from app.main import app
from app.routes.agent_chat import get_agent_chat_orchestrator_service
from app.services.agent_chat_intent_router_service import (
    AgentChatIntentRouterService,
)
from app.services.agent_chat_orchestrator_service import (
    AgentChatOrchestratorService,
)
from app.services.agent_chat_tool_executor import AgentChatToolExecutor
from app.tests.test_strategy_dry_run_auto_buy_service import (
    candidate,
    preview,
    service,
)


class ChatDryRunService:
    def __init__(self):
        self.inner = service()

    def run_once(self, db, request):
        return self.inner.run_once(
            db,
            request,
            preview_override=preview(candidate()),
        )

    def recent(self, db, **kwargs):
        return self.inner.recent(db, **kwargs)

    def summary(self, db, **kwargs):
        return self.inner.summary(db, **kwargs)


@pytest.fixture()
def client(db_session):
    dry_run_service = ChatDryRunService()

    def override_get_db():
        yield db_session

    def orchestrator_service():
        return AgentChatOrchestratorService(
            intent_router=AgentChatIntentRouterService(
                settings=_router_settings()
            ),
            tool_executor=AgentChatToolExecutor(
                dry_run_auto_buy_service_factory=lambda db: dry_run_service,
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


def test_agent_chat_recognizes_today_auto_buy_candidate_request(client):
    test_client, db_session = client

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "오늘 자동매수 후보 있어?",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["intent"]["category"] == "strategy_dry_run_auto_buy_request"
    assert body["selected_tools"][0]["tool_name"] == (
        "strategy_dry_run_auto_buy_once"
    )
    assert body["answer"]["answer_type"] == (
        "strategy_dry_run_auto_buy_answer"
    )
    assert "주문은 제출되지 않았" in body["answer"]["text"]
    assert body["live_order_action"] is None
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["validation_called"] is False
    assert db_session.query(AgentChatOrderAction).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0
    simulated = db_session.query(OrderLog).one()
    assert simulated.internal_status == "DRY_RUN_SIMULATED"
    assert simulated.broker_order_id is None


def test_agent_chat_explicit_balanced_profile_runs_dry_run_only(client):
    test_client, _ = client

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "보통형 기준이면 오늘 샀을까?",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert body["intent"]["category"] == "strategy_dry_run_auto_buy_request"
    assert body["intent"]["requested_profile"] == "balanced"
    assert body["tool_results"][0]["data"]["active_profile"] == "balanced"
    assert body["result_cards"][0]["card_type"] == (
        "strategy_dry_run_auto_buy"
    )
    assert "DRY RUN ONLY" in body["result_cards"][0]["badges"]
    assert "NO ORDER SUBMIT" in body["result_cards"][0]["badges"]


def test_agent_chat_recent_dry_run_query_does_not_create_live_action(client):
    test_client, db_session = client
    test_client.post(
        "/agent/chat/send",
        json={
            "message": "오늘 자동매수 후보 있어?",
            "auto_create_conversation": True,
        },
    )

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "최근 dry-run 매수 후보는 뭐였어?",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert body["intent"]["category"] == (
        "strategy_dry_run_auto_buy_recent_query"
    )
    assert body["live_order_action"] is None
    assert db_session.query(AgentChatOrderAction).count() == 0


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
