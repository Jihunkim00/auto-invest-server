from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.database import get_db
from app.db.models import OrderLog, SignalLog, TradeRunLog, User, UserTradingSettings
from app.main import app
from app.services.auth_service import create_session
from app.routes.user_trading import get_user_trading_execution_service
from app.services.user_broker_account_service import UserBrokerAccountService
from app.services.user_broker_credential_service import UserBrokerCredentialService
from app.services.user_risk_state_service import UserRiskStateService
from app.services.user_symbol_analysis_service import UserSymbolAnalysisService
from app.services.user_trading_execution_service import UserTradingExecutionService
from app.services.market_session_service import MarketSessionService


def _user(db_session, username: str) -> User:
    row = User(username=username, role='user', enabled=True, setup_completed=True)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


class FakeAccountService(UserBrokerAccountService):
    def __init__(self):
        pass

    def get_broker_snapshot(self, db, user, provider):
        currency = 'KRW' if provider == 'kis' else 'USD'
        return {
            'provider': provider,
            'environment': 'paper',
            'connected': True,
            'account': {
                'currency': currency,
                'portfolio_value': 10000.0,
                'equity': 10000.0,
                'buying_power': 10000.0,
                'cash': 10000.0,
            },
            'positions': [],
            'open_orders': [],
        }


class FakeCredentialService(UserBrokerCredentialService):
    def __init__(self):
        pass

    def get_credentials(self, db, user, provider):
        return {
            'environment': 'paper',
            'api_key': f'user-{user.id}-key',
            'secret_key': f'user-{user.id}-secret',
        }


class FakeAnalysisService(UserSymbolAnalysisService):
    def __init__(self, *, action='buy'):
        self.action = action

    def analyze(self, db, *, provider, symbol, gate_level=2, now=None):
        return {
            'provider': provider,
            'market': 'KR' if provider == 'kis' else 'US',
            'symbol': symbol,
            'requested_symbol': symbol,
            'analyzed_symbol': symbol,
            'returned_symbol': symbol,
            'action': self.action,
            'reason': 'fake_analysis',
            'current_price': 100.0,
            'final_buy_score': 80.0,
            'final_sell_score': 10.0,
            'quant_buy_score': 80.0,
            'quant_sell_score': 10.0,
            'confidence': 0.8,
            'indicator_payload': {'price': 100.0},
            'risk_flags': [],
            'gating_notes': [],
            'hard_blocked': False,
        }


class FakeSessionService(MarketSessionService):
    def get_session_status(self, market, now=None):
        return {
            'market': market,
            'is_market_open': True,
            'is_entry_allowed_now': True,
            'local_time': '2026-09-11T10:00:00+09:00',
        }


class FakeAlpacaOrderClient:
    def __init__(self, calls):
        self.calls = calls

    def submit_market_buy_qty(self, *, symbol, qty):
        self.calls.append({'symbol': symbol, 'qty': qty})
        return SimpleNamespace(
            id='paper-order-1',
            status='filled',
            client_order_id='client-order-1',
            filled_qty=qty,
            filled_avg_price=100.0,
        )


def _client(db_session, user, service):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_user_trading_execution_service] = lambda: service
    client = TestClient(app)
    client.cookies.set(get_settings().session_cookie_name, create_session(db_session, user))
    return client


@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _service(*, analysis='buy', alpaca_factory=None):
    return UserTradingExecutionService(
        account_service=FakeAccountService(),
        credential_service=FakeCredentialService(),
        analysis_service=FakeAnalysisService(action=analysis),
        session_service=FakeSessionService(),
        alpaca_client_factory=alpaca_factory or (lambda credentials: None),
    )


def test_user_trading_mode_has_exactly_two_modes_and_live_permission_requires_explicit_opt_in(db_session):
    user = _user(db_session, 'pr127-mode')
    service = _service()
    client = _client(db_session, user, service)

    initial = client.get('/users/me/trading/settings')
    assert initial.status_code == 200
    assert initial.json()['available_trading_modes'] == ['paper', 'live']
    assert initial.json()['trading_mode'] == 'paper'

    paper = client.patch('/users/me/trading/settings', json={'trading_mode': 'paper'})
    assert paper.status_code == 200
    assert paper.json()['enabled'] is True
    assert paper.json()['paper_trading_enabled'] is True
    assert paper.json()['live_trading_enabled'] is False

    live = client.patch('/users/me/trading/settings', json={'trading_mode': 'live'})
    assert live.status_code == 200
    assert live.json()['trading_mode'] == 'live'
    assert live.json()['live_trading_enabled'] is False
    assert live.json()['paper_trading_enabled'] is False

    enabled = client.patch('/users/me/trading/settings', json={'live_trading_enabled': True})
    assert enabled.status_code == 200
    assert enabled.json()['live_trading_enabled'] is True
    assert client.patch('/users/me/trading/settings', json={'trading_mode': 'simulation'}).status_code == 422

    back_to_paper = client.patch('/users/me/trading/settings', json={'trading_mode': 'paper'})
    assert back_to_paper.json()['paper_trading_enabled'] is True
    assert back_to_paper.json()['live_trading_enabled'] is False


