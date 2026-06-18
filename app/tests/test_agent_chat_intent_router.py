from __future__ import annotations

from types import SimpleNamespace

from app.schemas.agent_chat_orchestrator import AgentChatIntentCategory
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService


def _settings(openai_api_key=None):
    return SimpleNamespace(
        openai_api_key=openai_api_key,
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


def _service(openai_client=None):
    return AgentChatIntentRouterService(
        openai_client=openai_client,
        settings=_settings(openai_api_key="test-key" if openai_client else None),
    )


def test_korean_price_query_routes_to_kis_symbol():
    intent = _service().route(message="삼성전자 지금 가격 얼마야?", context=_context())

    assert intent.category == AgentChatIntentCategory.READ_ONLY_PRICE_QUERY
    assert intent.symbol == "005930"
    assert intent.symbol_name == "삼성전자"
    assert intent.market == "KR"
    assert intent.provider == "kis"
    assert intent.fallback_used is True


def test_korean_alias_and_us_price_queries_are_detected():
    service = _service()

    samsung = service.route(message="삼전 현재가", context=_context())
    apple = service.route(message="AAPL price", context={})

    assert samsung.category == AgentChatIntentCategory.READ_ONLY_PRICE_QUERY
    assert samsung.symbol == "005930"
    assert apple.category == AgentChatIntentCategory.READ_ONLY_PRICE_QUERY
    assert apple.symbol == "AAPL"
    assert apple.market == "US"
    assert apple.provider == "alpaca"


def test_positions_orders_analysis_and_live_order_patterns():
    service = _service()

    assert service.route(message="내 보유종목 보여줘", context=_context()).category == (
        AgentChatIntentCategory.READ_ONLY_POSITIONS_QUERY
    )
    assert service.route(message="오늘 주문 기록 보여줘", context=_context()).category == (
        AgentChatIntentCategory.READ_ONLY_ORDERS_QUERY
    )
    analysis = service.route(message="삼성전자 살만한지 분석해줘", context=_context())
    assert analysis.category == AgentChatIntentCategory.ANALYSIS_REQUEST
    assert analysis.symbol == "005930"
    live = service.route(message="삼성전자 지금 3만원 사줘", context=_context())
    assert live.category == AgentChatIntentCategory.LIVE_ORDER_REQUEST
    assert live.notional == 30000
    assert live.side == "buy"


def test_dangerous_and_unsupported_patterns():
    service = _service()

    dangerous = service.route(message="dry run 꺼", context=_context())
    unsupported = service.route(message="비트코인 선물 100배 롱 쳐줘", context=_context())

    assert dangerous.category == AgentChatIntentCategory.DANGEROUS_SETTING_REQUEST
    assert dangerous.requires_auth is True
    assert unsupported.category == AgentChatIntentCategory.UNSUPPORTED
    assert unsupported.supported is False


class _BadResponses:
    def create(self, **kwargs):
        return SimpleNamespace(output_text="not json")


class _BadClient:
    responses = _BadResponses()


def test_gpt_invalid_response_uses_fallback_router():
    intent = _service(openai_client=_BadClient()).route(
        message="삼전 현재가",
        context=_context(),
    )

    assert intent.category == AgentChatIntentCategory.READ_ONLY_PRICE_QUERY
    assert intent.symbol == "005930"
    assert intent.fallback_used is True
    assert intent.parser_status == "failed_fallback_used"
