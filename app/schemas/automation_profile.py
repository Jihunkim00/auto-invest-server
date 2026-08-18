from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AutomationProfileWriteRequest(BaseModel):
    model_config = ConfigDict(extra='allow')

    profile_key: str | None = Field(default=None, min_length=2, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    provider: str | None = Field(default=None, max_length=20)
    market: str | None = Field(default=None, max_length=10)
    enabled: bool | None = None
    status: str | None = Field(default=None, max_length=20)
    capital: dict[str, Any] = Field(default_factory=dict)
    universe: dict[str, Any] = Field(default_factory=dict)
    entry: dict[str, Any] = Field(default_factory=dict)
    monitoring: dict[str, Any] = Field(default_factory=dict)
    exit: dict[str, Any] = Field(default_factory=dict)
    operation: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)


class AutomationProfileActionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    confirm_operator_ack: bool = False


class AutomationProfileSizingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    equity: float = Field(default=0, ge=0)
    orderable_cash: float = Field(default=0, ge=0)
    current_position_value: float = Field(default=0, ge=0)
    current_total_exposure: float = Field(default=0, ge=0)
    current_price: float = Field(default=0, ge=0)

