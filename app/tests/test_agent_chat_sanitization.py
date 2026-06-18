from __future__ import annotations

from app.services.agent_chat_service import AgentChatService


def test_agent_chat_sanitizes_secret_text_and_metadata(db_session):
    service = AgentChatService()
    conversation = service.create_conversation(db_session)["conversation"]

    message = service.append_message(
        db_session,
        conversation_key=conversation["conversation_key"],
        request={
            "role": "assistant",
            "text": "authorization: Bearer abc.def OPENAI_API_KEY=sk-test password=hunter2",
            "message_type": "error",
            "status": "failed",
            "metadata": {
                "OPENAI_API_KEY": "sk-test",
                "access_token": "abc",
                "authorization": "Bearer abc.def",
                "command_type": "SHOW_POSITIONS",
                "safety": {
                    "real_order_submitted": False,
                    "refresh_token": "secret",
                },
            },
            "safety": {
                "real_order_submitted": False,
                "appsecret": "secret",
            },
        },
    )["message"]

    assert "sk-test" not in message["text"]
    assert "hunter2" not in message["text"]
    assert "abc.def" not in message["text"]
    assert "OPENAI_API_KEY" not in message["metadata"]
    assert "access_token" not in message["metadata"]
    assert "authorization" not in message["metadata"]
    assert message["metadata"]["command_type"] == "SHOW_POSITIONS"
    assert message["metadata"]["safety"]["real_order_submitted"] is False
    assert "refresh_token" not in message["metadata"]["safety"]
    assert message["safety"]["real_order_submitted"] is False
    assert "appsecret" not in message["safety"]


def test_agent_chat_drops_unapproved_metadata_payloads(db_session):
    service = AgentChatService()
    conversation = service.create_conversation(db_session)["conversation"]

    message = service.append_message(
        db_session,
        conversation_key=conversation["conversation_key"],
        request={
            "role": "assistant",
            "text": "Plan ready",
            "metadata": {
                "raw_openai_response": {"text": "large model output"},
                "broker_payload": {"account": "12345678"},
                "plan_id": 12,
                "scope_hash": "abc123",
            },
        },
    )["message"]

    assert message["metadata"] == {
        "plan_id": 12,
        "scope_hash": "abc123",
        "safety": {},
    }
