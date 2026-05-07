from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog
from app.services.kis_payload_sanitizer import sanitize_kis_payload, sanitize_kis_text
from app.services.runtime_setting_service import RuntimeSettingService

TERMINAL_CANCEL_STATUSES = {
    InternalOrderStatus.FILLED.value,
    InternalOrderStatus.REJECTED.value,
    InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value,
    InternalOrderStatus.CANCELED.value,
    "CANCELLED",
    InternalOrderStatus.FAILED.value,
}

CANCEL_SYNCABLE_STATUSES = {
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
}


class KisManualCancelService:
    """Manual-only cancel support for existing KIS orders."""

    def __init__(
        self,
        client: KisClient,
        *,
        runtime_settings: RuntimeSettingService | None = None,
    ):
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()

    def cancel_order(self, db: Session, order_id: int) -> tuple[int, dict[str, Any]]:
        order = db.get(OrderLog, order_id)
        if order is None:
            return 404, {
                "canceled": False,
                "order_id": order_id,
                "message": "KIS order not found.",
            }

        if str(order.broker or "").strip().lower() != "kis":
            return 400, {
                "canceled": False,
                "order_id": order.id,
                "internal_status": order.internal_status,
                "broker_status": order.broker_status,
                "message": "Only KIS orders can be canceled.",
            }

        order_no = _order_no(order)
        if not order_no:
            body = self._blocked_response(
                order,
                message="KIS ODNO is required to cancel.",
            )
            self._record_event(
                order,
                "kis_order_cancel_blocked",
                {"reason": "kis_odno_missing", "response": body},
            )
            db.commit()
            return 409, body

        if _is_terminal(order):
            body = self._blocked_response(
                order,
                message="Terminal orders cannot be canceled.",
            )
            self._record_event(
                order,
                "kis_order_cancel_blocked",
                {"reason": "terminal_order", "response": body},
            )
            db.commit()
            return 409, body

        if not _is_cancel_syncable(order):
            body = self._blocked_response(
                order,
                message="Only open syncable KIS orders can be canceled.",
            )
            self._record_event(
                order,
                "kis_order_cancel_blocked",
                {"reason": "non_syncable_order", "response": body},
            )
            db.commit()
            return 409, body

        runtime = self.runtime_settings.get_settings(db)
        if bool(runtime.get("kill_switch", False)):
            body = self._blocked_response(
                order,
                message="Kill switch is ON.",
            )
            self._record_event(
                order,
                "kis_order_cancel_blocked",
                {"reason": "kill_switch_enabled", "response": body},
            )
            db.commit()
            return 409, body

        qty = _cancel_qty(order)
        request_payload = _safe_call(
            lambda: self.client.build_domestic_cancel_payload(
                order_no=order_no,
                qty=qty,
            ),
            settings=self.client.settings,
        )

        try:
            broker_response = self.client.cancel_domestic_cash_order(
                order_no=order_no,
                qty=qty,
            )
        except Exception as exc:
            safe_error = _safe_error(exc, self.client.settings)
            raw_payload = _sanitize_payload(
                {
                    "request": request_payload,
                    "error": _exception_payload(exc, settings=self.client.settings),
                },
                settings=self.client.settings,
            )
            order.error_message = safe_error
            order.sync_error = safe_error
            order.last_synced_at = _now_naive_utc()
            self._record_event(
                order,
                "kis_order_cancel_failed",
                raw_payload,
                update_timestamp=False,
            )
            db.commit()
            db.refresh(order)
            return 502, {
                "canceled": False,
                "order_id": order.id,
                "kis_odno": order_no,
                "internal_status": order.internal_status,
                "broker_status": order.broker_status,
                "message": "KIS order cancel failed.",
                "raw_payload": raw_payload,
            }

        safe_response = _sanitize_payload(
            broker_response,
            settings=self.client.settings,
        )
        raw_payload = _sanitize_payload(
            {
                "request": request_payload,
                "response": safe_response,
            },
            settings=self.client.settings,
        )
        now = _now_naive_utc()

        if _cancel_confirmed(broker_response):
            order.internal_status = InternalOrderStatus.CANCELED.value
            order.broker_status = InternalOrderStatus.CANCELED.value
            order.broker_order_status = InternalOrderStatus.CANCELED.value
            order.canceled_at = order.canceled_at or now
            order.last_synced_at = now
            order.sync_error = None
            order.error_message = None
            self._record_event(
                order,
                "kis_order_cancel_success",
                raw_payload,
                update_timestamp=False,
            )
            db.commit()
            db.refresh(order)
            return 200, {
                "canceled": True,
                "order_id": order.id,
                "kis_odno": order_no,
                "internal_status": order.internal_status,
                "broker_status": order.broker_status,
                "message": "KIS order canceled.",
                "raw_payload": raw_payload,
            }

        order.last_synced_at = now
        self._record_event(
            order,
            "kis_order_cancel_unconfirmed",
            raw_payload,
            update_timestamp=False,
        )
        db.commit()
        db.refresh(order)
        return 200, {
            "canceled": False,
            "order_id": order.id,
            "kis_odno": order_no,
            "internal_status": order.internal_status,
            "broker_status": order.broker_status,
            "message": "KIS order cancel was not confirmed.",
            "raw_payload": raw_payload,
        }

    @staticmethod
    def _blocked_response(order: OrderLog, *, message: str) -> dict[str, Any]:
        return {
            "canceled": False,
            "order_id": order.id,
            "kis_odno": _order_no(order),
            "internal_status": order.internal_status,
            "broker_status": order.broker_status,
            "message": message,
        }

    @staticmethod
    def _record_event(
        order: OrderLog,
        event: str,
        payload: dict[str, Any],
        *,
        update_timestamp: bool = True,
    ) -> None:
        if update_timestamp:
            order.last_synced_at = _now_naive_utc()
        order.last_sync_payload = json.dumps(
            _sanitize_payload(
                {
                    "event": event,
                    "order": {
                        "order_id": order.id,
                        "broker": order.broker,
                        "market": order.market or "KR",
                        "symbol": order.symbol,
                        "side": order.side,
                        "kis_odno": _order_no(order),
                        "internal_status": order.internal_status,
                        "broker_status": order.broker_status,
                    },
                    "payload": payload,
                }
            ),
            ensure_ascii=False,
            default=str,
        )


