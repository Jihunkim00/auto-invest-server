from __future__ import annotations

import json
import pytest
from cryptography.fernet import Fernet

from app.db.models import OrderLog, User, UserBrokerCredential
from app.services.broker_credential_crypto_service import BrokerCredentialCryptoService
from app.services.kis_automation_execution_core import KisAutomationExecutionCore
from app.tests.test_kis_automation_execution_core import FakeKisClient, NOW


@pytest.fixture
def accounts(db_session, fake_kis_admin_credentials, monkeypatch):
    monkeypatch.setattr(fake_kis_admin_credentials, 'broker_credential_master_key', Fernet.generate_key().decode())
    admin = User(username='admin', role='admin', enabled=True)
    first = User(username='test01', role='user', enabled=True)
    second = User(username='test02', role='user', enabled=True)
    db_session.add_all([admin, first, second])
    db_session.commit()
    credentials = {}
    for user, number in ((first, '33334444'), (second, '55556666')):
        value = dict(environment='live', account_no=number, account_product_code='01',
                     app_key=f'fake-key-{user.id}', app_secret=f'fake-secret-{user.id}')
        credentials[user.id] = value
        db_session.add(UserBrokerCredential(user_id=user.id, provider='kis', environment='live',
            encrypted_payload=BrokerCredentialCryptoService().encrypt(value), encryption_version=1))
    db_session.commit()
    return admin, first, second, credentials


def _order(db, *, owner, side, status='REQUESTED', payload=None):
    row = OrderLog(broker='kis', market='KR', symbol='028670', side=side, order_type='market',
        qty=1, requested_qty=1, remaining_qty=1, notional=10_000, owner_user_id=owner,
        internal_status=status, request_payload=json.dumps(payload or {}),
        sync_error='kis_order_not_found_in_inquiry' if status == 'UNKNOWN_STALE' else None)
    db.add(row)
    db.commit()
    return row


def _client(owner, credentials, *, side):
    client = FakeKisClient(positions=[{'symbol': '028670', 'qty': 3}] if side == 'sell' else [])
    if owner is not None:
        client.user_id = owner
        client.credentials = dict(credentials[owner])
    return client


def _guard(core, db, order):
    if order.side == 'sell':
        return core._sell_jit_guard(db, order_id=order.id, symbol=order.symbol, qty=1)
    return core._buy_jit_guard(db, order_id=order.id, symbol=order.symbol, qty=1,
        expected_price=10_000, max_positions=1, max_order_notional_krw=100_000,
        min_price_krw=None, max_price_krw=None, now=NOW)


@pytest.mark.parametrize('side', ['buy', 'sell'])
@pytest.mark.parametrize('status', ['UNKNOWN_STALE', 'SYNC_FAILED', 'SUBMITTED', 'PARTIALLY_FILLED'])
@pytest.mark.parametrize('requested,previous,blocked', [
    ('admin', 'first', False), ('first', 'admin', False),
    ('first', 'first', True), ('admin', 'admin', True), ('first', 'second', False),
])
def test_unresolved_orders_are_isolated_without_mutating_history(db_session, accounts, side, status, requested, previous, blocked):
    admin, first, second, credentials = accounts
    owners = {'admin': None, 'first': first.id, 'second': second.id}
    old = _order(db_session, owner=owners[previous], side=side, status=status)
    before = (old.internal_status, old.sync_error, old.request_payload, old.response_payload)
    order = _order(db_session, owner=owners[requested], side=side)
    core = KisAutomationExecutionCore(_client(order.owner_user_id, credentials, side=side))
    result = _guard(core, db_session, order)
    assert result['allowed'] is not blocked
    if blocked:
        reason = 'duplicate_open_order' if side == 'buy' else 'duplicate_open_sell_order'
        assert result['reason'] == result['block_reason'] == reason
        assert result['duplicate_check_source'] == 'local_db'
        assert result['matched_order_id'] == old.id
        assert result['matched_order_owner_user_id'] == old.owner_user_id
        assert result['requested_order_owner_user_id'] == order.owner_user_id
    db_session.refresh(old)
    assert (old.internal_status, old.sync_error, old.request_payload, old.response_payload) == before


