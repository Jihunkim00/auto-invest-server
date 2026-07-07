from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, SignalLog
from app.schemas.auto_exit_candidate import (
    AutoExitCandidate,
    AutoExitCandidateSummary,
    AutoExitCandidatesResponse,
    CandidateSeverity,
    CandidateType,
)
from app.services.market_session_service import MarketSessionService
from app.services.position_exit_review_service import PositionExitReviewService


PROVIDER = "kis"
MARKET = "KR"
TIMEZONE = "Asia/Seoul"
KST = ZoneInfo(TIMEZONE)

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
_OPEN_ORDER_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
}
_SYNC_REQUIRED_STATUSES = {
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
}


class AutoExitCandidateService:
    """Read-only exit candidate detection for currently held positions."""

    def __init__(
        self,
        exit_review_service: PositionExitReviewService,
        *,
        session_service: MarketSessionService | None = None,
    ) -> None:
        self.exit_review_service = exit_review_service
        self.session_service = session_service or MarketSessionService()

    def candidates(
        self,
        db: Session,
        *,
        provider: str | None = None,
        market: str | None = None,
        symbol: str | None = None,
        include_details: bool = True,
        min_severity: str | None = None,
    ) -> dict[str, Any]:
        generated_at = datetime.now(UTC)
        normalized_provider = _normalize_provider(provider)
        normalized_market = _normalize_market(market)
        normalized_symbol = _normalize_symbol(symbol)
        severity = _normalize_min_severity(min_severity)

        if normalized_provider != PROVIDER or normalized_market != MARKET:
            return AutoExitCandidatesResponse(
                generated_at=generated_at.isoformat(),
                timezone=TIMEZONE,
                provider=normalized_provider,
                market=normalized_market,
                candidates=[],
                summary=AutoExitCandidateSummary(),
                safety_flags=_safety_flags(["unsupported_provider_or_market"]),
                details={"reason": "auto_exit_candidates_support_kis_kr_only"}
                if include_details
                else None,
            ).model_dump(mode="json")

        review = self.exit_review_service.exit_review(db)
        positions = [
            item
            for item in review.get("positions", [])
            if isinstance(item, dict)
            and (not normalized_symbol or str(item.get("symbol") or "").upper() == normalized_symbol)
        ]
        market_session = self._market_session()
        near_close = _is_near_close(market_session)
        all_candidates: list[AutoExitCandidate] = []

        for position in positions:
            all_candidates.extend(
                self._position_candidates(
                    db,
                    position=position,
                    generated_at=generated_at,
                    near_close=near_close,
                )
            )

        filtered = [
            item
            for item in all_candidates
            if _SEVERITY_ORDER[item.severity] <= _SEVERITY_ORDER[severity]
        ]
        filtered.sort(
            key=lambda item: (
                _SEVERITY_ORDER[item.severity],
                item.symbol,
                item.candidate_type,
            )
        )
        return AutoExitCandidatesResponse(
            generated_at=generated_at.isoformat(),
            timezone=TIMEZONE,
            provider=PROVIDER,
            market=MARKET,
            candidates=filtered,
            summary=_summary(filtered),
            safety_flags=_safety_flags(),
            details={
                "position_count": len(positions),
                "min_severity": severity,
                "symbol": normalized_symbol,
                "market_session": market_session,
                "read_errors": (review.get("safety") or {}).get("read_errors") or [],
            }
            if include_details
            else None,
        ).model_dump(mode="json")

    def _position_candidates(
        self,
        db: Session,
        *,
        position: dict[str, Any],
        generated_at: datetime,
        near_close: bool,
    ) -> list[AutoExitCandidate]:
        symbol = str(position.get("symbol") or "").upper()
        if not symbol:
            return []
        duplicate = bool(position.get("duplicate_open_sell_order"))
        sync_required = _symbol_sync_required(db, symbol=symbol)
        base = _base_payload(
            position,
            generated_at=generated_at,
            open_sell_order_conflict=duplicate,
            sync_required=sync_required,
        )
        items: list[AutoExitCandidate] = []

        if duplicate:
            items.append(
                self._candidate(
                    base,
                    candidate_type="duplicate_sell_conflict",
                    severity="critical",
                    primary_reason="Open sell order already exists for this symbol.",
                    next_safe_action="Review the existing sell order before any new preflight.",
                    extra_risk_flags=["duplicate_open_sell_order"],
                )
            )

        if sync_required:
            items.append(
                self._candidate(
                    base,
                    candidate_type="sync_required",
                    severity="warning",
                    primary_reason="Recent order state is stale or sync failed.",
                    next_safe_action="Review order sync state before opening a sell preflight.",
                    extra_risk_flags=["sync_required"],
                )
            )

        if _pl_incomplete(position):
            items.append(
                self._candidate(
                    base,
                    candidate_type="manual_review",
                    severity="warning",
                    primary_reason="Position P/L calculation is incomplete; cost basis or current value is missing.",
                    next_safe_action="Review broker position data before using exit thresholds.",
                    extra_risk_flags=["incomplete_pl_inputs"],
                    can_preflight=False,
                )
            )
            return items

        if bool(position.get("stop_loss_triggered")):
            items.append(
                self._candidate(
                    base,
                    candidate_type="stop_loss",
                    severity="critical",
                    primary_reason="Stop-loss threshold was reached from cost-basis P/L.",
                    next_safe_action="Run sell preflight for operator review; do not submit an order from candidate detection.",
                    extra_risk_flags=["stop_loss_triggered"],
                )
            )

        if bool(position.get("take_profit_triggered")):
            items.append(
                self._candidate(
                    base,
                    candidate_type="take_profit",
                    severity="warning",
                    primary_reason="Take-profit threshold was reached from cost-basis P/L.",
                    next_safe_action="Run sell preflight for operator review; do not submit an order from candidate detection.",
                    extra_risk_flags=["take_profit_triggered"],
                )
            )

        indicators = _latest_indicators(db, symbol=symbol)
        trend_reasons = _trend_breakdown_reasons(position, indicators)
        if trend_reasons:
            items.append(
                self._candidate(
                    base,
                    candidate_type="trend_breakdown",
                    severity="warning",
                    primary_reason="Price is below cached trend reference levels.",
                    next_safe_action="Review trend context and run sell preflight only if operator agrees.",
                    trend_breakdown=True,
                    momentum_note=", ".join(trend_reasons),
                    extra_risk_flags=["trend_breakdown"],
                )
            )

        momentum_note = _weak_momentum_note(indicators)
        if momentum_note:
            items.append(
                self._candidate(
                    base,
                    candidate_type="weak_momentum",
                    severity="info",
                    primary_reason="Cached momentum indicator is weak.",
                    next_safe_action="Review momentum context; continue holding unless a preflight is warranted.",
                    momentum_note=momentum_note,
                    extra_risk_flags=["weak_momentum"],
                )
            )

        if near_close:
            items.append(
                self._candidate(
                    base,
                    candidate_type="near_close_risk",
                    severity="info",
                    primary_reason="Market session is near regular close.",
                    next_safe_action="Review close-time risk; no sell order is created automatically.",
                    extra_risk_flags=["near_close_risk"],
                )
            )

        if not items and not indicators:
            items.append(
                self._candidate(
                    base,
                    candidate_type="manual_review",
                    severity="info",
                    primary_reason="No cached trend or momentum indicators are available for this held position.",
                    next_safe_action="Continue monitoring or run sell preflight for manual review.",
                    extra_risk_flags=["insufficient_indicator_data"],
                )
            )

        return items

    def _candidate(
        self,
        base: dict[str, Any],
        *,
        candidate_type: CandidateType,
        severity: CandidateSeverity,
        primary_reason: str,
        next_safe_action: str,
        extra_risk_flags: list[str] | None = None,
        trend_breakdown: bool = False,
        momentum_note: str | None = None,
        can_preflight: bool | None = None,
    ) -> AutoExitCandidate:
        conflict = bool(base["open_sell_order_conflict"])
        sync_required = bool(base["sync_required"])
        allowed = bool(base["available_quantity"] is not None and base["available_quantity"] > 0)
        if can_preflight is None:
            can_preflight = allowed and not conflict and not sync_required
        action_hint = "run_sell_preflight" if can_preflight else "review"
        if sync_required:
            action_hint = "sync_required"
        if candidate_type == "manual_review" and not can_preflight:
            action_hint = "review"
        gating_notes = _dedupe(
            [
                *base["gating_notes"],
                "Read-only candidate detection.",
                "Sell preflight is optional and operator-triggered only.",
                "No sell order is created by this candidate.",
                "Open sell order conflict blocks preflight hint." if conflict else "",
                "Sync-required order state blocks preflight hint." if sync_required else "",
            ]
        )
        risk_flags = _dedupe([*base["risk_flags"], *(extra_risk_flags or [])])
        return AutoExitCandidate(
            **{
                **base,
                "candidate_id": _candidate_id(
                    base["symbol"],
                    candidate_type,
                    base["generated_at"],
                ),
                "candidate_type": candidate_type,
                "severity": severity,
                "action_hint": action_hint,
                "trend_breakdown_triggered": trend_breakdown,
                "momentum_note": momentum_note,
                "risk_flags": risk_flags,
                "gating_notes": gating_notes,
                "primary_reason": primary_reason,
                "next_safe_action": next_safe_action,
                "can_run_sell_preflight": bool(can_preflight),
                "sell_preflight_endpoint_hint": (
                    f"/strategy/positions/{base['symbol']}/sell-preflight"
                    if can_preflight
                    else None
                ),
            }
        )

    def _market_session(self) -> dict[str, Any]:
        try:
            payload = self.session_service.get_session_status(MARKET)
            return dict(payload) if isinstance(payload, dict) else {}
        except Exception as exc:
            return {"market": MARKET, "error": f"{exc.__class__.__name__}: {str(exc)[:120]}"}


