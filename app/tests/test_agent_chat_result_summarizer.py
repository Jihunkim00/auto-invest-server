from app.schemas.agent_chat_orchestrator import (
    AgentChatAnswer,
    AgentChatIntent,
    AgentChatIntentCategory,
)
from app.schemas.agent_chat_tool import AgentChatToolResult
from app.services.agent_chat_result_summarizer import AgentChatResultSummarizer


def test_result_summarizer_builds_price_answer_card_and_suggestions():
    summarizer = AgentChatResultSummarizer()
    intent = AgentChatIntent(
        category=AgentChatIntentCategory.READ_ONLY_PRICE_QUERY,
        market="KR",
        provider="kis",
        symbol="005930",
        symbol_name="Samsung Electronics",
    )
    result = AgentChatToolResult(
        tool_name="kis_price_lookup",
        status="success",
        result_type="price",
        data={
            "price": {
                "symbol": "005930",
                "name": "Samsung Electronics",
                "price": 72000,
                "currency": "KRW",
                "provider": "kis",
                "market": "KR",
            }
        },
        summary="ok",
    )

    payload = summarizer.summarize(
        intent=intent,
        tool_results=[result],
        fallback_answer=AgentChatAnswer(text="fallback"),
    )

    assert payload["answer"].answer_type == "read_only_result"
    assert "현재가" in payload["answer"].text
    assert payload["result_cards"][0].card_type == "price"
    assert payload["result_cards"][0].primary_value == "₩72,000"
    assert "READ ONLY" in payload["result_cards"][0].badges
    assert payload["follow_up_suggestions"]


def test_result_summarizer_settings_answer_confirms_no_change():
    summarizer = AgentChatResultSummarizer()
    intent = AgentChatIntent(category=AgentChatIntentCategory.READ_ONLY_SETTINGS_QUERY)
    result = AgentChatToolResult(
        tool_name="ops_settings_lookup",
        status="success",
        result_type="settings",
        data={
            "settings": {
                "dry_run": True,
                "kill_switch": False,
                "scheduler_enabled": False,
                "kis_real_order_enabled": False,
            }
        },
        summary="ok",
    )

    payload = summarizer.summarize(
        intent=intent,
        tool_results=[result],
        fallback_answer=AgentChatAnswer(text="fallback"),
    )

    assert "dry-run" in payload["answer"].text
    assert "변경하지 않았습니다" in payload["answer"].text
    assert payload["result_cards"][0].card_type == "settings"
    assert "NO CHANGE" in payload["result_cards"][0].badges
