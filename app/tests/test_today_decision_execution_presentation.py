"""Read-only home response projection; never runs the scheduler or a broker."""
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from app.db.models import (
    AutomationProfileAiCandidateResult, AutomationProfileBuyReservation,
    AutomationProfileWatchlistItem, AutomationProfileWatchlistSnapshot,
    AutomationSchedulerSlot, OrderLog, SignalLog, TradeRunLog,
)
from app.services.automation_today_decision_service import AutomationTodayDecisionService


NOW = datetime(2026, 11, 13, 2, 12, tzinfo=UTC)
PROFILE = dict(id=5, owner_user_id=1, profile_key='admin-kis', provider='kis', market='KR')
REASON = 'calendar_gap_c_below_threshold'


def _ledger(db, *, account='admin', day='2026-11-13', slot='11:10', profile=5, payload=None):
    row = AutomationSchedulerSlot(
        slot_key=f'{account}:kis:{day}:{slot}', account_key=account, provider='kis',
        profile_id=profile, status='blocked', reason=REASON,
        scheduled_at=NOW.replace(tzinfo=None) - timedelta(minutes=2),
        finished_at=NOW.replace(tzinfo=None), result_json=json.dumps(payload or {}))
    db.add(row)
    db.commit()
    return row


def _payload():
    return dict(result='blocked', reason=REASON, profile_buy=dict(
        status='blocked', reason=REASON, broker_submit_called=False, real_order_submitted=False,
        calendar_gap_risk=dict(pre_market_closure_risk=True, required_c_score=75.0, required_final_score=70.0),
        calendar_gap_candidate_diagnostics=[dict(symbol='012750', quant_c_score=74.94,
            quant_c_threshold=65.0, final_buy_score=72.45, skip_reason=REASON)]))


