from __future__ import annotations

import math
from datetime import datetime, timedelta
from statistics import fmean, pstdev
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
MINUTE = timedelta(minutes=1)
TIMEFRAMES = (5, 10, 15, 30, 60)


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=KST) if parsed.tzinfo is None else parsed.astimezone(KST)


def number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def minute_bars(rows, session_open, cutoff):
    """Keep unique, valid, completed regular-session bars with minute-open labels."""
    bars = {}
    conflicts = set()
    for row in rows:
        at = timestamp(row.get("timestamp") or row.get("datetime"))
        if not at or at.second or at.microsecond or not session_open <= at <= cutoff - MINUTE:
            continue
        prices = {key: number(row.get(key)) for key in ("open", "high", "low", "close")}
        if any(value is None or value <= 0 for value in prices.values()):
            continue
        if not prices["low"] <= min(prices["open"], prices["close"]) <= max(
            prices["open"], prices["close"]
        ) <= prices["high"]:
            continue
        bar = {**prices, "timestamp": at.isoformat(), "volume": max(0, number(row.get("volume")) or 0)}
        if at in bars and bars[at] != bar:
            conflicts.add(at)
        bars[at] = bar
    return {at: bars[at] for at in sorted(bars) if at not in conflicts}


def completed_frames(bars, session_open):
    frames = {}
    for minutes in TIMEFRAMES:
        aggregates = {}
        for at, bar in bars.items():
            bucket = int((at - session_open) / MINUTE) // minutes
            aggregates.setdefault(bucket, []).append(bar)
        frames[minutes] = [
            {
                "timestamp": group[0]["timestamp"],
                "open": group[0]["open"], "close": group[-1]["close"],
                "high": max(bar["high"] for bar in group),
                "low": min(bar["low"] for bar in group),
                "volume": sum(bar["volume"] for bar in group),
            }
            for group in aggregates.values() if len(group) == minutes
        ]
    return frames


def aligned_returns(stock, index):
    if not stock:
        return {}
    end = max(stock)
    if end not in index or index[end] <= 0:
        return {}
    relative = {}
    for minutes in (5, 10, 30, 60):
        start = end - MINUTE * minutes
        if start in stock and start in index and index[start] > 0:
            stock_return = stock[end]["close"] / stock[start]["close"] - 1
            index_return = index[end] / index[start] - 1
            relative[f"{minutes}m"] = stock_return - index_return
    return relative


def adjusted_daily(daily, events, decision):
    """Apply point-in-time, verified changes to analytical daily prices only."""
    adjusted = [dict(bar) for bar in daily]
    applied = []
    for event in sorted(events, key=lambda item: item.get("event_date") or ""):
        event_at = timestamp(event.get("event_date"))
        published = timestamp(event.get("publication_timestamp") or event.get("first_seen_at"))
        if not event_at or event_at.date() > decision.date() or not published or published > decision:
            continue
        if event.get("verification_status") != "verified":
            continue
        factor = number(event.get("historical_price_multiplier"))
        if factor is None and event.get("event_type") == "ex_dividend_date":
            prior = [bar for bar in adjusted if str(bar.get("timestamp") or bar.get("date"))[:10] < event_at.date().isoformat()]
            previous = number(prior[-1]["close"]) if prior else None
            amount = number(event.get("amount"))
            if previous and amount and 0 < amount < previous:
                factor = 1 - amount / previous
        if factor is None or factor <= 0:
            continue
        for bar in adjusted:
            if str(bar.get("timestamp") or bar.get("date"))[:10] < event_at.date().isoformat():
                for key in ("open", "high", "low", "close"):
                    value = number(bar.get(key))
                    if value is not None:
                        bar[key] = value * factor
        applied.append(event.get("source_reference"))
    return adjusted, applied


def _frame_features(bars, price):
    if len(bars) < 2:
        return {"bar_count": len(bars)}
    prior, last = bars[-2:]
    recent = bars[-14:]
    atr = fmean(max(bar["high"] - bar["low"], abs(bar["high"] - prev["close"]),
                    abs(bar["low"] - prev["close"])) for prev, bar in zip(recent, recent[1:]))
    return {
        "bar_count": len(bars), "recent_candles": bars[-3:],
        "return": last["close"] / prior["close"] - 1,
        "higher_low": last["low"] > prior["low"],
        "lower_high": last["high"] < prior["high"],
        "fresh_lower_low": last["low"] < min(bar["low"] for bar in bars[-6:-1]),
        "upper_wick_pct": (last["high"] - max(last["open"], last["close"])) / price,
        "lower_wick_pct": (min(last["open"], last["close"]) - last["low"]) / price,
        "atr": atr, "atr_pct": atr / price,
    }


