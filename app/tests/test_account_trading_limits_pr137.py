from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.models import AccountTradingLimitAudit, OrderLog, User
from app.services.account_trading_limit_service import AccountTradingLimitError, AccountTradingLimitService
from app.services.automation_profile_safety import effective_profile_settings
from app.services.kis_automation_execution_core import KisAutomationExecutionCore
from app.services.runtime_setting_service import RuntimeSettingService


NOW = datetime(2026, 9, 10, 1, tzinfo=UTC)


def _user(db, role='user', name='test01', **limits):
    user = User(username=name, role=role, enabled=True, **limits)
    db.add(user)
    db.commit()
    return user


def _positions(total=0, symbol_value=0):
    result = []
    if symbol_value:
        result.append({'symbol': '005930', 'quantity': 10, 'current_price': symbol_value / 10})
    if total > symbol_value:
        result.append({'symbol': '000660', 'quantity': 10, 'market_value': total - symbol_value})
    return result


def _calculate(db, user, **kwargs):
    values = dict(symbol='005930', positions=[], profile_order_cap=3_000_000,
                  available_cash=5_000_000, owner_user_id=None if user.role == 'admin' else user.id)
    values.update(kwargs)
    return AccountTradingLimitService().calculate(db, **values)


@pytest.mark.parametrize('role,total,position', [('admin', None, None), ('user', 10_000_000, 1_000_000)])
def test_new_account_defaults(db_session, role, total, position):
    user = _user(db_session, role)
    assert user.account_max_total_exposure_krw == total
    assert user.account_max_position_notional_krw == position


@pytest.mark.parametrize('role,profile,cash,total,symbol_value,multiplier,expected,source', [
    ('admin', 3_000_000, 5_000_000, 0, 0, 1, 3_000_000, 'profile_order_cap'),
    ('admin', 3_000_000, 2_000_000, 0, 0, 1, 2_000_000, 'available_cash'),
    ('user', 500_000, 5_000_000, 0, 0, 1, 500_000, 'profile_order_cap'),
    ('user', 800_000, 5_000_000, 700_000, 700_000, 1, 300_000, 'account_position_cap'),
    ('user', 1_000_000, 5_000_000, 9_600_000, 0, 1, 400_000, 'account_total_exposure_cap'),
    ('user', 800_000, 5_000_000, 9_600_000, 700_000, 1, 300_000, 'account_position_cap'),
    ('user', 800_000, 5_000_000, 9_800_000, 700_000, 1, 200_000, 'account_total_exposure_cap'),
    ('user', 800_000, 100_000, 700_000, 700_000, 1, 100_000, 'available_cash'),
    ('user', 800_000, 5_000_000, 700_000, 700_000, .5, 150_000, 'risk_reduced'),
    ('admin', 3_000_000, 5_000_000, 0, 0, .5, 1_500_000, 'risk_reduced'),
])
def test_minimum_formula(db_session, role, profile, cash, total, symbol_value, multiplier, expected, source):
    user = _user(db_session, role)
    result = _calculate(db_session, user, positions=_positions(total, symbol_value),
                        profile_order_cap=profile, available_cash=cash, risk_sizing_multiplier=multiplier)
    assert result['effective_order_cap_krw'] == expected
    assert result['cap_source'] == source
    assert result['current_account_exposure_krw'] == total
    assert result['current_symbol_exposure_krw'] == symbol_value


def test_percentage_and_unlimited_dimensions(db_session):
    admin = _user(db_session, 'admin')
    result = _calculate(db_session, admin, profile_pct_cap=250_000)
    assert result['effective_order_cap_krw'] == 250_000
    assert result['cap_source'] == 'profile_pct_cap'
    assert result['remaining_account_exposure_krw'] is None
    assert result['remaining_symbol_exposure_krw'] is None
    regular = _user(db_session, name='test02', account_max_total_exposure_krw=None,
                    account_max_position_notional_krw=None)
    assert _calculate(db_session, regular)['effective_order_cap_krw'] == 3_000_000


@pytest.mark.parametrize('positions', [None, {}, [None], [{'symbol': '005930', 'quantity': 3}],
    [{'symbol': '005930', 'quantity': 3, 'avg_price': 100}],
    [{'symbol': '005930', 'quantity': -1, 'current_price': 100}],
    [{'symbol': '005930', 'quantity': 1, 'current_price': float('nan')}],
    [{'symbol': '005930', 'quantity': 1, 'current_price': 0}]])
