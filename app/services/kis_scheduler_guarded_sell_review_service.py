from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.services.kis_payload_sanitizer import sanitize_kis_payload


PROVIDER = "kis"
MARKET = "KR"
SELL = "sell"
BUY = "buy"
REVIEW_MODE = "kis_scheduler_guarded_sell_review"
SOURCE_MODE = "kis_scheduler_guarded_sell"
SOURCE_TRIGGER = "scheduler_guarded_sell"
SOURCE_TYPE = "scheduler_guarded_sell_execution"
KR_TZ = ZoneInfo("Asia/Seoul")

_SUBMITTED_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}

_BLOCK_REASON_LABELS = {
    "daily_auto_sell_limit_reached": "Daily sell limit reached",
    "duplicate_open_sell_order": "Duplicate open sell order",
    "kill_switch_enabled": "Kill switch enabled",
    "kis_real_order_disabled": "KIS real orders disabled",
    "no_exit_candidate": "No sell candidate",
    "no_sell_candidate": "No sell candidate",
    "runtime_dry_run_true": "Runtime dry-run enabled",
    "scheduler_disabled": "Scheduler disabled",
    "scheduler_real_orders_disabled": "Scheduler real orders disabled",
    "scheduler_sell_disabled": "Scheduler sell disabled",
    "validation_failed": "Validation failed",
}


