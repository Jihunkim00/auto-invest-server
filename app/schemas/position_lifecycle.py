from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PositionLifecycleEvent(BaseModel):
    timestamp: str | None = None
    event_type: str
    title: str
    status: str | None = None
    source: str | None = None
    related_id: str | None = None
    summary: str | None = None
    safety_flags: list[str] = Field(default_factory=list)
    real_order_submitted: bool = False
    broker_submit_called: bool = False
    manual_submit_called: bool = False


class PositionLifecycleItem(BaseModel):
    lifecycle_id: str
    symbol: str
    name: str | None = None
    provider: str
    market: str
    lifecycle_status: str
    entry_source: str
    entry_order_id: int | None = None
    entry_broker_order_id: str | None = None
    entry_kis_odno: str | None = None
    entry_submitted_at: str | None = None
    entry_filled_at: str | None = None
    entry_quantity: float | None = None
    entry_average_price: float | None = None
    entry_notional: float | None = None
    related_promotion_id: int | None = None
    related_signal_id: int | None = None
    current_quantity: float | None = None
    current_price: float | None = None
    current_value: float | None = None
    cost_basis: float | None = None
    unrealized_pl: float | None = None
    unrealized_pl_pct: float | None = None
    exit_order_id: int | None = None
    exit_broker_order_id: str | None = None
    exit_kis_odno: str | None = None
    exit_submitted_at: str | None = None
    exit_filled_at: str | None = None
    exit_quantity: float | None = None
    exit_average_price: float | None = None
    exit_notional: float | None = None
    realized_pl: float | None = None
    realized_pl_pct: float | None = None
    fees: float | None = None
    holding_period_minutes: int | None = None
    latest_status: str | None = None
    latest_broker_status: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    gating_notes: list[str] = Field(default_factory=list)
    audit_flags: list[str] = Field(default_factory=list)
    next_safe_action: str
    events: list[PositionLifecycleEvent] = Field(default_factory=list)


class PositionLifecycleTotals(BaseModel):
    open_position_count: int = 0
    closed_lifecycle_count: int = 0
    total_current_value: float = 0
    total_unrealized_pl: float = 0
    total_realized_pl: float = 0
    total_realized_pl_pct: float | None = None
    incomplete_calculation_count: int = 0


class PositionLifecycleResponse(BaseModel):
    provider: str
    market: str
    generated_at: str
    items: list[PositionLifecycleItem] = Field(default_factory=list)
    totals: PositionLifecycleTotals
    safety: dict[str, Any] = Field(default_factory=dict)
    audit_flags: list[str] = Field(default_factory=list)
