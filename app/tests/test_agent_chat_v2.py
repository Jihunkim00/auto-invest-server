from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.routes.agent_chat import get_agent_chat_v2_service
from app.schemas.agent_chat_v2 import AgentChatV2MessageRequest
from app.schemas.agent_chat_orchestrator import AgentChatIntent, AgentChatIntentCategory
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_v2_service import AgentChatV2Service


def _legacy(*, category: str, data: dict, symbol: str | None = "005930") -> dict:
    return {
        "conversation_key": "conv_v2",
        "user_message_id": 1,
        "assistant_message_id": 2,
        "intent": {
            "category": category,
            "supported": True,
            "market": "KR",
            "provider": "kis",
            "symbol": symbol,
            "symbol_name": "삼성전자" if symbol else None,
            "parser_status": "fallback",
        },
        "answer": {"text": "legacy", "answer_type": "read_only_result"},
        "data": data,
        "available_actions": [],
        "result_cards": [],
        "follow_up_suggestions": [],
        "context_snapshot": {"last_symbol": symbol},
        "safety": {
            "read_only": True,
            "safe_execution_only": True,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "validation_called": False,
            "setting_changed": False,
            "scheduler_changed": False,
        },
    }


class _FakeOrchestrator:
    def __init__(self, payload: dict):
        self.payload = payload

    def send(self, db, *, request):
        return self.payload


class _FakePreviewService:
    def __init__(self):
        self.preview_only = None

    def prepare(self, db, *, intent, conversation_key, user_message_id, preview_only=False):
        self.preview_only = preview_only
        return {
            "created": True,
            "action": {
                "action_id": 7,
                "status": "pending_confirmation",
                "provider": "kis",
                "market": "KR",
                "symbol": "005930",
                "symbol_name": "삼성전자",
                "side": "buy",
                "order_type": "market",
                "quantity": 3,
                "estimated_price": 60000,
                "estimated_notional": 180000,
                "currency": "KRW",
            },
        }

    def update_assistant_message_id(self, *args, **kwargs):
        return None

    def readiness(self, db):
        return {
            "ready_for_chat_confirmed_live_order": False,
            "blocking_reasons": ["agent_chat_live_order_disabled"],
        }


class _FakeResponses:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text)


class _FakeClient:
    def __init__(self, output_text: str):
        self.responses = _FakeResponses(output_text)


class _FakeRouter:
    def __init__(self, category: AgentChatIntentCategory, output_text: str):
        self.category = category
        self.client = _FakeClient(output_text)
        self.model_name = "test-composer"
        self.reasoning_effort = "low"

    def _intent(self):
        return AgentChatIntent(
            category=self.category,
            market="KR",
            provider="kis",
            symbol="005930",
            symbol_name="삼성전자",
            fallback_used=False,
        )

    def route(self, *, message, context):
        return self._intent()

    def fallback_route(self, message, context):
        return self._intent()


def test_v2_router_resolves_utf8_symbols_and_ambiguous_prefix():
    router = AgentChatIntentRouterService()
    samsung = router.fallback_route("삼성전자 분석해줘", {})
    hyundai = router.fallback_route("현대차 분석해줘", {})
    ambiguous = router.fallback_route("삼성 분석해줘", {})

    assert samsung.symbol == "005930"
    assert hyundai.symbol == "005380"
    assert ambiguous.symbol is None
    assert ambiguous.supported is False


def test_v2_quote_returns_trusted_korean_current_price_without_hold(db_session):
    router = AgentChatIntentRouterService(
        settings=SimpleNamespace(
            openai_api_key=None,
            agent_chat_model="test-agent-router",
            agent_chat_reasoning_effort="low",
            agent_chat_temperature=None,
            agent_chat_timeout_seconds=1.0,
            agent_chat_fallback_enabled=True,
        )
    )
    service = AgentChatV2Service(
        intent_router=router,
        orchestrator=_FakeOrchestrator(
            _legacy(
                category="read_only_price_query",
                data={
                    "price": {
                        "symbol": "005930",
                        "name": "삼성전자",
                        "current_price": 72000,
                        "currency": "KRW",
                        "provider": "kis",
                    }
                },
            )
        ),
    )
    response = service.send(
        db_session,
        request=AgentChatV2MessageRequest(message="삼성전자 주식 1주 가격 얼마야?"),
    )

    assert response["intent"] == "quote"
    assert "72,000원" in response["answer"]
    assert "HOLD" not in response["answer"]
    assert response["data"]["price"]["current_price"] == 72000
    assert response["safety"]["broker_submit_called"] is False
    assert response["gpt_used"] is False


