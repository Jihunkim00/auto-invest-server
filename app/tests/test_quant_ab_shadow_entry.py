from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.brokers.kis_client import (
    KIS_INTRADAY_BARS_PATH,
    KIS_INTRADAY_BARS_TR_ID,
    KisClient,
    normalize_domestic_intraday_bars,
)
from app.db.models import QuantABObservation, QuantABOutcome
from app.services.entry_timing_quant_service import (
    EntryTimingQuantService,
    resample_intraday_bars,
)
from app.services.kis_watchlist_preview_service import (
    KisWatchlistPreviewService,
    _record_quant_ab_observations,
)
from app.services.market_data_snapshot_service import (
    MarketDataSnapshotService,
    validate_intraday_snapshot,
)


KST = ZoneInfo('Asia/Seoul')


def _intraday_bars(count: int = 180) -> list[dict]:
    start = datetime(2026, 9, 4, 9, 0, tzinfo=KST)
    bars = []
    for index in range(count):
        timestamp = start + timedelta(minutes=index)
        close = 100.0 + index * 0.05
        bars.append(
            {
                'timestamp': timestamp.isoformat(),
                'open': close - 0.02,
                'high': close + 0.08,
                'low': close - 0.08,
                'close': close,
                'volume': 1000 + index,
            }
        )
    return bars


def _daily_bars(count: int = 60) -> list[dict]:
    start = datetime(2026, 7, 1, tzinfo=KST)
    bars = []
    for index in range(count):
        close = 100.0 + index * 0.5
        bars.append(
            {
                'timestamp': (start + timedelta(days=index)).date().isoformat(),
                'open': close - 0.2,
                'high': close + 0.5,
                'low': close - 0.5,
                'close': close,
                'volume': 10000 + index,
            }
        )
    return bars


def _normalized_intraday_bars(
    session_date: str = '2026-09-04',
    *,
    start_time: str = '09:00:00',
    count: int = 180,
    close_start: float = 100.0,
) -> list[dict]:
    start = datetime.fromisoformat(f'{session_date}T{start_time}').replace(tzinfo=KST)
    bars = []
    for index in range(count):
        timestamp = start + timedelta(minutes=index)
        close = close_start + index * 0.05
        bars.append(
            {
                'symbol': '005930',
                'session_date': session_date,
                'time': timestamp.strftime('%H:%M:%S'),
                'timestamp': timestamp.isoformat(),
                'open': close - 0.02,
                'high': close + 0.08,
                'low': close - 0.08,
                'close': close,
                'volume': 1000 + index,
            }
        )
    return bars


def test_resample_excludes_incomplete_and_future_buckets():
    decision = datetime(2026, 9, 4, 10, 4, tzinfo=KST)

    bars = resample_intraday_bars(
        _intraday_bars(),
        timeframe_minutes=15,
        decision_timestamp=decision,
    )

    assert len(bars) == 4
    assert all(datetime.fromisoformat(bar['timestamp']) < decision for bar in bars)
    assert not any('10:00:00' in bar['timestamp'] for bar in bars)
    assert bars[0]['source_bar_count'] == 15
    assert bars[0]['volume'] == sum(1000 + index for index in range(15))


def test_entry_timing_quant_returns_deterministic_b_fields():
    service = EntryTimingQuantService()
    result = service.score(
        current_price=130.0,
        daily_bars=_daily_bars(),
        intraday_bars=_intraday_bars(),
        decision_timestamp=datetime(2026, 9, 4, 11, 59, tzinfo=KST),
    )

    expected = {
        'entry_score_b',
        'future_up_score_b',
        'future_down_score_b',
        'entry_timing_score_b',
        'trend_context_score_b',
        'momentum_score_b',
        'volume_score_b',
        'volatility_fit_score_b',
        'trend_state_b',
        'direction_b',
        'confidence_b',
        'data_quality_b',
        'b_reason',
        'b_notes',
        'indicator_snapshot',
    }
    assert expected.issubset(result)
    assert 0.0 <= result['entry_score_b'] <= 100.0
    assert result['timeframe_bar_counts'] == {'15m': 11, '30m': 5, '60m': 2}
    assert result['data_quality_b'] > 0.0


def test_daily_snapshot_cache_is_keyed_by_kst_trading_date():
    class FakeClient:
        def __init__(self):
            self.price_calls = 0
            self.daily_calls = 0

        def get_domestic_stock_price(self, symbol):
            self.price_calls += 1
            return {'symbol': symbol, 'current_price': 100.0}

        def get_domestic_daily_bars(self, symbol, limit=120):
            self.daily_calls += 1
            return _daily_bars()

    current = [datetime(2026, 9, 4, 0, 30, tzinfo=ZoneInfo('UTC'))]
    client = FakeClient()
    MarketDataSnapshotService.clear_process_cache()
    service = MarketDataSnapshotService(client, now_provider=lambda: current[0])

    first = service.snapshot('005930')
    second = service.snapshot('005930')
    current[0] = datetime(2026, 9, 5, 0, 30, tzinfo=ZoneInfo('UTC'))
    third = service.snapshot('005930')

    assert first['daily_cache_miss'] is True
    assert second['daily_cache_hit'] is True
    assert third['daily_cache_miss'] is True
    assert client.price_calls == 3
    assert client.daily_calls == 2


