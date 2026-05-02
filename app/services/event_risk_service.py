from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import CompanyEvent

EVENT_RISK_TYPES = ("earnings", "earnings_call")


class EventRiskService:
    def get_event_risk(
        self,
        db: Session,
        *,
        symbol: str,
        market: str,
        as_of_date: date | None = None,
        intent: str = "entry",
    ) -> dict[str, Any]:
        normalized_symbol = _normalize_symbol(symbol, market)
        normalized_market = str(market or "").strip().upper()
        current_date = as_of_date or datetime.now(UTC).date()
        normalized_intent = str(intent or "entry").strip().lower()

        try:
            event = self._nearest_event(
                db,
                symbol=normalized_symbol,
                market=normalized_market,
                as_of_date=current_date,
            )
        except Exception:
            return self._empty_response(
                symbol=normalized_symbol,
                market=normalized_market,
                warnings=["event_data_unavailable"],
            )

        if event is None:
            return self._empty_response(symbol=normalized_symbol, market=normalized_market)

        days_to_event = (event.event_date - current_date).days
        risk = self._policy(
            days_to_event=days_to_event,
            intent=normalized_intent,
            event_type=str(event.event_type or "unknown"),
        )
        has_near_event = -1 <= days_to_event <= 2

        return {
            "symbol": normalized_symbol,
            "market": normalized_market,
            "has_near_event": has_near_event,
            "event_type": event.event_type,
            "event_date": event.event_date.isoformat(),
            "event_time_label": event.event_time_label or "unknown",
            "days_to_event": days_to_event,
            "risk_level": risk["risk_level"],
            "entry_blocked": risk["entry_blocked"],
            "scale_in_blocked": risk["scale_in_blocked"],
            "position_size_multiplier": risk["position_size_multiplier"],
            "force_gate_level": risk["force_gate_level"],
            "reason": risk["reason"],
            "source": event.provider,
            "company_name": event.company_name,
            "title": event.title,
            "warnings": [],
        }

    def _nearest_event(
        self,
        db: Session,
        *,
        symbol: str,
        market: str,
        as_of_date: date,
    ) -> CompanyEvent | None:
        candidates = (
            db.query(CompanyEvent)
            .filter(CompanyEvent.market == market)
            .filter(CompanyEvent.symbol == symbol)
            .filter(CompanyEvent.event_type.in_(EVENT_RISK_TYPES))
            .filter(CompanyEvent.event_date >= date.fromordinal(as_of_date.toordinal() - 1))
            .filter(CompanyEvent.event_date <= date.fromordinal(as_of_date.toordinal() + 30))
            .all()
        )
        if not candidates:
            return None
        return sorted(
            candidates,
            key=lambda item: (abs((item.event_date - as_of_date).days), item.event_date),
        )[0]

    @staticmethod
    def _policy(*, days_to_event: int, intent: str, event_type: str) -> dict[str, Any]:
        exit_intent = intent in {"exit", "sell", "position_management"}
        if exit_intent:
            return {
                "risk_level": "medium" if -1 <= days_to_event <= 2 else "low",
                "entry_blocked": False,
                "scale_in_blocked": False,
                "position_size_multiplier": 1.0,
                "force_gate_level": None,
                "reason": "event risk noted; exit allowed",
            }

        if days_to_event in {0, 1}:
            return {
                "risk_level": "high",
                "entry_blocked": True,
                "scale_in_blocked": True,
                "position_size_multiplier": 0.0,
                "force_gate_level": 1,
                "reason": f"{event_type} within restricted window",
            }
        if days_to_event == -1:
            return {
                "risk_level": "medium",
                "entry_blocked": False,
                "scale_in_blocked": True,
                "position_size_multiplier": 0.5,
                "force_gate_level": 1,
                "reason": "post earnings conservative window",
            }
        if days_to_event == 2:
            return {
                "risk_level": "medium",
                "entry_blocked": False,
                "scale_in_blocked": True,
                "position_size_multiplier": 0.5,
                "force_gate_level": None,
                "reason": f"{event_type} approaching",
            }
        return {
            "risk_level": "low",
            "entry_blocked": False,
            "scale_in_blocked": False,
            "position_size_multiplier": 1.0,
            "force_gate_level": None,
            "reason": "no restricted event window",
        }

    @staticmethod
    def _empty_response(
        *,
        symbol: str,
        market: str,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "market": market,
            "has_near_event": False,
            "event_type": None,
            "event_date": None,
            "event_time_label": "unknown",
            "days_to_event": None,
            "risk_level": "low",
            "entry_blocked": False,
            "scale_in_blocked": False,
            "position_size_multiplier": 1.0,
            "force_gate_level": None,
            "reason": "no structured event risk found",
            "source": None,
            "warnings": warnings or [],
        }


def _normalize_symbol(symbol: str, market: str) -> str:
    text = str(symbol or "").strip().upper()
    if str(market or "").strip().upper() == "KR":
        return text.zfill(6) if text.isdigit() and len(text) < 6 else text
    return text
