from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import OrderLog, TradeRunLog
from app.services.kis_payload_sanitizer import sanitize_kis_payload


PROVIDER = "kis"
MARKET = "KR"
MODE = "kis_scheduler_dry_run_review"
SOURCE_MODE = "kis_scheduler_dry_run_orchestration"
SOURCE_TRIGGER = "scheduler_dry_run_orchestration"
MODULES = (
    "scheduler_readiness",
    "portfolio_management",
    "limited_auto_sell",
    "limited_auto_buy",
)


class KisSchedulerDryRunReviewService:
    def review(
        self,
        db: Session,
        *,
        limit: int = 20,
        days: int = 30,
        include_raw: bool = False,
        slot_label: str | None = None,
        module: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        limit = min(max(int(limit or 20), 1), 100)
        days = min(max(int(days or 30), 1), 365)
        module_filter = _clean(module)
        slot_filter = _clean(slot_label)
        cutoff = _utc_now(now) - timedelta(days=days)

        rows = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.created_at >= _naive_utc(cutoff))
            .filter(
                or_(
                    TradeRunLog.mode == SOURCE_MODE,
                    TradeRunLog.trigger_source == SOURCE_TRIGGER,
                    TradeRunLog.request_payload.like(f"%{SOURCE_MODE}%"),
                    TradeRunLog.response_payload.like(f"%{SOURCE_MODE}%"),
                    TradeRunLog.request_payload.like(f"%{SOURCE_TRIGGER}%"),
                    TradeRunLog.response_payload.like(f"%{SOURCE_TRIGGER}%"),
                )
            )
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .all()
        )

        source_row_count = len(rows)
        ignored_row_count = 0
        malformed_row_count = 0
        recent_runs: list[dict[str, Any]] = []
        safety_violations: list[dict[str, Any]] = []

        for row in rows:
            payload = _parse_json_object(row.response_payload)
            if not payload:
                malformed_row_count += 1
                payload = _fallback_payload(row)
            if not _is_source_row(row, payload):
                ignored_row_count += 1
                continue
            if slot_filter and _clean(payload.get("slot_label")) != slot_filter:
                ignored_row_count += 1
                continue

            child_runs = _child_runs(payload)
            if module_filter:
                if not any(_clean(child.get("module")) == module_filter for child in child_runs):
                    ignored_row_count += 1
                    continue
                child_runs = [
                    child
                    for child in child_runs
                    if _clean(child.get("module")) == module_filter
                ]

            run_item = _serialize_run(
                row,
                payload,
                child_runs=child_runs,
                include_raw=include_raw,
            )
            safety_violations.extend(_row_safety_violations(row, payload, child_runs))
            recent_runs.append(run_item)
            if len(recent_runs) >= limit:
                break

        order_log_created_count = _dry_run_order_log_count(db, cutoff=cutoff)
        if order_log_created_count:
            safety_violations.append(
                {
                    "reason": "scheduler_dry_run_order_log_created",
                    "label": "Scheduler dry-run OrderLog rows were found.",
                    "run_id": None,
                    "module": None,
                    "count": order_log_created_count,
                }
            )

        top_block_reasons = _top_block_reasons(recent_runs)
        module_summary = _module_summary(recent_runs)
        no_submit_invariant_ok = not any(
            violation["reason"]
            in {
                "real_order_submitted_true",
                "broker_submit_called_true",
                "manual_submit_called_true",
                "child_order_id_present",
                "child_real_order_submitted_true",
                "child_broker_submit_called_true",
                "child_manual_submit_called_true",
                "order_log_created_flag_false",
                "scheduler_dry_run_order_log_created",
            }
            for violation in safety_violations
        )
        sell_before_buy_ordering_ok = not any(
            violation["reason"]
            in {
                "buy_before_sell_ordering_violation",
                "buy_not_skipped_after_sell_ready",
            }
            for violation in safety_violations
        )
        summary = _summary(
            recent_runs,
            order_log_created_count=order_log_created_count,
            no_submit_invariant_ok=no_submit_invariant_ok,
            sell_before_buy_ordering_ok=sell_before_buy_ordering_ok,
        )
        latest_action = summary["latest_recommended_operator_action"]

        return sanitize_kis_payload(
            {
                "provider": PROVIDER,
                "market": MARKET,
                "mode": MODE,
                "review_only": True,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "order_log_created": False,
                "summary": summary,
                "recent_runs": recent_runs,
                "top_block_reasons": top_block_reasons,
                "module_summary": module_summary,
                "safety_violations": safety_violations,
                "latest_recommended_operator_action": latest_action,
                "safety": {
                    "review_only": True,
                    "no_broker_submit_from_review": True,
                    "scheduler_real_orders_enabled": False,
                    "kis_scheduler_allow_real_orders": False,
                    "no_submit_invariant_ok": no_submit_invariant_ok,
                    "sell_before_buy_ordering_ok": sell_before_buy_ordering_ok,
                    "existing_scheduler_dry_run_unchanged": True,
                    "existing_guarded_buy_sell_unchanged": True,
                },
                "diagnostics": {
                    "source_row_count": source_row_count,
                    "ignored_row_count": ignored_row_count,
                    "malformed_row_count": malformed_row_count,
                    "include_raw": bool(include_raw),
                    "filters_applied": {
                        "limit": limit,
                        "days": days,
                        "slot_label": slot_filter,
                        "module": module_filter,
                    },
                    "price_forward_metrics_available": False,
                },
            }
        )


