from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import OrderLog, TradeRunLog
from app.services.kis_order_audit import (
    EXIT_SHADOW_SOURCE,
    EXIT_SHADOW_SOURCE_TYPE,
    kis_order_source_metadata_from_payloads,
)


MODE = "shadow_exit_review"
SHADOW_MODE = "shadow_exit_dry_run"
SHADOW_SOURCE = EXIT_SHADOW_SOURCE
SHADOW_SOURCE_TYPE = EXIT_SHADOW_SOURCE_TYPE
SHADOW_TRIGGER_SOURCE = "shadow_exit"
PROVIDER = "kis"
MARKET = "KR"

_SUBMIT_FLAG_KEYS = (
    "real_order_submitted",
    "broker_submit_called",
    "manual_submit_called",
)
_CANDIDATE_SUBMIT_FLAG_KEYS = (
    "real_order_submitted",
    "broker_submit_called",
    "manual_submit_called",
)
_AUDIT_SUBMIT_FLAG_KEYS = (
    "shadow_real_order_submitted",
    "shadow_broker_submit_called",
    "shadow_manual_submit_called",
)


@dataclass
class _ShadowDecision:
    row: TradeRunLog
    payload: dict[str, Any]
    candidate: dict[str, Any]
    created_at: str
    created_dt: datetime | None
    symbol: str | None
    decision: str
    action: str
    trigger: str | None
    trigger_source: str | None
    real_order_submitted: bool
    broker_submit_called: bool
    manual_submit_called: bool
    submit_invariant_ok: bool
    linked_manual_order: OrderLog | None = None


