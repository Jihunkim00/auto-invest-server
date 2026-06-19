from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.brokers.alpaca_client import AlpacaClient
from app.brokers.kis_client import KisClient
from app.schemas.agent_chat_orchestrator import AgentChatSendRequest
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService
from app.services.agent_schedule_service import AgentScheduleService
from app.services.kis_manual_order_service import KisManualOrderService
from app.services.kis_order_validation_service import KisOrderValidationService
from app.services.kis_single_symbol_trading_service import KisSingleSymbolTradingService
from app.services.runtime_setting_service import RuntimeSettingService


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


def _send(db_session, message: str, context: dict | None = None):
    return _service().send(
        db_session,
        request=AgentChatSendRequest(
            conversation_key=None,
            message=message,
            context=context or {"default_market": "KR", "default_provider": "kis"},
            auto_create_conversation=True,
        ),
    )


def test_blocked_and_prefill_chat_requests_do_not_call_forbidden_paths(monkeypatch, db_session):
    calls = _install_forbidden_path_spies(monkeypatch)
    cases = [
        ("삼성전자 지금 사줘", "live_order_request"),
        ("삼성전자 3만원 매수 티켓 준비해줘", "manual_ticket_request"),
        ("dry run 꺼줘", "dangerous_setting_request"),
        ("scheduler 실주문 켜줘", "scheduler_request"),
        (
            "첫 번째 종목 팔아야 해?",
            "exit_review_request",
            {"first_position_symbol": "005930", "first_position_name": "삼성전자", "last_market": "KR", "last_provider": "kis"},
        ),
    ]

    for item in cases:
        message, expected_category, *context = item
        payload = _send(db_session, message, context[0] if context else None)
        assert payload["intent"]["category"] == expected_category
        for flag in FORBIDDEN_SAFETY_FLAGS:
            assert payload["safety"][flag] is False

    assert calls == []


def _install_forbidden_path_spies(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def spy(label: str):
        def _called(*args, **kwargs):
            calls.append(label)
            raise AssertionError(f"Forbidden Agent Chat path called: {label}")

        return _called

    targets = (
        (KisClient, ("submit", "order")),
        (KisClient, ("submit", "domestic", "cash", "order")),
        (AlpacaClient, ("submit", "order")),
        (KisManualOrderService, ("submit", "manual")),
        (KisOrderValidationService, ("validate",)),
        (KisSingleSymbolTradingService, ("_validate", "order")),
        (KisSingleSymbolTradingService, ("_submit", "manual")),
        (RuntimeSettingService, ("update", "settings")),
        (RuntimeSettingService, ("set", "bot", "enabled")),
        (RuntimeSettingService, ("set", "kill", "switch")),
        (RuntimeSettingService, ("set", "scheduler", "enabled")),
        (AgentScheduleService, ("create", "schedule")),
    )
    for cls, parts in targets:
        name = "_".join(parts)
        monkeypatch.setattr(cls, name, spy(f"{cls.__name__}.{name}"), raising=False)
    return calls


class _FakeKisClient:
    def get_domestic_stock_price(self, symbol: str):
        return {
            "provider": "kis",
            "symbol": symbol,
            "name": "삼성전자",
            "current_price": 72000,
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
