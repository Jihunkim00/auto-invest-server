from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


AutomationSoakMode = Literal["dry_run_monitoring", "live_phase1_controlled"]
AutomationSoakTriggerSource = Literal["manual_soak_test", "scheduler_soak_test"]
AutomationSoakEffectiveStatus = Literal[
    "disabled",
    "monitoring",
    "dry_run_ready",
    "live_phase1_blocked",
    "live_phase1_ready",
    "kill_latched",
    "unsafe",
]
AutomationSoakRunResultStatus = Literal[
    "disabled",
    "kill_latched",
    "blocked",
    "dry_run_completed",
    "live_phase1_completed",
    "orchestrator_blocked",
    "orchestrator_action_taken",
    "error",
]
AutomationKillRuleSeverity = Literal["critical", "warning", "info"]
AutomationKillRuleSource = Literal[
    "watchdog",
    "orchestrator",
    "automation_mode",
    "readiness",
    "runtime_settings",
    "daily_pnl",
    "unknown",
]


class AutomationKillRuleResult(BaseModel):
    rule_id: str
    name: str
    severity: AutomationKillRuleSeverity
    triggered: bool
    automation_blocking: bool
    reason: str
    detected_at: str
    source: AutomationKillRuleSource
    recommended_action: str


class AutomationSoakRunOnceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "kis"
    market: str = "KR"
    mode: AutomationSoakMode | None = None
    trigger_source: AutomationSoakTriggerSource = "manual_soak_test"
    language: str | None = Field(default=None, max_length=20)
    locale: str | None = Field(default=None, max_length=20)
    operator_acknowledged_risks: bool = False

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        provider = str(value or "").strip().lower()
        if provider != "kis":
            raise ValueError("automation soak test supports provider=kis only.")
        return provider

    @field_validator("market")
    @classmethod
    def normalize_market(cls, value: str) -> str:
        market = str(value or "").strip().upper()
        if market != "KR":
            raise ValueError("automation soak test supports market=KR only.")
        return market


class AutomationSoakStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AutomationSoakMode = "dry_run_monitoring"
    allow_live_phase1: bool = False
    operator_acknowledged_risks: bool = False
    reason: str | None = Field(default=None, max_length=400)


class AutomationSoakStopRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=400)


class AutomationSoakResetKillLatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_acknowledged_risks: bool = False
    reason: str | None = Field(default=None, max_length=400)


class AutomationSoakStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    generated_at: str
    soak_enabled: bool = False
    soak_mode: AutomationSoakMode = "dry_run_monitoring"
    allow_live_phase1: bool = False
    kill_latch_active: bool = False
    kill_latch_reason: str | None = None
    kill_latch_triggered_at: str | None = None
    effective_status: AutomationSoakEffectiveStatus
    can_run_soak_cycle: bool = False
    can_attempt_live_phase1: bool = False
    can_submit_live_order: bool = False
    cycle_count_today: int = 0
    max_cycles_per_day: int = 3
    action_count_today: int = 0
    max_actions_per_day: int = 1
    consecutive_failure_count: int = 0
    max_consecutive_failures: int = 2
    latest_orchestrator_result: dict[str, Any] | None = None
    latest_watchdog_status: dict[str, Any] | None = None
    automation_mode_status: dict[str, Any] | None = None
    production_readiness_status: str = "unknown"
    daily_loss_status: str = "unknown"
    kill_rules: list[AutomationKillRuleResult] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    next_safe_action: str
    safety_flags: dict[str, Any] = Field(default_factory=dict)


class AutomationSoakRunResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: int | None = None
    generated_at: str
    provider: str = "kis"
    market: str = "KR"
    soak_mode: AutomationSoakMode
    trigger_source: AutomationSoakTriggerSource
    result_status: AutomationSoakRunResultStatus
    real_order_submitted: bool = False
    broker_submit_called: bool = False
    manual_submit_called: bool = False
    order_cancel_called: bool = False
    action_taken: str = "none"
    orchestrator_run_id: int | None = None
    broker_sync_health: str = "unknown"
    automation_mode_effective_status: str = "unknown"
    production_readiness_status: str = "unknown"
    kill_rules_evaluated: list[AutomationKillRuleResult] = Field(default_factory=list)
    kill_rules_triggered: list[AutomationKillRuleResult] = Field(default_factory=list)
    kill_latch_active: bool = False
    cycle_count_today: int = 0
    action_count_today: int = 0
    consecutive_failure_count: int = 0
    risk_flags: list[str] = Field(default_factory=list)
    gating_notes: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    next_safe_action: str
    safety_flags: dict[str, Any] = Field(default_factory=dict)

