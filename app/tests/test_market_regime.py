from __future__ import annotations

import inspect
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import MarketRegimeSnapshot
from app.services.scheduler_service import scheduler_service as _scheduler_service
from app.services.automation_scheduler_service import (
    AutomationSchedulerService,
    market_regime_scheduler_due,
)
from app.services.market_regime_service import (
    MarketMetric,
    PairedWeek,
    MarketRegimeService,
    advance_regime_state,
    build_market_metrics,
    calculate_momentum_score,
    calculate_rsi_score,
    calculate_trend_score,
    combine_market_scores,
    normalize,
    pair_market_metrics,
)

KST = ZoneInfo("Asia/Seoul")
LATEST_FRIDAY = date(2026, 9, 25)


def _bars(count=210, *, end=LATEST_FRIDAY, flat=False):
    rows = []
    for i in range(count):
        week = end - timedelta(weeks=count - i - 1)
        close = 100.0 if flat else 100.0 + i * 0.4
        rows.append({
            "week_ending": week.isoformat(),
            "open": close - 0.4,
            "high": close + (0 if flat else 2.0),
            "low": close - (0 if flat else 2.0),
            "close": close,
            "volume": 1000,
        })
    return rows


class FakeMarketDataProvider:
    def __init__(self, *, count=210, extra_kospi=None, extra_nasdaq=None):
        self.calls = 0
        self.kospi = _bars(count) + list(extra_kospi or [])
        self.nasdaq = _bars(count) + list(extra_nasdaq or [])

    def fetch_weekly_bars(self, *, as_of):
        self.calls += 1
        return {
            "kospi": list(self.kospi),
            "nasdaq": list(self.nasdaq),
            "data_source": {
                "kospi": {"provider": "fake", "symbol": "^KS11"},
                "nasdaq": {"provider": "fake", "symbol": "^IXIC", "is_proxy": False},
                "nasdaq_is_proxy": False,
            },
        }


def _metric(week, score=60.0, *, close=110.0, ema20=100.0, ema40=95.0,
            slope=1.0, histogram=1.0, rsi=60.0, atr=10.0, drawdown=0.0):
    return MarketMetric(
        week_ending=week, close=close, ema20=ema20, ema40=ema40,
        ema20_4w_slope=slope, macd_histogram=histogram, rsi14=rsi,
        atr14=atr, trend_score=score, momentum_score=score, rsi_score=score,
        market_score=score, drawdown_52w=drawdown,
    )


def _bull_week(week):
    k, n = _metric(week, 60), _metric(week, 70)
    return PairedWeek(week, k, n, 60, 70, 64, 5, 60)


def _bear_week(week):
    k = _metric(week, 30, close=80, ema20=100, ema40=90,
                histogram=-1, drawdown=20)
    n = _metric(week, 30, close=80, ema20=100, ema40=90,
                histogram=-1, drawdown=20)
    return PairedWeek(week, k, n, 30, 30, 30, -5, 40)


def test_normalize_clips_values():
    assert normalize(-100) == 0
    assert normalize(0) == 50
    assert normalize(100) == 100
    assert normalize(float("nan")) is None


def test_trend_score_formula_and_invalid_inputs():
    assert calculate_trend_score(104, 102, 100, 99, 2) == pytest.approx(82.5)
    assert calculate_trend_score(104, 102, 100, 99, 0) is None
    assert calculate_trend_score(None, 102, 100, 99, 2) is None


def test_momentum_and_rsi_score_formulas():
    assert calculate_momentum_score(1, 0, 2) == pytest.approx(90)
    assert calculate_momentum_score(1, 0, 0) is None
    assert calculate_rsi_score(70) == 100
    assert calculate_rsi_score(30) == 0
    assert calculate_rsi_score(float("nan")) is None


def test_combined_score_uses_sixty_forty_weights():
    assert combine_market_scores(56.70, 67.37) == pytest.approx(60.968)


def test_pair_scores_include_three_completed_week_delta():
    weeks = [date(2026, 1, 2) + timedelta(weeks=i) for i in range(4)]
    kospi = [_metric(w, 50 + 5 * i) for i, w in enumerate(weeks)]
    nasdaq = [_metric(w, 50) for w in weeks]
    paired = pair_market_metrics(kospi, nasdaq)
    assert paired[-1].combined_score == pytest.approx(59)
    assert paired[-1].score_change_3w == pytest.approx(9)
    assert paired[-1].nasdaq_score_3w_ago == pytest.approx(50)


