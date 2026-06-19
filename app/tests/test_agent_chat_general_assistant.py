from __future__ import annotations

from types import SimpleNamespace

from app.schemas.agent_chat_orchestrator import AgentChatSendRequest
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService


def _settings():
    return SimpleNamespace(
        openai_api_key=None,
        agent_chat_model="test-agent-router",
        agent_chat_reasoning_effort="low",
        agent_chat_temperature=None,
        agent_chat_timeout_seconds=1.0,
        agent_chat_fallback_enabled=True,
    )


def _service():
    return AgentChatOrchestratorService(
        intent_router=AgentChatIntentRouterService(settings=_settings()),
        kis_client_factory=lambda db: _FakeKisClient(),
        alpaca_client_factory=lambda: _FakeAlpacaClient(),
    )


def _send(db_session, message: str, conversation_key: str | None = None):
    return _service().send(
        db_session,
        request=AgentChatSendRequest(
            conversation_key=conversation_key,
            message=message,
            context={
                "default_market": "KR",
                "default_provider": "kis",
                "timezone": "Asia/Seoul",
            },
            auto_create_conversation=True,
        ),
    )


def test_general_assistant_answer_has_no_plan_or_tool_execution(db_session):
    payload = _send(db_session, "너는 뭐 할 수 있어?")

    assert payload["intent"]["category"] == "capability_question"
    assert payload["selected_tools"] == []
    assert payload["tool_results"] == []
    assert payload["plan"] is None
    assert payload["answer"]["text"]
    assert payload["follow_up_suggestions"]
    assert payload["safety"]["real_order_submitted"] is False
    assert payload["safety"]["setting_changed"] is False


def test_dry_run_status_uses_ops_settings_lookup_read_only(db_session):
    payload = _send(db_session, "dry run 켜져 있어?")

    assert payload["intent"]["category"] == "read_only_settings_query"
    assert payload["selected_tools"][0]["tool_name"] == "ops_settings_lookup"
    assert payload["tool_results"][0]["status"] == "success"
    assert payload["result_cards"][0]["card_type"] == "settings"
    assert payload["safety"]["read_only"] is True
    assert payload["safety"]["setting_changed"] is False


def test_follow_up_analysis_uses_previous_symbol_context(db_session):
    first = _send(db_session, "삼성전자 현재가 얼마야?")
    second = _send(db_session, "그럼 살만해?", conversation_key=first["conversation_key"])

    assert first["intent"]["symbol"] == "005930"
    assert first["selected_tools"][0]["tool_name"] == "kis_price_lookup"
    assert first["result_cards"][0]["card_type"] == "price"
    assert second["intent"]["category"] == "analysis_request"
    assert second["intent"]["symbol"] == "005930"
    assert second["context_snapshot"]["last_symbol"] == "005930"
    assert second["selected_tools"][0]["tool_name"] == "safe_symbol_analysis"
    assert second["safety"]["real_order_submitted"] is False


def test_live_order_request_returns_blocker_tool_and_manual_plan_only(db_session):
    payload = _send(db_session, "삼성전자 지금 3만원 사줘")

    assert payload["intent"]["category"] == "live_order_request"
    assert payload["selected_tools"][0]["tool_name"] == "live_order_request_blocker"
    assert payload["tool_results"][0]["status"] == "blocked"
    assert payload["answer"]["answer_type"] == "blocked"
    assert payload["plan"]["command_type"] == "PREPARE_MANUAL_BUY_TICKET"
    assert payload["safety"]["real_order_submitted"] is False
    assert payload["safety"]["validation_called"] is False


class _FakeKisClient:
    def get_domestic_stock_price(self, symbol: str):
        return {
            "symbol": symbol,
            "name": "삼성전자",
            "current_price": 72000,
            "timestamp": "2026-06-19T09:00:00+09:00",
        }

    def list_positions(self):
        return [{"symbol": "005930", "name": "삼성전자", "qty": 1}]

    def get_account_balance(self):
        return {"provider": "kis", "currency": "KRW", "cash": 100000}


class _FakeAlpacaClient:
    def get_latest_price(self, symbol: str):
        return {"symbol": symbol, "price": 190.25}

    def list_positions(self):
        return []

    def get_account(self):
        return SimpleNamespace(cash="1000", portfolio_value="2000")
