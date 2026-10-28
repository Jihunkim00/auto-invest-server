"""Production-DB replay. Never starts a live scheduler or external transport.

Absent production evidence is NOT REPRODUCIBLE, never silently synthetic.
See support/production_replay_oct28.py for the raw-OHLCV limitation.
"""
import json
import logging
import os
from pathlib import Path
import threading
from datetime import UTC

import pytest

from app.db.models import AutomationProfileBuyReservation, AutomationSchedulerSlot, OrderLog, WatchlistSnapshotRun, WatchlistSnapshotItem
from app.services.kis_daily_entry_accounting import daily_entry_counts
from app.services.scheduler_task_supervisor import check_scheduler_buy_allowed
from app.tests.support.production_replay_oct28 import Evidence, Replay, ROOT, at, parsed


@pytest.fixture(scope='module')
def evidence(tmp_path_factory):
    source = Path(os.environ.get('PR140_REPLAY_SOURCE_DB', ROOT / 'auto_invest.db'))
    if not source.is_file():
        pytest.skip('NOT REPRODUCIBLE: October 28 production DB is unavailable')
    value = Evidence(source, tmp_path_factory.mktemp('pr140-production-backup'))
    yield value
    integrity = value.verify_unchanged()
    target = ROOT / '.tmp' / 'pr140-production-replay'
    target.mkdir(parents=True, exist_ok=True)
    worker = os.environ.get('PYTEST_XDIST_WORKER', 'main')
    (target / f'integrity-{worker}.json').write_text(json.dumps(integrity, indent=2), encoding='utf-8')


