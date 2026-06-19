from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import AgentChatMessage
from app.main import app
from app.routes.agent_chat import get_agent_chat_orchestrator_service
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService


MOJIBAKE_MARKERS = tuple(chr(code) for code in (0x00EC, 0x00EB, 0x00EA, 0xFFFD))


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


def test_agent_chat_korean_utf8_survives_response_storage_and_json_roundtrip(client, db_session):
    request_text = "삼성전자 현재가 알려줘"
    response = client.post(
        "/agent/chat/send",
        json={
            "conversation_key": None,
            "message": request_text,
            "context": {"default_market": "KR", "default_provider": "kis", "timezone": "Asia/Seoul"},
            "auto_create_conversation": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    response_text = json.dumps(payload, ensure_ascii=False)
    assert "삼성전자" in response_text
    assert "현재가" in response_text
    assert "주문" in response_text
    assert payload["diagnostics"]["encoding_safe"] is True
    assert payload["diagnostics"]["answer_contains_mojibake_marker"] is False
    assert not any(marker in response_text for marker in MOJIBAKE_MARKERS)

    roundtrip = json.loads(json.dumps(payload, ensure_ascii=False))
    assert roundtrip["intent"]["symbol_name"] == "삼성전자"
    assert "삼성전자" in roundtrip["answer"]["text"]
    assert not any(marker in json.dumps(roundtrip, ensure_ascii=False) for marker in MOJIBAKE_MARKERS)

    messages = db_session.query(AgentChatMessage).order_by(AgentChatMessage.id.asc()).all()
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].text == request_text
    assert "삼성전자" in messages[1].text
    assert "현재가" in messages[1].text

    stored_text = "\n".join(
        item for message in messages for item in [message.text, message.metadata_json or "", message.safety_json or ""]
    )
    assert "삼성전자" in stored_text
    assert not any(marker in stored_text for marker in MOJIBAKE_MARKERS)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        openai_api_key=None,
        agent_chat_model="test-agent-router",
        agent_chat_reasoning_effort="low",
        agent_chat_temperature=None,
        agent_chat_timeout_seconds=1.0,
        agent_chat_fallback_enabled=True,
    )


class _FakeKisClient:
    def get_domestic_stock_price(self, symbol: str):
        return {
            "provider": "kis",
            "symbol": symbol,
            "name": "삼성전자",
            "current_price": 72000,
            "timestamp": "2026-06-18T09:00:00+09:00",
        }

    def list_positions(self):
        return [{"symbol": "005930", "name": "삼성전자", "qty": 3}]

    def get_account_balance(self):
        return {"provider": "kis", "currency": "KRW", "cash": 500000}


class _FakeAlpacaClient:
    def get_latest_price(self, symbol: str):
        return {"symbol": symbol, "price": 190.25}

    def list_positions(self):
        return []

    def get_account(self):
        return SimpleNamespace(cash="1000", portfolio_value="2000")
