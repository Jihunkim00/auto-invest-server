"""Closed-session scheduler and test01 reconciliation regressions.

All DB writes use independent SQLite copies; every broker response is fake.
Set AUTO_INVEST_DIAGNOSTIC_CLONE to an existing backup to replay its orders.
"""
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import AutomationSchedulerSlot, OrderLog, PositionLifecycle, TradeRunLog, User, UserBrokerCredential
from app.services.scheduler_service import AutomationSchedulerService
from app.services.broker_credential_crypto_service import BrokerCredentialCryptoService
from app.services.kis_order_sync_service import KisOrderSyncError, KisOrderSyncService, serialize_kis_order
from app.services.scheduler_slot_dispatcher import SchedulerSlotDispatcher
from app.services.user_broker_account_service import (
    KIS_BALANCE_PATH, KIS_OPEN_ORDERS_PATH, KIS_DAILY_EXECUTIONS_PATH,
    UserBrokerAccountService, UserKisReadOnlyClient, UserKisTokenManager,
)
from app.services.user_kis_order_sync_service import UserKisOrderSyncService
from app.tests.integration.test_kis_automation_scheduler_replay import build_harness, candidate
from app.tests.test_kis_duplicate_account_scope import accounts
from app.tests.test_user_broker_accounts import FakeBrokerHttp, FakeResponse, _client

KST = ZoneInfo('Asia/Seoul')
SLOTS = ('10:45', '12:20', '13:30')
NOW = datetime(2026, 11, 4, 15, 0, tzinfo=KST)


@pytest.fixture(autouse=True)
def forbid_transport(monkeypatch, fake_kis_admin_credentials):
    def forbidden(*args, **kwargs):
        pytest.fail('Real transport/submission is forbidden in replay')
    monkeypatch.setattr('requests.sessions.Session.request', forbidden)
    monkeypatch.setattr('httpx.HTTPTransport.handle_request', forbidden)
    monkeypatch.setattr('httpx.AsyncHTTPTransport.handle_async_request', forbidden)


@pytest.fixture
def sessions(tmp_path):
    engine = create_engine(f'sqlite:///{(tmp_path / "replay.db").as_posix()}')
    Base.metadata.create_all(engine)
    # Separate sessions and normal commit expiration reproduce production;
    # reusing a fixture session or expire_on_commit=False hid this failure.
    maker = sessionmaker(bind=engine, expire_on_commit=True, close_resets_only=False)
    try:
        yield maker
    finally:
        engine.dispose()


class ImmediateSupervisor:
    def launch(self, lane, callback, **kwargs):
        callback()
        return True


def canonical(maker, monkeypatch, *, now, mode='live', score=70):
    with maker() as db:
        harness = build_harness(db, monkeypatch, mode=mode, now=now,
            analysis_times=(*SLOTS, '11:20'), candidates=[candidate(score=score)])
    scheduler = AutomationSchedulerService(retry_now_provider=harness.clock.now)
    scheduler.runtime_settings = harness.runtime
    scheduler.automation_profiles = harness.profiles
    scheduler.profile_aware_dry_run_auto_buy_service = harness.strategy_scheduler.dry_run_service
    scheduler.automation_profile_buy_scheduler_service = harness.profile_buy
    monkeypatch.setattr('app.services.automation_scheduler_service.SessionLocal', maker)
    dispatcher = SchedulerSlotDispatcher(maker, ImmediateSupervisor(), harness.clock.now)
    return scheduler, harness, dispatcher