def _base_payload(
    position: dict[str, Any],
    *,
    generated_at: datetime,
    open_sell_order_conflict: bool,
    sync_required: bool,
) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "symbol": str(position.get("symbol") or "").upper(),
        "provider": str(position.get("provider") or PROVIDER),
        "market": str(position.get("market") or MARKET),
        "position_quantity": _float_or_none(position.get("quantity")),
        "available_quantity": _float_or_none(position.get("available_quantity")),
        "average_price": _float_or_none(position.get("average_price")),
        "current_price": _float_or_none(position.get("current_price")),
        "cost_basis": _float_or_none(position.get("cost_basis")),
        "current_value": _float_or_none(position.get("current_value")),
        "unrealized_pl": _float_or_none(position.get("unrealized_pl")),
        "unrealized_pl_pct": _float_or_none(position.get("unrealized_pl_pct")),
        "stop_loss_threshold_pct": _float_or_none(position.get("stop_loss_threshold_pct")),
        "take_profit_threshold_pct": _float_or_none(position.get("take_profit_threshold_pct")),
        "stop_loss_triggered": bool(position.get("stop_loss_triggered")),
        "take_profit_triggered": bool(position.get("take_profit_triggered")),
        "risk_flags": _strings(position.get("risk_flags")),
        "gating_notes": _strings(position.get("gating_notes")),
        "related_position_id": None,
        "related_buy_order_id": _int_or_none(position.get("related_buy_order_id")),
        "related_lifecycle_id": None,
        "open_sell_order_conflict": open_sell_order_conflict,
        "sync_required": sync_required,
    }


