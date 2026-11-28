from __future__ import annotations

import copy
import json
import threading
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db.models import CompanyEvent, KisGptShadowObservation, QuantABObservation
from app.schemas.kis_gpt_shadow import KisGptAnalysisSettings
from app.scripts.export_quant_abc_logs import read_rows, v2_comparisons
from app.services.kis_corporate_event_service import corporate_context, dividend_events
from app.services.kis_gpt_shadow_outcomes import evaluate_horizon
from app.services.kis_gpt_shadow_service import (
    WEIGHTS, KisGptShadowWorker, ShadowSnapshot, latest_shadow_results, schedule_snapshot, score_judgments,
)
from app.services.kis_watchlist_preview_service import KisGptPreview, KisWatchlistPreviewService
from app.services.kis_stop_loss_aware_feature_service import (
    KST, MINUTE, adjusted_daily, aligned_returns, build_features, completed_frames, minute_bars,
)
from app.services.reversal_quant_service import ReversalQuantService

DECISION = datetime(2026, 10, 29, 11, 30, tzinfo=KST)
OPEN = DECISION.replace(hour=9, minute=0)
CLOSE = DECISION.replace(hour=15, minute=30)


def _profile():
    return {
        "id": 18, "owner_user_id": 11, "updated_at": "2026-10-28T00:00:00Z", "status": "active",
        "effective_settings": {
            "exit": {"stop_loss_pct": -2, "take_profit_pct": 3,
                     "stop_loss_enabled": True, "take_profit_enabled": True},
            "entry": {"analysis_times": ["11:30", "12:00", "13:30"]},
            "gpt_analysis": {"gpt_short_horizon_minutes": 17, "gpt_long_horizon_minutes": 51},
        },
    }


def _schedule(profile=None):
    return schedule_snapshot(profile or _profile(), DECISION, "11:30", {},
                             user_scheduled=True)


def _bar(at, price=100, *, high=None, low=None, close=None, volume=10):
    return {"timestamp": at.isoformat(), "open": price, "high": high if high is not None else price + 1,
            "low": low if low is not None else price - 1,
            "close": close if close is not None else price, "volume": volume}


def _minute_rows():
    return [_bar(OPEN + i * MINUTE, 100 + i * .02, close=100.3 + i * .02) for i in range(155)]


def _daily_rows():
    return [_bar(OPEN - i * timedelta(days=1), 150 - i * .1) for i in range(60, 0, -1)]


def _judgment(short=80, long=70):
    return {
        horizon: {"component_scores": dict.fromkeys(WEIGHTS, value), "price_action_supported": True,
                  "stop_loss_risk_level": "low", "corporate_event_risk_level": "medium"}
        for horizon, value in (("short", short), ("long", long))
    } | {"gpt_reason_v2": "단기와 장기 반등 근거를 비교했습니다."}


@pytest.fixture
def isolated_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'pr144.db').as_posix()}")
    for model in (CompanyEvent, QuantABObservation, KisGptShadowObservation):
        model.__table__.create(engine)
    yield engine, sessionmaker(bind=engine)
    engine.dispose()


def test_schedule_snapshots_effective_profile_units_and_ranges():
    profile = _profile()
    schedule = _schedule(profile)
    profile["effective_settings"]["exit"].update(stop_loss_pct=4, take_profit_enabled=False)
    assert schedule["effective_stop_loss_pct"] == .02
    assert schedule["effective_take_profit_pct"] == .03
    assert schedule["gpt_short_horizon_minutes"] == 17
    assert schedule["gpt_long_horizon_minutes"] == 51
    assert schedule["next_position_management_at"] == DECISION.replace(hour=12, minute=0).isoformat()
    assert schedule["profile_id"] == 18 and schedule["profile_version"]
    assert _schedule(profile)["effective_stop_loss_pct"] == .04
    assert _schedule(profile)["take_profit_enabled"] is False
    for bad in ({"gpt_short_horizon_minutes": 0}, {"gpt_short_horizon_minutes": 60},
                {"gpt_scoring_mode": "v2"}, {"gpt_long_horizon_minutes": "90"},
                {"gpt_event_lookahead_days": 31}):
        with pytest.raises(ValidationError):
            KisGptAnalysisSettings.model_validate(bad)


