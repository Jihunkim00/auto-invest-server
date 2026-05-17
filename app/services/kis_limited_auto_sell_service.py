from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.brokers.kis_broker import KisBroker
from app.brokers.kis_client import KisClient, to_float
from app.core.enums import InternalOrderStatus
from app.db.models import KisShadowExitReviewQueueState, OrderLog, SignalLog, TradeRunLog
from app.services.kis_dry_run_risk_service import (
    MARKET,
    OPEN_ORDER_STATUSES,
    PROVIDER,
    SELL,
    position_exit_threshold_reasons,
    position_pl_diagnostics,
)
from app.services.kis_order_audit import (
    LIMITED_AUTO_SELL_SOURCE,
    LIMITED_AUTO_SELL_SOURCE_TYPE,
    kis_order_source_fields,
)
from app.services.kis_order_sync_service import KisOrderSyncService, serialize_kis_order
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "limited_auto_sell"
SOURCE = LIMITED_AUTO_SELL_SOURCE
SOURCE_TYPE = LIMITED_AUTO_SELL_SOURCE_TYPE
TRIGGER_SOURCE = "kis_limited_auto_sell"
SHADOW_MODE = "shadow_exit_dry_run"
SHADOW_TRIGGER_SOURCE = "shadow_exit"
STOP_LOSS_TRIGGER = "stop_loss"
TAKE_PROFIT_TRIGGER = "take_profit"
MANUAL_REVIEW_TRIGGER = "manual_review"
KR_TZ = ZoneInfo("Asia/Seoul")

SUBMITTED_STATUSES = {
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}


@dataclass(frozen=True)
class _AutoSellCandidate:
    symbol: str
    qty: int
    held_qty: float
    current_price: float
    notional: float
    trigger: str
    trigger_source: str
    reason: str
    risk_flags: list[str]
    gating_notes: list[str]
    diagnostics: dict[str, Any]
    position: dict[str, Any]


