from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentChatLiveOrderActionPayload(BaseModel):
    action_id: int
    conversation_key: str | None = None
    status: str
    action_type: str = "chat_confirmed_live_order"
    provider: str = "kis"
    market: str = "KR"
    symbol: str
    symbol_name: str | None = None
    side: str
    order_type: str = "market"
    quantity: float | None = None
    notional_amount: float | None = None
    currency: str = "KRW"
    estimated_price: float | None = None
    estimated_notional: float | None = None
    expires_at: datetime | str | None = None
    confirmation_phrase: str | None = None
    confirmation_token: str | None = None
    related_order_id: int | None = None
    broker_order_id: str | None = None
    broker_status: str | None = None
    internal_status: str | None = None
    last_sync_at: datetime | str | None = None
    last_sync_payload: dict[str, Any] = Field(default_factory=dict)
    audit: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)
    safety_controls: dict[str, Any] = Field(default_factory=dict)


class AgentChatLiveOrderConfirmRequest(BaseModel):
    confirmation: bool = False
    confirmation_phrase: str | None = Field(default=None, max_length=300)
    confirmation_token: str | None = Field(default=None, max_length=160)
    user_acknowledged_live_order: bool = False


class AgentChatLiveOrderCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class AgentChatLiveOrderAnswer(BaseModel):
    role: str = "assistant"
    text: str
    answer_type: str


class AgentChatLiveOrderResponse(BaseModel):
    status: str
    answer: AgentChatLiveOrderAnswer
    live_order_action: AgentChatLiveOrderActionPayload | None = None
    order: dict[str, Any] | None = None
    safety: dict[str, Any] = Field(default_factory=dict)
    assistant_message_id: int | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class AgentChatLiveOrderListResponse(BaseModel):
    status: str = "ok"
    count: int
    actions: list[AgentChatLiveOrderActionPayload] = Field(default_factory=list)
