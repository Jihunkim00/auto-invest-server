from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.db.models import (
    AccountBuyExecutionClaim,
    AutomationProfileBuyReservation,
    AutomationSchedulerSlot,
    KisLegacyOrderReconciliation,
    KisOrderValidationLog,
    OrderLog,
    PositionExitRetryJob,
    PositionLifecycle,
    RuntimeSetting,
    TradeRunLog,
    User,
)
from app.services.account_trading_limit_service import AccountTradingLimitService
from app.services.admin_preflight_service import check_admin_preflight
from app.services.automation_profile_service import AutomationProfileService
from app.services.kis_daily_entry_accounting import daily_entry_counts
from app.services.kis_legacy_admin_reconciliation_service import (
    KisLegacyAdminOrderReconciliationService,
    read_legacy_admin_broker_evidence,
)
from app.services.kis_legacy_order_state import LEGACY_ABSENCE_VERIFIED
from app.services.kis_order_reconciliation_service import ReconciliationBlocked, fingerprint

NOW = datetime(2026, 11, 9, 3, 20, tzinfo=UTC)
PROFILE = {
    'id': 5, 'owner_user_id': 1, 'profile_key': 'aut_kis_eec5f898',
    'provider': 'kis', 'market': 'KR', 'status': 'active', 'enabled': True,
}
PROFILE_SCHEDULE = {'profile': {
    **PROFILE, 'settings': {'entry': {'max_new_entries_per_day': 1, 'analysis_times': ['11:10', '12:20', '13:30']},
        'max_open_positions': 1},
    'entry': {'max_new_entries_per_day': 1, 'analysis_times': ['11:10', '12:20', '13:30']},
}}


class FakeBroker:
    def __init__(self):
        self.read_count = 0
        self.result = {
            'provider': 'kis', 'owner_user_id': None, 'broker_account_id': 'admin:kis:KR',
            'environment': 'live', 'checked_at': NOW.isoformat(), 'complete': True,
            'execution_filter': '00', 'exchange_scope': 'ALL', 'history_date': '2026-10-28',
            'history_page_count': 1, 'history_orders': [],
            'history_summary': {'order_count': 0, 'status_counts': {}},
            'open_orders': [], 'positions': [], 'open_orders_reliable': True,
            'positions_reliable': True, 'selected_profile': deepcopy(PROFILE),
        }

    def __call__(self, db, order, now):
        self.read_count += 1
        result = deepcopy(self.result)
        if result.get('checked_at') == NOW.isoformat():
            result['checked_at'] = now.isoformat()
        return result

    def list_positions(self):
        return []

    def list_open_orders(self):
        return []


def configure_profile(monkeypatch, profile=None):
    selected = deepcopy(profile or PROFILE)
    schedule = {'profile': {
        **selected,
        'settings': {'entry': {'max_new_entries_per_day': 1, 'analysis_times': ['11:10', '12:20', '13:30'],
                'min_final_score': 65, 'no_new_entry_after': '14:00'},
            'capital': {'cash_only': True},
            'max_open_positions': 1},
        'entry': {'max_new_entries_per_day': 1, 'analysis_times': ['11:10', '12:20', '13:30'],
            'min_final_score': 65, 'no_new_entry_after': '14:00'},
        'max_open_positions': 1,
    }}
    monkeypatch.setattr(AutomationProfileService, 'selected_profile_schedule',
        lambda self, db, *, now=None: deepcopy(schedule))
    return selected


