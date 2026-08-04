from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OperatorForcedOneShareBuyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    symbol: str = Field(min_length=1, max_length=20, examples=["005930"])
    operator: str = Field(min_length=1, max_length=80, examples=["operator"])
    confirm_live: bool = False
    confirmation: str = Field(min_length=1, max_length=300)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return str(value or "").strip().upper()

    @field_validator("operator", "confirmation")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        text = str(value or "").strip()
        return text

    @field_validator("reason")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        text = str(value or "").strip()
        return text or None


class OperatorForcedOneShareBuyResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    provider: str = "kis"
    market: str = "KR"
    mode: str
    source: str
    source_type: str
    result: str
    action: str
    reason: str | None = None
    primary_block_reason: str | None = None
    block_reasons: list[str] = Field(default_factory=list)
    forced_test_entry: bool = True
    operation_test: str = "test3"
    symbol: str | None = None
    qty: int = 1
    max_notional_krw: float
    real_order_submitted: bool = False
    broker_submit_called: bool = False
    manual_submit_called: bool = False
    validation_called: bool = False
    order_id: int | None = None
    broker_order_id: str | None = None
    kis_odno: str | None = None
    audit_metadata: dict[str, Any] = Field(default_factory=dict)


class OperationTest3PositionManagementRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    slot_label: str | None = Field(default=None, max_length=80)
    include_raw: bool = False

    @field_validator("slot_label")
    @classmethod
    def normalize_slot_label(cls, value: str | None) -> str | None:
        text = str(value or "").strip()
        return text or None


class OperationTest3EnableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    confirm_live: bool = False
    confirmation: str = Field(min_length=1, max_length=300)

    @field_validator("confirmation")
    @classmethod
    def normalize_confirmation(cls, value: str) -> str:
        return str(value or "").strip()


class OperationTest3MonitoringEnableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    confirmation: str = Field(min_length=1, max_length=300)

    @field_validator("confirmation")
    @classmethod
    def normalize_confirmation(cls, value: str) -> str:
        return str(value or "").strip()