class KisLimitedAutoSellService:
    """Guarded, disabled-by-default KIS SELL-only auto execution path."""

    def __init__(
        self,
        client: KisClient,
        *,
        broker: KisBroker | None = None,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
    ):
        self.client = client
        self.broker = broker or KisBroker(client)
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()

    def run_once(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc_now(now)
        created_at = now_utc.isoformat()
        runtime = self.runtime_settings.get_settings(db)
        settings = self.client.settings
        market_session = self._market_session(now_utc)
        checks = self._base_checks(runtime, settings, market_session)
        safety = _safety(runtime)

        preliminary_reason = _first_failed_preliminary_reason(checks)
        if preliminary_reason:
            return self._blocked(
                db,
                reason=preliminary_reason,
                checks=checks,
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                blocked_by=[preliminary_reason],
            )

        account_state = self._fetch_account_state(db)
        checks.update(
            {
                "account_state_available": bool(account_state.get("fetch_success")),
                "positions_available": bool(account_state.get("positions")),
                "open_order_fetch_available": "open_orders_unavailable"
                not in _warning_names(account_state),
            }
        )
        if checks["account_state_available"] is not True:
            return self._blocked(
                db,
                reason="broker_account_state_unavailable",
                checks=checks,
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                account_state=account_state,
                blocked_by=["broker_account_state_unavailable"],
            )

        candidate, candidate_block = self._select_candidate(
            db,
            runtime=runtime,
            account_state=account_state,
        )
        if candidate is None:
            reason = candidate_block or "no_stop_loss_candidate"
            return self._blocked(
                db,
                reason=reason,
                checks=checks,
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                account_state=account_state,
                blocked_by=[reason],
            )

        limit_reason = self._trade_limit_reason(db, now_utc=now_utc, runtime=runtime)
        if limit_reason:
            return self._blocked(
                db,
                reason=limit_reason,
                checks={**checks, "daily_limited_auto_sell_limit": False},
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                account_state=account_state,
                candidate=candidate,
                blocked_by=[limit_reason],
            )
        checks["daily_limited_auto_sell_limit"] = True

        duplicate_reason = self._duplicate_order_reason(
            db,
            candidate=candidate,
            account_state=account_state,
            now_utc=now_utc,
            runtime=runtime,
        )
        if duplicate_reason:
            return self._blocked(
                db,
                reason=duplicate_reason,
                checks={**checks, "duplicate_order_check": False},
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                account_state=account_state,
                candidate=candidate,
                blocked_by=[duplicate_reason],
            )
        checks["duplicate_order_check"] = True

        queue_status = self._queue_review_status(db, candidate)
        checks["queue_review_required"] = bool(
            runtime.get("kis_limited_auto_sell_requires_queue_review", True)
        )
        checks["queue_item_reviewed"] = queue_status == "reviewed"
        if checks["queue_review_required"] and queue_status != "reviewed":
            return self._blocked(
                db,
                reason="queue_review_required",
                checks=checks,
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                account_state=account_state,
                candidate=candidate,
                blocked_by=["queue_review_required"],
                queue_review_status=queue_status,
            )

        shadow_count = self._shadow_occurrence_count(db, candidate)
        min_occurrences = max(
            0,
            int(runtime.get("kis_limited_auto_sell_min_shadow_occurrences", 1) or 0),
        )
        checks["shadow_occurrence_count"] = shadow_count
        checks["min_shadow_occurrences_met"] = shadow_count >= min_occurrences
        if shadow_count < min_occurrences:
            return self._blocked(
                db,
                reason="min_shadow_occurrences_not_met",
                checks=checks,
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                account_state=account_state,
                candidate=candidate,
                blocked_by=["min_shadow_occurrences_not_met"],
                queue_review_status=queue_status,
            )

        try:
            return self._submit_sell(
                db,
                candidate=candidate,
                checks=checks,
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                queue_review_status=queue_status,
                shadow_occurrence_count=shadow_count,
            )
        except Exception as exc:
            return self._submission_failed(
                db,
                candidate=candidate,
                checks=checks,
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                queue_review_status=queue_status,
                shadow_occurrence_count=shadow_count,
                error=exc,
            )

    def _base_checks(
        self,
        runtime: dict[str, Any],
        settings: Any,
        market_session: dict[str, Any],
    ) -> dict[str, Any]:
        scheduler_real_orders = bool(
            getattr(settings, "kis_scheduler_allow_real_orders", False)
            or getattr(settings, "kr_scheduler_allow_real_orders", False)
        )
        is_holiday = bool(market_session.get("is_holiday"))
        closure_reason = str(market_session.get("closure_reason") or "")
        if closure_reason.startswith("holiday_"):
            is_holiday = True
        return {
            "kis_limited_auto_sell_enabled": bool(
                runtime.get("kis_limited_auto_sell_enabled", False)
            ),
            "kis_limited_auto_sell_stop_loss_enabled": bool(
                runtime.get("kis_limited_auto_sell_stop_loss_enabled", False)
            ),
            "kis_limited_auto_sell_take_profit_enabled": bool(
                runtime.get("kis_limited_auto_sell_take_profit_enabled", False)
            ),
            "kis_limited_auto_sell_requires_queue_review": bool(
                runtime.get("kis_limited_auto_sell_requires_queue_review", True)
            ),
            "kis_limited_auto_sell_allow_manual_review_trigger": bool(
                runtime.get("kis_limited_auto_sell_allow_manual_review_trigger", False)
            ),
            "kis_limited_auto_sell_allow_take_profit_trigger": bool(
                runtime.get("kis_limited_auto_sell_allow_take_profit_trigger", False)
            ),
            "dry_run": bool(runtime.get("dry_run", True)),
            "dry_run_false": bool(runtime.get("dry_run", True)) is False,
            "kill_switch": bool(runtime.get("kill_switch", False)),
            "kill_switch_false": bool(runtime.get("kill_switch", False)) is False,
            "kis_enabled": bool(getattr(settings, "kis_enabled", False)),
            "kis_real_order_enabled": bool(
                getattr(settings, "kis_real_order_enabled", False)
            ),
            "kis_live_auto_enabled": bool(runtime.get("kis_live_auto_enabled", False)),
            "kis_live_auto_sell_enabled": bool(
                runtime.get("kis_live_auto_sell_enabled", False)
            ),
            "kis_live_auto_buy_enabled": bool(
                runtime.get("kis_live_auto_buy_enabled", False)
            ),
            "auto_buy_enabled": False,
            "scheduler_real_order_enabled": False,
            "configured_scheduler_real_order_enabled": scheduler_real_orders,
            "scheduler_real_orders_disabled": scheduler_real_orders is False,
            "market_open": market_session.get("is_market_open") is True,
            "today_not_holiday": not is_holiday,
        }

    def _market_session(self, now_utc: datetime) -> dict[str, Any]:
        try:
            return self.session_service.get_session_status(MARKET, now=now_utc)
        except Exception as exc:
            return {
                "market": MARKET,
                "is_market_open": False,
                "is_entry_allowed_now": False,
                "error": _safe_error(exc),
            }

    def _fetch_account_state(self, db: Session) -> dict[str, Any]:
        state: dict[str, Any] = {
            "provider": PROVIDER,
            "market": MARKET,
            "balance": None,
            "positions": [],
            "open_orders": [],
            "recent_orders": [],
            "warnings": [],
            "fetch_success": True,
        }
        try:
            state["balance"] = self.client.get_account_balance()
        except Exception as exc:
            state["fetch_success"] = False
            state["warnings"].append(f"balance_unavailable:{exc.__class__.__name__}")
        try:
            state["positions"] = [
                _normalize_position(item) for item in self.client.list_positions()
            ]
        except Exception as exc:
            state["fetch_success"] = False
            state["warnings"].append(f"positions_unavailable:{exc.__class__.__name__}")
        try:
            state["open_orders"] = [
                _normalize_order(item) for item in self.client.list_open_orders()
            ]
        except Exception as exc:
            state["fetch_success"] = False
            state["warnings"].append(
                f"open_orders_unavailable:{exc.__class__.__name__}"
            )
        try:
            rows = KisOrderSyncService.recent_orders(
                db,
                limit=50,
                include_rejected=True,
            )
            state["recent_orders"] = [serialize_kis_order(row) for row in rows]
        except Exception as exc:
            state["warnings"].append(f"recent_orders_unavailable:{exc.__class__.__name__}")
        return sanitize_kis_payload(state)

    def _select_candidate(
        self,
        db: Session,
        *,
        runtime: dict[str, Any],
        account_state: dict[str, Any],
    ) -> tuple[_AutoSellCandidate | None, str | None]:
        positions = _held_positions(account_state.get("positions"))
        if not positions:
            return None, "no_held_position"

        blocks: list[str] = []
        stop_loss_candidates: list[_AutoSellCandidate] = []
        for position in positions:
            symbol = _symbol(position)
            if not symbol:
                blocks.append("missing_symbol")
                continue
            held_qty = _safe_float_or_none(position.get("qty"))
            current_price = _safe_float_or_none(position.get("current_price"))
            diagnostics = position_pl_diagnostics(position)
            flags = {flag.lower() for flag in _string_list(position.get("risk_flags"))}
            if "manual_review_required" in flags:
                blocks.append("manual_review_auto_sell_disabled")
                continue
            if held_qty is None or held_qty <= 0:
                blocks.append("qty_not_positive")
                continue
            if current_price is None or current_price <= 0:
                blocks.append("missing_current_price")
                continue
            if diagnostics.get("exit_trigger_source") != "cost_basis":
                blocks.append("missing_cost_basis")
                continue
            threshold_reasons, diagnostics = position_exit_threshold_reasons(position)
            if "stop_loss_triggered" in threshold_reasons:
                qty = int(held_qty)
                if qty <= 0:
                    blocks.append("qty_not_positive")
                    continue
                if float(qty) > held_qty:
                    blocks.append("quantity_exceeds_held_quantity")
                    continue
                notional = round(float(qty) * current_price, 2)
                notional_reason = _notional_cap_reason(
                    account_state,
                    notional=notional,
                    max_notional_pct=float(
                        runtime.get("kis_limited_auto_sell_max_notional_pct", 0.03)
                    ),
                )
                if notional_reason:
                    blocks.append(notional_reason)
                    continue
                stop_loss_candidates.append(
                    _AutoSellCandidate(
                        symbol=symbol,
                        qty=qty,
                        held_qty=held_qty,
                        current_price=current_price,
                        notional=notional,
                        trigger=STOP_LOSS_TRIGGER,
                        trigger_source="cost_basis_pl_pct",
                        reason=(
                            "Limited auto sell candidate: reliable cost-basis "
                            "stop-loss threshold was reached."
                        ),
                        risk_flags=_dedupe(
                            [
                                "stop_loss_triggered",
                                "limited_auto_sell",
                                "sell_only",
                            ]
                        ),
                        gating_notes=_dedupe(
                            [
                                "Limited auto sell is SELL-only.",
                                "Stop-loss is the only default auto-submit trigger.",
                                "No KIS auto buy or scheduler real order path is enabled.",
                            ]
                        ),
                        diagnostics=diagnostics,
                        position=position,
                    )
                )
                continue
            if "take_profit_triggered" in threshold_reasons:
                if not bool(runtime.get("kis_limited_auto_sell_allow_take_profit_trigger", False)):
                    blocks.append("take_profit_auto_sell_disabled")
                continue
            blocks.append("no_stop_loss_candidate")

        if stop_loss_candidates:
            stop_loss_candidates.sort(
                key=lambda item: (
                    abs(_safe_float(item.diagnostics.get("unrealized_pl"), 0.0)),
                    item.notional,
                ),
                reverse=True,
            )
            return stop_loss_candidates[0], None
        return None, _first_priority_block(blocks)

    def _duplicate_order_reason(
        self,
        db: Session,
        *,
        candidate: _AutoSellCandidate,
        account_state: dict[str, Any],
        now_utc: datetime,
        runtime: dict[str, Any],
    ) -> str | None:
        symbol = candidate.symbol.upper()
        for order in _dict_list(account_state.get("open_orders")):
            if _order_symbol(order) == symbol and _order_is_sell(order):
                return "duplicate_open_order"
        for order in _dict_list(account_state.get("recent_orders")):
            if _order_symbol(order) != symbol:
                continue
            status = str(
                order.get("internal_status")
                or order.get("clear_status")
                or order.get("status")
                or ""
            ).upper()
            if status in OPEN_ORDER_STATUSES and _order_is_sell(order):
                return "recent_open_sell_order"

        open_row = (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.symbol == symbol)
            .filter(OrderLog.side == SELL)
            .filter(OrderLog.internal_status.in_(sorted(OPEN_ORDER_STATUSES)))
            .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
            .first()
        )
        if open_row is not None:
            return "duplicate_open_order"

        start_utc = _naive_utc(now_utc - timedelta(days=1))
        recent_rows = (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.symbol == symbol)
            .filter(OrderLog.side == SELL)
            .filter(OrderLog.created_at >= start_utc)
            .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
            .limit(50)
            .all()
        )
        for row in recent_rows:
            if _order_mode(row) == MODE and str(row.internal_status or "").upper() in SUBMITTED_STATUSES:
                return "recent_limited_auto_sell_exists"
        return None

    def _trade_limit_reason(
        self,
        db: Session,
        *,
        now_utc: datetime,
        runtime: dict[str, Any],
    ) -> str | None:
        max_orders = max(
            0,
            int(runtime.get("kis_limited_auto_sell_max_orders_per_day", 1) or 0),
        )
        if max_orders <= 0:
            return "daily_limited_auto_sell_limit_reached"
        start_utc, end_utc = _day_bounds_utc(now_utc)
        rows = (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.side == SELL)
            .filter(OrderLog.created_at >= start_utc)
            .filter(OrderLog.created_at < end_utc)
            .all()
        )
        count = sum(
            1
            for row in rows
            if _order_mode(row) == MODE
            and str(row.internal_status or "").upper() in SUBMITTED_STATUSES
        )
        if count >= max_orders:
            return "daily_limited_auto_sell_limit_reached"
        return None

    def _queue_review_status(self, db: Session, candidate: _AutoSellCandidate) -> str:
        row = (
            db.query(KisShadowExitReviewQueueState)
            .filter(
                KisShadowExitReviewQueueState.queue_key
                == _queue_key(candidate.symbol, candidate.trigger, candidate.trigger_source)
            )
            .first()
        )
        status = str(row.status if row is not None else "open").strip().lower()
        if status in {"reviewed", "dismissed"}:
            return status
        return "open"

    def _shadow_occurrence_count(self, db: Session, candidate: _AutoSellCandidate) -> int:
        cutoff = _naive_utc(datetime.now(UTC) - timedelta(days=30))
        rows = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.created_at >= cutoff)
            .filter(
                (TradeRunLog.mode == SHADOW_MODE)
                | (TradeRunLog.trigger_source == SHADOW_TRIGGER_SOURCE)
            )
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .limit(500)
            .all()
        )
        count = 0
        for row in rows:
            payload = _parse_json_object(row.response_payload)
            candidate_payload = _candidate_payload(payload)
            symbol = _normalize_symbol(
                candidate_payload.get("symbol") or payload.get("symbol") or row.symbol
            )
            trigger = str(
                candidate_payload.get("trigger")
                or payload.get("exit_trigger")
                or ""
            ).strip()
            trigger_source = str(
                candidate_payload.get("trigger_source")
                or payload.get("exit_trigger_source")
                or ""
            ).strip()
            decision = str(payload.get("decision") or payload.get("result") or row.result).strip()
            if (
                symbol == candidate.symbol
                and trigger == candidate.trigger
                and trigger_source == candidate.trigger_source
                and decision in {"would_sell", "sell", "stop_loss"}
            ):
                count += 1
        return count

    def _submit_sell(
        self,
        db: Session,
        *,
        candidate: _AutoSellCandidate,
        checks: dict[str, Any],
        safety: dict[str, Any],
        created_at: str,
        runtime: dict[str, Any],
        market_session: dict[str, Any],
        queue_review_status: str,
        shadow_occurrence_count: int,
    ) -> dict[str, Any]:
        audit_metadata = _audit_metadata(
            candidate,
            created_at=created_at,
            runtime=runtime,
            queue_review_status=queue_review_status,
            shadow_occurrence_count=shadow_occurrence_count,
            submitted=False,
        )
        order = self._create_order_log(
            db,
            candidate=candidate,
            audit_metadata=audit_metadata,
            internal_status=InternalOrderStatus.REQUESTED.value,
            response_payload=None,
        )
        broker_response = self.broker.submit_market_sell(
            symbol=candidate.symbol,
            qty=candidate.qty,
        )
        broker_order_id = _extract_broker_order_id(broker_response)
        broker_status = _extract_broker_status(broker_response)
        submitted_audit = _audit_metadata(
            candidate,
            created_at=created_at,
            runtime=runtime,
            queue_review_status=queue_review_status,
            shadow_occurrence_count=shadow_occurrence_count,
            submitted=True,
        )
        payload = _base_payload(
            result="submitted",
            action=SELL,
            reason=(
                "Limited auto sell submitted for stop-loss after all "
                "safety gates passed."
            ),
            checks=checks,
            safety=safety,
            created_at=created_at,
            runtime=runtime,
            market_session=market_session,
            candidate=candidate,
            blocked_by=[],
            audit_metadata=submitted_audit,
        )
        payload.update(
            {
                "order_id": order.id,
                "order_log_id": order.id,
                "broker_order_id": broker_order_id,
                "kis_odno": broker_order_id,
                "broker_order_status": broker_status,
                "broker_status": broker_status,
                "real_order_submitted": True,
                "broker_submit_called": True,
                "manual_submit_called": False,
                "auto_sell_enabled": True,
                "queue_review_status": queue_review_status,
                "shadow_occurrence_count": shadow_occurrence_count,
            }
        )
        order.internal_status = InternalOrderStatus.SUBMITTED.value
        order.broker_status = broker_status
        order.broker_order_status = broker_status
        order.broker_order_id = broker_order_id
        order.kis_odno = broker_order_id
        order.requested_qty = float(candidate.qty)
        order.filled_qty = 0
        order.remaining_qty = float(candidate.qty)
        order.submitted_at = _naive_utc(datetime.now(UTC))
        order.response_payload = _json(
            {
                **payload,
                "kis_response": sanitize_kis_payload(broker_response),
            }
        )
        db.commit()
        db.refresh(order)
        signal = self._record_signal(
            db,
            payload=payload,
            candidate=candidate,
            related_order_id=order.id,
        )
        run = self._record_run(
            db,
            payload=payload,
            symbol=candidate.symbol,
            signal_id=signal.id,
            order_id=order.id,
        )
        payload["signal_id"] = signal.id
        payload["run"] = _serialize_run(run)
        return sanitize_kis_payload(payload)

    def _submission_failed(
        self,
        db: Session,
        *,
        candidate: _AutoSellCandidate,
        checks: dict[str, Any],
        safety: dict[str, Any],
        created_at: str,
        runtime: dict[str, Any],
        market_session: dict[str, Any],
        queue_review_status: str,
        shadow_occurrence_count: int,
        error: Exception,
    ) -> dict[str, Any]:
        payload = _base_payload(
            result="blocked",
            action="hold",
            reason="broker_submit_failed",
            checks=checks,
            safety=safety,
            created_at=created_at,
            runtime=runtime,
            market_session=market_session,
            candidate=candidate,
            blocked_by=["broker_submit_failed"],
            audit_metadata=_audit_metadata(
                candidate,
                created_at=created_at,
                runtime=runtime,
                queue_review_status=queue_review_status,
                shadow_occurrence_count=shadow_occurrence_count,
                submitted=False,
            ),
        )
        payload.update(
            {
                "error": _safe_error(error),
                "broker_submit_called": True,
                "real_order_submitted": False,
                "manual_submit_called": False,
                "queue_review_status": queue_review_status,
                "shadow_occurrence_count": shadow_occurrence_count,
            }
        )
        signal = self._record_signal(db, payload=payload, candidate=candidate)
        run = self._record_run(
            db,
            payload=payload,
            symbol=candidate.symbol,
            signal_id=signal.id,
            order_id=None,
        )
        payload["signal_id"] = signal.id
        payload["run"] = _serialize_run(run)
        return sanitize_kis_payload(payload)

    def _blocked(
        self,
        db: Session,
        *,
        reason: str,
        checks: dict[str, Any],
        safety: dict[str, Any],
        created_at: str,
        runtime: dict[str, Any],
        market_session: dict[str, Any],
        account_state: dict[str, Any] | None = None,
        candidate: _AutoSellCandidate | None = None,
        blocked_by: list[str] | None = None,
        queue_review_status: str | None = None,
    ) -> dict[str, Any]:
        payload = _base_payload(
            result="blocked",
            action="hold",
            reason=reason,
            checks=checks,
            safety=safety,
            created_at=created_at,
            runtime=runtime,
            market_session=market_session,
            candidate=candidate,
            blocked_by=blocked_by or [reason],
            audit_metadata=(
                _audit_metadata(
                    candidate,
                    created_at=created_at,
                    runtime=runtime,
                    queue_review_status=queue_review_status or "not_checked",
                    shadow_occurrence_count=None,
                    submitted=False,
                )
                if candidate is not None
                else None
            ),
        )
        payload["account_state"] = _account_state_summary(account_state or {})
        payload["queue_review_status"] = queue_review_status
        signal = self._record_signal(db, payload=payload, candidate=candidate)
        run = self._record_run(
            db,
            payload=payload,
            symbol=candidate.symbol if candidate else "WATCHLIST",
            signal_id=signal.id,
            order_id=None,
        )
        payload["signal_id"] = signal.id
        payload["run"] = _serialize_run(run)
        return sanitize_kis_payload(payload)

    def _create_order_log(
        self,
        db: Session,
        *,
        candidate: _AutoSellCandidate,
        audit_metadata: dict[str, Any],
        internal_status: str,
        response_payload: dict[str, Any] | None,
    ) -> OrderLog:
        source_fields = kis_order_source_fields(audit_metadata)
        row = OrderLog(
            broker=PROVIDER,
            market=MARKET,
            symbol=candidate.symbol,
            side=SELL,
            order_type="market",
            time_in_force="day",
            qty=float(candidate.qty),
            requested_qty=float(candidate.qty),
            remaining_qty=float(candidate.qty),
            notional=candidate.notional,
            internal_status=internal_status,
            extended_hours=False,
            request_payload=_json(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": MODE,
                    "source": SOURCE,
                    "source_type": SOURCE_TYPE,
                    "symbol": candidate.symbol,
                    "side": SELL,
                    "qty": candidate.qty,
                    "order_type": "market",
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                    **source_fields,
                }
            ),
            response_payload=_json(response_payload) if response_payload else None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def _record_signal(
        self,
        db: Session,
        *,
        payload: dict[str, Any],
        candidate: _AutoSellCandidate | None,
        related_order_id: int | None = None,
    ) -> SignalLog:
        signal = SignalLog(
            symbol=(candidate.symbol if candidate else None) or "WATCHLIST",
            action=str(payload.get("action") or "hold"),
            reason=str(payload.get("reason") or "limited_auto_sell_blocked"),
            indicator_payload=_json((candidate.position if candidate else {}) or {}),
            risk_flags=_json(payload.get("risk_flags") or []),
            approved_by_risk=payload.get("result") == "submitted",
            related_order_id=related_order_id,
            signal_status=MODE if payload.get("result") == "submitted" else "blocked",
            trigger_source=TRIGGER_SOURCE,
            hard_block_reason=(
                None
                if payload.get("result") == "submitted"
                else str(payload.get("reason") or "limited_auto_sell_blocked")
            ),
            hard_blocked=payload.get("result") != "submitted",
            gating_notes=_json(payload.get("gating_notes") or []),
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)
        return signal

    def _record_run(
        self,
        db: Session,
        *,
        payload: dict[str, Any],
        symbol: str,
        signal_id: int,
        order_id: int | None,
    ) -> TradeRunLog:
        run = TradeRunLog(
            run_key=f"kis_limited_auto_sell_{uuid.uuid4().hex[:10]}",
            trigger_source=TRIGGER_SOURCE,
            symbol=symbol,
            mode=MODE,
            stage="done",
            result=str(payload.get("result") or "blocked"),
            reason=str(payload.get("reason") or ""),
            signal_id=signal_id,
            order_id=order_id,
            request_payload=_json(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": MODE,
                    "source": SOURCE,
                    "source_type": SOURCE_TYPE,
                    "trigger_source": TRIGGER_SOURCE,
                    "real_order_submitted": payload.get("real_order_submitted") is True,
                    "broker_submit_called": payload.get("broker_submit_called") is True,
                    "manual_submit_called": False,
                }
            ),
            response_payload=_json(payload),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run