class KisSchedulerGuardedSellReviewService:
    """Read-only operator audit for scheduler guarded sell execution."""

    def review(
        self,
        db: Session,
        *,
        limit: int = 20,
        days: int = 30,
        symbol: str | None = None,
        include_raw: bool = False,
        result: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        safe_limit = min(max(int(limit or 20), 1), 100)
        safe_days = min(max(int(days or 30), 1), 365)
        normalized_symbol = _normalize_symbol(symbol)
        result_filter = _clean(result)
        cutoff = _naive_utc(_utc_now(now) - timedelta(days=safe_days))

        source_rows = self._query_trade_rows(
            db,
            cutoff=cutoff,
            symbol=normalized_symbol,
        )
        source_row_count = len(source_rows)
        ignored_row_count = 0
        malformed_row_count = 0
        attempts: list[dict[str, Any]] = []

        for row in source_rows:
            payload = _json_dict(row.response_payload)
            if not payload:
                malformed_row_count += 1
                payload = _fallback_payload(row)
            if not _is_source_row(row, payload):
                ignored_row_count += 1
                continue

            attempt = _attempt_from_row(row, payload, include_raw=include_raw)
            if normalized_symbol and _normalize_symbol(attempt.get("symbol")) != normalized_symbol:
                ignored_row_count += 1
                continue
            if result_filter and _clean(attempt.get("result")) != result_filter:
                ignored_row_count += 1
                continue
            attempts.append(attempt)

        attempts = attempts[:safe_limit]
        related_order_ids = {
            int(order_id)
            for order_id in (_int_value(item.get("order_id")) for item in attempts)
            if order_id is not None
        }
        order_rows = self._query_order_rows(
            db,
            cutoff=cutoff,
            symbol=normalized_symbol,
            related_order_ids=related_order_ids,
        )
        order_by_id = {int(row.id): row for row in order_rows}
        signal_rows = self._query_signal_rows(
            db,
            cutoff=cutoff,
            symbol=normalized_symbol,
        )

        submitted_sells = [
            _submitted_sell_from_attempt(
                attempt,
                order_by_id=order_by_id,
                include_raw=include_raw,
            )
            for attempt in attempts
            if _is_submitted_attempt(attempt)
        ]
        submitted_sells.sort(
            key=lambda item: (
                str(item.get("created_at") or ""),
                int(item.get("order_id") or 0),
            ),
            reverse=True,
        )
        blocked_attempts = [
            _blocked_attempt(item)
            for item in attempts
            if not _is_submitted_attempt(item)
        ]
        daily_usage = _daily_usage(submitted_sells)
        safety_violations = _safety_violations(
            attempts=attempts,
            submitted_sells=submitted_sells,
            daily_usage=daily_usage,
        )
        sell_only_invariant_ok = not any(
            item["reason"]
            in {
                "scheduler_guarded_sell_buy_execution_allowed",
                "scheduler_guarded_sell_action_buy",
                "scheduler_guarded_sell_buy_result_submitted",
                "child_limited_auto_buy_submitted",
            }
            for item in safety_violations
        )
        no_direct_scheduler_submit_invariant_ok = not any(
            item["reason"]
            in {
                "scheduler_broker_submit_without_limited_sell_child",
                "scheduler_manual_submit_without_limited_sell_child",
            }
            for item in safety_violations
        )
        buy_execution_never_called = sell_only_invariant_ok
        summary = _summary(
            attempts=attempts,
            submitted_sells=submitted_sells,
            daily_usage=daily_usage,
            sell_only_invariant_ok=sell_only_invariant_ok,
            no_direct_scheduler_submit_invariant_ok=(
                no_direct_scheduler_submit_invariant_ok
            ),
            buy_execution_never_called=buy_execution_never_called,
        )

        correlated_order_ids = {
            int(item["order_id"])
            for item in submitted_sells
            if _int_value(item.get("order_id")) is not None
        }
        return sanitize_kis_payload(
            {
                "provider": PROVIDER,
                "market": MARKET,
                "mode": REVIEW_MODE,
                "review_only": True,
                "sell_only": True,
                "buy_execution_allowed": False,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "order_log_created": False,
                "summary": summary,
                "recent_attempts": attempts,
                "submitted_sells": submitted_sells,
                "blocked_attempts": blocked_attempts,
                "top_block_reasons": _top_block_reasons(attempts),
                "daily_usage": daily_usage,
                "safety_violations": safety_violations,
                "safety": {
                    "review_only": True,
                    "sell_only": True,
                    "buy_execution_allowed": False,
                    "no_broker_submit_from_review": True,
                    "no_manual_submit_from_review": True,
                    "no_order_log_created_from_review": True,
                    "scheduler_real_orders_default_off": True,
                    "sell_only_invariant_ok": sell_only_invariant_ok,
                    "no_direct_scheduler_submit_invariant_ok": (
                        no_direct_scheduler_submit_invariant_ok
                    ),
                    "existing_guarded_sell_unchanged": True,
                    "existing_guarded_buy_unchanged": True,
                },
                "diagnostics": {
                    "source_row_count": source_row_count,
                    "order_log_rows_examined": len(order_rows),
                    "signal_log_rows_examined": len(signal_rows),
                    "correlated_order_count": len(correlated_order_ids),
                    "uncorrelated_order_count": max(
                        0,
                        len(order_rows) - len(correlated_order_ids),
                    ),
                    "malformed_row_count": malformed_row_count,
                    "ignored_row_count": ignored_row_count,
                    "filters_applied": {
                        "limit": safe_limit,
                        "days": safe_days,
                        "symbol": normalized_symbol,
                        "result": result_filter,
                    },
                    "include_raw": bool(include_raw),
                    "read_only": True,
                },
            }
        )

    def _query_trade_rows(
        self,
        db: Session,
        *,
        cutoff: datetime,
        symbol: str | None,
    ) -> list[TradeRunLog]:
        query = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.created_at >= cutoff)
            .filter(
                or_(
                    TradeRunLog.mode == SOURCE_MODE,
                    TradeRunLog.trigger_source == SOURCE_TRIGGER,
                    TradeRunLog.request_payload.like(f"%{SOURCE_MODE}%"),
                    TradeRunLog.response_payload.like(f"%{SOURCE_MODE}%"),
                    TradeRunLog.request_payload.like(f"%{SOURCE_TRIGGER}%"),
                    TradeRunLog.response_payload.like(f"%{SOURCE_TRIGGER}%"),
                    TradeRunLog.request_payload.like(f"%{SOURCE_TYPE}%"),
                    TradeRunLog.response_payload.like(f"%{SOURCE_TYPE}%"),
                )
            )
        )
        if symbol:
            query = query.filter(
                or_(
                    TradeRunLog.symbol == symbol,
                    TradeRunLog.request_payload.like(f"%{symbol}%"),
                    TradeRunLog.response_payload.like(f"%{symbol}%"),
                )
            )
        return query.order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc()).all()

    def _query_order_rows(
        self,
        db: Session,
        *,
        cutoff: datetime,
        symbol: str | None,
        related_order_ids: set[int],
    ) -> list[OrderLog]:
        filters = [
            OrderLog.request_payload.like(f"%{SOURCE_MODE}%"),
            OrderLog.response_payload.like(f"%{SOURCE_MODE}%"),
            OrderLog.last_sync_payload.like(f"%{SOURCE_MODE}%"),
            OrderLog.request_payload.like(f"%{SOURCE_TRIGGER}%"),
            OrderLog.response_payload.like(f"%{SOURCE_TRIGGER}%"),
            OrderLog.last_sync_payload.like(f"%{SOURCE_TRIGGER}%"),
        ]
        if related_order_ids:
            filters.append(OrderLog.id.in_(sorted(related_order_ids)))
        query = (
            db.query(OrderLog)
            .filter(OrderLog.created_at >= cutoff)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.side == SELL)
            .filter(or_(*filters))
        )
        if symbol:
            query = query.filter(
                or_(
                    OrderLog.symbol == symbol,
                    OrderLog.request_payload.like(f"%{symbol}%"),
                    OrderLog.response_payload.like(f"%{symbol}%"),
                    OrderLog.last_sync_payload.like(f"%{symbol}%"),
                )
            )
        return query.order_by(OrderLog.created_at.desc(), OrderLog.id.desc()).all()

    def _query_signal_rows(
        self,
        db: Session,
        *,
        cutoff: datetime,
        symbol: str | None,
    ) -> list[SignalLog]:
        query = (
            db.query(SignalLog)
            .filter(SignalLog.created_at >= cutoff)
            .filter(
                or_(
                    SignalLog.trigger_source == SOURCE_TRIGGER,
                    SignalLog.signal_status == SOURCE_TYPE,
                    SignalLog.reason.like(f"%{SOURCE_MODE}%"),
                    SignalLog.gating_notes.like(f"%{SOURCE_MODE}%"),
                    SignalLog.risk_flags.like(f"%{SOURCE_MODE}%"),
                )
            )
        )
        if symbol:
            query = query.filter(SignalLog.symbol == symbol)
        return query.order_by(SignalLog.created_at.desc(), SignalLog.id.desc()).all()


