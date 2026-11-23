from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import json
import sqlite3

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AutomationProfileBuyReservation, KisOrderReconciliationState, OrderLog,
    PositionLifecycle, StrategyProfile, TradeRunLog,
)
from app.services.kis_automatic_order_reconciliation_service import (
    KisAutomaticOrderReconciliationService, MODE,
)
from app.services.kis_daily_entry_accounting import daily_entry_counts
from app.services.kis_order_account_scope import position_management_block_reason, position_sell_block_reason
from app.services.kis_position_lifecycle_service import KisPositionLifecycleService
from app.tests.test_kis_duplicate_account_scope import accounts  # noqa: F401

NOW = datetime(2026, 11, 16, 0, 30, tzinfo=UTC)


class FakeKisClient:
    def __init__(self, owner, credentials, settings, pages):
        self.user_id, self.credentials, self.settings = owner, credentials, settings
        self.pages = pages
        self.calls = []

    def inquire_account_executions_page(self, **query):
        self.calls.append(query)
        result = self.pages[min(len(self.calls) - 1, len(self.pages) - 1)]
        if isinstance(result, Exception):
            raise result
        if callable(result):
            return result()
        return result

    def submit_domestic_cash_order(self, **kwargs):
        pytest.fail('Reconciliation must never submit')

    cancel_domestic_cash_order = submit_domestic_cash_order
    submit_market_buy_qty = submit_domestic_cash_order
    submit_market_sell_qty = submit_domestic_cash_order


def page(rows, flag='D', fk='', nk=''):
    return {'orders': rows, 'tr_cont': flag, 'fk': fk, 'nk': nk}


def evidence(**overrides):
    return {'odno': '00020', 'ord_dt': '20261109', 'pdno': '032640',
            'sll_buy_dvsn_cd': '01', 'ord_qty': '2', 'tot_ccld_qty': '0',
            'rmn_qty': '0', 'cncl_yn': 'Y', **overrides}


def order(db, owner, **overrides):
    values = dict(owner_user_id=owner, broker='kis', market='KR', symbol='032640',
                  side='sell', order_type='market', qty=2, requested_qty=2, remaining_qty=2,
                  filled_qty=0, internal_status='PENDING', broker_order_id='20', kis_odno='20',
                  created_at=datetime(2026, 11, 9, 1), submitted_at=datetime(2026, 11, 9, 1),
                  request_payload='{}', response_payload='{"original": true}')
    values.update(overrides)
    row = OrderLog(**values)
    db.add(row)
    db.commit()
    return row


def harness(db, accounts, settings, pages, owner=None):
    _admin, first, _second, credentials = accounts
    owner = first.id if owner == 'user' else owner
    client = FakeKisClient(owner, credentials.get(owner), settings, pages)
    clock = [NOW]
    service = KisAutomaticOrderReconciliationService(client_factory=lambda *_: client, now_provider=lambda: clock[0])
    return service, client, clock


@pytest.mark.parametrize('owner', [None, 'user'])
@pytest.mark.parametrize('initial', ['REQUESTED', 'PENDING_SUBMIT', 'PENDING', 'SUBMITTED', 'ACCEPTED',
                                     'PARTIALLY_FILLED', 'UNKNOWN_STALE', 'SYNC_FAILED'])
def test_admin_and_test01_all_unresolved_states(db_session, accounts, fake_kis_admin_credentials, owner, initial):
    svc, client, clock = harness(db_session, accounts, fake_kis_admin_credentials, [page([evidence()])], owner)
    row = order(db_session, client.user_id, internal_status=initial)
    result = svc.reconcile_account(db_session, owner_user_id=client.user_id)
    assert row.internal_status == 'CANCELED'
    assert result['finalized_count'] == 1 and result['unresolved_count'] == 0
    assert row.filled_at is None and row.submitted_at == datetime(2026, 11, 9, 1)
    assert json.loads(row.response_payload) == {'original': True}
    assert position_management_block_reason(db_session, owner_user_id=client.user_id) is None
    assert '+09:00' in result['last_synced_at']
    clock[0] += timedelta(minutes=10)
    svc.reconcile_account(db_session, owner_user_id=client.user_id)
    assert len(client.calls) == 1
    assert db_session.query(TradeRunLog).filter_by(mode=MODE).count() == 1


