"""Isolated October 21 reconstruction with real scoring, risk and lifecycle.

All transport is prohibited. Account reads, GPT and submission use fakes only.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet
import pytest

from app.config import get_settings
from app.db.database import SessionLocal
from app.db.models import (
    AutomationProfileAiCandidateResult, AutomationProfileWatchlistSnapshot, AutomationSchedulerSlot,
    OrderLog, PositionLifecycle, SignalLog, TradeRunLog, User, UserAutoTradingSlotClaim,
    UserTradingSettings,
    WatchlistSnapshotItem,
)
from app.services.broker_credential_crypto_service import BrokerCredentialCryptoService
from app.services.user_broker_account_service import (
    KIS_BALANCE_PATH, KIS_OPEN_ORDERS_PATH, UserBrokerAccountService,
    UserKisLiveTradingClient, UserKisTokenManager,
)
from app.services.user_broker_credential_service import UserBrokerCredentialService
from app.services.user_auto_trading_scheduler_service import UserAutoTradingCandidateService, UserAutoTradingSchedulerService
from app.services.user_trading_execution_service import UserTradingExecutionService
from app.services.kis_order_sync_service import KisOrderSyncService
from app.services.kis_watchlist_preview_service import KisPreviewGptAdvisor
from app.services.kr_market_context_service import KrMarketContextService
from app.services.market_data_snapshot_service import MarketDataSnapshotService
from app.services.scheduler_task_supervisor import scheduler_buy_guard
from app.tests.integration.test_pr138_full_pipeline_replay import (
    ClockSession, FakeResponses, RecordingPreview, setup_pipeline, synthetic_bars,
)
from app.tests.test_user_auto_trading_scheduler_pr129 import _user, _configure_user, _set_profile_schedule, FakeKisClient
from app.tests.test_user_broker_accounts import FakeBrokerHttp, FakeResponse

KST = ZoneInfo('Asia/Seoul')
NOW = datetime(2026, 10, 21, 11, 20, tzinfo=KST)


@pytest.fixture(autouse=True)
def no_network_or_real_submission(monkeypatch, fake_kis_admin_credentials):
    counters = {'actual_kis_submit_count': 0, 'external_network_count': 0}
    def forbidden(*args, **kwargs):
        counters['external_network_count'] += 1
        pytest.fail('Actual KIS/Alpaca/GPT transport is forbidden')
    def forbidden_submit(*args, **kwargs):
        counters['actual_kis_submit_count'] += 1
        pytest.fail('Actual KIS submit method is forbidden')
    monkeypatch.setattr('requests.sessions.Session.request', forbidden)
    monkeypatch.setattr('httpx.Client.send', forbidden)
    monkeypatch.setattr('httpx.AsyncClient.send', forbidden)
    monkeypatch.setattr('socket.create_connection', forbidden)
    monkeypatch.setattr('app.brokers.kis_client.KisClient.submit_domestic_cash_order', forbidden_submit)
    monkeypatch.setattr(UserKisLiveTradingClient, 'submit_market_buy_qty', forbidden_submit)
    monkeypatch.setattr(UserKisLiveTradingClient, 'submit_market_sell_qty', forbidden_submit)
    return counters


class EmptyAccountHttp(FakeBrokerHttp):
    def __init__(self, *, historical_sell=False):
        super().__init__()
        self.historical_sell = historical_sell

    def get(self, url, **kwargs):
        self.gets.append({'url': url, **kwargs})
        if url.endswith(KIS_BALANCE_PATH):
            return FakeResponse({'rt_cd': '0', 'output1': [], 'output2': {
                'dnca_tot_amt': '1000000', 'ord_psbl_cash': '1000000', 'tot_evlu_amt': '1000000'}})
        if url.endswith(KIS_OPEN_ORDERS_PATH):
            return FakeResponse({'rt_cd': '0', 'output': [{
                'odno': 'FAKE-PAST-1234', 'pdno': '005930', 'sll_buy_dvsn_cd': '01',
                'ord_qty': '2', 'tot_ccld_qty': '2', 'psbl_qty': '0'}] if self.historical_sell else []})
        raise AssertionError('Unexpected fake account endpoint')


class FillingUserClient(FakeKisClient):
    def __init__(self, user_id, clock):
        super().__init__()
        self.user_id = user_id
        self.clock = clock
        self.executions = {}

    def get_possible_buy_order(self, *, symbol, order_type='market'):
        self.possible_order_calls.append((symbol, order_type))
        return {'symbol': symbol, 'order_type': order_type, 'queried_at': self.clock.now().isoformat(),
                'nrcvb_buy_amt': 1000000, 'nrcvb_buy_qty': 95, 'psbl_qty_calc_unpr': 10442.02,
                'raw_status': 'ok'}

    def submit_market_buy_qty(self, *, symbol, qty):
        self.buy_calls.append((symbol, qty))
        order_id = f'FAKE-USER-{self.user_id}-1'
        self.executions[order_id] = {'ODNO': order_id, 'PDNO': symbol, 'ord_qty': qty,
            'tot_ccld_qty': qty, 'rmn_qty': 0, 'avg_prvs': 10442.02, 'status': 'filled'}
        return SimpleNamespace(id=order_id, status='submitted', filled_qty=0, filled_avg_price=None)

    def inquire_daily_order_executions(self, *, order_no, start_date, end_date):
        return {'orders': [self.executions[order_no]]}


def setup_user(db, monkeypatch, harness, name, *, score=70, failure=False, historical_sell=False):
    user = _user(db, name)
    # An unconfigured new user must not be enabled implicitly.
    assert db.query(UserTradingSettings).filter_by(user_id=user.id).count() == 0
    _configure_user(db, user, mode='live', live_enabled=True, kill_switch=False, confirmed=True)
    _set_profile_schedule(db, user, ['11:30'], fixed_budget=100000, max_order_notional=100000)
    profiles = harness.profiles
    profile = profiles.selected_owned_profile_schedule(db, owner_user_id=user.id, now=NOW)['profile']
    row = profiles.get_owned(db, profile['profile_key'], owner_user_id=user.id)
    values = json.loads(row.settings_json)
    values['universe'].update(watchlist_size=50, top_quant_candidates=5, top_ai_candidates=5,
        min_price_krw=1000, max_price_krw=50000, min_volume_ratio=0)
    row.settings_json = json.dumps(values)
    db.commit()
    crypto = BrokerCredentialCryptoService()
    credentials = UserBrokerCredentialService(crypto=crypto)
    credentials.save(db, user, 'kis', {'environment': 'live', 'app_key': f'fake-{name}-key',
        'app_secret': f'fake-{name}-secret', 'hts_id': f'fake-{name}',
        'account_no': f'{user.id:08d}', 'account_product_code': '01'})
    db.query(UserTradingSettings).filter_by(user_id=user.id).one().auto_live_confirmed_at = NOW
    db.commit()
    http = EmptyAccountHttp(historical_sell=historical_sell)
    account = UserBrokerAccountService(crypto=crypto, http_client=http, token_manager=UserKisTokenManager())
    sessions = ClockSession(harness.clock)
    responses = FakeResponses(score=score, failure=failure)
    preview = RecordingPreview(harness.client, session_service=sessions,
        gpt_advisor=KisPreviewGptAdvisor(settings=harness.client.settings, client=SimpleNamespace(responses=responses)),
        market_data_snapshot_service=MarketDataSnapshotService(harness.client, now_provider=harness.clock.now),
        market_context_service=KrMarketContextService(harness.client, alpaca_client=SimpleNamespace(), now_factory=harness.clock.now))
    client = FillingUserClient(user.id, harness.clock)
    execution = UserTradingExecutionService(account_service=account, credential_service=credentials,
        session_service=sessions, kis_live_client_factory=lambda *_: client, now_provider=harness.clock.now)
    scheduler = UserAutoTradingSchedulerService(execution_service=execution, account_service=account,
        candidate_service=UserAutoTradingCandidateService(runtime_preview_service=preview),
        now_provider=harness.clock.now, session_service=sessions, automation_profiles=profiles)
    return SimpleNamespace(user_id=user.id, scheduler=scheduler, preview=preview, responses=responses,
                           client=client, account=account, http=http, profile_id=profile['id'])


def run_user(state, clock):
    with SessionLocal() as db:
        aggregate = state.scheduler.run_provider_once(db, provider='kis', scheduler_slot='11:30',
            owner_user_id=state.user_id, now=clock.now())
        item = next(value for value in aggregate['items'] if value.get('owner_user_id') == state.user_id)
        if item.get('order_id') and item.get('result') == 'submitted':
            order = KisOrderSyncService(state.client, now_provider=clock.now).sync_order(db, item['order_id'])
            UserTradingExecutionService._maybe_create_position_lifecycle(db,
                user=db.get(User, state.user_id), order=order, now=clock.now())
        return item


def setup_all(db, monkeypatch, **kwargs):
    monkeypatch.setattr(get_settings(), 'broker_credential_master_key', Fernet.generate_key().decode())
    harness, scheduler, preview, responses, snapshot = setup_pipeline(db, monkeypatch, start_at=NOW)
    daily, minutes = synthetic_bars(NOW)
    harness.client.get_domestic_daily_bars = lambda symbol, limit=120: daily[-limit:]
    harness.client.get_domestic_intraday_bars = lambda symbol, **kw: [dict(row,
        timestamp=(datetime.fromisoformat(row['timestamp']) + (harness.clock.now() - NOW)).isoformat())
        for row in minutes]
    first = setup_user(db, monkeypatch, harness, 'test01', historical_sell=True, **kwargs)
    second = setup_user(db, monkeypatch, harness, 'test02')
    return harness, scheduler, preview, responses, snapshot, first, second


def test_three_accounts_finish_independent_real_pipeline(monkeypatch, tmp_path, no_network_or_real_submission):
    with SessionLocal() as db:
        harness, admin, preview, responses, snapshot, first, second = setup_all(db, monkeypatch)
    admin_timings = {}
    def observe(target, method_name, stage):
        original = getattr(target, method_name)
        def measured(*args, **kwargs):
            started = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                admin_timings[stage] = admin_timings.get(stage, 0) + (time.perf_counter() - started) * 1000
        monkeypatch.setattr(target, method_name, measured)
    observe(harness.client, 'get_account_balance', 'account_snapshot')
    observe(harness.client, 'list_positions', 'account_snapshot')
    observe(harness.profile_buy, '_position_priority', 'position_management')
    dry_run = harness.strategy_scheduler.dry_run_service
    observe(dry_run.profile_watchlists, 'build', 'profile_watchlist')
    for risk in {id(service): service for service in (
            dry_run.target_risk_service, harness.profile_buy.target_risk_service)}.values():
        observe(risk, 'evaluate_entry', 'risk_engine')
    admin_started = time.perf_counter()
    admin._plan_admin_slots(NOW)
    with admin._task_supervisor.lock:
        workers = list(admin._task_supervisor.tasks.values())
    for task in workers:
        task['thread'].join(30)
        assert not task['thread'].is_alive()
    admin_timings['total'] = (time.perf_counter() - admin_started) * 1000
    for stage, key in (('a_quant', 'a_quant_scan_ms'), ('c_quant', 'c_shadow_scan_ms'),
                       ('gpt', 'gpt_total_ms'), ('final_ranking', 'final_ranking_ms')):
        admin_timings[stage] = preview.result['performance'][key]
    assert {'account_snapshot', 'position_management', 'profile_watchlist', 'risk_engine'} <= admin_timings.keys()
    harness.clock.current = NOW.replace(minute=30)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda state: run_user(state, harness.clock), [first, second]))
    assert all(result.get('result') == 'submitted' for result in results), json.dumps([
        {key: result.get(key) for key in ('result', 'reason', 'failure_stage', 'exception_type', 'sanitized_error')}
        for result in results])
    records = []
    with SessionLocal() as db:
        assert db.query(OrderLog).count() == 3
        assert db.query(PositionLifecycle).filter_by(status='open').count() == 3
        assert {row.owner_user_id for row in db.query(OrderLog).all()} == {None, first.user_id, second.user_id}
        assert len(harness.broker.buy_calls) == 1
        assert harness.validation.calls and harness.validation.calls[0].validated_for_submission
        assert harness.client.external_kis_submit_count == 0
        assert no_network_or_real_submission == {'actual_kis_submit_count': 0, 'external_network_count': 0}
        for name, state, result, output, gpt_count in [
            ('admin', None, {}, preview.result, len(responses.calls)),
            ('test01', first, results[0], first.preview.result, len(first.responses.calls)),
            ('test02', second, results[1], second.preview.result, len(second.responses.calls))]:
            owner = state.user_id if state else None
            order = db.query(OrderLog).filter(OrderLog.owner_user_id == owner).one()
            assert order.internal_status == 'FILLED'
            assert 0 < order.qty * 10442.02 <= 100000
            assert db.query(PositionLifecycle).filter_by(owner_user_id=owner, entry_order_id=order.id).count() == 1
            profile_snapshot = db.query(AutomationProfileWatchlistSnapshot).filter_by(owner_user_id=owner).one()
            assert profile_snapshot.source_count == 200 and profile_snapshot.selected_count == 50
            top5 = [item for item in output['items'] if item.get('selected_by_a_top5')]
            assert len(top5) == gpt_count == 5
            assert all(item['quant_c_status'] == 'analyzed' and item['quant_c_score'] >= 65 for item in top5)
            selected = output['final_best_candidate']
            assert selected['ai_buy_score'] >= 60 and selected['final_buy_score'] >= 65
            audits = db.query(AutomationProfileAiCandidateResult).filter_by(owner_user_id=owner).all()
            assert len(audits) >= 5 and sum(row.final_selected for row in audits) == 1
            if state:
                assert len(state.client.buy_calls) == 1
                assert result['position_management']['action'] == 'entry_scan'
                assert result['position_management']['entry_blocked'] is False
                assert result['run_diagnostics']['stage_durations_ms']['risk_engine'] >= 0
                claim = db.query(UserAutoTradingSlotClaim).filter_by(user_id=owner).one()
                assert claim.status == 'completed'
                signal = db.get(SignalLog, db.get(TradeRunLog, result['run_id']).signal_id)
                assert signal.owner_user_id == owner and signal.approved_by_risk is True
            actual_submits = no_network_or_real_submission['actual_kis_submit_count']
            records.append({'account': name, 'simulation_only': True, 'real_order_submitted': bool(actual_submits),
                'actual_kis_submit_count': actual_submits, 'broker_submit_called': bool(actual_submits),
                'mock_submit_count': len(state.client.buy_calls) if state else len(harness.broker.buy_calls),
                'simulated_order_status': order.internal_status, 'watchlist': 200, 'profile': 50, 'a_top5': 5,
                'c65_passed': sum(item['quant_c_score'] >= 65 for item in top5), 'gpt_mock_completed': gpt_count,
                'selected_symbol': selected['symbol'], 'A': selected['quant_buy_score'], 'C': selected['quant_c_score'],
                'GPT': selected['ai_buy_score'], 'Final': selected['final_buy_score'], 'risk': 'APPROVED',
                'stage_durations_ms': result.get('run_diagnostics', {}).get('stage_durations_ms') or
                                      {key: round(value, 3) for key, value in admin_timings.items()},
                'stages': (result.get('run_diagnostics') or {}).get('stages') or {
                    'account_snapshot': 'COMPLETED', 'position_management': 'ENTRY_SCAN',
                    'profile_watchlist': 'COMPLETED', 'a_quant': 'COMPLETED', 'c_quant': 'COMPLETED',
                    'gpt': 'COMPLETED', 'final_ranking': 'COMPLETED', 'risk_engine': 'APPROVED'},
                'result': result.get('result', 'completed'), 'reason': result.get('reason'),
                'blocked_stage': (result.get('run_diagnostics') or {}).get('first_blocked_stage'),
                'thresholds': {'c_min': 65, 'gpt_min': 60, 'final_min': 65},
                'lineage': {key: output.get(key) for key in ('profile_snapshot_selected_symbols',
                    'runtime_input_symbols', 'runtime_quant_top5_symbols', 'gpt_target_symbols',
                    'gpt_completed_symbols', 'final_candidate_symbols', 'selected_final_symbol')},
                'candidates': [{
                    'symbol': item['symbol'], 'A': item.get('quant_buy_score'),
                    'C': item.get('quant_c_score'), 'C_status': item.get('quant_c_status', 'not_run'),
                    'GPT': item.get('ai_buy_score'), 'gpt_status': item.get('gpt_analysis_status'),
                    'Final': item.get('final_buy_score'),
                    'final_calculated': bool(item.get('gpt_used') and item.get('gpt_analysis_status') == 'completed'),
                    'selected_by_a_top5': bool(item.get('selected_by_a_top5')),
                    'final_selected': bool(item.get('final_selected')),
                    'block_reason': item.get('block_reason'),
                } for item in output['items']],
                'note': 'Mock transport counts; production execution flags describe its injected live client.'})
            assert len(records[-1]['candidates']) == 50
        for state in (first, second):
            # The same slot is consumed once, including after fake FILLED.
            again = state.scheduler.run_provider_once(db, provider='kis', scheduler_slot='11:30',
                owner_user_id=state.user_id, now=harness.clock.now())
            assert any(item.get('reason') == 'duplicate_scheduler_slot' for item in again['items'])
            assert len(state.client.buy_calls) == 1
        common_scores = [{'symbol': item.symbol, 'A_buy': item.quant_buy_score, 'A_sell': item.quant_sell_score}
            for item in db.query(WatchlistSnapshotItem).filter_by(run_id=snapshot['id']).all()]
        assert len(common_scores) == 200
    report = {'fixture_based_reconstruction': True, 'production_root_cause': 'root_cause_unconfirmed',
              'common_watchlist_scores': common_scores, 'accounts': records}
    (tmp_path / 'multi_account_result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PR138_MULTI_ACCOUNT_RESULT=' + json.dumps({
        'accounts': [{key: value for key, value in record.items() if key not in {'candidates', 'lineage'}}
                     for record in records], 'common_watchlist_score_count': len(common_scores)}, ensure_ascii=False))


@pytest.mark.parametrize('score,failure', [(59, False), (70, True)])
def test_one_users_gpt_failure_does_not_stop_other_account(monkeypatch, score, failure):
    with SessionLocal() as db:
        harness, _admin, _preview, _responses, _snapshot, first, second = setup_all(
            db, monkeypatch, score=score, failure=failure)
    harness.clock.current = NOW.replace(minute=30)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda state: run_user(state, harness.clock), [first, second]))
    assert not first.client.buy_calls
    assert len(second.client.buy_calls) == 1
    assert results[0]['result'].lower() in {'hold', 'blocked'}
    with SessionLocal() as db:
        assert db.query(OrderLog).filter_by(owner_user_id=first.user_id).count() == 0
        assert db.query(OrderLog).filter_by(owner_user_id=second.user_id, internal_status='FILLED').count() == 1


def test_admin_c65_regression_stops_before_any_gpt_or_order(monkeypatch):
    with SessionLocal() as db:
        harness, admin, preview, responses, _snapshot = setup_pipeline(db, monkeypatch, start_at=NOW)
    _daily, minutes = synthetic_bars(NOW)
    weak = [dict(row, open=11000-index*8, high=11003-index*8,
                 low=10997-index*8, close=11000-index*8, volume=10000)
            for index, row in enumerate(minutes)]
    harness.client.get_domestic_intraday_bars = lambda symbol, **kwargs: weak
    harness.client.get_domestic_stock_price = lambda symbol: {
        'symbol': symbol, 'current_price': weak[-1]['close'], 'previous_close': 11000}
    admin._plan_admin_slots(NOW)
    with admin._task_supervisor.lock:
        tasks = list(admin._task_supervisor.tasks.values())
    for task in tasks:
        task['thread'].join(30)
        assert not task['thread'].is_alive()
    top5 = [item for item in preview.result['items'] if item.get('selected_by_a_top5')]
    assert len(preview.result['runtime_input_symbols']) == 50
    assert len(top5) == 5
    assert all(item['quant_c_status'] == 'analyzed' and item['quant_c_score'] < 65 for item in top5)
    assert responses.calls == [] and harness.broker.buy_calls == []
    with SessionLocal() as db:
        ledger = db.query(AutomationSchedulerSlot).one()
        assert ledger.status in {'HOLD', 'blocked', 'completed'}
        assert db.query(OrderLog).count() == 0


@pytest.mark.parametrize('failure', ['daily_cap', 'market_closed', 'unreliable_snapshot', 'late_gpt'])
def test_user_fail_closed_and_late_response_cannot_submit(monkeypatch, failure):
    with SessionLocal() as db:
        harness, _admin, _preview, _responses, _snapshot, first, _second = setup_all(db, monkeypatch)
        harness.clock.current = NOW.replace(minute=30)
        if failure == 'daily_cap':
            settings = db.query(UserTradingSettings).filter_by(user_id=first.user_id).one()
            settings.max_daily_trades = 1
            db.add(OrderLog(owner_user_id=first.user_id, broker='kis', market='KR', symbol='999999',
                side='buy', order_type='market', qty=1, filled_qty=1, internal_status='FILLED',
                submitted_at=harness.clock.now(), filled_at=harness.clock.now(), notional=1000))
            db.commit()
        elif failure == 'market_closed':
            harness.clock.current = NOW.replace(hour=16, minute=0)
        elif failure == 'unreliable_snapshot':
            original = first.account.get_broker_snapshot
            first.account.get_broker_snapshot = lambda *args: {**original(*args), 'positions_reliable': False}
        else:
            original = first.responses.create
            def late(**kwargs):
                output = original(**kwargs)
                harness.clock.current = NOW.replace(minute=31, second=30)
                return output
            first.responses.create = late
    task = {'cancel': threading.Event(), 'deadline': time.monotonic() + 300, 'timeout': 300,
            'started_at': NOW.replace(minute=30), 'now_provider': harness.clock.now,
            'buy_deadline': time.monotonic() + 60, 'buy_expires_at': NOW.replace(minute=31)}
    with scheduler_buy_guard(task):
        result = run_user(first, harness.clock)
    assert first.client.buy_calls == []
    assert result.get('broker_submit_called') is False
    assert result['result'].lower() in {'hold', 'blocked', 'skipped', 'failed'}
    if failure == 'late_gpt':
        assert len(first.responses.calls) == 5
        assert result['reason'] == 'scheduler_task_expired_before_buy'
    with SessionLocal() as db:
        assert db.query(OrderLog).filter_by(owner_user_id=first.user_id).count() == (1 if failure == 'daily_cap' else 0)
