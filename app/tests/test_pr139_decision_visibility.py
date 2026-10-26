"""Read-only decision visibility, including rejected GPT and old schedule runs."""
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models import AutomationProfileAiCandidateResult, AutomationProfileWatchlistSnapshot, TradeRunLog, User
from app.routes import user_trading
from app.services.automation_today_decision_service import AutomationTodayDecisionService


NOW = datetime(2026, 10, 26, 5, 0, tzinfo=UTC)


def fixture_feed(db):
    owner = User(username='test01', role='user', enabled=True)
    admin = User(username='admin', role='admin', enabled=True)
    db.add_all([owner, admin])
    db.flush()
    profile = {'id': 8, 'profile_key': 'test01-01', 'owner_user_id': owner.id,
               'provider': 'kis', 'market': 'KR'}
    schedule = {'profile': profile, 'status': 'active', 'timezone': 'Asia/Seoul',
                'analysis_times': ['11:30', '12:30', '13:45']}
    profiles = SimpleNamespace(
        selected_owned_profile_schedule=lambda db, **kw: schedule,
        selected_profile_schedule=lambda db, **kw: {
            **schedule, 'profile': {**profile, 'id': 9, 'profile_key': 'admin', 'owner_user_id': admin.id}},
    )
    for slot in ['11:30', '12:30']:
        db.add(AutomationProfileWatchlistSnapshot(
            profile_id=8, owner_user_id=owner.id, provider='kis', market='KR',
            snapshot_date='2026-10-26', scheduler_slot=slot, status='success', generated_at=NOW,
            source_count=200, eligible_count=100, selected_count=50,
        ))
    db.flush()
    snapshot = db.query(AutomationProfileWatchlistSnapshot).filter_by(scheduler_slot='12:30').one()
    c_snapshot = db.query(AutomationProfileWatchlistSnapshot).filter_by(scheduler_slot='11:30').one()
    db.add(AutomationProfileAiCandidateResult(
        owner_user_id=owner.id, profile_id=8, snapshot_id=c_snapshot.id,
        snapshot_date='2026-10-26', scheduler_slot='11:30', symbol='005930',
        runtime_quant_rank=1, runtime_quant_buy_score=64.55,
        gpt_used=False, gpt_analysis_status='not_run',
        diagnostics_json=json.dumps({'candidate_rejections': [{
            'symbol': '005930', 'quant_c_score': 64.55,
            'block_reason': 'c_quant_score_below_threshold',
        }]}),
    ))
    row = AutomationProfileAiCandidateResult(
        owner_user_id=owner.id, profile_id=8, snapshot_id=snapshot.id,
        snapshot_date='2026-10-26', scheduler_slot='12:30', symbol='263750',
        symbol_name='펄어비스', runtime_quant_rank=1, runtime_quant_buy_score=65.35,
        gpt_target_rank=1, gpt_used=True, gpt_analysis_status='completed',
        ai_buy_score=52, ai_sell_score=48, final_buy_score=62.01,
        ai_reason='매수 확신 부족',
        # Legacy row: no candidate_score_gate. Never synthesize final rank.
        diagnostics_json=json.dumps({'candidate_rejections': [{
            'symbol': '263750', 'quant_c_score': 65.35,
            'block_reason': 'gpt_buy_score_below_threshold',
        }]}),
    )
    db.add(row)
    for slot, result, reason in [
        ('11:30', 'HOLD', 'c_quant_score_below_threshold'),
        ('12:30', 'HOLD', 'gpt_buy_score_below_threshold'),
        ('13:30', 'failed', 'user_scheduler_processing_failed'),
    ]:
        db.add(TradeRunLog(
            owner_user_id=owner.id, run_key=f'test01-{slot}', trigger_source='user_scheduler',
            mode='user_scheduler', symbol='NONE', stage='done', result=result, reason=reason,
            created_at=NOW - timedelta(minutes=10),
            request_payload=json.dumps({'profile_id': 8, 'scheduler_slot': slot}),
            response_payload=json.dumps({'failure_stage': 'account_snapshot', 'http_status': 500,
                                         'attempts': 3} if result == 'failed' else {}),
        ))
    db.commit()
    return owner, admin, row, AutomationTodayDecisionService(profiles=profiles)


