from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.agent_chat_tool import (
    AgentChatResultCard,
    AgentChatToolCall,
    AgentChatToolResult,
)
from app.schemas.agent_chat_live_order import AgentChatLiveOrderActionPayload
from app.schemas.agent_chat_strategy import AgentChatStrategyActionPayload


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
    READ_ONLY_DAILY_OPS_SUMMARY_QUERY = "read_only_daily_ops_summary_query"
    READ_ONLY_OPERATOR_ALERTS_QUERY = "read_only_operator_alerts_query"
    READ_ONLY_PRODUCTION_READINESS_QUERY = (
        "read_only_production_readiness_query"
    )
    READ_ONLY_BROKER_SYNC_WATCHDOG_QUERY = (
        "read_only_broker_sync_watchdog_query"
    )
    READ_ONLY_AUTOMATION_SOAK_QUERY = "read_only_automation_soak_query"
    ANALYSIS_REQUEST = "analysis_request"
    WATCHLIST_PREVIEW_REQUEST = "watchlist_preview_request"
    EXIT_REVIEW_REQUEST = "exit_review_request"
    MANUAL_TICKET_REQUEST = "manual_ticket_request"
    LIVE_ORDER_REQUEST = "live_order_request"
    DANGEROUS_SETTING_REQUEST = "dangerous_setting_request"
    SCHEDULER_REQUEST = "scheduler_request"
    STRATEGY_PROFILE_QUERY = "strategy_profile_query"
    STRATEGY_PROFILE_COMPARE = "strategy_profile_compare"
    STRATEGY_PROFILE_RECOMMENDATION = "strategy_profile_recommendation"
    STRATEGY_PROFILE_CHANGE_REQUEST = "strategy_profile_change_request"
    STRATEGY_MONTHLY_PROGRESS_QUERY = "strategy_monthly_progress_query"
    STRATEGY_RISK_BUDGET_QUERY = "strategy_risk_budget_query"
    STRATEGY_DAILY_PERFORMANCE_QUERY = "strategy_daily_performance_query"
    STRATEGY_MONTHLY_PERFORMANCE_QUERY = "strategy_monthly_performance_query"
    STRATEGY_TARGET_PROGRESS_QUERY = "strategy_target_progress_query"
    STRATEGY_TRADE_PERFORMANCE_QUERY = "strategy_trade_performance_query"
    STRATEGY_LOSS_BUDGET_QUERY = "strategy_loss_budget_query"
    STRATEGY_RISK_STATE_QUERY = "strategy_risk_state_query"
    STRATEGY_ENTRY_RISK_QUERY = "strategy_entry_risk_query"
    STRATEGY_ORDER_SIZING_QUERY = "strategy_order_sizing_query"
    STRATEGY_LOSS_LIMIT_QUERY = "strategy_loss_limit_query"
    STRATEGY_TARGET_GATE_QUERY = "strategy_target_gate_query"
    STRATEGY_DRY_RUN_AUTO_BUY_REQUEST = "strategy_dry_run_auto_buy_request"
    STRATEGY_DRY_RUN_AUTO_BUY_RECENT_QUERY = (
        "strategy_dry_run_auto_buy_recent_query"
    )
    STRATEGY_DRY_RUN_AUTO_BUY_SUMMARY_QUERY = (
        "strategy_dry_run_auto_buy_summary_query"
    )
    STRATEGY_DRY_RUN_AUTO_BUY_REASON_QUERY = (
        "strategy_dry_run_auto_buy_reason_query"
    )
    STRATEGY_AUTO_BUY_OPERATIONS_STATUS_QUERY = (
        "strategy_auto_buy_operations_status_query"
    )
    STRATEGY_AUTO_BUY_NEXT_ACTION_QUERY = "strategy_auto_buy_next_action_query"
    STRATEGY_AUTO_BUY_BLOCK_REASON_QUERY = (
        "strategy_auto_buy_block_reason_query"
    )
    STRATEGY_AUTO_BUY_SCHEDULER_STATUS_QUERY = (
        "strategy_auto_buy_scheduler_status_query"
    )
    STRATEGY_AUTO_BUY_PROMOTION_QUEUE_QUERY = (
        "strategy_auto_buy_promotion_queue_query"
    )
    STRATEGY_AUTO_BUY_PROMOTION_REASON_QUERY = (
        "strategy_auto_buy_promotion_reason_query"
    )
    STRATEGY_LIVE_AUTO_BUY_READINESS_QUERY = (
        "strategy_live_auto_buy_readiness_query"
    )
    STRATEGY_LIVE_AUTO_BUY_RECENT_QUERY = (
        "strategy_live_auto_buy_recent_query"
    )
    STRATEGY_LIVE_AUTO_BUY_BLOCK_REASON_QUERY = (
        "strategy_live_auto_buy_block_reason_query"
    )
    STRATEGY_LIVE_AUTO_EXIT_READINESS_QUERY = (
        "strategy_live_auto_exit_readiness_query"
    )
    STRATEGY_LIVE_AUTO_EXIT_RECENT_QUERY = (
        "strategy_live_auto_exit_recent_query"
    )
    STRATEGY_LIVE_AUTO_EXIT_BLOCK_REASON_QUERY = (
        "strategy_live_auto_exit_block_reason_query"
    )
    STRATEGY_EXIT_CANDIDATE_QUERY = "strategy_exit_candidate_query"
    STRATEGY_POSITION_MANAGEMENT_DRY_RUN_QUERY = (
        "strategy_position_management_dry_run_query"
    )
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
    language: str = Field(default="ko", max_length=10)
    locale: str = Field(default="ko-KR", max_length=20)

    @field_validator("language", mode="before")
    @classmethod
    def normalize_language(cls, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"en", "en-us", "english"}:
            return "en"
        return "ko"

    @field_validator("locale", mode="before")
    @classmethod
    def normalize_locale(cls, value: Any) -> str:
        normalized = str(value or "").strip().lower().replace("_", "-")
        if normalized.startswith("en"):
            return "en-US"
        return "ko-KR"

    @model_validator(mode="after")
    def align_locale_with_language(self) -> "AgentChatSendRequest":
        if self.language == "en" or self.locale == "en-US":
            self.language = "en"
            self.locale = "en-US"
        else:
            self.language = "ko"
            self.locale = "ko-KR"
        return self

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
    requested_profile: str | None = None
    target_monthly_return_pct: float | None = None
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
    language: str = "ko"
    locale: str = "ko-KR"
    user_message_id: int | None = None
    assistant_message_id: int | None = None
    intent: AgentChatIntent
    answer: AgentChatAnswer
    data: dict[str, Any] = Field(default_factory=dict)
    command: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    run: dict[str, Any] | None = None
    live_order_action: AgentChatLiveOrderActionPayload | None = None
    strategy_action: AgentChatStrategyActionPayload | None = None
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
