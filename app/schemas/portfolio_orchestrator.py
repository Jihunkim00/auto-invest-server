from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PortfolioOrchestratorTriggerSource = Literal[
    "manual_orchestrator_test",
    "scheduler_orchestrator",
]
PortfolioOrchestratorMode = Literal[
    "dry_run_monitoring",
    "live_phase1_controlled",
]
PortfolioOrchestratorResultStatus = Literal[
    "disabled",
    "blocked",
    "completed_no_action",
    "sell_submitted",
    "buy_submitted",
    "dry_run_completed",
    "error",
]
PortfolioOrchestratorAction = Literal[
    "none",
    "auto_sell_phase1",
    "auto_buy_phase1",
]


class PortfolioOrchestratorRunRequest(BaseModel):
    """A deliberately narrow request for one controlled portfolio cycle."""

    model_config = ConfigDict(extra="forbid")

    provider: str = "kis"
    market: str = "KR"
    trigger_source: PortfolioOrchestratorTriggerSource = "manual_orchestrator_test"
    mode: PortfolioOrchestratorMode = "dry_run_monitoring"
    language: str | None = Field(default=None, max_length=20)
    locale: str | None = Field(default=None, max_length=20)

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        provider = str(value or "").strip().lower()
        if provider != "kis":
            raise ValueError("portfolio orchestrator supports provider=kis only.")
        return provider

    @field_validator("market")
    @classmethod
    def normalize_market(cls, value: str) -> str:
        market = str(value or "").strip().upper()
        if market != "KR":
            raise ValueError("portfolio orchestrator supports market=KR only.")
        return market


class PortfolioOrchestratorResponse(BaseModel):
    run_id: int | None = None
    generated_at: str
    provider: str = "kis"
    market: str = "KR"
    trigger_source: str
    orchestrator_enabled: bool = False
    allow_live_orders: bool = False
    mode: PortfolioOrchestratorMode
    positions_first: bool = True
    max_actions_per_run: int = 1
    result_status: PortfolioOrchestratorResultStatus
    real_order_submitted: bool = False
    broker_submit_called: bool = False
    manual_submit_called: bool = False
    action_taken: PortfolioOrchestratorAction = "none"
    position_management_result: dict[str, Any] | None = None
    auto_sell_phase1_result: dict[str, Any] | None = None
    auto_buy_phase1_result: dict[str, Any] | None = None
    skipped_buy_reason: str | None = None
    skipped_sell_reason: str | None = None
    daily_trade_limit_used: int = 0
    daily_trade_limit_remaining: int = 0
    sync_required_count: int = 0
    critical_exit_candidate_count: int = 0
    pending_order_conflict_count: int = 0
    broker_sync_health: str = "unknown"
    broker_sync_blocking_reasons: list[str] = Field(default_factory=list)
    broker_sync_issue_count: int = 0
    broker_sync_watchdog: dict[str, Any] | None = None
    production_readiness_status: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    gating_notes: list[str] = Field(default_factory=list)
    checklist: list[dict[str, Any]] = Field(default_factory=list)
    primary_block_reason: str | None = None
    next_safe_action: str
    selected_symbol: str | None = None
    selected_candidate_id: str | None = None
    selected_promotion_id: int | None = None
    order_id: int | None = None
    broker_order_id: str | None = None
    kis_odno: str | None = None
    soak_kill_latch_active: bool = False
    soak_kill_latch_reason: str | None = None
    kill_rules_triggered: list[str] = Field(default_factory=list)
    safety: dict[str, Any] = Field(default_factory=dict)
