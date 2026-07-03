from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient, to_float
from app.db.models import OrderLog
from app.schemas.position_exit_review import PositionSellPreflightRequest
from app.services.kis_dry_run_risk_service import (
    MARKET,
    OPEN_ORDER_STATUSES,
    PROVIDER,
    SELL,
    position_exit_threshold_reasons,
    position_pl_diagnostics,
)
from app.services.kis_order_sync_service import (
    KisOrderSyncService,
    serialize_kis_order,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService


class PositionExitReviewService:
    """Read-only held-position review and guarded sell preflight."""

    def __init__(
        self,
        client: KisClient,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
    ):
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()

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


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        if text not in result:
            result.append(text)
    return result