def _order_no(order: OrderLog) -> str | None:
    value = order.kis_odno or order.broker_order_id
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _status(order: OrderLog) -> str:
    return str(order.internal_status or "").strip().upper()


def _is_terminal(order: OrderLog) -> bool:
    return _status(order) in TERMINAL_CANCEL_STATUSES


def _is_cancel_syncable(order: OrderLog) -> bool:
    return _status(order) in CANCEL_SYNCABLE_STATUSES


def _cancel_qty(order: OrderLog) -> int | None:
    for value in (order.remaining_qty, order.requested_qty, order.qty):
        if value is None:
            continue
        try:
            numeric = int(float(value))
        except (TypeError, ValueError):
            continue
        if numeric > 0:
            return numeric
    return None


def _cancel_confirmed(response: dict[str, Any]) -> bool:
    rt_cd = str(response.get("rt_cd", "0")).strip()
    return rt_cd in {"", "0"}


def _safe_call(func, *, settings=None):
    try:
        return _sanitize_payload(func(), settings=settings)
    except Exception as exc:
        return {"error": _safe_error(exc, settings)}


def _exception_payload(exc: Exception, *, settings=None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error_type": exc.__class__.__name__,
        "error_message": _safe_error(exc, settings),
    }
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        payload.update(details)
    return _sanitize_payload(payload, settings=settings)


def _safe_error(exc: Exception, settings=None) -> str:
    text = _sanitize_text(str(exc).strip() or exc.__class__.__name__, settings=settings)
    if len(text) > 500:
        text = f"{text[:500]}..."
    return f"kis_order_cancel_error: {exc.__class__.__name__}: {text}"


def _sanitize_payload(value: Any, *, settings=None) -> Any:
    return sanitize_kis_payload(
        value,
        known_secrets=_known_sensitive_values(settings),
    )


def _sanitize_text(value: str, *, settings=None) -> str:
    return sanitize_kis_text(
        value,
        known_secrets=_known_sensitive_values(settings),
    )


def _known_sensitive_values(settings) -> list:
    if settings is None:
        return []
    return [
        getattr(settings, "kis_app_key", None),
        getattr(settings, "kis_app_secret", None),
        getattr(settings, "kis_access_token", None),
        getattr(settings, "kis_approval_key", None),
        getattr(settings, "kis_account_no", None),
    ]


def _now_naive_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
