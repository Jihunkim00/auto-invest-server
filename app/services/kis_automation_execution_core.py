from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.enums import InternalOrderStatus
from app.core.automation_mode import automation_mode_authority
from app.services.automation_execution_authority_service import (
    AutomationExecutionAuthorityService,
)
from app.db.models import OrderLog
from app.services.kis_manual_order_service import KisManualOrderSubmitRequest
from app.services.kis_order_validation_service import (
    KisOrderValidationRequest,
    record_kis_order_validation,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload


class KisAutomationExecutionCore:
    POSSIBLE_ORDER_MAX_AGE_SECONDS = 10.0
    HARD_MAX_POSITIONS = 1
    HARD_MAX_NOTIONAL_KRW = 1_000_000.0

    OPEN_ORDER_INTERNAL_STATUSES = {
        InternalOrderStatus.REQUESTED.value,
        InternalOrderStatus.SUBMITTED.value,
        InternalOrderStatus.ACCEPTED.value,
        InternalOrderStatus.PENDING.value,
        InternalOrderStatus.PARTIALLY_FILLED.value,
        InternalOrderStatus.UNKNOWN_STALE.value,
    }

    def __init__(
        self,
        client: Any | None = None,
        *,
        broker: Any | None = None,
        validation_service: Any | None = None,
        order_sync_service: Any | None = None,
        lifecycle_service: Any | None = None,
        runtime_settings: Any | None = None,
        positions_loader: Callable[[Session], list[dict[str, Any]]] | None = None,
        open_orders_loader: Callable[[Session], list[dict[str, Any]]] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.client = client
        self.broker = broker
        self.validation_service = validation_service
        self.order_sync_service = order_sync_service
        self.lifecycle_service = lifecycle_service
        self.runtime_settings = runtime_settings
        self.positions_loader = positions_loader
        self.open_orders_loader = open_orders_loader
        self.now_provider = now_provider or (lambda: datetime.now(UTC))

    def validate_order(
        self,
        db: Session,
        request: KisOrderValidationRequest,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if self.validation_service is None:
            return {
                "validated_for_submission": False,
                "can_submit_later": False,
                "block_reasons": ["kis_validation_service_unavailable"],
                "primary_block_reason": "kis_validation_service_unavailable",
            }

        try:
            try:
                result = self.validation_service.validate(request, now=now)
            except TypeError:
                result = self.validation_service.validate(request)

            payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)

            try:
                payload["validation_id"] = record_kis_order_validation(
                    db,
                    request=request,
                    result=result,
                ).id
            except Exception:
                pass

            return sanitize_kis_payload(payload)

        except Exception as exc:
            return {
                "validated_for_submission": False,
                "can_submit_later": False,
                "block_reasons": ["validation_failed"],
                "primary_block_reason": "validation_failed",
                "error": _error(exc),
            }

    def submit_manual(
        self,
        db: Session,
        request: KisManualOrderSubmitRequest,
        *,
        manual_order_service: Any,
        now: datetime | None = None,
    ) -> tuple[int, dict[str, Any]]:
        status_code, response = manual_order_service.submit_manual(
            db,
            request,
            now=now or self.now_provider(),
        )

        payload = dict(response or {})
        order_id = _int(payload.get("order_id") or payload.get("order_log_id"))
        order = db.get(OrderLog, order_id) if order_id is not None else None

        if order is not None:
            payload.update(
                {
                    "execution_core": "kis_automation_execution_core",
                    "kis_odno": order.kis_odno or order.broker_order_id,
                    "internal_status": order.internal_status,
                    "lifecycle": self._reconcile_filled_order(
                        db,
                        order,
                        now=now,
                    ),
                }
            )

        return int(status_code), sanitize_kis_payload(payload)

    def submit_market_buy(
        self,
        db: Session,
        *,
        order: OrderLog,
        symbol: str,
        qty: int,
        submitter: Callable[[], dict[str, Any]] | None = None,
        now: datetime | None = None,
        expected_price: float | None = None,
        max_positions: int = 1,
        max_order_notional_krw: float | None = None,
        min_price_krw: float | None = None,
        max_price_krw: float | None = None,
    ) -> dict[str, Any]:
        authority = self._execution_authority(db)

        if authority.get("automation_mode") == "off":
            return self._blocked(
                db,
                order,
                {
                    "allowed": False,
                    "reason": "automation_mode_off",
                    "automation_mode": "off",
                },
            )

        guard = self._buy_jit_guard(
            db,
            order_id=order.id,
            symbol=symbol,
            qty=qty,
            expected_price=expected_price,
            max_positions=max_positions,
            max_order_notional_krw=max_order_notional_krw,
            min_price_krw=min_price_krw,
            max_price_krw=max_price_krw,
            now=now,
        )

        if not guard.get("allowed"):
            return self._blocked(db, order, guard)

        # KIS possible-order API may return a smaller executable quantity
        # than the quantity initially calculated from the fixed budget.
        #
        # Example:
        # planned qty = 8
        # KIS orderable qty = 6
        # effective qty = 6
        effective_qty = int(guard.get("effective_quantity") or qty)

        if effective_qty <= 0:
            return self._blocked(
                db,
                order,
                {
                    "allowed": False,
                    "reason": "possible_order_quantity_unavailable",
                    "possible_order": guard.get("possible_order"),
                },
            )

        # Persist the quantity that will actually be sent to KIS.
        # planned_quantity remains available inside guard for observability.
        order.qty = effective_qty
        order.requested_qty = effective_qty
        order.remaining_qty = effective_qty

        current_price = _number(guard.get("current_price"))

        if current_price is not None and current_price > 0:
            order.notional = current_price * effective_qty

        db.flush()

        if authority.get("automation_mode") == "test":
            return self._simulate_market(
                db,
                order=order,
                side="buy",
                symbol=symbol,
                qty=effective_qty,
                now=now,
                guard=guard,
            )

        return self._submit_market(
            db,
            order=order,
            side="buy",
            symbol=symbol,
            qty=effective_qty,
            submitter=submitter or self._broker_buy(symbol, effective_qty),
            now=now,
            guard=guard,
        )

    def submit_market_sell(
        self,
        db: Session,
        *,
        order: OrderLog,
        symbol: str,
        qty: int,
        submitter: Callable[[], dict[str, Any]] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        authority = self._execution_authority(db)

        if authority.get("automation_mode") == "off":
            return self._blocked(
                db,
                order,
                {
                    "allowed": False,
                    "reason": "automation_mode_off",
                    "automation_mode": "off",
                },
            )

        guard = self._sell_jit_guard(
            db,
            order_id=order.id,
            symbol=symbol,
            qty=qty,
        )

        effective_qty = int(guard.get('effective_quantity') or qty)
        if guard.get('allowed') and effective_qty <= 0:
            guard = {
                **guard,
                'allowed': False,
                'reason': 'insufficient_holdings',
            }
        if guard.get('allowed') and effective_qty != int(qty):
            order.qty = effective_qty
            order.requested_qty = effective_qty
            order.remaining_qty = effective_qty
            db.flush()

        if guard.get("allowed") and authority.get("automation_mode") == "test":
            return self._simulate_market(
                db,
                order=order,
                side="sell",
                symbol=symbol,
                qty=effective_qty,
                now=now,
                guard=guard,
            )

        return (
            self._blocked(db, order, guard)
            if not guard.get("allowed")
            else self._submit_market(
                db,
                order=order,
                side="sell",
                symbol=symbol,
                qty=effective_qty,
                submitter=submitter or self._broker_sell(symbol, effective_qty),
                now=now,
                guard=guard,
            )
        )

    def _execution_authority(self, db: Session) -> dict[str, Any]:
        return AutomationExecutionAuthorityService(
            self.runtime_settings
        ).snapshot(db)

        if self.runtime_settings is None:
            try:
                from app.services.runtime_setting_service import (
                    RuntimeSettingService,
                )

                settings = RuntimeSettingService().get_settings_read_only(db)
                return automation_mode_authority(
                    settings.get("automation_mode")
                )
            except Exception:
                return {
                    "automation_mode": "off",
                    "execution_authority": "OFF",
                    "broker_submit_allowed": False,
                    "source_of_truth": "automation_mode",
                    "reason": "automation_mode_unavailable",
                }

        reader = getattr(
            self.runtime_settings,
            "get_automation_execution_authority_read_only",
            None,
        )

        if callable(reader):
            try:
                return dict(reader(db))
            except Exception:
                return {
                    "automation_mode": "off",
                    "execution_authority": "OFF",
                    "broker_submit_allowed": False,
                    "source_of_truth": "automation_mode",
                    "reason": "automation_mode_unavailable",
                }

        try:
            settings = self.runtime_settings.get_settings_read_only(db)

            return automation_mode_authority(
                settings.get("automation_mode")
            )

        except Exception:
            return {
                "automation_mode": "off",
                "execution_authority": "OFF",
                "broker_submit_allowed": False,
                "source_of_truth": "automation_mode",
                "reason": "automation_mode_unavailable",
            }

    def _simulate_market(
        self,
        db: Session,
        *,
        order: OrderLog,
        side: str,
        symbol: str,
        qty: int,
        now: datetime | None,
        guard: dict[str, Any],
    ) -> dict[str, Any]:
        now_utc = _aware_utc(now or self.now_provider())

        fill_price = (
            _number(guard.get("current_price"))
            or _number(getattr(order, "limit_price", None))
            or 0
        )

        simulation_order_id = f"SIM-{side.upper()}-{order.id}"

        order.symbol = order.symbol or symbol
        order.side = order.side or side
        order.qty = order.qty or qty
        order.requested_qty = order.requested_qty or qty
        order.broker_order_id = order.kis_odno = simulation_order_id
        order.broker_status = order.broker_order_status = "simulated_filled"
        order.internal_status = InternalOrderStatus.FILLED.value
        order.submitted_at = now_utc
        order.filled_qty = int(qty)
        order.remaining_qty = 0
        order.avg_fill_price = order.filled_avg_price = fill_price
        order.filled_at = now_utc

        order.response_payload = _json(
            {
                "execution_core": "kis_automation_execution_core",
                "status": "simulated_filled",
                "simulation": True,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "source_metadata": _source_metadata(order),
                "guard": guard,
            }
        )

        db.commit()

        return {
            "status": "filled",
            "submitted": True,
            "simulated": True,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "order_id": order.id,
            "broker_order_id": simulation_order_id,
            "kis_odno": simulation_order_id,
            "broker_status": "simulated_filled",
            "internal_status": order.internal_status,
            "lifecycle": self._reconcile_filled_order(
                db,
                order,
                now=now_utc,
            ),
            "guard": guard,
        }

    def _broker_buy(
        self,
        symbol: str,
        qty: int,
    ) -> Callable[[], dict[str, Any]]:
        if self.broker is None:
            return lambda: {}

        return lambda: self.broker.submit_market_buy(
            symbol=symbol,
            qty=qty,
        )

    def _broker_sell(
        self,
        symbol: str,
        qty: int,
    ) -> Callable[[], dict[str, Any]]:
        if self.broker is None:
            return lambda: {}

        return lambda: self.broker.submit_market_sell(
            symbol=symbol,
            qty=qty,
        )

    def sync_order(
        self,
        db: Session,
        order_id: int,
    ) -> OrderLog:
        if self.order_sync_service is None:
            raise ValueError("kis_order_sync_service_unavailable")

        order = self.order_sync_service.sync_order(
            db,
            int(order_id),
        )

        self._reconcile_filled_order(
            db,
            order,
            now=self.now_provider(),
        )

        return order

    def _blocked(
        self,
        db: Session,
        order: OrderLog,
        guard: dict[str, Any],
    ) -> dict[str, Any]:
        reason = guard.get("reason") or "execution_core_gate_blocked"

        order.internal_status = (
            InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value
        )

        order.error_message = reason

        order.response_payload = _json(
            {
                "execution_core": "kis_automation_execution_core",
                "status": "blocked",
                "reason": reason,
                "source_metadata": _source_metadata(order),
                "guard": guard,
            }
        )

        db.commit()

        return {
            "status": "blocked",
            "reason": reason,
            "submitted": False,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "order_id": order.id,
            "internal_status": order.internal_status,
            "guard": guard,
        }

    def _submit_market(
        self,
        db: Session,
        *,
        order: OrderLog,
        side: str,
        symbol: str,
        qty: int,
        submitter: Callable[[], dict[str, Any]],
        now: datetime | None,
        guard: dict[str, Any],
    ) -> dict[str, Any]:
        authority = self._execution_authority(db)

        if authority.get("automation_mode") != "live":
            reason = (
                "automation_mode_off"
                if authority.get("automation_mode") == "off"
                else "automation_mode_not_live"
            )

            return self._blocked(
                db,
                order,
                {
                    "allowed": False,
                    "reason": reason,
                    "automation_mode": authority.get("automation_mode"),
                    "execution_authority": authority.get(
                        "execution_authority"
                    ),
                },
            )

        now_utc = _aware_utc(now or self.now_provider())

        try:
            response = submitter()

        except Exception as exc:
            error = _error(exc)

            order.internal_status = InternalOrderStatus.UNKNOWN_STALE.value
            order.broker_status = order.broker_order_status = "sync_required"
            order.error_message = error

            order.response_payload = _json(
                {
                    "execution_core": "kis_automation_execution_core",
                    "status": "sync_required",
                    "error": error,
                    "source_metadata": _source_metadata(order),
                    "guard": guard,
                }
            )

            db.commit()

            return {
                "status": "sync_required",
                "reason": "broker_submit_sync_required",
                "error": error,
                "submitted": False,
                "real_order_submitted": False,
                "broker_submit_called": True,
                "manual_submit_called": False,
                "order_id": order.id,
                "internal_status": order.internal_status,
                "guard": guard,
            }

        response = response if isinstance(response, dict) else {}

        broker_id = _broker_order_id(response)

        if not broker_id:
            reason = "broker_order_id_missing"

            order.internal_status = InternalOrderStatus.UNKNOWN_STALE.value
            order.broker_status = order.broker_order_status = "sync_required"
            order.error_message = reason

            order.response_payload = _json(
                {
                    "execution_core": "kis_automation_execution_core",
                    "status": "sync_required",
                    "reason": reason,
                    "source_metadata": _source_metadata(order),
                    "broker_response": response,
                    "guard": guard,
                }
            )

            db.commit()

            return {
                "status": "sync_required",
                "reason": reason,
                "submitted": False,
                "real_order_submitted": False,
                "broker_submit_called": True,
                "manual_submit_called": False,
                "order_id": order.id,
                "internal_status": order.internal_status,
                "guard": guard,
            }

        status = _broker_status(response)
        filled = _filled(status, response)

        order.symbol = order.symbol or symbol
        order.side = order.side or side
        order.qty = order.qty or qty
        order.requested_qty = order.requested_qty or qty

        order.broker_order_id = order.kis_odno = broker_id
        order.broker_status = order.broker_order_status = status

        order.internal_status = (
            InternalOrderStatus.FILLED.value
            if filled
            else InternalOrderStatus.SUBMITTED.value
        )

        order.submitted_at = now_utc

        if filled:
            order.filled_qty = _number(
                response.get("filled_qty")
                or response.get("executed_qty")
                or qty
            )

            fill_price = _number(
                response.get("avg_fill_price")
                or response.get("filled_avg_price")
                or response.get("price")
                or response.get("executed_price")
            )

            if fill_price and fill_price > 0:
                order.avg_fill_price = order.filled_avg_price = fill_price

            order.remaining_qty = 0
            order.filled_at = now_utc

        order.response_payload = _json(
            {
                "execution_core": "kis_automation_execution_core",
                "broker_response": response,
                "source_metadata": _source_metadata(order),
                "guard": guard,
                "real_order_submitted": True,
                "broker_submit_called": True,
            }
        )

        db.commit()

        return {
            "status": "filled" if filled else "submitted",
            "submitted": True,
            "real_order_submitted": True,
            "broker_submit_called": True,
            "manual_submit_called": False,
            "order_id": order.id,
            "broker_order_id": broker_id,
            "kis_odno": order.kis_odno,
            "broker_status": status,
            "internal_status": order.internal_status,
            "broker_response": response,
            "lifecycle": self._reconcile_filled_order(
                db,
                order,
                now=now_utc,
            ),
            "guard": guard,
        }

    def _buy_jit_guard(
        self,
        db: Session,
        *,
        order_id: int | None,
        symbol: str,
        qty: int,
        expected_price: float | None,
        max_positions: int,
        max_order_notional_krw: float | None,
        min_price_krw: float | None,
        max_price_krw: float | None,
        now: datetime | None,
    ) -> dict[str, Any]:
        if self.client is None:
            return {
                "allowed": True,
                "checks": [],
                "current_price": expected_price,
            }

        try:
            positions = self._positions(db)
            open_orders = self._open_orders(db)

        except Exception as exc:
            return {
                "allowed": False,
                "reason": "account_snapshot_unavailable",
                "error": _error(exc),
            }

        active = [
            item
            for item in positions
            if _position_qty(item) > 0
        ]

        if len(active) >= min(
            max(1, int(max_positions or 1)),
            self.HARD_MAX_POSITIONS,
        ):
            return {
                "allowed": False,
                "reason": "max_positions_reached",
            }

        if any(
            _symbol(item) == str(symbol).strip().upper()
            for item in active
        ):
            return {
                "allowed": False,
                "reason": "position_already_exists",
            }

        if _has_open_order(
            open_orders,
            symbol,
            "buy",
        ):
            return {
                "allowed": False,
                "reason": "duplicate_open_order",
            }

        if _has_db_open_order(
            db,
            symbol=symbol,
            side="buy",
            exclude_order_id=order_id,
        ):
            return {
                "allowed": False,
                "reason": "duplicate_open_order",
            }

        price = self._current_price(symbol)

        if not price or price <= 0:
            return {
                "allowed": False,
                "reason": "current_price_unavailable",
            }

        if (
            max_price_krw is not None
            and price > float(max_price_krw)
        ):
            return {
                "allowed": False,
                "reason": "profile_max_price_exceeded",
                "current_price": price,
                "profile_max_price_krw": float(max_price_krw),
            }

        if (
            min_price_krw is not None
            and price < float(min_price_krw)
        ):
            return {
                "allowed": False,
                "reason": "profile_min_price_not_met",
                "current_price": price,
                "profile_min_price_krw": float(min_price_krw),
            }

        possible = self._possible_order(
            symbol,
            price,
        )

        if possible.get("raw_status") != "ok":
            return {
                "allowed": False,
                "reason": "possible_order_unavailable",
                "possible_order": possible,
            }

        queried_at = _parse_datetime(
            possible.get("queried_at")
        )

        if (
            queried_at is None
            or (
                _aware_utc(now or self.now_provider())
                - queried_at
            ).total_seconds()
            > self.POSSIBLE_ORDER_MAX_AGE_SECONDS
        ):
            return {
                "allowed": False,
                "reason": "possible_order_snapshot_stale",
                "possible_order": possible,
            }

        cash = _number(
            possible.get("orderable_cash")
        )

        orderable_qty = _number(
            possible.get("orderable_quantity")
        )

        if cash is None or orderable_qty is None:
            return {
                "allowed": False,
                "reason": "possible_order_unavailable",
                "possible_order": possible,
            }

        planned_qty = int(qty)
        available_qty = int(orderable_qty)

        if planned_qty <= 0:
            return {
                "allowed": False,
                "reason": "possible_order_quantity_unavailable",
                "possible_order": possible,
            }

        if available_qty <= 0:
            return {
                "allowed": False,
                "reason": "possible_order_quantity_unavailable",
                "possible_order": possible,
            }

        # IMPORTANT:
        # Market-order possible quantity returned by KIS is the final
        # executable quantity ceiling.
        #
        # The quantity originally calculated from fixed_budget may be larger.
        #
        # Example:
        # planned_qty = 8
        # available_qty = 6
        # effective_qty = 6
        strategy_budget = _number(max_order_notional_krw)
        if strategy_budget is None or strategy_budget <= 0:
            strategy_budget = self.HARD_MAX_NOTIONAL_KRW
        effective_budget = min(
            max(0.0, strategy_budget),
            max(0.0, cash),
            self.HARD_MAX_NOTIONAL_KRW,
        )
        effective_qty = min(
            planned_qty,
            available_qty,
            max(0, int(effective_budget / price)),
        )
        if effective_qty <= 0:
            return {
                "allowed": False,
                "reason": "possible_order_quantity_unavailable",
                "possible_order": possible,
                "effective_budget_krw": effective_budget,
            }

        cap = min(
            self.HARD_MAX_NOTIONAL_KRW,
            _number(max_order_notional_krw)
            or self.HARD_MAX_NOTIONAL_KRW,
        )

        estimated = price * effective_qty

        if estimated > cash:
            return {
                "allowed": False,
                "reason": "insufficient_cash",
                "possible_order": possible,
            }

        if estimated > cap:
            return {
                "allowed": False,
                "reason": "max_order_notional_exceeded",
                "possible_order": possible,
            }

        return {
            "allowed": True,
            "current_price": price,
            "orderable_cash": cash,
            "strategy_budget_krw": strategy_budget,
            "effective_budget_krw": effective_budget,
            "orderable_quantity": available_qty,
            "planned_quantity": planned_qty,
            "effective_quantity": effective_qty,
            "quantity_adjusted": effective_qty < planned_qty,
            "possible_order": possible,
            "checks": [
                "latest_account_snapshot",
                "latest_price",
                "possible_order_fresh",
                "cash_only",
                "duplicate_protection",
                "orderable_quantity_reconciled",
            ],
        }

    def _sell_jit_guard(
        self,
        db: Session,
        *,
        order_id: int | None,
        symbol: str,
        qty: int,
    ) -> dict[str, Any]:
        if self.client is None:
            return {
                "allowed": True,
                "checks": [],
            }

        try:
            positions = self._positions(db)
            open_orders = self._open_orders(db)

        except Exception as exc:
            return {
                "allowed": False,
                "reason": "account_snapshot_unavailable",
                "error": _error(exc),
            }

        held = next(
            (
                item
                for item in positions
                if _symbol(item)
                == str(symbol).strip().upper()
            ),
            None,
        )
        held_qty = int(_position_qty(held)) if held is not None else 0

        if (
            held is None
            or held_qty <= 0
            or int(qty) <= 0
        ):
            return {
                "allowed": False,
                "reason": "insufficient_holdings",
            }

        if _has_open_order(
            open_orders,
            symbol,
            "sell",
        ):
            return {
                "allowed": False,
                "reason": "duplicate_open_sell_order",
            }

        if _has_db_open_order(
            db,
            symbol=symbol,
            side="sell",
            exclude_order_id=order_id,
        ):
            return {
                "allowed": False,
                "reason": "duplicate_open_sell_order",
            }

        return {
            "allowed": True,
            "held_quantity": held_qty,
            "effective_quantity": min(int(qty), held_qty),
            "quantity_reconciled": min(int(qty), held_qty) != int(qty),
            "checks": [
                "held_position_reconciled",
                "current_broker_quantity",
                "sell_quantity_reconciled",
                "duplicate_protection",
            ],
        }

    def _positions(
        self,
        db: Session,
    ) -> list[dict[str, Any]]:
        values = (
            self.positions_loader(db)
            if self.positions_loader is not None
            else self.client.list_positions()
        )

        return values if isinstance(values, list) else []

    def _open_orders(
        self,
        db: Session,
    ) -> list[dict[str, Any]]:
        values = (
            self.open_orders_loader(db)
            if self.open_orders_loader is not None
            else self.client.list_open_orders()
        )

        return values if isinstance(values, list) else []

    def _current_price(
        self,
        symbol: str,
    ) -> float | None:
        reader = getattr(
            self.client,
            "get_domestic_stock_price",
            None,
        )

        if not callable(reader):
            return None

        payload = reader(symbol)

        if not isinstance(payload, dict):
            return None

        return _number(
            payload.get("current_price")
            or payload.get("price")
            or payload.get("stck_prpr")
        )

    def _possible_order(
        self,
        symbol: str,
        price: float,
    ) -> dict[str, Any]:
        reader = getattr(
            self.client,
            "get_domestic_possible_order",
            None,
        )

        if not callable(reader):
            return {
                "raw_status": "error",
                "error": "possible_order_provider_unavailable",
            }

        payload = reader(
            symbol=symbol,
            order_type="market",
            order_price=price,
            side="buy",
            market="KR",
        )

        if isinstance(payload, dict):
            return payload

        return {
            "raw_status": "error",
            "error": "possible_order_invalid_response",
        }

    def _reconcile_filled_order(
        self,
        db: Session,
        order: OrderLog,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        if (
            str(order.internal_status or "").upper()
            != InternalOrderStatus.FILLED.value
        ):
            return None

        service = self.lifecycle_service

        if service is None:
            try:
                from app.services.kis_position_lifecycle_service import (
                    KisPositionLifecycleService,
                )

                service = KisPositionLifecycleService(
                    self.client,
                    runtime_settings=self.runtime_settings,
                )

            except Exception:
                return None

        try:
            if str(order.side or "").lower() == "buy":
                method = getattr(
                    service,
                    "sync_filled_buy",
                    None,
                )

                return (
                    method(
                        db,
                        order,
                        now=now,
                    )
                    if callable(method)
                    else None
                )

            if str(order.side or "").lower() == "sell":
                method = getattr(
                    service,
                    "sync_filled_sell",
                    None,
                )

                if not callable(method):
                    return None

                return method(
                    db,
                    order,
                    now=now,
                    positions=(
                        self._positions(db)
                        if self.client is not None
                        else None
                    ),
                )

        except TypeError:
            return method(
                db,
                order,
            )

        except Exception as exc:
            return {
                "closed": False,
                "reason": "lifecycle_reconciliation_failed",
                "error": _error(exc),
            }

        return None



def _broker_order_id(payload: dict[str, Any]) -> str | None:
    for key in (
        "broker_order_id",
        "kis_odno",
        "odno",
        "order_id",
        "ODNO",
    ):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    output = payload.get("output")

    if isinstance(output, dict):
        for key in (
            "broker_order_id",
            "kis_odno",
            "odno",
            "order_id",
            "ODNO",
        ):
            value = output.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()

    return None


def _broker_status(
    payload: dict[str, Any],
) -> str:
    return str(
        payload.get("broker_status")
        or payload.get("broker_order_status")
        or payload.get("status")
        or "submitted"
    ).strip().lower()


def _filled(
    status: str,
    payload: dict[str, Any],
) -> bool:
    return (
        str(status).lower()
        in {
            "filled",
            "executed",
            "완료",
            "체결",
        }
        or payload.get("filled") is True
        or payload.get("is_filled") is True
    )


def _symbol(
    value: dict[str, Any],
) -> str:
    return str(
        value.get("symbol")
        or value.get("pdno")
        or ""
    ).strip().upper()


def _position_qty(
    value: dict[str, Any],
) -> float:
    return (
        _number(
            value.get("qty")
            or value.get("quantity")
            or value.get("hold_qty")
            or value.get("hldg_qty")
        )
        or 0.0
    )


def _has_open_order(
    values: list[dict[str, Any]],
    symbol: str,
    side: str,
) -> bool:
    normalized = str(
        symbol or ""
    ).strip().upper()

    for item in values:
        if _symbol(item) != normalized:
            continue

        item_side = str(
            item.get("side")
            or item.get("order_side")
            or item.get("sll_buy_dvsn_cd_name")
            or ""
        ).lower()

        if (
            not item_side
            or side in item_side
            or (
                side == "buy"
                and "매수" in item_side
            )
            or (
                side == "sell"
                and "매도" in item_side
            )
        ):
            return True

    return False


def _has_db_open_order(
    db: Session,
    *,
    symbol: str,
    side: str,
    exclude_order_id: int | None = None,
) -> bool:
    query = (
        db.query(OrderLog.id)
        .filter(
            OrderLog.broker == "kis"
        )
        .filter(
            func.upper(OrderLog.symbol)
            == str(symbol or "").strip().upper()
        )
        .filter(
            func.lower(OrderLog.side)
            == str(side or "").strip().lower()
        )
        .filter(
            OrderLog.internal_status.in_(
                sorted(
                    KisAutomationExecutionCore.OPEN_ORDER_INTERNAL_STATUSES
                )
            )
        )
    )

    if exclude_order_id is not None:
        query = query.filter(
            OrderLog.id != int(exclude_order_id)
        )

    return query.first() is not None


def _number(
    value: Any,
) -> float | None:
    if (
        value is None
        or (
            isinstance(value, str)
            and not value.strip()
        )
    ):
        return None

    try:
        return float(
            str(value)
            .replace(",", "")
            .strip()
        )

    except (TypeError, ValueError):
        return None


def _int(
    value: Any,
) -> int | None:
    try:
        return (
            int(value)
            if value is not None
            else None
        )

    except (TypeError, ValueError):
        return None


def _parse_datetime(
    value: Any,
) -> datetime | None:
    if isinstance(value, datetime):
        return _aware_utc(value)

    if not value:
        return None

    try:
        return _aware_utc(
            datetime.fromisoformat(
                str(value).replace(
                    "Z",
                    "+00:00",
                )
            )
        )

    except (TypeError, ValueError):
        return None


def _aware_utc(
    value: datetime,
) -> datetime:
    return (
        value.replace(tzinfo=UTC)
        if value.tzinfo is None
        else value.astimezone(UTC)
    )


def _error(
    exc: Exception,
) -> str:
    return (
        f"{exc.__class__.__name__}: {exc}"
    )


def _json(
    value: Any,
) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        default=str,
    )


def _source_metadata(
    order: OrderLog,
) -> dict[str, Any]:
    try:
        payload = json.loads(
            order.request_payload or "{}"
        )

    except (TypeError, ValueError):
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    keys = (
        "source",
        "source_type",
        "mode",
        "trigger_source",
        "automation_profile",
        "automation_profile_key",
        "profile_key",
    )

    return {
        key: payload[key]
        for key in keys
        if key in payload
    }