class KisShadowExitReviewService:
    """Read-only quality review for historical KIS shadow exit decisions."""

    def review(
        self,
        db: Session,
        *,
        limit: int = 20,
        days: int = 30,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        safe_limit = min(max(int(limit or 20), 1), 100)
        safe_days = min(max(int(days or 30), 1), 365)
        cutoff = datetime.now(UTC) - timedelta(days=safe_days)

        rows = self._shadow_runs(db, cutoff=cutoff, symbol=symbol)
        decisions = [self._decision_from_run(row) for row in rows]
        self._link_manual_orders(db, decisions=decisions, cutoff=cutoff)

        summary = self._summary(decisions)
        recent = [self._serialize_decision(item) for item in decisions[:safe_limit]]
        linked_manual_orders = self._linked_manual_orders(decisions)
        warnings = []
        if not summary["no_submit_invariant_ok"]:
            warnings.append("historical_shadow_record_has_submit_flag_true")

        payload = {
            "status": "ok",
            "provider": PROVIDER,
            "market": MARKET,
            "mode": MODE,
            "review_window_days": safe_days,
            "summary": summary,
            "recent_decisions": recent,
            "linked_manual_orders": linked_manual_orders,
            "safety": {
                "read_only": True,
                "aggregates_existing_logs_only": True,
                "creates_orders": False,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "auto_buy_enabled": False,
                "auto_sell_enabled": False,
                "scheduler_real_order_enabled": False,
                "no_submit_invariant_ok": summary["no_submit_invariant_ok"],
                "warnings": warnings,
            },
            "diagnostics": {
                "source": SHADOW_SOURCE,
                "source_type": SHADOW_SOURCE_TYPE,
                "warnings": warnings,
            },
            "created_at": datetime.now(UTC).isoformat(),
        }
        return payload

    def _shadow_runs(
        self,
        db: Session,
        *,
        cutoff: datetime,
        symbol: str | None,
    ) -> list[TradeRunLog]:
        normalized_symbol = _normalize_symbol(symbol)
        query = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.created_at >= _naive_utc(cutoff))
            .filter(
                or_(
                    TradeRunLog.mode == SHADOW_MODE,
                    TradeRunLog.trigger_source == SHADOW_TRIGGER_SOURCE,
                )
            )
        )
        if normalized_symbol:
            query = query.filter(
                or_(
                    TradeRunLog.symbol == normalized_symbol,
                    TradeRunLog.response_payload.like(f"%{normalized_symbol}%"),
                )
            )
        return (
            query.order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .limit(500)
            .all()
        )

    def _decision_from_run(self, row: TradeRunLog) -> _ShadowDecision:
        request_payload = _parse_json_object(row.request_payload)
        payload = _parse_json_object(row.response_payload)
        candidate = _candidate_payload(payload)
        created_at = _string_or_none(payload.get("created_at")) or _iso(row.created_at)
        created_dt = _parse_dt(created_at) or _coerce_dt(row.created_at)
        decision = _normalized_decision(
            _first_present(payload.get("decision"), payload.get("result"), row.result)
        )
        action = str(_first_present(payload.get("action"), candidate.get("side"), row.result, "hold"))
        trigger = _string_or_none(
            _first_present(
                payload.get("exit_trigger"),
                candidate.get("trigger"),
                (candidate.get("audit_metadata") or {}).get("exit_trigger")
                if isinstance(candidate.get("audit_metadata"), dict)
                else None,
            )
        )
        trigger_source = _string_or_none(
            _first_present(
                payload.get("exit_trigger_source"),
                candidate.get("trigger_source"),
                (candidate.get("audit_metadata") or {}).get("trigger_source")
                if isinstance(candidate.get("audit_metadata"), dict)
                else None,
                request_payload.get("trigger_source"),
            )
        )
        symbol = _normalize_symbol(
            _first_present(
                candidate.get("symbol"),
                payload.get("symbol"),
                row.symbol if str(row.symbol or "").upper() != "WATCHLIST" else None,
            )
        )
        real_order_submitted = _bool_value(
            _first_present(
                payload.get("real_order_submitted"),
                candidate.get("real_order_submitted"),
                request_payload.get("real_order_submitted"),
            )
        ) or False
        broker_submit_called = _bool_value(
            _first_present(
                payload.get("broker_submit_called"),
                candidate.get("broker_submit_called"),
                request_payload.get("broker_submit_called"),
            )
        ) or False
        manual_submit_called = _bool_value(
            _first_present(
                payload.get("manual_submit_called"),
                candidate.get("manual_submit_called"),
                request_payload.get("manual_submit_called"),
            )
        ) or False

        return _ShadowDecision(
            row=row,
            payload=payload,
            candidate=candidate,
            created_at=created_at,
            created_dt=created_dt,
            symbol=symbol,
            decision=decision,
            action=action,
            trigger=trigger,
            trigger_source=trigger_source,
            real_order_submitted=real_order_submitted,
            broker_submit_called=broker_submit_called,
            manual_submit_called=manual_submit_called,
            submit_invariant_ok=_submit_invariant_ok(
                request_payload=request_payload,
                payload=payload,
                candidate=candidate,
            ),
        )

    def _link_manual_orders(
        self,
        db: Session,
        *,
        decisions: list[_ShadowDecision],
        cutoff: datetime,
    ) -> None:
        if not decisions:
            return

        rows = (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.side == "sell")
            .filter(OrderLog.created_at >= _naive_utc(cutoff - timedelta(days=1)))
            .order_by(OrderLog.created_at.asc(), OrderLog.id.asc())
            .limit(500)
            .all()
        )
        used_order_ids: set[int] = set()
        for decision in decisions:
            if decision.decision != "would_sell" or not decision.symbol:
                continue
            for order in rows:
                if order.id in used_order_ids:
                    continue
                if _manual_order_matches_decision(order, decision):
                    decision.linked_manual_order = order
                    used_order_ids.add(order.id)
                    break

    def _summary(self, decisions: list[_ShadowDecision]) -> dict[str, Any]:
        total = len(decisions)
        would_sell = [item for item in decisions if item.decision == "would_sell"]
        manual_review = [
            item for item in decisions if item.decision == "manual_review"
        ]
        holds = [item for item in decisions if item.decision == "hold"]
        no_candidate = [
            item for item in decisions if not isinstance(item.payload.get("candidate"), dict)
        ]
        stop_loss_count = sum(1 for item in decisions if item.trigger == "stop_loss")
        take_profit_count = sum(1 for item in decisions if item.trigger == "take_profit")
        manual_review_trigger_count = sum(
            1 for item in decisions if item.trigger == "manual_review"
        )
        insufficient_cost_basis_count = sum(
            1
            for item in decisions
            if item.trigger_source == "insufficient_cost_basis"
            or "insufficient_cost_basis" in _string_list(item.candidate.get("risk_flags"))
            or "insufficient_cost_basis" in _string_list(item.payload.get("risk_flags"))
        )
        would_sell_pl_pcts = [
            value
            for value in (
                _float_value(item.candidate.get("unrealized_pl_pct"))
                for item in would_sell
            )
            if value is not None
        ]
        linked_would_sell_count = sum(
            1 for item in would_sell if item.linked_manual_order is not None
        )
        no_submit_invariant_ok = all(item.submit_invariant_ok for item in decisions)
        symbols = {
            symbol
            for item in decisions
            for symbol in _decision_symbols(item)
            if symbol and symbol != "WATCHLIST"
        }

        return {
            "total_shadow_runs": total,
            "would_sell_count": len(would_sell),
            "hold_count": len(holds),
            "manual_review_count": len(manual_review),
            "no_candidate_count": len(no_candidate),
            "stop_loss_count": stop_loss_count,
            "take_profit_count": take_profit_count,
            "manual_review_trigger_count": manual_review_trigger_count,
            "insufficient_cost_basis_count": insufficient_cost_basis_count,
            "unique_symbols_evaluated": len(symbols),
            "latest_shadow_decision_at": decisions[0].created_at if decisions else None,
            "latest_would_sell_at": next(
                (item.created_at for item in decisions if item.decision == "would_sell"),
                None,
            ),
            "average_unrealized_pl_pct_for_would_sell": _average(
                would_sell_pl_pcts
            ),
            "min_unrealized_pl_pct_for_would_sell": min(would_sell_pl_pcts)
            if would_sell_pl_pcts
            else None,
            "max_unrealized_pl_pct_for_would_sell": max(would_sell_pl_pcts)
            if would_sell_pl_pcts
            else None,
            "would_sell_rate": _rate(len(would_sell), total),
            "manual_review_rate": _rate(len(manual_review), total),
            "manual_sell_followed_count": linked_would_sell_count,
            "manual_sell_followed_rate": _rate(
                linked_would_sell_count, len(would_sell)
            ),
            "unmatched_shadow_would_sell_count": len(would_sell)
            - linked_would_sell_count,
            "no_submit_invariant_ok": no_submit_invariant_ok,
        }

    def _serialize_decision(self, item: _ShadowDecision) -> dict[str, Any]:
        order = item.linked_manual_order
        return {
            "created_at": item.created_at,
            "run_id": item.row.id,
            "run_key": item.row.run_key,
            "signal_id": item.row.signal_id,
            "symbol": item.symbol,
            "decision": item.decision,
            "action": item.action,
            "trigger": item.trigger,
            "trigger_source": item.trigger_source,
            "unrealized_pl": _float_value(item.candidate.get("unrealized_pl")),
            "unrealized_pl_pct": _float_value(
                item.candidate.get("unrealized_pl_pct")
            ),
            "cost_basis": _float_value(item.candidate.get("cost_basis")),
            "current_value": _float_value(item.candidate.get("current_value")),
            "suggested_quantity": _float_value(
                _first_present(
                    item.candidate.get("suggested_quantity"),
                    item.candidate.get("quantity_available"),
                )
            ),
            "reason": str(
                _first_present(
                    item.candidate.get("reason"),
                    item.payload.get("reason"),
                    item.row.reason,
                    "",
                )
            ),
            "risk_flags": _dedupe(
                _string_list(item.candidate.get("risk_flags"))
                + _string_list(item.payload.get("risk_flags"))
            ),
            "gating_notes": _dedupe(
                _string_list(item.candidate.get("gating_notes"))
                + _string_list(item.payload.get("gating_notes"))
            ),
            "real_order_submitted": item.real_order_submitted,
            "broker_submit_called": item.broker_submit_called,
            "manual_submit_called": item.manual_submit_called,
            "no_submit_invariant_ok": item.submit_invariant_ok,
            "linked_manual_order_id": order.id if order is not None else None,
            "linked_manual_order_status": _order_status(order)
            if order is not None
            else None,
        }

    def _linked_manual_orders(
        self, decisions: list[_ShadowDecision]
    ) -> list[dict[str, Any]]:
        rows: list[OrderLog] = []
        seen: set[int] = set()
        for decision in decisions:
            order = decision.linked_manual_order
            if order is None or order.id in seen:
                continue
            rows.append(order)
            seen.add(order.id)
        return [
            {
                "order_id": row.id,
                "symbol": row.symbol,
                "side": row.side,
                "status": _order_status(row),
                "internal_status": row.internal_status,
                "broker_order_status": row.broker_order_status,
                "broker_status": row.broker_status,
                "filled_qty": row.filled_qty,
                "remaining_qty": row.remaining_qty,
                "created_at": _iso(row.created_at),
                "submitted_at": _iso(row.submitted_at),
                "filled_at": _iso(row.filled_at),
            }
            for row in rows
        ]


