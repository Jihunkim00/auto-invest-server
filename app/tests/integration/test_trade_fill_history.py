"""PR143: isolated DB + persisted FakeKisClient evidence only."""
from datetime import UTC, datetime, timedelta
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.db.database import get_db
from app.db.models import OrderLog, User, UserBrokerCredential
from app.routes.trade_fills import router
from app.services.auth_dependencies import get_current_user
from app.services.trade_fill_history_service import KST, history_window, list_trade_fills

NOW = datetime(2026, 11, 9, 15, tzinfo=KST)


class FakeKisClient:
    @staticmethod
    def evidence(order, *, environment='live', quantity=2, price=15000, clock='100100'):
        row = {'odno': order.kis_odno, 'pdno': order.symbol, 'prdt_name': '가짜 종목',
               'sll_buy_dvsn_cd': '02' if order.side == 'buy' else '01',
               'ord_dt': order.submitted_at.replace(tzinfo=UTC).astimezone(KST).strftime('%Y%m%d'),
               'ord_tmd': '100000', 'ord_qty': str(order.qty),
               'tot_ccld_qty': str(quantity), 'avg_prvs': str(price) if price else '',
               'rmn_qty': str(order.qty - quantity)}
        if clock is not None:
            row['ccld_tmd'] = clock
        return {'matched_order': row, 'inquiry': {
            'provider': 'kis', 'environment': environment, 'complete': True,
            'owner_user_id': order.owner_user_id,
            'broker_account_id': f'user:{order.owner_user_id}:kis:KR' if order.owner_user_id else 'admin:kis:KR',
        }}


@pytest.fixture
def owners(db_session, fake_kis_admin_credentials):
    users = [User(username='admin-pr143', role='admin'), User(username='test01-pr143', role='user'),
             User(username='other-pr143', role='user')]
    db_session.add_all(users)
    db_session.flush()
    for user in users[1:]:
        db_session.add(UserBrokerCredential(user_id=user.id, provider='kis',
            environment='live', encrypted_payload='fake-no-decryption-needed'))
    db_session.commit()
    return users


def seed(db, owner, *, day=NOW, status='FILLED', side='buy', qty=2,
         filled=2, environment='live', clock='100100', price=15000, request=None, number=None):
    order = OrderLog(owner_user_id=owner, broker='kis', market='KR', symbol='FAKE',
        side=side, order_type='market', qty=qty, requested_qty=qty,
        internal_status=status, filled_qty=filled, avg_fill_price=999999,
        submitted_at=day.replace(hour=0 if clock == '000000' else 10, minute=0, second=0, microsecond=0).astimezone(UTC).replace(tzinfo=None),
        request_payload=json.dumps(request or {}))
    db.add(order)
    db.flush()
    order.kis_odno = number or f'{order.id:010d}'
    order.last_sync_payload = json.dumps(FakeKisClient.evidence(order,
        quantity=filled, environment=environment, clock=clock, price=price))
    db.commit()
    return order


def read(db, user, **kwargs):
    return list_trade_fills(db, user=user, provider='kis', period='today',
                           limit=20, offset=0, now=NOW, **kwargs)


def test_owner_environment_broker_isolation_and_safe_whitelist(db_session, owners):
    admin, first, second = owners
    seed(db_session, None)
    seed(db_session, first.id)
    seed(db_session, second.id)
    seed(db_session, first.id, environment='paper')
    wrong_broker = seed(db_session, first.id)
    wrong_broker.broker = 'alpaca'
    db_session.commit()
    for user in owners:
        result = read(db_session, user)
        assert result['summary']['count'] == 1
        assert result['summary']['buy_amount'] == 30000
        assert result['environment'] == 'live'
        assert set(result['items'][0]) == {
            'id', 'symbol', 'name', 'side', 'quantity', 'average_price', 'amount',
            'currency', 'partial', 'trade_date', 'filled_at', 'time_precision'}
        assert 'inquiry' not in json.dumps(result)
    assert read(db_session, admin)['items'][0]['id'] != read(db_session, first)['items'][0]['id']


@pytest.mark.parametrize('status,filled', [
    ('REQUESTED', 2), ('PENDING', 0), ('SUBMITTED', 0), ('ACCEPTED', 0),
    ('UNKNOWN_STALE', 0), ('REJECTED', 2), ('REJECTED_BY_SAFETY_GATE', 2),
    ('CANCELED', 0), ('FAILED', 0), ('FILLED', 0),
])
def test_attempts_and_zero_fills_are_not_trades(db_session, owners, status, filled):
    seed(db_session, owners[1].id, status=status, filled=filled)
    assert read(db_session, owners[1])['items'] == []