def test_completed_candles_c_versions_and_risk_features():
    rows = _minute_rows()
    completed = minute_bars(rows, OPEN, DECISION)
    assert len(completed) == 150 and max(completed) == DECISION - MINUTE
    frames = completed_frames(completed, OPEN)
    assert {frame: len(bars) for frame, bars in frames.items()} == {5: 30, 10: 15, 15: 10, 30: 5, 60: 2}
    incomplete = minute_bars(rows[:1] + rows[2:], OPEN, DECISION)
    assert len(completed_frames(incomplete, OPEN)[10]) == 14
    service = ReversalQuantService()
    legacy = service.score(current_price=104, daily_bars=_daily_rows(), intraday_bars=rows,
                           decision_timestamp=DECISION)
    experimental = service.score_experimental(current_price=104, daily_bars=_daily_rows(),
                                              frames=frames, decision_timestamp=DECISION)
    assert legacy["c_score_version"] == "c-15m30m-v1"
    assert experimental["c_score_version"] == "c-10m30m-v2"
    assert "15m" in legacy["indicator_snapshot"] and "10m" in experimental["indicator_snapshot"]
    evidence = build_features(minute=completed, frames=frames, daily=_daily_rows(), entry=104,
                              entry_source="estimated", schedule=_schedule(), session_open=OPEN)
    assert evidence["stop_loss_price"] == pytest.approx(101.92)
    assert evidence["take_profit_price"] == pytest.approx(107.12)
    assert evidence["stop_loss_distance_atr"] > 0
    assert evidence["price_action_support"] and evidence["session_vwap"] > 100 and evidence["support"]
    assert aligned_returns(completed, {at + MINUTE: 100 for at in completed if at != max(completed) - MINUTE}) == {}
    assert set(aligned_returns(completed, dict.fromkeys(completed, 100))) == {"5m", "10m", "30m", "60m"}


def test_dividend_freshness_and_titles_and_verified_adjustment(isolated_db):
    _, sessions = isolated_db
    seen = DECISION - timedelta(minutes=20)
    payload = {"output1": [{"sht_cd": "005930", "record_date": "20261029", "divi_pay_dt": "20261030",
                            "per_sto_divi_amt": "1000"}]}
    events = dividend_events(payload, "005930", seen)
    assert {event["event_type"] for event in events} == {"dividend_record_date", "dividend_payment_date"}
    assert events[0]["publication_timestamp"] is None
    assert events[0]["risk_notes"] == ["ex_dividend_date_unknown"]
    assert events[1]["risk_notes"] == ["payment_date_only"]
    with sessions() as db:
        disclosures = {"available": True, "items": [
            {"title": "주식분할", "published_at": seen.isoformat()},
            {"title": "거래정지", "published_at": (DECISION + MINUTE).isoformat()},
            {"title": "감자", "published_at": "2026-10-29"},
        ]}
        context = corporate_context(db, "005930", DECISION, 7, (seen, events, "hit"), disclosures)
        assert context["status"] == "verified_event" and len(context["events"]) == 2
        assert context["catalyst"] == "확인된 재료 없음"
        assert [event["event_type"] for event in context["recent_disclosures"]] == ["stock_split"]
        assert corporate_context(db, "005930", DECISION, 7, (seen, [], "hit"), disclosures)["status"] == "none_found"
        assert corporate_context(db, "005930", DECISION, 7, (DECISION + MINUTE, events, "miss"), {})["status"] == "unavailable"
    raw = [_bar(OPEN - timedelta(days=1), 200), _bar(OPEN, 100)]
    split = {"event_date": DECISION.date().isoformat(), "publication_timestamp": seen.isoformat(),
             "verification_status": "verified", "event_type": "stock_split",
             "historical_price_multiplier": .5, "source_reference": "KRX-filing"}
    adjusted, references = adjusted_daily(raw, [split], DECISION)
    assert references == ["KRX-filing"]
    assert adjusted[0]["close"] == adjusted[1]["close"] == 100
    assert raw[0]["close"] == 200


def test_gpt_component_scoring_checks_both_horizons():
    payload = _judgment()
    payload["short"]["component_scores"]["stop_loss_safety_score"] = 90
    scores = score_judgments(payload, True)
    assert scores["gpt_buy_score_short"] == 83 and scores["gpt_buy_score_long"] == 70
    assert scores["gpt_buy_score_v2"] == 70 and scores["stop_loss_safety_score"] == 70
    assert score_judgments(payload, False)["gpt_buy_score_v2"] == 59
    payload["long"]["component_scores"]["corporate_event_score"] = 101
    with pytest.raises(ValueError):
        score_judgments(payload, True)


@pytest.mark.parametrize(("high", "low", "expected"), [
    (102, 97, "sl_first"), (104, 99, "tp_first"),
    (101, 99, "neither"), (104, 97, "ambiguous_same_bar"),
])
def test_barrier_outcomes(high, low, expected):
    bars = [_bar(DECISION, high=high, low=low), _bar(DECISION + MINUTE)]
    horizon = evaluate_horizon(bars, decision=DECISION, minutes=2, session_close=CLOSE,
                               now=DECISION + 2 * MINUTE, entry=100, sl=98, tp=103)
    assert horizon["first_intrabar_barrier"] == expected
    assert horizon["actual_broker_execution"] is None
    assert horizon["sl_first_sensitivity"] == ("sl_first" if expected == "ambiguous_same_bar" else expected)
    assert horizon["simulated_monitor_exit"] is None