def _candidate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload.get("candidate")
    if isinstance(candidate, dict):
        return candidate
    evaluated = payload.get("candidates_evaluated")
    if isinstance(evaluated, list):
        for item in evaluated:
            if isinstance(item, dict):
                return item
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        for item in candidates:
            if isinstance(item, dict):
                return item
    return {}


def _manual_order_matches_decision(
    order: OrderLog, decision: _ShadowDecision
) -> bool:
    metadata = _order_source_metadata(order)
    if metadata.get("source") != SHADOW_SOURCE:
        return False
    if metadata.get("source_type") != SHADOW_SOURCE_TYPE:
        return False
    if _normalize_symbol(order.symbol) != decision.symbol:
        return False

    order_trigger = _string_or_none(metadata.get("exit_trigger"))
    if order_trigger and decision.trigger and order_trigger != decision.trigger:
        return False

    order_trigger_source = _string_or_none(metadata.get("trigger_source"))
    if (
        order_trigger_source
        and decision.trigger_source
        and order_trigger_source != decision.trigger_source
    ):
        return False

    metadata_run_key = _string_or_none(metadata.get("shadow_decision_run_key"))
    if metadata_run_key and metadata_run_key == decision.row.run_key:
        return True

    checked_at = _parse_dt(
        _first_present(
            metadata.get("shadow_decision_checked_at"),
            metadata.get("checked_at"),
        )
    )
    if checked_at is not None and decision.created_dt is not None:
        delta = abs((checked_at - decision.created_dt).total_seconds())
        if delta <= 600:
            return True

    order_dt = _coerce_dt(order.created_at)
    if order_dt is None or decision.created_dt is None:
        return False
    delta_seconds = (order_dt - decision.created_dt).total_seconds()
    if delta_seconds < 0 or delta_seconds > 7 * 24 * 60 * 60:
        return False
    return bool(order_trigger or order_trigger_source)


