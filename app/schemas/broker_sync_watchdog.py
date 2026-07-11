from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


BrokerSyncIssueType = Literal[
    "stale_local_order",
    "pending_sync_order",
    "missing_broker_order_id",
    "missing_kis_odno",
    "broker_order_missing_local_record",
    "local_order_missing_broker_record",
    "position_quantity_mismatch",
    "position_symbol_mismatch",
    "cash_snapshot_stale",
    "broker_read_failed",
    "sync_endpoint_failed",
    "ambiguous_order_state",
    "unknown",
]
BrokerSyncIssueSeverity = Literal["critical", "warning", "info"]
BrokerSyncHealth = Literal["healthy", "warning", "unsafe", "unknown"]
BrokerSyncRecommendedAction = Literal[
    "run_sync",
    "manual_review",
    "wait_for_broker",
    "inspect_broker_app",
    "disable_automation",
    "no_action",
]


class BrokerSyncWatchdogIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str
    issue_type: BrokerSyncIssueType
    severity: BrokerSyncIssueSeverity
    provider: str
    market: str
    symbol: str | None = None
    order_id: int | None = None
    broker_order_id: str | None = None
    kis_odno: str | None = None
    detected_at: str
    age_minutes: float | None = None
    local_status: str | None = None
    broker_status: str | None = None
    local_quantity: float | None = None
    broker_quantity: float | None = None
    automation_blocking: bool
    recommended_action: BrokerSyncRecommendedAction
    reason: str
    sanitized_context: dict[str, Any] = Field(default_factory=dict)


class BrokerSyncWatchdogStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: int | None = None
    generated_at: str
    provider: str = "kis"
    market: str = "KR"
    watchdog_enabled: bool = False
    automation_blocked_by_sync: bool = False
    sync_health: BrokerSyncHealth
    can_run_automation: bool = False
    should_block_auto_buy: bool = False
    should_block_auto_sell: bool = False
    should_block_orchestrator: bool = False
    local_order_count: int = 0
    open_local_order_count: int = 0
    broker_open_order_count: int = 0
    stale_local_order_count: int = 0
    pending_sync_order_count: int = 0
    missing_broker_id_count: int = 0
    missing_kis_odno_count: int = 0
    broker_unmatched_order_count: int = 0
    local_unmatched_order_count: int = 0
    stale_position_snapshot_count: int = 0
    position_mismatch_count: int = 0
    cash_snapshot_stale: bool = False
    last_successful_sync_at: str | None = None
    last_watchdog_run_at: str | None = None
    issues: list[BrokerSyncWatchdogIssue] = Field(default_factory=list)
    summary: str
    risk_flags: list[str] = Field(default_factory=list)
    gating_notes: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    next_safe_action: str
    safety_flags: dict[str, Any] = Field(default_factory=dict)
