from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, RuntimeSetting, TradeRunLog
from app.services.broker_sync_watchdog_service import BrokerSyncWatchdogService
from app.services.ops_production_readiness_service import (
    OpsProductionReadinessService,
)
from app.services.runtime_setting_service import RuntimeSettingService


ALLOWED_AUTOMATION_MODES = {
    "off",
    "monitor_only",
    "dry_run_auto",
    "phase1_live_ready",
}
ACK_REQUIRED_MODES = {"dry_run_auto", "phase1_live_ready"}
PROVIDER = "kis"
MARKET = "KR"
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
}
SYNC_REQUIRED_STATUSES = {
    "UNKNOWN",
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
}
COUNTED_TRADE_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}


class AutomationModeAcknowledgementRequired(ValueError):
    pass


class AutomationModeControlService:
    """Central mode/status coordinator for existing automation switches."""

    def __init__(
        self,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        readiness_service: OpsProductionReadinessService | None = None,
        broker_sync_watchdog_service: BrokerSyncWatchdogService | None = None,
    ) -> None:
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.readiness_service = readiness_service or OpsProductionReadinessService(
            runtime_settings=self.runtime_settings
        )
        self.broker_sync_watchdog_service = (
            broker_sync_watchdog_service
            or BrokerSyncWatchdogService(runtime_settings=self.runtime_settings)
        )

    def status(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc(now)
        settings = self.runtime_settings.get_settings_read_only(db)
        mode = _mode(settings.get("automation_mode"))
        app_settings = getattr(self.runtime_settings, "settings", None)
        kis_enabled = bool(getattr(app_settings, "kis_enabled", False))
        kis_real_order_enabled = bool(
            getattr(app_settings, "kis_real_order_enabled", False)
        )
        production_status = self._production_readiness_status(db, now_utc=now_utc)
        blockers = self._pending_order_blockers(db, now_utc=now_utc)
        broker_sync = self._broker_sync_status(db, now_utc=now_utc)
        broker_sync_health = str(broker_sync.get("sync_health") or "unknown")
        broker_sync_blocking_reasons = _string_list(
            broker_sync.get("blocking_reasons")
        )
        broker_sync_issue_count = len(
            broker_sync.get("issues") if isinstance(broker_sync.get("issues"), list) else []
        )
        sync_required_count = len(
            [item for item in blockers if item.get("sync_required") is True]
        )
        daily_remaining = self._daily_trade_limit_remaining(
            db,
            settings=settings,
            now_utc=now_utc,
        )
        critical_exit_count = self._latest_critical_exit_candidate_count(db)

        blocking_reasons: list[str] = []
        warning_reasons: list[str] = []
        can_run_monitoring = mode in {"monitor_only", "dry_run_auto", "phase1_live_ready"}
        can_run_dry_run = mode == "dry_run_auto"

        if mode == "off":
            blocking_reasons.append("automation_mode_off")
            effective_status = "off"
            can_attempt_phase1_live = False
            can_submit_live_order = False
        elif mode == "monitor_only":
            blocking_reasons.append("phase1_live_disabled_in_monitor_only")
            effective_status = "monitoring"
            can_attempt_phase1_live = False
            can_submit_live_order = False
        elif mode == "dry_run_auto":
            blocking_reasons.append("phase1_live_disabled_in_dry_run_auto")
            effective_status = "dry_run_ready"
            can_attempt_phase1_live = False
            can_submit_live_order = False
        else:
            live_gate_reasons = self._live_gate_blockers(
                settings=settings,
                kis_enabled=kis_enabled,
                kis_real_order_enabled=kis_real_order_enabled,
                production_status=production_status,
                pending_order_blocker_count=len(blockers),
                sync_required_count=sync_required_count,
                broker_sync_should_block=bool(
                    broker_sync.get("should_block_orchestrator")
                    or broker_sync.get("should_block_auto_buy")
                    or broker_sync.get("should_block_auto_sell")
                ),
                daily_trade_limit_remaining=daily_remaining,
            )
            blocking_reasons.extend(live_gate_reasons)
            can_submit_live_order = not live_gate_reasons
            can_attempt_phase1_live = can_submit_live_order
            effective_status = "live_ready" if can_submit_live_order else "live_ready_blocked"

        if settings.get("dry_run") is True and mode != "off":
            warning_reasons.append("dry_run_is_separate")
        if settings.get("kill_switch") is True and mode != "off":
            warning_reasons.append("kill_switch_is_separate")
        soak_latch_active = bool(settings.get("automation_soak_kill_latch_active"))
        if soak_latch_active:
            blocking_reasons.append("automation_soak_kill_latch_active")
            effective_status = "kill_latched"
            can_attempt_phase1_live = False
            can_submit_live_order = False
            can_run_dry_run = False
        if not kis_real_order_enabled and mode != "off":
            warning_reasons.append("kis_real_orders_are_separate")
        if production_status not in {"ready", "warning"} and mode != "off":
            warning_reasons.append("production_readiness_needs_review")
        if broker_sync_health in {"unsafe", "unknown"} and mode != "off":
            warning_reasons.append("broker_sync_needs_review")

        blocking_reasons = _dedupe(blocking_reasons)
        warning_reasons = _dedupe(warning_reasons)
        return {
            "generated_at": now_utc.isoformat(),
            "automation_mode": mode,
            "mode_label": _mode_label(mode),
            "mode_description": _mode_description(mode),
            "mode_updated_at": _iso(settings.get("automation_mode_updated_at")),
            "mode_updated_by": _text(settings.get("automation_mode_updated_by")),
            "mode_reason": _text(settings.get("automation_mode_reason")),
            "mode_requires_manual_review": bool(
                settings.get("automation_mode_requires_manual_review", True)
            ),
            "effective_status": effective_status,
            "can_run_monitoring": can_run_monitoring,
            "can_run_dry_run": can_run_dry_run,
            "can_attempt_phase1_live": can_attempt_phase1_live,
            "can_submit_live_order": can_submit_live_order,
            "kill_switch": bool(settings.get("kill_switch")),
            "dry_run": bool(settings.get("dry_run", True)),
            "kis_enabled": kis_enabled,
            "kis_real_order_enabled": kis_real_order_enabled,
            "production_readiness_status": production_status,
            "broker_sync_health": broker_sync_health,
            "broker_sync_blocking_reasons": broker_sync_blocking_reasons,
            "broker_sync_issue_count": broker_sync_issue_count,
            "broker_sync_watchdog": broker_sync,
            "portfolio_orchestrator_enabled": bool(
                settings.get("portfolio_orchestrator_enabled")
            ),
            "portfolio_orchestrator_allow_live_orders": bool(
                settings.get("portfolio_orchestrator_allow_live_orders")
            ),
            "position_management_scheduler_enabled": bool(
                settings.get("position_management_scheduler_enabled")
            ),
            "auto_buy_live_phase1_enabled": bool(
                settings.get("auto_buy_live_phase1_enabled")
            ),
            "auto_sell_live_phase1_enabled": bool(
                settings.get("auto_sell_live_phase1_enabled")
            ),
            "scheduler_enabled": bool(settings.get("scheduler_enabled")),
            "pending_order_blockers": blockers,
            "sync_required_count": sync_required_count,
            "critical_exit_candidate_count": critical_exit_count,
            "daily_trade_limit_remaining": daily_remaining,
            "soak_kill_latch_active": soak_latch_active,
            "soak_kill_latch_reason": _text(
                settings.get("automation_soak_kill_latch_reason")
            ),
            "soak_kill_latch_triggered_at": _iso(
                settings.get("automation_soak_kill_latch_triggered_at")
            ),
            "blocking_reasons": blocking_reasons,
            "warning_reasons": warning_reasons,
            "next_safe_action": _next_safe_action(
                mode,
                effective_status,
                blocking_reasons,
            ),
            "safety_flags": self._safety_flags(),
            "modules": self._modules(settings),
        }

    def set_mode(
        self,
        db: Session,
        *,
        automation_mode: str,
        reason: str | None = None,
        operator_acknowledged_risks: bool = False,
        updated_by: str = "api",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        mode = _mode(automation_mode)
        if mode in ACK_REQUIRED_MODES and not operator_acknowledged_risks:
            raise AutomationModeAcknowledgementRequired(
                f"{mode} requires operator_acknowledged_risks=true"
            )

        payload = self._mode_payload(mode)
        self.runtime_settings.update_settings(db, payload)
        self._set_mode_metadata(
            db,
            mode=mode,
            reason=reason,
            updated_by=updated_by,
            now=_utc(now),
        )
        return self.status(db, now=now)

    def turn_off(
        self,
        db: Session,
        *,
        reason: str | None = None,
        updated_by: str = "api",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self.runtime_settings.update_settings(db, self._off_payload())
        self._set_mode_metadata(
            db,
            mode="off",
            reason=reason or "automation_off_endpoint",
            updated_by=updated_by,
            now=_utc(now),
        )
        return self.status(db, now=now)

    def _mode_payload(self, mode: str) -> dict[str, Any]:
        if mode == "off":
            return self._off_payload()
        if mode == "monitor_only":
            payload = self._off_payload()
            payload.update(
                {
                    "scheduler_enabled": False,
                    "position_management_scheduler_enabled": False,
                }
            )
            return payload
        if mode == "dry_run_auto":
            payload = self._off_payload()
            payload.update(
                {
                    "scheduler_enabled": True,
                    "position_management_scheduler_enabled": True,
                    "position_management_scheduler_dry_run_only": True,
                    "position_management_scheduler_allow_live_orders": False,
                    "portfolio_orchestrator_enabled": True,
                    "portfolio_orchestrator_allow_live_orders": False,
                }
            )
            return payload
        if mode == "phase1_live_ready":
            return {
                "scheduler_enabled": True,
                "position_management_scheduler_enabled": True,
                "position_management_scheduler_dry_run_only": True,
                "position_management_scheduler_allow_live_orders": False,
                "portfolio_orchestrator_enabled": True,
                "portfolio_orchestrator_allow_live_orders": True,
                "auto_buy_live_phase1_enabled": True,
                "auto_buy_live_phase1_allow_real_orders": True,
                "auto_sell_live_phase1_enabled": True,
                "auto_sell_live_phase1_allow_real_orders": True,
            }
        raise ValueError(f"unsupported automation mode: {mode}")

    def _off_payload(self) -> dict[str, Any]:
        return {
            "scheduler_enabled": False,
            "position_management_scheduler_enabled": False,
            "position_management_scheduler_dry_run_only": True,
            "position_management_scheduler_allow_live_orders": False,
            "portfolio_orchestrator_enabled": False,
            "portfolio_orchestrator_allow_live_orders": False,
            "auto_buy_live_phase1_enabled": False,
            "auto_buy_live_phase1_allow_real_orders": False,
            "auto_sell_live_phase1_enabled": False,
            "auto_sell_live_phase1_allow_real_orders": False,
            "strategy_auto_buy_scheduler_enabled": False,
            "strategy_auto_buy_scheduler_dry_run_only": True,
            "strategy_auto_buy_scheduler_allow_live_orders": False,
            "strategy_live_auto_buy_scheduler_enabled": False,
            "strategy_live_auto_exit_scheduler_enabled": False,
        }

    def _set_mode_metadata(
        self,
        db: Session,
        *,
        mode: str,
        reason: str | None,
        updated_by: str,
        now: datetime,
    ) -> None:
        row = self.runtime_settings.get_or_create(db)
        row.automation_mode = mode
        row.automation_mode_updated_at = now
        row.automation_mode_updated_by = str(updated_by or "api")[:80]
        row.automation_mode_reason = _text(reason)
        row.automation_mode_requires_manual_review = True
        db.commit()
        db.refresh(row)

    def _production_readiness_status(
        self,
        db: Session,
        *,
        now_utc: datetime,
    ) -> str:
        try:
            payload = self.readiness_service.readiness(
                db,
                provider=PROVIDER,
                market=MARKET,
                include_details=False,
                include_recent=False,
                now=now_utc,
            )
            return str(payload.get("overall_status") or "unknown").lower()
        except Exception:
            return "unknown"

    def _pending_order_blockers(
        self,
        db: Session,
        *,
        now_utc: datetime,
    ) -> list[dict[str, Any]]:
        rows = (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(or_(OrderLog.market == MARKET, OrderLog.market.is_(None)))
            .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
            .limit(500)
            .all()
        )
        blockers: list[dict[str, Any]] = []
        for row in rows:
            status = str(row.internal_status or "").strip().upper()
            broker_text = " ".join(
                [
                    str(row.broker_status or ""),
                    str(row.broker_order_status or ""),
                    str(row.sync_error or ""),
                ]
            ).lower()
            sync_required = (
                status in SYNC_REQUIRED_STATUSES
                or "sync_required" in broker_text
                or "pending_sync" in broker_text
            )
            stale_open = False
            if status in OPEN_ORDER_STATUSES and row.created_at is not None:
                stale_open = now_utc - _utc(row.created_at) > timedelta(hours=24)
            if status not in OPEN_ORDER_STATUSES and not sync_required and not stale_open:
                continue
            blockers.append(
                {
                    "order_id": row.id,
                    "symbol": row.symbol,
                    "side": row.side,
                    "internal_status": status,
                    "sync_required": bool(sync_required or stale_open),
                    "reason": "sync_required"
                    if sync_required or stale_open
                    else "pending_order",
                }
            )
            if len(blockers) >= 20:
                break
        return blockers

    def _daily_trade_limit_remaining(
        self,
        db: Session,
        *,
        settings: dict[str, Any],
        now_utc: datetime,
    ) -> int:
        limit = max(0, _int(settings.get("max_trades_per_day"), 0))
        if limit <= 0:
            return 0
        start_utc, end_utc = _kr_day_bounds(now_utc)
        used = (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(or_(OrderLog.market == MARKET, OrderLog.market.is_(None)))
            .filter(OrderLog.created_at >= start_utc)
            .filter(OrderLog.created_at < end_utc)
            .filter(OrderLog.internal_status.in_(sorted(COUNTED_TRADE_STATUSES)))
            .count()
        )
        return max(0, limit - used)

    def _latest_critical_exit_candidate_count(self, db: Session) -> int:
        row = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == "position_management_dry_run")
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .first()
        )
        if row is None:
            return 0
        payload = _json_dict(row.response_payload)
        count = _int(payload.get("critical_candidate_count"), 0)
        candidates = payload.get("candidates")
        if isinstance(candidates, list):
            count = max(
                count,
                len(
                    [
                        item
                        for item in candidates
                        if isinstance(item, dict)
                        and str(item.get("severity") or "").lower() == "critical"
                    ]
                ),
            )
        return count

    def _live_gate_blockers(
        self,
        *,
        settings: dict[str, Any],
        kis_enabled: bool,
        kis_real_order_enabled: bool,
        production_status: str,
        pending_order_blocker_count: int,
        sync_required_count: int,
        broker_sync_should_block: bool,
        daily_trade_limit_remaining: int,
    ) -> list[str]:
        checks = [
            (not bool(settings.get("dry_run", True)), "dry_run_enabled"),
            (not bool(settings.get("kill_switch")), "kill_switch_enabled"),
            (kis_enabled, "kis_disabled"),
            (kis_real_order_enabled, "kis_real_order_disabled"),
            (production_status == "ready", "production_readiness_not_ready"),
            (
                bool(settings.get("portfolio_orchestrator_enabled")),
                "portfolio_orchestrator_disabled",
            ),
            (
                bool(settings.get("portfolio_orchestrator_allow_live_orders")),
                "portfolio_orchestrator_live_orders_disabled",
            ),
            (
                bool(settings.get("auto_buy_live_phase1_enabled")),
                "auto_buy_live_phase1_disabled",
            ),
            (
                bool(settings.get("auto_buy_live_phase1_allow_real_orders")),
                "auto_buy_live_phase1_real_orders_disabled",
            ),
            (
                bool(settings.get("auto_sell_live_phase1_enabled")),
                "auto_sell_live_phase1_disabled",
            ),
            (
                bool(settings.get("auto_sell_live_phase1_allow_real_orders")),
                "auto_sell_live_phase1_real_orders_disabled",
            ),
            (pending_order_blocker_count == 0, "pending_order_blocker_exists"),
            (sync_required_count == 0, "sync_required_order_exists"),
            (not broker_sync_should_block, "broker_sync_watchdog_blocked"),
            (daily_trade_limit_remaining > 0, "daily_trade_limit_reached"),
        ]
        return [reason for ok, reason in checks if not ok]

    def _broker_sync_status(
        self,
        db: Session,
        *,
        now_utc: datetime,
    ) -> dict[str, Any]:
        try:
            return self.broker_sync_watchdog_service.status(
                db,
                provider=PROVIDER,
                market=MARKET,
                persist=False,
                now=now_utc,
                trigger_source="automation_mode_status",
            )
        except Exception as exc:
            return {
                "sync_health": "unknown",
                "should_block_auto_buy": True,
                "should_block_auto_sell": True,
                "should_block_orchestrator": True,
                "issues": [],
                "blocking_reasons": [
                    f"broker_sync_watchdog_failed:{exc.__class__.__name__}"
                ],
                "next_safe_action": "manual_review",
                "safety_flags": {
                    "read_only": True,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                    "order_cancel_called": False,
                },
            }

    def _modules(self, settings: dict[str, Any]) -> dict[str, Any]:
        return {
            "portfolio_orchestrator": {
                "enabled": bool(settings.get("portfolio_orchestrator_enabled")),
                "allow_live_orders": bool(
                    settings.get("portfolio_orchestrator_allow_live_orders")
                ),
            },
            "position_management_scheduler": {
                "enabled": bool(settings.get("position_management_scheduler_enabled")),
                "dry_run_only": True,
                "allow_live_orders": False,
            },
            "auto_buy_live_phase1": {
                "enabled": bool(settings.get("auto_buy_live_phase1_enabled")),
                "allow_real_orders": bool(
                    settings.get("auto_buy_live_phase1_allow_real_orders")
                ),
            },
            "auto_sell_live_phase1": {
                "enabled": bool(settings.get("auto_sell_live_phase1_enabled")),
                "allow_real_orders": bool(
                    settings.get("auto_sell_live_phase1_allow_real_orders")
                ),
            },
            "scheduler": {
                "enabled": bool(settings.get("scheduler_enabled")),
            },
            "automation_release": {
                "enabled": bool(settings.get("automation_release_enabled")),
                "mode": str(
                    settings.get("automation_release_mode") or "controlled_phase1"
                ),
                "allow_live_phase1": bool(
                    settings.get("automation_release_allow_live_phase1")
                ),
                "scheduler_enabled": bool(
                    settings.get("automation_release_scheduler_enabled")
                ),
            },
        }

    def _safety_flags(self) -> dict[str, Any]:
        return {
            "control_center_only": True,
            "settings_changed_only": True,
            "orders_mutated": False,
            "order_log_created": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "real_order_submitted": False,
            "dry_run_changed": False,
            "kill_switch_changed": False,
            "kis_real_order_enabled_changed": False,
            "agent_chat_can_change_mode": False,
            "soak_kill_latch_blocks_automation": True,
        }


def _mode(value: Any) -> str:
    mode = str(value or "off").strip().lower()
    if mode not in ALLOWED_AUTOMATION_MODES:
        raise ValueError(f"unsupported automation mode: {mode}")
    return mode


def _mode_label(mode: str) -> str:
    return {
        "off": "Automation Off",
        "monitor_only": "Monitoring Only",
        "dry_run_auto": "Dry-Run Automation",
        "phase1_live_ready": "Phase 1 Live Ready",
    }.get(mode, "Automation Off")


def _mode_description(mode: str) -> str:
    return {
        "off": "All automation layer flags are disabled.",
        "monitor_only": "Read-only monitoring and diagnostics may be reviewed.",
        "dry_run_auto": "Dry-run position management and orchestration may run.",
        "phase1_live_ready": (
            "Phase-one orchestration flags are armed, but independent safety "
            "gates still decide live eligibility."
        ),
    }.get(mode, "All automation layer flags are disabled.")


def _next_safe_action(
    mode: str,
    effective_status: str,
    blocking_reasons: list[str],
) -> str:
    if mode == "off":
        return "automation_is_off"
    if mode == "monitor_only":
        return "review_monitoring_status"
    if mode == "dry_run_auto":
        return "review_dry_run_results"
    if effective_status == "live_ready":
        return "run_phase1_orchestrator_only_if_operator_intends"
    if not blocking_reasons:
        return "review_phase1_live_readiness"
    first = blocking_reasons[0]
    mapping = {
        "dry_run_enabled": "review_dry_run_setting_without_changing_it_here",
        "kill_switch_enabled": "review_kill_switch_without_changing_it_here",
        "kis_real_order_disabled": "review_broker_real_order_setting_separately",
        "production_readiness_not_ready": "review_production_readiness",
        "pending_order_blocker_exists": "review_pending_orders",
        "sync_required_order_exists": "reconcile_orders_before_live_automation",
        "broker_sync_watchdog_blocked": "review_broker_sync_watchdog",
        "daily_trade_limit_reached": "wait_for_next_trading_day",
    }
    return mapping.get(first, "review_blocking_reasons")


def _kr_day_bounds(now_utc: datetime) -> tuple[datetime, datetime]:
    local = _utc(now_utc).astimezone(KST)
    start_local = datetime.combine(local.date(), time.min, tzinfo=KST)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC).replace(tzinfo=None), end_local.astimezone(
        UTC
    ).replace(tzinfo=None)


def _utc(value: Any | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value))
    except Exception:
        return datetime.now(UTC)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    text = str(value or "").strip()
    return text or None


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        payload = json.loads(str(value))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in values if str(item or "").strip()))

