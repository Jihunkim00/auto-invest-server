from __future__ import annotations

import math
from datetime import datetime, time as date_time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


KST = ZoneInfo('Asia/Seoul')
ENTRY_TIMING_WEIGHTS = {
    'daily_trend_context': 20.0,
    'context_60m': 20.0,
    'momentum_30m': 20.0,
    'entry_timing_15m': 15.0,
    'volume_price_position': 10.0,
    'volatility_fit': 15.0,
}
SUPPORTED_TIMEFRAMES = (15, 30, 60)


class EntryTimingQuantService:
    '''Deterministic, read-only B entry-timing score.'''

    def score(
        self,
        *,
        current_price: float | None,
        daily_bars: list[dict[str, Any]] | None,
        intraday_bars: list[dict[str, Any]] | None,
        decision_timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        decision = _decision_timestamp(decision_timestamp)
        daily_score, daily_detail = _daily_context_score(daily_bars, current_price)
        frames = {
            minutes: resample_intraday_bars(
                intraday_bars or [],
                timeframe_minutes=minutes,
                decision_timestamp=decision,
            )
            for minutes in SUPPORTED_TIMEFRAMES
        }
        context_60, context_60_detail = _timeframe_score(frames[60], purpose='context')
        momentum_30, momentum_30_detail = _timeframe_score(frames[30], purpose='momentum')
        timing_15, timing_15_detail = _timeframe_score(frames[15], purpose='timing')
        volume_score, volume_detail = _volume_price_score(
            frames[15] or frames[30] or frames[60]
        )
        volatility_score, volatility_detail = _volatility_fit_score(
            daily_bars=daily_bars,
            frames=frames,
            current_price=current_price,
        )

        components = {
            'daily_trend_context': daily_score,
            'context_60m': context_60,
            'momentum_30m': momentum_30,
            'entry_timing_15m': timing_15,
            'volume_price_position': volume_score,
            'volatility_fit': volatility_score,
        }
        available_weight = sum(
            ENTRY_TIMING_WEIGHTS[name]
            for name, value in components.items()
            if value is not None
        )
        if available_weight <= 0:
            entry_score = 0.0
        else:
            entry_score = sum(
                float(value) * ENTRY_TIMING_WEIGHTS[name]
                for name, value in components.items()
                if value is not None
            ) / available_weight
        entry_score = _bounded_score(entry_score)

        data_quality = _data_quality(
            daily_bars=daily_bars,
            intraday_bars=intraday_bars,
            frames=frames,
            available_weight=available_weight,
        )
        direction = _direction(entry_score, daily_score, context_60, momentum_30)
        trend_state = _trend_state(
            direction=direction,
            daily_score=daily_score,
            context_60=context_60,
            momentum_30=momentum_30,
            timing_15=timing_15,
        )
        confidence = round(
            min(1.0, max(0.0, data_quality * (0.5 + abs(entry_score - 50.0) / 100.0))),
            4,
        )
        future_up = _bounded_score(
            _average_available(
                (daily_score, context_60, momentum_30, timing_15),
                default=entry_score,
            )
        )
        future_down = _bounded_score(100.0 - future_up)
        missing = [name for name, value in components.items() if value is None]
        notes = [
            'B uses one raw intraday read and local 15m/30m/60m resampling.',
            'Missing timeframe components redistribute weight conservatively.',
        ]
        if missing:
            notes.append('missing_components=' + ','.join(missing))
        notes.extend(
            detail
            for detail in (
                daily_detail.get('note'),
                context_60_detail.get('note'),
                momentum_30_detail.get('note'),
                timing_15_detail.get('note'),
                volume_detail.get('note'),
                volatility_detail.get('note'),
            )
            if detail
        )

        return {
            'entry_score_b': entry_score,
            'future_up_score_b': future_up,
            'future_down_score_b': future_down,
            'entry_timing_score_b': _score_or_zero(timing_15),
            'trend_context_score_b': _score_or_zero(
                _average_available((daily_score, context_60), default=0.0)
            ),
            'momentum_score_b': _score_or_zero(momentum_30),
            'volume_score_b': _score_or_zero(volume_score),
            'volatility_fit_score_b': _score_or_zero(volatility_score),
            'trend_state_b': trend_state,
            'direction_b': direction,
            'confidence_b': confidence,
            'data_quality_b': round(data_quality, 4),
            'b_reason': _reason(
                entry_score=entry_score,
                trend_state=trend_state,
                data_quality=data_quality,
                missing=missing,
            ),
            'b_notes': _dedupe(notes),
            'timeframe_bar_counts': {
                '15m': len(frames[15]),
                '30m': len(frames[30]),
                '60m': len(frames[60]),
            },
            'indicator_snapshot': {
                'daily': daily_detail,
                '15m': timing_15_detail,
                '30m': momentum_30_detail,
                '60m': context_60_detail,
                'volume_price': volume_detail,
                'volatility': volatility_detail,
            },
        }


def resample_intraday_bars(
    bars: list[dict[str, Any]],
    *,
    timeframe_minutes: int,
    decision_timestamp: datetime | None = None,
) -> list[dict[str, Any]]:
    '''Resample bars and exclude every incomplete/future bucket.'''
    minutes = int(timeframe_minutes)
    if minutes not in SUPPORTED_TIMEFRAMES:
        raise ValueError('timeframe_minutes must be one of 15, 30, or 60')
    decision = _decision_timestamp(decision_timestamp)
    normalized = _normalize_intraday_bars(bars)
    if not normalized:
        return []

    frame = pd.DataFrame(normalized)
    timestamps = pd.to_datetime(frame['timestamp'], errors='coerce')
    if getattr(timestamps.dt, 'tz', None) is None:
        timestamps = timestamps.dt.tz_localize(KST)
    else:
        timestamps = timestamps.dt.tz_convert(KST)
    frame['timestamp'] = timestamps
    decision_ts = pd.Timestamp(decision)
    frame = frame.loc[
        (frame['timestamp'] <= decision_ts)
        & (frame['timestamp'].dt.date == decision.date())
    ].copy()
    if frame.empty:
        return []
    frame = frame.set_index('timestamp').sort_index()
    origin = pd.Timestamp.combine(decision.date(), date_time(9, 0)).tz_localize(KST)
    grouped = frame.resample(
        f'{minutes}min',
        origin=origin,
        label='left',
        closed='left',
    ).agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
        volume=('volume', 'sum'),
        source_bar_count=('close', 'count'),
    )
    grouped['bucket_end'] = grouped.index + pd.Timedelta(minutes=minutes)
    grouped = grouped.loc[grouped['bucket_end'] <= decision_ts]
    grouped = grouped.loc[grouped['source_bar_count'] > 0]

    result = []
    for timestamp, row in grouped.iterrows():
        values = [row.get(key) for key in ('open', 'high', 'low', 'close')]
        if any(_finite(value) is None or _finite(value) <= 0 for value in values):
            continue
        result.append(
            {
                'timestamp': timestamp.isoformat(),
                'open': round(float(row['open']), 8),
                'high': round(float(row['high']), 8),
                'low': round(float(row['low']), 8),
                'close': round(float(row['close']), 8),
                'volume': round(max(0.0, float(row['volume'] or 0.0)), 8),
                'source_bar_count': int(row['source_bar_count']),
            }
        )
    return result


