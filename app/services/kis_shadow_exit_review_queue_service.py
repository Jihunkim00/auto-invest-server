from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import KisShadowExitReviewQueueState, OrderLog, TradeRunLog
from app.services.kis_order_audit import (
    EXIT_SHADOW_SOURCE,
    EXIT_SHADOW_SOURCE_TYPE,
    kis_order_source_metadata_from_payloads,
)
from app.services.kis_payload_sanitizer import sanitize_kis_text


MODE = "shadow_exit_review_queue"
SHADOW_MODE = "shadow_exit_dry_run"
SHADOW_TRIGGER_SOURCE = "shadow_exit"
SHADOW_SOURCE = EXIT_SHADOW_SOURCE
SHADOW_SOURCE_TYPE = EXIT_SHADOW_SOURCE_TYPE
PROVIDER = "kis"
MARKET = "KR"

_INCLUDE_TRIGGERS = {"stop_loss", "take_profit", "manual_review"}
_REVIEW_HINTS = {
    "manual_review",
    "manual_review_required",
    "operator_review",
    "review_required",
    "insufficient_cost_basis",
    "duplicate_open_sell_order",
}


@dataclass
class _QueueCandidate:
    row: TradeRunLog
    payload: dict[str, Any]
    candidate: dict[str, Any]
    created_at: str
    created_dt: datetime | None
    symbol: str
    decision: str
    action: str
    trigger: str
    trigger_source: str
    latest_unrealized_pl: float | None
    latest_unrealized_pl_pct: float | None
    latest_cost_basis: float | None
    latest_current_value: float | None
    latest_current_price: float | None
    suggested_quantity: float | None
    reason: str
    risk_flags: list[str]
    gating_notes: list[str]
    real_order_submitted: bool
    broker_submit_called: bool
    manual_submit_called: bool
    linked_manual_order: OrderLog | None = None