def test_kis_intraday_method_uses_official_read_only_contract():
    client = object.__new__(KisClient)
    calls = []

    def fake_request_get(path, *, tr_id, params):
        calls.append((path, tr_id, params))
        return {
            'output2': [
                {
                    'stck_bsop_date': '20260904',
                    'stck_cntg_hour': '101530',
                    'stck_oprc': '100',
                    'stck_hgpr': '102',
                    'stck_lwpr': '99',
                    'stck_prpr': '101',
                    'cntg_vol': '500',
                }
            ]
        }

    client.request_get = fake_request_get
    bars = client.get_domestic_intraday_bars(
        '005930',
        as_of=datetime(2026, 9, 4, 11, 0, tzinfo=KST),
        limit=600,
    )

    assert calls[0][0] == KIS_INTRADAY_BARS_PATH
    assert calls[0][1] == KIS_INTRADAY_BARS_TR_ID
    assert calls[0][2]['FID_INPUT_DATE_1'] == '20260904'
    assert calls[0][2]['FID_INPUT_HOUR_1'] == '110000'
    assert bars[0]['timestamp'].startswith('2026-09-04T10:15:30')
    assert bars[0]['close'] == 101.0
    assert bars[0]['session_date'] == '2026-09-04'
    assert bars[0]['time'] == '10:15:30'
    assert bars[0]['source_session_date'] == '20260904'


def test_intraday_validation_accepts_same_day_and_emits_diagnostics():
    decision = datetime(2026, 9, 4, 11, 59, tzinfo=KST)
    bars, metadata = validate_intraday_snapshot(
        _normalized_intraday_bars(count=180),
        decision_timestamp=decision,
        reference_current_price=110.0,
        previous_close=100.0,
    )

    assert len(bars) == 180
    assert metadata['validation_status'] == 'ok'
    assert metadata['expected_session_date'] == '2026-09-04'
    assert metadata['actual_session_dates'] == ['2026-09-04']
    assert metadata['session_match'] is True
    assert metadata['first_bar_at'].startswith('2026-09-04T09:00:00')
    assert metadata['last_bar_at'].startswith('2026-09-04T11:59:00')
    assert metadata['latest_intraday_close'] == bars[-1]['close']
    assert metadata['reference_current_price'] == 110.0
    assert metadata['previous_close'] == 100.0
    assert metadata['price_gap_pct'] > 0
    assert metadata['raw_timeframe_minutes'] == 1
    assert metadata['decision_at'].startswith('2026-09-04T11:59:00')
    assert metadata['freshness_status'] == 'ok'
    assert metadata['validation_reasons'] == []


def test_intraday_validation_rejects_previous_day_only_and_keeps_price_gap_secondary():
    bars, metadata = validate_intraday_snapshot(
        _normalized_intraday_bars('2026-09-03', count=180, close_start=147900.0),
        decision_timestamp=datetime(2026, 9, 4, 11, 0, tzinfo=KST),
        reference_current_price=157300.0,
        previous_close=147900.0,
    )

    assert bars == []
    assert metadata['validation_status'] == 'stale_intraday'
    assert metadata['session_match'] is False
    assert metadata['actual_session_dates'] == ['2026-09-03']
    assert 'session_date_mismatch' in metadata['validation_reasons']
    assert metadata['price_gap_pct'] > 0


def test_intraday_validation_filters_mixed_and_future_bars():
    previous = _normalized_intraday_bars('2026-09-03', count=2, start_time='15:28:00')
    current_and_future = _normalized_intraday_bars('2026-09-04', count=392)
    bars, metadata = validate_intraday_snapshot(
        sorted(previous + current_and_future, key=lambda bar: bar['timestamp']),
        decision_timestamp=datetime(2026, 9, 4, 16, 30, tzinfo=KST),
    )

    assert metadata['validation_status'] == 'ok'
    assert metadata['actual_session_dates'] == ['2026-09-03', '2026-09-04']
    assert metadata['bar_count'] == 391
    assert metadata['excluded_bar_count'] == 2
    assert metadata['future_bar_count'] == 1
    assert bars[-1]['time'] == '15:30:00'
    assert all(bar['session_date'] == '2026-09-04' for bar in bars)
    assert metadata['effective_cutoff_at'].startswith('2026-09-04T15:30:00')


