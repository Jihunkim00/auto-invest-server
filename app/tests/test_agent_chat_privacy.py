import json
from types import SimpleNamespace

from app.services.agent_chat_privacy_service import (
    AgentChatContextPrivacyService,
    AgentChatPrivacyClass,
)
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService


def test_privacy_classifier_prioritizes_secret_then_private_account():
    service = AgentChatContextPrivacyService()

    assert service.classify({"appsecret": "hidden"}) == AgentChatPrivacyClass.SECRET
    assert service.classify({"account_number": "12345678"}) == AgentChatPrivacyClass.SECRET
    assert service.classify({"cash": 100000}) == AgentChatPrivacyClass.PRIVATE_ACCOUNT
    assert service.classify({"positions": [{"qty": 2}]}) == AgentChatPrivacyClass.PRIVATE_ACCOUNT
    assert service.classify({"current_price": 72000, "symbol": "005930"}) == AgentChatPrivacyClass.PUBLIC


def test_public_context_drops_account_and_secret_fields_recursively():
    service = AgentChatContextPrivacyService()
    context = service.public_context(
        intent_name="analyze",
        symbol="005930",
        symbol_name="삼성전자",
        market="KR",
        data={
            "price": {"current_price": 72000, "currency": "KRW", "cash": 100000},
            "analysis": {"final_score": 61, "reason": "공개 시장 분석"},
            "risk": {"risk_flags": ["score_gate"]},
            "balance": {"cash": 100000, "account_number": "12345678"},
            "positions": [{"symbol": "005930", "qty": 2, "average_cost": 65000}],
            "appsecret": "hidden",
            "runs": [{"action": "HOLD", "broker_order_id": "internal-id"}],
        },
    )

    serialized = json.dumps(context, ensure_ascii=False)
    assert service.classify(context) == AgentChatPrivacyClass.PUBLIC
    assert context["price"] == {"current_price": 72000, "currency": "KRW"}
    assert "cash" not in serialized
    assert "account_number" not in serialized
    assert "average_cost" not in serialized
    assert "broker_order_id" not in serialized
    assert "hidden" not in serialized


def test_secret_user_message_is_blocked_before_external_call():
    service = AgentChatContextPrivacyService()

    safe_message, privacy_class = service.redact_user_message(
        "삼성전자 분석해줘 appsecret=hidden-token"
    )

    assert safe_message is None
    assert privacy_class == AgentChatPrivacyClass.SECRET


def test_router_gpt_prompt_uses_only_public_routing_context():
    class FakeResponses:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                output_text='{"category":"analysis_request","supported":true,"confidence":0.9,"market":"KR","provider":"kis","symbol":"005930","symbol_name":"삼성전자","side":"none","quantity":null,"notional":null,"currency":null,"requires_plan":true,"requires_auth":false,"requires_manual_confirmation":false,"reason":"public analysis","selected_tools":[]}'
            )

    class FakeClient:
        def __init__(self):
            self.responses = FakeResponses()

    client = FakeClient()
    router = AgentChatIntentRouterService(openai_client=client)
    intent = router.route(
        message="삼성전자 분석해줘",
        context={
            "default_market": "KR",
            "default_provider": "kis",
            "cash": 100000,
            "positions": [{"qty": 2}],
            "account_number": "12345678",
            "appsecret": "hidden",
        },
    )

    prompt = json.loads(client.responses.calls[0]["input"])
    routing_context = json.dumps(prompt["context"], ensure_ascii=False)
    assert intent.category.value == "analysis_request"
    assert "default_market" in routing_context
    assert "cash" not in routing_context
    assert "positions" not in routing_context
    assert "account_number" not in routing_context
    assert "appsecret" not in routing_context
    assert "12345678" not in routing_context
