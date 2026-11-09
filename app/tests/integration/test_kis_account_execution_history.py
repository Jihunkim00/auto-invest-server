"""Broker account history, isolated DB and fake GET transport only."""
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.brokers.kis_client import KisClient
from app.brokers.kis_account_execution_reader import ExecutionReadBudget
from app.db.database import get_db
from app.db.models import OrderLog
from app.routes.kis_account_executions import router, get_execution_history_service
from app.services.auth_dependencies import get_current_user
from app.services.kis_account_execution_history_service import (
    ExecutionSnapshotCache, KisAccountExecutionHistoryService, KST,
    history_windows, period_dates, recent_boundary,
)
from app.services.user_broker_account_service import UserBrokerAccountService
from app.services.broker_credential_crypto_service import BrokerCredentialCryptoService
from app.tests.test_user_broker_accounts import _settings, _user, _credential

NOW = datetime(2026, 11, 9, 18, tzinfo=KST)


def execution(number='19', *, day='20261104', symbol='032640', side='02', qty='2', filled='2', price='15680', **extra):
    return {'ord_dt': day, 'odno': number, 'ord_gno_brno': '00001',
            'pdno': symbol, 'prdt_name': '가짜 종목', 'sll_buy_dvsn_cd': side,
            'ord_qty': qty, 'tot_ccld_qty': filled, 'avg_prvs': price,
            'rmn_qty': str(float(qty) - float(filled)), 'ord_tmd': '124800', **extra}


class FakeTokenManager:
    def __init__(self):
        self.calls = []

    def get_token(self, **kwargs):
        self.calls.append({key: kwargs[key] for key in ('user_id', 'environment', 'credential_identity', 'force_refresh')})
        return 'fake-only-access-token'


class FakeBrokerHTTP:
    def __init__(self):
        self.gets, self.rows = [], {}
        self.page_size = 2
        self.transform = lambda body, headers, call: (body, headers, 200)

    def post(self, *args, **kwargs):
        pytest.fail('No auth, trading, or cancel POST transport is needed in these fake tests')

    def get(self, url, *, params, headers, timeout):
        assert url.endswith('/uapi/domestic-stock/v1/trading/inquire-daily-ccld')
        call = {'url': url, 'params': deepcopy(params), 'headers': deepcopy(headers), 'timeout': timeout}
        self.gets.append(call)
        rows = [row for row in self.rows.get(params['CANO'], [])
                if params['INQR_STRT_DT'] <= row['ord_dt'] <= params['INQR_END_DT']]
        offset = int(params['CTX_AREA_NK100'] or 0)
        more = offset + self.page_size < len(rows)
        body = {'rt_cd': '0', 'output1': deepcopy(rows[offset:offset + self.page_size]),
                'output2': {}, 'ctx_area_fk100': 'fake-query' if more else '',
                'ctx_area_nk100': str(offset + self.page_size) if more else ''}
        body, response_headers, status = self.transform(body, {'tr_cont': 'F' if more else 'D'}, call)
        return SimpleNamespace(json=lambda: body, headers=response_headers, status_code=status)