def _attempt_from_row(
    row: TradeRunLog,
    payload: dict[str, Any],
    *,
    include_raw: bool,
) -> dict[str, Any]:
    summary = _dict_value(payload.get("summary"))
    checks = _dict_value(payload.get("checks"))
    safety = _dict_value(payload.get("safety"))
    sell_result = _dict_value(payload.get("sell_result"))
    buy_result = _dict_value(payload.get("buy_result"))
    daily_limit = _dict_value(payload.get("daily_limit"))
    duplicate_check = _dict_value(payload.get("duplicate_order_check"))
    market_check = _dict_value(payload.get("market_session_check"))
    block_reasons = _normalize_reasons(
        _string_list(payload.get("block_reasons"))
        or _string_list(payload.get("blocked_by"))
        or _string_list(summary.get("top_block_reasons"))
    )
    primary_block_reason = _first_text(
        payload.get("primary_block_reason"),
        summary.get("primary_block_reason"),
        block_reasons[0] if block_reasons else None,
        row.reason,
    )
    if primary_block_reason and primary_block_reason not in block_reasons:
        block_reasons = _normalize_reasons([primary_block_reason] + block_reasons)
    symbol = _normalize_symbol(
        _first_text(
            payload.get("symbol"),
            summary.get("symbol"),
            sell_result.get("symbol"),
            row.symbol if row.symbol != "WATCHLIST" else None,
        )
    )
    company = _first_text(
        payload.get("company_name"),
        payload.get("company"),
        payload.get("name"),
        sell_result.get("company_name"),
        sell_result.get("company"),
        sell_result.get("name"),
    )
    child_summary = _child_sell_summary(sell_result)
    order_id = _int_value(
        payload.get("order_id"),
        payload.get("order_log_id"),
        summary.get("order_id"),
        sell_result.get("order_id"),
        sell_result.get("order_log_id"),
        row.order_id,
    )
    item = {
        "run_id": row.id,
        "created_at": _iso_datetime(row.created_at),
        "slot_label": _first_text(payload.get("slot_label"), summary.get("slot_label")),
        "trigger_source": _first_text(
            payload.get("trigger_source"),
            row.trigger_source,
            SOURCE_TRIGGER,
        ),
        "mode": _first_text(payload.get("mode"), row.mode, SOURCE_MODE),
        "result": _first_text(payload.get("result"), row.result, "blocked"),
        "action": _first_text(payload.get("action"), "hold"),
        "symbol": symbol,
        "company_name": company,
        "name": company,
        "primary_block_reason": primary_block_reason,
        "block_reasons": block_reasons,
        "sell_only": _bool_value(
            payload.get("sell_only"),
            payload.get("scheduler_sell_only"),
            safety.get("sell_only"),
            safety.get("scheduler_sell_only"),
            default=True,
        ),
        "buy_execution_allowed": _bool_value(
            payload.get("buy_execution_allowed"),
            safety.get("buy_execution_allowed"),
        ),
        "scheduler_real_orders_enabled": _bool_value(
            payload.get("scheduler_real_orders_enabled"),
            safety.get("scheduler_real_orders_enabled"),
        ),
        "kis_scheduler_sell_enabled": _bool_value(
            checks.get("kis_scheduler_sell_enabled"),
            safety.get("kis_scheduler_sell_enabled"),
        ),
        "kis_scheduler_allow_real_orders": _bool_value(
            checks.get("kis_scheduler_allow_real_orders"),
            safety.get("kis_scheduler_allow_real_orders"),
        ),
        "dry_run": _bool_value(checks.get("dry_run"), safety.get("dry_run")),
        "kill_switch": _bool_value(
            checks.get("kill_switch"),
            safety.get("kill_switch"),
        ),
        "kis_real_order_enabled": _bool_value(
            checks.get("kis_real_order_enabled"),
            safety.get("kis_real_order_enabled"),
        ),
        "kis_live_auto_sell_enabled": _bool_value(
            checks.get("kis_live_auto_sell_enabled"),
            safety.get("kis_live_auto_sell_enabled"),
        ),
        "stop_loss_enabled": _bool_value(
            checks.get("kis_limited_auto_stop_loss_enabled"),
            checks.get("kis_limited_auto_sell_stop_loss_enabled"),
            sell_result.get("stop_loss_execution_enabled"),
        ),
        "take_profit_enabled": _bool_value(
            checks.get("kis_limited_auto_take_profit_enabled"),
            checks.get("kis_limited_auto_sell_take_profit_enabled"),
            sell_result.get("take_profit_execution_enabled"),
        ),
        "real_order_submitted": _bool_value(payload.get("real_order_submitted")),
        "broker_submit_called": _bool_value(payload.get("broker_submit_called")),
        "manual_submit_called": _bool_value(payload.get("manual_submit_called")),
        "order_id": order_id,
        "broker_order_id": _first_text(
            payload.get("broker_order_id"),
            summary.get("broker_order_id"),
            sell_result.get("broker_order_id"),
        ),
        "kis_odno": _first_text(
            payload.get("kis_odno"),
            summary.get("kis_odno"),
            sell_result.get("kis_odno"),
        ),
        "quantity": _int_value(
            payload.get("quantity"),
            summary.get("quantity"),
            sell_result.get("quantity"),
            sell_result.get("qty"),
        ),
        "trigger": _first_text(
            payload.get("trigger"),
            summary.get("trigger"),
            sell_result.get("trigger"),
            sell_result.get("exit_trigger"),
        ),
        "child_sell_result": child_summary,
        "buy_result": _buy_result_summary(buy_result),
        "duplicate_order_check": duplicate_check,
        "daily_limit_snapshot": daily_limit,
        "market_session_snapshot": market_check,
        "validation_summary": _dict_value(
            sell_result.get("validation_summary")
            or sell_result.get("validation")
            or sell_result.get("order_validation")
        ),
        "validation_called": _bool_or_none(sell_result.get("validation_called")),
    }
    if include_raw:
        item["raw_payload"] = payload
    return sanitize_kis_payload(item)


