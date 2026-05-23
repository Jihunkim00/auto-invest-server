from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, RuntimeSetting, SignalLog, TradeRunLog
from app.services.kis_dry_run_risk_service import BUY, MARKET, PROVIDER
from app.services.kis_limited_auto_buy_service import (
    GUARDED_SOURCE_TYPE,
    PREFLIGHT_MODE,
    PREFLIGHT_TRIGGER_SOURCE,
    RUN_MODE,
    RUN_TRIGGER_SOURCE,
    SOURCE,
    SOURCE_TYPE,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.runtime_setting_service import RuntimeSettingService


REVIEW_MODE = "kis_limited_auto_buy_execution_review"
REVIEW_SOURCE_TYPE = "limited_auto_buy_execution_review_only"
KR_TZ = ZoneInfo("Asia/Seoul")

_REVIEW_MODES = {PREFLIGHT_MODE, RUN_MODE}
_REVIEW_TRIGGER_SOURCES = {PREFLIGHT_TRIGGER_SOURCE, RUN_TRIGGER_SOURCE}
_REVIEW_SOURCE_TYPES = {SOURCE_TYPE, GUARDED_SOURCE_TYPE, "buy_readiness_only"}

_SUBMITTED_INTERNAL_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}

_AUDIT_KEYS = {
    "source",
    "source_type",
    "mode",
    "trigger_source",
    "symbol",
    "company",
    "company_name",
    "name",
    "side",
    "quantity",
    "qty",
    "suggested_quantity",
    "estimated_notional",
    "notional",
    "current_price",
    "available_cash",
    "cash_available",
    "total_asset_value",
    "max_notional_pct",
    "final_buy_score",
    "final_score",
    "required_buy_score",
    "effective_min_entry_score",
    "final_sell_score",
    "confidence",
    "gate_level",
    "block_reasons",
    "primary_block_reason",
    "reason",
    "runtime_snapshot",
    "runtime_safety_snapshot",
    "market_session_snapshot",
    "cash_snapshot",
    "duplicate_order_check",
    "duplicate_check_snapshot",
    "duplicate_position",
    "duplicate_open_buy_order",
    "duplicate_open_order",
    "daily_limit",
    "daily_limit_summary",
    "validation_summary",
    "real_order_submitted",
    "broker_submit_called",
    "manual_submit_called",
    "validation_called",
}

_REASON_LABELS = {
    "buy_entry_not_allowed_now": "Entry window closed",
    "buy_sell_spread_too_weak": "Buy/sell spread too weak",
    "confidence_threshold_not_met": "Confidence threshold not met",
    "daily_auto_buy_limit_reached": "Daily buy limit reached",
    "daily_buy_limit_reached": "Daily buy limit reached",
    "duplicate_open_buy_order": "Duplicate open order",
    "duplicate_open_order": "Duplicate open order",
    "duplicate_position": "Duplicate position",
    "insufficient_cash": "Insufficient cash",
    "market_closed": "Market session blocked",
    "max_notional_exceeded": "Max notional exceeded",
    "no_new_entry_after_blocked": "No new entry after cutoff",
    "score_threshold_not_met": "Score threshold not met",
    "sell_pressure_too_high": "Sell pressure too high",
    "validation_failed": "Validation failed",
}


