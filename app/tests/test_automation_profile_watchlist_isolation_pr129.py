from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import (
    AutomationProfileWatchlistSnapshot,
    User,
    UserWatchlist,
    WatchlistSnapshotItem,
    WatchlistSnapshotRun,
)
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.automation_profile_service import AutomationProfileService
from app.services.automation_profile_watchlist_service import AutomationProfileWatchlistService


NOW = datetime(2026, 9, 11, 1, 10, tzinfo=UTC)


def _user(db, username):
    row = User(username=username, role='user', enabled=True, setup_completed=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _profile(db, *, owner_user_id, key, max_price, budget):
    return AutomationProfileService().create(
        db,
        AutomationProfileWriteRequest(
            profile_key=key,
            name=key,
            provider='kis',
            market='KR',
            capital={
                'initial_budget_krw': budget,
                'fixed_budget': budget,
                'max_order_notional_krw': budget,
            },
            universe={
                'watchlist_size': 5,
                'min_price_krw': 1,
                'max_price_krw': max_price,
                'top_quant_candidates': 2,
                'top_ai_candidates': 1,
            },
            operation={'start_date': '2026-08-01', 'end_date': '2026-12-31'},
        ),
        owner_user_id=owner_user_id,
    )


def _raw_snapshot(db):
    run = WatchlistSnapshotRun(
        market='KR', started_at=NOW, completed_at=NOW, status='success',
    )
    db.add(run)
    db.commit()
    db.add_all([
        WatchlistSnapshotItem(
            run_id=run.id, symbol='000001', name='Affordable', market='KOSPI',
            current_price=100.0, quant_buy_score=70.0, quant_sell_score=20.0,
            indicators_json='{"volume_ratio": 2}', captured_at=NOW,
        ),
        WatchlistSnapshotItem(
            run_id=run.id, symbol='000002', name='Expensive best', market='KOSPI',
            current_price=700.0, quant_buy_score=95.0, quant_sell_score=5.0,
            indicators_json='{"volume_ratio": 2}', captured_at=NOW,
        ),
        WatchlistSnapshotItem(
            run_id=run.id, symbol='000003', name='ETF excluded', market='KOSPI',
            current_price=50.0, quant_buy_score=99.0, quant_sell_score=1.0,
            indicators_json='{}', captured_at=NOW,
        ),
    ])
    db.commit()
    return run


def test_ranked_snapshot_is_profile_and_owner_scoped_with_profile_budget_filter(db_session):
    owner = _user(db_session, 'snapshot-owner')
    other_owner = _user(db_session, 'snapshot-other-owner')
    cheap = _profile(db_session, owner_user_id=owner.id, key='snapshot-cheap', max_price=900, budget=150)
    broad = _profile(db_session, owner_user_id=owner.id, key='snapshot-broad', max_price=900, budget=800)
    other = _profile(db_session, owner_user_id=other_owner.id, key='snapshot-other', max_price=900, budget=800)
    system = _profile(db_session, owner_user_id=None, key='snapshot-system', max_price=900, budget=800)
    raw = _raw_snapshot(db_session)
    db_session.add(UserWatchlist(
        user_id=owner.id, symbol='FAVORITEONLY', provider='kis', market='KR',
    ))
    db_session.commit()

    service = AutomationProfileWatchlistService()
    cheap_snapshot = service.build(
        db_session, profile=cheap, owner_user_id=owner.id, scheduler_slot='09:10', now=NOW,
    )
    broad_snapshot = service.build(
        db_session, profile=broad, owner_user_id=owner.id, scheduler_slot='09:10', now=NOW,
    )
    other_snapshot = service.build(
        db_session, profile=other, owner_user_id=other_owner.id, scheduler_slot='09:10', now=NOW,
    )
    system_snapshot = service.build(
        db_session, profile=system, owner_user_id=None, scheduler_slot='09:10', now=NOW,
    )

    assert cheap_snapshot['snapshot']['source_run_id'] == raw.id
    assert broad_snapshot['snapshot']['source_run_id'] == raw.id
    assert cheap_snapshot['snapshot']['id'] != broad_snapshot['snapshot']['id']
    assert cheap_snapshot['snapshot']['effective_max_candidate_price'] == 150
    assert [item['symbol'] for item in cheap_snapshot['items']] == ['000001']
    assert [item['symbol'] for item in broad_snapshot['items']][:2] == ['000002', '000001']
    assert broad_snapshot['items'][0]['quant_rank'] == 1
    assert broad_snapshot['items'][0]['ai_rank'] == 1
    assert 'FAVORITEONLY' not in {item['symbol'] for item in broad_snapshot['items']}
    assert other_snapshot['snapshot']['owner_user_id'] == other_owner.id
    assert system_snapshot['snapshot']['owner_user_id'] is None
    assert system_snapshot['snapshot']['profile_id'] == system['id']
    assert service.latest(
        db_session, profile_id=cheap['id'], owner_user_id=other_owner.id,
    ) == {'snapshot': None, 'items': []}
    assert db_session.query(AutomationProfileWatchlistSnapshot).count() == 4