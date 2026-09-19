from datetime import datetime, timedelta
import inspect
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.db.models import QuantABObservation
from app.services.kis_watchlist_preview_service import (
    KisWatchlistPreviewService,
    _record_quant_ab_observations,
)
from app.services.reversal_quant_service import ReversalQuantService

KST = ZoneInfo('Asia/Seoul')
DECISION = datetime(2026, 9, 4, 12, 0, tzinfo=KST)


def _daily(closes, *, include_decision_day=False):
    start = datetime(2026, 7, 1)
    rows = []
    for index, close in enumerate(closes):
        day = start + timedelta(days=index)
        rows.append({
            'date': day.date().isoformat(), 'open': close, 'high': close * 1.01,
            'low': close * .99, 'close': close, 'volume': 1000 + index,
        })
    if include_decision_day:
        rows.append({
            'date': DECISION.date().isoformat(), 'open': 1, 'high': 9999,
            'low': .01, 'close': 9999, 'volume': 999999,
        })
    return rows


def _intraday(closes, *, volume_rising=False):
    start = DECISION.replace(hour=9, minute=0)
    rows = []
    previous = closes[0]
    for index, close in enumerate(closes):
        at = start + timedelta(minutes=index)
        rows.append({
            'timestamp': at.isoformat(), 'open': previous,
            'high': max(previous, close) * 1.001,
            'low': min(previous, close) * .999, 'close': close,
            'volume': 100 + index * 2 if volume_rising else 100,
        })
        previous = close
    return rows


def _score(daily, intraday, *, price=None):
    return ReversalQuantService().score(
        current_price=price or intraday[-1]['close'], daily_bars=daily,
        intraday_bars=intraday, decision_timestamp=DECISION,
    )


def test_reversal_score_bounded_and_oversold_falling_knife_is_not_high():
    daily = [200 * (0.982 ** i) for i in range(38)]
    intraday = [150 - .002 * i * i for i in range(180)]
    result = _score(_daily(daily, include_decision_day=True), _intraday(intraday, volume_rising=True))

    assert 0 <= result['reversal_score_c'] <= 100
    assert result['reversal_score_c'] < 50
    assert result['downtrend_continuation_risk_c'] >= 60
    assert result['oversold_score_c'] >= 60
    assert result['macd_reversal_score_c'] < 50


def test_confirmed_reversal_outscores_oversold_only():
    declining = [180 * (0.988 ** i) for i in range(25)]
    recovering_daily = declining + [declining[-1] * (1.012 ** i) for i in range(1, 13)]
    falling = [150 - .002 * i * i for i in range(180)]
    rising = [150 - .10 * i if i < 90 else 141 + .10 * (i - 90) for i in range(180)]
    oversold_only = _score(_daily(declining), _intraday(falling))
    confirmed = _score(_daily(recovering_daily), _intraday(rising, volume_rising=True))

    assert confirmed['reversal_score_c'] > oversold_only['reversal_score_c']
    assert confirmed['macd_reversal_score_c'] > oversold_only['macd_reversal_score_c']
    assert confirmed['intraday_reversal_score_c'] > oversold_only['intraday_reversal_score_c']
    assert confirmed['reversal_state_c'] in {'reversal_forming', 'reversal_confirmed'}


def test_future_daily_and_incomplete_or_future_intraday_are_excluded():
    daily = _daily([100 + i for i in range(25)], include_decision_day=True)
    intraday = _intraday([100 + i * .01 for i in range(61)])
    result = ReversalQuantService().score(
        current_price=intraday[-1]['close'], daily_bars=daily,
        intraday_bars=intraday, decision_timestamp=DECISION.replace(hour=10),
    )

    assert result['timeframe_bar_counts']['daily'] == 25
    assert result['timeframe_bar_counts']['15m'] == 4
    assert result['timeframe_bar_counts']['30m'] == 2
    assert result['timeframe_bar_counts']['60m'] == 1


def test_15m_buying_volume_improves_confirmation_component():
    daily = _daily([150 * (.997 ** i) for i in range(35)])
    prices = [120 + i * .04 for i in range(180)]
    quiet_bars = _intraday(prices)
    buying_bars = [dict(row) for row in quiet_bars]
    for row in buying_bars[-15:]:
        row['volume'] = 1200
    quiet = _score(daily, quiet_bars)
    buying = _score(daily, buying_bars)

    assert buying['volume_confirmation_score_c'] > quiet['volume_confirmation_score_c']
    assert buying['reversal_score_c'] > quiet['reversal_score_c']


def test_c_service_source_has_no_execution_risk_or_gpt_dependencies():
    source = inspect.getsource(ReversalQuantService)
    for forbidden in (
        'submit_order', 'submit_domestic_cash_order', 'KisManualOrderService',
        'RiskService', 'risk_engine', 'OpenAI', 'GPT',
    ):
        assert forbidden not in source