@pytest.mark.parametrize('metadata', [
    {'dry_run': True}, {'simulated': True}, {'mode': 'kis_user_simulation'},
    {'source': 'dry_run_sell_simulation'}, {'owner_user_id': 999},
    {'credential_environment': 'paper'},
])
def test_simulation_or_conflicting_scope_is_hidden(db_session, owners, metadata):
    seed(db_session, owners[1].id, request=metadata)
    assert read(db_session, owners[1])['items'] == []


@pytest.mark.parametrize('status', ['PARTIALLY_FILLED', 'CANCELED', 'FAILED', 'PENDING'])
def test_verified_partial_quantity_and_price_only(db_session, owners, status):
    seed(db_session, owners[1].id, qty=10, filled=2, status=status)
    item = read(db_session, owners[1])['items'][0]
    assert (item['quantity'], item['average_price'], item['amount'], item['partial']) == (2, 15000, 30000, True)


@pytest.mark.parametrize('change', [
    {'tot_ccld_qty': 'NaN'}, {'tot_ccld_qty': '-1'}, {'tot_ccld_qty': '3'},
    {'ord_dt': '20260230'}, {'ccld_tmd': '256100'}, {'pdno': 'OTHER'},
    {'sll_buy_dvsn_cd': '01'}, {'odno': 'MISMATCH'},
])
def test_invalid_execution_evidence_fails_closed(db_session, owners, change):
    order = seed(db_session, owners[1].id)
    payload = json.loads(order.last_sync_payload)
    payload['matched_order'].update(change)
    order.last_sync_payload = json.dumps(payload)
    db_session.commit()
    assert read(db_session, owners[1])['items'] == []


def test_unknown_stale_and_status_only_filled_never_invent_a_trade(db_session, owners):
    for status in ['UNKNOWN_STALE', 'FILLED']:
        order = seed(db_session, owners[1].id, status=status)
        order.last_sync_payload = '{"inquiry": {"orders": []}}'
    db_session.commit()
    assert read(db_session, owners[1])['items'] == []


def test_date_precision_does_not_use_order_or_sync_time_or_unknown_price(db_session, owners):
    order = seed(db_session, owners[1].id, clock=None, price=None)
    order.filled_at = NOW.astimezone(UTC).replace(tzinfo=None)
    db_session.commit()
    result = read(db_session, owners[1])
    item = result['items'][0]
    assert item['filled_at'] is None
    assert item['trade_date'] == '2026-11-09' and item['time_precision'] == 'day'
    assert item['average_price'] is None and item['amount'] is None
    assert result['summary']['unknown_amount_count'] == result['summary']['date_only_count'] == 1
    assert result['summary']['buy_amount'] is None


def test_pr142_sync_evidence_is_read_without_synthetic_fill_timestamp(db_session, owners):
    from types import SimpleNamespace
    from app.services.kis_order_mapper import map_kis_order_row
    from app.services.user_kis_order_sync_service import UserKisOrderSyncService

    order = seed(db_session, owners[1].id, status='PENDING', filled=0)
    evidence = FakeKisClient.evidence(order, clock=None)
    evidence['inquiry']['orders'] = [evidence['matched_order']]
    service = UserKisOrderSyncService(SimpleNamespace(user_id=owners[1].id, environment='live'))
    service._apply_mapped_result(order, map_kis_order_row(evidence['matched_order']),
                                evidence['inquiry'], now=NOW.astimezone(UTC).replace(tzinfo=None))
    db_session.commit()
    assert order.internal_status == 'FILLED' and order.filled_at is None
    item = read(db_session, owners[1])['items'][0]
    assert item['quantity'] == 2 and item['filled_at'] is None