@pytest.fixture
def harness(db_session, monkeypatch):
    settings = _settings(kis_env='live', kis_account_no='10000001', kis_account_product_code='01',
        kis_app_key='fake-admin-key', kis_app_secret='fake-admin-secret',
        kis_base_url='https://openapi.koreainvestment.com:9443')
    crypto, http, tokens = BrokerCredentialCryptoService(settings), FakeBrokerHTTP(), FakeTokenManager()
    admin = _user(db_session, 'fake-admin', role='admin')
    first, second = _user(db_session, 'fake-test01'), _user(db_session, 'fake-test02')
    for user, number in ((first, '10000002'), (second, '10000003')):
        _credential(db_session, user, crypto, 'kis', {
            'environment': 'live', 'account_no': number, 'account_product_code': '01',
            'app_key': f'fake-user-{user.id}-key', 'app_secret': f'fake-user-{user.id}-secret',
        })
    account = UserBrokerAccountService(crypto=crypto, http_client=http, token_manager=tokens)
    auth = SimpleNamespace(get_valid_access_token=lambda force_refresh=False: SimpleNamespace(token='fake-admin-token'))
    admin_client = KisClient(settings, auth_manager=auth)
    monkeypatch.setattr('app.brokers.kis_client.requests.get', http.get)
    cache = ExecutionSnapshotCache()
    service = KisAccountExecutionHistoryService(account_service=account,
        admin_client_factory=lambda: admin_client, now_provider=lambda: NOW, cache=cache,
        budget_factory=lambda period: ExecutionReadBudget(min_interval=0, max_calls=48, timeout_seconds=10))
    return SimpleNamespace(db=db_session, service=service, http=http, tokens=tokens,
        admin=admin, first=first, second=second, settings=settings, crypto=crypto, cache=cache,
        account=account, admin_client=admin_client)


def test_direct_broker_trades_without_any_local_order_and_account_isolation(harness):
    h = harness
    h.http.rows['10000002'] = [execution(), execution('13', day='20261013', symbol='028670', qty='5', filled='5'),
        execution('14', day='20261014', symbol='028670', side='01', qty='5', filled='5')]
    assert h.db.query(OrderLog).count() == 0
    admin = h.service.read(h.db, h.admin, period='week')
    first = h.service.read(h.db, h.first, period='week')
    second = h.service.read(h.db, h.second, period='week')
    assert (admin['status'], admin['count'], admin['total_buy_amount']) == ('success', 0, 0)
    assert (first['count'], first['total_buy_amount']) == (1, 31360)
    assert first['items'][0]['symbol'] == '032640'
    assert first['items'][0]['executed_at'] is None  # ord_tmd never becomes a fill time.
    assert second['count'] == 0
    month = h.service.read(h.db, h.first, period='month')
    assert month['count'] == 3 and month['total_sell_amount'] == 78400
    assert h.db.query(OrderLog).count() == 0
    assert h.tokens.calls and all(call['user_id'] in {h.first.id, h.second.id} for call in h.tokens.calls)
    user_calls = [call for call in h.http.gets if call['params']['CANO'] == '10000002']
    assert all(call['headers']['appkey'] == f'fake-user-{h.first.id}-key' for call in user_calls)
    for call in h.http.gets:
        assert call['params']['EXCG_ID_DVSN_CD'] == 'ALL'
        assert call['params']['CCLD_DVSN'] == '01' and call['params']['SLL_BUY_DVSN_CD'] == '00'
        assert call['params']['ODNO'] == ''


@pytest.mark.parametrize('environment,recent,older', [
    ('live', 'TTTC0081R', 'CTSC9215R'), ('paper', 'VTTC0081R', 'VTSC9215R'),
])
def test_year_split_and_live_paper_official_ids(harness, environment, recent, older):
    h = harness
    if environment == 'paper':
        from app.db.models import UserBrokerCredential
        row = h.db.query(UserBrokerCredential).filter_by(user_id=h.first.id, provider='kis').one()
        row.environment = 'paper'
        row.encrypted_payload = h.crypto.encrypt({'environment': 'paper', 'account_no': '10000002',
            'account_product_code': '01', 'app_key': 'fake-paper-key', 'app_secret': 'fake-paper-secret'})
        h.db.commit()
    result = h.service.read(h.db, h.first, period='year')
    assert result['status'] == 'success' and result['environment'] == environment
    calls = h.http.gets
    assert {call['headers']['tr_id'] for call in calls} == {recent, older}
    start, end = period_dates('year', NOW)
    dates = []
    for call in calls:
        lower, upper = (datetime.strptime(call['params'][key], '%Y%m%d').date()
                        for key in ('INQR_STRT_DT', 'INQR_END_DT'))
        assert (upper - lower).days < 30
        assert (call['headers']['tr_id'] == older) is (upper < recent_boundary(NOW.date()))
        dates.extend(lower + timedelta(days=day) for day in range((upper - lower).days + 1))
    assert len(dates) == len(set(dates)) == 365
    assert min(dates) == start and max(dates) == end