def _child_sell_summary(sell_result: dict[str, Any]) -> dict[str, Any]:
    if not sell_result:
        return {}
    return sanitize_kis_payload(
        {
            "result": sell_result.get("result"),
            "action": sell_result.get("action"),
            "reason": sell_result.get("reason"),
            "source": sell_result.get("source"),
            "source_type": sell_result.get("source_type"),
            "mode": sell_result.get("mode"),
            "trigger_source": sell_result.get("trigger_source"),
            "symbol": _normalize_symbol(sell_result.get("symbol")),
            "company_name": _first_text(
                sell_result.get("company_name"),
                sell_result.get("company"),
                sell_result.get("name"),
            ),
            "quantity": _int_value(sell_result.get("quantity"), sell_result.get("qty")),
            "current_price": _number_value(sell_result.get("current_price")),
            "estimated_notional": _number_value(
                sell_result.get("estimated_notional"),
                sell_result.get("notional"),
            ),
            "trigger": _first_text(
                sell_result.get("trigger"),
                sell_result.get("exit_trigger"),
            ),
            "order_id": _int_value(
                sell_result.get("order_id"),
                sell_result.get("order_log_id"),
            ),
            "broker_order_id": sell_result.get("broker_order_id"),
            "kis_odno": sell_result.get("kis_odno"),
            "primary_block_reason": sell_result.get("primary_block_reason"),
            "block_reasons": _normalize_reasons(
                _string_list(sell_result.get("block_reasons"))
                or _string_list(sell_result.get("blocked_by"))
            ),
            "runtime_safety_snapshot": _dict_value(
                sell_result.get("runtime_safety_snapshot")
                or sell_result.get("runtime_snapshot")
            ),
            "market_session_snapshot": _dict_value(
                sell_result.get("market_session_snapshot")
                or sell_result.get("market_session")
            ),
            "duplicate_order_check": _dict_value(sell_result.get("duplicate_order_check")),
            "daily_limit_snapshot": _dict_value(
                sell_result.get("daily_limit")
                or sell_result.get("daily_limit_snapshot")
            ),
            "validation_summary": _dict_value(
                sell_result.get("validation_summary")
                or sell_result.get("validation")
                or sell_result.get("order_validation")
            ),
            "validation_called": _bool_or_none(sell_result.get("validation_called")),
            "real_order_submitted": _bool_value(sell_result.get("real_order_submitted")),
            "broker_submit_called": _bool_value(sell_result.get("broker_submit_called")),
            "manual_submit_called": _bool_value(sell_result.get("manual_submit_called")),
        }
    )


def _buy_result_summary(buy_result: dict[str, Any]) -> dict[str, Any]:
    if not buy_result:
        return {}
    return sanitize_kis_payload(
        {
            "result": buy_result.get("result"),
            "action": buy_result.get("action"),
            "reason": buy_result.get("reason"),
            "real_order_submitted": _bool_value(buy_result.get("real_order_submitted")),
            "broker_submit_called": _bool_value(buy_result.get("broker_submit_called")),
            "manual_submit_called": _bool_value(buy_result.get("manual_submit_called")),
            "validation_called": _bool_or_none(buy_result.get("validation_called")),
        }
    )


