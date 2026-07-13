from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db.models import TradeRunLog
from app.services.auto_buy_live_phase1_service import AutoBuyLivePhase1Service
from app.services.auto_sell_live_phase1_service import AutoSellLivePhase1Service
from app.services.automation_mode_control_service import AutomationModeControlService
from app.services.automation_soak_test_service import AutomationSoakTestService
from app.services.broker_sync_watchdog_service import BrokerSyncWatchdogService
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.ops_production_readiness_service import OpsProductionReadinessService
from app.services.portfolio_orchestrator_service import PortfolioOrchestratorService
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "automation_release"
PROVIDER = "kis"
MARKET = "KR"
KST = ZoneInfo("Asia/Seoul")
LIVE_SOAK_MODE = "live_phase1_controlled"
MONITORING_SOAK_MODE = "dry_run_monitoring"


class AutomationReleaseAcknowledgementRequired(ValueError):
    pass


class AutomationReleaseService:
    """PR100 release gate over the existing controlled automation stack."""

    def __init__(
        self,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        automation_mode_service: AutomationModeControlService | None = None,
        broker_sync_watchdog_service: BrokerSyncWatchdogService | None = None,
        readiness_service: OpsProductionReadinessService | None = None,
        soak_test_service: AutomationSoakTestService | None = None,
        portfolio_orchestrator_service: PortfolioOrchestratorService | None = None,
        auto_buy_service: AutoBuyLivePhase1Service | None = None,
        auto_sell_service: AutoSellLivePhase1Service | None = None,
    ) -> None:
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.readiness_service = readiness_service or OpsProductionReadinessService(
            runtime_settings=self.runtime_settings
        )
        self.broker_sync_watchdog_service = (
            broker_sync_watchdog_service
            or BrokerSyncWatchdogService(runtime_settings=self.runtime_settings)
        )
        self.automation_mode_service = automation_mode_service or AutomationModeControlService(
            runtime_settings=self.runtime_settings,
            readiness_service=self.readiness_service,
            broker_sync_watchdog_service=self.broker_sync_watchdog_service,
        )
        self.portfolio_orchestrator_service = (
            portfolio_orchestrator_service
            or PortfolioOrchestratorService(
                runtime_settings=self.runtime_settings,
                readiness_service=self.readiness_service,
                broker_sync_watchdog_service=self.broker_sync_watchdog_service,
            )
        )
        self.soak_test_service = soak_test_service or AutomationSoakTestService(
            runtime_settings=self.runtime_settings,
            broker_sync_watchdog_service=self.broker_sync_watchdog_service,
            readiness_service=self.readiness_service,
            automation_mode_service=self.automation_mode_service,
            portfolio_orchestrator_service=self.portfolio_orchestrator_service,
        )
        self.auto_buy_service = auto_buy_service or AutoBuyLivePhase1Service(
            runtime_settings=self.runtime_settings,
            readiness_service=self.readiness_service,
        )
        self.auto_sell_service = auto_sell_service or AutoSellLivePhase1Service(
            runtime_settings=self.runtime_settings,
            readiness_service=self.readiness_service,
        )

    def status(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc(now)
        settings = self.runtime_settings.get_settings_read_only(db)
        sources = self._collect_sources(
            db,
            provider=provider,
            market=market,
            now_utc=now_utc,
        )
        counts = self._counts_today(db, now_utc=now_utc)

        release_enabled = bool(settings.get("automation_release_enabled", False))
        release_mode = "controlled_phase1"
        kill_latch_active = bool(
            settings.get("automation_soak_kill_latch_active")
            or sources["soak_status"].get("kill_latch_active")
        )
        broker_health = str(
            sources["broker_sync_status"].get("sync_health") or "unknown"
        ).lower()
        production_status = str(
            sources["production_readiness"].get("overall_status")
            or sources["automation_mode_status"].get("production_readiness_status")
            or "unknown"
        ).lower()
        automation_mode = str(
            sources["automation_mode_status"].get("automation_mode") or "off"
        )
        dry_run = bool(settings.get("dry_run", True))
        kill_switch = bool(settings.get("kill_switch", False))
        app_settings = getattr(self.runtime_settings, "settings", None)
        kis_enabled = bool(getattr(app_settings, "kis_enabled", False))
        kis_real_order_enabled = bool(
            getattr(app_settings, "kis_real_order_enabled", False)
        )
        release_allow_live = bool(
            settings.get("automation_release_allow_live_phase1", False)
        )
        daily_trade_remaining = self._daily_trade_remaining(
            settings=settings,
            automation_mode_status=sources["automation_mode_status"],
            counts=counts,
        )
        daily_auto_buy_remaining = self._daily_phase_remaining(
            release_limit=_int(settings.get("automation_release_max_daily_auto_buys"), 1),
            release_used=counts["buy_count"],
            phase_status=sources["auto_buy_phase1_status"],
            count_key="daily_auto_buy_count",
            limit_key="daily_auto_buy_limit",
        )
        daily_auto_sell_remaining = self._daily_phase_remaining(
            release_limit=_int(settings.get("automation_release_max_daily_auto_sells"), 1),
            release_used=counts["sell_count"],
            phase_status=sources["auto_sell_phase1_status"],
            count_key="daily_auto_sell_count",
            limit_key="daily_auto_sell_limit",
        )
        soak_recently_passed = self._soak_recently_passed(
            settings.get("automation_soak_last_successful_cycle_at"),
            now_utc=now_utc,
        )

        checklist: list[dict[str, Any]] = []

        def add_check(
            key: str,
            label: str,
            passed: bool,
            reason: str,
            next_action: str,
            *,
            severity: str = "critical",
            blocking: bool = True,
        ) -> None:
            checklist.append(
                {
                    "key": key,
                    "label": label,
                    "passed": bool(passed),
                    "severity": severity,
                    "reason": None if passed else reason,
                    "blocking": bool(blocking),
                    "next_action": "no_action" if passed else next_action,
                }
            )

        watchdog = sources["broker_sync_status"]
        orchestrator = sources["orchestrator_status"]
        auto_buy = sources["auto_buy_phase1_status"]
        auto_sell = sources["auto_sell_phase1_status"]
        add_check(
            "release_enabled",
            "Release enabled",
            release_enabled,
            "automation_release_disabled",
            "arm_release_with_operator_acknowledgement",
        )
        add_check(
            "automation_mode_phase1_live_ready",
            "Automation mode phase 1 live ready",
            automation_mode == "phase1_live_ready",
            "automation_mode_not_phase1_live_ready",
            "review_automation_mode_control",
        )
        add_check(
            "dry_run_off_for_live",
            "Dry-run off for live",
            not dry_run,
            "dry_run_enabled",
            "operator_must_change_dry_run_outside_release",
        )
        add_check(
            "kill_switch_off",
            "Kill switch off",
            not kill_switch,
            "kill_switch_enabled",
            "operator_must_review_kill_switch_outside_release",
        )
        add_check(
            "kis_real_orders_enabled",
            "KIS real orders enabled",
            kis_enabled and kis_real_order_enabled,
            "kis_real_order_disabled",
            "operator_must_enable_kis_real_orders_outside_release",
        )
        add_check(
            "production_readiness_ready",
            "Production readiness ready",
            production_status == "ready",
            f"production_readiness_{production_status}",
            "review_production_readiness",
        )
        add_check(
            "broker_sync_healthy",
            "Broker sync healthy",
            broker_health == "healthy",
            f"broker_sync_{broker_health}",
            str(watchdog.get("next_safe_action") or "review_broker_sync_watchdog"),
        )
        add_check(
            "kill_latch_clear",
            "Kill latch clear",
            not kill_latch_active,
            "automation_soak_kill_latch_active",
            "operator_review_then_reset_kill_latch",
        )
        add_check(
            "soak_recently_passed",
            "Soak recently passed",
            soak_recently_passed,
            "soak_recent_pass_missing",
            "run_successful_soak_cycle_before_live_release",
        )
        add_check(
            "orchestrator_enabled",
            "Orchestrator enabled",
            bool(settings.get("portfolio_orchestrator_enabled")),
            "portfolio_orchestrator_disabled",
            "enable_orchestrator_explicitly",
        )
        add_check(
            "orchestrator_allow_live_orders",
            "Orchestrator allows live orders",
            bool(settings.get("portfolio_orchestrator_allow_live_orders")),
            "portfolio_orchestrator_live_orders_disabled",
            "review_orchestrator_live_gate",
        )
        add_check(
            "auto_buy_phase1_enabled",
            "Auto buy phase 1 enabled",
            bool(settings.get("auto_buy_live_phase1_enabled"))
            or bool(auto_buy.get("auto_buy_live_enabled")),
            "auto_buy_live_phase1_disabled",
            "enable_auto_buy_phase1_explicitly",
        )
        add_check(
            "auto_sell_phase1_enabled",
            "Auto sell phase 1 enabled",
            bool(settings.get("auto_sell_live_phase1_enabled"))
            or bool(auto_sell.get("auto_sell_live_enabled")),
            "auto_sell_live_phase1_disabled",
            "enable_auto_sell_phase1_explicitly",
        )
        add_check(
            "daily_trade_limit_remaining",
            "Daily trade limit remaining",
            daily_trade_remaining > 0,
            "daily_trade_limit_exhausted",
            "wait_for_next_trading_day",
        )
        add_check(
            "no_pending_sync_orders",
            "No pending sync orders",
            _int(watchdog.get("pending_sync_order_count"), 0) == 0
            and _int(sources["automation_mode_status"].get("sync_required_count"), 0) == 0,
            "pending_sync_order_exists",
            "run_broker_sync_review",
        )
        add_check(
            "no_stale_orders",
            "No stale orders",
            _int(watchdog.get("stale_local_order_count"), 0) == 0,
            "stale_order_exists",
            "review_stale_orders",
        )
        add_check(
            "no_duplicate_orders",
            "No duplicate orders",
            _int(orchestrator.get("pending_order_conflict_count"), 0) == 0,
            "duplicate_or_pending_order_conflict",
            "review_open_order_conflicts",
        )
        add_check(
            "no_position_mismatch",
            "No position mismatch",
            _int(watchdog.get("position_mismatch_count"), 0) == 0,
            "position_mismatch_exists",
            "reconcile_positions_before_release",
        )
        add_check(
            "no_critical_exit_candidate_blocking_buy",
            "No critical exit candidate blocking buy",
            _int(sources["automation_mode_status"].get("critical_exit_candidate_count"), 0) == 0
            and _int(orchestrator.get("critical_exit_candidate_count"), 0) == 0,
            "critical_exit_candidate_blocks_buy",
            "resolve_exit_candidates_before_buy_phase",
        )
        add_check(
            "scheduler_release_enabled",
            "Release scheduler enabled",
            bool(settings.get("automation_release_scheduler_enabled")),
            "automation_release_scheduler_disabled",
            "enable_release_scheduler_only_after_preflight",
            severity="info",
            blocking=False,
        )

        blocking_reasons = _dedupe(
            [
                str(item["reason"])
                for item in checklist
                if item["blocking"] and not item["passed"] and item["reason"]
            ]
        )
        warning_reasons = _dedupe(
            [
                str(item["reason"])
                for item in checklist
                if (not item["blocking"] or item["severity"] != "critical")
                and not item["passed"]
                and item["reason"]
            ]
        )
        source_errors = _strings(sources.get("source_errors"))
        warning_reasons = _dedupe([*warning_reasons, *source_errors])

        core_safe = (
            release_enabled
            and not kill_latch_active
            and broker_health not in {"unsafe", "unknown"}
            and production_status in {"ready", "warning"}
        )
        can_run_monitoring = core_safe
        can_run_dry_run = core_safe and automation_mode in {
            "dry_run_auto",
            "phase1_live_ready",
        }
        live_checks_passed = all(
            item["passed"]
            for item in checklist
            if item["key"]
            in {
                "release_enabled",
                "automation_mode_phase1_live_ready",
                "dry_run_off_for_live",
                "kill_switch_off",
                "kis_real_orders_enabled",
                "production_readiness_ready",
                "broker_sync_healthy",
                "kill_latch_clear",
                "soak_recently_passed",
                "orchestrator_enabled",
                "orchestrator_allow_live_orders",
                "auto_buy_phase1_enabled",
                "auto_sell_phase1_enabled",
                "daily_trade_limit_remaining",
                "no_pending_sync_orders",
                "no_stale_orders",
                "no_duplicate_orders",
                "no_position_mismatch",
                "no_critical_exit_candidate_blocking_buy",
            }
        )
        can_run_live = (
            core_safe
            and release_allow_live
            and bool(sources["automation_mode_status"].get("can_submit_live_order"))
            and daily_auto_buy_remaining >= 0
            and daily_auto_sell_remaining >= 0
            and live_checks_passed
        )
        effective_status = self._effective_status(
            release_enabled=release_enabled,
            kill_latch_active=kill_latch_active,
            broker_health=broker_health,
            production_status=production_status,
            automation_mode=automation_mode,
            can_run_monitoring=can_run_monitoring,
            can_run_dry_run=can_run_dry_run,
            can_run_live=can_run_live,
        )
        response = {
            "generated_at": now_utc.isoformat(),
            "release_enabled": release_enabled,
            "release_mode": release_mode,
            "release_armed": release_enabled,
            "release_armed_at": _iso(settings.get("automation_release_armed_at")),
            "release_reason": _text(settings.get("automation_release_reason")),
            "effective_status": effective_status,
            "can_run_monitoring_cycle": can_run_monitoring,
            "can_run_dry_run_cycle": can_run_dry_run,
            "can_run_live_phase1_cycle": can_run_live,
            "can_submit_live_order": can_run_live,
            "automation_mode_status": sources["automation_mode_status"],
            "broker_sync_status": sources["broker_sync_status"],
            "soak_status": sources["soak_status"],
            "kill_latch_active": kill_latch_active,
            "production_readiness_status": production_status,
            "orchestrator_status": sources["orchestrator_status"],
            "auto_buy_phase1_status": sources["auto_buy_phase1_status"],
            "auto_sell_phase1_status": sources["auto_sell_phase1_status"],
            "daily_trade_limit_remaining": daily_trade_remaining,
            "daily_auto_buy_remaining": daily_auto_buy_remaining,
            "daily_auto_sell_remaining": daily_auto_sell_remaining,
            "blocking_reasons": blocking_reasons,
            "warning_reasons": warning_reasons,
            "checklist": checklist,
            "safety_flags": self._safety_flags(settings),
            "next_safe_action": self._next_safe_action(
                effective_status=effective_status,
                blocking_reasons=blocking_reasons,
                warning_reasons=warning_reasons,
            ),
        }
        return sanitize_kis_payload(response)

    def preflight(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return self.status(db, provider=provider, market=market, now=now)

    def arm(
        self,
        db: Session,
        *,
        operator_acknowledged_risks: bool,
        reason: str | None = None,
        release_mode: str = "controlled_phase1",
        armed_by: str = "api",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not operator_acknowledged_risks:
            raise AutomationReleaseAcknowledgementRequired(
                "release arm requires operator_acknowledged_risks=true"
            )
        if release_mode != "controlled_phase1":
            raise ValueError("unsupported automation release mode")
        now_utc = _utc(now)
        self.runtime_settings.update_settings(
            db,
            {
                "automation_release_enabled": True,
                "automation_release_mode": "controlled_phase1",
                "automation_release_armed_at": now_utc,
                "automation_release_armed_by": armed_by,
                "automation_release_disarmed_at": None,
                "automation_release_reason": reason,
            },
        )
        return self.status(db, now=now_utc)

    def disarm(
        self,
        db: Session,
        *,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc(now)
        self.runtime_settings.update_settings(
            db,
            {
                "automation_release_enabled": False,
                "automation_release_scheduler_enabled": False,
                "automation_release_disarmed_at": now_utc,
                "automation_release_reason": reason,
            },
        )
        return self.status(db, now=now_utc)

    def run_cycle_once(
        self,
        db: Session,
        request: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc(now)
        status = self.preflight(
            db,
            provider=str(request.get("provider") or PROVIDER),
            market=str(request.get("market") or MARKET),
            now=now_utc,
        )
        cycle_mode = str(request.get("mode") or "monitoring")
        response = self._base_cycle_response(
            status=status,
            cycle_mode=cycle_mode,
            generated_at=now_utc,
        )

        def block(reason: str, *, result_status: str = "blocked") -> dict[str, Any]:
            response["result_status"] = result_status
            response["blocking_reasons"].append(reason)
            response["next_safe_action"] = self._cycle_next_action(
                response["result_status"],
                response["blocking_reasons"],
            )
            return self._save_cycle(db, request=request, response=response, now_utc=now_utc)

        if not status.get("release_enabled"):
            return block("automation_release_disabled", result_status="disabled")
        if status.get("kill_latch_active"):
            return block("automation_soak_kill_latch_active", result_status="kill_latched")

        broker_health = str(
            (status.get("broker_sync_status") or {}).get("sync_health") or "unknown"
        ).lower()
        if broker_health in {"unsafe", "unknown"}:
            return block(f"broker_sync_{broker_health}")

        production_status = str(
            status.get("production_readiness_status") or "unknown"
        ).lower()
        if production_status not in {"ready", "warning"}:
            return block(f"production_readiness_{production_status}")

        if cycle_mode == "live_phase1":
            if not bool(request.get("operator_acknowledged_risks", False)):
                return block("operator_acknowledgement_required")
            if not bool(status.get("can_run_live_phase1_cycle")):
                response["blocking_reasons"].extend(_strings(status.get("blocking_reasons")))
                response["warning_reasons"].extend(_strings(status.get("warning_reasons")))
                return block("release_live_phase1_gates_blocked")
            soak_mode = LIVE_SOAK_MODE
        elif cycle_mode == "dry_run":
            if not bool(status.get("can_run_dry_run_cycle")):
                response["warning_reasons"].extend(_strings(status.get("warning_reasons")))
            soak_mode = MONITORING_SOAK_MODE
        else:
            cycle_mode = "monitoring"
            response["cycle_mode"] = cycle_mode
            soak_mode = MONITORING_SOAK_MODE

        try:
            soak_result = self.soak_test_service.run_once(
                db,
                {
                    "provider": request.get("provider") or PROVIDER,
                    "market": request.get("market") or MARKET,
                    "mode": soak_mode,
                    "trigger_source": "manual_soak_test"
                    if request.get("trigger_source") == "manual_release_cycle"
                    else "scheduler_soak_test",
                    "language": request.get("language"),
                    "locale": request.get("locale"),
                    "operator_acknowledged_risks": bool(
                        request.get("operator_acknowledged_risks", False)
                    ),
                },
                now=now_utc,
            )
        except Exception as exc:
            response["result_status"] = "error"
            response["blocking_reasons"].append(
                f"automation_soak_failed:{exc.__class__.__name__}"
            )
            response["next_safe_action"] = "review_release_cycle_error"
            return self._save_cycle(db, request=request, response=response, now_utc=now_utc)

        response["soak_run_id"] = _int_or_none(soak_result.get("run_id"))
        response["orchestrator_run_id"] = _int_or_none(
            soak_result.get("orchestrator_run_id")
        )
        response["real_order_submitted"] = bool(soak_result.get("real_order_submitted"))
        response["broker_submit_called"] = bool(soak_result.get("broker_submit_called"))
        response["manual_submit_called"] = bool(soak_result.get("manual_submit_called"))
        response["order_cancel_called"] = False
        response["action_taken"] = str(soak_result.get("action_taken") or "none")
        response["risk_flags"].extend(_strings(soak_result.get("risk_flags")))
        response["gating_notes"].extend(_strings(soak_result.get("gating_notes")))
        response["blocking_reasons"].extend(_strings(soak_result.get("blocking_reasons")))
        response["warning_reasons"].extend(_strings(soak_result.get("warning_reasons")))
        response["result_status"] = self._map_cycle_result(
            cycle_mode=cycle_mode,
            soak_result=soak_result,
        )
        response["next_safe_action"] = self._cycle_next_action(
            response["result_status"],
            response["blocking_reasons"],
        )
        return self._save_cycle(db, request=request, response=response, now_utc=now_utc)

    def _collect_sources(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
        now_utc: datetime,
    ) -> dict[str, Any]:
        errors: list[str] = []

        def read_source(name: str, fallback: dict[str, Any], reader) -> dict[str, Any]:
            try:
                value = reader()
                return sanitize_kis_payload(value if isinstance(value, dict) else fallback)
            except Exception as exc:
                errors.append(f"{name}:{exc.__class__.__name__}")
                return fallback

        automation_mode_status = read_source(
            "automation_mode",
            {
                "automation_mode": "off",
                "effective_status": "blocked",
                "can_run_dry_run": False,
                "can_submit_live_order": False,
                "blocking_reasons": ["automation_mode_status_unavailable"],
            },
            lambda: self.automation_mode_service.status(db, now=now_utc),
        )
        broker_sync_status = read_source(
            "broker_sync",
            {
                "sync_health": "unknown",
                "should_block_orchestrator": True,
                "blocking_reasons": ["broker_sync_watchdog_unavailable"],
                "next_safe_action": "manual_review",
            },
            lambda: self.broker_sync_watchdog_service.latest(
                db,
                provider=provider,
                market=market,
                now=now_utc,
            ),
        )
        soak_status = read_source(
            "soak",
            {
                "effective_status": "unsafe",
                "kill_latch_active": True,
                "blocking_reasons": ["automation_soak_status_unavailable"],
            },
            lambda: self.soak_test_service.status(
                db,
                provider=provider,
                market=market,
                now=now_utc,
            ),
        )
        production_readiness = read_source(
            "readiness",
            {
                "overall_status": "blocked",
                "blocking_reasons": ["production_readiness_unavailable"],
            },
            lambda: self.readiness_service.readiness(
                db,
                provider=provider,
                market=market,
                include_details=False,
                include_recent=False,
                now=now_utc,
            ),
        )
        orchestrator_status = read_source(
            "orchestrator",
            {
                "result_status": "disabled",
                "orchestrator_enabled": False,
                "allow_live_orders": False,
                "pending_order_conflict_count": 0,
            },
            lambda: self.portfolio_orchestrator_service.latest(
                db,
                provider=provider,
                market=market,
                now=now_utc,
            ),
        )
        auto_buy_status = read_source(
            "auto_buy_phase1",
            {
                "result_status": "disabled",
                "auto_buy_live_enabled": False,
                "daily_auto_buy_count": 0,
                "daily_auto_buy_limit": 1,
            },
            lambda: self.auto_buy_service.status(
                db,
                provider=provider,
                market=market,
                now=now_utc,
            ),
        )
        auto_sell_status = read_source(
            "auto_sell_phase1",
            {
                "result_status": "disabled",
                "auto_sell_live_enabled": False,
                "daily_auto_sell_count": 0,
                "daily_auto_sell_limit": 1,
            },
            lambda: self.auto_sell_service.status(
                db,
                provider=provider,
                market=market,
                now=now_utc,
            ),
        )
        return {
            "automation_mode_status": automation_mode_status,
            "broker_sync_status": broker_sync_status,
            "soak_status": soak_status,
            "production_readiness": production_readiness,
            "orchestrator_status": orchestrator_status,
            "auto_buy_phase1_status": auto_buy_status,
            "auto_sell_phase1_status": auto_sell_status,
            "source_errors": errors,
        }

    def _counts_today(self, db: Session, *, now_utc: datetime) -> dict[str, int]:
        start_utc, end_utc = _kr_day_bounds(now_utc)
        rows = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == MODE)
            .filter(TradeRunLog.created_at >= start_utc)
            .filter(TradeRunLog.created_at < end_utc)
            .all()
        )
        action_count = 0
        buy_count = 0
        sell_count = 0
        for row in rows:
            payload = _json_dict(row.response_payload)
            if payload.get("real_order_submitted") is not True:
                continue
            action_count += 1
            action = str(payload.get("action_taken") or "").lower()
            if "buy" in action:
                buy_count += 1
            if "sell" in action:
                sell_count += 1
        return {
            "action_count": action_count,
            "buy_count": buy_count,
            "sell_count": sell_count,
        }

    def _daily_trade_remaining(
        self,
        *,
        settings: dict[str, Any],
        automation_mode_status: dict[str, Any],
        counts: dict[str, int],
    ) -> int:
        mode_remaining = max(
            0,
            _int(automation_mode_status.get("daily_trade_limit_remaining"), 0),
        )
        release_limit = max(
            0,
            _int(settings.get("automation_release_max_daily_auto_actions"), 2),
        )
        release_remaining = max(0, release_limit - counts["action_count"])
        if mode_remaining <= 0:
            return release_remaining
        return min(mode_remaining, release_remaining)

    def _daily_phase_remaining(
        self,
        *,
        release_limit: int,
        release_used: int,
        phase_status: dict[str, Any],
        count_key: str,
        limit_key: str,
    ) -> int:
        release_remaining = max(0, max(0, release_limit) - max(0, release_used))
        phase_limit = max(0, _int(phase_status.get(limit_key), release_limit))
        phase_count = max(0, _int(phase_status.get(count_key), 0))
        phase_remaining = max(0, phase_limit - phase_count)
        return min(release_remaining, phase_remaining)

    def _soak_recently_passed(
        self,
        value: Any,
        *,
        now_utc: datetime,
    ) -> bool:
        passed_at = _utc_or_none(value)
        if passed_at is None:
            return False
        return now_utc - passed_at <= timedelta(hours=24)

    def _effective_status(
        self,
        *,
        release_enabled: bool,
        kill_latch_active: bool,
        broker_health: str,
        production_status: str,
        automation_mode: str,
        can_run_monitoring: bool,
        can_run_dry_run: bool,
        can_run_live: bool,
    ) -> str:
        if not release_enabled:
            return "disabled"
        if kill_latch_active:
            return "kill_latched"
        if broker_health in {"unsafe", "unknown"} or production_status in {
            "blocked",
            "unknown",
        }:
            return "unsafe"
        if can_run_live:
            return "live_ready"
        if automation_mode == "phase1_live_ready":
            return "live_ready_blocked"
        if can_run_dry_run:
            return "dry_run_ready"
        if can_run_monitoring:
            return "monitoring_ready"
        return "preflight_required"

    def _next_safe_action(
        self,
        *,
        effective_status: str,
        blocking_reasons: list[str],
        warning_reasons: list[str],
    ) -> str:
        if effective_status == "disabled":
            return "arm_release_after_preflight"
        if effective_status == "kill_latched":
            return "operator_review_then_reset_kill_latch"
        if blocking_reasons:
            first = blocking_reasons[0]
            if "broker_sync" in first or "sync" in first:
                return "review_broker_sync_watchdog"
            if "production_readiness" in first:
                return "review_production_readiness"
            if "dry_run" in first:
                return "operator_must_change_dry_run_outside_release"
            if "kill_switch" in first:
                return "operator_must_review_kill_switch_outside_release"
            return "resolve_release_checklist_blockers"
        if warning_reasons:
            return "review_release_warnings"
        if effective_status == "live_ready":
            return "run_live_phase1_cycle_only_with_acknowledgement"
        if effective_status == "dry_run_ready":
            return "run_dry_run_cycle_once"
        return "run_monitoring_cycle_once"

    def _safety_flags(self, settings: dict[str, Any]) -> dict[str, Any]:
        return {
            "release_does_not_change_dry_run": True,
            "release_does_not_change_kill_switch": True,
            "release_does_not_change_kis_real_order_enabled": True,
            "direct_broker_submit_path": False,
            "direct_manual_submit_path": False,
            "order_cancel_path": False,
            "phase1_services_own_live_gates": True,
            "orchestrator_positions_first": True,
            "single_action_per_cycle": _int(
                settings.get("automation_release_max_actions_per_cycle"),
                1,
            )
            == 1,
            "release_scheduler_enabled": bool(
                settings.get("automation_release_scheduler_enabled")
            ),
            "release_allow_live_phase1": bool(
                settings.get("automation_release_allow_live_phase1")
            ),
        }

    def _base_cycle_response(
        self,
        *,
        status: dict[str, Any],
        cycle_mode: str,
        generated_at: datetime,
    ) -> dict[str, Any]:
        return {
            "run_id": None,
            "generated_at": generated_at.isoformat(),
            "release_enabled": bool(status.get("release_enabled")),
            "release_mode": str(status.get("release_mode") or "controlled_phase1"),
            "cycle_mode": cycle_mode,
            "result_status": "blocked",
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "order_cancel_called": False,
            "action_taken": "none",
            "orchestrator_run_id": None,
            "soak_run_id": None,
            "checklist": status.get("checklist") or [],
            "blocking_reasons": [],
            "warning_reasons": _strings(status.get("warning_reasons")),
            "risk_flags": [],
            "gating_notes": [
                "Automation release delegates cycle execution to the existing soak test service.",
                "Release arming does not change dry_run, kill_switch, or KIS real-order settings.",
            ],
            "next_safe_action": "review_release_status",
            "safety_flags": status.get("safety_flags") or {},
        }

    def _map_cycle_result(
        self,
        *,
        cycle_mode: str,
        soak_result: dict[str, Any],
    ) -> str:
        soak_status = str(soak_result.get("result_status") or "blocked").lower()
        if soak_status == "disabled":
            return "disabled"
        if soak_status == "kill_latched":
            return "kill_latched"
        if soak_status in {"blocked", "orchestrator_blocked"}:
            return "blocked"
        if soak_status == "error":
            return "error"
        if soak_result.get("real_order_submitted") is True:
            return "live_order_submitted"
        if str(soak_result.get("action_taken") or "none") == "none":
            return "no_action"
        if cycle_mode == "live_phase1":
            return "live_phase1_completed"
        if cycle_mode == "dry_run":
            return "dry_run_completed"
        return "monitoring_completed"

    def _cycle_next_action(self, result_status: str, blocking_reasons: list[str]) -> str:
        if result_status == "disabled":
            return "arm_release_after_preflight"
        if result_status == "kill_latched":
            return "operator_review_then_reset_kill_latch"
        if result_status in {"blocked", "error"}:
            if blocking_reasons:
                return self._next_safe_action(
                    effective_status="preflight_required",
                    blocking_reasons=blocking_reasons,
                    warning_reasons=[],
                )
            return "review_release_cycle_result"
        if result_status == "live_order_submitted":
            return "sync_and_review_submitted_order"
        return "review_release_cycle_result"

    def _save_cycle(
        self,
        db: Session,
        *,
        request: dict[str, Any],
        response: dict[str, Any],
        now_utc: datetime,
    ) -> dict[str, Any]:
        response["blocking_reasons"] = _dedupe(response.get("blocking_reasons"))
        response["warning_reasons"] = _dedupe(response.get("warning_reasons"))
        response["risk_flags"] = _dedupe(response.get("risk_flags"))
        response["gating_notes"] = _dedupe(response.get("gating_notes"))
        response["order_cancel_called"] = False
        safe_response = sanitize_kis_payload(response)
        row = TradeRunLog(
            run_key=f"automation_release_{uuid.uuid4().hex[:12]}",
            trigger_source=str(request.get("trigger_source") or "manual_release_cycle")[:40],
            symbol="AUTOMATION_RELEASE",
            mode=MODE,
            stage="done",
            result=str(safe_response.get("result_status") or "error")[:40],
            reason=_text(
                (safe_response.get("blocking_reasons") or [None])[0]
                if isinstance(safe_response.get("blocking_reasons"), list)
                else None
            ),
            request_payload=_json(request),
            response_payload=_json(safe_response),
            created_at=now_utc.replace(tzinfo=None),
        )
        db.add(row)
        db.flush()
        safe_response["run_id"] = row.id
        row.response_payload = _json(safe_response)
        db.commit()
        return sanitize_kis_payload(safe_response)


def _kr_day_bounds(now_utc: datetime) -> tuple[datetime, datetime]:
    local = now_utc.astimezone(KST)
    start_local = datetime.combine(local.date(), time.min, tzinfo=KST)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(UTC).replace(tzinfo=None),
        end_local.astimezone(UTC).replace(tzinfo=None),
    )


def _utc(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _utc_or_none(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _utc(value)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return _utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def _iso(value: Any) -> str | None:
    parsed = _utc_or_none(value)
    return parsed.isoformat() if parsed is not None else None


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    source = values if isinstance(values, list) else []
    for value in source:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
