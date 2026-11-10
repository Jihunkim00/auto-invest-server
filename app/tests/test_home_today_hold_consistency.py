"""Presentation-only regression: a completed HOLD is not a position block."""
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db.database import get_db
from app.db.models import AutomationSchedulerSlot, TradeRunLog, User, OrderLog
from app.routes.history import router
from app.services.auth_service import create_session
from app.services.automation_today_decision_service import AutomationTodayDecisionService
from app.services.kis_order_reconciliation_service import fingerprint

NOW = datetime(2026, 11, 10, 6, 20, tzinfo=UTC)
REASON = 'no_gpt_completed_execution_candidate'
PROFILE = {'id': 5, 'owner_user_id': 1, 'profile_key': 'admin-kis', 'provider': 'kis', 'market': 'KR'}


def test_today_watchlist_hold_survives_old_position_block_and_raw_blocked_ledger(db_session):
    db = db_session
    schedule = {'profile': PROFILE, 'analysis_times': ['11:10', '12:20', '13:30'], 'timezone': 'Asia/Seoul'}
    service = AutomationTodayDecisionService(profiles=SimpleNamespace(selected_profile_schedule=lambda *a, **kw: schedule))
    for run_id, day, owner, profile, reason in [
        (1, 9, None, 5, 'position_retry_exit_unresolved'),
        (2, 10, None, 5, REASON),
        (3, 10, 1, 5, REASON),
        (4, 10, 2, 8, 'position_state_refresh_pending'),
        (5, 10, 1, 9, 'position_state_refresh_pending'),
    ]:
        db.add(TradeRunLog(id=run_id, run_key=f'presentation-{run_id}', owner_user_id=owner,
            trigger_source='automation_scheduler', mode='automation_scheduler_profile_analysis',
            stage='done', symbol='WATCHLIST', result='hold' if reason == REASON else 'blocked', reason=reason,
            created_at=datetime(2026, 11, day, 4, 31, run_id),
            request_payload=json.dumps({'profile_id': profile, 'scheduler_slot': '13:30'}),
            response_payload=json.dumps({'action': 'hold', 'reason': reason,
                'risk_flags': ['position_retry_exit_unresolved'], 'gating_notes': ['old_position_flag']})))
    db.add(AutomationSchedulerSlot(slot_key='admin:kis:2026-11-10:13:30', account_key='admin',
        provider='kis', profile_id=5, status='blocked', reason=REASON,
        scheduled_at=datetime(2026, 11, 10, 4, 30), finished_at=datetime(2026, 11, 10, 4, 32)))
    db.commit()
    slot = service.get_today(db, admin_user_id=1, now=NOW)['slots'][-1]
    assert (slot['status'], slot['action'], slot['reason']) == ('analysis_complete', 'hold', REASON)
    assert slot['run_id'] == 3
    assert slot['created_at_kst'] == '2026-11-10T13:31:03+09:00'
    assert slot['scheduled_at'] == '2026-11-10T04:30:00+00:00'
    assert slot['scheduler_status'] == 'blocked'  # Preserve the ledger's original result.
    assert 'risk_flags' not in slot and 'gating_notes' not in slot
    assert not db.new and not db.dirty and not db.deleted


@pytest.mark.parametrize('reason,status', [
    ('position_state_refresh_pending', 'retry_pending'),
    ('position_retry_exit_unresolved', 'blocked'),
    ('account_snapshot_unavailable', 'failed'),
])
def test_real_position_failures_remain_visible(db_session, reason, status):
    db = db_session
    db.add(AutomationSchedulerSlot(slot_key='admin:kis:2026-11-10:13:30', account_key='admin',
        provider='kis', profile_id=5, status=status, reason=reason,
        scheduled_at=NOW.replace(tzinfo=None), finished_at=NOW.replace(tzinfo=None)))
    db.commit()
    result = AutomationTodayDecisionService._with_scheduler_outcome(db,
        {'scheduler_slot': '13:30', 'status': 'analysis_complete', 'reason': REASON},
        profile=PROFILE, owner_user_id=None, local_date=date(2026, 11, 10))
    assert result['status'] == status and result['reason'] == reason


def test_newer_same_slot_analysis_supersedes_old_scheduler_failure(db_session):
    db = db_session
    db.add(AutomationSchedulerSlot(slot_key='admin:kis:2026-11-10:13:30', account_key='admin',
        provider='kis', profile_id=5, status='failed', reason='scheduler_task_timeout',
        scheduled_at=NOW.replace(tzinfo=None) - timedelta(minutes=10),
        finished_at=NOW.replace(tzinfo=None) - timedelta(minutes=5)))
    db.commit()
    result = AutomationTodayDecisionService._with_scheduler_outcome(db,
        {'scheduler_slot': '13:30', 'status': 'analysis_complete', 'action': 'hold',
         'reason': REASON, 'created_at': NOW.isoformat()},
        profile=PROFILE, owner_user_id=None, local_date=date(2026, 11, 10))
    assert result['status'] == 'analysis_complete' and result['reason'] == REASON
    assert result['execution_reason'] == 'scheduler_task_timeout'
    assert result['scheduler_outcome_applied'] is False


def test_nov10_operating_clone_authenticated_http_returns_latest_hold(monkeypatch):
    raw = os.environ.get('AUTO_INVEST_HOME_DIAGNOSTIC_CLONE')
    if not raw:
        pytest.skip('provide the read-only operating clone for the real-data HTTP replay')
    source = Path(raw).resolve()
    before = sha256(source.read_bytes()).hexdigest()
    memory = sqlite3.connect(':memory:', check_same_thread=False)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as original:
        original.backup(memory)
    engine = create_engine('sqlite://', poolclass=StaticPool, creator=lambda: memory)
    try:
        with Session(engine) as db:
            originals = {key: fingerprint(db.get(OrderLog, key)) for key in (13, 18, 19)}
            assert db.get(OrderLog, 18).internal_status == 'LEGACY_ABSENCE_VERIFIED'
            token = create_session(db, db.get(User, 1))
        app = FastAPI()
        app.include_router(router)
        def clone_db():
            with Session(engine) as db:
                yield db
        app.dependency_overrides[get_db] = clone_db
        import app.routes.history as history
        class FixedTimeService(AutomationTodayDecisionService):
            def get_today(self, db, **kwargs):
                return super().get_today(db, now=NOW, **kwargs)
        monkeypatch.setattr(history, 'AutomationTodayDecisionService', FixedTimeService)
        with TestClient(app) as client:
            assert client.get('/runs/automation/ai-decisions/today').status_code == 401
            client.cookies.set(get_settings().session_cookie_name, token)
            response = client.get('/runs/automation/ai-decisions/today')
        assert response.status_code == 200
        payload = response.json()
        assert payload['profile_id'] == 5 and payload['owner_user_id'] == 1
        assert [slot['run_id'] for slot in payload['slots']] == [340, 344, 347]
        assert all(slot['reason'] == REASON and slot['action'] == 'hold'
                   and slot['status'] == 'analysis_complete' for slot in payload['slots'])
        with Session(engine) as db:
            assert all(fingerprint(db.get(OrderLog, key)) == value for key, value in originals.items())
    finally:
        engine.dispose()
    assert sha256(source.read_bytes()).hexdigest() == before
