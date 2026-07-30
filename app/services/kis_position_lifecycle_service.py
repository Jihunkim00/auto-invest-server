from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, PositionLifecycle, TradeRunLog
from app.services.kis_dry_run_risk_service import (
    DEFAULT_EXIT_STOP_LOSS_THRESHOLD_DECIMAL,
    DEFAULT_EXIT_TAKE_PROFIT_THRESHOLD_DECIMAL,
    MARKET,
    OPEN_ORDER_STATUSES,
    PROVIDER,
    SELL,
)
from app.services.kis_limited_auto_sell_service import KisLimitedAutoSellService
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "kis_position_management"
PREFLIGHT_MODE = "kis_position_management_preflight"
RUN_MODE = "kis_position_management_run"
TRIGGER_SOURCE = "kis_position_management"
SCHEDULER_TRIGGER_SOURCE = "position_management_scheduler"
POSITION_LIFECYCLE_SCHEDULER_GATE_FLAGS = (
    ("scheduler_enabled", "scheduler_enabled_false"),
    ("kis_scheduler_enabled", "kis_scheduler_enabled_false"),
    (
        "kis_position_lifecycle_scheduler_enabled",
        "kis_position_lifecycle_scheduler_enabled_false",
    ),
)
BUY = "buy"
HOLD = "HOLD"
SELL_READY = "SELL_READY"
REVIEW_SELL = "REVIEW_SELL"
MANUAL_REVIEW = "manual_review"
OPEN = "open"
CLOSING = "closing"
CLOSED = "closed"
REVIEWED_BUY_SOURCE_TYPE = "operator_reviewed_limited_auto_buy"
REVIEWED_BUY_ENDPOINT = "/kis/limited-auto-buy/execute-reviewed-once"
REVIEWED_BUY_MODE = "kis_limited_auto_buy_execute_reviewed"
KR_TZ = ZoneInfo("Asia/Seoul")

SUBMITTED_SELL_STATUSES = {
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}


