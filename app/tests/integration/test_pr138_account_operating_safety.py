from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.db.models import OrderLog, PositionExitRetryJob, PositionLifecycle, TradeRunLog, User, UserBrokerCredential
from app.services.automation_profile_buy_scheduler_service import AutomationProfileBuySchedulerService
from app.services.scheduler_service import AutomationSchedulerService
from app.services.broker_credential_crypto_service import BrokerCredentialCryptoService
from app.services.kis_order_sync_service import KisOrderSyncError, KisOrderSyncService
from app.services.kis_position_lifecycle_service import KisPositionLifecycleService
from app.services.account_trading_limit_service import AccountTradingLimitError
from app.services.user_auto_trading_scheduler_service import UserAutoTradingSchedulerService
from app.tests.test_kis_duplicate_account_scope import accounts, _client, _order


KST = ZoneInfo('Asia/Seoul')
NEXT_DAY = datetime(2026, 10, 20, 11, 30, tzinfo=KST)
pytestmark = pytest.mark.usefixtures('fake_kis_admin_credentials')


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('External HTTP and KIS submissions are forbidden in this replay')
    monkeypatch.setattr('requests.sessions.Session.request', forbidden)


def _lifecycle(db, owner, *, status='open', symbol='028670', days_old=1):
    entry = _order(db, owner=owner, side='buy', status='FILLED', payload={
        'source': 'strategy_live_auto_buy', 'automation_profile': True,
        'source_type': 'profile_aware_guarded_live_auto_buy',
    })
    entry.filled_qty = 1
    entry.avg_fill_price = entry.filled_avg_price = 10_000
    entry.remaining_qty = 0
    row = PositionLifecycle(owner_user_id=owner, symbol=symbol, entry_order_id=entry.id,
        entry_price=10_000, cost_basis=10_000, quantity=1, status=status,
        opened_at=NEXT_DAY.astimezone(UTC).replace(tzinfo=None) - timedelta(days=days_old),
        stop_loss_threshold_pct=2, take_profit_threshold_pct=8)
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize('requested,previous', [('admin', 'first'), ('first', 'admin')])
@pytest.mark.parametrize('status', ['open', 'closing'])
@pytest.mark.parametrize('days_old', [1, 100])
def test_foreign_lifecycle_cannot_preempt_entry(db_session, accounts, requested, previous, status, days_old):
    _, first, _, credentials = accounts
    owners = {'admin': None, 'first': first.id}
    row = _lifecycle(db_session, owners[previous], status=status, days_old=days_old)
    client = _client(owners[requested], credentials, side='buy')
    service = AutomationProfileBuySchedulerService(client=client)
    assert service._position_priority(db_session) is False
    assert row.status == status


@pytest.mark.parametrize('owner', ['admin', 'first'])
@pytest.mark.parametrize('status', ['open', 'closing'])
def test_own_lifecycle_still_preempts_entry(db_session, accounts, owner, status):
    _, first, _, credentials = accounts
    owner_id = None if owner == 'admin' else first.id
    _lifecycle(db_session, owner_id, status=status)
    assert AutomationProfileBuySchedulerService(client=_client(owner_id, credentials, side='buy'))._position_priority(db_session)


def test_shared_physical_account_lifecycle_preempts_entry(db_session, accounts):
    _, first, _, credentials = accounts
    credentials[first.id]['account_no'] = '11112222'
    db_session.query(UserBrokerCredential).filter_by(user_id=first.id).one().encrypted_payload = (
        BrokerCredentialCryptoService().encrypt(credentials[first.id]))
    db_session.commit()
    _lifecycle(db_session, first.id)
    assert AutomationProfileBuySchedulerService(client=_client(None, credentials, side='buy'))._position_priority(db_session)


@pytest.mark.parametrize('requested,previous', [('admin', 'first'), ('first', 'admin')])
def test_lifecycle_manager_cannot_reconcile_another_owner(db_session, accounts, requested, previous):
    _, first, _, credentials = accounts
    owners = {'admin': None, 'first': first.id}
    row = _lifecycle(db_session, owners[previous])
    before = (row.status, row.last_evaluated_at, row.exit_reason)
    service = KisPositionLifecycleService(_client(owners[requested], credentials, side='buy'))
    result = service.run_management_once(db_session, execute=False, positions_snapshot=[], now=NEXT_DAY)
    db_session.refresh(row)
    assert result['managed_count'] == 0
    assert (row.status, row.last_evaluated_at, row.exit_reason) == before


