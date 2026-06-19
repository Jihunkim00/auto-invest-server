from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.schemas.agent_chat_orchestrator import AgentChatSendRequest
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "agent_chat_eval_cases.json"
MIN_CASES = 60
REQUIRED_GROUPS = {
    "price",
    "positions_balance",
    "logs_settings",
    "system_explanation",
    "analysis",
    "manual_ticket",
    "live_order_blocked",
    "dangerous_settings",
    "unsupported",
}
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
MOJIBAKE_MARKERS = ("ì", "ë", "ê")


def _cases() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


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


def test_eval_fixture_has_required_shape_and_coverage():
    cases = _cases()
    assert len(cases) >= MIN_CASES
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))

    groups = Counter(case["group"] for case in cases)
    assert REQUIRED_GROUPS.issubset(groups)

    raw_text = FIXTURE_PATH.read_text(encoding="utf-8")
    assert not any(marker in raw_text for marker in MOJIBAKE_MARKERS)
    assert any("삼성전자" in case["message"] for case in cases)
    assert any("현재가" in case["message"] for case in cases)

    for case in cases:
        expected = case["expected"]
        assert expected["category"]
        assert "answer_type" in expected
        assert "read_only" in expected


@pytest.mark.parametrize("case", _cases(), ids=lambda item: item["id"])
def test_agent_chat_eval_case_routes_and_answers_safely(db_session, case):
    payload = _service().send(
        db_session,
        request=AgentChatSendRequest(
            conversation_key=None,
            message=case["message"],
            context=case.get("context") or {},
            auto_create_conversation=True,
        ),
    )
    expected = case["expected"]

    assert payload["intent"]["category"] == expected["category"]
    if expected.get("symbol"):
        assert payload["intent"]["symbol"] == expected["symbol"]
    if expected.get("provider"):
        assert payload["intent"]["provider"] == expected["provider"]

    selected_tools = [tool["tool_name"] for tool in payload["selected_tools"]]
    if expected.get("selected_tool"):
        assert expected["selected_tool"] in selected_tools
    else:
        assert selected_tools == []

    assert payload["answer"]["answer_type"] == expected["answer_type"]
    if expected.get("result_card_type"):
        assert expected["result_card_type"] in [card["card_type"] for card in payload["result_cards"]]

    assert payload["safety"]["read_only"] is expected["read_only"]
    for flag in FORBIDDEN_SAFETY_FLAGS:
        assert payload["safety"][flag] is False

    response_text = json.dumps(payload, ensure_ascii=False)
    assert not any(marker in response_text for marker in MOJIBAKE_MARKERS)


class _FakeKisClient:
    def get_domestic_stock_price(self, symbol: str):
        return {
            "provider": "kis",
            "symbol": symbol,
            "name": "삼성전자" if symbol == "005930" else symbol,
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
        return {
            "provider": "kis",
            "market": "KR",
            "currency": "KRW",
            "cash": 500000,
            "total_asset_value": 716000,
            "unrealized_pl": 12000,
        }


class _FakeAlpacaClient:
    def get_latest_price(self, symbol: str):
        prices = {"AAPL": 190.25, "NVDA": 125.5, "MSFT": 430.0}
        return {"symbol": symbol, "price": prices.get(symbol, 100.0), "timestamp": "2026-06-18T00:00:00Z"}

    def list_positions(self):
        return [
            SimpleNamespace(symbol="AAPL", qty="2", market_value="380.5", unrealized_pl="20.0", current_price="190.25")
        ]

    def get_account(self):
        return SimpleNamespace(cash="1000", portfolio_value="2000")