def test_barrier_gap_monitoring_and_missing_close():
    bars = [_bar(DECISION, 95), _bar(DECISION + MINUTE)]
    kwargs = dict(decision=DECISION, minutes=2, session_close=CLOSE,
                  now=DECISION + 2 * MINUTE, entry=100, sl=98, tp=103,
                  monitoring_checks=[DECISION + MINUTE], cost_bps=10)
    outcome = evaluate_horizon(bars, **kwargs)
    assert outcome["gap_through_stop"] and outcome["simulated_monitor_exit"]["price"] == 95
    assert outcome["conservative_intrabar_net_return"] == -.051
    assert outcome["recovered_above_entry_after_sl"]
    assert evaluate_horizon(bars[:1], **kwargs)["status"] == "incomplete_path"
    assert evaluate_horizon(bars, **(kwargs | {"session_close": DECISION + MINUTE}))["status"] == "insufficient_regular_session"
    assert evaluate_horizon(bars, **(kwargs | {"now": DECISION + MINUTE}))["status"] == "pending"


class FakeKisClient:
    def __init__(self, *args):
        pass

    def dividend(self, *args):
        return (None, None), 0

    def sector(self, *args):
        return None, 0

    def execution_strength(self, *args):
        return None, 0


class _ControlledAdvisor:
    def __init__(self, fail=False):
        self.started = threading.Event()
        self.release = threading.Event()
        self.fail = fail

    def analyze(self, evidence, timeout):
        self.evidence = evidence
        self.started.set()
        if self.fail:
            raise ValueError("invalid response")
        assert self.release.wait(4)
        return score_judgments(_judgment(), evidence["features"]["price_action_support"])


def _shared(run_key):
    started = time.perf_counter()
    return ShadowSnapshot(run_key, DECISION, started, started, json.dumps({
        "schedule": _schedule(), "performance": {}, "market_context": {}, "market_regime": {},
        "candidates": [{"symbol": "005930", "name": "삼성전자", "a_rank": 1, "a_score": 74,
                        "price": 104, "minute": _minute_rows(), "daily": _daily_rows()}],
    }))


@pytest.mark.parametrize(("mode", "status"), [("complete", "partial"), ("timeout", "timeout"), ("exception", "failed")])
def test_independent_shadow_worker_bounded_persistence_and_export(isolated_db, monkeypatch, mode, status):
    bind, sessions = isolated_db
    advisor = _ControlledAdvisor(fail=mode == "exception")
    monkeypatch.setattr(ReversalQuantService, "score_experimental", lambda *args, **kw: {"reversal_score_c": 80})
    settings = get_settings().model_copy(update={"kis_gpt_shadow_workers": 1,
        "kis_gpt_shadow_queue_size": 0, "kis_gpt_shadow_deadline_seconds": 1.0})
    worker = KisGptShadowWorker(settings, advisor=advisor, market_data_factory=FakeKisClient)
    snapshot = _shared("pr144")
    began = time.perf_counter()
    try:
        assert worker.submit(snapshot, bind)
        assert advisor.started.wait(3)
        if mode == "complete":
            assert not worker.submit(_shared("capacity"), bind)
        with sessions() as production:
            production.add(QuantABObservation(observation_key="pr144:005930", run_key="pr144",
                trigger_source="test", symbol="005930", a_rank=1, a_gpt_buy_score=77,
                c_reversal_score=81, a_final_score=80, observed_at=DECISION))
            production.commit()
            if mode == "complete":
                result = latest_shadow_results(production, 18, 11)["items"][0]
                assert result["gpt_v2_status"] == "pending" and result["legacy_gpt_buy_score"] == 77
                assert result["gpt_buy_score_v2"] is None
                assert latest_shadow_results(production, 18, 99)["items"] == []
        print(f"controlled V1 persistence ms ({mode}): {(time.perf_counter() - began) * 1000:.2f}")
        if mode == "timeout":
            time.sleep(1.05)
        advisor.release.set()
    finally:
        advisor.release.set()
        worker.close()
    assert advisor.evidence["effective_schedule_snapshot"]["effective_take_profit_pct"] == .03
    assert advisor.evidence["effective_schedule_snapshot"]["gpt_short_horizon_minutes"] == 17
    assert "corporate_context" in advisor.evidence
    with sessions() as db:
        row = db.scalar(select(KisGptShadowObservation))
        assert row.status == status
        analysis = json.loads(row.analysis_json)
        if mode == "complete":
            assert analysis["gpt_buy_score_v2"] == 70 and analysis["final_score_v2"] == 77.5
        else:
            assert analysis["gpt_buy_score_v2"] is None
        retry = copy.deepcopy(analysis)
    worker._persist(sessions, snapshot, _schedule(), [retry], pending=True)
    args = SimpleNamespace(trigger_source=None, from_date=None, to_date=None, a_rank_max=5,
                           c_min_score=65, gpt_min_score=60, final_min_score=65,
                           official_only=False, passed_only=False)
    with bind.connect() as connection:
        columns, rows = read_rows(connection, args)
    assert "gpt_v2_analysis_json" in columns
    assert rows[0]["a_gpt_buy_score"] == 77 and rows[0]["gpt_v2_status"] == status
    summary = v2_comparisons(rows, DECISION.date())
    assert summary["status_coverage"] == {status: 1}
    assert summary["strict_matched_count"] == 0


