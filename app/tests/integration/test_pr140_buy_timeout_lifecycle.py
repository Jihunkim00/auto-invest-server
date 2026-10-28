"""PR140 replay: virtual time, isolated DB and fake broker only."""
import json
import threading
import time
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import AutomationProfileBuyReservation, AutomationSchedulerSlot, OrderLog, TradeRunLog, WatchlistSnapshotRun
from app.services.automation_profile_buy_scheduler_service import _persisted_daily_new_entry_count
from app.services.kis_daily_entry_accounting import daily_entry_counts
from app.services.scheduler_slot_dispatcher import SchedulerSlotDispatcher
from app.services.scheduler_task_supervisor import (
    ACCOUNT_SLOT_BUY_WINDOW_SECONDS, ACCOUNT_SLOT_TASK_TIMEOUT_SECONDS,
    SchedulerTaskExpired, SchedulerTaskSupervisor, check_scheduler_buy_allowed,
    scheduler_buy_guard,
)
from app.services.strategy_risk_budget_service import StrategyRiskBudgetService
from app.tests.integration.test_kis_automation_scheduler_replay import build_harness, candidate, CUSTOM_PROFILE_KEY, UTC_NOW


pytestmark = pytest.mark.usefixtures('fake_kis_admin_credentials')


@pytest.fixture(autouse=True)
def no_external_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Real HTTP/KIS submit is forbidden in PR140 tests')
    monkeypatch.setattr('requests.sessions.Session.request', forbidden)
    monkeypatch.setattr('httpx.Client.send', forbidden)
    monkeypatch.setattr('app.brokers.kis_client.KisClient.submit_domestic_cash_order', forbidden)


@pytest.fixture
def harness(db_session, monkeypatch):
    h = build_harness(db_session, monkeypatch, mode='live')
    h.clock.current = UTC_NOW.replace(hour=2, minute=20)
    profile = h.profiles.get(db_session, CUSTOM_PROFILE_KEY)
    settings = json.loads(profile.settings_json)
    settings['entry']['analysis_times'] = ['11:20', '12:20', '13:55']
    profile.settings_json = json.dumps(settings)
    db_session.add(WatchlistSnapshotRun(market='KR', started_at=h.clock.now(),
        completed_at=h.clock.now(), status='success', source_count=1, scored_count=1, error_count=0))
    db_session.commit()
    monkeypatch.setattr('app.services.market_session_service.MarketSessionService', lambda: h.market_sessions)
    return h


def task(h, *, started=None):
    started = started or h.clock.now()
    return {'started_at': started, 'now_provider': h.clock.now,
            'cancel': threading.Event(), 'timeout': ACCOUNT_SLOT_TASK_TIMEOUT_SECONDS,
            'deadline': time.monotonic() + ACCOUNT_SLOT_TASK_TIMEOUT_SECONDS,
            'buy_deadline': time.monotonic() + ACCOUNT_SLOT_BUY_WINDOW_SECONDS,
            'buy_expires_at': started + timedelta(seconds=ACCOUNT_SLOT_BUY_WINDOW_SECONDS)}


def run(h, *, slot='11:20', now=None):
    return h.profile_buy.run_once(h.db, [candidate()], scheduler_slot=slot,
        now=now or h.clock.now(), trusted_scheduler_authority=True)