def build_features(*, minute, frames, daily, entry, entry_source, schedule, session_open=None):
    bars = list(minute.values())
    trend = {f"{m}m": _frame_features(rows, entry) for m, rows in frames.items()}
    volumes = [bar["volume"] for bar in bars]
    volume = sum(volumes)
    vwap = sum((b["high"] + b["low"] + b["close"]) / 3 * b["volume"] for b in bars) / volume if volume else None
    vwap_state = []
    total_value = total_volume = 0.0
    for bar in bars:
        total_volume += bar["volume"]
        total_value += (bar["high"] + bar["low"] + bar["close"]) / 3 * bar["volume"]
        if total_volume:
            vwap_state.append(bar["close"] >= total_value / total_volume)
    up = [b["volume"] for b in bars[-30:] if b["close"] > b["open"]]
    down = [b["volume"] for b in bars[-30:] if b["close"] < b["open"]]
    recent = bars[-30:]
    supports = [b["low"] for b in recent if b["low"] <= entry]
    resistances = [b["high"] for b in recent if b["high"] >= entry]
    trough_at = min(range(len(recent)), key=lambda i: recent[i]["low"])
    trough = recent[trough_at]["low"]
    sl = schedule["effective_stop_loss_pct"] if schedule["stop_loss_enabled"] else None
    tp = schedule["effective_take_profit_pct"] if schedule["take_profit_enabled"] else None
    atr_pct = trend["10m"].get("atr_pct")
    pressure = [sum(b["volume"] for b in segment if b["close"] < b["open"])
                for segment in (bars[-20:-10], bars[-10:])]
    return {
        "timeframes": trend, "entry_reference": entry, "entry_source": entry_source,
        "stop_loss_price": entry * (1 - sl) if sl is not None else None,
        "take_profit_price": entry * (1 + tp) if tp is not None else None,
        "potential_reward_to_risk": tp / sl if tp and sl else None,
        "stop_loss_distance_atr": sl / atr_pct if sl is not None and atr_pct else None,
        "financial_loss_magnitude": sl,
        "recent_downside_pct": {
            f"{m}m": min(b["low"] for b in bars[-m:]) / bars[-m]["open"] - 1
            for m in (30, 60) if len(bars) >= m
        },
        "realized_minute_volatility": pstdev([
            math.log(b["close"] / a["close"]) for a, b in zip(bars[-61:], bars[-60:])
        ]) if len(bars) >= 61 else None,
        "rebound_pct": bars[-1]["close"] / trough - 1,
        "minutes_since_recent_low": (len(recent) - 1 - trough_at),
        "pullback_from_recent_high_pct": entry / max(b["high"] for b in recent) - 1,
        "up_candle_volume": sum(up), "down_candle_volume": sum(down),
        "rebound_average_volume": fmean(up) if up else None,
        "pullback_average_volume": fmean(down) if down else None,
        "down_candle_volume_change_10m": pressure[1] / pressure[0] - 1 if pressure[0] else None,
        "session_vwap": vwap, "entry_vs_vwap_pct": entry / vwap - 1 if vwap else None,
        "vwap_session_coverage": "from_open" if minute and min(minute) == session_open
        and max(minute) - min(minute) == MINUTE * (len(minute) - 1) else "partial",
        "vwap_reclaim": not all(vwap_state) and bool(vwap_state[-1]) if vwap_state else None,
        "vwap_above_last_five": sum(vwap_state[-5:]) if len(vwap_state) >= 5 else None,
        "vwap_retest": (
            "held" if vwap and bars[-1]["low"] <= vwap <= bars[-1]["close"] else
            "failed" if vwap and bars[-1]["close"] < vwap <= bars[-1]["high"] else None
        ),
        "previous_day_high": daily[-1]["high"] if daily else None,
        "previous_day_low": daily[-1]["low"] if daily else None,
        "session_high": max(b["high"] for b in bars), "session_low": min(b["low"] for b in bars),
        "support": max(supports) if supports else None,
        "resistance": min(resistances) if resistances else None,
        "support_distance_pct": 1 - max(supports) / entry if supports else None,
        "resistance_distance_pct": min(resistances) / entry - 1 if resistances else None,
        "price_action_support": (
            trend["10m"].get("higher_low", False)
            and not trend["30m"].get("fresh_lower_low", True)
            and trend["10m"].get("return", 0) > 0
        ),
    }
