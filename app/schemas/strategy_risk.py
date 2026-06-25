from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrategyRiskStateResponse(BaseModel):
    provider: str
    market: str
    active_profile: str
    monthly_target_return_pct: float
    monthly_target_min_pct: float
    monthly_target_max_pct: float
    current_month_return_pct: float
    target_progress_pct: float
    target_hit: bool
    monthly_max_loss_pct: float
    loss_budget_used_pct: float
    monthly_loss_limit_hit: bool
    daily_max_loss_pct: float
    current_daily_return_pct: float
    daily_loss_limit_hit: bool
    max_order_notional_pct: float
    max_order_notional_krw: float
    recommended_order_notional_pct: float
    recommended_order_notional_krw: float
    max_trades_per_day: int
    trades_used_today: int
    trades_remaining_today: int
    max_positions: int
    current_positions_count: int
    new_entries_allowed: bool
    primary_block_reason: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    gating_notes: list[str] = Field(default_factory=list)
    data_quality: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)


class StrategyEntryRiskEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "kis"
    market: str = "KR"
    symbol: str
    side: str
    requested_notional_krw: float | None = None
    requested_notional_pct: float | None = None
    buy_score: float | None = None
    sell_score: float | None = None
    confidence: float | None = None
    trigger_source: str | None = None
    dry_run: bool = True


class StrategyEntryRiskEvaluationResponse(BaseModel):
    approved: bool
    action: str
    symbol: str
    active_profile: str
    requested_notional_krw: float | None = None
    approved_notional_krw: float
    recommended_notional_krw: float
    sizing_multiplier: float
    block_reason: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    gating_notes: list[str] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    monthly_progress: dict[str, Any] = Field(default_factory=dict)
    daily_progress: dict[str, Any] = Field(default_factory=dict)
    profile_thresholds: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)
