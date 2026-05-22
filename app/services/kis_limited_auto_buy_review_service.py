from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import RuntimeSetting, TradeRunLog
from app.services.kis_dry_run_risk_service import MARKET, PROVIDER
from app.services.kis_limited_auto_buy_service import (
    PREFLIGHT_MODE,
    PREFLIGHT_TRIGGER_SOURCE,
    RUN_MODE,
    RUN_TRIGGER_SOURCE,
    SOURCE,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.runtime_setting_service import RuntimeSettingService


REVIEW_MODE = "kis_limited_auto_buy_review"
REVIEW_SOURCE_TYPE = "buy_readiness_review_only"
REVIEW_MODES = {PREFLIGHT_MODE, RUN_MODE}
REVIEW_TRIGGER_SOURCES = {PREFLIGHT_TRIGGER_SOURCE, RUN_TRIGGER_SOURCE}

_SAFETY_BLOCK_REASONS = {
    "auto_buy_execution_disabled",
    "live_auto_buy_disabled",
    "live_auto_buy_must_remain_disabled",
    "limited_auto_buy_disabled",
    "dry_run_blocks_real_submit",
    "kis_real_order_disabled",
    "scheduler_real_orders_disabled",
}

_WATCH_REASONS = {
    "score_threshold_not_met",
    "buy_sell_spread_too_weak",
    "sell_pressure_too_high",
    "confidence_threshold_not_met",
    "missing_indicators",
}

_REASON_LABELS = {
    "account_state_unavailable": "Account state unavailable",
    "auto_buy_execution_disabled": "Auto buy execution disabled",
    "buy_entry_not_allowed_now": "Entry window closed",
    "buy_readiness_disabled": "Buy readiness disabled",
    "confidence_threshold_not_met": "Confidence threshold not met",
    "current_price_unavailable": "Current price unavailable",
    "daily_buy_limit_reached": "Daily buy limit reached",
    "duplicate_open_buy_order": "Duplicate open order",
    "duplicate_open_order": "Duplicate open order",
    "duplicate_position": "Duplicate position",
    "existing_sell_guards_not_ready": "Existing sell guards not ready",
    "gpt_hard_block_new_buy": "GPT hard block",
    "insufficient_cash": "Insufficient cash",
    "kill_switch_enabled": "Kill switch enabled",
    "kis_disabled": "KIS disabled",
    "market_closed": "Market session blocked",
    "missing_indicators": "Missing indicators",
    "no_candidate": "No candidate",
    "no_new_entry_after_blocked": "No new entry after cutoff",
    "notional_cap_exceeded": "Notional cap exceeded",
    "same_day_reentry_blocked": "Same-day re-entry blocked",
    "score_threshold_not_met": "Score threshold not met",
    "sell_pressure_too_high": "Sell pressure too high",
}


class KisLimitedAutoBuyReviewService:
    """Read-only review for KIS limited buy readiness decisions."""

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
        runtime = self._runtime_settings_read_only(db)
        cutoff = _naive_utc(datetime.now(UTC) - timedelta(days=safe_days))

        rows = self._query_rows(
            db,
            cutoff=cutoff,
            symbol=normalized_symbol,
        )
        decisions = [
            _decision_from_row(row, include_raw=include_raw)
            for row in rows
        ]
        recent = decisions[:safe_limit]
        no_submit_invariant_ok = all(
            not decision["real_order_submitted"]
            and not decision["broker_submit_called"]
            and not decision["manual_submit_called"]
            for decision in decisions
        )
        summary = _summary(decisions, no_submit_invariant_ok=no_submit_invariant_ok)
        top_block_reasons = _top_block_reasons(decisions)
        latest_buy_ready = next(
            (decision for decision in decisions if decision["status"] == "BUY_READY"),
            None,
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
                "recent_decisions": recent,
                "top_block_reasons": top_block_reasons,
                "latest_buy_ready": latest_buy_ready,
                "safety": _safety(
                    runtime,
                    no_submit_invariant_ok=no_submit_invariant_ok,
                ),
                "diagnostics": {
                    "rows_scanned": len(rows),
                    "recent_limit": safe_limit,
                    "days": safe_days,
                    "symbol_filter": normalized_symbol,
                    "include_raw": include_raw,
                    "source_modes": sorted(REVIEW_MODES),
                    "source_trigger_sources": sorted(REVIEW_TRIGGER_SOURCES),
                    "price_review_metrics": {
                        "available": False,
                        "reason": (
                            "not_available_from_stored_limited_buy_logs_without_"
                            "additional_market_data_calls"
                        ),
                    },
                },
            }
        )

    def _query_rows(
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
                    TradeRunLog.mode.in_(sorted(REVIEW_MODES)),
                    TradeRunLog.trigger_source.in_(sorted(REVIEW_TRIGGER_SOURCES)),
                    TradeRunLog.request_payload.like(f"%{SOURCE}%"),
                    TradeRunLog.response_payload.like(f"%{SOURCE}%"),
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

    def _runtime_settings_read_only(self, db: Session) -> dict[str, Any]:
        row = db.query(RuntimeSetting).first()
        if row is None:
            return self.runtime_settings._defaults()
        return self.runtime_settings.get_settings(db)


def _decision_from_row(
    row: TradeRunLog,
    *,
    include_raw: bool,
) -> dict[str, Any]:
    request_payload = _json_dict(row.request_payload)
    payload = _json_dict(row.response_payload)
    candidate = _candidate_payload(payload)
    diagnostics = _dict_value(payload.get("diagnostics"))
    duplicate_check = _dict_value(diagnostics.get("duplicate_order_check"))

    block_reasons = _normalize_reasons(
        _string_list(payload.get("block_reasons"))
        or _string_list(payload.get("blocked_by"))
        or _string_list(payload.get("failed_checks"))
        or _string_list(candidate.get("block_reasons"))
    )
    reason = _first_text(payload.get("reason"), row.reason)
    primary_block_reason = _first_text(
        payload.get("primary_block_reason"),
        block_reasons[0] if block_reasons else None,
        reason if row.result == "blocked" else None,
    )
    if primary_block_reason and primary_block_reason not in block_reasons:
        block_reasons = _normalize_reasons([primary_block_reason] + block_reasons)

    symbol = _first_text(
        payload.get("symbol"),
        candidate.get("symbol"),
        row.symbol if row.symbol != "WATCHLIST" else None,
    )
    company = _first_text(
        payload.get("company"),
        payload.get("company_name"),
        payload.get("name"),
        candidate.get("company"),
        candidate.get("company_name"),
        candidate.get("name"),
    )
    result = _first_text(payload.get("result"), row.result, "blocked")
    action = _first_text(payload.get("action"), "hold")
    status = _decision_status(
        result=result,
        action=action,
        block_reasons=block_reasons,
        candidate=candidate,
    )
    real_order_submitted = _bool_value(
        payload.get("real_order_submitted"),
        request_payload.get("real_order_submitted"),
    )
    broker_submit_called = _bool_value(
        payload.get("broker_submit_called"),
        request_payload.get("broker_submit_called"),
    )
    manual_submit_called = _bool_value(
        payload.get("manual_submit_called"),
        request_payload.get("manual_submit_called"),
    )

    decision = {
        "run_id": row.id,
        "signal_id": _int_value(payload.get("signal_id")) or row.signal_id,
        "created_at": _iso_datetime(row.created_at),
        "trigger_source": _first_text(payload.get("trigger_source"), row.trigger_source),
        "symbol": symbol,
        "company": company,
        "company_name": company,
        "name": company,
        "result": result,
        "action": action,
        "status": status,
        "final_buy_score": _number_value(
            payload.get("final_buy_score"),
            payload.get("final_score"),
            candidate.get("final_buy_score"),
            candidate.get("final_score"),
        ),
        "required_buy_score": _number_value(
            payload.get("required_buy_score"),
            payload.get("effective_min_entry_score"),
            candidate.get("required_buy_score"),
            candidate.get("effective_min_entry_score"),
        ),
        "final_sell_score": _number_value(
            payload.get("final_sell_score"),
            candidate.get("final_sell_score"),
        ),
        "confidence": _number_value(payload.get("confidence"), candidate.get("confidence")),
        "buy_sell_spread": _number_value(
            payload.get("buy_sell_spread"),
            candidate.get("buy_sell_spread"),
        ),
        "estimated_notional": _number_value(
            payload.get("estimated_notional"),
            payload.get("notional"),
            candidate.get("estimated_notional"),
            candidate.get("suggested_notional"),
        ),
        "suggested_quantity": _int_value(
            payload.get("suggested_quantity"),
            payload.get("quantity"),
            payload.get("qty"),
            candidate.get("suggested_quantity"),
            candidate.get("quantity"),
        ),
        "cash_available": _number_value(
            payload.get("cash_available"),
            candidate.get("cash_available"),
            candidate.get("available_cash"),
        ),
        "block_reasons": block_reasons,
        "primary_block_reason": primary_block_reason,
        "reason": reason,
        "gate_level": _int_value(payload.get("gate_level"), row.gate_level),
        "duplicate_position": _bool_value(
            payload.get("duplicate_position"),
            candidate.get("duplicate_position"),
            duplicate_check.get("duplicate_position"),
        ),
        "duplicate_open_order": _bool_value(
            payload.get("duplicate_open_order"),
            payload.get("duplicate_open_buy_order"),
            candidate.get("duplicate_open_order"),
            candidate.get("duplicate_open_buy_order"),
            duplicate_check.get("duplicate_open_buy_order"),
        ),
        "market_session_allowed": _bool_value(
            payload.get("market_session_allowed"),
            candidate.get("market_session_allowed"),
            payload.get("entry_allowed_now"),
        ),
        "no_new_entry_after_blocked": _bool_value(
            payload.get("no_new_entry_after_blocked"),
            candidate.get("no_new_entry_after_blocked"),
        ),
        "real_order_submitted": real_order_submitted,
        "broker_submit_called": broker_submit_called,
        "manual_submit_called": manual_submit_called,
    }
    if include_raw:
        decision["raw_payload"] = {
            "request_payload": request_payload,
            "response_payload": payload,
        }
    return sanitize_kis_payload(decision)


def _summary(
    decisions: list[dict[str, Any]],
    *,
    no_submit_invariant_ok: bool,
) -> dict[str, Any]:
    latest = decisions[0] if decisions else None
    latest_candidate = next(
        (decision for decision in decisions if decision.get("symbol")),
        None,
    )
    return {
        "total_runs": len(decisions),
        "buy_ready_count": sum(1 for item in decisions if item["status"] == "BUY_READY"),
        "blocked_count": sum(
            1
            for item in decisions
            if item["result"] == "blocked" or item["status"] == "BLOCKED"
        ),
        "no_candidate_count": _count_reason(decisions, "no_candidate"),
        "insufficient_cash_count": _count_reason(decisions, "insufficient_cash"),
        "score_threshold_not_met_count": _count_reason(
            decisions,
            "score_threshold_not_met",
            "buy_sell_spread_too_weak",
        ),
        "sell_pressure_too_high_count": _count_reason(
            decisions,
            "sell_pressure_too_high",
        ),
        "duplicate_position_count": sum(
            1
            for item in decisions
            if item.get("duplicate_position") or _has_reason(item, "duplicate_position")
        ),
        "duplicate_open_order_count": sum(
            1
            for item in decisions
            if item.get("duplicate_open_order")
            or _has_reason(item, "duplicate_open_buy_order", "duplicate_open_order")
        ),
        "daily_limit_reached_count": _count_reason(
            decisions,
            "daily_buy_limit_reached",
        ),
        "market_session_block_count": _count_reason(
            decisions,
            "market_closed",
            "buy_entry_not_allowed_now",
        ),
        "no_new_entry_after_block_count": _count_reason(
            decisions,
            "no_new_entry_after_blocked",
        ),
        "missing_indicators_count": _count_reason(decisions, "missing_indicators"),
        "avg_final_buy_score": _average(decisions, "final_buy_score"),
        "avg_final_sell_score": _average(decisions, "final_sell_score"),
        "avg_required_buy_score": _average(decisions, "required_buy_score"),
        "avg_confidence": _average(decisions, "confidence"),
        "latest_run_at": latest.get("created_at") if latest else None,
        "latest_candidate_symbol": (
            latest_candidate.get("symbol") if latest_candidate else None
        ),
        "latest_candidate_company": (
            latest_candidate.get("company_name") if latest_candidate else None
        ),
        "no_submit_invariant_ok": no_submit_invariant_ok,
    }


def _top_block_reasons(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for decision in decisions:
        if decision["status"] == "BUY_READY":
            continue
        reasons = list(decision.get("block_reasons") or [])
        actionable = [reason for reason in reasons if reason not in _SAFETY_BLOCK_REASONS]
        for reason in actionable or reasons:
            if reason:
                counter[reason] += 1
    return [
        {"reason": reason, "count": count, "label": _reason_label(reason)}
        for reason, count in counter.most_common()
    ]


def _safety(
    runtime: dict[str, Any],
    *,
    no_submit_invariant_ok: bool,
) -> dict[str, Any]:
    return {
        "live_auto_buy_enabled": False,
        "configured_live_auto_buy_enabled": bool(
            runtime.get("kis_live_auto_buy_enabled", False)
        ),
        "limited_auto_buy_enabled": bool(
            runtime.get("kis_limited_auto_buy_enabled", False)
        ),
        "buy_readiness_enabled": bool(
            runtime.get("kis_limited_auto_buy_readiness_enabled", True)
        ),
        "scheduler_real_orders_enabled": False,
        "configured_scheduler_real_orders_enabled": bool(
            runtime.get("kis_scheduler_allow_real_orders", False)
        ),
        "review_only": True,
        "no_order_log_created": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "no_submit_invariant_ok": no_submit_invariant_ok,
    }


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


def _decision_status(
    *,
    result: str,
    action: str,
    block_reasons: list[str],
    candidate: dict[str, Any],
) -> str:
    candidate_status = _first_text(candidate.get("status"))
    if action == "buy_ready" or result in {"ready", "readiness_only"}:
        return "BUY_READY"
    if candidate_status:
        normalized = candidate_status.strip().upper().replace("_", " ")
        if normalized in {"BUY READY", "WATCH", "HOLD", "BLOCKED"}:
            return normalized.replace(" ", "_") if normalized == "BUY READY" else normalized
    if block_reasons:
        if any(reason in _WATCH_REASONS for reason in block_reasons):
            return "WATCH"
        return "BLOCKED"
    return "HOLD"


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return dict(decoded) if isinstance(decoded, dict) else {}


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _normalize_reasons(values: list[str]) -> list[str]:
    mapping = {
        "entry_not_allowed_now": "buy_entry_not_allowed_now",
        "hard_blocked": "gpt_hard_block_new_buy",
        "open_buy_order_exists": "duplicate_open_buy_order",
        "open_order_exists": "duplicate_open_buy_order",
        "position_already_exists": "duplicate_position",
        "position_exists": "duplicate_position",
    }
    result: list[str] = []
    for value in values:
        normalized = mapping.get(value.strip(), value.strip())
        if normalized and normalized not in result:
            result.append(normalized)
    return result


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


def _average(decisions: list[dict[str, Any]], key: str) -> float | None:
    values = [
        float(item[key])
        for item in decisions
        if isinstance(item.get(key), (int, float))
    ]
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _count_reason(decisions: list[dict[str, Any]], *reasons: str) -> int:
    return sum(1 for item in decisions if _has_reason(item, *reasons))


def _has_reason(item: dict[str, Any], *reasons: str) -> bool:
    block_reasons = set(item.get("block_reasons") or [])
    primary = item.get("primary_block_reason")
    reason = item.get("reason")
    return bool(
        block_reasons.intersection(reasons)
        or primary in reasons
        or reason in reasons
    )


def _reason_label(reason: str) -> str:
    if reason in _REASON_LABELS:
        return _REASON_LABELS[reason]
    return reason.replace("_", " ").strip().title()


def _normalize_symbol(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    value = str(symbol).strip().upper()
    if not value:
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
