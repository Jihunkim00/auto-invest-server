from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


StrategyProfileName = Literal["safe", "balanced", "aggressive"]


class ProfileAwareDryRunAutoBuyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "kis"
    market: str = "KR"
    # ``profile_name`` is the legacy strategy/risk preset identity. Custom
    # automation profile identity must travel separately.
    profile_name: StrategyProfileName | None = None
    automation_profile_key: str | None = Field(default=None, max_length=80)
    automation_profile_name: str | None = Field(default=None, max_length=120)
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

    @field_validator("automation_profile_key", "automation_profile_name")
    @classmethod
    def normalize_automation_profile_context(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class ProfileAwareDryRunAutoBuyResponse(BaseModel):
    status: str
    action: str
    provider: str
    market: str
    active_profile: str
    profile_key: str | None = None
    profile_name: str | None = None
    automation_profile_key: str | None = None
    automation_profile_name: str | None = None
    legacy_profile_name: StrategyProfileName | None = None
    profile_provider: str | None = None
    profile_market: str | None = None
    selected_symbol: str | None = None
    selected_symbol_name: str | None = None
    candidate_count: int
    configured_symbol_count: int = 0
    analyzed_symbol_count: int = 0
    quant_candidate_count: int = 0
    quant_scored_count: int = 0
    gpt_candidate_count: int = 0
    gpt_target_count: int = 0
    gpt_completed_count: int = 0
    gpt_failed_count: int = 0
    gpt_not_run_count: int = 0
    final_candidate_count: int = 0
    final_ranked_count: int = 0
    profile_eligible_symbol_count: int = 0
    profile_price_filtered_count: int = 0
    execution_candidate_count: int = 0
    profile_exclusion_counts: dict[str, int] = Field(default_factory=dict)
    preview_status: str = "unknown"
    preview_error: str | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    buy_score: float | None = None
    final_buy_score: float | None = None
    sell_score: float | None = None
    final_score: float | None = None
    selected_quant_buy_score: float | None = None
    selected_quant_sell_score: float | None = None
    selected_ai_buy_score: float | None = None
    selected_ai_sell_score: float | None = None
    selected_gpt_analysis_status: str | None = None
    selected_gpt_used: bool = False
    selected_gpt_reason: str | None = None
    selected_final_buy_score: float | None = None
    selected_final_sell_score: float | None = None
    selected_confidence: float | None = None
    selected_candidate_observability: dict[str, Any] = Field(default_factory=dict)
    required_entry_score: float = 0
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
    data_quality_limited: bool = False
    data_quality_notes: list[str] = Field(default_factory=list)
    data_quality_reduction_reasons: list[str] = Field(default_factory=list)
    sizing_mode: str = "equity_pct"
    fixed_budget_krw: float = 0.0
    target_position_pct: float = 0.0
    available_cash_krw: float | None = None
    total_assets_krw: float | None = None
    configured_max_order_notional_krw: float = 0.0
    hard_max_order_notional_krw: float = 1_000_000.0
    base_order_cap_krw: float = 0.0
    effective_max_order_notional_krw: float = 0.0
    order_cap_source: str = "equity_pct"
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