def test_52_week_kospi_drawdown_is_calculated_from_trailing_closes():
    rows = _bars(60, end=LATEST_FRIDAY, flat=True)
    rows[-1].update(open=80, high=82, low=78, close=80)
    metrics = build_market_metrics(rows)
    assert metrics[-1].drawdown_52w == pytest.approx(20.0)


def test_nasdaq_100_fallback_is_labeled_as_a_proxy(monkeypatch):
    from app.services.market_regime_provider import YahooFinanceMarketRegimeProvider

    provider = YahooFinanceMarketRegimeProvider()
    bars = _bars(205)

    def fake_fetch(symbol, start, end):
        if symbol == "^KS11":
            return bars, "Asia/Seoul", None
        if symbol == "^IXIC":
            return [], None, "index_unavailable"
        return bars, "America/New_York", None

    monkeypatch.setattr(provider, "_fetch_chart", fake_fetch)
    result = provider.fetch_weekly_bars(as_of=datetime(2026, 9, 26, 8, tzinfo=KST))
    assert result["data_source"]["nasdaq"]["symbol"] == "QQQ"
    assert result["data_source"]["nasdaq"]["label"] == "NASDAQ-100 proxy (QQQ)"
    assert result["data_source"]["nasdaq"]["is_proxy"] is True
    assert result["data_source"]["nasdaq_is_proxy"] is True


def test_insufficient_history_never_returns_a_regime_or_score(db_session):
    provider = FakeMarketDataProvider(count=100)
    row = MarketRegimeService(provider).calculate_and_persist(
        db_session, now=datetime(2026, 9, 26, 8, tzinfo=KST)
    )
    assert row.status == "insufficient_data"
    assert row.stage is None
    assert row.combined_score is None


def test_flat_bars_with_zero_atr_are_rejected():
    rows = _bars(210, flat=True)
    assert build_market_metrics(rows) == []


def test_bullish_confirmation_needs_two_consecutive_completed_weeks():
    first = advance_regime_state(1, _bull_week(date(2026, 9, 18)))
    assert first["stage"] == 1
    assert first["bullish_streak"] == 1
    assert first["new_bullish_reversal"] is False

    second = advance_regime_state(
        first["stage"], _bull_week(date(2026, 9, 25)),
        bullish_streak=first["bullish_streak"],
    )
    assert second["stage"] == 3
    assert second["new_bullish_reversal"] is True
    assert second["bullish_conditions"]["confirmed"] is True


def test_bearish_confirmation_needs_two_consecutive_completed_weeks():
    first = advance_regime_state(4, _bear_week(date(2026, 9, 18)))
    assert first["stage"] == 4
    assert first["bearish_streak"] == 1

    second = advance_regime_state(
        first["stage"], _bear_week(date(2026, 9, 25)),
        bearish_streak=first["bearish_streak"],
    )
    assert second["stage"] == 6
    assert second["new_bearish_reversal"] is True
    assert second["bearish_conditions"]["confirmed"] is True


def test_bullish_event_does_not_repeat_through_stages_four_and_five():
    week = date(2026, 9, 25)
    mixed_k = _metric(week, 50, close=110, ema20=100, ema40=95, slope=1)
    mixed_n = _metric(week, 50)
    mixed = PairedWeek(week, mixed_k, mixed_n, 50, 50, 50, -5, 50)
    into_topping = advance_regime_state(4, mixed)
    assert into_topping["stage"] == 5
    assert into_topping["new_bullish_reversal"] is False
    while_topping = advance_regime_state(5, mixed)
    assert while_topping["stage"] == 5
    assert while_topping["new_bullish_reversal"] is False


