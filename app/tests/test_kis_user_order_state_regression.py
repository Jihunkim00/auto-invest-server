"""October 21 failure reconstruction; raw incident response is unavailable."""
from datetime import UTC, datetime
import json

import pytest

from app.db.models import AutomationSchedulerSlot, OrderLog, PositionLifecycle
from app.services.user_broker_account_service import _normalize_kis_snapshot, _normalize_kis_order
from app.services.scheduler_slot_dispatcher import SchedulerSlotDispatcher
from app.tests.test_kis_duplicate_account_scope import accounts, _order
from app.tests.test_user_auto_trading_scheduler_pr129 import (
    _user, _harness, _retry_user_setup,
)

NOW = datetime(2026, 10, 21, 2, 30, tzinfo=UTC)


def snapshot(user, rows):
    return {**_normalize_kis_snapshot({'output1': [], 'output2': {}}, {'output': rows}),
            'owner_user_id': user.id, 'provider': 'kis', 'market': 'KR', 'environment': 'live',
            'connected': True, 'broker_account_id': f'user:{user.id}:kis:KR'}


@pytest.mark.parametrize('row,expected', [
    (None, 'entry_scan'),
    ({'ord_qty': '2', 'tot_ccld_qty': '2', 'psbl_qty': '0'}, 'entry_scan'),
    ({'ord_qty': '2', 'tot_ccld_qty': '0', 'psbl_qty': '0', 'cncl_yn': 'Y'}, 'entry_scan'),
    ({'ord_qty': '2', 'psbl_qty': '0', 'status': 'cancelled'}, 'entry_scan'),
    ({'ord_qty': '2', 'rmn_qty': '0'}, 'entry_scan'),
    ({'ord_qty': '2'}, 'order_status_unverified'),
    ({'ord_qty': '2', 'psbl_qty': '0'}, 'order_status_unverified'),
    ({'ord_qty': '2', 'psbl_qty': '2', 'tot_ccld_qty': '0'}, 'broker_active_sell_order'),
    ({'ord_qty': '2', 'psbl_qty': '1', 'tot_ccld_qty': '1'}, 'broker_active_sell_order'),
    ({'ord_qty': '2', 'psbl_qty': 'NaN'}, 'order_status_unverified'),
    ({'ord_qty': '2', 'psbl_qty': '-1'}, 'order_status_unverified'),
])
@pytest.mark.parametrize('held', [False, True])
def test_broker_sell_state_uses_quantities_not_missing_status(db_session, row, expected, held):
    user = _user(db_session, 'test01')
    scheduler, *_ = _harness()
    rows = [] if row is None else [{'odno': 'sensitive-order-1234', 'pdno': '005930',
                                    'sll_buy_dvsn_cd': '01', **row}]
    data = snapshot(user, rows)
    if held:
        data['positions'] = [{'symbol': '005930', 'quantity': 2, 'avg_price': 100, 'current_price': 100}]
    result = scheduler._manage_positions(db_session, user=user, provider='kis', snapshot=data,
                                        now=NOW, scheduler_slot='11:30')
    if expected == 'entry_scan':
        assert result['action'] == ('hold' if held else 'entry_scan')
        assert result['reason'] in {'no_open_position', 'no_exit_condition'}
    else:
        assert result['reason'] == expected
        assert result['entry_blocked'] is True
        assert result['entry_analysis_started'] is False
        assert result['account_scope_verified'] is True
        assert result['broker_order_id_masked'] == '***1234'
        assert 'sensitive-order-' not in json.dumps(result)


@pytest.mark.parametrize('slot', ['11:30', '13:30'])
def test_empty_test01_false_duplicate_before_and_after(db_session, slot):
    raw = {'odno': 'past-order', 'pdno': '005930', 'sll_buy_dvsn_cd': '01',
           'ord_qty': '2', 'tot_ccld_qty': '2', 'psbl_qty': '0'}
    # Exact pre-fix decisions: absent status became pending; the scheduler
    # ignored remaining_quantity and blocked every non-terminal SELL.
    old_status = raw.get('status') or 'pending'
    old_blocked = raw['sll_buy_dvsn_cd'] == '01' and old_status.upper() not in {
        'FILLED', 'CANCELED', 'CANCELLED', 'REJECTED', 'EXPIRED'}
    assert old_blocked
    user = _user(db_session, 'test01')
    scheduler, *_ = _harness()
    result = scheduler._manage_positions(db_session, user=user, provider='kis',
        snapshot=snapshot(user, [raw]), now=NOW, scheduler_slot=slot)
    assert result['action'] == 'entry_scan'
    assert result['entry_blocked'] is False
    assert result['next_stage'] == 'profile_watchlist'