@pytest.mark.parametrize('period,days', [('day', 1), ('week', 7), ('month', 30), ('year', 365)])
def test_kst_boundaries_all_periods(harness, period, days):
    h = harness
    start, end = period_dates(period, NOW)
    assert start == NOW.date() - timedelta(days=days - 1)
    h.http.rows['10000002'] = [execution('1', day=start.strftime('%Y%m%d')),
        execution('2', day=(start - timedelta(days=1)).strftime('%Y%m%d'))]
    result = h.service.read(h.db, h.first, period=period)
    assert result['count'] == 1
    assert result['start_at'] == start.isoformat() + 'T00:00:00+09:00'
    h.service.now_provider = lambda: datetime(2026, 11, 8, 15, 0, 1, tzinfo=UTC)
    assert period_dates('day', h.service.now_provider())[0] == date(2026, 11, 9)


def test_continuation_all_pages_deduplicates_cumulative_partial_fills_and_ui_pages(harness):
    h = harness
    h.http.rows['10000002'] = [execution(str(index), qty='10', filled='2') for index in range(1, 26)]
    h.http.rows['10000002'] += [execution('00001', qty='10', filled='5', cncl_yn='Y')]
    h.http.page_size = 5
    first = h.service.read(h.db, h.first, period='week', limit=20)
    assert first['status'] == 'success' and first['count'] == 25
    assert first['total_buy_amount'] == (24 * 2 + 5) * 15680
    assert len(first['items']) == 20 and first['next_offset'] == 20
    assert len(h.http.gets) == 6
    assert h.http.gets[0]['headers']['tr_cont'] == ''
    assert all(call['headers']['tr_cont'] == 'N' for call in h.http.gets[1:])
    count_before_more = len(h.http.gets)
    second = h.service.read(h.db, h.first, period='week', limit=20, offset=20,
        as_of=datetime.fromisoformat(first['end_at']))
    assert len(h.http.gets) == count_before_more
    ids = [item['id'] for item in first['items'] + second['items']]
    assert len(ids) == len(set(ids)) == 25
    assert second['next_offset'] is None
    assert all(item['partial'] for item in first['items'] + second['items'])


@pytest.mark.parametrize('broken', ['missing_header', 'missing_cursor', 'null_cursor', 'missing_rows',
                                   'bad_row_shape', 'repeat_cursor', 'unknown_flag', 'wrong_account'])
def test_incomplete_broker_responses_never_report_success_or_zero(harness, broken):
    h = harness
    h.http.rows['10000002'] = [execution(str(index)) for index in range(1, 6)]
    def transform(body, headers, call):
        if broken == 'missing_header': headers.clear()
        elif broken == 'missing_cursor': body.pop('ctx_area_nk100')
        elif broken == 'null_cursor': body['ctx_area_nk100'] = None
        elif broken == 'missing_rows': body.pop('output1')
        elif broken == 'bad_row_shape': body['output1'] = [{} , 'invalid']
        elif broken == 'repeat_cursor': body['ctx_area_nk100'] = '2'
        elif broken == 'unknown_flag': headers['tr_cont'] = 'Q'
        elif broken == 'wrong_account': body['CANO'] = '10000003'
        return body, headers, 200
    h.http.transform = transform
    result = h.service.read(h.db, h.first, period='week')
    assert result['status'] == 'incomplete'
    assert result['count'] is result['total_buy_amount'] is result['total_sell_amount'] is None
    assert result['items'] == [] and result['complete'] is False


