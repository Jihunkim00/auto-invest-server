from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.strategy import StrategyProfilePayload


class TradePerformanceItem(BaseModel):
    order_id: int | None = None
    entry_order_id: int | None = None
    exit_order_id: int | None = None
    symbol: str
    symbol_name: str | None = None
    provider: str
    market: str
    side: str
    quantity: float
    entry_price: float | None = None
    exit_price: float | None = None
    current_price: float | None = None
    realized_pnl: float | None = None
    unrealized_pnl: float | None = None
    net_pnl_estimated: float | None = None
    pnl_pct: float | None = None
    holding_minutes: int | None = None
    decision_source: str | None = None
    signal_id: int | None = None
    run_id: int | None = None
    agent_chat_action_id: int | None = None
    risk_flags: list[str] = Field(default_factory=list)
    gating_notes: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    closed_at: datetime | None = None
    status: str
    data_quality: dict[str, Any] = Field(default_factory=dict)


class StrategyDailyPerformanceResponse(BaseModel):
    date: date
    provider: str
    market: str
    active_profile: StrategyProfilePayload
    realized_pnl: float
    unrealized_pnl: float
    gross_pnl: float
    estimated_fees: float
    net_pnl_estimated: float
    pnl_pct: float
    orders_count: int
    filled_orders_count: int
    rejected_orders_count: int
    winning_trades_count: int
    losing_trades_count: int
    win_rate: float
    data_quality: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)


class StrategyMonthlyPerformanceResponse(BaseModel):
    month: str
    provider: str
    market: str
    active_profile: StrategyProfilePayload
    monthly_target_return_pct: float
    monthly_target_min_pct: float
    monthly_target_max_pct: float
    current_month_return_pct: float
    target_progress_pct: float
    monthly_max_loss_pct: float
    loss_budget_used_pct: float
    target_hit: bool
    loss_limit_hit: bool
    realized_pnl: float
    unrealized_pnl: float
    gross_pnl: float
    net_pnl_estimated: float
    estimated_fees: float
    orders_count: int
    filled_orders_count: int
    rejected_orders_count: int
    winning_trades_count: int
    losing_trades_count: int
    win_rate: float
    average_win: float
    average_loss: float
    profit_factor: float | None = None
    max_drawdown_pct: float
    new_entries_allowed_by_target: bool
    new_entries_block_reason: str | None = None
    data_quality: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)


class StrategyTradePerformanceResponse(BaseModel):
    provider: str
    market: str
    count: int
    items: list[TradePerformanceItem]
    data_quality: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)


class StrategyPerformanceSnapshotRequest(BaseModel):
    provider: str = "kis"
    market: str = "KR"
    period_type: str = "monthly"
    period_key: str | None = None


class StrategyPerformanceSnapshotResponse(BaseModel):
    status: str
    snapshot_id: int
    period_type: str
    period_key: str
    safety: dict[str, Any] = Field(default_factory=dict)
