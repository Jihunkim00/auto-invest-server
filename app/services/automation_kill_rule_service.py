from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog


KST = ZoneInfo("Asia/Seoul")
OPEN_ORDER_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
    "PENDING_SUBMIT",
    "PENDING_SYNC",
    "SYNC_REQUIRED",
}
SYNC_REQUIRED_STATUSES = {
    "UNKNOWN",
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
    "PENDING_SYNC",
    "SYNC_REQUIRED",
}


class AutomationKillRuleService:
    """Evaluates PR99 fail-closed automation kill rules from existing state."""

    def evaluate(
        self,
        db: Session,
        *,
        settings: dict[str, Any],
        provider: str = "kis",
        market: str = "KR",
        soak_mode: str = "dry_run_monitoring",
        watchdog_status: dict[str, Any] | None = None,
        automation_mode_status: dict[str, Any] | None = None,
        production_readiness: dict[str, Any] | None = None,
        daily_ops_summary: dict[str, Any] | None = None,
        orchestrator_result: dict[str, Any] | None = None,
        source_errors: list[str] | None = None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        now_utc = _utc(now)
        watchdog = watchdog_status or {}
        automation = automation_mode_status or {}
        readiness = production_readiness or {}
        daily_ops = daily_ops_summary or {}
        orchestrator = orchestrator_result or {}
        order_metrics = self._order_metrics(
            db,
            provider=provider,
            market=market,
            now_utc=now_utc,
        )
        live_mode = soak_mode == "live_phase1_controlled"
        max_unmatched = max(0, _int(settings.get("automation_soak_max_unmatched_order_count"), 0))
        max_pending_sync = max(0, _int(settings.get("automation_soak_max_pending_sync_count"), 0))
        max_stale = max(0, _int(settings.get("automation_soak_max_stale_order_count"), 0))
        max_failures = max(1, _int(settings.get("automation_soak_max_consecutive_failures"), 2))
        consecutive_failures = max(
            0,
            _int(settings.get("automation_soak_consecutive_failure_count"), 0),
        )
        rules = [
            self._rule(
                "broker_sync_unsafe",
                "Broker sync unsafe",
                "critical",
                _watchdog_blocks(watchdog)
                or str(watchdog.get("sync_health") or "").lower() == "unsafe",
                "watchdog",
                _first(watchdog.get("blocking_reasons"), "broker_sync_unsafe"),
                "review_broker_sync_watchdog",
                now_utc,
            ),
            self._rule(
                "broker_sync_unknown_in_live_mode",
                "Broker sync unknown in live mode",
                "critical",
                live_mode and str(watchdog.get("sync_health") or "unknown").lower() == "unknown",
                "watchdog",
                "broker_sync_health_unknown_for_live_phase1",
                "run_watchdog_or_manual_review",
                now_utc,
            ),
            self._rule(
                "pending_sync_order_present",
                "Pending sync order present",
                "critical",
                max(
                    _int(watchdog.get("pending_sync_order_count")),
                    order_metrics["pending_sync_order_count"],
                )
                > max_pending_sync,
                "watchdog",
                "pending_sync_order_requires_review",
                "reconcile_orders_before_next_cycle",
                now_utc,
            ),
            self._rule(
                "stale_order_present",
                "Stale order present",
                "critical",
                max(
                    _int(watchdog.get("stale_local_order_count")),
                    order_metrics["stale_order_count"],
                )
                > max_stale,
                "watchdog",
                "stale_order_requires_manual_review",
                "review_stale_orders",
                now_utc,
            ),
            self._rule(
                "duplicate_open_order_present",
                "Duplicate open order present",
                "critical",
                order_metrics["duplicate_open_order_count"] > 0,
                "watchdog",
                "duplicate_open_order_risk",
                "review_open_orders_before_next_cycle",
                now_utc,
            ),
            self._rule(
                "broker_unmatched_order_present",
                "Broker unmatched order present",
                "critical",
                _int(watchdog.get("broker_unmatched_order_count")) > max_unmatched,
                "watchdog",
                "broker_order_missing_local_record",
                "inspect_broker_app",
                now_utc,
            ),
            self._rule(
                "local_unmatched_order_present",
                "Local unmatched order present",
                "critical",
                _int(watchdog.get("local_unmatched_order_count")) > max_unmatched,
                "watchdog",
                "local_order_missing_broker_record",
                "manual_order_reconciliation",
                now_utc,
            ),
            self._rule(
                "position_quantity_mismatch",
                "Position quantity mismatch",
                "critical",
                _int(watchdog.get("position_mismatch_count")) > 0,
                "watchdog",
                "position_quantity_mismatch",
                "manual_position_reconciliation",
                now_utc,
            ),
            self._rule(
                "production_readiness_blocked",
                "Production readiness blocked",
                "critical",
                str(readiness.get("overall_status") or "unknown").lower() == "blocked",
                "readiness",
                "production_readiness_not_ready",
                "review_production_readiness",
                now_utc,
            ),
            self._rule(
                "automation_mode_not_ready",
                "Automation mode not ready",
                "critical",
                self._automation_mode_blocks(automation, live_mode=live_mode),
                "automation_mode",
                _first(automation.get("blocking_reasons"), "automation_mode_not_ready"),
                "review_automation_mode_control",
                now_utc,
            ),
            self._rule(
                "kill_switch_on",
                "Kill switch on",
                "critical",
                bool(settings.get("kill_switch")),
                "runtime_settings",
                "kill_switch_enabled",
                "review_kill_switch_without_changing_it_here",
                now_utc,
            ),
            self._rule(
                "dry_run_on_for_live_mode",
                "Dry-run on for live mode",
                "critical",
                live_mode and bool(settings.get("dry_run", True)),
                "runtime_settings",
                "dry_run_enabled_for_live_phase1",
                "review_dry_run_setting_separately",
                now_utc,
            ),
            self._rule(
                "kis_real_orders_disabled_for_live_mode",
                "KIS real orders disabled for live mode",
                "critical",
                live_mode and not bool(settings.get("_app_kis_real_order_enabled")),
                "runtime_settings",
                "kis_real_orders_disabled_for_live_phase1",
                "review_broker_real_order_setting_separately",
                now_utc,
            ),
            self._rule(
                "daily_trade_limit_exhausted",
                "Daily trade limit exhausted",
                "critical",
                bool(settings.get("_daily_action_limit_exhausted")),
                "runtime_settings",
                "daily_action_limit_exhausted",
                "wait_for_next_trading_day",
                now_utc,
            ),
            self._rule(
                "daily_loss_limit_breached",
                "Daily loss limit breached",
                "critical",
                self._daily_loss_breached(settings, daily_ops),
                "daily_pnl",
                "daily_loss_limit_breached",
                "stop_automation_and_review_pnl",
                now_utc,
            ),
            self._rule(
                "consecutive_failures_exceeded",
                "Consecutive failures exceeded",
                "critical",
                consecutive_failures >= max_failures,
                "runtime_settings",
                "automation_soak_consecutive_failures_exceeded",
                "review_recent_soak_failures",
                now_utc,
            ),
            self._rule(
                "unexpected_broker_submit_flag",
                "Unexpected broker submit flag",
                "critical",
                bool(orchestrator.get("broker_submit_called"))
                and (
                    soak_mode == "dry_run_monitoring"
                    or str(orchestrator.get("result_status") or "").lower()
                    not in {"sell_submitted", "buy_submitted"}
                ),
                "orchestrator",
                "unexpected_broker_submit_flag",
                "audit_orchestrator_and_phase_result",
                now_utc,
            ),
            self._rule(
                "unexpected_manual_submit_flag",
                "Unexpected manual submit flag",
                "critical",
                bool(orchestrator.get("manual_submit_called")),
                "orchestrator",
                "unexpected_manual_submit_flag",
                "audit_orchestrator_and_phase_result",
                now_utc,
            ),
            self._rule(
                "unexpected_order_cancel_flag",
                "Unexpected order cancellation flag",
                "critical",
                bool(orchestrator.get("order_cancel_called")),
                "orchestrator",
                "unexpected_order_cancel_flag",
                "audit_orchestrator_and_phase_result",
                now_utc,
            ),
            self._rule(
                "orchestrator_unexpected_error",
                "Orchestrator unexpected error",
                "critical",
                str(orchestrator.get("result_status") or "").lower() == "error",
                "orchestrator",
                str(orchestrator.get("primary_block_reason") or "orchestrator_error"),
                "review_orchestrator_error",
                now_utc,
            ),
            self._rule(
                "phase_service_unexpected_error",
                "Phase service unexpected error",
                "critical",
                self._phase_error(orchestrator),
                "orchestrator",
                "phase_service_unexpected_error",
                "review_phase_service_result",
                now_utc,
            ),
            self._rule(
                "stale_account_snapshot",
                "Stale account snapshot",
                "warning",
                _int(watchdog.get("stale_position_snapshot_count")) > 0
                or bool(watchdog.get("cash_snapshot_stale")),
                "watchdog",
                "account_or_position_snapshot_stale",
                "refresh_account_snapshot_before_live_cycle",
                now_utc,
                automation_blocking=False,
            ),
            self._rule(
                "unknown",
                "Unknown safety source",
                "warning",
                bool(source_errors),
                "unknown",
                "; ".join(source_errors or []) or "unknown_safety_source",
                "manual_review",
                now_utc,
                automation_blocking=live_mode,
            ),
        ]
        return rules

    def _automation_mode_blocks(
        self,
        automation: dict[str, Any],
        *,
        live_mode: bool,
    ) -> bool:
        if not automation:
            return live_mode
        if live_mode:
            return not bool(automation.get("can_attempt_phase1_live")) or not bool(
                automation.get("can_submit_live_order")
            )
        return False

    def _daily_loss_breached(
        self,
        settings: dict[str, Any],
        daily_ops: dict[str, Any],
    ) -> bool:
        pnl = daily_ops.get("pnl_summary")
        if not isinstance(pnl, dict):
            return False
        max_pct = _float_or_none(settings.get("automation_soak_max_daily_loss_pct"))
        realized_pct = _float_or_none(pnl.get("realized_pl_pct"))
        if max_pct is not None and max_pct > 0 and realized_pct is not None:
            if realized_pct <= -abs(max_pct):
                return True
        max_amount = _float_or_none(settings.get("automation_soak_max_daily_loss_amount"))
        realized = _float_or_none(pnl.get("realized_pl"))
        if max_amount is not None and max_amount > 0 and realized is not None:
            return realized <= -abs(max_amount)
        return False

    def _phase_error(self, orchestrator: dict[str, Any]) -> bool:
        for key in ("auto_sell_phase1_result", "auto_buy_phase1_result"):
            payload = orchestrator.get(key)
            if not isinstance(payload, dict):
                continue
            if str(payload.get("result_status") or "").lower() == "error":
                return True
        return False

    def _order_metrics(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
        now_utc: datetime,
    ) -> dict[str, int]:
        rows = (
            db.query(OrderLog)
            .filter(OrderLog.broker == provider)
            .filter(or_(OrderLog.market == market, OrderLog.market.is_(None)))
            .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
            .limit(1000)
            .all()
        )
        duplicate_counts: dict[tuple[str, str], int] = {}
        pending_sync = 0
        stale = 0
        for row in rows:
            status = _status(row)
            open_order = status in OPEN_ORDER_STATUSES
            if _needs_sync(row):
                pending_sync += 1
            if open_order and _latest_age(now_utc, row) > timedelta(hours=24):
                stale += 1
            if open_order and not _is_dry_run(row):
                key = (str(row.symbol or "").strip().upper(), str(row.side or "").strip().lower())
                if key[0] and key[1]:
                    duplicate_counts[key] = duplicate_counts.get(key, 0) + 1
        duplicate_count = sum(max(0, count - 1) for count in duplicate_counts.values())
        return {
            "pending_sync_order_count": pending_sync,
            "stale_order_count": stale,
            "duplicate_open_order_count": duplicate_count,
        }

    def _rule(
        self,
        rule_id: str,
        name: str,
        severity: str,
        triggered: bool,
        source: str,
        reason: str,
        recommended_action: str,
        detected_at: datetime,
        *,
        automation_blocking: bool | None = None,
    ) -> dict[str, Any]:
        blocking = severity == "critical" if automation_blocking is None else automation_blocking
        return {
            "rule_id": rule_id,
            "name": name,
            "severity": severity,
            "triggered": bool(triggered),
            "automation_blocking": bool(blocking and triggered),
            "reason": reason,
            "detected_at": detected_at.isoformat(),
            "source": source,
            "recommended_action": recommended_action,
        }


def _watchdog_blocks(value: dict[str, Any]) -> bool:
    return bool(
        value.get("automation_blocked_by_sync")
        or value.get("should_block_orchestrator")
        or value.get("should_block_auto_buy")
        or value.get("should_block_auto_sell")
    )


def _first(value: Any, fallback: str) -> str:
    if isinstance(value, list):
        for item in value:
            text = str(item or "").strip()
            if text:
                return text
    text = str(value or "").strip()
    return text or fallback


def _status(row: OrderLog) -> str:
    return str(row.internal_status or "").strip().upper()


def _needs_sync(row: OrderLog) -> bool:
    text = " ".join(
        [
            str(row.broker_status or ""),
            str(row.broker_order_status or ""),
            str(row.sync_error or ""),
        ]
    ).lower()
    return _status(row) in SYNC_REQUIRED_STATUSES or "sync_required" in text or "pending_sync" in text


def _latest_age(now_utc: datetime, row: OrderLog) -> timedelta:
    latest: datetime | None = None
    for value in (row.last_synced_at, row.updated_at, row.submitted_at, row.created_at):
        if value is None:
            continue
        current = _utc(value)
        latest = current if latest is None else max(latest, current)
    return now_utc - (latest or now_utc)


def _is_dry_run(row: OrderLog) -> bool:
    if _status(row) == InternalOrderStatus.DRY_RUN_SIMULATED.value:
        return True
    for raw in (row.request_payload, row.response_payload, row.last_sync_payload):
        payload = _json_dict(raw)
        if payload.get("dry_run") is True or payload.get("simulated") is True:
            return True
    return False


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _utc(value: Any | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        value = datetime.fromisoformat(text)
    if not isinstance(value, datetime):
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except Exception:
        return default


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def kr_day_bounds(now_utc: datetime) -> tuple[datetime, datetime]:
    local = _utc(now_utc).astimezone(KST)
    start_local = datetime.combine(local.date(), time.min, tzinfo=KST)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC).replace(tzinfo=None), end_local.astimezone(UTC).replace(tzinfo=None)