@pytest.mark.parametrize('failure,status', [('auth', 'authentication_failed'), ('error', 'error'), ('network', 'error')])
def test_api_errors_and_auth_refresh_do_not_masquerade_as_empty(harness, failure, status):
    h = harness
    def transform(body, headers, call):
        if failure == 'network': raise ConnectionError('fake-sensitive-material')
        return {'rt_cd': '1', 'msg_cd': 'EGW00123' if failure == 'auth' else 'BROKER_ERROR',
                'msg1': 'fake-sensitive-material'}, headers, 401 if failure == 'auth' else 500
    h.http.transform = transform
    result = h.service.read(h.db, h.first, period='day')
    assert result['status'] == status and result['count'] is None
    assert 'fake-sensitive-material' not in json.dumps(result)
    assert len(h.http.gets) == (2 if failure == 'auth' else 1)
    if failure == 'auth':
        assert [call['force_refresh'] for call in h.tokens.calls] == [False, True]


def test_authentication_refresh_can_finish_the_same_query(harness):
    h = harness
    h.http.rows['10000002'] = [execution()]
    h.http.transform = lambda body, headers, call: (
        ({'rt_cd': '1', 'msg_cd': 'EGW00123'}, headers, 401)
        if len(h.http.gets) == 1 else (body, headers, 200))
    result = h.service.read(h.db, h.first, period='week')
    assert result['status'] == 'success' and result['count'] == 1
    assert result['broker_query_count'] == 2
    assert h.http.gets[0]['params'] == h.http.gets[1]['params']


def test_failure_after_a_successful_page_is_incomplete_without_partial_totals(harness):
    h = harness
    h.http.rows['10000002'] = [execution(str(index)) for index in range(1, 6)]
    h.http.transform = lambda body, headers, call: (
        ({'rt_cd': '1', 'msg_cd': 'BROKER_ERROR'}, headers, 500)
        if len(h.http.gets) > 1 else (body, headers, 200))
    result = h.service.read(h.db, h.first, period='week')
    assert result['status'] == 'incomplete'
    assert result['count'] is None and result['total_buy_amount'] is None and result['items'] == []


@pytest.mark.parametrize('change', [
    {'tot_ccld_qty': 'NaN'}, {'tot_ccld_qty': '-1'}, {'tot_ccld_qty': '3'},
    {'tot_ccld_qty': '.5'}, {'pdno': 'BAD'}, {'sll_buy_dvsn_cd': '00'},
    {'ccld_tmd': '256100'}, {'rmn_qty': '-1'},
])
def test_invalid_trade_fields_make_query_incomplete(harness, change):
    row = execution()
    row.update(change)
    harness.http.rows['10000002'] = [row]
    result = harness.service.read(harness.db, harness.first, period='week')
    assert result['status'] == 'incomplete' and result['count'] is None


def test_only_actual_fills_and_verified_fields_are_returned(harness):
    h = harness
    h.http.rows['10000002'] = [execution('0', filled='0'),
        execution('1', status='REJECTED'), execution('2', simulated=True),
        execution('3', side='01', ccld_tmd='124900'),
        execution('4', qty='10', filled='2', price='', cncl_yn='Y')]
    result = h.service.read(h.db, h.first, period='week')
    assert result['count'] == 2 and result['total_buy_amount'] is None
    sell = next(item for item in result['items'] if item['side'] == 'sell')
    buy = next(item for item in result['items'] if item['side'] == 'buy')
    assert sell['executed_at'] == '2026-11-04T12:49:00+09:00'
    assert buy['executed_at'] is None and buy['avg_fill_price'] is None
    assert buy['filled_qty'] == 2 and buy['filled_amount'] is None
    assert not {'cano', 'CANO', 'appkey', 'appsecret', 'access_token', 'raw', 'inquiry'} & set(sell)


