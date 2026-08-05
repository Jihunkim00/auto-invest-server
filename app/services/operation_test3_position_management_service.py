from __future__ import annotations

import json
import re
import time as time_module
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, PositionLifecycle, TradeRunLog
from app.services.kis_dry_run_risk_service import MARKET, OPEN_ORDER_STATUSES, PROVIDER
from app.services.kis_limited_auto_sell_service import KisLimitedAutoSellService
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService

KR_TZ = ZoneInfo("Asia/Seoul")
OPERATION_TEST = "test3"
PHASE = "position_management"
MODE = "operation_test3_position_management"
STATUS_MODE = "operation_test3_position_management_status"
PREFLIGHT_MODE = "operation_test3_position_management_preflight"
RUN_MODE = "operation_test3_position_management_run"
TRADE_RUN_PREFLIGHT_MODE = "op_test3_pm_preflight"
TRADE_RUN_RUN_MODE = "op_test3_pm_run"
LIVE_READINESS_MODE = "operation_test3_live_readiness"
MANUAL_PREFLIGHT_TRIGGER_SOURCE = "operation_test3_preflight_once"
MANUAL_RUN_TRIGGER_SOURCE = "operation_test3_run_once"
SCHEDULER_TRIGGER_SOURCE = "operation_test3_scheduler"
ENABLE_CONFIRMATION = "ENABLE TEST3 POSITION MANAGEMENT"
MONITORING_CONFIRMATION = "ENABLE TEST3 MONITORING"
OPEN = "open"
CLOSING = "closing"
CLOSED = "closed"
HOLD = "HOLD"
SELL_READY = "SELL_READY"
TAKE_PROFIT_READY = "TAKE_PROFIT_READY"
REVIEW = "REVIEW"
SELL = "sell"
SCHEDULER_SLOTS_KST = ["10:00", "12:00", "14:30"]
BROKER_POSITION_READ_MAX_ATTEMPTS = 2
BROKER_POSITION_READ_RETRY_DELAY_SECONDS = 1.0

BUY_FLAGS = (
    "kis_live_auto_buy_enabled",
    "kis_limited_auto_buy_enabled",
    "kis_scheduler_buy_enabled",
    "kis_scheduler_allow_limited_auto_buy",
    "strategy_auto_buy_scheduler_enabled",
    "strategy_live_auto_buy_scheduler_enabled",
    "auto_buy_live_phase1_enabled",
    "auto_buy_live_phase1_allow_real_orders",
)
SUBMITTED_SELL_STATUSES = {
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}
CLOSING_SELL_STATUSES = {
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
}
REVIEW_SELL_STATUSES = {
    InternalOrderStatus.REJECTED.value,
    InternalOrderStatus.CANCELED.value,
    InternalOrderStatus.EXPIRED.value,
    InternalOrderStatus.FAILED.value,
    InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value,
}