def _first_failed_preliminary_reason(checks: dict[str, Any]) -> str | None:
    ordered = [
        ("kis_limited_auto_sell_enabled", "limited_auto_sell_disabled"),
        ("kis_limited_auto_sell_stop_loss_enabled", "stop_loss_auto_sell_disabled"),
        ("dry_run_false", "runtime_dry_run_true"),
        ("kill_switch_false", "kill_switch_enabled"),
        ("kis_enabled", "kis_disabled"),
        ("kis_real_order_enabled", "kis_real_order_disabled"),
        ("kis_live_auto_enabled", "kis_live_auto_disabled"),
        ("kis_live_auto_sell_enabled", "kis_live_auto_sell_disabled"),
        ("scheduler_real_orders_disabled", "scheduler_real_orders_must_remain_disabled"),
        ("market_open", "market_closed"),
        ("today_not_holiday", "today_is_holiday"),
    ]
    for key, reason in ordered:
        if checks.get(key) is not True:
            return reason
    if checks.get("kis_live_auto_buy_enabled") is True:
        return "auto_buy_must_remain_disabled"
    return None


def _safety(runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "max_orders_per_day": int(
            runtime.get("kis_limited_auto_sell_max_orders_per_day", 1) or 1
        ),
        "max_notional_pct": float(
            runtime.get("kis_limited_auto_sell_max_notional_pct", 0.03) or 0.03
        ),
        "stop_loss_only": not bool(
            runtime.get("kis_limited_auto_sell_allow_take_profit_trigger", False)
        ),
        "take_profit_auto_sell_enabled": bool(
            runtime.get("kis_limited_auto_sell_take_profit_enabled", False)
            and runtime.get("kis_limited_auto_sell_allow_take_profit_trigger", False)
        ),
        "manual_review_auto_sell_enabled": bool(
            runtime.get("kis_limited_auto_sell_allow_manual_review_trigger", False)
        ),
        "queue_review_required": bool(
            runtime.get("kis_limited_auto_sell_requires_queue_review", True)
        ),
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "auto_buy_enabled": False,
        "scheduler_real_order_enabled": False,
    }


