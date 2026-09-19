from __future__ import annotations

import math
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.services.entry_timing_quant_service import resample_intraday_bars

KST = ZoneInfo('Asia/Seoul')
WEIGHTS = {
    'oversold_score_c': 20.0,
    'macd_reversal_score_c': 25.0,
    'price_stabilization_score_c': 20.0,
    'intraday_reversal_score_c': 25.0,
    'volume_confirmation_score_c': 10.0,
}


class ReversalQuantService:
    '''Deterministic read-only reversal score.'''

    def score(self, *, current_price: float | None,
              daily_bars: list[dict[str, Any]] | None,
              intraday_bars: list[dict[str, Any]] | None,
              decision_timestamp: datetime | None = None) -> dict[str, Any]:
        decision = _as_kst(decision_timestamp)
        daily = _normalize_daily(daily_bars or [], before=decision.date())
        raw = intraday_bars or []
        frames = {
            m: resample_intraday_bars(raw, timeframe_minutes=m,
               decision_timestamp=decision)
            for m in (15, 30, 60)
        }
        d = _daily_metrics(daily)
        f30, f15, f60 = (_frame_metrics(frames[m]) for m in (30, 15, 60))
        price = _positive(current_price)
        parts = {
            'oversold_score_c': _oversold_score(d),
            'macd_reversal_score_c': _macd_score(f30),
            'price_stabilization_score_c': _stabilization_score(f30, f15, price),
            'intraday_reversal_score_c': _intraday_score(f30, f15, f60),
            'volume_confirmation_score_c': _volume_score(f15),
        }
        score = _bounded(sum((parts[k] or 0.0) * w for k, w in WEIGHTS.items()) / 100.0)
        risk = _continuation_risk(d, f30, f15, f60)
        quality = _data_quality(daily, frames, parts)
        state = _state(score, risk, parts, d, f30, f15)
        direction = 'bullish' if score >= 58 and risk < 65 else 'bearish' if risk >= 60 and score < 50 else 'neutral'
        confidence = round(min(1.0, max(0.0, quality * (0.35 + score / 150.0))), 4)
        notes = [
            'Deterministic reversal score, not a future-price probability.',
            'Daily context, primary 30m confirmation, immediate 15m confirmation; 60m supporting only.',
            'Incomplete/future intraday buckets excluded with B conservative resampling.',
        ]
        missing = [k for k, v in parts.items() if v is None]
        if missing:
            notes.append('missing_components=' + ','.join(missing))
        if risk >= 65:
            notes.append('downtrend_continuation_risk_is_elevated')
        if (d.get('rsi') or 100) <= 30 and (d.get('rsi_slope') or 0) <= 0:
            notes.append('oversold_without_daily_rsi_recovery')
        return {
            'reversal_score_c': score,
            **{k: None if v is None else _bounded(v) for k, v in parts.items()},
            'downtrend_continuation_risk_c': risk,
            'reversal_state_c': state, 'direction_c': direction,
            'confidence_c': confidence, 'data_quality_c': quality,
            'c_reason': f'C {state}; score={score:.2f}; continuation_risk={risk:.2f}; quality={quality:.2f}',
            'c_notes': notes,
            'timeframe_bar_counts': {'daily': len(daily), **{f'{m}m': len(frames[m]) for m in (15,30,60)}},
            'indicator_snapshot': {
                'daily': d, '15m': f15, '30m': f30, '60m': f60,
                'current_price': _round(price), 'weights': dict(WEIGHTS),
            },
        }


def _daily_metrics(bars):
    closes = [float(b['close']) for b in bars]
    if len(closes) < 2:
        return {'bar_count': len(closes)}
    rsi = _rsi(closes)
    prior_rsi = _rsi(closes[:-3]) if len(closes) > 16 else None
    ema20 = _ema(closes, min(20, len(closes)))[-1]
    recent = closes[-6:]
    return {
        'bar_count': len(closes), 'rsi': _round(rsi),
        'rsi_slope': _round(rsi-prior_rsi if rsi is not None and prior_rsi is not None else None),
        'recent_return_5d': _round(_pct(closes, min(5, len(closes)-1))),
        'recent_drawdown_5d': _round(min(recent)/max(recent)-1),
        'ema20': _round(ema20),
        'ema20_distance_pct': _round(closes[-1]/ema20-1 if ema20 else None),
        'macd_context': _macd(closes),
    }


