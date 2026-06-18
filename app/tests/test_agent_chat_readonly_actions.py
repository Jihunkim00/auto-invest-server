from __future__ import annotations

from types import SimpleNamespace

from app.db.models import OrderLog, SignalLog, TradeRunLog
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
        kis_client_factory=lambda db: _NoOrderKisClient(),
        alpaca_client_factory=lambda: _NoOrderAlpacaClient(),
    )


def _send(db_session, message: str):
    return _service().send(
        db_session,
        request=AgentChatSendRequest(
            message=message,
            context={"default_market": "KR", "default_provider": "kis"},
        ),
    )


def test_read_only_balance_query_does_not_call_forbidden_actions(db_session):
    payload = _send(db_session, "잔고 보여줘")

    assert payload["intent"]["category"] == "read_only_balance_query"
    assert payload["answer"]["answer_type"] == "read_only_result"
    assert payload["data"]["balance"]["cash"] == 100000
    assert payload["safety"]["read_only"] is True
    assert payload["safety"]["real_order_submitted"] is False
    assert payload["safety"]["broker_submit_called"] is False
    assert payload["safety"]["manual_submit_called"] is False
    assert payload["safety"]["validation_called"] is False
    assert payload["safety"]["setting_changed"] is False
    assert payload["safety"]["scheduler_changed"] is False


def test_recent_runs_and_signals_are_local_read_only(db_session):
    db_session.add(
        TradeRunLog(
            run_key="run_1",
            trigger_source="manual",
            symbol="005930",
            mode="entry_scan",
            stage="completed",
            result="skipped",
            reason="test",
        )
    )
    db_session.add(
        SignalLog(
            symbol="005930",
            action="hold",
            buy_score=60,
            sell_score=40,
            confidence=0.6,
            reason="test signal",
            signal_status="simulated",
            trigger_source="kis_buy_shadow",
        )
    )
    db_session.commit()

    runs = _send(db_session, "최근 실행 로그 보여줘")
    signals = _send(db_session, "최근 신호 보여줘")

    assert runs["intent"]["category"] == "read_only_runs_query"
    assert runs["data"]["count"] == 1
    assert runs["data"]["runs"][0]["result"] == "skipped"
    assert runs["safety"]["real_order_submitted"] is False
    assert signals["intent"]["category"] == "read_only_signals_query"
    assert signals["data"]["count"] == 1
    assert signals["data"]["signals"][0]["action"] == "hold"
    assert signals["safety"]["broker_submit_called"] is False


def test_forbidden_service_methods_raise_if_accidentally_called(db_session):
    payload = _send(db_session, "삼성전자 지금 가격 얼마야?")

    assert payload["intent"]["category"] == "read_only_price_query"
    assert payload["safety"]["real_order_submitted"] is False
    assert payload["safety"]["validation_called"] is False


class _NoOrderKisClient:
    def get_domestic_stock_price(self, symbol: str):
        return {"symbol": symbol, "name": "삼성전자", "current_price": 72000}

    def list_positions(self):
        return []

    def get_account_balance(self):
        return {"provider": "kis", "currency": "KRW", "cash": 100000}


class _NoOrderAlpacaClient:
    def get_latest_price(self, symbol: str):
        return {"symbol": symbol, "price": 190.25}

    def list_positions(self):
        return []

    def get_account(self):
        return SimpleNamespace(cash="1000", portfolio_value="2000")
