from __future__ import annotations

import json

from app.db.models import AgentCommandLog
from app.services.agent_chat_service import AgentChatService


def test_create_conversation_and_append_user_message_updates_last_message(db_session):
    service = AgentChatService()
    created = service.create_conversation(
        db_session,
        request={"title": None, "source": "flutter_dashboard", "metadata": {"source": "flutter_dashboard"}},
    )
    conversation = created["conversation"]

    assert conversation["conversation_key"].startswith("conv_")
    assert conversation["status"] == "active"

    appended = service.append_message(
        db_session,
        conversation_key=conversation["conversation_key"],
        request={
            "role": "user",
            "text": "Show my positions",
            "message_type": "plain_text",
        },
    )

    message = appended["message"]
    assert message["role"] == "user"
    assert message["text"] == "Show my positions"
    refreshed = service.get_conversation(
        db_session,
        conversation_key=conversation["conversation_key"],
    )["conversation"]
    assert refreshed["last_message_at"] is not None
    assert refreshed["title"] == "Show my positions"


def test_append_assistant_plan_message_saves_links_and_sanitizes_metadata(db_session):
    service = AgentChatService()
    conversation = service.create_conversation(db_session)["conversation"]

    message = service.append_message(
        db_session,
        conversation_key=conversation["conversation_key"],
        request={
            "role": "assistant",
            "text": "Plan ready. OPENAI_API_KEY=sk-secret",
            "message_type": "plan_review",
            "command_log_id": 7,
            "plan_id": 8,
            "plan_run_id": 9,
            "auth_approval_request_id": 10,
            "model_name": "gpt-5.4-mini",
            "parser_status": "gpt",
            "metadata": {
                "command_type": "SHOW_POSITIONS",
                "OPENAI_API_KEY": "sk-secret",
                "access_token": "token",
                "raw_response": {"should": "drop"},
            },
            "safety": {
                "real_order_submitted": False,
                "access_token": "token",
            },
        },
    )["message"]

    assert message["text"] == "Plan ready. OPENAI_API_KEY=[REDACTED]"
    assert message["command_log_id"] == 7
    assert message["plan_id"] == 8
    assert message["plan_run_id"] == 9
    assert message["auth_approval_request_id"] == 10
    assert message["model_name"] == "gpt-5.4-mini"
    assert message["parser_status"] == "gpt"
    assert message["metadata"]["command_type"] == "SHOW_POSITIONS"
    assert "OPENAI_API_KEY" not in message["metadata"]
    assert "access_token" not in message["metadata"]
    assert "raw_response" not in message["metadata"]
    assert message["safety"]["real_order_submitted"] is False
    assert "access_token" not in message["safety"]


def test_fetch_messages_preserves_created_order_and_limit(db_session):
    service = AgentChatService()
    conversation = service.create_conversation(db_session)["conversation"]
    for text in ["one", "two", "three"]:
        service.append_message(
            db_session,
            conversation_key=conversation["conversation_key"],
            request={"role": "user", "text": text},
        )

    messages = service.list_messages(
        db_session,
        conversation_key=conversation["conversation_key"],
        limit=2,
    )["messages"]

    assert [message["text"] for message in messages] == ["one", "two"]


def test_archive_conversation_excludes_it_from_active_list(db_session):
    service = AgentChatService()
    conversation = service.create_conversation(db_session)["conversation"]

    archived = service.archive_conversation(
        db_session,
        conversation_key=conversation["conversation_key"],
    )["conversation"]

    assert archived["status"] == "archived"
    assert archived["archived_at"] is not None
    assert service.list_conversations(db_session, status="active")["count"] == 0
    assert service.list_conversations(db_session, status="archived")["count"] == 1


def test_conversation_key_links_to_agent_command_log(db_session):
    service = AgentChatService()
    conversation = service.create_conversation(db_session)["conversation"]
    row = AgentCommandLog(
        conversation_id=conversation["conversation_key"],
        user_message="positions",
        parser_status="fallback",
        command_type="SHOW_POSITIONS",
        domain="position",
        market="KR",
        provider="kis",
        symbol=None,
        side="none",
        risk_level="read_only",
        requires_auth=False,
        needs_clarification=False,
        parsed_command_json=json.dumps({"command_type": "SHOW_POSITIONS"}),
        safety_json=json.dumps({"real_order_submitted": False}),
        model_name=None,
        schema_version="autoinvest_command_v1",
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    message = service.append_message(
        db_session,
        conversation_key=conversation["conversation_key"],
        request={
            "role": "assistant",
            "text": "Command parsed",
            "message_type": "command_parse",
            "command_log_id": row.id,
            "metadata": {"command_log_id": row.id},
        },
    )["message"]

    assert message["command_log_id"] == row.id
    assert row.conversation_id == conversation["conversation_key"]
