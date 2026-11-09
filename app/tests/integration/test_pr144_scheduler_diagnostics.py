from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models import AutomationSchedulerSlot, OrderLog, PositionExitRetryJob, PositionLifecycle, TradeRunLog, User
from app.services.scheduler_service import AutomationSchedulerService
from app.services.scheduler_slot_dispatcher import SchedulerSlotDispatcher
from app.services.account_snapshot_retry import AccountSnapshotReadError
from app.services.automation_today_decision_service import AutomationTodayDecisionService

NOW = datetime(2026, 11, 9, 4, 30, tzinfo=UTC)


def test_detached_admin_snapshot_retry_finishes_parent_slot(db_session, monkeypatch):
    db = db_session
    sessions = sessionmaker(bind=db.get_bind())
    import app.services.automation_scheduler_service as module
    monkeypatch.setattr(module, 'SessionLocal', sessions)
    clock = [NOW]
    callbacks = []
    def schedule(key, callback, **kwargs):
        callbacks.append(callback)
        return True
    class FakeRetryService:
        retry_now_provider = lambda self: clock[0]
        def _run_automation_tick(self, *args, **kwargs):
            with sessions() as inner:
                inner.add(TradeRunLog(run_key='FAKE-final-analysis', symbol='WATCHLIST',
                    trigger_source='automation_scheduler', mode='automation_scheduler_profile_analysis',
                    stage='done', result='hold', reason='gpt_buy_score_below_threshold', created_at=clock[0]))
                inner.commit()
            return {'result': 'blocked', 'reason': 'gpt_buy_score_below_threshold',
                'broker_submit_called': False, 'real_order_submitted': False}
    service = AutomationSchedulerService(retry_scheduler=schedule,
        retry_service_factory=FakeRetryService, retry_now_provider=lambda: clock[0])
    db.add(AutomationSchedulerSlot(slot_key='admin:kis:2026-11-09:13:30',
        account_key='admin', provider='kis', profile_id=5, status='retry_pending',
        scheduled_at=NOW.replace(tzinfo=None), started_at=NOW.replace(tzinfo=None),
        reason='account_snapshot_retry_pending_1_of_3'))
    db.commit()
    assert service._schedule_admin_account_snapshot_retry(slot='13:30', trading_date='2026-11-09',
        profile_key='FAKE-admin', profile_id=5, retry_started_at=NOW)
    clock[0] += timedelta(seconds=190)
    assert callbacks[0]() is None
    db.expire_all()
    row = db.query(AutomationSchedulerSlot).one()
    assert (row.status, row.reason) == ('HOLD', 'gpt_buy_score_below_threshold')
    assert row.finished_at == clock[0].replace(tzinfo=None)
    assert json.loads(row.result_json)['reason'] == row.reason
    service._slot_dispatcher.expire_overdue(NOW + timedelta(minutes=13))
    db.expire_all()
    assert row.reason == db.query(TradeRunLog).one().reason


def test_retry_cannot_overwrite_timeout_or_another_profile(db_session):
    db = db_session
    dispatcher = SchedulerSlotDispatcher(sessionmaker(bind=db.get_bind()), None, lambda: NOW)
    db.add(AutomationSchedulerSlot(slot_key='admin:kis:2026-11-09:13:30',
        account_key='admin', provider='kis', profile_id=5, status='retry_pending',
        scheduled_at=NOW.replace(tzinfo=None), started_at=NOW.replace(tzinfo=None)))
    db.commit()
    kwargs = dict(account='admin', provider='kis', trading_date='2026-11-09', slot='13:30',
        result={'result':'hold', 'reason':'gpt_buy_score_below_threshold'})
    assert not dispatcher.finish_retry(**kwargs, profile_id=6, now=NOW)
    assert dispatcher.finish_retry(**kwargs, profile_id=5, now=NOW + timedelta(seconds=720))
    db.expire_all()
    row = db.query(AutomationSchedulerSlot).one()
    assert (row.status,row.reason) == ('failed','scheduler_task_timeout')
    assert json.loads(row.result_json)['reason'] == row.reason
    assert json.loads(row.result_json)['last_observed_result']['reason'] == 'gpt_buy_score_below_threshold'
    assert not dispatcher.finish_retry(**kwargs, profile_id=5, now=NOW + timedelta(seconds=721))
    db.expire_all()
    assert row.reason == 'scheduler_task_timeout'