@pytest.mark.parametrize('row,expected,filled', [
    (evidence(tot_ccld_qty='2', avg_prvs='10000', cncl_yn='N'), 'FILLED', 2),
    (evidence(tot_ccld_qty='1', avg_prvs='10000'), 'CANCELED', 1),
    (evidence(cncl_yn='N', rjct_qty='2'), 'REJECTED', 0),
    (evidence(cncl_yn='N', ord_status='expired'), 'EXPIRED', 0),
    (evidence(cncl_yn='N', rmn_qty='2'), 'PENDING', 0),
    (evidence(cncl_yn='N', tot_ccld_qty='1', rmn_qty='1', avg_prvs='10000'), 'PARTIALLY_FILLED', 1),
])
def test_terminal_partial_and_active(db_session, accounts, fake_kis_admin_credentials, row, expected, filled):
    svc, client, _ = harness(db_session, accounts, fake_kis_admin_credentials, [page([row])], 'user')
    local = order(db_session, client.user_id)
    svc.reconcile_account(db_session, owner_user_id=client.user_id)
    assert local.internal_status == expected and local.filled_qty == filled
    if expected in {'PENDING', 'PARTIALLY_FILLED'}:
        assert position_management_block_reason(db_session, owner_user_id=client.user_id) is not None


@pytest.mark.parametrize('rows,reason', [
    ([], 'broker_order_record_missing'),
    ([evidence(odno='21')], 'broker_order_record_missing'),
    ([evidence(pdno='005930')], 'broker_order_identity_mismatch'),
    ([evidence(sll_buy_dvsn_cd='02')], 'broker_order_identity_mismatch'),
    ([evidence(ord_dt='20261108')], 'broker_order_not_uniquely_verified'),
    ([evidence(), evidence()], 'broker_order_not_uniquely_verified'),
    ([evidence(cano='55556666')], 'broker_order_identity_mismatch'),
    ([evidence(ord_qty='3')], 'broker_execution_quantity_invalid'),
    ([evidence(tot_ccld_qty='NaN')], 'broker_execution_quantity_invalid'),
    ([evidence(tot_ccld_qty='1')], 'broker_fill_price_missing'),
    ([evidence(cncl_yn='N')], 'broker_terminal_evidence_insufficient'),
    ([evidence(rmn_qty='1')], 'broker_terminal_evidence_insufficient'),
    ([evidence(cncl_yn='N', rmn_qty='1', rjct_qty='1')], 'broker_terminal_evidence_insufficient'),
])
def test_insufficient_evidence_holds(db_session, accounts, fake_kis_admin_credentials, rows, reason):
    svc, client, _ = harness(db_session, accounts, fake_kis_admin_credentials, [page(rows)], 'user')
    local = order(db_session, client.user_id)
    result = svc.reconcile_account(db_session, owner_user_id=client.user_id)
    assert local.internal_status == 'PENDING' and local.filled_qty == 0
    assert local.sync_error == reason
    assert result['manual_review_count'] == 1
    assert position_management_block_reason(db_session, owner_user_id=client.user_id) is not None


@pytest.mark.parametrize('changes,reason', [
    ({'kis_odno': None, 'broker_order_id': None}, 'kis_odno_missing'),
    ({'submitted_at': datetime(2026, 8, 16), 'created_at': datetime(2026, 8, 16)}, 'history_date_out_of_supported_range'),
    ({'request_payload': '{"environment":"paper"}'}, 'order_environment_mismatch'),
    ({'kis_odno': '19'}, 'local_order_number_conflict'),
])
def test_unsafe_orders_no_finalization(db_session, accounts, fake_kis_admin_credentials, changes, reason):
    svc, client, _ = harness(db_session, accounts, fake_kis_admin_credentials, [page([evidence()])], 'user')
    local = order(db_session, client.user_id, **changes)
    svc.reconcile_account(db_session, owner_user_id=client.user_id)
    assert local.internal_status == 'PENDING' and local.sync_error == reason