def test_order_sync_cannot_query_or_mutate_foreign_owner(db_session, accounts):
    _, first, _, credentials = accounts
    order = _order(db_session, owner=first.id, side='buy', status='UNKNOWN_STALE')
    order.kis_odno = 'FAKE-USER-ORDER'
    db_session.commit()
    client = _client(None, credentials, side='buy')
    calls = []
    client.inquire_daily_order_executions = lambda **kwargs: calls.append(kwargs) or {'orders': []}
    service = KisOrderSyncService(client)
    assert service.sync_submitted_orders(db_session) == []
    with pytest.raises(KisOrderSyncError, match='account_scope_mismatch'):
        service.sync_order(db_session, order.id)
    assert calls == []
    assert order.last_synced_at is None
    assert order.internal_status == 'UNKNOWN_STALE'


def test_position_cache_never_returns_another_accounts_holdings(accounts):
    _, first, _, credentials = accounts
    scheduler = AutomationSchedulerService()
    admin = _client(None, credentials, side='buy')
    user = _client(first.id, credentials, side='buy')
    admin.list_positions = lambda: [{'symbol': '005930', 'qty': 1}]
    user.list_positions = lambda: []
    assert scheduler._load_position_exit_positions(admin, now=NEXT_DAY)
    assert scheduler._load_position_exit_positions(user, now=NEXT_DAY) == []


def test_position_cache_revalidates_account_after_credentials_change(accounts):
    _, first, _, credentials = accounts
    scheduler = AutomationSchedulerService()
    client = _client(first.id, credentials, side='buy')
    client.list_positions = lambda: [{'symbol': '005930', 'qty': 1}]
    assert scheduler._load_position_exit_positions(client, now=NEXT_DAY)
    client.credentials = {**client.credentials, 'account_no': '99998888'}
    client.list_positions = lambda: []
    assert scheduler._load_position_exit_positions(client, now=NEXT_DAY) == []


def _snapshot(user, positions=None):
    return {'connected': True, 'environment': 'live', 'owner_user_id': user.id,
            'provider': 'kis', 'market': 'KR', 'broker_account_id': f'user:{user.id}:kis:KR',
            'positions_reliable': True, 'positions': list(positions or []), 'open_orders': []}


def _manage_user(db, user, snapshot):
    return UserAutoTradingSchedulerService(now_provider=lambda: NEXT_DAY)._manage_positions(
        db, user=user, provider='kis', snapshot=snapshot, now=NEXT_DAY,
        scheduler_slot='11:30', profile={})


@pytest.mark.parametrize('status', ['open', 'closing'])
def test_admin_lifecycle_does_not_preempt_regular_user_analysis(db_session, accounts, status):
    _, first, _, _ = accounts
    row = _lifecycle(db_session, None, status=status)
    assert _manage_user(db_session, first, _snapshot(first))['action'] == 'entry_scan'
    assert row.status == status


@pytest.mark.parametrize('field,value', [('owner_user_id', 1), ('broker_account_id', 'admin:kis:KR'),
    ('market', 'US'), ('provider', 'alpaca'), ('environment', 'paper'),
    ('positions_reliable', False), ('positions', None), ('open_orders', None)])
def test_user_position_snapshot_cannot_cross_scope(db_session, accounts, field, value):
    _, first, _, _ = accounts
    snapshot = {**_snapshot(first), field: value}
    with pytest.raises(ValueError, match='account_scope_mismatch|account_snapshot_unavailable'):
        _manage_user(db_session, first, snapshot)


def test_orphaned_user_lifecycle_is_never_assumed_to_be_admin(db_session, accounts):
    _, first, _, credentials = accounts
    row = _lifecycle(db_session, first.id)
    row.owner_user_id = None
    db_session.commit()
    service = AutomationProfileBuySchedulerService(client=_client(None, credentials, side='buy'))
    with pytest.raises(AccountTradingLimitError, match='account_scope_mismatch'):
        service._position_priority(db_session)
    with pytest.raises(AccountTradingLimitError, match='account_scope_mismatch'):
        service.lifecycle_service.run_management_once(db_session, positions_snapshot=[], now=NEXT_DAY)
    assert row.status == 'open'


def test_unowned_user_exit_is_never_inferred_to_be_a_different_admin_account(db_session, accounts):
    _, first, _, _ = accounts
    order = _order(db_session, owner=None, side='sell', status='UNKNOWN_STALE',
                   payload={'source': 'user_auto_trading_scheduler', 'user_id': first.id})
    with pytest.raises(AccountTradingLimitError, match='account_scope_mismatch'):
        _manage_user(db_session, first, _snapshot(first))
    assert order.internal_status == 'UNKNOWN_STALE'


