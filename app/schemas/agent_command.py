from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "autoinvest_command_v1"


class CommandType(str, Enum):
    SHOW_HELP = "SHOW_HELP"
    SHOW_SYSTEM_STATUS = "SHOW_SYSTEM_STATUS"
    SHOW_OPERATIONS_STATUS = "SHOW_OPERATIONS_STATUS"
    SHOW_RISK_STATUS = "SHOW_RISK_STATUS"
    SHOW_BROKER_STATUS = "SHOW_BROKER_STATUS"
    SHOW_SCHEDULER_STATUS = "SHOW_SCHEDULER_STATUS"
    SHOW_SETTINGS = "SHOW_SETTINGS"
    SHOW_LOGS = "SHOW_LOGS"
    SHOW_RECENT_RUNS = "SHOW_RECENT_RUNS"
    SHOW_RECENT_ORDERS = "SHOW_RECENT_ORDERS"
    SHOW_RECENT_SIGNALS = "SHOW_RECENT_SIGNALS"
    RUN_MARKET_ANALYSIS = "RUN_MARKET_ANALYSIS"
    RUN_SINGLE_SYMBOL_ANALYSIS = "RUN_SINGLE_SYMBOL_ANALYSIS"
    RUN_WATCHLIST_PREVIEW = "RUN_WATCHLIST_PREVIEW"
    RUN_WATCHLIST_GPT_REVIEW = "RUN_WATCHLIST_GPT_REVIEW"
    SHOW_DECISION_REVIEW = "SHOW_DECISION_REVIEW"
    SHOW_OPERATOR_SUMMARY = "SHOW_OPERATOR_SUMMARY"
    SHOW_CANDIDATE_DETAIL = "SHOW_CANDIDATE_DETAIL"
    SHOW_PORTFOLIO = "SHOW_PORTFOLIO"
    SHOW_POSITIONS = "SHOW_POSITIONS"
    SHOW_POSITION_DETAIL = "SHOW_POSITION_DETAIL"
    REFRESH_BALANCE = "REFRESH_BALANCE"
    REFRESH_POSITIONS = "REFRESH_POSITIONS"
    REFRESH_OPEN_ORDERS = "REFRESH_OPEN_ORDERS"
    RUN_PORTFOLIO_REVIEW = "RUN_PORTFOLIO_REVIEW"
    RUN_EXIT_PREFLIGHT = "RUN_EXIT_PREFLIGHT"
    RUN_EXIT_SHADOW_DECISION = "RUN_EXIT_SHADOW_DECISION"
    SHOW_EXIT_REVIEW = "SHOW_EXIT_REVIEW"
    SHOW_EXIT_REVIEW_QUEUE = "SHOW_EXIT_REVIEW_QUEUE"
    PREPARE_MANUAL_SELL_TICKET = "PREPARE_MANUAL_SELL_TICKET"
    MARK_EXIT_QUEUE_REVIEWED = "MARK_EXIT_QUEUE_REVIEWED"
    DISMISS_EXIT_QUEUE_ITEM = "DISMISS_EXIT_QUEUE_ITEM"
    PREPARE_MANUAL_BUY_TICKET = "PREPARE_MANUAL_BUY_TICKET"
    VALIDATE_MANUAL_ORDER = "VALIDATE_MANUAL_ORDER"
    REQUEST_LIVE_ORDER_SUBMIT = "REQUEST_LIVE_ORDER_SUBMIT"
    CANCEL_MANUAL_ORDER_DRAFT = "CANCEL_MANUAL_ORDER_DRAFT"
    SYNC_ORDER = "SYNC_ORDER"
    SYNC_OPEN_ORDERS = "SYNC_OPEN_ORDERS"
    CREATE_ANALYSIS_SCHEDULE = "CREATE_ANALYSIS_SCHEDULE"
    CREATE_EXIT_PREFLIGHT_SCHEDULE = "CREATE_EXIT_PREFLIGHT_SCHEDULE"
    CREATE_WATCHLIST_PREVIEW_SCHEDULE = "CREATE_WATCHLIST_PREVIEW_SCHEDULE"
    SHOW_SCHEDULES = "SHOW_SCHEDULES"
    CANCEL_SCHEDULE = "CANCEL_SCHEDULE"
    PAUSE_SCHEDULER = "PAUSE_SCHEDULER"
    RESUME_SCHEDULER = "RESUME_SCHEDULER"
    REQUEST_LIVE_ORDER_SCHEDULE = "REQUEST_LIVE_ORDER_SCHEDULE"
    REQUEST_SETTING_CHANGE = "REQUEST_SETTING_CHANGE"
    REQUEST_RISK_SETTING_CHANGE = "REQUEST_RISK_SETTING_CHANGE"
    SET_DRY_RUN = "SET_DRY_RUN"
    SET_KILL_SWITCH = "SET_KILL_SWITCH"
    SET_BOT_ENABLED = "SET_BOT_ENABLED"
    SET_SCHEDULER_ENABLED = "SET_SCHEDULER_ENABLED"
    SET_DEFAULT_GATE_LEVEL = "SET_DEFAULT_GATE_LEVEL"
    SET_MAX_TRADES_PER_DAY = "SET_MAX_TRADES_PER_DAY"
    SET_MAX_ORDER_SIZE = "SET_MAX_ORDER_SIZE"
    SET_NO_NEW_ENTRY_AFTER = "SET_NO_NEW_ENTRY_AFTER"
    SET_MAX_POSITION_SIZE = "SET_MAX_POSITION_SIZE"
    SET_DAILY_LOSS_LIMIT = "SET_DAILY_LOSS_LIMIT"
    SET_KIS_ENABLED = "SET_KIS_ENABLED"
    SET_KIS_REAL_ORDER_ENABLED = "SET_KIS_REAL_ORDER_ENABLED"
    SET_KIS_SCHEDULER_ENABLED = "SET_KIS_SCHEDULER_ENABLED"
    SET_KIS_SCHEDULER_REAL_ORDERS = "SET_KIS_SCHEDULER_REAL_ORDERS"
    SET_KIS_LIMITED_AUTO_SELL = "SET_KIS_LIMITED_AUTO_SELL"
    SET_KIS_LIMITED_AUTO_BUY = "SET_KIS_LIMITED_AUTO_BUY"
    SET_KIS_LIVE_AUTO_BUY = "SET_KIS_LIVE_AUTO_BUY"
    SET_KIS_LIVE_AUTO_SELL = "SET_KIS_LIVE_AUTO_SELL"
    SHOW_LIMITED_AUTO_SELL_READINESS = "SHOW_LIMITED_AUTO_SELL_READINESS"
    RUN_LIMITED_AUTO_SELL_REVIEW = "RUN_LIMITED_AUTO_SELL_REVIEW"
    REQUEST_LIMITED_AUTO_SELL_ENABLE = "REQUEST_LIMITED_AUTO_SELL_ENABLE"
    REQUEST_LIMITED_AUTO_SELL_DISABLE = "REQUEST_LIMITED_AUTO_SELL_DISABLE"
    SHOW_LIMITED_AUTO_BUY_READINESS = "SHOW_LIMITED_AUTO_BUY_READINESS"
    RUN_LIMITED_AUTO_BUY_REVIEW = "RUN_LIMITED_AUTO_BUY_REVIEW"
    REQUEST_LIMITED_AUTO_BUY_ENABLE = "REQUEST_LIMITED_AUTO_BUY_ENABLE"
    REQUEST_LIMITED_AUTO_BUY_DISABLE = "REQUEST_LIMITED_AUTO_BUY_DISABLE"
    CREATE_AGENT_PLAN = "CREATE_AGENT_PLAN"
    SHOW_AGENT_PLANS = "SHOW_AGENT_PLANS"
    CANCEL_AGENT_PLAN = "CANCEL_AGENT_PLAN"
    UPDATE_AGENT_PLAN = "UPDATE_AGENT_PLAN"
    APPROVE_AGENT_PLAN = "APPROVE_AGENT_PLAN"
    REJECT_AGENT_PLAN = "REJECT_AGENT_PLAN"
    UNKNOWN = "UNKNOWN"
    CLARIFY_REQUEST = "CLARIFY_REQUEST"


