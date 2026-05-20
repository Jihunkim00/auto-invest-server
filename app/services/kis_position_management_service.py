from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient, to_float
from app.db.models import OrderLog
from app.services.kis_dry_run_risk_service import (
    MARKET,
    OPEN_ORDER_STATUSES,
    PROVIDER,
    SELL,
    position_exit_threshold_reasons,
    position_pl_diagnostics,
)
from app.services.kis_order_sync_service import serialize_kis_order
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.market_profile_service import MarketProfileError, MarketProfileService
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.technical_indicator_service import TechnicalIndicatorService


HOLD = "HOLD"
REVIEW_SELL = "REVIEW_SELL"
SELL_READY = "SELL_READY"

SOURCE = "kis_portfolio_manual_sell"
SOURCE_TYPE = "operator_confirmed_position_exit"


class KisPositionManagementService:
    """Read-only operator view for held KIS positions and manual sell prep.

    This service deliberately does not submit orders. Manual sells continue to
    flow through the existing KIS validation and manual-submit services.
    """

    def __init__(
        self,
        client: KisClient,
        *,
        profile_service: MarketProfileService | None = None,
        session_service: MarketSessionService | None = None,
        runtime_settings: RuntimeSettingService | None = None,
        indicators: TechnicalIndicatorService | None = None,
    ):
        self.client = client
        self.profile_service = profile_service or MarketProfileService()
        self.session_service = session_service or MarketSessionService()
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.indicators = indicators or TechnicalIndicatorService()

    def positions_manage(self, db: Session) -> dict[str, Any]:
        settings = self.client.settings
        runtime = self.runtime_settings.get_settings(db)
        market_session = self._market_session()
        profile = self.profile_service.get_profile(MARKET)
        name_map = self._name_map()
        raw_positions = self._held_positions()
        open_orders = self._open_orders()
        checked_at = datetime.now(UTC).isoformat()

        positions = [
            self._managed_position(
                db,
                raw,
                runtime=runtime,
                market_session=market_session,
                profile_enabled=profile.enabled_for_trading,
                name_map=name_map,
                open_orders=open_orders,
                checked_at=checked_at,
            )
            for raw in raw_positions
        ]

        return sanitize_kis_payload(
            {
                "provider": PROVIDER,
                "market": MARKET,
                "currency": profile.currency,
                "mode": "position_management",
                "source": "kis_position_management",
                "read_only": True,
                "count": len(positions),
                "positions": positions,
                "market_session": _public_market_session(market_session),
                "runtime": _runtime_snapshot(runtime),
                "manual_sell": {
                    "prepare_endpoint": "/kis/positions/{symbol}/prepare-manual-sell",
                    "validate_endpoint": "/kis/orders/validate",
                    "submit_endpoint": "/kis/orders/manual-submit",
                    "requires_existing_manual_flow": True,
                    "confirm_live_required": True,
                    "final_confirmation_required": True,
                    "auto_sell_enabled": False,
                    "scheduler_real_order_enabled": False,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                },
                "checked_at": checked_at,
            }
        )

    def prepare_manual_sell(self, db: Session, *, symbol: str) -> dict[str, Any]:
        normalized_symbol = self.profile_service.normalize_symbol(symbol, MARKET)
        managed = self.positions_manage(db)
        positions = [
            item
            for item in _dict_list(managed.get("positions"))
            if str(item.get("symbol") or "").upper() == normalized_symbol
        ]
        if not positions:
            raise ValueError(f"No held KIS position found for {normalized_symbol}.")

        position = positions[0]
        qty = _safe_int(math.floor(_safe_float(position.get("quantity"), 0.0)), 0)
        current_price = _safe_float_or_none(position.get("current_price"))
        estimated_amount = (
            round(float(qty) * current_price, 2)
            if qty > 0 and current_price is not None
            else None
        )
        can_prepare = qty > 0
        block_reasons = _string_list(position.get("block_reasons"))
        if qty <= 0:
            block_reasons.append("no_held_quantity")
        block_reasons = _dedupe(block_reasons)
        can_submit = can_prepare and not block_reasons
        trigger_flags = _trigger_flags_from_position(position)
        source_metadata = {
            "source": SOURCE,
            "source_type": SOURCE_TYPE,
            "symbol": normalized_symbol,
            "company_name": position.get("company_name") or position.get("name"),
            "quantity": qty,
            "suggested_quantity": qty,
            "current_price": current_price,
            "estimated_amount": estimated_amount,
            "exit_reason": position.get("exit_reason"),
            "trigger_source": "portfolio_position_management",
            "trigger_flags": trigger_flags,
            "position_snapshot": _position_snapshot(position),
            "runtime_safety_snapshot": {
                **_runtime_snapshot(managed.get("runtime")),
                "market_open": (managed.get("market_session") or {}).get(
                    "is_market_open"
                ),
            },
            "risk_flags": _string_list(position.get("risk_flags")),
            "gating_notes": _string_list(position.get("gating_notes")),
            "manual_confirm_required": True,
            "auto_buy_enabled": False,
            "auto_sell_enabled": False,
            "scheduler_real_order_enabled": False,
            "real_order_submit_allowed": can_submit,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
        }

        return sanitize_kis_payload(
            {
                "provider": PROVIDER,
                "market": MARKET,
                "symbol": normalized_symbol,
                "name": position.get("name"),
                "company_name": position.get("company_name") or position.get("name"),
                "side": SELL,
                "quantity": qty,
                "suggested_quantity": qty if qty > 0 else None,
                "current_price": current_price,
                "estimated_amount": estimated_amount,
                "exit_reason": position.get("exit_reason"),
                "human_reason": position.get("human_reason"),
                "holding_status": position.get("holding_status"),
                "can_prepare": can_prepare,
                "can_submit": can_submit,
                "can_prepare_manual_sell": can_prepare,
                "can_submit_manual_sell": can_submit,
                "block_reasons": block_reasons,
                "safety_status": {
                    "dry_run": (managed.get("runtime") or {}).get("dry_run"),
                    "kill_switch": (managed.get("runtime") or {}).get("kill_switch"),
                    "kis_enabled": bool(getattr(self.client.settings, "kis_enabled", False)),
                    "kis_real_order_enabled": bool(
                        getattr(self.client.settings, "kis_real_order_enabled", False)
                    ),
                    "market_open": (managed.get("market_session") or {}).get(
                        "is_market_open"
                    ),
                    "confirm_live_required": True,
                    "final_confirmation_required": True,
                },
                "manual_order": {
                    "validate_endpoint": "/kis/orders/validate",
                    "submit_endpoint": "/kis/orders/manual-submit",
                    "requires_existing_manual_flow": True,
                    "confirm_live_required": True,
                    "final_confirmation_required": True,
                    "source_metadata": source_metadata,
                },
                "source_metadata": source_metadata,
                "position": position,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "checked_at": datetime.now(UTC).isoformat(),
            }
        )

    def _managed_position(
        self,
        db: Session,
        raw: dict[str, Any],
        *,
        runtime: dict[str, Any],
        market_session: dict[str, Any],
        profile_enabled: bool,
        name_map: dict[str, str],
        open_orders: list[dict[str, Any]],
        checked_at: str,
    ) -> dict[str, Any]:
        position = _normalize_position(raw)
        symbol = str(position.get("symbol") or "")
        name = _company_name(position, name_map)
        qty = _safe_float(position.get("qty"), 0.0)
        technical = self._technical_snapshot(
            symbol,
            current_price=_safe_float_or_none(position.get("current_price")),
        )
        diagnostics = position_pl_diagnostics(position)
        threshold_reasons, diagnostics = position_exit_threshold_reasons(position)
        weak_trend = _weak_trend_triggered(technical)
        sell_pressure = _sell_pressure_triggered(position)
        duplicate_sell = _has_duplicate_open_sell(
            db,
            symbol=symbol,
            open_orders=open_orders,
        )
        manual_review = (
            diagnostics.get("exit_trigger_source") != "cost_basis"
            or duplicate_sell
            or weak_trend
        )

        stop_loss = "stop_loss_triggered" in threshold_reasons
        take_profit = "take_profit_triggered" in threshold_reasons
        sell_ready = stop_loss or take_profit or sell_pressure
        if sell_ready:
            status = SELL_READY
        elif manual_review:
            status = REVIEW_SELL
        else:
            status = HOLD

        trigger_flags = {
            "stop_loss_triggered": stop_loss,
            "take_profit_triggered": take_profit,
            "weak_trend_triggered": weak_trend,
            "sell_pressure_triggered": sell_pressure,
            "manual_review_required": manual_review,
        }
        raw_reasons = _dedupe(
            threshold_reasons
            + (["weak_trend_triggered"] if weak_trend else [])
            + (["sell_pressure_triggered"] if sell_pressure else [])
            + (["duplicate_open_sell_order"] if duplicate_sell else [])
            + (
                ["cost_basis_unavailable"]
                if diagnostics.get("exit_trigger_source") != "cost_basis"
                else []
            )
        )
        if not raw_reasons:
            raw_reasons = ["no_exit_condition"]

        block_reasons = _manual_sell_block_reasons(
            qty=qty,
            runtime=runtime,
            settings=self.client.settings,
            market_session=market_session,
            profile_enabled=profile_enabled,
            duplicate_sell=duplicate_sell,
        )
        risk_flags = _dedupe(raw_reasons + block_reasons)
        gating_notes = _gating_notes(status=status, block_reasons=block_reasons)
        latest_order = _latest_manual_sell_order(db, symbol=symbol)

        unrealized_pct = (
            diagnostics.get("unrealized_pl_pct")
            if diagnostics.get("exit_trigger_source") == "cost_basis"
            else None
        )

        payload = {
            "provider": PROVIDER,
            "market": MARKET,
            "symbol": symbol,
            "name": name,
            "company_name": name,
            "quantity": qty,
            "qty": qty,
            "average_price": _safe_float_or_none(position.get("avg_entry_price")),
            "avg_entry_price": _safe_float_or_none(position.get("avg_entry_price")),
            "cost_basis": diagnostics.get("cost_basis"),
            "current_price": _safe_float_or_none(position.get("current_price")),
            "current_value": diagnostics.get("current_value"),
            "market_value": diagnostics.get("current_value"),
            "unrealized_pl": diagnostics.get("unrealized_pl"),
            "unrealized_pl_pct": unrealized_pct,
            "broker_unrealized_pl_pct": _safe_float_or_none(
                position.get("unrealized_plpc")
            ),
            "pl_diagnostics": diagnostics,
            "holding_status": status,
            "status": status,
            "exit_reason": raw_reasons[0],
            "human_reason": _human_reason(status, raw_reasons),
            "stop_loss_triggered": stop_loss,
            "take_profit_triggered": take_profit,
            "weak_trend_triggered": weak_trend,
            "sell_pressure_triggered": sell_pressure,
            "manual_review_required": manual_review,
            "trigger_flags": trigger_flags,
            "technical_snapshot": technical,
            "indicator_status": technical.get("indicator_status"),
            "indicator_bar_count": technical.get("indicator_bar_count"),
            "final_sell_score": _first_float(position, "final_sell_score", "sell_score"),
            "final_buy_score": _first_float(
                position, "final_buy_score", "final_entry_score", "score"
            ),
            "quant_sell_score": _first_float(position, "quant_sell_score"),
            "quant_buy_score": _first_float(position, "quant_buy_score", "quant_score"),
            "ai_sell_score": _first_float(position, "ai_sell_score", "gpt_sell_score"),
            "ai_buy_score": _first_float(position, "ai_buy_score", "gpt_buy_score"),
            "confidence": _first_float(position, "confidence"),
            "risk_flags": risk_flags,
            "gating_notes": gating_notes,
            "latest_related_manual_sell_order": latest_order,
            "latest_manual_sell_order": latest_order,
            "can_prepare_manual_sell": qty > 0,
            "can_submit_manual_sell": qty > 0 and not block_reasons,
            "block_reasons": block_reasons,
            "manual_submit_endpoint": "/kis/orders/manual-submit",
            "raw_position": position,
            "checked_at": checked_at,
        }
        return sanitize_kis_payload(payload)

    def _held_positions(self) -> list[dict[str, Any]]:
        positions = []
        for item in self.client.list_positions():
            if not isinstance(item, dict):
                continue
            normalized = _normalize_position(item)
            if _safe_float(normalized.get("qty"), 0.0) > 0:
                positions.append(normalized)
        positions.sort(key=lambda item: str(item.get("symbol") or ""))
        return positions

    def _open_orders(self) -> list[dict[str, Any]]:
        try:
            orders = self.client.list_open_orders()
        except Exception:
            return []
        return [item for item in orders if isinstance(item, dict)]

    def _market_session(self) -> dict[str, Any]:
        return self.session_service.get_session_status(MARKET)

    def _technical_snapshot(
        self,
        symbol: str,
        *,
        current_price: float | None,
    ) -> dict[str, Any]:
        try:
            bars = self.client.get_domestic_daily_bars(symbol, limit=120)
            result = self.indicators.calculate(bars, current_price=current_price)
        except Exception as exc:
            result = {
                "indicator_status": "error",
                "indicator_payload": {},
                "bar_count": 0,
                "error": _safe_error(exc),
            }

        payload = result.get("indicator_payload")
        indicators = payload if isinstance(payload, dict) else {}
        price = _safe_float_or_none(indicators.get("price")) or current_price
        snapshot = {
            "current_price": price,
            "ema20": _safe_float_or_none(indicators.get("ema20")),
            "ema50": _safe_float_or_none(indicators.get("ema50")),
            "vwap": _safe_float_or_none(indicators.get("vwap")),
            "rsi": _safe_float_or_none(indicators.get("rsi")),
            "atr": _safe_float_or_none(indicators.get("atr")),
            "volume_ratio": _safe_float_or_none(indicators.get("volume_ratio")),
            "recent_return": _safe_float_or_none(indicators.get("recent_return")),
            "momentum": _safe_float_or_none(
                indicators.get("momentum") or indicators.get("short_momentum")
            ),
            "price_vs_ema20": _price_relation(price, indicators.get("ema20")),
            "price_vs_ema50": _price_relation(price, indicators.get("ema50")),
            "price_vs_vwap": _price_relation(price, indicators.get("vwap")),
            "indicator_status": result.get("indicator_status"),
            "indicator_bar_count": result.get("bar_count"),
        }
        if result.get("error"):
            snapshot["error"] = result.get("error")
        return snapshot

    def _name_map(self) -> dict[str, str]:
        try:
            watchlist = self.profile_service.load_watchlist(MARKET)
        except MarketProfileError:
            return {}
        result: dict[str, str] = {}
        for item in _dict_list(watchlist.get("symbols")):
            symbol = str(item.get("symbol") or "").strip().upper()
            name = _name_value(item)
            if symbol and name:
                result[symbol] = name
        return result


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
        "unrealized_pl": to_float(item.get("unrealized_pl") or item.get("evlu_pfls_amt") or 0),
        "unrealized_plpc": to_float(
            item.get("unrealized_plpc") or item.get("evlu_pfls_rt") or 0
        ),
    }


