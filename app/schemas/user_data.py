from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AdminUserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)


class AdminUserStatusRequest(BaseModel):
    enabled: bool | None = None
    is_active: bool | None = None

    @property
    def requested_enabled(self) -> bool:
        return bool(self.enabled if self.enabled is not None else self.is_active)


class UserSettingsUpdateRequest(BaseModel):
    settings: dict[str, Any] | None = None
    settings_json: dict[str, Any] | None = None

    model_config = {'extra': 'allow'}

    def values(self) -> dict[str, Any]:
        if self.settings is not None:
            return dict(self.settings)
        if self.settings_json is not None:
            return dict(self.settings_json)
        values = self.model_dump(exclude_none=True)
        values.pop('settings', None)
        values.pop('settings_json', None)
        return values


class UserWatchlistCreateRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    provider: str = Field(default='kis', min_length=1, max_length=20)
    market: str = Field(default='KR', min_length=1, max_length=10)


class UserTradingSettingsUpdateRequest(BaseModel):
    '''Safe user trading mode and risk-limit changes for PR127.'''

    trading_mode: Literal['paper', 'live'] | None = None
    live_trading_enabled: bool | None = None
    kill_switch: bool | None = None

    max_daily_trades: int | None = Field(default=None, ge=0, le=100)
    max_daily_loss_pct: float | None = Field(default=None, ge=0, le=1)
    max_position_pct: float | None = Field(default=None, ge=0, le=100)
    max_open_positions: int | None = Field(default=None, ge=0, le=100)

    model_config = {'extra': 'forbid'}

    def values(self) -> dict[str, object]:
        return self.model_dump(exclude_none=True)
