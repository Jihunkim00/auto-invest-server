from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from app.services.market_calendar_service import MarketCalendarService


KST = ZoneInfo("Asia/Seoul")
WEEKEND_GAP_DAYS = 3
LONG_CLOSURE_GAP_DAYS = 4
WEEKEND_C_SCORE = 75.0
WEEKEND_FINAL_SCORE = 70.0
WEEKEND_POSITION_SIZE_MULTIPLIER = 0.5
WEEKEND_LATE_ENTRY_CUTOFF = "13:00"


class CalendarGapRiskService:
    """Apply conservative entry requirements before a configured market closure."""

    def __init__(self, market_calendar: MarketCalendarService | None = None) -> None:
        self.market_calendar = market_calendar or MarketCalendarService()

    def evaluate(
        self,
        market: str = "KR",
        *,
        now: datetime | None = None,
        existing_c_score: float | None = 70.0,
        existing_final_score: float = 65.0,
    ) -> dict[str, Any]:
        """Return deterministic calendar-gap gates and serializable diagnostics.

        Passing ``existing_c_score=None`` disables the C score gate, which is
        required for A_ONLY. The calendar service never invents a C score.
        """
        selected_market = str(market or "KR").strip().upper()
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=KST)

        try:
            calendar = self.market_calendar.get_calendar(selected_market)
            timezone = ZoneInfo(str(calendar["timezone"]))
            local_now = current.astimezone(timezone)
            trade_date = local_now.date()
            if not self.market_calendar.is_trading_day(selected_market, trade_date):
                raise ValueError("current_date_is_not_a_trading_day")
            next_date = self.market_calendar.next_trading_date(
                selected_market,
                trade_date,
            )
            gap_days = (next_date - trade_date).days
        except Exception as exc:
            try:
                local_trade_date = current.astimezone(KST).date().isoformat()
            except Exception:
                local_trade_date = None
            return self._unavailable(
                selected_market,
                trade_date=local_trade_date,
                existing_c_score=existing_c_score,
                existing_final_score=existing_final_score,
                error_type=type(exc).__name__,
            )

        closure_risk = gap_days >= WEEKEND_GAP_DAYS
        long_closure = gap_days >= LONG_CLOSURE_GAP_DAYS
        is_weekend_gap = gap_days == WEEKEND_GAP_DAYS
        required_c = existing_c_score
        required_final = float(existing_final_score)
        multiplier = 1.0
        cutoff = None
        flags: list[str] = []
        notes: list[str] = []
        blocked_reason = None

        if closure_risk:
            if required_c is not None:
                required_c = max(float(required_c), WEEKEND_C_SCORE)
            required_final = max(required_final, WEEKEND_FINAL_SCORE)
            multiplier = WEEKEND_POSITION_SIZE_MULTIPLIER
            cutoff = WEEKEND_LATE_ENTRY_CUTOFF

        if long_closure:
            blocked_reason = "long_market_closure_ahead"
            flags.append("long_market_closure_ahead")
            notes.append("long_market_closure_ahead")
        elif is_weekend_gap:
            flags.append("weekend_gap_risk")
            notes.extend(
                [
                    "weekend_gap_risk",
                    f"calendar_gap_required_final_score:{required_final:.1f}",
                    f"calendar_gap_position_size_multiplier:{multiplier:.1f}",
                    f"calendar_gap_late_entry_cutoff:{cutoff}",
                ]
            )
            if required_c is not None:
                notes.append(f"calendar_gap_required_c_score:{required_c:.1f}")
            if local_now.time().replace(tzinfo=None) >= time(13, 0):
                blocked_reason = "weekend_gap_late_entry_block"
                notes.append(blocked_reason)
        else:
            notes.append("calendar_gap_entry_requirement_unchanged")

        result = {
            "market": selected_market,
            "trade_date": trade_date.isoformat(),
            "next_trading_date": next_date.isoformat(),
            "calendar_gap_days": gap_days,
            "pre_market_closure_risk": closure_risk,
            "long_market_closure_ahead": long_closure,
            "required_c_score": required_c,
            "required_final_score": required_final,
            "position_size_multiplier": multiplier,
            "late_entry_cutoff_local": cutoff,
            "entry_blocked": blocked_reason is not None,
            "block_reason": blocked_reason,
            "risk_flags": flags,
            "gating_notes": notes,
        }
        return self._with_public_fields(result)

    def _unavailable(
        self,
        market: str,
        *,
        trade_date: str | None,
        existing_c_score: float | None,
        existing_final_score: float,
        error_type: str,
    ) -> dict[str, Any]:
        return self._with_public_fields(
            {
                "market": market,
                "trade_date": trade_date,
                "next_trading_date": None,
                "calendar_gap_days": None,
                "pre_market_closure_risk": False,
                "long_market_closure_ahead": False,
                "required_c_score": existing_c_score,
                "required_final_score": float(existing_final_score),
                "position_size_multiplier": 1.0,
                "late_entry_cutoff_local": None,
                "entry_blocked": True,
                "block_reason": "calendar_gap_risk_unavailable",
                "risk_flags": ["calendar_gap_risk_unavailable"],
                "gating_notes": [
                    f"calendar_gap_risk_unavailable:{str(error_type)[:80]}"
                ],
            }
        )

    @staticmethod
    def _with_public_fields(result: dict[str, Any]) -> dict[str, Any]:
        """Include the stable field names requested by scheduler responses."""
        result.update(
            {
                "calendar_gap_days": result.get("calendar_gap_days"),
                "trade_date": result.get("trade_date"),
                "next_trading_date": result.get("next_trading_date"),
                "pre_market_closure_risk": result.get("pre_market_closure_risk"),
                "long_market_closure_ahead": result.get("long_market_closure_ahead"),
                "calendar_gap_required_c_score": result.get("required_c_score"),
                "calendar_gap_required_final_score": result.get("required_final_score"),
                "calendar_gap_position_size_multiplier": result.get(
                    "position_size_multiplier"
                ),
                "calendar_gap_late_entry_cutoff": result.get(
                    "late_entry_cutoff_local"
                ),
                "calendar_gap_block_reason": result.get("block_reason"),
                "calendar_gap_risk_flags": list(result.get("risk_flags") or []),
                "calendar_gap_gating_notes": list(result.get("gating_notes") or []),
            }
        )
        return result