def setup(db, monkeypatch, *, profile=None):
    selected = configure_profile(monkeypatch, profile)
    db.add_all([
        User(id=1, username='admin', role='admin', enabled=True),
        User(id=2, username='test01', role='user', enabled=True),
        RuntimeSetting(id=1, active_automation_profile_key=selected['profile_key'],
            automation_mode='live', operation_mode_requested='live', bot_enabled=True,
            dry_run=False, kill_switch=False, scheduler_enabled=True,
            automation_profile_scheduler_enabled=True),
    ])
    # Seed the immutable production snapshot values from docs/pr144-readonly-evidence.json.
    snapshot = json.loads((Path(__file__).resolve().parents[3] / 'docs' /
        'pr144-readonly-evidence.json').read_text(encoding='utf-8'))['order18']
    assert (snapshot['id'], snapshot['owner_user_id'], snapshot['symbol'], snapshot['side'],
            snapshot['internal_status']) == (18, None, '036460', 'buy', 'REQUESTED')
    order = OrderLog(
        id=18, owner_user_id=None, broker='kis', market='KR', symbol='036460',
        profile_id=None, profile_key=None, side='buy', order_type='market', qty=7,
        notional=258300, requested_qty=7, remaining_qty=7,
        internal_status='REQUESTED', created_at=datetime(2026, 10, 28, 2, 23),
        request_payload=json.dumps({
            **snapshot['request'], 'automation_profile_key': selected['profile_key'],
            'reservation_key': 'admin:old:036460',
        }), response_payload='{}', last_sync_payload='{}',
    )
    order13 = OrderLog(id=13, owner_user_id=None, broker='kis', market='KR', symbol='036460',
        side='sell', order_type='market', qty=7, requested_qty=7,
        internal_status='UNKNOWN_STALE', created_at=datetime(2026, 10, 20, 2, 23),
        request_payload='{}', response_payload='{}', last_sync_payload='{}')
    order19 = OrderLog(id=19, owner_user_id=2, broker='kis', market='KR', symbol='036460',
        side='buy', order_type='market', qty=1, requested_qty=1,
        internal_status='UNKNOWN_STALE', created_at=datetime(2026, 10, 28, 2, 23),
        request_payload='{}', response_payload='{}', last_sync_payload='{}')
    reservation = AutomationProfileBuyReservation(
        id=10, reservation_key='admin:old:036460', provider='kis', market='KR',
        profile_key=selected['profile_key'], trade_date_kst='2026-10-28',
        scheduler_slot_kst='11:20', symbol='036460', status='reserved', order_id=18,
    )
    db.add_all([order, order13, order19, reservation,
        KisOrderValidationLog(id=15, market='KR', symbol='036460', side='buy', qty=7,
            validated_for_submission=True, created_at=datetime(2026, 10, 28, 2, 23, 2))])
    db.commit()
    import app.services.kis_legacy_admin_reconciliation_service as legacy_module
    monkeypatch.setattr(legacy_module, 'resolve_order_account_scope', lambda *args, **kwargs:
        SimpleNamespace(account=SimpleNamespace(owner_user_id=1, legacy_admin=True,
            broker_account_id='admin:kis:KR'), identity=('live', '11112222', '01')))
    broker = FakeBroker()
    service = KisLegacyAdminOrderReconciliationService(broker, now_provider=lambda: NOW)
    return service, broker, order13, order19


def account_pending_amount(db):
    limits = AccountTradingLimitService().calculate(db, symbol='036460', positions=[],
        profile_order_cap=500000, available_cash=1000000, owner_user_id=None)
    return limits['pending_buy_exposure_krw']