class KisShadowExitReviewQueueService:
    """Operator review queue built from existing KIS shadow exit logs only."""

    def queue(
        self,
        db: Session,
        *,
        days: int = 30,
        limit: int = 50,
    ) -> dict[str, Any]:
        safe_days = min(max(int(days or 30), 1), 365)
        safe_limit = min(max(int(limit or 50), 1), 100)
        cutoff = datetime.now(UTC) - timedelta(days=safe_days)

        rows = self._shadow_runs(db, cutoff=cutoff)
        candidates = [
            item
            for item in (self._candidate_from_run(row) for row in rows)
            if item is not None and _should_include(item)
        ]
        self._link_manual_orders(db, candidates=candidates, cutoff=cutoff)

        states = self._state_map(db)
        all_items = self._queue_items(candidates, states=states)
        all_items.sort(key=_queue_sort_key)
        summary = _summary(all_items)
        items = all_items[:safe_limit]

        return {
            "status": "ok",
            "provider": PROVIDER,
            "market": MARKET,
            "mode": MODE,
            "review_window_days": safe_days,
            "summary": summary,
            "items": items,
            "safety": _safety_payload(),
            "created_at": datetime.now(UTC).isoformat(),
        }

    def mark_reviewed(
        self,
        db: Session,
        *,
        queue_id: str,
        operator_note: str | None = None,
    ) -> dict[str, Any]:
        row = self._upsert_state(
            db,
            queue_id=queue_id,
            status="reviewed",
            operator_note=operator_note,
        )
        return self._state_response(row, action="mark-reviewed")

    def dismiss(
        self,
        db: Session,
        *,
        queue_id: str,
        operator_note: str | None = None,
    ) -> dict[str, Any]:
        row = self._upsert_state(
            db,
            queue_id=queue_id,
            status="dismissed",
            operator_note=operator_note,
        )
        return self._state_response(row, action="dismiss")

    def _shadow_runs(self, db: Session, *, cutoff: datetime) -> list[TradeRunLog]:
        return (
            db.query(TradeRunLog)
            .filter(TradeRunLog.created_at >= _naive_utc(cutoff))
            .filter(
                or_(
                    TradeRunLog.mode == SHADOW_MODE,
                    TradeRunLog.trigger_source == SHADOW_TRIGGER_SOURCE,
                )
            )
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .limit(500)
            .all()
        )

    def _candidate_from_run(self, row: TradeRunLog) -> _QueueCandidate | None:
        request_payload = _parse_json_object(row.request_payload)
        payload = _parse_json_object(row.response_payload)
        candidate = _candidate_payload(payload)
        created_at = _string_or_none(payload.get("created_at")) or _iso(row.created_at)
        created_dt = _parse_dt(created_at) or _coerce_dt(row.created_at)
        decision = _normalized_decision(
            _first_present(payload.get("decision"), payload.get("result"), row.result)
        )
        action = str(
            _first_present(payload.get("action"), candidate.get("side"), row.result, "hold")
        )
        trigger = _string_or_none(
            _first_present(
                payload.get("exit_trigger"),
                candidate.get("trigger"),
                _audit(candidate).get("exit_trigger"),
            )
        ) or "none"
        trigger_source = _string_or_none(
            _first_present(
                payload.get("exit_trigger_source"),
                candidate.get("trigger_source"),
                _audit(candidate).get("trigger_source"),
                request_payload.get("trigger_source"),
            )
        ) or "unknown"
        symbol = _normalize_symbol(
            _first_present(
                candidate.get("symbol"),
                payload.get("symbol"),
                row.symbol if str(row.symbol or "").upper() != "WATCHLIST" else None,
            )
        )
        if not symbol:
            return None
        risk_flags = _dedupe(
            _string_list(candidate.get("risk_flags"))
            + _string_list(payload.get("risk_flags"))
        )
        gating_notes = _dedupe(
            _string_list(candidate.get("gating_notes"))
            + _string_list(payload.get("gating_notes"))
        )
        return _QueueCandidate(
            row=row,
            payload=payload,
            candidate=candidate,
            created_at=created_at or _iso(row.created_at) or "",
            created_dt=created_dt,
            symbol=symbol,
            decision=decision,
            action=action,
            trigger=trigger,
            trigger_source=trigger_source,
            latest_unrealized_pl=_float_value(candidate.get("unrealized_pl")),
            latest_unrealized_pl_pct=_float_value(candidate.get("unrealized_pl_pct")),
            latest_cost_basis=_float_value(candidate.get("cost_basis")),
            latest_current_value=_float_value(candidate.get("current_value")),
            latest_current_price=_float_value(candidate.get("current_price")),
            suggested_quantity=_float_value(
                _first_present(
                    candidate.get("suggested_quantity"),
                    candidate.get("quantity_available"),
                )
            ),
            reason=str(
                _first_present(candidate.get("reason"), payload.get("reason"), row.reason, "")
            ),
            risk_flags=risk_flags,
            gating_notes=gating_notes,
            real_order_submitted=_flag(
                payload.get("real_order_submitted"),
                candidate.get("real_order_submitted"),
                request_payload.get("real_order_submitted"),
            ),
            broker_submit_called=_flag(
                payload.get("broker_submit_called"),
                candidate.get("broker_submit_called"),
                request_payload.get("broker_submit_called"),
            ),
            manual_submit_called=_flag(
                payload.get("manual_submit_called"),
                candidate.get("manual_submit_called"),
                request_payload.get("manual_submit_called"),
            ),
        )

    def _link_manual_orders(
        self,
        db: Session,
        *,
        candidates: list[_QueueCandidate],
        cutoff: datetime,
    ) -> None:
        if not candidates:
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
        used: set[int] = set()
        for candidate in candidates:
            if candidate.decision != "would_sell":
                continue
            for order in rows:
                if order.id in used:
                    continue
                if _manual_order_matches_candidate(order, candidate):
                    candidate.linked_manual_order = order
                    used.add(order.id)
                    break

    def _queue_items(
        self,
        candidates: list[_QueueCandidate],
        *,
        states: dict[str, KisShadowExitReviewQueueState],
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[_QueueCandidate]] = {}
        for item in candidates:
            grouped.setdefault(_queue_key(item.symbol, item.trigger, item.trigger_source), []).append(item)

        items: list[dict[str, Any]] = []
        for queue_id, group in grouped.items():
            group.sort(
                key=lambda item: (
                    item.created_dt or datetime.min.replace(tzinfo=UTC),
                    item.row.id or 0,
                )
            )
            first = group[0]
            latest = group[-1]
            state = states.get(queue_id)
            order = next((item.linked_manual_order for item in reversed(group) if item.linked_manual_order), None)
            status = _state_status(state)
            items.append(
                {
                    "queue_id": queue_id,
                    "symbol": latest.symbol,
                    "decision": latest.decision,
                    "action": latest.action,
                    "trigger": latest.trigger,
                    "trigger_source": latest.trigger_source,
                    "severity": _severity(latest),
                    "occurrence_count": len(group),
                    "first_seen_at": first.created_at,
                    "latest_seen_at": latest.created_at,
                    "latest_unrealized_pl": latest.latest_unrealized_pl,
                    "latest_unrealized_pl_pct": latest.latest_unrealized_pl_pct,
                    "latest_cost_basis": latest.latest_cost_basis,
                    "latest_current_value": latest.latest_current_value,
                    "latest_current_price": latest.latest_current_price,
                    "suggested_quantity": latest.suggested_quantity,
                    "reason": _queue_reason(group, latest),
                    "risk_flags": _dedupe([flag for item in group for flag in item.risk_flags]),
                    "gating_notes": _dedupe(
                        ["shadow_exit_only", "manual_confirm_required", "no_broker_submit"]
                        + [note for item in group for note in item.gating_notes]
                    ),
                    "source_run_id": latest.row.id,
                    "source_run_key": latest.row.run_key,
                    "source_signal_id": latest.row.signal_id,
                    "linked_manual_order_id": order.id if order is not None else None,
                    "linked_manual_order_status": _order_status(order),
                    "linked_manual_order_created_at": _iso(order.created_at) if order is not None else None,
                    "linked_manual_order_filled_quantity": order.filled_qty if order is not None else None,
                    "linked_manual_order_average_fill_price": (
                        order.avg_fill_price or order.filled_avg_price
                        if order is not None
                        else None
                    ),
                    "status": status,
                    "reviewed_at": _iso(state.reviewed_at) if state is not None else None,
                    "dismissed_at": _iso(state.dismissed_at) if state is not None else None,
                    "operator_note": state.operator_note if state is not None else None,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                }
            )
        return items

    def _state_map(self, db: Session) -> dict[str, KisShadowExitReviewQueueState]:
        rows = db.query(KisShadowExitReviewQueueState).all()
        return {row.queue_key: row for row in rows}

    def _upsert_state(
        self,
        db: Session,
        *,
        queue_id: str,
        status: str,
        operator_note: str | None,
    ) -> KisShadowExitReviewQueueState:
        safe_queue_id = _safe_queue_id(queue_id)
        symbol, trigger = _queue_id_parts(safe_queue_id)
        row = (
            db.query(KisShadowExitReviewQueueState)
            .filter(KisShadowExitReviewQueueState.queue_key == safe_queue_id)
            .first()
        )
        now = datetime.now(UTC).replace(tzinfo=None)
        if row is None:
            row = KisShadowExitReviewQueueState(
                queue_key=safe_queue_id,
                symbol=symbol,
                trigger=trigger,
            )
            db.add(row)
        row.status = status
        row.operator_note = _sanitize_note(operator_note)
        row.updated_at = now
        if status == "reviewed":
            row.reviewed_at = now
            row.dismissed_at = None
        elif status == "dismissed":
            row.dismissed_at = now
            row.reviewed_at = None
        db.commit()
        db.refresh(row)
        return row

    def _state_response(
        self,
        row: KisShadowExitReviewQueueState,
        *,
        action: str,
    ) -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": MODE,
            "action": action,
            "item": {
                "queue_id": row.queue_key,
                "symbol": row.symbol,
                "trigger": row.trigger,
                "status": row.status,
                "operator_note": row.operator_note,
                "reviewed_at": _iso(row.reviewed_at),
                "dismissed_at": _iso(row.dismissed_at),
            },
            "safety": _safety_payload(),
            "created_at": datetime.now(UTC).isoformat(),
        }