def _submitted_sell_from_attempt(
    attempt: dict[str, Any],
    *,
    order_by_id: dict[int, OrderLog],
    include_raw: bool,
) -> dict[str, Any]:
    child = _dict_value(attempt.get("child_sell_result"))
    order_id = _int_value(attempt.get("order_id"), child.get("order_id"))
    order = order_by_id.get(order_id or -1)
    order_payload = _order_payload(order)
    runtime_snapshot = _dict_value(
        child.get("runtime_safety_snapshot")
        or order_payload.get("runtime_safety_snapshot")
        or {
            "dry_run": attempt.get("dry_run"),
            "kill_switch": attempt.get("kill_switch"),
            "kis_real_order_enabled": attempt.get("kis_real_order_enabled"),
            "kis_scheduler_sell_enabled": attempt.get("kis_scheduler_sell_enabled"),
            "kis_scheduler_allow_real_orders": attempt.get(
                "kis_scheduler_allow_real_orders"
            ),
        }
    )
    qty = _number_value(
        child.get("quantity"),
        attempt.get("quantity"),
        getattr(order, "qty", None),
        getattr(order, "requested_qty", None),
    )
    current_price = _number_value(
        child.get("current_price"),
        order_payload.get("current_price"),
        getattr(order, "limit_price", None),
    )
    estimated_notional = _number_value(
        child.get("estimated_notional"),
        order_payload.get("estimated_notional"),
        order_payload.get("notional"),
        getattr(order, "notional", None),
    )
    if estimated_notional is None and qty is not None and current_price is not None:
        estimated_notional = qty * current_price
    item = {
        "order_id": order_id,
        "broker_order_id": _first_text(
            getattr(order, "broker_order_id", None),
            attempt.get("broker_order_id"),
            child.get("broker_order_id"),
        ),
        "kis_odno": _first_text(
            getattr(order, "kis_odno", None),
            attempt.get("kis_odno"),
            child.get("kis_odno"),
        ),
        "created_at": _iso_datetime(getattr(order, "created_at", None))
        or attempt.get("created_at"),
        "symbol": _normalize_symbol(
            _first_text(getattr(order, "symbol", None), attempt.get("symbol"), child.get("symbol"))
        ),
        "company_name": _first_text(attempt.get("company_name"), child.get("company_name")),
        "name": _first_text(attempt.get("name"), child.get("company_name")),
        "side": SELL,
        "quantity": int(qty) if qty is not None and qty.is_integer() else qty,
        "current_price": current_price,
        "estimated_notional": estimated_notional,
        "trigger": _first_text(attempt.get("trigger"), child.get("trigger")),
        "source": _first_text(child.get("source"), order_payload.get("source")),
        "source_type": _first_text(
            child.get("source_type"),
            order_payload.get("source_type"),
        ),
        "mode": _first_text(child.get("mode"), order_payload.get("mode"), attempt.get("mode")),
        "trigger_source": _first_text(
            child.get("trigger_source"),
            order_payload.get("trigger_source"),
            attempt.get("trigger_source"),
        ),
        "parent_scheduler_run_id": attempt.get("run_id"),
        "child_limited_auto_sell_run_id": _int_value(child.get("run_id")),
        "runtime_safety_snapshot": runtime_snapshot,
        "market_session_snapshot": _dict_value(
            child.get("market_session_snapshot")
            or attempt.get("market_session_snapshot")
            or order_payload.get("market_session_snapshot")
        ),
        "duplicate_order_check": _dict_value(
            child.get("duplicate_order_check")
            or attempt.get("duplicate_order_check")
            or order_payload.get("duplicate_order_check")
        ),
        "daily_limit_snapshot": _dict_value(
            child.get("daily_limit_snapshot")
            or attempt.get("daily_limit_snapshot")
            or order_payload.get("daily_limit_snapshot")
            or order_payload.get("daily_limit")
        ),
        "validation_summary": _dict_value(
            child.get("validation_summary")
            or attempt.get("validation_summary")
            or order_payload.get("validation_summary")
        ),
        "validation_called": _first_bool_or_none(
            child.get("validation_called"),
            attempt.get("validation_called"),
            order_payload.get("validation_called"),
        ),
        "real_order_submitted": attempt.get("real_order_submitted") is True,
        "broker_submit_called": attempt.get("broker_submit_called") is True,
        "manual_submit_called": attempt.get("manual_submit_called") is True,
        "broker_status": getattr(order, "broker_status", None),
        "internal_status": getattr(order, "internal_status", None),
    }
    if include_raw and order is not None:
        item["raw_order_payload"] = order_payload
    return sanitize_kis_payload(item)


