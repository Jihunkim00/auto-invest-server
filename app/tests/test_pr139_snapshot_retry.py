"""Fake-clock snapshot retries; no real broker transport or waiting."""
from datetime import UTC, datetime, timedelta
import json

import pytest

from app.brokers.base import KisApiError, KisAuthError, KisConfigurationError
from app.db.models import TradeRunLog, UserAutoTradingSlotClaim, UserTradingSettings
from app.services.account_snapshot_retry import (
    AccountSnapshotReadError, AccountSnapshotRetryCoordinator,
    RETRY_SLOT_REPLAY_GRACE_SECONDS, retryable_kis_account_snapshot_error,
)
from app.services.market_session_service import MarketSessionService
from app.tests.test_user_auto_trading_scheduler_pr129 import _retry_user_setup, _set_profile_schedule
from app.tests.integration.test_kis_automation_scheduler_replay import build_harness
from app.tests.integration.test_kis_automation_scheduler_registration import (
    _DeferredRetryQueue, _configure_admin_retry_scheduler,
)


@pytest.mark.parametrize('failures', [1, 2, 3])
def test_user_attempts_at_zero_sixty_three_hundred_seconds(db_session, monkeypatch, failures):
    user, scheduler, account, _, broker, kis, queue, clock, calls = _retry_user_setup(
        db_session, monkeypatch, failures=failures)
    start = clock[0]
    queried = []
    original = account.get_broker_snapshot
    def tracked(*args, **kwargs):
        queried.append((clock[0] - start).total_seconds())
        return original(*args, **kwargs)
    account.get_broker_snapshot = tracked
    first = scheduler.run_provider_once(db_session, provider='kis', scheduler_slot='09:10', now=clock[0])
    assert first['items'][0]['scheduled_retry_delay_seconds'] == 60
    assert first['items'][0]['next_retry_at'] == (start + timedelta(seconds=60)).isoformat()
    duplicate = scheduler.run_provider_once(db_session, provider='kis', scheduler_slot='09:10', now=clock[0])
    assert duplicate['items'][0]['reason'] == 'duplicate_scheduler_slot'
    while queue.pending:
        queue.run_next(clock)
    db_session.expire_all()
    claim = db_session.query(UserAutoTradingSlotClaim).filter_by(user_id=user.id).one()
    run = db_session.query(TradeRunLog).filter_by(run_key=claim.run_key).one()
    payload = json.loads(run.response_payload)
    details = payload.get('account_snapshot_retry') or payload
    assert queried == ([0, 60] if failures == 1 else [0, 60, 300])
    assert calls['count'] == min(failures + 1, 3)
    assert claim.status == ('failed' if failures == 3 else 'completed')
    assert details['retry_delays_seconds'] == [60, 240]
    history = details['attempt_history']
    assert history[0]['scheduled_retry_delay_seconds'] == 60
    assert history[-1]['scheduled_retry_delay_seconds'] == 0
    assert history[-1]['next_retry_at'] is None
    if failures > 1:
        assert history[1]['scheduled_retry_delay_seconds'] == 240
    assert len(db_session.query(UserAutoTradingSlotClaim).all()) == 1
    assert len(broker.buy_calls) <= 1
    assert kis.buy_calls == []


@pytest.mark.parametrize('failures', [1, 2, 3])
def test_admin_snapshot_path_has_same_attempt_delays(db_session, monkeypatch, failures):
    harness = build_harness(db_session, monkeypatch, mode='live')
    queue = _DeferredRetryQueue()
    scheduler = _configure_admin_retry_scheduler(db_session, harness, monkeypatch, queue)
    scheduler.retry_service_factory = lambda: scheduler
    start = harness.clock.now()
    queried = []
    original = scheduler._account_snapshot_preflight
    def snapshot(*args, **kwargs):
        queried.append((harness.clock.now() - start).total_seconds())
        if len(queried) <= failures:
            raise AccountSnapshotReadError(KisApiError('temporary', details={'http_status': 500, 'msg_cd': 'EGW00201'}))
        return original(*args, **kwargs)
    scheduler._account_snapshot_preflight = snapshot
    first = scheduler.run_once(slot='09:10', now=start)
    assert first['status'] == 'retry_pending', first
    assert first['next_retry_at'] == (start + timedelta(seconds=60)).isoformat()
    assert queue.pending[0][0][0] == 'admin'
    assert queue.pending[0][2] == 60
    while queue.pending:
        queue.run_next(harness.clock)
    assert queried == ([0, 60] if failures == 1 else [0, 60, 300])
    assert harness.client.external_kis_submit_count == 0
    assert len(harness.broker.buy_calls) <= 1
    if failures == 3:
        assert harness.broker.buy_calls == []
    assert RETRY_SLOT_REPLAY_GRACE_SECONDS == 375