def _serialize_run(
    row: TradeRunLog,
    payload: dict[str, Any],
    *,
    child_runs: list[dict[str, Any]],
    include_raw: bool,
) -> dict[str, Any]:
    summary = _dynamic_map(payload.get("summary"))
    block_reasons = _string_list(
        payload.get("block_reasons") or summary.get("top_block_reasons")
    )
    item = {
        "run_id": row.id,
        "created_at": row.created_at,
        "slot_label": payload.get("slot_label"),
        "trigger_source": row.trigger_source or payload.get("trigger_source"),
        "mode": row.mode or payload.get("mode"),
        "result": str(payload.get("result") or row.result or "blocked"),
        "primary_block_reason": _nullable_string(
            summary.get("primary_block_reason")
            or payload.get("primary_block_reason")
            or (block_reasons[0] if block_reasons else row.reason)
        ),
        "block_reasons": block_reasons,
        "modules_requested": _string_list(summary.get("modules_requested")),
        "modules_completed": _string_list(summary.get("modules_completed")),
        "modules_blocked": _string_list(summary.get("modules_blocked")),
        "sell_candidates_reviewed": _int(summary.get("sell_candidates_reviewed")),
        "buy_candidates_reviewed": _int(summary.get("buy_candidates_reviewed")),
        "sell_ready_count": _int(summary.get("sell_ready_count")),
        "buy_ready_count": _int(summary.get("buy_ready_count")),
        "buy_skipped_after_sell_review": _buy_skipped_after_sell_review(child_runs),
        "submitted_order_count": _int(summary.get("submitted_order_count")),
        "broker_submit_count": _int(summary.get("broker_submit_count")),
        "manual_submit_count": _int(summary.get("manual_submit_count")),
        "real_order_submitted": _bool(payload.get("real_order_submitted")),
        "broker_submit_called": _bool(payload.get("broker_submit_called")),
        "manual_submit_called": _bool(payload.get("manual_submit_called")),
        "latest_recommended_operator_action": _nullable_string(
            summary.get("next_recommended_operator_action")
        ),
        "child_runs": [_serialize_child(child, include_raw=include_raw) for child in child_runs],
    }
    if include_raw:
        item["raw_payload"] = payload
    return sanitize_kis_payload(item)


def _serialize_child(child: dict[str, Any], *, include_raw: bool) -> dict[str, Any]:
    block_reasons = _string_list(child.get("block_reasons"))
    item = {
        "module": child.get("module"),
        "result": child.get("result"),
        "action": child.get("action"),
        "symbol": child.get("symbol"),
        "status": child.get("status"),
        "primary_block_reason": child.get("primary_block_reason"),
        "block_reasons": block_reasons,
        "real_order_submitted": _bool(child.get("real_order_submitted")),
        "broker_submit_called": _bool(child.get("broker_submit_called")),
        "manual_submit_called": _bool(child.get("manual_submit_called")),
        "order_id": child.get("order_id"),
        "mode": child.get("mode"),
        "source": child.get("source"),
        "trigger_source": child.get("trigger_source"),
        "summary": _dynamic_map(child.get("summary")),
    }
    if include_raw and "raw_payload" in child:
        item["raw_payload"] = child.get("raw_payload")
    return sanitize_kis_payload(item)