def test_real_order18_clone_review_and_approved_recovery_releases_both_limits(db_session, monkeypatch):
    db = db_session
    service, broker, order13, order19 = setup(db, monkeypatch)
    untouched = {13: fingerprint(order13), 19: fingerprint(order19)}
    assert daily_entry_counts(db, now=NOW) == (0, 1)
    assert daily_entry_counts(db, now=NOW, owner_user_id=1) == (0, 0)
    assert daily_entry_counts(db, now=NOW, owner_user_id=2) == (0, 1)
    assert account_pending_amount(db) == 258300

    plan = service.propose(db, order_id=18, admin_user_id=1)
    assert plan['protocol'] == 'legacy_admin_broker_absence_v1'
    assert plan['historical_submit_call_state'] == 'not_provable_from_legacy_logs'
    assert plan['not_submitted_asserted'] is False
    assert plan['broker_evidence']['history_date'] == '2026-10-28'
    assert plan['broker_evidence']['execution_filter'] == '00'
    assert plan['broker_evidence']['exchange_scope'] == 'ALL'
    assert plan['broker_evidence']['target_symbol_matches'] == 0
    assert plan['execution_trace']['nearby_validated_true_count'] == 1

    with pytest.raises(ReconciliationBlocked, match='explicit_plan_approval_required'):
        service.apply(db, plan=plan, admin_user_id=1,
            approval_digest='wrong', approval_reference='TEST-APPROVAL')
    assert daily_entry_counts(db, now=NOW) == (0, 1)
    result = service.apply(db, plan=plan, admin_user_id=1,
        approval_digest=plan['approval_digest'], approval_reference='TEST-APPROVAL-PR145')
    assert result['internal_status'] == LEGACY_ABSENCE_VERIFIED
    assert result['not_submitted_asserted'] is False
    assert db.get(OrderLog, 18).broker_status is None
    assert db.get(OrderLog, 18).broker_order_status is None
    assert daily_entry_counts(db, now=NOW) == (0, 0)
    assert daily_entry_counts(db, now=NOW, owner_user_id=2) == (0, 1)
    assert account_pending_amount(db) == 0
    assert db.get(AutomationProfileBuyReservation, 10).status == 'blocked'
    assert db.get(AutomationProfileBuyReservation, 10).block_reason == 'legacy_broker_order_absence_verified'
    audit = db.query(KisLegacyOrderReconciliation).filter_by(order_id=18).one()
    assert json.loads(audit.before_state_json)['internal_status'] == 'REQUESTED'
    assert json.loads(audit.after_state_json)['internal_status'] == LEGACY_ABSENCE_VERIFIED
    assert audit.approved_by_user_id == 1 and audit.approval_reference == 'TEST-APPROVAL-PR145'
    assert broker.read_count == 2  # review and fresh apply-time broker evidence
    assert fingerprint(db.get(OrderLog, 13)) == untouched[13]
    assert fingerprint(db.get(OrderLog, 19)) == untouched[19]
    assert db.query(AccountBuyExecutionClaim).count() == 0


@pytest.mark.parametrize('change,reason', [
    ('history_incomplete', 'evidence_incomplete'),
    ('filter', 'evidence_incomplete'),
    ('exchange', 'evidence_incomplete'),
    ('open_orders', 'broker_submission_possible'),
    ('position', 'broker_submission_possible'),
    ('history_match', 'broker_submission_possible'),
    ('stale', 'evidence_stale'),
    ('claim', 'account_buy_in_progress'),
    ('profile', 'order_profile_mismatch'),
    ('submit_marker', 'broker_submission_marker_present'),
    ('analysis_submit_marker', 'broker_submission_marker_present'),
    ('scheduler_submit_marker', 'broker_submission_marker_present'),
])
def test_legacy_path_fails_closed_on_uncertainty(db_session, monkeypatch, change, reason):
    db = db_session
    service, broker, order13, order19 = setup(db, monkeypatch)
    if change == 'history_incomplete': broker.result['complete'] = False
    if change == 'filter': broker.result['execution_filter'] = '01'
    if change == 'exchange': broker.result['exchange_scope'] = 'KRX'
    if change == 'open_orders': broker.result['open_orders'] = [
        {'order_id': 'FAKE-ORDER', 'symbol': '036460', 'side': 'buy', 'unfilled_qty': 1}]
    if change == 'position': broker.result['positions'] = [{'symbol': '036460', 'qty': 1}]
    if change == 'history_match': broker.result['history_orders'] = [{'pdno': '036460'}]
    if change == 'stale': broker.result['checked_at'] = (NOW - timedelta(seconds=61)).isoformat()
    if change == 'claim': db.add(AccountBuyExecutionClaim(broker_account_id='admin:kis:KR', token='FAKE'))
    if change == 'profile':
        configure_profile(monkeypatch, {**PROFILE, 'profile_key': 'different_profile'})
    if change == 'submit_marker':
        db.add(TradeRunLog(owner_user_id=None, run_key='legacy-submit-marker',
            trigger_source='execution_core', symbol='036460', order_id=18,
            mode='execution', stage='submit', result='unknown',
            response_payload=json.dumps({'broker_submit_called': True})))
    if change == 'analysis_submit_marker':
        db.add(TradeRunLog(owner_user_id=None, run_key='legacy-analysis-submit-marker',
            trigger_source='automation_profile_scheduler', symbol='036460',
            mode='automation_scheduler_profile_analysis', stage='done', result='unknown',
            created_at=datetime(2026, 10, 28, 2, 23),
            request_payload=json.dumps({'automation_profile_key': PROFILE['profile_key']}),
            response_payload=json.dumps({'real_order_submitted': True})))
    if change == 'scheduler_submit_marker':
        db.add(AutomationSchedulerSlot(account_key='admin', provider='kis', profile_id=5,
            slot_key='admin:kis:2026-10-28:11:20', scheduled_at=datetime(2026, 10, 28, 2, 20),
            status='failed', reason='scheduler_task_timeout',
            result_json=json.dumps({'broker_submit_called': True})))
    db.commit()
    before = fingerprint(db.get(OrderLog, 18))
    with pytest.raises(ReconciliationBlocked, match=reason):
        service.propose(db, order_id=18, admin_user_id=1)
    assert fingerprint(db.get(OrderLog, 18)) == before
    assert daily_entry_counts(db, now=NOW) == (0, 1)
    assert db.query(KisLegacyOrderReconciliation).count() == 0