def _candidate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload.get("candidate")
    if isinstance(candidate, dict):
        return candidate
    for key in ("candidates", "candidates_evaluated"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    return item
    return {}


def _should_include(item: _QueueCandidate) -> bool:
    if item.decision in {"would_sell", "manual_review"}:
        return True
    if item.trigger in _INCLUDE_TRIGGERS:
        return True
    flags = {text.lower() for text in item.risk_flags + item.gating_notes}
    return bool(flags.intersection(_REVIEW_HINTS))


def _manual_order_matches_candidate(order: OrderLog, candidate: _QueueCandidate) -> bool:
    metadata = _order_source_metadata(order)
    if metadata.get("source") != SHADOW_SOURCE:
        return False
    if metadata.get("source_type") != SHADOW_SOURCE_TYPE:
        return False
    if _normalize_symbol(order.symbol) != candidate.symbol:
        return False

    order_trigger = _string_or_none(metadata.get("exit_trigger"))
    if order_trigger and candidate.trigger and order_trigger != candidate.trigger:
        return False
    order_trigger_source = _string_or_none(metadata.get("trigger_source"))
    if (
        order_trigger_source
        and candidate.trigger_source
        and order_trigger_source != candidate.trigger_source
    ):
        return False

    metadata_run_key = _string_or_none(metadata.get("shadow_decision_run_key"))
    if metadata_run_key and metadata_run_key == candidate.row.run_key:
        return True

    checked_at = _parse_dt(
        _first_present(metadata.get("shadow_decision_checked_at"), metadata.get("checked_at"))
    )
    if checked_at is not None and candidate.created_dt is not None:
        if abs((checked_at - candidate.created_dt).total_seconds()) <= 600:
            return True

    order_dt = _coerce_dt(order.created_at)
    if order_dt is None or candidate.created_dt is None:
        return False
    delta_seconds = (order_dt - candidate.created_dt).total_seconds()
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


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    open_items = [item for item in items if item["status"] == "open"]
    reviewed = [item for item in items if item["status"] == "reviewed"]
    dismissed = [item for item in items if item["status"] == "dismissed"]
    repeated_symbols = {
        item["symbol"]
        for item in open_items
        if int(item.get("occurrence_count") or 0) > 1
    }
    return {
        "open_count": len(open_items),
        "reviewed_count": len(reviewed),
        "dismissed_count": len(dismissed),
        "would_sell_open_count": sum(
            1 for item in open_items if item["decision"] == "would_sell"
        ),
        "manual_review_open_count": sum(
            1 for item in open_items if item["decision"] == "manual_review"
        ),
        "repeated_symbol_count": len(repeated_symbols),
        "latest_open_at": max(
            (str(item["latest_seen_at"]) for item in open_items if item.get("latest_seen_at")),
            default=None,
        ),
    }


def _queue_sort_key(item: dict[str, Any]) -> tuple[int, int, float]:
    status_rank = {"open": 0, "reviewed": 1, "dismissed": 2}.get(str(item.get("status")), 3)
    severity_rank = {"urgent": 0, "review": 1, "watch": 2}.get(str(item.get("severity")), 3)
    latest = _parse_dt(item.get("latest_seen_at"))
    timestamp = latest.timestamp() if latest is not None else 0.0
    return (status_rank, severity_rank, -timestamp)


def _queue_key(symbol: str, trigger: str, trigger_source: str) -> str:
    safe_symbol = _safe_key_part(symbol) or "UNKNOWN"
    safe_trigger = _safe_key_part(trigger) or "unknown"
    safe_source = _safe_key_part(trigger_source) or "unknown"
    return _safe_queue_id(f"{safe_symbol}:{safe_trigger}:{safe_source}")


def _safe_queue_id(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_.:-]+", "_", text)
    text = text.strip(":._-")
    return text[:180] or "UNKNOWN:unknown:unknown"


def _safe_key_part(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())[:80]


def _queue_id_parts(queue_id: str) -> tuple[str, str]:
    parts = queue_id.split(":")
    symbol = _normalize_symbol(parts[0] if parts else None) or "UNKNOWN"
    trigger = parts[1] if len(parts) > 1 and parts[1] else "unknown"
    return symbol, trigger[:50]


def _severity(item: _QueueCandidate) -> str:
    if item.trigger == "stop_loss":
        return "urgent"
    if item.decision in {"would_sell", "manual_review"}:
        return "review"
    return "watch"


def _queue_reason(group: list[_QueueCandidate], latest: _QueueCandidate) -> str:
    if len(group) > 1:
        return "Repeated shadow exit candidate. Manual operator review recommended."
    return latest.reason or "Shadow exit candidate needs operator review."


def _state_status(row: KisShadowExitReviewQueueState | None) -> str:
    if row is None:
        return "open"
    status = str(row.status or "open").strip().lower()
    if status in {"reviewed", "dismissed"}:
        return status
    return "open"


def _safety_payload() -> dict[str, Any]:
    return {
        "read_only": True,
        "operator_state_only": True,
        "creates_orders": False,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "auto_buy_enabled": False,
        "auto_sell_enabled": False,
        "scheduler_real_order_enabled": False,
    }


def _sanitize_note(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    sanitized = sanitize_kis_text(text)
    return sanitized[:500]


def _audit(candidate: dict[str, Any]) -> dict[str, Any]:
    metadata = candidate.get("audit_metadata")
    return metadata if isinstance(metadata, dict) else {}


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


def _flag(*values: Any) -> bool:
    for value in values:
        parsed = _bool_value(value)
        if parsed is not None:
            return parsed
    return False


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


def _order_status(order: OrderLog | None) -> str | None:
    if order is None:
        return None
    return order.internal_status or order.broker_order_status or order.broker_status