def test_pages_must_all_complete_and_bounded_retry(db_session, accounts, fake_kis_admin_credentials):
    svc, client, clock = harness(db_session, accounts, fake_kis_admin_credentials,
        [page([evidence()], 'M', 'first', 'next'), RuntimeError('token SECRET account 33334444')], 'user')
    local = order(db_session, client.user_id)
    result = svc.reconcile_account(db_session, owner_user_id=client.user_id)
    assert local.internal_status == 'PENDING' and len(client.calls) == 2
    assert 'SECRET' not in json.dumps(result) + local.last_sync_payload
    svc.reconcile_account(db_session, owner_user_id=client.user_id)
    assert len(client.calls) == 2
    clock[0] += timedelta(seconds=31)
    client.pages = [page([evidence()])]
    result = svc.reconcile_account(db_session, owner_user_id=client.user_id)
    assert local.internal_status == 'CANCELED'
    assert result['buy_hold_message'] is None and result['last_failure_reason'] is None


def test_multi_account_isolation_and_no_credentials_fallback(db_session, accounts, fake_kis_admin_credentials):
    admin, first, second, credentials = accounts
    locals = [order(db_session, owner, broker_order_id=None) for owner in (None, first.id, second.id)]
    clients = {owner: FakeKisClient(owner, credentials.get(owner), fake_kis_admin_credentials,
               [page([evidence()])]) for owner in (None, first.id, second.id)}
    clients[second.id].credentials = dict(credentials[first.id])
    svc = KisAutomaticOrderReconciliationService(client_factory=lambda db, owner: clients[owner], now_provider=lambda: NOW)
    svc.reconcile_all(db_session)
    assert [row.internal_status for row in locals] == ['CANCELED', 'CANCELED', 'PENDING']
    assert clients[second.id].calls == []
    audits = db_session.query(TradeRunLog).filter_by(mode=MODE).all()
    assert {(row.owner_user_id, row.order_id) for row in audits} == {(row.owner_user_id, row.id) for row in locals}


def test_legacy_admin_profile_owner_and_regular_profile_mismatch(db_session, accounts, fake_kis_admin_credentials):
    admin, first, _, _ = accounts
    from app.services.automation_profile_service import AutomationProfileService
    from app.tests.test_automation_profiles import _request
    created = AutomationProfileService().create(db_session, _request(profile_key='admin-owned-profile'), owner_user_id=admin.id)
    profile = db_session.get(StrategyProfile, created['id'])
    svc, client, _ = harness(db_session, accounts, fake_kis_admin_credentials, [page([evidence()])])
    row = order(db_session, None, profile_id=profile.id, profile_key=profile.profile_key)
    svc.reconcile_account(db_session)
    assert row.internal_status == 'CANCELED'


def test_concurrent_workers_use_database_lease_and_cas(db_session, accounts, fake_kis_admin_credentials, tmp_path):
    svc, client, _ = harness(db_session, accounts, fake_kis_admin_credentials, [], 'user')
    row = order(db_session, client.user_id)
    row_id = row.id
    path = tmp_path / 'concurrent_orders.db'
    with sqlite3.connect(path) as target:
        db_session.connection().connection.driver_connection.backup(target)
    engine = create_engine(f'sqlite:///{path.as_posix()}')
    sessions = sessionmaker(bind=engine)
    try:
        def during_read():
            with sessions() as other:
                assert svc.reconcile_account(other, owner_user_id=client.user_id)['status'] == 'deferred'
                changed = other.get(OrderLog, row_id)
                changed.internal_status = 'FILLED'
                changed.filled_qty = 2
                other.commit()
            return page([evidence()])

        client.pages = [during_read]
        with sessions() as db:
            svc.reconcile_account(db, owner_user_id=client.user_id)
            stored = db.get(OrderLog, row_id)
            assert stored.internal_status == 'FILLED' and stored.filled_qty == 2
            assert db.query(TradeRunLog).filter_by(mode=MODE).count() == 0
            assert db.get(KisOrderReconciliationState, f'user:{client.user_id}').last_failure_reason == 'concurrent_order_change'
    finally:
        engine.dispose()


