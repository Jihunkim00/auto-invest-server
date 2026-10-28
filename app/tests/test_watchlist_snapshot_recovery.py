"""Known injected READ faults, isolated SQLite, virtual waits, no real broker."""
from collections import Counter
from datetime import UTC, datetime, timedelta
import json
import threading

import pytest

from app.db.models import (WatchlistSnapshotError, WatchlistSnapshotItem,
    WatchlistSnapshotRecovery, WatchlistSnapshotRefreshClaim, WatchlistSnapshotRun)
from app.services.market_data_snapshot_service import MarketDataSnapshotService
from app.services.watchlist_snapshot_policy import (
    check_snapshot_read, safe_snapshot_error, sanitize_snapshot_error,
    SnapshotReadBudget, SnapshotReadStopped, snapshot_read_budget,
)
from app.services.watchlist_snapshot_scheduler import WatchlistSnapshotScheduler
from app.services.watchlist_snapshot_service import WatchlistSnapshotService
from app.tests.test_watchlist_snapshot import (
    FakeKisClient, FakeIndicatorService, FakeQuantService, _write_universe,
)


class Clock:
    def __init__(self):
        self.current = datetime(2026, 10, 28, 3, 50, tzinfo=UTC)
        self.elapsed = 0.0

    def now(self):
        return self.current

    def advance(self, seconds):
        self.elapsed += seconds
        self.current += timedelta(seconds=seconds)

    def wait(self, seconds):
        self.advance(seconds)
        return False


class FaultKisClient(FakeKisClient):
    """Each fake READ uses the same physical-send checkpoint as KisClient."""
    def __init__(self, clock):
        super().__init__()
        self.clock, self.reads, self.faults = clock, [], {}
        self.failure = lambda: TimeoutError('token=PRIVATE cano=87654321 https://private.invalid')
        self.after_read = None

    def read(self, stage, symbol):
        check_snapshot_read()
        self.reads.append((stage, symbol, self.clock.elapsed))
        if self.after_read:
            self.after_read(stage, symbol)
        key = stage, symbol
        if self.faults.get(key, 0) > 0:
            self.faults[key] -= 1
            raise self.failure()

    def get_domestic_stock_price(self, symbol):
        self.read('quote', symbol)
        return {**super().get_domestic_stock_price(symbol), 'current_price': 70.0}

    def get_domestic_daily_bars(self, symbol, limit=120):
        self.read('daily', symbol)
        return super().get_domestic_daily_bars(symbol, limit)


