from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import TradeRunLog
from app.schemas.automation_soak_test import (
    AutomationSoakRunOnceRequest,
    AutomationSoakStartRequest,
    AutomationSoakStopRequest,
)
from app.schemas.portfolio_orchestrator import PortfolioOrchestratorRunRequest
from app.services.automation_kill_rule_service import (
    AutomationKillRuleService,
    kr_day_bounds,
)
from app.services.automation_mode_control_service import AutomationModeControlService
from app.services.broker_sync_watchdog_service import BrokerSyncWatchdogService
from app.services.daily_ops_summary_service import DailyOpsSummaryService
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.ops_production_readiness_service import OpsProductionReadinessService
from app.services.portfolio_orchestrator_service import PortfolioOrchestratorService
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "automation_soak_test"
PROVIDER = "kis"
MARKET = "KR"
SUCCESS_STATUSES = {
    "dry_run_completed",
    "live_phase1_completed",
    "orchestrator_action_taken",
}


class AutomationSoakAcknowledgementRequired(ValueError):
    pass


class AutomationSoakTestService:
    """PR99 controlled soak-test layer over the existing automation loop."""

    def __init__(
        self,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        kill_rule_service: AutomationKillRuleService | None = None,
        broker_sync_watchdog_service: BrokerSyncWatchdogService | None = None,
        automation_mode_service: AutomationModeControlService | None = None,
        readiness_service: OpsProductionReadinessService | None = None,
        daily_ops_service: DailyOpsSummaryService | None = None,
        portfolio_orchestrator_service: PortfolioOrchestratorService | None = None,
    ) -> None:
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.kill_rule_service = kill_rule_service or AutomationKillRuleService()
        self.broker_sync_watchdog_service = (
            broker_sync_watchdog_service
            or BrokerSyncWatchdogService(runtime_settings=self.runtime_settings)
        )
        self.readiness_service = readiness_service or OpsProductionReadinessService(
            runtime_settings=self.runtime_settings
        )
        self.automation_mode_service = automation_mode_service or AutomationModeControlService(
            runtime_settings=self.runtime_settings,
            readiness_service=self.readiness_service,
            broker_sync_watchdog_service=self.broker_sync_watchdog_service,
        )
        self.daily_ops_service = daily_ops_service or DailyOpsSummaryService(
            runtime_settings=self.runtime_settings
        )
        self.portfolio_orchestrator_service = (
            portfolio_orchestrator_service
            or PortfolioOrchestratorService(
                runtime_settings=self.runtime_settings,
                readiness_service=self.readiness_service,
                broker_sync_watchdog_service=self.broker_sync_watchdog_service,
            )
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
        settings = self._settings(db)
        mode = _soak_mode(settings.get("automation_soak_mode"))
        counts = self._counts_today(db, now_utc=now_utc)
        sources = self._collect_sources(
            db,
            provider=provider,
            market=market,
            mode=mode,
            now_utc=now_utc,
            run_watchdog=False,
        )
        eval_settings = self._evaluation_settings(
            settings,
            counts=counts,
            mode=mode,
        )
        rules = self.kill_rule_service.evaluate(
            db,
            settings=eval_settings,
            provider=provider,
            market=market,
            soak_mode=mode,
            watchdog_status=sources["watchdog_status"],
            automation_mode_status=sources["automation_mode_status"],
            production_readiness=sources["production_readiness"],
            daily_ops_summary=sources["daily_ops_summary"],
            source_errors=sources["source_errors"],
            now=now_utc,
        )
        triggered = _triggered(rules)
        critical = _critical(triggered)
        blocking = _blocking_reasons(triggered)
        warnings = _warning_reasons(triggered)
        enabled = bool(settings.get("automation_soak_enabled", False))
        latch_active = bool(settings.get("automation_soak_kill_latch_active"))
        allow_live = bool(settings.get("automation_soak_allow_live_phase1", False))
        can_run = enabled and not latch_active and not critical and counts["cycle_count_today"] < max(
            0,
            _int(settings.get("automation_soak_max_cycles_per_day"), 3),
        )
        can_attempt_live = (
            can_run
            and mode == "live_phase1_controlled"
            and allow_live
            and bool((sources["automation_mode_status"] or {}).get("can_attempt_phase1_live"))
        )
        response = {
            "generated_at": now_utc.isoformat(),
            "soak_enabled": enabled,
            "soak_mode": mode,
            "allow_live_phase1": allow_live,
            "kill_latch_active": latch_active,
            "kill_latch_reason": _text(settings.get("automation_soak_kill_latch_reason")),
            "kill_latch_triggered_at": _iso(settings.get("automation_soak_kill_latch_triggered_at")),
            "effective_status": self._effective_status(
                enabled=enabled,
                latch_active=latch_active,
                mode=mode,
                allow_live=allow_live,
                can_run=can_run,
                can_attempt_live=can_attempt_live,
                critical=critical,
            ),
            "can_run_soak_cycle": can_run,
            "can_attempt_live_phase1": can_attempt_live,
            "can_submit_live_order": bool(
                can_attempt_live
                and (sources["automation_mode_status"] or {}).get("can_submit_live_order")
            ),
            "cycle_count_today": counts["cycle_count_today"],
            "max_cycles_per_day": max(0, _int(settings.get("automation_soak_max_cycles_per_day"), 3)),
            "action_count_today": counts["action_count_today"],
            "max_actions_per_day": max(0, _int(settings.get("automation_soak_max_actions_per_day"), 1)),
            "consecutive_failure_count": max(
                0,
                _int(settings.get("automation_soak_consecutive_failure_count"), 0),
            ),
            "max_consecutive_failures": max(
                1,
                _int(settings.get("automation_soak_max_consecutive_failures"), 2),
            ),
            "latest_orchestrator_result": self._latest_orchestrator(db),
            "latest_watchdog_status": sources["watchdog_status"],
            "automation_mode_status": sources["automation_mode_status"],
            "production_readiness_status": str(
                (sources["production_readiness"] or {}).get("overall_status") or "unknown"
            ).lower(),
            "daily_loss_status": self._daily_loss_status(settings, sources["daily_ops_summary"]),
            "kill_rules": rules,
            "blocking_reasons": blocking,
            "warning_reasons": warnings,
            "next_safe_action": self._next_safe_action(
                enabled=enabled,
                latch_active=latch_active,
                critical=critical,
                blocking=blocking,
                warnings=warnings,
                mode=mode,
            ),
            "safety_flags": self._safety_flags(),
        }
        return sanitize_kis_payload(response)

    def run_once(
        self,
        db: Session,
        request: AutomationSoakRunOnceRequest | dict[str, Any] | None = None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        payload = (
            request
            if isinstance(request, AutomationSoakRunOnceRequest)
            else AutomationSoakRunOnceRequest.model_validate(request or {})
        )
        now_utc = _utc(now)
        settings = self._settings(db)
        mode = payload.mode or _soak_mode(settings.get("automation_soak_mode"))
        counts = self._counts_today(db, now_utc=now_utc)
        response = self._base_run_response(
            payload=payload,
            mode=mode,
            now_utc=now_utc,
            counts=counts,
            settings=settings,
        )

        if not bool(settings.get("automation_soak_enabled", False)):
            response["result_status"] = "disabled"
            response["blocking_reasons"].append("automation_soak_disabled")
            response["next_safe_action"] = "enable_soak_test_explicitly"
            return self._finish_run(db, response=response, payload=payload, now_utc=now_utc)

        if bool(settings.get("automation_soak_kill_latch_active")):
            response["result_status"] = "kill_latched"
            response["kill_latch_active"] = True
            response["blocking_reasons"].append(
                _text(settings.get("automation_soak_kill_latch_reason"))
                or "automation_soak_kill_latch_active"
            )
            response["next_safe_action"] = "operator_review_then_reset_kill_latch"
            return self._finish_run(db, response=response, payload=payload, now_utc=now_utc)

        if counts["cycle_count_today"] >= max(
            0,
            _int(settings.get("automation_soak_max_cycles_per_day"), 3),
        ):
            response["result_status"] = "blocked"
            response["blocking_reasons"].append("automation_soak_daily_cycle_limit_reached")
            response["next_safe_action"] = "wait_for_next_trading_day"
            return self._finish_run(db, response=response, payload=payload, now_utc=now_utc)

        if mode == "live_phase1_controlled":
            if not bool(settings.get("automation_soak_allow_live_phase1", False)):
                response["result_status"] = "blocked"
                response["blocking_reasons"].append("automation_soak_live_phase1_disabled")
                response["next_safe_action"] = "review_soak_live_phase1_setting"
                return self._finish_run(db, response=response, payload=payload, now_utc=now_utc)
            if not payload.operator_acknowledged_risks:
                response["result_status"] = "blocked"
                response["blocking_reasons"].append("operator_acknowledgement_required")
                response["next_safe_action"] = "acknowledge_risks_before_live_phase1_soak"
                return self._finish_run(db, response=response, payload=payload, now_utc=now_utc)

        sources = self._collect_sources(
            db,
            provider=payload.provider,
            market=payload.market,
            mode=mode,
            now_utc=now_utc,
            run_watchdog=True,
        )
        response["broker_sync_health"] = str(
            (sources["watchdog_status"] or {}).get("sync_health") or "unknown"
        )
        response["automation_mode_effective_status"] = str(
            (sources["automation_mode_status"] or {}).get("effective_status")
            or "unknown"
        )
        response["production_readiness_status"] = str(
            (sources["production_readiness"] or {}).get("overall_status") or "unknown"
        ).lower()
        eval_settings = self._evaluation_settings(settings, counts=counts, mode=mode)
        rules = self.kill_rule_service.evaluate(
            db,
            settings=eval_settings,
            provider=payload.provider,
            market=payload.market,
            soak_mode=mode,
            watchdog_status=sources["watchdog_status"],
            automation_mode_status=sources["automation_mode_status"],
            production_readiness=sources["production_readiness"],
            daily_ops_summary=sources["daily_ops_summary"],
            source_errors=sources["source_errors"],
            now=now_utc,
        )
        response["kill_rules_evaluated"] = rules
        response["kill_rules_triggered"] = _triggered(rules)
        response["blocking_reasons"].extend(_blocking_reasons(response["kill_rules_triggered"]))
        response["warning_reasons"].extend(_warning_reasons(response["kill_rules_triggered"]))
        if _critical(response["kill_rules_triggered"]):
            self._activate_kill_latch(
                db,
                rules=response["kill_rules_triggered"],
                now_utc=now_utc,
                settings=settings,
            )
            response["result_status"] = "blocked"
            response["kill_latch_active"] = True
            response["next_safe_action"] = self._triggered_next_action(
                response["kill_rules_triggered"]
            )
            return self._finish_run(db, response=response, payload=payload, now_utc=now_utc)

        orchestrator_result: dict[str, Any] | None = None
        try:
            orchestrator_result = self.portfolio_orchestrator_service.run_once(
                db,
                PortfolioOrchestratorRunRequest(
                    provider=payload.provider,
                    market=payload.market,
                    trigger_source="manual_orchestrator_test"
                    if payload.trigger_source == "manual_soak_test"
                    else "scheduler_orchestrator",
                    mode=mode,
                    language=payload.language,
                    locale=payload.locale,
                ),
                now=now_utc,
            )
        except Exception as exc:
            orchestrator_result = {
                "result_status": "error",
                "primary_block_reason": f"orchestrator_failed:{exc.__class__.__name__}",
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "action_taken": "none",
            }

        response["orchestrator_run_id"] = _int_or_none(orchestrator_result.get("run_id"))
        response["real_order_submitted"] = bool(orchestrator_result.get("real_order_submitted"))
        response["broker_submit_called"] = bool(orchestrator_result.get("broker_submit_called"))
        response["manual_submit_called"] = bool(orchestrator_result.get("manual_submit_called"))
        response["action_taken"] = str(orchestrator_result.get("action_taken") or "none")
        response["risk_flags"].extend(_strings(orchestrator_result.get("risk_flags")))
        response["gating_notes"].extend(_strings(orchestrator_result.get("gating_notes")))

        post_rules = self.kill_rule_service.evaluate(
            db,
            settings=eval_settings,
            provider=payload.provider,
            market=payload.market,
            soak_mode=mode,
            watchdog_status=sources["watchdog_status"],
            automation_mode_status=sources["automation_mode_status"],
            production_readiness=sources["production_readiness"],
            daily_ops_summary=sources["daily_ops_summary"],
            orchestrator_result=orchestrator_result,
            source_errors=sources["source_errors"],
            now=now_utc,
        )
        response["kill_rules_evaluated"] = post_rules
        response["kill_rules_triggered"] = _triggered(post_rules)
        response["blocking_reasons"].extend(_blocking_reasons(response["kill_rules_triggered"]))
        response["warning_reasons"].extend(_warning_reasons(response["kill_rules_triggered"]))
        if _critical(response["kill_rules_triggered"]):
            self._activate_kill_latch(
                db,
                rules=response["kill_rules_triggered"],
                now_utc=now_utc,
                settings=settings,
            )
            response["result_status"] = "error"
            response["kill_latch_active"] = True
            response["next_safe_action"] = self._triggered_next_action(
                response["kill_rules_triggered"]
            )
            return self._finish_run(db, response=response, payload=payload, now_utc=now_utc)

        orchestrator_status = str(orchestrator_result.get("result_status") or "error").lower()
        if orchestrator_status in {"sell_submitted", "buy_submitted"}:
            response["result_status"] = "orchestrator_action_taken"
        elif orchestrator_status == "dry_run_completed":
            response["result_status"] = "dry_run_completed"
        elif orchestrator_status in {"completed_no_action"} and mode == "live_phase1_controlled":
            response["result_status"] = "live_phase1_completed"
        elif orchestrator_status in {"disabled", "blocked"}:
            response["result_status"] = "orchestrator_blocked"
            response["blocking_reasons"].append(
                str(orchestrator_result.get("primary_block_reason") or orchestrator_status)
            )
        elif orchestrator_status == "error":
            response["result_status"] = "error"
            response["blocking_reasons"].append(
                str(orchestrator_result.get("primary_block_reason") or "orchestrator_error")
            )
        else:
            response["result_status"] = "live_phase1_completed" if mode == "live_phase1_controlled" else "dry_run_completed"
        response["next_safe_action"] = self._run_next_action(response, orchestrator_result)
        return self._finish_run(db, response=response, payload=payload, now_utc=now_utc)

    def start(
        self,
        db: Session,
        payload: AutomationSoakStartRequest | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = (
            payload
            if isinstance(payload, AutomationSoakStartRequest)
            else AutomationSoakStartRequest.model_validate(payload or {})
        )
        if request.allow_live_phase1 and not request.operator_acknowledged_risks:
            raise AutomationSoakAcknowledgementRequired(
                "allow_live_phase1 requires operator_acknowledged_risks=true"
            )
        self.runtime_settings.update_settings(
            db,
            {
                "automation_soak_enabled": True,
                "automation_soak_mode": request.mode,
                "automation_soak_allow_live_phase1": bool(request.allow_live_phase1),
            },
        )
        return self.status(db)

    def stop(
        self,
        db: Session,
        payload: AutomationSoakStopRequest | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        AutomationSoakStopRequest.model_validate(payload or {})
        self.runtime_settings.update_settings(db, {"automation_soak_enabled": False})
        return self.status(db)

    def reset_kill_latch(
        self,
        db: Session,
        *,
        operator_acknowledged_risks: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if not operator_acknowledged_risks:
            raise AutomationSoakAcknowledgementRequired(
                "reset kill latch requires operator_acknowledged_risks=true"
            )
        row = self.runtime_settings.get_or_create(db)
        row.automation_soak_kill_latch_active = False
        row.automation_soak_kill_latch_reason = None
        row.automation_soak_kill_latch_triggered_at = None
        db.commit()
        db.refresh(row)
        return self.status(db)

    def _collect_sources(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
        mode: str,
        now_utc: datetime,
        run_watchdog: bool,
    ) -> dict[str, Any]:
        errors: list[str] = []
        watchdog_status = None
        try:
            if run_watchdog:
                watchdog_status = self.broker_sync_watchdog_service.status(
                    db,
                    provider=provider,
                    market=market,
                    persist=True,
                    now=now_utc,
                    trigger_source="automation_soak_precheck",
                )
            else:
                watchdog_status = self.broker_sync_watchdog_service.latest(
                    db,
                    provider=provider,
                    market=market,
                    now=now_utc,
                )
        except Exception as exc:
            errors.append(f"watchdog:{exc.__class__.__name__}")
            watchdog_status = {
                "sync_health": "unknown",
                "should_block_orchestrator": True,
                "blocking_reasons": ["broker_sync_watchdog_unavailable"],
                "issues": [],
                "next_safe_action": "manual_review",
            }

        try:
            automation_mode_status = self.automation_mode_service.status(db, now=now_utc)
        except Exception as exc:
            errors.append(f"automation_mode:{exc.__class__.__name__}")
            automation_mode_status = {
                "effective_status": "blocked",
                "can_attempt_phase1_live": False,
                "can_submit_live_order": False,
                "blocking_reasons": ["automation_mode_status_unavailable"],
            }

        try:
            production_readiness = self.readiness_service.readiness(
                db,
                provider=provider,
                market=market,
                include_details=False,
                include_recent=mode == "live_phase1_controlled",
                now=now_utc,
            )
        except Exception as exc:
            errors.append(f"readiness:{exc.__class__.__name__}")
            production_readiness = {
                "overall_status": "blocked",
                "blocking_reasons": ["production_readiness_unavailable"],
            }

        try:
            daily_ops_summary = self.daily_ops_service.summary(
                db,
                date_value=now_utc.date(),
                provider=provider,
                market=market,
                include_details=False,
            )
        except Exception as exc:
            errors.append(f"daily_ops:{exc.__class__.__name__}")
            daily_ops_summary = {}

        return {
            "watchdog_status": sanitize_kis_payload(watchdog_status),
            "automation_mode_status": sanitize_kis_payload(automation_mode_status),
            "production_readiness": sanitize_kis_payload(production_readiness),
            "daily_ops_summary": sanitize_kis_payload(daily_ops_summary),
            "source_errors": errors,
        }

    def _settings(self, db: Session) -> dict[str, Any]:
        settings = self.runtime_settings.get_settings_read_only(db)
        app_settings = getattr(self.runtime_settings, "settings", None)
        settings["_app_kis_real_order_enabled"] = bool(
            getattr(app_settings, "kis_real_order_enabled", False)
        )
        return settings

    def _evaluation_settings(
        self,
        settings: dict[str, Any],
        *,
        counts: dict[str, int],
        mode: str,
    ) -> dict[str, Any]:
        result = dict(settings)
        max_actions = max(0, _int(settings.get("automation_soak_max_actions_per_day"), 1))
        result["_daily_action_limit_exhausted"] = (
            mode == "live_phase1_controlled"
            and max_actions > 0
            and counts["action_count_today"] >= max_actions
        )
        return result

    def _counts_today(self, db: Session, *, now_utc: datetime) -> dict[str, int]:
        start_utc, end_utc = kr_day_bounds(now_utc)
        rows = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == MODE)
            .filter(TradeRunLog.created_at >= start_utc)
            .filter(TradeRunLog.created_at < end_utc)
            .all()
        )
        action_count = 0
        for row in rows:
            payload = _json_dict(row.response_payload)
            if payload.get("real_order_submitted") is True:
                action_count += 1
        return {
            "cycle_count_today": len(rows),
            "action_count_today": action_count,
        }

    def _base_run_response(
        self,
        *,
        payload: AutomationSoakRunOnceRequest,
        mode: str,
        now_utc: datetime,
        counts: dict[str, int],
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "run_id": None,
            "generated_at": now_utc.isoformat(),
            "provider": payload.provider,
            "market": payload.market,
            "soak_mode": mode,
            "trigger_source": payload.trigger_source,
            "result_status": "blocked",
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "order_cancel_called": False,
            "action_taken": "none",
            "orchestrator_run_id": None,
            "broker_sync_health": "unknown",
            "automation_mode_effective_status": "unknown",
            "production_readiness_status": "unknown",
            "kill_rules_evaluated": [],
            "kill_rules_triggered": [],
            "kill_latch_active": bool(settings.get("automation_soak_kill_latch_active")),
            "cycle_count_today": counts["cycle_count_today"],
            "action_count_today": counts["action_count_today"],
            "consecutive_failure_count": max(
                0,
                _int(settings.get("automation_soak_consecutive_failure_count"), 0),
            ),
            "risk_flags": [],
            "gating_notes": [
                "Automation soak test delegates only to the existing portfolio orchestrator.",
                "No direct broker submit or order cancellation path exists in the soak service.",
            ],
            "blocking_reasons": [],
            "warning_reasons": [],
            "next_safe_action": "review_soak_status",
            "safety_flags": self._safety_flags(),
        }

    def _finish_run(
        self,
        db: Session,
        *,
        response: dict[str, Any],
        payload: AutomationSoakRunOnceRequest,
        now_utc: datetime,
    ) -> dict[str, Any]:
        response["blocking_reasons"] = _dedupe(response.get("blocking_reasons"))
        response["warning_reasons"] = _dedupe(response.get("warning_reasons"))
        response["risk_flags"] = _dedupe(response.get("risk_flags"))
        response["gating_notes"] = _dedupe(response.get("gating_notes"))
        response["safety_flags"] = self._safety_flags()
        response["order_cancel_called"] = False
        response["consecutive_failure_count"] = self._record_failure_state(
            db,
            result_status=str(response.get("result_status") or "error"),
            now_utc=now_utc,
        )
        safe_response = sanitize_kis_payload(response)
        row = TradeRunLog(
            run_key=f"automation_soak_{uuid.uuid4().hex[:12]}",
            trigger_source=str(payload.trigger_source or "manual_soak_test")[:40],
            symbol="AUTOMATION_SOAK",
            mode=MODE,
            stage="done",
            result=str(safe_response.get("result_status") or "error")[:40],
            reason=_text(
                (safe_response.get("blocking_reasons") or [None])[0]
                if isinstance(safe_response.get("blocking_reasons"), list)
                else None
            ),
            request_payload=_json(payload.model_dump(mode="json")),
            response_payload=_json(safe_response),
            created_at=now_utc.replace(tzinfo=None),
        )
        db.add(row)
        db.flush()
        safe_response["run_id"] = row.id
        safe_response["cycle_count_today"] = int(safe_response["cycle_count_today"]) + 1
        if safe_response.get("real_order_submitted") is True:
            safe_response["action_count_today"] = int(safe_response["action_count_today"]) + 1
        row.response_payload = _json(safe_response)
        db.commit()
        return sanitize_kis_payload(safe_response)

    def _record_failure_state(
        self,
        db: Session,
        *,
        result_status: str,
        now_utc: datetime,
    ) -> int:
        row = self.runtime_settings.get_or_create(db)
        if result_status in SUCCESS_STATUSES:
            row.automation_soak_consecutive_failure_count = 0
            row.automation_soak_last_successful_cycle_at = now_utc
        elif result_status not in {"disabled", "kill_latched"}:
            row.automation_soak_consecutive_failure_count = int(
                row.automation_soak_consecutive_failure_count or 0
            ) + 1
        db.commit()
        db.refresh(row)
        return int(row.automation_soak_consecutive_failure_count or 0)

    def _activate_kill_latch(
        self,
        db: Session,
        *,
        rules: list[dict[str, Any]],
        now_utc: datetime,
        settings: dict[str, Any],
    ) -> None:
        if not bool(settings.get("automation_soak_stop_on_any_critical", True)):
            return
        critical = _critical(rules)
        reason = critical[0]["rule_id"] if critical else "automation_soak_kill_rule"
        row = self.runtime_settings.get_or_create(db)
        row.automation_soak_kill_latch_active = True
        row.automation_soak_kill_latch_reason = reason
        row.automation_soak_kill_latch_triggered_at = now_utc
        db.commit()
        db.refresh(row)

    def _latest_orchestrator(self, db: Session) -> dict[str, Any] | None:
        row = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == "portfolio_orchestrator")
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .first()
        )
        if row is None:
            return None
        payload = _json_dict(row.response_payload)
        if payload:
            payload["run_id"] = payload.get("run_id") or row.id
            return sanitize_kis_payload(payload)
        return {
            "run_id": row.id,
            "result_status": row.result,
            "primary_block_reason": row.reason,
        }

    def _effective_status(
        self,
        *,
        enabled: bool,
        latch_active: bool,
        mode: str,
        allow_live: bool,
        can_run: bool,
        can_attempt_live: bool,
        critical: list[dict[str, Any]],
    ) -> str:
        if latch_active:
            return "kill_latched"
        if not enabled:
            return "disabled"
        if critical:
            return "unsafe"
        if mode == "live_phase1_controlled":
            return "live_phase1_ready" if allow_live and can_attempt_live else "live_phase1_blocked"
        return "dry_run_ready" if can_run else "monitoring"

    def _daily_loss_status(
        self,
        settings: dict[str, Any],
        daily_ops: dict[str, Any] | None,
    ) -> str:
        if not daily_ops:
            return "unknown"
        rules = self.kill_rule_service.evaluate(
            _NullSession(),
            settings={**settings, "_daily_action_limit_exhausted": False},
            daily_ops_summary=daily_ops,
        )
        return "breached" if any(rule["rule_id"] == "daily_loss_limit_breached" and rule["triggered"] for rule in rules) else "ok"

    def _next_safe_action(
        self,
        *,
        enabled: bool,
        latch_active: bool,
        critical: list[dict[str, Any]],
        blocking: list[str],
        warnings: list[str],
        mode: str,
    ) -> str:
        if not enabled:
            return "enable_soak_test_explicitly"
        if latch_active:
            return "operator_review_then_reset_kill_latch"
        if critical:
            return critical[0].get("recommended_action") or "manual_review"
        if blocking:
            return "review_blocking_reasons"
        if warnings:
            return "review_warnings_before_next_cycle"
        if mode == "live_phase1_controlled":
            return "operator_may_run_live_phase1_soak_if_intended"
        return "run_dry_run_soak_cycle"

    def _triggered_next_action(self, rules: list[dict[str, Any]]) -> str:
        for rule in rules:
            if rule.get("automation_blocking"):
                return str(rule.get("recommended_action") or "manual_review")
        return "manual_review"

    def _run_next_action(
        self,
        response: dict[str, Any],
        orchestrator_result: dict[str, Any],
    ) -> str:
        if response["result_status"] in SUCCESS_STATUSES:
            return str(orchestrator_result.get("next_safe_action") or "continue_monitoring")
        if response["blocking_reasons"]:
            return "review_blocking_reasons"
        return "review_soak_run_result"

    def _safety_flags(self) -> dict[str, Any]:
        return {
            "read_only_status": True,
            "soak_service_direct_broker_execution": False,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "order_cancel_called": False,
            "dry_run_changed": False,
            "kill_switch_changed": False,
            "kis_real_order_enabled_changed": False,
            "automation_mode_changed": False,
            "scheduler_changed": False,
        }


class _NullSession:
    def query(self, *args: Any, **kwargs: Any) -> Any:
        return _NullQuery()


class _NullQuery:
    def filter(self, *args: Any, **kwargs: Any) -> "_NullQuery":
        return self

    def order_by(self, *args: Any, **kwargs: Any) -> "_NullQuery":
        return self

    def limit(self, *args: Any, **kwargs: Any) -> "_NullQuery":
        return self

    def all(self) -> list[Any]:
        return []


def _soak_mode(value: Any) -> str:
    mode = str(value or "dry_run_monitoring").strip().lower()
    return mode if mode in {"dry_run_monitoring", "live_phase1_controlled"} else "dry_run_monitoring"


def _triggered(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [rule for rule in rules if rule.get("triggered")]


def _critical(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [rule for rule in rules if rule.get("severity") == "critical" and rule.get("triggered")]


def _blocking_reasons(rules: list[dict[str, Any]]) -> list[str]:
    return _dedupe([str(rule.get("rule_id")) for rule in rules if rule.get("automation_blocking")])


def _warning_reasons(rules: list[dict[str, Any]]) -> list[str]:
    return _dedupe([str(rule.get("rule_id")) for rule in rules if rule.get("severity") == "warning" and rule.get("triggered")])


def _strings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _dedupe(value: Any) -> list[str]:
    values = value if isinstance(value, list) else []
    result: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


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


def _json(value: Any) -> str:
    return json.dumps(sanitize_kis_payload(value), ensure_ascii=False, default=str)


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


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return _utc(value).isoformat()
    except Exception:
        return None


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except Exception:
        return default


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
