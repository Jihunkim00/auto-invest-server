from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import StrategyAutoBuyPromotion
from app.services.kis_payload_sanitizer import sanitize_kis_payload


PROVIDER = "kis"
MARKET = "KR"
KST = ZoneInfo("Asia/Seoul")
ACTIVE_STATUSES = {"pending", "acknowledged"}
CONVERTED_STATUSES = {
    "converted_to_live_attempt",
    "live_order_created",
    "live_order_synced",
    "live_order_rejected",
    "live_order_filled",
}
FINAL_STATUSES = {
    *CONVERTED_STATUSES,
    "dismissed",
    "expired",
    "conversion_blocked",
}


class StrategyAutoBuyPromotionService:
    """Local promotion queue for scheduler-discovered dry-run would_buy results."""

    def create_from_dry_run(
        self,
        db: Session,
        *,
        dry_run_result: dict[str, Any],
        request_payload: dict[str, Any] | None = None,
        ttl_minutes: int = 45,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        result = sanitize_kis_payload(dict(dry_run_result or {}))
        if str(result.get("action") or "") != "would_buy":
            raise ValueError("promotion_requires_would_buy")
        trade_run_id = _int(result.get("trade_run_id"))
        if trade_run_id is not None:
            existing = (
                db.query(StrategyAutoBuyPromotion)
                .filter(
                    StrategyAutoBuyPromotion.source_dry_run_trade_run_id
                    == trade_run_id
                )
                .order_by(
                    StrategyAutoBuyPromotion.created_at.desc(),
                    StrategyAutoBuyPromotion.id.desc(),
                )
                .first()
            )
            if existing is not None:
                return self.item(existing)

        now_utc = _aware_utc(now)
        row = StrategyAutoBuyPromotion(
            provider=str(result.get("provider") or PROVIDER).lower(),
            market=str(result.get("market") or MARKET).upper(),
            active_profile=_text(result.get("active_profile")),
            symbol=_text(result.get("selected_symbol") or result.get("symbol")),
            symbol_name=_text(
                result.get("selected_symbol_name") or result.get("symbol_name")
            ),
            status="pending",
            promotion_reason=_text(
                result.get("reason") or "scheduler_dry_run_would_buy"
            ),
            source_dry_run_signal_id=_int(result.get("signal_id")),
            source_dry_run_trade_run_id=trade_run_id,
            source_dry_run_order_id=_int(result.get("simulated_order_id")),
            dry_run_action=_text(result.get("action")),
            buy_score=_float(result.get("buy_score")),
            sell_score=_float(result.get("sell_score")),
            final_score=_float(result.get("final_score")),
            confidence=_float(result.get("confidence")),
            recommended_notional_krw=_float(result.get("recommended_notional_krw")),
            simulated_quantity=_float(result.get("simulated_quantity")),
            simulated_price=_float(result.get("simulated_price")),
            simulated_notional_krw=_float(result.get("simulated_notional_krw")),
            target_risk_result=_json(result.get("target_risk_result") or {}),
            block_reason=_text(result.get("block_reason")),
            risk_flags=_json(_strings(result.get("risk_flags"))),
            gating_notes=_json(_strings(result.get("gating_notes"))),
            expires_at=_naive_utc(now_utc + timedelta(minutes=max(1, int(ttl_minutes)))),
            request_payload=_json(request_payload or {}),
            response_payload=_json(result),
            created_at=_naive_utc(now_utc),
            updated_at=_naive_utc(now_utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return self.item(row)

    def list(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
        status: str | None = None,
        symbol: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        query = (
            db.query(StrategyAutoBuyPromotion)
            .filter(StrategyAutoBuyPromotion.provider == str(provider).lower())
            .filter(StrategyAutoBuyPromotion.market == str(market).upper())
        )
        normalized_status = _text(status)
        if normalized_status:
            query = query.filter(StrategyAutoBuyPromotion.status == normalized_status)
        normalized_symbol = _text(symbol)
        if normalized_symbol:
            query = query.filter(
                StrategyAutoBuyPromotion.symbol == normalized_symbol.upper()
            )
        rows = (
            query.order_by(
                StrategyAutoBuyPromotion.created_at.desc(),
                StrategyAutoBuyPromotion.id.desc(),
            )
            .limit(max(1, min(int(limit or 20), 100)))
            .all()
        )
        return {
            "provider": str(provider).lower(),
            "market": str(market).upper(),
            "count": len(rows),
            "items": [self.item(row) for row in rows],
            "safety": _safety(read_only=True),
        }

    def acknowledge(self, db: Session, promotion_id: int) -> dict[str, Any]:
        row = self._row(db, promotion_id)
        now = _naive_utc(datetime.now(UTC))
        if row.status == "pending":
            row.status = "acknowledged"
            row.acknowledged_at = now
            row.updated_at = now
            db.commit()
            db.refresh(row)
        return {
            "status": row.status,
            "promotion": self.item(row),
            "safety": _safety(read_only=False),
        }

    def dismiss(self, db: Session, promotion_id: int) -> dict[str, Any]:
        row = self._row(db, promotion_id)
        now = _naive_utc(datetime.now(UTC))
        row.status = "dismissed"
        row.dismissed_at = now
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return {
            "status": row.status,
            "promotion": self.item(row),
            "safety": _safety(read_only=False),
        }

    def mark_converted(
        self,
        db: Session,
        promotion_id: int,
        *,
        promoted_to_live_attempt_id: int | None = None,
        related_live_order_id: int | None = None,
    ) -> dict[str, Any]:
        row = self._row(db, promotion_id)
        now = _naive_utc(datetime.now(UTC))
        row.status = "converted_to_live_attempt"
        row.promoted_to_live_attempt_id = promoted_to_live_attempt_id
        row.related_live_order_id = related_live_order_id
        row.converted_live_attempt_id = promoted_to_live_attempt_id
        row.converted_order_id = related_live_order_id
        row.converted_at = now
        row.conversion_status = "converted_to_live_attempt"
        row.trace_payload_json = _json(self.trace_payload(row))
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return {
            "status": row.status,
            "promotion": self.item(row),
            "safety": _safety(read_only=False),
        }

    def prepare_live_conversion(
        self,
        db: Session,
        *,
        promotion_id: int,
        provider: str,
        market: str,
        symbol: str | None,
        source_dry_run_id: int | None,
        active_profile: str | None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        row = self._row(db, promotion_id)
        now_utc = _aware_utc(now)
        normalized_provider = str(provider or PROVIDER).strip().lower()
        normalized_market = str(market or MARKET).strip().upper()
        normalized_symbol = _text(symbol)
        normalized_profile = _text(active_profile)

        if str(row.provider or "").lower() != normalized_provider or str(row.market or "").upper() != normalized_market:
            return self._conversion_block("promotion_scope_mismatch", row)

        if row.status == "pending" and _expired(row, now_utc):
            row.status = "expired"
            row.updated_at = _naive_utc(now_utc)
            db.commit()
            db.refresh(row)
            return self._conversion_block("promotion_expired", row)

        if _already_converted(row):
            return self._conversion_block("promotion_already_converted", row)
        if row.status != "pending":
            return self._conversion_block(_status_block_reason(row.status), row)

        row_symbol = _text(row.symbol)
        if normalized_symbol and row_symbol and normalized_symbol.upper() != row_symbol.upper():
            return self._conversion_block("promotion_symbol_mismatch", row)

        row_source_dry_run_id = _int(row.source_dry_run_trade_run_id)
        if (
            source_dry_run_id is not None
            and row_source_dry_run_id is not None
            and int(source_dry_run_id) != row_source_dry_run_id
        ):
            return self._conversion_block("promotion_source_dry_run_mismatch", row)

        row_profile = _text(row.active_profile)
        if normalized_profile and row_profile and normalized_profile != row_profile:
            return self._conversion_block("promotion_profile_mismatch", row)

        return {
            "accepted": True,
            "promotion_id": row.id,
            "row": row,
            "source_dry_run_id": row_source_dry_run_id or source_dry_run_id,
            "symbol": row_symbol or normalized_symbol,
            "trace": self.trace_payload(row),
        }

    def mark_conversion_blocked(
        self,
        db: Session,
        *,
        promotion_id: int,
        live_attempt_id: int | None,
        block_reason: str,
        trace: dict[str, Any] | None = None,
    ) -> None:
        row = self._row(db, promotion_id)
        if row.status != "pending":
            return
        now = _naive_utc(datetime.now(UTC))
        row.status = "conversion_blocked"
        row.block_reason = _text(block_reason)
        row.converted_live_attempt_id = live_attempt_id
        row.promoted_to_live_attempt_id = live_attempt_id
        row.converted_at = now
        row.conversion_status = "conversion_blocked"
        row.trace_payload_json = _json(
            {
                **self.trace_payload(row),
                **(trace or {}),
                "conversion_status": "conversion_blocked",
                "block_reason": block_reason,
            }
        )
        row.updated_at = now
        db.commit()

    def mark_live_order_created(
        self,
        db: Session,
        *,
        promotion_id: int,
        live_attempt_id: int,
        order_id: int | None,
        trace: dict[str, Any] | None = None,
    ) -> None:
        row = self._row(db, promotion_id)
        now = _naive_utc(datetime.now(UTC))
        row.status = "live_order_created"
        row.promoted_to_live_attempt_id = live_attempt_id
        row.related_live_order_id = order_id
        row.converted_live_attempt_id = live_attempt_id
        row.converted_order_id = order_id
        row.converted_at = row.converted_at or now
        row.conversion_status = "live_order_created"
        row.trace_payload_json = _json(
            {
                **self.trace_payload(row),
                **(trace or {}),
                "conversion_status": "live_order_created",
            }
        )
        row.updated_at = now
        db.commit()

    def mark_live_sync(
        self,
        db: Session,
        *,
        live_attempt_id: int | None,
        order_id: int | None,
        sync_status: str,
        trace: dict[str, Any] | None = None,
    ) -> None:
        row = self._row_for_live_link(
            db,
            live_attempt_id=live_attempt_id,
            order_id=order_id,
        )
        if row is None:
            return
        now = _naive_utc(datetime.now(UTC))
        row.status = _promotion_status_from_sync(sync_status)
        row.last_sync_at = now
        row.last_sync_status = _text(sync_status)
        row.conversion_status = _text(sync_status)
        row.trace_payload_json = _json(
            {
                **self.trace_payload(row),
                **(trace or {}),
                "last_sync_status": sync_status,
            }
        )
        row.updated_at = now
        db.commit()

    def summary(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        rows = (
            db.query(StrategyAutoBuyPromotion)
            .filter(StrategyAutoBuyPromotion.provider == str(provider).lower())
            .filter(StrategyAutoBuyPromotion.market == str(market).upper())
            .order_by(
                StrategyAutoBuyPromotion.created_at.desc(),
                StrategyAutoBuyPromotion.id.desc(),
            )
            .limit(100)
            .all()
        )
        now_utc = _aware_utc(now)
        today = now_utc.astimezone(KST).date()
        latest = rows[0] if rows else None
        return {
            "pending_count": sum(
                1
                for row in rows
                if row.status == "pending" and not _expired(row, now_utc)
            ),
            "latest_symbol": latest.symbol if latest is not None else None,
            "latest_status": (
                "expired"
                if latest is not None and latest.status == "pending" and _expired(latest, now_utc)
                else latest.status
                if latest is not None
                else None
            ),
            "latest_expires_at": _iso(latest.expires_at) if latest is not None else None,
            "acknowledged_count_today": sum(
                1
                for row in rows
                if row.acknowledged_at is not None
                and _aware_utc(row.acknowledged_at).astimezone(KST).date() == today
            ),
            "dismissed_count_today": sum(
                1
                for row in rows
                if row.dismissed_at is not None
                and _aware_utc(row.dismissed_at).astimezone(KST).date() == today
            ),
            "safety": _safety(read_only=True),
        }

    def item(self, row: StrategyAutoBuyPromotion) -> dict[str, Any]:
        return sanitize_kis_payload(
            {
                "id": row.id,
                "provider": row.provider,
                "market": row.market,
                "active_profile": row.active_profile,
                "symbol": row.symbol,
                "symbol_name": row.symbol_name,
                "status": row.status,
                "promotion_reason": row.promotion_reason,
                "source_dry_run_signal_id": row.source_dry_run_signal_id,
                "source_dry_run_trade_run_id": row.source_dry_run_trade_run_id,
                "source_dry_run_order_id": row.source_dry_run_order_id,
                "dry_run_action": row.dry_run_action,
                "buy_score": row.buy_score,
                "sell_score": row.sell_score,
                "final_score": row.final_score,
                "confidence": row.confidence,
                "recommended_notional_krw": row.recommended_notional_krw,
                "simulated_quantity": row.simulated_quantity,
                "simulated_price": row.simulated_price,
                "simulated_notional_krw": row.simulated_notional_krw,
                "target_risk_result": _parse_object(row.target_risk_result),
                "block_reason": row.block_reason,
                "risk_flags": _parse_list(row.risk_flags),
                "gating_notes": _parse_list(row.gating_notes),
                "expires_at": _iso(row.expires_at),
                "acknowledged_at": _iso(row.acknowledged_at),
                "dismissed_at": _iso(row.dismissed_at),
                "promoted_to_live_attempt_id": row.promoted_to_live_attempt_id,
                "related_live_order_id": row.related_live_order_id,
                "converted_live_attempt_id": row.converted_live_attempt_id,
                "converted_order_id": row.converted_order_id,
                "converted_at": _iso(row.converted_at),
                "conversion_status": row.conversion_status,
                "last_sync_at": _iso(row.last_sync_at),
                "last_sync_status": row.last_sync_status,
                "trace_payload": _parse_object(row.trace_payload_json)
                or self.trace_payload(row),
                "request_payload": _parse_object(row.request_payload),
                "response_payload": _parse_object(row.response_payload),
                "created_at": _iso(row.created_at),
                "updated_at": _iso(row.updated_at),
            }
        )

    def trace_payload(
        self,
        row: StrategyAutoBuyPromotion,
        *,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        score = row.final_score if row.final_score is not None else row.buy_score
        payload = {
            "promotion_id": row.id,
            "source_dry_run_id": row.source_dry_run_trade_run_id,
            "source_signal_id": row.source_dry_run_signal_id,
            "source_trade_run_id": row.source_dry_run_trade_run_id,
            "promotion_created_at": _iso(row.created_at),
            "promotion_symbol": row.symbol,
            "promotion_profile": row.active_profile,
            "promotion_score": score,
            "final_buy_score": row.final_score,
            "promotion_reason": row.promotion_reason,
            "promotion_status": row.status,
            "converted_live_attempt_id": row.converted_live_attempt_id
            or row.promoted_to_live_attempt_id,
            "converted_order_id": row.converted_order_id or row.related_live_order_id,
            "converted_at": _iso(row.converted_at),
            "conversion_status": row.conversion_status,
            "last_sync_at": _iso(row.last_sync_at),
            "last_sync_status": row.last_sync_status,
        }
        if extra:
            payload.update(extra)
        return sanitize_kis_payload(payload)

    def _row(self, db: Session, promotion_id: int) -> StrategyAutoBuyPromotion:
        row = db.get(StrategyAutoBuyPromotion, int(promotion_id))
        if row is None:
            raise ValueError("promotion_not_found")
        return row

    def _row_for_live_link(
        self,
        db: Session,
        *,
        live_attempt_id: int | None,
        order_id: int | None,
    ) -> StrategyAutoBuyPromotion | None:
        query = db.query(StrategyAutoBuyPromotion)
        filters = []
        if live_attempt_id is not None:
            filters.extend(
                [
                    StrategyAutoBuyPromotion.converted_live_attempt_id
                    == int(live_attempt_id),
                    StrategyAutoBuyPromotion.promoted_to_live_attempt_id
                    == int(live_attempt_id),
                ]
            )
        if order_id is not None:
            filters.extend(
                [
                    StrategyAutoBuyPromotion.converted_order_id == int(order_id),
                    StrategyAutoBuyPromotion.related_live_order_id == int(order_id),
                ]
            )
        if not filters:
            return None
        return query.filter(or_(*filters)).first()

    def _conversion_block(
        self,
        block_reason: str,
        row: StrategyAutoBuyPromotion,
    ) -> dict[str, Any]:
        return {
            "accepted": False,
            "promotion_id": row.id,
            "block_reason": block_reason,
            "trace": self.trace_payload(row, extra={"block_reason": block_reason}),
        }


def _expired(row: StrategyAutoBuyPromotion, now_utc: datetime) -> bool:
    if row.expires_at is None:
        return False
    return _aware_utc(row.expires_at) <= now_utc


def _already_converted(row: StrategyAutoBuyPromotion) -> bool:
    return (
        row.status in CONVERTED_STATUSES
        or row.converted_live_attempt_id is not None
        or row.converted_order_id is not None
        or row.promoted_to_live_attempt_id is not None
        or row.related_live_order_id is not None
    )


def _status_block_reason(status: str | None) -> str:
    normalized = str(status or "").strip()
    if normalized == "dismissed":
        return "promotion_dismissed"
    if normalized == "expired":
        return "promotion_expired"
    if normalized in CONVERTED_STATUSES:
        return "promotion_already_converted"
    if normalized == "conversion_blocked":
        return "promotion_conversion_blocked"
    return "promotion_not_pending"


def _promotion_status_from_sync(sync_status: str) -> str:
    normalized = str(sync_status or "").strip().lower()
    if normalized == "filled":
        return "live_order_filled"
    if normalized in {"rejected", "failed"}:
        return "live_order_rejected"
    return "live_order_synced"


def _safety(*, read_only: bool) -> dict[str, Any]:
    return {
        "read_only": read_only,
        "real_order_submitted": False,
        "validation_called": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "setting_changed": False,
        "scheduler_changed": False,
        "live_order_action_created": False,
    }


def _json(value: Any) -> str:
    return json.dumps(sanitize_kis_payload(value), ensure_ascii=False, default=str)


def _parse_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _parse_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(UTC)
    return value.replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _aware_utc(value).isoformat()