def test_intraday_validation_marks_current_day_short_history_partial():
    bars, metadata = validate_intraday_snapshot(
        _normalized_intraday_bars(start_time='09:59:00', count=2),
        decision_timestamp=datetime(2026, 9, 4, 10, 0, tzinfo=KST),
    )

    assert len(bars) == 2
    assert metadata['validation_status'] == 'partial'
    assert metadata['partial_history'] is True
    assert 'insufficient_current_day_history' in metadata['validation_reasons']


def test_intraday_validation_rejects_duplicate_and_non_ascending_timestamps():
    source = _normalized_intraday_bars(count=2)
    bars, metadata = validate_intraday_snapshot(
        [source[1], source[0], source[0]],
        decision_timestamp=datetime(2026, 9, 4, 10, 0, tzinfo=KST),
    )

    assert bars == []
    assert metadata['validation_status'] == 'stale_intraday'
    assert metadata['duplicate_timestamp_count'] == 1
    assert metadata['timestamp_ordering_valid'] is False
    assert 'duplicate_timestamp' in metadata['validation_reasons']
    assert 'timestamp_not_ascending' in metadata['validation_reasons']


def test_kis_intraday_normalizer_does_not_fabricate_missing_session_date():
    assert normalize_domestic_intraday_bars(
        '005930',
        [
            {
                'stck_cntg_hour': '101530',
                'stck_oprc': '100',
                'stck_hgpr': '102',
                'stck_lwpr': '99',
                'stck_prpr': '101',
                'cntg_vol': '500',
            }
        ],
        trading_date=datetime(2026, 9, 4, tzinfo=KST).date(),
    ) == []


def test_010950_previous_close_regression_is_stale_intraday():
    bars, metadata = validate_intraday_snapshot(
        [
            {
                'symbol': '010950',
                'session_date': '2026-09-03',
                'time': '15:30:00',
                'timestamp': '2026-09-03T15:30:00+09:00',
                'open': 147900.0,
                'high': 147900.0,
                'low': 147900.0,
                'close': 147900.0,
                'volume': 100,
            }
        ],
        decision_timestamp=datetime(2026, 9, 4, 16, 30, tzinfo=KST),
        reference_current_price=157300.0,
        previous_close=147900.0,
    )

    assert bars == []
    assert metadata['latest_intraday_close'] == 147900.0
    assert metadata['validation_status'] == 'stale_intraday'
    assert metadata['reference_current_price'] == 157300.0
    assert metadata['previous_close'] == 147900.0
    assert metadata['price_gap_pct'] > 0


def test_stale_shadow_b_is_null_and_never_ranked(monkeypatch):
    class FakeSnapshotService:
        def get_intraday_bars(self, symbol, **kwargs):
            return [], {
                'validation_status': 'stale_intraday',
                'validation_reasons': ['session_date_mismatch'],
                'expected_session_date': '2026-09-04',
                'actual_session_dates': ['2026-09-03'],
            }

    service = object.__new__(KisWatchlistPreviewService)
    service.market_data_snapshot_service = FakeSnapshotService()
    service.entry_timing_quant_service = EntryTimingQuantService()
    monkeypatch.setattr(
        'app.services.kis_watchlist_preview_service.get_settings',
        lambda: type('Settings', (), {'kis_enabled': True})(),
    )
    item = {
        'symbol': '010950',
        'current_price': 157300.0,
        'previous_close': 147900.0,
        'quant_buy_score': 72.0,
        'final_entry_score': 72.0,
    }
    result = service._run_shadow_b(
        quant_ranked_candidates=[item],
        market_snapshots={'010950': {'daily_bars': _daily_bars()}},
        items_by_symbol={'010950': item},
        runtime_settings={'quant_shadow_b_enabled': True, 'quant_shadow_b_candidate_limit': 10},
        decision_timestamp=datetime(2026, 9, 4, 16, 30, tzinfo=KST),
        market_session={'regular_open': '09:00', 'regular_close': '15:30'},
    )

    shadow = item['shadow_b']
    assert shadow['b_status'] == 'stale_intraday'
    assert shadow['entry_score_b'] is None
    assert shadow['trend_state_b'] is None
    assert shadow['direction_b'] is None
    assert shadow['confidence_b'] == 0.0
    assert shadow['data_quality_b'] == 0.0
    assert result['stale_count'] == 1
    assert result['b_shadow_ranked_symbols'] == []
    assert item['quant_buy_score'] == 72.0
    assert item['final_entry_score'] == 72.0


