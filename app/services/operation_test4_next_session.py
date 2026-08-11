from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

KR_TZ = ZoneInfo("Asia/Seoul")
ENTRY_SLOTS = ("09:35", "11:30", "13:30")


def next_valid_kr_trading_date(
    now: datetime,
    *,
    calendar_service: Any,
) -> date:
    local = now.astimezone(KR_TZ)
    candidate = local.date() + timedelta(days=1)
    while candidate.weekday() >= 5 or calendar_service.is_holiday("KR", candidate):
        candidate += timedelta(days=1)
    return candidate


def next_entry_slot_for_session(
    now: datetime,
    *,
    target_trading_date: date | None,
    enabled: bool,
    entry_slots: tuple[str, ...] = ENTRY_SLOTS,
) -> dict[str, str | None]:
    if not enabled or target_trading_date is None:
        return {
            "next_entry_slot_kst": None,
            "next_automatic_entry_run": None,
        }

    local = now.astimezone(KR_TZ)
    for slot in entry_slots:
        hour, minute = (int(part) for part in slot.split(":"))
        if target_trading_date > local.date() or (
            target_trading_date == local.date()
            and (local.hour, local.minute) < (hour, minute)
        ):
            run_at = datetime(
                target_trading_date.year,
                target_trading_date.month,
                target_trading_date.day,
                hour,
                minute,
                tzinfo=KR_TZ,
            )
            return {
                "next_entry_slot_kst": slot,
                "next_automatic_entry_run": run_at.isoformat(),
            }
    return {
        "next_entry_slot_kst": None,
        "next_automatic_entry_run": None,
    }


def is_entry_slot(slot_label: str, *, entry_slots: tuple[str, ...] = ENTRY_SLOTS) -> bool:
    return str(slot_label or "") in entry_slots


def is_last_entry_slot(
    slot_label: str,
    *,
    entry_slots: tuple[str, ...] = ENTRY_SLOTS,
) -> bool:
    return bool(entry_slots) and str(slot_label or "") == entry_slots[-1]


def parse_trading_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or ""))
    except (TypeError, ValueError):
        return None


def slot_time(slot_label: str) -> time | None:
    try:
        hour, minute = (int(part) for part in str(slot_label).split(":"))
        return time(hour=hour, minute=minute)
    except (TypeError, ValueError):
        return None