def _summary(candidates: list[AutoExitCandidate]) -> AutoExitCandidateSummary:
    severity = Counter(item.severity for item in candidates)
    types = Counter(item.candidate_type for item in candidates)
    return AutoExitCandidateSummary(
        candidate_count=len(candidates),
        critical_count=severity["critical"],
        warning_count=severity["warning"],
        info_count=severity["info"],
        stop_loss_count=types["stop_loss"],
        take_profit_count=types["take_profit"],
        trend_breakdown_count=types["trend_breakdown"],
        manual_review_count=types["manual_review"],
        duplicate_sell_block_count=types["duplicate_sell_conflict"],
        sync_required_count=types["sync_required"],
    )


def _symbol_sync_required(db: Session, *, symbol: str) -> bool:
    if not symbol:
        return False
    cutoff = datetime.now(UTC) - timedelta(minutes=15)
    rows = (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.symbol == symbol)
        .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
        .limit(20)
        .all()
    )
    for row in rows:
        status = str(row.internal_status or "").upper()
        if status in _SYNC_REQUIRED_STATUSES:
            return True
        if (
            status in _OPEN_ORDER_STATUSES
            and row.last_synced_at is None
            and _as_utc(row.created_at) is not None
            and _as_utc(row.created_at) <= cutoff
        ):
            return True
    return False