@pytest.mark.parametrize('stamp', [
    '2026-11-09 01:00:00', '2026-11-09 01:00:00.000000', '2026-11-09 10:00:00+09:00',
])
def test_reconciliation_accepts_legacy_sqlite_utc_representations(
    db_session, accounts, fake_kis_admin_credentials, stamp,
):
    svc, client, _ = harness(db_session, accounts, fake_kis_admin_credentials, [page([evidence()])], 'user')
    row = order(db_session, client.user_id, submitted_at=None)
    db_session.execute(text('update orders set created_at=:stamp where id=:id'), {'stamp': stamp, 'id': row.id})
    db_session.commit()
    assert svc.reconcile_account(db_session, owner_user_id=client.user_id)['finalized_count'] == 1
    assert row.internal_status == 'CANCELED'


@pytest.mark.parametrize('scenario', [
    'verified', 'quantity', 'average_price', 'additional_buy', 'other_entry', 'open_sell', 'write_failure',
])
def test_order21_lifecycle_link_and_hold(db_session, accounts, fake_kis_admin_credentials, monkeypatch, scenario):
    broker_fill = evidence(
        odno='00021', ord_dt='20261118', ord_tmd='122246', pdno='036460', sll_buy_dvsn_cd='02',
        ord_qty='6', tot_ccld_qty='6', rmn_qty='0', avg_prvs='38350', cncl_yn='N',
    )
    svc, client, clock = harness(db_session, accounts, fake_kis_admin_credentials, [page([broker_fill])])
    clock[0] = datetime(2026, 11, 23, 4, tzinfo=UTC)
    client.read_reconciliation_account_snapshot = lambda **_: (
        [{'symbol': '036460', 'qty': 7 if scenario == 'quantity' else 6,
          'avg_entry_price': 38400 if scenario == 'average_price' else 38350}],
        [{'symbol': '036460', 'side': 'sell', 'unfilled_qty': 6}] if scenario == 'open_sell' else [],
    )
    row = order(
        db_session, None, id=21, symbol='036460', side='buy', internal_status='SUBMITTED',
        qty=6, requested_qty=6, remaining_qty=6, broker_order_id='21', kis_odno='21',
        submitted_at=datetime(2026, 11, 18, 3, 22, 40),
        request_payload='{"source":"strategy_live_auto_buy"}',
    )
    db_session.execute(text("update orders set created_at='2026-11-18 03:22:38' where id=21"))
    observed = datetime(2026, 11, 18, 3, 22, 51, 691685)
    original = PositionLifecycle(
        id=5, symbol=row.symbol, owner_user_id=None, entry_order_id=19 if scenario == 'other_entry' else -1,
        entry_source='order_log' if scenario == 'other_entry' else 'broker_position_snapshot',
        entry_time_source='broker_position_first_observed_at_fallback', status='open', opened_at=observed,
        quantity=6, entry_price=38350, cost_basis=230100, stop_loss_threshold_pct=2, take_profit_threshold_pct=4,
    )
    unrelated = PositionLifecycle(
        id=9, owner_user_id=accounts[1].id, symbol=row.symbol, entry_order_id=-2, quantity=2,
        status='open', entry_price=12345, cost_basis=24690, opened_at=observed,
    )
    blocked = order(db_session, 1, id=97, symbol=row.symbol, internal_status='REJECTED_BY_SAFETY_GATE',
                    broker_order_id=None, kis_odno=None)
    if scenario == 'additional_buy':
        order(db_session, None, id=23, symbol=row.symbol, side='buy', internal_status='FILLED', filled_qty=1,
              broker_order_id='23', kis_odno='23')
    db_session.add_all([original, unrelated])
    db_session.commit()
    assert position_sell_block_reason(db_session, owner_user_id=None, symbol=row.symbol, broker_quantity=6) == (
        'position_lifecycle_reconciliation_pending'
    )

    if scenario == 'write_failure':
        reconcile = KisPositionLifecycleService.reconcile_existing_buy_position

        def fail_after_link(*args):
            reconcile(*args)
            raise RuntimeError('simulated lifecycle transaction failure')

        with monkeypatch.context() as mp:
            mp.setattr(KisPositionLifecycleService, 'reconcile_existing_buy_position', fail_after_link)
            assert svc.reconcile_account(db_session, trigger='startup_or_periodic')['finalized_count'] == 0
        assert row.internal_status == 'SUBMITTED' and original.entry_order_id == -1
        assert db_session.query(TradeRunLog).filter_by(mode=MODE).count() == 0
        clock[0] += timedelta(minutes=10)

    assert svc.reconcile_account(db_session, trigger='startup_or_periodic')['finalized_count'] == 1
    assert (row.internal_status, row.filled_qty, row.remaining_qty) == ('FILLED', 6, 0)
    assert original.id == 5 and original.status == 'open' and original.quantity == 6
    assert original.entry_price == 38350 and original.stop_loss_threshold_pct == 2
    assert original.opened_at == observed
    if scenario in ('verified', 'write_failure'):
        assert original.entry_order_id == 21 and original.entry_source == 'broker_position_snapshot'
        assert original.manual_review_required is False
        assert position_sell_block_reason(db_session, owner_user_id=None, symbol=row.symbol, broker_quantity=6) is None
        assert position_sell_block_reason(db_session, owner_user_id=None, symbol=row.symbol, broker_quantity=5) == (
            'position_lifecycle_quantity_mismatch'
        )
    else:
        assert original.entry_order_id == (19 if scenario == 'other_entry' else -1)
        assert original.manual_review_required is True
        assert position_sell_block_reason(db_session, owner_user_id=None, symbol=row.symbol, broker_quantity=6) == (
            'position_lifecycle_manual_review'
        )
    assert unrelated.quantity == 2 and unrelated.entry_order_id == -2 and not unrelated.manual_review_required
    assert blocked.internal_status == 'REJECTED_BY_SAFETY_GATE'
    KisPositionLifecycleService(client=client).sync_filled_buy(db_session, row)
    clock[0] += timedelta(minutes=10)
    svc.reconcile_account(db_session, trigger='startup_or_periodic')
    assert db_session.query(PositionLifecycle).filter_by(owner_user_id=None, symbol=row.symbol, status='open').count() == 1
    assert db_session.query(TradeRunLog).filter_by(mode=MODE).count() == 1