def _frame_metrics(bars):
    closes = [float(b['close']) for b in bars if _positive(b.get('close'))]
    if len(closes) < 2:
        return {'bar_count': len(closes)}
    lows = [float(b.get('low') or b['close']) for b in bars]
    vols = [max(0.0, _finite(b.get('volume'), 0.0) or 0.0) for b in bars]
    recent = min(lows[-min(4, len(lows)):])
    prior_rows = lows[-min(8, len(lows)):-min(4, len(lows))]
    prior = min(prior_rows) if prior_rows else min(lows[:-1])
    ema = _ema(closes, min(5, len(closes)))[-1]
    past = vols[-min(20, len(vols)):-1]
    avg_vol = sum(past)/len(past) if past else 0.0
    last = bars[-1]
    high, low = float(last.get('high') or last['close']), float(last.get('low') or last['close'])
    spread = max(0.0, high-low)
    return {
        **_macd(closes), 'bar_count': len(closes), 'close': _round(closes[-1]),
        'ema_fast': _round(ema), 'price_above_ema_fast': closes[-1] >= ema,
        'momentum_1bar': _round(_pct(closes, 1)),
        'momentum_3bar': _round(_pct(closes, min(3, len(closes)-1))),
        'momentum_slope': _round(_pct(closes,2)-_pct(closes[:-1],2) if len(closes)>=4 else None),
        'recent_low': _round(recent), 'prior_low': _round(prior),
        'higher_low': recent > prior*1.001, 'lower_low': recent < prior*.995,
        'fresh_lower_low': lows[-1] <= min(lows[:-1]),
        'volume_ratio': _round(vols[-1]/avg_vol if avg_vol else None),
        'close_location': _round((closes[-1]-low)/spread if spread else .5),
        'latest_bar_return': _round(_pct(closes,1)),
    }


def _oversold_score(daily):
    rsi = _finite(daily.get('rsi'))
    pressure = _finite(daily.get('recent_return_5d'))
    if rsi is None:
        return None
    value = 86.0 if rsi <= 25 else 70+(30-rsi)*3.2 if rsi <= 30 else 42+(42-rsi)*2.3 if rsi < 42 else max(0,42-(rsi-42)*1.4)
    if pressure is not None:
        value += _clamp(-pressure*180, -12, 12)
    slope = _finite(daily.get('rsi_slope'))
    if slope is not None:
        value += 6 if slope > 2 else -8 if slope < -2 else 0
    return _bounded(value)


def _macd_score(frame):
    hist, slope = _finite(frame.get('macd_histogram')), _finite(frame.get('macd_histogram_slope'))
    line, signal = _finite(frame.get('macd_line')), _finite(frame.get('macd_signal'))
    if any(v is None for v in (hist, slope, line, signal)):
        return None
    scale = max(abs(line), abs(signal), 1e-9)
    score = 32 + _clamp(slope/scale*90, -28, 28)
    score += 24 if hist >= 0 else 12 if slope > 0 else -12 if slope < 0 else 0
    score += 20 if line >= signal else 8 if (signal-line)/scale < .12 and slope > 0 else 0
    return _bounded(score)


def _stabilization_score(f30, f15, price):
    if f30.get('bar_count',0) < 2 and f15.get('bar_count',0) < 2:
        return None
    score = 30
    score += 28 if f30.get('higher_low') else -20 if f30.get('lower_low') else 0
    score += 16 if f30.get('fresh_lower_low') is False else -12 if f30.get('fresh_lower_low') else 0
    score += 16 if f15.get('higher_low') else -10 if f15.get('lower_low') else 0
    if price and f30.get('recent_low'):
        gap = price/float(f30['recent_low'])-1
        score += 10 if gap >= .015 else 5 if gap >= .005 else -10 if gap < 0 else 0
    return _bounded(score)


def _intraday_score(f30, f15, f60):
    if f30.get('bar_count',0) < 2 and f15.get('bar_count',0) < 2:
        return None
    score = 30
    if f30.get('bar_count',0) >= 2:
        score += 15 if float(f30.get('momentum_slope') or 0) > 0 else -12
        score += 15 if float(f30.get('momentum_3bar') or 0) > 0 else -10
        score += 14 if f30.get('higher_low') else -15 if f30.get('lower_low') else 0
    if f15.get('bar_count',0) >= 2:
        score += 12 if f15.get('price_above_ema_fast') else -8
        score += 12 if float(f15.get('momentum_1bar') or 0) > 0 else -8
        score += 10 if f15.get('higher_low') else -10 if f15.get('lower_low') else 0
    if f60.get('bar_count',0) >= 2 and float(f60.get('momentum_3bar') or 0) < -.03:
        score -= 8
    return _bounded(score)


def _volume_score(f15):
    ratio = _finite(f15.get('volume_ratio'))
    location = _finite(f15.get('close_location'))
    change = _finite(f15.get('latest_bar_return'))
    if any(v is None for v in (ratio,location,change)):
        return None
    score = 35 + _clamp((ratio-1)*24, -15, 25) + _clamp((location-.5)*32, -12, 12)
    score += 18 if change > 0 else -18 if change < 0 and ratio >= 1.4 else 0
    return _bounded(score)