def _normalize_intraday_bars(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for raw in bars or []:
        if not isinstance(raw, dict):
            continue
        timestamp = str(raw.get('timestamp') or raw.get('datetime') or '').strip()
        values = {key: _finite(raw.get(key)) for key in ('open', 'high', 'low', 'close')}
        volume = _finite(raw.get('volume'), default=0.0)
        if not timestamp or any(values[key] is None or values[key] <= 0 for key in values):
            continue
        if values['high'] < values['low']:
            continue
        normalized.append(
            {'timestamp': timestamp, **values, 'volume': max(0.0, volume or 0.0)}
        )
    return normalized


def _frame_from_bars(bars: list[dict[str, Any]] | None) -> pd.DataFrame | None:
    normalized = _normalize_intraday_bars(bars or [])
    if not normalized:
        return None
    frame = pd.DataFrame(normalized)
    return frame.sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)


def _decision_timestamp(value: datetime | None) -> datetime:
    current = value or datetime.now(KST)
    if current.tzinfo is None:
        return current.replace(tzinfo=KST)
    return current.astimezone(KST)


def _daily_context_score(
    bars: list[dict[str, Any]] | None,
    current_price: float | None,
) -> tuple[float | None, dict[str, Any]]:
    frame = _frame_from_bars(bars)
    if frame is None or len(frame) < 20:
        return None, {
            'bar_count': 0 if frame is None else len(frame),
            'note': 'daily_context_insufficient',
        }
    price = _positive(current_price) or float(frame.iloc[-1]['close'])
    ema20 = float(frame['close'].ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(
        frame['close'].ewm(span=min(50, len(frame)), adjust=False).mean().iloc[-1]
    )
    recent_return = _pct_change(frame['close'], 5)
    score = 50.0
    score += 15.0 if price >= ema20 else -15.0
    score += 15.0 if price >= ema50 else -15.0
    score += 10.0 if ema20 >= ema50 else -10.0
    score += _clamp(recent_return * 300.0, -10.0, 10.0)
    return _bounded_score(score), {
        'bar_count': len(frame),
        'price': round(price, 8),
        'ema20': round(ema20, 8),
        'ema50': round(ema50, 8),
        'recent_return': round(recent_return, 8),
    }


def _timeframe_score(
    bars: list[dict[str, Any]],
    *,
    purpose: str,
) -> tuple[float | None, dict[str, Any]]:
    frame = _frame_from_bars(bars)
    if frame is None or len(frame) < 2:
        return None, {
            'bar_count': 0 if frame is None else len(frame),
            'note': f'{purpose}_timeframe_insufficient',
        }
    close = float(frame.iloc[-1]['close'])
    fast = float(
        frame['close'].ewm(span=min(5, len(frame)), adjust=False).mean().iloc[-1]
    )
    slow = float(
        frame['close'].ewm(span=min(12, len(frame)), adjust=False).mean().iloc[-1]
    )
    short_return = _pct_change(frame['close'], min(3, len(frame) - 1))
    slope = _pct_change(frame['close'], min(2, len(frame) - 1))
    score = 50.0
    score += 18.0 if close >= fast else -18.0
    score += 18.0 if fast >= slow else -18.0
    score += _clamp(short_return * 500.0, -14.0, 14.0)
    score += _clamp(slope * 300.0, -8.0, 8.0)
    return _bounded_score(score), {
        'bar_count': len(frame),
        'close': round(close, 8),
        'ema_fast': round(fast, 8),
        'ema_slow': round(slow, 8),
        'short_return': round(short_return, 8),
        'slope': round(slope, 8),
    }


def _volume_price_score(
    bars: list[dict[str, Any]],
) -> tuple[float | None, dict[str, Any]]:
    frame = _frame_from_bars(bars)
    if frame is None or len(frame) < 2:
        return None, {
            'bar_count': 0 if frame is None else len(frame),
            'note': 'volume_price_insufficient',
        }
    latest = frame.iloc[-1]
    average_volume = float(frame['volume'].tail(min(20, len(frame))).mean())
    volume_ratio = float(latest['volume']) / average_volume if average_volume > 0 else 1.0
    spread = max(0.0, float(latest['high']) - float(latest['low']))
    close_location = (
        (float(latest['close']) - float(latest['low'])) / spread if spread > 0 else 0.5
    )
    score = 50.0 + _clamp((volume_ratio - 1.0) * 35.0, -20.0, 20.0)
    score += _clamp((close_location - 0.5) * 30.0, -15.0, 15.0)
    return _bounded_score(score), {
        'bar_count': len(frame),
        'volume_ratio': round(volume_ratio, 8),
        'close_location': round(close_location, 8),
    }


def _volatility_fit_score(
    *,
    daily_bars: list[dict[str, Any]] | None,
    frames: dict[int, list[dict[str, Any]]],
    current_price: float | None,
) -> tuple[float | None, dict[str, Any]]:
    price = _positive(current_price)
    source = _frame_from_bars(daily_bars)
    source_name = 'daily'
    if source is None or len(source) < 15:
        source_name = '60m'
        source = _frame_from_bars(frames[60])
    if price is None and source is not None and not source.empty:
        price = float(source.iloc[-1]['close'])
    if source is None or len(source) < 2 or not price or price <= 0:
        return None, {'note': 'volatility_fit_insufficient'}
    prev_close = source['close'].shift(1)
    true_range = pd.concat(
        [
            source['high'] - source['low'],
            (source['high'] - prev_close).abs(),
            (source['low'] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = float(true_range.tail(min(14, len(true_range))).mean())
    atr_pct = atr / price if price > 0 else 1.0
    # Moderate volatility fits the intended -2% stop / +5% target structure.
    score = 100.0 - abs(atr_pct - 0.02) * 2_500.0
    return _bounded_score(score), {
        'source': source_name,
        'atr': round(atr, 8),
        'atr_pct': round(atr_pct, 8),
        'stop_loss_pct': 0.02,
        'take_profit_pct': 0.05,
    }


def _data_quality(
    *,
    daily_bars: list[dict[str, Any]] | None,
    intraday_bars: list[dict[str, Any]] | None,
    frames: dict[int, list[dict[str, Any]]],
    available_weight: float,
) -> float:
    daily_factor = min(1.0, len(daily_bars or []) / 50.0)
    raw_factor = min(1.0, len(intraday_bars or []) / 120.0)
    timeframe_factor = sum(1 for bars in frames.values() if len(bars) >= 2) / 3.0
    component_factor = available_weight / sum(ENTRY_TIMING_WEIGHTS.values())
    return round(
        min(
            1.0,
            max(
                0.0,
                (daily_factor + raw_factor + timeframe_factor + component_factor) / 4.0,
            ),
        ),
        4,
    )


def _trend_state(
    *,
    direction: str,
    daily_score: float | None,
    context_60: float | None,
    momentum_30: float | None,
    timing_15: float | None,
) -> str:
    context_average = _average_available(
        tuple(value for value in (daily_score, context_60) if value is not None),
        default=50.0,
    )
    momentum = momentum_30 if momentum_30 is not None else 50.0
    timing = timing_15 if timing_15 is not None else 50.0
    if context_average >= 58.0 and timing <= 45.0 and momentum >= 42.0:
        return 'bullish_pullback'
    if context_average >= 58.0 and momentum >= 50.0:
        return 'bullish_continuation'
    if context_average <= 42.0 and momentum <= 45.0:
        return 'bearish'
    if direction == 'bearish' and context_average < 50.0:
        return 'bearish_deterioration'
    return 'neutral'


def _direction(
    entry_score: float,
    daily_score: float | None,
    context_60: float | None,
    momentum_30: float | None,
) -> str:
    average = _average_available(
        tuple(value for value in (daily_score, context_60, momentum_30) if value is not None),
        default=entry_score,
    )
    if average >= 58.0:
        return 'bullish'
    if average <= 42.0:
        return 'bearish'
    return 'neutral'


def _reason(
    *,
    entry_score: float,
    trend_state: str,
    data_quality: float,
    missing: list[str],
) -> str:
    if data_quality <= 0:
        return 'B unavailable: no valid intraday or daily bars'
    missing_text = '; missing=' + ','.join(missing) if missing else ''
    return (
        f'B {trend_state}; entry_score_b={entry_score:.2f}; '
        f'data_quality_b={data_quality:.2f}{missing_text}'
    )


def _pct_change(series: pd.Series, periods: int) -> float:
    if len(series) <= periods:
        return 0.0
    first = float(series.iloc[-periods - 1])
    last = float(series.iloc[-1])
    return (last - first) / first if first else 0.0


def _average_available(values: tuple[float | None, ...], *, default: float) -> float:
    valid = [float(value) for value in values if value is not None]
    return sum(valid) / len(valid) if valid else default


def _bounded_score(value: float) -> float:
    return round(min(100.0, max(0.0, float(value))), 2)


def _score_or_zero(value: float | None) -> float:
    return _bounded_score(value if value is not None else 0.0)


def _positive(value: Any) -> float | None:
    number = _finite(value)
    return number if number is not None and number > 0 else None


def _finite(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