@pytest.mark.parametrize('change,reason', [
    ('kill_switch', 'user_kill_switch_enabled'),
    ('auto_off', 'auto_trading_disabled_before_account_snapshot_retry'),
    ('user_off', 'user_disabled_before_account_snapshot_retry'),
    ('profile', 'automation_profile_changed_before_account_snapshot_retry'),
    ('market_close', 'market_closed'),
    ('cutoff', 'entry_window_closed'),
])
def test_retry_rechecks_current_safety_before_order(db_session, monkeypatch, change, reason):
    user, scheduler, account, _, broker, kis, queue, clock, calls = _retry_user_setup(
        db_session, monkeypatch, failures=2)
    # Read the explicit fake time for every market/cutoff check.
    scheduler.session_service = MarketSessionService()
    if change == 'cutoff':
        _set_profile_schedule(db_session, user, ['09:10'], no_new_entry_after='09:14')
    scheduler.run_provider_once(db_session, provider='kis', scheduler_slot='09:10', now=clock[0])
    settings = db_session.query(UserTradingSettings).filter_by(user_id=user.id).one()
    if change == 'kill_switch':
        settings.trading_mode = 'live'
        settings.live_trading_enabled = True
        settings.kill_switch = True
        settings.auto_live_confirmed_at = clock[0]
    elif change == 'auto_off':
        settings.auto_trading_enabled = False
    elif change == 'user_off':
        user.enabled = False
    elif change == 'profile':
        _set_profile_schedule(db_session, user, ['11:30'])
    db_session.commit()
    if change == 'market_close':
        clock[0] = clock[0].replace(hour=6, minute=30)  # 15:30 KST on the same trading day.
    while queue.pending:
        queue.run_next(clock)
    db_session.expire_all()
    claim = db_session.query(UserAutoTradingSlotClaim).filter_by(user_id=user.id).one()
    assert claim.reason == reason
    assert broker.buy_calls == [] and kis.buy_calls == []
    assert calls['count'] == (3 if change == 'cutoff' else 1)


@pytest.mark.parametrize('error', [KisAuthError('auth'), KisConfigurationError('config')])
def test_permanent_broker_errors_never_retry(error):
    assert retryable_kis_account_snapshot_error(AccountSnapshotReadError(error)) is False


def test_coordinator_retains_key_between_attempts_and_isolates_scopes(monkeypatch):
    coordinator = AccountSnapshotRetryCoordinator()
    timers = []
    monkeypatch.setattr(coordinator, '_start_timer', lambda key, callback, delay: timers.append((key, callback, delay)))
    admin, user = ('admin', 8, 'day', '12:30'), ('user', 2, 'kis', 'KR', 'day', '12:30')
    assert coordinator.schedule(admin, lambda: 240, delay_seconds=60)
    assert coordinator.schedule(user, lambda: None, delay_seconds=60)
    assert not coordinator.schedule(admin, lambda: None, delay_seconds=60)
    coordinator._run(*timers[0][:2])
    assert timers[-1][2] == 240
    assert not coordinator.schedule(admin, lambda: None, delay_seconds=60)
    assert coordinator.pending_count('admin') == coordinator.pending_count('user') == 1
    coordinator._finish(admin)
    coordinator._finish(user)
    coordinator._executor.shutdown(wait=False)
