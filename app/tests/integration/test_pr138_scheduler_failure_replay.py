"""2026-10-20 failure reconstruction. Isolated DB, virtual time, no HTTP."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import AutomationSchedulerSlot, WatchlistSnapshotRun
from app.services.scheduler_service import AutomationSchedulerService
from app.services.scheduler_slot_dispatcher import SchedulerSlotDispatcher
from app.services.scheduler_task_supervisor import (
    SchedulerTaskExpired, SchedulerTaskSupervisor, check_scheduler_buy_allowed,
    check_scheduler_watchlist_ready, check_scheduler_task_active,
)

KST = ZoneInfo('Asia/Seoul')
ADMIN = ('11:20', '12:20', '13:40')
USER = ('11:30', '12:30', '13:30')


def at(value):
    return datetime.fromisoformat(f'2026-10-20T{value}:00').replace(tzinfo=KST)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx
    original_send = httpx.Client.send
    def forbidden(*args, **kwargs):
        pytest.fail('No external HTTP or real KIS submit is permitted')
    def only_testserver(self, request, *args, **kwargs):
        if request.url.host == 'testserver':
            return original_send(self, request, *args, **kwargs)
        return forbidden()
    monkeypatch.setattr('requests.sessions.Session.request', forbidden)
    monkeypatch.setattr('httpx.Client.send', only_testserver)


@pytest.fixture
def replay(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{(tmp_path / "replay.db").as_posix()}',
                           connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    clock = [at('07:37')]
    scheduler = AutomationSchedulerService(retry_now_provider=lambda: clock[0])
    monkeypatch.setattr('app.services.automation_scheduler_service.SessionLocal', sessions)
    monkeypatch.setattr(scheduler, '_next_automation_run_at', lambda now: None)
    schedule = {'status': 'active', 'provider': 'kis', 'market': 'KR',
                'analysis_times': ADMIN, 'profile': {'id': 1, 'provider': 'kis', 'market': 'KR'}}
    monkeypatch.setattr(scheduler, '_selected_profile_schedule', lambda now: schedule)
    user_schedule = {'profile': {'id': 2, 'effective_settings': {'entry': {'analysis_times': USER}}}}
    users = scheduler.user_auto_trading_scheduler_service
    monkeypatch.setattr(users, 'due_slots', lambda *args, **kwargs: [])
    monkeypatch.setattr(users, '_eligible_user_profiles', lambda *args, provider, **kwargs:
                        [(SimpleNamespace(id=2), None, user_schedule)] if provider == 'kis' else [])
    def drain():
        with scheduler._task_supervisor.lock:
            threads = [task['thread'] for task in scheduler._task_supervisor.tasks.values()]
        for thread in threads:
            thread.join(5)
            assert not thread.is_alive()
    yield SimpleNamespace(scheduler=scheduler, sessions=sessions, clock=clock, drain=drain)
    scheduler._task_supervisor.cancel_all()
    drain()
    engine.dispose()


def rows(replay):
    with replay.sessions() as db:
        return [(row.account_key, row.scheduled_at, row.status, row.reason)
                for row in db.query(AutomationSchedulerSlot).order_by(AutomationSchedulerSlot.scheduled_at).all()]


class FakeKisClient:
    def __init__(self):
        self.uncertain = False
        self.actual_kis_submit_count = 0

    def get_account_balance(self):
        if self.uncertain:
            raise RuntimeError('HTTP 500 synthetic inquire-balance')
        return {'orderable_cash': 100000}


def test_balance_500_and_blocked_monitor_preserve_all_six_slots(replay, monkeypatch):
    scheduler, clock = replay.scheduler, replay.clock
    fake = FakeKisClient()
    events = []
    def admin(slot, now):
        try:
            fake.get_account_balance()
        except RuntimeError:
            events.append(('admin', slot))
            return {'result': 'blocked', 'reason': 'account_snapshot_unavailable'}
        return {'result': 'HOLD', 'reason': 'no_candidate'}
    monkeypatch.setattr(scheduler, '_run_automation_tick', admin)
    monkeypatch.setattr(scheduler, '_run_user_account_slot', lambda user, provider, slot, now:
                        events.append(('test01', slot)) or {'result': 'HOLD', 'reason': 'no_candidate'})
    # 07:37 discovery registers all six slots before any failure.
    scheduler._plan_admin_slots(clock[0])
    scheduler._plan_user_slots(clock[0])
    assert len(rows(replay)) == 6
    for value, failed in [('09:02', True), ('09:04', False), ('09:17', True)]:
        clock[0] = at(value)
        fake.uncertain = failed
        if failed:
            with pytest.raises(RuntimeError, match='HTTP 500'):
                fake.get_account_balance()
        else:
            assert fake.get_account_balance()['orderable_cash'] > 0
    blocked = threading.Event()
    started = threading.Event()
    assert scheduler._task_supervisor.launch('position-monitor',
        lambda: (started.set(), blocked.wait(10)), timeout=120)
    assert started.wait(1)
    try:
        for value in sorted(ADMIN + USER):
            clock[0] = at(value)
            scheduler._plan_admin_slots(clock[0])
            scheduler._plan_user_slots(clock[0])
            with scheduler._task_supervisor.lock:
                workers = [task['thread'] for name, task in scheduler._task_supervisor.tasks.items()
                           if name.startswith('account-')]
            for worker in workers:
                worker.join(5)
        assert len(events) == 6
        assert [row[2] for row in rows(replay)] == ['blocked', 'HOLD', 'blocked', 'HOLD', 'HOLD', 'blocked']
        assert fake.actual_kis_submit_count == 0
        assert any(task['expired'] for task in scheduler._task_supervisor.snapshot(clock[0]))
    finally:
        blocked.set()


@pytest.mark.parametrize('duration', [403, 202])
def test_slow_incomplete_watchlist_does_not_hide_slots(replay, monkeypatch, duration):
    scheduler, clock = replay.scheduler, replay.clock
    blocked = threading.Event()
    started = threading.Event()
    def refresh():
        started.set()
        blocked.wait(10)
    scheduler._task_supervisor.launch('watchlist-refresh', refresh, timeout=600)
    assert started.wait(1)
    clock[0] = at('11:20')
    with replay.sessions() as db:
        db.add(WatchlistSnapshotRun(market='KR', started_at=at('11:20').astimezone(UTC),
            source_count=200, scored_count=199, error_count=1, status='failed', elapsed_seconds=duration))
        db.commit()
    def entry(*args):
        with replay.sessions() as db:
            check_scheduler_watchlist_ready(db, clock[0])
        pytest.fail('Incomplete watchlist must never reach BUY')
    monkeypatch.setattr(scheduler, '_run_automation_tick', entry)
    monkeypatch.setattr(scheduler, '_run_user_account_slot', entry)
    try:
        for value in ('11:20', '11:30'):
            clock[0] = at(value)
            scheduler._plan_admin_slots(clock[0])
            scheduler._plan_user_slots(clock[0])
            with scheduler._task_supervisor.lock:
                workers = [task['thread'] for name, task in scheduler._task_supervisor.tasks.items()
                           if name.startswith('account-')]
            for worker in workers:
                worker.join(5)
        assert [row[2] for row in rows(replay)][:2] == ['failed', 'failed']
        assert all(row[3] == 'watchlist_snapshot_not_ready' for row in rows(replay)[:2])
    finally:
        blocked.set()


def test_due_slots_and_db_exceptions_are_logged_and_recovery_never_catches_up(replay, monkeypatch, caplog):
    scheduler, clock = replay.scheduler, replay.clock
    monkeypatch.setattr(scheduler, 'is_running', lambda: True)
    clock[0] = at('11:20')
    monkeypatch.setattr(scheduler, '_plan_maintenance', lambda now: None)
    def db_error(now):
        raise RuntimeError('synthetic SQLite lock')
    monkeypatch.setattr(scheduler, '_selected_profile_schedule', db_error)
    users = scheduler.user_auto_trading_scheduler_service
    def due_error(*args, **kwargs):
        raise ValueError('synthetic due_slots failure')
    monkeypatch.setattr(users, 'due_slots', due_error)
    scheduler._last_heartbeat_at = clock[0]
    scheduler._dispatch_scheduler_iteration(clock[0])
    replay.drain()
    assert 'scheduler_task_failed' in caplog.text
    assert any(record.exc_info for record in caplog.records)
    assert scheduler.scheduler_health(now=clock[0])['scheduler_health_status'] != 'healthy'
    # Fresh heartbeat alone cannot cover a frozen scheduler's progress.
    clock[0] = at('12:00')
    scheduler._last_heartbeat_at = clock[0]
    scheduler._last_tick_at = at('11:20')
    assert scheduler.scheduler_health(now=clock[0])['scheduler_health_status'] == 'stalled'
    monkeypatch.setattr(scheduler, 'is_running', lambda: False)
    assert scheduler.scheduler_health(now=clock[0])['scheduler_health_status'] == 'stopped'
    dispatcher = scheduler._slot_dispatcher
    dispatcher.reconcile(account='admin', provider='kis', profile_id=1, slots=[at(v) for v in ADMIN],
        now=at('16:23'), callback=lambda *args: pytest.fail('No past slot may submit'))
    dispatcher.reconcile(account='user-2', provider='kis', profile_id=2, slots=[at(v) for v in USER],
        now=at('16:23'), callback=lambda *args: pytest.fail('No past slot may submit'))
    assert all(row[2] == 'missed' for row in rows(replay))
    assert dispatcher.summary()['scheduler_missed_slot_count'] == 6
    # New process / supervisor still sees the terminal rows.
    replacement = SchedulerSlotDispatcher(replay.sessions, SchedulerTaskSupervisor(), lambda: at('16:23'))
    replacement.reconcile(account='admin', provider='kis', profile_id=1, slots=[at(v) for v in ADMIN],
        now=at('16:23'), callback=lambda *args: pytest.fail('No restart replay'))
    assert len(rows(replay)) == 6


def test_timeout_keeps_lane_until_exit_and_revokes_late_buy(replay):
    supervisor = replay.scheduler._task_supervisor
    entered, release = threading.Event(), threading.Event()
    result = []
    def work():
        entered.set()
        release.wait(10)
        with pytest.raises(SchedulerTaskExpired, match='scheduler_task_timeout'):
            check_scheduler_task_active()
        try:
            check_scheduler_buy_allowed()
            result.append('submitted')
        except SchedulerTaskExpired:
            result.append('blocked')
    assert supervisor.launch('account-admin', work, timeout=1, critical=True)
    assert entered.wait(1)
    try:
        replay.clock[0] += timedelta(seconds=403)
        assert supervisor.snapshot(replay.clock[0])[0]['expired']
        for _ in range(10):
            assert not supervisor.launch('account-admin', lambda: result.append('duplicate'))
        assert len(supervisor.tasks) == 1
    finally:
        release.set()
        replay.drain()
    assert result == ['blocked']


def test_runtime_health_remains_readable_when_status_queries_fail(replay, monkeypatch):
    scheduler = replay.scheduler
    def failure(*args, **kwargs):
        raise RuntimeError('synthetic DB unavailable')
    monkeypatch.setattr(scheduler, 'user_auto_trading_jobs', failure)
    monkeypatch.setattr(scheduler, '_selected_profile_schedule', failure)
    status = scheduler.runtime_status(now=replay.clock[0])
    assert status['scheduler_health_status'] == 'stopped'
    assert status['user_auto_trading_jobs'] == []
    assert status['scheduler_last_error']


def test_real_loop_survives_iteration_exception_and_api_reports_dead_thread(replay, monkeypatch, caplog):
    from fastapi.testclient import TestClient
    from app.main import app
    scheduler = replay.scheduler
    progressed = threading.Event()
    calls = []
    def iteration(now):
        calls.append(now)
        if len(calls) == 1:
            raise RuntimeError('synthetic top-level DB error')
        scheduler._last_tick_at = datetime.now(UTC)
        progressed.set()
    monkeypatch.setattr(scheduler, '_dispatch_scheduler_iteration', iteration)
    # A short interruptible wait tests the real loop without waiting 20 seconds.
    original_wait = scheduler._stop_event.wait
    monkeypatch.setattr(scheduler._stop_event, 'wait', lambda timeout=None: original_wait(.01))
    scheduler.start()
    try:
        assert progressed.wait(2)
        assert scheduler.is_running()
        assert any(record.exc_info for record in caplog.records)
    finally:
        scheduler.stop()
    assert not scheduler.is_running()
    monkeypatch.setattr('app.routes.scheduler.scheduler_service', scheduler)
    response = TestClient(app).get('/scheduler/health')
    assert response.status_code == 200
    assert response.json()['scheduler_health_status'] == 'stopped'
    assert response.json()['scheduler_engine_running'] is False


def test_durable_claim_prevents_duplicates_and_busy_account_cannot_spawn_replacements(replay):
    dispatcher = replay.scheduler._slot_dispatcher
    entered, release = threading.Event(), threading.Event()
    calls = []
    def work(slot, now):
        calls.append(slot)
        entered.set()
        release.wait(10)
        return {'result': 'HOLD'}
    replay.clock[0] = at('11:20')
    args = dict(account='admin', provider='kis', profile_id=1,
                slots=[at('11:20'), at('12:20')], callback=work)
    dispatcher.reconcile(now=replay.clock[0], **args)
    assert entered.wait(1)
    try:
        replacement = SchedulerSlotDispatcher(replay.sessions, replay.scheduler._task_supervisor,
                                               lambda: replay.clock[0])
        replacement.reconcile(now=replay.clock[0], **args)
        assert calls == ['11:20']
        replay.clock[0] = at('12:20')
        replay.scheduler._task_supervisor.snapshot(replay.clock[0])
        dispatcher.reconcile(now=replay.clock[0], **args)
        assert [row[2] for row in rows(replay)] == ['failed', 'blocked']
        assert len(replay.scheduler._task_supervisor.tasks) == 1
    finally:
        release.set()
        replay.drain()
    assert [row[2] for row in rows(replay)] == ['failed', 'blocked']


def test_restart_expires_previous_day_pending_slots_without_dispatch(replay):
    dispatcher = replay.scheduler._slot_dispatcher
    dispatcher.reconcile(account='admin', provider='kis', profile_id=1, slots=[at('11:20')],
        now=at('07:37'), callback=lambda *args: pytest.fail('Not due'))
    dispatcher.expire_overdue(at('07:37') + timedelta(days=1))
    assert rows(replay)[0][2:] == ('missed', 'slot_window_elapsed_no_catchup')