def test_unknown_or_unreliable_positions_fail_closed(db_session, positions):
    user = _user(db_session)
    with pytest.raises(AccountTradingLimitError, match='account_exposure_state_unavailable'):
        _calculate(db_session, user, positions=positions)


@pytest.mark.parametrize('cash', [None, float('nan'), float('inf'), -1, True])
def test_unknown_cash_fails_closed(db_session, cash):
    with pytest.raises(AccountTradingLimitError):
        _calculate(db_session, _user(db_session), available_cash=cash)


def test_duplicate_position_rows_are_not_double_counted(db_session):
    row = {'symbol': '005930', 'quantity': 10, 'current_price': 70_000, 'market_value': 1}
    result = _calculate(db_session, _user(db_session), positions=[row, dict(row)])
    assert result['current_account_exposure_krw'] == 700_000
    assert result['remaining_symbol_exposure_krw'] == 300_000
    with pytest.raises(AccountTradingLimitError):
        _calculate(db_session, db_session.query(User).one(), positions=[row, {**row, 'quantity': 11}])


@pytest.mark.parametrize('total,symbol_value,reason', [(10_100_000, 0, 'account_total_exposure_limit_reached'),
    (1_100_000, 1_100_000, 'account_position_limit_reached')])
def test_exceeded_exposure_blocks_buy(db_session, total, symbol_value, reason):
    result = _calculate(db_session, _user(db_session), positions=_positions(total, symbol_value))
    assert result['effective_order_cap_krw'] == 0
    assert result['reason'] == reason


def test_scope_isolation_and_no_regular_fallback(db_session):
    admin = _user(db_session, 'admin', name='renamed-admin')
    first = _user(db_session, name='first', account_max_total_exposure_krw=500_000)
    second = _user(db_session, name='second')
    assert _calculate(db_session, first)['effective_order_cap_krw'] == 500_000
    assert _calculate(db_session, second)['effective_order_cap_krw'] == 1_000_000
    assert _calculate(db_session, admin)['effective_order_cap_krw'] == 3_000_000
    for kwargs in ({'owner_user_id': 123456}, {'owner_user_id': admin.id}, {'provider': 'alpaca'}, {'market': 'US'}):
        with pytest.raises(AccountTradingLimitError):
            _calculate(db_session, first, **kwargs)


def test_profile_value_preserved_with_all_other_safety_floors():
    result = effective_profile_settings({'capital': {'max_order_notional_krw': 5_000_000},
        'entry': {'min_final_score': 10, 'no_new_entry_after': '15:00'},
        'max_open_positions': 10, 'exit': {}})
    assert result['capital']['max_order_notional_krw'] == 5_000_000
    assert result['entry']['min_final_score'] == 65
    assert result['entry']['no_new_entry_after'] == '14:00'
    assert result['max_open_positions'] == 1
    assert result['capital']['cash_only'] is True
    assert result['exit']['stop_loss_enabled'] is True
    assert result['exit']['take_profit_enabled'] is True


def test_additive_migration_rerun_preserves_explicit_values_and_profile(monkeypatch):
    import app.db.init_db as migration
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, role VARCHAR(30))'))
        conn.execute(text("INSERT INTO users (id, role) VALUES (17, 'admin'), (42, 'user')"))
        conn.execute(text('CREATE TABLE strategy_profiles (max_order_notional_krw FLOAT)'))
        conn.execute(text('INSERT INTO strategy_profiles VALUES (5000000)'))
    monkeypatch.setattr(migration, 'engine', engine)
    migration._migrate_account_trading_limits_if_needed()
    with engine.begin() as conn:
        rows = conn.execute(text('SELECT * FROM users ORDER BY id')).mappings().all()
        assert rows[0]['account_max_total_exposure_krw'] is None
        assert rows[0]['account_max_position_notional_krw'] is None
        assert rows[1]['account_max_total_exposure_krw'] == 10_000_000
        assert rows[1]['account_max_position_notional_krw'] == 1_000_000
        conn.execute(text('UPDATE users SET account_max_total_exposure_krw = NULL, account_max_position_notional_krw = 2000000 WHERE id = 42'))
    migration._migrate_account_trading_limits_if_needed()
    with engine.connect() as conn:
        row = conn.execute(text('SELECT * FROM users WHERE id = 42')).mappings().one()
        assert row['account_max_total_exposure_krw'] is None
        assert row['account_max_position_notional_krw'] == 2_000_000
        assert conn.execute(text('SELECT max_order_notional_krw FROM strategy_profiles')).scalar_one() == 5_000_000
    engine.dispose()


