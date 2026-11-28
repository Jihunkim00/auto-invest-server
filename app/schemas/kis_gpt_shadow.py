from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class KisGptAnalysisSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    gpt_scoring_mode: Literal["legacy"] = "legacy"
    gpt_v2_shadow_enabled: bool = True
    gpt_short_horizon_minutes: int = Field(30, ge=1, le=119)
    gpt_long_horizon_minutes: int = Field(60, ge=2, le=120)
    gpt_event_lookahead_days: int = Field(7, ge=0, le=30)

    @model_validator(mode="after")
    def validate_horizon_order(self):
        if self.gpt_short_horizon_minutes >= self.gpt_long_horizon_minutes:
            raise ValueError("The short horizon must be shorter than the long horizon")
        return self
