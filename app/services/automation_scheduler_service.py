from __future__ import annotations

"""The only production scheduler for Custom Profile automation.

Historical scheduler services remain callable through their compatibility
routes, but are intentionally never started by the application.
"""

import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import SessionLocal
from app.db.models import PositionLifecycle
from app.schemas.strategy_dry_run_auto_buy import ProfileAwareDryRunAutoBuyRequest
from app.services.automation_execution_authority_service import (
    AutomationExecutionAuthorityService,
)
from app.services.profile_aware_dry_run_auto_buy_factory import (
    build_profile_aware_dry_run_auto_buy_service,
)
from app.services.kis_watchlist_update_service import (
    AUTOMATION_WATCHLIST_SOURCE_FILE,
    KisWatchlistUpdateService,
)
from app.services.market_profile_service import MarketProfileService
from app.services.profile_aware_guarded_live_auto_exit_service import (
    ProfileAwareGuardedLiveAutoExitService,
)
from app.services.scheduler_service import SchedulerService


KST = ZoneInfo("Asia/Seoul")
CRITICAL_EXIT_ACTIONS = {"SELL_READY", "STOP_LOSS", "TAKE_PROFIT", "EXIT_SIGNAL"}


CANONICAL_TRIGGER_SOURCE = 'automation_scheduler'
CANONICAL_JOB_ID = 'automation_scheduler.kis.profile_tick'
AUTOMATION_WATCHLIST_REFRESH_JOB_ID_PREFIX = (
    'automation_scheduler.kis.watchlist_refresh'
)
# Compatibility alias. Registered job ids are derived from the refresh slot.
AUTOMATION_WATCHLIST_REFRESH_JOB_ID = AUTOMATION_WATCHLIST_REFRESH_JOB_ID_PREFIX
AUTOMATION_WATCHLIST_REFRESH_LEAD = timedelta(minutes=10)
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
        self.profile_aware_guarded_live_auto_exit_service = None
        self._canonical_slot_lock = threading.Lock()
        self.automation_watchlist_update_service = None
        self._automation_watchlist_refresh_lock = threading.Lock()
        self._automation_watchlist_refresh_slots: set[str] = set()
        self._automation_watchlist_refresh_inflight: set[str] = set()
        self._automation_watchlist_status: dict[str, Any] = {
            'last_watchlist_refresh_at': None,
            'last_watchlist_refresh_slot': None,
            'last_watchlist_refresh_analysis_slot': None,
            'last_watchlist_refresh_result': None,
            'last_watchlist_refresh_reason': None,
            'source_universe_file': AUTOMATION_WATCHLIST_SOURCE_FILE,
            'source_universe_count': 0,
            'source_kospi_count': 0,
            'source_kosdaq_count': 0,
            'configured_max_price_krw': None,
            'budget_max_price_krw': None,
            'effective_max_price_krw': None,
            'price_lookup_success_count': 0,
            'price_lookup_failure_count': 0,
            'eligible_kospi_count': 0,
            'eligible_kosdaq_count': 0,
            'selected_kospi_count': 0,
            'selected_kosdaq_count': 0,
            'final_watchlist_count': 0,
            'max_price_in_final_watchlist': None,
            'over_budget_price_count': 0,
            'watchlist_file': 'config/watchlist_kr.yaml',
            'backup_file': None,
        }

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

    def maintenance_jobs(
        self,
        *,
        now: datetime | None = None,
    ) -> list[dict[str, object]]:
        now_kst = self._as_kst(now)
        schedule = self._selected_profile_schedule(now_kst)
        if not self._is_kis_kr_schedule(schedule):
            return []
        return [
            {
                'job_id': self._automation_watchlist_job_id(context['refresh_slot']),
                'authority': self.__class__.__name__,
                'scheduler_authority': self.__class__.__name__,
                'provider': 'kis',
                'market': 'KR',
                'slot': context['refresh_slot'],
                'analysis_slot': context['analysis_slot'],
                'scheduled_refresh_at': context['refresh_at'].isoformat(),
                'timezone': 'Asia/Seoul',
                'recurring': True,
                'automatic': True,
                'trading': False,
                'order_submission': False,
            }
            for context in self._derived_watchlist_refresh_slots(
                schedule,
                now_kst,

            )
        ]

    def runtime_status(self, *, now: datetime | None = None) -> dict[str, object]:
        status = super().runtime_status()
        now_kst = self._as_kst(now)
        maintenance = self.maintenance_jobs(now=now_kst)
        status.update(self._automation_watchlist_status)
        status.update(
            {
                'maintenance_jobs': maintenance,
                'maintenance_job_count': len(maintenance),
                'next_watchlist_refresh_at': self._next_watchlist_refresh_at(now_kst),
            }
        )
        return status

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
            self._automation_watchlist_refresh_slots = {
                value
                for value in self._automation_watchlist_refresh_slots
                if value.startswith(f'{day_key}:')
            }
            schedule = self._selected_profile_schedule(now_kst)
            for context in self._derived_watchlist_refresh_slots(
                schedule,
                now_kst,
                include_next_day=True,
            ):
                if not (
                    context['refresh_at'] <= now_kst < context['analysis_at']
                ):
                    continue
                self._safe_call(
                    self._run_automation_watchlist_refresh_scheduled_once,
                    context['analysis_slot'],
                    now_kst,
                )
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
        schedule = self._selected_profile_schedule(now_kst)
        if not self._is_kis_kr_schedule(schedule):
            return []
        db = SessionLocal()
        try:
            authority = AutomationExecutionAuthorityService(
                self.runtime_settings
            ).snapshot(db)
            runtime = self.runtime_settings.get_settings_read_only(db)
            if (
                schedule.get('status') != 'active'
                or not authority.get('scheduler_allowed')
                or not runtime.get('automation_profile_scheduler_enabled')
            ):
                return []
        finally:
            db.close()
        return [
            (
                context['analysis_slot'],
                context['analysis_at'].hour,
                context['analysis_at'].minute,
            )
            for context in self._derived_watchlist_analysis_slots(
                schedule,
                now_kst,
            )
        ]

    @staticmethod
    def _as_kst(value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(KST)
        if value.tzinfo is None:
            return value.replace(tzinfo=KST)
        return value.astimezone(KST)

    def _selected_profile_schedule(
        self,
        now_kst: datetime,
    ) -> dict[str, Any] | None:
        db = SessionLocal()
        try:
            return self.automation_profiles.selected_profile_schedule(
                db,
                now=now_kst,
            )
        finally:
            db.close()

    @staticmethod
    def _is_kis_kr_schedule(schedule: dict[str, Any] | None) -> bool:
        if not isinstance(schedule, dict):
            return False
        profile = schedule.get('profile')
        if not isinstance(profile, dict):
            return False
        return (
            str(profile.get('provider') or '').lower() == 'kis'
            and str(profile.get('market') or '').upper() == 'KR'
        )

    @staticmethod
    def _automation_watchlist_job_id(refresh_slot: str) -> str:
        return f'{AUTOMATION_WATCHLIST_REFRESH_JOB_ID_PREFIX}.{refresh_slot}'

    def _derived_watchlist_refresh_slots(
        self,
        schedule: dict[str, Any] | None,
        now_kst: datetime,
        *,
        include_next_day: bool = False,
    ) -> list[dict[str, Any]]:
        if not self._is_kis_kr_schedule(schedule):
            return []
        contexts: list[dict[str, Any]] = []
        day_offsets = range(2) if include_next_day else range(1)
        for value in schedule.get('analysis_times') or []:
            slot = self._profile_scheduler_slot(str(value))
            if slot is None:
                continue
            try:
                hour, minute = (int(part) for part in slot.split(':', 1))
            except (TypeError, ValueError):
                continue
            for day_offset in day_offsets:
                try:
                    analysis_at = now_kst.replace(
                        hour=hour,
                        minute=minute,
                        second=0,
                        microsecond=0,
                    ) + timedelta(days=day_offset)
                except (TypeError, ValueError):
                    continue
                refresh_at = analysis_at - AUTOMATION_WATCHLIST_REFRESH_LEAD
                contexts.append(
                    {
                        'analysis_slot': slot,
                        'refresh_slot': refresh_at.strftime('%H:%M'),
                        'analysis_at': analysis_at,
                        'refresh_at': refresh_at,
                        'idempotency_key': (
                            f'{analysis_at.date().isoformat()}:{slot}'
                        ),
                    }
                )
        return contexts

    def _derived_watchlist_analysis_slots(
        self,
        schedule: dict[str, Any] | None,
        now_kst: datetime,
    ) -> list[dict[str, Any]]:
        return self._derived_watchlist_refresh_slots(schedule, now_kst)

    def _next_watchlist_refresh_at(self, now_kst: datetime) -> str | None:
        schedule = self._selected_profile_schedule(now_kst)
        if not self._is_kis_kr_schedule(schedule):
            return None
        next_run = schedule.get('next_run_at')
        if not isinstance(next_run, datetime):
            return None
        next_run = self._as_kst(next_run)
        candidate = next_run - AUTOMATION_WATCHLIST_REFRESH_LEAD
        if candidate <= now_kst:
            # At the refresh minute itself the profile service quite correctly
            # still reports that analysis as the next run. Probe after that
            # analysis to move to the following canonical slot.
            next_schedule = self._selected_profile_schedule(
                now_kst + AUTOMATION_WATCHLIST_REFRESH_LEAD,
            )
            next_run = (
                next_schedule.get('next_run_at')
                if self._is_kis_kr_schedule(next_schedule)
                else None
            )
            if not isinstance(next_run, datetime):
                return None
            candidate = self._as_kst(next_run) - AUTOMATION_WATCHLIST_REFRESH_LEAD
        return candidate.isoformat() if candidate > now_kst else None

    def _next_automation_run_at(self, now_kst: datetime) -> datetime | None:
        slots = self._profile_slots(now_kst)
        for _, hour, minute in slots:
            candidate = now_kst.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate > now_kst:
                return candidate
        if not slots:
            return None
        _, hour, minute = slots[0]
        return (
            now_kst.replace(hour=hour, minute=minute, second=0, microsecond=0)
            + timedelta(days=1)
        )

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
            held_positions = list((portfolio or {}).get('broker_positions') or [])
            critical_item = next(
                (
                    item
                    for item in (portfolio or {}).get('items', [])
                    if isinstance(item, dict)
                    and str(item.get('action') or '').upper() in CRITICAL_EXIT_ACTIONS
                ),
                None,
            )
            effective_profile = (schedule.get('profile') or {}).get('effective_settings') or {}
            max_open_positions = int(effective_profile.get('max_open_positions') or 1)
            position_capacity_reached = len(held_positions) >= max_open_positions
            if critical_item is not None or position_capacity_reached:
                exit_result = None
                if critical_item is not None or held_positions:
                    exit_service = self._profile_guarded_live_auto_exit_service(db)
                    exit_result = exit_service.run_scheduler_once(
                        db,
                        scheduler_slot=slot,
                        symbol=(critical_item or {}).get('symbol') if critical_item else None,
                        now=now_kst,
                    )
                portfolio = {
                    **(portfolio or {}),
                    'sell_result': exit_result,
                    'buy_blocked': True,
                    'buy_block_reason': 'position_management_priority_buy_skipped',
                }
                sell_submitted = bool((exit_result or {}).get('submitted'))
                exit_block_reason = str((exit_result or {}).get('block_reason') or '')
                sell_status = (
                    'SELL_SUBMITTED'
                    if sell_submitted
                    else (
                        'blocked'
                        if exit_block_reason not in {'', 'no_exit_candidate', 'no_exit_trigger'}
                        else 'HOLD'
                    )
                )
                sell_reason = str(
                    (exit_result or {}).get('exit_reason')
                    or (exit_result or {}).get('block_reason')
                    or (exit_result or {}).get('reason')
                    or 'position_management_priority_buy_skipped'
                )
                return {
                    'scheduler': self.__class__.__name__,
                    'mode': str(authority.get('automation_mode') or 'test'),
                    'execution_mode': str(authority.get('automation_mode') or 'test'),
                    'execution_authority': str(
                        authority.get('execution_authority')
                        or str(authority.get('automation_mode') or 'test').upper()
                    ),
                    'profile_key': schedule.get('profile_key'),
                    'slot': slot,
                    'result': sell_status,
                    'reason': sell_reason,
                    'submission_eligible': False,
                    'real_order_submitted': sell_submitted,
                    'validation_called': bool((exit_result or {}).get('safety', {}).get('validation_called')),
                    'broker_submit_called': bool((exit_result or {}).get('safety', {}).get('broker_submit_called')),
                    'manual_submit_called': False,
                    'portfolio': portfolio,
                    'position_management': portfolio,
                    'dry_run': None,
                    'profile_buy': {
                        'status': 'blocked',
                        'action': 'hold',
                        'reason': 'position_management_priority_buy_skipped',
                        'broker_submit_called': False,
                        'broker_buy_call_count': 0,
                        'real_external_kis_submit_count': 0,
                    },
                }

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

    def run_automation_watchlist_refresh_once(
        self,
        *,
        now: datetime | None = None,
        analysis_slot: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        '''Run one derived, non-trading Automation watchlist maintenance job.'''
        now_kst = self._as_kst(now)
        schedule = self._selected_profile_schedule(now_kst)
        context = self._resolve_watchlist_refresh_context(
            schedule,
            now_kst,
            analysis_slot=analysis_slot,
        )
        if context is None:
            reason = (
                'no_active_profile'
                if schedule is None
                else 'automation_watchlist_refresh_slot_unavailable'
            )
            return self._automation_watchlist_skip(now_kst, reason)

        refresh_key = context['idempotency_key']
        if not force:
            with self._automation_watchlist_refresh_lock:
                if (
                    refresh_key in self._automation_watchlist_refresh_slots
                    or refresh_key in self._automation_watchlist_refresh_inflight
                ):
                    return self._automation_watchlist_already_run(
                        now_kst,
                        context,
                    )
                self._automation_watchlist_refresh_inflight.add(refresh_key)
        try:
            result = self._execute_automation_watchlist_refresh(
                now_kst,
                context=context,
            )
            outcome = str(
                result.get('result') or result.get('status') or ''
            ).lower()
            if not force and outcome in {'success', 'degraded'}:
                with self._automation_watchlist_refresh_lock:
                    self._automation_watchlist_refresh_slots.add(refresh_key)
            return result
        finally:
            if not force:
                with self._automation_watchlist_refresh_lock:
                    self._automation_watchlist_refresh_inflight.discard(refresh_key)

    def _run_automation_watchlist_refresh_scheduled_once(
        self,
        analysis_slot: str | datetime | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        # Preserve the old private callback shape where now was the only
        # positional argument.
        if isinstance(analysis_slot, datetime) and now is None:
            now = analysis_slot
            analysis_slot = None
        return self.run_automation_watchlist_refresh_once(
            now=now,
            analysis_slot=(
                str(analysis_slot) if analysis_slot is not None else None
            ),
        )

    def _run_automation_watchlist_maintenance_once(
        self,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        '''Compatibility name for the same canonical maintenance job.'''
        return self._run_automation_watchlist_refresh_scheduled_once(now=now)

    def _resolve_watchlist_refresh_context(
        self,
        schedule: dict[str, Any] | None,
        now_kst: datetime,
        *,
        analysis_slot: str | None,
    ) -> dict[str, Any] | None:
        contexts = self._derived_watchlist_refresh_slots(
            schedule,
            now_kst,
            include_next_day=True,
        )
        if analysis_slot is not None:
            normalized_slot = self._profile_scheduler_slot(analysis_slot)
            return next(
                (
                    context
                    for context in contexts
                    if context['analysis_slot'] == normalized_slot
                ),
                None,
            )
        return next(
            (
                context
                for context in contexts
                if context['refresh_at'] <= now_kst < context['analysis_at']
            ),
            None,
        )

    @staticmethod
    def _automation_watchlist_metadata(
        now_kst: datetime,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not context:
            return {
                'scheduler': 'AutomationSchedulerService',
                'job_type': 'maintenance',
                'refresh_at': now_kst.isoformat(),
            }
        return {
            'scheduler': 'AutomationSchedulerService',
            'job_id': AutomationSchedulerService._automation_watchlist_job_id(
                context['refresh_slot']
            ),
            'job_type': 'maintenance',
            'slot': context['refresh_slot'],
            'analysis_slot': context['analysis_slot'],
            'scheduled_refresh_at': context['refresh_at'].isoformat(),
            'refresh_at': now_kst.isoformat(),
            'scheduler_authority': 'AutomationSchedulerService',
            'trading': False,
            'order_submission': False,
        }

    def _automation_watchlist_already_run(
        self,
        now_kst: datetime,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        result = {
            **self._automation_watchlist_metadata(now_kst, context),
            'status': 'skipped',
            'result': 'skipped',
            'reason': 'automation_watchlist_refresh_already_run',
            'updated': False,
            'real_order_submitted': False,
            'broker_submit_called': False,
            'manual_submit_called': False,
        }
        return result

    def _execute_automation_watchlist_refresh(
        self,
        now_kst: datetime,
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            authority = AutomationExecutionAuthorityService(
                self.runtime_settings
            ).snapshot(db)
            runtime = self.runtime_settings.get_settings_read_only(db)
            schedule = self.automation_profiles.selected_profile_schedule(
                db,
                now=now_kst,
            )
            if not schedule:
                return self._automation_watchlist_skip(
                    now_kst,
                    'no_active_profile',
                    context=context,
                )
            profile = schedule.get('profile') or {}
            if (
                str(profile.get('provider') or '').lower() != 'kis'
                or str(profile.get('market') or '').upper() != 'KR'
            ):
                return self._automation_watchlist_skip(
                    now_kst,
                    'automation_not_active',
                    context=context,
                )
            if not authority.get('scheduler_allowed'):
                return self._automation_watchlist_skip(
                    now_kst,
                    'automation_not_active',
                    context=context,
                )
            if not runtime.get('automation_profile_scheduler_enabled'):
                return self._automation_watchlist_skip(
                    now_kst,
                    'automation_not_active',
                    context=context,
                )
            if schedule.get('status') != 'active':
                reason = (
                    'profile_outside_operation_window'
                    if schedule.get('status') in {'scheduled', 'ended'}
                    else 'automation_not_active'
                )
                return self._automation_watchlist_skip(
                    now_kst,
                    reason,
                    context=context,
                )

            updater = self._automation_watchlist_updater(db)
            result = updater.update_automation_watchlist(
                profile,
                now=now_kst,
            )
            result = {
                **result,
                **self._automation_watchlist_metadata(now_kst, context),
            }
            self._record_automation_watchlist_status(result)
            return result
        except Exception as exc:
            return self._automation_watchlist_failure(
                now_kst,
                self._automation_watchlist_failure_reason(exc),
                exc,
                context=context,
            )
        finally:
            db.close()
    def _automation_watchlist_updater(self, db):
        if self.automation_watchlist_update_service is None:
            settings_obj = get_settings()
            client = KisClient(settings_obj, KisAuthManager(settings_obj, db))
            self.automation_watchlist_update_service = KisWatchlistUpdateService(
                client,
                profile_service=MarketProfileService(),
            )
        return self.automation_watchlist_update_service

    def _automation_watchlist_skip(
        self,
        now_kst: datetime,
        reason: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = {
            **self._automation_watchlist_metadata(now_kst, context),
            'status': 'skipped',
            'result': 'skipped',
            'reason': reason,
            'updated': False,
            'real_order_submitted': False,
            'broker_submit_called': False,
            'manual_submit_called': False,
        }
        self._record_automation_watchlist_status(result)
        return result

    def _automation_watchlist_failure(
        self,
        now_kst: datetime,
        reason: str,
        exc: Exception,
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = {
            **self._automation_watchlist_metadata(now_kst, context),
            'status': 'failed',
            'result': 'failed',
            'reason': reason,
            'error': f'{exc.__class__.__name__}: {exc}',
            'updated': False,
            'real_order_submitted': False,
            'broker_submit_called': False,
            'manual_submit_called': False,
        }
        self._record_automation_watchlist_status(result)
        return result
    @staticmethod
    def _automation_watchlist_failure_reason(exc: Exception) -> str:
        message = str(exc).lower()
        if 'source universe' in message:
            return 'source_universe_load_failed'
        if 'profile' in message and 'budget' in message:
            return 'invalid_profile_budget'
        if 'file update' in message or 'watchlist refresh file' in message:
            return 'watchlist_file_write_failed'
        if 'zero usable' in message:
            return 'zero_usable_symbols'
        return 'automation_watchlist_refresh_failed'

    def _record_automation_watchlist_status(
        self,
        result: dict[str, Any],
    ) -> None:
        field_names = (
            'refresh_at',
            'slot',
            'analysis_slot',
            'source_universe_file',
            'source_universe_count',
            'source_kospi_count',
            'source_kosdaq_count',
            'configured_max_price_krw',
            'budget_max_price_krw',
            'effective_max_price_krw',
            'price_lookup_success_count',
            'price_lookup_failure_count',
            'eligible_kospi_count',
            'eligible_kosdaq_count',
            'selected_kospi_count',
            'selected_kosdaq_count',
            'final_watchlist_count',
            'max_price_in_final_watchlist',
            'over_budget_price_count',
            'watchlist_file',
            'backup_file',
        )
        for field_name in field_names:
            if field_name in result:
                target_name = {
                    'refresh_at': 'last_watchlist_refresh_at',
                    'slot': 'last_watchlist_refresh_slot',
                    'analysis_slot': 'last_watchlist_refresh_analysis_slot',
                }.get(field_name, field_name)
                self._automation_watchlist_status[target_name] = result[field_name]
        self._automation_watchlist_status['last_watchlist_refresh_result'] = (
            result.get('result') or result.get('status')
        )
        self._automation_watchlist_status['last_watchlist_refresh_reason'] = (
            result.get('reason')
        )

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

    def _profile_guarded_live_auto_exit_service(self, db):
        if self.profile_aware_guarded_live_auto_exit_service is not None:
            return self.profile_aware_guarded_live_auto_exit_service
        profile_buy = self._profile_buy_scheduler_service(db)
        client = getattr(profile_buy, 'client', None)
        self.profile_aware_guarded_live_auto_exit_service = (
            ProfileAwareGuardedLiveAutoExitService(
                client=client,
                broker=getattr(profile_buy, 'broker', None),
                validation_service=getattr(profile_buy, 'validation_service', None),
                order_sync_service=getattr(profile_buy, 'order_sync_service', None),
                runtime_settings=self.runtime_settings,
                strategy_profiles=self.automation_profiles,
                positions_loader=getattr(profile_buy, 'positions_loader', None),
                open_orders_loader=getattr(profile_buy, 'open_orders_loader', None),
                execution_core=getattr(profile_buy, 'execution_core', None),
            )
        )
        return self.profile_aware_guarded_live_auto_exit_service

    def _manage_portfolio_first(self, db, *, slot: str, now: datetime) -> dict[str, Any] | None:
        service = self._profile_buy_scheduler_service(db)
        lifecycle = getattr(service, "lifecycle_service", None)
        if lifecycle is not None and db.query(PositionLifecycle).filter(
            PositionLifecycle.status.in_(["open", "closing"])
        ).count():
            result = lifecycle.run_management_once(
                db,
                execute=False,
                trigger_source="automation_scheduler",
                scheduler_slot=slot,
                now=now,
            )
        else:
            result = {
                'managed_count': 0,
                'items': [],
                'reason': 'no_open_lifecycle',
            }
        positions_loader = getattr(service, 'positions_loader', None)
        try:
            positions = positions_loader(db) if callable(positions_loader) else service.client.list_positions()
        except Exception:
            positions = []
        held_positions = [
            item
            for item in (positions if isinstance(positions, list) else [])
            if isinstance(item, dict)
            and float(item.get('qty') or item.get('quantity') or item.get('hold_qty') or 0) > 0
        ]
        return {
            **(result or {}),
            'broker_positions': held_positions,
            'broker_held_count': len(held_positions),
        }

    @staticmethod
    def _critical_exit(result: dict[str, Any] | None) -> bool:
        return any(
            str(item.get("action") or "").upper() in CRITICAL_EXIT_ACTIONS
            for item in (result or {}).get("items", [])
            if isinstance(item, dict)
        )
