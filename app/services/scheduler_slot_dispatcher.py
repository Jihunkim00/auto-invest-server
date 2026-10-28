from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.db.models import AutomationSchedulerSlot
from app.services.scheduler_task_supervisor import (
    ACCOUNT_SLOT_BUY_WINDOW_SECONDS, ACCOUNT_SLOT_TASK_TIMEOUT_SECONDS,
    SchedulerTaskExpired,
)

logger = logging.getLogger(__name__)


def utc_naive(value):
    return value.astimezone(UTC).replace(tzinfo=None)


class SchedulerSlotDispatcher:
    def __init__(self, session_factory, supervisor, now_provider):
        self.sessions = session_factory
        self.supervisor = supervisor
        self.now = now_provider
        self.last_successful_slot = None
        self.last_failed_slot = None
        self.missed_count = 0

    def expire_overdue(self, now):
        """Also close slots from previous days or profiles no longer selected."""
        current = utc_naive(now)
        with self.sessions() as db:
            db.execute(update(AutomationSchedulerSlot).where(
                AutomationSchedulerSlot.status == 'pending',
                AutomationSchedulerSlot.scheduled_at <= current - timedelta(minutes=1),
            ).values(status='missed', reason='slot_window_elapsed_no_catchup', finished_at=current))
            db.execute(update(AutomationSchedulerSlot).where(
                AutomationSchedulerSlot.status.in_(['running', 'retry_pending']),
                AutomationSchedulerSlot.started_at <= current - timedelta(seconds=ACCOUNT_SLOT_TASK_TIMEOUT_SECONDS),
            ).values(status='failed', reason='scheduler_task_timeout', finished_at=current))
            db.commit()

    def reconcile(self, *, account, provider, profile_id, slots, now, callback):
        """Register the whole day, expire missed slots, atomically claim only due ones."""
        for scheduled in slots:
            slot = scheduled.strftime('%H:%M')
            key = f'{account}:{provider}:{scheduled.date().isoformat()}:{slot}'
            current = utc_naive(now)
            nominal = utc_naive(scheduled)
            with self.sessions() as db:
                row = db.query(AutomationSchedulerSlot).filter_by(slot_key=key).first()
                if row is None:
                    row = AutomationSchedulerSlot(slot_key=key, account_key=account, provider=provider,
                        profile_id=profile_id, scheduled_at=nominal, status='pending')
                    db.add(row)
                    try:
                        db.commit()
                    except IntegrityError:
                        db.rollback()
                        row = db.query(AutomationSchedulerSlot).filter_by(slot_key=key).one()
                row_id = row.id
                if row.status in {'running', 'retry_pending'} and row.started_at and current - row.started_at >= timedelta(seconds=ACCOUNT_SLOT_TASK_TIMEOUT_SECONDS):
                    self._finish(row_id, 'failed', 'scheduler_task_timeout', now, expected=row.status)
                    continue
                if row.status != 'pending' or current < nominal:
                    continue
                if current >= nominal + timedelta(minutes=1):
                    self._finish(row_id, 'missed', 'slot_window_elapsed_no_catchup', now, expected='pending')
                    continue
                claimed = db.execute(update(AutomationSchedulerSlot).where(
                    AutomationSchedulerSlot.id == row_id, AutomationSchedulerSlot.status == 'pending'
                ).values(status='running', started_at=current))
                db.commit()
                if claimed.rowcount != 1:
                    continue
                logger.info('scheduler_slot_started slot_key=%s scheduled_at=%s', key, scheduled.isoformat())

            def execute(row_id=row_id, slot=slot, scheduled=scheduled):
                started = self.now()
                if started >= scheduled + timedelta(minutes=1) or started < scheduled:
                    self._finish(row_id, 'missed', 'slot_window_elapsed_before_worker_start', started)
                    return
                try:
                    result = callback(slot, started)
                    if self.now() - started >= timedelta(seconds=ACCOUNT_SLOT_TASK_TIMEOUT_SECONDS):
                        raise SchedulerTaskExpired('scheduler_task_timeout')
                    status, reason = self._outcome(result)
                    self._finish(row_id, status, reason, self.now(), result=result)
                except Exception as exc:
                    self._finish(row_id, 'failed', str(exc) if isinstance(exc, SchedulerTaskExpired)
                                 else f'scheduler_slot_failed:{type(exc).__name__}', self.now())
                    raise

            if not self.supervisor.launch(f'account-{account}', execute, timeout=ACCOUNT_SLOT_TASK_TIMEOUT_SECONDS, critical=True,
                buy_timeout=max(0, (scheduled + timedelta(seconds=ACCOUNT_SLOT_BUY_WINDOW_SECONDS) - self.now()).total_seconds()),
                buy_expires_at=scheduled + timedelta(seconds=ACCOUNT_SLOT_BUY_WINDOW_SECONDS)):
                self._finish(row_id, 'blocked', 'account_worker_busy_or_capacity_reached', now)

    def _finish(self, row_id, status, reason, now, *, result=None, expected='running'):
        with self.sessions() as db:
            changed = db.execute(update(AutomationSchedulerSlot).where(
                AutomationSchedulerSlot.id == row_id, AutomationSchedulerSlot.status == expected
            ).values(status=status, reason=reason,
                     finished_at=None if status == 'retry_pending' else utc_naive(now),
                     result_json=json.dumps(result, ensure_ascii=False, default=str) if result else None))
            db.commit()
            if changed.rowcount:
                key = db.get(AutomationSchedulerSlot, row_id).slot_key
                if status in {'completed', 'HOLD'}:
                    self.last_successful_slot = key
                elif status in {'failed', 'blocked', 'missed'}:
                    self.last_failed_slot = key
                logger.info('scheduler_slot_finished slot_key=%s status=%s reason=%s', key, status, reason)

    def summary(self):
        with self.sessions() as db:
            self.missed_count = db.query(AutomationSchedulerSlot).filter_by(status='missed').count()
            latest = db.query(AutomationSchedulerSlot).filter(
                AutomationSchedulerSlot.status.in_(['completed', 'HOLD'])).order_by(
                AutomationSchedulerSlot.finished_at.desc()).first()
            failed = db.query(AutomationSchedulerSlot).filter(
                AutomationSchedulerSlot.status.in_(['failed', 'blocked', 'missed'])).order_by(
                AutomationSchedulerSlot.finished_at.desc()).first()
            recent = db.query(AutomationSchedulerSlot).order_by(
                AutomationSchedulerSlot.scheduled_at.desc(), AutomationSchedulerSlot.id.desc()).limit(30).all()
            return {'scheduler_last_successful_slot': latest.slot_key if latest else None,
                    'scheduler_last_failed_slot': failed.slot_key if failed else None,
                    'scheduler_missed_slot_count': self.missed_count,
                    'scheduler_recent_slots': [
                        {'slot_key': row.slot_key, 'account_key': row.account_key, 'status': row.status,
                         'reason': row.reason, 'scheduled_at': row.scheduled_at.replace(tzinfo=UTC).isoformat()}
                        for row in recent]}

    @staticmethod
    def _outcome(result):
        if not isinstance(result, dict):
            raw = str(getattr(result, 'status', 'skipped')).lower()
            return ('skipped' if raw not in {'failed', 'blocked'} else raw, 'scheduler_gate_skipped')
        items = result.get('items')
        if isinstance(items, list) and items:
            return SchedulerSlotDispatcher._outcome(items[0])
        if result.get('processed') == 0:
            return 'skipped', 'no_eligible_user_for_slot'
        raw = str(result.get('result') or result.get('action') or result.get('status') or '').lower()
        reason = str(result.get('reason') or result.get('primary_block_reason') or raw)[:240]
        if raw == 'retry_pending':
            return 'retry_pending', reason
        if raw in {'error', 'failed'}:
            return 'failed', reason
        if raw in {'blocked', 'rejected'}:
            return 'blocked', reason
        if raw in {'hold', 'resolved_hold', 'no_trade', 'would_hold'}:
            return 'HOLD', reason
        if raw in {'skipped', 'skip'}:
            return 'skipped', reason
        return 'completed', reason