class _FakeReversal:
    def __init__(self, *, fail=False):
        self.called = []
        self.fail = fail

    def score(self, **kwargs):
        self.called.append(kwargs['current_price'])
        if self.fail:
            raise RuntimeError('isolated C failure')
        value = float(kwargs['current_price'])
        return {
            'reversal_score_c': value, 'data_quality_c': 1.0,
            'confidence_c': .8, 'timeframe_bar_counts': {'15m': 2, '30m': 2, '60m': 2},
            'indicator_snapshot': {}, 'c_notes': [], 'c_reason': 'test',
        }


def _shadow_service(fake):
    service = object.__new__(KisWatchlistPreviewService)
    service.reversal_quant_service = fake
    return service


def test_c_scope_is_top5_deterministic_and_does_not_mutate_a_scores(monkeypatch):
    monkeypatch.setattr(
        'app.services.kis_watchlist_preview_service.get_settings',
        lambda: SimpleNamespace(kis_enabled=True),
    )
    fake = _FakeReversal()
    service = _shadow_service(fake)
    candidates = [
        {'symbol': f'{i:06d}', 'current_price': float(i), 'quant_buy_score': 70-i,
         'final_entry_score': 80-i}
        for i in range(1, 8)
    ]
    items = {row['symbol']: row for row in candidates}
    snapshots = {row['symbol']: {'daily_bars': []} for row in candidates}
    shared = {row['symbol']: {'bars': [], 'metadata': {'validation_status': 'ok'}} for row in candidates}

    result = service._run_shadow_c(
        quant_ranked_candidates=candidates, market_snapshots=snapshots,
        items_by_symbol=items, intraday_snapshots_by_symbol=shared,
        decision_timestamp=DECISION,
    )

    assert len(fake.called) == 5
    assert result['candidate_limit'] == 5
    assert result['c_shadow_ranked_symbols'] == ['000005', '000004', '000003', '000002', '000001']
    assert items['000001']['quant_buy_score'] == 69
    assert items['000001']['final_entry_score'] == 79
    assert 'shadow_c' not in items['000006']


def test_c_failure_is_fail_soft_and_never_calls_order_or_risk(monkeypatch):
    monkeypatch.setattr(
        'app.services.kis_watchlist_preview_service.get_settings',
        lambda: SimpleNamespace(kis_enabled=True),
    )
    fake = _FakeReversal(fail=True)
    service = _shadow_service(fake)
    candidates = [{'symbol': '005930', 'current_price': 100, 'quant_buy_score': 75}]
    item = candidates[0]
    result = service._run_shadow_c(
        quant_ranked_candidates=candidates,
        market_snapshots={'005930': {'daily_bars': []}},
        items_by_symbol={'005930': item},
        intraday_snapshots_by_symbol={'005930': {'bars': [], 'metadata': {'validation_status': 'ok'}}},
        decision_timestamp=DECISION,
    )
    assert result['failed_count'] == 1
    assert item['shadow_c']['c_status'] == 'failed_soft'
    assert item['quant_buy_score'] == 75
    assert item['shadow_c']['reversal_score_c'] is None


def test_c_observation_fields_persist_idempotently_with_shared_snapshot(db_session):
    payload = {
        'quant_experiment': {
            'shadow_b_enabled': True, 'shadow_c_enabled': True,
            'b_shadow_ranked_symbols': ['005930'],
            'c_shadow_ranked_symbols': ['005930'],
            'decision_slot': DECISION.isoformat(),
        },
        'quant_ranked_candidates': [{'rank': 1, 'symbol': '005930', 'quant_buy_score': 70}],
        'watchlist': [{
            'symbol': '005930', 'current_price': 100, 'quant_buy_score': 70,
            'final_buy_score': 72,
            'shadow_b': {'entry_score_b': 68, 'data_quality_b': .9, 'indicator_snapshot': {'15m': {'n': 2}}},
            'shadow_c': {
                'reversal_score_c': 82, 'oversold_score_c': 18,
                'macd_reversal_score_c': 22, 'price_stabilization_score_c': 17,
                'intraday_reversal_score_c': 17, 'volume_confirmation_score_c': 8,
                'downtrend_continuation_risk_c': 15, 'confidence_c': .8,
                'data_quality_c': .91, 'reversal_state_c': 'reversal_confirmed',
                'direction_c': 'bullish', 'c_reason': 'test', 'c_notes': ['point-in-time'],
                'indicator_snapshot': {'30m': {'macd_histogram_slope': .1}},
            },
        }],
        'final_best_candidate': {'symbol': '005930'}, 'gpt_target_symbols': [],
    }
    assert _record_quant_ab_observations(
        db_session, payload=payload, gate_level=2, trigger_source='test', run_key='c_obs_run'
    ) == 1
    assert _record_quant_ab_observations(
        db_session, payload=payload, gate_level=2, trigger_source='test', run_key='c_obs_run'
    ) == 0
    row = db_session.query(QuantABObservation).one()
    assert row.authoritative_variant == 'A'
    assert row.shadow_variant == 'B'
    assert row.c_rank_within_shadow_pool == 1
    assert row.selected_by_c_shadow is True
    assert row.c_reversal_score == 82
    assert row.reversal_state_c == 'reversal_confirmed'
    assert row.data_quality_c == .91