class KisPositionLifecycleService:
    """Post-buy lifecycle manager for the Stage 3 one-share KIS test.

    This service owns lifecycle state and management logs. It does not create a
    new broker submission path; stop-loss execution is delegated to the existing
    guarded limited auto-sell service.
    """

    def __init__(
        self,
        client: Any | None = None,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        limited_auto_sell_service: Any | None = None,
        now_provider: Any | None = None,
    ) -> None:
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.limited_auto_sell_service = limited_auto_sell_service
        self.now_provider = now_provider or (lambda: datetime.now(UTC))

    def status(self, db: Session) -> dict[str, Any]:
        runtime = self.runtime_settings.get_settings_read_only(db)
        scheduler_gate = position_lifecycle_scheduler_gate(runtime)
        lifecycles = (
            db.query(PositionLifecycle)
            .order_by(PositionLifecycle.opened_at.desc(), PositionLifecycle.id.desc())
            .all()
        )
        active = [row for row in lifecycles if row.status in {OPEN, CLOSING}]
        return sanitize_kis_payload(
            {
                "provider": PROVIDER,
                "market": MARKET,
                "mode": MODE,
                "status": "ok",
                "scheduler_enabled": scheduler_gate["scheduler_enabled"],
                "kis_scheduler_enabled": scheduler_gate["kis_scheduler_enabled"],
                "kis_position_lifecycle_scheduler_enabled": scheduler_gate[
                    "kis_position_lifecycle_scheduler_enabled"
                ],
                "scheduler_execution_allowed": scheduler_gate[
                    "scheduler_execution_allowed"
                ],
                "blocking_reasons": scheduler_gate["blocking_reasons"],
                "active_lifecycle_count": len(active),
                "lifecycles": [_serialize_lifecycle(row) for row in lifecycles],
                "scheduler": {
                    "slots_kst": ["10:00", "12:00", "14:30"],
                    "sell_only": True,
                    "buy_scheduler_enabled": False,
                    "position_management_priority": "before_new_buy_candidates",
                    "runs_only_when_position_exists": True,
                    "scheduler_enabled": scheduler_gate["scheduler_enabled"],
                    "kis_scheduler_enabled": scheduler_gate[
                        "kis_scheduler_enabled"
                    ],
                    "kis_position_lifecycle_scheduler_enabled": (
                        scheduler_gate[
                            "kis_position_lifecycle_scheduler_enabled"
                        ]
                    ),
                    "scheduler_execution_allowed": scheduler_gate[
                        "scheduler_execution_allowed"
                    ],
                    "blocking_reasons": scheduler_gate["blocking_reasons"],
                },
                "runtime": _buy_sell_runtime_snapshot(runtime),
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        )

    def sync_filled_buy(
        self,
        db: Session,
        order: OrderLog | int,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        row = db.get(OrderLog, int(order)) if isinstance(order, int) else order
        now_utc = _aware_utc(now or self.now_provider())
        if row is None:
            return {"created": False, "reason": "entry_order_not_found"}
        if not _is_filled_kis_buy(row):
            return {
                "created": False,
                "reason": "entry_order_not_filled_buy",
                "order_id": row.id,
                "internal_status": row.internal_status,
            }
        if not _is_reviewed_buy_order(row):
            return {
                "created": False,
                "reason": "entry_order_not_reviewed_buy",
                "order_id": row.id,
            }

        existing = (
            db.query(PositionLifecycle)
            .filter(PositionLifecycle.entry_order_id == int(row.id))
            .first()
        )
        if existing is not None:
            self._disable_new_buy_settings(db)
            return {
                "created": False,
                "reason": "lifecycle_already_exists",
                "lifecycle": _serialize_lifecycle(existing),
            }

        entry_price = _entry_price(row)
        if entry_price is None or entry_price <= 0:
            return {
                "created": False,
                "reason": "entry_price_unavailable",
                "order_id": row.id,
            }

        quantity = 1.0
        opened_at = _naive_utc(
            _aware_utc(
                row.filled_at
                or row.last_synced_at
                or row.submitted_at
                or row.created_at
                or now_utc
            )
        )
        lifecycle = PositionLifecycle(
            symbol=str(row.symbol or "").strip().upper(),
            entry_order_id=int(row.id),
            entry_price=float(entry_price),
            cost_basis=round(float(entry_price) * quantity, 2),
            quantity=quantity,
            status=OPEN,
            opened_at=opened_at,
            last_price=float(entry_price),
            unrealized_pl=0.0,
            unrealized_pl_pct=0.0,
            max_price_since_entry=float(entry_price),
            stop_loss_threshold_pct=round(
                DEFAULT_EXIT_STOP_LOSS_THRESHOLD_DECIMAL * 100.0,
                4,
            ),
            take_profit_threshold_pct=round(
                DEFAULT_EXIT_TAKE_PROFIT_THRESHOLD_DECIMAL * 100.0,
                4,
            ),
            exit_reason=None,
            exit_order_id=None,
            last_evaluated_at=None,
        )
        db.add(lifecycle)
        db.commit()
        db.refresh(lifecycle)

        self._disable_new_buy_settings(db)
        return {
            "created": True,
            "reason": "filled_buy_lifecycle_created",
            "lifecycle": _serialize_lifecycle(lifecycle),
        }

    def sync_current_position(
        self,
        db: Session,
        lifecycle: PositionLifecycle | None = None,
        *,
        now: datetime | None = None,
        positions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        row = lifecycle or self._latest_active_lifecycle(db)
        now_utc = _aware_utc(now or self.now_provider())
        if row is None:
            return {
                "synced": False,
                "reason": "no_open_lifecycle",
                "position": None,
                "lifecycle": None,
            }

        matched = _find_position(
            positions if positions is not None else self._broker_positions(),
            row.symbol,
        )
        row.last_evaluated_at = _naive_utc(now_utc)
        if matched is None:
            row.status = CLOSED
            row.exit_reason = row.exit_reason or "broker_position_not_found"
            db.commit()
            db.refresh(row)
            return {
                "synced": True,
                "reason": "broker_position_not_found",
                "position": None,
                "lifecycle": _serialize_lifecycle(row),
            }

        current_price = _position_current_price(matched)
        quantity = float(row.quantity or 1.0)
        if current_price is not None and current_price > 0:
            current_value = current_price * quantity
            unrealized_pl = (
                current_value - float(row.cost_basis)
                if row.cost_basis is not None
                else None
            )
            unrealized_pl_pct = (
                unrealized_pl / float(row.cost_basis)
                if unrealized_pl is not None and row.cost_basis and row.cost_basis > 0
                else None
            )
            row.last_price = float(current_price)
            row.unrealized_pl = _round_money(unrealized_pl)
            row.unrealized_pl_pct = _round_ratio(unrealized_pl_pct)
            row.max_price_since_entry = max(
                _safe_float(row.max_price_since_entry, float(row.entry_price)),
                float(current_price),
            )
        if row.status == CLOSED:
            row.status = OPEN
        db.commit()
        db.refresh(row)
        return {
            "synced": True,
            "reason": "position_synced",
            "position": _position_for_lifecycle(matched, row),
            "lifecycle": _serialize_lifecycle(row),
        }

    def evaluate_position(
        self,
        db: Session,
        lifecycle: PositionLifecycle | None = None,
        *,
        now: datetime | None = None,
        positions: list[dict[str, Any]] | None = None,
        open_orders: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        row = lifecycle or self._latest_active_lifecycle(db)
        if row is None:
            return self._decision_payload(
                lifecycle=None,
                action=HOLD,
                result="skipped",
                reason="no_open_lifecycle",
                current_price=None,
                order_id=None,
                position=None,
            )

        synced = self.sync_current_position(
            db,
            row,
            now=now,
            positions=positions,
        )
        db.refresh(row)
        position = synced.get("position")
        current_price = row.last_price

        if row.status == CLOSED:
            return self._decision_payload(
                lifecycle=row,
                action=HOLD,
                result=CLOSED,
                reason="broker_position_not_found",
                current_price=current_price,
                order_id=row.exit_order_id,
                position=position,
            )

        broker_open_orders = (
            open_orders if open_orders is not None else self._broker_open_orders()
        )
        if self._has_open_or_unknown_sell_order(db, row, broker_open_orders):
            row.status = CLOSING
            row.exit_reason = row.exit_reason or "open_sell_order_exists"
            row.last_evaluated_at = _naive_utc(_aware_utc(now or self.now_provider()))
            db.commit()
            db.refresh(row)
            return self._decision_payload(
                lifecycle=row,
                action=HOLD,
                result="blocked",
                reason="duplicate_open_sell_order",
                current_price=current_price,
                order_id=row.exit_order_id,
                position=position,
            )

        if not _valid_cost_basis(row):
            row.exit_reason = "cost_basis_unavailable"
            db.commit()
            db.refresh(row)
            return self._decision_payload(
                lifecycle=row,
                action=MANUAL_REVIEW,
                result=MANUAL_REVIEW,
                reason="cost_basis_unavailable",
                current_price=current_price,
                order_id=None,
                position=position,
            )

        if current_price is None or current_price <= 0:
            row.exit_reason = "current_price_unavailable"
            db.commit()
            db.refresh(row)
            return self._decision_payload(
                lifecycle=row,
                action=MANUAL_REVIEW,
                result=MANUAL_REVIEW,
                reason="current_price_unavailable",
                current_price=current_price,
                order_id=None,
                position=position,
            )

        stop_loss_threshold = _stop_loss_threshold_price(row)
        if stop_loss_threshold is not None and current_price <= stop_loss_threshold:
            row.exit_reason = "stop_loss_triggered"
            db.commit()
            db.refresh(row)
            return self._decision_payload(
                lifecycle=row,
                action=SELL_READY,
                result=SELL_READY,
                reason="stop_loss_triggered",
                current_price=current_price,
                order_id=None,
                position=position,
                stop_loss_triggered=True,
            )

        if _take_profit_triggered(row, current_price):
            row.exit_reason = "take_profit_execution_disabled"
            db.commit()
            db.refresh(row)
            return self._decision_payload(
                lifecycle=row,
                action=HOLD,
                result="hold",
                reason="take_profit_execution_disabled",
                current_price=current_price,
                order_id=None,
                position=position,
                take_profit_triggered=True,
            )

        if _weak_trend_triggered(position) or _sell_pressure_triggered(position):
            reason = (
                "weak_trend_triggered"
                if _weak_trend_triggered(position)
                else "sell_pressure_triggered"
            )
            row.exit_reason = reason
            db.commit()
            db.refresh(row)
            return self._decision_payload(
                lifecycle=row,
                action=REVIEW_SELL,
                result=REVIEW_SELL,
                reason=reason,
                current_price=current_price,
                order_id=None,
                position=position,
            )

        row.exit_reason = "no_exit_condition"
        db.commit()
        db.refresh(row)
        return self._decision_payload(
            lifecycle=row,
            action=HOLD,
            result="hold",
            reason="no_exit_condition",
            current_price=current_price,
            order_id=None,
            position=position,
        )

    def run_management_once(
        self,
        db: Session,
        *,
        execute: bool = False,
        trigger_source: str = "manual_position_management",
        scheduler_slot: str | None = None,
        now: datetime | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        now_utc = _aware_utc(now or self.now_provider())
        self._ensure_lifecycles_from_filled_buys(db, now=now_utc)
        active = self._active_lifecycles(db)
        if active:
            self._disable_new_buy_settings(db)

        if not active:
            payload = self._decision_payload(
                lifecycle=None,
                action=HOLD,
                result="skipped",
                reason="no_open_lifecycle",
                current_price=None,
                order_id=None,
                position=None,
            )
            payload.update(
                {
                    "trigger_source": trigger_source,
                    "scheduler_slot": scheduler_slot,
                    "execute": execute,
                    "preflight_only": not execute,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                }
            )
            run = self._record_run(
                db,
                payload=payload,
                trigger_source=trigger_source,
                mode=RUN_MODE if execute else PREFLIGHT_MODE,
                now=now_utc,
            )
            payload["run"] = _serialize_run(run)
            return sanitize_kis_payload(
                {
                    **payload,
                    "managed_count": 0,
                    "items": [],
                    "summary": _summary([payload]),
                }
            )

        positions = self._broker_positions()
        open_orders = self._broker_open_orders()
        items: list[dict[str, Any]] = []
        sell_submitted = False
        for row in active:
            decision = self.evaluate_position(
                db,
                row,
                now=now_utc,
                positions=positions,
                open_orders=open_orders,
            )
            if execute and decision.get("action") == SELL_READY and not sell_submitted:
                decision = self._execute_stop_loss(
                    db,
                    row,
                    decision=decision,
                    now=now_utc,
                    include_raw=include_raw,
                )
                sell_submitted = decision.get("real_order_submitted") is True
            else:
                decision.update(
                    {
                        "real_order_submitted": False,
                        "broker_submit_called": False,
                        "manual_submit_called": False,
                    }
                )
            decision.update(
                {
                    "trigger_source": trigger_source,
                    "scheduler_slot": scheduler_slot,
                    "execute": execute,
                    "preflight_only": not execute,
                }
            )
            run = self._record_run(
                db,
                payload=decision,
                trigger_source=trigger_source,
                mode=RUN_MODE if execute else PREFLIGHT_MODE,
                now=now_utc,
            )
            decision["run"] = _serialize_run(run)
            items.append(decision)

        response = {
            "provider": PROVIDER,
            "market": MARKET,
            "mode": RUN_MODE if execute else PREFLIGHT_MODE,
            "trigger_source": trigger_source,
            "scheduler_slot": scheduler_slot,
            "sell_only": True,
            "buy_execution_allowed": False,
            "managed_count": len(items),
            "items": items,
            "summary": _summary(items),
            "real_order_submitted": any(
                item.get("real_order_submitted") is True for item in items
            ),
            "broker_submit_called": any(
                item.get("broker_submit_called") is True for item in items
            ),
            "manual_submit_called": any(
                item.get("manual_submit_called") is True for item in items
            ),
        }
        return sanitize_kis_payload(response)

    def preflight_once(
        self,
        db: Session,
        *,
        trigger_source: str = "manual_position_management_preflight",
        scheduler_slot: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return self.run_management_once(
            db,
            execute=False,
            trigger_source=trigger_source,
            scheduler_slot=scheduler_slot,
            now=now,
        )

    def run_once(
        self,
        db: Session,
        *,
        trigger_source: str = "manual_position_management_run",
        scheduler_slot: str | None = None,
        now: datetime | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        return self.run_management_once(
            db,
            execute=True,
            trigger_source=trigger_source,
            scheduler_slot=scheduler_slot,
            now=now,
            include_raw=include_raw,
        )

    def has_manageable_position(self, db: Session) -> bool:
        if self._active_lifecycles(db):
            return True
        try:
            return bool(_held_positions(self._broker_positions()))
        except Exception:
            return False

    def _execute_stop_loss(
        self,
        db: Session,
        lifecycle: PositionLifecycle,
        *,
        decision: dict[str, Any],
        now: datetime,
        include_raw: bool,
    ) -> dict[str, Any]:
        block_reason = self._sell_execution_block_reason(db, lifecycle, now=now)
        if block_reason:
            return {
                **decision,
                "action": HOLD,
                "result": "blocked",
                "reason": block_reason,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }

        service = self._limited_sell_service()
        try:
            sell_result = service.run_once(db, now=now)
        except Exception as exc:
            latest_order = _latest_sell_order(db, lifecycle.symbol)
            if latest_order is not None:
                lifecycle.status = CLOSING
                lifecycle.exit_order_id = int(latest_order.id)
                lifecycle.exit_reason = "stop_loss_submit_uncertain"
                lifecycle.last_evaluated_at = _naive_utc(now)
                db.commit()
            return {
                **decision,
                "action": HOLD,
                "result": "error",
                "reason": f"stop_loss_sell_submit_failed:{exc.__class__.__name__}",
                "order_id": latest_order.id if latest_order is not None else None,
                "real_order_submitted": False,
                "broker_submit_called": latest_order is not None,
                "manual_submit_called": latest_order is not None,
                "sell_result": None,
            }

        child = sell_result if include_raw else _without_raw(sell_result)
        order_id = _int_or_none(
            sell_result.get("order_id") or sell_result.get("order_log_id")
        )
        submitted = sell_result.get("real_order_submitted") is True
        broker_called = sell_result.get("broker_submit_called") is True
        manual_called = sell_result.get("manual_submit_called") is True
        if submitted or (broker_called and order_id is not None):
            lifecycle.status = CLOSING
            lifecycle.exit_order_id = order_id
            lifecycle.exit_reason = "stop_loss_triggered"
            lifecycle.last_evaluated_at = _naive_utc(now)
            db.commit()
            db.refresh(lifecycle)

        if submitted:
            return {
                **decision,
                "action": "SELL",
                "result": "submitted",
                "reason": str(
                    sell_result.get("reason") or "stop_loss_auto_sell_submitted"
                ),
                "order_id": order_id,
                "real_order_submitted": True,
                "broker_submit_called": broker_called,
                "manual_submit_called": manual_called,
                "sell_result": child,
            }
        return {
            **decision,
            "action": HOLD,
            "result": str(sell_result.get("result") or "blocked"),
            "reason": str(sell_result.get("reason") or "stop_loss_sell_blocked"),
            "order_id": order_id,
            "real_order_submitted": False,
            "broker_submit_called": broker_called,
            "manual_submit_called": manual_called,
            "sell_result": child,
        }

    def _sell_execution_block_reason(
        self,
        db: Session,
        lifecycle: PositionLifecycle,
        *,
        now: datetime,
    ) -> str | None:
        if lifecycle.status == CLOSING and lifecycle.exit_order_id is not None:
            return "exit_order_already_pending"
        if self._has_open_or_unknown_sell_order(db, lifecycle, self._broker_open_orders()):
            return "duplicate_open_sell_order"
        daily = self._daily_sell_state(db, now=now)
        if daily["daily_limit_reached"]:
            return "daily_auto_sell_limit_reached"
        return None

    def _daily_sell_state(self, db: Session, *, now: datetime) -> dict[str, Any]:
        runtime = self.runtime_settings.get_settings_read_only(db)
        max_orders = max(
            0,
            int(runtime.get("kis_limited_auto_sell_max_orders_per_day", 1) or 0),
        )
        start_utc, end_utc = _kr_day_bounds_utc(now)
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

    def _has_open_or_unknown_sell_order(
        self,
        db: Session,
        lifecycle: PositionLifecycle,
        open_orders: list[dict[str, Any]],
    ) -> bool:
        if lifecycle.status == CLOSING and lifecycle.exit_order_id is not None:
            return True
        symbol = str(lifecycle.symbol or "").upper()
        for order in open_orders:
            if _order_symbol(order) == symbol and _order_is_sell(order):
                return True
        row = (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.symbol == symbol)
            .filter(OrderLog.side == SELL)
            .filter(OrderLog.internal_status.in_(sorted(OPEN_ORDER_STATUSES)))
            .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
            .first()
        )
        return row is not None

    def _ensure_lifecycles_from_filled_buys(
        self,
        db: Session,
        *,
        now: datetime,
    ) -> None:
        rows = (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.side == BUY)
            .filter(OrderLog.internal_status == InternalOrderStatus.FILLED.value)
            .order_by(OrderLog.filled_at.desc(), OrderLog.id.desc())
            .all()
        )
        for row in rows:
            self.sync_filled_buy(db, row, now=now)

    def _disable_new_buy_settings(self, db: Session) -> dict[str, Any]:
        runtime = self.runtime_settings.get_settings_read_only(db)
        payload = {
            "kis_live_auto_buy_enabled": False,
            "kis_limited_auto_buy_enabled": False,
            "kis_scheduler_buy_enabled": False,
            "kis_scheduler_allow_limited_auto_buy": False,
            "strategy_auto_buy_scheduler_enabled": False,
            "strategy_live_auto_buy_scheduler_enabled": False,
            "auto_buy_live_phase1_enabled": False,
            "auto_buy_live_phase1_allow_real_orders": False,
        }
        if all(runtime.get(key) is value for key, value in payload.items()):
            return runtime
        return self.runtime_settings.update_settings(db, payload)

    def _latest_active_lifecycle(self, db: Session) -> PositionLifecycle | None:
        return (
            db.query(PositionLifecycle)
            .filter(PositionLifecycle.status.in_([OPEN, CLOSING]))
            .order_by(PositionLifecycle.opened_at.desc(), PositionLifecycle.id.desc())
            .first()
        )

    def _active_lifecycles(self, db: Session) -> list[PositionLifecycle]:
        return (
            db.query(PositionLifecycle)
            .filter(PositionLifecycle.status.in_([OPEN, CLOSING]))
            .order_by(PositionLifecycle.opened_at.asc(), PositionLifecycle.id.asc())
            .all()
        )

    def _broker_positions(self) -> list[dict[str, Any]]:
        if self.client is None:
            return []
        return _held_positions(self.client.list_positions())

    def _broker_open_orders(self) -> list[dict[str, Any]]:
        if self.client is None:
            return []
        try:
            raw = self.client.list_open_orders()
        except Exception:
            return []
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    def _limited_sell_service(self) -> Any:
        if self.limited_auto_sell_service is not None:
            return self.limited_auto_sell_service
        if self.client is None:
            raise RuntimeError("KIS client is required for stop-loss execution.")
        self.limited_auto_sell_service = KisLimitedAutoSellService(
            self.client,
            runtime_settings=self.runtime_settings,
        )
        return self.limited_auto_sell_service

    def _decision_payload(
        self,
        *,
        lifecycle: PositionLifecycle | None,
        action: str,
        result: str,
        reason: str,
        current_price: float | None,
        order_id: int | None,
        position: dict[str, Any] | None,
        stop_loss_triggered: bool = False,
        take_profit_triggered: bool = False,
    ) -> dict[str, Any]:
        entry_price = lifecycle.entry_price if lifecycle is not None else None
        stop_loss_threshold = (
            _stop_loss_threshold_price(lifecycle) if lifecycle is not None else None
        )
        payload = {
            "provider": PROVIDER,
            "market": MARKET,
            "mode": MODE,
            "lifecycle_id": lifecycle.id if lifecycle is not None else None,
            "symbol": lifecycle.symbol if lifecycle is not None else "POSITIONS",
            "entry_order_id": lifecycle.entry_order_id if lifecycle is not None else None,
            "entry_price": entry_price,
            "cost_basis": lifecycle.cost_basis if lifecycle is not None else None,
            "quantity": lifecycle.quantity if lifecycle is not None else None,
            "status": lifecycle.status if lifecycle is not None else None,
            "current_price": current_price,
            "last_price": current_price,
            "unrealized_pl": lifecycle.unrealized_pl if lifecycle is not None else None,
            "unrealized_pl_pct": (
                lifecycle.unrealized_pl_pct if lifecycle is not None else None
            ),
            "max_price_since_entry": (
                lifecycle.max_price_since_entry if lifecycle is not None else None
            ),
            "stop_loss_threshold_pct": (
                lifecycle.stop_loss_threshold_pct if lifecycle is not None else None
            ),
            "stop_loss_threshold": stop_loss_threshold,
            "take_profit_threshold_pct": (
                lifecycle.take_profit_threshold_pct if lifecycle is not None else None
            ),
            "take_profit_execution_enabled": False,
            "action": action,
            "result": result,
            "reason": reason,
            "exit_reason": reason,
            "order_id": order_id,
            "exit_order_id": (
                lifecycle.exit_order_id if lifecycle is not None else order_id
            ),
            "stop_loss_triggered": stop_loss_triggered,
            "take_profit_triggered": take_profit_triggered,
            "weak_trend_triggered": _weak_trend_triggered(position),
            "sell_pressure_triggered": _sell_pressure_triggered(position),
            "position": position,
            "sell_only": True,
            "buy_execution_allowed": False,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
        }
        return sanitize_kis_payload(payload)

    def _record_run(
        self,
        db: Session,
        *,
        payload: dict[str, Any],
        trigger_source: str,
        mode: str,
        now: datetime,
    ) -> TradeRunLog:
        order_id = _int_or_none(payload.get("order_id"))
        required_log_fields = {
            "symbol": payload.get("symbol"),
            "entry_price": payload.get("entry_price"),
            "current_price": payload.get("current_price"),
            "unrealized_pl": payload.get("unrealized_pl"),
            "unrealized_pl_pct": payload.get("unrealized_pl_pct"),
            "stop_loss_threshold": payload.get("stop_loss_threshold"),
            "action": payload.get("action"),
            "reason": payload.get("reason"),
            "order_id": order_id,
        }
        response_payload = {
            **payload,
            "operation_log": required_log_fields,
        }
        run = TradeRunLog(
            run_key=f"kis_position_mgmt_{uuid.uuid4().hex[:12]}",
            trigger_source=trigger_source,
            symbol=str(payload.get("symbol") or "POSITIONS"),
            mode=mode,
            stage="done",
            result=str(payload.get("result") or "hold"),
            reason=str(payload.get("reason") or ""),
            order_id=order_id,
            request_payload=_json(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": mode,
                    "trigger_source": trigger_source,
                    "sell_only": True,
                    "buy_execution_allowed": False,
                }
            ),
            response_payload=_json(response_payload),
            created_at=_naive_utc(now),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run


def _is_filled_kis_buy(order: OrderLog) -> bool:
    return (
        str(order.broker or "").lower() == PROVIDER
        and str(order.side or "").lower() == BUY
        and str(order.internal_status or "").upper()
        == InternalOrderStatus.FILLED.value
    )


def _is_reviewed_buy_order(order: OrderLog) -> bool:
    payloads = [
        _parse_object(order.request_payload),
        _parse_object(order.response_payload),
        _parse_object(order.last_sync_payload),
    ]
    return any(_payload_has_reviewed_buy_marker(payload) for payload in payloads)


def _payload_has_reviewed_buy_marker(payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    text_values = [
        payload.get("source_type"),
        payload.get("source_context"),
        payload.get("operator_action_source"),
        payload.get("source_endpoint"),
        payload.get("reason"),
        payload.get("mode"),
        payload.get("trigger_source"),
    ]
    normalized = {str(value or "").strip().lower() for value in text_values}
    if REVIEWED_BUY_SOURCE_TYPE in normalized:
        return True
    if REVIEWED_BUY_ENDPOINT in normalized or REVIEWED_BUY_MODE in normalized:
        return True
    reason = str(payload.get("reason") or "").strip().lower()
    if "operator reviewed limited auto buy" in reason:
        return True
    for key in ("source_metadata", "audit_metadata"):
        nested = payload.get(key)
        if isinstance(nested, dict) and _payload_has_reviewed_buy_marker(nested):
            return True
    return False


def _entry_price(order: OrderLog) -> float | None:
    for value in (order.avg_fill_price, order.filled_avg_price, order.limit_price):
        parsed = _safe_float_or_none(value)
        if parsed is not None and parsed > 0:
            return parsed
    qty = _safe_float_or_none(order.filled_qty) or _safe_float_or_none(order.qty)
    if qty is not None and qty > 0:
        notional = _safe_float_or_none(order.notional)
        if notional is not None and notional > 0:
            return notional / qty
    payloads = [_parse_object(order.response_payload), _parse_object(order.request_payload)]
    for payload in payloads:
        for key in (
            "avg_fill_price",
            "filled_avg_price",
            "entry_price",
            "current_price",
            "estimated_price",
        ):
            parsed = _safe_float_or_none(payload.get(key))
            if parsed is not None and parsed > 0:
                return parsed
    return None


def _valid_cost_basis(lifecycle: PositionLifecycle) -> bool:
    return (
        lifecycle.entry_price is not None
        and lifecycle.entry_price > 0
        and lifecycle.cost_basis is not None
        and lifecycle.cost_basis > 0
        and lifecycle.quantity is not None
        and lifecycle.quantity > 0
    )


def _stop_loss_threshold_price(lifecycle: PositionLifecycle | None) -> float | None:
    if lifecycle is None or lifecycle.entry_price is None:
        return None
    pct = _safe_float(
        lifecycle.stop_loss_threshold_pct,
        DEFAULT_EXIT_STOP_LOSS_THRESHOLD_DECIMAL * 100.0,
    )
    if pct <= 0:
        pct = DEFAULT_EXIT_STOP_LOSS_THRESHOLD_DECIMAL * 100.0
    return round(float(lifecycle.entry_price) * (1.0 - (abs(pct) / 100.0)), 4)


def _take_profit_triggered(
    lifecycle: PositionLifecycle,
    current_price: float,
) -> bool:
    pct = _safe_float(
        lifecycle.take_profit_threshold_pct,
        DEFAULT_EXIT_TAKE_PROFIT_THRESHOLD_DECIMAL * 100.0,
    )
    if pct <= 0 or lifecycle.entry_price is None or lifecycle.entry_price <= 0:
        return False
    threshold = float(lifecycle.entry_price) * (1.0 + (abs(pct) / 100.0))
    return current_price >= threshold


def position_lifecycle_scheduler_gate(runtime: dict[str, Any]) -> dict[str, Any]:
    gate = {
        key: bool(runtime.get(key, False))
        for key, _reason in POSITION_LIFECYCLE_SCHEDULER_GATE_FLAGS
    }
    blocking_reasons = [
        reason
        for key, reason in POSITION_LIFECYCLE_SCHEDULER_GATE_FLAGS
        if not gate[key]
    ]
    return {
        **gate,
        "scheduler_execution_allowed": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
    }


def position_lifecycle_scheduler_block_reason(gate: dict[str, Any]) -> str:
    reasons = gate.get("blocking_reasons") or []
    if not reasons:
        return "position_lifecycle_scheduler_allowed"
    return ",".join(str(reason) for reason in reasons)


def _held_positions(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_position(item)
        if _safe_float(normalized.get("qty"), 0.0) > 0:
            result.append(normalized)
    return result


def _normalize_position(item: dict[str, Any]) -> dict[str, Any]:
    raw_symbol = item.get("symbol") or item.get("pdno") or item.get("code")
    symbol = str(raw_symbol or "").strip()
    if symbol.isdigit() and len(symbol) < 6:
        symbol = symbol.zfill(6)
    return {
        **item,
        "symbol": symbol.upper(),
        "qty": _safe_float(item.get("qty") or item.get("hldg_qty"), 0.0),
        "current_price": _safe_float_or_none(
            item.get("current_price") or item.get("prpr") or item.get("stck_prpr")
        ),
        "avg_entry_price": _safe_float_or_none(
            item.get("avg_entry_price") or item.get("pchs_avg_pric")
        ),
        "cost_basis": _safe_float_or_none(
            item.get("cost_basis")
            or item.get("pchs_amt")
            or item.get("pchs_amt_smtl_amt")
        ),
        "unrealized_pl": _safe_float_or_none(
            item.get("unrealized_pl") or item.get("evlu_pfls_amt")
        ),
    }


def _find_position(
    positions: list[dict[str, Any]],
    symbol: str,
) -> dict[str, Any] | None:
    normalized = str(symbol or "").upper()
    for item in positions:
        if str(item.get("symbol") or "").upper() == normalized:
            return item
    return None


def _position_for_lifecycle(
    position: dict[str, Any],
    lifecycle: PositionLifecycle,
) -> dict[str, Any]:
    current_price = _position_current_price(position)
    quantity = float(lifecycle.quantity or 1.0)
    current_value = (
        round(current_price * quantity, 2)
        if current_price is not None and current_price > 0
        else None
    )
    return {
        **position,
        "symbol": lifecycle.symbol,
        "qty": quantity,
        "quantity": quantity,
        "avg_entry_price": lifecycle.entry_price,
        "entry_price": lifecycle.entry_price,
        "cost_basis": lifecycle.cost_basis,
        "current_price": current_price,
        "current_value": current_value,
        "unrealized_pl": lifecycle.unrealized_pl,
        "unrealized_pl_pct": lifecycle.unrealized_pl_pct,
    }


def _position_current_price(position: dict[str, Any] | None) -> float | None:
    if not isinstance(position, dict):
        return None
    return _safe_float_or_none(
        position.get("current_price") or position.get("prpr") or position.get("stck_prpr")
    )


def _weak_trend_triggered(position: dict[str, Any] | None) -> bool:
    if not isinstance(position, dict):
        return False
    if position.get("weak_trend_triggered") is True:
        return True
    flags = {item.lower() for item in _string_list(position.get("risk_flags"))}
    if "weak_trend_triggered" in flags or "weak_trend" in flags:
        return True
    technical = position.get("technical_snapshot")
    if isinstance(technical, dict):
        below_count = sum(
            1
            for key in ("price_vs_ema20", "price_vs_ema50", "price_vs_vwap")
            if technical.get(key) == "below"
        )
        momentum = _safe_float_or_none(technical.get("momentum"))
        return below_count >= 2 or (momentum is not None and momentum < 0)
    return False


def _sell_pressure_triggered(position: dict[str, Any] | None) -> bool:
    if not isinstance(position, dict):
        return False
    if position.get("sell_pressure_triggered") is True:
        return True
    flags = {item.lower() for item in _string_list(position.get("risk_flags"))}
    if "sell_pressure_triggered" in flags or "sell_pressure" in flags:
        return True
    sell_score = _first_float(position, "final_sell_score", "sell_score", "quant_sell_score")
    buy_score = _first_float(position, "final_buy_score", "buy_score", "quant_buy_score")
    if sell_score is None:
        return False
    return sell_score >= 65 or (buy_score is not None and sell_score >= 50 and sell_score > buy_score)


def _order_symbol(order: dict[str, Any]) -> str:
    raw = order.get("symbol") or order.get("pdno") or order.get("code")
    symbol = str(raw or "").strip()
    if symbol.isdigit() and len(symbol) < 6:
        symbol = symbol.zfill(6)
    return symbol.upper()


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


def _latest_sell_order(db: Session, symbol: str) -> OrderLog | None:
    return (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.symbol == str(symbol or "").upper())
        .filter(OrderLog.side == SELL)
        .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
        .first()
    )


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


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    first = items[0] if items else {}
    return {
        "managed_count": len(items),
        "sell_ready_count": len([item for item in items if item.get("action") == SELL_READY]),
        "review_sell_count": len([item for item in items if item.get("action") == REVIEW_SELL]),
        "hold_count": len([item for item in items if item.get("action") == HOLD]),
        "manual_review_count": len([item for item in items if item.get("action") == MANUAL_REVIEW]),
        "real_order_submitted": any(item.get("real_order_submitted") is True for item in items),
        "symbol": first.get("symbol"),
        "action": first.get("action"),
        "reason": first.get("reason"),
        "order_id": first.get("order_id"),
    }


def _buy_sell_runtime_snapshot(runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "dry_run": bool(runtime.get("dry_run", True)),
        "kill_switch": bool(runtime.get("kill_switch", False)),
        "kis_position_lifecycle_scheduler_enabled": bool(
            runtime.get("kis_position_lifecycle_scheduler_enabled", False)
        ),
        "kis_live_auto_buy_enabled": bool(runtime.get("kis_live_auto_buy_enabled", False)),
        "kis_limited_auto_buy_enabled": bool(runtime.get("kis_limited_auto_buy_enabled", False)),
        "kis_scheduler_buy_enabled": bool(runtime.get("kis_scheduler_buy_enabled", False)),
        "kis_scheduler_allow_limited_auto_buy": bool(
            runtime.get("kis_scheduler_allow_limited_auto_buy", False)
        ),
        "kis_live_auto_sell_enabled": bool(runtime.get("kis_live_auto_sell_enabled", False)),
        "kis_limited_auto_sell_enabled": bool(runtime.get("kis_limited_auto_sell_enabled", False)),
        "kis_limited_auto_sell_max_orders_per_day": int(
            runtime.get("kis_limited_auto_sell_max_orders_per_day", 1) or 0
        ),
    }


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


def _parse_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


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


def _safe_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any, default: float) -> float:
    parsed = _safe_float_or_none(value)
    return default if parsed is None else parsed


def _round_money(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _round_ratio(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 8)


def _first_float(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _safe_float_or_none(payload.get(key))
        if value is not None:
            return value
    return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
