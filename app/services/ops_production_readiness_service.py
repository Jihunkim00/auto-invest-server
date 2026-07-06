from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, RuntimeSetting, StrategyProfile, TradeRunLog
from app.services.agent_chat_tool_registry import AgentChatToolRegistry
from app.services.operator_alerts_service import OperatorAlertsService
from app.services.position_lifecycle_audit_service import PositionLifecycleAuditService
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "ops_production_readiness"
DEFAULT_PROVIDER = "kis"
DEFAULT_MARKET = "KR"
KST = ZoneInfo("Asia/Seoul")

OPEN_ORDER_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
}
LIVE_ID_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}
REJECTED_ORDER_STATUSES = {
    InternalOrderStatus.REJECTED.value,
    InternalOrderStatus.FAILED.value,
    InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value,
}
PENDING_SYNC_STATUSES = {
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
}
EXPECTED_TABLES = {
    "orders",
    "trade_run_logs",
    "runtime_settings",
    "strategy_profiles",
    "strategy_auto_buy_promotions",
    "strategy_live_auto_buy_attempts",
    "strategy_live_auto_exit_attempts",
    "agent_chat_order_actions",
}


class OpsProductionReadinessService:
    """Read-only production readiness checklist from local state."""

    def __init__(
        self,
        client: KisClient | None = None,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        alerts_service: OperatorAlertsService | None = None,
        lifecycle_service: PositionLifecycleAuditService | None = None,
        tool_registry: AgentChatToolRegistry | None = None,
    ) -> None:
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.alerts_service = alerts_service or OperatorAlertsService(
            runtime_settings=self.runtime_settings,
        )
        self.lifecycle_service = lifecycle_service or PositionLifecycleAuditService()
        self.tool_registry = tool_registry or AgentChatToolRegistry()

    def readiness(
        self,
        db: Session,
        *,
        provider: str | None = None,
        market: str | None = None,
        include_details: bool = True,
        days: int = 7,
        include_recent: bool = True,
        now: datetime | None = None,
        include_raw: bool | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc(now)
        generated_at = now_utc.astimezone(KST).isoformat()
        safe_provider = _provider(provider)
        safe_market = _market(market, safe_provider)
        safe_days = max(1, min(int(days or 7), 365))

        runtime = self._runtime_snapshot(db)
        app_settings = self._app_settings()
        app_flags = _app_safety_flags(app_settings)
        active_profile = _active_profile_snapshot(db)
        orders = _order_metrics(
            db,
            provider=safe_provider,
            market=safe_market,
            now=now_utc,
        )
        recent = (
            _recent_activity(
                db,
                provider=safe_provider,
                market=safe_market,
                now=now_utc,
                days=safe_days,
            )
            if include_recent
            else {"items": [], "scheduler_run_count": 0, "dry_run_count": 0}
        )
        positions = self._position_metrics(
            db,
            provider=safe_provider,
            market=safe_market,
        )
        alerts = self._alert_metrics(
            db,
            provider=safe_provider,
            market=safe_market,
        )
        database = _database_metrics(db)
        agent_chat = _agent_chat_metrics(self.tool_registry)
        guarded = _guarded_readiness(runtime=runtime, app_flags=app_flags)

        checklist = _build_checklist(
            provider=safe_provider,
            market=safe_market,
            runtime=runtime,
            app_flags=app_flags,
            active_profile=active_profile,
            orders=orders,
            positions=positions,
            alerts=alerts,
            database=database,
            recent=recent,
            agent_chat=agent_chat,
            guarded=guarded,
        )
        summary = _summary(checklist, guarded=guarded, alerts=alerts, orders=orders)
        overall_status = _overall_status(summary)
        score = _readiness_score(checklist)
        blocking_reasons = _blocking_reasons(checklist)
        warnings = _warning_reasons(checklist)
        next_actions = _next_actions(checklist)
        safety_flags = {
            "read_only": True,
            "readiness_only": True,
            "no_live_orders": True,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "validation_called": False,
            "broker_sync_called": False,
            "settings_changed": False,
            "scheduler_changed": False,
            "orders_mutated": False,
            "dry_run_changed": False,
            "kill_switch_changed": False,
            "kis_real_order_enabled_changed": False,
            "can_enable_scheduler_live_orders": False,
            "scheduler_real_orders_allowed": False,
            "automation_unlock_allowed": False,
            "agent_chat_trading_allowed": False,
        }

        details = {
            "runtime": _runtime_details(runtime, app_flags, active_profile),
            "orders": orders,
            "positions": positions,
            "alerts": alerts,
            "database": database,
            "agent_chat": agent_chat,
            "guarded": guarded,
            "recent": recent,
        }
        response: dict[str, Any] = {
            "generated_at": generated_at,
            "timezone": "Asia/Seoul",
            "provider": safe_provider,
            "market": safe_market,
            "overall_status": overall_status,
            "readiness_score": score,
            "summary": summary,
            "checklist": checklist,
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
            "next_safe_actions": next_actions,
            "safety_flags": safety_flags,
            "details": details if include_details else {},
        }
        response.update(
            _legacy_projection(
                response,
                runtime=runtime,
                app_flags=app_flags,
                orders=orders,
                recent=recent,
                positions=positions,
                alerts=alerts,
                database=database,
            )
        )
        return response

    def _runtime_snapshot(self, db: Session) -> dict[str, Any]:
        row = db.query(RuntimeSetting).first()
        values = self.runtime_settings.get_settings_read_only(db)
        values["source"] = "runtime_row" if row is not None else "defaults_no_runtime_row"
        values["updated_at"] = _iso(getattr(row, "updated_at", None)) if row else None
        return values

    def _app_settings(self) -> Any:
        if self.client is not None and getattr(self.client, "settings", None) is not None:
            return self.client.settings
        return get_settings()

    def _alert_metrics(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
    ) -> dict[str, Any]:
        try:
            payload = self.alerts_service.alerts(
                db,
                severity="all",
                status="active",
                provider=provider,
                market=market,
                limit=200,
                include_details=False,
            )
            source_summary = payload.get("summary")
            summary = source_summary if isinstance(source_summary, dict) else {}
            return {
                "available": True,
                "active_alert_count": _int(summary.get("active_alert_count")),
                "critical_alert_count": _int(summary.get("critical_count")),
                "warning_alert_count": _int(summary.get("warning_count")),
                "info_alert_count": _int(summary.get("info_count")),
                "sync_required_alert_count": _int(summary.get("sync_required_count")),
                "rejected_order_alert_count": _int(summary.get("rejected_order_count")),
                "incomplete_pl_alert_count": _int(summary.get("incomplete_pl_count")),
            }
        except Exception as exc:
            return {
                "available": False,
                "active_alert_count": 0,
                "critical_alert_count": 0,
                "warning_alert_count": 0,
                "info_alert_count": 0,
                "sync_required_alert_count": 0,
                "rejected_order_alert_count": 0,
                "incomplete_pl_alert_count": 0,
                "error": _safe_error(exc),
            }

    def _position_metrics(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
    ) -> dict[str, Any]:
        try:
            payload = self.lifecycle_service.list(
                db,
                provider=provider,
                market=market,
                limit=200,
                include_events=False,
            )
            totals = payload.get("totals") if isinstance(payload.get("totals"), dict) else {}
            items = payload.get("items") if isinstance(payload.get("items"), list) else []
            cost_basis_missing = 0
            for item in items:
                if not isinstance(item, dict):
                    continue
                flags = item.get("audit_flags") if isinstance(item.get("audit_flags"), list) else []
                if "cost_basis_missing" in flags:
                    cost_basis_missing += 1
            open_count = _int(totals.get("open_position_count"))
            closed_count = _int(totals.get("closed_lifecycle_count"))
            incomplete = _int(totals.get("incomplete_calculation_count"))
            return {
                "available": True,
                "open_position_count": open_count,
                "closed_lifecycle_count": closed_count,
                "incomplete_pl_count": incomplete,
                "lifecycle_calculation_incomplete_count": incomplete,
                "unrealized_pl_available": open_count == 0
                or totals.get("total_unrealized_pl") is not None,
                "realized_pl_available": closed_count == 0
                or totals.get("total_realized_pl") is not None,
                "cost_basis_missing_count": cost_basis_missing,
                "total_unrealized_pl": totals.get("total_unrealized_pl"),
                "total_realized_pl": totals.get("total_realized_pl"),
                "audit_flags": _string_list(payload.get("audit_flags")),
            }
        except Exception as exc:
            return {
                "available": False,
                "open_position_count": 0,
                "closed_lifecycle_count": 0,
                "incomplete_pl_count": 0,
                "lifecycle_calculation_incomplete_count": 0,
                "unrealized_pl_available": False,
                "realized_pl_available": False,
                "cost_basis_missing_count": 0,
                "audit_flags": [],
                "error": _safe_error(exc),
            }


def _build_checklist(
    *,
    provider: str,
    market: str,
    runtime: dict[str, Any],
    app_flags: dict[str, Any],
    active_profile: dict[str, Any],
    orders: dict[str, Any],
    positions: dict[str, Any],
    alerts: dict[str, Any],
    database: dict[str, Any],
    recent: dict[str, Any],
    agent_chat: dict[str, Any],
    guarded: dict[str, Any],
) -> list[dict[str, Any]]:
    dry_run = runtime.get("dry_run")
    kill_switch = runtime.get("kill_switch")
    kis_real_order_enabled = app_flags.get("kis_real_order_enabled")
    scheduler_real_configured = any(
        bool(runtime.get(key))
        for key in (
            "kis_scheduler_allow_real_orders",
            "kis_scheduler_configured_allow_real_orders",
            "strategy_auto_buy_scheduler_allow_live_orders",
            "kis_scheduler_live_enabled",
            "strategy_live_auto_buy_scheduler_enabled",
            "strategy_live_auto_exit_scheduler_enabled",
        )
    )
    return [
        _check(
            "kill_switch_off",
            "runtime",
            "pass" if kill_switch is False else "fail",
            "Kill switch off",
            "Kill switch is off."
            if kill_switch is False
            else "Kill switch is on, so guarded live actions are blocked.",
            blocking=kill_switch is not False,
            severity="critical" if kill_switch is not False else "info",
            next_safe_action="Review existing safety controls before any live flow.",
        ),
        _known_bool_check("dry_run_state_known", "runtime", "Dry-run state known", dry_run),
        _check(
            "dry_run_blocks_live_submit",
            "runtime",
            "warn" if dry_run is True else "pass",
            "Dry-run live block",
            "Dry-run is enabled; live order entry remains blocked."
            if dry_run is True
            else "Dry-run is off; live preflight still requires every guarded confirmation.",
            blocking=dry_run is True,
            severity="warning" if dry_run is True else "info",
            next_safe_action="Keep dry-run on until the operator intentionally reviews live prerequisites.",
        ),
        _known_bool_check(
            "kis_enabled_state_known",
            "runtime",
            "KIS enabled state known",
            app_flags.get("kis_enabled"),
        ),
        _known_bool_check(
            "kis_real_order_enabled_state_known",
            "runtime",
            "KIS real-order flag known",
            kis_real_order_enabled,
        ),
        _check(
            "kis_real_order_enabled_for_live",
            "broker",
            "pass" if provider != "kis" or kis_real_order_enabled is True else "fail",
            "KIS real-order readiness",
            "KIS real-order flag is enabled."
            if kis_real_order_enabled is True
            else "KIS real-order flag is disabled, so KIS live order entry is blocked.",
            blocking=provider == "kis" and kis_real_order_enabled is not True,
            severity="critical"
            if provider == "kis" and kis_real_order_enabled is not True
            else "info",
            next_safe_action="Use existing settings review controls only after dry-run evidence is complete.",
        ),
        _known_bool_check("bot_enabled_state_known", "runtime", "Bot enabled state known", runtime.get("bot_enabled")),
        _check(
            "active_profile_known",
            "runtime",
            "pass" if active_profile.get("known") else "unknown",
            "Active profile known",
            f"Active strategy profile is {active_profile.get('profile_name')}."
            if active_profile.get("known")
            else "Active strategy profile was not found without seeding data.",
            severity="info" if active_profile.get("known") else "warning",
            next_safe_action="Review strategy profile state from the existing read-only profile screen.",
        ),
        _check(
            "broker_config_present",
            "broker",
            "pass" if app_flags.get("kis_config_present") or provider != "kis" else "fail",
            "Broker configuration",
            "Required KIS configuration keys are present."
            if app_flags.get("kis_config_present")
            else "Required KIS configuration keys are missing or KIS is disabled.",
            blocking=provider == "kis" and not app_flags.get("kis_config_present"),
            severity="critical"
            if provider == "kis" and not app_flags.get("kis_config_present")
            else "info",
            next_safe_action="Review environment configuration without exposing credentials.",
        ),
        _check(
            "broker_connectivity_readiness",
            "broker",
            "pass" if app_flags.get("kis_enabled") else "unknown",
            "Broker connectivity readiness",
            "KIS is enabled; connectivity can be verified with existing read-only account views."
            if app_flags.get("kis_enabled")
            else "KIS is disabled, so connectivity readiness is unknown.",
            severity="info" if app_flags.get("kis_enabled") else "warning",
            next_safe_action="Use existing read-only account views to verify broker connectivity.",
        ),
        _check(
            "scheduler_enabled_state_known",
            "scheduler",
            "pass",
            "Scheduler enabled state",
            f"Scheduler enabled is {bool(runtime.get('scheduler_enabled'))}.",
            severity="info",
            next_safe_action="Keep scheduler changes outside this readiness report.",
        ),
        _check(
            "scheduler_dry_run_only",
            "scheduler",
            "pass" if bool(runtime.get("strategy_auto_buy_scheduler_dry_run_only", True)) else "fail",
            "Scheduler dry-run only",
            "Strategy auto-buy scheduler is dry-run only."
            if bool(runtime.get("strategy_auto_buy_scheduler_dry_run_only", True))
            else "Strategy auto-buy scheduler is not marked dry-run only.",
            blocking=not bool(runtime.get("strategy_auto_buy_scheduler_dry_run_only", True)),
            severity="critical"
            if not bool(runtime.get("strategy_auto_buy_scheduler_dry_run_only", True))
            else "info",
            next_safe_action="Keep scheduler dry-run-only controls enabled.",
        ),
        _check(
            "scheduler_real_orders_allowed",
            "scheduler",
            "fail" if scheduler_real_configured else "pass",
            "Scheduler real orders disabled",
            "A scheduler real-order flag is configured on; this report still allows no scheduler real orders."
            if scheduler_real_configured
            else "Scheduler real orders are not allowed.",
            blocking=scheduler_real_configured,
            severity="critical" if scheduler_real_configured else "info",
            next_safe_action="Do not use this report to unlock scheduler live orders.",
        ),
        _check(
            "no_live_scheduler_path",
            "scheduler",
            "fail" if scheduler_real_configured else "pass",
            "No live scheduler path",
            "No scheduler live-order path is enabled by readiness."
            if not scheduler_real_configured
            else "Live scheduler configuration must be reviewed outside this read-only report.",
            blocking=scheduler_real_configured,
            severity="critical" if scheduler_real_configured else "info",
            next_safe_action="Keep scheduler live order entry disabled.",
        ),
        _check(
            "recent_scheduler_run_health",
            "scheduler",
            "pass" if _int(recent.get("scheduler_run_count")) > 0 else "warn",
            "Recent scheduler run health",
            "Recent scheduler activity was found."
            if _int(recent.get("scheduler_run_count")) > 0
            else "No recent scheduler activity was found in local logs.",
            severity="info" if _int(recent.get("scheduler_run_count")) > 0 else "warning",
            next_safe_action="Review existing logs or run an explicit dry-run workflow if needed.",
        ),
        _count_check("pending_sync_count", "orders", "Pending reconciliation", orders, "pending_sync_count"),
        _count_check("rejected_order_count", "orders", "Rejected orders", orders, "rejected_order_count"),
        _count_check("unknown_order_count", "orders", "Unknown orders", orders, "unknown_order_count"),
        _count_check("stale_order_count", "orders", "Stale open orders", orders, "stale_order_count", blocking=True),
        _count_check("missing_broker_order_id_count", "orders", "Missing broker order IDs", orders, "missing_broker_order_id_count"),
        _count_check("missing_kis_odno_count", "orders", "Missing KIS order numbers", orders, "missing_kis_odno_count"),
        _count_check("duplicate_open_order_risk_count", "orders", "Duplicate open-order risk", orders, "duplicate_open_order_risk_count", blocking=True),
        _check(
            "open_position_count",
            "positions",
            "pass",
            "Open positions",
            f"Open position count is {_int(positions.get('open_position_count'))}.",
            severity="info",
            next_safe_action="Use position review for any sell-readiness decisions.",
        ),
        _count_check("incomplete_pl_count", "pnl", "Incomplete P/L", positions, "incomplete_pl_count"),
        _count_check(
            "lifecycle_calculation_incomplete_count",
            "positions",
            "Lifecycle calculation completeness",
            positions,
            "lifecycle_calculation_incomplete_count",
        ),
        _availability_check("unrealized_pl_available", "pnl", "Unrealized P/L available", positions),
        _availability_check("realized_pl_available", "pnl", "Realized P/L available", positions),
        _count_check("cost_basis_missing_count", "pnl", "Missing cost basis", positions, "cost_basis_missing_count"),
        _alert_count_check("active_alert_count", "alerts", "Active alerts", alerts, "active_alert_count"),
        _alert_count_check("critical_alert_count", "alerts", "Critical alerts", alerts, "critical_alert_count", blocking=True),
        _alert_count_check("warning_alert_count", "alerts", "Warning alerts", alerts, "warning_alert_count"),
        _alert_count_check("sync_required_alert_count", "alerts", "Sync-required alerts", alerts, "sync_required_alert_count"),
        _check(
            "database_expected_tables",
            "database",
            "pass" if not database.get("missing_tables") else "fail",
            "Expected database tables",
            "Expected local tables are present."
            if not database.get("missing_tables")
            else f"Missing local tables: {', '.join(database.get('missing_tables', []))}.",
            blocking=bool(database.get("missing_tables")),
            severity="critical" if database.get("missing_tables") else "info",
            next_safe_action="Apply migrations outside the readiness endpoint.",
        ),
        _check(
            "recent_logs_query",
            "database",
            "pass" if database.get("recent_logs_query_ok") else "unknown",
            "Recent logs query",
            "Recent log queries completed."
            if database.get("recent_logs_query_ok")
            else "Recent log queries could not be completed.",
            severity="info" if database.get("recent_logs_query_ok") else "warning",
            next_safe_action="Review database connectivity and migrations.",
        ),
        _check(
            "agent_chat_read_only_for_trading",
            "agent_chat",
            "pass" if agent_chat.get("trading_guardrails_ok") else "fail",
            "Agent Chat trading guardrails",
            "Agent Chat trading actions are blocked or manual-review only."
            if agent_chat.get("trading_guardrails_ok")
            else "An Agent Chat trading tool appears auto-executable.",
            blocking=not agent_chat.get("trading_guardrails_ok"),
            severity="critical" if not agent_chat.get("trading_guardrails_ok") else "info",
            next_safe_action="Keep Agent Chat limited to read-only readiness summaries.",
        ),
        _check(
            "agent_chat_live_confirmation_blocked",
            "agent_chat",
            "pass" if agent_chat.get("live_confirmation_blocked") else "fail",
            "Agent Chat live confirmation blocked",
            "Agent Chat cannot auto-pass live order confirmation."
            if agent_chat.get("live_confirmation_blocked")
            else "Agent Chat live confirmation guardrail could not be verified.",
            blocking=not agent_chat.get("live_confirmation_blocked"),
            severity="critical" if not agent_chat.get("live_confirmation_blocked") else "info",
            next_safe_action="Use only existing explicit operator confirmation surfaces.",
        ),
        _check(
            "guarded_live_buy_endpoint_available",
            "guarded_buy",
            "pass",
            "Guarded live buy readiness endpoint",
            "Guarded live buy readiness endpoint is available for read-only checks.",
            severity="info",
            next_safe_action="Use preflight and final confirmation before any manual live buy.",
        ),
        _check(
            "guarded_live_sell_endpoint_available",
            "guarded_sell",
            "pass",
            "Guarded live sell readiness endpoint",
            "Guarded live sell readiness endpoint is available for read-only checks.",
            severity="info",
            next_safe_action="Use sell preflight and final confirmation before any manual live sell.",
        ),
        _guarded_check("guarded_live_buy_ready", "guarded_buy", "Guarded buy readiness", guarded, "can_use_guarded_live_buy"),
        _guarded_check("guarded_live_sell_ready", "guarded_sell", "Guarded sell readiness", guarded, "can_use_guarded_live_sell"),
        _check(
            "final_confirmation_required",
            "guarded_buy",
            "pass" if guarded.get("final_confirmation_required") else "fail",
            "Final confirmation required",
            "Guarded live flows require final operator confirmation."
            if guarded.get("final_confirmation_required")
            else "A guarded live flow does not require final operator confirmation.",
            blocking=not guarded.get("final_confirmation_required"),
            severity="critical" if not guarded.get("final_confirmation_required") else "info",
            next_safe_action="Keep final confirmation required for all guarded live flows.",
        ),
    ]


def _summary(
    checklist: list[dict[str, Any]],
    *,
    guarded: dict[str, Any],
    alerts: dict[str, Any],
    orders: dict[str, Any],
) -> dict[str, Any]:
    counts = Counter(item["status"] for item in checklist)
    critical_blocks = sum(
        1
        for item in checklist
        if item.get("blocking") and item.get("severity") == "critical"
    )
    return {
        "ready_count": counts["pass"],
        "warning_count": counts["warn"],
        "blocked_count": counts["fail"],
        "unknown_count": counts["unknown"],
        "critical_block_count": critical_blocks,
        "can_use_guarded_live_buy": bool(guarded.get("can_use_guarded_live_buy")),
        "can_use_guarded_live_sell": bool(guarded.get("can_use_guarded_live_sell")),
        "can_enable_scheduler_live_orders": False,
        "scheduler_real_orders_allowed": False,
        "automation_unlock_allowed": False,
        "active_alert_count": _int(alerts.get("active_alert_count")),
        "critical_alert_count": _int(alerts.get("critical_alert_count")),
        "warning_alert_count": _int(alerts.get("warning_alert_count")),
        "sync_required_alert_count": _int(alerts.get("sync_required_alert_count")),
        "pending_sync_count": _int(orders.get("pending_sync_count")),
        "rejected_order_count": _int(orders.get("rejected_order_count")),
        "stale_order_count": _int(orders.get("stale_order_count")),
    }


def _legacy_projection(
    response: dict[str, Any],
    *,
    runtime: dict[str, Any],
    app_flags: dict[str, Any],
    orders: dict[str, Any],
    recent: dict[str, Any],
    positions: dict[str, Any],
    alerts: dict[str, Any],
    database: dict[str, Any],
) -> dict[str, Any]:
    checklist = response["checklist"]
    summary = dict(response["summary"])
    summary.update(
        {
            "overall_status": response["overall_status"],
            "production_ready": response["overall_status"] == "ready",
            "live_trading_ready": summary["can_use_guarded_live_buy"]
            or summary["can_use_guarded_live_sell"],
            "paper_or_dry_run_ready": bool(runtime.get("dry_run"))
            and not bool(runtime.get("kill_switch")),
            "dry_run": bool(runtime.get("dry_run")),
            "kill_switch": bool(runtime.get("kill_switch")),
            "kis_enabled": bool(app_flags.get("kis_enabled")),
            "kis_real_order_enabled": bool(app_flags.get("kis_real_order_enabled")),
            "kis_scheduler_allow_real_orders": False,
            "kis_scheduler_sell_enabled": bool(runtime.get("kis_scheduler_sell_enabled")),
            "kis_scheduler_buy_enabled": bool(runtime.get("kis_scheduler_buy_enabled")),
            "critical_issue_count": summary["critical_block_count"],
        }
    )
    return {
        "mode": MODE,
        "readiness_only": True,
        "production_ready": response["overall_status"] == "ready",
        "live_trading_ready": summary["live_trading_ready"],
        "paper_or_dry_run_ready": summary["paper_or_dry_run_ready"],
        "safety_checks": [_legacy_check(item) for item in checklist],
        "blocking_issues": list(response["blocking_reasons"]),
        "recommended_actions": list(response["next_safe_actions"]),
        "runtime": runtime,
        "kis": {
            "kis_enabled": bool(app_flags.get("kis_enabled")),
            "kis_real_order_enabled": bool(app_flags.get("kis_real_order_enabled")),
            "real_order_possible": bool(app_flags.get("kis_config_present"))
            and bool(app_flags.get("kis_real_order_enabled")),
        },
        "scheduler": {
            "scheduler_real_orders_allowed": False,
            "scheduler_sell_enabled": bool(runtime.get("kis_scheduler_sell_enabled")),
            "scheduler_buy_enabled": bool(runtime.get("kis_scheduler_buy_enabled")),
            "recent_scheduler_run_count": _int(recent.get("scheduler_run_count")),
        },
        "risk": {**orders, **positions, **alerts},
        "today": _today_activity_projection(recent, orders),
        "recent_activity": list(recent.get("items") or []),
        "documentation": {
            "docs_present": not database.get("missing_tables"),
            "env_example_present": True,
        },
        "diagnostics": {
            "read_only": True,
            "generated_at": response["generated_at"],
            "include_details": bool(response.get("details")),
        },
        "summary": summary,
    }


def _check(
    key: str,
    category: str,
    status: str,
    title: str,
    detail: str,
    *,
    blocking: bool = False,
    severity: str = "info",
    related_type: str | None = None,
    related_id: str | None = None,
    next_safe_action: str = "Review this item in the existing read-only operations screens.",
) -> dict[str, Any]:
    return {
        "key": key,
        "category": category,
        "status": status,
        "title": title,
        "detail": detail,
        "blocking": bool(blocking),
        "severity": severity,
        "related_type": related_type,
        "related_id": related_id,
        "next_safe_action": next_safe_action,
    }


def _known_bool_check(
    key: str,
    category: str,
    title: str,
    value: Any,
) -> dict[str, Any]:
    known = isinstance(value, bool)
    return _check(
        key,
        category,
        "pass" if known else "unknown",
        title,
        f"{title}: {value}." if known else f"{title} is unknown.",
        severity="info" if known else "warning",
        next_safe_action="Review runtime settings from the existing settings screen.",
    )


def _count_check(
    key: str,
    category: str,
    title: str,
    metrics: dict[str, Any],
    metric_key: str,
    *,
    blocking: bool = False,
) -> dict[str, Any]:
    count = _int(metrics.get(metric_key))
    return _check(
        key,
        category,
        "warn" if count else "pass",
        title,
        f"{title}: {count}.",
        blocking=blocking and count > 0,
        severity="warning" if count else "info",
        next_safe_action="Review the affected local records before live operation.",
    )


def _alert_count_check(
    key: str,
    category: str,
    title: str,
    metrics: dict[str, Any],
    metric_key: str,
    *,
    blocking: bool = False,
) -> dict[str, Any]:
    count = _int(metrics.get(metric_key))
    return _check(
        key,
        category,
        "warn" if count else "pass",
        title,
        f"{title}: {count}.",
        blocking=blocking and count > 0,
        severity="critical" if blocking and count > 0 else ("warning" if count else "info"),
        next_safe_action="Review operator alerts; use only explicit existing controls for follow-up.",
    )


def _availability_check(
    key: str,
    category: str,
    title: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    available = metrics.get(key)
    return _check(
        key,
        category,
        "pass" if available is True else "unknown",
        title,
        f"{title}: {available}.",
        severity="info" if available is True else "warning",
        next_safe_action="Do not guess P/L values; review lifecycle audit details.",
    )


def _guarded_check(
    key: str,
    category: str,
    title: str,
    guarded: dict[str, Any],
    metric_key: str,
) -> dict[str, Any]:
    ready = bool(guarded.get(metric_key))
    reasons = guarded.get("block_reasons") if isinstance(guarded.get("block_reasons"), list) else []
    return _check(
        key,
        category,
        "pass" if ready else "fail",
        title,
        f"{title}: ready." if ready else f"{title}: blocked by {', '.join(reasons) or 'safety prerequisites'}.",
        blocking=not ready,
        severity="critical" if not ready else "info",
        next_safe_action="Use existing guarded preflight and final operator confirmation screens only.",
    )


def _overall_status(summary: dict[str, Any]) -> str:
    if _int(summary.get("blocked_count")) > 0 or _int(summary.get("critical_block_count")) > 0:
        return "blocked"
    if _int(summary.get("unknown_count")) > 0 and _int(summary.get("warning_count")) == 0:
        return "unknown"
    if _int(summary.get("warning_count")) > 0 or _int(summary.get("unknown_count")) > 0:
        return "warning"
    return "ready"


def _readiness_score(checklist: list[dict[str, Any]]) -> int:
    if not checklist:
        return 0
    weights = {"pass": 1.0, "warn": 0.5, "unknown": 0.25, "fail": 0.0}
    score = sum(weights.get(str(item.get("status")), 0.0) for item in checklist)
    return max(0, min(100, round(score / len(checklist) * 100)))


def _blocking_reasons(checklist: list[dict[str, Any]]) -> list[str]:
    return [
        item["key"]
        for item in checklist
        if item.get("blocking") or item.get("status") == "fail"
    ]


def _warning_reasons(checklist: list[dict[str, Any]]) -> list[str]:
    return [item["key"] for item in checklist if item.get("status") in {"warn", "unknown"}]


def _next_actions(checklist: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    for item in checklist:
        if item.get("status") == "pass" and not item.get("blocking"):
            continue
        action = str(item.get("next_safe_action") or "").strip()
        if action and action not in actions:
            actions.append(action)
        if len(actions) >= 8:
            break
    if "Keep this report read-only; use existing explicit controls for any operational change." not in actions:
        actions.append(
            "Keep this report read-only; use existing explicit controls for any operational change."
        )
    return actions


def _app_safety_flags(settings: Any) -> dict[str, Any]:
    kis_enabled = bool(getattr(settings, "kis_enabled", False))
    app_key_present = bool(str(getattr(settings, "kis_app_key", "") or "").strip())
    app_secret_present = bool(str(getattr(settings, "kis_app_secret", "") or "").strip())
    account_present = bool(str(getattr(settings, "kis_account_no", "") or "").strip())
    base_url_present = bool(str(getattr(settings, "kis_base_url", "") or "").strip())
    return {
        "kis_enabled": kis_enabled,
        "kis_real_order_enabled": bool(getattr(settings, "kis_real_order_enabled", False)),
        "kis_env": str(getattr(settings, "kis_env", "") or ""),
        "kis_config_present": kis_enabled
        and app_key_present
        and app_secret_present
        and account_present
        and base_url_present,
        "has_kis_app_key": app_key_present,
        "has_kis_app_secret": app_secret_present,
        "has_kis_account": account_present,
        "has_kis_base_url": base_url_present,
    }


def _active_profile_snapshot(db: Session) -> dict[str, Any]:
    try:
        if not _table_exists(db, "strategy_profiles"):
            return {"known": False, "profile_name": None, "reason": "table_missing"}
        row = (
            db.query(StrategyProfile)
            .filter(StrategyProfile.is_active.is_(True))
            .order_by(StrategyProfile.id.asc())
            .first()
        )
        if row is None:
            return {"known": False, "profile_name": None, "reason": "active_profile_missing"}
        return {"known": True, "profile_name": row.profile_name}
    except Exception as exc:
        return {"known": False, "profile_name": None, "reason": _safe_error(exc)}


def _order_metrics(
    db: Session,
    *,
    provider: str,
    market: str,
    now: datetime,
) -> dict[str, Any]:
    rows = (
        db.query(OrderLog)
        .filter(OrderLog.broker == provider)
        .filter(OrderLog.market == market)
        .all()
    )
    open_rows = [row for row in rows if _order_status(row) in OPEN_ORDER_STATUSES]
    duplicate_groups: dict[tuple[str, str], int] = {}
    for row in open_rows:
        key = (str(row.symbol or "").upper(), str(row.side or "").lower())
        if key[0] and key[1]:
            duplicate_groups[key] = duplicate_groups.get(key, 0) + 1
    duplicate_count = sum(1 for value in duplicate_groups.values() if value > 1)
    stale_count = sum(1 for row in open_rows if _is_stale(row, now=now))
    pending_sync_count = sum(1 for row in rows if _needs_sync_review(row))
    rejected_count = sum(1 for row in rows if _order_status(row) in REJECTED_ORDER_STATUSES)
    unknown_count = sum(1 for row in rows if _is_unknown(row))
    live_rows = [row for row in rows if _requires_broker_identity(row)]
    return {
        "order_count": len(rows),
        "open_order_count": len(open_rows),
        "pending_sync_count": pending_sync_count,
        "rejected_order_count": rejected_count,
        "unknown_order_count": unknown_count,
        "stale_order_count": stale_count,
        "missing_broker_order_id_count": sum(1 for row in live_rows if not row.broker_order_id),
        "missing_kis_odno_count": sum(1 for row in live_rows if provider == "kis" and not row.kis_odno),
        "duplicate_open_order_risk_count": duplicate_count,
        "broker_submit_observed_count": sum(1 for row in rows if _order_broker_action_observed(row)),
        "real_order_observed_count": sum(1 for row in rows if _payload_bool(row, "real_order_submitted") is True),
    }


def _recent_activity(
    db: Session,
    *,
    provider: str,
    market: str,
    now: datetime,
    days: int,
) -> dict[str, Any]:
    cutoff = _naive_utc(now - timedelta(days=days))
    runs = (
        db.query(TradeRunLog)
        .filter(TradeRunLog.created_at >= cutoff)
        .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
        .limit(40)
        .all()
    )
    safe_items = [_serialize_run(row) for row in runs]
    scheduler_count = sum(
        1
        for item in safe_items
        if "scheduler" in str(item.get("mode") or "").lower()
        or "scheduler" in str(item.get("trigger_source") or "").lower()
    )
    dry_run_count = sum(
        1
        for item in safe_items
        if "dry_run" in str(item.get("mode") or "").lower()
        or "dry_run" in str(item.get("trigger_source") or "").lower()
    )
    return {
        "items": safe_items,
        "provider": provider,
        "market": market,
        "days": days,
        "scheduler_run_count": scheduler_count,
        "dry_run_count": dry_run_count,
    }


def _database_metrics(db: Session) -> dict[str, Any]:
    missing: list[str] = []
    try:
        inspector = sqlalchemy_inspect(db.bind)
        tables = set(inspector.get_table_names())
        missing = sorted(EXPECTED_TABLES - tables)
    except Exception as exc:
        return {
            "available": False,
            "expected_tables_present": False,
            "missing_tables": sorted(EXPECTED_TABLES),
            "recent_logs_query_ok": False,
            "error": _safe_error(exc),
        }
    try:
        db.execute(text("SELECT 1")).scalar()
        db.query(TradeRunLog.id).order_by(TradeRunLog.id.desc()).limit(1).all()
        db.query(OrderLog.id).order_by(OrderLog.id.desc()).limit(1).all()
        recent_ok = True
        error = None
    except Exception as exc:
        recent_ok = False
        error = _safe_error(exc)
    payload = {
        "available": True,
        "expected_tables_present": not missing,
        "missing_tables": missing,
        "recent_logs_query_ok": recent_ok,
    }
    if error:
        payload["error"] = error
    return payload


def _agent_chat_metrics(registry: AgentChatToolRegistry) -> dict[str, Any]:
    tools = registry.list_tools(include_blocked=True)
    names = {tool.tool_name for tool in tools}
    auto_mutating = [
        tool.tool_name
        for tool in tools
        if registry.can_auto_execute(tool.tool_name) and bool(tool.mutation)
    ]
    blocked_tools_ok = {
        "live_order_request_blocker",
        "settings_change_blocker",
    }.issubset(names) and all(
        registry.is_blocked(name)
        for name in ("live_order_request_blocker", "settings_change_blocker")
    )
    manual_tools_ok = all(
        registry.is_blocked(name)
        for name in ("manual_ticket_prefill", "strategy_profile_change_prepare")
        if name in names
    )
    readiness_tool_ok = (
        "ops_production_readiness_lookup" not in names
        or registry.can_auto_execute("ops_production_readiness_lookup")
    )
    return {
        "tool_count": len(tools),
        "blocked_tools_ok": blocked_tools_ok,
        "manual_tools_ok": manual_tools_ok,
        "auto_mutating_tool_count": len(auto_mutating),
        "auto_mutating_tools": auto_mutating[:5],
        "readiness_tool_available": "ops_production_readiness_lookup" in names,
        "readiness_tool_read_only": readiness_tool_ok,
        "trading_guardrails_ok": blocked_tools_ok
        and manual_tools_ok
        and len(auto_mutating) == 0,
        "live_confirmation_blocked": blocked_tools_ok,
    }


def _guarded_readiness(
    *,
    runtime: dict[str, Any],
    app_flags: dict[str, Any],
) -> dict[str, Any]:
    block_reasons: list[str] = []
    if runtime.get("kill_switch") is True:
        block_reasons.append("kill_switch_enabled")
    if runtime.get("dry_run") is True:
        block_reasons.append("dry_run_enabled")
    if app_flags.get("kis_real_order_enabled") is not True:
        block_reasons.append("kis_real_order_disabled")
    if app_flags.get("kis_config_present") is not True:
        block_reasons.append("kis_config_incomplete")
    final_confirmation_required = bool(
        runtime.get("strategy_live_auto_buy_requires_operator_confirm", True)
        and runtime.get("strategy_live_auto_exit_requires_operator_confirm", True)
    )
    if not final_confirmation_required:
        block_reasons.append("final_confirmation_not_required")
    buy_enabled = bool(runtime.get("strategy_live_auto_buy_enabled", False))
    sell_enabled = bool(runtime.get("strategy_live_auto_exit_enabled", False))
    if not buy_enabled:
        block_reasons.append("guarded_live_buy_disabled")
    if not sell_enabled:
        block_reasons.append("guarded_live_sell_disabled")
    base_clear = not any(
        reason
        in {
            "kill_switch_enabled",
            "dry_run_enabled",
            "kis_real_order_disabled",
            "kis_config_incomplete",
            "final_confirmation_not_required",
        }
        for reason in block_reasons
    )
    return {
        "preflight_available": True,
        "result_tracking_available": True,
        "final_confirmation_required": final_confirmation_required,
        "dry_run_blocks_live": runtime.get("dry_run") is True,
        "kill_switch_blocks_live": runtime.get("kill_switch") is True,
        "kis_real_order_flag_blocks_live": app_flags.get("kis_real_order_enabled") is not True,
        "can_use_guarded_live_buy": base_clear and buy_enabled,
        "can_use_guarded_live_sell": base_clear and sell_enabled,
        "block_reasons": _dedupe(block_reasons),
    }


def _runtime_details(
    runtime: dict[str, Any],
    app_flags: dict[str, Any],
    active_profile: dict[str, Any],
) -> dict[str, Any]:
    keys = [
        "source",
        "updated_at",
        "bot_enabled",
        "dry_run",
        "kill_switch",
        "scheduler_enabled",
        "kis_scheduler_enabled",
        "kis_scheduler_dry_run",
        "kis_scheduler_live_enabled",
        "kis_scheduler_allow_real_orders",
        "strategy_auto_buy_scheduler_dry_run_only",
        "strategy_auto_buy_scheduler_allow_live_orders",
        "strategy_live_auto_buy_enabled",
        "strategy_live_auto_exit_enabled",
    ]
    safe = {key: runtime.get(key) for key in keys if key in runtime}
    safe["app_flags"] = {
        "kis_enabled": app_flags.get("kis_enabled"),
        "kis_real_order_enabled": app_flags.get("kis_real_order_enabled"),
        "kis_env": app_flags.get("kis_env"),
        "kis_config_present": app_flags.get("kis_config_present"),
    }
    safe["active_profile"] = active_profile
    return safe


def _today_activity_projection(
    recent: dict[str, Any],
    orders: dict[str, Any],
) -> dict[str, Any]:
    items = recent.get("items") if isinstance(recent.get("items"), list) else []
    result_counts = Counter(str(item.get("result") or "").lower() for item in items)
    reasons = Counter(
        str(item.get("reason") or "").strip()
        for item in items
        if str(item.get("reason") or "").strip()
    )
    return {
        "total_runs": len(items),
        "blocked_count": result_counts["blocked"],
        "failed_count": result_counts["failed"],
        "order_logs_created": _int(orders.get("order_count")),
        "broker_submits": _int(orders.get("broker_submit_observed_count")),
        "real_order_submitted_count": _int(orders.get("real_order_observed_count")),
        "manual_submit_count": 0,
        "top_block_reasons": [
            {"reason": reason, "count": count}
            for reason, count in reasons.most_common(5)
        ],
    }


def _legacy_check(item: dict[str, Any]) -> dict[str, Any]:
    status_map = {
        "pass": "PASS",
        "warn": "WARN",
        "fail": "FAIL",
        "unknown": "INFO",
    }
    return {
        "key": item["key"],
        "label": item["title"],
        "status": status_map.get(item["status"], "INFO"),
        "value": item.get("status"),
        "message": item.get("detail", ""),
        "recommended_action": item.get("next_safe_action", ""),
    }


def _order_status(row: OrderLog) -> str:
    return str(row.internal_status or "").strip().upper()


def _needs_sync_review(row: OrderLog) -> bool:
    status = _order_status(row)
    broker_status = " ".join(
        [
            str(row.broker_status or ""),
            str(row.broker_order_status or ""),
            str(row.sync_error or ""),
        ]
    ).lower()
    return status in PENDING_SYNC_STATUSES or "sync_required" in broker_status or "pending_sync" in broker_status


def _is_unknown(row: OrderLog) -> bool:
    status = _order_status(row)
    broker_status = " ".join(
        [str(row.broker_status or ""), str(row.broker_order_status or "")]
    ).lower()
    return status in {"UNKNOWN", InternalOrderStatus.UNKNOWN_STALE.value} or "unknown" in broker_status


def _is_stale(row: OrderLog, *, now: datetime) -> bool:
    if _order_status(row) not in OPEN_ORDER_STATUSES:
        return False
    created = _utc(row.created_at)
    return now - created > timedelta(hours=24)


def _requires_broker_identity(row: OrderLog) -> bool:
    status = _order_status(row)
    return status in LIVE_ID_STATUSES or _order_broker_action_observed(row)


def _order_broker_action_observed(row: OrderLog) -> bool:
    return bool(
        row.broker_order_id
        or row.kis_odno
        or _payload_bool(row, "broker_submit_called") is True
        or _payload_bool(row, "manual_submit_called") is True
        or _payload_bool(row, "real_order_submitted") is True
    )


def _payload_bool(row: OrderLog, key: str) -> bool | None:
    for raw in (row.request_payload, row.response_payload, row.last_sync_payload):
        payload = _json_dict(raw)
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def _serialize_run(row: TradeRunLog) -> dict[str, Any]:
    return {
        "type": "trade_run",
        "run_id": row.id,
        "created_at": _iso(row.created_at),
        "trigger_source": row.trigger_source,
        "mode": row.mode,
        "symbol": row.symbol,
        "result": row.result,
        "reason": _safe_text(row.reason, max_length=160),
    }


def _table_exists(db: Session, table_name: str) -> bool:
    inspector = sqlalchemy_inspect(db.bind)
    return table_name in set(inspector.get_table_names())


def _provider(value: str | None) -> str:
    text_value = str(value or DEFAULT_PROVIDER).strip().lower()
    return text_value if text_value else DEFAULT_PROVIDER


def _market(value: str | None, provider: str) -> str:
    text_value = str(value or "").strip().upper()
    if text_value:
        return text_value
    return "KR" if provider == "kis" else "US"


def _utc(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    return _utc(value).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _utc(value).isoformat()


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _safe_text(value: Any, *, max_length: int = 200) -> str | None:
    text_value = str(value or "").strip()
    if not text_value:
        return None
    return text_value[:max_length]


def _safe_error(exc: Exception) -> str:
    text_value = str(exc).strip() or exc.__class__.__name__
    return f"{exc.__class__.__name__}: {text_value[:160]}"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