@pytest.mark.parametrize('minute, expected', [(23, 'filled'), (30, 'blocked'), (31, 'blocked'), (32, 'blocked')])
def test_analysis_finishes_after_slot_order_lifecycle_is_final(harness, monkeypatch, minute, expected):
    h = harness
    started = h.clock.now()
    original = h.profile_buy._validate
    def delayed(*args, **kwargs):
        result = original(*args, **kwargs)
        h.clock.current = started.replace(minute=minute)
        return result
    monkeypatch.setattr(h.profile_buy, '_validate', delayed)
    with scheduler_buy_guard(task(h)):
        result = run(h, now=started)
    order = h.db.query(OrderLog).one()
    reservation = h.db.query(AutomationProfileBuyReservation).one()
    assert result['status'] == expected
    assert order.internal_status != 'REQUESTED'
    assert h.client.external_kis_submit_count == 0
    if expected == 'filled':
        assert len(h.broker.buy_calls) == 1
        assert reservation.status == 'filled'
    else:
        assert h.broker.buy_calls == []
        assert order.internal_status == 'REJECTED_BY_SAFETY_GATE'
        assert reservation.status == 'blocked'
        assert reservation.block_reason == ('scheduler_task_timeout' if minute == 32 else 'scheduler_task_expired_before_buy')
        assert json.loads(order.response_payload)['broker_submit_called'] is False
        assert result['real_order_submitted'] is False
        assert order.filled_qty is None
        assert h.db.query(TradeRunLog).filter_by(order_id=order.id).one().reason == reservation.block_reason
        assert daily_entry_counts(h.db, now=h.clock.now()) == (0, 0)


def test_validation_failure_records_reason_without_request_residue(harness):
    h = harness
    h.validation.approved = False
    with scheduler_buy_guard(task(h)):
        result = run(h)
    order = h.db.query(OrderLog).one()
    assert result['status'] == 'blocked'
    assert result['real_order_submitted'] is False
    assert order.internal_status == 'REJECTED_BY_SAFETY_GATE'
    assert order.error_message == h.validation.block_reason
    assert order.broker_status == 'not_submitted'
    assert h.db.query(AutomationProfileBuyReservation).one().status == 'blocked'
    assert h.broker.buy_calls == []


def test_raised_validation_timeout_is_finalized_and_next_slot_can_trade(harness, monkeypatch):
    h = harness
    original = h.profile_buy._validate
    def expired(*args, **kwargs):
        raise SchedulerTaskExpired('scheduler_task_timeout')
    monkeypatch.setattr(h.profile_buy, '_validate', expired)
    with scheduler_buy_guard(task(h)):
        first = run(h)
    assert first['reason'] == 'scheduler_task_timeout'
    assert daily_entry_counts(h.db, now=h.clock.now()) == (0, 0)
    monkeypatch.setattr(h.profile_buy, '_validate', original)
    h.clock.current += timedelta(hours=1)
    with scheduler_buy_guard(task(h)):
        second = run(h, slot='12:20')
    assert second['status'] == 'filled'
    assert len(h.broker.buy_calls) == 1
    assert daily_entry_counts(h.db, now=h.clock.now()) == (1, 0)


@pytest.mark.parametrize('response', ['timeout', 'missing_id'])
def test_dispatch_uncertainty_reserves_capacity_and_never_resubmits(harness, monkeypatch, response):
    h = harness
    calls = []
    def uncertain(**kwargs):
        calls.append(kwargs)
        # The durable ambiguous record must already exist when POST starts.
        assert h.db.query(OrderLog).one().internal_status == 'UNKNOWN_STALE'
        if response == 'timeout':
            raise TimeoutError('request dispatched, acknowledgment lost')
        return {}
    monkeypatch.setattr(h.broker, 'submit_market_buy', uncertain)
    with scheduler_buy_guard(task(h)):
        first = run(h)
        again = run(h)
    assert first['status'] == again['status'] == 'sync_required'
    assert first['broker_submit_called'] is True
    assert first['broker_buy_call_count'] == 1
    assert h.db.query(OrderLog).one().internal_status == 'UNKNOWN_STALE'
    assert h.db.query(AutomationProfileBuyReservation).one().status == 'sync_required'
    assert daily_entry_counts(h.db, now=h.clock.now()) == (0, 1)
    assert _persisted_daily_new_entry_count(h.db, now=h.clock.now()) == 0
    h.clock.current += timedelta(hours=1)
    with scheduler_buy_guard(task(h)):
        next_slot = run(h, slot='12:20')
    assert next_slot['reason'] == 'unresolved_entry_limit_hit'
    assert len(calls) == 1


