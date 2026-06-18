from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentChatConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    source: str = Field(default="flutter_dashboard", max_length=40)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentChatMessageAppendRequest(BaseModel):
    role: str = Field(default="user", max_length=20)
    text: str = Field(min_length=1)
    message_type: str = Field(default="plain_text", max_length=40)
    status: str = Field(default="completed", max_length=20)
    command_log_id: int | None = None
    plan_id: int | None = None
    plan_run_id: int | None = None
    auth_approval_request_id: int | None = None
    prefill_source_plan_id: int | None = None
    model_name: str | None = Field(default=None, max_length=120)
    parser_status: str | None = Field(default=None, max_length=40)
    safety: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentChatConversationPayload(BaseModel):
    id: int
    conversation_key: str
    title: str | None
    status: str
    source: str
    metadata: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None
    last_message_at: datetime | None = None


class AgentChatMessagePayload(BaseModel):
    id: int
    conversation_id: int
    conversation_key: str
    role: str
    message_type: str
    status: str
    text: str
    command_log_id: int | None = None
    plan_id: int | None = None
    plan_run_id: int | None = None
    auth_approval_request_id: int | None = None
    prefill_source_plan_id: int | None = None
    model_name: str | None = None
    parser_status: str | None = None
    safety: dict[str, Any]
    metadata: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None