@pytest.mark.parametrize('owner,blocked', [('admin', False), ('first', True)])
@pytest.mark.parametrize('status', ['pending', 'running'])
def test_retry_jobs_are_scoped_even_with_no_broker_holdings(db_session, accounts, owner, blocked, status):
    admin, first, _, _ = accounts
    job = PositionExitRetryJob(owner_user_id=admin.id if owner == 'admin' else first.id,
        exit_cycle_key=f'fake-{owner}-{status}', profile_key='fake-profile', provider='kis', market='KR',
        scheduler_slot='11:30', status=status, next_retry_at=NEXT_DAY)
    db_session.add(job)
    db_session.commit()
    result = _manage_user(db_session, first, _snapshot(first))
    assert bool(result.get('entry_blocked')) is blocked
    assert result['reason'] == ('kis_exit_read_retry_pending' if blocked else 'no_open_position')
    assert job.status == status


@pytest.mark.parametrize('owner,blocked', [('admin', False), ('first', True)])
@pytest.mark.parametrize('status', ['REQUESTED', 'SUBMITTED', 'UNKNOWN_STALE', 'SYNC_FAILED'])
def test_unresolved_sell_blocks_only_its_account(db_session, accounts, owner, blocked, status):
    _, first, _, credentials = accounts
    old = _order(db_session, owner=None if owner == 'admin' else first.id, side='sell', status=status)
    result = _manage_user(db_session, first, _snapshot(first))
    assert bool(result.get('entry_blocked')) is blocked
    assert AutomationProfileBuySchedulerService(client=_client(None, credentials, side='buy'))._position_priority(db_session) is (not blocked)
    assert old.internal_status == status


@pytest.mark.parametrize('status', ['SUBMITTED', 'UNKNOWN_STALE', 'SYNC_FAILED'])
def test_broker_pending_sell_blocks_entry_without_local_holdings(db_session, accounts, status):
    _, first, _, _ = accounts
    snapshot = _snapshot(first)
    snapshot['open_orders'] = [{'symbol': '028670', 'side': 'sell', 'status': status}]
    result = _manage_user(db_session, first, snapshot)
    assert result['entry_blocked'] is True
    assert result['reason'] == 'duplicate_open_sell_order'


@pytest.mark.parametrize('price,reason', [(9700, 'stop_loss_triggered'), (10900, 'take_profit_triggered')])
def test_own_held_position_still_routes_to_exit_before_entry(db_session, accounts, price, reason):
    _, first, _, _ = accounts
    _lifecycle(db_session, first.id)
    snapshot = _snapshot(first, [{'symbol': '028670', 'quantity': 1,
                                 'current_price': price, 'average_price': 10_000}])
    result = _manage_user(db_session, first, snapshot)
    assert result['action'] == 'sell'
    assert result['reason'] == reason


def test_completed_fresh_monitor_snapshot_avoids_one_entry_read(accounts):
    _, _, _, credentials = accounts
    now = [NEXT_DAY]
    scheduler = AutomationSchedulerService(retry_now_provider=lambda: now[0])
    client = _client(None, credentials, side='buy')
    calls = []
    client.list_positions = lambda: calls.append(now[0]) or []
    scheduler.automation_profile_buy_scheduler_service = SimpleNamespace(client=client, positions_loader=None)
    scheduler._load_position_exit_positions(client, now=now[0], force_refresh=True)
    scheduler._positions_first(None)
    assert len(calls) == 1  # Before the fix, monitor + entry issued two reads.
    now[0] += timedelta(seconds=6)
    scheduler._positions_first(None)
    assert len(calls) == 2


def test_cached_empty_discovery_does_not_replace_final_execution_checks(db_session, accounts):
    from app.services.kis_automation_execution_core import KisAutomationExecutionCore
    from app.tests.test_kis_duplicate_account_scope import _guard
    _, _, _, credentials = accounts
    client = _client(None, credentials, side='buy')
    scheduler = AutomationSchedulerService(retry_now_provider=lambda: NEXT_DAY)
    scheduler.automation_profile_buy_scheduler_service = SimpleNamespace(client=client, positions_loader=None)
    scheduler._load_position_exit_positions(client, now=NEXT_DAY)
    client.positions = [{'symbol': '028670', 'qty': 1}]
    assert scheduler._positions_first(None) == []
    order = _order(db_session, owner=None, side='buy')
    assert _guard(KisAutomationExecutionCore(client), db_session, order)['reason'] == 'max_positions_reached'


