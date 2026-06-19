from app.schemas.agent_chat import AgentChatConversationCreateRequest
from app.schemas.agent_chat_orchestrator import AgentChatIntent, AgentChatIntentCategory
from app.schemas.agent_chat_tool import AgentChatToolResult
from app.services.agent_chat_context_service import AgentChatContextService
from app.services.agent_chat_service import AgentChatService


def test_context_service_loads_latest_persisted_context_snapshot(db_session):
    chat = AgentChatService()
    created = chat.create_conversation(
        db_session,
        request=AgentChatConversationCreateRequest(title="Context"),
    )
    key = created["conversation"]["conversation_key"]
    chat.append_message(
        db_session,
        conversation_key=key,
        request={
            "role": "assistant",
            "text": "Price answer",
            "message_type": "read_only_result",
            "metadata": {
                "context_snapshot": {
                    "last_symbol": "005930",
                    "last_symbol_name": "Samsung Electronics",
                    "last_market": "KR",
                    "last_provider": "kis",
                    "last_intent": "read_only_price_query",
                    "last_tool_name": "kis_price_lookup",
                    "last_price": 72000,
                }
            },
        },
    )

    snapshot = AgentChatContextService().load_context(db_session, conversation_key=key)

    assert snapshot["last_symbol"] == "005930"
    assert snapshot["last_provider"] == "kis"
    assert snapshot["last_tool_name"] == "kis_price_lookup"
    assert snapshot["last_price"] == 72000


def test_context_service_builds_snapshot_from_intent_and_tool_results():
    service = AgentChatContextService()
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
                "market": "KR",
                "provider": "kis",
            }
        },
        summary="ok",
    )

    snapshot = service.build_snapshot(intent=intent, tool_results=[result])

    assert snapshot["last_symbol"] == "005930"
    assert snapshot["last_symbol_name"] == "Samsung Electronics"
    assert snapshot["last_market"] == "KR"
    assert snapshot["last_provider"] == "kis"
    assert snapshot["last_tool_name"] == "kis_price_lookup"
    assert snapshot["last_price"] == 72000