def test_quant_ab_observation_persistence_is_idempotent(db_session):
    payload = {
        'quant_experiment': {
            'shadow_b_enabled': True,
            'b_shadow_ranked_symbols': ['005930'],
            'decision_slot': '2026-09-04T10:00:00+09:00',
        },
        'quant_ranked_candidates': [
            {
                'rank': 1,
                'symbol': '005930',
                'quant_buy_score': 72.0,
                'quant_sell_score': 12.0,
                'final_entry_score': 72.0,
            }
        ],
        'watchlist': [
            {
                'symbol': '005930',
                'current_price': 70000.0,
                'quant_buy_score': 72.0,
                'quant_sell_score': 12.0,
                'final_buy_score': 72.0,
                'indicator_payload': {'ema20': 69000.0},
                'shadow_b': {
                    'entry_score_b': 68.0,
                    'future_up_score_b': 70.0,
                    'future_down_score_b': 30.0,
                    'entry_timing_score_b': 66.0,
                    'trend_context_score_b': 71.0,
                    'momentum_score_b': 69.0,
                    'volume_score_b': 63.0,
                    'volatility_fit_score_b': 60.0,
                    'trend_state_b': 'bullish_continuation',
                    'direction_b': 'bullish',
                    'confidence_b': 0.6191,
                    'data_quality_b': 0.9,
                    'indicator_snapshot': {'15m': {'bar_count': 4}},
                    'intraday_snapshot_metadata': {'raw_timeframe_minutes': 1},
                    'b_reason': 'test',
                    'b_notes': ['test'],
                },
            }
        ],
        'gpt_target_symbols': ['005930'],
        'final_best_candidate': {'symbol': '005930'},
    }

    assert _record_quant_ab_observations(
        db_session,
        payload=payload,
        gate_level=2,
        trigger_source='test',
        run_key='kis_ab_test_run',
    ) == 1
    assert _record_quant_ab_observations(
        db_session,
        payload=payload,
        gate_level=2,
        trigger_source='test',
        run_key='kis_ab_test_run',
    ) == 0
    row = db_session.query(QuantABObservation).one()
    assert row.authoritative_variant == 'A'
    assert row.shadow_variant == 'B'
    assert row.selected_by_a is True
    assert row.selected_by_b_shadow is True
    assert row.confidence_b == 0.6191

    payload['quant_experiment'] = {
        **payload['quant_experiment'],
        'b_shadow_ranked_symbols': [],
        'decision_slot': '2026-09-04T16:30:00+09:00',
    }
    payload['watchlist'][0]['shadow_b'] = {
        'entry_score_b': None,
        'trend_state_b': None,
        'direction_b': None,
        'data_quality_b': 0.0,
        'b_status': 'stale_intraday',
        'b_reason': 'stale test',
        'b_notes': ['b_stale_intraday'],
        'intraday_snapshot_metadata': {
            'validation_status': 'stale_intraday',
        },
    }
    assert _record_quant_ab_observations(
        db_session,
        payload=payload,
        gate_level=2,
        trigger_source='test',
        run_key='kis_ab_stale_run',
    ) == 1
    stale_row = (
        db_session.query(QuantABObservation)
        .filter_by(run_key='kis_ab_stale_run')
        .one()
    )
    assert stale_row.outcome_status == 'invalid_stale_intraday'
    assert stale_row.b_entry_score is None
    assert stale_row.trend_state_b is None
    assert stale_row.direction_b is None
    assert stale_row.selected_by_b_shadow is False


def test_quant_ab_recent_serializer_preserves_confidence_and_legacy_null(db_session):
    from app.services.quant_ab_evaluation_service import QuantABEvaluationService

    observations = []
    for symbol, confidence in (("SERIALIZE", 0.6191), ("LEGACY", None)):
        observation = QuantABObservation(
            observation_key=f"serializer:{symbol}",
            run_key="serializer-run",
            experiment_cohort_key="serializer-cohort",
            trigger_source="test",
            provider="kis",
            market="KR",
            symbol=symbol,
            observed_at=datetime(2026, 9, 4, 9, 10, tzinfo=KST),
            decision_slot="2026-09-04T09:10:00+09:00",
            current_price=100.0,
            b_entry_score=80.0,
            confidence_b=confidence,
            data_quality_b=1.0,
            outcome_status="pending",
        )
        db_session.add(observation)
        observations.append(observation)
    db_session.commit()
    for observation in observations:
        db_session.add(
            QuantABOutcome(
                observation_id=observation.id,
                cohort_key="serializer-cohort",
                symbol=observation.symbol,
                outcome_status="pending",
                data_quality=1.0,
            )
        )
    db_session.commit()

    result = QuantABEvaluationService().recent(db_session)
    items = {item["observation"]["symbol"]: item for item in result["items"]}
    assert items["SERIALIZE"]["observation"]["confidence_b"] == 0.6191
    assert items["SERIALIZE"]["confidence_b"] == 0.6191
    assert items["LEGACY"]["observation"]["confidence_b"] is None
    assert items["LEGACY"]["confidence_b"] is None
