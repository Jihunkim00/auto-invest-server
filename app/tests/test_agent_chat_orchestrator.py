from __future__ import annotations

from types import SimpleNamespace

from app.db.models import AgentChatMessage, OrderLog
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


def _context():
    return {
        "default_market": "KR",
        "default_provider": "kis",
        "timezone": "Asia/Seoul",
    }


def _service(kis_client=None, alpaca_client=None):
    return AgentChatOrchestratorService(
        intent_router=AgentChatIntentRouterService(settings=_settings()),
        kis_client_factory=lambda db: kis_client or _FakeKisClient(),
        alpaca_client_factory=lambda: alpaca_client or _FakeAlpacaClient(),
    )


def _send(service, db_session, message: str):
    return service.send(
        db_session,
        request=AgentChatSendRequest(
            conversation_key=None,
            message=message,
            context=_context(),
            auto_create_conversation=True,
        ),
    )


def test_general_chat_returns_assistant_answer_without_plan(db_session):
    payload = _send(_service(), db_session, "너 뭐 할 수 있어?")

    assert payload["intent"]["category"] == "capability_question"
    assert payload["answer"]["text"]
    assert payload["plan"] is None
    assert payload["safety"]["real_order_submitted"] is False
    assert payload["safety"]["validation_called"] is False


def test_korean_price_query_returns_read_only_answer_and_saves_messages(db_session):
    payload = _send(_service(), db_session, "삼성전자 지금 가격 얼마야?")

    assert payload["intent"]["category"] == "read_only_price_query"
    assert payload["intent"]["symbol"] == "005930"
    assert payload["data"]["price"]["price"] == 72000
    assert "현재가" in payload["answer"]["text"]
    assert payload["answer"]["answer_type"] == "read_only_result"
    assert payload["plan"] is None
    assert payload["safety"]["read_only"] is True
    assert payload["safety"]["real_order_submitted"] is False
    assert payload["safety"]["broker_submit_called"] is False
    assert payload["safety"]["manual_submit_called"] is False
    assert payload["safety"]["validation_called"] is False

    messages = db_session.query(AgentChatMessage).order_by(AgentChatMessage.id.asc()).all()
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[-1].message_type == "read_only_result"


def test_positions_query_uses_read_only_lookup(db_session):
    payload = _send(_service(), db_session, "내 보유종목 보여줘")

    assert payload["intent"]["category"] == "read_only_positions_query"
    assert payload["data"]["count"] == 1
    assert "보유종목" in payload["answer"]["text"]
    assert payload["plan"] is None
    assert payload["safety"]["real_order_submitted"] is False


def test_recent_orders_query_reads_local_logs(db_session):
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="buy",
            order_type="market",
            qty=1,
            internal_status="DRY_RUN_SIMULATED",
        )
    )
    db_session.commit()

    payload = _send(_service(), db_session, "오늘 주문 기록 보여줘")

    assert payload["intent"]["category"] == "read_only_orders_query"
    assert payload["data"]["count"] == 1
    assert payload["data"]["orders"][0]["symbol"] == "005930"
    assert payload["plan"] is None
    assert payload["safety"]["real_order_submitted"] is False


def test_analysis_request_creates_safe_plan_and_run(db_session):
    payload = _send(_service(), db_session, "삼성전자 살만한지 분석해줘")

    assert payload["intent"]["category"] == "analysis_request"
    assert payload["plan"]["command_type"] == "RUN_SINGLE_SYMBOL_ANALYSIS"
    assert payload["run"]["status"] == "executed_safe_action"
    assert payload["safety"]["safe_execution_only"] is True
    assert payload["safety"]["real_order_submitted"] is False
    assert payload["safety"]["validation_called"] is False


def test_manual_ticket_request_creates_prefill_only_plan_without_submit(db_session):
    payload = _send(_service(), db_session, "삼성전자 3만원 매수 티켓 준비해줘")

    assert payload["intent"]["category"] == "manual_ticket_request"
    assert payload["plan"]["command_type"] == "PREPARE_MANUAL_BUY_TICKET"
    assert payload["plan"]["risk_level"] == "prefill_only"
    assert "prepare_manual_ticket" in payload["available_actions"]
    assert payload["safety"]["confirm_live_auto_checked"] is False
    assert payload["safety"]["manual_submit_called"] is False


def test_live_order_request_is_blocked_and_only_manual_plan_is_returned(db_session):
    payload = _send(_service(), db_session, "삼성전자 지금 3만원 사줘")

    assert payload["intent"]["category"] == "live_order_request"
    assert payload["answer"]["answer_type"] == "blocked"
    assert "실주문" in payload["answer"]["text"]
    assert payload["plan"]["command_type"] == "PREPARE_MANUAL_BUY_TICKET"
    assert payload["safety"]["real_order_submitted"] is False
    assert payload["safety"]["broker_submit_called"] is False
    assert payload["safety"]["validation_called"] is False


def test_dangerous_setting_request_does_not_create_plan_or_change_settings(db_session):
    payload = _send(_service(), db_session, "dry run 꺼")

    assert payload["intent"]["category"] == "dangerous_setting_request"
    assert payload["answer"]["answer_type"] == "auth_required"
    assert payload["plan"] is None
    assert payload["safety"]["setting_changed"] is False
    assert payload["safety"]["scheduler_changed"] is False


def test_unsupported_request_is_safely_refused(db_session):
    payload = _send(_service(), db_session, "비트코인 선물 100배 롱 쳐줘")

    assert payload["intent"]["category"] == "unsupported"
    assert payload["answer"]["answer_type"] == "unsupported"
    assert payload["plan"] is None
    assert payload["safety"]["real_order_submitted"] is False


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
                "qty": 1,
                "market_value": 72000,
                "unrealized_pl": 1000,
            }
        ]

    def get_account_balance(self):
        return {
            "provider": "kis",
            "currency": "KRW",
            "cash": 100000,
            "total_asset_value": 172000,
        }


class _FakeAlpacaClient:
    def get_latest_price(self, symbol: str):
        return {"symbol": symbol, "price": 190.25, "timestamp": "2026-06-18T00:00:00Z"}

    def list_positions(self):
        return []

    def get_account(self):
        return SimpleNamespace(cash="1000", portfolio_value="2000")