def test_database_claim_serializes_workers_without_cross_account_blocking(db_session):
    first = _user(db_session)
    second = _user(db_session, name='second')
    service = AccountTradingLimitService()
    other_session = sessionmaker(bind=db_session.get_bind())()
    try:
        with service.buy_execution_claim(db_session, owner_user_id=first.id):
            with pytest.raises(AccountTradingLimitError, match='account_buy_in_progress'):
                with service.buy_execution_claim(other_session, owner_user_id=first.id):
                    pytest.fail('Concurrent account claim was accepted')
            with service.buy_execution_claim(other_session, owner_user_id=second.id):
                pass
        with service.buy_execution_claim(other_session, owner_user_id=first.id):
            pass
    finally:
        other_session.close()


class FakeKisClient:
    def __init__(self):
        self.positions = []
        self.cash = 5_000_000
        self.on_possible = None
        self.on_price = None

    def list_positions(self):
        return self.positions

    def list_open_orders(self):
        return []

    def get_domestic_stock_price(self, symbol):
        if self.on_price:
            self.on_price()
        return {'current_price': 100_000}

    def get_domestic_possible_order(self, **kwargs):
        if self.on_possible:
            self.on_possible()
        return {'raw_status': 'ok', 'orderable_cash': self.cash,
                'orderable_quantity': 50, 'queried_at': NOW.isoformat()}


def _order(db, symbol='005930', side='buy', owner=None):
    RuntimeSettingService().update_settings(db, {'automation_mode': 'live'})
    row = OrderLog(broker='kis', market='KR', symbol=symbol, side=side, order_type='market', time_in_force='day', qty=30,
                   notional=3_000_000, internal_status='REQUESTED', owner_user_id=owner)
    db.add(row)
    db.commit()
    return row


def _buy(core, db, order, submitter):
    return core.submit_market_buy(db, order=order, symbol=order.symbol, qty=30,
                                 max_order_notional_krw=3_000_000, submitter=submitter, now=NOW)


def test_real_buy_admin_above_one_million_still_cash_limited(db_session):
    _user(db_session, 'admin')
    client = FakeKisClient()
    client.cash = 2_000_000
    order = _order(db_session)
    submitted = []
    result = _buy(KisAutomationExecutionCore(client), db_session, order,
                  lambda: submitted.append(order.qty) or {'order_id': 'FAKE', 'status': 'submitted'})
    assert result['submitted'] is True
    assert submitted == [20]
    assert result['guard']['account_trading_limits']['effective_order_cap_krw'] == 2_000_000


def test_real_buy_reloads_changed_limits_before_post(db_session):
    admin = _user(db_session, 'admin')
    client = FakeKisClient()
    def lower_limit():
        admin.account_max_total_exposure_krw = 400_000
        db_session.commit()
    client.on_possible = lower_limit
    order = _order(db_session)
    submitted = []
    result = _buy(KisAutomationExecutionCore(client), db_session, order,
                  lambda: submitted.append(order.qty) or {'order_id': 'FAKE', 'status': 'submitted'})
    assert result['submitted'] is True
    assert submitted == [4]


def test_concurrent_buy_and_pending_reservation_cannot_bypass_limit(db_session):
    admin = _user(db_session, 'admin', account_max_total_exposure_krw=1_000_000)
    client = FakeKisClient()
    core = KisAutomationExecutionCore(client)
    first = _order(db_session)
    second_result = []
    def submit():
        second = _order(db_session, symbol='000660')
        second_result.append(_buy(core, db_session, second, lambda: pytest.fail('Concurrent POST')))
        return {'order_id': 'FAKE', 'status': 'submitted'}
    assert _buy(core, db_session, first, submit)['submitted'] is True
    assert second_result[0]['reason'] == 'account_buy_in_progress'
    third = _order(db_session, symbol='035420')
    result = _buy(core, db_session, third, lambda: pytest.fail('Exposure cap bypass'))
    assert result['reason'] == 'account_total_exposure_limit_reached'
    assert admin.account_max_total_exposure_krw == 1_000_000


