from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


AutomationMode = Literal[
    "off",
    "monitor_only",
    "dry_run_auto",
    "phase1_live_ready",
]

AutomationEffectiveStatus = Literal[
    "off",
    "monitoring",
    "dry_run_ready",
    "live_ready_blocked",
    "live_ready",
    "blocked",
]


class AutomationModeSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    automation_mode: AutomationMode
    reason: str | None = Field(default=None, max_length=400)
    operator_acknowledged_risks: bool = False
    language: str | None = Field(default=None, max_length=20)
    locale: str | None = Field(default=None, max_length=20)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        text = str(value or "").strip()
        return text or None


class AutomationModeOffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=400)
    language: str | None = Field(default=None, max_length=20)
    locale: str | None = Field(default=None, max_length=20)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        text = str(value or "").strip()
        return text or None


class AutomationModeStatusResponse(BaseModel):
    generated_at: str
    automation_mode: AutomationMode
    mode_label: str
    mode_description: str
    mode_updated_at: str | None = None
    mode_updated_by: str | None = None
    mode_reason: str | None = None
    mode_requires_manual_review: bool = True
    effective_status: AutomationEffectiveStatus
    can_run_monitoring: bool
    can_run_dry_run: bool
    can_attempt_phase1_live: bool
    can_submit_live_order: bool
    kill_switch: bool
    dry_run: bool
    kis_enabled: bool
    kis_real_order_enabled: bool
    production_readiness_status: str
    portfolio_orchestrator_enabled: bool
    portfolio_orchestrator_allow_live_orders: bool
    position_management_scheduler_enabled: bool
    auto_buy_live_phase1_enabled: bool
    auto_sell_live_phase1_enabled: bool
    scheduler_enabled: bool
    pending_order_blockers: list[dict[str, Any]] = Field(default_factory=list)
    sync_required_count: int = 0
    critical_exit_candidate_count: int = 0
    daily_trade_limit_remaining: int = 0
    blocking_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    next_safe_action: str
    safety_flags: dict[str, Any] = Field(default_factory=dict)
    modules: dict[str, Any] = Field(default_factory=dict)

