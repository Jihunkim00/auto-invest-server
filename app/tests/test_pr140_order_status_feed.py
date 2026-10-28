import json
from types import SimpleNamespace

import pytest

from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.services.automation_today_decision_service import AutomationTodayDecisionService
from app.tests.test_automation_today_decision_service_pr129 import NOW, _profile, _run, _snapshot, _user


@pytest.mark.parametrize('status, broker_id, response, expected', [
    ('REJECTED_BY_SAFETY_GATE', None, {'broker_submit_called': False}, 'NOT SUBMITTED'),
    ('REQUESTED', None, {}, 'SYNC REQUIRED'),
    ('UNKNOWN_STALE', None, {'broker_submit_called': True}, 'SYNC REQUIRED'),
    ('SUBMITTED', 'FAKE-ACK', {'broker_submit_called': True}, 'BROKER SUBMITTED'),
    ('FILLED', 'FAKE-FILL', {'broker_submit_called': True}, 'FILLED'),
])
def test_admin_and_test01_order_status_is_scoped_and_independent_of_ai(db_session, status, broker_id, response, expected):
    admin = _user(db_session, 'admin')
    admin.role = 'admin'
    test_user = _user(db_session, 'test01')
    admin_profile = _profile(db_session, admin.id, 'status-admin')
    user_profile = _profile(db_session, test_user.id, 'status-test01')
    for owner, profile in [(admin, admin_profile), (test_user, user_profile)]:
        _snapshot(db_session, profile, owner.id, '11:30', '036460')
        _run(db_session, owner.id, '11:30', '036460', NOW)
    run = db_session.query(TradeRunLog).filter_by(owner_user_id=admin.id).one()
    run.trigger_source = 'automation_scheduler'
    run.mode = 'automation_scheduler_profile_analysis'
    run.result = 'LIVE_READY'
    signal = db_session.get(SignalLog, run.signal_id)
    signal.action = 'buy'
    signal.signal_status = 'would_buy'
    signal.approved_by_risk = True
    db_session.add(OrderLog(owner_user_id=None, broker='kis', market='KR', symbol='036460',
        side='buy', order_type='market', qty=7, internal_status=status,
        broker_order_id=broker_id, filled_qty=7 if status == 'FILLED' else None,
        request_payload=json.dumps({'automation_profile_key': admin_profile['profile_key'], 'scheduler_slot': '11:30'}),
        response_payload=json.dumps(response), created_at=NOW,
        error_message='scheduler_task_expired_before_buy' if expected == 'NOT SUBMITTED' else None))
    # Newer foreign order IDs must never replace the admin's order evidence.
    db_session.add(OrderLog(owner_user_id=test_user.id, broker='kis', market='KR', symbol='036460',
        side='buy', order_type='market', qty=1, filled_qty=1, internal_status='FILLED',
        request_payload=json.dumps({'sizing': {'profile_id': user_profile['id']}, 'scheduler_slot': '11:30'}),
        created_at=NOW))
    db_session.commit()
    schedules = SimpleNamespace(
        selected_profile_schedule=lambda db, now: {'profile': admin_profile, 'timezone': 'Asia/Seoul', 'analysis_times': ['11:30']},
        selected_owned_profile_schedule=lambda db, owner_user_id, now: {'profile': user_profile, 'timezone': 'Asia/Seoul', 'analysis_times': ['11:30']},
    )
    feed = AutomationTodayDecisionService(profiles=schedules)
    admin_slot = feed.get_today(db_session, admin_user_id=admin.id, now=NOW)['slots'][0]
    user_slot = feed.get_today(db_session, owner_user_id=test_user.id, now=NOW)['slots'][0]
    assert admin_slot['ai_decision'] == 'BUY APPROVED'
    assert admin_slot['order_status'] == expected
    assert user_slot['order_status'] == 'FILLED'
    assert user_slot['order_id'] != admin_slot['order_id']
    if expected == 'NOT SUBMITTED':
        assert admin_slot['order_block_reason'] == 'scheduler_task_expired_before_buy'


def test_inspection_cannot_modify_order_or_reservation(db_session, tmp_path):
    import sqlite3
    from app.scripts.inspect_kis_unsubmitted_order import inspect_order
    path = tmp_path / 'inspection.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE orders(id INTEGER PRIMARY KEY, internal_status TEXT, response_payload TEXT)')
        conn.execute("INSERT INTO orders VALUES(18, 'REQUESTED', NULL)")
    before = path.read_bytes()
    result = inspect_order(path, 18)
    assert result['order']['internal_status'] == 'REQUESTED'
    assert result['order']['submission_evidence']['broker_submit_called'] is None
    assert result['db_modified'] is False
    assert path.read_bytes() == before
