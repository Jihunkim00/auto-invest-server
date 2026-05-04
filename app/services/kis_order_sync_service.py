from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog
from app.services.kis_order_mapper import (
    find_kis_order_row,
    map_kis_order_row,
    stale_kis_order_status,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload, sanitize_kis_text

KR_TZ = ZoneInfo("Asia/Seoul")

OPEN_KIS_INTERNAL_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.UNKNOWN_STALE.value,
    "PENDING_SUBMIT",
}


class KisOrderSyncError(ValueError):
    pass


class KisOrderSyncService:
    def __init__(
        self,
        client: KisClient,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.client = client
        self.now_provider = now_provider or (lambda: datetime.now(KR_TZ))

    def sync_order(self, db: Session, order_id: int) -> OrderLog:
        order = db.get(OrderLog, order_id)
        if order is None:
            raise KisOrderSyncError("KIS order not found.")
        if str(order.broker or "").strip().lower() != "kis":
            raise KisOrderSyncError("Order is not a KIS order.")

        order_no = _order_no(order)
        if not order_no:
            order.sync_error = "kis_odno_missing"
            order.error_message = order.sync_error
            order.last_synced_at = _now_naive_utc()
            db.commit()
            db.refresh(order)
            raise KisOrderSyncError("KIS order number is missing.")

        old_status = order.internal_status
        now = _now_naive_utc()
        start_date = None
        end_date = None
        attempts: list[dict[str, Any]] = []

        try:
            submitted_kst_date = _submitted_kst_date(order)
            start_date, end_date = _sync_date_window(
                order,
                now=self.now_provider(),
            )
            try:
                inquiry = self._inquire_daily_order_executions(
                    order_no=order_no,
                    start_date=start_date,
                    end_date=end_date,
                    attempts=attempts,
                    label="first_attempt",
                )
            except Exception as first_exc:
                if _should_retry_submitted_date_only(
                    first_exc,
                    submitted_kst_date=submitted_kst_date,
                    start_date=start_date,
                    end_date=end_date,
                ):
                    start_date = submitted_kst_date
                    end_date = submitted_kst_date
                    inquiry = self._inquire_daily_order_executions(
                        order_no=order_no,
                        start_date=start_date,
                        end_date=end_date,
                        attempts=attempts,
                        label="fallback_attempt",
                    )
                else:
                    raise
            rows = _rows_from_inquiry(inquiry)
            matched = find_kis_order_row(rows, order_no)
            if matched is None:
                mapped = stale_kis_order_status(order_no, _sanitize_payload(inquiry))
                self._apply_stale_result(order, mapped, inquiry, now=now)
            else:
                mapped = map_kis_order_row(
                    matched,
                    requested_qty_fallback=order.requested_qty or order.qty,
                )
                self._apply_mapped_result(order, mapped, inquiry, now=now)
        except Exception as exc:
            order.internal_status = old_status
            order.sync_error = _safe_error(exc)
            order.error_message = order.sync_error
            order.last_synced_at = now
            order.last_sync_payload = json.dumps(
                _sync_failure_payload(
                    exc,
                    order=order,
                    order_no=order_no,
                    start_date=start_date,
                    end_date=end_date,
                    attempts=attempts,
                ),
                ensure_ascii=False,
                default=str,
            )
            db.commit()
            db.refresh(order)
            return order

        db.commit()
        db.refresh(order)
        return order

    def sync_open_orders(self, db: Session) -> list[OrderLog]:
        orders = (
            db.query(OrderLog)
            .filter(OrderLog.broker == "kis")
            .filter(OrderLog.internal_status.in_(sorted(OPEN_KIS_INTERNAL_STATUSES)))
            .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
            .all()
        )
        synced = []
        for order in orders:
            try:
                synced.append(self.sync_order(db, int(order.id)))
            except KisOrderSyncError:
                db.refresh(order)
                synced.append(order)
        return synced

    @staticmethod
    def recent_orders(
        db: Session,
        *,
        limit: int = 20,
        include_rejected: bool = False,
    ) -> list[OrderLog]:
        safe_limit = max(1, min(int(limit or 20), 100))
        query = db.query(OrderLog).filter(OrderLog.broker == "kis")
        if not include_rejected:
            query = query.filter(
                OrderLog.internal_status != InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value
            )
        return query.order_by(OrderLog.created_at.desc(), OrderLog.id.desc()).limit(safe_limit).all()

    def _apply_mapped_result(
        self,
        order: OrderLog,
        mapped,
        inquiry: dict[str, Any],
        *,
        now: datetime,
    ) -> None:
        order.market = order.market or "KR"
        order.kis_odno = mapped.order_no or order.kis_odno or order.broker_order_id
        order.kis_orgn_odno = mapped.original_order_no or order.kis_orgn_odno
        order.broker_order_id = order.broker_order_id or order.kis_odno
        order.requested_qty = mapped.requested_qty or order.requested_qty or order.qty
        order.filled_qty = mapped.filled_qty
        order.remaining_qty = mapped.remaining_qty
        order.avg_fill_price = mapped.avg_fill_price
        order.filled_avg_price = mapped.avg_fill_price
        order.broker_order_status = mapped.broker_order_status
        order.broker_status = mapped.broker_order_status
        order.internal_status = mapped.internal_status
        order.last_synced_at = now
        order.sync_error = None
        order.error_message = None
        order.last_sync_payload = json.dumps(
            {
                "matched_order": _sanitize_payload(mapped.raw_payload),
                "inquiry": _sanitize_payload(inquiry),
            },
            ensure_ascii=False,
            default=str,
        )
        if mapped.internal_status == InternalOrderStatus.FILLED.value and order.filled_at is None:
            order.filled_at = now
        if mapped.internal_status == InternalOrderStatus.CANCELED.value and order.canceled_at is None:
            order.canceled_at = now

    def _apply_stale_result(
        self,
        order: OrderLog,
        mapped,
        inquiry: dict[str, Any],
        *,
        now: datetime,
    ) -> None:
        order.market = order.market or "KR"
        order.internal_status = mapped.internal_status
        order.broker_order_status = mapped.broker_order_status
        order.last_synced_at = now
        order.sync_error = "kis_order_not_found_in_inquiry"
        order.error_message = order.sync_error
        order.last_sync_payload = json.dumps(
            {
                "order_no": mapped.order_no,
                "inquiry": _sanitize_payload(inquiry),
            },
            ensure_ascii=False,
            default=str,
        )

    def _inquire_daily_order_executions(
        self,
        *,
        order_no: str,
        start_date: date,
        end_date: date,
        attempts: list[dict[str, Any]],
        label: str,
    ) -> dict[str, Any]:
        attempt = {
            "label": label,
            "params": _inquiry_attempt_params(
                order_no=order_no,
                start_date=start_date,
                end_date=end_date,
            ),
        }
        attempts.append(attempt)
        try:
            _validate_inquiry_dates(start_date, end_date)
            return self.client.inquire_daily_order_executions(
                order_no=order_no,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:
            attempt["error"] = _exception_payload(exc)
            raise


def serialize_kis_order(order: OrderLog, *, include_sync_payload: bool = False) -> dict[str, Any]:
    requested_qty = order.requested_qty
    if requested_qty is None:
        requested_qty = order.qty
    filled_qty = float(order.filled_qty or 0)
    remaining_qty = order.remaining_qty
    if remaining_qty is None and requested_qty is not None:
        remaining_qty = max(float(requested_qty) - filled_qty, 0)

    internal_status = str(order.internal_status or "").upper()
    payload = {
        "order_id": order.id,
        "broker": order.broker,
        "market": order.market or "KR",
        "symbol": order.symbol,
        "side": order.side,
        "order_type": order.order_type,
        "requested_qty": _nullable_float(requested_qty),
        "filled_qty": filled_qty,
        "remaining_qty": _nullable_float(remaining_qty),
        "avg_fill_price": _nullable_float(order.avg_fill_price or order.filled_avg_price),
        "internal_status": order.internal_status,
        "broker_order_status": order.broker_order_status or order.broker_status,
        "broker_status": order.broker_status,
        "kis_odno": order.kis_odno or order.broker_order_id,
        "kis_orgn_odno": order.kis_orgn_odno,
        "submitted_at": _iso(order.submitted_at),
        "last_synced_at": _iso(order.last_synced_at),
        "sync_error": order.sync_error or order.error_message,
        "is_live_order": bool(str(order.broker or "").lower() == "kis" and (order.kis_odno or order.broker_order_id)),
        "is_terminal": internal_status in {"FILLED", "CANCELLED", "CANCELED", "REJECTED", "FAILED"},
        "is_syncable": internal_status in {"SUBMITTED", "ACCEPTED", "PARTIALLY_FILLED", "UNKNOWN_STALE", "SYNC_FAILED"},
        "display_status": _display_status(internal_status),
    }
    if include_sync_payload and order.last_sync_payload:
        try:
            payload["last_sync_payload"] = _sanitize_payload(json.loads(order.last_sync_payload))
        except Exception:
            payload["last_sync_payload"] = _sanitize_payload(order.last_sync_payload)
    return payload


def _display_status(internal_status: str) -> str:
    mapping = {
        "FILLED": "Filled",
        "PARTIALLY_FILLED": "Partially filled",
        "SUBMITTED": "Submitted",
        "ACCEPTED": "Submitted",
        "UNKNOWN_STALE": "Sync uncertain",
        "FAILED": "Failed",
        "REJECTED_BY_SAFETY_GATE": "Rejected by safety gate",
    }
    return mapping.get(internal_status, internal_status.title().replace("_", " "))


def _order_no(order: OrderLog) -> str | None:
    value = order.kis_odno or order.broker_order_id
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _submitted_kst_date(order: OrderLog) -> date:
    source = order.submitted_at or order.created_at or _now_naive_utc()
    if source.tzinfo is None:
        source = source.replace(tzinfo=UTC)
    return source.astimezone(KR_TZ).date()


def _sync_date_window(order: OrderLog, *, now: datetime | None = None) -> tuple[date, date]:
    submitted_date = _submitted_kst_date(order)
    current = now or datetime.now(KR_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KR_TZ)
    current_date = current.astimezone(KR_TZ).date()

    if (
        current_date > submitted_date
        and _is_valid_order_inquiry_date(submitted_date)
        and _is_valid_order_inquiry_date(current_date)
    ):
        return submitted_date, current_date
    return submitted_date, submitted_date


def _inquiry_attempt_params(
    *,
    order_no: str,
    start_date: date,
    end_date: date,
) -> dict[str, str]:
    return {
        "ODNO": order_no,
        "INQR_STRT_DT": start_date.strftime("%Y%m%d"),
        "INQR_END_DT": end_date.strftime("%Y%m%d"),
    }


def _validate_inquiry_dates(start_date: date, end_date: date) -> None:
    start_text = start_date.strftime("%Y%m%d")
    end_text = end_date.strftime("%Y%m%d")
    parsed_start = datetime.strptime(start_text, "%Y%m%d").date()
    parsed_end = datetime.strptime(end_text, "%Y%m%d").date()

    if parsed_start != start_date or parsed_end != end_date:
        raise KisOrderSyncError("invalid_kis_inquiry_date_format")
    if start_date > end_date:
        raise KisOrderSyncError("invalid_kis_inquiry_date_range: start_date_after_end_date")

    weekend_dates = [
        item.strftime("%Y%m%d")
        for item in (start_date, end_date)
        if not _is_valid_order_inquiry_date(item)
    ]
    if weekend_dates:
        raise KisOrderSyncError(
            f"invalid_kis_inquiry_date: weekend_endpoint_date={','.join(weekend_dates)}"
        )


def _is_valid_order_inquiry_date(value: date) -> bool:
    return value.weekday() < 5


def _should_retry_submitted_date_only(
    exc: Exception,
    *,
    submitted_kst_date: date,
    start_date: date,
    end_date: date,
) -> bool:
    if start_date == submitted_kst_date and end_date == submitted_kst_date:
        return False
    return _is_kis_date_error(exc)


def _is_kis_date_error(exc: Exception) -> bool:
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        msg_cd = str(details.get("msg_cd") or "").strip()
        msg1 = str(details.get("msg1") or "")
        if msg_cd == "KIER2570" or "\uc870\ud68c\uc77c\uc790" in msg1:
            return True
    return "\uc870\ud68c\uc77c\uc790" in str(exc)


def _rows_from_inquiry(inquiry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = inquiry.get("orders") or inquiry.get("output1") or inquiry.get("output") or []
    if isinstance(rows, dict):
        return [rows]
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def _now_naive_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _nullable_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _safe_error(exc: Exception) -> str:
    text = _sanitize_text(str(exc).strip() or exc.__class__.__name__)
    if len(text) > 500:
        text = f"{text[:500]}..."
    return f"kis_order_sync_error: {exc.__class__.__name__}: {text}"


def _sync_failure_payload(
    exc: Exception,
    *,
    order: OrderLog,
    order_no: str,
    start_date: date | None,
    end_date: date | None,
    attempts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    error_details = getattr(exc, "details", None)
    safe_attempts = _sanitize_payload(attempts or [])
    first_attempt = _attempt_by_label(safe_attempts, "first_attempt")
    fallback_attempt = _attempt_by_label(safe_attempts, "fallback_attempt")
    final_error = _exception_payload(exc)
    payload = {
        "event": "kis_order_sync_failed",
        "error_type": exc.__class__.__name__,
        "error_message": _safe_error(exc),
        "order": {
            "order_id": order.id,
            "broker": order.broker,
            "market": order.market or "KR",
            "symbol": order.symbol,
            "side": order.side,
            "kis_odno": order_no,
            "internal_status_preserved": order.internal_status,
        },
        "request": (
            first_attempt.get("params")
            if first_attempt
            else {
                "ODNO": order_no,
                "INQR_STRT_DT": start_date.strftime("%Y%m%d") if start_date else None,
                "INQR_END_DT": end_date.strftime("%Y%m%d") if end_date else None,
            }
        ),
        "first_attempt": first_attempt,
        "fallback_attempt": fallback_attempt,
        "attempts": safe_attempts,
        "final_error": final_error,
    }
    for key in ("rt_cd", "msg_cd", "msg1", "tr_id", "path"):
        value = final_error.get(key)
        if value is not None:
            payload[key] = value
    if isinstance(error_details, dict):
        payload["kis_error"] = error_details
    return _sanitize_payload(payload)


def _attempt_by_label(
    attempts: list[dict[str, Any]],
    label: str,
) -> dict[str, Any] | None:
    for attempt in attempts:
        if attempt.get("label") == label:
            return attempt
    return None


def _exception_payload(exc: Exception) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error_type": exc.__class__.__name__,
        "error_message": _safe_error(exc),
    }
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        payload.update(details)
    return _sanitize_payload(payload)


def _sanitize_payload(value: Any) -> Any:
    return sanitize_kis_payload(value)


def _sanitize_text(value: str) -> str:
    return sanitize_kis_text(value)