def test_limits_and_historical_market_hours_never_publish_partial_success(harness):
    h = harness
    h.http.rows['10000002'] = [execution(str(index)) for index in range(1, 11)]
    h.service.budget_factory = lambda period: ExecutionReadBudget(max_calls=1, min_interval=0)
    result = h.service.read(h.db, h.first, period='week')
    assert result['status'] == 'incomplete' and result['code'] == 'call_budget_exceeded'
    h.http.gets.clear()
    h.service.now_provider = lambda: NOW.replace(hour=12)
    result = h.service.read(h.db, h.first, period='year')
    assert result['status'] == 'incomplete' and result['code'] == 'historical_query_after_close'
    assert h.http.gets == []


def test_page_and_deadline_limits_are_explicitly_incomplete(harness):
    h = harness
    h.http.rows['10000002'] = [execution(str(index)) for index in range(1, 31)]
    result = h.service.read(h.db, h.first, period='week')
    assert result['status'] == 'incomplete' and result['code'] == 'continuation_not_completed'
    assert len(h.http.gets) == 10
    elapsed = [0.0]
    h.service.budget_factory = lambda period: ExecutionReadBudget(
        min_interval=0, clock=lambda: elapsed[0], timeout_seconds=0.5)
    def slow(body, headers, call):
        elapsed[0] += 1
        return body, headers, 200
    h.http.transform = slow
    result = h.service.read(h.db, h.first, period='week')
    assert result['status'] == 'incomplete' and result['code'] == 'read_deadline_exceeded'
    assert result['count'] is None and result['items'] == []


def test_snapshot_cannot_cross_users_credentials_environment_or_expiry(harness):
    h = harness
    first = h.service.read(h.db, h.first, period='week')
    as_of = datetime.fromisoformat(first['end_at'])
    result = h.service.read(h.db, h.second, period='week', as_of=as_of)
    assert result['status'] == 'incomplete'
    from app.db.models import UserBrokerCredential
    row = h.db.query(UserBrokerCredential).filter_by(user_id=h.first.id, provider='kis').one()
    old = h.crypto.decrypt(row.encrypted_payload)
    row.encrypted_payload = h.crypto.encrypt({**old, 'account_no': '10000004'})
    h.db.commit()
    assert h.service.read(h.db, h.first, period='week', as_of=as_of)['status'] == 'incomplete'
    h.cache.ttl = -1
    assert h.service.read(h.db, h.first, period='week', as_of=as_of)['status'] == 'incomplete'


def test_authenticated_routes_enforce_role_and_account_and_read_only(harness):
    h = harness
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: h.db
    app.dependency_overrides[get_execution_history_service] = lambda: h.service
    client = TestClient(app)
    assert client.get('/kis/account/executions').status_code == 401
    app.dependency_overrides[get_current_user] = lambda: h.first
    assert client.get('/kis/account/executions').status_code == 403
    h.http.rows['10000002'] = [execution()]
    response = client.get('/users/me/trading/executions?period=week&user_id=0&CANO=10000001')
    assert response.status_code == 200 and response.json()['count'] == 1
    assert response.headers['cache-control'] == 'no-store, private'
    assert h.http.gets[-1]['params']['CANO'] == '10000002'
    assert client.get('/users/me/trading/executions?period=all').status_code == 422
    assert client.get('/users/me/trading/executions?as_of=2099-01-01T00:00:00Z').status_code == 422
    assert client.post('/users/me/trading/executions').status_code == 405
    app.dependency_overrides[get_current_user] = lambda: h.admin
    assert client.get('/users/me/trading/executions').status_code == 403
    assert client.get('/kis/account/executions?period=week').json()['count'] == 0
    assert h.http.gets[-1]['params']['CANO'] == '10000001'
    assert h.db.query(OrderLog).count() == 0


def test_missing_account_or_corrupt_credentials_is_not_success_zero(harness):
    from app.db.models import UserBrokerCredential
    h = harness
    h.db.query(UserBrokerCredential).filter_by(user_id=h.first.id).delete()
    h.db.commit()
    result = h.service.read(h.db, h.first)
    assert result['status'] == 'not_connected' and result['count'] is None
    assert h.http.gets == []