def _latest_indicators(db: Session, *, symbol: str) -> dict[str, Any]:
    row = (
        db.query(SignalLog)
        .filter(SignalLog.symbol == symbol)
        .filter(SignalLog.indicator_payload.isnot(None))
        .order_by(SignalLog.created_at.desc(), SignalLog.id.desc())
        .first()
    )
    if row is None or not row.indicator_payload:
        return {}
    try:
        payload = json.loads(row.indicator_payload)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _trend_breakdown_reasons(
    position: dict[str, Any],
    indicators: dict[str, Any],
) -> list[str]:
    if not indicators:
        return []
    price = _float_or_none(position.get("current_price")) or _float_or_none(indicators.get("price"))
    if price is None or price <= 0:
        return []
    reasons: list[str] = []
    for key in ("ema20", "ema50", "vwap"):
        value = _float_or_none(indicators.get(key))
        if value is not None and value > 0 and price < value:
            reasons.append(f"price_below_{key}")
    return _dedupe(reasons)


def _weak_momentum_note(indicators: dict[str, Any]) -> str | None:
    if not indicators:
        return None
    checks = []
    for key in ("momentum", "short_momentum", "recent_return"):
        value = _float_or_none(indicators.get(key))
        if value is not None and value < 0:
            checks.append(f"{key}={value:.4f}")
    return ", ".join(checks) if checks else None


def _pl_incomplete(position: dict[str, Any]) -> bool:
    return (
        _float_or_none(position.get("cost_basis")) is None
        or _float_or_none(position.get("current_value")) is None
        or _float_or_none(position.get("unrealized_pl_pct")) is None
    )


def _is_near_close(market_session: dict[str, Any]) -> bool:
    if market_session.get("is_near_close") is True:
        return True
    if market_session.get("is_market_open") is True and market_session.get("is_entry_allowed_now") is False:
        return True
    return False


def _candidate_id(symbol: str, candidate_type: str, generated_at: datetime) -> str:
    day = generated_at.astimezone(KST).strftime("%Y%m%d")
    return f"auto-exit:{PROVIDER}:{MARKET}:{symbol}:{candidate_type}:{day}"


def _safety_flags(extra: list[str] | None = None) -> list[str]:
    return _dedupe(
        [
            "read_only",
            "no_live_orders",
            "no_broker_submit",
            "preflight_hint_only",
            "scheduler_real_orders_disabled",
            *(extra or []),
        ]
    )


def _normalize_provider(value: str | None) -> str:
    text = str(value or PROVIDER).strip().lower()
    return text or PROVIDER


def _normalize_market(value: str | None) -> str:
    text = str(value or MARKET).strip().upper()
    return text or MARKET


def _normalize_symbol(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if text.isdigit() and len(text) < 6:
        return text.zfill(6)
    return text


def _normalize_min_severity(value: str | None) -> str:
    text = str(value or "info").strip().lower()
    return text if text in _SEVERITY_ORDER else "info"


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value is None:
        return []
    return [str(value)] if str(value) else []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