def test_preview_reuses_quotes_and_minute_bars_while_shadow_gpt_is_blocked(isolated_db, monkeypatch):
    bind, sessions = isolated_db
    advisor = _ControlledAdvisor()
    settings = get_settings().model_copy(update={"kis_enabled": True, "openai_api_key": None})
    monkeypatch.setattr("app.services.kis_watchlist_preview_service.get_settings", lambda: settings)
    monkeypatch.setattr(ReversalQuantService, "score_experimental", lambda *args, **kw: {"reversal_score_c": 80})
    calls = []

    class FakePreviewKisClient:
        def get_domestic_stock_price(self, symbol):
            calls.append(("quote", symbol))
            return {"symbol": symbol, "current_price": 103.28, "previous_close": 103}

        def get_domestic_daily_bars(self, symbol, limit):
            calls.append(("daily", symbol))
            return _daily_rows()

        def get_domestic_intraday_bars(self, symbol, *, as_of, limit):
            calls.append(("minute", symbol))
            return _minute_rows()

    legacy = SimpleNamespace(analyze=lambda **kw: KisGptPreview(
        True, "watch", "기존 점수", [], ai_buy_score=76, ai_sell_score=20,
        gpt_analysis_status="completed",
    ))
    preview = KisWatchlistPreviewService(
        FakePreviewKisClient(), gpt_advisor=legacy,
        market_context_service=SimpleNamespace(
            snapshot=lambda **kw: {}, summary=lambda payload: {},
            get_disclosures=lambda *args, **kw: {"items": [], "available": False},
        ),
        reversal_quant_service=SimpleNamespace(
            score=lambda **kw: {"reversal_score_c": 80, "data_quality_c": 1,
                                "timeframe_bar_counts": {"15m": 3, "30m": 2}},
        ),
    )
    preview.market_data_snapshot_service.clear_process_cache()
    monkeypatch.setattr(preview, "_rank_quant_candidates", lambda items: items)
    worker = KisGptShadowWorker(settings, advisor=advisor, market_data_factory=FakeKisClient)
    monkeypatch.setattr("app.services.kis_watchlist_preview_service.shadow_worker", lambda: worker)
    monkeypatch.setattr(preview, "_runtime_settings", lambda db: {"quant_selection_mode": "A_TOP5_C_GPT"})

    def run(db, profile):
        return preview.run_preview(
            db=db, decision_timestamp=DECISION, account_positions=[],
            profile_snapshot_items=[{"symbol": "005930", "name": "삼성전자"}],
            profile_snapshot_context={"scheduler_slot": "11:30", "_effective_schedule_profile": profile},
        )

    disabled = _profile()
    disabled["effective_settings"]["gpt_analysis"]["gpt_v2_shadow_enabled"] = False
    try:
        with sessions() as db:
            started = time.perf_counter()
            baseline = run(db, disabled)
            baseline_ms = (time.perf_counter() - started) * 1000
            assert ("minute", "005930") in calls
            calls.clear()
            preview.market_data_snapshot_service.clear_process_cache()
            started = time.perf_counter()
            parallel = run(db, _profile())
            parallel_ms = (time.perf_counter() - started) * 1000
            assert parallel["gpt_shadow"]["status"] == "pending"
            for key in ("symbol", "ai_buy_score", "quant_c_score", "final_entry_score", "entry_ready"):
                assert parallel["final_best_candidate"][key] == baseline["final_best_candidate"][key]
            assert parallel["real_order_submitted"] is False
            assert parallel["broker_submit_called"] is False
            assert calls == [("quote", "005930"), ("daily", "005930"), ("minute", "005930")]
        assert advisor.started.wait(2)
        assert not advisor.release.is_set()
        print(f"controlled preview V1-only {baseline_ms:.2f} ms; parallel V1 {parallel_ms:.2f} ms")
    finally:
        advisor.release.set()
        worker.close()
    with sessions() as db:
        result = latest_shadow_results(db, 18, 11)["items"][0]
        assert result["snapshot_id"] == parallel["gpt_shadow"]["run_key"]
        assert result["legacy_gpt_buy_score"] == 76
