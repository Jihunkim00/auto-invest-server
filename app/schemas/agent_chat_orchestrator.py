from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.agent_chat_tool import (
    AgentChatResultCard,
    AgentChatToolCall,
    AgentChatToolResult,
)
from app.schemas.agent_chat_live_order import AgentChatLiveOrderActionPayload


class AgentChatIntentCategory(str, Enum):
    GENERAL_CHAT = "general_chat"
    CAPABILITY_QUESTION = "capability_question"
    READ_ONLY_PRICE_QUERY = "read_only_price_query"
    READ_ONLY_POSITIONS_QUERY = "read_only_positions_query"
    READ_ONLY_BALANCE_QUERY = "read_only_balance_query"
    READ_ONLY_ORDERS_QUERY = "read_only_orders_query"
    READ_ONLY_RUNS_QUERY = "read_only_runs_query"
    READ_ONLY_SIGNALS_QUERY = "read_only_signals_query"
    READ_ONLY_SETTINGS_QUERY = "read_only_settings_query"
    ANALYSIS_REQUEST = "analysis_request"
    WATCHLIST_PREVIEW_REQUEST = "watchlist_preview_request"
    EXIT_REVIEW_REQUEST = "exit_review_request"
    MANUAL_TICKET_REQUEST = "manual_ticket_request"
    LIVE_ORDER_REQUEST = "live_order_request"
    DANGEROUS_SETTING_REQUEST = "dangerous_setting_request"
    SCHEDULER_REQUEST = "scheduler_request"
    UNSUPPORTED = "unsupported"
    NEEDS_CLARIFICATION = "needs_clarification"


class AgentChatContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    default_market: str | None = Field(default=None, max_length=10)
    default_provider: str | None = Field(default=None, max_length=20)
    timezone: str | None = Field(default="Asia/Seoul", max_length=80)


class AgentChatSendRequest(BaseModel):
    conversation_key: str | None = Field(default=None, max_length=80)
    message: str = Field(min_length=1, max_length=4000)
    context: AgentChatContext | dict[str, Any] = Field(default_factory=AgentChatContext)
    auto_create_conversation: bool = True

    def context_dict(self) -> dict[str, Any]:
        if isinstance(self.context, AgentChatContext):
            return self.context.model_dump(mode="json", exclude_none=True)
        return dict(self.context or {})


class AgentChatIntent(BaseModel):
    model_config = ConfigDict(extra="allow")

    category: AgentChatIntentCategory
    supported: bool = True
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    market: str | None = None
    provider: str | None = None
    symbol: str | None = None
    symbol_name: str | None = None
    side: str = "none"
    quantity: float | None = None
    notional: float | None = None
    currency: str | None = None
    requires_plan: bool = False
    requires_auth: bool = False
    requires_manual_confirmation: bool = False
    reason: str | None = None
    fallback_used: bool = False
    parser_status: str = "fallback"
    model_name: str | None = None
    selected_tools: list[AgentChatToolCall] = Field(default_factory=list)


class AgentChatAnswer(BaseModel):
    role: str = "assistant"
    text: str
    answer_type: str = "general_answer"


class AgentChatSafetyFlags(BaseModel):
    read_only: bool = True
    safe_execution_only: bool = True
    real_order_submitted: bool = False
    broker_submit_called: bool = False
    manual_submit_called: bool = False
    validation_called: bool = False
    setting_changed: bool = False
    scheduler_changed: bool = False
    confirm_live_auto_checked: bool = False
    broker_api_called: bool = False
    agent_schedule_created: bool = False
    mutation: bool = False


class AgentChatSendResponse(BaseModel):
    conversation_key: str
    user_message_id: int | None = None
    assistant_message_id: int | None = None
    intent: AgentChatIntent
    answer: AgentChatAnswer
    data: dict[str, Any] = Field(default_factory=dict)
    command: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    run: dict[str, Any] | None = None
    live_order_action: AgentChatLiveOrderActionPayload | None = None
    available_actions: list[str] = Field(default_factory=list)
    safety: AgentChatSafetyFlags = Field(default_factory=AgentChatSafetyFlags)
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    selected_tools: list[AgentChatToolCall] = Field(default_factory=list)
    tool_results: list[AgentChatToolResult] = Field(default_factory=list)
    result_cards: list[AgentChatResultCard] = Field(default_factory=list)
    follow_up_suggestions: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    answer_type: str | None = None
    fallback_used: bool = False
