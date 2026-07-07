from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PositionManagementResultStatus = Literal["completed", "skipped", "blocked", "error"]


class PositionManagementDryRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "kis"
    market: str = "KR"
    symbol: str | None = None
    trigger_source: str = Field(
        default="manual_position_management_dry_run",
        max_length=80,
    )
    scheduler_slot: str | None = Field(default=None, max_length=80)
    include_sell_preflight: bool = True

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        provider = str(value or "").strip().lower()
        if provider != "kis":
            raise ValueError("position management dry-run supports provider=kis only.")
        return provider

    @field_validator("market")
    @classmethod
    def normalize_market(cls, value: str) -> str:
        market = str(value or "").strip().upper()
        if market != "KR":
            raise ValueError("position management dry-run supports market=KR only.")
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


class PositionManagementDryRunResponse(BaseModel):
    run_id: int | None = None
    generated_at: str
    provider: str = "kis"
    market: str = "KR"
    trigger_source: str
    dry_run_only: bool = True
    real_order_submitted: bool = False
    broker_submit_called: bool = False
    manual_submit_called: bool = False
    positions_checked: int = 0
    exit_candidate_count: int = 0
    critical_candidate_count: int = 0
    warning_candidate_count: int = 0
    simulated_sell_preflight_count: int = 0
    blocked_preflight_count: int = 0
    sync_required_count: int = 0
    duplicate_sell_conflict_count: int = 0
    result_status: PositionManagementResultStatus
    primary_reason: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    gating_notes: list[str] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    sell_preflight_results: list[dict[str, Any]] = Field(default_factory=list)
    next_safe_actions: list[str] = Field(default_factory=list)
    priority: str = "positions_first"
    entry_orders_allowed: bool = False
    exit_orders_allowed: bool = False
    dry_run_monitoring_only: bool = True
    scheduler_enabled: bool = False
    scheduler_dry_run_only: bool = True
    scheduler_allow_live_orders: bool = False
    safety: dict[str, Any] = Field(default_factory=dict)
