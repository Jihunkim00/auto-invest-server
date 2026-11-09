from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

import pytest

from app.db.models import (
    AccountBuyExecutionClaim, AutomationProfileBuyReservation, OrderLog,
    KisOrderSubmissionEvidence, PositionLifecycle, TradeRunLog, User,
)
from app.services.kis_daily_entry_accounting import daily_entry_counts
from app.services.kis_order_reconciliation_service import ReconciliationBlocked, fingerprint
from app.services.kis_unsubmitted_order_reconciliation_service import (
    KisUnsubmittedOrderReconciliationService, record_pre_submit_abort,
    read_admin_reconciliation_evidence,
)

NOW = datetime(2026, 11, 9, 3, 20, tzinfo=UTC)


class FakeBrokerEvidence:
    def __init__(self):
        self.calls = 0
        self.result = {'provider': 'kis', 'owner_user_id': None,
            'broker_account_id': 'admin:kis:KR', 'environment': 'live',
            'checked_at': NOW.isoformat(), 'complete': True, 'execution_filter': '00',
            'history_date': '2026-10-28', 'history_orders': [], 'open_orders': [], 'positions': [],
            'positions_reliable': True, 'open_orders_reliable': True}

    def __call__(self, db, order, now):
        self.calls += 1
        return deepcopy(self.result)


def setup(db, *, proof=False):
    db.add_all([User(id=1, username='admin', role='admin', enabled=True),
                User(id=2, username='test01', role='user', enabled=True)])
    for order_id, owner, side, status in [(18, None, 'buy', 'REQUESTED'),
            (13, None, 'sell', 'UNKNOWN_STALE'), (19, 2, 'buy', 'UNKNOWN_STALE')]:
        db.add(OrderLog(id=order_id, owner_user_id=owner, broker='kis', market='KR',
            symbol='036460', side=side, order_type='market', qty=7, requested_qty=7,
            remaining_qty=7, internal_status=status, created_at=datetime(2026, 10, 28, 2, 23),
            request_payload=json.dumps({'dispatch_protocol':'durable_unknown_before_submit_v1'}
                if proof and order_id == 18 else {})))
    db.add(AutomationProfileBuyReservation(id=10, reservation_key='admin:old:036460',
        provider='kis', market='KR', profile_key='admin-old', trade_date_kst='2026-10-28',
        scheduler_slot_kst='11:20', symbol='036460', status='reserved', order_id=18))
    db.commit()
    if proof:
        # Simulate a crash AFTER durable abort evidence, BEFORE terminal status.
        record_pre_submit_abort(db, db.get(OrderLog, 18), 'scheduler_task_expired_before_buy')
    broker = FakeBrokerEvidence()
    return KisUnsubmittedOrderReconciliationService(broker, now_provider=lambda: NOW), broker


def test_old18_blocks_until_positive_evidence_and_explicit_approval(db_session):
    db = db_session
    service, broker = setup(db)
    unaffected = {key: fingerprint(db.get(OrderLog, key)) for key in (13, 19)}
    assert daily_entry_counts(db, now=NOW) == (0, 1)
    assert daily_entry_counts(db, now=NOW, owner_user_id=1) == (0, 0)
    assert daily_entry_counts(db, now=NOW, owner_user_id=2) == (0, 1)
    with pytest.raises(ReconciliationBlocked, match='positive_pre_submit_evidence_missing'):
        service.propose(db, order_id=18, admin_user_id=1)
    assert broker.calls == 0
    # A separate, verifiable protocol history is a counterfactual test input;
    # the legacy production row has no such evidence and is never changed.
    db.get(OrderLog, 18).request_payload = json.dumps({'dispatch_protocol':'durable_unknown_before_submit_v1'})
    db.commit()
    record_pre_submit_abort(db, db.get(OrderLog, 18), 'scheduler_task_expired_before_buy')
    plan = service.propose(db, order_id=18, admin_user_id=1)
    assert (plan['owner_user_id'], plan['policy_user_id']) == (None, 1)
    with pytest.raises(ReconciliationBlocked, match='explicit_plan_approval_required'):
        service.apply(db, plan=plan, admin_user_id=1, approval_digest='wrong', approval_reference='TEST')
    assert daily_entry_counts(db, now=NOW) == (0, 1)
    result = service.apply(db, plan=plan, admin_user_id=1,
        approval_digest=plan['approval_digest'], approval_reference='TEST_ONLY_APPROVAL')
    assert result['internal_status'] == 'REJECTED_BY_SAFETY_GATE'
    assert daily_entry_counts(db, now=NOW) == (0, 0)
    assert daily_entry_counts(db, now=NOW, owner_user_id=2) == (0, 1)
    assert db.get(AutomationProfileBuyReservation, 10).status == 'blocked'
    assert db.get(AutomationProfileBuyReservation, 10).reservation_key == 'admin:old:036460'
    audit = db.get(TradeRunLog, result['audit_id'])
    state = json.loads(audit.response_payload)
    assert state['before']['internal_status'] == 'REQUESTED'
    assert state['after']['internal_status'] == 'REJECTED_BY_SAFETY_GATE'
    assert broker.calls == 2  # review and fresh apply-time evidence
    assert db.query(AccountBuyExecutionClaim).count() == 0
    assert all(fingerprint(db.get(OrderLog, key)) == value for key, value in unaffected.items())


