from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient, to_float
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.services.kis_dry_run_risk_service import (
    MARKET,
    OPEN_ORDER_STATUSES,
    PROVIDER,
    SELL,
    position_exit_threshold_reasons,
    position_pl_diagnostics,
)
from app.services.kis_manual_order_service import (
    KIS_MANUAL_CONFIRMATION_PHRASE,
    KisManualOrderService,
    KisManualOrderSubmitRequest,
)
from app.services.kis_order_audit import kis_order_source_fields
from app.services.kis_order_sync_service import KisOrderSyncService, serialize_kis_order
from app.services.kis_order_validation_service import (
    KisOrderValidationRequest,
    KisOrderValidationService,
    record_kis_order_validation,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService


STATUS_MODE = "kis_limited_auto_stop_loss_status"
PREFLIGHT_MODE = "kis_limited_auto_stop_loss_preflight"
RUN_MODE = "kis_limited_auto_stop_loss_run"
MODE = RUN_MODE
SOURCE = "kis_limited_auto_stop_loss"
PREFLIGHT_SOURCE_TYPE = "limited_auto_sell_preflight"
RUN_SOURCE_TYPE = "guarded_stop_loss_auto_sell"
TRIGGER_SOURCE = "kis_limited_auto_sell"
RUN_TRIGGER_SOURCE = "limited_auto_sell_run_once"
STOP_LOSS_TRIGGER = "stop_loss"
TAKE_PROFIT_TRIGGER = "take_profit"
KR_TZ = ZoneInfo("Asia/Seoul")

HOLD = "HOLD"
REVIEW_SELL = "REVIEW_SELL"
SELL_READY = "SELL_READY"

SUBMITTED_STATUSES = {
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}


@dataclass(frozen=True)
class _Context:
    runtime: dict[str, Any]
    settings: Any
    market_session: dict[str, Any]
    now_utc: datetime
    created_at: str
    live_auto_sell_enabled: bool
    stop_loss_enabled: bool
    take_profit_enabled: bool
    scheduler_real_orders_configured: bool
    scheduler_limited_auto_sell_configured: bool
    live_auto_buy_configured: bool
    sell_session_allowed: bool


@dataclass(frozen=True)
class _AutoSellCandidate:
    symbol: str
    name: str | None
    quantity: int
    held_qty: float
    current_price: float | None
    average_price: float | None
    cost_basis: float | None
    current_value: float | None
    unrealized_pl: float | None
    unrealized_pl_pct: float | None
    stop_loss_threshold_pct: float | None
    take_profit_threshold_pct: float | None
    stop_loss_triggered: bool
    take_profit_triggered: bool
    weak_trend_triggered: bool
    sell_pressure_triggered: bool
    status: str
    exit_reason: str
    risk_flags: list[str]
    gating_notes: list[str]
    block_reasons: list[str]
    trigger_source: str
    diagnostics: dict[str, Any]
    position: dict[str, Any]
    duplicate_open_sell_order: bool
    latest_order: dict[str, Any] | None


class KisLimitedAutoSellService:
    """Readiness and guarded run-once path for limited KIS stop-loss auto sell.

    Status and preflight never submit orders. The run-once endpoint only reaches
    the existing validation/manual-submit services after all explicit safety
    gates pass.
    """

    def __init__(
        self,
        client: KisClient,
        *,
        broker: Any | None = None,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
    ):
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()
        self._unused_legacy_broker = broker

    def status(self, db: Session, *, now: datetime | None = None) -> dict[str, Any]:
        context = self._context(db, now=now)
        block_reasons = _status_block_reasons(context)
        daily_limit = self._daily_limit_state(db, context=context, symbol=None)
        payload = _status_payload(
            context=context,
            block_reasons=block_reasons,
            daily_limit=daily_limit,
            result="blocked" if block_reasons else "ready",
            reason=block_reasons[0] if block_reasons else "base_gates_ready",
        )
        return sanitize_kis_payload(payload)

    def preflight_once(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        context = self._context(db, now=now)
        account_state = self._fetch_account_state(db)
        candidates = self._evaluate_candidates(db, account_state=account_state)
        final_candidate = _select_final_candidate(candidates)
        payload = self._decision_payload(
            db,
            context=context,
            mode=PREFLIGHT_MODE,
            source_type=PREFLIGHT_SOURCE_TYPE,
            result=_preflight_result(final_candidate),
            action=_action_for_candidate(final_candidate),
            reason=_preflight_reason(final_candidate),
            account_state=account_state,
            candidates=candidates,
            final_candidate=final_candidate,
            block_reasons=_preflight_block_reasons(final_candidate),
            read_only=True,
        )
        return sanitize_kis_payload(payload)

    def run_once(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        context = self._context(db, now=now)
        pre_account_blocks = _run_pre_account_block_reasons(context)
        if pre_account_blocks:
            payload = self._decision_payload(
                db,
                context=context,
                mode=RUN_MODE,
                source_type=RUN_SOURCE_TYPE,
                result="blocked",
                action="hold",
                reason=pre_account_blocks[0],
                account_state=None,
                candidates=[],
                final_candidate=None,
                block_reasons=pre_account_blocks,
                read_only=False,
            )
            signal = self._record_signal(
                db,
                payload=payload,
                candidate=None,
                source_type=RUN_SOURCE_TYPE,
            )
            run = self._record_run(
                db,
                payload=payload,
                candidate=None,
                mode=RUN_MODE,
                source_type=RUN_SOURCE_TYPE,
                signal_id=signal.id,
                order_id=None,
            )
            payload["signal_id"] = signal.id
            payload["run"] = _serialize_run(run)
            return sanitize_kis_payload(payload)

        account_state = self._fetch_account_state(db)
        candidates = self._evaluate_candidates(db, account_state=account_state)
        final_candidate = _select_final_candidate(candidates)
        run_blocks = self._run_candidate_block_reasons(
            db,
            context=context,
            account_state=account_state,
            candidates=candidates,
            final_candidate=final_candidate,
        )
        if run_blocks:
            payload = self._decision_payload(
                db,
                context=context,
                mode=RUN_MODE,
                source_type=RUN_SOURCE_TYPE,
                result="blocked",
                action=_run_blocked_action(final_candidate),
                reason=run_blocks[0],
                account_state=account_state,
                candidates=candidates,
                final_candidate=final_candidate,
                block_reasons=run_blocks,
                read_only=False,
            )
            signal = self._record_signal(
                db,
                payload=payload,
                candidate=final_candidate,
                source_type=RUN_SOURCE_TYPE,
            )
            run = self._record_run(
                db,
                payload=payload,
                candidate=final_candidate,
                mode=RUN_MODE,
                source_type=RUN_SOURCE_TYPE,
                signal_id=signal.id,
                order_id=None,
            )
            payload["signal_id"] = signal.id
            payload["run"] = _serialize_run(run)
            return sanitize_kis_payload(payload)

        validation_block, validation_payload = self._validate_candidate(
            db,
            context=context,
            candidate=final_candidate,
        )
        if validation_block:
            payload = self._decision_payload(
                db,
                context=context,
                mode=RUN_MODE,
                source_type=RUN_SOURCE_TYPE,
                result="blocked",
                action=_run_blocked_action(final_candidate),
                reason=validation_block[0],
                account_state=account_state,
                candidates=candidates,
                final_candidate=final_candidate,
                block_reasons=validation_block,
                read_only=False,
                diagnostics_extra={"validation": validation_payload},
            )
            signal = self._record_signal(
                db,
                payload=payload,
                candidate=final_candidate,
                source_type=RUN_SOURCE_TYPE,
            )
            run = self._record_run(
                db,
                payload=payload,
                candidate=final_candidate,
                mode=RUN_MODE,
                source_type=RUN_SOURCE_TYPE,
                signal_id=signal.id,
                order_id=None,
            )
            payload["signal_id"] = signal.id
            payload["run"] = _serialize_run(run)
            return sanitize_kis_payload(payload)

        return self._submit_via_existing_manual_path(
            db,
            context=context,
            account_state=account_state,
            candidates=candidates,
            final_candidate=final_candidate,
            validation_payload=validation_payload,
        )

    def _context(self, db: Session, *, now: datetime | None) -> _Context:
        now_utc = _utc_now(now)
        runtime = self.runtime_settings.get_settings(db)
        settings = self.client.settings
        market_session = self._market_session(now_utc)
        scheduler_real_orders_configured = bool(
            getattr(settings, "kis_scheduler_allow_real_orders", False)
            or getattr(settings, "kr_scheduler_allow_real_orders", False)
            or runtime.get("kis_scheduler_allow_real_orders", False)
        )
        scheduler_limited_auto_sell_configured = bool(
            runtime.get("kis_scheduler_allow_limited_auto_sell", False)
        )
        live_auto_buy_configured = bool(runtime.get("kis_live_auto_buy_enabled", False))
        is_holiday = bool(market_session.get("is_holiday"))
        closure_reason = str(market_session.get("closure_reason") or "")
        if closure_reason.startswith("holiday_"):
            is_holiday = True
        sell_session_allowed = (
            market_session.get("is_market_open") is True and not is_holiday
        )
        return _Context(
            runtime=runtime,
            settings=settings,
            market_session=market_session,
            now_utc=now_utc,
            created_at=now_utc.isoformat(),
            live_auto_sell_enabled=bool(runtime.get("kis_live_auto_sell_enabled", False)),
            stop_loss_enabled=_stop_loss_enabled(runtime),
            take_profit_enabled=_take_profit_enabled(runtime),
            scheduler_real_orders_configured=scheduler_real_orders_configured,
            scheduler_limited_auto_sell_configured=scheduler_limited_auto_sell_configured,
            live_auto_buy_configured=live_auto_buy_configured,
            sell_session_allowed=sell_session_allowed,
        )

    def _market_session(self, now_utc: datetime) -> dict[str, Any]:
        try:
            return self.session_service.get_session_status(MARKET, now=now_utc)
        except Exception as exc:
            return {
                "market": MARKET,
                "is_market_open": False,
                "is_entry_allowed_now": False,
                "is_holiday": False,
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
            state["warnings"].append(f"open_orders_unavailable:{exc.__class__.__name__}")
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

    def _evaluate_candidates(
        self,
        db: Session,
        *,
        account_state: dict[str, Any],
    ) -> list[_AutoSellCandidate]:
        candidates: list[_AutoSellCandidate] = []
        for position in _held_positions(account_state.get("positions")):
            candidates.append(
                self._candidate_from_position(
                    db,
                    position,
                    account_state=account_state,
                )
            )
        return candidates

    def _candidate_from_position(
        self,
        db: Session,
        position: dict[str, Any],
        *,
        account_state: dict[str, Any],
    ) -> _AutoSellCandidate:
        symbol = _symbol(position) or ""
        held_qty = _safe_float(position.get("qty"), 0.0)
        quantity = int(held_qty) if held_qty > 0 else 0
        current_price = _safe_float_or_none(position.get("current_price"))
        average_price = _safe_float_or_none(position.get("avg_entry_price"))
        threshold_reasons, diagnostics = position_exit_threshold_reasons(position)
        stop_loss_triggered = "stop_loss_triggered" in threshold_reasons
        take_profit_triggered = "take_profit_triggered" in threshold_reasons
        cost_basis_valid = diagnostics.get("exit_trigger_source") == "cost_basis"
        weak_trend = _weak_trend_triggered(position)
        sell_pressure = _sell_pressure_triggered(position)
        latest_order = _latest_related_sell_order(
            db,
            symbol=symbol,
            account_state=account_state,
        )
        duplicate_open_sell = _has_duplicate_open_sell(
            db,
            symbol=symbol,
            account_state=account_state,
        )

        block_reasons: list[str] = []
        risk_flags: list[str] = []
        if quantity <= 0:
            block_reasons.append("quantity_not_positive")
        if current_price is None or current_price <= 0:
            block_reasons.append("current_price_unavailable")
        if not cost_basis_valid:
            block_reasons.extend(["manual_review_required", "missing_cost_basis"])
            risk_flags.extend(["manual_review_required", "insufficient_cost_basis"])
        if duplicate_open_sell:
            block_reasons.append("duplicate_open_sell_order")
            risk_flags.append("duplicate_open_sell_order")
        if take_profit_triggered:
            block_reasons.append("take_profit_auto_sell_disabled")
            risk_flags.append("take_profit_triggered")
        if weak_trend:
            risk_flags.append("weak_trend_triggered")
        if sell_pressure:
            risk_flags.append("sell_pressure_triggered")
        if stop_loss_triggered:
            risk_flags.append("stop_loss_triggered")

        if stop_loss_triggered and cost_basis_valid and quantity > 0 and not duplicate_open_sell:
            status = SELL_READY
            exit_reason = "stop_loss_triggered"
        elif (
            stop_loss_triggered
            or take_profit_triggered
            or weak_trend
            or sell_pressure
            or not cost_basis_valid
            or duplicate_open_sell
        ):
            status = REVIEW_SELL
            exit_reason = _first_reason(
                [
                    "stop_loss_triggered" if stop_loss_triggered else "",
                    "take_profit_triggered" if take_profit_triggered else "",
                    "manual_review_required" if not cost_basis_valid else "",
                    "duplicate_open_sell_order" if duplicate_open_sell else "",
                    "weak_trend_triggered" if weak_trend else "",
                    "sell_pressure_triggered" if sell_pressure else "",
                ],
                "manual_review_required",
            )
        else:
            status = HOLD
            exit_reason = "no_stop_loss_candidate"

        gating_notes = _candidate_gating_notes(
            status=status,
            stop_loss_triggered=stop_loss_triggered,
            take_profit_triggered=take_profit_triggered,
            cost_basis_valid=cost_basis_valid,
            duplicate_open_sell=duplicate_open_sell,
        )
        return _AutoSellCandidate(
            symbol=symbol,
            name=_name(position),
            quantity=quantity,
            held_qty=held_qty,
            current_price=current_price,
            average_price=average_price,
            cost_basis=_safe_float_or_none(diagnostics.get("cost_basis")),
            current_value=_safe_float_or_none(diagnostics.get("current_value")),
            unrealized_pl=_safe_float_or_none(diagnostics.get("unrealized_pl")),
            unrealized_pl_pct=(
                _safe_float_or_none(diagnostics.get("unrealized_pl_pct"))
                if cost_basis_valid
                else None
            ),
            stop_loss_threshold_pct=_safe_float_or_none(
                diagnostics.get("stop_loss_threshold_pct")
            ),
            take_profit_threshold_pct=_safe_float_or_none(
                diagnostics.get("take_profit_threshold_pct")
            ),
            stop_loss_triggered=bool(stop_loss_triggered and cost_basis_valid),
            take_profit_triggered=bool(take_profit_triggered and cost_basis_valid),
            weak_trend_triggered=weak_trend,
            sell_pressure_triggered=sell_pressure,
            status=status,
            exit_reason=exit_reason,
            risk_flags=_dedupe(risk_flags),
            gating_notes=gating_notes,
            block_reasons=_dedupe(block_reasons),
            trigger_source="cost_basis_pl_pct" if cost_basis_valid else "manual_review",
            diagnostics=diagnostics,
            position=position,
            duplicate_open_sell_order=duplicate_open_sell,
            latest_order=latest_order,
        )

    def _run_candidate_block_reasons(
        self,
        db: Session,
        *,
        context: _Context,
        account_state: dict[str, Any],
        candidates: list[_AutoSellCandidate],
        final_candidate: _AutoSellCandidate | None,
    ) -> list[str]:
        reasons: list[str] = []
        if account_state.get("fetch_success") is not True:
            reasons.append("broker_account_state_unavailable")
        if not candidates:
            reasons.append("no_held_position")
        if final_candidate is None:
            reasons.append("no_stop_loss_candidate")
            return _dedupe(reasons)
        if final_candidate.stop_loss_triggered is not True:
            if final_candidate.take_profit_triggered:
                reasons.append("take_profit_auto_sell_disabled")
            else:
                reasons.append(final_candidate.exit_reason or "no_stop_loss_candidate")
        if final_candidate.cost_basis is None or final_candidate.cost_basis <= 0:
            reasons.extend(["manual_review_required", "missing_cost_basis"])
        if final_candidate.current_price is None or final_candidate.current_price <= 0:
            reasons.append("current_price_unavailable")
        if final_candidate.unrealized_pl_pct is None:
            reasons.extend(["manual_review_required", "missing_or_ambiguous_pl_basis"])
        if final_candidate.status != SELL_READY and not final_candidate.block_reasons:
            reasons.append(final_candidate.exit_reason or "candidate_not_sell_ready")
        if final_candidate.quantity <= 0:
            reasons.append("quantity_not_positive")
        if not context.sell_session_allowed:
            reasons.append("sell_session_not_allowed")
        if final_candidate.duplicate_open_sell_order:
            reasons.append("duplicate_open_sell_order")
        daily_limit = self._daily_limit_state(
            db, context=context, symbol=final_candidate.symbol
        )
        daily_reason = _daily_limit_block_reason(daily_limit)
        if daily_reason:
            reasons.append(daily_reason)
        reasons.extend(final_candidate.block_reasons)
        return _dedupe(reasons)

    def _daily_limit_state(
        self,
        db: Session,
        *,
        context: _Context,
        symbol: str | None,
    ) -> dict[str, Any]:
        max_orders = max(
            0,
            int(context.runtime.get("kis_limited_auto_sell_max_orders_per_day", 1) or 0),
        )
        start_utc, end_utc = _day_bounds_utc(context.now_utc)
        rows = (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.side == SELL)
            .filter(OrderLog.created_at >= start_utc)
            .filter(OrderLog.created_at < end_utc)
            .all()
        )
        total = 0
        symbol_total = 0
        normalized_symbol = str(symbol or "").upper()
        for row in rows:
            if not _is_limited_auto_stop_loss_order(row):
                continue
            status = str(row.internal_status or "").upper()
            if status not in SUBMITTED_STATUSES:
                continue
            total += 1
            if normalized_symbol and str(row.symbol or "").upper() == normalized_symbol:
                symbol_total += 1
        return {
            "max_orders_per_day": max_orders,
            "submitted_count_today": total,
            "symbol_submitted_count_today": symbol_total,
            "daily_limit_remaining": max(0, max_orders - total),
            "symbol_already_auto_sold_today": symbol_total > 0,
            "daily_limit_reached": max_orders <= 0 or total >= max_orders,
            "checked_symbol": normalized_symbol or None,
        }

    def _validate_candidate(
        self,
        db: Session,
        *,
        context: _Context,
        candidate: _AutoSellCandidate | None,
    ) -> tuple[list[str] | None, dict[str, Any] | None]:
        if candidate is None:
            return ["no_stop_loss_candidate"], None
        request = KisOrderValidationRequest(
            market=MARKET,
            symbol=candidate.symbol,
            side=SELL,
            qty=candidate.quantity,
            order_type="market",
            dry_run=True,
            reason="KIS limited auto stop-loss validation.",
            source_metadata=_source_metadata(
                context=context,
                candidate=candidate,
                source_type=RUN_SOURCE_TYPE,
                real_order_submitted=False,
                broker_submit_called=False,
                manual_submit_called=False,
                real_order_submit_allowed=False,
                block_reasons=[],
                daily_limit=self._daily_limit_state(
                    db, context=context, symbol=candidate.symbol
                ),
            ),
        )
        try:
            validation = KisOrderValidationService(self.client).validate(
                request,
                now=context.now_utc,
            )
            record_kis_order_validation(db, request=request, result=validation)
        except Exception as exc:
            return ["backend_validation_failed"], {"error": _safe_error(exc)}
        payload = validation.to_dict()
        if not validation.validated_for_submission:
            reasons = _string_list(payload.get("block_reasons"))
            return reasons or ["backend_validation_failed"], payload
        return None, payload

    def _submit_via_existing_manual_path(
        self,
        db: Session,
        *,
        context: _Context,
        account_state: dict[str, Any],
        candidates: list[_AutoSellCandidate],
        final_candidate: _AutoSellCandidate | None,
        validation_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if final_candidate is None:
            raise ValueError("final_candidate is required after validation")

        source_metadata = _source_metadata(
            context=context,
            candidate=final_candidate,
            source_type=RUN_SOURCE_TYPE,
            real_order_submitted=False,
            broker_submit_called=False,
            manual_submit_called=False,
            real_order_submit_allowed=True,
            block_reasons=[],
            daily_limit=self._daily_limit_state(
                db, context=context, symbol=final_candidate.symbol
            ),
        )
        confirmation_phrase = str(
            getattr(context.settings, "kis_confirmation_phrase", None)
            or KIS_MANUAL_CONFIRMATION_PHRASE
        )
        request = KisManualOrderSubmitRequest(
            market=MARKET,
            symbol=final_candidate.symbol,
            side=SELL,
            qty=final_candidate.quantity,
            order_type="market",
            dry_run=False,
            confirm_live=True,
            confirmation=confirmation_phrase,
            reason="KIS limited auto stop-loss run.",
            source_metadata=source_metadata,
        )
        status_code, manual_payload = KisManualOrderService(
            self.client,
            runtime_settings=self.runtime_settings,
            session_service=self.session_service,
        ).submit_manual(db, request, now=context.now_utc)
        submitted = bool(manual_payload.get("real_order_submitted") is True)
        block_reasons = [] if submitted else _string_list(manual_payload.get("block_reasons"))
        reason = (
            "stop_loss_auto_sell_submitted"
            if submitted
            else block_reasons[0] if block_reasons else "manual_submit_blocked"
        )
        payload = self._decision_payload(
            db,
            context=context,
            mode=RUN_MODE,
            source_type=RUN_SOURCE_TYPE,
            result="submitted" if submitted else "blocked",
            action="sell" if submitted else _run_blocked_action(final_candidate),
            reason=reason,
            account_state=account_state,
            candidates=candidates,
            final_candidate=final_candidate,
            block_reasons=block_reasons,
            read_only=False,
            diagnostics_extra={
                "validation": validation_payload,
                "manual_submit_status_code": status_code,
                "manual_submit_response": manual_payload,
            },
        )
        payload.update(
            {
                "real_order_submitted": submitted,
                "broker_submit_called": bool(manual_payload.get("broker_submit_called")),
                "manual_submit_called": bool(manual_payload.get("manual_submit_called")),
                "order_id": manual_payload.get("order_id")
                or manual_payload.get("order_log_id"),
                "order_log_id": manual_payload.get("order_log_id")
                or manual_payload.get("order_id"),
                "broker_order_id": manual_payload.get("broker_order_id"),
                "broker_status": manual_payload.get("broker_status"),
                "broker_order_status": manual_payload.get("broker_order_status")
                or manual_payload.get("broker_status"),
                "kis_odno": manual_payload.get("kis_odno"),
            }
        )
        payload["source_metadata"] = _source_metadata(
            context=context,
            candidate=final_candidate,
            source_type=RUN_SOURCE_TYPE,
            real_order_submitted=submitted,
            broker_submit_called=bool(manual_payload.get("broker_submit_called")),
            manual_submit_called=bool(manual_payload.get("manual_submit_called")),
            real_order_submit_allowed=submitted,
            block_reasons=block_reasons,
            daily_limit=self._daily_limit_state(
                db, context=context, symbol=final_candidate.symbol
            ),
        )
        payload["audit_metadata"] = payload["source_metadata"]
        payload.update(kis_order_source_fields(payload["source_metadata"]))
        payload["safety"] = {
            **payload["safety"],
            "real_order_submitted": submitted,
            "broker_submit_called": bool(manual_payload.get("broker_submit_called")),
            "manual_submit_called": bool(manual_payload.get("manual_submit_called")),
            "no_broker_submit": not submitted,
        }
        signal = self._record_signal(
            db,
            payload=payload,
            candidate=final_candidate,
            source_type=RUN_SOURCE_TYPE,
            related_order_id=payload.get("order_id") if submitted else None,
        )
        run = self._record_run(
            db,
            payload=payload,
            candidate=final_candidate,
            mode=RUN_MODE,
            source_type=RUN_SOURCE_TYPE,
            signal_id=signal.id,
            order_id=payload.get("order_id") if submitted else None,
        )
        payload["signal_id"] = signal.id
        payload["run"] = _serialize_run(run)
        return sanitize_kis_payload(payload)

    def _decision_payload(
        self,
        db: Session,
        *,
        context: _Context,
        mode: str,
        source_type: str,
        result: str,
        action: str,
        reason: str,
        account_state: dict[str, Any] | None,
        candidates: list[_AutoSellCandidate],
        final_candidate: _AutoSellCandidate | None,
        block_reasons: list[str],
        read_only: bool,
        diagnostics_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        status_block_reasons = _status_block_reasons(context)
        daily_limit = self._daily_limit_state(
            db,
            context=context,
            symbol=final_candidate.symbol if final_candidate else None,
        )
        candidate_payloads = [_candidate_payload(candidate) for candidate in candidates]
        final_payload = (
            _candidate_payload(final_candidate) if final_candidate is not None else None
        )
        safety = _safety_payload(
            context,
            read_only=read_only,
            source_type=source_type,
        )
        metadata = (
            _source_metadata(
                context=context,
                candidate=final_candidate,
                source_type=source_type,
                real_order_submitted=False,
                broker_submit_called=False,
                manual_submit_called=False,
                real_order_submit_allowed=False,
                block_reasons=block_reasons,
                daily_limit=daily_limit,
            )
            if final_candidate is not None
            else None
        )
        all_block_reasons = _dedupe(block_reasons)
        diagnostics = {
            "positions_evaluated": len(candidates),
            "candidate_selected": final_candidate is not None,
            "status_block_reasons": status_block_reasons,
            "daily_limit": daily_limit,
            "account_state": _account_state_summary(account_state or {}),
            "market_session": _public_market_session(context.market_session),
            "cost_basis_required_for_stop_loss": True,
            "take_profit_actionable": False,
            "read_only": read_only,
        }
        validation_payload = (
            diagnostics.get("validation")
            if isinstance(diagnostics.get("validation"), dict)
            else None
        )
        if diagnostics_extra:
            diagnostics.update(diagnostics_extra)
            validation_payload = (
                diagnostics.get("validation")
                if isinstance(diagnostics.get("validation"), dict)
                else None
            )
        validation_status = _validation_status(validation_payload, read_only=read_only)
        payload: dict[str, Any] = {
            "status": "ok",
            "provider": PROVIDER,
            "market": MARKET,
            "mode": mode,
            "source": SOURCE,
            "source_type": source_type,
            "trigger_source": _trigger_source(source_type),
            "result": result,
            "action": action,
            "reason": reason,
            "primary_block_reason": all_block_reasons[0] if all_block_reasons else None,
            "human_readable_status": _human_status(result, reason, all_block_reasons),
            "candidate_count": len(candidate_payloads),
            "candidates": candidate_payloads,
            "final_candidate": final_payload,
            "symbol": final_candidate.symbol if final_candidate else None,
            "company_name": final_candidate.name if final_candidate else None,
            "name": final_candidate.name if final_candidate else None,
            "quantity": final_candidate.quantity if final_candidate else None,
            "qty": final_candidate.quantity if final_candidate else None,
            "current_price": final_candidate.current_price if final_candidate else None,
            "average_price": final_candidate.average_price if final_candidate else None,
            "cost_basis": final_candidate.cost_basis if final_candidate else None,
            "current_value": final_candidate.current_value if final_candidate else None,
            "unrealized_pl": final_candidate.unrealized_pl if final_candidate else None,
            "unrealized_pl_pct": (
                final_candidate.unrealized_pl_pct if final_candidate else None
            ),
            "stop_loss_threshold_pct": (
                final_candidate.stop_loss_threshold_pct if final_candidate else None
            ),
            "take_profit_threshold_pct": (
                final_candidate.take_profit_threshold_pct if final_candidate else None
            ),
            "trigger": (
                STOP_LOSS_TRIGGER
                if final_candidate and final_candidate.stop_loss_triggered
                else TAKE_PROFIT_TRIGGER
                if final_candidate and final_candidate.take_profit_triggered
                else None
            ),
            "trigger_source_detail": (
                final_candidate.trigger_source if final_candidate else None
            ),
            "exit_trigger": (
                STOP_LOSS_TRIGGER
                if final_candidate and final_candidate.stop_loss_triggered
                else TAKE_PROFIT_TRIGGER
                if final_candidate and final_candidate.take_profit_triggered
                else None
            ),
            "exit_trigger_source": (
                final_candidate.trigger_source if final_candidate else None
            ),
            "side": SELL,
            "stop_loss_triggered": bool(
                final_candidate and final_candidate.stop_loss_triggered
            ),
            "take_profit_triggered": bool(
                final_candidate and final_candidate.take_profit_triggered
            ),
            "weak_trend_triggered": bool(
                final_candidate and final_candidate.weak_trend_triggered
            ),
            "sell_pressure_triggered": bool(
                final_candidate and final_candidate.sell_pressure_triggered
            ),
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "broker_order_id": None,
            "kis_odno": None,
            "order_id": None,
            "order_log_id": None,
            "live_auto_sell_enabled": context.live_auto_sell_enabled,
            "stop_loss_auto_sell_enabled": context.stop_loss_enabled,
            "take_profit_auto_sell_enabled": False,
            "scheduler_real_orders_enabled": False,
            "dry_run": bool(context.runtime.get("dry_run", True)),
            "kill_switch": bool(context.runtime.get("kill_switch", False)),
            "kis_enabled": bool(getattr(context.settings, "kis_enabled", False)),
            "kis_real_order_enabled": bool(
                getattr(context.settings, "kis_real_order_enabled", False)
            ),
            "market_open": context.market_session.get("is_market_open") is True,
            "sell_session_allowed": context.sell_session_allowed,
            "auto_order_ready": bool(
                final_candidate is not None
                and final_candidate.stop_loss_triggered
                and not all_block_reasons
            ),
            "real_order_submit_allowed": bool(
                source_type == RUN_SOURCE_TYPE
                and final_candidate is not None
                and final_candidate.stop_loss_triggered
                and not all_block_reasons
                and not read_only
            ),
            "stop_loss_execution_enabled": (
                not status_block_reasons
                and daily_limit["daily_limit_remaining"] > 0
            ),
            "daily_limit_remaining": daily_limit["daily_limit_remaining"],
            "daily_limit": daily_limit,
            "duplicate_order_check": {
                "duplicate_open_sell_order": bool(
                    final_candidate and final_candidate.duplicate_open_sell_order
                ),
                "latest_related_sell_order": (
                    final_candidate.latest_order if final_candidate else None
                ),
            },
            "validation_status": validation_status,
            "block_reasons": all_block_reasons,
            "blocked_by": all_block_reasons,
            "failed_checks": all_block_reasons,
            "safety": safety,
            "diagnostics": diagnostics,
            "checks": _checks_payload(context, account_state=account_state),
            "risk_flags": _dedupe(
                ["limited_auto_sell", "stop_loss_only", "no_auto_buy"]
                + _string_list(final_candidate.risk_flags if final_candidate else [])
                + all_block_reasons
            ),
            "gating_notes": _dedupe(
                [
                    "readiness_only" if read_only else "guarded_execution",
                    "stop_loss_only",
                    "take_profit_disabled",
                    "auto_buy_disabled",
                    "scheduler_real_orders_disabled",
                    "no_broker_submit_unless_all_gates_pass",
                ]
                + _string_list(final_candidate.gating_notes if final_candidate else [])
            ),
            "audit_metadata": metadata,
            "source_metadata": metadata,
            "market_session": _public_market_session(context.market_session),
            "account_state": _account_state_summary(account_state or {}),
            "readiness_labels": _readiness_labels(
                read_only=read_only,
                submitted=result == "submitted",
            ),
            "created_at": context.created_at,
            "checked_at": context.created_at,
        }
        if metadata:
            payload.update(kis_order_source_fields(metadata))
        return sanitize_kis_payload(payload)

    def _record_signal(
        self,
        db: Session,
        *,
        payload: dict[str, Any],
        candidate: _AutoSellCandidate | None,
        source_type: str,
        related_order_id: int | None = None,
    ) -> SignalLog:
        signal = SignalLog(
            symbol=(candidate.symbol if candidate else None) or "WATCHLIST",
            action=str(payload.get("action") or "hold"),
            reason=str(payload.get("reason") or "limited_auto_sell_blocked"),
            indicator_payload=_json((candidate.position if candidate else {}) or {}),
            risk_flags=_json(payload.get("risk_flags") or []),
            approved_by_risk=payload.get("real_order_submitted") is True,
            related_order_id=related_order_id,
            signal_status=source_type,
            trigger_source=_trigger_source(source_type),
            hard_block_reason=(
                None
                if payload.get("real_order_submitted") is True
                else str(payload.get("reason") or "limited_auto_sell_blocked")
            ),
            hard_blocked=payload.get("real_order_submitted") is not True,
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
        candidate: _AutoSellCandidate | None,
        mode: str,
        source_type: str,
        signal_id: int,
        order_id: int | None,
    ) -> TradeRunLog:
        run = TradeRunLog(
            run_key=f"kis_limited_auto_sell_{uuid.uuid4().hex[:10]}",
            trigger_source=_trigger_source(source_type),
            symbol=(candidate.symbol if candidate else None) or "WATCHLIST",
            mode=mode,
            stage="done",
            result=str(payload.get("result") or "blocked"),
            reason=str(payload.get("reason") or ""),
            signal_id=signal_id,
            order_id=order_id,
            request_payload=_json(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": mode,
                    "source": SOURCE,
                    "source_type": source_type,
                    "trigger_source": _trigger_source(source_type),
                    "real_order_submitted": payload.get("real_order_submitted") is True,
                    "broker_submit_called": payload.get("broker_submit_called") is True,
                    "manual_submit_called": payload.get("manual_submit_called") is True,
                }
            ),
            response_payload=_json(payload),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run


def _status_payload(
    *,
    context: _Context,
    block_reasons: list[str],
    daily_limit: dict[str, Any],
    result: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "status": "ok",
        "provider": PROVIDER,
        "market": MARKET,
        "mode": STATUS_MODE,
        "source": SOURCE,
        "source_type": "limited_auto_sell_status",
        "trigger_source": "limited_auto_sell_status",
        "result": result,
        "action": "hold",
        "reason": reason,
        "primary_block_reason": block_reasons[0] if block_reasons else None,
        "live_auto_sell_enabled": context.live_auto_sell_enabled,
        "stop_loss_auto_sell_enabled": context.stop_loss_enabled,
        "take_profit_auto_sell_enabled": False,
        "scheduler_real_orders_enabled": False,
        "dry_run": bool(context.runtime.get("dry_run", True)),
        "kill_switch": bool(context.runtime.get("kill_switch", False)),
        "kis_enabled": bool(getattr(context.settings, "kis_enabled", False)),
        "kis_real_order_enabled": bool(
            getattr(context.settings, "kis_real_order_enabled", False)
        ),
        "market_open": context.market_session.get("is_market_open") is True,
        "sell_session_allowed": context.sell_session_allowed,
        "auto_order_ready": False,
        "real_order_submit_allowed": False,
        "stop_loss_execution_enabled": (
            not block_reasons and daily_limit["daily_limit_remaining"] > 0
        ),
        "daily_limit_remaining": daily_limit["daily_limit_remaining"],
        "daily_limit": daily_limit,
        "block_reasons": block_reasons,
        "blocked_by": block_reasons,
        "human_readable_status": _human_status(result, reason, block_reasons),
        "candidate_count": 0,
        "candidates": [],
        "final_candidate": None,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "live_auto_buy_enabled": False,
        "configured_live_auto_buy_enabled": context.live_auto_buy_configured,
        "configured_take_profit_auto_sell_enabled": context.take_profit_enabled,
        "configured_scheduler_real_orders_enabled": (
            context.scheduler_real_orders_configured
        ),
        "configured_scheduler_limited_auto_sell_enabled": (
            context.scheduler_limited_auto_sell_configured
        ),
        "safety": _safety_payload(
            context,
            read_only=True,
            source_type="limited_auto_sell_status",
        ),
        "checks": _checks_payload(context, account_state=None),
        "diagnostics": {
            "status_only": True,
            "positions_evaluated": 0,
            "market_session": _public_market_session(context.market_session),
            "daily_limit": daily_limit,
            "runtime_aliases": {
                "kis_limited_auto_stop_loss_enabled": context.stop_loss_enabled,
                "kis_limited_auto_take_profit_enabled": False,
            },
        },
        "readiness_labels": _readiness_labels(read_only=True, submitted=False),
        "market_session": _public_market_session(context.market_session),
        "created_at": context.created_at,
        "checked_at": context.created_at,
    }


def _checks_payload(
    context: _Context,
    *,
    account_state: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = {
        "dry_run": bool(context.runtime.get("dry_run", True)),
        "dry_run_false": bool(context.runtime.get("dry_run", True)) is False,
        "kill_switch": bool(context.runtime.get("kill_switch", False)),
        "kill_switch_false": bool(context.runtime.get("kill_switch", False)) is False,
        "kis_enabled": bool(getattr(context.settings, "kis_enabled", False)),
        "kis_real_order_enabled": bool(
            getattr(context.settings, "kis_real_order_enabled", False)
        ),
        "kis_live_auto_sell_enabled": context.live_auto_sell_enabled,
        "kis_live_auto_buy_enabled": False,
        "configured_kis_live_auto_buy_enabled": context.live_auto_buy_configured,
        "kis_limited_auto_stop_loss_enabled": context.stop_loss_enabled,
        "kis_limited_auto_sell_stop_loss_enabled": context.stop_loss_enabled,
        "kis_limited_auto_take_profit_enabled": False,
        "kis_limited_auto_sell_take_profit_enabled": False,
        "configured_take_profit_auto_sell_enabled": context.take_profit_enabled,
        "kis_scheduler_allow_real_orders": False,
        "configured_scheduler_real_orders_enabled": (
            context.scheduler_real_orders_configured
        ),
        "configured_scheduler_limited_auto_sell_enabled": (
            context.scheduler_limited_auto_sell_configured
        ),
        "scheduler_real_orders_disabled": (
            context.scheduler_real_orders_configured is False
        ),
        "scheduler_limited_auto_sell_disabled": (
            context.scheduler_limited_auto_sell_configured is False
        ),
        "market_open": context.market_session.get("is_market_open") is True,
        "sell_session_allowed": context.sell_session_allowed,
    }
    if account_state is not None:
        payload.update(
            {
                "account_state_available": bool(account_state.get("fetch_success")),
                "positions_available": bool(account_state.get("positions")),
                "open_order_fetch_available": "open_orders_unavailable"
                not in _warning_names(account_state),
            }
        )
    return payload


def _safety_payload(
    context: _Context,
    *,
    read_only: bool,
    source_type: str,
) -> dict[str, Any]:
    return {
        "read_only": read_only,
        "readiness_only": source_type != RUN_SOURCE_TYPE,
        "preflight_only": source_type == PREFLIGHT_SOURCE_TYPE,
        "guarded_execution": source_type == RUN_SOURCE_TYPE,
        "stop_loss_only": True,
        "take_profit_disabled": True,
        "take_profit_auto_sell_enabled": False,
        "auto_buy_disabled": True,
        "live_auto_buy_enabled": False,
        "scheduler_real_orders_enabled": False,
        "scheduler_real_order_enabled": False,
        "dry_run": bool(context.runtime.get("dry_run", True)),
        "kill_switch": bool(context.runtime.get("kill_switch", False)),
        "max_orders_per_day": int(
            context.runtime.get("kis_limited_auto_sell_max_orders_per_day", 1) or 1
        ),
        "requires_valid_cost_basis": _requires_valid_cost_basis(context.runtime),
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "no_broker_submit": True,
        "uses_existing_manual_submit_path": True,
    }


def _status_block_reasons(context: _Context) -> list[str]:
    reasons: list[str] = []
    if bool(context.runtime.get("dry_run", True)):
        reasons.append("dry_run_true")
    if bool(context.runtime.get("kill_switch", False)):
        reasons.append("kill_switch_enabled")
    if not bool(getattr(context.settings, "kis_enabled", False)):
        reasons.append("kis_disabled")
    if not bool(getattr(context.settings, "kis_real_order_enabled", False)):
        reasons.append("kis_real_order_disabled")
    if context.live_auto_buy_configured:
        reasons.append("live_auto_buy_must_remain_disabled")
    if not context.live_auto_sell_enabled:
        reasons.append("kis_live_auto_sell_disabled")
    if not context.stop_loss_enabled:
        reasons.append("stop_loss_auto_sell_disabled")
    if context.take_profit_enabled:
        reasons.append("take_profit_auto_sell_must_remain_disabled")
    if context.scheduler_real_orders_configured:
        reasons.append("scheduler_real_orders_must_remain_disabled")
    if context.scheduler_limited_auto_sell_configured:
        reasons.append("scheduler_limited_auto_sell_must_remain_disabled")
    if not context.sell_session_allowed:
        reasons.append("sell_session_not_allowed")
    return _dedupe(reasons)


def _run_pre_account_block_reasons(context: _Context) -> list[str]:
    return _status_block_reasons(context)


def _daily_limit_block_reason(daily_limit: dict[str, Any]) -> str | None:
    if bool(daily_limit.get("symbol_already_auto_sold_today")):
        return "symbol_already_auto_sold_today"
    if bool(daily_limit.get("daily_limit_reached")):
        return "daily_auto_sell_limit_reached"
    return None


def _preflight_block_reasons(candidate: _AutoSellCandidate | None) -> list[str]:
    reasons = ["preflight_read_only_no_submit"]
    if candidate is None:
        reasons.append("no_held_position")
    elif candidate.block_reasons:
        reasons.extend(candidate.block_reasons)
    return _dedupe(reasons)


def _preflight_result(candidate: _AutoSellCandidate | None) -> str:
    if candidate is None:
        return "blocked"
    return "preview_only"


def _preflight_reason(candidate: _AutoSellCandidate | None) -> str:
    if candidate is None:
        return "no_held_position"
    if candidate.status == SELL_READY:
        return "stop_loss_candidate_ready_read_only"
    if candidate.status == REVIEW_SELL:
        return candidate.exit_reason or "manual_review_required"
    return "no_stop_loss_candidate"


def _action_for_candidate(candidate: _AutoSellCandidate | None) -> str:
    if candidate is None:
        return "hold"
    if candidate.status == SELL_READY:
        return "sell_ready"
    if candidate.status == REVIEW_SELL:
        return "review_sell"
    return "hold"


def _trigger_source(source_type: str) -> str:
    if source_type == RUN_SOURCE_TYPE:
        return RUN_TRIGGER_SOURCE
    return TRIGGER_SOURCE


def _run_blocked_action(candidate: _AutoSellCandidate | None) -> str:
    if candidate is not None and candidate.stop_loss_triggered:
        return "blocked_sell"
    return "hold"


def _validation_status(
    validation_payload: dict[str, Any] | None,
    *,
    read_only: bool,
) -> str:
    if read_only:
        return "not_called_read_only"
    if validation_payload is None:
        return "not_called"
    if validation_payload.get("validated_for_submission") is True:
        return "passed"
    return "blocked"


def _readiness_labels(*, read_only: bool, submitted: bool) -> list[str]:
    labels = [
        "STOP-LOSS ONLY",
        "GUARDED EXECUTION",
        "DEFAULT OFF",
        "TAKE-PROFIT DISABLED",
        "AUTO BUY DISABLED",
        "SCHEDULER REAL ORDERS DISABLED",
    ]
    labels.append("BROKER SUBMIT CALLED" if submitted else "NO BROKER SUBMIT")
    if read_only:
        labels.append("READ-ONLY")
    return labels


def _select_final_candidate(
    candidates: list[_AutoSellCandidate],
) -> _AutoSellCandidate | None:
    if not candidates:
        return None
    sell_ready = [item for item in candidates if item.status == SELL_READY]
    if sell_ready:
        sell_ready.sort(
            key=lambda item: (
                abs(_safe_float(item.unrealized_pl, 0.0)),
                _safe_float(item.current_value, 0.0),
            ),
            reverse=True,
        )
        return sell_ready[0]
    review = [item for item in candidates if item.status == REVIEW_SELL]
    if review:
        review.sort(
            key=lambda item: _safe_float(item.current_value, 0.0),
            reverse=True,
        )
        return review[0]
    return candidates[0]


def _candidate_payload(candidate: _AutoSellCandidate) -> dict[str, Any]:
    return {
        "provider": PROVIDER,
        "market": MARKET,
        "symbol": candidate.symbol,
        "name": candidate.name,
        "company_name": candidate.name,
        "quantity": candidate.quantity,
        "qty": candidate.held_qty,
        "current_price": candidate.current_price,
        "average_price": candidate.average_price,
        "avg_entry_price": candidate.average_price,
        "cost_basis": candidate.cost_basis,
        "current_value": candidate.current_value,
        "market_value": candidate.current_value,
        "unrealized_pl": candidate.unrealized_pl,
        "unrealized_pl_pct": candidate.unrealized_pl_pct,
        "stop_loss_threshold_pct": candidate.stop_loss_threshold_pct,
        "take_profit_threshold_pct": candidate.take_profit_threshold_pct,
        "stop_loss_triggered": candidate.stop_loss_triggered,
        "take_profit_triggered": candidate.take_profit_triggered,
        "weak_trend_triggered": candidate.weak_trend_triggered,
        "sell_pressure_triggered": candidate.sell_pressure_triggered,
        "status": candidate.status,
        "holding_status": candidate.status,
        "exit_reason": candidate.exit_reason,
        "risk_flags": candidate.risk_flags,
        "gating_notes": candidate.gating_notes,
        "block_reasons": candidate.block_reasons,
        "trigger_source": candidate.trigger_source,
        "latest_order": candidate.latest_order,
        "latest_related_sell_order": candidate.latest_order,
        "duplicate_open_sell_order": candidate.duplicate_open_sell_order,
        "manual_review_required": "manual_review_required" in candidate.block_reasons,
        "pl_diagnostics": candidate.diagnostics,
    }


def _source_metadata(
    *,
    context: _Context,
    candidate: _AutoSellCandidate,
    source_type: str,
    real_order_submitted: bool,
    broker_submit_called: bool,
    manual_submit_called: bool,
    real_order_submit_allowed: bool,
    block_reasons: list[str],
    daily_limit: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": SOURCE,
        "source_type": source_type,
        "mode": RUN_MODE if source_type == RUN_SOURCE_TYPE else PREFLIGHT_MODE,
        "limited_auto_sell_checked_at": context.created_at,
        "checked_at": context.created_at,
        "symbol": candidate.symbol,
        "company_name": candidate.name,
        "quantity": candidate.quantity,
        "exit_trigger": STOP_LOSS_TRIGGER
        if candidate.stop_loss_triggered
        else TAKE_PROFIT_TRIGGER
        if candidate.take_profit_triggered
        else "none",
        "trigger_source": _trigger_source(source_type),
        "pl_trigger_source": candidate.trigger_source,
        "trigger_flags": {
            "stop_loss_triggered": candidate.stop_loss_triggered,
            "take_profit_triggered": False,
            "take_profit_triggered_ignored": candidate.take_profit_triggered,
            "weak_trend_triggered": candidate.weak_trend_triggered,
            "sell_pressure_triggered": candidate.sell_pressure_triggered,
        },
        "position_snapshot": {
            "symbol": candidate.symbol,
            "quantity": candidate.quantity,
            "cost_basis": candidate.cost_basis,
            "current_price": candidate.current_price,
            "current_value": candidate.current_value,
            "unrealized_pl": candidate.unrealized_pl,
            "unrealized_pl_pct": candidate.unrealized_pl_pct,
            "status": candidate.status,
        },
        "duplicate_order_check": {
            "duplicate_open_sell_order": candidate.duplicate_open_sell_order,
            "latest_related_sell_order": candidate.latest_order,
        },
        "daily_limit": daily_limit,
        "runtime_safety_snapshot": {
            "dry_run": bool(context.runtime.get("dry_run", True)),
            "kill_switch": bool(context.runtime.get("kill_switch", False)),
            "kis_live_auto_sell_enabled": context.live_auto_sell_enabled,
            "kis_limited_auto_stop_loss_enabled": context.stop_loss_enabled,
            "kis_limited_auto_take_profit_enabled": False,
            "kis_scheduler_allow_real_orders": False,
            "kis_live_auto_buy_enabled": False,
            "kis_enabled": bool(getattr(context.settings, "kis_enabled", False)),
            "kis_real_order_enabled": bool(
                getattr(context.settings, "kis_real_order_enabled", False)
            ),
        },
        "market_session_snapshot": _public_market_session(context.market_session),
        "stop_loss_triggered": candidate.stop_loss_triggered,
        "take_profit_triggered": False,
        "take_profit_triggered_ignored": candidate.take_profit_triggered,
        "weak_trend_triggered": candidate.weak_trend_triggered,
        "sell_pressure_triggered": candidate.sell_pressure_triggered,
        "status": candidate.status,
        "block_reasons": block_reasons,
        "real_order_submitted": real_order_submitted,
        "broker_submit_called": broker_submit_called,
        "manual_submit_called": manual_submit_called,
        "limited_auto_sell_real_order_submitted": real_order_submitted,
        "limited_auto_sell_broker_submit_called": broker_submit_called,
        "limited_auto_sell_manual_submit_called": manual_submit_called,
        "manual_confirm_required": False,
        "auto_buy_enabled": False,
        "auto_sell_enabled": real_order_submitted,
        "scheduler_real_order_enabled": False,
        "real_order_submit_allowed": real_order_submit_allowed,
        "limited_auto_sell_enabled": context.live_auto_sell_enabled,
        "stop_loss_auto_sell_enabled": context.stop_loss_enabled,
        "take_profit_auto_sell_enabled": False,
        "manual_review_auto_sell_enabled": False,
        "unrealized_pl": candidate.unrealized_pl,
        "unrealized_pl_pct": candidate.unrealized_pl_pct,
        "cost_basis": candidate.cost_basis,
        "current_value": candidate.current_value,
        "current_price": candidate.current_price,
        "suggested_quantity": candidate.quantity,
        "risk_flags": candidate.risk_flags,
        "gating_notes": candidate.gating_notes,
    }


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
        "name": _name(item),
        "qty": to_float(item.get("qty") or item.get("hldg_qty") or 0),
        "avg_entry_price": to_float(
            item.get("avg_entry_price") or item.get("pchs_avg_pric") or 0
        ),
        "current_price": to_float(
            item.get("current_price") or item.get("prpr") or item.get("stck_prpr") or 0
        ),
        "market_value": to_float(item.get("market_value") or item.get("evlu_amt") or 0),
        "current_value": to_float(
            item.get("current_value")
            or item.get("market_value")
            or item.get("evlu_amt")
            or 0
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


def _has_duplicate_open_sell(
    db: Session,
    *,
    symbol: str,
    account_state: dict[str, Any],
) -> bool:
    if not symbol:
        return False
    normalized = symbol.upper()
    for order in _dict_list(account_state.get("open_orders")):
        if _order_symbol(order) == normalized and _order_is_sell(order):
            return True
    for order in _dict_list(account_state.get("recent_orders")):
        if _order_symbol(order) != normalized:
            continue
        status = str(
            order.get("internal_status")
            or order.get("clear_status")
            or order.get("status")
            or ""
        ).upper()
        if status in OPEN_ORDER_STATUSES and _order_is_sell(order):
            return True
    row = (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.symbol == normalized)
        .filter(OrderLog.side == SELL)
        .filter(OrderLog.internal_status.in_(sorted(OPEN_ORDER_STATUSES)))
        .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
        .first()
    )
    return row is not None


def _latest_related_sell_order(
    db: Session,
    *,
    symbol: str,
    account_state: dict[str, Any],
) -> dict[str, Any] | None:
    normalized = symbol.upper()
    for order in _dict_list(account_state.get("open_orders")):
        if _order_symbol(order) == normalized and _order_is_sell(order):
            return order
    for order in _dict_list(account_state.get("recent_orders")):
        if _order_symbol(order) == normalized and _order_is_sell(order):
            return order
    row = (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.symbol == normalized)
        .filter(OrderLog.side == SELL)
        .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
        .first()
    )
    return serialize_kis_order(row) if row is not None else None


def _is_limited_auto_stop_loss_order(row: OrderLog) -> bool:
    for raw in (row.response_payload, row.request_payload, row.last_sync_payload):
        payload = _parse_json_object(raw)
        hint = " ".join(
            str(payload.get(key) or "")
            for key in ("mode", "source", "source_type", "trigger_source")
        ).lower()
        if "limited_auto_sell" in hint or "kis_limited_auto_stop_loss" in hint:
            return True
        metadata = payload.get("source_metadata")
        if isinstance(metadata, dict):
            source = str(metadata.get("source") or "").lower()
            if source in {"kis_limited_auto_stop_loss", "kis_limited_auto_sell"}:
                return True
    return False


def _weak_trend_triggered(position: dict[str, Any]) -> bool:
    flags = {flag.lower() for flag in _string_list(position.get("risk_flags"))}
    if "weak_trend_triggered" in flags or "weak_trend" in flags:
        return True
    for key in ("momentum", "recent_return"):
        value = _safe_float_or_none(position.get(key))
        if value is not None and value < 0:
            return True
    return False


def _sell_pressure_triggered(position: dict[str, Any]) -> bool:
    sell_score = _first_float(position, "final_sell_score", "sell_score", "quant_sell_score")
    buy_score = _first_float(position, "final_buy_score", "final_entry_score", "score")
    if sell_score is None:
        return False
    if sell_score >= 65:
        return True
    return buy_score is not None and sell_score >= 50 and sell_score > buy_score


def _candidate_gating_notes(
    *,
    status: str,
    stop_loss_triggered: bool,
    take_profit_triggered: bool,
    cost_basis_valid: bool,
    duplicate_open_sell: bool,
) -> list[str]:
    notes = [
        "Limited KIS auto sell is readiness/preflight-first.",
        "Only cost-basis stop-loss is actionable in this PR.",
        "Take-profit auto sell is visible but disabled.",
        "KIS auto buy and scheduler real orders remain disabled.",
    ]
    if status == SELL_READY and stop_loss_triggered:
        notes.append("Stop-loss threshold was reached with valid cost basis.")
    if take_profit_triggered:
        notes.append("Take-profit trigger is non-actionable in this PR.")
    if not cost_basis_valid:
        notes.append("Missing or ambiguous cost basis requires manual review.")
    if duplicate_open_sell:
        notes.append("Existing open sell order blocks auto sell.")
    return _dedupe(notes)


def _stop_loss_enabled(runtime: dict[str, Any]) -> bool:
    return bool(
        runtime.get(
            "kis_limited_auto_stop_loss_enabled",
            runtime.get("kis_limited_auto_sell_stop_loss_enabled", False),
        )
    )


def _take_profit_enabled(runtime: dict[str, Any]) -> bool:
    return bool(
        runtime.get(
            "kis_limited_auto_take_profit_enabled",
            runtime.get("kis_limited_auto_sell_take_profit_enabled", False),
        )
    )


def _requires_valid_cost_basis(runtime: dict[str, Any]) -> bool:
    return bool(runtime.get("kis_limited_auto_sell_requires_valid_cost_basis", True))


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
        "local_time",
        "error",
    ]
    return {key: market_session.get(key) for key in keys if key in market_session}


def _human_status(result: str, reason: str, block_reasons: list[str]) -> str:
    if result == "submitted":
        return "Stop-loss auto sell submitted through existing KIS manual order flow."
    if result == "preview_only":
        return "Read-only stop-loss preflight completed. No broker submit was called."
    if block_reasons:
        return f"Blocked: {block_reasons[0]}."
    return reason or "Ready."


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


def _name(payload: dict[str, Any]) -> str | None:
    for key in (
        "name",
        "company_name",
        "display_name",
        "symbol_name",
        "korean_name",
        "asset_name",
        "prdt_name",
    ):
        text = str(payload.get(key) or "").strip()
        if text:
            return text
    return None


def _first_reason(values: list[str], fallback: str) -> str:
    for value in values:
        if value:
            return value
    return fallback


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
