from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import User, UserBrokerCredential
from app.main import app
from app.routes.user_brokers import get_user_broker_account_service
from app.services.auth_service import create_session
from app.services.broker_credential_crypto_service import (
    BrokerCredentialCryptoService,
)
from app.services.user_broker_account_service import (
    ALPACA_BASE_URLS,
    KIS_BALANCE_PATH,
    KIS_OPEN_ORDERS_PATH,
    KIS_TOKEN_PATH,
    UserBrokerAccountService,
    UserBrokerAuthenticationError,
    UserKisTokenManager,
    get_user_kis_token_manager,
)
from app.services.user_broker_credential_service import (
    UserBrokerCredentialService,
)


@dataclass
class FakeResponse:
    body: object
    status_code: int = 200

    def json(self):
        return self.body


class FakeBrokerHttp:
    def __init__(
        self,
        *,
        expire_first_for: set[str] | None = None,
        always_expired_for: set[str] | None = None,
    ):
        self.expire_first_for = expire_first_for or set()
        self.always_expired_for = always_expired_for or set()
        self.posts: list[dict] = []
        self.gets: list[dict] = []
        self.token_counts: dict[str, int] = {}

    def post(self, url, data, headers, timeout):
        payload = json.loads(data)
        app_key = payload['appkey']
        count = self.token_counts.get(app_key, 0) + 1
        self.token_counts[app_key] = count
        self.posts.append({
            'url': url,
            'data': data,
            'headers': headers,
            'timeout': timeout,
        })
        return FakeResponse({
            'access_token': f'token-{app_key}-{count}',
            'access_token_token_expired': '2099-01-01 00:00:00',
        })

    def get(self, url, **kwargs):
        self.gets.append({'url': url, **kwargs})
        if '/v2/account' in url:
            key = kwargs['headers']['APCA-API-KEY-ID']
            return FakeResponse({
                'currency': 'USD',
                'cash': '1000',
                'buying_power': '2500',
                'equity': '3200',
                'portfolio_value': '3200',
                'key_marker': key,
            })
        if '/v2/positions' in url:
            return FakeResponse([{
                'symbol': 'AAPL',
                'qty': '2',
                'avg_entry_price': '100',
                'current_price': '110',
                'market_value': '220',
                'cost_basis': '200',
                'unrealized_pl': '20',
            }])
        if '/v2/orders' in url:
            return FakeResponse([{
                'id': 'alpaca-order-1',
                'symbol': 'AAPL',
                'side': 'buy',
                'qty': '2',
                'filled_qty': '1',
                'type': 'limit',
                'status': 'open',
                'submitted_at': '2099-01-01T00:00:00Z',
            }])

        key = kwargs['headers']['appkey']
        token = kwargs['headers']['authorization']
        if key in self.always_expired_for or (
            key in self.expire_first_for and self.token_counts.get(key) == 1
        ):
            return FakeResponse({
                'rt_cd': '1',
                'msg_cd': 'EGW00123',
                'msg1': 'expired token',
            })
        if url.endswith(KIS_BALANCE_PATH):
            return FakeResponse({
                'rt_cd': '0',
                'output2': {
                    'dnca_tot_amt': '1000000',
                    'ord_psbl_cash': '350000',
                    'tot_evlu_amt': '1050000',
                    'scts_evlu_amt': '700000',
                    'pchs_amt_smtl_amt': '700000',
                    'evlu_pfls_smtl_amt': '35000',
                },
                'output1': [{
                    'pdno': '005930',
                    'prdt_name': 'Samsung',
                    'hldg_qty': '10',
                    'ord_psbl_qty': '10',
                    'pchs_avg_pric': '70000',
                    'pchs_amt': '700000',
                    'prpr': '72000',
                    'evlu_amt': '720000',
                    'evlu_pfls_amt': '20000',
                }],
                'token_marker': token,
            })
        if url.endswith(KIS_OPEN_ORDERS_PATH):
            return FakeResponse({
                'rt_cd': '0',
                'output': [{
                    'odno': 'kis-order-1',
                    'pdno': '005930',
                    'prdt_name': 'Samsung',
                    'sll_buy_dvsn_cd': '02',
                    'ord_qty': '4',
                    'psbl_qty': '3',
                    'ord_unpr': '71000',
                    'ord_tmd': '120000',
                }],
            })
        raise AssertionError(f'unexpected fake GET: {url}')