def test_slow_monitor_does_not_lock_another_account_or_fresh_entry(accounts):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    _, first, _, credentials = accounts
    scheduler = AutomationSchedulerService(retry_now_provider=lambda: NEXT_DAY)
    slow = _client(None, credentials, side='buy')
    other = _client(first.id, credentials, side='buy')
    entered, release = Event(), Event()
    calls = []
    def read():
        calls.append(True)
        if len(calls) == 1:
            entered.set()
            assert release.wait(timeout=5)
        return []
    slow.list_positions = read
    scheduler.automation_profile_buy_scheduler_service = SimpleNamespace(client=slow, positions_loader=None)
    with ThreadPoolExecutor(max_workers=3) as pool:
        monitor = pool.submit(scheduler._load_position_exit_positions, slow, now=NEXT_DAY)
        assert entered.wait(timeout=2)
        try:
            assert pool.submit(scheduler._load_position_exit_positions, other, now=NEXT_DAY).result(timeout=2) == []
            assert pool.submit(scheduler._positions_first, None).result(timeout=2) == []
            assert not monitor.done()
        finally:
            release.set()
        assert monitor.result(timeout=2) == []
    assert len(calls) == 2  # One pending discovery plus one independent fresh entry read.


def _next_day_admin(db, monkeypatch, *, slot='11:30', score=67.32):
    from app.tests.integration.test_kis_automation_scheduler_replay import build_harness, candidate
    from app.tests.integration.test_kis_automation_scheduler_registration import _canonical_scheduler
    import app.services.automation_scheduler_service as module
    at = NEXT_DAY.replace(hour=int(slot[:2]), minute=int(slot[3:]))
    harness = build_harness(db, monkeypatch, now=at, analysis_times=(slot,), candidates=[
        candidate(symbol='028670', price=10_000, score=score,
                  quant_buy_score=68.76, quant_c_score=68.76, ai_buy_score=63),
    ])
    scheduler = _canonical_scheduler(harness, monkeypatch)
    scheduler.retry_now_provider = harness.clock.now
    scheduler.retry_scheduler = lambda *args, **kwargs: True
    harness.runtime.update_settings(db, {'scheduler_enabled': True})
    harness.profile_buy.positions_loader = None
    monkeypatch.setattr(module, 'KisClient', lambda *args, **kwargs: harness.client)
    monkeypatch.setattr(module, 'KisAuthManager', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, 'MarketSessionService', lambda: harness.market_sessions)
    return harness, scheduler, at


def _next_day_user(db, monkeypatch, *, score=67.32, shared=False):
    from cryptography.fernet import Fernet
    from app.config import get_settings
    from app.tests.test_user_auto_trading_scheduler_pr129 import (
        _user, _configure_user, _set_profile_schedule, _harness,
        _enable_live_canonical_user, _final_candidate,
        CanonicalProfileWatchlists, CanonicalRuntimePreview,
    )
    from app.services.user_auto_trading_scheduler_service import UserAutoTradingCandidateService
    user = _user(db, 'virtual-test01')
    _configure_user(db, user)
    _set_profile_schedule(db, user, ['11:30', '13:30'], fixed_budget=50_000, max_order_notional=48_000)
    scheduler, account, _, broker, client = _harness(snapshots={(user.id, 'kis'): {
        **_snapshot(user), 'environment': 'paper',
        'account': {'currency': 'KRW', 'portfolio_value': 1_000_000,
                    'equity': 1_000_000, 'cash': 1_000_000, 'buying_power': 1_000_000},
    }})
    _enable_live_canonical_user(db, user, account)
    scheduler.now_provider = lambda: NEXT_DAY
    settings = get_settings()
    monkeypatch.setattr(settings, 'broker_credential_master_key', Fernet.generate_key().decode())
    credentials = dict(environment='live', account_no='11112222' if shared else '33334444',
                       account_product_code='01', app_key='fake-user-key', app_secret='fake-user-secret')
    db.add(UserBrokerCredential(user_id=user.id, provider='kis', environment='live',
        encrypted_payload=BrokerCredentialCryptoService().encrypt(credentials), encryption_version=1))
    db.commit()
    item = _final_candidate('028670', price=10_000, c_score=68.76, final_score=score, ai_buy_score=63)
    watchlists = CanonicalProfileWatchlists([item])
    original_build = watchlists.build
    def build(*args, **kwargs):
        result = original_build(*args, **kwargs)
        result['snapshot']['snapshot_date'] = NEXT_DAY.date().isoformat()
        return result
    watchlists.build = build
    preview = CanonicalRuntimePreview({'028670': 10_000}, final_score=score)
    scheduler.candidate_service = UserAutoTradingCandidateService(
        profile_watchlists=watchlists, runtime_preview_service=preview)
    return scheduler, user, preview, account, broker, client


