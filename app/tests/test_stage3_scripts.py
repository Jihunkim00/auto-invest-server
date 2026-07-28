from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def test_trend_builder_defaults_keep_conservative_notional(monkeypatch):
    monkeypatch.delenv("STAGE3_MAX_NOTIONAL_KRW", raising=False)
    monkeypatch.delenv("STAGE3_MAX_NOTIONAL_PCT", raising=False)
    script = _load_script("stage3_build_trend_watchlist.py")

    config = script.parse_args([])

    assert config.max_notional_krw == 50000.0
    assert config.max_notional_pct == 0.80


def test_trend_builder_uses_double_notional_limit():
    script = _load_script("stage3_build_trend_watchlist.py")

    max_notional = script.calculate_max_notional(
        configured_max_notional_krw=55000,
        configured_max_notional_pct=0.93,
        equity=100000,
        cash=90000,
    )

    assert max_notional == 55000


def test_trend_checks_require_one_share_cash_and_technical_pass():
    script = _load_script("stage3_build_trend_watchlist.py")

    checks, expected_qty, estimated_notional = script.build_candidate_checks(
        current_price=52000,
        ema20=51000,
        ema50=50000,
        vwap=51500,
        short_momentum=0.01,
        max_notional=55000,
        cash=60000,
    )

    assert expected_qty == 1
    assert estimated_notional == 52000
    assert all(checks.values())


def test_trend_checks_reject_two_share_candidate():
    script = _load_script("stage3_build_trend_watchlist.py")

    checks, expected_qty, _ = script.build_candidate_checks(
        current_price=25000,
        ema20=24000,
        ema50=23000,
        vwap=24500,
        short_momentum=0.01,
        max_notional=55000,
        cash=60000,
    )

    assert expected_qty == 2
    assert checks["one_share_quantity"] is False


def test_source_universe_requires_100_unique_symbols(tmp_path):
    script = _load_script("stage3_build_trend_watchlist.py")
    path = tmp_path / "universe.yaml"
    symbols = [
        {"symbol": f"{index:06d}", "name": f"name{index}", "market": "KOSPI"}
        for index in range(100)
    ]
    path.write_text(
        "symbols:\n"
        + "\n".join(
            f"- symbol: '{item['symbol']}'\n"
            f"  name: {item['name']}\n"
            f"  market: {item['market']}"
            for item in symbols
        ),
        encoding="utf-8",
    )

    loaded, summary = script.load_source_symbols(path, required_count=100)

    assert len(loaded) == 100
    assert summary["source_symbol_count"] == 100


def test_universe_builder_price_range_for_one_share():
    script = _load_script("stage3_build_universe100.py")

    minimum, maximum = script.one_share_price_range(55000)

    assert minimum == 27501
    assert maximum == 55000
    assert int(55000 // minimum) == 1
    assert int(55000 // (minimum - 1)) == 2


def test_scheduled_check_uses_only_allowed_submit_free_endpoints():
    text = (ROOT / "scripts" / "stage3_scheduled_check.ps1").read_text(
        encoding="utf-8"
    )

    forbidden = [
        "POST " + "/kis/limited-auto-buy/" + "run-once",
        "POST " + "/kis/orders/" + "manual-submit",
        "/kis/limited-auto-buy/" + "run-once",
        "/kis/orders/" + "manual-submit",
        "/kis/orders/" + "submit-manual",
        "submit" + "_order",
        "submit" + "_manual",
    ]
    for pattern in forbidden:
        assert pattern not in text

    assert "/kis/watchlist/preview" in text
    assert "/kis/limited-auto-buy/preflight-once" in text
    assert "/ops/settings" in text