def _blocked_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
    return sanitize_kis_payload(
        {
            "run_id": attempt.get("run_id"),
            "created_at": attempt.get("created_at"),
            "symbol": attempt.get("symbol"),
            "result": attempt.get("result"),
            "action": attempt.get("action"),
            "primary_block_reason": attempt.get("primary_block_reason"),
            "block_reasons": attempt.get("block_reasons") or [],
            "scheduler_real_orders_enabled": attempt.get("scheduler_real_orders_enabled"),
            "kis_scheduler_sell_enabled": attempt.get("kis_scheduler_sell_enabled"),
            "dry_run": attempt.get("dry_run"),
            "kill_switch": attempt.get("kill_switch"),
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "order_id": None,
        }
    )


def _summary(
    *,
    attempts: list[dict[str, Any]],
    submitted_sells: list[dict[str, Any]],
    daily_usage: list[dict[str, Any]],
    sell_only_invariant_ok: bool,
    no_direct_scheduler_submit_invariant_ok: bool,
    buy_execution_never_called: bool,
) -> dict[str, Any]:
    latest_attempt = attempts[0] if attempts else {}
    latest_submitted = submitted_sells[0] if submitted_sells else {}
    blocked = [item for item in attempts if _is_blocked_or_failed_attempt(item)]
    latest_blocked = blocked[0] if blocked else {}
    return {
        "total_attempts": len(attempts),
        "submitted_count": sum(1 for item in attempts if _is_submitted_attempt(item)),
        "blocked_count": sum(1 for item in attempts if item.get("result") == "blocked"),
        "failed_count": sum(1 for item in attempts if item.get("result") == "failed"),
        "skipped_count": sum(1 for item in attempts if item.get("result") == "skipped"),
        "stop_loss_submit_count": sum(
            1 for item in submitted_sells if item.get("trigger") == "stop_loss"
        ),
        "take_profit_submit_count": sum(
            1 for item in submitted_sells if item.get("trigger") == "take_profit"
        ),
        "duplicate_order_block_count": _count_reason(
            attempts,
            "duplicate_open_sell_order",
        ),
        "daily_limit_block_count": _count_reason(
            attempts,
            "daily_auto_sell_limit_reached",
            "daily_sell_limit_reached",
        ),
        "dry_run_block_count": _count_reason(
            attempts,
            "runtime_dry_run_true",
            "dry_run_true",
        ),
        "kill_switch_block_count": _count_reason(attempts, "kill_switch_enabled"),
        "scheduler_disabled_block_count": _count_reason(
            attempts,
            "scheduler_disabled",
            "kis_scheduler_disabled",
        ),
        "scheduler_sell_disabled_block_count": _count_reason(
            attempts,
            "scheduler_sell_disabled",
        ),
        "scheduler_real_orders_disabled_block_count": _count_reason(
            attempts,
            "scheduler_real_orders_disabled",
            "configured_scheduler_real_orders_disabled",
        ),
        "kis_real_order_disabled_block_count": _count_reason(
            attempts,
            "kis_real_order_disabled",
        ),
        "validation_failed_count": _count_reason(attempts, "validation_failed"),
        "no_candidate_count": _count_reason(
            attempts,
            "no_exit_candidate",
            "no_sell_candidate",
            "no_sell_candidates",
        ),
        "sell_only_invariant_ok": sell_only_invariant_ok,
        "no_direct_scheduler_submit_invariant_ok": (
            no_direct_scheduler_submit_invariant_ok
        ),
        "buy_execution_never_called": buy_execution_never_called,
        "submitted_rows_have_order_ids": all(
            item.get("order_id") is not None for item in submitted_sells
        ),
        "submitted_rows_have_kis_odno_count": sum(
            1 for item in submitted_sells if _first_text(item.get("kis_odno"))
        ),
        "submitted_rows_have_audit_metadata": all(
            _submitted_has_audit_metadata(item) for item in submitted_sells
        ),
        "max_daily_sell_count_observed": max(
            [int(item.get("submitted_sell_count") or 0) for item in daily_usage]
            or [0]
        ),
        "latest_attempt_at": latest_attempt.get("created_at"),
        "latest_submitted_at": latest_submitted.get("created_at"),
        "latest_blocked_at": latest_blocked.get("created_at"),
        "latest_symbol": latest_attempt.get("symbol"),
        "latest_result": latest_attempt.get("result"),
    }