def _settings(**overrides) -> Settings:
    values = {
        'alpaca_api_key': 'admin-alpaca-key',
        'alpaca_secret_key': 'admin-alpaca-secret',
        'alpaca_base_url': ALPACA_BASE_URLS['paper'],
        'broker_credential_master_key': Fernet.generate_key().decode('ascii'),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _user(db_session, username: str, role: str = 'user') -> User:
    user = User(
        username=username,
        role=role,
        enabled=True,
        setup_completed=True,
        password_hash='test-only',
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _credential(db_session, user, crypto, provider, payload):
    row = UserBrokerCredential(
        user_id=user.id,
        provider=provider,
        environment=payload['environment'],
        encrypted_payload=crypto.encrypt(payload),
        encryption_version=1,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _service(settings, http, token_manager=None):
    return UserBrokerAccountService(
        crypto=BrokerCredentialCryptoService(settings),
        http_client=http,
        token_manager=token_manager or UserKisTokenManager(),
    )


def _client(db_session, user):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    session = create_session(db_session, user)
    client.cookies.set('auto_invest_session', session)
    return client


def test_kis_snapshot_is_normalized_and_user_token_isolated(db_session):
    settings = _settings()
    crypto = BrokerCredentialCryptoService(settings)
    user_a = _user(db_session, 'account-a')
    user_b = _user(db_session, 'account-b')
    _credential(db_session, user_a, crypto, 'kis', {
        'environment': 'paper',
        'app_key': 'user-a-key',
        'app_secret': 'user-a-secret',
        'account_no': '11111111',
        'account_product_code': '01',
    })
    _credential(db_session, user_b, crypto, 'kis', {
        'environment': 'paper',
        'app_key': 'user-b-key',
        'app_secret': 'user-b-secret',
        'account_no': '22222222',
        'account_product_code': '01',
    })
    http = FakeBrokerHttp()
    service = _service(settings, http)

    snapshot_a = service.get_broker_snapshot(db_session, user_a, 'kis')
    snapshot_b = service.get_broker_snapshot(db_session, user_b, 'kis')
    again_a = service.get_broker_snapshot(db_session, user_a, 'kis')

    assert snapshot_a['provider'] == 'kis'
    assert snapshot_a['environment'] == 'paper'
    assert snapshot_a['account']['cash'] == 1000000.0
    assert snapshot_a['account']['buying_power'] == 350000.0
    assert snapshot_a['account']['portfolio_value'] == 1050000.0
    assert snapshot_a['account']['equity'] == 1050000.0
    assert snapshot_a['account']['unrealized_pl'] == 35000.0
    assert snapshot_a['account']['unrealized_pl_pct'] == pytest.approx(5.0)
    assert snapshot_a['positions'][0]['symbol'] == '005930'
    assert snapshot_a['positions'][0]['available_quantity'] == 10.0
    assert snapshot_a['positions'][0]['unrealized_pl_pct'] == pytest.approx(
        20000 / 700000 * 100
    )
    assert snapshot_a['open_orders'][0]['side'] == 'buy'
    assert snapshot_a['open_orders'][0]['filled_quantity'] == 1.0
    assert snapshot_a['open_orders'][0]['remaining_quantity'] == 3.0
    assert snapshot_b['account'] == snapshot_a['account']
    assert again_a['account'] == snapshot_a['account']
    assert http.token_counts == {'user-a-key': 1, 'user-b-key': 1}
    assert 'user-a-secret' not in json.dumps(snapshot_a)
    assert 'user-b-secret' not in json.dumps(snapshot_b)
    assert all('access_token' not in json.dumps(item) for item in http.gets)


def test_kis_zero_cost_basis_has_null_percentage(db_session):
    settings = _settings()
    crypto = BrokerCredentialCryptoService(settings)
    user = _user(db_session, 'zero-cost')
    _credential(db_session, user, crypto, 'kis', {
        'environment': 'live',
        'app_key': 'zero-key',
        'app_secret': 'zero-secret',
        'account_no': '33333333',
        'account_product_code': '01',
    })
    http = FakeBrokerHttp()
    original_get = http.get

    def zero_cost_get(url, **kwargs):
        response = original_get(url, **kwargs)
        if url.endswith(KIS_BALANCE_PATH):
            body = response.json()
            body['output2']['pchs_amt_smtl_amt'] = '0'
            body['output2']['evlu_pfls_smtl_amt'] = '100'
            body['output1'][0]['pchs_amt'] = '0'
            body['output1'][0]['pchs_avg_pric'] = '0'
            response = FakeResponse(body)
        return response

    http.get = zero_cost_get
    snapshot = _service(settings, http).get_broker_snapshot(db_session, user, 'kis')
    assert snapshot['account']['unrealized_pl_pct'] is None
    assert snapshot['positions'][0]['unrealized_pl_pct'] is None


def test_expired_kis_token_refreshes_once_and_second_failure_is_safe(db_session):
    settings = _settings()
    crypto = BrokerCredentialCryptoService(settings)
    user = _user(db_session, 'refresh-user')
    _credential(db_session, user, crypto, 'kis', {
        'environment': 'paper',
        'app_key': 'refresh-key',
        'app_secret': 'refresh-secret',
        'account_no': '44444444',
        'account_product_code': '01',
    })

    retry_http = FakeBrokerHttp(expire_first_for={'refresh-key'})
    snapshot = _service(settings, retry_http).get_broker_snapshot(
        db_session, user, 'kis'
    )
    assert snapshot['connected'] is True
    assert retry_http.token_counts['refresh-key'] == 2

    failing_http = FakeBrokerHttp(always_expired_for={'refresh-key'})
    failing_service = _service(settings, failing_http)
    with pytest.raises(UserBrokerAuthenticationError):
        failing_service.get_broker_snapshot(db_session, user, 'kis')
    assert failing_http.token_counts['refresh-key'] == 2


def test_credential_replacement_does_not_reuse_old_kis_token(db_session):
    settings = _settings()
    crypto = BrokerCredentialCryptoService(settings)
    user = _user(db_session, 'replacement-user')
    _credential(db_session, user, crypto, 'kis', {
        'environment': 'paper',
        'app_key': 'old-key',
        'app_secret': 'old-secret',
        'account_no': '55555555',
        'account_product_code': '01',
    })
    http = FakeBrokerHttp()
    manager = get_user_kis_token_manager()
    manager.invalidate(user_id=user.id)
    service = _service(settings, http, manager)
    service.get_broker_snapshot(db_session, user, 'kis')

    credentials_service = UserBrokerCredentialService(crypto=crypto)
    credentials_service.save(db_session, user, 'kis', {
        'environment': 'paper',
        'app_key': 'new-key',
        'app_secret': 'new-secret',
        'hts_id': 'replacement-hts',
        'account_no': '55555555',
        'account_product_code': '01',
    })
    service.get_broker_snapshot(db_session, user, 'kis')

    assert http.token_counts == {'old-key': 1, 'new-key': 1}


@pytest.mark.parametrize('environment', ['paper', 'live'])
def test_alpaca_snapshot_uses_user_environment_and_normalizes_data(
    db_session, environment
):
    settings = _settings()
    crypto = BrokerCredentialCryptoService(settings)
    user = _user(db_session, f'alpaca-{environment}')
    _credential(db_session, user, crypto, 'alpaca', {
        'environment': environment,
        'api_key': f'{environment}-user-key',
        'secret_key': f'{environment}-user-secret',
    })
    http = FakeBrokerHttp()
    snapshot = _service(settings, http).get_broker_snapshot(
        db_session, user, 'alpaca'
    )

    assert snapshot['environment'] == environment
    assert snapshot['account']['portfolio_value'] == 3200.0
    assert snapshot['account']['equity'] == 3200.0
    assert snapshot['account']['cash'] == 1000.0
    assert snapshot['positions'][0]['quantity'] == 2.0
    assert snapshot['positions'][0]['unrealized_pl_pct'] == pytest.approx(10.0)
    assert snapshot['open_orders'][0]['remaining_quantity'] == 1.0
    account_url = next(item['url'] for item in http.gets if '/v2/account' in item['url'])
    assert account_url.startswith(ALPACA_BASE_URLS[environment])
    assert f'{environment}-user-secret' not in json.dumps(snapshot)


def test_route_uses_authenticated_owner_and_rejects_override_or_admin(db_session):
    settings = _settings()
    crypto = BrokerCredentialCryptoService(settings)
    user_a = _user(db_session, 'route-a')
    user_b = _user(db_session, 'route-b')
    admin = _user(db_session, 'route-admin', role='admin')
    _credential(db_session, user_a, crypto, 'alpaca', {
        'environment': 'paper',
        'api_key': 'route-a-key',
        'secret_key': 'route-a-secret',
    })
    http = FakeBrokerHttp()
    account_service = _service(settings, http)
    app.dependency_overrides[get_user_broker_account_service] = (
        lambda: account_service
    )
    client_a = _client(db_session, user_a)
    client_b = _client(db_session, user_b)
    client_admin = _client(db_session, admin)

    try:
        response_a = client_a.get(
            '/users/me/brokers/alpaca/account?user_id=' + str(user_b.id)
        )
        response_b = client_b.get('/users/me/brokers/alpaca/account')
        response_admin = client_admin.get('/users/me/brokers/alpaca/account')

        assert response_a.status_code == 200
        assert response_a.json()['connected'] is True
        assert response_b.status_code == 404
        assert response_b.json()['detail'] == 'broker_credentials_not_configured'
        assert response_admin.status_code == 403
        assert response_admin.json()['detail'] == 'admin_uses_env_broker_credentials'
        assert 'route-a-secret' not in response_a.text
    finally:
        app.dependency_overrides.clear()


def test_safe_account_route_errors_do_not_expose_upstream_data(db_session):
    settings = _settings()
    crypto = BrokerCredentialCryptoService(settings)
    user = _user(db_session, 'error-user')
    _credential(db_session, user, crypto, 'alpaca', {
        'environment': 'live',
        'api_key': 'error-key',
        'secret_key': 'error-secret',
    })

    class AuthFailureHttp(FakeBrokerHttp):
        def get(self, url, **kwargs):
            return FakeResponse({'message': 'secret-upstream-value'}, status_code=401)

    app.dependency_overrides[get_user_broker_account_service] = lambda: _service(
        settings, AuthFailureHttp()
    )
    client = _client(db_session, user)
    try:
        response = client.get('/users/me/brokers/alpaca/account')
        assert response.status_code == 502
        assert response.json() == {'detail': 'broker_authentication_failed'}
        assert 'secret-upstream-value' not in response.text
        unsupported = client.get('/users/me/brokers/other/account')
        assert unsupported.status_code == 400
        assert unsupported.json() == {'detail': 'unsupported_broker_provider'}
    finally:
        app.dependency_overrides.clear()


def test_encryption_and_decrypt_failures_are_safe_account_errors(db_session):
    valid_settings = _settings()
    valid_crypto = BrokerCredentialCryptoService(valid_settings)
    user = _user(db_session, 'storage-error-user')
    row = _credential(db_session, user, valid_crypto, 'alpaca', {
        'environment': 'paper',
        'api_key': 'storage-key',
        'secret_key': 'storage-secret',
    })
    client = _client(db_session, user)

    app.dependency_overrides[get_user_broker_account_service] = lambda: _service(
        _settings(broker_credential_master_key=None), FakeBrokerHttp()
    )
    try:
        unavailable = client.get('/users/me/brokers/alpaca/account')
        assert unavailable.status_code == 503
        assert unavailable.json() == {
            'detail': 'broker_credential_encryption_unavailable'
        }

        row.encrypted_payload = 'not-a-fernet-payload'
        db_session.commit()
        app.dependency_overrides[get_user_broker_account_service] = (
            lambda: _service(valid_settings, FakeBrokerHttp())
        )
        invalid = client.get('/users/me/brokers/alpaca/account')
        assert invalid.status_code == 503
        assert invalid.json() == {'detail': 'broker_credentials_unavailable'}
        assert 'storage-secret' not in invalid.text
    finally:
        app.dependency_overrides.clear()
