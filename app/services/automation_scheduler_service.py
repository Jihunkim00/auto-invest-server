from __future__ import annotations

"""The only production scheduler for Custom Profile automation.

Historical scheduler services remain callable through their compatibility
routes, but are intentionally never started by the application.
"""

import threading
import time
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.db.database import SessionLocal
from app.db.models import PositionLifecycle
from app.schemas.strategy_dry_run_auto_buy import ProfileAwareDryRunAutoBuyRequest
from app.services.automation_execution_authority_service import (
    AutomationExecutionAuthorityService,
)
from app.services.profile_aware_dry_run_auto_buy_factory import (
    build_profile_aware_dry_run_auto_buy_service,
)
from app.services.scheduler_service import SchedulerService


KST = ZoneInfo("Asia/Seoul")
CRITICAL_EXIT_ACTIONS = {"SELL_READY", "STOP_LOSS", "TAKE_PROFIT", "EXIT_SIGNAL"}


CANONICAL_TRIGGER_SOURCE = 'automation_scheduler'
CANONICAL_JOB_ID = 'automation_scheduler.kis.profile_tick'
CANONICAL_STAGES = [
    'profile_slot_resolution',
    'broker_account_sync',
    'positions_first',
    'exit_management',
    'entry_analysis',
    'risk_decision',
    'persistence',
]


