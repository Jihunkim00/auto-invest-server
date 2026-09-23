from __future__ import annotations

import json
from datetime import UTC, datetime

from app.db.models import (
    WatchlistSnapshotItem,
    WatchlistSnapshotRun,
    AutomationProfileWatchlistItem,
    AutomationProfileWatchlistSnapshot,
    SignalLog,
    TradeRunLog,
    User,
)
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.automation_profile_service import AutomationProfileService
from app.services.automation_profile_watchlist_service import AutomationProfileWatchlistService
from app.services.automation_today_decision_service import AutomationTodayDecisionService


NOW = datetime(2026, 9, 16, 5, 0, tzinfo=UTC)


def _user(db, username: str) -> User:
    row = User(
        username=username,
        role='user',
        enabled=True,
        setup_completed=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _profile(db, owner_id: int, key: str) -> dict:
    service = AutomationProfileService()
    result = service.create(
        db,
        AutomationProfileWriteRequest(
            profile_key=key,
            name=key,
            provider='kis',
            market='KR',
            capital={
                'fixed_budget': 50000,
                'initial_budget_krw': 50000,
                'max_order_notional_krw': 50000,
            },
            universe={
                'watchlist_size': 50,
                'min_price_krw': 1,
                'max_price_krw': 500000,
                'top_quant_candidates': 10,
                'top_ai_candidates': 5,
            },
            entry={'analysis_times': ['09:10', '11:30', '13:30']},
            operation={'start_date': '2026-09-01', 'end_date': '2026-09-30'},
        ),
        owner_user_id=owner_id,
    )
    service.activate(db, str(result['id']), owner_user_id=owner_id)
    return result


def _snapshot(db, profile: dict, owner_id: int, slot: str, symbol: str) -> None:
    snapshot = AutomationProfileWatchlistSnapshot(
        profile_id=profile['id'],
        owner_user_id=owner_id,
        provider='kis',
        market='KR',
        snapshot_date='2026-09-16',
        scheduler_slot=slot,
        generated_at=NOW,
        source_count=200,
        eligible_count=100,
        selected_count=50,
        effective_entry_budget_krw=50000,
        effective_max_candidate_price=50000,
        status='success',
    )
    db.add(snapshot)
    db.flush()
    db.add(AutomationProfileWatchlistItem(
        snapshot_id=snapshot.id,
        symbol=symbol,
        name='스냅샷 이름',
        market='KOSPI',
        current_price=10000,
        quant_buy_score=80,
        quant_sell_score=10,
        rank=1,
        quant_rank=1,
        ai_rank=1,
        eligible=True,
        indicators_json='{}',
    ))
    db.commit()


def _run(db, owner_id: int, slot: str, symbol: str, created_at: datetime) -> None:
    run = TradeRunLog(
        owner_user_id=owner_id,
        run_key=f'test-{owner_id}-{slot}',
        trigger_source='user_scheduler',
        symbol=symbol,
        mode='user_scheduler',
        stage='done',
        result='hold',
        reason='hold',
        created_at=created_at,
        request_payload=json.dumps({
            'provider': 'kis',
            'market': 'KR',
            'scheduler_slot': slot,
        }),
        response_payload=json.dumps({
            'provider': 'kis',
            'market': 'KR',
            'returned_symbol': symbol,
            'scheduler_slot': slot,
            'analysis': {
                'final_buy_score': 66,
                'final_sell_score': 12,
                'confidence': 0.8,
                'reason': 'snapshot reason',
                'ai_reason': 'AI snapshot reason',
            },
        }),
    )
    db.add(run)
    db.flush()
    signal = SignalLog(
        owner_user_id=owner_id,
        symbol=symbol,
        action='hold',
        final_buy_score=66,
        final_sell_score=12,
        confidence=0.8,
        reason='snapshot reason',
        ai_reason='AI snapshot reason',
        signal_status='hold',
        trigger_source='user_scheduler',
        timeframe=slot,
        created_at=created_at,
    )
    db.add(signal)
    db.flush()
    run.signal_id = signal.id
    db.commit()



def test_profile_candidate_flow_is_top50_then_db_configured_top10_to_top5(db_session):
    owner = _user(db_session, 'pipeline-owner')
    profile = _profile(db_session, owner.id, 'pipeline-profile')
    raw = WatchlistSnapshotRun(
        market='KR',
        started_at=NOW,
        completed_at=NOW,
        status='success',
    )
    db_session.add(raw)
    db_session.commit()
    db_session.add_all([
        WatchlistSnapshotItem(
            run_id=raw.id,
            symbol=f'{index:06d}',
            name=f'Candidate {index}',
            market='KOSPI',
            current_price=10000 + index,
            quant_buy_score=100 - index,
            quant_sell_score=index,
            indicators_json='{}',
            captured_at=NOW,
        )
        for index in range(1, 13)
    ])
    db_session.commit()

    from app.services.user_auto_trading_scheduler_service import (
        UserAutoTradingCandidateService,
    )
    candidates = UserAutoTradingCandidateService().select_candidates(
        db_session,
        user=owner,
        provider='kis',
        profile=profile,
        scheduler_slot='11:30',
        now=NOW,
    )

    assert len(candidates) == 5
    assert [item['symbol'] for item in candidates] == [
        '000001', '000002', '000003', '000004', '000005',
    ]
    assert [item['quant_rank'] for item in candidates] == [1, 2, 3, 4, 5]
    assert [item['ai_rank'] for item in candidates] == [1, 2, 3, 4, 5]
    snapshot = AutomationProfileWatchlistService().latest(
        db_session,
        profile_id=profile['id'],
        owner_user_id=owner.id,
    )['snapshot']
    assert snapshot['selected_count'] == 12
    assert snapshot['effective_entry_budget_krw'] == 50000
def test_today_decisions_are_exact_owner_profile_slot_scoped_and_kst(db_session):
    owner = _user(db_session, 'today-owner')
    other = _user(db_session, 'today-other')
    profile = _profile(db_session, owner.id, 'today-owner-profile')
    other_profile = _profile(db_session, other.id, 'today-other-profile')

    _snapshot(db_session, profile, owner.id, '09:10', '010170')
    _snapshot(db_session, profile, owner.id, '11:30', '010170')
    _snapshot(db_session, profile, owner.id, '13:30', '010170')
    _snapshot(db_session, other_profile, other.id, '11:30', '005930')

    _run(db_session, owner.id, '11:30', '010170', NOW)
    _run(db_session, other.id, '11:30', '005930', NOW)
    _run(
        db_session,
        owner.id,
        '13:30',
        '010170',
        datetime(2026, 9, 15, 5, 0, tzinfo=UTC),
    )
    _run(db_session, owner.id, '09:10', 'NONE', NOW)

    result = AutomationTodayDecisionService().get_today(
        db_session,
        owner_user_id=owner.id,
        now=NOW,
    )

    assert result['profile_id'] == profile['id']
    assert result['owner_user_id'] == owner.id
    assert [slot['scheduler_slot'] for slot in result['slots']] == [
        '09:10', '11:30', '13:30',
    ]
    assert result['slots'][0]['status'] == 'analysis_complete'
    assert result['slots'][0]['action'] == 'hold'
    assert result['slots'][0]['reason'] == 'no_completed_gpt_final_candidate'
    assert result['slots'][0]['snapshot_selected_count'] == 50
    assert result['slots'][0]['symbol'] is None
    assert result['slots'][1]['symbol'] == '010170'
    assert result['slots'][1]['symbol_name'] == '스냅샷 이름'
    assert result['slots'][1]['created_at_kst'] == '2026-09-16T14:00:00+09:00'
    assert result['slots'][2]['status'] == 'no_result'
    assert all(slot['symbol'] != '005930' for slot in result['slots'])