@pytest.mark.parametrize('day', ['2026-10-31', '2026-11-02'])
@pytest.mark.parametrize('slot', (*SLOTS, '11:20'))
@pytest.mark.parametrize('reason', ['active_profile_or_slot_unavailable', 'automation_disabled', 'automation_mode_off'])
def test_skip_audit_crosses_closed_session_as_plain_values(sessions, monkeypatch, day, slot, reason):
    now = datetime.fromisoformat(f'{day}T{slot}:00').replace(tzinfo=KST)
    scheduler, harness, dispatcher = canonical(sessions, monkeypatch, now=now)
    with sessions() as db:
        if reason == 'active_profile_or_slot_unavailable':
            monkeypatch.setattr(scheduler.automation_profiles, 'selected_profile_schedule',
                                lambda *args, **kwargs: None)
        else:
            harness.runtime.update_settings(db, {'automation_profile_scheduler_enabled': False}
                if reason == 'automation_disabled' else {'automation_mode': 'off'})
        db.add(OrderLog(id=18, broker='kis', market='KR', symbol='036460', side='buy',
            order_type='market', qty=7, internal_status='REQUESTED', request_payload='{"unresolved":true}'))
        db.commit()
    dispatcher.reconcile(account='admin', provider='kis', profile_id=None, slots=[now],
        now=now, callback=scheduler._run_scheduled_admin_slot)
    with sessions() as db:
        slot_row = db.query(AutomationSchedulerSlot).one()
        result = json.loads(slot_row.result_json)
        assert slot_row.status == 'skipped'
        assert slot_row.reason == result['reason'] == reason
        audit = db.query(TradeRunLog).one()
        assert audit.id == result['scheduler_skip_run_id']
        assert json.loads(audit.response_payload)['run_diagnostics']['gates']
        assert db.get(OrderLog, 18).internal_status == 'REQUESTED'
        assert db.get(OrderLog, 18).request_payload == '{"unresolved":true}'
    assert harness.broker.buy_calls == harness.broker.sell_calls == []


@pytest.mark.parametrize('slot', SLOTS)
@pytest.mark.parametrize('branch', ['normal', 'hold', 'buy', 'failure'])
def test_all_admin_slots_have_durable_outcomes(sessions, monkeypatch, slot, branch):
    now = datetime.fromisoformat(f'2026-11-02T{slot}:00').replace(tzinfo=KST)
    scheduler, harness, dispatcher = canonical(sessions, monkeypatch, now=now,
        mode='paper' if branch == 'normal' else 'live', score=64 if branch == 'hold' else 70)
    if branch == 'failure':
        def fail(*args, **kwargs):
            raise RuntimeError('fake_analysis_failure')
        monkeypatch.setattr(scheduler, '_run_profile_analysis', fail)
        with pytest.raises(RuntimeError, match='fake_analysis_failure'):
            dispatcher.reconcile(account='admin', provider='kis', profile_id=None, slots=[now],
                now=now, callback=scheduler._run_scheduled_admin_slot)
    else:
        dispatcher.reconcile(account='admin', provider='kis', profile_id=None, slots=[now],
            now=now, callback=scheduler._run_scheduled_admin_slot)
    with sessions() as db:
        row = db.query(AutomationSchedulerSlot).one()
        if branch == 'failure':
            assert row.status == 'failed' and row.reason == 'scheduler_slot_failed:RuntimeError'
        else:
            result = json.loads(row.result_json)
            assert result['run_diagnostics']['gates']
            assert result['result'] == ('LIVE_READY' if branch == 'buy' else
                                        'blocked' if branch == 'hold' else 'PAPER_SIMULATED')
        assert len(harness.broker.buy_calls) == (1 if branch == 'buy' else 0)
        assert harness.client.external_kis_submit_count == 0
    # Re-delivery never creates a second order or replays a failed slot.
    dispatcher.reconcile(account='admin', provider='kis', profile_id=None, slots=[now],
        now=now, callback=scheduler._run_scheduled_admin_slot)
    assert len(harness.broker.buy_calls) == (1 if branch == 'buy' else 0)


def seed_order(db, owner, *, order_id=19, status='PENDING', symbol='032640', qty=2):
    order = OrderLog(id=order_id, owner_user_id=owner, broker='kis', market='KR',
        symbol=symbol, side='buy', order_type='market', qty=qty, requested_qty=qty,
        filled_qty=0, remaining_qty=qty, internal_status=status, kis_odno=f'{order_id:010d}',
        broker_order_id=f'{order_id:010d}', submitted_at=datetime(2026, 11, 4, 3, 48),
        request_payload='{"trigger_source":"user_scheduler","mode":"kis_live"}')
    db.add(order)
    db.commit()
    return order