def _company_name(position: dict[str, Any], name_map: dict[str, str]) -> str:
    return (
        _name_value(position)
        or name_map.get(str(position.get("symbol") or "").upper())
        or "Unknown company"
    )


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


def _weak_trend_triggered(snapshot: dict[str, Any]) -> bool:
    below_count = sum(
        1
        for key in ("price_vs_ema20", "price_vs_ema50", "price_vs_vwap")
        if snapshot.get(key) == "below"
    )
    momentum = _safe_float_or_none(snapshot.get("momentum"))
    recent = _safe_float_or_none(snapshot.get("recent_return"))
    return below_count >= 2 or (momentum is not None and momentum < 0) or (
        recent is not None and recent < 0
    )


def _sell_pressure_triggered(position: dict[str, Any]) -> bool:
    sell_score = _first_float(position, "final_sell_score", "sell_score", "quant_sell_score")
    buy_score = _first_float(position, "final_buy_score", "final_entry_score", "score")
    if sell_score is None:
        return False
    if sell_score >= 65:
        return True
    return buy_score is not None and sell_score >= 50 and sell_score > buy_score


def _manual_sell_block_reasons(
    *,
    qty: float,
    runtime: dict[str, Any],
    settings: Any,
    market_session: dict[str, Any],
    profile_enabled: bool,
    duplicate_sell: bool,
) -> list[str]:
    reasons: list[str] = []
    if qty <= 0:
        reasons.append("no_held_quantity")
    if bool(runtime.get("dry_run", True)):
        reasons.append("runtime_dry_run_enabled")
    if bool(runtime.get("kill_switch", False)):
        reasons.append("kill_switch_enabled")
    if not bool(getattr(settings, "kis_enabled", False)):
        reasons.append("kis_enabled_false")
    if not bool(getattr(settings, "kis_real_order_enabled", False)):
        reasons.append("kis_real_order_enabled_false")
    if not profile_enabled:
        reasons.append("kr_trading_profile_disabled")
    if market_session.get("is_market_open") is not True:
        reasons.append("market_closed")
    if duplicate_sell:
        reasons.append("duplicate_open_sell_order")
    return _dedupe(reasons)


