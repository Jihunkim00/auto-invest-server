from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.core.constants import DEFAULT_GATE_LEVEL
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, TradeRunLog
from app.services.kis_dry_run_risk_service import BUY, MARKET, OPEN_ORDER_STATUSES, PROVIDER
from app.services.kis_limited_auto_buy_service import KisLimitedAutoBuyService
from app.services.kis_limited_auto_sell_service import KisLimitedAutoSellService
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.kis_scheduler_readiness_service import KisSchedulerReadinessService
from app.services.runtime_setting_service import RuntimeSettingService


STATUS_MODE = "kis_scheduler_guarded_buy_status"
MODE = "kis_scheduler_guarded_buy"
TRIGGER_SOURCE = "scheduler_guarded_buy"
SOURCE_TYPE = "scheduler_guarded_buy_execution"
DEFAULT_SLOT_LABEL = "manual_guarded_buy"
KR_TZ = ZoneInfo("Asia/Seoul")
ALLOWED_REQUEST_TRIGGER_SOURCES = {"scheduler", "scheduler_manual_test"}
BUY_SLOT_KEYWORDS = (
    "buy",
    "entry",
    "open",
    "scan",
    "new",
    "candidate",
    "readiness",
)
SELL_READY_REASONS = {
    "stop_loss_candidate_ready_read_only",
    "take_profit_readiness_only",
}