@pytest.mark.parametrize('cap', ['account_max_total_exposure_krw', 'account_max_position_notional_krw'])
def test_sell_ignores_account_exposure_limits(db_session, cap):
    _user(db_session, 'admin', **{cap: 1.0})
    client = FakeKisClient()
    client.positions = [{'symbol': '005930', 'qty': 30, 'current_price': 100_000}]
    order = _order(db_session, side='sell')
    submitted = []
    result = KisAutomationExecutionCore(client).submit_market_sell(
        db_session, order=order, symbol='005930', qty=30,
        submitter=lambda: submitted.append(True) or {'order_id': 'FAKE-SELL', 'status': 'submitted'}, now=NOW)
    assert result['submitted'] is True
    assert submitted == [True]


@pytest.fixture
def admin_api(db_session):
    from app.db.database import get_db
    from app.main import app
    from app.services.auth_dependencies import get_current_user
    admin = _user(db_session, 'admin', name='admin')
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: admin
    client = TestClient(app)
    try:
        yield client, admin
    finally:
        app.dependency_overrides.clear()


def test_admin_detail_update_null_roundtrip_and_audit_isolation(db_session, admin_api):
    client, admin = admin_api
    first = _user(db_session, name='test01')
    second = _user(db_session, name='test02')
    url = f'/admin/users/{first.id}'
    assert client.get(url).json()['trading_limits']['max_total_exposure_krw'] == 10_000_000
    result = client.put(url + '/trading-limits', json={'max_total_exposure_krw': None, 'max_position_notional_krw': 2_000_000})
    assert result.status_code == 200
    assert result.json()['trading_limits']['total_exposure_unlimited'] is True
    assert client.get(url).json()['trading_limits']['max_total_exposure_krw'] is None
    assert client.get(f'/admin/users/{admin.id}').json()['trading_limits']['position_notional_unlimited'] is True
    assert client.get(f'/admin/users/{second.id}').json()['trading_limits']['max_position_notional_krw'] == 1_000_000
    audit = db_session.query(AccountTradingLimitAudit).one()
    assert audit.target_owner_user_id == first.id
    assert audit.changed_by_user_id == admin.id
    assert audit.previous_max_total_exposure_krw == 10_000_000
    assert audit.new_max_total_exposure_krw is None
    assert audit.previous_max_position_notional_krw == 1_000_000
    assert audit.new_max_position_notional_krw == 2_000_000
    assert audit.changed_at is not None
    # Retrying the same update must not create a duplicate mutation/audit.
    client.put(url + '/trading-limits', json={'max_total_exposure_krw': None, 'max_position_notional_krw': 2_000_000})
    assert db_session.query(AccountTradingLimitAudit).count() == 1
    serialized = json.dumps(result.json()).lower()
    for secret in ('appkey', 'appsecret', 'access_token', 'approval_key', 'encrypted_payload'):
        assert secret not in serialized


@pytest.mark.parametrize('payload', [{}, {'max_total_exposure_krw': -1, 'max_position_notional_krw': 1},
    {'max_total_exposure_krw': 0, 'max_position_notional_krw': 1},
    {'max_total_exposure_krw': 1, 'max_position_notional_krw': 1, 'owner_user_id': 1}])
def test_invalid_admin_limit_updates_rejected(db_session, admin_api, payload):
    client, _ = admin_api
    user = _user(db_session)
    assert client.put(f'/admin/users/{user.id}/trading-limits', json=payload).status_code == 422
    assert user.account_max_total_exposure_krw == 10_000_000


def test_regular_user_cannot_edit_account_limits(db_session, admin_api):
    from app.main import app
    from app.services.auth_dependencies import get_current_user
    client, _ = admin_api
    user = _user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user
    assert client.get(f'/admin/users/{user.id}').status_code == 403
    assert client.put(f'/admin/users/{user.id}/trading-limits', json={'max_total_exposure_krw': None, 'max_position_notional_krw': None}).status_code == 403
    assert client.patch('/users/me/trading/settings', json={'account_max_total_exposure_krw': None}).status_code == 422