def test_retry_can_finish_before_initial_worker_persists_pending(db_session):
    db = db_session
    dispatcher = SchedulerSlotDispatcher(sessionmaker(bind=db.get_bind()), None, lambda: NOW)
    row = AutomationSchedulerSlot(slot_key='admin:kis:2026-11-09:13:30',
        account_key='admin', provider='kis', profile_id=5, status='running',
        scheduled_at=NOW.replace(tzinfo=None), started_at=NOW.replace(tzinfo=None))
    db.add(row)
    db.commit()
    assert dispatcher.finish_retry(account='admin', provider='kis', profile_id=5,
        trading_date='2026-11-09', slot='13:30', now=NOW + timedelta(seconds=60),
        result={'result':'hold','reason':'gpt_buy_score_below_threshold'})
    dispatcher._finish(row.id, 'retry_pending','account_snapshot_retry_pending_1_of_3', NOW)
    db.expire_all()
    assert (row.status, row.reason) == ('HOLD','gpt_buy_score_below_threshold')


@pytest.mark.parametrize('exposure', ['none','holding','unknown_sell','no_recent_snapshot','stale_snapshot'])
def test_empty_account_monitor_does_not_create_repeated_exit_jobs(db_session, monkeypatch, exposure):
    db = db_session
    import app.services.automation_scheduler_service as module
    monkeypatch.setattr(module, 'KisClient', lambda *a: SimpleNamespace())
    monkeypatch.setattr(module, 'kis_client_cache_scope', lambda client: 'FAKE-admin-scope')
    db.add(User(id=1,username='admin',role='admin',enabled=True))
    if exposure == 'holding':
        db.add(PositionLifecycle(owner_user_id=None,symbol='036460',entry_order_id=999,
            entry_price=100,cost_basis=100,quantity=1,status='open',opened_at=NOW))
    if exposure == 'unknown_sell':
        db.add(OrderLog(owner_user_id=None,broker='kis',market='KR',side='sell',symbol='036460',
            order_type='market',qty=1,internal_status='UNKNOWN_STALE'))
    db.commit()
    service = AutomationSchedulerService()
    if exposure != 'no_recent_snapshot':
        service._position_exit_positions_cache['FAKE-admin-scope'] = (
            NOW - timedelta(seconds=301 if exposure == 'stale_snapshot' else 20), [])
    for index in range(2):
        result = service._position_snapshot_failure_result(db, profile={'id':5,'owner_user_id':1},
            profile_id=5,profile_key='FAKE-admin',scheduler_slot=f'position_exit_{index}',
            now=NOW,error=TimeoutError(),monitor_only=True)
        assert result['position_state_known'] is False
        assert result['buy_execution_allowed'] is False
    jobs = db.query(PositionExitRetryJob).all()
    assert len(jobs) == (0 if exposure == 'none' else 1)
    if jobs:
        assert jobs[0].status == 'pending'


@pytest.mark.parametrize('reason,status', [
    ('unresolved_entry_limit_hit','blocked'), ('position_state_refresh_pending','retry_pending'),
    ('position_retry_exit_unresolved','blocked'), ('account_snapshot_unavailable','failed'),
    ('scheduler_task_timeout','failed'), ('gpt_buy_score_below_threshold','HOLD'),
])
def test_home_feed_keeps_exact_execution_reason_and_separate_analysis(db_session, reason, status):
    db = db_session
    db.add_all([AutomationSchedulerSlot(slot_key='admin:kis:2026-11-09:13:30',
        account_key='admin',provider='kis',profile_id=5,status=status,reason=reason,
        scheduled_at=NOW.replace(tzinfo=None)),
        AutomationSchedulerSlot(slot_key='user-2:kis:2026-11-09:13:30',
        account_key='user-2',provider='kis',profile_id=8,status='failed',reason='other_account',
        scheduled_at=NOW.replace(tzinfo=None))])
    db.commit()
    decision = {'scheduler_slot':'13:30','status':'analysis_complete',
        'reason':'gpt_buy_score_below_threshold','final_buy_score':61}
    result = AutomationTodayDecisionService._with_scheduler_outcome(db,decision,
        profile={'id':5,'provider':'kis'},owner_user_id=None,local_date=NOW.date())
    assert result['reason'] == reason
    assert result['analysis_reason'] == 'gpt_buy_score_below_threshold'
    assert result['final_buy_score'] == 61
    assert result['status'] == ('analysis_complete' if status == 'HOLD' else status)