class AutomationSchedulerService(SchedulerService):
    """Runs exactly one profile-defined KST automation tick per due slot."""

    _is_production_scheduler_authority = True

    def __init__(self):
        super().__init__()
        self.profile_aware_dry_run_auto_buy_service = None
        self._canonical_slot_lock = threading.Lock()

    def production_trading_jobs(self) -> list[dict[str, object]]:
        return [
            {
                'job_id': CANONICAL_JOB_ID,
                'authority': self.__class__.__name__,
                'provider': 'kis',
                'market': 'KR',
                'recurring': True,
                'automatic': True,
                'stages': list(CANONICAL_STAGES),
            }
        ]
    def _safe_call(self, callback, *args):
        result = super()._safe_call(callback, *args)
        if callback.__name__ == '_run_automation_tick':
            self._last_profile_run_at = datetime.now(UTC)
            if isinstance(result, dict):
                self._last_profile_run_result = str(
                    result.get('result')
                    or result.get('action')
                    or result.get('status')
                    or result.get('reason')
                    or 'completed'
                )
            else:
                self._last_profile_run_result = 'error' if result is None else 'completed'
        return result

    def _run_loop(self) -> None:
        # Deliberately do not start the former US/KR, phase, soak, release,
        # dry-run, or lifecycle scheduler loops. They are diagnostics or
        # compatibility entry points, not production execution authorities.
        while not self._stop_event.is_set():
            now_kst = datetime.now(KST)
            self._last_heartbeat_at = datetime.now(UTC)
            self._next_profile_run_at = self._next_automation_run_at(now_kst)
            day_key = now_kst.date().isoformat()
            self._slot_runs = {
                key for key in self._slot_runs if key.startswith(f"{day_key}:KR:")
            }
            for slot, hour, minute in self._profile_slots(now_kst):
                if now_kst.hour != hour or now_kst.minute != minute:
                    continue
                run_key = f"{day_key}:KR:automation:{slot}"
                if run_key in self._slot_runs:
                    continue
                self._slot_runs.add(run_key)
                self._safe_call(self._run_automation_tick, slot, now_kst, True)
            self._last_tick_at = datetime.now(UTC)
            time.sleep(20)

    def _profile_slots(self, now_kst: datetime) -> list[tuple[str, int, int]]:
        db = SessionLocal()
        try:
            schedule = self.automation_profiles.selected_profile_schedule(db, now=now_kst)
            if schedule and (
                (schedule.get('profile') or {}).get('provider') != 'kis'
                or (schedule.get('profile') or {}).get('market') != 'KR'
            ):
                return []
            authority = AutomationExecutionAuthorityService(self.runtime_settings).snapshot(db)
            runtime = self.runtime_settings.get_settings_read_only(db)
            if (
                not schedule
                or schedule.get("status") != "active"
                or not authority.get("scheduler_allowed")
                or not runtime.get("automation_profile_scheduler_enabled")
            ):
                return []
            result: list[tuple[str, int, int]] = []
            for value in schedule.get("analysis_times") or []:
                slot = self._profile_scheduler_slot(str(value))
                if slot is None:
                    continue
                hour, minute = (int(item) for item in slot.split(":"))
                result.append((slot, hour, minute))
            return result
        finally:
            db.close()

    def _next_automation_run_at(self, now_kst: datetime) -> datetime | None:
        slots = self._profile_slots(now_kst)
        for _, hour, minute in slots:
            candidate = now_kst.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate > now_kst:
                return candidate
        if not slots:
            return None
        _, hour, minute = slots[0]
        return (now_kst.replace(hour=hour, minute=minute, second=0, microsecond=0)
                + __import__("datetime").timedelta(days=1))

    def run_once(self, *, slot: str | None = None, now: datetime | None = None) -> dict[str, Any]:
        current = now.astimezone(KST) if now and now.tzinfo else (now or datetime.now(KST))
        resolved_slot = self._profile_scheduler_slot(slot or f"{current.hour:02d}:{current.minute:02d}")
        if resolved_slot is None:
            return {"status": "blocked", "reason": "invalid_profile_slot"}
        return self._safe_call(self._run_automation_tick, resolved_slot, current)

    def _run_automation_tick(
        self,
        slot_name: str,
        now: datetime | None = None,
        slot_claimed: bool = False,
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            now_kst = (now or datetime.now(KST)).astimezone(KST)
            slot = self._profile_scheduler_slot(slot_name)
            if slot is not None and not slot_claimed and not self._claim_slot(slot, now_kst):
                return {
                    'scheduler': self.__class__.__name__,
                    'status': 'skipped',
                    'reason': 'scheduler_slot_already_run',
                    'slot': slot,
                }
            authority = AutomationExecutionAuthorityService(self.runtime_settings).snapshot(db)
            runtime = self.runtime_settings.get_settings_read_only(db)
            schedule = self.automation_profiles.selected_profile_schedule(db, now=now_kst)
            if not authority.get("scheduler_allowed"):
                return self._create_scheduler_skip_log(
                    db, slot_name, "automation_mode_off", market="KR", provider="kis"
                )
            if not runtime.get("automation_profile_scheduler_enabled"):
                return self._create_scheduler_skip_log(
                    db, slot_name, "automation_disabled", market="KR", provider="kis"
                )
            if not schedule or schedule.get("status") != "active" or slot is None:
                return self._create_scheduler_skip_log(
                    db, slot_name, "active_profile_or_slot_unavailable", market="KR", provider="kis"
                )

            portfolio = self._manage_portfolio_first(db, slot=slot, now=now_kst)
            if self._critical_exit(portfolio):
                return self._create_scheduler_skip_log(
                    db, slot_name, "position_management_priority_buy_skipped",
                    market="KR", provider="kis",
                )

            mode = str(authority.get("automation_mode") or "test").strip().lower()
            execution_authority = str(
                authority.get("execution_authority") or mode.upper()
            )
            dry_result = self._run_profile_analysis(
                db,
                schedule=schedule,
                slot=slot,
                now=now_kst,
                execution_mode=mode,
            )
            dry_run = self._canonical_analysis_response(
                dry_result,
                schedule=schedule,
                slot=slot,
                now=now_kst,
                execution_mode=mode,
                execution_authority=execution_authority,
            )
            if mode == "live" and dry_result.get("action") == "would_buy":
                profile_buy = self._profile_buy_scheduler_service(db).run_once(
                    db,
                    dry_result,
                    scheduler_slot=slot,
                    trigger_source="automation_scheduler",
                    now=now_kst,
                    enforce_custom_profile_live_guard=True,
                    trusted_scheduler_authority=True,
                )
            elif mode == "live":
                profile_buy = {
                    "status": "blocked",
                    "action": "hold",
                    "reason": dry_result.get("reason") or "analysis_blocked",
                    "broker_submit_called": False,
                    "broker_buy_call_count": 0,
                    "real_external_kis_submit_count": 0,
                }
            else:
                profile_buy = {
                    "status": "simulated" if mode == "paper" else "analyzed",
                    "action": "hold",
                    "reason": "paper_mode_no_broker_submit" if mode == "paper" else "test_mode_no_broker_submit",
                    "broker_submit_called": False,
                    "broker_buy_call_count": 0,
                    "real_external_kis_submit_count": 0,
                }
            profile_buy_blocked = profile_buy.get("status") == "blocked"
            if mode == "live":
                canonical_result = (
                    "blocked" if profile_buy_blocked else "LIVE_READY"
                )
                canonical_reason = (
                    profile_buy.get("reason")
                    if profile_buy_blocked
                    else profile_buy.get("reason") or "canonical_live_ready"
                )
            else:
                canonical_result = dry_run.get("result") or (
                    "blocked" if dry_result.get("action") == "blocked" else dry_result.get("action")
                )
                canonical_reason = dry_result.get("reason") or "analysis_completed"
            risk_decision = dict(dry_run.get("risk_decision") or {})
            if profile_buy_blocked:
                risk_decision.update(
                    {
                        "approved": False,
                        "reason": canonical_reason,
                        "source": "canonical_execution_gate",
                    }
                )
            submission_eligible = bool(
                mode == "live"
                and canonical_result == "LIVE_READY"
                and dry_run.get("submission_eligible")
            )
            return {
                "scheduler": "AutomationSchedulerService",
                "mode": mode,
                "execution_mode": mode,
                "execution_authority": execution_authority,
                "profile_key": schedule.get("profile_key"),
                "slot": slot,
                "result": canonical_result,
                "reason": canonical_reason,
                "risk_decision": risk_decision,
                "submission_eligible": submission_eligible,
                "effective_min_entry_score": dry_run.get(
                    "effective_min_entry_score"
                ),
                "risk_flags": dry_run.get("risk_flags", []),
                "gating_notes": dry_run.get("gating_notes", []),
                "safety": dry_run.get("safety", {}),
                "portfolio": portfolio,
                "dry_run": dry_run,
                "profile_buy": profile_buy,
            }
        finally:
            db.close()

    def _run_profile_analysis(
        self,
        db,
        *,
        schedule: dict[str, Any],
        slot: str,
        now: datetime,
        execution_mode: str,
    ) -> dict[str, Any]:
        service = self.profile_aware_dry_run_auto_buy_service
        if service is None:
            service = build_profile_aware_dry_run_auto_buy_service(db)
            self.profile_aware_dry_run_auto_buy_service = service
        profile = schedule.get('profile') or {}
        request = ProfileAwareDryRunAutoBuyRequest(
            provider='kis',
            market='KR',
            automation_profile_key=str(schedule.get('profile_key') or '') or None,
            automation_profile_name=str(profile.get('display_name') or '') or None,
            trigger_source=CANONICAL_TRIGGER_SOURCE,
            use_watchlist=True,
            save_logs=True,
        )
        return service.run_once(
            db,
            request,
            now=now,
            execution_mode=execution_mode,
        )

    def _canonical_analysis_response(
        self,
        result: dict[str, Any],
        *,
        schedule: dict[str, Any],
        slot: str,
        now: datetime,
        execution_mode: str,
        execution_authority: str,
    ) -> dict[str, Any]:
        result_name = result.get("result") or result.get("action", "hold")
        return {
            'status': 'ok',
            'action': result.get('action', 'hold'),
            'result': result_name,
            'reason': result.get('reason'),
            'provider': 'kis',
            'market': 'KR',
            'profile_key': schedule.get('profile_key'),
            'slot': slot,
            'scheduled_slot_key': (
                f"{schedule.get('profile_key')}:{now.date().isoformat()}:{slot}"
            ),
            'analysis_completed': True,
            'scheduled_analysis_counted': True,
            'execution_mode': execution_mode,
            'execution_authority': execution_authority,
            'risk_decision': result.get('risk_decision', {}),
            'submission_eligible': bool(result.get('submission_eligible')),
            'effective_min_entry_score': result.get('effective_min_entry_score'),
            'final_buy_score': result.get('final_buy_score'),
            'required_entry_score': result.get('required_entry_score'),
            'risk_flags': result.get('risk_flags', []),
            'gating_notes': result.get('gating_notes', []),
            'dry_run_only': result.get('dry_run_only'),
            'preview_only': result.get('preview_only'),
            'dry_run_result': result,
            'real_order_submitted': False,
            'validation_called': False,
            'broker_submit_called': False,
            'manual_submit_called': False,
        }

    def _claim_slot(self, slot: str, now_kst: datetime) -> bool:
        run_key = f"{now_kst.date().isoformat()}:KR:automation:{slot}"
        with self._canonical_slot_lock:
            if run_key in self._slot_runs:
                return False
            self._slot_runs.add(run_key)
            return True

    def _manage_portfolio_first(self, db, *, slot: str, now: datetime) -> dict[str, Any] | None:
        if not db.query(PositionLifecycle).filter(
            PositionLifecycle.status.in_(["open", "closing"])
        ).count():
            return {"managed_count": 0, "items": []}
        service = self._profile_buy_scheduler_service(db)
        lifecycle = getattr(service, "lifecycle_service", None)
        if lifecycle is None:
            return {"managed_count": 0, "items": [], "reason": "portfolio_service_unavailable"}
        return lifecycle.run_management_once(
            db,
            execute=False,
            trigger_source="automation_scheduler",
            scheduler_slot=slot,
            now=now,
        )

    @staticmethod
    def _critical_exit(result: dict[str, Any] | None) -> bool:
        return any(
            str(item.get("action") or "").upper() in CRITICAL_EXIT_ACTIONS
            for item in (result or {}).get("items", [])
            if isinstance(item, dict)
        )