def _continuation_risk(d, f30, f15, f60):
    if d.get('bar_count',0) < 2 and f30.get('bar_count',0) < 2:
        return 0.0
    risk = 12.0
    ret = float(d.get('recent_return_5d') or 0)
    risk += 24 if ret < -.08 else 15 if ret < -.04 else 8 if ret < -.02 else 0
    risk += 12 if float(d.get('rsi_slope') or 0) < -4 else 0
    hist, slope = float(f30.get('macd_histogram') or 0), float(f30.get('macd_histogram_slope') or 0)
    risk += 22 if hist < 0 and slope < 0 else 12 if hist < 0 and slope <= 0 else 0
    risk += 18 if f30.get('lower_low') or f30.get('fresh_lower_low') else 0
    risk += 12 if f15.get('lower_low') or f15.get('fresh_lower_low') else 0
    risk += 12 if float(f15.get('latest_bar_return') or 0) < 0 and float(f15.get('volume_ratio') or 0) > 1.5 else 0
    risk += 8 if f60.get('bar_count',0) >= 2 and float(f60.get('momentum_3bar') or 0) < -.04 else 0
    return _bounded(risk)


def _state(score, risk, parts, daily, f30, f15):
    oversold = parts['oversold_score_c']
    confirm = float(f30.get('macd_histogram_slope') or 0) > 0 and float(f15.get('momentum_1bar') or 0) > 0
    if risk >= 72 and score < 52:
        return 'downtrend_continuation'
    if oversold is not None and oversold >= 65 and not confirm:
        return 'failed_reversal' if risk >= 60 else 'oversold_only'
    if score >= 70 and confirm and (parts['price_stabilization_score_c'] or 0) >= 55:
        return 'reversal_confirmed'
    if score >= 48 and (confirm or float(f30.get('macd_histogram_slope') or 0) > 0):
        return 'reversal_forming'
    return 'oversold_only' if oversold is not None and oversold >= 55 else 'neutral'


def _data_quality(daily, frames, parts):
    daily_quality = min(1.0, len(daily)/40.0)
    frame_quality = sum(len(frames[m]) >= 2 for m in (15,30,60))/3.0
    component_quality = sum(WEIGHTS[k] for k,v in parts.items() if v is not None)/100.0
    return round(min(1.0, max(0.0, (daily_quality+frame_quality+component_quality)/3.0)),4)


def _normalize_daily(bars, *, before):
    result = []
    for row in bars:
        if not isinstance(row, dict):
            continue
        stamp = row.get('timestamp') or row.get('datetime') or row.get('date')
        parsed = _parse_time(stamp)
        # Never use the current-session aggregate daily candle.
        if parsed is None or parsed.date() >= before:
            continue
        values = {k:_positive(row.get(k)) for k in ('open','high','low','close')}
        if any(v is None for v in values.values()) or values['high'] < values['low']:
            continue
        result.append({**values, 'volume':max(0.0,_finite(row.get('volume'),0.0) or 0.0), 'timestamp':str(stamp)})
    return sorted(result, key=lambda row:row['timestamp'])


def _macd(closes):
    if len(closes) < 2:
        return {}
    fast, slow = _ema(closes,12), _ema(closes,26)
    line = [a-b for a,b in zip(fast,slow)]
    signal = _ema(line,9)
    hist = [line[i]-signal[i] for i in range(len(line))]
    return {
        'macd_line':_round(line[-1]), 'macd_signal':_round(signal[-1]),
        'macd_histogram':_round(hist[-1]),
        'macd_histogram_slope':_round(hist[-1]-hist[-2] if len(hist)>1 else None),
    }


def _ema(values, period):
    if not values:
        return []
    alpha = 2.0/(max(1,period)+1.0)
    result = [float(values[0])]
    for value in values[1:]:
        result.append(alpha*float(value)+(1-alpha)*result[-1])
    return result


def _rsi(values, period=14):
    changes = [float(values[i])-float(values[i-1]) for i in range(1,len(values))][-period:]
    if not changes:
        return None
    gains = sum(max(0.0,x) for x in changes)/len(changes)
    losses = sum(max(0.0,-x) for x in changes)/len(changes)
    if losses <= 1e-12:
        return 100.0 if gains > 1e-12 else 50.0
    return 100.0-100.0/(1.0+gains/losses)


def _pct(values, periods):
    if len(values) <= periods or not values[-periods-1]:
        return 0.0
    return (float(values[-1])-float(values[-periods-1]))/float(values[-periods-1])


def _parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z','+00:00'))
    except (TypeError,ValueError):
        try:
            parsed = datetime.fromisoformat(str(value)[:10])
        except (TypeError,ValueError):
            return None
    return parsed.replace(tzinfo=KST) if parsed.tzinfo is None else parsed.astimezone(KST)


def _as_kst(value):
    current = value or datetime.now(KST)
    return current.replace(tzinfo=KST) if current.tzinfo is None else current.astimezone(KST)


def _positive(value):
    number = _finite(value)
    return number if number is not None and number > 0 else None


def _finite(value, default=None):
    try:
        number = float(value)
    except (TypeError,ValueError):
        return default
    return number if math.isfinite(number) else default


def _bounded(value):
    return round(min(100.0,max(0.0,float(value))),2)


def _round(value):
    return None if value is None else round(float(value),8)


def _clamp(value, lower, upper):
    return min(upper,max(lower,value))
