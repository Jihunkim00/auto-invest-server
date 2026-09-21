from __future__ import annotations

"""The only production scheduler for Custom Profile automation.

Historical scheduler services remain callable through their compatibility
routes, but are intentionally never started by the application.
"""

import logging
import math
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.brokers.base import KisApiError
from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import SessionLocal
from app.db.models import PositionLifecycle
from app.schemas.strategy_dry_run_auto_buy import ProfileAwareDryRunAutoBuyRequest
from app.services.automation_profile_watchlist_service import AutomationProfileWatchlistService
from app.services.account_snapshot_retry import (
    MAX_ATTEMPTS as ACCOUNT_SNAPSHOT_RETRY_MAX_ATTEMPTS,
    RETRY_DELAY_SECONDS as ACCOUNT_SNAPSHOT_RETRY_DELAY_SECONDS,
    AccountSnapshotReadError,
    account_snapshot_failure_diagnostics,
    account_snapshot_retry_coordinator,
    retryable_kis_account_snapshot_error,
)
from app.services.kis_account_state_cache_service import KisAccountStateCacheService
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

from app.services.market_session_service import MarketSessionService
from app.services.market_profile_service import MarketProfileService
from app.services.kis_position_lifecycle_service import KisPositionLifecycleService
from app.services.profile_aware_guarded_live_auto_exit_service import (
    ProfileAwareGuardedLiveAutoExitService,
)
from app.services.scheduler_service import SchedulerService
from app.services.quant_ab_outcome_label_service import QuantABOutcomeLabelService
from app.services.user_auto_trading_scheduler_service import UserAutoTradingSchedulerService
from app.services.user_watchlist_analysis_scheduler_service import (
    UserWatchlistAnalysisSchedulerService,
)