def execution(order):
    return {'odno': order.kis_odno, 'pdno': order.symbol, 'sll_buy_dvsn_cd': '02',
        'ord_dt': order.submitted_at.replace(tzinfo=UTC).astimezone(KST).strftime('%Y%m%d'),
        'ord_qty': str(int(order.qty)), 'tot_ccld_qty': str(int(order.qty)),
        'rmn_qty': '0', 'avg_prvs': '14500'}


class FakeHistoryHttp(FakeBrokerHttp):
    def __init__(self, rows, *, continuation='', malformed=False, failure=False):
        super().__init__()
        self.rows, self.continuation = rows, continuation
        self.malformed, self.failure = malformed, failure
        self.positions = [{'pdno': '032640', 'hldg_qty': '2', 'pchs_avg_pric': '15680',
                           'pchs_amt': '31360', 'prpr': '15680', 'evlu_amt': '31360'}]

    @property
    def history_gets(self):
        return [call for call in self.gets if call['url'].endswith(KIS_DAILY_EXECUTIONS_PATH)]

    def get(self, url, **kwargs):
        self.gets.append({'url': url, **kwargs})
        if url.endswith(KIS_BALANCE_PATH):
            return FakeResponse({'rt_cd': '0', 'output1': self.positions,
                'output2': {'dnca_tot_amt': '100000', 'tot_evlu_amt': '131360'}})
        if url.endswith(KIS_OPEN_ORDERS_PATH):
            return FakeResponse({'rt_cd': '0', 'output': []})
        if not url.endswith(KIS_DAILY_EXECUTIONS_PATH):
            pytest.fail('Only owner history/balance/open-order inquiries are allowed')
        if self.failure:
            raise ConnectionError('fake history unavailable')
        payload = {'rt_cd': '0', 'output1': {} if self.malformed else self.rows}
        return SimpleNamespace(status_code=200, json=lambda: payload, headers={'tr_cont': self.continuation})


def owner_service(db, user, rows, **kwargs):
    http = FakeHistoryHttp(rows, **kwargs)
    account = UserBrokerAccountService(http_client=http, token_manager=UserKisTokenManager())
    client = account.get_kis_read_only_client(db, user)
    assert type(client) is UserKisReadOnlyClient
    assert not hasattr(client, 'submit_market_buy_qty')
    return UserKisOrderSyncService(client, now_provider=lambda: NOW), http, account


def test_owner_fill_links_position_once_and_leaves_admin_and_old_order_untouched(db_session, accounts):
    _, first, second, _ = accounts
    order = seed_order(db_session, first.id)
    old = seed_order(db_session, first.id, order_id=13, status='UNKNOWN_STALE', symbol='028670', qty=5)
    admin = seed_order(db_session, None, order_id=18, status='REQUESTED')
    admin_before = (admin.internal_status, admin.last_synced_at, admin.filled_qty)
    service, http, _ = owner_service(db_session, first, [execution(order)])
    for _ in range(2):
        synced = service.sync_order(db_session, 19)
        assert (synced.internal_status, synced.filled_qty, synced.remaining_qty) == ('FILLED', 2, 0)
    life = db_session.query(PositionLifecycle).one()
    assert (life.owner_user_id, life.entry_order_id, life.symbol, life.quantity) == (first.id, 19, '032640', 2)
    assert synced.last_synced_at and synced.filled_at is None
    assert len(http.history_gets) == 1
    assert http.history_gets[0]['params']['ODNO'] == order.kis_odno
    assert all(call['params']['CANO'] == service.client.credentials['account_no'] for call in http.gets)
    assert http.history_gets[0]['params']['EXCG_ID_DVSN_CD'] == 'ALL'
    assert all(call['url'].endswith('/oauth2/tokenP') for call in http.posts)
    assert (admin.internal_status, admin.last_synced_at, admin.filled_qty) == admin_before
    assert old.internal_status == 'UNKNOWN_STALE' and old.last_synced_at is None
    for foreign in (admin, seed_order(db_session, second.id, order_id=20)):
        with pytest.raises(KisOrderSyncError, match='account_scope_mismatch'):
            service.sync_order(db_session, foreign.id)
    assert len(http.history_gets) == 1


