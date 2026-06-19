from __future__ import annotations

from types import SimpleNamespace

from app.schemas.agent_chat_orchestrator import AgentChatIntent, AgentChatIntentCategory
from app.schemas.agent_chat_tool import AgentChatToolCall
from app.services.agent_chat_tool_executor import AgentChatToolExecutor


def test_executor_runs_read_only_kis_price_lookup(db_session):
    executor = AgentChatToolExecutor(
        kis_client_factory=lambda db: _FakeKisClient(),
        alpaca_client_factory=lambda: _FakeAlpacaClient(),
    )
    intent = AgentChatIntent(
        category=AgentChatIntentCategory.READ_ONLY_PRICE_QUERY,
        market="KR",
        provider="kis",
        symbol="005930",
    )

    result = executor.execute(
        db_session,
        call=AgentChatToolCall(
            tool_name="kis_price_lookup",
            arguments={"symbol": "005930"},
        ),
        intent=intent,
    )

    assert result.status == "success"
    assert result.result_type == "price"
    assert result.data["price"]["price"] == 72000
    assert result.safety.read_only is True
    assert result.safety.real_order_submitted is False
    assert result.safety.broker_submit_called is False
    assert result.safety.manual_submit_called is False
    assert result.safety.validation_called is False


def test_executor_blocks_live_settings_and_unknown_tools(db_session):
    executor = AgentChatToolExecutor(
        kis_client_factory=lambda db: _FakeKisClient(),
        alpaca_client_factory=lambda: _FakeAlpacaClient(),
    )
    intent = AgentChatIntent(category=AgentChatIntentCategory.LIVE_ORDER_REQUEST)

    live = executor.execute(
        db_session,
        call=AgentChatToolCall(tool_name="live_order_request_blocker"),
        intent=intent,
    )
    settings = executor.execute(
        db_session,
        call=AgentChatToolCall(tool_name="settings_change_blocker"),
        intent=intent,
    )
    unknown = executor.execute(
        db_session,
        call=AgentChatToolCall(tool_name="unknown_tool_now"),
        intent=intent,
    )

    assert live.status == "blocked"
    assert settings.status == "blocked"
    assert unknown.status == "unsupported"
    for result in (live, settings, unknown):
        assert result.safety.real_order_submitted is False
        assert result.safety.validation_called is False
        assert result.safety.setting_changed is False


def test_executor_ops_settings_lookup_is_read_only(db_session):
    executor = AgentChatToolExecutor(
        kis_client_factory=lambda db: _FakeKisClient(),
        alpaca_client_factory=lambda: _FakeAlpacaClient(),
    )
    intent = AgentChatIntent(category=AgentChatIntentCategory.READ_ONLY_SETTINGS_QUERY)

    result = executor.execute(
        db_session,
        call=AgentChatToolCall(tool_name="ops_settings_lookup"),
        intent=intent,
    )

    assert result.status == "success"
    assert result.result_type == "settings"
    assert "dry_run" in result.data["settings"]
    assert result.safety.setting_changed is False


class _FakeKisClient:
    def get_domestic_stock_price(self, symbol: str):
        return {
            "symbol": symbol,
            "name": "Samsung Electronics",
            "current_price": 72000,
        }

    def list_positions(self):
        return [{"symbol": "005930", "qty": 1}]

    def get_account_balance(self):
        return {"currency": "KRW", "cash": 100000}


class _FakeAlpacaClient:
    def get_latest_price(self, symbol: str):
        return {"symbol": symbol, "price": 190.25}

    def list_positions(self):
        return []

    def get_account(self):
        return SimpleNamespace(cash="1000", portfolio_value="2000")