def test_alpaca_uses_latest_broker_fill_and_isolates_environment(db_session, owners):
    user = owners[1]
    db_session.add(UserBrokerCredential(user_id=user.id, provider='alpaca',
        environment='paper', encrypted_payload='fake'))
    row = OrderLog(owner_user_id=user.id, broker='alpaca', market='US', symbol='FAKE',
        side='buy', order_type='market', qty=10, internal_status='PARTIALLY_FILLED',
        broker_order_id='fake-alpaca', submitted_at=datetime(2026, 11, 8, 16),
        request_payload=json.dumps({'credential_environment': 'paper'}),
        response_payload=json.dumps({'id': 'fake-alpaca', 'symbol': 'FAKE', 'side': 'buy',
            'qty': '10', 'filled_qty': '0', 'filled_at': None}))
    row.last_sync_payload = json.dumps({'id': 'fake-alpaca', 'symbol': 'FAKE', 'side': 'buy',
        'qty': '10', 'filled_qty': '2', 'filled_avg_price': '15.5',
        'filled_at': '2026-11-08T16:01:00Z'})
    db_session.add(row)
    db_session.commit()
    result = list_trade_fills(db_session, user=user, provider='alpaca', period='today',
                             limit=20, offset=0, now=NOW)
    assert result['summary']['buy_amount'] == 31
    assert result['items'][0]['quantity'] == 2
    assert result['items'][0]['filled_at'] == '2026-11-09T01:01:00+09:00'
    assert read(db_session, user)['items'] == []


def test_deduplicate_cumulative_order_snapshots_before_summary_and_pagination(db_session, owners):
    seed(db_session, owners[1].id, qty=10, filled=2, number='0000013')
    seed(db_session, owners[1].id, qty=10, filled=5, number='13', status='CANCELED')
    seed(db_session, owners[1].id, side='sell')
    result = read(db_session, owners[1])
    assert result['summary']['count'] == 2
    assert result['summary']['buy_amount'] == 75000
    assert result['summary']['sell_amount'] == 30000


@pytest.mark.parametrize('period,days', [('today', 1), ('week', 7), ('month', 30), ('year', 365)])
def test_kst_period_boundaries_and_all_pages(db_session, owners, period, days):
    start, end = history_window(period, NOW)
    assert start == datetime(2026, 11, 9, tzinfo=KST) - timedelta(days=days - 1)
    # More than the old twenty-row feed, including history at the lower edge.
    for index in range(25):
        seed(db_session, owners[1].id, day=start, side='buy' if index % 2 else 'sell')
    seed(db_session, owners[1].id, day=start - timedelta(days=1))
    seed(db_session, owners[1].id, day=NOW + timedelta(days=1))
    pages = [list_trade_fills(db_session, user=owners[1], provider='kis', period=period,
             limit=10, offset=offset, now=NOW) for offset in (0, 10, 20)]
    assert [page['next_offset'] for page in pages] == [10, 20, None]
    assert all(page['summary']['count'] == 25 for page in pages)
    ids = [item['id'] for page in pages for item in page['items']]
    assert len(ids) == len(set(ids)) == 25
    assert all(page['start_at'].endswith('+09:00') for page in pages)


def test_kst_midnight_uses_trade_day_not_sync_day(db_session, owners):
    seed(db_session, owners[1].id, day=NOW - timedelta(days=1), clock='235959')
    seed(db_session, owners[1].id, clock='000000')
    result = list_trade_fills(db_session, user=owners[1], provider='kis', period='today',
        limit=20, offset=0, now=datetime(2026, 11, 8, 15, 0, 1, tzinfo=UTC))
    assert result['summary']['count'] == 1
    assert result['items'][0]['filled_at'] == '2026-11-09T00:00:00+09:00'


def test_authenticated_route_read_only_and_owner_cannot_be_overridden(db_session, owners):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    assert client.get('/trading/fills').status_code == 401
    seed(db_session, None, day=datetime.now(KST))
    own = seed(db_session, owners[1].id, day=datetime.now(KST), clock='000000')
    before = [(row.id, row.internal_status, row.last_sync_payload) for row in db_session.query(OrderLog)]
    app.dependency_overrides[get_current_user] = lambda: owners[1]
    response = client.get('/trading/fills?owner_user_id=0&period=year')
    assert response.status_code == 200
    assert [item['id'] for item in response.json()['items']] == [f'kis:{own.id}']
    assert client.get('/trading/fills?period=all').status_code == 422
    assert client.get('/trading/fills?offset=-1').status_code == 422
    assert client.get('/trading/fills?limit=101').status_code == 422
    assert client.get('/trading/fills?as_of=2026-01-01T00:00:00').status_code == 422
    assert client.get('/trading/fills?as_of=2099-01-01T00:00:00Z').status_code == 422
    assert client.post('/trading/fills').status_code == 405
    assert [(row.id, row.internal_status, row.last_sync_payload) for row in db_session.query(OrderLog)] == before