@pytest.mark.parametrize('fault', ['absent', 'date', 'symbol', 'side', 'qty', 'overfill',
    'remaining', 'price', 'nan', 'duplicate', 'continuation', 'malformed', 'failure', 'wrong_credentials'])
def test_holdings_never_replace_verified_execution_evidence(db_session, accounts, fault):
    _, first, _, _ = accounts
    order = seed_order(db_session, first.id)
    row = execution(order)
    changes = {'date': ('ord_dt', '20261103'), 'symbol': ('pdno', '005930'),
        'side': ('sll_buy_dvsn_cd', '01'), 'qty': ('ord_qty', '3'),
        'overfill': ('tot_ccld_qty', '3'), 'remaining': ('rmn_qty', '1'),
        'price': ('avg_prvs', '0'), 'nan': ('tot_ccld_qty', 'nan')}
    if fault in changes:
        key, value = changes[fault]
        row[key] = value
    rows = [] if fault == 'absent' else [row, row] if fault == 'duplicate' else [row]
    service, http, _ = owner_service(db_session, first, rows,
        continuation='M' if fault == 'continuation' else '', malformed=fault == 'malformed', failure=fault == 'failure')
    # A matching holding is deliberately present but never consulted as proof.
    service.client.positions = [{'symbol': '032640', 'qty': 2}]
    if fault == 'wrong_credentials':
        service.client.credentials['account_no'] = '99998888'
        with pytest.raises(KisOrderSyncError, match='account_scope_mismatch'):
            service.sync_order(db_session, 19)
        assert http.gets == [] and order.last_synced_at is None
    else:
        result = service.sync_order(db_session, 19)
        assert result.internal_status == ('UNKNOWN_STALE' if fault == 'absent' else 'PENDING')
        assert result.sync_error and result.last_synced_at
    assert order.filled_qty == 0 and order.remaining_qty == 2
    assert db_session.query(PositionLifecycle).count() == 0


def test_authenticated_owner_route_does_not_use_administrator_client(db_session, accounts):
    from app.main import app
    from app.routes.user_brokers import get_user_broker_account_service

    admin, first, second, _ = accounts
    order = seed_order(db_session, first.id)
    other = seed_order(db_session, second.id, order_id=20)
    _, http, account = owner_service(db_session, first, [execution(order)])
    app.dependency_overrides[get_user_broker_account_service] = lambda: account
    try:
        with _client(db_session, first) as client:
            assert client.post(f'/users/me/trading/orders/{other.id}/sync').status_code == 404
            response = client.post('/users/me/trading/orders/19/sync?owner_user_id=1')
            assert response.status_code == 200
            assert response.json()['internal_status'] == 'FILLED'
            assert response.json()['owner_user_id'] == first.id
        with _client(db_session, admin) as client:
            assert client.post('/users/me/trading/orders/19/sync').status_code == 403
        assert len(http.history_gets) == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize('position_case', ['absent', 'quantity_mismatch', 'unreliable', 'already_managed'])
def test_verified_fill_does_not_invent_or_duplicate_current_holdings(db_session, accounts, monkeypatch, position_case):
    _, first, _, _ = accounts
    order = seed_order(db_session, first.id)
    service, http, _ = owner_service(db_session, first, [execution(order)])
    if position_case == 'absent':
        http.positions = []
    elif position_case == 'quantity_mismatch':
        http.positions[0]['hldg_qty'] = '3'
    elif position_case == 'unreliable':
        monkeypatch.setattr(service.client, 'get_snapshot', lambda: {'positions_reliable': False})
    else:
        db_session.add(PositionLifecycle(owner_user_id=first.id, symbol='032640', entry_order_id=-1,
            quantity=2, entry_price=14500, cost_basis=29000, status='open', opened_at=NOW))
        db_session.commit()
    result = service.sync_order(db_session, order.id)
    assert result.internal_status == 'FILLED' and result.filled_qty == 2
    position = json.loads(result.last_sync_payload)['position_reconciliation']
    assert position['status'] == ('not_held' if position_case == 'absent' else 'review_required')
    assert db_session.query(PositionLifecycle).filter_by(entry_order_id=19).count() == 0