@pytest.mark.parametrize('side', ['buy', 'sell'])
@pytest.mark.parametrize('requested,previous', [('admin', 'first'), ('first', 'admin'), ('first', 'second')])
def test_different_owners_sharing_a_real_account_still_block(db_session, accounts, side, requested, previous):
    admin, first, second, credentials = accounts
    shared_number = '11112222' if 'admin' in (requested, previous) else '33334444'
    for user in (first, second):
        credentials[user.id]['account_no'] = shared_number
        row = db_session.query(UserBrokerCredential).filter_by(user_id=user.id).one()
        row.encrypted_payload = BrokerCredentialCryptoService().encrypt(credentials[user.id])
    db_session.commit()
    owners = {'admin': None, 'first': first.id, 'second': second.id}
    old = _order(db_session, owner=owners[previous], side=side, status='UNKNOWN_STALE')
    order = _order(db_session, owner=owners[requested], side=side)
    result = _guard(KisAutomationExecutionCore(_client(order.owner_user_id, credentials, side=side)), db_session, order)
    assert result['allowed'] is False
    assert result['matched_order_id'] == old.id
    assert result['duplicate_check_source'] == 'local_db'


@pytest.mark.parametrize('side', ['buy', 'sell'])
@pytest.mark.parametrize('owner', ['admin', 'first'])
def test_broker_open_orders_block_and_read_the_verified_client(db_session, accounts, side, owner):
    _, first, _, credentials = accounts
    order = _order(db_session, owner=None if owner == 'admin' else first.id, side=side)
    client = _client(order.owner_user_id, credentials, side=side)
    calls = []
    def open_orders():
        calls.append(getattr(client, 'user_id', None))
        return [{'symbol': order.symbol, 'side': side}]
    client.list_open_orders = open_orders
    result = _guard(KisAutomationExecutionCore(client), db_session, order)
    assert result['allowed'] is False
    assert result['duplicate_check_source'] == 'broker'
    assert result['requested_order_owner_user_id'] == order.owner_user_id
    assert calls == [order.owner_user_id]


@pytest.mark.parametrize('side', ['buy', 'sell'])
@pytest.mark.parametrize('mutation', ['missing_client', 'missing_identity', 'wrong_account', 'wrong_key', 'wrong_user', 'invalid_orders', 'read_failure'])
def test_untrusted_broker_scope_fails_closed_without_submit(db_session, accounts, side, mutation):
    _, first, _, credentials = accounts
    order = _order(db_session, owner=first.id, side=side)
    client = _client(first.id, credentials, side=side)
    reads = []
    client.list_open_orders = lambda: reads.append(True) or []
    if mutation == 'missing_client':
        client = None
    elif mutation == 'missing_identity':
        del client.credentials['account_no']
    elif mutation == 'wrong_account':
        client.credentials['account_no'] = '99998888'
    elif mutation == 'wrong_key':
        client.credentials['app_key'] = 'different-secret-key'
    elif mutation == 'wrong_user':
        client.user_id += 1
    elif mutation == 'invalid_orders':
        client.list_open_orders = lambda: None
    else:
        def unavailable():
            raise RuntimeError('account unavailable')
        client.list_open_orders = unavailable
    core = KisAutomationExecutionCore(client)
    from app.services.runtime_setting_service import RuntimeSettingService
    RuntimeSettingService().update_settings(db_session, {'automation_mode': 'live'})
    calls = []
    submit = core.submit_market_buy if side == 'buy' else core.submit_market_sell
    result = submit(db_session, order=order, symbol=order.symbol, qty=1, now=NOW,
                    submitter=lambda: calls.append(True) or {})
    assert result['status'] == 'blocked'
    assert result['broker_submit_called'] is False
    assert calls == []
    if mutation not in {'invalid_orders', 'read_failure'}:
        assert reads == []


@pytest.mark.parametrize('side', ['buy', 'sell'])
@pytest.mark.parametrize('evidence', ['client', 'payload', 'profile', 'user_source'])
def test_missing_regular_owner_cannot_use_legacy_admin_scope(db_session, accounts, side, evidence):
    _, first, _, credentials = accounts
    order = _order(db_session, owner=None, side=side)
    client = _client(None, credentials, side=side)
    if evidence == 'client':
        client = _client(first.id, credentials, side=side)
    elif evidence == 'payload':
        order.request_payload = json.dumps({'owner_user_id': first.id})
    elif evidence == 'user_source':
        order.request_payload = json.dumps({'mode': 'kis_live', 'trigger_source': 'user_run_once'})
    else:
        from app.schemas.automation_profile import AutomationProfileWriteRequest
        from app.services.automation_profile_service import AutomationProfileService
        profile = AutomationProfileService().create(db_session,
            AutomationProfileWriteRequest(profile_key='test01-profile', name='Test01'),
            owner_user_id=first.id)
        order.profile_id = profile['id']
    db_session.commit()
    assert _guard(KisAutomationExecutionCore(client), db_session, order)['reason'] == 'account_scope_mismatch'