def test_bullish_event_is_only_on_stage_three_entry_and_can_rearm():
    second = advance_regime_state(
        1, _bull_week(date(2026, 9, 25)), bullish_streak=1
    )
    assert second["new_bullish_reversal"] is True

    continuing = advance_regime_state(3, _bull_week(date(2026, 10, 2)))
    assert continuing["stage"] == 4
    assert continuing["new_bullish_reversal"] is False

    returned_to_falling = advance_regime_state(6, _bear_week(date(2026, 10, 9)))
    assert returned_to_falling["stage"] == 1
    first_again = advance_regime_state(1, _bull_week(date(2026, 10, 16)))
    second_again = advance_regime_state(
        1, _bull_week(date(2026, 10, 23)),
        bullish_streak=first_again["bullish_streak"],
    )
    assert second_again["stage"] == 3
    assert second_again["new_bullish_reversal"] is True


def test_week_is_confirmed_only_after_both_exchange_closes():
    from app.services.market_regime_service import completed_weekly_bars

    bar = _bars(1)[0]
    bar["week_ending"] = "2026-09-25"
    before = datetime(2026, 9, 25, 8, tzinfo=KST)
    after = datetime(2026, 9, 26, 8, tzinfo=KST)
    assert completed_weekly_bars([bar], market="KOSPI", as_of=before) == []
    assert len(completed_weekly_bars([bar], market="KOSPI", as_of=after)) == 1
    assert len(completed_weekly_bars([bar], market="NASDAQ", as_of=after)) == 1


def test_incomplete_current_week_does_not_change_confirmed_regime(db_session):
    provider = FakeMarketDataProvider()
    service = MarketRegimeService(provider)
    first = service.calculate_and_persist(db_session, now=datetime(2026, 9, 26, 8, tzinfo=KST))
    assert first.confirmed is True

    partial = {
        "week_ending": "2026-10-02", "open": 184, "high": 187,
        "low": 183, "close": 186, "volume": 100,
    }
    provider.kospi.append(partial)
    provider.nasdaq.append(partial)
    next_day = service.calculate_and_persist(db_session, now=datetime(2026, 9, 27, 8, tzinfo=KST))
    assert next_day.stage == first.stage
    assert next_day.state_week_ending == first.state_week_ending
    assert next_day.new_bullish_reversal is False


def test_daily_calculation_is_idempotent_and_persisted(db_session):
    provider = FakeMarketDataProvider()
    service = MarketRegimeService(provider)
    now = datetime(2026, 9, 26, 8, tzinfo=KST)
    first = service.calculate_and_persist(db_session, now=now)
    second = service.calculate_and_persist(db_session, now=now.replace(minute=10))
    assert first.id == second.id
    assert provider.calls == 1
    assert db_session.query(MarketRegimeSnapshot).count() == 1


def test_scheduler_due_time_is_explicitly_asia_seoul_0800():
    assert market_regime_scheduler_due(datetime(2026, 9, 30, 22, 59, tzinfo=UTC)) is False
    assert market_regime_scheduler_due(datetime(2026, 9, 30, 23, 0, tzinfo=UTC)) is True
    with pytest.raises(ValueError):
        market_regime_scheduler_due(datetime(2026, 9, 30, 8, 0))


def test_current_endpoint_returns_the_persisted_snapshot(db_session):
    provider = FakeMarketDataProvider()
    MarketRegimeService(provider).calculate_and_persist(
        db_session, now=datetime(2026, 9, 26, 8, tzinfo=KST)
    )
    from app.main import app

    def override_db():
        yield db_session

    prior_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/market-regime/current")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(prior_overrides)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "confirmed"
    assert payload["stage"] in range(1, 7)
    assert payload["market_score"] == pytest.approx(
        0.6 * payload["kospi_score"] + 0.4 * payload["nasdaq_score"]
    )
    assert payload["data_source"]["nasdaq_is_proxy"] is False


def test_market_regime_path_has_no_order_submission_access():
    from app.routes import market_regime as route
    from app.services import market_regime_provider as provider
    from app.services import market_regime_service as service

    source_files = (Path(inspect.getfile(route)), Path(inspect.getfile(provider)), Path(inspect.getfile(service)))
    forbidden = ("KisClient", "KisManualOrderService", "submit_order", "submit_market_buy", "submit_market_sell")
    for file in source_files:
        source = file.read_text(encoding="utf-8")
        assert not any(token in source for token in forbidden), str(file)

    scheduler_method = inspect.getsource(AutomationSchedulerService._run_market_regime_scheduled_once)
    assert not any(token in scheduler_method for token in forbidden)
