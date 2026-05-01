from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from app.config import get_settings


class MarketCalendarError(ValueError):
    """Raised when market holiday calendar config is missing or invalid."""


class MarketCalendarService:
    """Local conservative exchange calendar.

    This config-backed service is intentionally small so an official calendar
    provider can be added later without changing session callers.
    """

    def __init__(self, config_path: str | None = None):
        settings = get_settings()
        self.config_path = config_path or settings.market_holidays_config_path
        self._root = Path(__file__).resolve().parents[2]

    def list_calendars(self) -> dict[str, dict[str, Any]]:
        payload = self._load_config()
        markets = payload.get("markets") or {}
        if not isinstance(markets, dict):
            return {}
        return {
            self._normalize_market(market): self.get_calendar(market)
            for market in sorted(markets)
        }

    def get_calendar(self, market: str) -> dict[str, Any]:
        payload = self._load_config()
        selected_market = self._normalize_market(market)
        markets = payload.get("markets") or {}
        if not isinstance(markets, dict) or selected_market not in markets:
            raise MarketCalendarError(f"Unknown market calendar: {selected_market}.")

        raw = markets[selected_market]
        if not isinstance(raw, dict):
            raise MarketCalendarError(f"Invalid market calendar: {selected_market}.")

        return {
            "market": selected_market,
            "timezone": str(raw.get("timezone") or "UTC"),
            "holidays": [
                self._normalize_holiday(item)
                for item in raw.get("holidays") or []
            ],
            "early_closes": [
                self._normalize_early_close(item)
                for item in raw.get("early_closes") or []
            ],
        }

    def get_holiday(self, market: str, value: datetime | date) -> dict[str, Any] | None:
        target_date = self._local_date(market, value)
        for holiday in self.get_calendar(market)["holidays"]:
            if holiday["date"] == target_date.isoformat() and holiday["full_day"]:
                return holiday
        return None

    def is_holiday(self, market: str, value: datetime | date) -> bool:
        return self.get_holiday(market, value) is not None

    def get_early_close(
        self,
        market: str,
        value: datetime | date,
    ) -> dict[str, Any] | None:
        target_date = self._local_date(market, value)
        for early_close in self.get_calendar(market)["early_closes"]:
            if early_close["date"] == target_date.isoformat():
                return early_close
        return None

    def is_early_close(self, market: str, value: datetime | date) -> bool:
        return self.get_early_close(market, value) is not None

    def get_close_time_for_date(
        self,
        market: str,
        value: datetime | date,
        default_close: str,
    ) -> str:
        early_close = self.get_early_close(market, value)
        if early_close and early_close.get("close"):
            return str(early_close["close"])
        return default_close

    def get_calendar_status(self, market: str, value: datetime | date) -> dict[str, Any]:
        holiday = self.get_holiday(market, value)
        early_close = self.get_early_close(market, value)
        return {
            "is_holiday": holiday is not None,
            "holiday_name": holiday.get("name") if holiday else None,
            "closure_reason": holiday.get("reason") if holiday else None,
            "is_early_close": early_close is not None,
            "early_close_name": early_close.get("name") if early_close else None,
            "early_close_reason": early_close.get("reason") if early_close else None,
            "early_close_time": early_close.get("close") if early_close else None,
        }

    def _load_config(self) -> dict[str, Any]:
        path = Path(self.config_path)
        if not path.is_absolute():
            path = self._root / path
        if not path.exists():
            raise MarketCalendarError(
                f"Market holiday config file not found: {self.config_path}."
            )
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise MarketCalendarError("Invalid market holiday YAML config.") from exc
        if not isinstance(payload, dict):
            raise MarketCalendarError("Market holiday config must be a mapping.")
        return payload

    def _local_date(self, market: str, value: datetime | date) -> date:
        if isinstance(value, datetime):
            timezone = ZoneInfo(self.get_calendar(market)["timezone"])
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone).date()
            return value.astimezone(timezone).date()
        return value

    @staticmethod
    def _normalize_holiday(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise MarketCalendarError("Holiday calendar entries must be mappings.")
        return {
            "date": str(raw.get("date") or ""),
            "name": str(raw.get("name") or ""),
            "reason": str(raw.get("reason") or "holiday"),
            "full_day": raw.get("full_day") is not False,
        }

    @staticmethod
    def _normalize_early_close(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise MarketCalendarError("Early close calendar entries must be mappings.")
        return {
            "date": str(raw.get("date") or ""),
            "name": str(raw.get("name") or ""),
            "reason": str(raw.get("reason") or "early_close"),
            "close": str(raw.get("close") or ""),
        }

    @staticmethod
    def _normalize_market(market: str | None) -> str:
        return str(market or "US").strip().upper()