def test_partial_fill_preserves_daily_cap_reservation_and_lifecycle(db_session, accounts, fake_kis_admin_credentials):
    svc, client, _ = harness(db_session, accounts, fake_kis_admin_credentials,
        [page([evidence(sll_buy_dvsn_cd='02', tot_ccld_qty='1', avg_prvs='10000')])], 'user')
    row = order(db_session, client.user_id, side='buy')
    reservation = AutomationProfileBuyReservation(reservation_key='original-slot', profile_key='profile',
        trade_date_kst='2026-11-09', scheduler_slot_kst='11:30', symbol=row.symbol,
        status='sync_required', order_id=row.id)
    db_session.add(reservation)
    db_session.commit()
    svc.reconcile_account(db_session, owner_user_id=client.user_id)
    assert row.internal_status == 'CANCELED' and row.filled_qty == 1
    assert daily_entry_counts(db_session, owner_user_id=client.user_id,
                              now=NOW - timedelta(days=7)) == (1, 0)
    from app.services.user_risk_state_service import UserRiskStateService
    assert UserRiskStateService().get_daily_trade_count(
        db_session, accounts[1], as_of=NOW - timedelta(days=7)) == 1
    assert daily_entry_counts(db_session, owner_user_id=client.user_id, now=NOW) == (0, 0)
    assert reservation.status == 'sync_required' and reservation.order_id == row.id
    assert db_session.query(PositionLifecycle).count() == 0  # historical buys cannot invent a current holding


def test_no_number_order19_and_missing_order20_do_not_clear_hold(db_session, accounts, fake_kis_admin_credentials):
    svc, client, _ = harness(db_session, accounts, fake_kis_admin_credentials, [page([])], 'user')
    buy = order(db_session, client.user_id, side='buy', broker_order_id=None, kis_odno=None,
                created_at=datetime(2026, 11, 4), submitted_at=datetime(2026, 11, 4))
    sell = order(db_session, client.user_id)
    svc.reconcile_account(db_session, owner_user_id=client.user_id)
    assert buy.internal_status == sell.internal_status == 'PENDING'
    assert sell.last_synced_at is not None
    assert position_management_block_reason(db_session, owner_user_id=client.user_id) is not None


