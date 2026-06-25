from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


StrategyProfileName = Literal["safe", "balanced", "aggressive"]


class ProfileAwareDryRunAutoBuyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "kis"
    market: str = "KR"
    profile_name: StrategyProfileName | None = None
    symbol: str | None = None
    max_candidates: int = Field(default=5, ge=1, le=20)
    trigger_source: str = Field(
        default="manual",
        min_length=1,
        max_length=80,
    )
    use_watchlist: bool = True
    save_logs: bool = True

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


class ProfileAwareDryRunAutoBuyResponse(BaseModel):
    status: str
    action: str
    provider: str
    market: str
    active_profile: str
    selected_symbol: str | None = None
    selected_symbol_name: str | None = None
    candidate_count: int
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    buy_score: float | None = None
    sell_score: float | None = None
    final_score: float | None = None
    confidence: float | None = None
    target_risk_approved: bool
    target_risk_result: dict[str, Any] = Field(default_factory=dict)
    recommended_notional_krw: float
    recommended_notional_pct: float
    simulated_quantity: int
    simulated_price: float | None = None
    simulated_notional_krw: float
    reason: str
    risk_flags: list[str] = Field(default_factory=list)
    gating_notes: list[str] = Field(default_factory=list)
    signal_id: int | None = None
    trade_run_id: int | None = None
    simulated_order_id: int | None = None
    data_quality: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class ProfileAwareDryRunRecentResponse(BaseModel):
    provider: str
    market: str
    count: int
    items: list[dict[str, Any]] = Field(default_factory=list)
    safety: dict[str, Any] = Field(default_factory=dict)


class ProfileAwareDryRunSummaryResponse(BaseModel):
    provider: str
    market: str
    today: dict[str, Any] = Field(default_factory=dict)
    month: dict[str, Any] = Field(default_factory=dict)
    profiles: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)
