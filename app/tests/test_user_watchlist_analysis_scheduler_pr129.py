from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import (
    OrderLog,
    SignalLog,
    User,
    UserWatchlist,
    UserWatchlistAnalysis,
)
from app.services.user_watchlist_analysis_scheduler_service import (
    USER_WATCHLIST_ANALYSIS_TRIGGER_SOURCE,
    UserWatchlistAnalysisSchedulerService,
)


RUN_AT = datetime(2026, 9, 11, 0, 30, tzinfo=UTC)


class FakeAnalysisService:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def analyze(self, _db, *, provider, symbol, gate_level, now):
        self.calls.append((provider, symbol))
        return {
            'symbol': symbol,
            'action': 'watch',
            'reason': 'analysis_only_fake',
            'quant_buy_score': 71.0,
            'quant_sell_score': 19.0,
            'ai_buy_score': 70.0,
            'ai_sell_score': 20.0,
            'final_buy_score': 70.5,
            'final_sell_score': 19.5,
            'confidence': 0.77,
            'indicator_payload': {'source': 'fake'},
        }


def _user(db, username: str) -> User:
    row = User(username=username, role='user', enabled=True, setup_completed=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_personal_watchlist_analysis_is_stored_owner_scoped_and_never_trades(db_session):
    first = _user(db_session, 'pr129-favorite-a')
    second = _user(db_session, 'pr129-favorite-b')
    db_session.add_all([
        UserWatchlist(user_id=first.id, symbol='005930', provider='kis', market='KR'),
        UserWatchlist(user_id=second.id, symbol='000660', provider='kis', market='KR'),
    ])
    db_session.commit()
    analysis = FakeAnalysisService()
    scheduler = UserWatchlistAnalysisSchedulerService(analysis_service=analysis)

    result = scheduler.run_once(db_session, scheduler_slot='09:30', now=RUN_AT)

    assert result['trigger_source'] == USER_WATCHLIST_ANALYSIS_TRIGGER_SOURCE
    assert result['analytics_only'] is True
    assert result['stored'] == 2
    assert result['risk_approval_called'] is False
    assert result['broker_submit_called'] is False
    assert analysis.calls == [('kis', '005930'), ('kis', '000660')]
    first_row = db_session.query(UserWatchlistAnalysis).filter_by(user_id=first.id).one()
    second_row = db_session.query(UserWatchlistAnalysis).filter_by(user_id=second.id).one()
    assert first_row.symbol == '005930'
    assert second_row.symbol == '000660'
    assert first_row.final_buy_score == 70.5
    assert second_row.indicator_payload == '{"source": "fake"}'
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(SignalLog).count() == 0


def test_favorite_analysis_slots_are_idempotent_per_owner_symbol_and_slot(db_session):
    user = _user(db_session, 'pr129-favorite-idempotent')
    db_session.add(UserWatchlist(user_id=user.id, symbol='005930', provider='kis', market='KR'))
    db_session.commit()
    analysis = FakeAnalysisService()
    scheduler = UserWatchlistAnalysisSchedulerService(analysis_service=analysis)

    scheduler.run_once(db_session, scheduler_slot='12:00', now=RUN_AT)
    scheduler.run_once(db_session, scheduler_slot='12:00', now=RUN_AT)

    assert db_session.query(UserWatchlistAnalysis).filter_by(user_id=user.id).count() == 1
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(SignalLog).count() == 0