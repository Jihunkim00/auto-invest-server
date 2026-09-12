from datetime import datetime, timezone
import json
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

import app.db.init_db as db_init
from app.config import get_settings
from app.db.database import get_db
from app.db.models import OrderLog, PositionLifecycle, SignalLog, TradeRunLog, User, UserTradingRiskState, UserTradingSettings
from app.main import app
from app.services.auth_service import create_session
from app.services.user_risk_state_service import UserRiskStateService
from app.services.user_trading_context_service import UserTradingContext, apply_user_owner


_KST = ZoneInfo('Asia/Seoul')


def _user(db_session, username, role='user'):
    row = User(
        username=username,
        role=role,
        enabled=True,
        setup_completed=True,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _client(db_session, user):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.cookies.set(get_settings().session_cookie_name, create_session(db_session, user))
    return client


@pytest.fixture(autouse=True)
def clear_app_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _run(owner_id, key):
    return TradeRunLog(
        owner_user_id=owner_id,
        run_key=key,
        trigger_source='user_test',
        symbol='005930',
        stage='done',
        result='hold',
    )


def _signal(owner_id):
    return SignalLog(
        owner_user_id=owner_id,
        symbol='005930',
        action='hold',
        signal_status='hold',
        trigger_source='user_test',
    )


def _order(owner_id, *, broker='kis', market='KR', status='FILLED', realized_pl=None, currency=None, payload=None):
    return OrderLog(
        owner_user_id=owner_id,
        broker=broker,
        market=market,
        symbol='005930' if market == 'KR' else 'AAPL',
        side='sell',
        order_type='market',
        internal_status=status,
        filled_qty=1,
        avg_fill_price=100,
        realized_pl=realized_pl,
        currency=currency,
        response_payload=payload,
        filled_at=datetime.now(timezone.utc),
    )


def test_user_history_is_scoped_for_lists_and_ids(db_session):
    user_a = _user(db_session, 'ownership-a')
    user_b = _user(db_session, 'ownership-b')
    run_a = _run(user_a.id, 'run-a')
    run_b = _run(user_b.id, 'run-b')
    signal_a = _signal(user_a.id)
    signal_b = _signal(user_b.id)
    order_a = _order(user_a.id, realized_pl=10)
    order_b = _order(user_b.id, realized_pl=20)
    db_session.add_all([run_a, run_b, signal_a, signal_b, order_a, order_b])
    db_session.commit()

    client_a = _client(db_session, user_a)
    assert [item['id'] for item in client_a.get('/users/me/trading/runs').json()['items']] == [run_a.id]
    assert [item['id'] for item in client_a.get('/users/me/trading/signals').json()['items']] == [signal_a.id]
    assert [item['id'] for item in client_a.get('/users/me/trading/orders').json()['items']] == [order_a.id]
    assert client_a.get(f'/users/me/trading/runs/{run_b.id}').status_code == 404
    assert client_a.get(f'/users/me/trading/signals/{signal_b.id}').status_code == 404
    assert client_a.get(f'/users/me/trading/orders/{order_b.id}').status_code == 404
    # Query-string owner overrides are ignored because the route has no owner
    # input; ownership comes from the authenticated session only.
    response = client_a.get(f'/users/me/trading/orders?user_id={user_b.id}')
    assert [item['id'] for item in response.json()['items']] == [order_a.id]


def test_context_derives_owner_and_admin_context_keeps_null_owner(db_session):
    user = _user(db_session, 'context-user')
    admin = _user(db_session, 'context-admin', role='admin')
    context = UserTradingContext.from_user(user)
    row = _run(None, 'context-run')
    apply_user_owner(row, user)
    assert row.owner_user_id == user.id
    assert context.record_values({'owner_user_id': admin.id})['owner_user_id'] == user.id
    assert UserTradingContext.from_user(admin).owner_user_id is None


def test_settings_are_disabled_by_default_and_only_safe_limits_are_mutable(db_session):
    user = _user(db_session, 'settings-user')
    client = _client(db_session, user)
    defaults = client.get('/users/me/trading/settings')
    assert defaults.status_code == 200
    body = defaults.json()
    assert body['user_id'] == user.id
    assert body['enabled'] is False
    assert body['paper_trading_enabled'] is False
    assert body['live_trading_enabled'] is False
    assert body['max_daily_trades'] == 2

    updated = client.patch(
        '/users/me/trading/settings',
        json={'max_daily_trades': 1, 'max_position_pct': 8},
    )
    assert updated.status_code == 200
    assert updated.json()['max_daily_trades'] == 1
    assert updated.json()['max_position_pct'] == 8
    enabled = client.patch('/users/me/trading/settings', json={'live_trading_enabled': True})
    assert enabled.status_code == 200
    assert enabled.json()['live_trading_enabled'] is True


def test_risk_state_isolated_by_user_provider_currency_and_excludes_simulated_and_admin(db_session):
    user_a = _user(db_session, 'risk-a')
    user_b = _user(db_session, 'risk-b')
    admin = _user(db_session, 'risk-admin', role='admin')
    db_session.add(UserTradingSettings(
        user_id=user_a.id,
        enabled=True,
        paper_trading_enabled=True,
        max_daily_trades=1,
        max_daily_loss_pct=0.02,
        max_open_positions=1,
    ))
    kis = _order(
        user_a.id,
        realized_pl=-100,
        currency='KRW',
        payload=json.dumps({'daily_loss_pct': -0.03}),
    )
    simulated = _order(
        user_a.id,
        realized_pl=-500,
        currency='KRW',
        status='DRY_RUN_SIMULATED',
    )
    alpaca = _order(user_a.id, broker='alpaca', market='US', realized_pl=50, currency='USD')
    other_user = _order(user_b.id, realized_pl=-900, currency='KRW')
    admin_order = _order(admin.id, realized_pl=-900, currency='KRW')
    db_session.add_all([kis, simulated, alpaca, other_user, admin_order])
    db_session.commit()

    service = UserRiskStateService()
    assert service.get_daily_trade_count(db_session, user_a) == 1
    assert service.get_daily_realized_pl(db_session, user_a) == -100
    risk = service.get_user_risk_state(db_session, user_a)
    assert risk['daily_trade_count'] == 1
    assert risk['daily_realized_pl'] == -100
    assert risk['daily_loss_limit_hit'] is True
    assert risk['risk_allowed'] is False
    assert 'max_daily_trades_reached' in risk['risk_flags']
    assert 'daily_loss_limit_reached' in risk['risk_flags']
    assert service.get_daily_trade_count(db_session, user_a, provider='alpaca', market='US') == 1
    assert service.get_daily_realized_pl(db_session, user_a, provider='alpaca', market='US') == 50
    assert service.get_daily_trade_count(db_session, user_b) == 1
    assert service.get_daily_realized_pl(db_session, user_b) == -900

    client_a = _client(db_session, user_a)
    response = client_a.get('/users/me/trading/risk-status')
    assert response.status_code == 200
    assert response.json()['owner_user_id'] == user_a.id
    assert response.json()['daily_realized_pl'] == -100


def test_risk_snapshot_can_supply_future_reconciled_loss_without_cross_user_access(db_session):
    user_a = _user(db_session, 'snapshot-a')
    user_b = _user(db_session, 'snapshot-b')
    today = datetime.now(_KST).date()
    db_session.add(UserTradingRiskState(
        user_id=user_a.id,
        provider='kis',
        market='KR',
        currency='KRW',
        trading_date=today,
        daily_trade_count=2,
        daily_realized_pl=-25,
        daily_loss_pct=-0.025,
    ))
    db_session.commit()
    service = UserRiskStateService()
    assert service.get_daily_trade_count(db_session, user_a) == 2
    assert service.get_daily_realized_pl(db_session, user_a) == -25
    assert service.get_daily_trade_count(db_session, user_b) == 0
    assert service.get_daily_realized_pl(db_session, user_b) == 0


def test_legacy_trading_tables_migrate_owner_columns_without_backfill(monkeypatch):
    legacy_engine = create_engine('sqlite:///:memory:', future=True)
    with legacy_engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE orders (id INTEGER PRIMARY KEY, broker VARCHAR(20), market VARCHAR(10), created_at DATETIME)')
        connection.exec_driver_sql('CREATE TABLE signals (id INTEGER PRIMARY KEY, created_at DATETIME)')
        connection.exec_driver_sql('CREATE TABLE trade_run_logs (id INTEGER PRIMARY KEY, created_at DATETIME)')
        connection.exec_driver_sql('CREATE TABLE position_lifecycles (id INTEGER PRIMARY KEY, created_at DATETIME)')
        connection.exec_driver_sql('INSERT INTO orders (id, broker, market) VALUES (1, \'kis\', \'KR\')')

    monkeypatch.setattr(db_init, 'engine', legacy_engine)
    db_init._migrate_user_trading_ownership_columns_if_needed()
    inspector = inspect(legacy_engine)
    for table_name in ('orders', 'signals', 'trade_run_logs', 'position_lifecycles'):
        columns = {column['name'] for column in inspector.get_columns(table_name)}
        assert 'owner_user_id' in columns
    order = legacy_engine.connect().exec_driver_sql('SELECT owner_user_id FROM orders WHERE id = 1').scalar_one()
    assert order is None
    order_indexes = {index['name'] for index in inspector.get_indexes('orders')}
    assert 'ix_orders_owner_user_id_created_at' in order_indexes