def _top_block_reasons(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for item in attempts:
        counter.update(_string_list(item.get("block_reasons")))
        primary = _first_text(item.get("primary_block_reason"))
        if primary:
            counter[primary] += 1
    return [
        {"reason": reason, "label": _reason_label(reason), "count": count}
        for reason, count in counter.most_common(10)
    ]


def _daily_usage(submitted_sells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in submitted_sells:
        date_key = _kr_date_key(item.get("created_at"))
        if date_key:
            grouped[date_key].append(item)
    usage: list[dict[str, Any]] = []
    for date_key in sorted(grouped.keys(), reverse=True):
        rows = grouped[date_key]
        daily_limit = _daily_limit_for_rows(rows)
        symbols = sorted(
            {
                str(row.get("symbol") or "").strip()
                for row in rows
                if str(row.get("symbol") or "").strip()
            }
        )
        triggers = sorted(
            {
                str(row.get("trigger") or "").strip()
                for row in rows
                if str(row.get("trigger") or "").strip()
            }
        )
        total_notional = sum(
            float(row.get("estimated_notional") or 0)
            for row in rows
            if isinstance(row.get("estimated_notional"), (int, float))
        )
        usage.append(
            {
                "date": date_key,
                "submitted_sell_count": len(rows),
                "symbols": symbols,
                "triggers": triggers,
                "total_estimated_notional": round(total_notional, 2),
                "daily_limit": daily_limit,
                "limit_exceeded": len(rows) > daily_limit,
            }
        )
    return usage


def _safety_violations(
    *,
    attempts: list[dict[str, Any]],
    submitted_sells: list[dict[str, Any]],
    daily_usage: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for attempt in attempts:
        child = _dict_value(attempt.get("child_sell_result"))
        buy_result = _dict_value(attempt.get("buy_result"))
        child_present = _has_limited_auto_sell_child(child)
        if attempt.get("buy_execution_allowed") is True:
            violations.append(_violation("scheduler_guarded_sell_buy_execution_allowed", attempt))
        if str(attempt.get("action") or "").lower() == BUY:
            violations.append(_violation("scheduler_guarded_sell_action_buy", attempt))
        if _buy_result_submitted(buy_result):
            violations.append(_violation("scheduler_guarded_sell_buy_result_submitted", attempt))
            violations.append(_violation("child_limited_auto_buy_submitted", attempt))
        if attempt.get("broker_submit_called") is True and not child_present:
            violations.append(
                _violation("scheduler_broker_submit_without_limited_sell_child", attempt)
            )
        if attempt.get("manual_submit_called") is True and not child_present:
            violations.append(
                _violation("scheduler_manual_submit_without_limited_sell_child", attempt)
            )
        if _is_blocked_or_failed_attempt(attempt) and attempt.get("real_order_submitted") is True:
            violations.append(_violation("blocked_attempt_real_order_submitted", attempt))
        if _is_submitted_attempt(attempt):
            if attempt.get("order_id") is None:
                violations.append(_violation("submitted_attempt_missing_order_id", attempt))
            if not _submitted_attempt_has_source_metadata(attempt):
                violations.append(
                    _violation("submitted_attempt_missing_source_metadata", attempt)
                )
            if attempt.get("validation_called") is False:
                violations.append(
                    _violation("submitted_attempt_missing_validation_called", attempt)
                )
            if attempt.get("dry_run") is True:
                violations.append(_violation("submitted_attempt_while_dry_run", attempt))
            if attempt.get("kill_switch") is True:
                violations.append(
                    _violation("submitted_attempt_while_kill_switch", attempt)
                )
            if attempt.get("kis_scheduler_sell_enabled") is False:
                violations.append(
                    _violation("submitted_attempt_scheduler_sell_disabled", attempt)
                )
            if attempt.get("kis_scheduler_allow_real_orders") is False:
                violations.append(
                    _violation("submitted_attempt_scheduler_real_orders_disabled", attempt)
                )

    for usage in daily_usage:
        if usage.get("limit_exceeded") is True:
            violations.append(
                _violation(
                    "submitted_sell_daily_limit_exceeded",
                    {
                        "created_at": usage.get("date"),
                        "details": usage,
                    },
                )
            )

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in submitted_sells:
        symbol = str(item.get("symbol") or "").strip()
        date_key = _kr_date_key(item.get("created_at"))
        if symbol and date_key:
            grouped[(symbol, date_key)].append(item)
    for (symbol, date_key), rows in grouped.items():
        if len(rows) <= 1:
            continue
        violations.append(
            _violation(
                "duplicate_submitted_sell_same_symbol_day",
                {
                    "symbol": symbol,
                    "created_at": date_key,
                    "details": {
                        "order_ids": [row.get("order_id") for row in rows],
                        "submitted_sell_count": len(rows),
                    },
                },
            )
        )
    return violations


def _violation(reason: str, item: dict[str, Any]) -> dict[str, Any]:
    return sanitize_kis_payload(
        {
            "reason": reason,
            "label": _reason_label(reason),
            "severity": "warning",
            "run_id": item.get("run_id") or item.get("parent_scheduler_run_id"),
            "order_id": item.get("order_id"),
            "symbol": item.get("symbol"),
            "created_at": item.get("created_at"),
            "details": item.get("details") or {},
        }
    )


def _fallback_payload(row: TradeRunLog) -> dict[str, Any]:
    return {
        "mode": row.mode,
        "trigger_source": row.trigger_source,
        "result": row.result,
        "action": "hold",
        "symbol": row.symbol if row.symbol != "WATCHLIST" else None,
        "primary_block_reason": row.reason,
        "block_reasons": [row.reason] if row.reason else [],
        "sell_only": True,
        "buy_execution_allowed": False,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
    }


def _is_source_row(row: TradeRunLog, payload: dict[str, Any]) -> bool:
    return bool(
        row.mode == SOURCE_MODE
        or row.trigger_source == SOURCE_TRIGGER
        or payload.get("mode") == SOURCE_MODE
        or payload.get("trigger_source") == SOURCE_TRIGGER
        or payload.get("source") == SOURCE_MODE
        or payload.get("source_type") == SOURCE_TYPE
    )


def _order_payload(order: OrderLog | None) -> dict[str, Any]:
    if order is None:
        return {}
    merged: dict[str, Any] = {}
    for raw in (order.request_payload, order.response_payload, order.last_sync_payload):
        value = _json_dict(raw)
        if value:
            merged.update(value)
    for key in ("audit_metadata", "source_metadata"):
        value = _dict_value(merged.get(key))
        if value:
            merged.update(value)
    return merged


def _is_submitted_attempt(item: dict[str, Any]) -> bool:
    return item.get("result") == "submitted" or item.get("real_order_submitted") is True


def _is_blocked_or_failed_attempt(item: dict[str, Any]) -> bool:
    return str(item.get("result") or "").lower() in {"blocked", "failed", "skipped"}


def _has_limited_auto_sell_child(child: dict[str, Any]) -> bool:
    source = str(child.get("source") or "").lower()
    source_type = str(child.get("source_type") or "").lower()
    mode = str(child.get("mode") or "").lower()
    return bool(
        child
        and (
            "limited_auto_sell" in source
            or "limited_auto" in source
            or "guarded_stop_loss" in source_type
            or "guarded_take_profit" in source_type
            or "limited_auto" in mode
        )
    )


def _buy_result_submitted(value: dict[str, Any]) -> bool:
    return bool(
        str(value.get("result") or "").lower() == "submitted"
        or str(value.get("action") or "").lower() == BUY
        or value.get("real_order_submitted") is True
    )


def _submitted_attempt_has_source_metadata(attempt: dict[str, Any]) -> bool:
    child = _dict_value(attempt.get("child_sell_result"))
    return _first_text(child.get("source")) is not None and _first_text(
        child.get("source_type")
    ) is not None


def _submitted_has_audit_metadata(item: dict[str, Any]) -> bool:
    return _first_text(item.get("source")) is not None and _first_text(
        item.get("source_type")
    ) is not None


def _daily_limit_for_rows(rows: list[dict[str, Any]]) -> int:
    for row in rows:
        snapshot = _dict_value(row.get("daily_limit_snapshot"))
        value = _int_value(
            snapshot.get("max_orders_per_day"),
            snapshot.get("daily_limit"),
            snapshot.get("daily_sell_limit"),
        )
        if value is not None:
            return value
    return 1


def _count_reason(items: list[dict[str, Any]], *reasons: str) -> int:
    return sum(1 for item in items if _has_reason(item, *reasons))


def _has_reason(item: dict[str, Any], *reasons: str) -> bool:
    values = set(_string_list(item.get("block_reasons")))
    primary = _first_text(item.get("primary_block_reason"))
    if primary:
        values.add(primary)
    return bool(values.intersection(reasons))


def _normalize_reasons(values: list[str]) -> list[str]:
    mapping = {
        "daily_sell_limit_reached": "daily_auto_sell_limit_reached",
        "duplicate_open_order": "duplicate_open_sell_order",
        "dry_run_enabled": "runtime_dry_run_true",
        "dry_run_true": "runtime_dry_run_true",
        "no_candidate": "no_exit_candidate",
        "no_sell_candidate": "no_exit_candidate",
    }
    result: list[str] = []
    for value in values:
        normalized = mapping.get(str(value).strip(), str(value).strip())
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _reason_label(reason: str) -> str:
    return _BLOCK_REASON_LABELS.get(reason, reason.replace("_", " ").strip().title())


def _kr_date_key(value: Any) -> str | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return parsed.astimezone(KR_TZ).date().isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _clean(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text or None


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {"none", "null"}:
            return text
    return None


def _bool_value(*values: Any, default: bool = False) -> bool:
    for value in values:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y"}:
                return True
            if normalized in {"false", "0", "no", "n", ""}:
                return False
    return default


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n", ""}:
            return False
    return None


def _first_bool_or_none(*values: Any) -> bool | None:
    for value in values:
        parsed = _bool_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _number_value(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            text = str(value).replace(",", "").replace("%", "").strip()
            if not text:
                continue
            return float(text)
        except (TypeError, ValueError):
            continue
    return None


def _int_value(*values: Any) -> int | None:
    number = _number_value(*values)
    return int(number) if number is not None else None


def _normalize_symbol(symbol: Any) -> str | None:
    if symbol is None:
        return None
    value = str(symbol).strip().upper()
    if not value or value in {"NONE", "NULL", "WATCHLIST"}:
        return None
    if value.isdigit() and len(value) < 6:
        value = value.zfill(6)
    return value


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.astimezone(UTC).isoformat()


def _utc_now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    return _utc_now(value).replace(tzinfo=None)