@pytest.mark.parametrize('side', ['buy', 'sell'])
def test_unidentifiable_other_owner_does_not_silently_bypass_protection(db_session, accounts, side):
    _, first, _, credentials = accounts
    old = _order(db_session, owner=first.id, side=side, status='UNKNOWN_STALE')
    db_session.query(UserBrokerCredential).filter_by(user_id=first.id).one().encrypted_payload = 'corrupt'
    db_session.commit()
    order = _order(db_session, owner=None, side=side)
    result = _guard(KisAutomationExecutionCore(_client(None, credentials, side=side)), db_session, order)
    assert result['reason'] == 'account_scope_unavailable'
    assert old.internal_status == 'UNKNOWN_STALE'


def test_block_diagnostics_are_persisted_without_credentials(db_session, accounts):
    _, first, _, credentials = accounts
    old = _order(db_session, owner=first.id, side='buy', status='UNKNOWN_STALE')
    order = _order(db_session, owner=first.id, side='buy', payload={'reservation_id': 42, 'scheduler_slot': '13:40'})
    from app.services.runtime_setting_service import RuntimeSettingService
    RuntimeSettingService().update_settings(db_session, {'automation_mode': 'live'})
    result = KisAutomationExecutionCore(_client(first.id, credentials, side='buy')).submit_market_buy(
        db_session, order=order, symbol=order.symbol, qty=1, now=NOW,
        submitter=lambda: pytest.fail('duplicate must never submit'))
    payload = json.loads(order.response_payload)
    assert payload['order_id'] == order.id
    assert payload['guard'] == result['guard']
    assert payload['guard']['matched_order_id'] == old.id
    assert payload['source_metadata']['reservation_id'] == 42
    for secret in credentials[first.id].values():
        if secret not in {'01', 'live'}:
            assert secret not in order.response_payload


def test_scheduler_block_links_run_order_and_reservation(db_session, fake_kis_admin_credentials):
    from app.db.models import AutomationProfileBuyReservation, TradeRunLog
    from app.tests.test_pr110_final_buy_readiness import _build_service, _candidate, NOW as SLOT_NOW
    service, _, _, _, broker, validation, _, _ = _build_service(db_session)
    validate = validation.validate
    previous = []
    def introduce_unresolved_order(request, **kwargs):
        old = _order(db_session, owner=None, side='buy', status='UNKNOWN_STALE')
        old.symbol = '005930'
        db_session.commit()
        previous.append(old)
        return validate(request, **kwargs)
    validation.validate = introduce_unresolved_order
    result = service.run_once(db_session, [_candidate()], scheduler_slot='09:10', now=SLOT_NOW)
    assert result['reason'] == 'duplicate_open_order'
    order = db_session.get(OrderLog, result['order_id'])
    reservation = db_session.get(AutomationProfileBuyReservation, result['reservation_id'])
    run = db_session.query(TradeRunLog).filter_by(order_id=order.id).one()
    assert reservation.order_id == order.id
    assert reservation.status == 'blocked'
    assert reservation.block_reason == run.reason == 'duplicate_open_order'
    assert json.loads(run.response_payload)['reservation_id'] == reservation.id
    assert json.loads(run.response_payload)['guard']['matched_order_id'] == previous[0].id
    assert json.loads(order.response_payload)['source_metadata']['reservation_id'] == reservation.id
    assert broker.buy_calls == []
    assert previous[0].internal_status == 'UNKNOWN_STALE'


@pytest.mark.parametrize('output', [None, {}, [None]])
def test_malformed_kis_open_order_response_fails_closed(db_session, accounts, output):
    from app.brokers.kis_client import KisClient
    _, _, _, credentials = accounts
    order = _order(db_session, owner=None, side='buy')
    client = _client(None, credentials, side='buy')
    client.request_get = lambda *args, **kwargs: {'rt_cd': '0', 'output': output}
    client.list_open_orders = lambda: KisClient.list_open_orders(client)
    result = _guard(KisAutomationExecutionCore(client), db_session, order)
    assert result['allowed'] is False
    assert result['reason'] == 'account_snapshot_unavailable'


def test_admin_broker_inquiry_uses_the_verified_account(db_session, accounts):
    from app.brokers.kis_client import KisClient
    _, _, _, credentials = accounts
    order = _order(db_session, owner=None, side='buy')
    client = _client(None, credentials, side='buy')
    calls = []
    def inquire(path, **kwargs):
        calls.append(kwargs['params'])
        return {'rt_cd': '0', 'output': [{'pdno': order.symbol, 'sll_buy_dvsn_cd': '02',
                                         'ord_qty': '1', 'psbl_qty': '1'}]}
    client.request_get = inquire
    client.list_open_orders = lambda: KisClient.list_open_orders(client)
    result = _guard(KisAutomationExecutionCore(client), db_session, order)
    assert result['duplicate_check_source'] == 'broker'
    assert calls[0]['CANO'] == client.settings.kis_account_no
    assert calls[0]['ACNT_PRDT_CD'] == client.settings.kis_account_product_code