def test_complete_second_page_and_daily_history_cache(db_session, accounts, fake_kis_admin_credentials):
    svc, client, _ = harness(db_session, accounts, fake_kis_admin_credentials,
        [page([], 'M', 'first', 'next'), page([evidence(), evidence(odno='19', sll_buy_dvsn_cd='02')])], 'user')
    sell = order(db_session, client.user_id)
    buy = order(db_session, client.user_id, side='buy', broker_order_id='19', kis_odno='19')
    svc.reconcile_account(db_session, owner_user_id=client.user_id)
    assert sell.internal_status == buy.internal_status == 'CANCELED'
    assert len(client.calls) == 2
    assert client.calls[1]['continuation'] == 'N' and client.calls[1]['nk'] == 'next'
    assert all(call['execution_filter'] == '00' and call['start_date'] == call['end_date'] for call in client.calls)


@pytest.mark.parametrize('pages', [
    [page([evidence()], 'M')],
    [page([evidence()], 'M', 'same', 'same')],
    [page([evidence()], 'unknown')],
    [page([evidence()], 'M', str(i), str(i)) for i in range(12)],
])
def test_incomplete_and_cyclic_pages_never_finalize(db_session, accounts, fake_kis_admin_credentials, pages):
    svc, client, _ = harness(db_session, accounts, fake_kis_admin_credentials, pages, 'user')
    row = order(db_session, client.user_id)
    svc.reconcile_account(db_session, owner_user_id=client.user_id)
    assert row.internal_status == 'PENDING' and row.sync_error == 'history_incomplete'
    assert len(client.calls) <= 12


def test_first_post_submit_read_bypasses_interval_but_never_lease(db_session, accounts, fake_kis_admin_credentials):
    svc, client, _ = harness(db_session, accounts, fake_kis_admin_credentials, [page([evidence()])], 'user')
    svc.reconcile_account(db_session, owner_user_id=client.user_id, trigger='pre_entry')
    row = order(db_session, client.user_id)
    result = svc.reconcile_account(db_session, owner_user_id=client.user_id, client=client,
                                   trigger='post_submit', order_id=row.id)
    assert row.internal_status == 'CANCELED' and result['finalized_count'] == 1
    assert len(client.calls) == 1


def test_retry_limit_stops_periodic_reads_until_next_regular_slot(db_session, accounts, fake_kis_admin_credentials):
    svc, client, clock = harness(db_session, accounts, fake_kis_admin_credentials, [page([])], 'user')
    local = order(db_session, client.user_id)
    for advance in (0, 31, 121):
        clock[0] += timedelta(seconds=advance)
        svc.reconcile_account(db_session, owner_user_id=client.user_id, trigger='periodic')
    clock[0] += timedelta(hours=1)
    svc.reconcile_account(db_session, owner_user_id=client.user_id, trigger='periodic')
    assert len(client.calls) == 3 and local.internal_status == 'PENDING'
    client.pages = [page([evidence()])]
    svc.reconcile_account(db_session, owner_user_id=client.user_id, trigger='pre_entry')
    assert len(client.calls) == 4 and local.internal_status == 'CANCELED'


def test_credential_rotation_during_read_cannot_finalize_old_scope(db_session, accounts, fake_kis_admin_credentials):
    from app.db.models import UserBrokerCredential
    from app.services.broker_credential_crypto_service import BrokerCredentialCryptoService
    svc, client, _ = harness(db_session, accounts, fake_kis_admin_credentials, [], 'user')
    local = order(db_session, client.user_id)
    def rotated():
        credential = db_session.query(UserBrokerCredential).filter_by(user_id=client.user_id, provider='kis').one()
        credential.encrypted_payload = BrokerCredentialCryptoService().encrypt(
            {**client.credentials, 'account_no': '88889999'})
        db_session.commit()
        return page([evidence()])
    client.pages = [rotated]
    svc.reconcile_account(db_session, owner_user_id=client.user_id)
    assert local.internal_status == 'PENDING' and local.sync_error == 'account_scope_mismatch'


