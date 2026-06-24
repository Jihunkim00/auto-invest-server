from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


StrategyProfileName = Literal["safe", "balanced", "aggressive"]
StrategyProfileSource = Literal["settings_ui", "agent_chat"]


class StrategyProfilePayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_name: str
    display_name: str
    description: str | None = None
    monthly_target_return_pct: float
    monthly_target_min_pct: float
    monthly_target_max_pct: float
    monthly_max_loss_pct: float
    daily_max_loss_pct: float
    max_order_notional_pct: float
    max_order_notional_krw: float
    max_trades_per_day: int
    max_positions: int
    buy_score_threshold: float
    sell_score_threshold: float
    stop_loss_pct: float
    take_profit_pct: float
    max_holding_days: int
    stop_after_monthly_target: bool
    reduce_size_after_loss: bool
    consecutive_loss_reduce_threshold: int
    is_active: bool
    is_builtin: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StrategyProfileApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_name: StrategyProfileName
    confirm_operator_ack: bool = False
    source: StrategyProfileSource = "settings_ui"


class StrategyProfileApplyResponse(BaseModel):
    status: str
    active_profile: StrategyProfilePayload
    previous_profile: StrategyProfilePayload | None = None
    audit_id: int | None = None
    safety: dict[str, Any] = Field(default_factory=dict)


class StrategyProfileListResponse(BaseModel):
    profiles: list[StrategyProfilePayload]
    active_profile: StrategyProfilePayload


class StrategyMonthlyProgressResponse(BaseModel):
    active_profile: StrategyProfilePayload
    month: str | None = None
    provider: str | None = None
    market: str | None = None
    current_month_return_pct: float
    target_return_pct: float
    target_min_pct: float
    target_max_pct: float
    progress_ratio: float
    target_progress_pct: float = 0
    loss_budget_used_pct: float = 0
    target_hit: bool = False
    loss_limit_hit: bool = False
    realized_pnl: float = 0
    unrealized_pnl: float = 0
    net_pnl_estimated: float = 0
    data_quality: dict[str, Any] = Field(default_factory=dict)
    skeleton: bool = False
    note: str


class StrategyRiskBudgetResponse(BaseModel):
    active_profile: StrategyProfilePayload
    monthly_max_loss_pct: float
    daily_max_loss_pct: float
    max_order_notional_pct: float
    max_order_notional_krw: float
    max_trades_per_day: int
    max_positions: int
    buy_score_threshold: float
    sell_score_threshold: float
    stop_loss_pct: float
    take_profit_pct: float
    current_month_return_pct: float = 0
    target_progress_pct: float = 0
    loss_budget_used_pct: float = 0
    target_hit: bool = False
    loss_limit_hit: bool = False
    new_entries_allowed_by_target: bool = True
    new_entries_block_reason: str | None = None
    data_quality: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)

