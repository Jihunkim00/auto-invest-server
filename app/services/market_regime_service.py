from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import MarketRegimeSnapshot
from app.services.market_regime_provider import YahooFinanceMarketRegimeProvider


KST = ZoneInfo("Asia/Seoul")
TIMEZONES = {"KOSPI": ZoneInfo("Asia/Seoul"), "NASDAQ": ZoneInfo("America/New_York")}
CLOSES = {"KOSPI": time(15, 30), "NASDAQ": time(16, 0)}
MIN_WEEKLY_BARS = 200
BULLISH_SCORE_THRESHOLD = 60.0
BEARISH_SCORE_THRESHOLD = 40.0
KOSPI_BULLISH_SCORE_THRESHOLD = 55.0
NASDAQ_BULLISH_SCORE_THRESHOLD = 50.0
KOSPI_BEARISH_SCORE_THRESHOLD = 45.0
DRAWDOWN_BEARISH_THRESHOLD = 15.0
THREE_WEEK_CHANGE_THRESHOLD = 5.0
CONFIRMATION_WEEKS = 2
KOSPI_WEIGHT = 0.60
NASDAQ_WEIGHT = 0.40

STAGES = {
    1: ("falling", "하락 진행", "하락", "중장기 하락 추세"),
    2: ("bottoming", "하락 둔화·바닥 탐색", "바닥 탐색", "하락이 둔화되며 반전을 탐색"),
    3: ("bullish_reversal_confirmed", "상승 전환 확인", "상승 전환", "상승 전환 확인"),
    4: ("rising", "상승 진행", "상승", "중장기 상승 추세"),
    5: ("topping_or_sideways", "상승 둔화·고점권", "상승 둔화", "상승 둔화 또는 고점권 흐름"),
    6: ("bearish_reversal_confirmed", "하락 전환 확인", "하락 전환", "하락 전환 확인"),
}


@dataclass(frozen=True)
class MarketMetric:
    week_ending: date
    close: float
    ema20: float
    ema40: float
    ema20_4w_slope: float
    macd_histogram: float
    rsi14: float
    atr14: float
    trend_score: float
    momentum_score: float
    rsi_score: float
    market_score: float
    drawdown_52w: float | None


@dataclass(frozen=True)
class PairedWeek:
    week_ending: date
    kospi: MarketMetric
    nasdaq: MarketMetric
    kospi_score: float
    nasdaq_score: float
    combined_score: float
    score_change_3w: float | None
    nasdaq_score_3w_ago: float | None


def _finite(value):
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _number(value):
    return float(value) if _finite(value) else None


def _rounded(value):
    return round(float(value), 4) if _finite(value) else None


def normalize(value):
    return min(100.0, max(0.0, 50.0 + 25.0 * float(value))) if _finite(value) else None


def calculate_trend_score(close, ema20, ema40, ema20_4w_ago, atr14):
    if not all(_finite(v) for v in (close, ema20, ema40, ema20_4w_ago, atr14)) or atr14 <= 0:
        return None
    parts = (
        normalize((close - ema20) / atr14),
        normalize((ema20 - ema40) / atr14),
        normalize((ema20 - ema20_4w_ago) / (0.5 * atr14)),
    )
    return None if any(v is None for v in parts) else 0.4 * parts[0] + 0.3 * parts[1] + 0.3 * parts[2]


def calculate_momentum_score(histogram, histogram_3w_ago, atr14):
    if not all(_finite(v) for v in (histogram, histogram_3w_ago, atr14)) or atr14 <= 0:
        return None
    level = normalize(histogram / (0.5 * atr14))
    change = normalize((histogram - histogram_3w_ago) / (0.25 * atr14))
    return None if level is None or change is None else 0.4 * level + 0.6 * change


def calculate_rsi_score(rsi14):
    return min(100.0, max(0.0, 50.0 + 2.5 * (rsi14 - 50.0))) if _finite(rsi14) else None