@pytest.fixture(autouse=True)
def no_external_reads(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('PR141 requires FakeKisClient; external HTTP is forbidden')
    monkeypatch.setattr('requests.sessions.Session.request', forbidden)
    monkeypatch.setattr('httpx.Client.send', forbidden)
    monkeypatch.setattr('httpx.AsyncClient.send', forbidden)
    MarketDataSnapshotService.clear_process_cache()
    yield
    MarketDataSnapshotService.clear_process_cache()


def make_service(tmp_path, *, count=200):
    path, clock = tmp_path / 'universe.yaml', Clock()
    _write_universe(path, kospi=count, kosdaq=0)
    client = FaultKisClient(clock)
    service = WatchlistSnapshotService(client=client, universe_path=path,
        indicator_service=FakeIndicatorService(), quant_signal_service=FakeQuantService(),
        now_provider=clock.now, wait_provider=clock.wait, monotonic_provider=lambda: clock.elapsed)
    return service, client, clock


def due(service, db, clock):
    job = service.latest_recovery(db)
    if job.next_retry_at:
        clock.advance(max(0, (job.next_retry_at.replace(tzinfo=UTC) - clock.now()).total_seconds()))
    return service.recover_due(db)


@pytest.mark.parametrize('stage', ['quote', 'daily'])
def test_inline_transient_retry_records_and_resolves_only_affected_symbol(tmp_path, db_session, stage):
    service, client, clock = make_service(tmp_path, count=2)
    client.faults[stage, '000001'] = 1
    result = service.refresh(db_session)
    assert result['status'] == 'success' and result['error_count'] == 0
    errors = service.error_details(db_session, result['id'])
    primary = [error for error in errors if error['stage'] == stage]
    assert len(primary) == 1 and primary[0]['reason_code'] == 'transport_timeout'
    assert all(error['resolved'] and error['attempt'] == 1 for error in errors)
    assert Counter((s, symbol) for s, symbol, _ in client.reads)['quote', '000002'] == 1
    assert all(b[2] - a[2] >= 1 for a, b in zip(client.reads, client.reads[1:]))


def test_failed_200_snapshot_recovers_only_one_symbol_without_relabeling(tmp_path, db_session, caplog):
    service, client, clock = make_service(tmp_path)
    client.faults['quote', '000001'] = 3
    failed = service.refresh(db_session)
    assert (failed['status'], failed['scored_count'], failed['error_count']) == ('failed', 199, 1)
    assert failed['recovery']['status'] == 'pending'
    assert service.recover_due(db_session) is None  # Backoff is enforced.
    retained = db_session.query(WatchlistSnapshotItem).filter_by(run_id=failed['id'], symbol='000002').one().captured_at
    before = len(client.reads)
    recovered = due(service, db_session, clock)
    assert recovered['id'] != failed['id'] and recovered['status'] == 'success'
    assert len(client.reads) == before + 1
    assert (recovered['scored_count'], recovered['error_count']) == (200, 0)
    assert (recovered['recovery']['initial_read_calls'], recovered['recovery']['recovery_read_calls']) == (402, 1)
    assert clock.now() < datetime(2026, 10, 28, 4, 30, tzinfo=UTC)  # Before both 13:30/13:45.
    assert db_session.get(WatchlistSnapshotRun, failed['id']).status == 'failed'
    assert db_session.query(WatchlistSnapshotError).filter_by(run_id=failed['id'], stage='quote', resolved=False).count() == 3
    assert db_session.query(WatchlistSnapshotItem).filter_by(run_id=recovered['id'], symbol='000002').one().captured_at == retained
    stored = json.dumps(service.error_details(db_session, failed['id'])) + caplog.text
    assert all(secret not in stored for secret in ('PRIVATE', '87654321', 'private.invalid'))


def test_persistent_transient_exhausts_three_recoveries_and_restart_cannot_reset(tmp_path, db_session):
    service, client, clock = make_service(tmp_path)
    client.faults['quote', '000001'] = 100
    first = service.refresh(db_session)
    for attempt in range(1, 4):
        result = due(service, db_session, clock)
        assert result['status'] == 'failed' and result['recovery']['attempts'] == attempt
    assert result['recovery']['status'] == 'exhausted'
    assert result['recovery']['recovery_read_calls'] == 9
    assert db_session.query(WatchlistSnapshotRun).count() == 4
    before = len(client.reads)
    # Simulate bootstrap on a restarted scheduler with no successful snapshot.
    class SessionContext:
        def __enter__(self): return db_session
        def __exit__(self, *args): return False
    scheduler = WatchlistSnapshotScheduler(service, session_factory=SessionContext, now_provider=clock.now)
    scheduler._bootstrap_if_needed()
    assert len(client.reads) == before
    assert service.recover_due(db_session) is None
    assert db_session.get(WatchlistSnapshotRun, first['id']).status == 'failed'


@pytest.mark.parametrize('limit', ['deadline', 'reads'])
def test_durable_deadline_and_read_budget_stop_new_attempts(tmp_path, db_session, limit):
    service, client, clock = make_service(tmp_path, count=2)
    client.faults['quote', '000001'] = 3
    service.refresh(db_session)
    job = service.latest_recovery(db_session)
    if limit == 'deadline':
        clock.advance((job.deadline_at.replace(tzinfo=UTC) - clock.now()).total_seconds())
    else:
        job.recovery_read_calls = 60
        db_session.commit()
        clock.advance(15)
    before = len(client.reads)
    assert service.recover_due(db_session)['status'] == 'recovery_exhausted'
    assert len(client.reads) == before
    assert db_session.query(WatchlistSnapshotRun).count() == 1


def test_recovery_read_budget_is_enforced_mid_attempt(tmp_path, db_session):
    service, client, clock = make_service(tmp_path, count=2)
    client.faults['quote', '000001'] = 100
    service.refresh(db_session)
    job = service.latest_recovery(db_session)
    job.recovery_read_calls = 59
    db_session.commit()
    before = len(client.reads)
    result = due(service, db_session, clock)
    assert result['status'] == 'failed' and result['recovery']['status'] == 'exhausted'
    assert result['recovery']['recovery_read_calls'] == 60
    assert len(client.reads) == before + 1


def test_auth_failure_is_not_retried_or_exposed(tmp_path, db_session):
    service, client, clock = make_service(tmp_path, count=2)
    client.faults['quote', '000001'] = 100
    client.failure = lambda: RuntimeError('HTTP 401 account=87654321 token=PRIVATE')
    result = service.refresh(db_session)
    assert result['status'] == 'failed' and result['recovery']['status'] == 'blocked'
    primary = [error for error in service.error_details(db_session, result['id']) if error['stage'] == 'quote']
    assert len(primary) == 1 and primary[0]['reason_code'] == 'provider_auth_rejected'
    assert due(service, db_session, clock) is None


@pytest.mark.parametrize('stage', ['indicator', 'exception'])
def test_indicator_and_quant_exceptions_record_symbol_and_stage(tmp_path, db_session, stage):
    service, client, clock = make_service(tmp_path, count=1)
    class Broken:
        def calculate(self, *args, **kwargs): raise ValueError('SECRET')
        def score(self, *args, **kwargs): raise ValueError('SECRET')
    if stage == 'indicator': service.indicator_service = Broken()
    else: service.quant_signal_service = Broken()
    result = service.refresh(db_session)
    error = service.error_details(db_session, result['id'])[0]
    assert error['stage'] == stage and error['symbol'] == '000001'
    assert 'SECRET' not in json.dumps(error)


def test_active_database_claim_prevents_other_process_refresh(tmp_path, db_session):
    service, client, clock = make_service(tmp_path, count=1)
    db_session.add(WatchlistSnapshotRefreshClaim(market='KR', token='another-process',
        expires_at=clock.now().replace(tzinfo=None) + timedelta(seconds=600)))
    db_session.commit()
    assert service.refresh(db_session)['status'] == 'already_running'
    assert client.reads == [] and db_session.query(WatchlistSnapshotRun).count() == 0


def test_expired_worker_lease_recovers_persisted_partial_data(tmp_path, db_session):
    service, client, clock = make_service(tmp_path, count=2)
    client.faults['quote', '000001'] = 3
    failed = service.refresh(db_session)
    # Persisted state of a worker killed before its final status transaction.
    run = db_session.get(WatchlistSnapshotRun, failed['id'])
    run.status, run.completed_at = 'running', None
    job = service.latest_recovery(db_session)
    job.status = 'building'
    db_session.add(WatchlistSnapshotRefreshClaim(market='KR', token='crashed-worker',
        run_id=run.id, expires_at=clock.now().replace(tzinfo=None) - timedelta(seconds=1)))
    db_session.commit()
    clock.advance(15)
    # Fresh service instance shares only the database checkpoint.
    restarted = WatchlistSnapshotService(client=client, universe_path=service.universe_path,
        indicator_service=service.indicator_service, quant_signal_service=service.quant_signal_service,
        now_provider=clock.now, wait_provider=clock.wait, monotonic_provider=lambda: clock.elapsed)
    result = restarted.recover_due(db_session)
    assert result['status'] == 'success' and result['recovery']['attempts'] == 1
    assert db_session.get(WatchlistSnapshotRun, failed['id']).status == 'failed'
    assert db_session.query(WatchlistSnapshotError).filter_by(reason_code='worker_interrupted').count() == 1
    assert db_session.get(WatchlistSnapshotRefreshClaim, 'KR') is None


def test_late_worker_cannot_publish_or_delete_replacement_claim(tmp_path, db_session):
    service, client, clock = make_service(tmp_path, count=1)
    def steal(stage, symbol):
        db_session.query(WatchlistSnapshotRefreshClaim).update({'token': 'replacement'})
        db_session.commit()
    client.after_read = steal
    result = service.refresh(db_session)
    assert result['reason_code'] == 'snapshot_lease_lost'
    assert db_session.query(WatchlistSnapshotRun).one().status != 'success'
    assert db_session.get(WatchlistSnapshotRefreshClaim, 'KR').token == 'replacement'


def test_timed_out_read_cannot_mark_snapshot_success(tmp_path, db_session):
    service, client, clock = make_service(tmp_path, count=1)
    client.after_read = lambda *_: clock.advance(481)
    result = service.refresh(db_session)
    assert result['status'] == 'failed' and result['error_count'] > 0
    assert len(client.reads) == 1
    assert db_session.get(WatchlistSnapshotRefreshClaim, 'KR') is None


def test_cancel_stops_reads_and_releases_claim(tmp_path, db_session):
    service, client, clock = make_service(tmp_path, count=1)
    cancel = threading.Event()
    cancel.set()
    result = service.refresh(db_session, cancel_event=cancel)
    assert result['status'] == 'failed' and not client.reads
    assert result['recovery']['status'] == 'pending'
    assert db_session.get(WatchlistSnapshotRefreshClaim, 'KR') is None


def test_universe_change_blocks_reusing_incompatible_scores(tmp_path, db_session):
    service, client, clock = make_service(tmp_path, count=2)
    client.faults['quote', '000001'] = 3
    service.refresh(db_session)
    _write_universe(service.universe_path, kospi=3, kosdaq=0)
    before = len(client.reads)
    assert due(service, db_session, clock)['status'] == 'recovery_blocked'
    assert len(client.reads) == before


def test_untrusted_adapter_diagnostics_are_allowlisted():
    result = sanitize_snapshot_error({'stage': 'SECRET', 'reason_code': 'transport_timeout',
        'exception_type': 'SECRET', 'http_status': 'SECRET', 'message': 'PRIVATE',
        'retryable': True}, stage='quote')
    assert result == {'stage': 'quote', 'reason_code': 'transport_timeout',
        'exception_type': 'UnknownError', 'http_status': None, 'retryable': True}
    assert safe_snapshot_error(RuntimeError('HTTP 429 SECRET'), stage='daily')['retryable']


def test_stale_healthy_item_is_fetched_again_in_recovery(tmp_path, db_session):
    service, client, clock = make_service(tmp_path, count=3)
    client.faults['quote', '000001'] = 3
    failed = service.refresh(db_session)
    row = db_session.query(WatchlistSnapshotItem).filter_by(run_id=failed['id'], symbol='000002').one()
    row.captured_at = clock.now().replace(tzinfo=None) - timedelta(seconds=901)
    db_session.commit()
    before = len(client.reads)
    result = due(service, db_session, clock)
    assert result['status'] == 'success'
    assert [(stage, symbol) for stage, symbol, _ in client.reads[before:]] == [
        ('quote', '000001'), ('quote', '000002')]


def test_poll_loop_recovers_without_waiting_for_regular_slot(tmp_path, db_session):
    service, client, clock = make_service(tmp_path, count=2)
    client.faults['quote', '000001'] = 3
    service.refresh(db_session)
    class SessionContext:
        def __enter__(self): return db_session
        def __exit__(self, *args): return False
    scheduler = WatchlistSnapshotScheduler(service, session_factory=SessionContext, now_provider=clock.now)
    polls = []
    def tick(seconds):
        polls.append(seconds)
        assert len(polls) <= 3
        clock.wait(seconds)
        if service.latest_recovery(db_session).status == 'succeeded':
            scheduler._stop_event.set()
    scheduler._stop_event.wait = tick
    scheduler._run()
    assert service.latest_run(db_session).status == 'success'
    assert service.latest_recovery(db_session).attempts == 1


def test_bootstrap_recovers_failed_latest_even_with_fresh_older_success(tmp_path, db_session):
    service, client, clock = make_service(tmp_path, count=2)
    assert service.refresh(db_session)['status'] == 'success'
    clock.advance(1)
    client.faults['quote', '000001'] = 3
    assert service.refresh(db_session)['status'] == 'failed'
    clock.advance(15)
    class SessionContext:
        def __enter__(self): return db_session
        def __exit__(self, *args): return False
    WatchlistSnapshotScheduler(service, session_factory=SessionContext,
        now_provider=clock.now)._bootstrap_if_needed()
    assert service.latest_run(db_session).status == 'success'
    assert service.latest_recovery(db_session).attempts == 1


def test_daily_timeout_records_unavailable_indicators_and_then_recovers(tmp_path, db_session):
    from app.services.technical_indicator_service import TechnicalIndicatorService
    service, client, clock = make_service(tmp_path, count=1)
    service.indicator_service = TechnicalIndicatorService()
    client.faults['daily', '000001'] = 1
    result = service.refresh(db_session)
    assert result['status'] == 'success'
    errors = service.error_details(db_session, result['id'])
    assert {(error['stage'], error['reason_code']) for error in errors} == {
        ('daily', 'transport_timeout'), ('indicator', 'indicator_input_unavailable')}
    assert all(error['resolved'] and error['retryable'] for error in errors)


def test_restart_after_deadline_finalizes_interrupted_run_without_reads(tmp_path, db_session):
    service, client, clock = make_service(tmp_path, count=1)
    client.faults['quote', '000001'] = 3
    result = service.refresh(db_session)
    run = db_session.get(WatchlistSnapshotRun, result['id'])
    run.status, run.completed_at = 'running', None
    service.latest_recovery(db_session).status = 'building'
    db_session.commit()
    clock.advance(901)
    before = len(client.reads)
    assert service.recover_due(db_session)['status'] == 'recovery_exhausted'
    assert run.status == 'failed' and run.completed_at is not None
    assert len(client.reads) == before


def test_bootstrap_still_refreshes_an_old_successful_snapshot(tmp_path, db_session):
    service, client, clock = make_service(tmp_path, count=1)
    first = service.refresh(db_session)
    clock.advance(7201)
    class SessionContext:
        def __enter__(self): return db_session
        def __exit__(self, *args): return False
    WatchlistSnapshotScheduler(service, session_factory=SessionContext,
        now_provider=clock.now)._bootstrap_if_needed()
    assert service.latest_run(db_session).id != first['id']
    assert service.latest_run(db_session).status == 'success'


def test_stopping_busy_scheduler_retains_thread_until_it_exits():
    entered, release = threading.Event(), threading.Event()
    class BusyService:
        def latest_successful_run(self, *args, **kwargs): return None
        def refresh(self, *args, **kwargs):
            entered.set()
            assert release.wait(10)
            return {'status': 'failed'}
    class SessionContext:
        def __enter__(self): return self
        def __exit__(self, *args): return False
    scheduler = WatchlistSnapshotScheduler(BusyService(), session_factory=SessionContext,
        now_provider=lambda: Clock().now())
    scheduler.start()
    thread = scheduler._thread
    try:
        assert entered.wait(2)
        scheduler.stop()
        scheduler.start()
        assert scheduler._thread is thread and scheduler._stop_event.is_set()
    finally:
        release.set()
        thread.join(2)
        scheduler.stop()
    assert not thread.is_alive()


@pytest.mark.parametrize('cap,expected_gets', [(1, 1), (2, 2)])
def test_actual_read_send_hook_counts_token_retry_and_enforces_budget(monkeypatch, cap, expected_gets):
    """Inherited transport under a FakeKisClient, both HTTP/auth fully fake."""
    from types import SimpleNamespace
    from app.brokers.kis_client import KisClient
    from app.config import Settings
    clock, sent, reserved = Clock(), [], []
    class TransportFakeKisClient(KisClient):
        def build_headers(self, **kwargs): return {}
        def _token_refresh_guard_diagnostics(self): return True, {}
    client = TransportFakeKisClient(settings=Settings(_env_file=None,
        kis_enabled=False, kis_env='demo', kis_base_url='https://fake.invalid'),
        auth_manager=SimpleNamespace(refresh_access_token_for_expired_api_token=lambda: SimpleNamespace(token='FAKE')))
    def fake_get(*args, **kwargs):
        sent.append(clock.elapsed)
        body = {'rt_cd': '1', 'msg_cd': 'EGW00123'} if len(sent) == 1 else {'rt_cd': '0'}
        return SimpleNamespace(status_code=200, json=lambda: body)
    monkeypatch.setattr('app.brokers.kis_client.requests.get', fake_get)
    def reserve():
        if len(reserved) >= cap:
            raise SnapshotReadStopped('snapshot_read_budget_exhausted')
        reserved.append(True)
    budget = SnapshotReadBudget(checkpoint=lambda: None, reserve=reserve,
        wait=clock.wait, monotonic=lambda: clock.elapsed)
    with snapshot_read_budget(budget):
        if cap == 1:
            with pytest.raises(SnapshotReadStopped, match='snapshot_read_budget_exhausted'):
                client.request_get('/fake-read', tr_id='FAKE')
        else:
            assert client.request_get('/fake-read', tr_id='FAKE')['rt_cd'] == '0'
    assert len(sent) == len(reserved) == expected_gets
    if len(sent) == 2:
        assert sent[1] - sent[0] >= 1
