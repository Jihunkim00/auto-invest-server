from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db.models import StrategyAutoBuyPromotion
from app.services.kis_payload_sanitizer import sanitize_kis_payload


PROVIDER = "kis"
MARKET = "KR"
KST = ZoneInfo("Asia/Seoul")
ACTIVE_STATUSES = {"pending", "acknowledged"}


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
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return {
            "status": row.status,
            "promotion": self.item(row),
            "safety": _safety(read_only=False),
        }

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
                "request_payload": _parse_object(row.request_payload),
                "response_payload": _parse_object(row.response_payload),
                "created_at": _iso(row.created_at),
                "updated_at": _iso(row.updated_at),
            }
        )

    def _row(self, db: Session, promotion_id: int) -> StrategyAutoBuyPromotion:
        row = db.get(StrategyAutoBuyPromotion, int(promotion_id))
        if row is None:
            raise ValueError("promotion_not_found")
        return row


def _expired(row: StrategyAutoBuyPromotion, now_utc: datetime) -> bool:
    if row.expires_at is None:
        return False
    return _aware_utc(row.expires_at) <= now_utc


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