def combine_market_scores(kospi_score, nasdaq_score):
    if not _finite(kospi_score) or not _finite(nasdaq_score):
        return None
    return KOSPI_WEIGHT * kospi_score + NASDAQ_WEIGHT * nasdaq_score


def _week_ending(raw, timezone):
    raw_date = raw.get("week_ending")
    if raw_date:
        try:
            return date.fromisoformat(str(raw_date)[:10])
        except ValueError:
            pass
    timestamp = raw.get("timestamp")
    if not timestamp:
        return None
    try:
        text = str(timestamp).strip().replace("Z", "+00:00")
        try:
            instant = datetime.fromisoformat(text)
        except ValueError:
            return date.fromisoformat(text[:10])
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=UTC)
        day = instant.astimezone(timezone).date()
        return day + timedelta(days=(4 - day.weekday()) % 7)
    except (TypeError, ValueError, OverflowError):
        return None


def completed_weekly_bars(bars, *, market, as_of):
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("Market-regime calculations require a timezone-aware timestamp.")
    timezone = TIMEZONES[market]
    local_now = as_of.astimezone(timezone)
    grouped = {}
    for raw in bars or []:
        if not isinstance(raw, dict):
            continue
        week = _week_ending(raw, timezone)
        if week is None:
            continue
        closed = local_now.date() > week or (
            local_now.date() == week and local_now.timetz().replace(tzinfo=None) >= CLOSES[market]
        )
        if not closed:
            continue
        fields = {k: _number(raw.get(k)) for k in ("open", "high", "low", "close")}
        if any(v is None or v <= 0 for v in fields.values()):
            continue
        grouped[week] = {"week_ending": week, **fields, "volume": _number(raw.get("volume")) or 0.0}
    return [grouped[w] for w in sorted(grouped)]