class CommandDomain(str, Enum):
    GENERAL = "general"
    ANALYSIS = "analysis"
    WATCHLIST = "watchlist"
    PORTFOLIO = "portfolio"
    POSITION = "position"
    EXIT = "exit"
    ORDER = "order"
    SCHEDULER = "scheduler"
    SETTINGS = "settings"
    RISK = "risk"
    SAFETY = "safety"
    LOGS = "logs"
    LIMITED_AUTO = "limited_auto"
    AGENT = "agent"
    UNKNOWN = "unknown"


class Market(str, Enum):
    US = "US"
    KR = "KR"
    ALL = "ALL"
    UNKNOWN = "UNKNOWN"


class Provider(str, Enum):
    ALPACA = "alpaca"
    KIS = "kis"
    ALL = "all"
    UNKNOWN = "unknown"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"
    NONE = "none"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    READ_ONLY = "read_only"
    ANALYSIS_ONLY = "analysis_only"
    PREFILL_ONLY = "prefill_only"
    SETTINGS_SAFE = "settings_safe"
    SETTINGS_DANGEROUS = "settings_dangerous"
    LIVE_ORDER_POSSIBLE = "live_order_possible"
    LIVE_ORDER = "live_order"
    SCHEDULER_LIVE_ORDER = "scheduler_live_order"
    UNKNOWN = "unknown"


class BudgetPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    amount: float | None = None
    currency: str | None = None
    mode: str | None = None


class SchedulePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str | None = None
    run_at: str | None = None
    timezone: str | None = None
    raw_time_text: str | None = None


class SettingsChangePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str | None = None
    value: Any = None
    previous_value: Any = None
    safety_direction: str | None = None
    raw_value: str | None = None


class RiskChangePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str | None = None
    value: Any = None
    previous_value: Any = None
    direction: str | None = None
    high_risk: bool = False


class PortfolioScopePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    scope: str | None = None
    symbol: str | None = None
    include_open_orders: bool | None = None


class ExecutionPolicyPayload(BaseModel):
    allow_execution: bool = False
    allow_live_order: bool = False
    allow_setting_change: bool = False
    allow_scheduler_change: bool = False
    requires_auth: bool = False
    requires_risk_approval: bool = False
    requires_recent_validation: bool = False
    requires_confirm_live: bool = False
    execution_blocked_in_pr56: bool = True
    reason: str = "PR56 parses commands only and never executes actions."


class SafetyFlagsPayload(BaseModel):
    execution_blocked_in_pr56: bool = True
    real_order_submitted: bool = False
    broker_submit_called: bool = False
    manual_submit_called: bool = False
    setting_changed: bool = False
    scheduler_changed: bool = False


class AutoInvestCommand(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = SCHEMA_VERSION
    command_type: CommandType = CommandType.UNKNOWN
    domain: CommandDomain = CommandDomain.UNKNOWN
    intent: str = "unknown"
    market: Market = Market.UNKNOWN
    provider: Provider = Provider.UNKNOWN
    symbol: str | None = None
    side: OrderSide = OrderSide.NONE
    quantity: float | None = None
    budget: BudgetPayload | None = None
    schedule: SchedulePayload | None = None
    settings_change: SettingsChangePayload | None = None
    risk_change: RiskChangePayload | None = None
    portfolio_scope: PortfolioScopePayload | None = None
    execution_policy: ExecutionPolicyPayload = Field(default_factory=ExecutionPolicyPayload)
    safety: SafetyFlagsPayload = Field(default_factory=SafetyFlagsPayload)
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    requires_auth: bool = False
    requires_risk_approval: bool = False
    needs_clarification: bool = False
    clarification_question: str | None = None
    user_visible_summary: str = "Command parsed for review. No action was executed."
    parser_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    high_risk: bool = False


class AgentCommandParseResponse(BaseModel):
    status: str
    parser_status: str
    command: AutoInvestCommand
    safety: SafetyFlagsPayload
    command_log_id: int | None = None
    error_message: str | None = None
