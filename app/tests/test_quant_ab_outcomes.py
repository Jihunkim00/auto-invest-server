from datetime import datetime
from zoneinfo import ZoneInfo

from app.db.models import QuantABObservation, QuantABOutcome
from app.services.quant_ab_evaluation_service import QuantABEvaluationService
from app.services.quant_ab_outcome_label_service import (
    QuantABOutcomeLabelService,
    calculate_next_decision_slots,
    evaluate_virtual_trade,
)

KST = ZoneInfo("Asia/Seoul")


class FakeSession:
    def is_trading_day(self, market, value):
        return value.weekday() < 5


class FakeMarketData:
    def __init__(self, bars):
        self.bars = bars
        self.calls = []

    def get_intraday_bars(self, symbol, **kwargs):
        self.calls.append((symbol, kwargs["as_of"].date()))
        return [bar for bar in self.bars if bar["timestamp"].startswith(kwargs["as_of"].date().isoformat())], {
            "validation_status": "ok"
        }


def _bar(at, close, *, high=None, low=None):
    return {
        "timestamp": at.isoformat(),
        "open": close,
        "high": high if high is not None else close,
        "low": low if low is not None else close,
        "close": close,
        "volume": 1,
    }


def _observation(db, *, symbol="005930", observed_at=None, cohort="cohort-1", a_rank=1, b_rank=1):
    row = QuantABObservation(
        observation_key=f"{cohort}:{symbol}",
        run_key=cohort,
        experiment_cohort_key=cohort,
        trigger_source="test",
        provider="kis",
        market="KR",
        symbol=symbol,
        observed_at=observed_at or datetime(2026, 9, 4, 9, 10, tzinfo=KST),
        decision_slot="2026-09-04T09:10:00+09:00",
        current_price=100.0,
        a_rank=a_rank,
        b_rank_within_shadow_pool=b_rank,
        b_entry_score=80.0,
        confidence_b=0.9,
        data_quality_b=1.0,
        outcome_status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _service(bars):
    return QuantABOutcomeLabelService(
        market_data_snapshot_service=FakeMarketData(bars),
        session_service=FakeSession(),
        analysis_times=["09:10", "11:30", "13:30"],
    )


def test_next_three_slots_skip_weekend():
    slots = calculate_next_decision_slots(
        datetime(2026, 9, 4, 13, 30, tzinfo=KST),
        analysis_times=["09:10", "11:30", "13:30"],
        trading_day_fn=lambda value: value.weekday() < 5,
    )
    assert [value.isoformat() for value in slots] == [
        "2026-09-07T09:10:00+09:00",
        "2026-09-07T11:30:00+09:00",
        "2026-09-07T13:30:00+09:00",
    ]


def test_not_mature_stays_pending(db_session):
    observed = datetime(2026, 9, 4, 9, 10, tzinfo=KST)
    row = _observation(db_session, observed_at=observed)
    result = _service([]).label_mature_observations(
        db_session, now=datetime(2026, 9, 4, 13, 31, tzinfo=KST)
    )
    assert result["performance"]["outcomes_pending"] == 1
    assert db_session.get(QuantABObservation, row.id).outcome_status == "pending"


def test_complete_tp_before_sl_and_returns(db_session):
    observed = datetime(2026, 9, 4, 9, 10, tzinfo=KST)
    bars = [
        _bar(datetime(2026, 9, 4, 9, 11, tzinfo=KST), 100, high=101, low=99),
        _bar(datetime(2026, 9, 4, 9, 12, tzinfo=KST), 100, high=105, low=99),
        _bar(datetime(2026, 9, 4, 11, 30, tzinfo=KST), 101),
        _bar(datetime(2026, 9, 4, 13, 30, tzinfo=KST), 102),
        _bar(datetime(2026, 9, 7, 9, 10, tzinfo=KST), 103),
    ]
    row = _observation(db_session, observed_at=observed)
    service = _service(bars)
    result = service.label_mature_observations(
        db_session, now=datetime(2026, 9, 7, 13, 31, tzinfo=KST)
    )
    saved = db_session.query(QuantABOutcome).one()
    assert result["performance"]["outcomes_labeled"] == 1
    assert saved.outcome_status == "complete"
    assert saved.first_barrier_hit == "take_profit"
    assert saved.simulated_return_pct == 5.0
    assert saved.return_next_slot_pct == 1.0
    assert saved.return_second_slot_pct == 2.0
    assert saved.return_third_slot_pct == 3.0
    assert saved.max_favorable_excursion_pct == 5.0
    assert row.outcome_status == "complete"
    again = service.label_mature_observations(
        db_session, now=datetime(2026, 9, 7, 13, 31, tzinfo=KST)
    )
    assert again["count"] == 0


def test_same_bar_uses_conservative_sl_first():
    observed = datetime(2026, 9, 4, 9, 10, tzinfo=KST)
    result = evaluate_virtual_trade(
        [_bar(datetime(2026, 9, 4, 9, 11, tzinfo=KST), 100, high=106, low=97)],
        observed_at=observed,
        horizon_end=datetime(2026, 9, 4, 11, 30, tzinfo=KST),
        horizon_slots=[datetime(2026, 9, 4, 11, 30, tzinfo=KST)],
        entry_price=100,
    )
    assert result["first_barrier_hit"] == "stop_loss"
    assert result["simulated_exit_reason"] == "stop_loss_same_bar_conservative"
    assert result["simulated_return_pct"] == -2.0
    assert result["tp_hit"] is True and result["sl_hit"] is True


def test_future_bar_after_horizon_is_ignored():
    observed = datetime(2026, 9, 4, 9, 10, tzinfo=KST)
    result = evaluate_virtual_trade(
        [_bar(datetime(2026, 9, 4, 11, 31, tzinfo=KST), 100, high=110, low=99)],
        observed_at=observed,
        horizon_end=datetime(2026, 9, 4, 11, 30, tzinfo=KST),
        horizon_slots=[datetime(2026, 9, 4, 11, 30, tzinfo=KST)],
        entry_price=100,
    )
    assert result["first_barrier_hit"] is None
    assert result["tp_hit"] is False


def test_evaluation_extracts_a_and_b_winners(db_session):
    first = _observation(db_session, symbol="AAA", cohort="cohort-eval", a_rank=1, b_rank=2)
    second = _observation(db_session, symbol="BBB", cohort="cohort-eval", a_rank=2, b_rank=1)

    for row, value in ((first, 1.0), (second, 4.0)):
        db_session.add(QuantABOutcome(
            observation_id=row.id,
            cohort_key="cohort-eval",
            symbol=row.symbol,
            outcome_status="complete",
            data_quality=1.0,
            simulated_return_pct=value,
            max_favorable_excursion_pct=value,
            max_adverse_excursion_pct=-1.0,
            tp_hit=value > 3,
            sl_hit=False,
        ))
    db_session.commit()
    summary = QuantABEvaluationService().summary(db_session)
    assert summary["evaluated_cohort_count"] == 1
    assert summary["a"]["avg_return"] == 1.0
    assert summary["b"]["avg_return"] == 4.0
    assert summary["difference"]["b_wins_count"] == 1
