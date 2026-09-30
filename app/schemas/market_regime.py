from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MarketRegimeCondition(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str
    label: str
    passed: bool
    actual: Any = None
    rule: str | None = None


class MarketRegimeTransitionGroup(BaseModel):
    model_config = ConfigDict(extra="allow")

    passed: int = 0
    total: int = 0
    eligible: bool = False
    conditions: list[MarketRegimeCondition] = Field(default_factory=list)


class MarketRegimeTransition(BaseModel):
    model_config = ConfigDict(extra="allow")

    passed: int = 0
    total: int = 0
    eligible: bool = False
    confirmed: bool = False
    streak: int = 0
    required_streak: int = 2
    conditions: list[MarketRegimeCondition] = Field(default_factory=list)
    kospi_transition: MarketRegimeTransitionGroup | None = None
    combined_transition: MarketRegimeTransitionGroup | None = None


class MarketRegimeResponse(BaseModel):
    status: Literal["confirmed", "pending", "insufficient_data"]
    stage: int | None = None
    stage_key: str | None = None
    stage_label: str | None = None
    short_label: str
    summary: str
    market_score: float | None = None
    score_change_3w: float | None = None
    kospi_score: float | None = None
    nasdaq_score: float | None = None
    kospi_week: str | None = None
    nasdaq_week: str | None = None
    confirmed: bool = False
    new_bullish_reversal: bool = False
    new_bearish_reversal: bool = False
    bullish_transition: MarketRegimeTransition = Field(default_factory=MarketRegimeTransition)
    bearish_transition: MarketRegimeTransition = Field(default_factory=MarketRegimeTransition)
    kospi: dict[str, Any] = Field(default_factory=dict)
    nasdaq: dict[str, Any] = Field(default_factory=dict)
    calculated_at: str | None = None
    next_scheduled_calculation: str
    data_source: dict[str, Any] = Field(default_factory=dict)
