from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json

import pytest
from sqlalchemy import or_

from app.db.database import SessionLocal
from app.db.models import OrderLog, PositionLifecycle, TradeRunLog, User
from app.services.kis_order_reconciliation_service import (
    ReconciliationBlocked, propose_reconciliation, apply_verified_reconciliation, fingerprint,
)
from app.services.kis_order_sync_service import KisOrderSyncService
from app.services.user_trading_execution_service import UserTradingExecutionService
from app.tests.integration.test_pr138_account_risk_gate_matrix import setup_matrix, run, profile_values
from app.tests.integration.test_pr138_multi_account_normalization import no_network_or_real_submission

FAKE_ORDER_NO = 'FAKE-ORDER14-2100'


def reconstruction(db, monkeypatch):
    harness, states, _snapshot = setup_matrix(db, monkeypatch)
    first = states[1]
    profile_values(db, first, lambda settings: settings['entry'].update(analysis_times=['11:30', '13:30']))
    order = OrderLog(id=14, owner_user_id=first.user_id, broker='kis', market='KR', currency='KRW',
        symbol='028670', side='sell', order_type='market', qty=5, requested_qty=5, filled_qty=0, remaining_qty=5,
        internal_status='UNKNOWN_STALE', broker_status='submitted', broker_order_status='not_found_in_inquiry',
        broker_order_id=FAKE_ORDER_NO, kis_odno=FAKE_ORDER_NO,
        created_at=datetime(2026, 10, 14, 2, 30, 21), submitted_at=datetime(2026, 10, 14, 2, 30, 21, 621677),
        last_synced_at=datetime(2026, 10, 19, 8, 12, 17, 794338), sync_error='kis_order_not_found_in_inquiry',
        error_message='kis_order_not_found_in_inquiry',
        request_payload=json.dumps({'provider': 'kis', 'market': 'KR', 'side': 'sell', 'mode': 'alpaca_live',
            'trigger_source': 'user_scheduler', 'authorization_mode': 'automatic', 'scheduler_slot': '11:30'}),
        response_payload=json.dumps({'id': FAKE_ORDER_NO, 'status': 'submitted', 'filled_qty': 0}),
        last_sync_payload=json.dumps({'inquiry': {'orders': []}}))
    db.add(order)
    db.commit()
    db.refresh(order)
    now = harness.clock.now()
    scope = {'owner_user_id': first.user_id, 'provider': 'kis', 'environment': 'live',
        'broker_account_id': f'user:{first.user_id}:kis:KR', 'checked_at': now.isoformat()}
    history = {**scope, 'complete': True, 'orders': [{'odno': FAKE_ORDER_NO, 'ord_dt': '20261014',
        'ord_tmd': '113021', 'pdno': '028670', 'sll_buy_dvsn_cd': '01', 'ord_qty': '5',
        'tot_ccld_qty': '5', 'rmn_qty': '0', 'rjct_qty': '0', 'cncl_yn': '', 'avg_prvs': '7070'}]}
    snapshot = {**first.account.get_broker_snapshot(db, db.get(User, first.user_id), 'kis'), **scope}
    return harness, states, order, history, snapshot


def run_next_slot(state, harness):
    with SessionLocal() as db:
        result = state.scheduler.run_provider_once(db, provider='kis', scheduler_slot='13:30',
            owner_user_id=state.user_id, now=harness.clock.now())
        item = next(row for row in result['items'] if row.get('owner_user_id') == state.user_id)
        if item.get('result') == 'submitted':
            order = KisOrderSyncService(state.client, now_provider=harness.clock.now).sync_order(db, item['order_id'])
            UserTradingExecutionService._maybe_create_position_lifecycle(db,
                user=db.get(User, state.user_id), order=order, now=harness.clock.now())
        return item


