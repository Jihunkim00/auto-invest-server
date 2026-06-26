from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


StrategyAutoBuyPromotionStatus = Literal[
    "pending",
    "acknowledged",
    "dismissed",
    "expired",
    "converted_to_live_attempt",
    "live_order_created",
    "live_order_synced",
    "live_order_rejected",
    "live_order_filled",
    "conversion_blocked",
    "blocked",
    "stale",
]


class StrategyAutoBuySchedulerRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "kis"
    market: str = "KR"
    symbol: str | None = None
    trigger_source: str = Field(default="manual_scheduler_dry_run", max_length=80)
    scheduler_slot: str | None = Field(default=None, max_length=80)

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        provider = str(value or "").strip().lower()
        if provider != "kis":
            raise ValueError("strategy auto-buy scheduler supports provider=kis only.")
        return provider

    @field_validator("market")
    @classmethod
    def normalize_market(cls, value: str) -> str:
        market = str(value or "").strip().upper()
        if market != "KR":
            raise ValueError("strategy auto-buy scheduler supports market=KR only.")
        return market

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        if value is None:
            return None
        symbol = str(value).strip().upper()
        if not symbol:
            return None
        if not symbol.isdigit() or len(symbol) > 6:
            raise ValueError("KIS symbol must be numeric.")
        return symbol.zfill(6)


class StrategyAutoBuyPromotionItem(BaseModel):
    id: int
    provider: str
    market: str
    active_profile: str | None = None
    symbol: str | None = None
    symbol_name: str | None = None
    status: str
    promotion_reason: str | None = None
    source_dry_run_signal_id: int | None = None
    source_dry_run_trade_run_id: int | None = None
    source_dry_run_order_id: int | None = None
    dry_run_action: str | None = None
    buy_score: float | None = None
    sell_score: float | None = None
    final_score: float | None = None
    confidence: float | None = None
    recommended_notional_krw: float | None = None
    simulated_quantity: float | None = None
    simulated_price: float | None = None
    simulated_notional_krw: float | None = None
    target_risk_result: dict[str, Any] = Field(default_factory=dict)
    block_reason: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    gating_notes: list[str] = Field(default_factory=list)
    expires_at: str | None = None
    acknowledged_at: str | None = None
    dismissed_at: str | None = None
    promoted_to_live_attempt_id: int | None = None
    related_live_order_id: int | None = None
    converted_live_attempt_id: int | None = None
    converted_order_id: int | None = None
    converted_at: str | None = None
    conversion_status: str | None = None
    last_sync_at: str | None = None
    last_sync_status: str | None = None
    trace_payload: dict[str, Any] = Field(default_factory=dict)
    request_payload: dict[str, Any] = Field(default_factory=dict)
    response_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class StrategyAutoBuyPromotionsResponse(BaseModel):
    provider: str = "kis"
    market: str = "KR"
    count: int
    items: list[StrategyAutoBuyPromotionItem] = Field(default_factory=list)
    safety: dict[str, Any] = Field(default_factory=dict)


class StrategyAutoBuyPromotionActionResponse(BaseModel):
    status: str
    promotion: StrategyAutoBuyPromotionItem
    safety: dict[str, Any] = Field(default_factory=dict)


class StrategyAutoBuyPromotionMarkConvertedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    promoted_to_live_attempt_id: int | None = None
    related_live_order_id: int | None = None


class StrategyAutoBuySchedulerStatusResponse(BaseModel):
    provider: str = "kis"
    market: str = "KR"
    enabled: bool
    dry_run_only: bool
    promotion_queue_only: bool
    allow_live_orders: bool
    real_order_submit_allowed: bool
    active_profile: str | None = None
    allowed_profiles: list[str] = Field(default_factory=list)
    runs_today: int = 0
    max_runs_per_day: int = 0
    next_allowed_run_at: str | None = None
    min_minutes_between_runs: int = 0
    market_open: bool | None = None
    after_no_new_entry_time: bool = False
    primary_block_reason: str | None = None
    pending_promotion_count: int = 0
    latest_scheduler_run: dict[str, Any] | None = None
    schedule_slots: list[str] = Field(default_factory=list)
    safety: dict[str, Any] = Field(default_factory=dict)


class StrategyAutoBuySchedulerRunResponse(BaseModel):
    status: str
    action: str
    provider: str = "kis"
    market: str = "KR"
    active_profile: str | None = None
    dry_run_result: dict[str, Any] | None = None
    promotion: StrategyAutoBuyPromotionItem | None = None
    created_promotion: bool = False
    block_reason: str | None = None
    scheduler_run_id: int | None = None
    real_order_submitted: bool = False
    validation_called: bool = False
    broker_submit_called: bool = False
    manual_submit_called: bool = False
    safety: dict[str, Any] = Field(default_factory=dict)
