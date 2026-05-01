from __future__ import annotations

import math
from typing import Any

import pandas as pd


EMPTY_TECHNICAL_INDICATORS: dict[str, float | None] = {
    "price": None,
    "close": None,
    "ema20": None,
    "ema50": None,
    "rsi": None,
    "vwap": None,
    "atr": None,
    "volume_ratio": None,
    "momentum": None,
    "short_momentum": None,
    "recent_return": None,
    "day_open": None,
    "previous_high": None,
    "previous_low": None,
}


class TechnicalIndicatorService:
    """Broker-neutral indicators over normalized OHLCV bars."""

    def calculate(
        self,
        bars: list[dict[str, Any]],
        *,
        current_price: float | None = None,
    ) -> dict[str, Any]:
        normalized_bars = normalize_ohlcv_bars(bars)
        payload: dict[str, float | None] = dict(EMPTY_TECHNICAL_INDICATORS)

        if not normalized_bars:
            return {
                "indicator_status": "price_only",
                "indicator_payload": payload,
                "bar_count": 0,
            }

        df = pd.DataFrame(normalized_bars)
        latest = df.iloc[-1]
        prev = df.iloc[:-1]
        bar_count = len(df)

        close = _finite_or_none(latest.get("close"))
        price = _finite_or_none(current_price)
        if price is None or price <= 0:
            price = close

        payload.update(
            {
                "price": _round_or_none(price),
                "close": _round_or_none(close),
                "day_open": _round_or_none(latest.get("open")),
                "previous_high": (
                    _round_or_none(prev["high"].max()) if not prev.empty else None
                ),
                "previous_low": (
                    _round_or_none(prev["low"].min()) if not prev.empty else None
                ),
            }
        )

        if bar_count >= 20:
            ema20 = df["close"].ewm(span=20, adjust=False).mean().iloc[-1]
            payload["ema20"] = _round_or_none(ema20)

        if bar_count >= 50:
            ema50 = df["close"].ewm(span=50, adjust=False).mean().iloc[-1]
            payload["ema50"] = _round_or_none(ema50)

        if bar_count >= 14:
            payload["rsi"] = _round_or_none(_latest_rsi(df["close"], period=14))
            payload["atr"] = _round_or_none(_latest_atr(df, period=14))

        volume_sum = _finite_or_none(df["volume"].sum())
        if volume_sum is not None and volume_sum > 0:
            typical_price = (df["high"] + df["low"] + df["close"]) / 3
            vwap = (typical_price * df["volume"]).sum() / volume_sum
            payload["vwap"] = _round_or_none(vwap)

        if bar_count >= 20:
            avg_volume = _finite_or_none(df["volume"].tail(20).mean())
            latest_volume = _finite_or_none(latest.get("volume"))
            if avg_volume is not None and avg_volume > 0 and latest_volume is not None:
                payload["volume_ratio"] = _round_or_none(latest_volume / avg_volume)

        if bar_count > 5:
            momentum = df["close"].pct_change(periods=5).iloc[-1]
            payload["momentum"] = _round_or_none(momentum)
            payload["short_momentum"] = _round_or_none(momentum)

        if bar_count > 20:
            payload["recent_return"] = _round_or_none(
                df["close"].pct_change(periods=20).iloc[-1]
            )

        status = self._status(payload, bar_count)
        return {
            "indicator_status": status,
            "indicator_payload": payload,
            "bar_count": bar_count,
        }

    @staticmethod
    def _status(payload: dict[str, float | None], bar_count: int) -> str:
        if bar_count <= 0:
            return "price_only"

        core_keys = (
            "ema20",
            "ema50",
            "rsi",
            "vwap",
            "atr",
            "volume_ratio",
            "momentum",
        )
        if all(payload.get(key) is not None for key in core_keys):
            return "ok"

        if bar_count >= 50 and any(payload.get(key) is not None for key in core_keys):
            return "partial"

        return "insufficient_data"


def normalize_ohlcv_bars(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_timestamp: dict[str, dict[str, Any]] = {}
    for raw in bars or []:
        if not isinstance(raw, dict):
            continue

        timestamp = str(raw.get("timestamp") or "").strip()
        if not timestamp:
            continue

        open_price = _finite_or_none(raw.get("open"))
        high = _finite_or_none(raw.get("high"))
        low = _finite_or_none(raw.get("low"))
        close = _finite_or_none(raw.get("close"))
        volume = _finite_or_none(raw.get("volume"), default=0.0)

        if (
            open_price is None
            or high is None
            or low is None
            or close is None
            or open_price <= 0
            or high <= 0
            or low <= 0
            or close <= 0
        ):
            continue

        by_timestamp[timestamp] = {
            "symbol": raw.get("symbol"),
            "timestamp": timestamp,
            "open": float(open_price),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": float(volume or 0.0),
        }

    return [by_timestamp[key] for key in sorted(by_timestamp)]


def indicator_payload_is_quant_ready(payload: dict[str, Any]) -> bool:
    required = (
        "price",
        "ema20",
        "ema50",
        "rsi",
        "vwap",
        "atr",
        "volume_ratio",
        "short_momentum",
        "day_open",
        "previous_high",
        "previous_low",
    )
    return all(_finite_or_none(payload.get(key)) is not None for key in required)


def _latest_rsi(series: pd.Series, period: int = 14) -> float | None:
    delta = series.diff().fillna(0.0)
    gain = delta.clip(lower=0).rolling(window=period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).rolling(window=period, min_periods=period).mean()
    latest_loss = _finite_or_none(loss.iloc[-1])
    latest_gain = _finite_or_none(gain.iloc[-1])
    if latest_loss is None or latest_gain is None:
        return None
    if latest_loss == 0:
        return 100.0 if latest_gain > 0 else 50.0
    rs = latest_gain / latest_loss
    return 100 - (100 / (1 + rs))


def _latest_atr(df: pd.DataFrame, period: int = 14) -> float | None:
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            (df["high"] - df["low"]),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return _finite_or_none(
        true_range.rolling(window=period, min_periods=period).mean().iloc[-1]
    )


def _finite_or_none(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        numeric = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return default
    if not math.isfinite(numeric):
        return default
    return numeric


def _round_or_none(value: Any, digits: int = 6) -> float | None:
    numeric = _finite_or_none(value)
    if numeric is None:
        return None
    return round(float(numeric), digits)
