from datetime import date, timedelta

import pytest

from app.services.technical_indicator_service import (
    TechnicalIndicatorService,
    indicator_payload_is_quant_ready,
    normalize_ohlcv_bars,
)


def _bars(count: int):
    rows = []
    start = date(2026, 1, 1)
    for i in range(count):
        close = 100.0 + i
        rows.append(
            {
                "symbol": "005930",
                "timestamp": (start + timedelta(days=i)).isoformat(),
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1000 + i * 10,
            }
        )
    return rows


def test_normalized_ohlcv_bars_are_sorted_and_deduped():
    rows = [
        {
            "timestamp": "2026-05-02",
            "open": "102",
            "high": "103",
            "low": "101",
            "close": "102",
            "volume": "1,200",
        },
        {
            "timestamp": "2026-05-01",
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "100",
            "volume": "1,000",
        },
        {
            "timestamp": "2026-05-02",
            "open": "104",
            "high": "105",
            "low": "103",
            "close": "104",
            "volume": "1,400",
        },
    ]

    bars = normalize_ohlcv_bars(rows)

    assert [bar["timestamp"] for bar in bars] == ["2026-05-01", "2026-05-02"]
    assert bars[-1]["close"] == 104.0
    assert bars[-1]["volume"] == 1400.0


def test_technical_indicator_service_calculates_core_metrics():
    result = TechnicalIndicatorService().calculate(_bars(60), current_price=160.5)
    payload = result["indicator_payload"]

    assert result["indicator_status"] == "ok"
    assert result["bar_count"] == 60
    assert payload["price"] == 160.5
    assert payload["ema20"] is not None
    assert payload["ema50"] is not None
    assert payload["rsi"] is not None
    assert payload["atr"] == pytest.approx(2.0)
    assert payload["vwap"] is not None
    assert payload["volume_ratio"] is not None
    assert payload["momentum"] is not None
    assert payload["recent_return"] is not None
    assert indicator_payload_is_quant_ready(payload) is True


def test_technical_indicator_service_marks_short_history_insufficient():
    result = TechnicalIndicatorService().calculate(_bars(8), current_price=108)

    assert result["indicator_status"] == "insufficient_data"
    assert result["indicator_payload"]["ema20"] is None
    assert indicator_payload_is_quant_ready(result["indicator_payload"]) is False


def test_technical_indicator_service_marks_no_bars_price_only():
    result = TechnicalIndicatorService().calculate([], current_price=72000)

    assert result["indicator_status"] == "price_only"
    assert result["bar_count"] == 0
    assert result["indicator_payload"]["ema20"] is None