@pytest.fixture
def replay(evidence, tmp_path, monkeypatch, request):
    counters = {'external_http': 0, 'real_kis_submit': 0, 'real_alpaca_submit': 0}
    def forbidden(*args, **kwargs):
        counters['external_http'] += 1
        pytest.fail('Production replay forbids external HTTP, including order/cancel/replace')
    def real_submit(*args, **kwargs):
        counters['real_kis_submit'] += 1
        pytest.fail('Production KIS submit is forbidden')
    def real_alpaca_submit(*args, **kwargs):
        counters['real_alpaca_submit'] += 1
        pytest.fail('Production Alpaca submit is forbidden')
    monkeypatch.setattr('requests.sessions.Session.request', forbidden)
    monkeypatch.setattr('httpx.Client.send', forbidden)
    monkeypatch.setattr('httpx.AsyncClient.send', forbidden)
    monkeypatch.setattr('socket.create_connection', forbidden)
    monkeypatch.setattr('app.brokers.kis_client.KisClient.submit_domestic_cash_order', real_submit)
    monkeypatch.setattr('app.brokers.kis_client.KisClient.cancel_domestic_cash_order', real_submit)
    monkeypatch.setattr('app.services.user_broker_account_service.UserKisLiveTradingClient.submit_market_buy_qty', real_submit)
    monkeypatch.setattr('app.services.user_broker_account_service.UserKisLiveTradingClient.submit_market_sell_qty', real_submit)
    monkeypatch.setattr('app.brokers.alpaca_client.AlpacaClient.submit_market_buy', real_alpaca_submit)
    monkeypatch.setattr('app.brokers.alpaca_client.AlpacaClient.submit_market_buy_qty', real_alpaca_submit)
    monkeypatch.setattr('app.brokers.alpaca_client.AlpacaClient.submit_market_sell', real_alpaca_submit)
    monkeypatch.setattr(logging.FileHandler, 'emit', lambda *args: None)
    value = Replay(evidence, tmp_path / 'isolated-replay.db', monkeypatch)
    value.preview.hook = value.stage
    yield value
    value.close()
    assert counters == {'external_http': 0, 'real_kis_submit': 0, 'real_alpaca_submit': 0}
    evidence.verify_unchanged()
    target = ROOT / '.tmp' / 'pr140-production-replay'
    target.mkdir(parents=True, exist_ok=True)
    # Export only explicit public facts. Never dump result/response/DB rows.
    rows = [{k: v for k, v in row.items() if k != 'result'} for row in value.results]
    report = {'scenario': request.node.name, 'rows': rows, 'transport': counters,
        'source': 'SQLite backup of October 28 production DB',
        'raw_ohlcv_recalculation': 'NOT REPRODUCIBLE: source bars were not persisted',
        'historical_C': 'persisted C results replayed; C/GPT/Final gates use production code'}
    (target / f'{request.node.name}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


def test_a_recorded_admin_buy_finishes_at_1123_and_fills_once(replay):
    r = replay
    result = r.slot('11:20')
    assert len(r.broker.calls) == 1, {k: v for k, v in result.items() if k != 'result'}
    assert r.broker.calls[0] == {'symbol': '036460', 'qty': 7}
    assert result['order_status'] == 'FILLED'
    assert result['daily_entries_used'] == 1
    assert result['risk'] == 'approved' and result['buy_window'] == 'allowed'
    with r.sessions() as db:
        order = db.query(OrderLog).filter(OrderLog.created_at >= at('11:20:00').astimezone(UTC)).one()
        assert order.kis_odno.startswith('FAKE-REPLAY-')
        assert db.query(AutomationProfileBuyReservation).filter_by(order_id=order.id).one().status == 'filled'
    selected = r.preview.last['final_best_candidate']
    assert [selected[k] for k in ('quant_buy_score', 'quant_c_score', 'ai_buy_score', 'final_buy_score')] == [72., 69.09, 61., 67.07]
    assert r.clock.now() == at('11:23:00')


@pytest.mark.parametrize('fault', ['window', 'kill', 'account', 'validation', 'closed', 'cutoff', 'preparation'])
def test_b_pre_submit_failures_leave_no_requested_or_occupied_capacity(replay, monkeypatch, fault):
    r = replay
    validate = r.validation.validate
    def failed(request, **kwargs):
        if fault == 'validation':
            monkeypatch.setattr(r.client, 'get_domestic_stock_price', lambda *_: {'current_price': None})
        if fault == 'cutoff':
            r.clock.current = at('14:00:00')
        response = validate(request, **kwargs)
        if fault == 'window':
            r.clock.current = at('11:31:00')
        elif fault == 'kill':
            with r.sessions() as db:
                r.runtime.update_settings(db, {'kill_switch': True})
        elif fault == 'account':
            r.client.failure = 'account'
        elif fault == 'closed':
            r.market.force_closed = True
        elif fault == 'preparation':
            def unavailable(**kwargs):
                raise ConnectionError('pre-dispatch preparation failed')
            monkeypatch.setattr(r.client, 'get_domestic_possible_order', unavailable)
        return response
    monkeypatch.setattr(r.validation, 'validate', failed)
    row = r.slot('11:20')
    assert r.broker.calls == []
    assert row['order_status'] == 'REJECTED_BY_SAFETY_GATE', {k: v for k, v in row.items() if k != 'result'}
    assert row['daily_entries_used'] == row['unresolved_entry_count'] == 0
    with r.sessions() as db:
        reservation = db.query(AutomationProfileBuyReservation).filter_by(trade_date_kst='2026-10-28').one()
        assert reservation.status == 'blocked'
        response = parsed(db.get(OrderLog, reservation.order_id).response_payload)
        assert response['broker_submit_called'] is response['real_order_submitted'] is False
        assert not db.query(OrderLog).filter_by(internal_status='REQUESTED').count()


@pytest.mark.parametrize('first', ['filled', 'blocked', 'unknown', 'submitted'])
def test_c_1220_uses_actual_fills_and_retains_unresolved_risk(replay, monkeypatch, first):
    r = replay
    r.broker.mode = 'filled' if first == 'blocked' else first
    validate = r.validation.validate
    if first == 'blocked':
        def fail(request, **kwargs):
            raise ConnectionError('pre-broker validation transport unavailable')
        monkeypatch.setattr(r.validation, 'validate', fail)
    one = r.slot('11:20')
    with r.sessions() as db:
        reservation = db.query(AutomationProfileBuyReservation).filter_by(trade_date_kst='2026-10-28').one()
        assert reservation.status == {'filled': 'filled', 'blocked': 'blocked', 'unknown': 'sync_required', 'submitted': 'submitted'}[first]
        response = parsed(db.get(OrderLog, reservation.order_id).response_payload)
        assert response['broker_submit_called'] is (first != 'blocked')
    monkeypatch.setattr(r.validation, 'validate', validate)
    r.broker.mode = 'filled'
    r.import_snapshot(228)
    two = r.slot('12:20')
    if first == 'blocked':
        assert one['daily_entries_used'] == one['unresolved_entry_count'] == 0
        assert len(r.broker.calls) == 1 and two['order_status'] == 'FILLED', two['block_reason']
    elif first == 'filled':
        assert one['daily_entries_used'] == two['daily_entries_used'] == 1
        assert len(r.broker.calls) == 1
    else:
        assert one['daily_entries_used'] == two['daily_entries_used'] == 0
        assert one['unresolved_entry_count'] == two['unresolved_entry_count'] == 1
        assert len(r.broker.calls) == 1
        assert two['order_status'] == ('UNKNOWN_STALE' if first == 'unknown' else 'SUBMITTED')


def test_d_failed_229_blocks_both_accounts_and_does_not_auto_recover(replay):
    r = replay
    r.import_snapshot(228)
    r.import_snapshot(229)
    from app.services.watchlist_snapshot_scheduler import WatchlistSnapshotScheduler
    from app.services.watchlist_snapshot_service import WatchlistSnapshotService
    r.clock.current = at('13:25:00')
    refresh = WatchlistSnapshotScheduler(service=WatchlistSnapshotService(client=r.client),
        session_factory=r.sessions, now_provider=r.clock.now)
    refresh._stop_event.wait = lambda *_: refresh._stop_event.set()
    refresh._run()  # Real bootstrap + one real scheduling iteration, virtual time.
    admin = r.slot('13:30')
    user = r.slot('13:45', user=True)
    assert admin['block_reason'] == 'watchlist_snapshot_not_ready'
    assert user['block_reason'] == 'user_scheduler_processing_failed'
    assert user['root_reason'] == 'watchlist_snapshot_not_ready'
    assert not r.broker.calls
    assert not r.preview.calls and not r.user_preview.calls
    with r.sessions() as db:
        assert db.get(WatchlistSnapshotRun, 229).status == 'failed'
        assert not db.query(WatchlistSnapshotRun).filter(WatchlistSnapshotRun.id > 229).count()
    # The actual later success at 13:53 cannot replay either failed old slot.
    r.import_snapshot(230)
    r.clock.current = at('13:53:30')
    r.scheduler._plan_admin_slots(r.clock.now())
    r.scheduler._plan_user_slots(r.clock.now())
    r.drain()
    assert not r.preview.calls and not r.user_preview.calls
    # Capability result: NOT IMPLEMENTED. This assertion proves absence,
    # rather than labelling fail-closed or a hand-added snapshot auto-recovery.


def test_d_new_valid_snapshot_allows_analysis_without_relabeling_229(replay):
    r = replay
    r.import_snapshot(228)
    r.import_snapshot(229)
    new_id = r.import_snapshot(230, recovered_at=at('13:25:00'))
    assert new_id > 229
    admin = r.slot('13:30')
    user = r.slot('13:45', user=True)
    assert r.preview.calls == ['13:30']
    assert r.user_preview.calls == ['13:45']
    assert admin['block_reason'] != 'watchlist_snapshot_not_ready'
    assert user['root_reason'] != 'watchlist_snapshot_not_ready'
    assert not r.broker.calls
    with r.sessions() as db:
        assert db.get(WatchlistSnapshotRun, 229).status == 'failed'
        new = db.get(WatchlistSnapshotRun, new_id)
        assert (new.status, new.source_count, new.scored_count, new.error_count) == ('success', 200, 200, 0)
        from app.services.technical_indicator_service import indicator_payload_is_quant_ready
        from app.services.quant_signal_service import QuantSignalService
        items = db.query(WatchlistSnapshotItem).filter_by(run_id=new_id).all()
        assert len(items) == 200
        for item in items:
            indicators = parsed(item.indicators_json)
            assert indicator_payload_is_quant_ready(indicators)
            assert QuantSignalService().score(indicators, gate_level=2)['quant_buy_score'] == item.quant_buy_score


def test_e_all_six_real_slots_preserve_account_isolation(replay):
    r = replay
    r.broker.mode = 'unknown'
    for slot, user in [('11:20', False), ('11:30', True), ('12:20', False),
                       ('12:45', True), ('13:30', False), ('13:45', True)]:
        if slot == '12:20':
            r.import_snapshot(228)
        if slot == '13:30':
            r.import_snapshot(229)
        result = r.slot(slot, user=user)
        if user:
            assert result['daily_entries_used'] == 0
            assert result['unresolved_entry_count'] == result['unresolved_entry_count_before'] == 1
    assert len(r.results) == 6
    assert len(r.broker.calls) == 1
    assert r.results[2]['unresolved_entry_count'] == 1
    assert r.results[-1]['root_reason'] == 'watchlist_snapshot_not_ready'


def test_e_real_parallel_lanes_keep_test01_running_during_admin_timeout(replay):
    r = replay
    entered, release = threading.Event(), threading.Event()
    def slow(slot):
        entered.set()
        assert release.wait(45)
    r.preview.hook = slow
    r.scheduler._plan_admin_slots(at('11:20:00'))
    assert entered.wait(5)
    try:
        r.clock.current = at('11:30:00')
        r.scheduler._plan_user_slots(r.clock.now())
        with r.scheduler._task_supervisor.lock:
            user_thread = r.scheduler._task_supervisor.tasks.get('account-user-2', {}).get('thread')
        if user_thread:
            user_thread.join(30)
            assert not user_thread.is_alive()
        with r.sessions() as db:
            user = db.query(AutomationSchedulerSlot).filter_by(account_key='user-2').filter(
                AutomationSchedulerSlot.scheduled_at == at('11:30:00').astimezone(UTC).replace(tzinfo=None)).one()
            assert user.status == 'HOLD', user.reason
        r.clock.current = at('11:32:00')
        assert any(task['expired'] for task in r.scheduler._task_supervisor.snapshot(r.clock.now()))
    finally:
        release.set()
        r.drain()
    assert not r.broker.calls
    with r.sessions() as db:
        assert daily_entry_counts(db, now=r.clock.now(), owner_user_id=2) == (0, 1)
        assert not db.query(OrderLog).filter_by(internal_status='REQUESTED').count()
        for account, slot, owner in [('admin', '11:20', None), ('test01', '11:30', 2)]:
            ledger = db.query(AutomationSchedulerSlot).filter_by(account_key='admin' if owner is None else 'user-2').filter(
                AutomationSchedulerSlot.scheduled_at == at(slot+':00').astimezone(UTC).replace(tzinfo=None)).one()
            filled, unresolved = daily_entry_counts(db, now=r.clock.now(), owner_user_id=owner)
            r.results.append({'account': account, 'slot': slot, 'slot_status': ledger.status,
                'block_reason': ledger.reason, 'watchlist': 'success',
                'buy_window': 'expired' if owner is None else 'allowed', 'ai_action': 'NOT RUN' if owner is None else 'HOLD',
                'risk': 'NOT RUN', 'fake_submit_count': 0, 'order_status': 'NOT SUBMITTED',
                'daily_entries_used': filled, 'unresolved_entry_count': unresolved,
                'actual_kis_submit_count': 0})
