from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import get_settings as get_app_settings
from app.db.models import (
    OrderLog,
    StrategyAutoBuyPromotion,
    StrategyLiveAutoBuyAttempt,
    StrategyLiveAutoExitAttempt,
)
from app.services.daily_ops_summary_service import DailyOpsSummaryService
from app.services.runtime_setting_service import RuntimeSettingService


KST = ZoneInfo("Asia/Seoul")
OPEN_ORDER_STATUSES = {"REQUESTED", "SUBMITTED", "ACCEPTED", "PENDING", "PARTIALLY_FILLED"}
SUBMITTED_ORDER_STATUSES = OPEN_ORDER_STATUSES | {"FILLED"}
REJECTED_ORDER_STATUSES = {"REJECTED", "FAILED", "REJECTED_BY_SAFETY_GATE"}
SYNC_REQUIRED_STATUSES = {"UNKNOWN_STALE", "SYNC_FAILED"}
KNOWN_ORDER_STATUSES = (
    OPEN_ORDER_STATUSES
    | SUBMITTED_ORDER_STATUSES
    | REJECTED_ORDER_STATUSES
    | {"FILLED", "CANCELED", "EXPIRED", "DRY_RUN_SIMULATED"}
)
BLOCKED_ATTEMPT_STATUSES = {
    "blocked",
    "failed",
    "rejected",
    "validation_failed",
    "safety_rejected",
    "rejected_by_safety_gate",
}
CONVERSION_BLOCKED_STATUSES = {
    "blocked",
    "failed",
    "rejected",
    "conversion_blocked",
    "live_order_rejected",
}
SENSITIVE_NOTE_PATTERN = re.compile(
    r"(token|secret|app[_\s-]?key|approval|authorization|bearer|account|acct)",
    re.IGNORECASE,
)