def test_operational_backup_reconciles_19_and_diagnoses_13_in_separate_copy(tmp_path, monkeypatch):
    path = os.environ.get('AUTO_INVEST_DIAGNOSTIC_CLONE')
    if not path:
        pytest.skip('optional read-only operational backup replay')
    source = Path(path).resolve()
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    copy = tmp_path / 'operational_copy.db'
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
        src.execute('PRAGMA query_only=ON')
        with sqlite3.connect(copy) as dst:
            src.backup(dst)
    engine = create_engine(f'sqlite:///{copy.as_posix()}')
    try:
        with sessionmaker(bind=engine)() as db:
            first = db.query(User).filter_by(username='test01').one()
            # Replace credentials only in the disposable copy. Never decrypt
            # an operational credential or query a real broker in this test.
            from cryptography.fernet import Fernet
            from app.config import get_settings
            monkeypatch.setattr(get_settings(), 'broker_credential_master_key', Fernet.generate_key().decode())
            value = dict(environment='live', account_no='33334444', account_product_code='01',
                         app_key='fake-key', app_secret='fake-secret')
            credential = db.query(UserBrokerCredential).filter_by(user_id=first.id, provider='kis').one()
            credential.encrypted_payload = BrokerCredentialCryptoService().encrypt(value)
            db.commit()
            order, old, admin = (db.get(OrderLog, key) for key in (19, 13, 18))
            assert order.symbol == '032640' and order.qty == 2 and order.internal_status == 'PENDING'
            admin_before = {c.name: getattr(admin, c.name) for c in admin.__table__.columns}
            row = execution(order)
            evidence_path = os.environ.get('AUTO_INVEST_ORDER19_EVIDENCE')
            if evidence_path:
                evidence = json.loads(Path(evidence_path).read_text(encoding='utf-8'))['history']
                assert evidence['status'] == 'VERIFIED_READ' and evidence['owner_user_id'] == first.id
                assert len(evidence['exact_matches']) == 1
                row = {**evidence['exact_matches'][0], 'odno': order.kis_odno}
                assert row.pop('order_no_masked') == '***' + order.kis_odno[-4:]
            service, http, _ = owner_service(db, first, [row])
            assert service.sync_order(db, 19).internal_status == 'FILLED'
            http.rows = []
            old_before = (old.request_payload, old.response_payload, old.filled_qty)
            assert service.sync_order(db, 13).internal_status == 'UNKNOWN_STALE'
            assert old.sync_error == 'kis_order_not_found_in_inquiry'
            assert (old.request_payload, old.response_payload, old.filled_qty) == old_before
            # The verified historical buy had already been sold as local #14.
            # Reconcile it separately without inventing a current position.
            old_row = execution(old)
            old_evidence_path = os.environ.get('AUTO_INVEST_ORDER13_EVIDENCE')
            if old_evidence_path:
                old_evidence = json.loads(Path(old_evidence_path).read_text(encoding='utf-8'))['history']
                assert old_evidence['status'] == 'VERIFIED_READ' and len(old_evidence['exact_matches']) == 1
                old_row = {**old_evidence['exact_matches'][0], 'odno': old.kis_odno}
                assert old_row.pop('order_no_masked') == '***' + old.kis_odno[-4:]
            http.rows = [old_row]
            assert service.sync_order(db, 13).internal_status == 'FILLED'
            assert old.filled_at is None
            assert json.loads(old.last_sync_payload)['position_reconciliation']['status'] == 'not_held'
            assert db.query(PositionLifecycle).filter_by(entry_order_id=13).count() == 0
            from app.services.kis_daily_entry_accounting import daily_entry_counts
            assert daily_entry_counts(db, now=NOW, owner_user_id=first.id) == (1, 0)
            assert {c.name: getattr(admin, c.name) for c in admin.__table__.columns} == admin_before
            assert db.query(PositionLifecycle).filter_by(owner_user_id=first.id, entry_order_id=19).count() == 1
    finally:
        engine.dispose()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