def test_usage_failure_keeps_configuration_available(db_session, admin_api, monkeypatch):
    from app.services.user_broker_account_service import UserBrokerAccountService
    client, _ = admin_api
    user = _user(db_session)
    monkeypatch.setattr(UserBrokerAccountService, 'get_broker_snapshot', lambda *args: (_ for _ in ()).throw(RuntimeError('secret-not-to-leak')))
    usage = client.get(f'/admin/users/{user.id}/trading-limits/usage')
    assert usage.status_code == 200
    assert usage.json() == {'available': False, 'reason': 'account_exposure_state_unavailable'}
    assert client.get(f'/admin/users/{user.id}').json()['trading_limits']['max_total_exposure_krw'] == 10_000_000


@pytest.mark.parametrize('mutation', ['limit', 'profile', 'positions_unavailable', 'wrong_owner', 'cash'])
def test_regular_real_buy_refreshes_owner_profile_positions_and_cash(db_session, mutation):
    from app.tests.test_user_auto_trading_scheduler_pr129 import (
        _canonical_live_harness, _final_candidate, _run_user_scheduler_slot,
    )
    from app.db.models import StrategyProfile
    scheduler, user, profile, _, account, _, _, client = _canonical_live_harness(
        db_session, candidates=[_final_candidate('005930')],
        fixed_budget=500_000, max_order_notional=500_000,
    )
    original = account.get_broker_snapshot
    count = 0
    def fresh_snapshot(db, owner, provider):
        nonlocal count
        snapshot = original(db, owner, provider)
        count += 1
        if count >= 2:
            if mutation == 'limit':
                owner.account_max_total_exposure_krw = 200_000
                db.commit()
            elif mutation == 'profile':
                row = db.get(StrategyProfile, profile['id'])
                settings = json.loads(row.settings_json)
                settings['capital']['max_order_notional_krw'] = 30_000
                row.settings_json = json.dumps(settings)
                db.commit()
            elif mutation == 'positions_unavailable':
                snapshot = {**snapshot, 'positions': None}
            elif mutation == 'wrong_owner':
                snapshot = {**snapshot, 'owner_user_id': owner.id + 1}
            elif mutation == 'cash':
                snapshot = {**snapshot, 'account': {**snapshot['account'], 'buying_power': 100_000}}
        return snapshot
    account.get_broker_snapshot = fresh_snapshot
    item = _run_user_scheduler_slot(db_session, scheduler, user)
    if mutation in {'positions_unavailable', 'profile', 'wrong_owner'}:
        assert client.buy_calls == []
    else:
        assert client.buy_calls == [('005930', 4 if mutation == 'limit' else 2)]
    assert count >= 2
    assert item['owner_user_id'] == user.id


def test_uncertain_user_broker_post_retains_capacity_without_retry(db_session):
    from app.tests.test_user_auto_trading_scheduler_pr129 import (
        _canonical_live_harness, _final_candidate, _run_user_scheduler_slot,
    )
    scheduler, user, _, _, _, _, _, client = _canonical_live_harness(
        db_session, candidates=[_final_candidate('005930')],
    )
    client.submit_failures.add('005930')
    _run_user_scheduler_slot(db_session, scheduler, user)
    order = db_session.query(OrderLog).filter_by(owner_user_id=user.id, side='buy').one()
    assert order.internal_status == 'UNKNOWN_STALE'
    assert len(client.buy_calls) == 1
    result = _calculate(db_session, user)
    assert result['pending_buy_exposure_krw'] > 0


def test_admin_finite_override_is_not_bypassed_by_role(db_session):
    admin = _user(db_session, 'admin', account_max_total_exposure_krw=600_000,
                  account_max_position_notional_krw=400_000)
    result = _calculate(db_session, admin)
    assert result['effective_order_cap_krw'] == 400_000
    assert result['account_total_exposure_unlimited'] is False
    assert result['account_position_unlimited'] is False


def test_filled_ack_before_holdings_refresh_keeps_exposure_reserved(db_session):
    admin = _user(db_session, 'admin', account_max_total_exposure_krw=1_000_000)
    client = FakeKisClient()
    core = KisAutomationExecutionCore(client)
    first = _order(db_session)
    result = _buy(core, db_session, first, lambda: {'order_id': 'FAKE', 'status': 'filled',
                  'filled_qty': 10, 'avg_fill_price': 100_000})
    assert result['submitted'] is True
    lag = _calculate(db_session, admin)
    assert lag['current_account_exposure_krw'] == 0
    assert lag['pending_buy_exposure_krw'] == 1_000_000
    assert lag['effective_order_cap_krw'] == 0
    reflected = _calculate(db_session, admin, positions=_positions(1_000_000, 1_000_000))
    assert reflected['pending_buy_exposure_krw'] == 0
    assert reflected['current_account_exposure_krw'] == 1_000_000


