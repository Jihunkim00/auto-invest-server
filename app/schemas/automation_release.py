from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


AutomationReleaseMode = Literal["controlled_phase1"]
AutomationReleaseEffectiveStatus = Literal[
    "disabled",
    "preflight_required",
    "monitoring_ready",
    "dry_run_ready",
    "live_ready_blocked",
    "live_ready",
    "kill_latched",
    "unsafe",
]
AutomationReleaseCycleMode = Literal["monitoring", "dry_run", "live_phase1"]
AutomationReleaseTriggerSource = Literal[
    "manual_release_cycle",
    "scheduler_release_cycle",
]
AutomationReleaseCycleResultStatus = Literal[
    "disabled",
    "blocked",
    "monitoring_completed",
    "dry_run_completed",
    "live_phase1_completed",
    "live_order_submitted",
    "no_action",
    "kill_latched",
    "error",
]


class AutomationReleaseChecklistItem(BaseModel):
    key: str
    label: str
    passed: bool
    severity: Literal["critical", "warning", "info"] = "critical"
    reason: str | None = None
    blocking: bool = True
    next_action: str


class AutomationReleaseArmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_acknowledged_risks: bool = False
    reason: str | None = Field(default=None, max_length=400)
    release_mode: AutomationReleaseMode = "controlled_phase1"
    language: str | None = Field(default=None, max_length=20)
    locale: str | None = Field(default=None, max_length=20)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        text = str(value or "").strip()
        return text or None


class AutomationReleaseDisarmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=400)
    language: str | None = Field(default=None, max_length=20)
    locale: str | None = Field(default=None, max_length=20)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        text = str(value or "").strip()
        return text or None


class AutomationReleaseRunCycleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AutomationReleaseCycleMode = "monitoring"
    operator_acknowledged_risks: bool = False
    trigger_source: AutomationReleaseTriggerSource = "manual_release_cycle"
    provider: str = "kis"
    market: str = "KR"
    language: str | None = Field(default=None, max_length=20)
    locale: str | None = Field(default=None, max_length=20)

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        provider = str(value or "").strip().lower()
        if provider != "kis":
            raise ValueError("automation release supports provider=kis only.")
        return provider

    @field_validator("market")
    @classmethod
    def normalize_market(cls, value: str) -> str:
        market = str(value or "").strip().upper()
        if market != "KR":
            raise ValueError("automation release supports market=KR only.")
        return market


class AutomationReleaseStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    generated_at: str
    release_enabled: bool = False
    release_mode: AutomationReleaseMode = "controlled_phase1"
    release_armed: bool = False
    release_armed_at: str | None = None
    release_reason: str | None = None
    effective_status: AutomationReleaseEffectiveStatus
    can_run_monitoring_cycle: bool = False
    can_run_dry_run_cycle: bool = False
    can_run_live_phase1_cycle: bool = False
    can_submit_live_order: bool = False
    automation_mode_status: dict[str, Any] = Field(default_factory=dict)
    broker_sync_status: dict[str, Any] = Field(default_factory=dict)
    soak_status: dict[str, Any] = Field(default_factory=dict)
    kill_latch_active: bool = False
    production_readiness_status: str = "unknown"
    orchestrator_status: dict[str, Any] = Field(default_factory=dict)
    auto_buy_phase1_status: dict[str, Any] = Field(default_factory=dict)
    auto_sell_phase1_status: dict[str, Any] = Field(default_factory=dict)
    daily_trade_limit_remaining: int = 0
    daily_auto_buy_remaining: int = 0
    daily_auto_sell_remaining: int = 0
    blocking_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    checklist: list[AutomationReleaseChecklistItem] = Field(default_factory=list)
    safety_flags: dict[str, Any] = Field(default_factory=dict)
    next_safe_action: str


class AutomationReleaseCycleResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: int | None = None
    generated_at: str
    release_enabled: bool = False
    release_mode: AutomationReleaseMode = "controlled_phase1"
    cycle_mode: AutomationReleaseCycleMode
    result_status: AutomationReleaseCycleResultStatus
    real_order_submitted: bool = False
    broker_submit_called: bool = False
    manual_submit_called: bool = False
    order_cancel_called: bool = False
    action_taken: str = "none"
    orchestrator_run_id: int | None = None
    soak_run_id: int | None = None
    checklist: list[AutomationReleaseChecklistItem] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    gating_notes: list[str] = Field(default_factory=list)
    next_safe_action: str
    safety_flags: dict[str, Any] = Field(default_factory=dict)
