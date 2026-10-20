"""Bounded, single-flight scheduler lanes and cooperative BUY cancellation.

A timed-out thread keeps its lane until it actually exits. No replacement or
queue is created. Transport read timeouts remain the final bound on HTTP reads;
the cancellation guard prevents a late result from starting a new BUY.
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
_buy_guard = ContextVar('scheduler_buy_guard', default=None)


class SchedulerTaskExpired(RuntimeError):
    pass


def check_scheduler_task_active():
    """Cooperative checkpoint between bounded transport/analysis operations."""
    task = _buy_guard.get()
    if task is not None and (
        task['cancel'].is_set() or time.monotonic() >= task['deadline']
        or task['now_provider']() >= task['started_at'] + timedelta(seconds=task['timeout'])
    ):
        raise SchedulerTaskExpired('scheduler_task_timeout')


def check_scheduler_buy_allowed():
    guard = _buy_guard.get()
    expired_by_clock = bool(guard and guard.get('buy_expires_at') and
                            guard['now_provider']() >= guard['buy_expires_at'])
    if guard is not None and (guard['cancel'].is_set() or expired_by_clock or
                              time.monotonic() >= guard.get('buy_deadline', guard['deadline'])):
        raise SchedulerTaskExpired('scheduler_task_expired_before_buy')


def check_scheduler_watchlist_ready(db, now):
    if _buy_guard.get() is None:
        return
    from app.db.models import WatchlistSnapshotRun
    run = db.query(WatchlistSnapshotRun).filter_by(market='KR').order_by(
        WatchlistSnapshotRun.started_at.desc(), WatchlistSnapshotRun.id.desc()).first()
    if run is None or run.status != 'success' or run.error_count or run.scored_count != run.source_count:
        raise SchedulerTaskExpired('watchlist_snapshot_not_ready')
    completed = run.completed_at
    if completed is None:
        raise SchedulerTaskExpired('watchlist_snapshot_not_ready')
    if completed.tzinfo is None:
        completed = completed.replace(tzinfo=UTC)
    if completed > now or now - completed > timedelta(hours=2) or completed.astimezone(ZoneInfo('Asia/Seoul')).date() != now.astimezone(ZoneInfo('Asia/Seoul')).date():
        raise SchedulerTaskExpired('watchlist_snapshot_stale')


@contextmanager
def scheduler_buy_guard(task):
    token = _buy_guard.set(task)
    try:
        yield
    finally:
        _buy_guard.reset(token)


class SchedulerTaskSupervisor:
    def __init__(self, *, now_provider=None, max_tasks=32):
        self.now = now_provider or (lambda: datetime.now(UTC))
        self.max_tasks = max_tasks
        self.lock = threading.RLock()
        self.tasks = {}
        self.last_error = None
        self.errors = {}
        self.last_progress_at = None
        self.accepting = True

    def launch(self, lane, callback, *, timeout=300, critical=False, buy_timeout=None):
        with self.lock:
            if not self.accepting or lane in self.tasks or len(self.tasks) >= self.max_tasks:
                return False
            task = {'lane': lane, 'started_at': self.now(), 'deadline': time.monotonic() + timeout,
                    'timeout': timeout, 'cancel': threading.Event(), 'critical': critical,
                    'now_provider': self.now}
            if buy_timeout is not None:
                task['buy_deadline'] = time.monotonic() + buy_timeout
                task['buy_expires_at'] = task['started_at'] + timedelta(seconds=buy_timeout)
                task['now_provider'] = self.now
            self.tasks[lane] = task

        def run():
            try:
                with scheduler_buy_guard(task):
                    callback()
                with self.lock:
                    self.last_progress_at = self.now()
                    self.errors.pop(lane, None)
                    self.last_error = next(reversed(self.errors.values()), None)
            except Exception as exc:
                with self.lock:
                    self.last_error = f'{lane}:{type(exc).__name__}'
                    self.errors[lane] = self.last_error
                logger.exception('scheduler_task_failed lane=%s error_type=%s', lane, type(exc).__name__)
            finally:
                with self.lock:
                    self.tasks.pop(lane, None)

        thread = threading.Thread(target=run, daemon=True, name=f'automation-{lane}')
        task['thread'] = thread
        try:
            thread.start()
        except Exception:
            with self.lock:
                self.tasks.pop(lane, None)
            raise
        return True

    def snapshot(self, now=None):
        current = now or self.now()
        with self.lock:
            result = []
            for task in self.tasks.values():
                age = max(0.0, (current - task['started_at']).total_seconds())
                expired = age >= task['timeout'] or time.monotonic() >= task['deadline']
                if expired:
                    task['cancel'].set()
                    if not task.get('timeout_reported'):
                        logger.error('scheduler_task_timeout lane=%s duration_ms=%.2f replacement_blocked=true',
                                     task['lane'], age * 1000)
                        task['timeout_reported'] = True
                result.append({'lane': task['lane'], 'started_at': task['started_at'].isoformat(),
                               'duration_ms': round(age * 1000, 2), 'expired': expired,
                               'critical': task['critical']})
            return result

    def cancel_all(self):
        with self.lock:
            self.accepting = False
            for task in self.tasks.values():
                task['cancel'].set()

    def resume(self):
        with self.lock:
            self.accepting = True