def test_pending_partial_fills_are_not_double_counted(db_session):
    user = _user(db_session)
    order = _order(db_session, owner=user.id)
    order.qty = order.requested_qty = 10
    order.filled_qty = 4
    order.remaining_qty = 6
    order.notional = 1_000_000
    order.internal_status = 'PARTIALLY_FILLED'
    db_session.commit()
    result = _calculate(db_session, user, positions=[{'symbol': '005930', 'quantity': 4, 'current_price': 100_000}])
    assert result['pending_buy_exposure_krw'] == 600_000
    assert result['current_account_exposure_krw'] == 400_000
    assert result['remaining_symbol_exposure_krw'] == 0


def test_broker_account_identity_mismatch_blocks_policy(db_session):
    user = _user(db_session)
    with pytest.raises(AccountTradingLimitError, match='account_scope_mismatch'):
        _calculate(db_session, user, broker_account_id='admin:kis:KR')



def test_policy_telemetry_survives_sanitization_without_exposing_account_secrets():
    from app.services.kis_payload_sanitizer import sanitize_kis_payload
    payload = {'account_trading_limits': {'broker_account_id': 'user:42:kis:KR',
        'account_max_total_exposure_krw': None, 'account_max_position_notional_krw': 1_000_000,
        'current_account_exposure_krw': 9_600_000, 'remaining_account_exposure_krw': 400_000,
        'account_total_exposure_unlimited': True, 'appsecret': 'secret-secret',
        'account_no': '12345678'}}
    cleaned = sanitize_kis_payload(payload)['account_trading_limits']
    assert cleaned['account_max_total_exposure_krw'] is None
    assert cleaned['current_account_exposure_krw'] == 9_600_000
    assert cleaned['account_total_exposure_unlimited'] is True
    assert cleaned['broker_account_id'] == 'user:42:kis:KR'
    assert cleaned['appsecret'] == '***'
    assert cleaned['account_no'] != '12345678'
    assert sanitize_kis_payload({'broker_account_id': '12345678'})['broker_account_id'] != '12345678'


@pytest.mark.parametrize('quantity', [None, -1, 'invalid', float('nan')])
def test_normalized_unknown_position_quantities_are_not_reported_as_reliable(quantity):
    from app.services.user_broker_account_service import _normalize_kis_snapshot
    snapshot = _normalize_kis_snapshot(
        {'output1': [{'pdno': '005930', 'hldg_qty': quantity}], 'output2': [{}]}, {'output': []},
    )
    assert snapshot['positions_reliable'] is False


def test_reliable_market_value_is_usable_when_normalized_price_is_missing(db_session):
    result = _calculate(db_session, _user(db_session),
        positions=[{'symbol': '005930', 'qty': 10, 'current_price': 0, 'market_value': 700_000}])
    assert result['current_symbol_exposure_krw'] == 700_000
    assert result['effective_order_cap_krw'] == 300_000


@pytest.mark.parametrize('mutation', ['unreliable', 'provider', 'market', 'broker_account_id'])
def test_usage_requires_reliable_owner_account_snapshot(db_session, admin_api, monkeypatch, mutation):
    from app.services.user_broker_account_service import UserBrokerAccountService
    client, _ = admin_api
    user = _user(db_session)
    snapshot = {'connected': True, 'owner_user_id': user.id, 'provider': 'kis', 'market': 'KR',
                'broker_account_id': f'user:{user.id}:kis:KR', 'positions': [], 'positions_reliable': True}
    if mutation == 'unreliable':
        snapshot['positions_reliable'] = False
    else:
        snapshot[mutation] = {'provider': 'alpaca', 'market': 'US',
                              'broker_account_id': 'admin:kis:KR'}[mutation]
    monkeypatch.setattr(UserBrokerAccountService, 'get_broker_snapshot', lambda *args: snapshot)
    usage = client.get(f'/admin/users/{user.id}/trading-limits/usage')
    assert usage.json() == {'available': False, 'reason': 'account_exposure_state_unavailable'}
    assert client.get(f'/admin/users/{user.id}').json()['trading_limits']['max_total_exposure_krw'] == 10_000_000
