from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


OperationMode = Literal["paper", "live", "paused"]
OperationModeStatus = Literal["active", "blocked", "unchanged", "error"]
OperationModeSafetyStatus = Literal["ready", "blocked", "paper", "paused"]


class OperationModeBlockingReason(BaseModel):
    code: str
    message: str


class OperationModeChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: OperationMode
    acknowledged: bool = False
    reason: str | None = Field(default=None, max_length=400)
    provider: str | None = Field(default=None, max_length=20)
    market: str | None = Field(default=None, max_length=10)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        text = str(value or "").strip()
        return text or None

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str | None) -> str | None:
        text = str(value or "").strip().lower()
        return text or None

    @field_validator("market")
    @classmethod
    def normalize_market(cls, value: str | None) -> str | None:
        text = str(value or "").strip().upper()
        return text or None


class OperationModeStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    requested_mode: OperationMode
    effective_mode: OperationMode
    display_label: str
    status: OperationModeStatus
    safety_status: OperationModeSafetyStatus
    can_change_mode: bool = True
    can_enter_paper: bool = True
    can_enter_live: bool = False
    can_enter_paused: bool = True
    requires_acknowledgement: dict[str, bool] = Field(default_factory=dict)
    mode_drift_detected: bool = False
    blocking_reasons: list[OperationModeBlockingReason] = Field(default_factory=list)
    warnings: list[OperationModeBlockingReason] = Field(default_factory=list)
    underlying_state: dict[str, Any] = Field(default_factory=dict)
    last_changed_at: str | None = None
    last_changed_by: str | None = None


class OperationModeChangeResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    changed: bool
    previous_mode: OperationMode
    requested_mode: OperationMode
    effective_mode: OperationMode
    status: OperationModeStatus
    safety_status: OperationModeSafetyStatus
    display_label: str
    message: str
    blocking_reasons: list[OperationModeBlockingReason] = Field(default_factory=list)
    warnings: list[OperationModeBlockingReason] = Field(default_factory=list)
    audit_id: int | None = None
    changed_at: str | None = None
    underlying_state: dict[str, Any] = Field(default_factory=dict)