def test_verified_order14_repair_unblocks_next_real_slot_with_account_isolation(monkeypatch, tmp_path,
        no_network_or_real_submission, caplog):
    with SessionLocal() as db:
        harness, states, order, history, snapshot = reconstruction(db, monkeypatch)
        original = (order.request_payload, order.response_payload, order.submitted_at)
        initial_hash = fingerprint(order)
        plan = propose_reconciliation(order, history=history, snapshot=snapshot, now=harness.clock.now())
        assert fingerprint(order) == initial_hash and order.internal_status == 'UNKNOWN_STALE'
    with caplog.at_level('INFO', logger='app.services.kis_order_account_scope'):
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda state: run(state, harness.clock), states))
    admin, first, second = states
    blocked = results[1]
    assert blocked['reason'] == 'local_unresolved_sell_order', blocked
    evidence = blocked['position_management']
    assert evidence['local_order_id'] == 14 and evidence['order_status'] == 'UNKNOWN_STALE'
    assert evidence['remaining_quantity'] == 5 and evidence['order_source'] == 'user_scheduler'
    assert evidence['checked_at'] and 'order_id=14' in caplog.text
    assert FAKE_ORDER_NO not in caplog.text
    assert len(admin.buys) == len(second.buys) == 1 and first.buys == []
    assert first.responses.calls == []
    with SessionLocal() as db:
        unaffected = {row.id: fingerprint(row) for row in db.query(OrderLog).filter(or_(
            OrderLog.owner_user_id.is_(None), OrderLog.owner_user_id != first.user_id)).all()}
        repaired = apply_verified_reconciliation(db, plan, approval_reference='TEST_ONLY_USER_APPROVAL_ORDER14',
            history=history, snapshot=snapshot, now=harness.clock.now())
        order = db.get(OrderLog, 14)
        assert (order.internal_status, order.filled_qty, order.remaining_qty, order.avg_fill_price) == ('FILLED', 5, 0, 7070)
        assert (order.request_payload, order.response_payload, order.submitted_at) == original
        assert order.filled_at is None and order.sync_error is None
        assert order.last_sync_payload and obj(order.last_sync_payload)['inquiry'] == {'orders': []}
        audit = db.get(TradeRunLog, repaired['audit_id'])
        assert audit.owner_user_id == first.user_id and audit.order_id == 14
        assert audit.reason == 'broker_terminal_order_verified'
        assert obj(audit.response_payload)['before']['sync_error'] == 'kis_order_not_found_in_inquiry'
        assert all(fingerprint(db.get(OrderLog, key)) == value for key, value in unaffected.items())
        # The historical SELL is not falsely counted as a trade today.
        risk = first.risk.get_user_risk_state(db, db.get(User, first.user_id), as_of=harness.clock.now())
        assert risk['daily_trade_count'] == 0
    harness.clock.current = harness.clock.now().replace(hour=13, minute=30)
    result = run_next_slot(first, harness)
    assert result['result'] == 'submitted', result
    assert result['position_management']['action'] == 'entry_scan'
    assert len(first.preview.result['runtime_input_symbols']) == 50
    assert len(first.responses.calls) == 5 and len(first.buys) == 1
    with SessionLocal() as db:
        assert db.query(OrderLog).filter_by(owner_user_id=first.user_id, side='buy', internal_status='FILLED').count() == 1
        assert db.query(PositionLifecycle).filter_by(owner_user_id=first.user_id, status='open').count() == 1
        assert db.query(OrderLog).filter_by(id=14, internal_status='FILLED').count() == 1
        assert all(fingerprint(db.get(OrderLog, key)) == value for key, value in unaffected.items())
    assert no_network_or_real_submission == {'actual_kis_submit_count': 0, 'external_network_count': 0}
    (tmp_path / 'order14-repair-simulation.json').write_text(json.dumps({
        'production_database_modified': False, 'actual_kis_submit_count': 0,
        'before': {'reason': blocked['reason'], 'evidence': evidence, 'fake_buy_count': 0, 'fake_filled_count': 0},
        'approved_test_repair': plan,
        'after': {'slot': '13:30', 'reason': result['reason'], 'position_action': 'entry_scan',
            'fake_buy_count': 1, 'fake_filled_count': 1, 'gpt_completed': 5,
            'gates': result['run_diagnostics']['gates']}, 'other_accounts_unchanged': True}, ensure_ascii=False, indent=2), encoding='utf-8')


def obj(value):
    return json.loads(value)