class OperatorAlertsService:
    """Read-only operator alert aggregation from local DB state only."""

    def __init__(
        self,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        daily_ops: DailyOpsSummaryService | None = None,
    ) -> None:
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.daily_ops = daily_ops or DailyOpsSummaryService(
            runtime_settings=self.runtime_settings,
        )

    def alerts(
        self,
        db: Session,
        *,
        severity: str = "all",
        status: str = "active",
        provider: str | None = None,
        market: str | None = None,
        limit: int = 50,
        include_details: bool = True,
    ) -> dict[str, Any]:
        normalized_provider = self._provider(provider)
        normalized_market = self._market(market, normalized_provider)
        normalized_severity = str(severity or "all").strip().lower()
        normalized_status = str(status or "active").strip().lower()
        generated_at = datetime.now(UTC)
        settings = self.runtime_settings.get_settings_read_only(db)
        app_settings = get_app_settings()
        target_date = generated_at.astimezone(KST).date()
        start_utc, end_utc = self._day_bounds_utc(target_date)

        daily_summary = self.daily_ops.summary(
            db,
            date_value=target_date,
            provider=normalized_provider,
            market=normalized_market,
            include_details=True,
        )
        orders_today = self._orders_today(
            db,
            provider=normalized_provider,
            market=normalized_market,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        buy_attempts_today = self._attempts_today(
            db,
            StrategyLiveAutoBuyAttempt,
            provider=normalized_provider,
            market=normalized_market,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        sell_attempts_today = self._attempts_today(
            db,
            StrategyLiveAutoExitAttempt,
            provider=normalized_provider,
            market=normalized_market,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        promotions = self._promotions(
            db,
            provider=normalized_provider,
            market=normalized_market,
        )

        alerts: list[dict[str, Any]] = []
        alerts.extend(
            self._runtime_alerts(
                settings=settings,
                app_settings=app_settings,
                provider=normalized_provider,
                market=normalized_market,
                generated_at=generated_at,
            )
        )
        alerts.extend(
            self._order_alerts(
                orders_today,
                provider=normalized_provider,
                market=normalized_market,
                generated_at=generated_at,
            )
        )
        alerts.extend(
            self._duplicate_order_alerts(
                orders_today,
                provider=normalized_provider,
                market=normalized_market,
                generated_at=generated_at,
            )
        )
        alerts.extend(
            self._promotion_alerts(
                promotions,
                provider=normalized_provider,
                market=normalized_market,
                generated_at=generated_at,
            )
        )
        alerts.extend(
            self._blocked_attempt_alerts(
                [*buy_attempts_today, *sell_attempts_today],
                provider=normalized_provider,
                market=normalized_market,
                generated_at=generated_at,
            )
        )
        alerts.extend(
            self._daily_summary_alerts(
                daily_summary,
                provider=normalized_provider,
                market=normalized_market,
                generated_at=generated_at,
            )
        )

        filtered = self._filter_alerts(
            alerts,
            severity=normalized_severity,
            status=normalized_status,
        )
        filtered.sort(
            key=lambda item: (
                self._severity_rank(item.get("severity")),
                self._parse_iso(item.get("updated_at")) or datetime.min.replace(tzinfo=UTC),
                str(item.get("alert_id") or ""),
            ),
            reverse=True,
        )
        filtered.sort(key=lambda item: self._severity_rank(item.get("severity")))
        summary = self._summary(filtered)
        limited = filtered[: max(1, min(int(limit or 50), 200))]
        if not include_details:
            limited = [self._without_details(item) for item in limited]

        return {
            "generated_at": self._iso(generated_at),
            "timezone": "Asia/Seoul",
            "provider": normalized_provider,
            "market": normalized_market,
            "summary": summary,
            "alerts": limited,
            "next_safe_actions": self._next_safe_actions(limited),
            "safety_flags": self._safety_flags(daily_summary=daily_summary),
        }

    def _runtime_alerts(
        self,
        *,
        settings: dict[str, Any],
        app_settings: Any,
        provider: str,
        market: str,
        generated_at: datetime,
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        live_expected = self._live_path_expected(settings)
        if settings.get("kill_switch"):
            alerts.append(
                self._alert(
                    severity="critical" if live_expected else "warning",
                    category="runtime",
                    title="Kill switch is on",
                    message=(
                        "Runtime kill switch is enabled. Review runtime safety "
                        "state before any manual live workflow."
                    ),
                    provider=provider,
                    market=market,
                    related_type="runtime_setting",
                    related_id="kill_switch",
                    created_at=settings.get("updated_at") or generated_at,
                    updated_at=settings.get("updated_at") or generated_at,
                    source="runtime_settings",
                    reason_code="kill_switch_on",
                    risk_flags=["kill_switch_on"],
                    gating_notes=["read_only_alert_center"],
                    next_safe_action="Review runtime settings; do not change them from the alert center.",
                    action_type="review_only",
                )
            )
        if settings.get("dry_run", True):
            alerts.append(
                self._alert(
                    severity="info",
                    category="runtime",
                    title="Dry-run mode is on",
                    message="Runtime dry-run mode is enabled. This is informational, not an error.",
                    provider=provider,
                    market=market,
                    related_type="runtime_setting",
                    related_id="dry_run",
                    created_at=settings.get("updated_at") or generated_at,
                    updated_at=settings.get("updated_at") or generated_at,
                    source="runtime_settings",
                    reason_code="dry_run_on",
                    risk_flags=["dry_run_on"],
                    gating_notes=["live_submit_blocked_by_dry_run"],
                    next_safe_action="Use existing settings screens only if an operator intentionally reviews dry-run state.",
                    action_type="review_only",
                    is_actionable=False,
                )
            )
        kis_real_enabled = bool(getattr(app_settings, "kis_real_order_enabled", False))
        if provider == "kis" and live_expected and not kis_real_enabled:
            alerts.append(
                self._alert(
                    severity="warning",
                    category="runtime",
                    title="KIS real orders are disabled",
                    message="A live-capable path is configured, but KIS real-order submission is disabled.",
                    provider=provider,
                    market=market,
                    related_type="runtime_setting",
                    related_id="kis_real_order_enabled",
                    created_at=settings.get("updated_at") or generated_at,
                    updated_at=settings.get("updated_at") or generated_at,
                    source="app_settings",
                    reason_code="kis_real_order_disabled",
                    risk_flags=["kis_real_order_disabled"],
                    gating_notes=["runtime_live_path_expected"],
                    next_safe_action="Review live readiness and settings outside this read-only alert center.",
                    action_type="review_only",
                )
            )
        scheduler_enabled = bool(
            settings.get("strategy_auto_buy_scheduler_enabled")
            or settings.get("scheduler_enabled")
        )
        scheduler_real_allowed = bool(
            settings.get("strategy_auto_buy_scheduler_allow_live_orders")
        )
        if scheduler_enabled and not scheduler_real_allowed:
            alerts.append(
                self._alert(
                    severity="info",
                    category="scheduler",
                    title="Scheduler is dry-run only",
                    message="Scheduler is enabled, but scheduler real orders are not allowed.",
                    provider=provider,
                    market=market,
                    related_type="runtime_setting",
                    related_id="strategy_auto_buy_scheduler_allow_live_orders",
                    created_at=settings.get("updated_at") or generated_at,
                    updated_at=settings.get("updated_at") or generated_at,
                    source="runtime_settings",
                    reason_code="scheduler_dry_run_only",
                    risk_flags=["scheduler_real_orders_disabled"],
                    gating_notes=["scheduler_alert_is_read_only"],
                    next_safe_action="Review scheduler dry-run results and promotions; do not expect live scheduler orders.",
                    action_type="review_only",
                    is_actionable=False,
                )
            )
        return alerts

    def _order_alerts(
        self,
        orders: list[OrderLog],
        *,
        provider: str,
        market: str,
        generated_at: datetime,
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        for row in orders:
            status = self._status(row)
            if status in REJECTED_ORDER_STATUSES:
                alerts.append(
                    self._alert(
                        severity="warning",
                        category="order",
                        title="Rejected order recorded",
                        message=f"{row.symbol} {self._side(row)} order is {status}.",
                        provider=provider,
                        market=market,
                        symbol=row.symbol,
                        related_type="order",
                        related_id=row.id,
                        created_at=row.created_at,
                        updated_at=row.updated_at or row.created_at,
                        source="orders",
                        reason_code="rejected_order",
                        risk_flags=["rejected_order"],
                        gating_notes=self._compact_notes([row.error_message, row.sync_error]),
                        next_safe_action="Open the order detail and review the rejection reason.",
                        action_type="open_order_detail",
                    )
                )
            if self._needs_sync(row):
                alerts.append(
                    self._alert(
                        severity="warning",
                        category="order",
                        title="Order status sync required",
                        message=f"{row.symbol} {self._side(row)} order needs explicit status review.",
                        provider=provider,
                        market=market,
                        symbol=row.symbol,
                        related_type="order",
                        related_id=row.id,
                        created_at=row.created_at,
                        updated_at=row.updated_at or row.created_at,
                        source="orders",
                        reason_code="order_sync_required",
                        risk_flags=["sync_required"],
                        gating_notes=self._compact_notes([row.sync_error, row.broker_status, row.broker_order_status]),
                        next_safe_action="Review order details; use existing explicit sync controls only after operator review.",
                        action_type="open_order_detail",
                    )
                )
            missing_ids = self._missing_broker_identifier_flags(row, provider=provider)
            if missing_ids:
                alerts.append(
                    self._alert(
                        severity="warning",
                        category="broker_reconciliation",
                        title="Live order missing broker identifier",
                        message=f"{row.symbol} {self._side(row)} order is missing broker identifier metadata.",
                        provider=provider,
                        market=market,
                        symbol=row.symbol,
                        related_type="order",
                        related_id=row.id,
                        created_at=row.created_at,
                        updated_at=row.updated_at or row.created_at,
                        source="orders",
                        reason_code="missing_broker_identifier",
                        risk_flags=missing_ids,
                        gating_notes=["local_order_requires_broker_identifier_review"],
                        next_safe_action="Open the order detail and compare it with broker records using existing tools.",
                        action_type="open_order_detail",
                    )
                )
            if self._is_stale_order(row, generated_at=generated_at):
                alerts.append(
                    self._alert(
                        severity="warning",
                        category="order",
                        title="Stale local order status",
                        message=f"{row.symbol} {self._side(row)} order status has not been refreshed recently.",
                        provider=provider,
                        market=market,
                        symbol=row.symbol,
                        related_type="order",
                        related_id=row.id,
                        created_at=row.created_at,
                        updated_at=row.updated_at or row.created_at,
                        source="orders",
                        reason_code="stale_order_status",
                        risk_flags=["stale_order_status"],
                        gating_notes=["last_sync_missing_or_old"],
                        next_safe_action="Review order detail before taking any separate explicit sync action.",
                        action_type="open_order_detail",
                    )
                )
            if self._unknown_status(row):
                alerts.append(
                    self._alert(
                        severity="warning",
                        category="broker_reconciliation",
                        title="Unknown order status",
                        message=f"{row.symbol} {self._side(row)} order has unknown local or broker status.",
                        provider=provider,
                        market=market,
                        symbol=row.symbol,
                        related_type="order",
                        related_id=row.id,
                        created_at=row.created_at,
                        updated_at=row.updated_at or row.created_at,
                        source="orders",
                        reason_code="unknown_broker_status",
                        risk_flags=["unknown_broker_status"],
                        gating_notes=self._compact_notes([row.internal_status, row.broker_status, row.broker_order_status]),
                        next_safe_action="Open the order detail and inspect local status fields.",
                        action_type="open_order_detail",
                    )
                )
        return alerts

    def _duplicate_order_alerts(
        self,
        orders: list[OrderLog],
        *,
        provider: str,
        market: str,
        generated_at: datetime,
    ) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], list[OrderLog]] = defaultdict(list)
        for row in orders:
            if self._status(row) not in OPEN_ORDER_STATUSES:
                continue
            if self._is_dry_run_order(row):
                continue
            symbol = str(row.symbol or "").strip().upper()
            side = self._side(row)
            if symbol and side:
                grouped[(symbol, side)].append(row)
        alerts: list[dict[str, Any]] = []
        for (symbol, side), rows in grouped.items():
            if len(rows) < 2:
                continue
            alerts.append(
                self._alert(
                    severity="critical" if len(rows) >= 3 else "warning",
                    category="risk_gate",
                    title="Duplicate open order risk",
                    message=f"{len(rows)} open {side} orders exist for {symbol}.",
                    provider=provider,
                    market=market,
                    symbol=symbol,
                    related_type="order_group",
                    related_id=f"{symbol}:{side}",
                    created_at=min((self._aware_utc(row.created_at) or generated_at) for row in rows),
                    updated_at=max((self._aware_utc(row.updated_at) or generated_at) for row in rows),
                    source="orders",
                    reason_code="duplicate_open_order_risk",
                    risk_flags=["duplicate_open_order_risk"],
                    gating_notes=[f"open_order_count={len(rows)}", f"side={side}"],
                    next_safe_action="Review open orders for the symbol before any further order workflow.",
                    action_type="open_order_detail",
                )
            )
        return alerts

    def _promotion_alerts(
        self,
        promotions: list[StrategyAutoBuyPromotion],
        *,
        provider: str,
        market: str,
        generated_at: datetime,
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        for row in promotions:
            if self._promotion_stale(row, generated_at=generated_at):
                alerts.append(
                    self._alert(
                        severity="warning",
                        category="promotion",
                        title="Stale promotion",
                        message=f"{row.symbol or 'Promotion'} is expired or stale and needs review.",
                        provider=provider,
                        market=market,
                        symbol=row.symbol,
                        related_type="promotion",
                        related_id=row.id,
                        created_at=row.created_at,
                        updated_at=row.updated_at or row.created_at,
                        source="strategy_auto_buy_promotions",
                        reason_code="stale_promotion",
                        risk_flags=self._json_list(row.risk_flags) or ["stale_promotion"],
                        gating_notes=self._json_list(row.gating_notes),
                        next_safe_action="Open the promotion queue and review or dismiss the stale item.",
                        action_type="open_promotion",
                    )
                )
            if self._promotion_conversion_blocked(row):
                alerts.append(
                    self._alert(
                        severity="warning",
                        category="promotion",
                        title="Promotion conversion blocked",
                        message=f"{row.symbol or 'Promotion'} conversion is blocked.",
                        provider=provider,
                        market=market,
                        symbol=row.symbol,
                        related_type="promotion",
                        related_id=row.id,
                        created_at=row.created_at,
                        updated_at=row.updated_at or row.created_at,
                        source="strategy_auto_buy_promotions",
                        reason_code="promotion_conversion_blocked",
                        risk_flags=self._json_list(row.risk_flags) or ["promotion_conversion_blocked"],
                        gating_notes=self._json_list(row.gating_notes) or self._compact_notes([row.block_reason, row.conversion_status]),
                        next_safe_action="Review the promotion risk notes; conversion remains blocked outside this alert center.",
                        action_type="open_promotion",
                    )
                )
        return alerts

    def _blocked_attempt_alerts(
        self,
        attempts: list[Any],
        *,
        provider: str,
        market: str,
        generated_at: datetime,
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        for row in attempts:
            if not self._attempt_blocked(row):
                continue
            side = "sell" if hasattr(row, "exit_trigger") else "buy"
            alerts.append(
                self._alert(
                    severity="warning",
                    category="risk_gate",
                    title=f"Guarded {side} attempt blocked",
                    message=f"{getattr(row, 'symbol', None) or 'Symbol'} guarded {side} attempt was blocked.",
                    provider=provider,
                    market=market,
                    symbol=getattr(row, "symbol", None),
                    related_type=f"guarded_{side}_attempt",
                    related_id=getattr(row, "id", None),
                    created_at=getattr(row, "created_at", None) or generated_at,
                    updated_at=getattr(row, "updated_at", None)
                    or getattr(row, "created_at", None)
                    or generated_at,
                    source=(
                        "strategy_live_auto_exit_attempts"
                        if side == "sell"
                        else "strategy_live_auto_buy_attempts"
                    ),
                    reason_code=f"guarded_{side}_blocked",
                    risk_flags=self._json_list(getattr(row, "risk_flags", None))
                    or [str(getattr(row, "block_reason", None) or "guarded_attempt_blocked")],
                    gating_notes=self._json_list(getattr(row, "gating_notes", None)),
                    next_safe_action="Review the guarded attempt details and risk gate notes.",
                    action_type="open_lifecycle" if side == "sell" else "review_only",
                )
            )
        return alerts

    def _daily_summary_alerts(
        self,
        daily_summary: dict[str, Any],
        *,
        provider: str,
        market: str,
        generated_at: datetime,
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        date_value = str(daily_summary.get("date") or generated_at.astimezone(KST).date())
        pnl = daily_summary.get("pnl_summary") if isinstance(daily_summary.get("pnl_summary"), dict) else {}
        incomplete_count = int(pnl.get("incomplete_calculation_count") or 0)
        if incomplete_count:
            alerts.append(
                self._alert(
                    severity="warning",
                    category="pnl",
                    title="P/L calculation incomplete",
                    message=f"{incomplete_count} P/L calculation item(s) are incomplete.",
                    provider=provider,
                    market=market,
                    related_type="daily_ops_summary",
                    related_id=date_value,
                    created_at=generated_at,
                    updated_at=generated_at,
                    source="daily_ops_summary",
                    reason_code="incomplete_pl_calculation",
                    risk_flags=list(pnl.get("audit_flags") or ["pnl_calculation_incomplete"]),
                    gating_notes=["local_order_logs_and_cached_snapshots"],
                    next_safe_action="Open daily operations or lifecycle details and review missing fill/cost-basis data.",
                    action_type="open_daily_summary",
                )
            )
        reconciliation = (
            daily_summary.get("reconciliation")
            if isinstance(daily_summary.get("reconciliation"), dict)
            else {}
        )
        warnings = [
            str(item)
            for item in (reconciliation.get("warnings") or [])
            if str(item).strip()
        ]
        actionable_warnings = [
            item for item in warnings if item != "local_summary_only_no_broker_read"
        ]
        if reconciliation.get("status") == "attention_required" or actionable_warnings:
            alerts.append(
                self._alert(
                    severity="warning",
                    category="broker_reconciliation",
                    title="Broker reconciliation needs attention",
                    message="Daily operations summary found local order or reconciliation warnings.",
                    provider=provider,
                    market=market,
                    related_type="daily_ops_summary",
                    related_id=date_value,
                    created_at=generated_at,
                    updated_at=generated_at,
                    source="daily_ops_summary",
                    reason_code="daily_ops_reconciliation_warning",
                    risk_flags=actionable_warnings or warnings,
                    gating_notes=list(reconciliation.get("next_safe_actions") or []),
                    next_safe_action="Open the daily operations summary and review the warning list.",
                    action_type="open_daily_summary",
                )
            )
        return alerts

    def _alert(
        self,
        *,
        severity: str,
        category: str,
        title: str,
        message: str,
        provider: str,
        market: str,
        related_type: str,
        related_id: Any,
        created_at: Any,
        updated_at: Any,
        source: str,
        reason_code: str,
        next_safe_action: str,
        action_type: str,
        symbol: Any = None,
        risk_flags: list[Any] | None = None,
        gating_notes: list[Any] | None = None,
        is_actionable: bool = True,
    ) -> dict[str, Any]:
        clean_related_id = self._string_or_none(related_id)
        clean_symbol = self._string_or_none(symbol)
        created = self._iso(created_at) or self._iso(datetime.now(UTC))
        updated = self._iso(updated_at) or created
        payload = {
            "alert_id": self._alert_id(
                provider,
                market,
                category,
                reason_code,
                related_type,
                clean_related_id or clean_symbol or "system",
            ),
            "severity": severity,
            "category": category,
            "status": "active",
            "title": title,
            "message": message,
            "provider": provider,
            "market": market,
            "symbol": clean_symbol,
            "related_type": related_type,
            "related_id": clean_related_id,
            "created_at": created,
            "updated_at": updated,
            "source": source,
            "reason_code": reason_code,
            "risk_flags": self._clean_list(risk_flags),
            "gating_notes": self._clean_list(gating_notes),
            "next_safe_action": next_safe_action,
            "is_actionable": bool(is_actionable),
            "action_type": action_type,
        }
        return payload

    def _summary(self, alerts: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "active_alert_count": len([item for item in alerts if item.get("status") == "active"]),
            "critical_count": len([item for item in alerts if item.get("severity") == "critical"]),
            "warning_count": len([item for item in alerts if item.get("severity") == "warning"]),
            "info_count": len([item for item in alerts if item.get("severity") == "info"]),
            "sync_required_count": len([item for item in alerts if item.get("reason_code") == "order_sync_required"]),
            "rejected_order_count": len([item for item in alerts if item.get("reason_code") == "rejected_order"]),
            "blocked_attempt_count": len([item for item in alerts if str(item.get("reason_code") or "").startswith("guarded_")]),
            "stale_promotion_count": len([item for item in alerts if item.get("reason_code") == "stale_promotion"]),
            "incomplete_pl_count": len([item for item in alerts if item.get("reason_code") == "incomplete_pl_calculation"]),
            "runtime_warning_count": len(
                [
                    item
                    for item in alerts
                    if item.get("category") in {"runtime", "scheduler"}
                    and item.get("severity") in {"critical", "warning"}
                ]
            ),
        }

    def _next_safe_actions(self, alerts: list[dict[str, Any]]) -> list[str]:
        if not alerts:
            return [
                "No active operator alerts matched the filter.",
                "Continue using read-only logs and explicit existing controls for review.",
            ]
        actions: list[str] = []
        for alert in alerts:
            action = str(alert.get("next_safe_action") or "").strip()
            if action and action not in actions:
                actions.append(action)
            if len(actions) >= 5:
                break
        if any(item.get("reason_code") == "order_sync_required" for item in alerts):
            action = "Do not sync from the alert center; use existing explicit sync controls only after review."
            if action not in actions:
                actions.append(action)
        return actions

    def _safety_flags(self, *, daily_summary: dict[str, Any]) -> dict[str, Any]:
        safety = daily_summary.get("safety") if isinstance(daily_summary.get("safety"), dict) else {}
        return {
            "read_only": True,
            "no_live_orders": True,
            "scheduler_dry_run_only": True,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "validation_called": False,
            "sync_called": False,
            "setting_changed": False,
            "scheduler_changed": False,
            "order_state_mutated": False,
            **{
                key: value
                for key, value in safety.items()
                if key
                in {
                    "read_only",
                    "broker_submit_called",
                    "manual_submit_called",
                    "validation_called",
                    "sync_called",
                    "setting_changed",
                    "scheduler_changed",
                    "order_state_mutated",
                }
            },
        }

    def _filter_alerts(
        self,
        alerts: list[dict[str, Any]],
        *,
        severity: str,
        status: str,
    ) -> list[dict[str, Any]]:
        if status in {"acknowledged", "resolved"}:
            return []
        result = list(alerts)
        if severity != "all":
            result = [item for item in result if item.get("severity") == severity]
        if status != "all":
            result = [item for item in result if item.get("status") == status]
        return result

    def _orders_today(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[OrderLog]:
        rows = db.query(OrderLog).filter(OrderLog.broker == provider).all()
        return [
            row
            for row in rows
            if self._row_market(row, provider) == market
            and self._order_in_window(row, start_utc, end_utc)
        ]

    def _attempts_today(
        self,
        db: Session,
        model: Any,
        *,
        provider: str,
        market: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[Any]:
        rows = (
            db.query(model)
            .filter(model.provider == provider, model.market == market)
            .order_by(model.created_at.desc(), model.id.desc())
            .all()
        )
        return [
            row
            for row in rows
            if self._in_window(getattr(row, "created_at", None), start_utc, end_utc)
            or self._in_window(getattr(row, "submitted_at", None), start_utc, end_utc)
        ]

    def _promotions(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
    ) -> list[StrategyAutoBuyPromotion]:
        return (
            db.query(StrategyAutoBuyPromotion)
            .filter(
                StrategyAutoBuyPromotion.provider == provider,
                StrategyAutoBuyPromotion.market == market,
            )
            .order_by(
                StrategyAutoBuyPromotion.created_at.desc(),
                StrategyAutoBuyPromotion.id.desc(),
            )
            .limit(200)
            .all()
        )

    def _provider(self, value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        return normalized or "kis"

    def _market(self, value: str | None, provider: str) -> str:
        normalized = str(value or "").strip().upper()
        if normalized:
            return normalized
        return "KR" if provider == "kis" else "US"

    def _day_bounds_utc(self, target_date: Any) -> tuple[datetime, datetime]:
        start_local = datetime.combine(target_date, time.min, tzinfo=KST)
        end_local = start_local + timedelta(days=1)
        return start_local.astimezone(UTC), end_local.astimezone(UTC)

    def _row_market(self, row: OrderLog, provider: str) -> str:
        explicit = str(row.market or "").strip().upper()
        if explicit:
            return explicit
        return "KR" if provider == "kis" else "US"

    def _order_in_window(self, row: OrderLog, start: datetime, end: datetime) -> bool:
        return any(
            self._in_window(value, start, end)
            for value in (
                row.created_at,
                row.submitted_at,
                row.filled_at,
                row.canceled_at,
                row.updated_at,
            )
        )

    def _in_window(self, value: Any, start: datetime, end: datetime) -> bool:
        dt = self._aware_utc(value)
        return dt is not None and start <= dt < end

    def _aware_utc(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            try:
                value = datetime.fromisoformat(text)
            except ValueError:
                return None
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _iso(self, value: Any) -> str | None:
        dt = self._aware_utc(value)
        if dt is None:
            return None
        return dt.isoformat().replace("+00:00", "Z")

    def _parse_iso(self, value: Any) -> datetime | None:
        return self._aware_utc(value)

    def _status(self, row: OrderLog) -> str:
        return str(row.internal_status or "").strip().upper()

    def _side(self, row: OrderLog) -> str:
        return str(row.side or "").strip().lower()

    def _needs_sync(self, row: OrderLog) -> bool:
        status = self._status(row)
        broker_status = " ".join(
            [
                str(row.broker_status or ""),
                str(row.broker_order_status or ""),
                str(row.sync_error or ""),
            ]
        ).lower()
        if status in SYNC_REQUIRED_STATUSES:
            return True
        if "sync_required" in broker_status or "pending_sync" in broker_status:
            return True
        if (
            status in OPEN_ORDER_STATUSES
            and not self._is_dry_run_order(row)
            and (row.last_synced_at is None or not self._has_broker_status(row))
        ):
            return True
        return False

    def _has_broker_status(self, row: OrderLog) -> bool:
        return bool(str(row.broker_status or row.broker_order_status or "").strip())

    def _missing_broker_identifier_flags(
        self,
        row: OrderLog,
        *,
        provider: str,
    ) -> list[str]:
        if not self._live_order_requiring_broker_id(row):
            return []
        flags: list[str] = []
        if not str(row.broker_order_id or "").strip():
            flags.append("missing_broker_order_id")
        if provider == "kis" and not str(row.kis_odno or "").strip():
            flags.append("missing_kis_odno")
        return flags

    def _is_stale_order(self, row: OrderLog, *, generated_at: datetime) -> bool:
        if self._status(row) not in OPEN_ORDER_STATUSES and not self._needs_sync(row):
            return False
        latest = self._aware_utc(row.last_synced_at) or self._latest_order_time(row)
        if latest is None:
            return True
        return generated_at - latest > timedelta(minutes=30)

    def _unknown_status(self, row: OrderLog) -> bool:
        status = self._status(row)
        broker_status = " ".join(
            [
                str(row.broker_status or ""),
                str(row.broker_order_status or ""),
            ]
        ).strip().lower()
        return (
            status == "UNKNOWN"
            or status not in KNOWN_ORDER_STATUSES
            or "unknown" in broker_status
        )

    def _live_order_requiring_broker_id(self, row: OrderLog) -> bool:
        return (
            self._status(row) in SUBMITTED_ORDER_STATUSES
            and not self._is_dry_run_order(row)
            and self._side(row) in {"buy", "sell"}
        )

    def _latest_order_time(self, row: OrderLog) -> datetime | None:
        latest: datetime | None = None
        for value in (
            row.updated_at,
            row.filled_at,
            row.submitted_at,
            row.canceled_at,
            row.created_at,
        ):
            candidate = self._aware_utc(value)
            if candidate is not None and (latest is None or candidate > latest):
                latest = candidate
        return latest

    def _is_dry_run_order(self, row: OrderLog) -> bool:
        return (
            self._status(row) == "DRY_RUN_SIMULATED"
            or self._payload_bool(row, "dry_run")
            or self._payload_bool(row, "simulated")
            or self._payload_bool(row, "preview_only")
        )

    def _payload_bool(self, row: Any, key: str) -> bool:
        for attr in ("request_payload", "response_payload", "last_sync_payload"):
            payload = self._json_obj(getattr(row, attr, None))
            if payload.get(key) is True:
                return True
        return False

    def _json_obj(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if not value:
            return {}
        try:
            parsed = json.loads(str(value))
        except Exception:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}

    def _promotion_stale(
        self,
        row: StrategyAutoBuyPromotion,
        *,
        generated_at: datetime,
    ) -> bool:
        status = str(row.status or "").strip().lower()
        expires_at = self._aware_utc(row.expires_at)
        return status in {"expired", "stale"} or (
            status == "pending" and expires_at is not None and expires_at < generated_at
        )

    def _promotion_conversion_blocked(self, row: StrategyAutoBuyPromotion) -> bool:
        status = str(row.status or "").strip().lower()
        conversion_status = str(row.conversion_status or "").strip().lower()
        return (
            bool(row.block_reason)
            or status in CONVERSION_BLOCKED_STATUSES
            or conversion_status in CONVERSION_BLOCKED_STATUSES
        )

    def _attempt_blocked(self, row: Any) -> bool:
        status = str(getattr(row, "status", "") or "").strip().lower()
        return status in BLOCKED_ATTEMPT_STATUSES or bool(getattr(row, "block_reason", None))

    def _live_path_expected(self, settings: dict[str, Any]) -> bool:
        keys = (
            "kis_scheduler_live_enabled",
            "kis_scheduler_allow_real_orders",
            "kis_scheduler_configured_allow_real_orders",
            "kis_scheduler_buy_enabled",
            "kis_scheduler_sell_enabled",
            "kis_scheduler_allow_limited_auto_buy",
            "kis_scheduler_allow_limited_auto_sell",
            "kis_live_auto_buy_enabled",
            "kis_live_auto_sell_enabled",
            "kis_limited_auto_buy_enabled",
            "kis_limited_auto_sell_enabled",
            "strategy_live_auto_buy_enabled",
            "strategy_live_auto_buy_scheduler_enabled",
            "strategy_live_auto_exit_enabled",
            "strategy_live_auto_exit_scheduler_enabled",
        )
        return any(bool(settings.get(key)) for key in keys)

    def _json_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return self._clean_list(value)
        if not value:
            return []
        try:
            parsed = json.loads(str(value))
        except Exception:
            return []
        if not isinstance(parsed, list):
            return []
        return self._clean_list(parsed)

    def _compact_notes(self, values: list[Any]) -> list[str]:
        return self._clean_list(values)[:5]

    def _clean_list(self, values: list[Any] | None) -> list[str]:
        result: list[str] = []
        for value in values or []:
            text = str(value or "").strip()
            if not text or text.lower() == "none":
                continue
            text = text.replace("\r", " ").replace("\n", " ")
            if SENSITIVE_NOTE_PATTERN.search(text):
                text = "[redacted]"
            if len(text) > 200:
                text = f"{text[:197]}..."
            if text not in result:
                result.append(text)
        return result

    def _without_details(self, alert: dict[str, Any]) -> dict[str, Any]:
        return {
            **alert,
            "risk_flags": [],
            "gating_notes": [],
        }

    def _severity_rank(self, value: Any) -> int:
        return {"critical": 0, "warning": 1, "info": 2}.get(str(value), 3)

    def _alert_id(
        self,
        provider: str,
        market: str,
        category: str,
        reason_code: str,
        related_type: str,
        related_id: str,
    ) -> str:
        raw = f"pr89:{provider}:{market}:{category}:{reason_code}:{related_type}:{related_id}"
        return re.sub(r"[^a-zA-Z0-9_.:-]+", "-", raw).strip("-")

    def _string_or_none(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None