def test_fill_quantity_is_not_inferred_from_cancel_capacity():
    order = _normalize_kis_order({'ord_qty': '10', 'tot_ccld_qty': '2', 'psbl_qty': '0',
                                'cncl_yn': 'Y', 'sll_buy_dvsn_cd': '02'})
    assert order['filled_quantity'] == 2
    assert order['side'] == 'buy'
    assert order['status'] == 'canceled'


@pytest.mark.parametrize('missing', ['odno', 'pdno'])
def test_native_active_buy_without_identity_is_not_a_reliable_order(db_session, missing):
    user = _user(db_session, 'test01')
    raw = {'odno': 'fake-buy', 'pdno': '005930', 'sll_buy_dvsn_cd': '02',
           'ord_qty': '2', 'tot_ccld_qty': '0', 'psbl_qty': '2'}
    raw.pop(missing)
    data = snapshot(user, [raw])
    assert data['open_orders_reliable'] is False
    scheduler, *_ = _harness()
    result = scheduler._manage_positions(db_session, user=user, provider='kis', snapshot=data,
                                        now=NOW, scheduler_slot='11:30')
    assert result['reason'] == 'order_status_unverified'
    assert result['entry_blocked'] is True


@pytest.mark.parametrize('failures', [1, 2, 3])
def test_retry_final_result_updates_same_ledger_without_replay(db_session, monkeypatch, failures):
    user, scheduler, _account, _analysis, _broker, _client, retries, clock, calls = (
        _retry_user_setup(db_session, monkeypatch, failures=failures))
    scheduler.candidate_service = lambda *args, **kwargs: None  # Recovered snapshot, final HOLD.
    key = f'user-{user.id}:kis:{clock[0].date().isoformat()}:09:10'
    ledger = AutomationSchedulerSlot(slot_key=key, account_key=f'user-{user.id}', provider='kis',
        scheduled_at=clock[0].replace(tzinfo=None), started_at=clock[0].replace(tzinfo=None), status='running')
    db_session.add(ledger)
    db_session.commit()
    result = scheduler.run_provider_once(db_session, provider='kis', scheduler_slot='09:10', now=clock[0])
    assert SchedulerSlotDispatcher._outcome(result)[0] == 'retry_pending'
    ledger.status = 'retry_pending'
    db_session.commit()
    while retries.pending:
        retries.run_next(clock)
    db_session.expire_all()
    assert calls['count'] == min(failures + 1, 3)
    final = json.loads(ledger.result_json)
    assert ledger.status == SchedulerSlotDispatcher._outcome(final)[0]
    assert ledger.status != 'retry_pending'
    assert (ledger.status == 'failed') == (failures == 3)
    assert ledger.status == ('failed' if failures == 3 else 'HOLD')
    assert len((final.get('account_snapshot_retry') or final)['attempt_history']) == calls['count']


def test_unknown_open_orders_fail_closed(db_session):
    user = _user(db_session, 'test01')
    scheduler, *_ = _harness()
    data = snapshot(user, [])
    data['open_orders_reliable'] = False
    result = scheduler._manage_positions(db_session, user=user, provider='kis', snapshot=data,
                                        now=NOW, scheduler_slot='11:30')
    assert result['reason'] == 'open_orders_snapshot_unavailable'


def test_actual_local_unresolved_sell_is_preserved_and_not_broker_duplicate(db_session, accounts):
    _admin, first, second, _credentials = accounts
    order = _order(db_session, owner=first.id, side='sell', status='UNKNOWN_STALE')
    scheduler, *_ = _harness()
    result = scheduler._manage_positions(db_session, user=first, provider='kis', snapshot=snapshot(first, []),
                                        now=NOW, scheduler_slot='11:30')
    assert result['reason'] == 'local_unresolved_sell_order'
    assert result['duplicate_check_source'] == 'local_order_log'
    assert result['local_order_id'] == order.id
    assert result['order_status'] == 'UNKNOWN_STALE'
    db_session.refresh(order)
    assert order.internal_status == 'UNKNOWN_STALE'
    assert order.sync_error == 'kis_order_not_found_in_inquiry'
    other = scheduler._manage_positions(db_session, user=second, provider='kis', snapshot=snapshot(second, []),
                                       now=NOW, scheduler_slot='11:30')
    assert other['action'] == 'entry_scan'
