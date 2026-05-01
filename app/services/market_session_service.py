from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from app.config import get_settings
from app.services.market_calendar_service import (
    MarketCalendarError,
    MarketCalendarService,
)


class MarketSessionError(ValueError):
    """Raised when market session config is missing or invalid."""


@dataclass(frozen=True)
class MarketEntrySlot:
    name: str
    time: str


@dataclass(frozen=True)
class MarketSession:
    market: str
    timezone: str
    regular_open: str
    regular_close: str
    entry_slots: list[MarketEntrySlot]
    no_new_entry_after: str
    avoid_open_minutes: int
    avoid_close_minutes: int
    enabled_for_scheduler: bool
    force_manage_until: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entry_slots"] = [asdict(slot) for slot in self.entry_slots]
        return payload


class MarketSessionService:
    def __init__(
        self,
        config_path: str | None = None,
        *,
        calendar_service: MarketCalendarService | None = None,
    ):
        settings = get_settings()
        self.config_path = config_path or settings.market_sessions_config_path
        self._root = Path(__file__).resolve().parents[2]
        self.calendar_service = calendar_service or MarketCalendarService()

    def list_sessions(self) -> list[dict[str, Any]]:
        payload = self._load_config()
        markets = payload.get("markets") or {}
        if not isinstance(markets, dict):
            return []
        return [
            self._session_from_config(market, raw).to_dict()
            for market, raw in sorted(markets.items())
        ]

    def get_session(self, market: str | None = None) -> MarketSession:
        payload = self._load_config()
        selected_market = self._normalize_market(
            market or payload.get("default_market") or "US"
        )
        markets = payload.get("markets") or {}
        if not isinstance(markets, dict) or selected_market not in markets:
            raise MarketSessionError(f"Unknown market session: {selected_market}.")
        return self._session_from_config(selected_market, markets[selected_market])

    def get_default_session(self) -> MarketSession:
        return self.get_session(None)

    def get_timezone(self, market: str | None = None) -> str:
        return self.get_session(market).timezone

    def get_entry_slots(self, market: str | None = None) -> list[dict[str, str]]:
        return [asdict(slot) for slot in self.get_session(market).entry_slots]

    def is_market_open(self, market: str, now: datetime | None = None) -> bool:
        session = self.get_session(market)
        local_now = self._local_now(session, now)
        if self._calendar_status(session, local_now)["is_holiday"]:
            return False
        current = local_now.time()
        effective_close = self._effective_close(session, local_now)
        return self._parse_time(session.regular_open) <= current <= effective_close

    def is_entry_allowed_now(
        self,
        market: str,
        now: datetime | None = None,
    ) -> bool:
        session = self.get_session(market)
        local_now = self._local_now(session, now)
        current = local_now.time()
        return (
            self.is_market_open(market, local_now)
            and current < self._parse_time(session.no_new_entry_after)
        )

    def is_near_close(self, market: str, now: datetime | None = None) -> bool:
        session = self.get_session(market)
        local_now = self._local_now(session, now)
        if self._calendar_status(session, local_now)["is_holiday"]:
            return False
        current = local_now.time()
        close_start = self._minutes_before(
            self._effective_close(session, local_now),
            session.avoid_close_minutes,
        )
        return close_start <= current <= self._effective_close(session, local_now)

    def get_next_entry_slots(
        self,
        market: str,
        now: datetime | None = None,
    ) -> list[dict[str, str]]:
        session = self.get_session(market)
        local_now = self._local_now(session, now)
        current = local_now.time()
        upcoming = []
        for slot in session.entry_slots:
            if self._parse_time(slot.time) >= current:
                upcoming.append(asdict(slot))
        return upcoming

    def get_session_status(
        self,
        market: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        session = self.get_session(market)
        local_now = self._local_now(session, now)
        calendar_status = self._calendar_status(session, local_now)
        effective_close = self._effective_close(session, local_now).strftime("%H:%M")
        is_market_open = self.is_market_open(session.market, local_now)
        closure_reason = None
        closure_name = None

        if calendar_status["is_holiday"]:
            closure_reason = calendar_status["closure_reason"]
            closure_name = calendar_status["holiday_name"]
        elif not is_market_open:
            current = local_now.time()
            close_time = self._parse_time(effective_close)
            if calendar_status["is_early_close"] and current > close_time:
                closure_reason = calendar_status["early_close_reason"]
                closure_name = calendar_status["early_close_name"]
            else:
                closure_reason = "outside_regular_hours"

        return {
            "market": session.market,
            "timezone": session.timezone,
            "is_market_open": is_market_open,
            "is_entry_allowed_now": self.is_entry_allowed_now(
                session.market,
                local_now,
            ),
            "is_near_close": self.is_near_close(session.market, local_now),
            "closure_reason": closure_reason,
            "closure_name": closure_name,
            "regular_open": session.regular_open,
            "regular_close": session.regular_close,
            "effective_close": effective_close,
            "no_new_entry_after": session.no_new_entry_after,
            "is_holiday": calendar_status["is_holiday"],
            "is_early_close": calendar_status["is_early_close"],
            "early_close_name": calendar_status["early_close_name"],
            "early_close_reason": calendar_status["early_close_reason"],
            "local_time": local_now.isoformat(),
            "enabled_for_scheduler": session.enabled_for_scheduler,
        }

    def get_status(self, market: str, now: datetime | None = None) -> dict[str, Any]:
        return self.get_session_status(market, now)

    def get_default_market_key(self) -> str:
        payload = self._load_config()
        return self._normalize_market(payload.get("default_market") or "US")

    def _load_config(self) -> dict[str, Any]:
        path = Path(self.config_path)
        if not path.is_absolute():
            path = self._root / path
        if not path.exists():
            raise MarketSessionError(
                f"Market session config file not found: {self.config_path}."
            )
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise MarketSessionError("Invalid market session YAML config.") from exc
        if not isinstance(payload, dict):
            raise MarketSessionError("Market session config must be a mapping.")
        return payload

    def _session_from_config(self, market: str, raw: Any) -> MarketSession:
        if not isinstance(raw, dict):
            raise MarketSessionError(f"Invalid market session: {market}.")
        required = [
            "timezone",
            "regular_open",
            "regular_close",
            "entry_slots",
            "no_new_entry_after",
            "avoid_open_minutes",
            "avoid_close_minutes",
            "enabled_for_scheduler",
        ]
        missing = [key for key in required if key not in raw]
        if missing:
            raise MarketSessionError(
                f"Market session {market} is missing: {', '.join(missing)}."
            )
        raw_slots = raw.get("entry_slots")
        if not isinstance(raw_slots, list):
            raise MarketSessionError(
                f"Market session {market} entry_slots must be a list."
            )
        slots = []
        for raw_slot in raw_slots:
            if (
                not isinstance(raw_slot, dict)
                or not raw_slot.get("name")
                or not raw_slot.get("time")
            ):
                raise MarketSessionError(
                    f"Market session {market} has invalid entry slot."
                )
            slots.append(
                MarketEntrySlot(name=str(raw_slot["name"]), time=str(raw_slot["time"]))
            )

        return MarketSession(
            market=self._normalize_market(market),
            timezone=str(raw["timezone"]),
            regular_open=str(raw["regular_open"]),
            regular_close=str(raw["regular_close"]),
            entry_slots=slots,
            no_new_entry_after=str(raw["no_new_entry_after"]),
            force_manage_until=(
                str(raw["force_manage_until"])
                if raw.get("force_manage_until")
                else None
            ),
            avoid_open_minutes=int(raw["avoid_open_minutes"]),
            avoid_close_minutes=int(raw["avoid_close_minutes"]),
            enabled_for_scheduler=bool(raw["enabled_for_scheduler"]),
        )

    def _local_now(self, session: MarketSession, now: datetime | None) -> datetime:
        timezone = ZoneInfo(session.timezone)
        if now is None:
            return datetime.now(timezone)
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone)
        return now.astimezone(timezone)

    def _calendar_status(
        self,
        session: MarketSession,
        local_now: datetime,
    ) -> dict[str, Any]:
        try:
            return self.calendar_service.get_calendar_status(session.market, local_now)
        except MarketCalendarError:
            return {
                "is_holiday": False,
                "holiday_name": None,
                "closure_reason": None,
                "is_early_close": False,
                "early_close_name": None,
                "early_close_reason": None,
                "early_close_time": None,
            }

    def _effective_close(self, session: MarketSession, local_now: datetime) -> time:
        try:
            close_text = self.calendar_service.get_close_time_for_date(
                session.market,
                local_now,
                session.regular_close,
            )
        except MarketCalendarError:
            close_text = session.regular_close
        return self._parse_time(close_text)

    @staticmethod
    def _parse_time(value: str) -> time:
        try:
            hour_text, minute_text = str(value).split(":", 1)
            return time(hour=int(hour_text), minute=int(minute_text))
        except (TypeError, ValueError) as exc:
            raise MarketSessionError(f"Invalid market session time: {value}.") from exc

    @staticmethod
    def _minutes_before(value: time, minutes: int) -> time:
        total = value.hour * 60 + value.minute - minutes
        total = max(total, 0)
        return time(hour=total // 60, minute=total % 60)

    @staticmethod
    def _normalize_market(market: str | None) -> str:
        return str(market or "US").strip().upper()
