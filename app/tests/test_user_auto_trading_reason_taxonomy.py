from __future__ import annotations

import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.db.models import OrderLog, TradeRunLog, UserAutoTradingSlotClaim
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.automation_profile_service import AutomationProfileService
from app.services.user_auto_trading_scheduler_service import _canonical_preview_score_gate_failure
from app.tests.test_user_auto_trading_scheduler_pr129 import (
    FakeSessionService, _canonical_live_harness, _final_candidate,
    _run_user_scheduler_slot, _set_possible_order, _set_profile_schedule,
)


KST = ZoneInfo("Asia/Seoul")


class SlotSessionService(FakeSessionService):
    def get_session_status(self, market, now=None):
        result = super().get_session_status(market, now=now)
        if now is not None:
            result['local_time'] = now.astimezone(KST).isoformat()
        return result


class RetainedPreview:
    """Fake preview retaining failed rows exactly as the upstream funnel does."""
    def __init__(self, *, filtered, mode, by_slot=None):
        self.filtered = filtered
        self.mode = mode
        self.by_slot = by_slot
        self.calls = []

    def run_preview(self, **kwargs):
        self.calls.append(kwargs)
        snapshot = kwargs['profile_snapshot_context']
        slot = snapshot['scheduler_slot']
        items = [dict(item) for item in (
            self.by_slot[slot] if self.by_slot else kwargs['profile_snapshot_items']
        )]
        for rank, item in enumerate(items, start=1):
            item['runtime_quant_rank'] = rank
            item['gpt_target_rank'] = rank
        symbols = [item['symbol'] for item in items]
        completed = [item for item in items if item['gpt_used'] and item['gpt_analysis_status'] == 'completed']
        finals = [] if self.filtered else sorted(completed, key=lambda item: -item['final_buy_score'])
        for rank, item in enumerate(finals, start=1):
            item.update(final_rank=rank, final_selected=rank == 1)
        return {
            'canonical_profile_pipeline': True,
            'selection_mode': self.mode,
            'items': items,
            'runtime_input_symbols': [item['symbol'] for item in kwargs['profile_snapshot_items']],
            'runtime_quant_candidate_symbols': symbols,
            'runtime_quant_top5_symbols': symbols,
            'gpt_target_symbols': symbols,
            'gpt_completed_symbols': [item['symbol'] for item in completed],
            'final_candidate_symbols': [item['symbol'] for item in finals],
            'selected_final_symbol': finals[0]['symbol'] if finals else None,
            'final_ranked_candidates': finals,
            'final_best_candidate': finals[0] if finals else None,
            'runtime_quant_candidate_count': len(items),
        }


def row(symbol='000001', **fields):
    result = _final_candidate(
        symbol, c_score=76.16, final_score=66.16,
        selected_by_a_top5=True, quant_a_rank=1,
        gpt_used=True, gpt_analysis_status='completed',
        ai_buy_score=64.0, ai_sell_score=36.0,
        indicator_status='ok', data_sufficient=True, hard_blocked=False,
    )
    result.update(fields)
    return result


def harness(db, rows, *, filtered=True, mode=None, by_slot=None):
    scheduler, user, profile, _preview, _account, analysis, broker, kis = _canonical_live_harness(
        db, candidates=rows,
    )
    user.username = 'test01'
    db.commit()
    _set_profile_schedule(db, user, ['11:30', '13:30'])
    preview = RetainedPreview(filtered=filtered, mode=mode, by_slot=by_slot)
    scheduler.candidate_service.runtime_preview_service = preview
    sessions = SlotSessionService()
    scheduler.session_service = sessions
    scheduler.execution_service.session_service = sessions
    return scheduler, user, profile, preview, analysis, broker, kis


def run_and_assert_hold(db, setup, slot, expected, *, score=None):
    scheduler, user, _profile, _preview, analysis, broker, kis = setup
    hour, minute = map(int, slot.split(':'))
    now = datetime(2026, 10, 6, hour, minute, tzinfo=KST).astimezone(UTC)
    item = _run_user_scheduler_slot(db, scheduler, user, slot=slot, now=now)
    claim = db.query(UserAutoTradingSlotClaim).filter_by(user_id=user.id, scheduler_slot=slot).one()
    run = db.get(TradeRunLog, item['run_id'])
    payload = json.loads(run.response_payload)
    assert user.role == 'user'
    assert claim.status == 'completed'
    assert str(claim.result).lower() == str(item['result']).lower() == 'hold'
    assert claim.reason == run.reason == payload['reason'] == item['reason'] == expected
    assert expected not in {'no_completed_gpt_final_candidate', 'no_gpt_completed_execution_candidate'}
    assert payload['primary_block_reason'] == expected
    diagnostic = payload['score_gate_candidate']
    assert diagnostic['skip_reason'] == diagnostic['block_reason'] == expected
    assert diagnostic['required_gpt_buy_score'] == 60
    assert diagnostic['required_final_buy_score'] >= 65
    if score is not None:
        assert diagnostic['gpt_buy_score'] == score
    assert payload['candidate_rejection_summary'][expected] >= 1
    assert payload['pipeline_diagnostics']['primary_block_reason'] == expected
    assert item['broker_submit_called'] is False
    assert item['real_order_submitted'] is False
    assert db.query(OrderLog).count() == 0
    assert broker.buy_calls == kis.buy_calls == kis.possible_order_calls == []
    assert analysis.calls == []
    return item, payload