def test_a_manual_legacy_terminal_string_without_audit_keeps_count_and_amount(db_session, monkeypatch):
    db = db_session
    setup(db, monkeypatch)
    db.get(OrderLog, 18).internal_status = LEGACY_ABSENCE_VERIFIED
    db.commit()
    assert daily_entry_counts(db, now=NOW) == (0, 1)
    assert account_pending_amount(db) == 258300


def test_duplicate_approval_is_rejected_and_audit_is_unique(db_session, monkeypatch):
    db = db_session
    service, _, _, _ = setup(db, monkeypatch)
    plan = service.propose(db, order_id=18, admin_user_id=1)
    service.apply(db, plan=plan, admin_user_id=1,
        approval_digest=plan['approval_digest'], approval_reference='TEST-ONCE')
    with pytest.raises(ReconciliationBlocked, match='already_applied'):
        service.apply(db, plan=plan, admin_user_id=1,
            approval_digest=plan['approval_digest'], approval_reference='TEST-REPLAY')
    assert db.query(KisLegacyOrderReconciliation).count() == 1


def test_admin_and_test01_are_isolated(db_session, monkeypatch):
    db = db_session
    service, _, _, _ = setup(db, monkeypatch)
    with pytest.raises(ReconciliationBlocked, match='admin_approval_required'):
        service.propose(db, order_id=18, admin_user_id=2)
    with pytest.raises(ReconciliationBlocked, match='legacy_admin_buy_scope_required'):
        service.propose(db, order_id=19, admin_user_id=1)
    assert daily_entry_counts(db, now=NOW, owner_user_id=2) == (0, 1)
    assert db.get(OrderLog, 13).internal_status == 'UNKNOWN_STALE'
    assert db.get(OrderLog, 19).internal_status == 'UNKNOWN_STALE'