def test_expiry_after_dispatch_marker_commit_still_proves_no_broker_call(harness, monkeypatch):
    h = harness
    started = h.clock.now()
    commit = h.db.commit
    def delayed_commit():
        pending = h.db.query(OrderLog).filter_by(internal_status='REQUESTED').first()
        dispatching = pending is not None and pending.internal_status == 'UNKNOWN_STALE'
        commit()
        if dispatching:
            h.clock.current = started + timedelta(minutes=11)
    monkeypatch.setattr(h.db, 'commit', delayed_commit)
    with scheduler_buy_guard(task(h)):
        result = run(h)
    order = h.db.query(OrderLog).one()
    assert result['status'] == 'blocked'
    assert result['reason'] == 'scheduler_task_expired_before_buy'
    assert result['broker_submit_called'] is False
    assert result['real_order_submitted'] is False
    assert order.internal_status == 'REJECTED_BY_SAFETY_GATE'
    assert order.broker_status == 'not_submitted'
    assert h.broker.buy_calls == []
    assert daily_entry_counts(h.db, now=h.clock.now()) == (0, 0)


def test_missing_broker_is_known_not_submitted(harness):
    h = harness
    h.profile_buy.execution_core.broker = None
    with scheduler_buy_guard(task(h)):
        result = run(h)
    assert result['reason'] == 'broker_unavailable'
    assert result['broker_submit_called'] is False
    assert h.db.query(OrderLog).one().internal_status == 'REJECTED_BY_SAFETY_GATE'
    assert h.db.query(AutomationProfileBuyReservation).one().status == 'blocked'


@pytest.mark.parametrize('failure', ['kill_switch', 'market_closed', 'cutoff', 'watchlist', 'authority', 'validation_exception'])
def test_final_safety_during_extended_window(harness, monkeypatch, failure):
    h = harness
    started = h.clock.now()
    original = h.profile_buy._validate
    def late_safety(*args, **kwargs):
        result = original(*args, **kwargs)
        h.clock.current += timedelta(minutes=3)
        if failure == 'kill_switch':
            h.runtime.update_settings(h.db, {'kill_switch': True})
        elif failure == 'market_closed':
            h.market_sessions.is_open = False
        elif failure == 'cutoff':
            profile = h.profiles.get(h.db, CUSTOM_PROFILE_KEY)
            settings = json.loads(profile.settings_json)
            settings['entry']['no_new_entry_after'] = '11:22'
            profile.settings_json = json.dumps(settings)
            h.db.commit()
        elif failure == 'watchlist':
            h.db.query(WatchlistSnapshotRun).one().status = 'failed'
            h.db.commit()
        elif failure == 'authority':
            h.runtime.update_settings(h.db, {'automation_mode': 'off'})
        else:
            raise ValueError('validation adapter failed before broker call')
        return result
    monkeypatch.setattr(h.profile_buy, '_validate', late_safety)
    with scheduler_buy_guard(task(h)):
        result = run(h, now=started)
    assert result['status'] == 'blocked'
    assert h.broker.buy_calls == []
    assert h.db.query(OrderLog).one().internal_status == 'REJECTED_BY_SAFETY_GATE'
    assert h.db.query(AutomationProfileBuyReservation).one().status == 'blocked'


@pytest.mark.parametrize('status, filled_qty, expected', [
    ('REQUESTED', None, (0, 1)), ('SUBMITTED', None, (0, 1)),
    ('ACCEPTED', None, (0, 1)), ('PENDING', None, (0, 1)),
    ('UNKNOWN_STALE', None, (0, 1)), ('SYNC_FAILED', None, (0, 1)),
    ('PARTIALLY_FILLED', 0, (0, 1)), ('PARTIALLY_FILLED', 1, (1, 0)),
    ('FILLED', 3, (1, 0)), ('CANCELED', 1, (1, 0)),
    ('REJECTED_BY_SAFETY_GATE', None, (0, 0)), ('DRY_RUN_SIMULATED', 3, (0, 0)),
])
def test_actual_entries_are_distinct_from_unresolved_capacity(harness, status, filled_qty, expected):
    h = harness
    row = OrderLog(broker='kis', market='KR', symbol='036460', side='buy', order_type='market',
        qty=3, filled_qty=filled_qty, internal_status=status, created_at=h.clock.now())
    h.db.add(row)
    h.db.commit()
    for _ in range(2):
        assert daily_entry_counts(h.db, now=h.clock.now()) == expected
        budget = StrategyRiskBudgetService(now_provider=h.clock.now)
        assert budget._trades_used_today(h.db, provider='kis', market='KR') == expected[0]
    assert daily_entry_counts(h.db, now=h.clock.now(), owner_user_id=999) == (0, 0)