def test_v2_quote_failure_never_invents_a_price(db_session):
    router = AgentChatIntentRouterService(
        settings=SimpleNamespace(
            openai_api_key=None,
            agent_chat_model="test-agent-router",
            agent_chat_reasoning_effort="low",
            agent_chat_temperature=None,
            agent_chat_timeout_seconds=1.0,
            agent_chat_fallback_enabled=True,
        )
    )
    response = AgentChatV2Service(
        intent_router=router,
        orchestrator=_FakeOrchestrator(
            _legacy(
                category="read_only_price_query",
                data={"price": {"symbol": "005930", "name": "삼성전자"}, "error": "retryable"},
            )
        ),
    ).send(
        db_session,
        request=AgentChatV2MessageRequest(message="005930 현재가 알려줘"),
    )

    assert response["intent"] == "quote"
    assert "조회하지 못했습니다" in response["answer"]
    assert "원" not in response["answer"]


def test_v2_affordability_is_read_only_and_uses_whole_share_math(db_session):
    router = AgentChatIntentRouterService(
        settings=SimpleNamespace(
            openai_api_key=None,
            agent_chat_model="test-agent-router",
            agent_chat_reasoning_effort="low",
            agent_chat_temperature=None,
            agent_chat_timeout_seconds=1.0,
            agent_chat_fallback_enabled=True,
        )
    )
    legacy = _legacy(
        category="affordability_query",
        data={
            "price": {"symbol": "005930", "name": "삼성전자", "current_price": 72000, "currency": "KRW"},
            "balance": {"available_cash": 150000, "currency": "KRW"},
        },
    )
    legacy["intent"]["quantity"] = 2
    response = AgentChatV2Service(
        intent_router=router,
        orchestrator=_FakeOrchestrator(legacy),
    ).send(
        db_session,
        request=AgentChatV2MessageRequest(message="삼성전자 2주 살 수 있어?"),
    )

    assert response["intent"] == "affordability"
    assert "144,000원" in response["answer"]
    assert "매수 가능한 범위" in response["answer"]
    assert response["safety"]["real_order_submitted"] is False


def test_v2_indicator_explanation_is_general_and_does_not_lookup_broker(db_session):
    router = AgentChatIntentRouterService(
        settings=SimpleNamespace(
            openai_api_key=None,
            agent_chat_model="test-agent-router",
            agent_chat_reasoning_effort="low",
            agent_chat_temperature=None,
            agent_chat_timeout_seconds=1.0,
            agent_chat_fallback_enabled=True,
        )
    )
    response = AgentChatV2Service(
        intent_router=router,
        orchestrator=_FakeOrchestrator(_legacy(category="general_chat", data={})),
    ).send(
        db_session,
        request=AgentChatV2MessageRequest(message="RSI가 뭐야?"),
    )

    assert response["intent"] == "explain_indicator"
    assert "RSI" in response["answer"]
    assert response["diagnostics"]["tool_names"] == []


def test_v2_gpt_composer_receives_public_projection_only(db_session):
    router = _FakeRouter(
        AgentChatIntentCategory.ANALYSIS_REQUEST,
        "삼성전자 공개 시장 데이터 기준으로는 현재 판단 근거를 설명할 수 있습니다.",
    )
    legacy = _legacy(
        category="analysis_request",
        data={
            "analysis": {
                "symbol": "005930",
                "action": "HOLD",
                "current_price": 255500,
                "final_score": 61,
                "market_model": "gpt-5.6-luna",
                "market_reasoning_effort": "xhigh",
                "market_gpt_used": True,
                "market_gpt_fallback_used": False,
                "risk_flags": ["score_gate"],
            },
            "balance": {"cash": 100000, "account_number": "12345678"},
            "positions": [{"symbol": "005930", "qty": 2, "average_cost": 65000}],
            "appsecret": "hidden",
        },
    )
    service = AgentChatV2Service(
        intent_router=router,
        orchestrator=_FakeOrchestrator(legacy),
    )

    response = service.send(
        db_session,
        request=AgentChatV2MessageRequest(message="삼성전자 분석해줘"),
    )

    call_input = router.client.responses.calls[0]["input"]
    assert response["intent"] == "analyze"
    assert response["gpt_used"] is True
    assert response["diagnostics"]["gpt_called"] is True
    assert response["diagnostics"]["parser_status"] == "fallback"
    assert response["diagnostics"]["intent_parser_status"] == "deterministic_fallback"
    assert response["diagnostics"]["intent_parser_fallback_used"] is True
    assert response["diagnostics"]["chat_gpt_fallback_used"] is False
    assert response["diagnostics"]["market_gpt_fallback_used"] is False
    assert response["diagnostics"]["market_model"] == "gpt-5.6-luna"
    assert "공개 시장 데이터" in response["answer"]
    assert "cash" not in call_input
    assert "positions" not in call_input
    assert "account_number" not in call_input
    assert "appsecret" not in call_input
    assert "12345678" not in call_input
    assert "65000" not in call_input


