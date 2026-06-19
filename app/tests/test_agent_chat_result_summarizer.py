from app.schemas.agent_chat_orchestrator import (
    AgentChatAnswer,
    AgentChatIntent,
    AgentChatIntentCategory,
)
from app.schemas.agent_chat_tool import AgentChatToolResult
from app.services.agent_chat_answer_service import AgentChatAnswerService
from app.services.agent_chat_result_summarizer import AgentChatResultSummarizer


def test_result_summarizer_builds_polished_price_answer_card_and_suggestions():
    summarizer = AgentChatResultSummarizer()
    intent = AgentChatIntent(
        category=AgentChatIntentCategory.READ_ONLY_PRICE_QUERY,
        market="KR",
        provider="kis",
        symbol="005930",
        symbol_name="삼성전자",
    )
    result = AgentChatToolResult(
        tool_name="kis_price_lookup",
        status="success",
        result_type="price",
        data={
            "price": {
                "symbol": "005930",
                "name": "삼성전자",
                "price": 72000,
                "currency": "KRW",
                "provider": "kis",
                "market": "KR",
                "timestamp": "2026-06-18T09:00:00+09:00",
            }
        },
        summary="ok",
    )

    payload = summarizer.summarize(
        intent=intent,
        tool_results=[result],
        fallback_answer=AgentChatAnswer(text="fallback"),
    )

    answer_text = payload["answer"].text
    assert payload["answer"].answer_type == "read_only_result"
    assert "삼성전자(005930)" in answer_text
    assert "read-only" in answer_text
    assert "주문" in answer_text
    assert "validation" in answer_text
    assert "confirm_live" in answer_text

    card = payload["result_cards"][0]
    assert card.card_type == "price"
    assert card.title == "삼성전자 현재가"
    assert card.subtitle == "005930 · KIS"
    assert card.primary_value == "₩72,000"
    assert "READ ONLY" in card.badges
    assert "NO ORDER" in card.badges
    assert "NO VALIDATION" in card.badges
    assert {"label": "lookup", "value": "read-only lookup"} in card.rows
    assert payload["follow_up_suggestions"] == [
        "이 종목 분석해줘",
        "보유 여부 확인해줘",
        "최근 주문 기록 보여줘",
    ]


def test_result_summarizer_positions_answer_confirms_lookup_only():
    summarizer = AgentChatResultSummarizer()
    intent = AgentChatIntent(category=AgentChatIntentCategory.READ_ONLY_POSITIONS_QUERY)
    result = AgentChatToolResult(
        tool_name="kis_positions_lookup",
        status="success",
        result_type="positions",
        data={
            "provider": "kis",
            "market": "KR",
            "count": 1,
            "positions": [
                {
                    "symbol": "005930",
                    "name": "삼성전자",
                    "qty": 1,
                    "market_value": 72000,
                    "unrealized_pl": 1500,
                }
            ],
        },
        summary="ok",
    )

    payload = summarizer.summarize(
        intent=intent,
        tool_results=[result],
        fallback_answer=AgentChatAnswer(text="fallback"),
    )

    assert "현재 KIS 보유종목은 1개입니다" in payload["answer"].text
    assert "삼성전자 1주" in payload["answer"].text
    assert "매도나 주문 검증은 실행하지 않았습니다" in payload["answer"].text
    card = payload["result_cards"][0]
    assert card.title == "보유종목"
    assert card.primary_value == "1개 종목"
    assert card.subtitle == "KIS"
    assert card.rows[0]["label"] == "삼성전자"
    assert "qty 1" in card.rows[0]["value"]


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
                "kis_scheduler_enabled": False,
            }
        },
        summary="ok",
    )

    payload = summarizer.summarize(
        intent=intent,
        tool_results=[result],
        fallback_answer=AgentChatAnswer(text="fallback"),
    )

    assert "dry-run은 ON" in payload["answer"].text
    assert "설정을 변경하지 않았습니다" in payload["answer"].text
    assert payload["result_cards"][0].card_type == "settings"
    assert "NO SETTINGS CHANGE" in payload["result_cards"][0].badges


def test_answer_service_live_order_block_copy_stays_manual_review_only():
    answer = AgentChatAnswerService().compose(
        intent=AgentChatIntent(
            category=AgentChatIntentCategory.LIVE_ORDER_REQUEST,
            market="KR",
            provider="kis",
            symbol="005930",
            symbol_name="삼성전자",
            side="buy",
        ),
        data={"direct_order_blocked": True},
        plan=None,
        run=None,
        available_actions=[],
    )

    assert answer.answer_type == "blocked"
    assert "채팅에서는 실주문" in answer.text
    assert "수동 주문 티켓" in answer.text
    assert "Validate" in answer.text
    assert "confirm_live" in answer.text
