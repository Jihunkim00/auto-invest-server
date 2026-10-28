"""Durable single-flight snapshot reads, selective retries and bounded recovery."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import uuid
from datetime import UTC, timedelta

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.db.models import (WatchlistSnapshotRun, WatchlistSnapshotItem,
    WatchlistSnapshotError, WatchlistSnapshotRecovery, WatchlistSnapshotRefreshClaim)
from app.services.scheduler_task_supervisor import check_scheduler_task_active, SchedulerTaskExpired
from app.services.technical_indicator_service import indicator_payload_is_quant_ready
from app.services.watchlist_snapshot_policy import (
    ITEM_RETRY_DELAYS, RECOVERY_RETRY_DELAYS, RUN_TIMEOUT_SECONDS,
    RECOVERY_WINDOW_SECONDS, REUSE_MAX_AGE_SECONDS, INITIAL_MAX_READ_CALLS,
    RECOVERY_MAX_READ_CALLS, CLAIM_LEASE_SECONDS, SnapshotReadStopped,
    SnapshotReadBudget, snapshot_read_budget, safe_snapshot_error,
)

logger = logging.getLogger(__name__)


def naive(value):
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def universe_hash(universe, gate):
    return hashlib.sha256(json.dumps([gate, universe], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class SnapshotRecoveryCoordinator:
    def __init__(self, service, db, cancel_event=None):
        import threading
        self.service, self.db = service, db
        self.cancel = cancel_event or threading.Event()
        self.token = uuid.uuid4().hex
        self.now = lambda: naive(service._now_utc())
        self.monotonic = service.monotonic_provider
        self.run = self.job = None

    def pause(self, seconds):
        cancelled = (self.service.wait_provider(seconds) if self.service.wait_provider
                     else self.cancel.wait(seconds))
        if cancelled or self.cancel.is_set():
            raise SnapshotReadStopped('snapshot_cancelled')

    def checkpoint(self):
        try:
            check_scheduler_task_active()
        except SchedulerTaskExpired:
            raise SnapshotReadStopped('snapshot_cancelled') from None
        if self.cancel.is_set():
            raise SnapshotReadStopped('snapshot_cancelled')
        if self.now() >= self.run_deadline or self.monotonic() >= self.clock_deadline:
            raise SnapshotReadStopped('snapshot_timeout')
        if self.now() >= self.job.deadline_at:
            raise SnapshotReadStopped('snapshot_recovery_deadline')
        claim = self.db.query(WatchlistSnapshotRefreshClaim.token).filter_by(market='KR').scalar()
        if claim != self.token:
            raise SnapshotReadStopped('snapshot_lease_lost')

    def reserve_read(self):
        self.fence()
        column = (WatchlistSnapshotRecovery.recovery_read_calls if self.recovering
                  else WatchlistSnapshotRecovery.initial_read_calls)
        cap = RECOVERY_MAX_READ_CALLS if self.recovering else INITIAL_MAX_READ_CALLS
        changed = self.db.execute(update(WatchlistSnapshotRecovery).where(
            WatchlistSnapshotRecovery.id == self.job.id, column < cap,
            WatchlistSnapshotRecovery.status.in_(['building', 'running']),
        ).values({column: column + 1}))
        self.db.commit()
        if changed.rowcount != 1:
            raise SnapshotReadStopped('snapshot_read_budget_exhausted')

    def fence(self):
        # Take a write lock in the same transaction as the data/status update.
        # A worker whose lease was replaced cannot publish or spend more reads.
        changed = self.db.query(WatchlistSnapshotRefreshClaim).filter_by(
            market='KR', token=self.token).filter(
                WatchlistSnapshotRefreshClaim.expires_at > self.now()).update(
                    {'token': self.token}, synchronize_session=False)
        if changed != 1:
            self.db.rollback()
            raise SnapshotReadStopped('snapshot_lease_lost')

    def acquire(self):
        """The DB mutex is also a fencing token for workers returning late."""
        now = self.now()
        old = self.db.get(WatchlistSnapshotRefreshClaim, 'KR')
        if old and old.expires_at > now:
            return False
        if old:
            old_run_id = old.run_id
            deleted = self.db.query(WatchlistSnapshotRefreshClaim).filter_by(token=old.token, market='KR').filter(
                WatchlistSnapshotRefreshClaim.expires_at <= now).delete(synchronize_session=False)
            if not deleted:
                self.db.rollback()
                return False
            self.db.expunge(old)
            if old_run_id:
                self.interrupt_run(old_run_id)
        self.db.add(WatchlistSnapshotRefreshClaim(market='KR', token=self.token,
            expires_at=now + timedelta(seconds=CLAIM_LEASE_SECONDS)))
        try:
            self.db.commit()
            return True
        except IntegrityError:
            self.db.rollback()
            return False

    def interrupt_run(self, run_id):
        run = self.db.get(WatchlistSnapshotRun, run_id)
        if run is not None and run.status == 'running':
            run.status, run.completed_at = 'failed', self.now()
            run.error_count = max(1, run.error_count or 0)
            self.db.add(WatchlistSnapshotError(run_id=run.id, symbol=None, stage='exception',
                reason_code='worker_interrupted', exception_type=None, retryable=True,
                attempt=1, resolved=False, created_at=self.now()))

    def release(self):
        self.db.query(WatchlistSnapshotRefreshClaim).filter_by(market='KR', token=self.token).delete(synchronize_session=False)
        self.db.commit()

    def record_errors(self, errors, *, symbol=None, attempt=1):
        for error in errors:
            self.db.add(WatchlistSnapshotError(run_id=self.run.id, symbol=symbol,
                attempt=attempt, resolved=False, created_at=self.now(), **error))
            logger.warning('watchlist_snapshot_error run_id=%s symbol=%s stage=%s reason_code=%s exception_type=%s http_status=%s retryable=%s attempt=%s',
                self.run.id, symbol, error['stage'], error['reason_code'], error.get('exception_type'),
                error.get('http_status'), error['retryable'], attempt)

    def counts(self):
        items = self.db.query(WatchlistSnapshotItem).filter_by(run_id=self.run.id).all()
        unresolved = {r.symbol for r in self.db.query(WatchlistSnapshotError).filter_by(run_id=self.run.id, resolved=False)}
        scored = sum(self.valid_item(item, check_age=False) for item in items)
        missing = max(0, self.run.source_count - len(items))
        return scored, len(unresolved) + missing

    def valid_item(self, item, *, check_age=True):
        try:
            indicators = json.loads(item.indicators_json or '{}')
            return (item.current_price is not None and math.isfinite(item.current_price) and item.current_price > 0
                and indicator_payload_is_quant_ready(indicators)
                and math.isfinite(item.quant_buy_score) and math.isfinite(item.quant_sell_score)
                and (not check_age or (item.captured_at is not None and
                     0 <= (self.now() - naive(item.captured_at)).total_seconds() <= REUSE_MAX_AGE_SECONDS)))
        except (ValueError, TypeError):
            return False

    def reuse(self, parent_id, universe):
        self.fence()
        sources = {r['symbol']: r for r in universe}
        bad = {r.symbol for r in self.db.query(WatchlistSnapshotError).filter_by(run_id=parent_id, resolved=False)}
        retained = set()
        for item in self.db.query(WatchlistSnapshotItem).filter_by(run_id=parent_id).all():
            source = sources.get(item.symbol)
            if source and item.symbol not in bad and source['market'] == item.market and self.valid_item(item):
                self.db.add(WatchlistSnapshotItem(run_id=self.run.id, **{
                    field: getattr(item, field) for field in ('symbol', 'name', 'market', 'current_price',
                        'quant_buy_score', 'quant_sell_score', 'indicators_json', 'quant_reason', 'captured_at')}))
                retained.add(item.symbol)
        self.db.commit()
        return retained

    def process_item(self, source, market_data, budget):
        for attempt in range(1, len(ITEM_RETRY_DELAYS) + 2):
            self.checkpoint()
            item, _scored, _failed = self.service._build_item(source, market_data=market_data,
                                                          gate_level=self.job.gate_level)
            self.fence()
            errors = item.pop('errors', [])
            self.record_errors(errors, symbol=source['symbol'], attempt=attempt)
            if not errors:
                self.db.query(WatchlistSnapshotError).filter_by(run_id=self.run.id, symbol=source['symbol']).update({'resolved': True})
            row = self.db.query(WatchlistSnapshotItem).filter_by(run_id=self.run.id, symbol=source['symbol']).first()
            if row is None:
                row = WatchlistSnapshotItem(run_id=self.run.id, **item)
                self.db.add(row)
            else:
                for key, value in item.items():
                    setattr(row, key, value)
            self.db.flush()
            self.run.scored_count, self.run.error_count = self.counts()
            self.db.commit()  # Checkpoint useful data before another symbol/read.
            if budget.stopped:
                raise SnapshotReadStopped(budget.stopped)
            if not errors or not all(e['retryable'] for e in errors) or attempt > len(ITEM_RETRY_DELAYS):
                return
            self.pause(ITEM_RETRY_DELAYS[attempt - 1])

    def finish(self):
        self.fence()
        self.db.flush()
        self.run.scored_count, errors = self.counts()
        self.run.error_count = max(errors, self.run.error_count if self.run.status == 'failed' else 0)
        self.run.completed_at = self.now()
        self.run.elapsed_seconds = round(max(0, self.monotonic() - self.started_clock), 3)
        if self.run.status != 'failed':
            self.run.status = ('success' if self.run.scored_count == self.run.source_count
                               and self.run.source_count > 0 and not self.run.error_count else 'failed')
        if self.run.status == 'success':
            self.job.status, self.job.next_retry_at, self.job.reason_code = 'succeeded', None, None
        else:
            errors = self.db.query(WatchlistSnapshotError).filter_by(run_id=self.run.id, resolved=False).all()
            retryable = bool(errors) and all(e.retryable for e in errors)
            if self.now() >= self.job.deadline_at:
                status, reason = 'exhausted', 'snapshot_recovery_deadline'
            elif self.job.attempts >= len(RECOVERY_RETRY_DELAYS) or self.job.recovery_read_calls >= RECOVERY_MAX_READ_CALLS:
                status, reason = 'exhausted', 'snapshot_recovery_budget_exhausted'
            elif not retryable:
                status, reason = 'blocked', 'non_retryable_snapshot_error'
            else:
                status, reason = 'pending', 'transient_snapshot_error'
            self.job.status, self.job.reason_code = status, reason
            self.job.next_retry_at = (self.now() + timedelta(seconds=RECOVERY_RETRY_DELAYS[self.job.attempts])
                                      if status == 'pending' else None)
        self.db.commit()
        logger.info('watchlist_snapshot_finished run_id=%s root_run_id=%s status=%s source_count=%s scored_count=%s error_count=%s recovery_status=%s recovery_attempts=%s read_calls=%s',
            self.run.id, self.job.root_run_id, self.run.status, self.run.source_count,
            self.run.scored_count, self.run.error_count, self.job.status, self.job.attempts,
            self.job.initial_read_calls + self.job.recovery_read_calls)

    def result(self):
        from app.services.watchlist_snapshot_service import serialize_snapshot_run
        return {**serialize_snapshot_run(self.run), 'recovery': {
            'root_run_id': self.job.root_run_id, 'status': self.job.status,
            'attempts': self.job.attempts, 'reason_code': self.job.reason_code,
            'next_retry_at': self.job.next_retry_at.isoformat() if self.job.next_retry_at else None,
            'initial_read_calls': self.job.initial_read_calls, 'recovery_read_calls': self.job.recovery_read_calls}}

    def refresh(self, *, gate_level, recovery_id=None):
        if not self.service._refresh_lock.acquire(blocking=False):
            return {'status': 'already_running', 'market': 'KR'}
        acquired = False
        try:
            acquired = self.acquire()
            if not acquired:
                return {'status': 'already_running', 'market': 'KR'}
            parent_id = None
            self.recovering = recovery_id is not None
            if self.recovering:
                self.job = self.db.query(WatchlistSnapshotRecovery).filter_by(id=recovery_id).populate_existing().one()
                if self.job.status not in {'pending', 'running', 'building'}:
                    return {'status': 'recovery_not_due', 'market': 'KR'}
                self.interrupt_run(self.job.latest_run_id)
                if (self.now() >= self.job.deadline_at or self.job.attempts >= len(RECOVERY_RETRY_DELAYS)
                        or self.job.recovery_read_calls >= RECOVERY_MAX_READ_CALLS):
                    self.job.status = 'exhausted'
                    self.job.reason_code = ('snapshot_recovery_deadline' if self.now() >= self.job.deadline_at
                                            else 'snapshot_recovery_budget_exhausted')
                    self.db.commit()
                    return {'status': 'recovery_exhausted', 'market': 'KR'}
            try:
                universe = self.service.load_universe()
            except Exception:
                if self.recovering:
                    self.job.status, self.job.reason_code = 'blocked', 'snapshot_universe_unavailable'
                    self.db.commit()
                raise
            if self.recovering:
                if self.job.universe_hash != universe_hash(universe, self.job.gate_level):
                    self.job.status, self.job.reason_code = 'blocked', 'snapshot_universe_changed'
                    self.db.commit()
                    return {'status': 'recovery_blocked', 'market': 'KR'}
                if self.job.next_retry_at and self.job.next_retry_at > self.now():
                    return {'status': 'recovery_not_due', 'market': 'KR'}
                parent_id = self.job.latest_run_id
                self.job.attempts += 1
                self.job.status = 'running'
                gate_level = self.job.gate_level
            self.started_clock = self.monotonic()
            self.run_deadline = self.now() + timedelta(seconds=RUN_TIMEOUT_SECONDS)
            self.clock_deadline = self.started_clock + RUN_TIMEOUT_SECONDS
            self.run = WatchlistSnapshotRun(market='KR', started_at=self.now(), source_count=len(universe), status='running')
            self.db.add(self.run)
            self.db.flush()
            if not self.recovering:
                # A newer normal refresh replaces outstanding older chains.
                self.db.query(WatchlistSnapshotRecovery).filter(
                    WatchlistSnapshotRecovery.market == 'KR',
                    WatchlistSnapshotRecovery.status.in_(['pending', 'building', 'running']),
                ).update({'status': 'superseded', 'reason_code': 'newer_regular_snapshot'})
                self.job = WatchlistSnapshotRecovery(root_run_id=self.run.id, latest_run_id=self.run.id,
                    market='KR', gate_level=gate_level, universe_hash=universe_hash(universe, gate_level),
                    status='building', attempts=0, initial_read_calls=0, recovery_read_calls=0,
                    deadline_at=self.now() + timedelta(seconds=RECOVERY_WINDOW_SECONDS), created_at=self.now())
                self.db.add(self.job)
            self.job.latest_run_id = self.run.id
            self.db.query(WatchlistSnapshotRefreshClaim).filter_by(market='KR', token=self.token).update({'run_id': self.run.id})
            self.db.commit()
            budget = SnapshotReadBudget(checkpoint=self.checkpoint, reserve=self.reserve_read,
                wait=self.pause, monotonic=self.monotonic)
            try:
                retained = self.reuse(parent_id, universe) if parent_id else set()
                client = self.service.client or self.service.client_factory(self.db)
                market_data = self.service.market_data_service_factory(client)
                with snapshot_read_budget(budget):
                    for source in universe:
                        if source['symbol'] not in retained:
                            self.process_item(source, market_data, budget)
                    self.checkpoint()
            except Exception as exc:
                self.db.rollback()
                if isinstance(exc, SnapshotReadStopped) and str(exc) == 'snapshot_lease_lost':
                    return {'status': 'failed', 'reason_code': 'snapshot_lease_lost', 'market': 'KR'}
                error = safe_snapshot_error(exc, stage='exception')
                if isinstance(exc, SnapshotReadStopped) and str(exc) in {'snapshot_timeout', 'snapshot_cancelled'}:
                    error['retryable'] = True
                self.record_errors([error])
                self.run.status, self.run.error_count = 'failed', max(1, self.run.error_count or 0)
            self.finish()
            return self.result()
        finally:
            try:
                if acquired:
                    self.release()
            finally:
                self.service._refresh_lock.release()

    def recover_due(self):
        now = self.now()
        latest = self.service.latest_run(self.db)
        if latest is None:
            return None
        job = self.db.query(WatchlistSnapshotRecovery).filter_by(latest_run_id=latest.id).first()
        if job is None:
            # Historical failures such as 229 have no attributed error record.
            # Do not infer a transient error or silently retry unknown causes.
            return None
        if job.status not in {'pending', 'building', 'running'}:
            return None
        claim = self.db.get(WatchlistSnapshotRefreshClaim, 'KR')
        if claim and claim.expires_at > now:
            return None
        if job.status == 'pending' and job.next_retry_at and job.next_retry_at > now:
            return None
        return self.refresh(gate_level=job.gate_level, recovery_id=job.id)
