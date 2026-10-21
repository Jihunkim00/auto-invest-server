"""Real account risk and scheduler decisions; only external inputs are faked."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.db.database import SessionLocal
from app.db.models import OrderLog, PositionLifecycle, RuntimeSetting, SignalLog, StrategyProfile, TradeRunLog, User, UserTradingRiskState, UserTradingSettings
from app.tests.integration.test_pr138_multi_account_normalization import (
    NOW, setup_all, run_user, no_network_or_real_submission,
)

ACCOUNTS = ('admin', 'test01', 'test02')
CASES = ('c65', 'gpt60', 'final65', 'cash', 'position_pct', 'daily_cap', 'daily_loss',
         'account_kill', 'global_kill', 'duplicate', 'unverified_order', 'market_closed',
         'stale_snapshot', 'reentry', 'cutoff', 'bad_snapshot')
FIELDS = {'gate_name', 'stage', 'status', 'actual_value', 'required_value', 'reason_code',
          'reason_detail', 'owner_user_id', 'profile_id', 'scheduler_slot', 'checked_at', 'duration_ms'}


def setup_matrix(db, monkeypatch):
    harness, admin, preview, responses, snapshot, first, second = setup_all(db, monkeypatch)
    harness.clock.current = NOW.replace(minute=30)
    row = db.query(StrategyProfile).filter(StrategyProfile.owner_user_id.is_(None),
        StrategyProfile.profile_key == harness.profiles.selected_profile_schedule(db, now=NOW)['profile_key']).one()
    values = json.loads(row.settings_json)
    values['entry']['analysis_times'] = ['11:30']
    row.daily_max_loss_pct = -.02
    row.settings_json = json.dumps(values)
    db.commit()
    admin_state = SimpleNamespace(name='admin', user_id=None, profile_id=row.id, scheduler=admin,
        preview=preview, responses=responses, client=harness.client, buys=harness.broker.buy_calls,
        risk=harness.profile_buy.target_risk_service)
    first.name, second.name = 'test01', 'test02'
    for state in (first, second):
        state.buys = state.client.buy_calls
        state.risk = state.scheduler.execution_service.risk_service
    states = [admin_state, first, second]
    for state in states:
        method = 'evaluate_entry' if state.user_id is None else 'get_user_risk_state'
        spy = Mock(wraps=getattr(state.risk, method))
        monkeypatch.setattr(state.risk, method, spy)
        state.risk_spy = spy
    return harness, states, snapshot


def run(state, clock):
    return (state.scheduler.run_once(slot='11:30', now=clock.now()) if state.user_id is None
            else run_user(state, clock))


def profile_values(db, state, update):
    row = db.get(StrategyProfile, state.profile_id)
    values = json.loads(row.settings_json)
    update(values)
    row.settings_json = json.dumps(values)
    db.commit()
    return row


def filled(db, state, clock, *, symbol='999999', side='buy', price=10000, qty=1):
    profile = db.get(StrategyProfile, state.profile_id)
    row = OrderLog(owner_user_id=state.user_id, broker='kis', market='KR', currency='KRW',
        symbol=symbol, side=side, order_type='market', qty=qty, requested_qty=qty, filled_qty=qty,
        remaining_qty=0, notional=price*qty, avg_fill_price=price, filled_avg_price=price,
        internal_status='FILLED', broker_status='filled',
        created_at=clock.now()-timedelta(minutes=20 if side == 'buy' else 10),
        submitted_at=clock.now()-timedelta(minutes=20 if side == 'buy' else 10),
        filled_at=clock.now()-timedelta(minutes=20 if side == 'buy' else 10),
        request_payload=json.dumps({'provider': 'kis', 'market': 'KR', 'profile_key': profile.profile_key,
            'automation_profile': True, 'broker_account_id': 'admin:kis:KR' if state.user_id is None
             else f'user:{state.user_id}:kis:KR'}))
    db.add(row)
    db.commit()
    return row


def fake_snapshot(state, monkeypatch, change, harness):
    if state.user_id is None:
        original = state.scheduler._account_snapshot_preflight
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            change(result)
            return result
        monkeypatch.setattr(state.scheduler, '_account_snapshot_preflight', changed)
    else:
        original = state.account.get_broker_snapshot
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            change(result)
            return result
        monkeypatch.setattr(state.account, 'get_broker_snapshot', changed)


def inject(db, harness, state, case, monkeypatch):
    if case in {'c65', 'final65'}:
        # Fake OHLCV goes through the actual C calculator. No score method is mocked.
        def minutes(symbol, **kwargs):
            rows = []
            for index in range(150):
                price = 11000-index*8 if case == 'c65' else 10000+.001*index*index
                rows.append({'timestamp': (harness.clock.now().replace(hour=9, minute=0)+timedelta(minutes=index)).isoformat(),
                    'open': price-2, 'high': price+3, 'low': price-3, 'close': price,
                    'volume': 10000+index*50})
            return rows
        monkeypatch.setattr(harness.client, 'get_domestic_intraday_bars', minutes)
        monkeypatch.setattr(harness.client, 'get_domestic_stock_price', lambda symbol:
            {'symbol': symbol, 'current_price': minutes(symbol)[-1]['close'], 'previous_close': 11000})
        if case == 'final65':
            state.responses.score = 60
    elif case == 'gpt60':
        state.responses.score = 0  # An actual zero, never NOT_REACHED.
    elif case == 'cash':
        def no_cash(snapshot):
            account = snapshot.get('account') or snapshot['balance']
            for key in ('cash', 'buying_power', 'ord_psbl_cash', 'available_cash', 'orderable_cash'):
                account[key] = 0
        fake_snapshot(state, monkeypatch, no_cash, harness)
        if state.user_id is None:
            original = harness.client.get_account_balance
            monkeypatch.setattr(harness.client, 'get_account_balance', lambda: {
                **original(), 'cash': 0, 'ord_psbl_cash': 0, 'available_cash': 0, 'buying_power': 0, 'orderable_cash': 0})
    elif case == 'position_pct':
        profile_values(db, state, lambda v: v['capital'].update(sizing_mode='equity_pct',
            target_position_pct=.001, max_position_pct=.001))
    elif case in {'daily_cap', 'daily_loss', 'reentry'}:
        settings = db.query(UserTradingSettings).filter_by(user_id=state.user_id).first()
        if settings:
            settings.max_daily_trades = 1 if case == 'daily_cap' else 10
        if case != 'daily_cap':
            row = profile_values(db, state, lambda v: v['entry'].update(max_new_entries_per_day=10))
            row.max_trades_per_day = 10
            db.commit()
        if case == 'daily_loss':
            if state.user_id is None:
                filled(db, state, harness.clock, price=10000, qty=10)
                filled(db, state, harness.clock, side='sell', price=1000, qty=10)
            else:
                db.add(UserTradingRiskState(user_id=state.user_id, provider='kis', market='KR',
                    trading_date=harness.clock.now().date(), currency='KRW', daily_realized_pl=-30000,
                    daily_loss_pct=-.03, daily_trade_count=0))
        elif case == 'reentry':
            for symbol in ('000100', '000101', '000102', '000103', '000104'):
                filled(db, state, harness.clock, symbol=symbol)
        else:
            filled(db, state, harness.clock)
        db.commit()
    elif case == 'account_kill':
        owner = state.user_id or db.query(User).filter_by(role='admin').one().id
        settings = db.query(UserTradingSettings).filter_by(user_id=owner).first()
        if settings is None:
            settings = UserTradingSettings(user_id=owner, kill_switch=True)
            db.add(settings)
        settings.kill_switch = True
        db.commit()
    elif case == 'global_kill':
        harness.runtime.update_settings(db, {'kill_switch': True})
    elif case in {'duplicate', 'unverified_order'}:
        order = {'broker_order_id': 'FAKE-ACTIVE-1234', 'symbol': '000100', 'side': 'sell',
            'quantity': 1, 'filled_quantity': 0, 'remaining_quantity': 1, 'status': 'pending',
            'order_status_verified': True}
        if case == 'unverified_order':
            order.update(status='unknown', order_status_verified=False, remaining_quantity=None)
        fake_snapshot(state, monkeypatch, lambda snapshot: snapshot.update(open_orders=[order]), harness)
    elif case == 'market_closed':
        harness.clock.current = harness.clock.now().replace(hour=16, minute=0)
    elif case == 'cutoff':
        if state.user_id is None:
            profile_values(db, state, lambda values: values['entry'].update(no_new_entry_after='11:29'))
        else:
            db.query(UserTradingSettings).filter_by(user_id=state.user_id).one().no_new_entry_after = '11:29'
            db.commit()
    elif case == 'stale_snapshot':
        fake_snapshot(state, monkeypatch, lambda snapshot: snapshot.update(
            fetched_at=(harness.clock.now()-timedelta(seconds=11)).isoformat()), harness)
    elif case == 'bad_snapshot':
        fake_snapshot(state, monkeypatch, lambda snapshot: (snapshot.get('account') or snapshot['balance']).update(cash='bad-data'), harness)
    elif case == 'api_error':
        from app.services.user_broker_account_service import UserBrokerUnavailableError
        def failed_get(*args, **kwargs):
            raise UserBrokerUnavailableError('synthetic account API unavailable', details={'error_type': 'upstream_timeout'})
        monkeypatch.setattr(state.account, 'get_broker_snapshot', failed_get)
        state.scheduler.retry_scheduler = lambda **kwargs: False
    elif case == 'local_duplicate':
        for symbol in ('000100', '000150', '000240', '000250', '000270'):
            row = filled(db, state, harness.clock, symbol=symbol)
            row.internal_status = 'PENDING'
            row.filled_qty, row.remaining_qty = 0, 1
        db.commit()


def report(state, result, db, *, case, transport):
    trace = result.get('run_diagnostics') or {}
    gates = trace.get('gates', [])
    assert gates, result
    assert all(FIELDS <= row.keys() and row['status'] in {'PASS', 'BLOCK', 'FAILED', 'NOT_REACHED'} for row in gates)
    assert all(row['owner_user_id'] == state.user_id and row['profile_id'] == state.profile_id for row in gates)
    assert all(row['actual_value'] is None for row in gates if row['status'] == 'NOT_REACHED')
    assert all(row['duration_ms'] >= 0 and row['checked_at'] for row in gates)
    persisted = [json.loads(row.response_payload or '{}').get('run_diagnostics')
        for row in db.query(TradeRunLog).filter(TradeRunLog.owner_user_id == state.user_id).all()]
    assert any(item and item.get('gates') == gates for item in persisted)
    output = getattr(state.preview, 'result', {})
    top = [row for row in output.get('items', []) if row.get('selected_by_a_top5')]
    risk_observations = [row for row in gates if row['gate_name'] == 'ACCOUNT_RISK' and row['status'] != 'NOT_REACHED']
    assert len(risk_observations) == state.risk_spy.call_count
    if state.user_id is not None:
        assert all(row['actual_value']['owner_user_id'] == state.user_id for row in risk_observations)
    return {'account': state.name, 'owner_user_id': state.user_id, 'profile_id': state.profile_id,
        'case': case, 'result': result.get('result') or result.get('status'), 'reason': result.get('reason'),
        'risk_engine_call_count': state.risk_spy.call_count,
        'gate_counts': trace['gate_counts'], 'first_blocked_gate': trace.get('first_blocked_gate'),
        'gates': gates, 'top5': [{'symbol': row['symbol'], 'A': row.get('quant_buy_score'),
            'C': row.get('quant_c_score'), 'GPT': row.get('ai_buy_score'),
            'Final': row.get('final_buy_score')} for row in top],
        'fake_buy_count': len(state.buys),
        'fake_filled_count': db.query(OrderLog).filter(OrderLog.owner_user_id == state.user_id,
            OrderLog.kis_odno.like('FAKE-%'), OrderLog.internal_status == 'FILLED').count(),
        'actual_kis_submit_count': transport['actual_kis_submit_count'],
        'external_network_count': transport['external_network_count']}


def export(tmp_path, records):
    (tmp_path / 'gate-verification.json').write_text(json.dumps(records, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def test_three_account_positive_risk_engines_and_concurrent_slots(monkeypatch, tmp_path, no_network_or_real_submission):
    with SessionLocal() as db:
        harness, states, snapshot = setup_matrix(db, monkeypatch)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda state: run(state, harness.clock), states))
    records = []
    with SessionLocal() as db:
        for state, result in zip(states, results):
            assert len(state.buys) == 1, result
            assert state.risk_spy.call_count >= 1
            record = report(state, result, db, case='normal', transport=no_network_or_real_submission)
            assert record['fake_filled_count'] == 1
            assert len(record['top5']) == 5 and all(row['C'] >= 65 and row['GPT'] >= 60 and row['Final'] >= 65 for row in record['top5'])
            assert all(row['status'] == 'PASS' for row in record['gates']), [
                {key: row[key] for key in ('gate_name', 'status', 'reason_code')} for row in record['gates'] if row['status'] != 'PASS']
            assert db.query(PositionLifecycle).filter_by(owner_user_id=state.user_id, status='open').count() == 1
            assert db.query(SignalLog).filter_by(owner_user_id=state.user_id).count() >= 1
            assert snapshot['source_count'] == 200
            assert len(state.preview.result['runtime_input_symbols']) == 50
            records.append(record)
        assert db.query(OrderLog).count() == 3
        assert len({row.id for row in db.query(OrderLog).all()}) == 3
    assert no_network_or_real_submission == {'actual_kis_submit_count': 0, 'external_network_count': 0}
    export(tmp_path, records)


def test_optional_orderable_balance_fields_still_require_real_risk_and_preflight(monkeypatch, tmp_path,
        no_network_or_real_submission):
    with SessionLocal() as db:
        harness, states, _snapshot = setup_matrix(db, monkeypatch)
    for state in states:
        fake_snapshot(state, monkeypatch, lambda snapshot: (snapshot.get('account') or snapshot['balance']).update(
            buying_power=None, orderable_cash=None), harness)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda state: run(state, harness.clock), states))
    records = []
    with SessionLocal() as db:
        for state, result in zip(states, results):
            assert len(state.buys) == 1 and state.risk_spy.call_count >= 1, result
            record = report(state, result, db, case='optional_balance', transport=no_network_or_real_submission)
            assert record['fake_filled_count'] == 1
            assert all(row['status'] == 'PASS' for row in record['gates'])
            assert any(row['gate_name'] == 'BROKER_PREFLIGHT' and row['status'] == 'PASS' for row in record['gates'])
            records.append(record)
    export(tmp_path, records)


@pytest.mark.parametrize('account', ACCOUNTS)
@pytest.mark.parametrize('kill_scope', ['account', 'global'])
def test_kill_switch_changed_after_preflight_blocks_final_submit(monkeypatch, tmp_path,
        no_network_or_real_submission, account, kill_scope):
    with SessionLocal() as db:
        harness, states, _snapshot = setup_matrix(db, monkeypatch)
        state = next(item for item in states if item.name == account)
        owner = state.user_id or db.query(User).filter_by(role='admin').one().id
        if kill_scope == 'account' and not db.query(UserTradingSettings).filter_by(user_id=owner).first():
            db.add(UserTradingSettings(user_id=owner, kill_switch=False))
            db.commit()
    retained = []

    def flip(db):
        model = RuntimeSetting if kill_scope == 'global' else UserTradingSettings
        query = db.query(model)
        row = query.first() if kill_scope == 'global' else query.filter_by(user_id=owner).one()
        retained.append(row)
        # Inject the setting immediately before submit without replacing any
        # safety method. A second writer cannot acquire SQLite's existing
        # execution transaction lock here; separate-connection cache reads are
        # verified in test_automation_entry_safety instead.
        db.query(model).filter_by(id=row.id).update({'kill_switch': True}, synchronize_session=False)
        assert row.kill_switch is False

    if state.user_id is None:
        core = harness.profile_buy.execution_core
        original = core._submit_market
        def final_submit(db, **kwargs):
            flip(db)
            return original(db, **kwargs)
        monkeypatch.setattr(core, '_submit_market', final_submit)
    else:
        execution = state.scheduler.execution_service
        original = execution.kis_live_client_factory
        def final_client(db, user, credentials):
            if db.query(OrderLog).filter_by(owner_user_id=user.id, internal_status='REQUESTED').count():
                flip(db)
            return original(db, user, credentials)
        monkeypatch.setattr(execution, 'kis_live_client_factory', final_client)
    result = run(state, harness.clock)
    reason = 'global_kill_switch_enabled' if kill_scope == 'global' else 'user_kill_switch_enabled'
    assert isinstance(result, dict), getattr(state.scheduler, '_last_scheduler_error', None)
    assert retained and state.buys == [] and state.risk_spy.call_count >= 2, result
    with SessionLocal() as db:
        record = report(state, result, db, case='late_' + kill_scope + '_kill', transport=no_network_or_real_submission)
        assert record['first_blocked_gate']['reason_code'] == reason
        assert record['fake_filled_count'] == 0
        assert any(row['gate_name'] == 'BROKER_PREFLIGHT' and row['status'] == 'PASS' for row in record['gates'])
        assert all(row['status'] == 'NOT_REACHED' for row in record['gates'] if row['gate_name'] == 'BROKER_BUY')
    export(tmp_path, [record])


@pytest.mark.parametrize('account', ACCOUNTS)
@pytest.mark.parametrize('case', CASES)
def test_independent_account_block_matrix(monkeypatch, tmp_path, no_network_or_real_submission, account, case):
    with SessionLocal() as db:
        harness, states, _snapshot = setup_matrix(db, monkeypatch)
        state = next(item for item in states if item.name == account)
        inject(db, harness, state, case, monkeypatch)
    result = run(state, harness.clock)
    assert state.buys == [], result
    with SessionLocal() as db:
        record = report(state, result, db, case=case, transport=no_network_or_real_submission)
        assert record['fake_filled_count'] == 0
        assert record['first_blocked_gate'], result
        if case in {'c65', 'gpt60', 'final65'}:
            assert record['first_blocked_gate']['gate_name'] == case.upper()
        assert all(row['status'] == 'NOT_REACHED' for row in record['gates'] if row['gate_name'] == 'BROKER_BUY')
        assert all(row['status'] == 'NOT_REACHED' for row in record['gates']
            if row['gate_name'] in {'BROKER_PREFLIGHT', 'SUBMIT_SAFETY'})
        if case == 'daily_loss':
            assert record['first_blocked_gate']['reason_code'] in {'daily_loss_limit_hit', 'daily_loss_limit_reached'}
        if case == 'gpt60':
            assert all(row['actual_value'] == 0 and row['status'] == 'BLOCK'
                for row in record['gates'] if row['gate_name'] == 'GPT60')
        if case == 'c65':
            assert not state.responses.calls
        if case == 'final65':
            assert all(65 <= row['C'] and row['GPT'] == 60 and row['Final'] < 65 for row in record['top5'])
        assert no_network_or_real_submission == {'actual_kis_submit_count': 0, 'external_network_count': 0}
    export(tmp_path, [record])


@pytest.mark.parametrize('account,case', [('admin', 'daily_loss'), ('test01', 'daily_loss'),
    ('test02', 'daily_cap'), ('test01', 'api_error'), ('test01', 'unverified_order'),
    ('test01', 'duplicate'), ('test01', 'local_duplicate'), ('admin', 'global_kill')])
def test_one_account_block_cannot_contaminate_other_accounts(monkeypatch, tmp_path, no_network_or_real_submission, account, case):
    with SessionLocal() as db:
        harness, states, _snapshot = setup_matrix(db, monkeypatch)
        blocked = next(state for state in states if state.name == account)
        inject(db, harness, blocked, case, monkeypatch)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda state: run(state, harness.clock), states))
    records = []
    with SessionLocal() as db:
        for state, result in zip(states, results):
            assert len(state.buys) == (0 if state is blocked or case == 'global_kill' else 1), result
            if case == 'api_error' and state is blocked:
                first_gate = result['run_diagnostics']['first_blocked_gate']
                assert first_gate['reason_code'] == 'upstream_timeout'
                assert first_gate['actual_value']['exception_type'] == 'UserBrokerUnavailableError'
            records.append(report(state, result, db, case='isolation_'+case, transport=no_network_or_real_submission))
    export(tmp_path, records)


@pytest.mark.parametrize('account', ('test01', 'test02'))
@pytest.mark.parametrize('price,reason', [(9700, 'stop_loss_triggered'), (10900, 'take_profit_triggered')])
def test_sell_priority_survives_buy_cash_and_entry_cutoff_blocks(monkeypatch, tmp_path,
        no_network_or_real_submission, account, price, reason):
    with SessionLocal() as db:
        harness, states, _snapshot = setup_matrix(db, monkeypatch)
        state = next(item for item in states if item.name == account)
        inject(db, harness, state, 'cutoff', monkeypatch)
        def held(snapshot):
            snapshot['positions'] = [{'symbol': '000100', 'quantity': 5, 'available_quantity': 5,
                'avg_price': 10000, 'current_price': price, 'market_value': 5*price}]
            snapshot['account'].update(cash=0, buying_power=0)
        fake_snapshot(state, monkeypatch, held, harness)
        aggregate = state.scheduler.run_provider_once(db, provider='kis', scheduler_slot='11:30',
            owner_user_id=state.user_id, now=harness.clock.now())
        result = next(item for item in aggregate['items'] if item.get('owner_user_id') == state.user_id)
        assert 'position_management' in result, {key: result.get(key) for key in
            ('result', 'reason', 'failure_stage', 'exception_type', 'sanitized_error')}
        assert result['position_management']['reason'] == reason, result
        assert state.client.sell_calls == [('000100', 5)]
        assert state.buys == [] and state.responses.calls == []
        assert db.query(OrderLog).filter_by(owner_user_id=state.user_id, side='sell', internal_status='FILLED').count() == 1
        assert no_network_or_real_submission['actual_kis_submit_count'] == 0
        export(tmp_path, [{'account': account, 'case': reason, 'fake_sell_count': 1,
            'fake_buy_count': 0, 'actual_kis_submit_count': 0, 'gates': result['run_diagnostics']['gates']}])


def test_admin_risk_performance_excludes_foreign_owner_even_with_wrong_profile_tag(monkeypatch):
    with SessionLocal() as db:
        harness, states, _snapshot = setup_matrix(db, monkeypatch)
        admin, first, _second = states
        profile_values(db, admin, lambda values: values['capital'].update(
            compound_enabled=True, compound_basis='realized_pnl', initial_budget_krw=100000))
        for side, price in (('buy', 10000), ('sell', 1000)):
            row = filled(db, first, harness.clock, side=side, price=price, qty=10)
            payload = json.loads(row.request_payload)
            payload['profile_key'] = db.get(StrategyProfile, admin.profile_id).profile_key
            row.request_payload = json.dumps(payload)
        db.commit()
        budget = admin.risk.budget_service
        performance = budget.performance_service.daily(db, provider='kis', market='KR', date_value=harness.clock.now().date())
        assert performance['orders_count'] == 0 and performance['pnl_pct'] == 0
        capital = harness.profiles.capital_state(db, str(admin.profile_id))
        assert capital['cumulative_realized_pnl_krw'] == 0
        assert capital['current_strategy_budget_krw'] == 100000
        result = run(admin, harness.clock)
        assert len(admin.buys) == 1, result