def test_completed_rejected_gpt_visible_without_final_candidate_and_without_writes(db_session):
    owner, _, _, service = fixture_feed(db_session)
    result = service.get_today(db_session, owner_user_id=owner.id, now=NOW)
    c_hold, gpt_hold, unexecuted = result['slots']
    assert c_hold['status'] == 'analysis_complete'
    assert c_hold['reason'] == 'c_quant_score_below_threshold'
    assert c_hold['gpt_completed_symbols'] == []
    assert c_hold['analysis_candidates'][0]['quant_c_score'] == 64.55
    assert c_hold['analysis_candidates'][0]['gpt_buy_score'] is None
    assert gpt_hold['status'] == 'analysis_complete'
    assert gpt_hold['action'] == 'hold'
    assert gpt_hold['symbol'] == '263750'
    assert gpt_hold['gpt_buy_score'] == 52
    assert gpt_hold['final_buy_score'] == 62.01
    assert gpt_hold['reason'] == 'gpt_buy_score_below_threshold'
    assert gpt_hold['ai_reason'] == '매수 확신 부족'
    assert gpt_hold['score_gate_candidates'] == []
    assert gpt_hold['final_ranked_top5'] == []
    assert gpt_hold['analysis_candidates'][0]['entry_ready'] is False
    assert unexecuted['status'] == 'no_result'
    assert unexecuted['run_id'] is None
    history = result['execution_history']
    assert len(history) == 1
    assert history[0]['scheduler_slot'] == '13:30'
    assert history[0]['status'] == 'failed'
    assert history[0]['failure_stage'] == 'account_snapshot'
    assert history[0]['http_status'] == 500
    assert history[0]['attempts'] == 3
    assert not db_session.new and not db_session.dirty and not db_session.deleted


def test_missing_scores_remain_missing_and_completed_analysis_is_retained(db_session):
    owner, _, row, service = fixture_feed(db_session)
    row.final_buy_score = None
    row.diagnostics_json = '{}'
    db_session.commit()
    slot = service.get_today(db_session, owner_user_id=owner.id, now=NOW)['slots'][1]
    assert slot['gpt_buy_score'] == 52
    assert slot['final_buy_score'] is None
    assert slot['analysis_candidates'][0]['quant_c_score'] is None
    assert slot['reason'] == 'gpt_buy_score_below_threshold'
    assert slot['final_candidate_count'] == 0


def test_owner_profile_and_explicit_slot_filters_precede_run_selection(db_session):
    owner, admin, _, service = fixture_feed(db_session)
    db_session.add(TradeRunLog(
        owner_user_id=owner.id, run_key='other-profile', trigger_source='user_scheduler',
        mode='user_scheduler', symbol='NONE', result='failed', stage='done',
        reason='DO_NOT_EXPOSE', created_at=NOW,
        request_payload=json.dumps({'profile_id': 77, 'scheduler_slot': '12:30'}),
    ))
    db_session.commit()
    regular = service.get_today(db_session, owner_user_id=owner.id, now=NOW)
    assert regular['slots'][1]['symbol'] == '263750'
    administrator = service.get_today(db_session, admin_user_id=admin.id, now=NOW)
    assert all(slot['run_id'] is None for slot in administrator['slots'])
    assert administrator['execution_history'] == []
    assert '263750' not in json.dumps(administrator)
    assert 'DO_NOT_EXPOSE' not in json.dumps(regular)


def test_user_today_route_returns_completed_hold_analysis(db_session, monkeypatch):
    owner, _, _, service = fixture_feed(db_session)
    class FixedTodayService:
        def get_today(self, db, *, owner_user_id, now):
            return service.get_today(db, owner_user_id=owner_user_id, now=NOW)
    monkeypatch.setattr(user_trading, 'AutomationTodayDecisionService', FixedTodayService)
    app = FastAPI()
    app.include_router(user_trading.router)
    app.dependency_overrides[user_trading.get_db] = lambda: db_session
    app.dependency_overrides[user_trading.require_regular_user] = lambda: owner
    with TestClient(app) as client:
        response = client.get('/users/me/trading/ai-decisions/today')
    assert response.status_code == 200
    slot = response.json()['slots'][1]
    assert (slot['symbol'], slot['gpt_buy_score'], slot['final_buy_score']) == ('263750', 52, 62.01)
    assert slot['final_ranked_top5'] == []


def test_profile_context_alone_does_not_imply_completed_analysis(db_session):
    owner, _, _, service = fixture_feed(db_session)
    db_session.add(TradeRunLog(
        owner_user_id=owner.id, run_key='not-analyzed', trigger_source='user_scheduler',
        mode='user_scheduler', symbol='NONE', result='SKIPPED', stage='done',
        reason='market_closed', created_at=NOW,
        request_payload=json.dumps({'profile_id': 8, 'scheduler_slot': '13:45'}),
    ))
    db_session.commit()
    slot = service.get_today(db_session, owner_user_id=owner.id, now=NOW)['slots'][2]
    assert slot['status'] != 'analysis_complete'
    assert slot['gpt_completed_count'] == 0
    assert slot['analysis_candidates'] == []
