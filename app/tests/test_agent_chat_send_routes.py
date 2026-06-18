from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.routes.agent_chat import get_agent_chat_orchestrator_service
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    def override_service():
        return AgentChatOrchestratorService(
            intent_router=AgentChatIntentRouterService(settings=_settings()),
            kis_client_factory=lambda db: _FakeKisClient(),
            alpaca_client_factory=lambda: _FakeAlpacaClient(),
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_agent_chat_orchestrator_service] = override_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _settings():
    return SimpleNamespace(
        openai_api_key=None,
        agent_chat_model="test-agent-router",
        agent_chat_reasoning_effort="low",
        agent_chat_temperature=None,
        agent_chat_timeout_seconds=1.0,
        agent_chat_fallback_enabled=True,
    )


def test_agent_chat_send_creates_conversation_and_assistant_answer(client):
    response = client.post(
        "/agent/chat/send",
        json={
            "conversation_key": None,
            "message": "삼성전자 주식 지금 가격 얼마야?",
            "context": {
                "default_market": "KR",
                "default_provider": "kis",
                "timezone": "Asia/Seoul",
            },
            "auto_create_conversation": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["conversation_key"].startswith("conv_")
    assert payload["user_message_id"] is not None
    assert payload["assistant_message_id"] is not None
    assert payload["intent"]["category"] == "read_only_price_query"
    assert payload["intent"]["symbol"] == "005930"
    assert payload["answer"]["answer_type"] == "read_only_result"
    assert payload["safety"]["real_order_submitted"] is False
    assert payload["safety"]["validation_called"] is False

    messages = client.get(f"/agent/chat/conversations/{payload['conversation_key']}/messages")
    assert messages.status_code == 200
    assert messages.json()["count"] == 2
    assert [item["role"] for item in messages.json()["messages"]] == ["user", "assistant"]


def test_agent_chat_send_reuses_existing_conversation(client):
    created = client.post("/agent/chat/conversations", json={"title": "Existing"})
    key = created.json()["conversation"]["conversation_key"]

    response = client.post(
        "/agent/chat/send",
        json={
            "conversation_key": key,
            "message": "내 보유종목 보여줘",
            "context": {"default_market": "KR", "default_provider": "kis"},
        },
    )

    assert response.status_code == 200
    assert response.json()["conversation_key"] == key
    assert response.json()["intent"]["category"] == "read_only_positions_query"


def test_agent_chat_send_invalid_conversation_returns_404(client):
    response = client.post(
        "/agent/chat/send",
        json={
            "conversation_key": "missing",
            "message": "삼전 현재가",
            "context": {"default_market": "KR", "default_provider": "kis"},
        },
    )

    assert response.status_code == 404


class _FakeKisClient:
    def get_domestic_stock_price(self, symbol: str):
        return {
            "symbol": symbol,
            "name": "삼성전자",
            "current_price": 72000,
            "timestamp": "2026-06-18T09:00:00+09:00",
        }

    def list_positions(self):
        return [{"symbol": "005930", "name": "삼성전자", "qty": 1}]

    def get_account_balance(self):
        return {"currency": "KRW", "cash": 100000}


class _FakeAlpacaClient:
    def get_latest_price(self, symbol: str):
        return {"symbol": symbol, "price": 190.25}

    def list_positions(self):
        return []

    def get_account(self):
        return SimpleNamespace(cash="1000", portfolio_value="2000")