@pytest.mark.parametrize('slot', ['11:30', '13:30'])
@pytest.mark.parametrize('fields,reason', [
    ({'quant_c_score': 64.99}, 'c_score_below_threshold'),
    ({'gpt_used': False, 'gpt_analysis_status': 'not_run', 'ai_buy_score': None, 'ai_sell_score': None}, 'no_gpt_completed_candidate'),
    ({'gpt_analysis_status': 'failed', 'ai_buy_score': None, 'ai_sell_score': None}, 'gpt_analysis_failed'),
    ({'gpt_analysis_status': 'incomplete', 'ai_buy_score': None, 'ai_sell_score': None}, 'gpt_analysis_incomplete'),
    ({'ai_buy_score': 53.0, 'ai_sell_score': 47.0}, 'gpt_buy_score_below_threshold'),
    ({'final_buy_score': 63.0}, 'below_profile_buy_threshold'),
    ({'data_sufficient': False, 'indicator_status': 'insufficient'}, 'data_quality_blocked'),
])
def test_test01_completed_slots_record_actual_upstream_rejection(db_session, slot, fields, reason):
    setup = harness(db_session, [row(**fields)])
    run_and_assert_hold(db_session, setup, slot, reason)


@pytest.mark.parametrize('slot', ['11:30', '13:30'])
@pytest.mark.parametrize('fields,reason', [
    ({'quant_c_score': 64.99}, 'c_score_below_threshold'),
    ({'ai_buy_score': 53.0, 'ai_sell_score': 47.0}, 'gpt_buy_score_below_threshold'),
    ({'final_buy_score': 63.0}, 'below_profile_buy_threshold'),
    ({'data_sufficient': False, 'indicator_status': 'insufficient'}, 'data_quality_blocked'),
])
def test_test01_fallback_hold_logs_same_actual_gate(db_session, slot, fields, reason):
    setup = harness(db_session, [row(**fields)], filtered=False, mode='A_TOP5_C_GPT')
    run_and_assert_hold(db_session, setup, slot, reason)


@pytest.mark.parametrize('filtered', [True, False])
@pytest.mark.parametrize('reverse', [True, False])
def test_test01_primary_reason_uses_furthest_gate_without_selecting_another_candidate(db_session, filtered, reverse):
    rows = [
        row('000001', ai_buy_score=58.0, ai_sell_score=42.0, final_buy_score=70.0),
        row('000002', ai_buy_score=65.0, ai_sell_score=35.0, final_buy_score=62.0),
    ]
    if reverse:
        rows.reverse()
    setup = harness(db_session, rows, filtered=filtered, mode='A_TOP5_C_GPT')
    item, payload = run_and_assert_hold(db_session, setup, '13:30', 'below_profile_buy_threshold')
    assert payload['score_gate_candidate']['symbol'] == '000002'
    assert payload['candidate_rejection_summary'] == {
        'gpt_buy_score_below_threshold': 1, 'below_profile_buy_threshold': 1,
    }
    if not filtered:
        assert item['candidate']['symbol'] == '000002'


def test_test01_two_completed_claims_preserve_their_own_gate_reason(db_session):
    c_low = row('000001', quant_c_score=64.99)
    gpt_low = row('000002', ai_buy_score=53.0, ai_sell_score=47.0)
    setup = harness(db_session, [c_low, gpt_low], by_slot={'11:30': [c_low], '13:30': [gpt_low]})
    run_and_assert_hold(db_session, setup, '11:30', 'c_score_below_threshold')
    run_and_assert_hold(db_session, setup, '13:30', 'gpt_buy_score_below_threshold', score=53)
    assert db_session.query(UserAutoTradingSlotClaim).filter_by(user_id=setup[1].id, status='completed').count() == 2


def test_valid_boundary_keeps_existing_candidate_selection_and_fake_order(db_session):
    valid = row(quant_c_score=65.0, ai_buy_score=60.0, ai_sell_score=40.0, final_buy_score=65.0)
    setup = harness(db_session, [valid], filtered=False, mode='A_TOP5_C_GPT')
    scheduler, user, _profile, _preview, _analysis, broker, kis = setup
    _set_possible_order(kis, '000001', 1)
    result = _run_user_scheduler_slot(
        db_session, scheduler, user, slot='11:30', now=datetime(2026, 10, 6, 2, 30, tzinfo=UTC),
    )
    assert result['result'] == 'submitted'
    assert result['candidate']['symbol'] == '000001'
    assert kis.buy_calls == [('000001', 1)]
    assert broker.buy_calls == []


def test_diagnostics_keep_profile_threshold_distinct_from_calendar_threshold():
    failure = _canonical_preview_score_gate_failure(
        {'_pipeline_preview': {'items': [row(final_buy_score=69.0)]}},
        selection_mode='A_TOP5_C_GPT', required_final_score=75.0,
        profile={'effective_settings': {'entry': {'min_final_score': 75.0}}},
    )
    assert failure['reason'] == 'below_profile_buy_threshold'
    assert failure['candidate']['required_final_buy_score'] == 75.0