@pytest.mark.parametrize('slot', ['11:30', '13:30'])
@pytest.mark.parametrize('poll_age,delay', [(0, 0), (20, 0), (0, 3), (0, 61)])
def test_next_day_idle_monitor_preserves_one_entry_analysis(db_session, monkeypatch, slot, poll_age, delay):
    harness, scheduler, nominal = _next_day_admin(db_session, monkeypatch, slot=slot)
    def forbidden_evaluation(*args, **kwargs):
        pytest.fail('Empty portfolio must not evaluate a sell signal')
    monkeypatch.setattr(KisPositionLifecycleService, 'run_due_management_once', forbidden_evaluation)
    harness.clock.current = nominal - timedelta(seconds=poll_age)
    monitor = scheduler._run_position_exit_monitor_once(now=harness.clock.now())
    assert monitor['position_exit_monitor_state'] == 'idle'
    assert monitor['reason'] == 'no_position'
    assert monitor['held_position_count'] == 0
    assert monitor['poll_interval_seconds'] == 20
    assert monitor['position_exit_interval_minutes'] == 30
    assert monitor['broker_submit_called'] is False
    harness.clock.current = nominal + timedelta(seconds=delay)
    result = scheduler.run_once(slot=slot, now=harness.clock.now())
    if delay > 60:
        assert result['result'] == 'blocked'
        assert result['reason'] == 'missed_slot_replay_forbidden'
        # Existing policy completes analysis but refuses the expired BUY slot.
        assert len(harness.preview.calls) == 1
        assert result['entry_slot_delay_ms'] == 61_000
        assert harness.broker.buy_calls == harness.broker.sell_calls == []
        assert harness.client.external_kis_submit_count == 0
        return
    assert result['result'] == 'LIVE_READY', result.get('reason')
    assert result['held_position_count'] == 0
    assert result['position_monitor_state'] == 'idle'
    assert result['entry_slot_delay_ms'] == delay * 1000
    assert result['entry_blocked_by_position_management'] is False
    assert len(harness.preview.calls) == 1
    assert len(harness.broker.buy_calls) == 1
    assert harness.broker.sell_calls == []
    assert scheduler.run_once(slot=slot, now=nominal)['reason'] == 'scheduler_slot_already_run'
    assert len(harness.preview.calls) == 1
    assert harness.client.external_kis_submit_count == 0


@pytest.mark.parametrize('admin_score,user_score', [(67.32, 67.32), (64, 67.32), (67.32, 64)])
@pytest.mark.parametrize('first', ['admin', 'user'])
def test_next_day_accounts_keep_scores_positions_and_daily_limits_independent(
    db_session, monkeypatch, admin_score, user_score, first,
):
    from app.tests.test_user_auto_trading_scheduler_pr129 import _run_user_scheduler_slot
    harness, admin_scheduler, at = _next_day_admin(db_session, monkeypatch, score=admin_score)
    user_scheduler, user, preview, account, broker, client = _next_day_user(
        db_session, monkeypatch, score=user_score)
    user_id = user.id
    if first == 'admin':
        admin = admin_scheduler.run_once(slot='11:30', now=at)
        user = db_session.get(User, user_id)
        regular = _run_user_scheduler_slot(db_session, user_scheduler, user, slot='11:30', now=at)
    else:
        regular = _run_user_scheduler_slot(db_session, user_scheduler, user, slot='11:30', now=at)
        admin = admin_scheduler.run_once(slot='11:30', now=at)
    assert len(harness.preview.calls) == len(preview.calls) == 1
    assert bool(harness.broker.buy_calls) is (admin_score >= 65), admin
    assert bool(client.buy_calls) is (user_score >= 65)
    assert len(harness.broker.buy_calls) <= 1
    assert len(client.buy_calls) <= 1
    if admin_score >= 65:
        assert admin['result'] == 'LIVE_READY'
    if user_score >= 65:
        assert regular['result'] == 'submitted'
        assert db_session.query(PositionLifecycle).filter_by(owner_user_id=user_id, status='open').count() == 1
    # Each service still enforces its own slot claims and position/daily caps.
    assert admin_scheduler.run_once(slot='11:30', now=at)['reason'] == 'scheduler_slot_already_run'
    user = db_session.get(User, user_id)
    assert _run_user_scheduler_slot(db_session, user_scheduler, user, slot='11:30', now=at)['reason'] == 'duplicate_scheduler_slot'
    assert harness.client.external_kis_submit_count == 0
    assert broker.buy_calls == broker.sell_calls == []


