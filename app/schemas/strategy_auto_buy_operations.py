from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


StrategyAutoBuyStage = Literal[
    "scheduler_disabled",
    "scheduled_dry_run_waiting",
    "scheduled_dry_run_blocked",
    "promotion_pending",
    "promotion_expired",
    "no_dry_run",
    "dry_run_blocked",
    "dry_run_would_buy",
    "live_readiness_blocked",
    "ready_for_operator_confirm",
    "submitted_today",
    "sync_required",
    "disabled",
]

StrategyAutoBuyNextOperatorAction = Literal[
    "enable_dry_run_scheduler_if_desired",
    "wait_for_scheduled_dry_run",
    "review_promotion",
    "acknowledge_or_dismiss_promotion",
    "run_dry_run",
    "review_block_reason",
    "enable_prerequisites_manually",
    "confirm_guarded_live_buy",
    "sync_latest_attempt",
    "wait",
    "no_action",
]


class StrategyAutoBuyOperationsDryRunStatus(BaseModel):
    recent_found: bool
    latest_action: str | None = None
    latest_symbol: str | None = None
    latest_score: float | None = None
    latest_time: str | None = None
    would_buy_count_today: int = 0
    blocked_count_today: int = 0
    summary: dict[str, Any] = Field(default_factory=dict)


class StrategyAutoBuyOperationsLiveReadinessStatus(BaseModel):
    ready: bool
    enabled: bool
    primary_block_reason: str | None = None
    recent_dry_run_required: bool
    recent_dry_run_found: bool
    dry_run_status: str | None = None
    kill_switch: bool
    kis_real_order_enabled: bool
    target_risk_ready: bool
    orders_remaining_today: int


class StrategyAutoBuyOperationsLiveAttemptsStatus(BaseModel):
    latest_status: str | None = None
    submitted_count_today: int = 0
    blocked_count_today: int = 0
    sync_required_count: int = 0
    recent: list[dict[str, Any]] = Field(default_factory=list)


class StrategyAutoBuyOperationsRiskStatus(BaseModel):
    entry_allowed: bool
    size_multiplier: float | None = None
    target_progress_pct: float | None = None
    daily_loss_limit_hit: bool
    monthly_loss_limit_hit: bool


class StrategyAutoBuyOperationsSchedulerStatus(BaseModel):
    enabled: bool = False
    dry_run_only: bool = True
    allow_live_orders: bool = False
    runs_today: int = 0
    max_runs_per_day: int = 0
    latest_run_status: str | None = None
    next_allowed_run_at: str | None = None


class StrategyAutoBuyOperationsPromotionsStatus(BaseModel):
    pending_count: int = 0
    latest_symbol: str | None = None
    latest_status: str | None = None
    latest_expires_at: str | None = None
    acknowledged_count_today: int = 0
    dismissed_count_today: int = 0


class StrategyAutoBuyOperationsSafetyStatus(BaseModel):
    read_only: bool = True
    validation_called: bool = False
    broker_submit_called: bool = False
    manual_submit_called: bool = False
    setting_changed: bool = False
    scheduler_changed: bool = False


class StrategyAutoBuyOperationsStatusResponse(BaseModel):
    provider: str
    market: str
    active_profile: str | None = None
    auto_buy_stage: StrategyAutoBuyStage
    next_operator_action: StrategyAutoBuyNextOperatorAction
    dry_run: StrategyAutoBuyOperationsDryRunStatus
    scheduler: StrategyAutoBuyOperationsSchedulerStatus = Field(
        default_factory=StrategyAutoBuyOperationsSchedulerStatus
    )
    promotions: StrategyAutoBuyOperationsPromotionsStatus = Field(
        default_factory=StrategyAutoBuyOperationsPromotionsStatus
    )
    live_readiness: StrategyAutoBuyOperationsLiveReadinessStatus
    live_attempts: StrategyAutoBuyOperationsLiveAttemptsStatus
    risk: StrategyAutoBuyOperationsRiskStatus
    safety: StrategyAutoBuyOperationsSafetyStatus = Field(
        default_factory=StrategyAutoBuyOperationsSafetyStatus
    )