def test_readonly_status_api_enforces_authenticated_account_scope(db_session, accounts):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.database import get_db
    from app.services.auth_dependencies import get_current_user
    admin, first, second, _ = accounts
    order(db_session, first.id, broker_order_id=None)
    order(db_session, second.id, broker_order_id=None)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: first
    try:
        api = TestClient(app)
        result = api.get(f'/users/me/trading/order-reconciliation?owner_user_id={second.id}')
        assert result.status_code == 200
        assert result.json()['scope'] == f'user:{first.id}'
        assert result.json()['unresolved_count'] == 1
        assert api.get('/kis/orders/reconciliation-status').status_code == 403
        app.dependency_overrides[get_current_user] = lambda: admin
        assert api.get('/kis/orders/reconciliation-status').json()['scope'] == 'admin'
        assert db_session.query(KisOrderReconciliationState).count() == 0
        assert db_session.query(TradeRunLog).filter_by(mode=MODE).count() == 0
    finally:
        app.dependency_overrides.clear()


def test_next_regular_slot_can_judge_without_replaying_finished_slot(db_session, accounts, fake_kis_admin_credentials, monkeypatch):
    from app.tests.test_user_auto_trading_scheduler_pr129 import _harness, _configure_user, _set_profile_schedule
    from app.db.models import UserAutoTradingSlotClaim
    first = accounts[1]
    _configure_user(db_session, first, provider='kis', mode='live', live_enabled=True,
                    kill_switch=False, confirmed=True)
    _set_profile_schedule(db_session, first, ['09:30', '11:30'])
    svc, client, clock = harness(db_session, accounts, fake_kis_admin_credentials, [page([])], 'user')
    row = order(db_session, client.user_id)
    scheduler, _account, _analysis, broker, _kis = _harness()
    monkeypatch.setattr(_account, 'get_kis_read_only_client', lambda *_: client)
    candidate_calls = []
    original_candidates = scheduler.candidate_service
    def candidates(*args, **kwargs):
        candidate_calls.append(kwargs['scheduler_slot'])
        return original_candidates(*args, **kwargs)
    scheduler.candidate_service = candidates
    first_result = scheduler.run_provider_once(db_session, provider='kis', scheduler_slot='09:30', now=NOW)
    assert first_result['processed'] == 1 and row.internal_status == 'PENDING'
    assert first_result['items'][0]['reason'] == 'local_unresolved_sell_order', first_result
    assert broker.buy_calls == _kis.buy_calls == []
    claim = db_session.query(UserAutoTradingSlotClaim).filter_by(user_id=first.id, scheduler_slot='09:30').one()
    original_claim = (claim.id, claim.status, claim.run_key)
    clock[0] += timedelta(minutes=61)
    client.pages = [page([evidence()])]
    svc.reconcile_account(db_session, owner_user_id=first.id, trigger='pre_entry')
    assert row.internal_status == 'CANCELED'
    assert _kis.buy_calls == []  # reconciliation itself cannot trigger entry
    assert (claim.id, claim.status, claim.run_key) == original_claim
    replay = scheduler.run_provider_once(db_session, provider='kis', scheduler_slot='09:30', now=NOW)
    assert replay['processed'] == 0 and broker.buy_calls == _kis.buy_calls == []
    next_result = scheduler.run_provider_once(db_session, provider='kis', scheduler_slot='11:30', now=NOW + timedelta(hours=2))
    assert next_result['processed'] == 1
    assert next_result['items'][0]['reason'] != 'local_unresolved_sell_order'
    assert candidate_calls == ['11:30']
    assert position_management_block_reason(db_session, owner_user_id=first.id, allow_own_open=True) is None
    assert len(_kis.buy_calls) <= 1
    submitted = len(_kis.buy_calls)
    repeated = scheduler.run_provider_once(db_session, provider='kis', scheduler_slot='11:30', now=NOW + timedelta(hours=2))
    assert repeated['processed'] == 0 and len(_kis.buy_calls) == submitted