def _gating_notes(*, status: str, block_reasons: list[str]) -> list[str]:
    notes = [
        "Read-only position management view.",
        "Manual sell must use /kis/orders/validate and /kis/orders/manual-submit.",
        "No auto sell execution was enabled.",
    ]
    if status == HOLD:
        notes.append("No sell-ready trigger was detected.")
    if block_reasons:
        notes.append("Manual live submit is blocked until safety checks pass.")
    return notes


def _human_reason(status: str, reasons: list[str]) -> str:
    labels = {
        "stop_loss_triggered": "Stop-loss threshold reached.",
        "take_profit_triggered": "Take-profit threshold reached.",
        "weak_trend_triggered": "Weak trend detected; review the position.",
        "sell_pressure_triggered": "Sell pressure is elevated.",
        "duplicate_open_sell_order": "An open KIS sell order already exists.",
        "cost_basis_unavailable": "Cost basis is missing, so P/L percent needs review.",
        "no_exit_condition": "No sell trigger detected.",
    }
    if status == HOLD:
        return labels["no_exit_condition"]
    return " ".join(labels.get(reason, reason.replace("_", " ").title() + ".") for reason in reasons)


def _has_duplicate_open_sell(
    db: Session,
    *,
    symbol: str,
    open_orders: list[dict[str, Any]],
) -> bool:
    normalized = symbol.upper()
    for order in open_orders:
        order_symbol = str(order.get("symbol") or order.get("pdno") or "").strip().upper()
        if order_symbol == normalized and _order_is_sell(order):
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