@pytest.mark.parametrize('change,reason', [
    ('unknown', 'broker_submission_possible'), ('broker_id', 'broker_submission_possible'),
    ('submitted', 'broker_submission_possible'), ('partial', 'broker_submission_possible'),
    ('journal_dispatch', 'broker_submission_possible'), ('history', 'broker_submission_possible'),
    ('open', 'broker_submission_possible'), ('position', 'broker_submission_possible'),
    ('incomplete', 'evidence_incomplete'), ('fills_only', 'evidence_incomplete'),
    ('wrong_owner', 'evidence_scope_mismatch'), ('stale', 'evidence_stale'),
    ('claim', 'account_buy_in_progress'), ('regular_actor', 'admin_approval_required'),
    ('regular_order', 'legacy_admin_buy_scope_required'),
])
def test_uncertain_submission_and_wrong_accounts_remain_blocked(db_session, change, reason):
    db = db_session
    service, broker = setup(db, proof=True)
    order, actor, order_id = db.get(OrderLog, 18), 1, 18
    if change == 'unknown': order.internal_status = 'UNKNOWN_STALE'
    if change == 'broker_id': order.broker_order_id = 'FAKE-POSSIBLE'
    if change == 'submitted': order.submitted_at = NOW
    if change == 'partial': order.filled_qty = 1
    if change == 'journal_dispatch':
        db.add(TradeRunLog(owner_user_id=None, run_key='fake-dispatch', trigger_source='execution_core',
            symbol=order.symbol, mode='execution', order_id=18,
            response_payload=json.dumps({'broker_submit_called': True})))
    if change in {'history', 'open', 'position'}:
        broker.result[{'history':'history_orders','open':'open_orders','position':'positions'}[change]] = [
            {'symbol': '036460', 'qty': 1}]
    if change == 'incomplete': broker.result['complete'] = False
    if change == 'fills_only': broker.result['execution_filter'] = '01'
    if change == 'wrong_owner': broker.result['owner_user_id'] = 2
    if change == 'stale': broker.result['checked_at'] = (NOW - timedelta(seconds=61)).isoformat()
    if change == 'claim': db.add(AccountBuyExecutionClaim(broker_account_id='admin:kis:KR',token='FAKE'))
    if change == 'regular_actor': actor = 2
    if change == 'regular_order': order_id = 19
    db.commit()
    before = fingerprint(order)
    with pytest.raises(ReconciliationBlocked, match=reason):
        service.propose(db, order_id=order_id, admin_user_id=actor)
    assert fingerprint(order) == before
    assert db.query(TradeRunLog).filter_by(mode='kis_pre_submit_reconciliation').count() == 0


@pytest.mark.parametrize('target', ['order', 'reservation', 'proof', 'broker'])
def test_apply_revalidates_every_source(db_session, target):
    db = db_session
    service, broker = setup(db, proof=True)
    plan = service.propose(db, order_id=18, admin_user_id=1)
    if target == 'order': db.get(OrderLog, 18).error_message = 'changed'
    if target == 'reservation': db.get(AutomationProfileBuyReservation, 10).block_reason = 'changed'
    if target == 'proof': db.get(KisOrderSubmissionEvidence, plan['proof_id']).reason = 'changed'
    if target == 'broker': broker.result['open_orders'] = [{'symbol': '036460'}]
    db.commit()
    before = fingerprint(db.get(OrderLog, 18))
    with pytest.raises(ReconciliationBlocked):
        service.apply(db, plan=plan, admin_user_id=1,
            approval_digest=plan['approval_digest'], approval_reference='TEST_ONLY')
    assert fingerprint(db.get(OrderLog, 18)) == before
    assert daily_entry_counts(db, now=NOW) == (0, 1)
    assert db.query(AccountBuyExecutionClaim).count() == 0


def test_get_adapter_reads_all_pages_and_historical_unfilled(db_session, monkeypatch):
    db = db_session
    setup(db)
    import app.services.kis_order_account_scope as scope_module
    monkeypatch.setattr(scope_module, 'resolve_order_account_scope', lambda *a, **kw:
        SimpleNamespace(account=SimpleNamespace(legacy_admin=True, broker_account_id='admin:kis:KR'),
                        identity=('live','FAKE','01')))
    class FakeKisClient:
        def __init__(self): self.calls = []
        def inquire_account_executions_page(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return {'orders': [], 'tr_cont': 'M', 'fk': 'FAKE-FK', 'nk': 'FAKE-NK'}
            return {'orders': [], 'tr_cont': 'D', 'fk': '', 'nk': ''}
        def list_positions(self): return []
    client = FakeKisClient()
    evidence = read_admin_reconciliation_evidence(db, db.get(OrderLog,18), NOW, client=client)
    assert evidence['complete'] is True and evidence['history_date'] == '2026-10-28'
    assert len(client.calls) == 3
    assert all(call['execution_filter'] == '00' for call in client.calls)
    assert client.calls[1]['continuation'] == 'N' and client.calls[1]['fk'] == 'FAKE-FK'
