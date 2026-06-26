from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProfileAwareGuardedLiveAutoBuyReadinessResponse(BaseModel):
    enabled: bool
    ready: bool
    provider: str
    market: str
    active_profile: str | None = None
    allowed_profiles: list[str] = Field(default_factory=list)
    dry_run: bool
    kill_switch: bool
    kis_enabled: bool
    kis_real_order_enabled: bool
    scheduler_live_enabled: bool
    recent_dry_run_required: bool
    recent_dry_run_found: bool
    recent_dry_run_age_minutes: float | None = None
    recent_dry_run_ttl_minutes: int
    selected_symbol: str | None = None
    max_orders_per_day: int
    orders_used_today: int
    orders_remaining_today: int
    max_notional_krw: float
    max_notional_pct: float
    primary_block_reason: str | None = None
    checks: list[dict[str, Any]] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    gating_notes: list[str] = Field(default_factory=list)
    safety: dict[str, Any] = Field(default_factory=dict)


class ProfileAwareGuardedLiveAutoBuyRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "kis"
    market: str = "KR"
    symbol: str | None = None
    confirm_operator_ack: bool
    source_dry_run_id: int | None = None
    max_notional_krw: float | None = Field(default=None, gt=0)
    trigger_source: str = Field(default="manual", min_length=1, max_length=80)
    client_request_id: str | None = Field(default=None, max_length=120)

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        provider = str(value or "").strip().lower()
        if provider != "kis":
            raise ValueError("guarded live auto buy supports provider=kis only.")
        return provider

    @field_validator("market")
    @classmethod
    def normalize_market(cls, value: str) -> str:
        market = str(value or "").strip().upper()
        if market != "KR":
            raise ValueError("guarded live auto buy supports market=KR only.")
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

    @field_validator("client_request_id")
    @classmethod
    def normalize_client_request_id(cls, value: str | None) -> str | None:
        text = str(value or "").strip()
        return text or None


class ProfileAwareGuardedLiveAutoBuyRunResponse(BaseModel):
    status: str
    action: str
    provider: str
    market: str
    active_profile: str | None = None
    symbol: str | None = None
    symbol_name: str | None = None
    source_dry_run_id: int | None = None
    source_signal_id: int | None = None
    source_trade_run_id: int | None = None
    target_risk_approved: bool
    validation_approved: bool
    submitted: bool
    quantity: int | None = None
    estimated_price: float | None = None
    submitted_notional_krw: float | None = None
    related_order_id: int | None = None
    broker_order_id: str | None = None
    broker_status: str | None = None
    internal_status: str | None = None
    block_reason: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    gating_notes: list[str] = Field(default_factory=list)
    attempt_id: int | None = None
    signal_id: int | None = None
    trade_run_id: int | None = None
    safety: dict[str, Any] = Field(default_factory=dict)


class ProfileAwareGuardedLiveAutoBuyRecentResponse(BaseModel):
    provider: str
    market: str
    count: int
    items: list[dict[str, Any]] = Field(default_factory=list)
    safety: dict[str, Any] = Field(default_factory=dict)