class KisLimitedAutoBuyExecutionReviewService:
    """Read-only operator audit for guarded KIS limited buy execution."""

    def __init__(self, runtime_settings: RuntimeSettingService | None = None):
        self.runtime_settings = runtime_settings or RuntimeSettingService()

    def review(
        self,
        db: Session,
        *,
        limit: int = 20,
        days: int = 30,
        symbol: str | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        safe_limit = min(max(int(limit or 20), 1), 100)
        safe_days = min(max(int(days or 30), 1), 365)
        normalized_symbol = _normalize_symbol(symbol)
        cutoff = _naive_utc(datetime.now(UTC) - timedelta(days=safe_days))
        runtime = self._runtime_settings_read_only(db)

        trade_rows = self._query_trade_rows(
            db,
            cutoff=cutoff,
            symbol=normalized_symbol,
        )
        signal_rows = self._query_signal_rows(
            db,
            cutoff=cutoff,
            symbol=normalized_symbol,
            excluded_signal_ids={row.signal_id for row in trade_rows if row.signal_id},
        )
        order_rows = self._query_order_rows(
            db,
            cutoff=cutoff,
            symbol=normalized_symbol,
            related_order_ids={row.order_id for row in trade_rows if row.order_id},
        )

        decisions = [
            _decision_from_trade_row(row, include_raw=include_raw)
            for row in trade_rows
        ]
        decisions.extend(
            _decision_from_signal_row(row, include_raw=include_raw)
            for row in signal_rows
        )
        decisions.sort(
            key=lambda item: (
                str(item.get("created_at") or ""),
                int(item.get("run_id") or item.get("signal_id") or 0),
            ),
            reverse=True,
        )

        runs_by_order_id = _runs_by_order_id(trade_rows)
        submitted_buys = [
            _submitted_buy_from_order(
                row,
                run_payloads=runs_by_order_id.get(int(row.id), []),
                include_raw=include_raw,
            )
            for row in order_rows
            if _is_submitted_buy_order(row)
        ]
        submitted_buys.sort(
            key=lambda item: (
                str(item.get("created_at") or ""),
                int(item.get("order_id") or 0),
            ),
            reverse=True,
        )

        blocked_decisions = [
            item for item in decisions if _is_blocked_decision(item)
        ]
        safety_violations = _safety_violations(
            decisions=decisions,
            submitted_buys=submitted_buys,
            daily_limit_default=int(
                runtime.get("kis_limited_auto_buy_max_orders_per_day", 1) or 1
            ),
        )
        no_submit_invariant_ok = not any(
            item["code"]
            in {
                "blocked_decision_real_order_submitted",
                "readiness_row_broker_submit_called",
            }
            for item in safety_violations
        )
        daily_usage = _daily_usage(
            submitted_buys,
            daily_limit_default=int(
                runtime.get("kis_limited_auto_buy_max_orders_per_day", 1) or 1
            ),
        )
        summary = _summary(
            decisions=decisions,
            submitted_buys=submitted_buys,
            daily_usage=daily_usage,
            no_submit_invariant_ok=no_submit_invariant_ok,
        )

        return sanitize_kis_payload(
            {
                "provider": PROVIDER,
                "market": MARKET,
                "mode": REVIEW_MODE,
                "source": SOURCE,
                "source_type": REVIEW_SOURCE_TYPE,
                "review_only": True,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "summary": summary,
                "recent_decisions": decisions[:safe_limit],
                "submitted_buys": submitted_buys[:safe_limit],
                "blocked_decisions": blocked_decisions[:safe_limit],
                "safety_violations": safety_violations[:safe_limit],
                "top_block_reasons": _top_block_reasons(blocked_decisions),
                "daily_usage": daily_usage,
                "safety": {
                    "review_only": True,
                    "no_broker_submit_from_review": True,
                    "scheduler_real_orders_enabled": False,
                    "configured_scheduler_real_orders_enabled": bool(
                        runtime.get("kis_scheduler_allow_real_orders", False)
                    ),
                    "live_auto_buy_default_safe": True,
                    "no_submit_invariant_ok": no_submit_invariant_ok,
                    "existing_buy_execution_unchanged": True,
                    "existing_sell_execution_unchanged": True,
                    "no_order_log_created": True,
                },
                "diagnostics": {
                    "trade_run_rows_scanned": len(trade_rows),
                    "signal_rows_scanned": len(signal_rows),
                    "order_rows_scanned": len(order_rows),
                    "recent_limit": safe_limit,
                    "days": safe_days,
                    "symbol_filter": normalized_symbol,
                    "include_raw": include_raw,
                    "source": SOURCE,
                    "source_types": sorted(_REVIEW_SOURCE_TYPES),
                    "source_modes": sorted(_REVIEW_MODES),
                    "source_trigger_sources": sorted(_REVIEW_TRIGGER_SOURCES),
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
                    TradeRunLog.mode.in_(sorted(_REVIEW_MODES)),
                    TradeRunLog.trigger_source.in_(sorted(_REVIEW_TRIGGER_SOURCES)),
                    TradeRunLog.request_payload.like(f"%{SOURCE}%"),
                    TradeRunLog.response_payload.like(f"%{SOURCE}%"),
                    TradeRunLog.request_payload.like(f"%{GUARDED_SOURCE_TYPE}%"),
                    TradeRunLog.response_payload.like(f"%{GUARDED_SOURCE_TYPE}%"),
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
        return (
            query.order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .all()
        )

    def _query_signal_rows(
        self,
        db: Session,
        *,
        cutoff: datetime,
        symbol: str | None,
        excluded_signal_ids: set[int | None],
    ) -> list[SignalLog]:
        query = (
            db.query(SignalLog)
            .filter(SignalLog.created_at >= cutoff)
            .filter(
                or_(
                    SignalLog.trigger_source.in_(sorted(_REVIEW_TRIGGER_SOURCES)),
                    SignalLog.signal_status.in_(sorted(_REVIEW_SOURCE_TYPES)),
                    SignalLog.reason.like(f"%{SOURCE}%"),
                    SignalLog.gating_notes.like(f"%{SOURCE}%"),
                    SignalLog.risk_flags.like(f"%{SOURCE}%"),
                )
            )
        )
        excluded = [value for value in excluded_signal_ids if value is not None]
        if excluded:
            query = query.filter(~SignalLog.id.in_(excluded))
        if symbol:
            query = query.filter(SignalLog.symbol == symbol)
        return (
            query.order_by(SignalLog.created_at.desc(), SignalLog.id.desc())
            .all()
        )

    def _query_order_rows(
        self,
        db: Session,
        *,
        cutoff: datetime,
        symbol: str | None,
        related_order_ids: set[int | None],
    ) -> list[OrderLog]:
        related_ids = [value for value in related_order_ids if value is not None]
        filters = [
            OrderLog.request_payload.like(f"%{SOURCE}%"),
            OrderLog.response_payload.like(f"%{SOURCE}%"),
            OrderLog.last_sync_payload.like(f"%{SOURCE}%"),
            OrderLog.request_payload.like(f"%{GUARDED_SOURCE_TYPE}%"),
            OrderLog.response_payload.like(f"%{GUARDED_SOURCE_TYPE}%"),
            OrderLog.last_sync_payload.like(f"%{GUARDED_SOURCE_TYPE}%"),
        ]
        if related_ids:
            filters.append(OrderLog.id.in_(related_ids))
        query = (
            db.query(OrderLog)
            .filter(OrderLog.created_at >= cutoff)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.side == BUY)
            .filter(or_(*filters))
        )
        if symbol:
            query = query.filter(
                or_(
                    OrderLog.symbol == symbol,
                    OrderLog.request_payload.like(f"%{symbol}%"),
                    OrderLog.response_payload.like(f"%{symbol}%"),
                )
            )
        return query.order_by(OrderLog.created_at.desc(), OrderLog.id.desc()).all()

    def _runtime_settings_read_only(self, db: Session) -> dict[str, Any]:
        row = db.query(RuntimeSetting).first()
        if row is None:
            return self.runtime_settings._defaults()
        return self.runtime_settings.get_settings(db)


def _decision_from_trade_row(
    row: TradeRunLog,
    *,
    include_raw: bool,
) -> dict[str, Any]:
    request_payload = _json_dict(row.request_payload)
    payload = _json_dict(row.response_payload)
    metadata = _merged_metadata(request_payload, payload)
    candidate = _candidate_payload(payload)
    diagnostics = _dict_value(payload.get("diagnostics"))
    duplicate_check = _dict_value(
        diagnostics.get("duplicate_order_check")
        or metadata.get("duplicate_order_check")
        or metadata.get("duplicate_check_snapshot")
    )
    daily_limit = _dict_value(
        payload.get("daily_limit")
        or payload.get("daily_limit_summary")
        or diagnostics.get("daily_limit_summary")
        or metadata.get("daily_limit_summary")
        or metadata.get("daily_limit")
    )
    block_reasons = _normalize_reasons(
        _string_list(payload.get("block_reasons"))
        or _string_list(payload.get("blocked_by"))
        or _string_list(payload.get("failed_checks"))
        or _string_list(candidate.get("block_reasons"))
        or _string_list(metadata.get("block_reasons"))
    )
    reason = _first_text(payload.get("reason"), metadata.get("reason"), row.reason)
    primary_block_reason = _first_text(
        payload.get("primary_block_reason"),
        metadata.get("primary_block_reason"),
        block_reasons[0] if block_reasons else None,
        reason if row.result == "blocked" else None,
    )
    if primary_block_reason and primary_block_reason not in block_reasons:
        block_reasons = _normalize_reasons([primary_block_reason] + block_reasons)

    symbol = _first_text(
        payload.get("symbol"),
        metadata.get("symbol"),
        candidate.get("symbol"),
        row.symbol if row.symbol != "WATCHLIST" else None,
    )
    company = _first_text(
        payload.get("company_name"),
        payload.get("company"),
        payload.get("name"),
        metadata.get("company_name"),
        metadata.get("company"),
        metadata.get("name"),
        candidate.get("company_name"),
        candidate.get("company"),
        candidate.get("name"),
    )
    result = _first_text(payload.get("result"), row.result, "blocked")
    action = _first_text(payload.get("action"), "hold")
    source_type = _first_text(
        payload.get("source_type"),
        metadata.get("source_type"),
        request_payload.get("source_type"),
        SOURCE_TYPE,
    )
    real_order_submitted = _bool_value(
        payload.get("real_order_submitted"),
        metadata.get("real_order_submitted"),
        request_payload.get("real_order_submitted"),
    )
    broker_submit_called = _bool_value(
        payload.get("broker_submit_called"),
        metadata.get("broker_submit_called"),
        request_payload.get("broker_submit_called"),
    )
    manual_submit_called = _bool_value(
        payload.get("manual_submit_called"),
        metadata.get("manual_submit_called"),
        request_payload.get("manual_submit_called"),
    )
    validation_called = _bool_value(
        payload.get("validation_called"),
        metadata.get("validation_called"),
        request_payload.get("validation_called"),
    )
    decision = {
        "run_id": row.id,
        "signal_id": _int_value(payload.get("signal_id")) or row.signal_id,
        "order_id": _int_value(payload.get("order_id"), row.order_id),
        "created_at": _iso_datetime(row.created_at),
        "source": _first_text(payload.get("source"), metadata.get("source"), SOURCE),
        "source_type": source_type,
        "mode": _first_text(payload.get("mode"), request_payload.get("mode"), row.mode),
        "trigger_source": _first_text(
            payload.get("trigger_source"),
            metadata.get("trigger_source"),
            row.trigger_source,
        ),
        "symbol": symbol,
        "company": company,
        "company_name": company,
        "name": company,
        "result": result,
        "action": action,
        "status": _decision_status(
            result=result,
            action=action,
            block_reasons=block_reasons,
            source_type=source_type,
        ),
        "primary_block_reason": primary_block_reason,
        "block_reasons": block_reasons,
        "final_buy_score": _number_value(
            payload.get("final_buy_score"),
            payload.get("final_score"),
            metadata.get("final_buy_score"),
            metadata.get("final_score"),
            candidate.get("final_buy_score"),
            candidate.get("final_score"),
        ),
        "required_buy_score": _number_value(
            payload.get("required_buy_score"),
            payload.get("effective_min_entry_score"),
            metadata.get("required_buy_score"),
            metadata.get("effective_min_entry_score"),
            candidate.get("required_buy_score"),
            candidate.get("effective_min_entry_score"),
        ),
        "final_sell_score": _number_value(
            payload.get("final_sell_score"),
            metadata.get("final_sell_score"),
            candidate.get("final_sell_score"),
        ),
        "confidence": _number_value(
            payload.get("confidence"),
            metadata.get("confidence"),
            candidate.get("confidence"),
        ),
        "estimated_notional": _number_value(
            payload.get("estimated_notional"),
            payload.get("notional"),
            metadata.get("estimated_notional"),
            metadata.get("notional"),
            candidate.get("estimated_notional"),
            candidate.get("suggested_notional"),
        ),
        "suggested_quantity": _int_value(
            payload.get("suggested_quantity"),
            payload.get("quantity"),
            payload.get("qty"),
            metadata.get("suggested_quantity"),
            metadata.get("quantity"),
            metadata.get("qty"),
            candidate.get("suggested_quantity"),
            candidate.get("quantity"),
        ),
        "cash_available": _number_value(
            payload.get("cash_available"),
            payload.get("available_cash"),
            metadata.get("cash_available"),
            metadata.get("available_cash"),
            candidate.get("cash_available"),
            candidate.get("available_cash"),
        ),
        "duplicate_position": _bool_value(
            payload.get("duplicate_position"),
            metadata.get("duplicate_position"),
            candidate.get("duplicate_position"),
            duplicate_check.get("duplicate_position"),
        ),
        "duplicate_open_order": _bool_value(
            payload.get("duplicate_open_order"),
            payload.get("duplicate_open_buy_order"),
            metadata.get("duplicate_open_order"),
            metadata.get("duplicate_open_buy_order"),
            candidate.get("duplicate_open_order"),
            candidate.get("duplicate_open_buy_order"),
            duplicate_check.get("duplicate_open_buy_order"),
        ),
        "daily_limit_remaining": _int_value(
            payload.get("daily_buy_limit_remaining"),
            metadata.get("daily_buy_limit_remaining"),
            daily_limit.get("daily_buy_limit_remaining"),
            candidate.get("daily_buy_limit_remaining"),
        ),
        "real_order_submitted": real_order_submitted,
        "broker_submit_called": broker_submit_called,
        "manual_submit_called": manual_submit_called,
        "validation_called": validation_called,
    }
    if include_raw:
        decision["raw_payload"] = {
            "request_payload": request_payload,
            "response_payload": payload,
        }
    return sanitize_kis_payload(decision)


def _decision_from_signal_row(
    row: SignalLog,
    *,
    include_raw: bool,
) -> dict[str, Any]:
    block_reasons = _normalize_reasons(
        _json_string_list(row.risk_flags) or _json_string_list(row.gating_notes)
    )
    source_type = _first_text(row.signal_status, SOURCE_TYPE)
    result = "submitted" if row.related_order_id else ("blocked" if row.hard_blocked else "readiness_only")
    action = _first_text(row.action, "hold")
    decision = {
        "run_id": None,
        "signal_id": row.id,
        "order_id": row.related_order_id,
        "created_at": _iso_datetime(row.created_at),
        "source": SOURCE,
        "source_type": source_type,
        "mode": RUN_MODE if row.trigger_source == RUN_TRIGGER_SOURCE else PREFLIGHT_MODE,
        "trigger_source": row.trigger_source,
        "symbol": _normalize_symbol(row.symbol),
        "company": None,
        "company_name": None,
        "name": None,
        "result": result,
        "action": action,
        "status": _decision_status(
            result=result,
            action=action,
            block_reasons=block_reasons,
            source_type=source_type,
        ),
        "primary_block_reason": row.hard_block_reason or (block_reasons[0] if block_reasons else None),
        "block_reasons": block_reasons,
        "final_buy_score": row.final_buy_score or row.buy_score,
        "required_buy_score": None,
        "final_sell_score": row.final_sell_score or row.sell_score,
        "confidence": row.confidence,
        "estimated_notional": None,
        "suggested_quantity": None,
        "cash_available": None,
        "duplicate_position": _has_reason_dict({"block_reasons": block_reasons}, "duplicate_position"),
        "duplicate_open_order": _has_reason_dict(
            {"block_reasons": block_reasons},
            "duplicate_open_buy_order",
            "duplicate_open_order",
        ),
        "daily_limit_remaining": None,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "validation_called": False,
    }
    if include_raw:
        decision["raw_payload"] = {
            "signal_status": row.signal_status,
            "risk_flags": _json_value(row.risk_flags),
            "gating_notes": _json_value(row.gating_notes),
        }
    return sanitize_kis_payload(decision)


def _submitted_buy_from_order(
    row: OrderLog,
    *,
    run_payloads: list[dict[str, Any]],
    include_raw: bool,
) -> dict[str, Any]:
    request_payload = _json_dict(row.request_payload)
    response_payload = _json_dict(row.response_payload)
    last_sync_payload = _json_dict(row.last_sync_payload)
    order_metadata = _merged_metadata(
        request_payload,
        response_payload,
        last_sync_payload,
    )
    metadata = _merged_metadata(
        *run_payloads,
        request_payload,
        response_payload,
        last_sync_payload,
    )
    run_payload = run_payloads[0] if run_payloads else {}
    diagnostics = _dict_value(run_payload.get("diagnostics"))
    validation_summary = _dict_value(
        metadata.get("validation_summary")
        or response_payload.get("validation_summary")
        or diagnostics.get("validation_summary")
    )
    daily_limit = _dict_value(
        metadata.get("daily_limit_summary")
        or metadata.get("daily_limit")
        or diagnostics.get("daily_limit_summary")
        or run_payload.get("daily_limit_summary")
        or run_payload.get("daily_limit")
    )
    duplicate_check = _dict_value(
        metadata.get("duplicate_order_check")
        or metadata.get("duplicate_check_snapshot")
        or diagnostics.get("duplicate_order_check")
    )
    runtime_snapshot = _dict_value(
        metadata.get("runtime_safety_snapshot")
        or metadata.get("runtime_snapshot")
        or diagnostics.get("runtime_snapshot")
    )
    market_snapshot = _dict_value(
        metadata.get("market_session_snapshot")
        or diagnostics.get("market_session_snapshot")
    )
    quantity = _number_value(
        row.requested_qty,
        row.qty,
        metadata.get("quantity"),
        metadata.get("suggested_quantity"),
        run_payload.get("quantity"),
        run_payload.get("suggested_quantity"),
    )
    current_price = _number_value(
        metadata.get("current_price"),
        run_payload.get("current_price"),
        validation_summary.get("current_price"),
    )
    estimated_notional = _number_value(
        row.notional,
        metadata.get("estimated_notional"),
        metadata.get("notional"),
        run_payload.get("estimated_notional"),
        run_payload.get("notional"),
        validation_summary.get("estimated_amount"),
    )
    if estimated_notional is None and quantity is not None and current_price is not None:
        estimated_notional = round(float(quantity) * float(current_price), 2)
    source = _first_text(metadata.get("source"), response_payload.get("source"), request_payload.get("source"))
    source_type = _first_text(
        metadata.get("source_type"),
        response_payload.get("source_type"),
        request_payload.get("source_type"),
    )
    real_order_submitted = _bool_value(
        response_payload.get("real_order_submitted"),
        request_payload.get("real_order_submitted"),
        metadata.get("real_order_submitted"),
        metadata.get("limited_auto_buy_real_order_submitted"),
        _is_submitted_status(row.internal_status),
    )
    broker_submit_called = _bool_value(
        response_payload.get("broker_submit_called"),
        request_payload.get("broker_submit_called"),
        metadata.get("broker_submit_called"),
        metadata.get("limited_auto_buy_broker_submit_called"),
        _is_submitted_status(row.internal_status),
    )
    manual_submit_called = _bool_value(
        response_payload.get("manual_submit_called"),
        request_payload.get("manual_submit_called"),
        metadata.get("manual_submit_called"),
        metadata.get("limited_auto_buy_manual_submit_called"),
        _is_submitted_status(row.internal_status),
    )
    validation_called = _bool_value(
        response_payload.get("validation_called"),
        request_payload.get("validation_called"),
        metadata.get("validation_called"),
        run_payload.get("validation_called"),
    )
    item = {
        "order_id": row.id,
        "broker_order_id": row.broker_order_id or response_payload.get("broker_order_id"),
        "kis_odno": row.kis_odno or row.broker_order_id or response_payload.get("kis_odno"),
        "created_at": _iso_datetime(row.created_at),
        "symbol": _normalize_symbol(
            row.symbol
            or metadata.get("symbol")
            or run_payload.get("symbol")
            or response_payload.get("symbol")
        ),
        "company": _first_text(
            metadata.get("company_name"),
            metadata.get("company"),
            metadata.get("name"),
            run_payload.get("company_name"),
            run_payload.get("company"),
            run_payload.get("name"),
        ),
        "company_name": _first_text(
            metadata.get("company_name"),
            metadata.get("company"),
            metadata.get("name"),
            run_payload.get("company_name"),
            run_payload.get("company"),
            run_payload.get("name"),
        ),
        "name": _first_text(
            metadata.get("name"),
            metadata.get("company_name"),
            metadata.get("company"),
            run_payload.get("name"),
            run_payload.get("company_name"),
        ),
        "quantity": int(quantity) if quantity is not None else None,
        "estimated_notional": estimated_notional,
        "current_price": current_price,
        "final_buy_score": _number_value(
            metadata.get("final_buy_score"),
            metadata.get("final_score"),
            run_payload.get("final_buy_score"),
            run_payload.get("final_score"),
        ),
        "required_buy_score": _number_value(
            metadata.get("required_buy_score"),
            metadata.get("effective_min_entry_score"),
            run_payload.get("required_buy_score"),
            run_payload.get("effective_min_entry_score"),
        ),
        "final_sell_score": _number_value(
            metadata.get("final_sell_score"),
            run_payload.get("final_sell_score"),
        ),
        "confidence": _number_value(
            metadata.get("confidence"),
            run_payload.get("confidence"),
        ),
        "gate_level": _int_value(metadata.get("gate_level"), run_payload.get("gate_level")),
        "available_cash": _number_value(
            metadata.get("available_cash"),
            metadata.get("cash_available"),
            run_payload.get("available_cash"),
            run_payload.get("cash_available"),
        ),
        "max_notional_pct": _number_value(
            metadata.get("max_notional_pct"),
            run_payload.get("max_notional_pct"),
        ),
        "total_asset_value": _number_value(
            metadata.get("total_asset_value"),
            run_payload.get("total_asset_value"),
        ),
        "daily_limit_snapshot": daily_limit,
        "duplicate_check_snapshot": duplicate_check,
        "market_session_snapshot": market_snapshot,
        "runtime_safety_snapshot": runtime_snapshot,
        "validation_summary": validation_summary,
        "source": source,
        "source_type": source_type,
        "order_audit_metadata_present": (
            order_metadata.get("source") == SOURCE
            and bool(order_metadata.get("source_type"))
        ),
        "mode": _first_text(metadata.get("mode"), response_payload.get("mode"), request_payload.get("mode")),
        "trigger_source": _first_text(
            metadata.get("trigger_source"),
            response_payload.get("trigger_source"),
            request_payload.get("trigger_source"),
        ),
        "real_order_submitted": real_order_submitted,
        "broker_submit_called": broker_submit_called,
        "manual_submit_called": manual_submit_called,
        "validation_called": validation_called,
        "broker_status": row.broker_status or response_payload.get("broker_status"),
        "internal_status": row.internal_status,
        "broker_order_status": row.broker_order_status or row.broker_status,
    }
    if include_raw:
        item["raw_payload"] = {
            "request_payload": request_payload,
            "response_payload": response_payload,
            "last_sync_payload": last_sync_payload,
            "run_payloads": run_payloads,
        }
    return sanitize_kis_payload(item)


def _summary(
    *,
    decisions: list[dict[str, Any]],
    submitted_buys: list[dict[str, Any]],
    daily_usage: list[dict[str, Any]],
    no_submit_invariant_ok: bool,
) -> dict[str, Any]:
    blocked = [item for item in decisions if _is_blocked_decision(item)]
    readiness = [item for item in decisions if _is_readiness_decision(item)]
    latest_submitted = submitted_buys[0] if submitted_buys else None
    latest_blocked = blocked[0] if blocked else None
    latest_symbol = _first_text(
        latest_submitted.get("symbol") if latest_submitted else None,
        latest_blocked.get("symbol") if latest_blocked else None,
        next((item.get("symbol") for item in decisions if item.get("symbol")), None),
    )
    return {
        "total_decisions": len(decisions),
        "submitted_buy_count": len(submitted_buys),
        "blocked_count": len(blocked),
        "readiness_only_count": len(readiness),
        "validation_failed_count": _count_reason(decisions, "validation_failed"),
        "duplicate_position_block_count": sum(
            1
            for item in blocked
            if item.get("duplicate_position") or _has_reason_dict(item, "duplicate_position")
        ),
        "duplicate_open_order_block_count": sum(
            1
            for item in blocked
            if item.get("duplicate_open_order")
            or _has_reason_dict(item, "duplicate_open_buy_order", "duplicate_open_order")
        ),
        "daily_limit_block_count": _count_reason(
            blocked,
            "daily_auto_buy_limit_reached",
            "daily_buy_limit_reached",
        ),
        "cash_block_count": _count_reason(blocked, "insufficient_cash"),
        "max_notional_block_count": _count_reason(
            blocked,
            "max_notional_exceeded",
            "notional_cap_exceeded",
        ),
        "market_session_block_count": _count_reason(
            blocked,
            "market_closed",
            "buy_entry_not_allowed_now",
        ),
        "no_new_entry_after_block_count": _count_reason(
            blocked,
            "no_new_entry_after_blocked",
        ),
        "score_block_count": _count_reason(
            blocked,
            "score_threshold_not_met",
            "confidence_threshold_not_met",
        ),
        "sell_pressure_block_count": _count_reason(
            blocked,
            "sell_pressure_too_high",
        ),
        "buy_sell_spread_block_count": _count_reason(
            blocked,
            "buy_sell_spread_too_weak",
        ),
        "no_submit_invariant_ok": no_submit_invariant_ok,
        "submitted_rows_have_audit_metadata": all(
            _has_submitted_audit_metadata(item) for item in submitted_buys
        ),
        "submitted_rows_have_order_ids": all(
            item.get("order_id") is not None for item in submitted_buys
        ),
        "submitted_rows_have_kis_odno_count": sum(
            1 for item in submitted_buys if _first_text(item.get("kis_odno"))
        ),
        "max_daily_buy_count_observed": max(
            [int(item.get("submitted_buy_count") or 0) for item in daily_usage] or [0]
        ),
        "latest_submitted_at": latest_submitted.get("created_at") if latest_submitted else None,
        "latest_blocked_at": latest_blocked.get("created_at") if latest_blocked else None,
        "latest_symbol": latest_symbol,
    }


def _top_block_reasons(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for decision in decisions:
        for reason in decision.get("block_reasons") or []:
            if reason:
                counter[reason] += 1
    return [
        {"reason": reason, "count": count, "label": _reason_label(reason)}
        for reason, count in counter.most_common()
    ]


def _daily_usage(
    submitted_buys: list[dict[str, Any]],
    *,
    daily_limit_default: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in submitted_buys:
        date_key = _kr_date_key(item.get("created_at"))
        if date_key:
            grouped[date_key].append(item)
    usage: list[dict[str, Any]] = []
    for date_key in sorted(grouped.keys(), reverse=True):
        rows = grouped[date_key]
        daily_limit = _daily_limit_for_rows(rows, daily_limit_default)
        symbols = sorted(
            {
                str(row.get("symbol") or "").strip()
                for row in rows
                if str(row.get("symbol") or "").strip()
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
                "submitted_buy_count": len(rows),
                "symbols": symbols,
                "total_estimated_notional": round(total_notional, 2),
                "daily_limit": daily_limit,
                "limit_exceeded": len(rows) > daily_limit,
            }
        )
    return usage


def _safety_violations(
    *,
    decisions: list[dict[str, Any]],
    submitted_buys: list[dict[str, Any]],
    daily_limit_default: int,
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for decision in decisions:
        if _is_blocked_decision(decision) and decision.get("real_order_submitted") is True:
            violations.append(
                _violation(
                    "blocked_decision_real_order_submitted",
                    "Blocked decision recorded real_order_submitted=true.",
                    symbol=decision.get("symbol"),
                    run_id=decision.get("run_id"),
                    signal_id=decision.get("signal_id"),
                    created_at=decision.get("created_at"),
                )
            )
        if _is_readiness_or_preflight_row(decision) and decision.get("broker_submit_called") is True:
            violations.append(
                _violation(
                    "readiness_row_broker_submit_called",
                    "Readiness/preflight row recorded broker_submit_called=true.",
                    symbol=decision.get("symbol"),
                    run_id=decision.get("run_id"),
                    signal_id=decision.get("signal_id"),
                    created_at=decision.get("created_at"),
                )
            )

    for item in submitted_buys:
        if not _has_submitted_audit_metadata(item):
            violations.append(
                _violation(
                    "submitted_buy_missing_source_metadata",
                    "Submitted buy is missing source/source_type audit metadata.",
                    symbol=item.get("symbol"),
                    order_id=item.get("order_id"),
                    created_at=item.get("created_at"),
                    details={
                        "source": item.get("source"),
                        "source_type": item.get("source_type"),
                    },
                )
            )
        if item.get("order_id") is None:
            violations.append(
                _violation(
                    "submitted_buy_missing_order_id",
                    "Submitted buy is missing an order_id.",
                    symbol=item.get("symbol"),
                    created_at=item.get("created_at"),
                )
            )
        if _snapshot_bool(item.get("runtime_safety_snapshot"), "dry_run") is True:
            violations.append(
                _violation(
                    "submitted_buy_while_dry_run",
                    "Submitted buy metadata recorded dry_run=true.",
                    symbol=item.get("symbol"),
                    order_id=item.get("order_id"),
                    created_at=item.get("created_at"),
                )
            )
        if _snapshot_bool(item.get("runtime_safety_snapshot"), "kill_switch") is True:
            violations.append(
                _violation(
                    "submitted_buy_while_kill_switch",
                    "Submitted buy metadata recorded kill_switch=true.",
                    symbol=item.get("symbol"),
                    order_id=item.get("order_id"),
                    created_at=item.get("created_at"),
                )
            )
        if _scheduler_enabled_in_item(item):
            violations.append(
                _violation(
                    "submitted_buy_while_scheduler_real_orders_enabled",
                    "Submitted buy metadata recorded scheduler real orders enabled.",
                    symbol=item.get("symbol"),
                    order_id=item.get("order_id"),
                    created_at=item.get("created_at"),
                )
            )
        if _snapshot_bool(item.get("market_session_snapshot"), "no_new_entry_after_blocked") is True:
            violations.append(
                _violation(
                    "submitted_buy_after_no_new_entry_after",
                    "Submitted buy metadata indicates no_new_entry_after was already blocked.",
                    symbol=item.get("symbol"),
                    order_id=item.get("order_id"),
                    created_at=item.get("created_at"),
                )
            )
        if item.get("validation_called") is not True:
            violations.append(
                _violation(
                    "submitted_buy_missing_validation_called",
                    "Submitted buy is missing validation_called=true.",
                    symbol=item.get("symbol"),
                    order_id=item.get("order_id"),
                    created_at=item.get("created_at"),
                )
            )
        max_notional_violation = _max_notional_violation(item)
        if max_notional_violation:
            violations.append(max_notional_violation)

    for usage in _daily_usage(
        submitted_buys,
        daily_limit_default=daily_limit_default,
    ):
        if usage.get("limit_exceeded") is True:
            violations.append(
                _violation(
                    "submitted_buy_daily_limit_exceeded",
                    "Submitted buys exceeded the configured daily limited-buy cap.",
                    created_at=usage.get("date"),
                    details=usage,
                )
            )

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in submitted_buys:
        symbol = str(item.get("symbol") or "").strip()
        date_key = _kr_date_key(item.get("created_at"))
        if symbol and date_key:
            grouped[(symbol, date_key)].append(item)
    for (symbol, date_key), rows in grouped.items():
        if len(rows) <= 1:
            continue
        violations.append(
            _violation(
                "duplicate_submitted_buy_same_symbol_day",
                "Multiple submitted buys were recorded for the same symbol/day.",
                symbol=symbol,
                created_at=date_key,
                details={
                    "order_ids": [row.get("order_id") for row in rows],
                    "submitted_buy_count": len(rows),
                },
            )
        )
    return violations


def _max_notional_violation(item: dict[str, Any]) -> dict[str, Any] | None:
    estimated = _number_value(item.get("estimated_notional"))
    pct = _number_value(item.get("max_notional_pct"))
    total_asset_value = _number_value(item.get("total_asset_value"))
    if estimated is None or pct is None or total_asset_value is None:
        return None
    max_allowed = total_asset_value * pct
    if estimated <= max_allowed:
        return None
    return _violation(
        "submitted_buy_max_notional_pct_exceeded",
        "Submitted buy exceeds max_notional_pct based on available metadata.",
        symbol=item.get("symbol"),
        order_id=item.get("order_id"),
        created_at=item.get("created_at"),
        details={
            "estimated_notional": estimated,
            "total_asset_value": total_asset_value,
            "max_notional_pct": pct,
            "max_allowed_notional": round(max_allowed, 2),
        },
    )


def _runs_by_order_id(rows: list[TradeRunLog]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.order_id is None:
            continue
        grouped[int(row.order_id)].append(_json_dict(row.response_payload))
    for payloads in grouped.values():
        payloads.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return grouped


def _is_submitted_buy_order(row: OrderLog) -> bool:
    return str(row.side or "").lower() == BUY and _is_submitted_status(row.internal_status)


def _is_submitted_status(value: Any) -> bool:
    return str(value or "").upper() in _SUBMITTED_INTERNAL_STATUSES


def _is_blocked_decision(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").upper()
    result = str(item.get("result") or "").lower()
    if status == "SUBMITTED" or result == "submitted":
        return False
    return result == "blocked" or status in {"BLOCKED", "WATCH", "HOLD"}


def _is_readiness_decision(item: dict[str, Any]) -> bool:
    result = str(item.get("result") or "").lower()
    action = str(item.get("action") or "").lower()
    source_type = str(item.get("source_type") or "")
    return (
        source_type == SOURCE_TYPE
        or result in {"ready", "readiness_only"}
        or action == "buy_ready"
    )


def _is_readiness_or_preflight_row(item: dict[str, Any]) -> bool:
    return _is_readiness_decision(item) or item.get("mode") == PREFLIGHT_MODE


def _has_submitted_audit_metadata(item: dict[str, Any]) -> bool:
    if "order_audit_metadata_present" in item:
        return (
            item.get("order_audit_metadata_present") is True
            and item.get("source") == SOURCE
            and bool(item.get("source_type"))
        )
    return item.get("source") == SOURCE and bool(item.get("source_type"))


def _daily_limit_for_rows(
    rows: list[dict[str, Any]],
    daily_limit_default: int,
) -> int:
    for row in rows:
        snapshot = _dict_value(row.get("daily_limit_snapshot"))
        value = _int_value(
            snapshot.get("daily_buy_limit"),
            snapshot.get("daily_limit"),
            snapshot.get("max_orders_per_day"),
        )
        if value is not None:
            return value
    return daily_limit_default


def _decision_status(
    *,
    result: str | None,
    action: str | None,
    block_reasons: list[str],
    source_type: str | None,
) -> str:
    normalized_result = str(result or "").lower()
    normalized_action = str(action or "").lower()
    if normalized_result == "submitted" or normalized_action == BUY:
        return "SUBMITTED"
    if (
        normalized_action == "buy_ready"
        or normalized_result in {"ready", "readiness_only"}
        or source_type == SOURCE_TYPE
    ):
        return "BUY_READY" if not block_reasons else "BLOCKED"
    if block_reasons:
        if any(
            reason
            in {
                "score_threshold_not_met",
                "buy_sell_spread_too_weak",
                "sell_pressure_too_high",
                "confidence_threshold_not_met",
            }
            for reason in block_reasons
        ):
            return "WATCH"
        return "BLOCKED"
    return "HOLD"


def _candidate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("final_candidate", "candidate"):
        value = payload.get(key)
        if isinstance(value, dict):
            return dict(value)
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        for item in candidates:
            if isinstance(item, dict):
                return dict(item)
    return {}


def _merged_metadata(*payloads: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key in ("source_metadata", "audit_metadata"):
            value = payload.get(key)
            if isinstance(value, dict):
                merged.update(value)
        for key in _AUDIT_KEYS:
            if key in payload and payload[key] is not None:
                merged[key] = payload[key]
    return merged


def _normalize_reasons(values: list[str]) -> list[str]:
    mapping = {
        "daily_buy_limit_reached": "daily_auto_buy_limit_reached",
        "entry_not_allowed_now": "buy_entry_not_allowed_now",
        "open_buy_order_exists": "duplicate_open_buy_order",
        "open_order_exists": "duplicate_open_buy_order",
        "position_already_exists": "duplicate_position",
        "position_exists": "duplicate_position",
        "notional_cap_exceeded": "max_notional_exceeded",
    }
    result: list[str] = []
    for value in values:
        normalized = mapping.get(str(value).strip(), str(value).strip())
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _count_reason(items: list[dict[str, Any]], *reasons: str) -> int:
    return sum(1 for item in items if _has_reason_dict(item, *reasons))


def _has_reason_dict(item: dict[str, Any], *reasons: str) -> bool:
    block_reasons = set(item.get("block_reasons") or [])
    return bool(
        block_reasons.intersection(reasons)
        or item.get("primary_block_reason") in reasons
        or item.get("reason") in reasons
    )


def _reason_label(reason: str) -> str:
    return _REASON_LABELS.get(reason, reason.replace("_", " ").strip().title())


def _violation(
    code: str,
    reason: str,
    *,
    symbol: Any = None,
    order_id: Any = None,
    run_id: Any = None,
    signal_id: Any = None,
    created_at: Any = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return sanitize_kis_payload(
        {
            "code": code,
            "reason": reason,
            "severity": "warning",
            "symbol": symbol,
            "order_id": order_id,
            "run_id": run_id,
            "signal_id": signal_id,
            "created_at": created_at,
            "details": details or {},
        }
    )


def _scheduler_enabled_in_item(item: dict[str, Any]) -> bool:
    runtime = _dict_value(item.get("runtime_safety_snapshot"))
    return any(
        _bool_value(runtime.get(key), item.get(key)) is True
        for key in (
            "scheduler_real_orders_enabled",
            "kis_scheduler_allow_real_orders",
            "scheduler_real_order_enabled",
        )
    )


def _snapshot_bool(value: Any, key: str) -> bool | None:
    snapshot = _dict_value(value)
    if key not in snapshot:
        return None
    return _bool_value(snapshot.get(key))


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
    parsed = _json_value(value)
    return parsed if isinstance(parsed, dict) else {}


def _json_value(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _json_string_list(value: str | None) -> list[str]:
    parsed = _json_value(value)
    return _string_list(parsed)


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


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "none":
            return text
    return None


def _bool_value(*values: Any) -> bool:
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
    return False


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
    if not value or value == "NONE":
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


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