def test_slot_window_is_nominal_and_task_expiry_remains_twelve_minutes(tmp_path):
    engine = create_engine(f'sqlite:///{(tmp_path / "slots.db").as_posix()}')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    nominal = UTC_NOW.replace(hour=2, minute=20)
    clock = [nominal + timedelta(seconds=40)]
    class CapturingSupervisor:
        def launch(self, lane, callback, **kwargs):
            self.callback, self.kwargs = callback, kwargs
            return True
    supervisor = CapturingSupervisor()
    dispatcher = SchedulerSlotDispatcher(sessions, supervisor, lambda: clock[0])
    try:
        args = dict(account='admin', provider='kis', profile_id=1,
                    slots=[nominal], callback=lambda *_: {'result': 'HOLD'})
        dispatcher.reconcile(now=clock[0], **args)
        assert supervisor.kwargs['timeout'] == 720
        assert supervisor.kwargs['buy_timeout'] == 560
        assert supervisor.kwargs['buy_expires_at'] == nominal + timedelta(seconds=600)
        clock[0] += timedelta(seconds=719)
        dispatcher.expire_overdue(clock[0])
        with sessions() as db:
            assert db.query(AutomationSchedulerSlot).one().status == 'running'
        clock[0] += timedelta(seconds=1)
        dispatcher.expire_overdue(clock[0])
        with sessions() as db:
            assert db.query(AutomationSchedulerSlot).one().reason == 'scheduler_task_timeout'
        # Start eligibility stays one minute, even with a ten minute BUY window.
        dispatcher.reconcile(now=nominal + timedelta(hours=1, minutes=3),
            **{**args, 'slots': [nominal + timedelta(hours=1)]})
        with sessions() as db:
            assert db.query(AutomationSchedulerSlot).order_by(AutomationSchedulerSlot.id.desc()).first().status == 'missed'
    finally:
        engine.dispose()


def test_simulated_fill_and_repeated_orphan_runs_never_count_as_real_fills(harness):
    h = harness
    h.db.add(OrderLog(broker='kis', market='KR', symbol='SIM', side='buy', order_type='market',
        internal_status='FILLED', filled_qty=3, created_at=h.clock.now(),
        response_payload=json.dumps({'simulation': True})))
    for index in range(2):
        h.db.add(TradeRunLog(run_key=f'orphan-{index}', trigger_source='automation_profile_scheduler',
            symbol='036460', mode='automation_profile_scheduler_buy', stage='done',
            result='submitted', order_id=999, created_at=h.clock.now()))
    h.db.commit()
    assert daily_entry_counts(h.db, now=h.clock.now()) == (0, 1)


def test_expired_worker_keeps_account_lane_and_blocks_without_snapshot(harness):
    h = harness
    supervisor = SchedulerTaskSupervisor(now_provider=h.clock.now)
    entered, release = threading.Event(), threading.Event()
    result = []
    def work():
        entered.set()
        assert release.wait(5)
        try:
            check_scheduler_buy_allowed()
        except SchedulerTaskExpired as exc:
            result.append(str(exc))
    assert supervisor.launch('account-admin', work, timeout=720, buy_timeout=600)
    worker = supervisor.tasks['account-admin']['thread']
    try:
        assert entered.wait(1)
        h.clock.current += timedelta(seconds=720)
        assert not supervisor.launch('account-admin', lambda: pytest.fail('Duplicate worker'))
        # No snapshot call is needed to make wall-clock expiry effective.
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        assert result == ['scheduler_task_timeout']
    finally:
        release.set()
        worker.join(5)
