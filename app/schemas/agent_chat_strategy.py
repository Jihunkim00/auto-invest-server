from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.strategy import StrategyProfilePayload


class AgentChatStrategyActionPayload(BaseModel):
    action_id: int
    conversation_key: str | None = None
    user_message_id: int | None = None
    assistant_message_id: int | None = None
    action_type: str = "strategy_profile_apply"
    requested_profile: str
    current_profile: str | None = None
    status: str
    expires_at: datetime | str | None = None
    confirmed_at: datetime | str | None = None
    cancelled_at: datetime | str | None = None
    active_profile: StrategyProfilePayload | None = None
    requested_profile_payload: StrategyProfilePayload | None = None
    result_payload: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)
    audit: dict[str, Any] = Field(default_factory=dict)


class AgentChatStrategyActionConfirmRequest(BaseModel):
    confirmation: bool = True
    confirm_operator_ack: bool = True


class AgentChatStrategyActionCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class AgentChatStrategyActionAnswer(BaseModel):
    role: str = "assistant"
    text: str
    answer_type: str


class AgentChatStrategyActionResponse(BaseModel):
    status: str
    answer: AgentChatStrategyActionAnswer
    strategy_action: AgentChatStrategyActionPayload | None = None
    active_profile: StrategyProfilePayload | None = None
    safety: dict[str, Any] = Field(default_factory=dict)
    assistant_message_id: int | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)