@pytest.mark.parametrize('failure,reason', [
    ('missing', 'broker_order_not_uniquely_verified'), ('duplicate', 'broker_order_not_uniquely_verified'),
    ('incomplete', 'history_incomplete'), ('wrong_owner', 'evidence_scope_mismatch'),
    ('wrong_account', 'evidence_scope_mismatch'), ('wrong_symbol', 'broker_order_identity_mismatch'),
    ('wrong_side', 'broker_order_identity_mismatch'), ('wrong_date', 'broker_order_identity_mismatch'),
    ('stale', 'evidence_stale'), ('active', 'broker_active_sell_order'),
    ('unknown', 'order_status_unverified'), ('unreliable', 'account_snapshot_unreliable'),
    ('partial', 'broker_order_not_terminal'), ('quantity', 'broker_quantity_mismatch'),
    ('nan', 'broker_quantity_invalid'), ('no_price', 'broker_fill_price_missing')])
def test_unverified_repair_fails_closed_without_mutating_order(monkeypatch, failure, reason):
    with SessionLocal() as db:
        harness, states, order, history, snapshot = reconstruction(db, monkeypatch)
        original = fingerprint(order)
        row = history['orders'][0]
        if failure == 'missing': history['orders'] = []
        elif failure == 'duplicate': history['orders'].append(dict(row))
        elif failure == 'incomplete': history['complete'] = False
        elif failure == 'wrong_owner': history['owner_user_id'] = states[2].user_id
        elif failure == 'wrong_account': history['broker_account_id'] = 'admin:kis:KR'
        elif failure == 'wrong_symbol': row['pdno'] = '005930'
        elif failure == 'wrong_side': row['sll_buy_dvsn_cd'] = '02'
        elif failure == 'wrong_date': row['ord_dt'] = '20261013'
        elif failure == 'stale': history['checked_at'] = (harness.clock.now()-timedelta(seconds=301)).isoformat()
        elif failure in {'active', 'unknown'}:
            snapshot['open_orders'] = [{'symbol': '028670', 'side': 'sell', 'status':
                'pending' if failure == 'active' else 'unknown', 'remaining_quantity': 5}]
        elif failure == 'unreliable': snapshot['positions_reliable'] = False
        elif failure == 'partial': row.update(tot_ccld_qty='2', rmn_qty='3')
        elif failure == 'quantity': row['ord_qty'] = '6'
        elif failure == 'nan': row['tot_ccld_qty'] = 'NaN'
        elif failure == 'no_price': row['avg_prvs'] = '0'
        with pytest.raises(ReconciliationBlocked, match=reason):
            propose_reconciliation(order, history=history, snapshot=snapshot, now=harness.clock.now())
        assert fingerprint(order) == original and states[1].buys == []


@pytest.mark.parametrize('failure', ['approval', 'changed_order', 'changed_broker_status'])
def test_apply_requires_approval_and_exact_unchanged_order(monkeypatch, failure):
    with SessionLocal() as db:
        harness, states, order, history, snapshot = reconstruction(db, monkeypatch)
        plan = propose_reconciliation(order, history=history, snapshot=snapshot, now=harness.clock.now())
        if failure == 'changed_order':
            order.remaining_qty = 4
            db.commit()
        elif failure == 'changed_broker_status':
            order.broker_status = 'filled'
            db.commit()
        before = fingerprint(order)
        with pytest.raises(ReconciliationBlocked, match='approval_required' if failure == 'approval' else 'plan_stale'):
            apply_verified_reconciliation(db, plan, approval_reference='' if failure == 'approval' else 'TEST_ONLY',
                history=history, snapshot=snapshot, now=harness.clock.now())
        assert fingerprint(order) == before
        assert db.query(TradeRunLog).filter_by(mode='kis_order_reconciliation').count() == 0


@pytest.mark.parametrize('terminal', ['CANCELED', 'REJECTED'])
def test_verified_terminal_zero_fill_never_fabricates_a_fill(monkeypatch, terminal):
    with SessionLocal() as db:
        harness, _states, order, history, snapshot = reconstruction(db, monkeypatch)
        history['orders'][0].update(tot_ccld_qty='0', rmn_qty='0', avg_prvs='0',
            cncl_yn='Y' if terminal == 'CANCELED' else '', rjct_qty='5' if terminal == 'REJECTED' else '0')
        plan = propose_reconciliation(order, history=history, snapshot=snapshot, now=harness.clock.now())
        result = apply_verified_reconciliation(db, plan, approval_reference='TEST_ONLY_TERMINAL',
            history=history, snapshot=snapshot, now=harness.clock.now())
        assert result['internal_status'] == terminal
        assert order.filled_qty == 0 and order.remaining_qty == 0
        assert order.filled_at is None and order.avg_fill_price is None