class KisSchedulerGuardedBuyService:
    """Buy-only scheduler wrapper for the existing guarded limited buy path."""

    def __init__(
        self,
        client: KisClient,
        *,
        limited_auto_buy_service: Any | None = None,
        limited_auto_sell_service: Any | None = None,
        readiness_service: Any | None = None,
        runtime_settings: RuntimeSettingService | None = None,
    ):
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.readiness_service = readiness_service or KisSchedulerReadinessService(
            client,
            runtime_settings=self.runtime_settings,
        )
        self.limited_auto_sell_service = limited_auto_sell_service or KisLimitedAutoSellService(
            client,
            runtime_settings=self.runtime_settings,
        )
        self.limited_auto_buy_service = limited_auto_buy_service or KisLimitedAutoBuyService(
            client,
            runtime_settings=self.runtime_settings,
            allow_scheduler_guarded_buy=True,
        )

    def status(
        self,
        db: Session,
        *,
        slot_label: str | None = None,
        trigger_source: str = "scheduler_manual_test",
        include_raw: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc_now(now)
        created_at = now_utc.isoformat()
        resolved_slot_label = _slot_label(slot_label)
        runtime = self.runtime_settings.get_settings(db)
        checks = _checks(
            runtime,
            self.client.settings,
            slot_label=resolved_slot_label,
            requested_trigger_source=trigger_source,
        )
        daily_limit = _daily_limited_buy_state(db, runtime=runtime, now_utc=now_utc)
        readiness = self._scheduler_readiness(db, include_raw=include_raw, now=now_utc)
        sell_review = self._sell_review(db, include_raw=include_raw, now=now_utc)
        sell_priority = _sell_priority_state(
            db,
            self.client,
            sell_review=sell_review,
            slot_label=resolved_slot_label,
            now_utc=now_utc,
        )
        block_reasons = _dedupe(
            _block_reasons(checks)
            + _readiness_block_reasons(readiness)
            + sell_priority["block_reasons"]
        )
        buy_execution_allowed = not block_reasons
        return _payload(
            mode=STATUS_MODE,
            result="blocked" if block_reasons else "ready",
            action="hold",
            reason=block_reasons[0] if block_reasons else "scheduler_buy_gates_ready",
            slot_label=resolved_slot_label,
            requested_trigger_source=trigger_source,
            checks=checks,
            daily_limit=daily_limit,
            readiness=readiness,
            sell_review=sell_review,
            sell_priority=sell_priority,
            buy_result=None,
            block_reasons=block_reasons,
            created_at=created_at,
            include_raw=include_raw,
            buy_execution_allowed=buy_execution_allowed,
        )

    def run_once(
        self,
        db: Session,
        *,
        slot_label: str | None = None,
        trigger_source: str = "scheduler_manual_test",
        include_raw: bool = False,
        gate_level: int = DEFAULT_GATE_LEVEL,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc_now(now)
        created_at = now_utc.isoformat()
        resolved_slot_label = _slot_label(slot_label)
        runtime = self.runtime_settings.get_settings(db)
        checks = _checks(
            runtime,
            self.client.settings,
            slot_label=resolved_slot_label,
            requested_trigger_source=trigger_source,
        )
        checks["scheduler_slot_submitted_count"] = _slot_submitted_count(
            db,
            slot_label=resolved_slot_label,
            now_utc=now_utc,
        )
        checks["scheduler_slot_dedupe_ok"] = (
            checks["scheduler_slot_submitted_count"] == 0
        )
        checks["scheduler_sell_submitted_in_slot_count"] = _scheduler_sell_submitted_count(
            db,
            slot_label=resolved_slot_label,
            now_utc=now_utc,
        )
        checks["scheduler_sell_submitted_in_slot"] = (
            checks["scheduler_sell_submitted_in_slot_count"] > 0
        )
        checks["scheduler_no_sell_submitted_in_slot"] = (
            checks["scheduler_sell_submitted_in_slot_count"] == 0
        )
        daily_limit = _daily_limited_buy_state(db, runtime=runtime, now_utc=now_utc)
        readiness = self._scheduler_readiness(db, include_raw=include_raw, now=now_utc)
        sell_review = self._sell_review(db, include_raw=include_raw, now=now_utc)
        sell_priority = _sell_priority_state(
            db,
            self.client,
            sell_review=sell_review,
            slot_label=resolved_slot_label,
            now_utc=now_utc,
        )
        block_reasons = _dedupe(
            _block_reasons(checks) + _readiness_block_reasons(readiness)
        )
        if block_reasons:
            payload = _payload(
                mode=MODE,
                result="blocked",
                action="hold",
                reason=block_reasons[0],
                slot_label=resolved_slot_label,
                requested_trigger_source=trigger_source,
                checks=checks,
                daily_limit=daily_limit,
                readiness=readiness,
                sell_review=sell_review,
                sell_priority=sell_priority,
                buy_result=_skipped_buy_result(
                    "scheduler_buy_gates_blocked",
                    block_reasons=block_reasons,
                ),
                block_reasons=block_reasons,
                created_at=created_at,
                include_raw=include_raw,
                buy_execution_allowed=False,
            )
            return self._record_parent_run(db, payload=payload, gate_level=gate_level)

        sell_blocks = _string_list(sell_priority.get("block_reasons"))
        if sell_blocks:
            payload = _payload(
                mode=MODE,
                result="skipped",
                action="hold",
                reason=sell_blocks[0],
                slot_label=resolved_slot_label,
                requested_trigger_source=trigger_source,
                checks=checks,
                daily_limit=daily_limit,
                readiness=readiness,
                sell_review=sell_review,
                sell_priority=sell_priority,
                buy_result=_skipped_buy_result(
                    "sell_review_required_before_buy",
                    block_reasons=sell_blocks,
                ),
                block_reasons=sell_blocks,
                created_at=created_at,
                include_raw=include_raw,
                buy_execution_allowed=False,
            )
            return self._record_parent_run(db, payload=payload, gate_level=gate_level)

        buy_result = sanitize_kis_payload(
            self.limited_auto_buy_service.run_once(
                db,
                gate_level=gate_level,
                now=now_utc,
                scheduler_context=True,
            )
        )
        child_blocks = _string_list(
            buy_result.get("block_reasons")
            or buy_result.get("blocked_by")
            or buy_result.get("failed_checks")
        )
        submitted = buy_result.get("real_order_submitted") is True
        if submitted:
            result = "submitted"
            action = BUY
            reason = str(
                buy_result.get("reason") or "scheduler_guarded_buy_submitted"
            )
            block_reasons = []
        else:
            result = "skipped" if buy_result.get("result") == "skipped" else "blocked"
            action = "hold"
            reason = str(
                buy_result.get("primary_block_reason")
                or buy_result.get("reason")
                or (child_blocks[0] if child_blocks else "no_buy_candidate")
            )
            block_reasons = child_blocks or [reason]

        payload = _payload(
            mode=MODE,
            result=result,
            action=action,
            reason=reason,
            slot_label=resolved_slot_label,
            requested_trigger_source=trigger_source,
            checks=checks,
            daily_limit=_daily_limited_buy_state(
                db,
                runtime=runtime,
                now_utc=now_utc,
            ),
            readiness=readiness,
            sell_review=sell_review,
            sell_priority=sell_priority,
            buy_result=buy_result,
            block_reasons=block_reasons,
            created_at=created_at,
            include_raw=include_raw,
            buy_execution_allowed=True,
        )
        return self._record_parent_run(db, payload=payload, gate_level=gate_level)

    def _scheduler_readiness(
        self,
        db: Session,
        *,
        include_raw: bool,
        now: datetime,
    ) -> dict[str, Any]:
        try:
            payload = self.readiness_service.readiness(
                db,
                include_modules=True,
                include_recent_runs=True,
                include_raw=include_raw,
                now=now,
            )
            return sanitize_kis_payload(payload if include_raw else _without_raw(payload))
        except Exception as exc:
            return {
                "mode": "kis_scheduler_readiness",
                "result": "blocked",
                "status": "error",
                "primary_block_reason": "scheduler_readiness_unavailable",
                "block_reasons": [
                    "scheduler_readiness_unavailable",
                    _safe_error(exc),
                ],
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }

    def _sell_review(
        self,
        db: Session,
        *,
        include_raw: bool,
        now: datetime,
    ) -> dict[str, Any]:
        try:
            payload = self.limited_auto_sell_service.preflight_once(db, now=now)
            return sanitize_kis_payload(payload if include_raw else _without_raw(payload))
        except Exception as exc:
            return {
                "mode": "kis_limited_auto_stop_loss_preflight",
                "result": "blocked",
                "status": "error",
                "primary_block_reason": "sell_review_unavailable",
                "block_reasons": ["sell_review_unavailable", _safe_error(exc)],
                "candidate_count": 0,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }

    def _record_parent_run(
        self,
        db: Session,
        *,
        payload: dict[str, Any],
        gate_level: int,
    ) -> dict[str, Any]:
        order_id = _int_or_none(payload.get("order_id"))
        run = TradeRunLog(
            run_key=f"kis_scheduler_guarded_buy_{uuid.uuid4().hex[:10]}",
            trigger_source=TRIGGER_SOURCE,
            symbol=str(payload.get("symbol") or "WATCHLIST"),
            mode=MODE,
            gate_level=gate_level,
            stage="done",
            result=str(payload.get("result") or "blocked"),
            reason=str(payload.get("reason") or ""),
            order_id=order_id,
            request_payload=_json(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": MODE,
                    "trigger_source": TRIGGER_SOURCE,
                    "requested_trigger_source": payload.get(
                        "requested_trigger_source"
                    ),
                    "slot_label": payload.get("slot_label"),
                    "buy_only": True,
                    "sell_priority_required": True,
                }
            ),
            response_payload=_json(payload),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        payload["run"] = {
            "run_id": run.id,
            "run_key": run.run_key,
            "trigger_source": run.trigger_source,
            "symbol": run.symbol,
            "mode": run.mode,
            "result": run.result,
            "reason": run.reason,
            "order_id": run.order_id,
            "created_at": run.created_at,
        }
        return sanitize_kis_payload(payload)


def _checks(
    runtime: dict[str, Any],
    settings: Any,
    *,
    slot_label: str,
    requested_trigger_source: str,
) -> dict[str, Any]:
    configured_allow_real_orders = bool(
        runtime.get("kis_scheduler_configured_allow_real_orders", False)
        or getattr(settings, "kis_scheduler_allow_real_orders", False)
        or getattr(settings, "kr_scheduler_allow_real_orders", False)
    )
    scheduler_buy_enabled = bool(runtime.get("kis_scheduler_buy_enabled", False))
    return {
        "scheduler_enabled": bool(runtime.get("scheduler_enabled", False)),
        "kis_scheduler_enabled": bool(runtime.get("kis_scheduler_enabled", False)),
        "kis_scheduler_dry_run": bool(runtime.get("kis_scheduler_dry_run", True)),
        "kis_scheduler_dry_run_false": bool(
            runtime.get("kis_scheduler_dry_run", True)
        )
        is False,
        "kis_scheduler_allow_real_orders": bool(
            runtime.get("kis_scheduler_allow_real_orders", False)
        ),
        "configured_kis_scheduler_allow_real_orders": configured_allow_real_orders,
        "kis_scheduler_buy_enabled": scheduler_buy_enabled,
        "kis_scheduler_sell_enabled": bool(
            runtime.get("kis_scheduler_sell_enabled", False)
        ),
        "kis_scheduler_allow_limited_auto_buy": bool(
            runtime.get("kis_scheduler_allow_limited_auto_buy", False)
        ),
        "kis_scheduler_allow_limited_auto_sell": bool(
            runtime.get("kis_scheduler_allow_limited_auto_sell", False)
        ),
        "requested_trigger_source": requested_trigger_source,
        "trigger_source_allowed": requested_trigger_source
        in ALLOWED_REQUEST_TRIGGER_SOURCES,
        "slot_label": slot_label,
        "slot_allows_buy": _slot_allows_buy(slot_label),
        "dry_run": bool(runtime.get("dry_run", True)),
        "dry_run_false": bool(runtime.get("dry_run", True)) is False,
        "kill_switch": bool(runtime.get("kill_switch", False)),
        "kill_switch_false": bool(runtime.get("kill_switch", False)) is False,
        "kis_enabled": bool(getattr(settings, "kis_enabled", False)),
        "kis_real_order_enabled": bool(
            getattr(settings, "kis_real_order_enabled", False)
        ),
        "kis_live_auto_buy_enabled": bool(
            runtime.get("kis_live_auto_buy_enabled", False)
        ),
        "kis_limited_auto_buy_enabled": bool(
            runtime.get("kis_limited_auto_buy_enabled", False)
        ),
        "sell_safety_modules_known": _sell_safety_modules_known(runtime),
    }


def _block_reasons(checks: dict[str, Any]) -> list[str]:
    ordered = [
        ("kis_scheduler_allow_real_orders", "scheduler_real_orders_disabled"),
        (
            "configured_kis_scheduler_allow_real_orders",
            "configured_scheduler_real_orders_disabled",
        ),
        ("kis_scheduler_buy_enabled", "scheduler_buy_disabled"),
        ("scheduler_enabled", "scheduler_disabled"),
        ("kis_scheduler_enabled", "kis_scheduler_disabled"),
        ("kis_scheduler_dry_run_false", "kis_scheduler_dry_run_true"),
        ("trigger_source_allowed", "scheduler_trigger_source_invalid"),
        ("slot_allows_buy", "scheduler_slot_not_buy_enabled"),
        ("scheduler_slot_dedupe_ok", "scheduler_slot_real_order_already_submitted"),
        ("scheduler_no_sell_submitted_in_slot", "scheduler_sell_submitted_in_slot"),
        ("dry_run_false", "runtime_dry_run_true"),
        ("kill_switch_false", "kill_switch_enabled"),
        ("kis_enabled", "kis_disabled"),
        ("kis_real_order_enabled", "kis_real_order_disabled"),
        ("kis_live_auto_buy_enabled", "kis_live_auto_buy_disabled"),
        ("kis_limited_auto_buy_enabled", "kis_limited_auto_buy_disabled"),
        ("sell_safety_modules_known", "sell_safety_modules_unavailable"),
    ]
    reasons: list[str] = []
    for key, reason in ordered:
        if key in checks and checks.get(key) is not True:
            reasons.append(reason)
    return _dedupe(reasons)


def _payload(
    *,
    mode: str,
    result: str,
    action: str,
    reason: str,
    slot_label: str,
    requested_trigger_source: str,
    checks: dict[str, Any],
    daily_limit: dict[str, Any],
    readiness: dict[str, Any],
    sell_review: dict[str, Any],
    sell_priority: dict[str, Any],
    buy_result: dict[str, Any] | None,
    block_reasons: list[str],
    created_at: str,
    include_raw: bool,
    buy_execution_allowed: bool,
) -> dict[str, Any]:
    child = _without_raw(buy_result) if buy_result and not include_raw else buy_result
    sell_child = sell_review if include_raw else _without_raw(sell_review)
    readiness_child = readiness if include_raw else _without_raw(readiness)
    submitted = bool((child or {}).get("real_order_submitted") is True)
    broker_called = bool((child or {}).get("broker_submit_called") is True)
    manual_called = bool((child or {}).get("manual_submit_called") is True)
    order_id = (child or {}).get("order_id") or (child or {}).get("order_log_id")
    symbol = (child or {}).get("symbol")
    duplicate_order_check = _duplicate_order_check(child)
    market_session_check = _market_session_check(child, sell_child)
    primary_block_reason = block_reasons[0] if block_reasons else None
    scheduler_real_orders_enabled = bool(
        checks.get("kis_scheduler_allow_real_orders")
        and checks.get("configured_kis_scheduler_allow_real_orders")
    )
    scheduler_buy_enabled = bool(checks.get("kis_scheduler_buy_enabled"))
    sell_review_completed = bool(sell_priority.get("sell_review_completed"))
    safety = {
        "scheduler_buy_only": True,
        "buy_only": True,
        "sell_priority_required": True,
        "sell_review_completed": sell_review_completed,
        "sell_ready_blocks_buy": True,
        "no_direct_broker_submit_from_scheduler": True,
        "no_direct_manual_submit_from_scheduler": True,
        "existing_limited_auto_buy_path_reused": True,
        "scheduler_real_orders_enabled": scheduler_real_orders_enabled,
        "dry_run": bool(checks.get("dry_run")),
        "kill_switch": bool(checks.get("kill_switch")),
        "kis_real_order_enabled": bool(checks.get("kis_real_order_enabled")),
        "kis_live_auto_buy_enabled": bool(
            checks.get("kis_live_auto_buy_enabled")
        ),
        "kis_limited_auto_buy_enabled": bool(
            checks.get("kis_limited_auto_buy_enabled")
        ),
        "kis_scheduler_allow_real_orders": bool(
            checks.get("kis_scheduler_allow_real_orders")
        ),
        "kis_scheduler_buy_enabled": scheduler_buy_enabled,
        "daily_limit_remaining": daily_limit.get("daily_limit_remaining"),
        "duplicate_order_check": duplicate_order_check,
        "market_session_check": market_session_check,
        "real_order_submitted": submitted,
        "broker_submit_called": broker_called,
        "manual_submit_called": manual_called,
    }
    payload = {
        "status": "ok",
        "provider": PROVIDER,
        "market": MARKET,
        "mode": mode,
        "source": MODE,
        "source_type": SOURCE_TYPE,
        "trigger_source": TRIGGER_SOURCE,
        "requested_trigger_source": requested_trigger_source,
        "slot_label": slot_label,
        "buy_only": True,
        "scheduler_buy_only": True,
        "sell_priority_required": True,
        "sell_priority_checked": sell_review_completed,
        "sell_ready_blocks_buy": True,
        "sell_review_required_before_buy": True,
        "scheduler_buy_enabled": scheduler_buy_enabled,
        "scheduler_real_orders_enabled": scheduler_real_orders_enabled,
        "real_order_submit_allowed": bool(
            (child or {}).get("real_order_submit_allowed") is True
        ),
        "buy_execution_allowed": buy_execution_allowed,
        "result": result,
        "action": action,
        "reason": reason,
        "primary_block_reason": primary_block_reason,
        "summary": {
            "result": result,
            "action": action,
            "primary_block_reason": primary_block_reason,
            "buy_only": True,
            "sell_priority_checked": sell_review_completed,
            "sell_ready_blocks_buy": True,
            "scheduler_real_orders_enabled": scheduler_real_orders_enabled,
            "scheduler_buy_enabled": scheduler_buy_enabled,
            "daily_limit_remaining": daily_limit.get("daily_limit_remaining"),
            "symbol": symbol,
            "company_name": (child or {}).get("company_name")
            or (child or {}).get("name"),
            "quantity": (child or {}).get("quantity") or (child or {}).get("qty"),
            "estimated_notional": (child or {}).get("estimated_notional")
            or (child or {}).get("notional"),
            "order_id": order_id,
            "broker_order_id": (child or {}).get("broker_order_id"),
            "kis_odno": (child or {}).get("kis_odno"),
        },
        "sell_review_result": sell_child,
        "buy_result": child or _skipped_buy_result(
            reason or "buy_execution_not_called",
            block_reasons=block_reasons,
        ),
        "block_reasons": block_reasons,
        "blocked_by": block_reasons,
        "safety": safety,
        "diagnostics": {
            "checks": checks,
            "daily_limit": daily_limit,
            "scheduler_readiness": readiness_child,
            "sell_priority": sell_priority,
            "limited_auto_buy_result_available": child is not None,
            "include_raw": include_raw,
        },
        "checks": checks,
        "daily_limit": daily_limit,
        "duplicate_order_check": duplicate_order_check,
        "market_session_check": market_session_check,
        "real_order_submitted": submitted,
        "broker_submit_called": broker_called,
        "manual_submit_called": manual_called,
        "order_id": order_id,
        "order_log_id": (child or {}).get("order_log_id") or order_id,
        "broker_order_id": (child or {}).get("broker_order_id"),
        "kis_odno": (child or {}).get("kis_odno"),
        "symbol": symbol,
        "company_name": (child or {}).get("company_name") or (child or {}).get("name"),
        "quantity": (child or {}).get("quantity") or (child or {}).get("qty"),
        "estimated_notional": (child or {}).get("estimated_notional")
        or (child or {}).get("notional"),
        "created_at": created_at,
    }
    return sanitize_kis_payload(payload)


def _sell_priority_state(
    db: Session,
    client: KisClient,
    *,
    sell_review: dict[str, Any],
    slot_label: str,
    now_utc: datetime,
) -> dict[str, Any]:
    sell_ready_count = _sell_ready_count(sell_review)
    open_sell = _open_sell_order_state(db, client)
    scheduler_sell_count = _scheduler_sell_submitted_count(
        db,
        slot_label=slot_label,
        now_utc=now_utc,
    )
    block_reasons: list[str] = []
    if sell_review.get("status") == "error":
        block_reasons.append("sell_review_unavailable")
    if sell_ready_count > 0:
        block_reasons.append("sell_review_required_before_buy")
    if scheduler_sell_count > 0:
        block_reasons.append("scheduler_sell_submitted_in_slot")
    if open_sell["open_sell_order_count"] > 0:
        block_reasons.append("open_sell_order_exists")
    return sanitize_kis_payload(
        {
            "sell_review_completed": sell_review.get("status") != "error",
            "sell_ready_count": sell_ready_count,
            "sell_ready_blocks_buy": True,
            "scheduler_sell_submitted_in_slot_count": scheduler_sell_count,
            "open_sell_order_count": open_sell["open_sell_order_count"],
            "open_sell_order_checked": open_sell["checked"],
            "open_sell_order_warnings": open_sell["warnings"],
            "block_reasons": _dedupe(block_reasons),
        }
    )


def _sell_ready_count(sell_review: dict[str, Any]) -> int:
    if not sell_review:
        return 0
    count = 0
    final_candidate = _dict_value(sell_review.get("final_candidate"))
    candidates = sell_review.get("candidates")
    if isinstance(candidates, list):
        for item in candidates:
            if _candidate_sell_ready(_dict_value(item)):
                count += 1
    if count == 0 and _candidate_sell_ready(final_candidate):
        count = 1
    action = str(sell_review.get("action") or "").lower()
    reason = str(sell_review.get("reason") or "")
    if count == 0 and (
        action == "sell_ready" or reason in SELL_READY_REASONS
    ):
        count = 1
    ready_count = _int_or_none(_dict_value(sell_review.get("summary")).get("ready_count"))
    if ready_count is not None:
        count = max(count, ready_count)
    return count


def _candidate_sell_ready(candidate: dict[str, Any]) -> bool:
    status = str(candidate.get("status") or "").strip().upper()
    if status in {"SELL_READY", "TAKE_PROFIT_READY"}:
        return True
    reason = str(candidate.get("reason") or candidate.get("exit_reason") or "")
    return reason in SELL_READY_REASONS


def _open_sell_order_state(db: Session, client: KisClient) -> dict[str, Any]:
    warnings: list[str] = []
    count = 0
    try:
        for item in client.list_open_orders():
            if _order_is_sell(_dict_value(item)):
                count += 1
    except Exception as exc:
        warnings.append(f"broker_open_orders_unavailable:{exc.__class__.__name__}")
    try:
        count += int(
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(or_(OrderLog.market == MARKET, OrderLog.market.is_(None)))
            .filter(OrderLog.side == "sell")
            .filter(OrderLog.internal_status.in_(sorted(OPEN_ORDER_STATUSES)))
            .count()
            or 0
        )
    except Exception as exc:
        warnings.append(f"db_open_sell_orders_unavailable:{exc.__class__.__name__}")
    return {
        "checked": True,
        "open_sell_order_count": count,
        "warnings": warnings,
    }


def _daily_limited_buy_state(
    db: Session,
    *,
    runtime: dict[str, Any],
    now_utc: datetime,
) -> dict[str, Any]:
    max_orders = max(
        0,
        int(runtime.get("kis_limited_auto_buy_max_orders_per_day", 1) or 0),
    )
    start_utc, end_utc = _kr_day_bounds_utc(now_utc)
    rows = (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.side == BUY)
        .filter(OrderLog.created_at >= start_utc)
        .filter(OrderLog.created_at < end_utc)
        .all()
    )
    submitted_statuses = {
        InternalOrderStatus.SUBMITTED.value,
        InternalOrderStatus.ACCEPTED.value,
        InternalOrderStatus.PENDING.value,
        InternalOrderStatus.PARTIALLY_FILLED.value,
        InternalOrderStatus.FILLED.value,
    }
    total = 0
    for row in rows:
        if str(row.internal_status or "").upper() not in submitted_statuses:
            continue
        total += 1
    return {
        "max_orders_per_day": max_orders,
        "submitted_count_today": total,
        "daily_limit_remaining": max(0, max_orders - total),
        "daily_limit_reached": max_orders <= 0 or total >= max_orders,
    }


def _slot_submitted_count(
    db: Session,
    *,
    slot_label: str,
    now_utc: datetime,
) -> int:
    start_utc, end_utc = _kr_day_bounds_utc(now_utc)
    return int(
        db.query(TradeRunLog)
        .filter(TradeRunLog.mode == MODE)
        .filter(TradeRunLog.trigger_source == TRIGGER_SOURCE)
        .filter(TradeRunLog.result == "submitted")
        .filter(TradeRunLog.created_at >= start_utc)
        .filter(TradeRunLog.created_at < end_utc)
        .filter(TradeRunLog.response_payload.like(f"%{slot_label}%"))
        .count()
        or 0
    )


def _scheduler_sell_submitted_count(
    db: Session,
    *,
    slot_label: str,
    now_utc: datetime,
) -> int:
    start_utc, end_utc = _kr_day_bounds_utc(now_utc)
    return int(
        db.query(TradeRunLog)
        .filter(TradeRunLog.mode == "kis_scheduler_guarded_sell")
        .filter(TradeRunLog.trigger_source == "scheduler_guarded_sell")
        .filter(TradeRunLog.result == "submitted")
        .filter(TradeRunLog.created_at >= start_utc)
        .filter(TradeRunLog.created_at < end_utc)
        .filter(TradeRunLog.response_payload.like(f"%{slot_label}%"))
        .count()
        or 0
    )


def _skipped_buy_result(reason: str, *, block_reasons: list[str]) -> dict[str, Any]:
    return {
        "result": "skipped",
        "action": "hold",
        "reason": reason,
        "primary_block_reason": block_reasons[0] if block_reasons else reason,
        "block_reasons": block_reasons or [reason],
        "buy_execution_skipped": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "validation_called": False,
        "order_id": None,
        "broker_order_id": None,
        "kis_odno": None,
    }


def _readiness_block_reasons(readiness: dict[str, Any]) -> list[str]:
    if readiness.get("status") == "error":
        return ["scheduler_readiness_unavailable"]
    modules = _dict_value(readiness.get("modules"))
    reasons: list[str] = []
    for name in ("limited_auto_sell", "limited_auto_buy"):
        module = _dict_value(modules.get(name))
        if module and module.get("available") is False:
            reasons.append(f"{name}_unavailable")
    return reasons


def _duplicate_order_check(child: dict[str, Any] | None) -> dict[str, Any]:
    diagnostics = _dict_value((child or {}).get("diagnostics"))
    duplicate = _dict_value(
        (child or {}).get("duplicate_order_check")
        or diagnostics.get("duplicate_order_check")
    )
    if duplicate:
        duplicate["checked"] = True
        return duplicate
    return {
        "checked": child is not None,
        "duplicate_open_buy_order": None,
    }


def _market_session_check(
    child: dict[str, Any] | None,
    sell_review: dict[str, Any],
) -> dict[str, Any]:
    market = _dict_value((child or {}).get("market_session"))
    checks = _dict_value((child or {}).get("checks"))
    if not market:
        market = _dict_value(
            _dict_value((child or {}).get("diagnostics")).get(
                "market_session_snapshot"
            )
        )
    sell_market = _dict_value(sell_review.get("market_session"))
    return {
        "checked": bool(child),
        "market_open": market.get("is_market_open"),
        "entry_allowed_now": market.get("entry_allowed_now")
        if "entry_allowed_now" in market
        else market.get("is_entry_allowed_now"),
        "no_new_entry_after": market.get("no_new_entry_after")
        or checks.get("no_new_entry_after"),
        "sell_session_allowed": sell_review.get("sell_session_allowed")
        if "sell_session_allowed" in sell_review
        else sell_market.get("is_market_open"),
        "closure_reason": market.get("closure_reason"),
    }


def _order_is_sell(order: dict[str, Any]) -> bool:
    side = str(
        order.get("side")
        or order.get("order_side")
        or order.get("sll_buy_dvsn_cd_name")
        or order.get("sll_buy_dvsn_name")
        or ""
    ).strip().lower()
    if side in {"sell", "s"} or "sell" in side:
        return True
    code = str(order.get("sll_buy_dvsn_cd") or order.get("sll_buy_dvsn") or "").strip()
    return code in {"01", "1"}


def _sell_safety_modules_known(runtime: dict[str, Any]) -> bool:
    keys = {
        "kis_limited_auto_sell_enabled",
        "kis_limited_auto_sell_stop_loss_enabled",
        "kis_limited_auto_sell_take_profit_enabled",
        "kis_limited_auto_stop_loss_enabled",
        "kis_limited_auto_take_profit_enabled",
    }
    return any(key in runtime for key in keys)


def _slot_label(value: str | None) -> str:
    text = str(value or "").strip()
    return text or DEFAULT_SLOT_LABEL


def _slot_allows_buy(slot_label: str) -> bool:
    normalized = slot_label.strip().lower().replace("-", "_")
    return any(keyword in normalized for keyword in BUY_SLOT_KEYWORDS)


def _without_raw(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_raw(item)
            for key, item in value.items()
            if key not in {"raw_payload", "raw", "request_payload", "response_payload"}
        }
    if isinstance(value, list):
        return [_without_raw(item) for item in value]
    return value


def _kr_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    local = now_utc.astimezone(KR_TZ)
    start_local = datetime.combine(local.date(), time.min, tzinfo=KR_TZ)
    end_local = start_local + timedelta(days=1)
    return _naive_utc(start_local), _naive_utc(end_local)


def _utc_now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    return _utc_now(value).replace(tzinfo=None)


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _json(payload: Any) -> str:
    return json.dumps(sanitize_kis_payload(payload), ensure_ascii=False, default=str)


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 180:
        text = f"{text[:180]}..."
    return f"{exc.__class__.__name__}: {text}"
