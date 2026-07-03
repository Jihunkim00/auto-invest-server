from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PositionSellPreflightRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str = "kis"
    market: str = "KR"
    quantity_mode: str = Field(default="full")
    quantity: float | None = Field(default=None, gt=0)
    language: str | None = Field(default=None, max_length=20)
    locale: str | None = Field(default=None, max_length=20)

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        provider = str(value or "").strip().lower()
        if provider != "kis":
            raise ValueError("position sell preflight supports provider=kis only.")
        return provider

    @field_validator("market")
    @classmethod
    def normalize_market(cls, value: str) -> str:
        market = str(value or "").strip().upper()
        if market != "KR":
            raise ValueError("position sell preflight supports market=KR only.")
        return market

    @field_validator("quantity_mode")
    @classmethod
    def normalize_quantity_mode(cls, value: str) -> str:
        mode = str(value or "").strip().lower()
        if mode not in {"full", "partial"}:
            raise ValueError("quantity_mode must be full or partial.")
        return mode


class PositionExitReviewResponse(BaseModel):
    provider: str
    market: str
    positions: list[dict[str, Any]]
    total_position_value: float
    total_unrealized_pl: float
    total_unrealized_pl_pct: float | None = None
    updated_at: str
    safety: dict[str, Any]
    safety_flags: list[str]


class PositionSellPreflightResponse(BaseModel):
    symbol: str
    provider: str
    market: str
    preflight_status: str
    can_submit_after_confirmation: bool
    final_confirmation_required: bool = True
    real_order_submitted: bool = False
    broker_submit_called: bool = False
    manual_submit_called: bool = False
    order_id: int | None = None
    broker_order_id: str | None = None
    kis_odno: str | None = None
    position_exists: bool
    quantity_held: float | None = None
    available_quantity: float | None = None
    requested_quantity: float | None = None
    estimated_sell_notional: float | None = None
    current_price: float | None = None
    average_price: float | None = None
    cost_basis: float | None = None
    current_value: float | None = None
    unrealized_pl: float | None = None
    unrealized_pl_pct: float | None = None
    stop_loss_threshold_pct: float | None = None
    take_profit_threshold_pct: float | None = None
    stop_loss_triggered: bool
    take_profit_triggered: bool
    kill_switch: bool
    dry_run: bool
    kis_real_order_enabled: bool
    market_session_allowed: bool
    no_new_entry_window_allowed: bool
    risk_flags: list[str]
    gating_notes: list[str]
    checklist: list[dict[str, Any]]
    primary_block_reason: str | None = None
    next_required_action: str
    safety: dict[str, Any]
    updated_at: str | None = None