def _base_payload(
    *,
    result: str,
    action: str,
    reason: str,
    checks: dict[str, Any],
    safety: dict[str, Any],
    created_at: str,
    runtime: dict[str, Any],
    market_session: dict[str, Any],
    candidate: _AutoSellCandidate | None,
    blocked_by: list[str],
    audit_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    diagnostics = candidate.diagnostics if candidate is not None else {}
    risk_flags = _dedupe(
        ["limited_auto_sell", "sell_only", "no_auto_buy"]
        + _string_list(candidate.risk_flags if candidate is not None else [])
        + blocked_by
    )
    gating_notes = _dedupe(
        [
            "KIS limited auto sell is disabled by default.",
            "This path can submit SELL only after every runtime and risk gate passes.",
            "KIS auto buy and scheduler real orders remain disabled.",
            "Manual submit service is not called by limited auto sell.",
        ]
        + _string_list(candidate.gating_notes if candidate is not None else [])
    )
    payload = {
        "status": "ok",
        "provider": PROVIDER,
        "market": MARKET,
        "mode": MODE,
        "source": SOURCE,
        "source_type": SOURCE_TYPE,
        "result": result,
        "action": action,
        "reason": reason,
        "symbol": candidate.symbol if candidate is not None else None,
        "quantity": candidate.qty if candidate is not None else None,
        "qty": candidate.qty if candidate is not None else None,
        "trigger": candidate.trigger if candidate is not None else None,
        "trigger_source": candidate.trigger_source if candidate is not None else None,
        "exit_trigger": candidate.trigger if candidate is not None else None,
        "exit_trigger_source": candidate.trigger_source if candidate is not None else None,
        "cost_basis": diagnostics.get("cost_basis"),
        "current_value": diagnostics.get("current_value"),
        "current_price": candidate.current_price if candidate is not None else None,
        "unrealized_pl": diagnostics.get("unrealized_pl"),
        "unrealized_pl_pct": diagnostics.get("unrealized_pl_pct"),
        "notional": candidate.notional if candidate is not None else None,
        "order_id": None,
        "broker_order_id": None,
        "kis_odno": None,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "auto_buy_enabled": False,
        "auto_sell_enabled": bool(
            runtime.get("kis_limited_auto_sell_enabled", False)
            and runtime.get("kis_live_auto_sell_enabled", False)
        ),
        "scheduler_real_order_enabled": False,
        "checks": checks,
        "failed_checks": blocked_by,
        "blocked_by": blocked_by,
        "safety": safety,
        "risk_flags": risk_flags,
        "gating_notes": gating_notes,
        "audit_metadata": audit_metadata,
        "market_session": _public_market_session(market_session),
        "created_at": created_at,
        "checked_at": created_at,
    }
    if audit_metadata:
        payload.update(kis_order_source_fields(audit_metadata))
    return payload


def _audit_metadata(
    candidate: _AutoSellCandidate,
    *,
    created_at: str,
    runtime: dict[str, Any],
    queue_review_status: str,
    shadow_occurrence_count: int | None,
    submitted: bool,
) -> dict[str, Any]:
    return {
        "source": SOURCE,
        "source_type": SOURCE_TYPE,
        "limited_auto_sell_checked_at": created_at,
        "checked_at": created_at,
        "exit_trigger": candidate.trigger,
        "trigger_source": candidate.trigger_source,
        "queue_id": _queue_key(candidate.symbol, candidate.trigger, candidate.trigger_source),
        "queue_review_required": bool(
            runtime.get("kis_limited_auto_sell_requires_queue_review", True)
        ),
        "queue_review_status": queue_review_status,
        "unrealized_pl": candidate.diagnostics.get("unrealized_pl"),
        "unrealized_pl_pct": candidate.diagnostics.get("unrealized_pl_pct"),
        "cost_basis": candidate.diagnostics.get("cost_basis"),
        "current_value": candidate.diagnostics.get("current_value"),
        "current_price": candidate.current_price,
        "suggested_quantity": candidate.qty,
        "quantity": candidate.qty,
        "notional": candidate.notional,
        "max_notional_pct": float(
            runtime.get("kis_limited_auto_sell_max_notional_pct", 0.03) or 0.03
        ),
        "risk_flags": candidate.risk_flags,
        "gating_notes": candidate.gating_notes,
        "manual_confirm_required": False,
        "auto_buy_enabled": False,
        "auto_sell_enabled": submitted,
        "scheduler_real_order_enabled": False,
        "real_order_submit_allowed": True,
        "limited_auto_sell_enabled": bool(
            runtime.get("kis_limited_auto_sell_enabled", False)
        ),
        "stop_loss_auto_sell_enabled": bool(
            runtime.get("kis_limited_auto_sell_stop_loss_enabled", False)
        ),
        "take_profit_auto_sell_enabled": False,
        "manual_review_auto_sell_enabled": False,
        "limited_auto_sell_real_order_submitted": submitted,
        "limited_auto_sell_broker_submit_called": submitted,
        "limited_auto_sell_manual_submit_called": False,
        "shadow_occurrence_count": shadow_occurrence_count,
    }


def _notional_cap_reason(
    account_state: dict[str, Any],
    *,
    notional: float,
    max_notional_pct: float,
) -> str | None:
    balance = account_state.get("balance")
    if not isinstance(balance, dict):
        return "account_value_unavailable_for_notional_cap"
    account_value = _first_float(
        balance,
        "total_asset_value",
        "total_equity",
        "equity",
        "stock_evaluation_amount",
        "total_market_value",
        "tot_evlu_amt",
    )
    if account_value is None or account_value <= 0:
        return "account_value_unavailable_for_notional_cap"
    if notional > account_value * max_notional_pct:
        return "notional_cap_exceeded"
    return None


def _held_positions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    positions = [
        item
        for item in value
        if isinstance(item, dict) and _safe_float(item.get("qty"), 0.0) > 0
    ]
    positions.sort(key=lambda item: str(item.get("symbol") or ""))
    return positions


def _normalize_position(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    raw_symbol = item.get("symbol") or item.get("pdno") or item.get("code")
    symbol = _normalize_symbol(raw_symbol) or ""
    return {
        **item,
        "symbol": symbol,
        "name": item.get("name") or item.get("prdt_name"),
        "qty": to_float(item.get("qty") or item.get("hldg_qty") or 0),
        "avg_entry_price": to_float(
            item.get("avg_entry_price") or item.get("pchs_avg_pric") or 0
        ),
        "current_price": to_float(
            item.get("current_price") or item.get("prpr") or item.get("stck_prpr") or 0
        ),
        "market_value": to_float(item.get("market_value") or item.get("evlu_amt") or 0),
        "current_value": to_float(
            item.get("current_value") or item.get("market_value") or item.get("evlu_amt") or 0
        ),
        "cost_basis": to_float(
            item.get("cost_basis")
            or item.get("pchs_amt")
            or item.get("pchs_amt_smtl_amt")
            or 0
        ),
        "unrealized_pl": to_float(
            item.get("unrealized_pl") or item.get("evlu_pfls_amt") or 0
        ),
        "unrealized_plpc": to_float(
            item.get("unrealized_plpc") or item.get("evlu_pfls_rt") or 0
        ),
    }


def _normalize_order(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    symbol = _normalize_symbol(item.get("symbol") or item.get("pdno") or item.get("code"))
    return {**item, "symbol": symbol or ""}


def _first_priority_block(blocks: list[str]) -> str:
    priority = [
        "missing_cost_basis",
        "missing_current_price",
        "qty_not_positive",
        "take_profit_auto_sell_disabled",
        "manual_review_auto_sell_disabled",
        "notional_cap_exceeded",
        "account_value_unavailable_for_notional_cap",
        "quantity_exceeds_held_quantity",
        "no_stop_loss_candidate",
    ]
    for item in priority:
        if item in blocks:
            return item
    return blocks[0] if blocks else "no_stop_loss_candidate"


def _queue_key(symbol: str, trigger: str, trigger_source: str) -> str:
    return f"{_safe_key_part(symbol)}:{_safe_key_part(trigger)}:{_safe_key_part(trigger_source)}"


def _safe_key_part(value: Any) -> str:
    text = "".join(
        char if char.isalnum() or char in {"_", ".", "-"} else "_"
        for char in str(value or "").strip()
    )
    return text[:80] or "unknown"


def _candidate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload.get("candidate")
    if isinstance(candidate, dict):
        return candidate
    candidates = payload.get("candidates") or payload.get("candidates_evaluated")
    if isinstance(candidates, list):
        for item in candidates:
            if isinstance(item, dict):
                return item
    return {}


def _order_mode(row: OrderLog) -> str:
    for raw in (row.response_payload, row.request_payload, row.last_sync_payload):
        payload = _parse_json_object(raw)
        mode = str(payload.get("mode") or "").strip()
        if mode:
            return mode
    return ""


def _order_symbol(order: dict[str, Any]) -> str:
    return _normalize_symbol(order.get("symbol") or order.get("pdno") or order.get("code")) or ""


def _order_is_sell(order: dict[str, Any]) -> bool:
    side = str(
        order.get("side")
        or order.get("order_side")
        or order.get("sll_buy_dvsn_cd_name")
        or order.get("sll_buy_dvsn_name")
        or ""
    ).strip().lower()
    if side in {"sell", "s"}:
        return True
    code = str(order.get("sll_buy_dvsn_cd") or order.get("sll_buy_dvsn") or "").strip()
    return code in {"01", "1"}


def _account_state_summary(account_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": PROVIDER,
        "market": MARKET,
        "fetch_success": bool(account_state.get("fetch_success")),
        "balance_available": isinstance(account_state.get("balance"), dict),
        "position_count": len(account_state.get("positions") or []),
        "open_order_count": len(account_state.get("open_orders") or []),
        "recent_order_count": len(account_state.get("recent_orders") or []),
        "warnings": _string_list(account_state.get("warnings")),
    }


def _public_market_session(market_session: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "market",
        "timezone",
        "is_market_open",
        "is_entry_allowed_now",
        "is_near_close",
        "closure_reason",
        "closure_name",
        "is_holiday",
        "regular_open",
        "regular_close",
        "effective_close",
        "no_new_entry_after",
    ]
    return {key: market_session.get(key) for key in keys if key in market_session}


def _serialize_run(row: TradeRunLog) -> dict[str, Any]:
    return {
        "run_id": row.id,
        "run_key": row.run_key,
        "trigger_source": row.trigger_source,
        "symbol": row.symbol,
        "mode": row.mode,
        "stage": row.stage,
        "result": row.result,
        "reason": row.reason,
        "signal_id": row.signal_id,
        "order_id": row.order_id,
        "created_at": row.created_at,
    }


def _extract_broker_order_id(response: dict[str, Any]) -> str | None:
    output = response.get("output")
    if isinstance(output, list) and output:
        output = output[0]
    if not isinstance(output, dict):
        output = response
    value = (
        output.get("ODNO")
        or output.get("odno")
        or output.get("order_id")
        or output.get("ORD_NO")
        or output.get("ord_no")
    )
    return str(value) if value is not None and str(value).strip() else None


def _extract_broker_status(response: dict[str, Any]) -> str:
    rt_cd = str(response.get("rt_cd", "0"))
    if rt_cd in {"0", ""}:
        return "submitted"
    return str(response.get("msg_cd") or rt_cd)


def _warning_names(account_state: dict[str, Any]) -> set[str]:
    return {text.split(":", 1)[0] for text in _string_list(account_state.get("warnings"))}


def _day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    local = now_utc.astimezone(KR_TZ)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return _naive_utc(start.astimezone(UTC)), _naive_utc(end.astimezone(UTC))


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(UTC)
    return value.replace(tzinfo=None)


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


def _normalize_symbol(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text or text == "NULL":
        return None
    if text.isdigit() and len(text) < 6:
        text = text.zfill(6)
    return text


def _symbol(value: dict[str, Any] | None) -> str | None:
    return _normalize_symbol((value or {}).get("symbol"))


def _first_float(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _safe_float_or_none(payload.get(key))
        if value is not None:
            return value
    return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    parsed = _safe_float_or_none(value)
    return default if parsed is None else parsed


def _safe_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _json(payload: Any) -> str:
    return json.dumps(sanitize_kis_payload(payload), ensure_ascii=False, default=str)


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 180:
        text = f"{text[:180]}..."
    return f"{exc.__class__.__name__}: {text}"