KST = ZoneInfo("Asia/Seoul")
POSITION_EXIT_POSITION_CACHE_SECONDS = 300
POSITION_EXIT_FRESH_READ_SECONDS = 5
CRITICAL_EXIT_ACTIONS = {"SELL_READY", "STOP_LOSS", "TAKE_PROFIT", "EXIT_SIGNAL"}
logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        *,
        retry_scheduler=None,
        retry_service_factory=None,
        retry_now_provider=None,
    ):
        super().__init__()
        self.retry_scheduler = retry_scheduler or account_snapshot_retry_coordinator.schedule
        self.retry_service_factory = retry_service_factory
        self.retry_now_provider = retry_now_provider or (lambda: datetime.now(KST))
        self.profile_aware_dry_run_auto_buy_service = None
        self.profile_aware_guarded_live_auto_exit_service = None
        self._canonical_slot_lock = threading.Lock()
        self._monitoring_due_at: datetime | None = None
        self._position_exit_monitor_due_at: datetime | None = None
        self._position_exit_positions_lock = threading.Lock()
        self._position_exit_positions_cached_at: datetime | None = None
        self._position_exit_positions_cache: list[dict[str, Any]] | None = None
        self._last_position_exit_monitor_run_at: datetime | None = None
        self._last_position_exit_monitor_result: str | None = None
        self._position_exit_monitor_active = False
        self._position_exit_monitor_state = "unknown"
        self._held_position_count: int | None = None
        self._position_state_known = False
        self._position_exit_monitor_reason: str | None = None
        self._last_monitoring_run_at: datetime | None = None
        self._last_monitoring_result: str | None = None
        self._last_automatic_sync_at: datetime | None = None
        self._automatic_sync_due_at: datetime | None = None
        self._outcome_labeling_due_at: datetime | None = None
        self._outcome_labeling_lock = threading.Lock()
        self._outcome_labeling_inflight = False
        self._last_outcome_labeling_at: datetime | None = None
        self._last_outcome_labeling_result: str | None = None
        self.automation_watchlist_update_service = None
        self.user_auto_trading_scheduler_service = UserAutoTradingSchedulerService(
            automation_profiles=self.automation_profiles,
        )
        self.user_watchlist_analysis_scheduler_service = (
            UserWatchlistAnalysisSchedulerService()
        )
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

    def user_auto_trading_jobs(
        self,
        *,
        now: datetime | None = None,
    ) -> list[dict[str, object]]:
        db = SessionLocal()
        try:
            return self.user_auto_trading_scheduler_service.dispatcher_jobs(
                db,
                now=now,
            )
        finally:
            db.close()

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
        user_jobs = self.user_auto_trading_jobs(now=now)
        watchlist_analysis_jobs = (
            self.user_watchlist_analysis_scheduler_service.dispatcher_jobs(now=now)
        )
        status.update({
            'account_snapshot_retry': {
                'max_attempts': ACCOUNT_SNAPSHOT_RETRY_MAX_ATTEMPTS,
                'retry_delay_seconds': ACCOUNT_SNAPSHOT_RETRY_DELAY_SECONDS,
                'pending_count': account_snapshot_retry_coordinator.pending_count(),
                'admin_pending_count': account_snapshot_retry_coordinator.pending_count('admin'),
                'user_pending_count': account_snapshot_retry_coordinator.pending_count('user'),
            },
            'user_auto_trading_jobs': user_jobs,
            'user_auto_trading_job_count': len(user_jobs),
            'user_watchlist_analysis_jobs': watchlist_analysis_jobs,
            'user_watchlist_analysis_job_count': len(watchlist_analysis_jobs),
        })
        now_kst = self._as_kst(now)
        maintenance = self.maintenance_jobs(now=now_kst)
        status.update(self._automation_watchlist_status)
        status.update(
            {
                'maintenance_jobs': maintenance,
                'maintenance_job_count': len(maintenance),
                'next_watchlist_refresh_at': self._next_watchlist_refresh_at(now_kst),
                'last_monitoring_run_at': self._last_monitoring_run_at.isoformat() if self._last_monitoring_run_at else None,
                'last_monitoring_result': self._last_monitoring_result,
                'monitoring_due_at': self._monitoring_due_at.isoformat() if self._monitoring_due_at else None,
                'position_exit_monitor_interval_minutes': 30,
                'position_exit_monitor_poll_seconds': 20,
                'position_exit_interval_minutes': 30,
                'poll_interval_seconds': 20,
                'position_exit_monitor_active': self._position_exit_monitor_active,
                'position_exit_monitor_state': self._position_exit_monitor_state,
                'held_position_count': self._held_position_count,
                'position_state_known': self._position_state_known,
                'position_exit_monitor_reason': self._position_exit_monitor_reason,
                'position_exit_monitor_due_at': self._position_exit_monitor_due_at.isoformat() if self._position_exit_monitor_due_at else None,
                'last_position_exit_monitor_run_at': self._last_position_exit_monitor_run_at.isoformat() if self._last_position_exit_monitor_run_at else None,
                'last_position_exit_monitor_result': self._last_position_exit_monitor_result,
                'last_automatic_sync_at': self._last_automatic_sync_at.isoformat() if self._last_automatic_sync_at else None,
                'automatic_sync_due_at': self._automatic_sync_due_at.isoformat() if self._automatic_sync_due_at else None,
                'automatic_order_sync_enabled': True,
                'quant_ab_auto_labeling_enabled': bool(getattr(get_settings(), 'quant_ab_auto_labeling_enabled', False)),
                'last_quant_ab_labeling_at': self._last_outcome_labeling_at.isoformat() if self._last_outcome_labeling_at else None,
                'last_quant_ab_labeling_result': self._last_outcome_labeling_result,
                'quant_ab_labeling_due_at': self._outcome_labeling_due_at.isoformat() if self._outcome_labeling_due_at else None,
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
            ny_day_key = now_kst.astimezone(ZoneInfo('America/New_York')).date().isoformat()
            self._slot_runs = {
                key for key in self._slot_runs
                if key.startswith(f'{day_key}:KR:') or key.startswith(f'{ny_day_key}:US:')
            }
            self._automation_watchlist_refresh_slots = {
                value
                for value in self._automation_watchlist_refresh_slots
                if value.startswith(f'{day_key}:')
            }
            schedule = self._selected_profile_schedule(now_kst)
            if self._automatic_sync_due_at is None or now_kst >= self._automatic_sync_due_at:
                self._automatic_sync_due_at = now_kst + timedelta(seconds=20)
                self._safe_call(self._run_automatic_order_sync_once, now_kst)
            if self._monitoring_due_at is None or now_kst >= self._monitoring_due_at:
                interval = self._monitoring_interval_seconds(schedule)
                self._monitoring_due_at = now_kst + timedelta(seconds=interval)
                self._safe_call(self._run_automation_monitoring_tick, now_kst)
            if (
                self._position_exit_monitor_due_at is None
                or now_kst >= self._position_exit_monitor_due_at
            ):
                self._position_exit_monitor_due_at = now_kst + timedelta(seconds=20)
                self._safe_call(self._run_position_exit_monitor_once, now_kst)
            if self._outcome_labeling_due_at is None or now_kst >= self._outcome_labeling_due_at:
                self._outcome_labeling_due_at = now_kst + timedelta(minutes=1)
                self._safe_call(self._schedule_quant_ab_labeling, now_kst)
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
            dispatcher_db = SessionLocal()
            try:
                for provider in ('kis', 'alpaca'):
                    for slot, _scheduled_at in self.user_auto_trading_scheduler_service.due_slots(
                        dispatcher_db,
                        provider=provider,
                        now=now_kst,
                    ):
                        provider_date = now_kst.astimezone(
                            ZoneInfo('Asia/Seoul' if provider == 'kis' else 'America/New_York')
                        ).date().isoformat()
                        dispatch_key = f'{provider_date}:{provider}:user_auto:{slot}'
                        if dispatch_key in self._slot_runs:
                            continue
                        self._slot_runs.add(dispatch_key)
                        self._safe_call(
                            self._run_user_auto_dispatcher,
                            provider,
                            slot,
                            now_kst,
                        )
            finally:
                dispatcher_db.close()
            for slot in self.user_watchlist_analysis_scheduler_service.due_slots(
                now=now_kst,
            ):
                analysis_key = f'{day_key}:KR:user_watchlist_analysis:{slot}'
                if analysis_key in self._slot_runs:
                    continue
                self._slot_runs.add(analysis_key)
                self._safe_call(
                    self._run_user_watchlist_analysis_dispatcher,
                    slot,
                    now_kst,
                )
            self._last_tick_at = datetime.now(UTC)
            time.sleep(20)

    def run_user_auto_once(
        self,
        *,
        provider: str,
        slot: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            return self.user_auto_trading_scheduler_service.run_provider_once(
                db,
                provider=provider,
                scheduler_slot=slot,
                now=now,
            )
        finally:
            db.close()

    def _run_user_auto_dispatcher(
        self,
        provider: str,
        slot: str,
        now: datetime,
    ) -> dict[str, Any]:
        return self.run_user_auto_once(provider=provider, slot=slot, now=now)

    def run_user_watchlist_analysis_once(
        self,
        *,
        slot: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            return self.user_watchlist_analysis_scheduler_service.run_once(
                db,
                scheduler_slot=slot,
                now=now,
            )
        finally:
            db.close()

    def _run_user_watchlist_analysis_dispatcher(
        self,
        slot: str,
        now: datetime,
    ) -> dict[str, Any]:
        return self.run_user_watchlist_analysis_once(slot=slot, now=now)

    def _schedule_quant_ab_labeling(self, now_kst: datetime) -> dict[str, Any]:
        """Start a bounded analytics job without blocking the trading loop."""
        if not bool(getattr(get_settings(), 'quant_ab_auto_labeling_enabled', False)):
            self._last_outcome_labeling_result = 'disabled_by_default'
            return {
                'status': 'disabled',
                'reason': 'quant_ab_auto_labeling_disabled',
                'broker_submit_called': False,
                'real_order_submitted': False,
            }
        with self._outcome_labeling_lock:
            if self._outcome_labeling_inflight:
                return {'status': 'skipped', 'reason': 'quant_ab_labeling_inflight'}
            self._outcome_labeling_inflight = True
        thread = threading.Thread(
            target=self._run_quant_ab_labeling_background,
            args=(now_kst,),
            daemon=True,
            name='quant-ab-outcome-labeler',
        )
        thread.start()
        return {'status': 'started', 'reason': 'quant_ab_labeling_background_started'}

    def _run_quant_ab_labeling_background(self, now_kst: datetime) -> None:
        try:
            self.run_quant_ab_labeling_once(now=now_kst)
        finally:
            with self._outcome_labeling_lock:
                self._outcome_labeling_inflight = False

    def run_quant_ab_labeling_once(
        self,
        *,
        now: datetime | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Run read-only outcome labeling; errors are fail-soft."""
        if not bool(getattr(get_settings(), 'quant_ab_auto_labeling_enabled', False)):
            self._last_outcome_labeling_result = 'disabled_by_default'
            return {
                'status': 'disabled',
                'reason': 'quant_ab_auto_labeling_disabled',
                'safety': {
                    'analytics_only': True,
                    'broker_submit_called': False,
                    'real_order_submitted': False,
                },
            }
        db = SessionLocal()
        try:
            settings = get_settings()
            client = KisClient(settings, KisAuthManager(settings, db))
            result = QuantABOutcomeLabelService(client=client).label_mature_observations(
                db,
                now=now,
                limit=limit,
            )
            self._last_outcome_labeling_at = datetime.now(UTC)
            self._last_outcome_labeling_result = str(result.get('status') or 'ok')
            return result
        except Exception as exc:
            self._last_outcome_labeling_at = datetime.now(UTC)
            self._last_outcome_labeling_result = 'fail_soft_error'
            return {
                'status': 'error',
                'reason': f'quant_ab_labeling_failed:{exc.__class__.__name__}',
                'safety': {
                    'analytics_only': True,
                    'broker_submit_called': False,
                    'real_order_submitted': False,
                },
            }
        finally:
            db.close()

    def _run_automatic_order_sync_once(self, now_kst: datetime | None = None) -> dict[str, Any]:
        db = SessionLocal()
        try:
            service = self._profile_buy_scheduler_service(db)
            sync_service = getattr(service, 'order_sync_service', None)
            if not callable(getattr(sync_service, 'sync_submitted_orders', None)):
                return {'status': 'skipped', 'reason': 'order_sync_unavailable', 'synced_count': 0}
            rows = sync_service.sync_submitted_orders(db, limit=20)
            self._last_automatic_sync_at = datetime.now(UTC)
            return {
                'status': 'ok',
                'reason': 'bounded_submitted_order_reconciliation',
                'synced_count': len(rows),
            }
        except Exception as exc:
            self._last_automatic_sync_at = datetime.now(UTC)
            return {
                'status': 'error',
                'reason': f'automatic_order_sync_failed:{exc.__class__.__name__}',
                'synced_count': 0,
            }
        finally:
            db.close()


    def _run_automation_monitoring_tick(
        self,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Publish a monitoring heartbeat without any broker side effect."""
        db = SessionLocal()
        now_kst = self._as_kst(now)
        self._last_monitoring_run_at = datetime.now(UTC)
        try:
            authority = AutomationExecutionAuthorityService(
                self.runtime_settings
            ).snapshot(db)
            runtime = self.runtime_settings.get_settings_read_only(db)
            schedule = self.automation_profiles.selected_profile_schedule(
                db,
                now=now_kst,
            )
            session = MarketSessionService().get_session_status('KR')
            if not schedule or schedule.get('status') != 'active':
                status = 'skipped'
                reason = 'active_profile_unavailable'
            elif not authority.get('scheduler_allowed'):
                status = 'blocked'
                reason = 'automation_mode_off'
            elif not runtime.get('automation_profile_scheduler_enabled'):
                status = 'blocked'
                reason = 'automation_disabled'
            elif not session.get('is_market_open'):
                status = 'skipped'
                reason = 'market_session_closed'
            else:
                status = 'evaluated'
                reason = 'monitoring_heartbeat_only'
            self._last_monitoring_result = status
            return {
                'scheduler': self.__class__.__name__,
                'trigger_source': CANONICAL_TRIGGER_SOURCE,
                'status': status,
                'reason': reason,
                'market_session': session,
                'buy_execution_allowed': False,
                'broker_submit_called': False,
                'manual_submit_called': False,
                'real_order_submitted': False,
            }
        finally:
            db.close()

    def _monitoring_interval_seconds(self, schedule: dict[str, Any] | None) -> int:
        settings = ((schedule or {}).get('profile') or {}).get('effective_settings') or {}
        monitoring = settings.get('monitoring') if isinstance(settings, dict) else {}
        try:
            return max(30, int((monitoring or {}).get('interval_seconds') or 60))
        except (TypeError, ValueError):
            return 60

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
        *,
        retry_attempt: int = 1,
        retry_started_at: datetime | None = None,
        expected_profile_key: str | None = None,
        expected_profile_id: int | None = None,
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
            profile = (schedule.get('profile') or {})
            profile_key = str(schedule.get('profile_key') or profile.get('profile_key') or '')
            profile_id = _safe_int(profile.get('id'))
            configured_slots = {
                self._profile_scheduler_slot(str(value))
                for value in (schedule.get('analysis_times') or [])
            }
            retry_slot_expired = (
                retry_started_at is not None
                and self._as_kst(retry_started_at).date() != now_kst.date()
            )
            if (
                expected_profile_key is not None
                and (
                    profile_key != expected_profile_key
                    or (expected_profile_id is not None and profile_id != expected_profile_id)
                    or slot not in configured_slots
                    or retry_slot_expired
                )
            ):
                return {
                    'scheduler': self.__class__.__name__,
                    'status': 'skipped',
                    'result': 'SKIPPED',
                    'reason': 'automation_profile_changed_before_account_snapshot_retry',
                    'slot': slot,
                    'real_order_submitted': False,
                    'broker_submit_called': False,
                }

            market_session = MarketSessionService().get_session_status(
                'KR',
                now=now_kst,
            )
            if market_session.get('is_market_open') is not True:
                return {
                    'scheduler': self.__class__.__name__,
                    'status': 'skipped',
                    'result': 'SKIPPED',
                    'reason': 'market_session_closed',
                    'profile_key': profile_key,
                    'slot': slot,
                    'submission_eligible': False,
                    'real_order_submitted': False,
                    'broker_submit_called': False,
                }

            try:
                account_snapshot = self._account_snapshot_preflight(db)
            except AccountSnapshotReadError as exc:
                return self._account_snapshot_retry_result(
                    slot=slot,
                    now_kst=now_kst,
                    profile_key=profile_key,
                    profile_id=profile_id,
                    error=exc,
                    attempt=retry_attempt,
                    retry_started_at=retry_started_at or now_kst,
                )

            portfolio = self._manage_portfolio_first(
                db,
                slot=slot,
                now=now_kst,
                account_snapshot=account_snapshot,
            )
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

            entry_settings = effective_profile.get('entry') or {}
            cutoff = str(entry_settings.get('no_new_entry_after') or '').strip()
            cutoff_reached = bool(
                len(cutoff) == 5
                and cutoff[2] == ':'
                and now_kst.strftime('%H:%M') >= cutoff
            )
            if (
                market_session.get('is_entry_allowed_now') is not True
                or cutoff_reached
            ):
                return {
                    'scheduler': self.__class__.__name__,
                    'status': 'blocked',
                    'mode': str(authority.get('automation_mode') or 'test'),
                    'execution_mode': str(authority.get('automation_mode') or 'test'),
                    'profile_key': schedule.get('profile_key'),
                    'slot': slot,
                    'result': 'blocked',
                    'reason': 'entry_window_closed',
                    'risk_decision': {
                        'approved': False,
                        'reason': 'entry_window_closed',
                        'source': 'market_session_gate',
                    },
                    'submission_eligible': False,
                    'real_order_submitted': False,
                    'broker_submit_called': False,
                    'manual_submit_called': False,
                    'portfolio': portfolio,
                    'dry_run': None,
                    'profile_buy': {
                        'status': 'blocked',
                        'action': 'hold',
                        'reason': 'entry_window_closed',
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
                    account_snapshot_override=account_snapshot,
                    allow_retry_slot_replay=retry_attempt > 1,
                    retry_started_at=retry_started_at,
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
            # Raw market data may be common, but ranked selection is owned by
            # this exact Admin/system profile and never shared with user rows.
            profile_watchlist = AutomationProfileWatchlistService().build(
                db,
                profile=profile,
                owner_user_id=(
                    int(profile.get('owner_user_id'))
                    if profile.get('owner_user_id') is not None
                    else None
                ),
                scheduler_slot=str((context or {}).get('analysis_slot') or 'refresh'),
                now=now_kst,
            )
            result = {
                **result,
                **self._automation_watchlist_metadata(now_kst, context),
                'automation_profile_watchlist_snapshot': profile_watchlist.get('snapshot'),
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
            scheduler_slot=slot,
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

    def _run_position_exit_monitor_once(
        self,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Poll held positions independently and delegate SELLs to guarded execution."""
        now_kst = self._as_kst(now)
        self._last_position_exit_monitor_run_at = datetime.now(UTC)
        monitor_state = "unknown"
        position_state_known = False
        held_position_count: int | None = None
        monitor_reason: str | None = None
        db = SessionLocal()
        try:
            runtime = self.runtime_settings.get_settings_read_only(db)
            authority = AutomationExecutionAuthorityService(
                self.runtime_settings
            ).snapshot(db)
            if not runtime.get("scheduler_enabled"):
                result = {"status": "blocked", "reason": "scheduler_disabled", "items": []}
            elif not authority.get("scheduler_allowed"):
                result = {"status": "blocked", "reason": "automation_mode_off", "items": []}
            else:
                settings_obj = get_settings()
                kis_client = KisClient(settings_obj, KisAuthManager(settings_obj, db))
                try:
                    broker_positions = self._load_position_exit_positions(
                        kis_client,
                        now=now_kst,
                        force_refresh=True,
                    )
                    held_position_count = _position_exit_held_position_count(
                        broker_positions
                    )
                except Exception as exc:
                    monitor_reason = "broker_position_snapshot_unavailable"
                    result = {
                        "status": "skipped",
                        "reason": monitor_reason,
                        "snapshot_error": exc.__class__.__name__,
                        "items": [],
                    }
                else:
                    position_state_known = True
                    if held_position_count == 0:
                        monitor_state = "idle"
                        monitor_reason = "no_position"
                        result = {
                            "status": "skipped",
                            "reason": monitor_reason,
                            "items": [],
                        }
                    else:
                        monitor_state = "active"
                        lifecycle = KisPositionLifecycleService(
                            kis_client,
                            runtime_settings=self.runtime_settings,
                            automation_profiles=self.automation_profiles,
                            position_snapshot_loader=(
                                lambda *, force_refresh=False: self._load_position_exit_positions(
                                    kis_client,
                                    now=now_kst,
                                    force_refresh=force_refresh,
                                )
                            ),
                        )
                        slot = f"position_exit_{now_kst.strftime('%Y%m%d_%H%M')}"
                        try:
                            result = lifecycle.run_due_management_once(
                                db,
                                trigger_source="position_exit_monitor",
                                scheduler_slot=slot,
                                now=now_kst,
                            )
                        except Exception as exc:
                            result = {
                                "status": "failed",
                                "reason": "position_exit_monitor_failed",
                                "error": exc.__class__.__name__,
                                "items": [],
                            }
                        else:
                            result = self._route_position_exit_monitor_sells(
                                db,
                                lifecycle=lifecycle,
                                result=result,
                                scheduler_slot=slot,
                                now=now_kst,
                                dry_run=bool(runtime.get("dry_run", True)),
                            )
                        if not isinstance(result, dict):
                            result = {
                                "status": "failed",
                                "reason": "position_exit_monitor_failed",
                                "items": [],
                            }
                        result["automation_mode"] = authority.get("automation_mode")
            result["position_exit_monitor_interval_minutes"] = 30
            result["poll_interval_seconds"] = 20
            result["position_exit_interval_minutes"] = 30
            result["position_exit_monitor_active"] = monitor_state == "active"
            result["position_exit_monitor_state"] = monitor_state
            result["held_position_count"] = held_position_count
            result["position_state_known"] = position_state_known
            result["sell_only"] = True
            result["monitor_independent_of_buy_scheduler"] = True
            result.setdefault("monitor_execution_mode", "guarded_live_exit")
            result["real_order_submitted"] = bool(
                result.get("real_order_submitted")
                or any(
                    item.get("real_order_submitted") is True
                    for item in result.get("items", [])
                    if isinstance(item, dict)
                )
            )
            result["broker_submit_called"] = bool(
                result.get("broker_submit_called")
                or any(
                    item.get("broker_submit_called") is True
                    for item in result.get("items", [])
                    if isinstance(item, dict)
                )
            )
            result.setdefault("buy_execution_allowed", False)
            if monitor_reason is not None:
                result["reason"] = monitor_reason
            self._position_exit_monitor_active = monitor_state == "active"
            self._position_exit_monitor_state = monitor_state
            self._held_position_count = held_position_count
            self._position_state_known = position_state_known
            self._position_exit_monitor_reason = monitor_reason or result.get("reason")
            self._last_position_exit_monitor_result = str(
                result.get("reason") or result.get("status") or "completed"
            )
            return result
        finally:
            db.close()

    def _load_position_exit_positions(
        self,
        kis_client: Any,
        *,
        now: datetime,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Refresh discovery on each poll and reuse only a fresh snapshot for evaluation."""
        now_utc = self._as_kst(now).astimezone(UTC)
        with self._position_exit_positions_lock:
            cached_at = self._position_exit_positions_cached_at
            cached = self._position_exit_positions_cache
            age = (now_utc - cached_at) if cached_at is not None else None
            cache_fresh = (
                age is not None
                and timedelta(0) <= age
                and age.total_seconds() < POSITION_EXIT_POSITION_CACHE_SECONDS
            )
            force_read_fresh = (
                force_refresh
                and (age is None or age < timedelta(0)
                     or age.total_seconds() > POSITION_EXIT_FRESH_READ_SECONDS)
            )
            if cached is not None and cache_fresh and not force_read_fresh:
                return [dict(item) for item in cached]
            result = kis_client.list_positions()
            if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
                raise ValueError("kis_position_snapshot_invalid")
            snapshot = [dict(item) for item in result]
            self._position_exit_positions_cache = snapshot
            self._position_exit_positions_cached_at = now_utc
            return [dict(item) for item in snapshot]

    def _route_position_exit_monitor_sells(
        self,
        db,
        *,
        lifecycle: KisPositionLifecycleService,
        result: dict[str, Any],
        scheduler_slot: str,
        now: datetime,
        dry_run: bool,
    ) -> dict[str, Any]:
        """Delegate due SELL recommendations to the existing guarded exit path."""
        if not isinstance(result, dict):
            return result
        items = result.get("items")
        if not isinstance(items, list):
            return result

        sell_items = [
            item
            for item in items
            if isinstance(item, dict)
            and str(item.get("action") or "").upper() == "SELL"
            and item.get("exit_check_due") is True
            and item.get("status") == "checked"
        ]
        if not sell_items:
            result["real_order_submitted"] = any(
                item.get("real_order_submitted") is True
                for item in items
                if isinstance(item, dict)
            )
            result["broker_submit_called"] = any(
                item.get("broker_submit_called") is True
                for item in items
                if isinstance(item, dict)
            )
            return result

        exit_service = self._profile_guarded_live_auto_exit_service(db)
        for item in sell_items:
            symbol = str(item.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            try:
                exit_result = exit_service.run_scheduler_once(
                    db,
                    scheduler_slot=scheduler_slot,
                    symbol=symbol,
                    now=now,
                )
            except Exception as exc:
                exit_result = {
                    "status": "failed",
                    "action": "blocked",
                    "block_reason": "guarded_live_exit_exception",
                    "reason": exc.__class__.__name__,
                    "submitted": False,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                    "safety": {
                        "real_order_submitted": False,
                        "broker_submit_called": False,
                        "manual_submit_called": False,
                    },
                }

            submitted = bool(
                exit_result.get("submitted") or exit_result.get("real_order_submitted")
            )
            safety = exit_result.get("safety")
            broker_submit_called = bool(
                exit_result.get("broker_submit_called")
                or (safety.get("broker_submit_called") if isinstance(safety, dict) else False)
            )
            if dry_run:
                execution_action = "BLOCKED_DRY_RUN"
            elif submitted:
                execution_action = "SUBMITTED"
            elif broker_submit_called:
                execution_action = "SUBMIT_ATTEMPTED"
            else:
                execution_action = "BLOCKED"
            execution_reason = str(
                exit_result.get("block_reason")
                or exit_result.get("reason")
                or exit_result.get("status")
                or "guarded_exit_not_submitted"
            )
            lifecycle.record_monitor_execution_result(
                db,
                item,
                execution_action=execution_action,
                execution_reason=execution_reason,
                execution_result=exit_result,
            )

        result["guarded_sell_recommendation_count"] = len(sell_items)
        result["real_order_submitted"] = any(
            item.get("real_order_submitted") is True
            for item in items
            if isinstance(item, dict)
        )
        result["broker_submit_called"] = any(
            item.get("broker_submit_called") is True
            for item in items
            if isinstance(item, dict)
        )
        result["manual_submit_called"] = any(
            item.get("manual_submit_called") is True
            for item in items
            if isinstance(item, dict)
        )
        result["guarded_sell_submitted_count"] = sum(
            1
            for item in items
            if isinstance(item, dict) and item.get("real_order_submitted") is True
        )
        return result

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

    def _account_snapshot_preflight(self, db) -> dict[str, Any]:
        service = self._profile_buy_scheduler_service(db)
        client = getattr(service, 'client', None)
        positions_loader = getattr(service, 'positions_loader', None)
        orders_loader = getattr(service, 'open_orders_loader', None)
        balance_loader = getattr(service, 'balance_loader', None)
        try:
            if any(callable(loader) for loader in (positions_loader, orders_loader, balance_loader)):
                positions = (
                    positions_loader(db)
                    if callable(positions_loader)
                    else client.list_positions()
                )
                open_orders = (
                    orders_loader(db)
                    if callable(orders_loader)
                    else client.list_open_orders()
                )
                balance = (
                    balance_loader(db)
                    if callable(balance_loader)
                    else client.get_account_balance()
                )
                if (
                    not isinstance(positions, list)
                    or not all(isinstance(item, dict) for item in positions)
                    or not isinstance(open_orders, list)
                    or not all(isinstance(item, dict) for item in open_orders)
                    or not isinstance(balance, dict)
                ):
                    raise ValueError('kis_account_snapshot_invalid')
                return {
                    'positions': [dict(item) for item in positions],
                    'open_orders': [dict(item) for item in open_orders],
                    'balance': dict(balance),
                    'fetch_success': True,
                    'account_state_live_verified': True,
                    'read_at': datetime.now(UTC).isoformat(),
                }

            state = KisAccountStateCacheService.get_or_create(client).get_account_state(
                read_only=True,
                require_fresh=True,
                max_attempts=1,
            )
            if (
                not isinstance(state, dict)
                or state.get('fetch_success') is not True
                or state.get('account_state_status') != 'available'
                or state.get('account_state_live_verified') is not True
            ):
                details = state.get('error_details') if isinstance(state, dict) else {}
                details = details if isinstance(details, dict) else {}
                cause = KisApiError(
                    'KIS account snapshot unavailable',
                    details={
                        'account_state_retryable': (
                            (
                                state.get('account_state_retryable') is True
                                or state.get('account_state_error_category') == 'invalid_response'
                            )
                            if isinstance(state, dict)
                            else False
                        ),
                        'error_type': (
                            state.get('account_state_error_category')
                            if isinstance(state, dict)
                            else 'unknown'
                        ),
                        'http_status': (
                            state.get('account_state_http_status')
                            if isinstance(state, dict)
                            else None
                        ),
                        'msg_cd': details.get('error_code'),
                    },
                )
                raise AccountSnapshotReadError(
                    cause,
                    diagnostics={
                        'failed_component': (
                            state.get('account_state_failed_component')
                            if isinstance(state, dict)
                            else 'unknown'
                        ),
                        'error_category': (
                            state.get('account_state_error_category')
                            if isinstance(state, dict)
                            else 'unknown'
                        ),
                    },
                )
            return state
        except AccountSnapshotReadError:
            raise
        except Exception as exc:
            raise AccountSnapshotReadError(exc) from exc

    def _account_snapshot_retry_result(
        self,
        *,
        slot: str,
        now_kst: datetime,
        profile_key: str,
        profile_id: int | None,
        error: AccountSnapshotReadError,
        attempt: int,
        retry_started_at: datetime,
    ) -> dict[str, Any]:
        retryable = retryable_kis_account_snapshot_error(error)
        diagnostics = account_snapshot_failure_diagnostics(
            error,
            attempt=attempt,
            retryable=retryable,
        )
        if retryable and attempt < ACCOUNT_SNAPSHOT_RETRY_MAX_ATTEMPTS:
            if attempt == 1:
                accepted = self._schedule_admin_account_snapshot_retry(
                    slot=slot,
                    trading_date=now_kst.date().isoformat(),
                    profile_key=profile_key,
                    profile_id=profile_id,
                    retry_started_at=retry_started_at,
                )
                if not accepted:
                    retryable = False
                    diagnostics['retryable'] = False
            if retryable:
                logger.warning(
                    'kis account snapshot retry scheduled scope=admin provider=kis market=KR profile_id=%s profile_key=%s slot=%s attempt=%s max_attempts=%s retry_in_seconds=%s retryable=true failure_stage=account_snapshot exception_type=%s',
                    profile_id,
                    profile_key,
                    slot,
                    attempt,
                    ACCOUNT_SNAPSHOT_RETRY_MAX_ATTEMPTS,
                    ACCOUNT_SNAPSHOT_RETRY_DELAY_SECONDS,
                    diagnostics['exception_type'],
                )
                return {
                    'scheduler': self.__class__.__name__,
                    'status': 'retry_pending',
                    'result': 'retry_pending',
                    'reason': f'account_snapshot_retry_pending_{attempt}_of_{ACCOUNT_SNAPSHOT_RETRY_MAX_ATTEMPTS}',
                    'profile_id': profile_id,
                    'profile_key': profile_key,
                    'slot': slot,
                    'retry_policy': 'kis_account_snapshot',
                    'attempts': attempt,
                    'max_attempts': ACCOUNT_SNAPSHOT_RETRY_MAX_ATTEMPTS,
                    'retry_delay_seconds': ACCOUNT_SNAPSHOT_RETRY_DELAY_SECONDS,
                    'failure_stage': 'account_snapshot',
                    'real_order_submitted': False,
                    'broker_submit_called': False,
                }
        reason = (
            'account_snapshot_retry_exhausted'
            if attempt >= ACCOUNT_SNAPSHOT_RETRY_MAX_ATTEMPTS and retryable
            else 'account_snapshot_unavailable'
        )
        event_name = (
            'kis account snapshot retry exhausted'
            if retryable and attempt >= ACCOUNT_SNAPSHOT_RETRY_MAX_ATTEMPTS
            else 'kis account snapshot failed without retry'
        )
        logger.error(
            '%s scope=admin provider=kis market=KR profile_id=%s profile_key=%s slot=%s attempts=%s max_attempts=%s retry_delay_seconds=%s retryable=%s failure_stage=account_snapshot final_failure_stage=account_snapshot exception_type=%s',
            event_name,
            profile_id,
            profile_key,
            slot,
            attempt,
            ACCOUNT_SNAPSHOT_RETRY_MAX_ATTEMPTS,
            ACCOUNT_SNAPSHOT_RETRY_DELAY_SECONDS,
            retryable,
            diagnostics['exception_type'],
        )
        return {
            'scheduler': self.__class__.__name__,
            'status': 'failed',
            'result': 'failed',
            'reason': reason,
            'profile_id': profile_id,
            'profile_key': profile_key,
            'slot': slot,
            **diagnostics,
            'real_order_submitted': False,
            'broker_submit_called': False,
        }

    def _schedule_admin_account_snapshot_retry(
        self,
        *,
        slot: str,
        trading_date: str,
        profile_key: str,
        profile_id: int | None,
        retry_started_at: datetime,
    ) -> bool:
        state = {'attempt': 2}

        def retry_callback() -> int | None:
            attempt = int(state['attempt'])
            try:
                retry_service = (
                    self.retry_service_factory()
                    if self.retry_service_factory is not None
                    else self._new_account_snapshot_retry_service()
                )
                retry_now = retry_service.retry_now_provider()
                result = retry_service._run_automation_tick(
                    slot,
                    retry_now,
                    True,
                    retry_attempt=attempt,
                    retry_started_at=retry_started_at,
                    expected_profile_key=profile_key,
                    expected_profile_id=profile_id,
                )
            except Exception as exc:
                logger.error(
                    'kis account snapshot retry worker failed scope=admin provider=kis market=KR profile_id=%s profile_key=%s slot=%s attempt=%s max_attempts=%s exception_type=%s',
                    profile_id,
                    profile_key,
                    slot,
                    attempt,
                    ACCOUNT_SNAPSHOT_RETRY_MAX_ATTEMPTS,
                    type(exc).__name__,
                )
                return None
            if (
                isinstance(result, dict)
                and result.get('status') == 'retry_pending'
                and attempt < ACCOUNT_SNAPSHOT_RETRY_MAX_ATTEMPTS
            ):
                state['attempt'] = attempt + 1
                return ACCOUNT_SNAPSHOT_RETRY_DELAY_SECONDS
            if (
                isinstance(result, dict)
                and result.get('status') != 'failed'
                and result.get('status') != 'skipped'
                and result.get('result') != 'failed'
            ):
                logger.info(
                    'kis account snapshot retry recovered scope=admin provider=kis market=KR profile_id=%s profile_key=%s slot=%s attempt=%s max_attempts=%s',
                    profile_id,
                    profile_key,
                    slot,
                    attempt,
                    ACCOUNT_SNAPSHOT_RETRY_MAX_ATTEMPTS,
                )
            return None

        retry_key = (
            'admin',
            profile_id if profile_id is not None else profile_key,
            trading_date,
            slot,
        )
        return bool(
            self.retry_scheduler(
                retry_key,
                retry_callback,
                delay_seconds=ACCOUNT_SNAPSHOT_RETRY_DELAY_SECONDS,
            )
        )

    def _new_account_snapshot_retry_service(self):
        retry_service = AutomationSchedulerService(
            retry_scheduler=self.retry_scheduler,
            retry_now_provider=self.retry_now_provider,
        )
        retry_service.runtime_settings = self.runtime_settings
        retry_service.automation_profiles = self.automation_profiles
        return retry_service

    def _manage_portfolio_first(
        self,
        db,
        *,
        slot: str,
        now: datetime,
        account_snapshot: dict[str, Any],
    ) -> dict[str, Any] | None:
        service = self._profile_buy_scheduler_service(db)
        positions = account_snapshot.get('positions') or []
        held_positions = [
            item
            for item in (positions if isinstance(positions, list) else [])
            if isinstance(item, dict)
            and float(item.get('qty') or item.get('quantity') or item.get('hold_qty') or 0) > 0
        ]
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

def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _position_exit_held_position_count(positions: Any) -> int:
    if not isinstance(positions, list):
        raise ValueError("kis_position_snapshot_invalid")

    held_count = 0
    for position in positions:
        if not isinstance(position, dict):
            raise ValueError("kis_position_snapshot_invalid")
        symbol = str(
            position.get("symbol") or position.get("pdno") or position.get("code") or ""
        ).strip()
        raw_qty = position.get("qty")
        if raw_qty is None:
            raw_qty = position.get("hldg_qty")
        if not symbol or raw_qty is None:
            raise ValueError("kis_position_snapshot_invalid")
        try:
            quantity = float(str(raw_qty).replace(",", ""))
        except (TypeError, ValueError) as exc:
            raise ValueError("kis_position_snapshot_invalid") from exc
        if not math.isfinite(quantity) or quantity < 0:
            raise ValueError("kis_position_snapshot_invalid")
        if quantity > 0:
            held_count += 1
    return held_count
