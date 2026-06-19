from __future__ import annotations

from types import SimpleNamespace

from app.schemas.agent_chat_orchestrator import AgentChatSendRequest
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService


FORBIDDEN_SAFETY_FLAGS = (
    "real_order_submitted",
    "broker_submit_called",
    "manual_submit_called",
    "validation_called",
    "setting_changed",
    "scheduler_changed",
    "confirm_live_auto_checked",
    "broker_api_called",
    "agent_schedule_created",
    "mutation",
)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        openai_api_key=None,
        agent_chat_model="test-agent-router",
        agent_chat_reasoning_effort="low",
        agent_chat_temperature=None,
        agent_chat_timeout_seconds=1.0,
        agent_chat_fallback_enabled=True,
    )


def _service() -> AgentChatOrchestratorService:
    return AgentChatOrchestratorService(
        intent_router=AgentChatIntentRouterService(settings=_settings()),
        kis_client_factory=lambda db: _FakeKisClient(),
        alpaca_client_factory=lambda: _FakeAlpacaClient(),
    )


def _send(service, db_session, message: str, conversation_key: str | None = None):
    return service.send(
        db_session,
        request=AgentChatSendRequest(
            conversation_key=conversation_key,
            message=message,
            context={"default_market": "KR", "default_provider": "kis", "timezone": "Asia/Seoul"},
            auto_create_conversation=True,
        ),
    )


def test_price_then_analysis_followup_uses_last_symbol(db_session):
    service = _service()
    first = _send(service, db_session, "삼성전자 현재가 알려줘")
    second = _send(service, db_session, "방금 본 종목 분석해줘", first["conversation_key"])

    assert first["context_snapshot"]["last_symbol"] == "005930"
    assert second["intent"]["category"] == "analysis_request"
    assert second["intent"]["symbol"] == "005930"
    assert second["intent"]["provider"] == "kis"
    assert second["answer"]["answer_type"] == "analysis_summary"
    _assert_safe(second)


def test_us_price_then_manual_ticket_followup_keeps_us_provider_and_amount(db_session):
    service = _service()
    first = _send(service, db_session, "AAPL 현재가 알려줘")
    second = _send(service, db_session, "이거 10달러 매수 티켓 준비해줘", first["conversation_key"])

    assert first["context_snapshot"]["last_symbol"] == "AAPL"
    assert second["intent"]["category"] == "manual_ticket_request"
    assert second["intent"]["symbol"] == "AAPL"
    assert second["intent"]["provider"] == "alpaca"
    assert second["intent"]["notional"] == 10.0
    assert second["intent"]["currency"] == "USD"
    assert second["plan"]["command"]["budget"]["amount"] == 10.0
    assert second["answer"]["answer_type"] == "manual_ticket_prepared"
    _assert_safe(second)


def test_positions_then_first_holding_exit_review_uses_first_position_symbol(db_session):
    service = _service()
    first = _send(service, db_session, "내 보유종목 보여줘")
    second = _send(service, db_session, "첫 번째 종목 팔아야 해?", first["conversation_key"])

    assert first["context_snapshot"]["first_position_symbol"] == "005930"
    assert first["context_snapshot"]["last_symbol"] == "005930"
    assert second["intent"]["category"] == "exit_review_request"
    assert second["intent"]["symbol"] == "005930"
    assert second["intent"]["side"] == "sell"
    assert second["answer"]["answer_type"] == "analysis_summary"
    _assert_safe(second)


def _assert_safe(payload: dict) -> None:
    for flag in FORBIDDEN_SAFETY_FLAGS:
        assert payload["safety"][flag] is False


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
        return [
            {
                "symbol": "005930",
                "name": "삼성전자",
                "qty": 3,
                "market_value": 216000,
                "unrealized_pl": 12000,
            }
        ]

    def get_account_balance(self):
        return {"provider": "kis", "currency": "KRW", "cash": 500000}


class _FakeAlpacaClient:
    def get_latest_price(self, symbol: str):
        return {"symbol": symbol, "price": 190.25, "timestamp": "2026-06-18T00:00:00Z"}

    def list_positions(self):
        return []

    def get_account(self):
        return SimpleNamespace(cash="1000", portfolio_value="2000")