def build_market_metrics(bars, *, market=None):
    if not bars:
        return []
    frame = pd.DataFrame(bars).sort_values("week_ending").reset_index(drop=True)
    close = pd.to_numeric(frame["close"], errors="coerce")
    high, low = pd.to_numeric(frame["high"], errors="coerce"), pd.to_numeric(frame["low"], errors="coerce")
    ema20 = close.ewm(span=20, adjust=False, min_periods=20).mean()
    ema40 = close.ewm(span=40, adjust=False, min_periods=40).mean()
    slope = ema20 - ema20.shift(4)
    macd = close.ewm(span=12, adjust=False, min_periods=12).mean() - close.ewm(span=26, adjust=False, min_periods=26).mean()
    histogram = macd - macd.ewm(span=9, adjust=False, min_periods=9).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=14).mean()
    rsi = (100.0 - 100.0 / (1.0 + gain / loss)).mask((loss == 0) & (gain > 0), 100.0).mask((loss == 0) & (gain == 0), 50.0)
    prior = close.shift(1)
    tr = pd.concat([high - low, (high - prior).abs(), (low - prior).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=14).mean()

    result = []
    for i, raw in frame.iterrows():
        values = (close.iloc[i], ema20.iloc[i], ema40.iloc[i], slope.iloc[i], histogram.iloc[i], rsi.iloc[i], atr.iloc[i])
        if not all(_finite(v) for v in values):
            continue
        c, e20, e40, sl, hist, rv, av = (float(v) for v in values)
        if av <= 0:
            continue
        e20_prior = float(ema20.iloc[i - 4]) if i >= 4 and _finite(ema20.iloc[i - 4]) else None
        hist_prior = float(histogram.iloc[i - 3]) if i >= 3 and _finite(histogram.iloc[i - 3]) else None
        trend = calculate_trend_score(c, e20, e40, e20_prior, av)
        momentum = calculate_momentum_score(hist, hist_prior, av)
        rsi_score = calculate_rsi_score(rv)
        if None in (trend, momentum, rsi_score):
            continue
        score = 0.4 * trend + 0.4 * momentum + 0.2 * rsi_score
        dd = None
        if i >= 51:
            peak = _number(close.iloc[i - 51:i + 1].max())
            if peak and peak > 0:
                dd = 100.0 * (1.0 - c / peak)
        result.append(MarketMetric(
            raw["week_ending"], c, e20, e40, sl, hist, rv, av,
            trend, momentum, rsi_score, score, dd,
        ))
    return result


def pair_market_metrics(kospi_metrics, nasdaq_metrics):
    km = {x.week_ending: x for x in kospi_metrics}
    nm = {x.week_ending: x for x in nasdaq_metrics}
    weeks = sorted(km.keys() & nm.keys())
    combined = {
        w: combine_market_scores(km[w].market_score, nm[w].market_score)
        for w in weeks
    }
    paired = []
    for week in weeks:
        prior_week = week - timedelta(weeks=3)
        prior_combined = combined.get(prior_week)
        prior_nasdaq = nm.get(prior_week)
        current_combined = combined[week]
        paired.append(PairedWeek(
            week_ending=week,
            kospi=km[week],
            nasdaq=nm[week],
            kospi_score=km[week].market_score,
            nasdaq_score=nm[week].market_score,
            combined_score=current_combined,
            score_change_3w=(
                current_combined - prior_combined
                if current_combined is not None and prior_combined is not None
                else None
            ),
            nasdaq_score_3w_ago=prior_nasdaq.market_score if prior_nasdaq else None,
        ))
    return paired


def _condition(key, label, passed, actual, rule):
    return {"key": key, "label": label, "passed": bool(passed), "actual": actual, "rule": rule}


def bullish_confirmation_conditions(stage_before, w):
    checks = [
        _condition("previous_stage", "이전 국면이 하락 진행 또는 바닥 탐색", stage_before in (1, 2), stage_before, "stage 1 or 2"),
        _condition("combined_score", "시장 점수 >= 60", w.combined_score >= 60, w.combined_score, ">= 60"),
        _condition("kospi_score", "KOSPI 점수 >= 55", w.kospi_score >= 55, w.kospi_score, ">= 55"),
        _condition("nasdaq_score", "NASDAQ 점수 >= 50", w.nasdaq_score >= 50, w.nasdaq_score, ">= 50"),
        _condition("nasdaq_score_not_lower_3w", "NASDAQ 점수가 3주 전보다 낮지 않음",
                   w.nasdaq_score_3w_ago is not None and w.nasdaq_score >= w.nasdaq_score_3w_ago,
                   {"current": w.nasdaq_score, "three_weeks_ago": w.nasdaq_score_3w_ago}, "current >= three weeks earlier"),
        _condition("kospi_above_ema20", "KOSPI 종가 > EMA20", w.kospi.close > w.kospi.ema20,
                   {"close": w.kospi.close, "ema20": w.kospi.ema20}, "close > EMA20"),
        _condition("kospi_ema20_slope_positive", "KOSPI EMA20 4주 기울기 > 0", w.kospi.ema20_4w_slope > 0, w.kospi.ema20_4w_slope, "> 0"),
        _condition("kospi_macd_histogram_positive", "KOSPI MACD 히스토그램 > 0", w.kospi.macd_histogram > 0, w.kospi.macd_histogram, "> 0"),
    ]
    return {"passed": sum(c["passed"] for c in checks), "total": len(checks), "conditions": checks, "eligible": all(c["passed"] for c in checks)}


def bearish_confirmation_conditions(w):
    below20 = w.kospi.close < w.kospi.ema20
    k = [
        _condition("kospi_close_below_ema20", "KOSPI 종가 < EMA20", below20, {"close": w.kospi.close, "ema20": w.kospi.ema20}, "close < EMA20"),
        _condition("kospi_histogram_negative", "KOSPI MACD 히스토그램 < 0", w.kospi.macd_histogram < 0, w.kospi.macd_histogram, "< 0"),
        _condition("kospi_close_below_ema40_or_drawdown", "KOSPI 종가 < EMA40 또는 52주 낙폭 >= 15%",
                   w.kospi.close < w.kospi.ema40 or (w.kospi.drawdown_52w is not None and w.kospi.drawdown_52w >= 15),
                   {"close": w.kospi.close, "ema40": w.kospi.ema40, "drawdown_52w": w.kospi.drawdown_52w},
                   "close < EMA40 or drawdown >= 15%"),
    ]
    c = [
        _condition("combined_score_bearish", "시장 점수 <= 40", w.combined_score <= 40, w.combined_score, "<= 40"),
        _condition("kospi_score_bearish", "KOSPI 점수 < 45", w.kospi_score < 45, w.kospi_score, "< 45"),
        _condition("kospi_close_below_ema20_combined", "KOSPI 종가 < EMA20", below20, {"close": w.kospi.close, "ema20": w.kospi.ema20}, "close < EMA20"),
    ]
    kp, cp = all(x["passed"] for x in k), all(x["passed"] for x in c)
    return {
        "passed": sum(x["passed"] for x in k + c), "total": len(k) + len(c), "eligible": kp or cp,
        "kospi_transition": {"passed": sum(x["passed"] for x in k), "total": len(k), "conditions": k, "eligible": kp},
        "combined_transition": {"passed": sum(x["passed"] for x in c), "total": len(c), "conditions": c, "eligible": cp},
        "conditions": k + c,
    }


def advance_regime_state(stage_before, w, *, bullish_streak=0, bearish_streak=0):
    bull = bullish_confirmation_conditions(stage_before, w)
    bear = bearish_confirmation_conditions(w)
    bs = bullish_streak + 1 if stage_before in (1, 2) and bull["eligible"] else 0
    ds = bearish_streak + 1 if stage_before in (3, 4, 5) and bear["eligible"] else 0
    stage, new_bull, new_bear = stage_before, False, False
    if bs >= CONFIRMATION_WEEKS:
        stage, new_bull, bs, ds = 3, stage_before != 3, 0, 0
    elif ds >= CONFIRMATION_WEEKS:
        stage, new_bear, ds, bs = 6, stage_before != 6, 0, 0
    elif stage_before is None:
        stage, bs, ds = _bootstrap_stage(w), 0, 0
    elif stage_before == 1:
        if w.combined_score < 60 and w.score_change_3w is not None and w.score_change_3w >= 5 and w.kospi.close <= w.kospi.ema20:
            stage = 2
    elif stage_before == 2:
        if w.combined_score <= 40 and w.score_change_3w is not None and w.score_change_3w <= -5 and w.kospi.close < w.kospi.ema20:
            stage = 1
    elif stage_before == 3 and _rising(w):
        stage = 4
    elif stage_before == 4:
        if (w.combined_score > 40 and w.score_change_3w is not None and w.score_change_3w <= -5) or (40 < w.combined_score < 60 and w.kospi.close >= w.kospi.ema20):
            stage = 5
    elif stage_before == 5:
        if _rising(w):
            stage = 4
        elif w.combined_score <= 40 and w.score_change_3w is not None and w.score_change_3w <= -5 and w.kospi.close < w.kospi.ema20:
            stage = 1
    elif stage_before == 6 and w.combined_score <= 40 and w.score_change_3w is not None and w.score_change_3w < 0 and w.kospi.close < w.kospi.ema20:
        stage = 1
    return {
        "stage": stage, "bullish_streak": bs, "bearish_streak": ds,
        "new_bullish_reversal": new_bull, "new_bearish_reversal": new_bear,
        "bullish_conditions": {**bull, "streak": bs, "required_streak": 2, "confirmed": stage == 3 and stage_before in (1, 2)},
        "bearish_conditions": {**bear, "streak": ds, "required_streak": 2, "confirmed": stage == 6 and stage_before in (3, 4, 5)},
    }


def _rising(w):
    return w.combined_score >= 60 and w.kospi.close > w.kospi.ema20 and w.kospi.ema20_4w_slope > 0


def _bootstrap_stage(w):
    if w.combined_score <= 40 and w.score_change_3w is not None and w.score_change_3w <= -5 and w.kospi.close < w.kospi.ema20:
        return 1
    if w.combined_score < 60 and w.score_change_3w is not None and w.score_change_3w >= 5 and w.kospi.close <= w.kospi.ema20:
        return 2
    if _rising(w):
        return 4
    if 40 < w.combined_score < 60 and w.kospi.close >= w.kospi.ema20 and w.score_change_3w is not None and w.score_change_3w <= 0:
        return 5
    return None


def _process_history(weeks, *, stage=None, bull=0, bear=0, state_week=None):
    prior, latest, bull_entry, bear_entry = state_week, {}, None, None
    for w in weeks:
        if prior and (w.week_ending - prior).days > 7:
            bull = bear = 0
        out = advance_regime_state(stage, w, bullish_streak=bull, bearish_streak=bear)
        if out["new_bullish_reversal"]:
            bull_entry = w.week_ending
        if out["new_bearish_reversal"]:
            bear_entry = w.week_ending
        stage, bull, bear, latest, prior = out["stage"], out["bullish_streak"], out["bearish_streak"], out, w.week_ending
    latest["bullish_entry_week"], latest["bearish_entry_week"] = bull_entry, bear_entry
    return stage, bull, bear, latest


class MarketRegimeService:
    def __init__(self, provider=None):
        self.provider = provider or YahooFinanceMarketRegimeProvider()

    def calculate_and_persist(self, db: Session, *, now=None):
        instant = _as_utc(now or datetime.now(UTC))
        day = instant.astimezone(KST).date()
        existing = db.query(MarketRegimeSnapshot).filter_by(calculation_date=day).first()
        if existing:
            return existing
        previous = db.query(MarketRegimeSnapshot).filter(MarketRegimeSnapshot.calculation_date < day).order_by(MarketRegimeSnapshot.calculation_date.desc()).first()
        try:
            fetched = self.provider.fetch_weekly_bars(as_of=instant) or {}
        except Exception as exc:
            fetched = {"kospi": [], "nasdaq": [], "data_source": {
                "kospi": {"provider": "unavailable", "error": type(exc).__name__},
                "nasdaq": {"provider": "unavailable", "error": type(exc).__name__}, "nasdaq_is_proxy": False,
            }}
        kb = completed_weekly_bars(fetched.get("kospi"), market="KOSPI", as_of=instant)
        nb = completed_weekly_bars(fetched.get("nasdaq"), market="NASDAQ", as_of=instant)
        km, nm = build_market_metrics(kb), build_market_metrics(nb)
        paired = pair_market_metrics(km, nm)
        kw, nw = (kb[-1]["week_ending"] if kb else None), (nb[-1]["week_ending"] if nb else None)
        latest = paired[-1] if paired else None
        enough = len(kb) >= MIN_WEEKLY_BARS and len(nb) >= MIN_WEEKLY_BARS and latest is not None
        aligned = enough and kw == nw == latest.week_ending

        stage = previous.stage if previous else None
        bull = previous.bullish_confirmation_streak if previous else 0
        bear = previous.bearish_confirmation_streak if previous else 0
        state_week = previous.state_week_ending if previous else None
        bull_detail = _json(previous.bullish_conditions_json if previous else None)
        bear_detail = _json(previous.bearish_conditions_json if previous else None)
        new_bull = new_bear = False
        status, confirmed = "insufficient_data", bool(previous.confirmed) if previous else False

        if enough and aligned:
            if previous is None or previous.state_week_ending is None:
                stage, bull, bear, out = _process_history(paired)
                bull_detail, bear_detail = out.get("bullish_conditions", {}), out.get("bearish_conditions", {})
                new_bull = out.get("bullish_entry_week") == latest.week_ending
                new_bear = out.get("bearish_entry_week") == latest.week_ending
            elif latest.week_ending > previous.state_week_ending:
                newer = [w for w in paired if w.week_ending > previous.state_week_ending]
                stage, bull, bear, out = _process_history(
                    newer, stage=stage, bull=bull, bear=bear, state_week=previous.state_week_ending
                )
                bull_detail, bear_detail = out.get("bullish_conditions", {}), out.get("bearish_conditions", {})
                new_bull = out.get("bullish_entry_week") == latest.week_ending
                new_bear = out.get("bearish_entry_week") == latest.week_ending
            else:
                stage, state_week = previous.stage, previous.state_week_ending
                bull_detail, bear_detail = _json(previous.bullish_conditions_json), _json(previous.bearish_conditions_json)
            state_week = max(state_week, latest.week_ending) if state_week else latest.week_ending
            status, confirmed = ("confirmed", True) if stage in STAGES else ("pending", False)
        elif enough:
            status, confirmed = "pending", bool(previous.confirmed) if previous else False

        source = dict(fetched.get("data_source") or {})
        for key, count in (("kospi", len(kb)), ("nasdaq", len(nb))):
            item = dict(source.get(key) or {})
            item["completed_weekly_bar_count"] = count
            source[key] = item
        source["nasdaq_is_proxy"] = bool((source.get("nasdaq") or {}).get("is_proxy") or source.get("nasdaq_is_proxy", False))
        row = MarketRegimeSnapshot(
            calculation_date=day, calculated_at=instant, calculation_timezone="Asia/Seoul",
            kospi_week_ending=kw, nasdaq_week_ending=nw, state_week_ending=state_week,
            kospi_score=_rounded(latest.kospi_score) if enough else None,
            nasdaq_score=_rounded(latest.nasdaq_score) if enough else None,
            combined_score=_rounded(latest.combined_score) if enough else None,
            score_change_3w=_rounded(latest.score_change_3w) if enough else None,
            stage=stage, stage_key=STAGES.get(stage, (None,))[0],
            stage_label=STAGES.get(stage, (None, None))[1],
            status=status, confirmed=bool(confirmed), new_bullish_reversal=new_bull,
            new_bearish_reversal=new_bear, bullish_confirmation_streak=bull,
            bearish_confirmation_streak=bear, **_diagnostics(latest),
            bullish_conditions_json=json.dumps(bull_detail or {}, ensure_ascii=False, allow_nan=False),
            bearish_conditions_json=json.dumps(bear_detail or {}, ensure_ascii=False, allow_nan=False),
            data_source_json=json.dumps(source, ensure_ascii=False, allow_nan=False),
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            row = db.query(MarketRegimeSnapshot).filter_by(calculation_date=day).first()
            if row is None:
                raise
            return row
        db.refresh(row)
        return row

    def get_current_payload(self, db: Session, *, now=None):
        row = db.query(MarketRegimeSnapshot).order_by(MarketRegimeSnapshot.calculation_date.desc(), MarketRegimeSnapshot.id.desc()).first()
        now = _as_utc(now or datetime.now(UTC))
        if row is None:
            return _empty_payload(now)
        info = STAGES.get(row.stage)
        return {
            "status": row.status, "stage": row.stage, "stage_key": row.stage_key, "stage_label": row.stage_label,
            "short_label": info[2] if info else ("확정 대기" if row.status == "pending" else "데이터 없음"),
            "summary": info[3] if info else "주간 국면을 확인할 데이터가 부족합니다.",
            "market_score": row.combined_score, "score_change_3w": row.score_change_3w,
            "kospi_score": row.kospi_score, "nasdaq_score": row.nasdaq_score,
            "kospi_week": _date_text(row.kospi_week_ending), "nasdaq_week": _date_text(row.nasdaq_week_ending),
            "confirmed": bool(row.confirmed), "new_bullish_reversal": bool(row.new_bullish_reversal),
            "new_bearish_reversal": bool(row.new_bearish_reversal),
            "bullish_transition": _json(row.bullish_conditions_json), "bearish_transition": _json(row.bearish_conditions_json),
            "kospi": {"close": row.kospi_close, "ema20": row.kospi_ema20, "ema40": row.kospi_ema40,
                      "ema20_4w_slope": row.kospi_ema20_4w_slope, "macd_histogram": row.kospi_macd_histogram,
                      "rsi14": row.kospi_rsi14, "atr14": row.kospi_atr14, "drawdown_52w": row.kospi_drawdown_52w},
            "nasdaq": {"close": row.nasdaq_close, "ema20": row.nasdaq_ema20, "ema40": row.nasdaq_ema40,
                       "ema20_4w_slope": row.nasdaq_ema20_4w_slope, "macd_histogram": row.nasdaq_macd_histogram,
                       "rsi14": row.nasdaq_rsi14, "atr14": row.nasdaq_atr14},
            "calculated_at": _datetime_text(row.calculated_at),
            "next_scheduled_calculation": _next_calculation(now).isoformat(),
            "data_source": _json(row.data_source_json),
        }


def _diagnostics(w):
    keys = ("kospi_close", "kospi_ema20", "kospi_ema40", "kospi_ema20_4w_slope",
            "kospi_macd_histogram", "kospi_rsi14", "kospi_atr14", "kospi_drawdown_52w",
            "nasdaq_close", "nasdaq_ema20", "nasdaq_ema40", "nasdaq_ema20_4w_slope",
            "nasdaq_macd_histogram", "nasdaq_rsi14", "nasdaq_atr14")
    if w is None:
        return {k: None for k in keys}
    k, n = w.kospi, w.nasdaq
    return {
        "kospi_close": _rounded(k.close), "kospi_ema20": _rounded(k.ema20), "kospi_ema40": _rounded(k.ema40),
        "kospi_ema20_4w_slope": _rounded(k.ema20_4w_slope), "kospi_macd_histogram": _rounded(k.macd_histogram),
        "kospi_rsi14": _rounded(k.rsi14), "kospi_atr14": _rounded(k.atr14), "kospi_drawdown_52w": _rounded(k.drawdown_52w),
        "nasdaq_close": _rounded(n.close), "nasdaq_ema20": _rounded(n.ema20), "nasdaq_ema40": _rounded(n.ema40),
        "nasdaq_ema20_4w_slope": _rounded(n.ema20_4w_slope), "nasdaq_macd_histogram": _rounded(n.macd_histogram),
        "nasdaq_rsi14": _rounded(n.rsi14), "nasdaq_atr14": _rounded(n.atr14),
    }


def _empty_payload(now):
    return {
        "status": "insufficient_data", "stage": None, "stage_key": None, "stage_label": None,
        "short_label": "데이터 없음", "summary": "주간 국면을 확인할 데이터가 부족합니다.",
        "market_score": None, "score_change_3w": None, "kospi_score": None, "nasdaq_score": None,
        "kospi_week": None, "nasdaq_week": None, "confirmed": False,
        "new_bullish_reversal": False, "new_bearish_reversal": False, "bullish_transition": {},
        "bearish_transition": {}, "kospi": {}, "nasdaq": {}, "calculated_at": None,
        "next_scheduled_calculation": _next_calculation(now).isoformat(), "data_source": {},
    }


def _next_calculation(now):
    local = _as_utc(now).astimezone(KST)
    day = local.date() + (timedelta(days=1) if local.timetz().replace(tzinfo=None) >= time(8) else timedelta())
    return datetime.combine(day, time(8), tzinfo=KST)


def _date_text(v):
    return v.isoformat() if v else None


def _datetime_text(v):
    if v is None:
        return None
    return (v.replace(tzinfo=UTC) if v.tzinfo is None else v).astimezone(UTC).isoformat()


def _as_utc(v):
    if v.tzinfo is None or v.utcoffset() is None:
        raise ValueError("Market-regime timestamps must include an explicit timezone.")
    return v.astimezone(UTC)


def _json(v):
    if not v:
        return {}
    try:
        value = json.loads(v)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}