def test_esone_today_response_preserves_analysis_and_adds_canonical_buy_evidence(db_session, monkeypatch):
    db = db_session
    snapshot = AutomationProfileWatchlistSnapshot(profile_id=5, owner_user_id=1,
        provider='kis', market='KR', snapshot_date='2026-11-13', scheduler_slot='11:10', generated_at=NOW)
    db.add(snapshot)
    db.flush()
    db.add(AutomationProfileWatchlistItem(snapshot_id=snapshot.id, symbol='012750', name='에스원',
        market='KOSPI', rank=1, quant_rank=1, ai_rank=1))
    signal = SignalLog(symbol='012750', owner_user_id=1, action='would_buy',
        signal_status='would_buy', reason='target_aware_risk_approved', final_buy_score=72.45)
    db.add(signal)
    db.flush()
    run = TradeRunLog(run_key='analysis-esone', owner_user_id=1,
        trigger_source='automation_scheduler', mode='automation_scheduler_profile_analysis',
        stage='done', symbol='012750', result='LIVE_READY', reason='target_aware_risk_approved', signal_id=signal.id,
        created_at=NOW.replace(tzinfo=None) - timedelta(minutes=1),
        request_payload=json.dumps(dict(profile_id=5, scheduler_slot='11:10')),
        response_payload=json.dumps(dict(action='buy', reason='target_aware_risk_approved', final_buy_score=72.45)))
    db.add(run)
    db.flush()
    db.add(AutomationProfileAiCandidateResult(profile_id=5, owner_user_id=1, snapshot_id=snapshot.id,
        run_id=run.id, snapshot_date='2026-11-13', scheduler_slot='11:10', symbol='012750', symbol_name='에스원',
        runtime_quant_rank=1, runtime_quant_buy_score=62, gpt_target_rank=1, gpt_used=True,
        gpt_analysis_status='completed', ai_buy_score=65.0, ai_sell_score=10, final_buy_score=72.45,
        final_rank=1, final_selected=True, diagnostics_json=json.dumps(dict(candidate_score_gate=dict(quant_c_score=74.94)))))
    _ledger(db, payload=_payload())
    # Other accounts, profiles, dates, and slots must not provide these diagnostics.
    _ledger(db, account='user-2', profile=8, payload={'real_order_submitted': True})
    _ledger(db, day='2026-11-12', payload={'real_order_submitted': True})
    _ledger(db, slot='12:20', profile=9, payload={'real_order_submitted': True})
    schedule = dict(profile=PROFILE, analysis_times=['11:10', '12:20'], timezone='Asia/Seoul')
    service = AutomationTodayDecisionService(profiles=SimpleNamespace(selected_profile_schedule=lambda *a, **kw: schedule))
    before = [(row.id, row.result_json) for row in db.query(AutomationSchedulerSlot).all()]
    response = service.get_today(db, admin_user_id=1, now=NOW)
    slot, upcoming = response['slots']
    assert slot['analysis_execution_status'] == 'LIVE_READY'
    assert slot['analysis_reason'] == 'target_aware_risk_approved'
    assert slot['scheduler_status'] == slot['execution_status'] == 'blocked'
    assert slot['execution_reason'] == REASON
    assert slot['calendar_gap_risk']['required_c_score'] == 75.0
    assert slot['calendar_gap_candidate_diagnostics'][0]['quant_c_score'] == 74.94
    assert slot['analysis_candidates'][0]['quant_buy_score'] == 62
    assert slot['broker_submit_called'] is False and slot['real_order_submitted'] is False
    assert 'calendar_gap_risk' not in upcoming
    assert db.query(OrderLog).count() == db.query(AutomationProfileBuyReservation).count() == 0
    assert not db.new and not db.dirty and not db.deleted
    assert before == [(row.id, row.result_json) for row in db.query(AutomationSchedulerSlot).all()]
    # Exercise the actual read-only HTTP endpoint and its JSON serialization.
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import app.routes.history as history
    from app.db.database import get_db

    class FixedService:
        def get_today(self, session, **kwargs):
            return service.get_today(session, now=NOW, **kwargs)

    monkeypatch.setattr(history, 'AutomationTodayDecisionService', FixedService)
    app = FastAPI()
    app.include_router(history.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[history.require_admin_or_uninitialized_legacy_access] = lambda: SimpleNamespace(id=1)
    with TestClient(app) as client:
        result = client.get('/runs/automation/ai-decisions/today')
    assert result.status_code == 200 and result.json() == response
    assert not db.new and not db.dirty and not db.deleted


def test_stale_scheduler_diagnostics_are_not_applied_to_a_newer_analysis(db_session):
    _ledger(db_session, payload=_payload())
    result = AutomationTodayDecisionService._with_scheduler_outcome(db_session,
        dict(scheduler_slot='11:10', status='result', signal_status='LIVE_READY',
             reason='new_analysis', created_at=(NOW + timedelta(seconds=1)).isoformat()),
        profile=PROFILE, owner_user_id=None, local_date=date(2026, 11, 13))
    assert result['scheduler_outcome_applied'] is False
    assert 'calendar_gap_risk' not in result and 'execution_status' not in result


def test_exit_submission_flags_do_not_become_buy_submission_flags(db_session):
    payload = _payload()
    payload.update(broker_submit_called=True, real_order_submitted=True)
    _ledger(db_session, payload=payload)
    result = AutomationTodayDecisionService._with_scheduler_outcome(db_session,
        dict(scheduler_slot='11:10', status='result'), profile=PROFILE,
        owner_user_id=None, local_date=date(2026, 11, 13))
    assert result['broker_submit_called'] is result['real_order_submitted'] is False


def test_regular_user_wrapper_projects_only_its_own_buy_result(db_session):
    payload = _payload()
    _ledger(db_session, account='user-2', profile=8,
        payload={'items': [dict(user_id=1, real_order_submitted=True), dict(user_id=2, **payload)]})
    result = AutomationTodayDecisionService._with_scheduler_outcome(db_session,
        dict(scheduler_slot='11:10', status='result'), profile={**PROFILE, 'id': 8},
        owner_user_id=2, local_date=date(2026, 11, 13))
    assert result['real_order_submitted'] is False


def test_user_exit_submission_is_not_buy_submission_evidence(db_session):
    _ledger(db_session, account='user-2', profile=8,
        payload={'items': [dict(user_id=2, action='sell', result='submitted',
            broker_submit_called=True, real_order_submitted=True)]})
    result = AutomationTodayDecisionService._with_scheduler_outcome(db_session,
        dict(scheduler_slot='11:10', status='result'), profile={**PROFILE, 'id': 8},
        owner_user_id=2, local_date=date(2026, 11, 13))
    assert 'real_order_submitted' not in result
    assert 'broker_submit_called' not in result
    assert result['execution_status'] is None