def test_kis_paper_run_creates_owned_simulation_without_broker_submit(db_session):
    user = _user(db_session, 'pr127-kis')
    db_session.add(UserTradingSettings(
        user_id=user.id,
        enabled=True,
        paper_trading_enabled=True,
        live_trading_enabled=False,
        trading_mode='paper',
    ))
    db_session.commit()
    client = _client(db_session, user, _service())

    response = client.post('/users/me/trading/run-once', json={'provider': 'kis', 'symbol': '5930'})
    assert response.status_code == 200
    body = response.json()
    assert body['result'] == 'simulated'
    assert body['requested_symbol'] == '005930'
    assert body['analyzed_symbol'] == '005930'
    assert body['returned_symbol'] == '005930'
    assert body['symbol_match'] is True
    assert body['real_order_submitted'] is False
    assert body['broker_submit_called'] is False
    assert body['manual_submit_called'] is False

    order = db_session.query(OrderLog).one()
    run = db_session.query(TradeRunLog).one()
    signal = db_session.query(SignalLog).one()
    assert order.owner_user_id == user.id
    assert order.internal_status == 'DRY_RUN_SIMULATED'
    assert order.broker_order_id is None
    assert run.owner_user_id == user.id
    assert signal.owner_user_id == user.id


def test_kis_hold_and_live_mode_create_no_order(db_session):
    user = _user(db_session, 'pr127-blocks')
    db_session.add(UserTradingSettings(
        user_id=user.id,
        enabled=True,
        paper_trading_enabled=True,
        live_trading_enabled=False,
        trading_mode='paper',
    ))
    db_session.commit()
    hold_client = _client(db_session, user, _service(analysis='hold'))
    hold = hold_client.post('/users/me/trading/run-once', json={'provider': 'kis', 'symbol': '005930'})
    assert hold.json()['result'] == 'hold'
    assert db_session.query(OrderLog).count() == 0

    live_client = _client(db_session, user, _service())
    live_client.patch('/users/me/trading/settings', json={'trading_mode': 'live'})
    live = live_client.post('/users/me/trading/run-once', json={'provider': 'kis', 'symbol': '005930'})
    assert live.json()['result'] == 'blocked'
    assert live.json()['reason'] == 'live_trading_disabled'
    assert db_session.query(OrderLog).count() == 0


def test_alpaca_paper_order_uses_user_credentials_and_persists_status(db_session):
    user = _user(db_session, 'pr127-alpaca')
    db_session.add(UserTradingSettings(
        user_id=user.id,
        enabled=True,
        paper_trading_enabled=True,
        live_trading_enabled=False,
        trading_mode='paper',
    ))
    db_session.commit()
    calls = []
    received_credentials = []

    def factory(credentials):
        received_credentials.append(dict(credentials))
        return FakeAlpacaOrderClient(calls)

    client = _client(db_session, user, _service(alpaca_factory=factory))
    response = client.post('/users/me/trading/run-once', json={'provider': 'alpaca', 'symbol': 'AAPL'})
    assert response.status_code == 200
    assert response.json()['result'] == 'submitted'
    assert response.json()['real_order_submitted'] is True
    assert calls == [{'symbol': 'AAPL', 'qty': 10}]
    assert received_credentials[0]['api_key'] == f'user-{user.id}-key'
    assert 'secret_key' not in response.text

    order = db_session.query(OrderLog).one()
    assert order.owner_user_id == user.id
    assert order.broker_order_id == 'paper-order-1'
    assert order.broker_status == 'filled'
    assert order.internal_status == 'FILLED'


def test_run_once_rejects_user_owned_fields_in_request(db_session):
    user = _user(db_session, 'pr127-request')
    client = _client(db_session, user, _service())
    response = client.post(
        '/users/me/trading/run-once',
        json={
            'provider': 'kis',
            'symbol': '005930',
            'owner_user_id': user.id,
            'live_execution': True,
            'bypass_risk': True,
        },
    )
    assert response.status_code == 422


def test_partially_filled_user_order_blocks_duplicate_run(db_session):
    user = _user(db_session, 'pr127-partial-duplicate')
    db_session.add(UserTradingSettings(
        user_id=user.id,
        enabled=True,
        paper_trading_enabled=True,
        live_trading_enabled=False,
        trading_mode='paper',
    ))
    db_session.add(OrderLog(
        owner_user_id=user.id,
        broker='kis',
        market='KR',
        symbol='005930',
        side='buy',
        order_type='market',
        qty=10,
        requested_qty=10,
        filled_qty=3,
        remaining_qty=7,
        currency='KRW',
        internal_status='PARTIALLY_FILLED',
        broker_status='PARTIALLY_FILLED',
    ))
    db_session.commit()

    client = _client(db_session, user, _service())
    response = client.post(
        '/users/me/trading/run-once',
        json={'provider': 'kis', 'symbol': '005930'},
    )

    assert response.status_code == 200
    assert response.json()['result'] == 'blocked'
    assert response.json()['reason'] == 'duplicate_open_order'
    assert db_session.query(OrderLog).count() == 1


def test_partially_filled_order_counts_once_toward_daily_trade_count(db_session):
    user = _user(db_session, 'pr127-partial-daily-count')
    as_of = datetime(2026, 9, 12, 1, 0, tzinfo=UTC)
    db_session.add(OrderLog(
        owner_user_id=user.id,
        broker='kis',
        market='KR',
        symbol='005930',
        side='buy',
        order_type='market',
        qty=10,
        requested_qty=10,
        filled_qty=3,
        remaining_qty=7,
        currency='KRW',
        internal_status='PARTIALLY_FILLED',
        broker_status='PARTIALLY_FILLED',
        created_at=as_of,
        filled_at=as_of,
    ))
    db_session.commit()

    service = UserRiskStateService()
    assert service.get_daily_trade_count(
        db_session,
        user,
        provider='kis',
        market='KR',
        as_of=as_of,
    ) == 1