def test_v2_account_query_never_calls_gpt_even_when_client_exists(db_session):
    router = _FakeRouter(
        AgentChatIntentCategory.READ_ONLY_BALANCE_QUERY,
        "이 응답은 호출되면 안 됩니다.",
    )
    service = AgentChatV2Service(
        intent_router=router,
        orchestrator=_FakeOrchestrator(
            _legacy(
                category="read_only_balance_query",
                data={"balance": {"cash": 100000, "orderable_cash": 90000}},
                symbol=None,
            )
        ),
    )

    response = service.send(
        db_session,
        request=AgentChatV2MessageRequest(message="내 잔고 보여줘"),
    )

    assert response["intent"] == "account"
    assert response["gpt_used"] is False
    assert response["diagnostics"]["gpt_called"] is False
    assert router.client.responses.calls == []


def test_v2_analyze_returns_structured_scores_without_submit(db_session):
    service = AgentChatV2Service(
        orchestrator=_FakeOrchestrator(
            _legacy(
                category="analysis_request",
                data={
                    "analysis": {
                        "symbol": "005930",
                        "action": "HOLD",
                        "current_price": 255500,
                        "final_score": 61,
                        "required_score": 65,
                        "confidence": 0.67,
                        "risk_flags": ["final_score_gate_not_met"],
                    }
                },
            )
        )
    )
    response = service.send(
        db_session,
        request=AgentChatV2MessageRequest(message="삼성전자 분석해줘"),
    )

    assert response["intent"] == "analyze"
    assert response["status"] == "completed"
    assert response["action"] == "HOLD"
    assert response["scores"]["final_score"] == 61
    assert response["analysis"]["current_price"] == 255500
    assert response["data"]["analysis"]["current_price"] == 255500
    assert response["requires_confirmation"] is False
    assert response["safety"]["real_order_submitted"] is False


def test_v2_explain_and_portfolio_are_read_only(db_session):
    explain = AgentChatV2Service(
        orchestrator=_FakeOrchestrator(
            _legacy(
                category="read_only_runs_query",
                data={"runs": [{"symbol": "005930", "action": "HOLD"}], "count": 1},
            )
        )
    ).send(
        db_session,
        request=AgentChatV2MessageRequest(message="오늘 왜 HOLD였어?"),
    )
    portfolio = AgentChatV2Service(
        orchestrator=_FakeOrchestrator(
            _legacy(
                category="read_only_positions_query",
                data={
                    "count": 1,
                    "positions": [{"symbol": "005930", "qty": 3, "unrealized_pl": 1200}],
                },
            )
        )
    ).send(
        db_session,
        request=AgentChatV2MessageRequest(message="내 포트폴리오 보여줘"),
    )

    assert explain["intent"] == "explain"
    assert "HOLD" in explain["message"]
    assert portfolio["intent"] == "portfolio"
    assert portfolio["portfolio"]["count"] == 1
    assert portfolio["safety"]["broker_submit_called"] is False


def test_v2_trade_prepare_creates_preview_only_and_never_submits(db_session):
    preview_service = _FakePreviewService()
    service = AgentChatV2Service(
        orchestrator=_FakeOrchestrator(
            _legacy(category="live_order_request", data={}, symbol="005930")
        ),
        live_order_service=preview_service,
    )
    response = service.send(
        db_session,
        request=AgentChatV2MessageRequest(message="삼성전자 3주 사고 싶어"),
    )

    assert response["intent"] == "trade_prepare"
    assert response["status"] == "confirmation_required"
    assert response["requires_confirmation"] is True
    assert response["order_preview"]["quantity"] == 3
    assert preview_service.preview_only is True
    assert response["safety"]["real_order_submitted"] is False
    assert response["safety"]["broker_submit_called"] is False


def test_v2_dangerous_setting_request_is_blocked_without_mutation(db_session):
    response = AgentChatV2Service(
        orchestrator=_FakeOrchestrator(
            _legacy(category="dangerous_setting_request", data={}, symbol=None)
        )
    ).send(
        db_session,
        request=AgentChatV2MessageRequest(message="안전장치 꺼줘"),
    )

    assert response["intent"] == "safety_block"
    assert response["status"] == "blocked"
    assert response["safety"]["setting_changed"] is False
    assert response["safety"]["scheduler_changed"] is False


def test_v2_message_route_is_available_without_changing_legacy_route(db_session):
    class _RouteService:
        def send(self, db, *, request):
            return {
                "intent": "analyze",
                "status": "completed",
                "message": "분석만 수행했습니다.",
                "requires_confirmation": False,
                "safety": {"real_order_submitted": False},
            }

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_agent_chat_v2_service] = lambda: _RouteService()
    try:
        response = TestClient(app).post(
            "/agent/chat/v2/message",
            json={"message": "삼성전자 분석해줘"},
        )
        assert response.status_code == 200
        assert response.json()["intent"] == "analyze"
    finally:
        app.dependency_overrides.clear()