def _row_safety_violations(
    row: TradeRunLog,
    payload: dict[str, Any],
    child_runs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    safety = _dynamic_map(payload.get("safety"))
    checks = [
        ("real_order_submitted_true", payload.get("real_order_submitted")),
        ("broker_submit_called_true", payload.get("broker_submit_called")),
        ("manual_submit_called_true", payload.get("manual_submit_called")),
        (
            "scheduler_real_orders_enabled_true",
            payload.get("scheduler_real_orders_enabled")
            or safety.get("scheduler_real_orders_enabled"),
        ),
        (
            "kis_scheduler_allow_real_orders_true",
            safety.get("kis_scheduler_allow_real_orders"),
        ),
    ]
    for reason, value in checks:
        if _bool(value):
            violations.append(_violation(reason, row, None))

    if safety.get("no_order_log_created") is False:
        violations.append(_violation("order_log_created_flag_false", row, None))

    for child in child_runs:
        module = _clean(child.get("module"))
        if child.get("order_id") is not None:
            violations.append(_violation("child_order_id_present", row, module))
        if _bool(child.get("real_order_submitted")):
            violations.append(_violation("child_real_order_submitted_true", row, module))
        if _bool(child.get("broker_submit_called")):
            violations.append(_violation("child_broker_submit_called_true", row, module))
        if _bool(child.get("manual_submit_called")):
            violations.append(_violation("child_manual_submit_called_true", row, module))

    module_order = [_clean(child.get("module")) for child in child_runs]
    if "limited_auto_buy" in module_order and "limited_auto_sell" in module_order:
        if module_order.index("limited_auto_buy") < module_order.index("limited_auto_sell"):
            violations.append(
                _violation("buy_before_sell_ordering_violation", row, "limited_auto_buy")
            )

    sell_ready = any(
        _clean(child.get("module")) == "limited_auto_sell"
        and (
            child.get("action") == "sell_ready"
            or _int(_dynamic_map(child.get("summary")).get("ready_count")) > 0
        )
        for child in child_runs
    )
    buy_children = [
        child for child in child_runs if _clean(child.get("module")) == "limited_auto_buy"
    ]
    if sell_ready and buy_children:
        if not all(
            child.get("result") == "skipped"
            or child.get("primary_block_reason") == "sell_review_required_before_buy"
            for child in buy_children
        ):
            violations.append(
                _violation("buy_not_skipped_after_sell_ready", row, "limited_auto_buy")
            )
    return violations


def _summary(
    recent_runs: list[dict[str, Any]],
    *,
    order_log_created_count: int,
    no_submit_invariant_ok: bool,
    sell_before_buy_ordering_ok: bool,
) -> dict[str, Any]:
    latest = recent_runs[0] if recent_runs else {}
    return {
        "total_runs": len(recent_runs),
        "completed_count": sum(1 for run in recent_runs if run.get("result") == "completed"),
        "blocked_count": sum(1 for run in recent_runs if run.get("result") == "blocked"),
        "partial_count": sum(1 for run in recent_runs if run.get("result") == "partial"),
        "sell_candidates_reviewed": sum(_int(run.get("sell_candidates_reviewed")) for run in recent_runs),
        "buy_candidates_reviewed": sum(_int(run.get("buy_candidates_reviewed")) for run in recent_runs),
        "sell_ready_count": sum(_int(run.get("sell_ready_count")) for run in recent_runs),
        "buy_ready_count": sum(_int(run.get("buy_ready_count")) for run in recent_runs),
        "buy_skipped_after_sell_review_count": sum(
            1 for run in recent_runs if run.get("buy_skipped_after_sell_review") is True
        ),
        "submitted_order_count": sum(_int(run.get("submitted_order_count")) for run in recent_runs),
        "broker_submit_count": sum(_int(run.get("broker_submit_count")) for run in recent_runs),
        "manual_submit_count": sum(_int(run.get("manual_submit_count")) for run in recent_runs),
        "order_log_created_count": order_log_created_count,
        "no_submit_invariant_ok": no_submit_invariant_ok,
        "sell_before_buy_ordering_ok": sell_before_buy_ordering_ok,
        "latest_run_at": latest.get("created_at"),
        "latest_slot_label": latest.get("slot_label"),
        "latest_result": latest.get("result"),
        "latest_primary_block_reason": latest.get("primary_block_reason"),
        "latest_recommended_operator_action": latest.get(
            "latest_recommended_operator_action"
        ),
    }


def _module_summary(recent_runs: list[dict[str, Any]]) -> dict[str, Any]:
    counters: dict[str, dict[str, Any]] = {
        "scheduler_readiness": {"run_count": 0, "blocked_count": 0},
        "limited_auto_sell": {
            "run_count": 0,
            "sell_ready_count": 0,
            "blocked_count": 0,
            "top_block_reason": None,
        },
        "limited_auto_buy": {
            "run_count": 0,
            "buy_ready_count": 0,
            "blocked_count": 0,
            "skipped_after_sell_review_count": 0,
            "top_block_reason": None,
        },
        "portfolio_management": {"run_count": 0, "reviewed_count": 0},
    }
    reason_counts: dict[str, Counter[str]] = {
        "limited_auto_sell": Counter(),
        "limited_auto_buy": Counter(),
    }
    for run in recent_runs:
        for child in run.get("child_runs") or []:
            module = _clean(child.get("module"))
            if module not in counters:
                continue
            counters[module]["run_count"] += 1
            if child.get("result") == "blocked" or child.get("primary_block_reason"):
                counters[module]["blocked_count"] = counters[module].get("blocked_count", 0) + 1
            for reason in _string_list(child.get("block_reasons")):
                if module in reason_counts:
                    reason_counts[module][reason] += 1
            ready_count = _int(_dynamic_map(child.get("summary")).get("ready_count"))
            if module == "limited_auto_sell":
                counters[module]["sell_ready_count"] += ready_count
            elif module == "limited_auto_buy":
                counters[module]["buy_ready_count"] += ready_count
                if child.get("result") == "skipped" and (
                    child.get("primary_block_reason") == "sell_review_required_before_buy"
                ):
                    counters[module]["skipped_after_sell_review_count"] += 1
            elif module == "portfolio_management":
                counters[module]["reviewed_count"] += 1
    for module in ("limited_auto_sell", "limited_auto_buy"):
        if reason_counts[module]:
            counters[module]["top_block_reason"] = reason_counts[module].most_common(1)[0][0]
    return counters


def _top_block_reasons(recent_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for run in recent_runs:
        counts.update(_string_list(run.get("block_reasons")))
        for child in run.get("child_runs") or []:
            counts.update(_string_list(child.get("block_reasons")))
    return [
        {"reason": reason, "label": _label(reason), "count": count}
        for reason, count in counts.most_common(10)
    ]


def _violation(reason: str, row: TradeRunLog, module: str | None) -> dict[str, Any]:
    return {
        "reason": reason,
        "label": _label(reason),
        "run_id": row.id,
        "module": module,
    }


def _dry_run_order_log_count(db: Session, *, cutoff: datetime) -> int:
    return int(
        db.query(OrderLog)
        .filter(OrderLog.created_at >= _naive_utc(cutoff))
        .filter(
            or_(
                OrderLog.request_payload.like(f"%{SOURCE_MODE}%"),
                OrderLog.response_payload.like(f"%{SOURCE_MODE}%"),
                OrderLog.request_payload.like(f"%{SOURCE_TRIGGER}%"),
                OrderLog.response_payload.like(f"%{SOURCE_TRIGGER}%"),
            )
        )
        .count()
        or 0
    )


def _child_runs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("child_runs")
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _fallback_payload(row: TradeRunLog) -> dict[str, Any]:
    return {
        "mode": row.mode,
        "trigger_source": row.trigger_source,
        "result": row.result,
        "primary_block_reason": row.reason,
        "block_reasons": [row.reason] if row.reason else [],
        "child_runs": [],
        "summary": {},
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
    )


def _buy_skipped_after_sell_review(child_runs: list[dict[str, Any]]) -> bool:
    return any(
        _clean(child.get("module")) == "limited_auto_buy"
        and child.get("result") == "skipped"
        and child.get("primary_block_reason") == "sell_review_required_before_buy"
        for child in child_runs
    )


def _parse_json_object(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _dynamic_map(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    return text in {"true", "1", "yes"}


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _nullable_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _label(reason: str) -> str:
    return reason.replace("_", " ").strip().title()


def _utc_now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    return _utc_now(value).replace(tzinfo=None)