class OperationTest3PositionManagementService:
    """Dedicated sell-only position manager for Operation Test 3."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        limited_auto_sell_service: Any | None = None,
        session_service: MarketSessionService | None = None,
        now_provider: Any | None = None,
        sleeper: Any | None = None,
        broker_position_read_retry_delay_seconds: float = BROKER_POSITION_READ_RETRY_DELAY_SECONDS,
    ) -> None:
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.limited_auto_sell_service = limited_auto_sell_service
        self.session_service = session_service or MarketSessionService()
        self.now_provider = now_provider or (lambda: datetime.now(UTC))
        self.sleeper = sleeper or time_module.sleep
        self.broker_position_read_retry_delay_seconds = broker_position_read_retry_delay_seconds

    def status(self, db: Session) -> dict[str, Any]:
        runtime = self.runtime_settings.get_settings_read_only(db)
        active = _active_lifecycles(db)
        latest_run = _latest_test3_run(db)
        return sanitize_kis_payload(
            {
                "provider": PROVIDER,
                "market": MARKET,
                "mode": STATUS_MODE,
                "operation_test": OPERATION_TEST,
                "operation_test3_phase": PHASE,
                "status": "ok",
                "sell_only": True,
                "position_first": True,
                "buy_execution_allowed": False,
                "active_lifecycle_count": len(active),
                "active_lifecycles": [_serialize_lifecycle(row) for row in active],
                "runtime": _runtime_snapshot(runtime, self._settings()),
                "scheduler": {
                    **operation_test3_scheduler_gate(runtime),
                    "slots_kst": SCHEDULER_SLOTS_KST,
                    "runs_only_when_position_exists": True,
                    "sell_only": True,
                    "buy_execution_allowed": False,
                },
                "latest_run": _serialize_run(latest_run) if latest_run else None,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        )

    def live_readiness(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _aware_utc(now or self.now_provider())
        runtime = self.runtime_settings.get_settings_read_only(db)
        settings = self._settings()
        active = _active_lifecycles(db)
        lifecycle = active[0] if len(active) == 1 else None

        positions, broker_position_read = self._broker_positions_with_retry()
        try:
            open_orders = self._broker_open_orders()
            open_orders_error = None
        except Exception as exc:
            open_orders = []
            open_orders_error = _safe_error(exc)

        held_positions = [_normalize_position(item) for item in positions]
        held_positions = [item for item in held_positions if _safe_float(item.get("qty"), 0.0) > 0]
        broker_position = held_positions[0] if len(held_positions) == 1 else None
        local_pending = _local_pending_sell_order(db, lifecycle.symbol) if lifecycle is not None else None
        broker_pending = (
            _broker_open_sell_order(open_orders, lifecycle.symbol)
            if lifecycle is not None
            else None
        )
        daily = _daily_sell_state(db, runtime=runtime, now_utc=now_utc)
        market_session = self._market_session(now_utc)
        sell_session_allowed = _sell_session_allowed(market_session)
        runtime_snapshot = _runtime_snapshot(runtime, settings)

        checks: list[dict[str, Any]] = []
        blocking_reasons: list[str] = []
        review_reasons: list[str] = []

        def add_check(
            key: str,
            passed: bool,
            *,
            reason: str | None = None,
            category: str = "blocking",
            blocking: bool = True,
            detail: Any | None = None,
        ) -> None:
            checks.append(
                {
                    "key": key,
                    "passed": bool(passed),
                    "blocking": bool(blocking),
                    "detail": detail,
                }
            )
            if passed or not blocking or reason is None:
                return
            if category == "review":
                review_reasons.append(reason)
            else:
                blocking_reasons.append(reason)

        add_check(
            "operation_test3_enabled",
            bool(runtime.get("operation_test3_enabled", False)),
            reason="operation_test3_disabled",
        )
        add_check(
            "operation_test3_scheduler_enabled",
            bool(runtime.get("operation_test3_scheduler_enabled", False)),
            reason="operation_test3_scheduler_disabled",
        )
        add_check(
            "operation_test3_position_management_enabled",
            bool(runtime.get("operation_test3_position_management_enabled", False)),
            reason="operation_test3_position_management_disabled",
        )
        add_check(
            "operation_test3_allow_real_orders",
            bool(runtime.get("operation_test3_allow_real_orders", False)),
            reason="operation_test3_real_orders_disabled",
        )
        add_check("dry_run_false", not bool(runtime.get("dry_run", True)), reason="dry_run_true")
        add_check("kill_switch_false", not bool(runtime.get("kill_switch", False)), reason="kill_switch_enabled")
        add_check("kis_enabled", bool(getattr(settings, "kis_enabled", False)), reason="kis_disabled")
        add_check(
            "kis_real_order_enabled",
            bool(getattr(settings, "kis_real_order_enabled", False)),
            reason="kis_real_order_disabled",
        )
        enabled_buy_flags = [key for key in BUY_FLAGS if bool(runtime.get(key, False))]
        add_check(
            "all_buy_flags_false",
            not enabled_buy_flags,
            reason="buy_flags_enabled",
            detail={"enabled_buy_flags": enabled_buy_flags},
        )
        add_check(
            "stop_loss_enabled",
            bool(runtime.get("operation_test3_stop_loss_enabled", True)),
            reason="operation_test3_stop_loss_disabled",
        )
        if bool(runtime.get("operation_test3_take_profit_enabled", False)):
            add_check("take_profit_enabled", True, blocking=False, detail="take_profit_exit_enabled")
        else:
            add_check("take_profit_disabled", True, blocking=False, detail="stop_loss_only")

        active_lifecycle_exactly_one = len(active) == 1
        add_check(
            "active_lifecycle_exactly_one",
            active_lifecycle_exactly_one,
            reason="active_lifecycle_count_not_one",
            category="review",
            detail={"active_lifecycle_count": len(active)},
        )
        lifecycle_status_open = lifecycle is not None and str(lifecycle.status or "").lower() == OPEN
        add_check(
            "lifecycle_status_open",
            lifecycle_status_open,
            reason="lifecycle_status_not_open" if lifecycle is not None else None,
            category="review",
            detail=getattr(lifecycle, "status", None),
        )
        add_check(
            "manual_review_not_required",
            lifecycle is not None and not bool(getattr(lifecycle, "manual_review_required", False)),
            reason="manual_review_required" if lifecycle is not None else None,
            category="review",
            detail={"exit_reason": getattr(lifecycle, "exit_reason", None)},
        )

        broker_positions_readable = broker_position_read.get("final_status") in {"ok", "empty"}
        add_check(
            "broker_positions_readable",
            broker_positions_readable,
            reason="broker_positions_unavailable",
            category="review",
            detail=broker_position_read.get("final_status"),
        )
        broker_position_exactly_one = len(held_positions) == 1
        add_check(
            "broker_position_exactly_one",
            broker_position_exactly_one,
            reason="broker_position_count_not_one" if broker_positions_readable else None,
            category="review",
            detail={"broker_position_count": len(held_positions)},
        )

        symbol_matches = (
            lifecycle is not None
            and broker_position is not None
            and _symbol(broker_position) == _normalize_symbol(lifecycle.symbol)
        )
        add_check(
            "lifecycle_broker_symbol_match",
            symbol_matches,
            reason=(
                "broker_position_symbol_mismatch"
                if lifecycle is not None and broker_position is not None
                else None
            ),
            category="review",
        )
        quantity_matches = (
            lifecycle is not None
            and broker_position is not None
            and _quantity_matches(broker_position, lifecycle)
        )
        add_check(
            "lifecycle_broker_quantity_match",
            quantity_matches,
            reason=(
                "broker_position_quantity_mismatch"
                if lifecycle is not None and broker_position is not None
                else None
            ),
            category="review",
        )
        add_check(
            "valid_cost_basis",
            lifecycle is not None and _valid_cost_basis(lifecycle),
            reason="invalid_cost_basis" if lifecycle is not None else None,
            category="review",
        )
        add_check(
            "no_broker_open_sell_order",
            open_orders_error is None and broker_pending is None,
            reason=(
                "broker_open_orders_unavailable"
                if open_orders_error
                else "broker_open_sell_order_exists"
                if broker_pending is not None
                else None
            ),
            category="review",
            detail={"open_orders_error": open_orders_error},
        )
        add_check(
            "no_local_pending_sell_order",
            local_pending is None,
            reason="local_pending_sell_order_exists" if local_pending is not None else None,
            category="review",
        )
        add_check(
            "daily_sell_limit_available",
            not bool(daily.get("daily_limit_reached")),
            reason="daily_sell_limit_reached",
            detail=daily,
        )
        add_check(
            "market_session_sell_allowed",
            sell_session_allowed,
            reason="sell_session_not_allowed",
            detail=_public_market_session(market_session),
        )

        blocking_reasons = _dedupe(blocking_reasons)
        review_reasons = _dedupe(review_reasons)
        live_ready = not blocking_reasons and not review_reasons
        status = "ready" if live_ready else "blocked" if blocking_reasons else "review_required"

        return {
                "provider": PROVIDER,
                "market": MARKET,
                "mode": LIVE_READINESS_MODE,
                "operation_test": OPERATION_TEST,
                "operation_test3_phase": PHASE,
                "read_only": True,
                "status": status,
                "live_ready": live_ready,
                "symbol": lifecycle.symbol if lifecycle is not None else _symbol(broker_position),
                "lifecycle_id": lifecycle.id if lifecycle is not None else None,
                "entry_order_id": lifecycle.entry_order_id if lifecycle is not None else None,
                "quantity": lifecycle.quantity if lifecycle is not None else None,
                "checks": checks,
                "blocking_reasons": blocking_reasons,
                "review_reasons": review_reasons,
                "broker_position_read": broker_position_read,
                "runtime": runtime_snapshot,
                "market_session": _public_market_session(market_session),
                "daily_limit": daily,
                "safety": {
                    "read_only": True,
                    "preflight_only": True,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                    "buy_service_called": False,
                },
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "buy_service_called": False,
        }
    def preflight_once(
        self,
        db: Session,
        slot_label: str | None = None,
        *,
        now: datetime | None = None,
        trigger_source: str = MANUAL_PREFLIGHT_TRIGGER_SOURCE,
    ) -> dict[str, Any]:
        return self._run_management_once(
            db,
            execute=False,
            slot_label=slot_label,
            now=now,
            trigger_source=trigger_source,
            include_raw=False,
        )

    def run_once(
        self,
        db: Session,
        slot_label: str | None = None,
        *,
        now: datetime | None = None,
        trigger_source: str = MANUAL_RUN_TRIGGER_SOURCE,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        return self._run_management_once(
            db,
            execute=True,
            slot_label=slot_label,
            now=now,
            trigger_source=trigger_source,
            include_raw=include_raw,
        )

    def enable_monitoring(
        self,
        db: Session,
        *,
        confirmation: str | None,
    ) -> dict[str, Any]:
        if str(confirmation or "").strip() != MONITORING_CONFIRMATION:
            return sanitize_kis_payload(
                {
                    "status": "blocked",
                    "operation_test": OPERATION_TEST,
                    "operation_test3_phase": PHASE,
                    "enablement_mode": "monitoring",
                    "reason": "operator_confirmation_required",
                    "required_confirmation": MONITORING_CONFIRMATION,
                    "immediate_order_execution": False,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                }
            )
        settings = self.runtime_settings.update_settings(
            db,
            {
                "operation_test3_enabled": True,
                "operation_test3_scheduler_enabled": True,
                "operation_test3_position_management_enabled": True,
                "operation_test3_allow_real_orders": False,
                "operation_test3_stop_loss_enabled": True,
                "operation_test3_take_profit_enabled": False,
                **{key: False for key in BUY_FLAGS},
            },
        )
        return sanitize_kis_payload(
            {
                "status": "monitoring_enabled",
                "operation_test": OPERATION_TEST,
                "operation_test3_phase": PHASE,
                "enablement_mode": "monitoring",
                "runtime": _runtime_snapshot(settings, self._settings()),
                "confirmation_accepted": True,
                "immediate_order_execution": False,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        )

    def enable(
        self,
        db: Session,
        *,
        confirm_live: bool,
        confirmation: str | None,
    ) -> dict[str, Any]:
        if confirm_live is not True or str(confirmation or "").strip() != ENABLE_CONFIRMATION:
            return sanitize_kis_payload(
                {
                    "status": "blocked",
                    "operation_test": OPERATION_TEST,
                    "operation_test3_phase": PHASE,
                    "enablement_mode": "live",
                    "reason": "operator_confirmation_required",
                    "required_confirmation": ENABLE_CONFIRMATION,
                    "immediate_order_execution": False,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                }
            )
        settings = self.runtime_settings.update_settings(
            db,
            {
                "operation_test3_enabled": True,
                "operation_test3_scheduler_enabled": True,
                "operation_test3_allow_real_orders": True,
                "operation_test3_position_management_enabled": True,
                "operation_test3_stop_loss_enabled": True,
                "operation_test3_take_profit_enabled": False,
                "operation_test3_max_sell_orders_per_day": 1,
                **{key: False for key in BUY_FLAGS},
            },
        )
        return sanitize_kis_payload(
            {
                "status": "live_enabled",
                "operation_test": OPERATION_TEST,
                "operation_test3_phase": PHASE,
                "enablement_mode": "live",
                "runtime": _runtime_snapshot(settings, self._settings()),
                "confirmation_accepted": True,
                "immediate_order_execution": False,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        )

    def disable(self, db: Session) -> dict[str, Any]:
        settings = self.runtime_settings.update_settings(
            db,
            {
                "operation_test3_enabled": False,
                "operation_test3_scheduler_enabled": False,
                "operation_test3_allow_real_orders": False,
                "operation_test3_position_management_enabled": False,
                "operation_test3_stop_loss_enabled": False,
                "operation_test3_take_profit_enabled": False,
            },
        )
        return sanitize_kis_payload(
            {
                "status": "disabled",
                "operation_test": OPERATION_TEST,
                "operation_test3_phase": PHASE,
                "runtime": _runtime_snapshot(settings, self._settings()),
                "lifecycle_deleted": False,
                "position_deleted": False,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        )

    def has_manageable_position(self, db: Session) -> bool:
        return bool(_active_lifecycles(db))

    def _run_management_once(
        self,
        db: Session,
        *,
        execute: bool,
        slot_label: str | None,
        now: datetime | None,
        trigger_source: str,
        include_raw: bool,
    ) -> dict[str, Any]:
        now_utc = _aware_utc(now or self.now_provider())
        if execute and slot_label and _scheduler_slot_already_ran(db, now_utc, slot_label):
            return sanitize_kis_payload(
                _base_payload(
                    mode=RUN_MODE,
                    trigger_source=trigger_source,
                    slot_label=slot_label,
                    execute=execute,
                    result="skipped",
                    action=HOLD,
                    reason="scheduler_slot_already_ran",
                    now_utc=now_utc,
                )
            )

        runtime = self.runtime_settings.get_settings(db)
        active = _active_lifecycles(db)
        if active:
            runtime = self._ensure_buy_flags_disabled(db)
            for lifecycle in active:
                self._sync_lifecycle_from_exit_order(db, lifecycle, now_utc=now_utc)
            active = _active_lifecycles(db)

        if not active:
            payload = _base_payload(
                mode=RUN_MODE if execute else PREFLIGHT_MODE,
                trigger_source=trigger_source,
                slot_label=slot_label,
                execute=execute,
                result="skipped",
                action=HOLD,
                reason="no_open_lifecycle",
                now_utc=now_utc,
                runtime=runtime,
                settings=self._settings(),
            )
            run = self._record_run(db, payload=payload, now_utc=now_utc)
            payload["run"] = _serialize_run(run)
            return sanitize_kis_payload(payload)

        if len(active) != 1:
            payload = _base_payload(
                mode=RUN_MODE if execute else PREFLIGHT_MODE,
                trigger_source=trigger_source,
                slot_label=slot_label,
                execute=execute,
                result="review",
                action=REVIEW,
                reason="active_lifecycle_count_not_one",
                now_utc=now_utc,
                runtime=runtime,
                settings=self._settings(),
                lifecycle_count=len(active),
                block_reasons=["active_lifecycle_count_not_one"],
                manual_review_required=True,
            )
            run = self._record_run(db, payload=payload, now_utc=now_utc)
            payload["run"] = _serialize_run(run)
            return sanitize_kis_payload(payload)

        lifecycle = active[0]
        if str(lifecycle.status or "").lower() == CLOSING:
            payload = self._payload_for_lifecycle(
                db,
                lifecycle,
                runtime=runtime,
                positions=[],
                open_orders=[],
                execute=execute,
                slot_label=slot_label,
                trigger_source=trigger_source,
                now_utc=now_utc,
                result="blocked",
                action=HOLD,
                reason="exit_order_already_pending",
                block_reasons=["exit_order_already_pending"],
            )
            run = self._record_run(db, payload=payload, now_utc=now_utc)
            payload["run"] = _serialize_run(run)
            return sanitize_kis_payload(payload)

        positions, broker_position_read = self._broker_positions_with_retry()
        try:
            open_orders = self._broker_open_orders()
            open_orders_error = None
        except Exception as exc:
            open_orders = []
            open_orders_error = _safe_error(exc)

        decision = self._evaluate_lifecycle(
            db,
            lifecycle,
            runtime=runtime,
            positions=positions,
            open_orders=open_orders,
            execute=execute,
            slot_label=slot_label,
            trigger_source=trigger_source,
            now_utc=now_utc,
            broker_position_read=broker_position_read,
            open_orders_error=open_orders_error,
        )
        if execute and decision.get("execution_ready") is True:
            decision = self._execute_sell(
                db,
                lifecycle,
                decision=decision,
                runtime=runtime,
                now_utc=now_utc,
                include_raw=include_raw,
            )
        run = self._record_run(db, payload=decision, now_utc=now_utc)
        decision["run"] = _serialize_run(run)
        return sanitize_kis_payload(decision)

    def _evaluate_lifecycle(
        self,
        db: Session,
        lifecycle: PositionLifecycle,
        *,
        runtime: dict[str, Any],
        positions: list[dict[str, Any]],
        open_orders: list[dict[str, Any]],
        execute: bool,
        slot_label: str | None,
        trigger_source: str,
        now_utc: datetime,
        broker_position_read: dict[str, Any],
        open_orders_error: str | None,
    ) -> dict[str, Any]:
        settings = self._settings()
        held_positions = [_normalize_position(item) for item in positions]
        held_positions = [item for item in held_positions if _safe_float(item.get("qty"), 0.0) > 0]
        position = held_positions[0] if len(held_positions) == 1 else None

        block_reasons: list[str] = []
        manual_review_required = False
        if broker_position_read.get("final_status") in {"unavailable", "invalid"}:
            block_reasons.append("broker_positions_unavailable")
            manual_review_required = True
        if open_orders_error:
            block_reasons.append("broker_open_orders_unavailable")
            manual_review_required = True
        if len(held_positions) != 1:
            block_reasons.append("broker_position_count_not_one")
            manual_review_required = True
        if position is not None and _symbol(position) != _normalize_symbol(lifecycle.symbol):
            block_reasons.append("broker_position_symbol_mismatch")
            manual_review_required = True
        if position is not None and not _quantity_matches(position, lifecycle):
            block_reasons.append("broker_position_quantity_mismatch")
            manual_review_required = True
        if not _valid_cost_basis(lifecycle):
            block_reasons.append("invalid_cost_basis")
            manual_review_required = True
        current_price = _position_current_price(position)
        if position is not None and (current_price is None or current_price <= 0):
            block_reasons.append("current_price_unavailable")
            manual_review_required = True

        local_pending = _local_pending_sell_order(db, lifecycle.symbol)
        broker_pending = _broker_open_sell_order(open_orders, lifecycle.symbol)
        if local_pending is not None:
            lifecycle.status = CLOSING
            lifecycle.exit_order_id = int(local_pending.id)
            lifecycle.exit_order_status = str(local_pending.internal_status or "").upper()
            lifecycle.exit_reason = lifecycle.exit_reason or "local_pending_sell_order_exists"
            lifecycle.last_evaluated_at = _naive_utc(now_utc)
            db.commit()
            db.refresh(lifecycle)
            block_reasons.append("local_pending_sell_order_exists")
        if broker_pending is not None:
            lifecycle.status = CLOSING
            lifecycle.exit_reason = lifecycle.exit_reason or "broker_open_sell_order_exists"
            lifecycle.last_evaluated_at = _naive_utc(now_utc)
            db.commit()
            db.refresh(lifecycle)
            block_reasons.append("broker_open_sell_order_exists")

        if position is not None and current_price is not None and current_price > 0:
            _update_lifecycle_price(lifecycle, current_price=current_price, now_utc=now_utc)
            db.commit()
            db.refresh(lifecycle)

        should_auto_clear_transient_broker_read_review = _should_auto_clear_transient_broker_read_review(
            lifecycle,
            broker_position_read=broker_position_read,
            core_block_reasons=block_reasons,
        )

        daily = _daily_sell_state(db, runtime=runtime, now_utc=now_utc)
        if daily["daily_limit_reached"]:
            block_reasons.append("daily_sell_limit_reached")

        market_session = self._market_session(now_utc)
        sell_session_allowed = _sell_session_allowed(market_session)
        if not sell_session_allowed:
            block_reasons.append("sell_session_not_allowed")

        stop_loss_threshold = _stop_loss_threshold_price(lifecycle)
        take_profit_threshold = _take_profit_threshold_price(lifecycle)
        stop_loss_triggered = bool(
            current_price is not None
            and stop_loss_threshold is not None
            and current_price <= stop_loss_threshold
        )
        take_profit_triggered = bool(
            current_price is not None
            and take_profit_threshold is not None
            and current_price >= take_profit_threshold
        )

        structural = {
            "broker_positions_unavailable",
            "broker_open_orders_unavailable",
            "broker_position_count_not_one",
            "broker_position_symbol_mismatch",
            "broker_position_quantity_mismatch",
            "invalid_cost_basis",
            "current_price_unavailable",
        }
        trigger: str | None = None
        action = HOLD
        result = "hold"
        reason = "no_exit_condition"
        if any(item in structural for item in block_reasons):
            action = REVIEW
            result = "review"
            reason = block_reasons[0]
        elif stop_loss_triggered:
            trigger = "stop_loss"
            action = SELL_READY
            result = "sell_ready" if not execute else "blocked"
            reason = "stop_loss_triggered"
        elif take_profit_triggered and not bool(runtime.get("operation_test3_take_profit_enabled", False)):
            action = HOLD
            result = "hold"
            reason = "take_profit_execution_disabled"
        elif take_profit_triggered:
            trigger = "take_profit"
            action = TAKE_PROFIT_READY
            result = "take_profit_ready" if not execute else "blocked"
            reason = "take_profit_triggered"

        gate_reasons: list[str] = []
        if trigger is not None:
            gate_reasons = _live_execution_gate_reasons(
                runtime,
                settings=settings,
                trigger=trigger,
                structural_block_reasons=block_reasons,
            )
            if execute and gate_reasons:
                result = "blocked"
                reason = gate_reasons[0]

        all_block_reasons = _dedupe(block_reasons + gate_reasons)
        if action == REVIEW:
            _mark_manual_review(lifecycle, reason=reason, now_utc=now_utc)
            db.commit()
            db.refresh(lifecycle)
        elif should_auto_clear_transient_broker_read_review:
            lifecycle.manual_review_required = False
            lifecycle.exit_reason = None
            lifecycle.last_evaluated_at = _naive_utc(now_utc)
            db.commit()
            db.refresh(lifecycle)
        manual_review_required = bool(getattr(lifecycle, "manual_review_required", False))
        payload = self._payload_for_lifecycle(
            db,
            lifecycle,
            runtime=runtime,
            positions=held_positions,
            open_orders=open_orders,
            execute=execute,
            slot_label=slot_label,
            trigger_source=trigger_source,
            now_utc=now_utc,
            result=result,
            action=action,
            reason=reason,
            block_reasons=all_block_reasons,
            trigger=trigger,
            current_price=current_price,
            stop_loss_threshold=stop_loss_threshold,
            take_profit_threshold=take_profit_threshold,
            stop_loss_triggered=stop_loss_triggered,
            take_profit_triggered=take_profit_triggered,
            daily_limit=daily,
            market_session=market_session,
            manual_review_required=manual_review_required,
            lifecycle_count=1,
            broker_position_read=broker_position_read,
        )
        payload["execution_ready"] = bool(execute and trigger is not None and not gate_reasons)
        return payload

    def _execute_sell(
        self,
        db: Session,
        lifecycle: PositionLifecycle,
        *,
        decision: dict[str, Any],
        runtime: dict[str, Any],
        now_utc: datetime,
        include_raw: bool,
    ) -> dict[str, Any]:
        service = self._limited_sell_service(lifecycle, runtime)
        try:
            sell_result = service.run_once(db, now=now_utc)
        except Exception as exc:
            latest_order = _latest_sell_order(db, lifecycle.symbol)
            if latest_order is not None:
                lifecycle.status = CLOSING
                lifecycle.exit_order_id = int(latest_order.id)
                lifecycle.exit_order_status = str(latest_order.internal_status or "").upper()
            lifecycle.exit_reason = "sell_submit_uncertain_manual_review_required"
            lifecycle.manual_review_required = True
            lifecycle.last_evaluated_at = _naive_utc(now_utc)
            db.commit()
            db.refresh(lifecycle)
            return {
                **decision,
                "action": HOLD,
                "result": "manual_review",
                "reason": f"sell_submit_uncertain:{exc.__class__.__name__}",
                "manual_review_required": True,
                "order_id": latest_order.id if latest_order else None,
                "exit_order_id": lifecycle.exit_order_id,
                "real_order_submitted": False,
                "broker_submit_called": latest_order is not None,
                "manual_submit_called": latest_order is not None,
                "sell_result": None,
                "execution_ready": False,
            }

        child = sell_result if include_raw else _without_raw(sell_result)
        order_id = _int_or_none(sell_result.get("order_id") or sell_result.get("order_log_id"))
        order = db.get(OrderLog, order_id) if order_id is not None else None
        status = _sell_order_status(order, sell_result)
        submitted = bool(sell_result.get("real_order_submitted") is True)
        broker_called = bool(sell_result.get("broker_submit_called") is True)
        manual_called = bool(sell_result.get("manual_submit_called") is True)
        trigger = str(decision.get("trigger") or "sell")
        exit_reason = f"{trigger}_triggered" if trigger in {"stop_loss", "take_profit"} else "sell_triggered"

        lifecycle.exit_order_id = order_id or lifecycle.exit_order_id
        lifecycle.exit_order_status = status or lifecycle.exit_order_status
        lifecycle.last_evaluated_at = _naive_utc(now_utc)
        if status == InternalOrderStatus.FILLED.value:
            if self._broker_position_zero(lifecycle):
                lifecycle.status = CLOSED
                lifecycle.exit_reason = exit_reason
                lifecycle.manual_review_required = False
                lifecycle.closed_at = _naive_utc(now_utc)
                result = "filled"
                reason = "sell_filled_lifecycle_closed"
            else:
                lifecycle.status = CLOSING
                lifecycle.exit_reason = "filled_waiting_broker_position_zero"
                lifecycle.manual_review_required = True
                result = "manual_review"
                reason = "filled_but_broker_position_not_zero"
        elif status in REVIEW_SELL_STATUSES:
            lifecycle.status = OPEN
            lifecycle.exit_reason = "sell_rejected_manual_review_required"
            lifecycle.manual_review_required = True
            result = "manual_review"
            reason = "sell_rejected_manual_review_required"
        elif status in CLOSING_SELL_STATUSES or submitted or (broker_called and order_id is not None):
            lifecycle.status = CLOSING
            lifecycle.exit_reason = exit_reason
            lifecycle.manual_review_required = False
            result = "submitted"
            reason = str(sell_result.get("reason") or f"{trigger}_auto_sell_submitted")
        elif broker_called or order_id is not None:
            lifecycle.status = CLOSING
            lifecycle.exit_reason = "sell_submit_uncertain_manual_review_required"
            lifecycle.manual_review_required = True
            result = "manual_review"
            reason = "sell_submit_uncertain_manual_review_required"
        else:
            result = str(sell_result.get("result") or "blocked")
            reason = str(sell_result.get("reason") or "sell_blocked")
        db.commit()
        db.refresh(lifecycle)

        return sanitize_kis_payload(
            {
                **decision,
                "status": lifecycle.status,
                "lifecycle": _serialize_lifecycle(lifecycle),
                "result": result,
                "reason": reason,
                "exit_reason": lifecycle.exit_reason,
                "order_id": order_id,
                "exit_order_id": lifecycle.exit_order_id,
                "exit_order_status": lifecycle.exit_order_status,
                "manual_review_required": bool(lifecycle.manual_review_required),
                "real_order_submitted": submitted,
                "broker_submit_called": broker_called,
                "manual_submit_called": manual_called,
                "sell_result": child,
                "execution_path": "KisLimitedAutoSellService",
                "execution_ready": False,
            }
        )

    def _payload_for_lifecycle(
        self,
        db: Session,
        lifecycle: PositionLifecycle,
        *,
        runtime: dict[str, Any],
        positions: list[dict[str, Any]],
        open_orders: list[dict[str, Any]],
        execute: bool,
        slot_label: str | None,
        trigger_source: str,
        now_utc: datetime,
        result: str,
        action: str,
        reason: str,
        block_reasons: list[str],
        trigger: str | None = None,
        current_price: float | None = None,
        stop_loss_threshold: float | None = None,
        take_profit_threshold: float | None = None,
        stop_loss_triggered: bool = False,
        take_profit_triggered: bool = False,
        daily_limit: dict[str, Any] | None = None,
        market_session: dict[str, Any] | None = None,
        manual_review_required: bool = False,
        lifecycle_count: int = 1,
        broker_position_read: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return sanitize_kis_payload(
            {
                **_base_payload(
                    mode=RUN_MODE if execute else PREFLIGHT_MODE,
                    trigger_source=trigger_source,
                    slot_label=slot_label,
                    execute=execute,
                    result=result,
                    action=action,
                    reason=reason,
                    now_utc=now_utc,
                    runtime=runtime,
                    settings=self._settings(),
                    lifecycle_count=lifecycle_count,
                    block_reasons=block_reasons,
                    manual_review_required=manual_review_required,
                    broker_position_read=broker_position_read,
                ),
                "lifecycle_id": lifecycle.id,
                "entry_order_id": lifecycle.entry_order_id,
                "symbol": lifecycle.symbol,
                "quantity": lifecycle.quantity,
                "entry_price": lifecycle.entry_price,
                "cost_basis": lifecycle.cost_basis,
                "current_price": current_price if current_price is not None else lifecycle.last_price,
                "unrealized_pl": lifecycle.unrealized_pl,
                "unrealized_pl_pct": lifecycle.unrealized_pl_pct,
                "stop_loss_threshold_pct": lifecycle.stop_loss_threshold_pct,
                "stop_loss_threshold": stop_loss_threshold,
                "take_profit_threshold_pct": lifecycle.take_profit_threshold_pct,
                "take_profit_threshold": take_profit_threshold,
                "take_profit_execution_enabled": bool(runtime.get("operation_test3_take_profit_enabled", False)),
                "trigger": trigger,
                "stop_loss_triggered": stop_loss_triggered,
                "take_profit_triggered": take_profit_triggered,
                "take_profit_triggered_ignored": bool(stop_loss_triggered and take_profit_triggered),
                "lifecycle": _serialize_lifecycle(lifecycle),
                "positions": positions,
                "open_orders": open_orders,
                "daily_limit": daily_limit or _daily_sell_state(db, runtime=runtime, now_utc=now_utc),
                "market_session": _public_market_session(market_session or {}),
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        )

    def _ensure_buy_flags_disabled(self, db: Session) -> dict[str, Any]:
        runtime = self.runtime_settings.get_settings(db)
        if all(runtime.get(key) is False for key in BUY_FLAGS):
            return runtime
        return self.runtime_settings.update_settings(db, {key: False for key in BUY_FLAGS})

    def _limited_sell_service(self, lifecycle: PositionLifecycle, runtime: dict[str, Any]) -> Any:
        if self.limited_auto_sell_service is not None:
            return self.limited_auto_sell_service
        if self.client is None:
            raise RuntimeError("KIS client is required for Operation Test 3 sell execution.")
        adapter = _OperationTest3SellRuntimeAdapter(
            self.runtime_settings,
            operation_runtime=runtime,
            lifecycle=lifecycle,
        )
        self.limited_auto_sell_service = KisLimitedAutoSellService(
            self.client,
            runtime_settings=adapter,
            session_service=self.session_service,
            allow_scheduler_guarded_sell=True,
        )
        return self.limited_auto_sell_service

    def _broker_positions(self) -> list[dict[str, Any]]:
        positions, _ = self._broker_positions_with_retry()
        return positions

    def _broker_positions_with_retry(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        positions: list[dict[str, Any]] = []
        errors: list[str] = []
        first_attempt_failed = False
        retry_attempted = False
        final_status = "unavailable"
        attempt_count = 0

        for attempt in range(1, BROKER_POSITION_READ_MAX_ATTEMPTS + 1):
            attempt_count = attempt
            try:
                positions, final_status, error = self._broker_positions_once()
            except Exception as exc:
                positions = []
                final_status = "unavailable"
                error = _safe_error(exc)

            if error:
                errors.append(error)

            if final_status in {"ok", "empty"}:
                return positions, _broker_position_read_snapshot(
                    {
                        "attempt_count": attempt_count,
                        "retry_attempted": retry_attempted,
                        "retry_succeeded": bool(first_attempt_failed and retry_attempted),
                        "first_attempt_failed": first_attempt_failed,
                        "final_status": final_status,
                        "errors": errors,
                    }
                )

            first_attempt_failed = first_attempt_failed or attempt == 1
            if attempt < BROKER_POSITION_READ_MAX_ATTEMPTS:
                retry_attempted = True
                delay = max(0.0, float(self.broker_position_read_retry_delay_seconds or 0.0))
                if delay:
                    self.sleeper(delay)

        return positions, _broker_position_read_snapshot(
            {
                "attempt_count": attempt_count,
                "retry_attempted": retry_attempted,
                "retry_succeeded": False,
                "first_attempt_failed": first_attempt_failed,
                "final_status": final_status,
                "errors": errors,
            }
        )

    def _broker_positions_once(self) -> tuple[list[dict[str, Any]], str, str | None]:
        if self.client is None:
            return [], "empty", None
        raw = self.client.list_positions()
        if raw is None:
            return [], "invalid", "list_positions_returned_none"
        if not isinstance(raw, list):
            return [], "invalid", "list_positions_returned_non_list"
        positions: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                return [], "invalid", "list_positions_returned_invalid_item"
            positions.append(item)
        if not positions:
            return [], "empty", None
        return positions, "ok", None
    def _broker_open_orders(self) -> list[dict[str, Any]]:
        if self.client is None:
            return []
        raw = self.client.list_open_orders()
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    def _broker_position_zero(self, lifecycle: PositionLifecycle) -> bool:
        try:
            positions, broker_position_read = self._broker_positions_with_retry()
            if broker_position_read.get("final_status") in {"unavailable", "invalid"}:
                return False
            positions = [_normalize_position(item) for item in positions]
        except Exception:
            return False
        symbol = _normalize_symbol(lifecycle.symbol)
        for position in positions:
            if _symbol(position) == symbol and _safe_float(position.get("qty"), 0.0) > 0:
                return False
        return True

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

    def _settings(self) -> Any:
        if self.client is not None and getattr(self.client, "settings", None) is not None:
            return self.client.settings
        return self.runtime_settings.settings

    def _sync_lifecycle_from_exit_order(
        self,
        db: Session,
        lifecycle: PositionLifecycle,
        *,
        now_utc: datetime,
    ) -> None:
        if lifecycle.exit_order_id is None:
            return
        order = db.get(OrderLog, int(lifecycle.exit_order_id))
        if order is None:
            return
        status = str(order.internal_status or "").upper()
        lifecycle.exit_order_status = status or lifecycle.exit_order_status
        lifecycle.last_evaluated_at = _naive_utc(now_utc)
        if status in CLOSING_SELL_STATUSES:
            lifecycle.status = CLOSING
        elif status == InternalOrderStatus.FILLED.value:
            if self._broker_position_zero(lifecycle):
                lifecycle.status = CLOSED
                lifecycle.closed_at = lifecycle.closed_at or _naive_utc(now_utc)
                lifecycle.manual_review_required = False
                lifecycle.exit_reason = lifecycle.exit_reason or "sell_filled_lifecycle_closed"
            else:
                lifecycle.status = CLOSING
                lifecycle.manual_review_required = True
                lifecycle.exit_reason = "filled_but_broker_position_not_zero"
        elif status in REVIEW_SELL_STATUSES:
            lifecycle.status = OPEN
            lifecycle.manual_review_required = True
            lifecycle.exit_reason = "sell_rejected_manual_review_required"
        db.commit()
        db.refresh(lifecycle)

    def _record_run(self, db: Session, *, payload: dict[str, Any], now_utc: datetime) -> TradeRunLog:
        slot_label = payload.get("scheduler_slot")
        run_key = (
            _scheduler_slot_run_key(now_utc, str(slot_label))
            if slot_label
            else f"op_test3_pm_{uuid.uuid4().hex[:12]}"
        )
        metadata = _operation_metadata(payload)
        run = TradeRunLog(
            run_key=run_key,
            trigger_source=str(payload.get("trigger_source") or MANUAL_RUN_TRIGGER_SOURCE)[:40],
            symbol=str(payload.get("symbol") or "POSITIONS"),
            mode=TRADE_RUN_RUN_MODE if payload.get("execute") else TRADE_RUN_PREFLIGHT_MODE,
            stage="done",
            result=str(payload.get("result") or "hold"),
            reason=str(payload.get("reason") or ""),
            order_id=_int_or_none(payload.get("order_id")),
            request_payload=_json({"provider": PROVIDER, "market": MARKET, **metadata}),
            response_payload=_json(
                {
                    **payload,
                    "metadata": metadata,
                    "operation_log": {
                        "action": payload.get("action"),
                        "reason": payload.get("reason"),
                        "result": payload.get("result"),
                        "order_id": payload.get("order_id"),
                        "lifecycle_id": payload.get("lifecycle_id"),
                        "symbol": payload.get("symbol"),
                    },
                }
            ),
            created_at=_naive_utc(now_utc),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

class _OperationTest3SellRuntimeAdapter:
    def __init__(
        self,
        base: RuntimeSettingService,
        *,
        operation_runtime: dict[str, Any],
        lifecycle: PositionLifecycle,
    ) -> None:
        self.base = base
        self.settings = base.settings
        self.operation_runtime = operation_runtime
        self.lifecycle = lifecycle

    def get_settings(self, db: Session) -> dict[str, Any]:
        return self._adapt(self.base.get_settings(db))

    def get_settings_read_only(self, db: Session) -> dict[str, Any]:
        return self._adapt(self.base.get_settings_read_only(db))

    def get_kis_risk_summary_read_only(self, db: Session) -> dict[str, Any]:
        return self.base.get_kis_risk_summary_read_only(db)

    def _adapt(self, runtime: dict[str, Any]) -> dict[str, Any]:
        adapted = dict(runtime)
        operation_runtime = {**runtime, **self.operation_runtime}
        operation_gate = bool(
            operation_runtime.get("operation_test3_enabled", False)
            and operation_runtime.get("operation_test3_position_management_enabled", False)
            and operation_runtime.get("operation_test3_allow_real_orders", False)
        )
        take_profit_decimal = _pct_decimal(self.lifecycle.take_profit_threshold_pct, 2.0)
        adapted.update(
            {
                "kis_live_auto_buy_enabled": False,
                "kis_limited_auto_buy_enabled": False,
                "kis_scheduler_buy_enabled": False,
                "kis_scheduler_allow_limited_auto_buy": False,
                "strategy_auto_buy_scheduler_enabled": False,
                "strategy_live_auto_buy_scheduler_enabled": False,
                "auto_buy_live_phase1_enabled": False,
                "auto_buy_live_phase1_allow_real_orders": False,
                "kis_live_auto_sell_enabled": operation_gate,
                "kis_limited_auto_sell_enabled": operation_gate,
                "kis_limited_auto_stop_loss_enabled": bool(
                    operation_runtime.get("operation_test3_stop_loss_enabled", True)
                ),
                "kis_limited_auto_sell_stop_loss_enabled": bool(
                    operation_runtime.get("operation_test3_stop_loss_enabled", True)
                ),
                "kis_limited_auto_take_profit_enabled": bool(
                    operation_runtime.get("operation_test3_take_profit_enabled", False)
                ),
                "kis_limited_auto_sell_take_profit_enabled": bool(
                    operation_runtime.get("operation_test3_take_profit_enabled", False)
                ),
                "kis_limited_auto_sell_allow_take_profit_trigger": bool(
                    operation_runtime.get("operation_test3_take_profit_enabled", False)
                ),
                "kis_limited_auto_sell_max_orders_per_day": int(
                    operation_runtime.get("operation_test3_max_sell_orders_per_day", 1) or 1
                ),
                "kis_scheduler_allow_real_orders": False,
                "kis_scheduler_allow_limited_auto_sell": False,
                "kis_limited_auto_take_profit_min_profit_pct": take_profit_decimal,
                "kis_limited_auto_sell_take_profit_min_profit_pct": take_profit_decimal,
            }
        )
        return adapted

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base, name)


def operation_test3_scheduler_gate(runtime: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(runtime.get("operation_test3_scheduler_enabled", False))
    return {
        "operation_test3_scheduler_enabled": enabled,
        "scheduler_execution_allowed": enabled,
        "blocking_reasons": [] if enabled else ["operation_test3_scheduler_enabled_false"],
        "independent_of_common_scheduler": True,
        "ignored_common_scheduler_flags": {
            "scheduler_enabled": bool(runtime.get("scheduler_enabled", False)),
            "kis_scheduler_enabled": bool(runtime.get("kis_scheduler_enabled", False)),
            "kis_position_lifecycle_scheduler_enabled": bool(
                runtime.get("kis_position_lifecycle_scheduler_enabled", False)
            ),
        },
    }


def _base_payload(
    *,
    mode: str,
    trigger_source: str,
    slot_label: str | None,
    execute: bool,
    result: str,
    action: str,
    reason: str,
    now_utc: datetime,
    runtime: dict[str, Any] | None = None,
    settings: Any | None = None,
    lifecycle_count: int = 0,
    block_reasons: list[str] | None = None,
    manual_review_required: bool = False,
    broker_position_read: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "provider": PROVIDER,
        "market": MARKET,
        "mode": mode,
        "operation_test": OPERATION_TEST,
        "operation_test3_auto": trigger_source == SCHEDULER_TRIGGER_SOURCE,
        "operation_test3_phase": PHASE,
        "trigger_source": trigger_source,
        "scheduler_slot": slot_label,
        "position_first": True,
        "sell_only": True,
        "buy_execution_allowed": False,
        "buy_service_called": False,
        "execute": execute,
        "preflight_only": not execute,
        "result": result,
        "action": action,
        "reason": reason,
        "block_reasons": _dedupe(block_reasons or []),
        "manual_review_required": manual_review_required,
        "active_lifecycle_count": lifecycle_count,
        "broker_position_read": _broker_position_read_snapshot(broker_position_read),
        "runtime": _runtime_snapshot(runtime or {}, settings),
        "evaluated_at": now_utc.isoformat(),
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
    }


def _runtime_snapshot(runtime: dict[str, Any], settings: Any | None) -> dict[str, Any]:
    return {
        "dry_run": bool(runtime.get("dry_run", True)),
        "kill_switch": bool(runtime.get("kill_switch", False)),
        "kis_enabled": bool(getattr(settings, "kis_enabled", False)) if settings is not None else False,
        "kis_real_order_enabled": bool(getattr(settings, "kis_real_order_enabled", False)) if settings is not None else False,
        "operation_test3_enabled": bool(runtime.get("operation_test3_enabled", False)),
        "operation_test3_scheduler_enabled": bool(runtime.get("operation_test3_scheduler_enabled", False)),
        "operation_test3_allow_real_orders": bool(runtime.get("operation_test3_allow_real_orders", False)),
        "operation_test3_position_management_enabled": bool(runtime.get("operation_test3_position_management_enabled", False)),
        "operation_test3_stop_loss_enabled": bool(runtime.get("operation_test3_stop_loss_enabled", True)),
        "operation_test3_take_profit_enabled": bool(runtime.get("operation_test3_take_profit_enabled", False)),
        "operation_test3_max_sell_orders_per_day": int(runtime.get("operation_test3_max_sell_orders_per_day", 1) or 1),
        "buy_flags": {key: bool(runtime.get(key, False)) for key in BUY_FLAGS},
        "buy_flags_all_false": all(not bool(runtime.get(key, False)) for key in BUY_FLAGS),
        "common_scheduler_flags": {
            "scheduler_enabled": bool(runtime.get("scheduler_enabled", False)),
            "kis_scheduler_enabled": bool(runtime.get("kis_scheduler_enabled", False)),
            "kis_position_lifecycle_scheduler_enabled": bool(runtime.get("kis_position_lifecycle_scheduler_enabled", False)),
        },
    }


def _live_execution_gate_reasons(
    runtime: dict[str, Any],
    *,
    settings: Any,
    trigger: str,
    structural_block_reasons: list[str],
) -> list[str]:
    reasons: list[str] = []
    if not bool(runtime.get("operation_test3_enabled", False)):
        reasons.append("operation_test3_disabled")
    if not bool(runtime.get("operation_test3_position_management_enabled", False)):
        reasons.append("operation_test3_position_management_disabled")
    if not bool(runtime.get("operation_test3_allow_real_orders", False)):
        reasons.append("operation_test3_real_orders_disabled")
    if trigger == "stop_loss" and not bool(runtime.get("operation_test3_stop_loss_enabled", True)):
        reasons.append("operation_test3_stop_loss_disabled")
    if trigger == "take_profit" and not bool(runtime.get("operation_test3_take_profit_enabled", False)):
        reasons.append("operation_test3_take_profit_disabled")
    if bool(runtime.get("dry_run", True)):
        reasons.append("dry_run_true")
    if bool(runtime.get("kill_switch", False)):
        reasons.append("kill_switch_enabled")
    if not bool(getattr(settings, "kis_enabled", False)):
        reasons.append("kis_disabled")
    if not bool(getattr(settings, "kis_real_order_enabled", False)):
        reasons.append("kis_real_order_disabled")
    reasons.extend(structural_block_reasons)
    return _dedupe(reasons)

def _daily_sell_state(db: Session, *, runtime: dict[str, Any], now_utc: datetime) -> dict[str, Any]:
    max_orders = max(0, int(runtime.get("operation_test3_max_sell_orders_per_day", 1) or 0))
    start_utc, end_utc = _kr_day_bounds_utc(now_utc)
    count = (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.side == SELL)
        .filter(OrderLog.created_at >= start_utc)
        .filter(OrderLog.created_at < end_utc)
        .filter(OrderLog.internal_status.in_(sorted(SUBMITTED_SELL_STATUSES)))
        .count()
    )
    return {
        "max_orders_per_day": max_orders,
        "submitted_count_today": int(count or 0),
        "daily_limit_remaining": max(0, max_orders - int(count or 0)),
        "daily_limit_reached": max_orders <= 0 or int(count or 0) >= max_orders,
    }


def _active_lifecycles(db: Session) -> list[PositionLifecycle]:
    return (
        db.query(PositionLifecycle)
        .filter(PositionLifecycle.status.in_([OPEN, CLOSING]))
        .order_by(PositionLifecycle.opened_at.asc(), PositionLifecycle.id.asc())
        .all()
    )


def _local_pending_sell_order(db: Session, symbol: str | None) -> OrderLog | None:
    normalized = _normalize_symbol(symbol)
    if not normalized:
        return None
    return (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.symbol == normalized)
        .filter(OrderLog.side == SELL)
        .filter(OrderLog.internal_status.in_(sorted(OPEN_ORDER_STATUSES)))
        .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
        .first()
    )


def _latest_sell_order(db: Session, symbol: str | None) -> OrderLog | None:
    normalized = _normalize_symbol(symbol)
    if not normalized:
        return None
    return (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.symbol == normalized)
        .filter(OrderLog.side == SELL)
        .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
        .first()
    )


def _broker_open_sell_order(open_orders: list[dict[str, Any]], symbol: str | None) -> dict[str, Any] | None:
    normalized = _normalize_symbol(symbol)
    for order in open_orders:
        if _order_symbol(order) == normalized and _order_is_sell(order):
            return order
    return None


def _scheduler_slot_already_ran(db: Session, now_utc: datetime, slot_label: str) -> bool:
    return (
        db.query(TradeRunLog)
        .filter(TradeRunLog.run_key == _scheduler_slot_run_key(now_utc, slot_label))
        .first()
        is not None
    )


def _scheduler_slot_run_key(now_utc: datetime, slot_label: str) -> str:
    day = now_utc.astimezone(KR_TZ).strftime("%Y%m%d")
    slot = re.sub(r"[^A-Za-z0-9]+", "_", str(slot_label or "slot")).strip("_")
    return f"op_test3_pm_{day}_{slot}"[:64]


def _latest_test3_run(db: Session) -> TradeRunLog | None:
    return (
        db.query(TradeRunLog)
        .filter(TradeRunLog.mode.in_([TRADE_RUN_PREFLIGHT_MODE, TRADE_RUN_RUN_MODE]))
        .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
        .first()
    )


def _operation_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    broker_position_read = _broker_position_read_snapshot(payload.get("broker_position_read"))
    return {
        "operation_test": OPERATION_TEST,
        "operation_test3_auto": bool(payload.get("operation_test3_auto")),
        "operation_test3_phase": PHASE,
        "scheduler_slot": payload.get("scheduler_slot"),
        "position_first": True,
        "sell_only": True,
        "buy_execution_allowed": False,
        "lifecycle_id": payload.get("lifecycle_id"),
        "entry_order_id": payload.get("entry_order_id"),
        "symbol": payload.get("symbol"),
        "broker_position_read_attempt_count": broker_position_read["attempt_count"],
        "broker_position_read_retry_attempted": broker_position_read["retry_attempted"],
        "broker_position_read_retry_succeeded": broker_position_read["retry_succeeded"],
        "broker_position_read_final_status": broker_position_read["final_status"],
    }


def _broker_position_read_snapshot(value: Any | None) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    attempt_count = _int_or_none(raw.get("attempt_count")) or 0
    final_status = str(raw.get("final_status") or "empty").strip().lower()
    if final_status not in {"ok", "unavailable", "empty", "invalid"}:
        final_status = "unavailable"
    errors = raw.get("errors") if isinstance(raw.get("errors"), list) else []
    sanitized_errors = []
    for error in errors:
        text = str(error or "").strip()
        if not text:
            continue
        if len(text) > 180:
            text = f"{text[:180]}..."
        sanitized_errors.append(text)
    return {
        "attempt_count": int(attempt_count),
        "retry_attempted": bool(raw.get("retry_attempted", False)),
        "retry_succeeded": bool(raw.get("retry_succeeded", False)),
        "first_attempt_failed": bool(raw.get("first_attempt_failed", False)),
        "final_status": final_status,
        "errors": sanitized_errors,
    }


def _should_auto_clear_transient_broker_read_review(
    lifecycle: PositionLifecycle,
    *,
    broker_position_read: dict[str, Any],
    core_block_reasons: list[str],
) -> bool:
    if not bool(getattr(lifecycle, "manual_review_required", False)):
        return False
    if str(getattr(lifecycle, "exit_reason", None) or "") != "broker_positions_unavailable":
        return False
    if str(lifecycle.status or "").lower() != OPEN:
        return False
    if broker_position_read.get("final_status") != "ok":
        return False
    return not bool(core_block_reasons)


def _update_lifecycle_price(lifecycle: PositionLifecycle, *, current_price: float, now_utc: datetime) -> None:
    quantity = _safe_float(lifecycle.quantity, 0.0)
    cost_basis = _safe_float(lifecycle.cost_basis, 0.0)
    current_value = current_price * quantity if quantity > 0 else None
    unrealized = current_value - cost_basis if current_value is not None and cost_basis > 0 else None
    lifecycle.last_price = float(current_price)
    lifecycle.unrealized_pl = _round_money(unrealized)
    lifecycle.unrealized_pl_pct = _round_ratio(unrealized / cost_basis) if unrealized is not None and cost_basis > 0 else None
    lifecycle.max_price_since_entry = max(
        _safe_float(lifecycle.max_price_since_entry, _safe_float(lifecycle.entry_price, current_price)),
        float(current_price),
    )
    lifecycle.last_evaluated_at = _naive_utc(now_utc)


def _mark_manual_review(lifecycle: PositionLifecycle, *, reason: str, now_utc: datetime) -> None:
    lifecycle.manual_review_required = True
    lifecycle.exit_reason = reason
    lifecycle.last_evaluated_at = _naive_utc(now_utc)


def _stop_loss_threshold_price(lifecycle: PositionLifecycle) -> float | None:
    if lifecycle.entry_price is None or lifecycle.entry_price <= 0:
        return None
    pct = _safe_float(lifecycle.stop_loss_threshold_pct, 2.0)
    if pct <= 0:
        pct = 2.0
    return round(float(lifecycle.entry_price) * (1.0 - abs(pct) / 100.0), 4)


def _take_profit_threshold_price(lifecycle: PositionLifecycle) -> float | None:
    if lifecycle.entry_price is None or lifecycle.entry_price <= 0:
        return None
    pct = _safe_float(lifecycle.take_profit_threshold_pct, 2.0)
    if pct <= 0:
        pct = 2.0
    return round(float(lifecycle.entry_price) * (1.0 + abs(pct) / 100.0), 4)


def _valid_cost_basis(lifecycle: PositionLifecycle) -> bool:
    return (
        lifecycle.entry_price is not None
        and lifecycle.entry_price > 0
        and lifecycle.cost_basis is not None
        and lifecycle.cost_basis > 0
        and lifecycle.quantity is not None
        and lifecycle.quantity > 0
    )


def _quantity_matches(position: dict[str, Any], lifecycle: PositionLifecycle) -> bool:
    return abs(_safe_float(position.get("qty"), 0.0) - _safe_float(lifecycle.quantity, 0.0)) < 0.000001


def _normalize_position(item: dict[str, Any]) -> dict[str, Any]:
    raw_symbol = item.get("symbol") or item.get("pdno") or item.get("code")
    symbol = _normalize_symbol(raw_symbol) or ""
    return {
        **item,
        "symbol": symbol,
        "qty": _safe_float(item.get("qty") or item.get("hldg_qty"), 0.0),
        "current_price": _safe_float_or_none(item.get("current_price") or item.get("prpr") or item.get("stck_prpr")),
        "avg_entry_price": _safe_float_or_none(item.get("avg_entry_price") or item.get("pchs_avg_pric")),
        "cost_basis": _safe_float_or_none(item.get("cost_basis") or item.get("pchs_amt") or item.get("pchs_amt_smtl_amt")),
    }


def _position_current_price(position: dict[str, Any] | None) -> float | None:
    if not isinstance(position, dict):
        return None
    return _safe_float_or_none(position.get("current_price") or position.get("prpr") or position.get("stck_prpr"))


def _symbol(position: dict[str, Any] | None) -> str | None:
    if not isinstance(position, dict):
        return None
    return _normalize_symbol(position.get("symbol") or position.get("pdno") or position.get("code"))


def _normalize_symbol(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text or text == "NULL":
        return None
    if text.isdigit() and len(text) < 6:
        text = text.zfill(6)
    return text

def _order_symbol(order: dict[str, Any]) -> str | None:
    return _normalize_symbol(order.get("symbol") or order.get("pdno") or order.get("code"))


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


def _sell_order_status(order: OrderLog | None, payload: dict[str, Any]) -> str | None:
    if order is not None and order.internal_status:
        return str(order.internal_status).upper()
    valid = {item.value for item in InternalOrderStatus}
    for key in ("internal_status", "real_order_status", "broker_order_status", "broker_status"):
        value = payload.get(key)
        if not value:
            continue
        text = str(value).strip().upper()
        if text == "SUBMITTED":
            return InternalOrderStatus.SUBMITTED.value
        if text in valid:
            return text
    return None


def _sell_session_allowed(market_session: dict[str, Any]) -> bool:
    is_holiday = bool(market_session.get("is_holiday"))
    closure_reason = str(market_session.get("closure_reason") or "")
    if closure_reason.startswith("holiday_"):
        is_holiday = True
    return market_session.get("is_market_open") is True and not is_holiday


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


def _serialize_lifecycle(row: PositionLifecycle) -> dict[str, Any]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "entry_order_id": row.entry_order_id,
        "entry_price": row.entry_price,
        "cost_basis": row.cost_basis,
        "quantity": row.quantity,
        "status": row.status,
        "opened_at": _iso(row.opened_at),
        "last_price": row.last_price,
        "unrealized_pl": row.unrealized_pl,
        "unrealized_pl_pct": row.unrealized_pl_pct,
        "max_price_since_entry": row.max_price_since_entry,
        "stop_loss_threshold_pct": row.stop_loss_threshold_pct,
        "take_profit_threshold_pct": row.take_profit_threshold_pct,
        "exit_reason": row.exit_reason,
        "exit_order_id": row.exit_order_id,
        "exit_order_status": getattr(row, "exit_order_status", None),
        "manual_review_required": bool(getattr(row, "manual_review_required", False)),
        "closed_at": _iso(getattr(row, "closed_at", None)),
        "last_evaluated_at": _iso(row.last_evaluated_at),
    }


def _serialize_run(row: TradeRunLog) -> dict[str, Any]:
    return {
        "run_id": row.id,
        "run_key": row.run_key,
        "trigger_source": row.trigger_source,
        "symbol": row.symbol,
        "mode": row.mode,
        "result": row.result,
        "reason": row.reason,
        "order_id": row.order_id,
        "created_at": _iso(row.created_at),
    }


def _without_raw(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_raw(item)
            for key, item in value.items()
            if key not in {"raw", "raw_payload", "request_payload", "response_payload"}
        }
    if isinstance(value, list):
        return [_without_raw(item) for item in value]
    return value


def _pct_decimal(value: Any, default_pct: float) -> float:
    parsed = _safe_float_or_none(value)
    if parsed is None or parsed <= 0:
        parsed = default_pct
    if parsed > 1.0:
        parsed = parsed / 100.0
    return float(parsed)


def _kr_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    local = _aware_utc(now_utc).astimezone(KR_TZ)
    start_local = datetime.combine(local.date(), time.min, tzinfo=KR_TZ)
    end_local = start_local + timedelta(days=1)
    return _naive_utc(start_local), _naive_utc(end_local)


def _aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    return _aware_utc(value).replace(tzinfo=None)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _aware_utc(value).isoformat()
    return str(value)


def _json(value: Any) -> str:
    return json.dumps(sanitize_kis_payload(value), ensure_ascii=False, default=str)


def _safe_float(value: Any, default: float) -> float:
    parsed = _safe_float_or_none(value)
    return default if parsed is None else parsed


def _safe_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _round_money(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _round_ratio(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 8)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 180:
        text = f"{text[:180]}..."
    return f"{exc.__class__.__name__}: {text}"