def _latest_manual_sell_order(db: Session, *, symbol: str) -> dict[str, Any] | None:
    row = (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.symbol == symbol.upper())
        .filter(OrderLog.side == SELL)
        .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
        .first()
    )
    if row is None:
        return None
    return serialize_kis_order(row)


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


def _trigger_flags_from_position(position: dict[str, Any]) -> dict[str, bool]:
    return {
        "stop_loss_triggered": position.get("stop_loss_triggered") is True,
        "take_profit_triggered": position.get("take_profit_triggered") is True,
        "weak_trend_triggered": position.get("weak_trend_triggered") is True,
        "sell_pressure_triggered": position.get("sell_pressure_triggered") is True,
        "manual_review_required": position.get("manual_review_required") is True,
    }


def _position_snapshot(position: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "provider",
        "market",
        "symbol",
        "name",
        "company_name",
        "quantity",
        "average_price",
        "cost_basis",
        "current_price",
        "current_value",
        "unrealized_pl",
        "unrealized_pl_pct",
        "holding_status",
        "exit_reason",
        "human_reason",
    ]
    return {key: position.get(key) for key in keys if key in position}


def _public_market_session(market_session: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "market",
        "timezone",
        "is_market_open",
        "is_entry_allowed_now",
        "is_near_close",
        "closure_reason",
        "closure_name",
        "effective_close",
        "no_new_entry_after",
        "local_time",
    ]
    return {key: market_session.get(key) for key in keys if key in market_session}


def _runtime_snapshot(runtime: Any) -> dict[str, Any]:
    value = runtime if isinstance(runtime, dict) else {}
    return {
        "dry_run": bool(value.get("dry_run", True)),
        "kill_switch": bool(value.get("kill_switch", False)),
        "scheduler_enabled": bool(value.get("scheduler_enabled", False)),
        "kis_live_auto_enabled": bool(value.get("kis_live_auto_enabled", False)),
        "kis_live_auto_buy_enabled": bool(
            value.get("kis_live_auto_buy_enabled", False)
        ),
        "kis_live_auto_sell_enabled": bool(
            value.get("kis_live_auto_sell_enabled", False)
        ),
    }


def _price_relation(price: Any, reference: Any) -> str | None:
    price_value = _safe_float_or_none(price)
    reference_value = _safe_float_or_none(reference)
    if price_value is None or reference_value is None:
        return None
    if price_value > reference_value:
        return "above"
    if price_value < reference_value:
        return "below"
    return "at"


def _first_float(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _safe_float_or_none(payload.get(key))
        if value is not None:
            return value
    return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if not value:
            continue
        if value not in result:
            result.append(value)
    return result


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 160:
        text = f"{text[:160]}..."
    return f"{exc.__class__.__name__}: {text}"
