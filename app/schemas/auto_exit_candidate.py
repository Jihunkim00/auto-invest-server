from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


CandidateType = Literal[
    "stop_loss",
    "take_profit",
    "trend_breakdown",
    "weak_momentum",
    "near_close_risk",
    "duplicate_sell_conflict",
    "sync_required",
    "manual_review",
]
CandidateSeverity = Literal["critical", "warning", "info"]
CandidateStatus = Literal["active", "dismissed", "converted_to_preflight", "unknown"]
CandidateActionHint = Literal["review", "run_sell_preflight", "hold", "sync_required"]


class AutoExitCandidate(BaseModel):
    candidate_id: str
    symbol: str
    provider: str
    market: str
    candidate_type: CandidateType
    severity: CandidateSeverity
    status: CandidateStatus = "active"
    action_hint: CandidateActionHint
    position_quantity: float | None = None
    available_quantity: float | None = None
    average_price: float | None = None
    current_price: float | None = None
    cost_basis: float | None = None
    current_value: float | None = None
    unrealized_pl: float | None = None
    unrealized_pl_pct: float | None = None
    stop_loss_threshold_pct: float | None = None
    take_profit_threshold_pct: float | None = None
    stop_loss_triggered: bool = False
    take_profit_triggered: bool = False
    trend_breakdown_triggered: bool = False
    momentum_note: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    gating_notes: list[str] = Field(default_factory=list)
    primary_reason: str
    next_safe_action: str
    related_position_id: int | None = None
    related_buy_order_id: int | None = None
    related_lifecycle_id: int | None = None
    open_sell_order_conflict: bool = False
    sync_required: bool = False
    can_run_sell_preflight: bool = False
    sell_preflight_endpoint_hint: str | None = None


class AutoExitCandidateSummary(BaseModel):
    candidate_count: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    stop_loss_count: int = 0
    take_profit_count: int = 0
    trend_breakdown_count: int = 0
    manual_review_count: int = 0
    duplicate_sell_block_count: int = 0
    sync_required_count: int = 0


class AutoExitCandidatesResponse(BaseModel):
    generated_at: str
    timezone: str
    provider: str
    market: str
    candidates: list[AutoExitCandidate]
    summary: AutoExitCandidateSummary
    safety_flags: list[str]
    details: dict[str, Any] | None = None