def test_history_adapter_reads_all_pages_and_all_status_filter(db_session, monkeypatch):
    db = db_session
    setup(db, monkeypatch)
    import app.services.kis_legacy_admin_reconciliation_service as legacy_module
    monkeypatch.setattr(legacy_module, 'resolve_order_account_scope', lambda *args, **kwargs:
        SimpleNamespace(account=SimpleNamespace(owner_user_id=1, legacy_admin=True,
            broker_account_id='admin:kis:KR'), identity=('live', '11112222', '01')))
    closed_rejected = {'pdno': '005930', 'ord_dt': '20261028', 'odno': 'FAKE-1',
        'sll_buy_dvsn_cd': '02', 'ord_qty': '2', 'tot_ccld_qty': '0', 'rmn_qty': '0',
        'rjct_qty': '2', 'cncl_yn': 'Y'}
    filled_sell = {'pdno': '000660', 'ord_dt': '20261028', 'odno': 'FAKE-2',
        'sll_buy_dvsn_cd': '01', 'ord_qty': '3', 'tot_ccld_qty': '3', 'rmn_qty': '0',
        'rjct_qty': '0', 'cncl_yn': 'N'}
    open_buy = {'pdno': '035720', 'ord_dt': '20261028', 'odno': 'FAKE-3',
        'sll_buy_dvsn_cd': '02', 'ord_qty': '1', 'tot_ccld_qty': '0', 'rmn_qty': '1',
        'rjct_qty': '0', 'cncl_yn': 'N'}
    class FakeKisClient:
        def __init__(self): self.calls = []
        def inquire_account_executions_page(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return {'orders': [closed_rejected], 'tr_cont': 'M', 'fk': 'FAKE-FK', 'nk': 'FAKE-NK'}
            return {'orders': [filled_sell, open_buy], 'tr_cont': 'D', 'fk': '', 'nk': ''}
        def list_open_orders(self): return []
        def list_positions(self): return []
    client = FakeKisClient()
    evidence = read_legacy_admin_broker_evidence(db, db.get(OrderLog, 18), NOW, client=client)
    assert evidence['complete'] is True
    assert evidence['execution_filter'] == '00' and evidence['exchange_scope'] == 'ALL'
    assert evidence['history_page_count'] == 2 and len(client.calls) == 2
    assert client.calls[0]['execution_filter'] == '00'
    assert client.calls[0]['older'] is False
    assert client.calls[1]['continuation'] == 'N'
    assert evidence['history_summary']['status_counts'] == {
        'buy': 2, 'canceled': 1, 'filled': 1, 'rejected': 1, 'sell': 1, 'unfilled': 1,
    }
    assert evidence['open_orders_reliable'] and evidence['positions_reliable']


def test_legacy_plan_includes_nearby_analysis_and_timeout_evidence(db_session, monkeypatch):
    db = db_session
    service, _, _, _ = setup(db, monkeypatch)
    db.add(AutomationSchedulerSlot(account_key='admin', provider='kis', profile_id=5,
        slot_key='admin:kis:2026-10-28:11:20', scheduled_at=datetime(2026, 10, 28, 2, 20),
        status='failed', reason='scheduler_task_timeout',
        result_json=json.dumps({'attempt': 1, 'status': 'retry_pending',
            'failure_stage': 'account_snapshot', 'broker_submit_called': False,
            'real_order_submitted': False})))
    db.add(TradeRunLog(owner_user_id=None, run_key='analysis-live-ready',
        trigger_source='automation_profile_scheduler', symbol='036460',
        mode='automation_scheduler_profile_analysis', stage='done', result='LIVE_READY',
        reason='target_aware_risk_approved', created_at=datetime(2026, 10, 28, 2, 22, 58),
        request_payload=json.dumps({'automation_profile_key': PROFILE['profile_key'],
            'broker_submit_called': False, 'real_order_submitted': False}),
        response_payload=json.dumps({'submission_eligible': True})))
    db.commit()
    plan = service.propose(db, order_id=18, admin_user_id=1)
    trace = plan['execution_trace']
    assert trace['nearby_scheduler_slots'][0]['failure_stage'] == 'account_snapshot'
    assert trace['nearby_scheduler_slots'][0]['broker_submit_called'] is False
    assert trace['nearby_profile_analysis_records'][0]['submission_eligible'] is True
    assert plan['historical_submit_call_state'] == 'not_provable_from_legacy_logs'
    assert plan['not_submitted_asserted'] is False


def test_preflight_0840_blocks_before_approval_and_ready_only_after_verified_repair(db_session, monkeypatch):
    db = db_session
    service, broker, _, _ = setup(db, monkeypatch)
    import app.services.admin_preflight_service as preflight_module
    monkeypatch.setattr(preflight_module, 'resolve_position_account_scope', lambda *args, **kwargs: None)
    broker.settings = SimpleNamespace(kis_env='live')
    at_0840 = datetime(2026, 11, 9, 23, 40, tzinfo=UTC)
    before = check_admin_preflight(db, target_date=date(2026, 11, 10), now=at_0840,
        kis_client=broker, scheduler_health={'scheduler_health_status': 'healthy'})
    assert before['status'] == 'BLOCKED'
    assert before['entry_capacity'] == {'max_entries': 1, 'filled_entries': 0,
        'unresolved_entries': 1, 'remaining_entry_capacity': 0}
    assert 'unresolved_entry_limit_hit' in before['reason_codes']
    assert before['schedule'] == ['11:10', '12:20', '13:30']

    plan = service.propose(db, order_id=18, admin_user_id=1)
    service.apply(db, plan=plan, admin_user_id=1,
        approval_digest=plan['approval_digest'], approval_reference='TEST-PREFLIGHT-0840')
    ready = check_admin_preflight(db, target_date=date(2026, 11, 10), now=at_0840,
        kis_client=broker, scheduler_health={'scheduler_health_status': 'healthy'})
    assert ready['status'] == 'READY'
    assert ready['entry_capacity'] == {'max_entries': 1, 'filled_entries': 0,
        'unresolved_entries': 0, 'remaining_entry_capacity': 1}
    assert ready['kis']['positions_reliability'] == 'RELIABLE'
    assert ready['kis']['open_orders_reliability'] == 'RELIABLE'
    assert ready['order_execution_guaranteed'] is False


def test_preflight_unknown_broker_or_scheduler_never_reports_ready(db_session, monkeypatch):
    db = db_session
    _, broker, _, _ = setup(db, monkeypatch)
    import app.services.admin_preflight_service as preflight_module
    monkeypatch.setattr(preflight_module, 'resolve_position_account_scope', lambda *args, **kwargs: None)
    broker.settings = SimpleNamespace(kis_env='live')
    report = check_admin_preflight(db, target_date=date(2026, 11, 9), now=NOW,
        kis_client=broker, scheduler_health=None)
    assert report['status'] == 'BLOCKED'
    assert report['scheduler_health']['status'] == 'unknown'
    assert 'scheduler_health_unavailable' in report['reason_codes']


def test_preflight_blocks_active_exit_retry_and_reports_profile_safety(db_session, monkeypatch):
    db = db_session
    _, broker, _, _ = setup(db, monkeypatch)
    import app.services.admin_preflight_service as preflight_module
    monkeypatch.setattr(preflight_module, 'resolve_position_account_scope', lambda *args, **kwargs: None)
    broker.settings = SimpleNamespace(kis_env='live')
    db.add(PositionExitRetryJob(id=1, exit_cycle_key='admin-exit-retry-1', owner_user_id=1,
        profile_key=PROFILE['profile_key'], scheduler_slot='11:10', symbol='005930',
        provider='kis', market='KR', status='pending', next_retry_at=NOW))
    db.commit()
    report = check_admin_preflight(db, target_date=date(2026, 11, 9), now=NOW,
        kis_client=broker, scheduler_health={'scheduler_health_status': 'healthy'})
    assert report['status'] == 'BLOCKED'
    assert report['active_exit_retries'] == 1
    assert 'position_retry_exit_unresolved' in report['reason_codes']
    assert report['profile_safety_settings'] == {
        'min_entry_score': 65, 'cash_only': True, 'max_positions': 1,
        'no_new_entry_after': '14:00',
    }


def test_preflight_malformed_broker_snapshot_is_not_reliable(db_session, monkeypatch):
    db = db_session
    _, broker, _, _ = setup(db, monkeypatch)
    import app.services.admin_preflight_service as preflight_module
    monkeypatch.setattr(preflight_module, 'resolve_position_account_scope', lambda *args, **kwargs: None)
    broker.settings = SimpleNamespace(kis_env='live')
    broker.list_positions = lambda: [{'symbol': '', 'qty': 'bad'}]
    report = check_admin_preflight(db, target_date=date(2026, 11, 9), now=NOW,
        kis_client=broker, scheduler_health={'scheduler_health_status': 'healthy'})
    assert report['kis']['authentication'] == 'UNKNOWN'
    assert report['kis']['positions_reliability'] == 'UNKNOWN'
    assert 'account_snapshot_unavailable' in report['reason_codes']
    assert report['status'] != 'READY'

