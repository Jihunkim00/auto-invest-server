from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient, to_float
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, StrategyLiveAutoExitAttempt
from app.schemas.position_exit_review import (
    GuardedPositionSellRequest,
    PositionSellPreflightRequest,
)
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
from app.services.kis_order_validation_service import (
    KisOrderValidationRequest,
    KisOrderValidationService,
    record_kis_order_validation,
)
from app.services.kis_order_sync_service import (
    KisOrderSyncService,
    serialize_kis_order,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService


GUARDED_SELL_MODE = "guarded_position_sell"
GUARDED_SELL_TRIGGER_SOURCE = "manual_guarded_position_sell"


class PositionExitReviewService:
    """Read-only held-position review and guarded sell preflight."""

    def __init__(
        self,
        client: KisClient,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
        manual_order_service: KisManualOrderService | None = None,
        validation_service: KisOrderValidationService | None = None,
        order_sync_service: KisOrderSyncService | None = None,
    ):
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()
        self.manual_order_service = manual_order_service or KisManualOrderService(
            client,
            runtime_settings=self.runtime_settings,
            session_service=self.session_service,
        )
        self.validation_service = validation_service or KisOrderValidationService(
            client,
            session_service=self.session_service,
        )
        self.order_sync_service = order_sync_service or KisOrderSyncService(client)

    def exit_review(self, db: Session) -> dict[str, Any]:
        snapshot = self._snapshot(db)
        positions = [
            self._review_position(db, item, snapshot=snapshot)
            for item in snapshot["positions"]
        ]
        total_value = round(
            sum(_safe_float(item.get("current_value"), 0.0) for item in positions),
            2,
        )
        total_pl = round(
            sum(_safe_float(item.get("unrealized_pl"), 0.0) for item in positions),
            2,
        )
        total_cost = sum(_safe_float(item.get("cost_basis"), 0.0) for item in positions)
        total_pl_pct = round(total_pl / total_cost, 6) if total_cost > 0 else None
        read_errors = _read_errors(snapshot)

        return sanitize_kis_payload(
            {
                "provider": PROVIDER,
                "market": MARKET,
                "positions": positions,
                "total_position_value": total_value,
                "total_unrealized_pl": total_pl,
                "total_unrealized_pl_pct": total_pl_pct,
                "updated_at": snapshot["updated_at"],
                "dry_run": snapshot["dry_run"],
                "kill_switch": snapshot["kill_switch"],
                "kis_real_order_enabled": snapshot["kis_real_order_enabled"],
                "market_session_allowed": snapshot["market_session_allowed"],
                "safety_flags": [
                    "read_only",
                    "preflight_only",
                    "no_live_order_submitted",
                    "no_broker_submit",
                    "final_confirmation_required",
                    *read_errors,
                ],
                "safety": _safety(
                    broker_read_available=not read_errors,
                    read_errors=read_errors,
                ),
            }
        )

    def sell_preflight(
        self,
        db: Session,
        *,
        symbol: str,
        request: PositionSellPreflightRequest,
    ) -> dict[str, Any]:
        normalized_symbol = _normalize_symbol(symbol)
        snapshot = self._snapshot(db)
        position = self._position_by_symbol(snapshot["positions"], normalized_symbol)
        position_exists = position is not None
        review = self._review_position(db, position or {}, snapshot=snapshot)
        quantity = _safe_float_or_none(review.get("quantity")) if position_exists else None
        available = (
            _safe_float_or_none(review.get("available_quantity"))
            if position_exists
            else None
        )
        requested = self._requested_quantity(
            request=request,
            available_quantity=available,
        )
        current_price = _safe_float_or_none(review.get("current_price"))
        estimated = _notional(requested, current_price)
        duplicate_sell = bool(review.get("duplicate_open_sell_order"))
        read_errors = _read_errors(snapshot)
        stop_loss = bool(review.get("stop_loss_triggered"))
        take_profit = bool(review.get("take_profit_triggered"))
        exit_context = stop_loss or take_profit

        checks: list[dict[str, Any]] = []

        def check(
            key: str,
            status: str,
            detail: str,
            *,
            blocking: bool = False,
        ) -> None:
            checks.append(
                {
                    "key": key,
                    "status": status,
                    "label_key": key,
                    "detail": detail,
                    "blocking": blocking,
                }
            )

        check(
            "position_exists",
            "pass" if position_exists else "fail",
            "Held position was found." if position_exists else "No held position was found.",
            blocking=True,
        )
        check(
            "available_quantity_positive",
            "pass" if available is not None and available > 0 else "fail",
            f"Available quantity is {available or 0}.",
            blocking=True,
        )
        requested_valid = (
            requested is not None
            and requested > 0
            and available is not None
            and requested <= available
        )
        check(
            "requested_quantity_valid",
            "pass" if requested_valid else "fail",
            f"Requested quantity is {requested or 0}; available quantity is {available or 0}.",
            blocking=True,
        )
        check(
            "final_confirmation_required",
            "pass",
            "Final operator confirmation remains required before any live sell.",
        )
        check(
            "kill_switch_off",
            "pass" if not snapshot["kill_switch"] else "fail",
            "Kill switch is off." if not snapshot["kill_switch"] else "Kill switch is enabled.",
            blocking=True,
        )
        check(
            "market_session_allowed",
            "pass" if snapshot["market_session_allowed"] else "fail",
            "Market session allows exit review."
            if snapshot["market_session_allowed"]
            else "Market is closed or unavailable.",
            blocking=True,
        )
        check(
            "broker_read_available",
            "pass" if not read_errors else "fail",
            "Broker position and open-order reads completed."
            if not read_errors
            else f"Broker read warnings: {', '.join(read_errors)}.",
            blocking=True,
        )
        cost_basis_available = review.get("cost_basis") is not None
        check(
            "cost_basis_available",
            "pass" if cost_basis_available else "warn",
            "Cost basis is available."
            if cost_basis_available
            else "Cost basis is unavailable; P/L percent needs manual review.",
        )
        pl_safe = review.get("unrealized_pl") is not None and (
            review.get("cost_basis") is not None or review.get("current_value") is not None
        )
        check(
            "pl_calculation_safe",
            "pass" if pl_safe else "warn",
            "P/L was calculated from cost basis/current value."
            if pl_safe
            else "P/L inputs are missing or incomplete.",
        )
        check(
            "duplicate_sell_order_check",
            "fail" if duplicate_sell else "pass",
            "Open sell order already exists."
            if duplicate_sell
            else "No duplicate open sell order was found.",
            blocking=True,
        )
        check(
            "open_order_conflict_check",
            "fail" if duplicate_sell else "pass",
            "Open sell order conflicts with this preflight."
            if duplicate_sell
            else "No open-order conflict was found.",
            blocking=True,
        )
        check(
            "stop_loss_or_take_profit_context",
            "pass" if exit_context else "warn",
            "Stop-loss or take-profit context is present."
            if exit_context
            else "No stop-loss or take-profit trigger was detected.",
        )
        check(
            "manual_review_required",
            "warn" if not exit_context else "pass",
            "Manual review is required before final confirmation."
            if not exit_context
            else "Exit trigger context is present for operator review.",
        )

        if snapshot["dry_run"]:
            _set_check_failed(
                checks,
                "dry_run_off_for_live_submit",
                "Runtime dry_run is enabled.",
            )
        else:
            checks.append(
                {
                    "key": "dry_run_off_for_live_submit",
                    "status": "pass",
                    "label_key": "dry_run_off_for_live_submit",
                    "detail": "Runtime dry_run is off.",
                    "blocking": False,
                }
            )

        if not snapshot["kis_real_order_enabled"]:
            _set_check_failed(
                checks,
                "kis_real_orders_enabled",
                "KIS real order setting is disabled.",
            )
        else:
            checks.append(
                {
                    "key": "kis_real_orders_enabled",
                    "status": "pass",
                    "label_key": "kis_real_orders_enabled",
                    "detail": "KIS real order setting is enabled.",
                    "blocking": False,
                }
            )

        checks.append(
            {
                "key": "no_new_entry_window_allowed",
                "status": "pass",
                "label_key": "no_new_entry_window_allowed",
                "detail": "No-new-entry window does not block risk-reducing exit preflight.",
                "blocking": False,
            }
        )

        explicit_blockers = _dedupe(
            [
                "no_held_position" if not position_exists else "",
                "no_available_quantity" if position_exists and (available or 0) <= 0 else "",
                "requested_quantity_invalid" if position_exists and not requested_valid else "",
                "kill_switch_enabled" if snapshot["kill_switch"] else "",
                "market_closed" if not snapshot["market_session_allowed"] else "",
                "runtime_dry_run_true" if snapshot["dry_run"] else "",
                "kis_real_order_enabled_false"
                if not snapshot["kis_real_order_enabled"]
                else "",
                "duplicate_open_sell_order" if duplicate_sell else "",
                *read_errors,
            ]
        )
        explicit_blockers = [item for item in explicit_blockers if item]

        if explicit_blockers:
            status = "blocked"
        elif not exit_context:
            status = "review_required"
        else:
            status = "allowed"

        primary_block = explicit_blockers[0] if explicit_blockers else None
        risk_flags = _dedupe(
            [
                "preflight_only",
                "no_live_order_submitted",
                *review.get("risk_flags", []),
                *explicit_blockers,
            ]
        )
        gating_notes = _dedupe(
            [
                "Sell preflight is read-only; no live sell order was created.",
                "Final confirmation is required before any manual live sell.",
                "No-new-entry window is not treated as an exit blocker.",
                *review.get("gating_notes", []),
            ]
        )

        return sanitize_kis_payload(
            {
                "symbol": normalized_symbol,
                "provider": PROVIDER,
                "market": MARKET,
                "preflight_status": status,
                "can_submit_after_confirmation": status == "allowed",
                "final_confirmation_required": True,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "order_id": None,
                "broker_order_id": None,
                "kis_odno": None,
                "position_exists": position_exists,
                "quantity_held": quantity,
                "available_quantity": available,
                "requested_quantity": requested,
                "estimated_sell_notional": estimated,
                "current_price": current_price,
                "average_price": review.get("average_price"),
                "cost_basis": review.get("cost_basis"),
                "current_value": review.get("current_value"),
                "unrealized_pl": review.get("unrealized_pl"),
                "unrealized_pl_pct": review.get("unrealized_pl_pct"),
                "stop_loss_threshold_pct": review.get("stop_loss_threshold_pct"),
                "take_profit_threshold_pct": review.get("take_profit_threshold_pct"),
                "stop_loss_triggered": stop_loss,
                "take_profit_triggered": take_profit,
                "kill_switch": snapshot["kill_switch"],
                "dry_run": snapshot["dry_run"],
                "kis_real_order_enabled": snapshot["kis_real_order_enabled"],
                "market_session_allowed": snapshot["market_session_allowed"],
                "no_new_entry_window_allowed": True,
                "risk_flags": risk_flags,
                "gating_notes": gating_notes,
                "checklist": checks,
                "primary_block_reason": primary_block,
                "next_required_action": _next_required_action(
                    status=status,
                    primary_block=primary_block,
                ),
                "safety": _safety(
                    broker_read_available=not read_errors,
                    read_errors=read_errors,
                ),
                "updated_at": snapshot["updated_at"],
            }
        )

    def guarded_sell(
        self,
        db: Session,
        *,
        symbol: str,
        request: GuardedPositionSellRequest,
    ) -> dict[str, Any]:
        normalized_symbol = _normalize_symbol(symbol)
        existing = self._idempotent_guarded_sell_attempt(db, request)
        if existing is not None:
            return self._guarded_sell_result_from_attempt(existing, idempotent_replay=True)

        context = self._guarded_sell_context(
            db,
            symbol=normalized_symbol,
            request=request,
        )
        blockers = list(context["hard_blockers"])
        if blockers:
            response = self._guarded_sell_response(
                context=context,
                request=request,
                result_status="blocked",
                primary_block_reason=blockers[0],
            )
            attempt = self._save_guarded_sell_attempt(
                db,
                request=request,
                context=context,
                response=response,
            )
            response["attempt_id"] = attempt.id
            attempt.response_payload = _json(response)
            db.commit()
            return sanitize_kis_payload(response)

        if context["dry_run"]:
            response = self._guarded_sell_response(
                context=context,
                request=request,
                result_status="dry_run_simulated",
                primary_block_reason="dry_run_enabled",
                risk_flags=["dry_run_enabled"],
                gating_notes=[
                    "Runtime dry_run is enabled; no broker submit was called.",
                ],
            )
            attempt = self._save_guarded_sell_attempt(
                db,
                request=request,
                context=context,
                response=response,
            )
            response["attempt_id"] = attempt.id
            attempt.response_payload = _json(response)
            db.commit()
            return sanitize_kis_payload(response)

        validation = self._validate_guarded_sell(db, context=context, request=request)
        if validation.get("validated_for_submission") is not True:
            reason = str(
                validation.get("primary_block_reason")
                or (validation.get("block_reasons") or ["validation_failed"])[0]
            )
            response = self._guarded_sell_response(
                context=context,
                request=request,
                result_status="blocked",
                primary_block_reason=reason,
                risk_flags=[reason, *_string_list(validation.get("warnings"))],
                gating_notes=_string_list(validation.get("block_reasons")),
                safety_overrides={"validation_called": True},
            )
            attempt = self._save_guarded_sell_attempt(
                db,
                request=request,
                context=context,
                response=response,
                validation=validation,
            )
            response["attempt_id"] = attempt.id
            attempt.response_payload = _json(response)
            db.commit()
            return sanitize_kis_payload(response)

        manual_request = KisManualOrderSubmitRequest(
            market=MARKET,
            symbol=normalized_symbol,
            side=SELL,
            qty=int(context["requested_quantity"]),
            order_type="market",
            dry_run=False,
            confirm_live=True,
            confirmation=_kis_confirmation_phrase(self.client),
            reason=request.reason or "manual guarded position sell",
            source_context=GUARDED_SELL_MODE,
            source_metadata=_guarded_sell_source_metadata(
                request=request,
                context=context,
                validation=validation,
            ),
        )
        status_code, manual_body = self.manual_order_service.submit_manual(
            db,
            manual_request,
        )
        order_id = _safe_int_or_none(
            manual_body.get("order_id") or manual_body.get("order_log_id")
        )
        order = db.get(OrderLog, order_id) if order_id is not None else None
        result_status = _manual_submit_result_status(
            status_code=status_code,
            body=manual_body,
            order=order,
        )
        response = self._guarded_sell_response(
            context=context,
            request=request,
            result_status=result_status,
            primary_block_reason=(
                None
                if result_status in {"submitted", "filled", "pending_sync"}
                else _manual_primary_block_reason(manual_body)
            ),
            real_order_submitted=manual_body.get("real_order_submitted") is True,
            broker_submit_called=_manual_bool(manual_body, "broker_submit_called"),
            manual_submit_called=True,
            order=order,
            manual_body=manual_body,
            safety_overrides={"validation_called": True},
        )
        attempt = self._save_guarded_sell_attempt(
            db,
            request=request,
            context=context,
            response=response,
            validation=validation,
            related_order_id=order_id,
        )
        response["attempt_id"] = attempt.id
        attempt.response_payload = _json(response)
        db.commit()
        return sanitize_kis_payload(response)

    def guarded_sell_result(self, db: Session, attempt_id: int) -> dict[str, Any]:
        attempt = self._guarded_sell_attempt(db, attempt_id)
        return self._guarded_sell_result_from_attempt(attempt)

    def sync_guarded_sell_result(self, db: Session, attempt_id: int) -> dict[str, Any]:
        attempt = self._guarded_sell_attempt(db, attempt_id)
        if attempt.related_order_id:
            order = self.order_sync_service.sync_order(db, int(attempt.related_order_id))
            response = self._guarded_sell_result_from_attempt(
                attempt,
                order=order,
                sync_only=True,
            )
            attempt.status = response["result_status"]
            attempt.broker_order_id = response.get("broker_order_id")
            attempt.synced_at = datetime.now(UTC)
            attempt.response_payload = _json(response)
            db.commit()
            db.refresh(attempt)
            return sanitize_kis_payload(response)
        response = self._guarded_sell_result_from_attempt(attempt, sync_only=True)
        return sanitize_kis_payload(response)

    def _snapshot(self, db: Session) -> dict[str, Any]:
        runtime = self.runtime_settings.get_settings(db)
        settings = self.client.settings
        positions, positions_error = self._read_positions()
        open_orders, open_orders_error = self._read_open_orders()
        recent_orders, recent_orders_error = self._read_recent_orders(db)
        market_session = self._market_session()

        return {
            "positions": positions,
            "open_orders": open_orders,
            "recent_orders": recent_orders,
            "positions_error": positions_error,
            "open_orders_error": open_orders_error,
            "recent_orders_error": recent_orders_error,
            "market_session": market_session,
            "market_session_allowed": market_session.get("is_market_open") is True,
            "dry_run": bool(runtime.get("dry_run", True)),
            "kill_switch": bool(runtime.get("kill_switch", False)),
            "kis_enabled": bool(getattr(settings, "kis_enabled", False)),
            "kis_real_order_enabled": bool(
                getattr(settings, "kis_real_order_enabled", False)
            ),
            "updated_at": datetime.now(UTC).isoformat(),
        }

    def _read_positions(self) -> tuple[list[dict[str, Any]], str | None]:
        try:
            positions = [
                _normalize_position(item)
                for item in self.client.list_positions()
                if isinstance(item, dict)
            ]
        except Exception as exc:
            return [], f"positions_unavailable:{exc.__class__.__name__}"
        held = [item for item in positions if _safe_float(item.get("qty"), 0.0) > 0]
        held.sort(key=lambda item: str(item.get("symbol") or ""))
        return held, None

    def _read_open_orders(self) -> tuple[list[dict[str, Any]], str | None]:
        try:
            orders = [
                _normalize_order(item)
                for item in self.client.list_open_orders()
                if isinstance(item, dict)
            ]
        except Exception as exc:
            return [], f"open_orders_unavailable:{exc.__class__.__name__}"
        return orders, None

    def _read_recent_orders(self, db: Session) -> tuple[list[dict[str, Any]], str | None]:
        try:
            rows = KisOrderSyncService.recent_orders(db, limit=50, include_rejected=True)
            return [serialize_kis_order(row) for row in rows], None
        except Exception as exc:
            return [], f"recent_orders_unavailable:{exc.__class__.__name__}"

    def _market_session(self) -> dict[str, Any]:
        try:
            return self.session_service.get_session_status(MARKET)
        except Exception as exc:
            return {
                "market": MARKET,
                "is_market_open": False,
                "is_entry_allowed_now": False,
                "error": f"{exc.__class__.__name__}: {str(exc)[:120]}",
            }

    def _review_position(
        self,
        db: Session,
        raw: dict[str, Any],
        *,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        position = _normalize_position(raw)
        symbol = str(position.get("symbol") or "").upper()
        diagnostics = position_pl_diagnostics(position)
        reasons, diagnostics = position_exit_threshold_reasons(position)
        stop_loss = "stop_loss_triggered" in reasons
        take_profit = "take_profit_triggered" in reasons
        duplicate_sell = _has_duplicate_open_sell(
            db,
            symbol=symbol,
            open_orders=snapshot["open_orders"],
            recent_orders=snapshot["recent_orders"],
        )
        quantity = _safe_float_or_none(position.get("qty"))
        available = _available_quantity(position, fallback=quantity)
        risk_flags = _dedupe(
            [
                *reasons,
                diagnostics.get("pl_input_warning") or "",
                "duplicate_open_sell_order" if duplicate_sell else "",
                "no_available_quantity"
                if available is not None and available <= 0
                else "",
            ]
        )
        if not risk_flags:
            risk_flags = ["no_exit_condition"]
        latest_buy = _latest_buy_order(db, symbol=symbol)
        status = _exit_review_status(
            duplicate_sell=duplicate_sell,
            available_quantity=available,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        return {
            "symbol": symbol,
            "name": _name_value(position),
            "provider": PROVIDER,
            "market": MARKET,
            "quantity": quantity,
            "available_quantity": available,
            "average_price": _safe_float_or_none(position.get("avg_entry_price")),
            "cost_basis": diagnostics.get("cost_basis"),
            "current_price": _safe_float_or_none(position.get("current_price")),
            "current_value": diagnostics.get("current_value"),
            "unrealized_pl": diagnostics.get("unrealized_pl"),
            "unrealized_pl_pct": diagnostics.get("unrealized_pl_pct"),
            "day_pl": _first_float(position, "day_pl", "daily_pl", "today_pl"),
            "entry_source": position.get("entry_source")
            or _entry_source_from_order(latest_buy),
            "related_buy_order_id": _order_id(latest_buy),
            "related_promotion_id": _promotion_id_from_order(latest_buy),
            "stop_loss_threshold_pct": diagnostics.get("stop_loss_threshold_pct"),
            "take_profit_threshold_pct": diagnostics.get("take_profit_threshold_pct"),
            "stop_loss_triggered": stop_loss,
            "take_profit_triggered": take_profit,
            "duplicate_open_sell_order": duplicate_sell,
            "exit_review_status": status,
            "primary_risk_note": _primary_risk_note(
                status=status,
                reasons=risk_flags,
                diagnostics=diagnostics,
            ),
            "risk_flags": risk_flags,
            "gating_notes": _review_gating_notes(
                status=status,
                duplicate_sell=duplicate_sell,
                available_quantity=available,
            ),
            "next_safe_action": _next_safe_review_action(status),
        }

    def _position_by_symbol(
        self,
        positions: list[dict[str, Any]],
        symbol: str,
    ) -> dict[str, Any] | None:
        for item in positions:
            if str(item.get("symbol") or "").strip().upper() == symbol:
                return item
        return None

    def _requested_quantity(
        self,
        *,
        request: PositionSellPreflightRequest,
        available_quantity: float | None,
    ) -> float | None:
        if available_quantity is None:
            return None
        if request.quantity_mode == "partial":
            return request.quantity
        return available_quantity

    def _guarded_sell_context(
        self,
        db: Session,
        *,
        symbol: str,
        request: GuardedPositionSellRequest,
    ) -> dict[str, Any]:
        provider = str(request.provider or "").strip().lower()
        market = str(request.market or "").strip().upper()
        request_symbol = _normalize_symbol(request.symbol) if request.symbol else symbol
        quantity_mode = str(request.quantity_mode or "").strip().lower()
        snapshot = self._snapshot(db)
        position = self._position_by_symbol(snapshot["positions"], symbol)
        position_exists = position is not None
        review = self._review_position(db, position or {}, snapshot=snapshot)
        held = _safe_float_or_none(review.get("quantity")) if position_exists else None
        available = (
            _safe_float_or_none(review.get("available_quantity"))
            if position_exists
            else None
        )
        requested = _guarded_requested_quantity(
            quantity_mode=quantity_mode,
            quantity=request.quantity,
            available_quantity=available,
        )
        current_price = _safe_float_or_none(review.get("current_price"))
        estimated = _notional(requested, current_price)
        duplicate_sell = bool(review.get("duplicate_open_sell_order"))
        read_errors = _read_errors(snapshot)
        stop_loss = bool(review.get("stop_loss_triggered"))
        take_profit = bool(review.get("take_profit_triggered"))
        manual_review_complete = stop_loss or take_profit
        quantity_mode_valid = quantity_mode in {"full", "partial"}
        requested_valid = _guarded_quantity_valid(
            requested_quantity=requested,
            available_quantity=available,
        )
        provider_ok = provider == PROVIDER
        market_ok = market == MARKET
        symbol_ok = request_symbol == symbol

        checklist: list[dict[str, Any]] = []

        def check(key: str, ok: bool, detail: str, *, blocking: bool = True) -> None:
            checklist.append(
                {
                    "key": key,
                    "status": "pass" if ok else "fail",
                    "label_key": key,
                    "detail": detail,
                    "blocking": bool(blocking and not ok),
                }
            )

        check(
            "position_exists",
            position_exists,
            "Held position was found." if position_exists else "No held position was found.",
        )
        check(
            "available_quantity_positive",
            available is not None and available > 0,
            f"Available quantity is {available or 0}.",
        )
        check(
            "requested_quantity_valid",
            quantity_mode_valid and requested_valid,
            (
                f"Requested quantity is {requested or request.quantity or 0}; "
                f"available quantity is {available or 0}."
            ),
        )
        check(
            "final_confirmation_received",
            request.confirm_live is True,
            "Final confirmation was received."
            if request.confirm_live is True
            else "Final live-sell confirmation is required.",
        )
        check(
            "kill_switch_off",
            not snapshot["kill_switch"],
            "Kill switch is off." if not snapshot["kill_switch"] else "Kill switch is enabled.",
        )
        check(
            "dry_run_allows_live_submit",
            not snapshot["dry_run"],
            "Runtime dry_run is off."
            if not snapshot["dry_run"]
            else "Runtime dry_run is enabled; live submit is not allowed.",
        )
        check(
            "kis_real_orders_enabled",
            bool(snapshot["kis_real_order_enabled"]),
            "KIS real-order setting is enabled."
            if snapshot["kis_real_order_enabled"]
            else "KIS real-order setting is disabled.",
        )
        check(
            "market_session_allowed",
            bool(snapshot["market_session_allowed"]),
            "Market session allows sell execution."
            if snapshot["market_session_allowed"]
            else "Market session blocks sell execution.",
        )
        check(
            "duplicate_sell_order_check",
            not duplicate_sell,
            "No duplicate open sell order was found."
            if not duplicate_sell
            else "Open sell order already exists.",
        )
        check(
            "open_order_conflict_check",
            not duplicate_sell,
            "No open-order conflict was found."
            if not duplicate_sell
            else "Open sell order conflicts with this request.",
        )
        broker_submit_ready = (
            provider_ok
            and market_ok
            and symbol_ok
            and position_exists
            and quantity_mode_valid
            and requested_valid
            and request.confirm_live is True
            and not snapshot["kill_switch"]
            and not snapshot["dry_run"]
            and bool(snapshot["kis_real_order_enabled"])
            and bool(snapshot["market_session_allowed"])
            and not duplicate_sell
            and not read_errors
            and manual_review_complete
        )
        check(
            "broker_submit_ready",
            broker_submit_ready,
            "Broker submit path is ready."
            if broker_submit_ready
            else "Broker submit path is not ready.",
        )
        check(
            "manual_review_complete",
            manual_review_complete,
            "Sell preflight exit context is complete."
            if manual_review_complete
            else "Sell preflight requires stop-loss or take-profit review context.",
        )
        if read_errors:
            checklist.append(
                {
                    "key": "broker_read_available",
                    "status": "fail",
                    "label_key": "broker_read_available",
                    "detail": f"Broker read warnings: {', '.join(read_errors)}.",
                    "blocking": True,
                }
            )

        hard_blockers = _dedupe(
            [
                "provider_not_supported" if not provider_ok else "",
                "market_not_supported" if not market_ok else "",
                "request_symbol_mismatch" if not symbol_ok else "",
                "no_held_position" if not position_exists else "",
                "no_available_quantity"
                if position_exists and (available is None or available <= 0)
                else "",
                "quantity_mode_invalid" if not quantity_mode_valid else "",
                "requested_quantity_invalid"
                if position_exists and quantity_mode_valid and not requested_valid
                else "",
                "confirm_live_required" if request.confirm_live is not True else "",
                "kill_switch_enabled" if snapshot["kill_switch"] else "",
                "kis_real_order_enabled_false"
                if not snapshot["kis_real_order_enabled"]
                else "",
                "market_closed" if not snapshot["market_session_allowed"] else "",
                "duplicate_open_sell_order" if duplicate_sell else "",
                "manual_review_required" if not manual_review_complete else "",
                *read_errors,
            ]
        )
        risk_flags = _dedupe(
            [
                *review.get("risk_flags", []),
                *hard_blockers,
                "dry_run_enabled" if snapshot["dry_run"] else "",
            ]
        )
        gating_notes = _dedupe(
            [
                "Guarded sell revalidated PR85 sell preflight at submit time.",
                "Final operator confirmation is required for guarded live sell.",
                "No scheduler, retry, or background sell path is used.",
                "Runtime dry_run is enabled; no broker submit will be called."
                if snapshot["dry_run"]
                else "",
                *review.get("gating_notes", []),
                *hard_blockers,
            ]
        )
        return {
            "symbol": symbol,
            "request_symbol": request_symbol,
            "provider": provider or PROVIDER,
            "market": market or MARKET,
            "quantity_mode": quantity_mode,
            "quantity_mode_valid": quantity_mode_valid,
            "position_exists": position_exists,
            "quantity_held": held,
            "available_quantity": available,
            "requested_quantity": requested,
            "estimated_sell_notional": estimated,
            "current_price": current_price,
            "average_price": review.get("average_price"),
            "cost_basis": review.get("cost_basis"),
            "current_value": review.get("current_value"),
            "unrealized_pl": review.get("unrealized_pl"),
            "unrealized_pl_pct": review.get("unrealized_pl_pct"),
            "stop_loss_triggered": stop_loss,
            "take_profit_triggered": take_profit,
            "kill_switch": snapshot["kill_switch"],
            "dry_run": snapshot["dry_run"],
            "kis_real_order_enabled": snapshot["kis_real_order_enabled"],
            "market_session_allowed": snapshot["market_session_allowed"],
            "duplicate_sell": duplicate_sell,
            "checklist": checklist,
            "risk_flags": risk_flags,
            "gating_notes": gating_notes,
            "hard_blockers": hard_blockers,
            "updated_at": snapshot["updated_at"],
        }

    def _validate_guarded_sell(
        self,
        db: Session,
        *,
        context: dict[str, Any],
        request: GuardedPositionSellRequest,
    ) -> dict[str, Any]:
        validation_request = KisOrderValidationRequest(
            market=MARKET,
            symbol=str(context["symbol"]),
            side=SELL,
            qty=int(context["requested_quantity"]),
            order_type="market",
            dry_run=True,
            reason=request.reason or "guarded manual position sell validation",
            source_metadata=_guarded_sell_source_metadata(
                request=request,
                context=context,
            ),
        )
        try:
            validation_result = self.validation_service.validate(validation_request)
        except Exception as exc:
            return {
                "validated_for_submission": False,
                "primary_block_reason": "validation_unavailable",
                "block_reasons": ["validation_unavailable"],
                "warnings": [_safe_error(exc)],
            }
        record_kis_order_validation(
            db,
            request=validation_request,
            result=validation_result,
        )
        return sanitize_kis_payload(validation_result.to_dict())

    def _guarded_sell_response(
        self,
        *,
        context: dict[str, Any],
        request: GuardedPositionSellRequest,
        result_status: str,
        primary_block_reason: str | None,
        real_order_submitted: bool = False,
        broker_submit_called: bool = False,
        manual_submit_called: bool = False,
        order: OrderLog | None = None,
        manual_body: dict[str, Any] | None = None,
        risk_flags: list[str] | None = None,
        gating_notes: list[str] | None = None,
        safety_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        order_id = order.id if order is not None else _safe_int_or_none((manual_body or {}).get("order_id"))
        broker_order_id = (
            order.broker_order_id
            if order is not None
            else _string_or_none((manual_body or {}).get("broker_order_id"))
        )
        kis_odno = (
            (order.kis_odno or order.broker_order_id)
            if order is not None
            else _string_or_none((manual_body or {}).get("kis_odno"))
            or broker_order_id
        )
        submitted_at = order.submitted_at if order is not None else None
        last_synced_at = order.last_synced_at if order is not None else None
        submitted_quantity = (
            _safe_float_or_none(order.requested_qty or order.qty)
            if order is not None and real_order_submitted
            else (
                context.get("requested_quantity")
                if result_status in {"submitted", "filled"}
                else None
            )
        )
        merged_risk_flags = _dedupe(
            [
                *context.get("risk_flags", []),
                *(risk_flags or []),
                *(_string_list((manual_body or {}).get("block_reasons"))),
                primary_block_reason or "",
            ]
        )
        merged_gating_notes = _dedupe(
            [
                *context.get("gating_notes", []),
                *(gating_notes or []),
                *(_string_list((manual_body or {}).get("failed_checks"))),
            ]
        )
        safety = {
            "read_only": False,
            "manual_only": True,
            "one_shot": True,
            "final_confirmation_required": True,
            "confirm_live": request.confirm_live is True,
            "validation_called": False,
            "real_order_submitted": bool(real_order_submitted),
            "broker_submit_called": bool(broker_submit_called),
            "manual_submit_called": bool(manual_submit_called),
            "scheduler_changed": False,
            "setting_changed": False,
            "dry_run_changed": False,
            "kill_switch_changed": False,
            "kis_real_order_changed": False,
            **(safety_overrides or {}),
        }
        return sanitize_kis_payload(
            {
                "symbol": context["symbol"],
                "provider": PROVIDER,
                "market": MARKET,
                "action": SELL,
                "result_status": result_status,
                "attempt_id": None,
                "confirm_live": request.confirm_live is True,
                "final_confirmation_required": True,
                "real_order_submitted": bool(real_order_submitted),
                "broker_submit_called": bool(broker_submit_called),
                "manual_submit_called": bool(manual_submit_called),
                "order_id": order_id,
                "broker_order_id": broker_order_id,
                "kis_odno": kis_odno,
                "requested_quantity": context.get("requested_quantity"),
                "submitted_quantity": submitted_quantity,
                "estimated_sell_notional": context.get("estimated_sell_notional"),
                "current_price": context.get("current_price"),
                "average_price": context.get("average_price"),
                "cost_basis": context.get("cost_basis"),
                "unrealized_pl": context.get("unrealized_pl"),
                "unrealized_pl_pct": context.get("unrealized_pl_pct"),
                "risk_flags": merged_risk_flags,
                "gating_notes": merged_gating_notes,
                "checklist": context.get("checklist") or [],
                "primary_block_reason": primary_block_reason,
                "next_safe_action": _guarded_next_safe_action(
                    result_status,
                    primary_block_reason=primary_block_reason,
                ),
                "submitted_at": _iso(submitted_at),
                "last_synced_at": _iso(last_synced_at),
                "broker_status": (
                    order.broker_status or order.broker_order_status
                    if order is not None
                    else (manual_body or {}).get("broker_status")
                ),
                "internal_status": (
                    order.internal_status if order is not None else (manual_body or {}).get("internal_status")
                ),
                "sanitized_broker_payload": _sanitized_manual_payload(manual_body),
                "safety": safety,
            }
        )

    def _save_guarded_sell_attempt(
        self,
        db: Session,
        *,
        request: GuardedPositionSellRequest,
        context: dict[str, Any],
        response: dict[str, Any],
        validation: dict[str, Any] | None = None,
        related_order_id: int | None = None,
    ) -> StrategyLiveAutoExitAttempt:
        attempt = StrategyLiveAutoExitAttempt(
            provider=PROVIDER,
            market=MARKET,
            active_profile=None,
            symbol=response.get("symbol") or context.get("symbol"),
            symbol_name=None,
            status=response.get("result_status") or "blocked",
            trigger_source=GUARDED_SELL_TRIGGER_SOURCE,
            client_request_id=request.client_request_id,
            exit_trigger=_guarded_exit_trigger(context, request),
            exit_reason=request.reason,
            quantity=response.get("requested_quantity"),
            current_price=response.get("current_price"),
            cost_basis=response.get("cost_basis"),
            unrealized_pnl=response.get("unrealized_pl"),
            unrealized_pnl_pct=response.get("unrealized_pl_pct"),
            requested_notional_krw=response.get("estimated_sell_notional"),
            approved_notional_krw=(
                response.get("estimated_sell_notional")
                if response.get("real_order_submitted") is True
                else None
            ),
            validation_result=_json(validation or {}),
            related_order_id=related_order_id or response.get("order_id"),
            broker_order_id=response.get("broker_order_id") or response.get("kis_odno"),
            block_reason=response.get("primary_block_reason"),
            risk_flags=_json(response.get("risk_flags") or []),
            gating_notes=_json(response.get("gating_notes") or []),
            safety_flags=_json(response.get("safety") or {}),
            request_payload=_json(
                {
                    **request.model_dump(mode="json"),
                    "path_symbol": context.get("symbol"),
                    "mode": GUARDED_SELL_MODE,
                    "source": GUARDED_SELL_MODE,
                    "trigger_source": GUARDED_SELL_TRIGGER_SOURCE,
                    "resolved_quantity": context.get("requested_quantity"),
                }
            ),
            response_payload=_json(response),
            submitted_at=(
                datetime.now(UTC)
                if response.get("real_order_submitted") is True
                else None
            ),
        )
        db.add(attempt)
        db.flush()
        return attempt

    def _idempotent_guarded_sell_attempt(
        self,
        db: Session,
        request: GuardedPositionSellRequest,
    ) -> StrategyLiveAutoExitAttempt | None:
        if not request.client_request_id:
            return None
        return (
            db.query(StrategyLiveAutoExitAttempt)
            .filter(StrategyLiveAutoExitAttempt.provider == PROVIDER)
            .filter(StrategyLiveAutoExitAttempt.market == MARKET)
            .filter(
                StrategyLiveAutoExitAttempt.trigger_source
                == GUARDED_SELL_TRIGGER_SOURCE
            )
            .filter(
                StrategyLiveAutoExitAttempt.client_request_id
                == request.client_request_id
            )
            .order_by(
                StrategyLiveAutoExitAttempt.created_at.desc(),
                StrategyLiveAutoExitAttempt.id.desc(),
            )
            .first()
        )

    def _guarded_sell_attempt(
        self,
        db: Session,
        attempt_id: int,
    ) -> StrategyLiveAutoExitAttempt:
        attempt = db.get(StrategyLiveAutoExitAttempt, int(attempt_id))
        if attempt is None or attempt.trigger_source != GUARDED_SELL_TRIGGER_SOURCE:
            raise ValueError("guarded_sell_attempt_not_found")
        return attempt

    def _guarded_sell_result_from_attempt(
        self,
        attempt: StrategyLiveAutoExitAttempt,
        *,
        order: OrderLog | None = None,
        sync_only: bool = False,
        idempotent_replay: bool = False,
    ) -> dict[str, Any]:
        payload = _parse_object(attempt.response_payload)
        if order is None and attempt.related_order_id:
            # The caller may not have a session-bound order. Re-read lazily through
            # object_session only when SQLAlchemy has one attached.
            from sqlalchemy.orm import object_session

            session = object_session(attempt)
            order = session.get(OrderLog, int(attempt.related_order_id)) if session else None
        if not payload:
            payload = {
                "symbol": attempt.symbol,
                "provider": attempt.provider or PROVIDER,
                "market": attempt.market or MARKET,
                "action": SELL,
                "result_status": attempt.status,
                "confirm_live": True,
                "final_confirmation_required": True,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "order_id": attempt.related_order_id,
                "broker_order_id": attempt.broker_order_id,
                "kis_odno": attempt.broker_order_id,
                "requested_quantity": attempt.quantity,
                "submitted_quantity": None,
                "estimated_sell_notional": attempt.approved_notional_krw,
                "current_price": attempt.current_price,
                "average_price": None,
                "cost_basis": attempt.cost_basis,
                "unrealized_pl": attempt.unrealized_pnl,
                "unrealized_pl_pct": attempt.unrealized_pnl_pct,
                "risk_flags": _parse_list(attempt.risk_flags),
                "gating_notes": _parse_list(attempt.gating_notes),
                "checklist": [],
                "primary_block_reason": attempt.block_reason,
                "next_safe_action": _guarded_next_safe_action(
                    attempt.status,
                    primary_block_reason=attempt.block_reason,
                ),
                "submitted_at": _iso(attempt.submitted_at),
                "last_synced_at": _iso(attempt.synced_at),
                "broker_status": None,
                "internal_status": None,
                "sanitized_broker_payload": None,
                "safety": _parse_object(attempt.safety_flags),
            }
        payload["attempt_id"] = attempt.id
        if order is not None:
            payload["order_id"] = order.id
            payload["broker_order_id"] = order.broker_order_id
            payload["kis_odno"] = order.kis_odno or order.broker_order_id
            payload["broker_status"] = order.broker_status or order.broker_order_status
            payload["internal_status"] = order.internal_status
            payload["submitted_at"] = _iso(order.submitted_at or attempt.submitted_at)
            payload["last_synced_at"] = _iso(order.last_synced_at or attempt.synced_at)
            payload["submitted_quantity"] = _safe_float_or_none(
                order.requested_qty or order.qty
            )
            payload["result_status"] = _order_result_status(
                order,
                fallback=str(payload.get("result_status") or attempt.status),
            )
            payload["next_safe_action"] = _guarded_next_safe_action(
                str(payload["result_status"]),
                primary_block_reason=payload.get("primary_block_reason"),
            )
        safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
        payload["safety"] = {
            **safety,
            "read_only": True,
            "sync_only": bool(sync_only),
            "idempotent_replay": bool(idempotent_replay),
            "scheduler_changed": False,
            "setting_changed": False,
            "dry_run_changed": False,
            "kill_switch_changed": False,
            "kis_real_order_changed": False,
        }
        return sanitize_kis_payload(payload)


def _normalize_position(item: dict[str, Any]) -> dict[str, Any]:
    raw_symbol = item.get("symbol") or item.get("pdno") or item.get("code")
    symbol = str(raw_symbol or "").strip()
    if symbol.isdigit() and len(symbol) < 6:
        symbol = symbol.zfill(6)
    return {
        **item,
        "symbol": symbol.upper(),
        "name": _name_value(item),
        "qty": to_float(item.get("qty") or item.get("hldg_qty") or 0),
        "available_quantity": to_float(
            _first_present(
                item,
                "available_quantity",
                "ord_psbl_qty",
                "sellable_qty",
                "tradable_qty",
                "hldg_qty",
                "qty",
            )
            or 0
        ),
        "avg_entry_price": to_float(
            item.get("avg_entry_price") or item.get("pchs_avg_pric") or 0
        ),
        "current_price": to_float(
            item.get("current_price") or item.get("prpr") or item.get("stck_prpr") or 0
        ),
        "market_value": to_float(item.get("market_value") or item.get("evlu_amt") or 0),
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


def _normalize_order(item: dict[str, Any]) -> dict[str, Any]:
    raw_symbol = item.get("symbol") or item.get("pdno") or item.get("code")
    symbol = str(raw_symbol or "").strip()
    if symbol.isdigit() and len(symbol) < 6:
        symbol = symbol.zfill(6)
    return {**item, "symbol": symbol.upper()}


def _has_duplicate_open_sell(
    db: Session,
    *,
    symbol: str,
    open_orders: list[dict[str, Any]],
    recent_orders: list[dict[str, Any]],
) -> bool:
    if not symbol:
        return False
    for order in open_orders:
        if _order_symbol(order) == symbol and _order_is_sell(order):
            return True
    for order in recent_orders:
        status = str(
            order.get("internal_status")
            or order.get("clear_status")
            or order.get("status")
            or ""
        ).upper()
        if _order_symbol(order) == symbol and status in OPEN_ORDER_STATUSES and _order_is_sell(order):
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


def _latest_buy_order(db: Session, *, symbol: str) -> OrderLog | None:
    if not symbol:
        return None
    return (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.symbol == symbol)
        .filter(OrderLog.side == "buy")
        .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
        .first()
    )


def _entry_source_from_order(row: OrderLog | None) -> str | None:
    payload = _order_response_payload(row)
    if not payload:
        return None
    return _string_or_none(
        payload.get("source")
        or payload.get("source_type")
        or payload.get("trigger_source")
    )


def _promotion_id_from_order(row: OrderLog | None) -> int | None:
    payload = _order_response_payload(row)
    if not payload:
        return None
    for key in ("promotion_id", "source_promotion_id", "auto_buy_promotion_id"):
        value = _safe_int_or_none(payload.get(key))
        if value is not None:
            return value
    return None


def _order_response_payload(row: OrderLog | None) -> dict[str, Any]:
    if row is None or not row.response_payload:
        return {}
    try:
        decoded = json.loads(row.response_payload)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _order_id(row: OrderLog | None) -> int | None:
    return row.id if row is not None else None


def _order_symbol(order: dict[str, Any]) -> str:
    return str(order.get("symbol") or order.get("pdno") or "").strip().upper()


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


def _exit_review_status(
    *,
    duplicate_sell: bool,
    available_quantity: float | None,
    stop_loss: bool,
    take_profit: bool,
) -> str:
    if duplicate_sell or available_quantity is None or available_quantity <= 0:
        return "blocked"
    if stop_loss or take_profit:
        return "review_required"
    return "hold"


def _primary_risk_note(
    *,
    status: str,
    reasons: list[str],
    diagnostics: dict[str, Any],
) -> str:
    if status == "blocked":
        return reasons[0] if reasons else "exit_blocked"
    if "stop_loss_triggered" in reasons:
        return "Stop-loss condition reached; run sell preflight before any action."
    if "take_profit_triggered" in reasons:
        return "Take-profit condition reached; run sell preflight before any action."
    if diagnostics.get("pl_input_warning"):
        return str(diagnostics["pl_input_warning"])
    return "No exit trigger detected; continue monitoring or run preflight for review."


def _review_gating_notes(
    *,
    status: str,
    duplicate_sell: bool,
    available_quantity: float | None,
) -> list[str]:
    notes = [
        "Read-only position exit review.",
        "Sell preflight is required before any final confirmation flow.",
        "No live sell order is created from this review.",
    ]
    if duplicate_sell:
        notes.append("Duplicate open sell order blocks new sell preflight.")
    if available_quantity is not None and available_quantity <= 0:
        notes.append("No sellable quantity is available.")
    if status == "hold":
        notes.append("No stop-loss or take-profit context was detected.")
    return notes


def _next_safe_review_action(status: str) -> str:
    if status == "blocked":
        return "resolve_block_before_preflight"
    if status == "review_required":
        return "run_sell_preflight"
    return "monitor_or_run_sell_preflight"


def _next_required_action(*, status: str, primary_block: str | None) -> str:
    if status == "blocked":
        return f"resolve_{primary_block or 'block'}"
    if status == "review_required":
        return "manual_review_required_before_final_confirmation"
    return "final_operator_confirmation_required"


def _set_check_failed(
    checks: list[dict[str, Any]],
    key: str,
    detail: str,
) -> None:
    for item in checks:
        if item.get("key") == key:
            item["status"] = "fail"
            item["detail"] = detail
            item["blocking"] = True
            return
    checks.append(
        {
            "key": key,
            "status": "fail",
            "label_key": key,
            "detail": detail,
            "blocking": True,
        }
    )


def _safety(
    *,
    broker_read_available: bool,
    read_errors: list[str],
) -> dict[str, Any]:
    return {
        "read_only": True,
        "preflight_only": True,
        "final_confirmation_required": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "order_id": None,
        "broker_order_id": None,
        "kis_odno": None,
        "auto_sell_enabled": False,
        "scheduler_real_order_enabled": False,
        "broker_read_available": broker_read_available,
        "read_errors": read_errors,
    }


def _read_errors(snapshot: dict[str, Any]) -> list[str]:
    return _dedupe(
        [
            snapshot.get("positions_error") or "",
            snapshot.get("open_orders_error") or "",
            snapshot.get("recent_orders_error") or "",
            "market_session_unavailable"
            if snapshot.get("market_session_allowed") is not True
            and (snapshot.get("market_session") or {}).get("error")
            else "",
        ]
    )


def _available_quantity(
    position: dict[str, Any],
    *,
    fallback: float | None,
) -> float | None:
    value = _safe_float_or_none(position.get("available_quantity"))
    if value is not None:
        return value
    return fallback


def _normalize_symbol(value: str) -> str:
    symbol = str(value or "").strip().upper()
    if symbol.isdigit() and len(symbol) < 6:
        return symbol.zfill(6)
    return symbol


def _name_value(payload: dict[str, Any]) -> str | None:
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


def _first_float(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _safe_float_or_none(payload.get(key))
        if value is not None:
            return value
    return None


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _notional(qty: float | None, price: float | None) -> float | None:
    if qty is None or price is None:
        return None
    return round(qty * price, 2)


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


def _safe_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _guarded_requested_quantity(
    *,
    quantity_mode: str,
    quantity: Any,
    available_quantity: float | None,
) -> float | None:
    if available_quantity is None:
        return None
    if quantity_mode == "full":
        return available_quantity
    if quantity_mode == "partial":
        return _safe_float_or_none(quantity)
    return None


def _guarded_quantity_valid(
    *,
    requested_quantity: float | None,
    available_quantity: float | None,
) -> bool:
    if requested_quantity is None or available_quantity is None:
        return False
    if requested_quantity <= 0 or requested_quantity > available_quantity:
        return False
    return float(requested_quantity).is_integer()


def _guarded_sell_source_metadata(
    *,
    request: GuardedPositionSellRequest,
    context: dict[str, Any],
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "source": GUARDED_SELL_MODE,
        "source_type": GUARDED_SELL_MODE,
        "source_context": GUARDED_SELL_MODE,
        "operator_action_source": "position_exit_review_panel",
        "trigger_source": GUARDED_SELL_TRIGGER_SOURCE,
        "symbol": context.get("symbol"),
        "quantity_mode": context.get("quantity_mode"),
        "requested_quantity": context.get("requested_quantity"),
        "estimated_sell_notional": context.get("estimated_sell_notional"),
        "reason": request.reason,
        "preflight_id": request.preflight_id,
        "client_request_id": request.client_request_id,
        "final_confirmation_required": True,
        "confirm_live": request.confirm_live is True,
        "manual_only": True,
        "auto_sell_enabled": False,
        "retry_enabled": False,
    }
    if validation:
        payload["validation_block_reasons"] = validation.get("block_reasons")
        payload["validation_id"] = validation.get("validation_id")
    return sanitize_kis_payload(payload)


def _kis_confirmation_phrase(client: KisClient) -> str:
    return str(
        getattr(client.settings, "kis_confirmation_phrase", KIS_MANUAL_CONFIRMATION_PHRASE)
        or KIS_MANUAL_CONFIRMATION_PHRASE
    )


def _manual_bool(payload: dict[str, Any], key: str) -> bool:
    if payload.get(key) is True:
        return True
    audit = payload.get("audit_metadata")
    return bool(isinstance(audit, dict) and audit.get(key) is True)


def _manual_primary_block_reason(payload: dict[str, Any]) -> str | None:
    primary = _string_or_none(payload.get("primary_block_reason"))
    if primary:
        return primary
    block_reasons = payload.get("block_reasons")
    if isinstance(block_reasons, list) and block_reasons:
        return _string_or_none(block_reasons[0])
    failed = payload.get("failed_checks")
    if isinstance(failed, list) and failed:
        safety_checks = payload.get("safety_checks")
        if isinstance(safety_checks, dict):
            first = safety_checks.get(str(failed[0]))
            if isinstance(first, dict):
                return _string_or_none(first.get("reason")) or _string_or_none(failed[0])
        return _string_or_none(failed[0])
    return None


def _manual_submit_result_status(
    *,
    status_code: int,
    body: dict[str, Any],
    order: OrderLog | None,
) -> str:
    if order is not None:
        return _order_result_status(order, fallback="submitted")
    if body.get("real_order_submitted") is True:
        return "submitted"
    internal = str(body.get("internal_status") or "").upper()
    if internal in {
        InternalOrderStatus.REJECTED.value,
        InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value,
        InternalOrderStatus.FAILED.value,
    }:
        return "rejected"
    if _manual_bool(body, "broker_submit_called") and body.get("real_order_submitted") is not True:
        return "pending_sync"
    if status_code >= 400:
        return "rejected"
    return "unknown"


def _order_result_status(order: OrderLog, *, fallback: str) -> str:
    internal = str(order.internal_status or "").upper()
    if internal == InternalOrderStatus.FILLED.value:
        return "filled"
    if internal in {
        InternalOrderStatus.REJECTED.value,
        InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value,
        InternalOrderStatus.FAILED.value,
        InternalOrderStatus.CANCELED.value,
        InternalOrderStatus.EXPIRED.value,
    }:
        return "rejected"
    if internal in {
        InternalOrderStatus.UNKNOWN_STALE.value,
        InternalOrderStatus.SYNC_FAILED.value,
    }:
        return "pending_sync"
    if internal in {
        InternalOrderStatus.REQUESTED.value,
        InternalOrderStatus.SUBMITTED.value,
        InternalOrderStatus.ACCEPTED.value,
        InternalOrderStatus.PENDING.value,
        InternalOrderStatus.PARTIALLY_FILLED.value,
    }:
        return "submitted"
    return fallback


def _guarded_next_safe_action(
    result_status: str,
    *,
    primary_block_reason: str | None,
) -> str:
    status = str(result_status or "").strip().lower()
    if status == "blocked":
        return f"resolve_{primary_block_reason or 'block'}"
    if status == "dry_run_simulated":
        return "review_dry_run_result"
    if status in {"submitted", "pending_sync"}:
        return "sync_order_status"
    if status in {"filled", "rejected"}:
        return "review_result"
    return "refresh_result"


def _sanitized_manual_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    allowed = {
        "provider",
        "market",
        "mode",
        "symbol",
        "side",
        "qty",
        "order_type",
        "broker_order_id",
        "broker_status",
        "broker_order_status",
        "internal_status",
        "order_id",
        "order_log_id",
        "kis_odno",
        "block_reasons",
        "failed_checks",
        "primary_block_reason",
        "message",
        "detail",
        "audit_warning_level",
        "audit_validation_age_seconds",
    }
    return sanitize_kis_payload({key: payload.get(key) for key in allowed if key in payload})


def _guarded_exit_trigger(
    context: dict[str, Any],
    request: GuardedPositionSellRequest,
) -> str:
    reason = str(request.reason or "").strip().lower()
    if reason in {"stop_loss_review", "stop_loss"}:
        return "stop_loss"
    if reason in {"take_profit_review", "take_profit"}:
        return "take_profit"
    if context.get("stop_loss_triggered") is True:
        return "stop_loss"
    if context.get("take_profit_triggered") is True:
        return "take_profit"
    return "manual_exit"


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


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


def _parse_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 180:
        text = f"{text[:180]}..."
    return f"{exc.__class__.__name__}: {text}"


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        if text not in result:
            result.append(text)
    return result