@pytest.mark.parametrize('shared', [False, True])
@pytest.mark.parametrize('requested', ['admin', 'user'])
def test_next_day_unresolved_buy_is_physical_account_scoped(db_session, monkeypatch, shared, requested):
    from app.tests.test_user_auto_trading_scheduler_pr129 import _run_user_scheduler_slot
    harness, admin_scheduler, at = _next_day_admin(db_session, monkeypatch)
    user_scheduler, user, _, _, _, client = _next_day_user(db_session, monkeypatch, shared=shared)
    old = _order(db_session, owner=user.id if requested == 'admin' else None,
                 side='buy', status='UNKNOWN_STALE')
    old_id = old.id
    if requested == 'admin':
        result = admin_scheduler.run_once(slot='11:30', now=at)
        submitted = bool(harness.broker.buy_calls)
        if shared:
            assert result['profile_buy']['reason'] == 'duplicate_open_order'
    else:
        result = _run_user_scheduler_slot(db_session, user_scheduler, user, slot='11:30', now=at)
        submitted = bool(client.buy_calls)
        if shared:
            assert result['pipeline_diagnostics']['fallback_candidate_results_by_symbol']['028670']['skip_reason'] == 'duplicate_open_order'
            run = db_session.query(TradeRunLog).filter_by(
                owner_user_id=user.id, reason='duplicate_open_order').one()
            risk = json.loads(run.response_payload)['risk']
            assert risk['duplicate_check_source'] == 'local_db'
            assert risk['matched_order_id'] == old_id
            assert risk['matched_order_owner_user_id'] is None
            assert risk['requested_order_owner_user_id'] == user.id
            assert risk['block_reason'] == 'duplicate_open_order'
            encoded = json.dumps(risk)
            assert '11112222' not in encoded
            assert 'fake-user-key' not in encoded
            assert 'fake-user-secret' not in encoded
    assert submitted is (not shared)
    old = db_session.get(OrderLog, old_id)
    assert old.internal_status == 'UNKNOWN_STALE'
    assert old.sync_error == 'kis_order_not_found_in_inquiry'
    assert harness.client.external_kis_submit_count == 0


def test_next_day_position_read_timeout_defers_entry_without_analysis(db_session, monkeypatch):
    harness, scheduler, at = _next_day_admin(db_session, monkeypatch)
    def timeout():
        raise TimeoutError('fake position timeout')
    harness.client.list_positions = timeout
    monitor = scheduler._run_position_exit_monitor_once(now=at)
    result = scheduler.run_once(slot='11:30', now=at)
    assert monitor['position_state_known'] is False
    assert result['reason'] in {'position_state_refresh_pending', 'kis_exit_read_retry_pending'}
    assert result['entry_blocked_by_position_management'] is True
    assert harness.preview.calls == []
    assert harness.broker.buy_calls == harness.broker.sell_calls == []
    assert harness.client.external_kis_submit_count == 0


def test_mock_latency_saved_without_changing_discovery_interval(accounts):
    _, _, _, credentials = accounts
    elapsed = [0.0]
    client = _client(None, credentials, side='buy')
    def read():
        elapsed[0] += 0.5  # Deterministic 500 ms broker read; no wall-clock sleep.
        return []
    client.list_positions = read
    scheduler = AutomationSchedulerService(retry_now_provider=lambda: NEXT_DAY)
    scheduler.automation_profile_buy_scheduler_service = SimpleNamespace(client=client, positions_loader=None)
    scheduler._load_position_exit_positions(client, now=NEXT_DAY, force_refresh=True)
    scheduler._positions_first(None)
    assert elapsed[0] == 0.5  # Previous monitor + entry discovery cost 1.0 s / two reads.
    scheduler._load_position_exit_positions(client, now=NEXT_DAY + timedelta(seconds=20), force_refresh=True)
    assert elapsed[0] == 1.0  # The next normal 20-second poll still refreshes.