def _order_source_metadata(order: OrderLog) -> dict[str, Any]:
    payloads = [
        _parse_json_object(order.request_payload),
        _parse_json_object(order.response_payload),
        _parse_json_object(order.last_sync_payload),
    ]
    return kis_order_source_metadata_from_payloads(*payloads)


def _submit_invariant_ok(
    *,
    request_payload: dict[str, Any],
    payload: dict[str, Any],
    candidate: dict[str, Any],
) -> bool:
    audit_metadata = candidate.get("audit_metadata")
    if not isinstance(audit_metadata, dict):
        audit_metadata = {}
    for key in _SUBMIT_FLAG_KEYS:
        if _bool_value(_first_present(payload.get(key), request_payload.get(key))):
            return False
    for key in _CANDIDATE_SUBMIT_FLAG_KEYS:
        if _bool_value(candidate.get(key)):
            return False
    for key in _AUDIT_SUBMIT_FLAG_KEYS:
        if _bool_value(audit_metadata.get(key)):
            return False
    return True


def _decision_symbols(item: _ShadowDecision) -> list[str]:
    symbols: list[str] = []
    symbol = _normalize_symbol(item.symbol)
    if symbol:
        symbols.append(symbol)
    for key in ("candidate", "candidates", "candidates_evaluated"):
        value = item.payload.get(key)
        if isinstance(value, dict):
            symbol = _normalize_symbol(value.get("symbol"))
            if symbol:
                symbols.append(symbol)
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    symbol = _normalize_symbol(entry.get("symbol"))
                    if symbol:
                        symbols.append(symbol)
    return _dedupe(symbols)


def _parse_json_object(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def _normalized_decision(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"would_sell", "sell", "stop_loss", "take_profit"}:
        return "would_sell"
    if text in {"manual_review", "review"}:
        return "manual_review"
    return "hold"


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _bool_value(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _float_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "null":
        return None
    return text


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _normalize_symbol(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text or text == "NULL":
        return None
    if text.isdigit() and len(text) < 6:
        text = text.zfill(6)
    return text


def _parse_dt(value: Any) -> datetime | None:
    text = _string_or_none(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _coerce_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    return _parse_dt(value)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _iso(value: Any) -> str | None:
    dt = _coerce_dt(value)
    if dt is None:
        return None
    return dt.isoformat()


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _order_status(order: OrderLog | None) -> str | None:
    if order is None:
        return None
    return (
        order.internal_status
        or order.broker_order_status
        or order.broker_status
    )
