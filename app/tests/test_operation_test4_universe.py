from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.services.operation_test4_universe import (
    OperationTest4UniverseError,
    build_operation_test4_universe,
    load_operation_test4_universe,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_source(path: Path, symbols: list[str], *, prefix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "market": "KR",
                "symbols": [
                    {
                        "symbol": symbol,
                        "name": f"{prefix}-{symbol}",
                        "market": "KOSPI",
                    }
                    for symbol in symbols
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_universe_merges_approved_sources_in_priority_order_and_deduplicates(tmp_path, monkeypatch):
    _write_source(
        tmp_path / "config/local-watchlists/watchlist_kr.base50.yaml",
        ["000001", "000002"],
        prefix="base",
    )
    _write_source(
        tmp_path / "config/local-watchlists/watchlist_kr.operation-test.current.yaml",
        ["000002", *[f"{index:06d}" for index in range(3, 71)]],
        prefix="operation",
    )

    monkeypatch.setattr("app.services.operation_test4_universe._git_history_rows", lambda root: [])
    output = tmp_path / "config/watchlist_kr_test4_universe.yaml"
    payload = build_operation_test4_universe(
        root=tmp_path,
        output_path=output,
        minimum_count=70,
        maximum_count=100,
    )
    loaded = load_operation_test4_universe(output, minimum_count=70, maximum_count=100)

    assert payload["configured_count"] == 70
    assert loaded["count"] == 70
    assert loaded["symbols"][0]["symbol"] == "000001"
    assert loaded["symbols"][1]["symbol"] == "000002"
    assert loaded["symbols"][-1]["symbol"] == "000070"
    assert payload["source_counts"]["local_watchlist_kr_base50"] == 2
    assert payload["source_counts"]["operational_watchlist:watchlist_kr.operation-test.current.yaml"] == 68


def test_universe_preserves_leading_zero_codes(tmp_path, monkeypatch):
    _write_source(
        tmp_path / "config/local-watchlists/watchlist_kr.base50.yaml",
        ["005930", "000660"],
        prefix="base",
    )
    _write_source(
        tmp_path / "config/local-watchlists/watchlist_kr.operation-test.current.yaml",
        [f"{index:06d}" for index in range(3, 71)],
        prefix="operation",
    )
    monkeypatch.setattr(
        "app.services.operation_test4_universe._git_history_rows",
        lambda root: [],
    )

    output = tmp_path / "universe.yaml"
    build_operation_test4_universe(
        root=tmp_path,
        output_path=output,
        minimum_count=70,
        maximum_count=70,
    )
    payload = load_operation_test4_universe(output, minimum_count=70, maximum_count=70)

    assert payload["symbols"][0]["symbol"] == "005930"
    assert payload["symbols"][1]["symbol"] == "000660"
    assert all(len(row["symbol"]) == 6 for row in payload["symbols"])


def test_configured_test4_universe_has_exact_market_shape_and_valid_rows():
    path = REPO_ROOT / "config/watchlist_kr_test4_universe.yaml"
    payload = load_operation_test4_universe(
        path,
        minimum_count=180,
        maximum_count=200,
        expected_market_counts={"KOSPI": 150, "KOSDAQ": 50},
    )

    assert payload["minimum_count"] == 180
    assert payload["maximum_count"] == 200
    assert payload["configured_count"] == 200
    assert len(payload["symbols"]) == 200
    assert len({row["symbol"] for row in payload["symbols"]}) == 200
    raw_rows = yaml.safe_load(path.read_text(encoding="utf-8"))["symbols"]
    for market, expected_count in (("KOSPI", 150), ("KOSDAQ", 50)):
        rows = [row for row in payload["symbols"] if row["market"] == market]
        raw_market_rows = [row for row in raw_rows if row["market"] == market]
        assert len(rows) == expected_count
        assert [row["market_cap_rank"] for row in raw_market_rows] == list(
            range(1, expected_count + 1)
        )
    assert all(
        not any(
            marker in str(row.get("name") or "").upper()
            for marker in ("ETF", "ETN", "ELW", "SPAC", "REIT", "PREFERRED")
        )
        for row in payload["symbols"]
    )


def test_universe_below_minimum_fails_without_writing_output(tmp_path, monkeypatch):
    _write_source(
        tmp_path / "config/local-watchlists/watchlist_kr.base50.yaml",
        ["000001", "000002"],
        prefix="base",
    )
    monkeypatch.setattr(
        "app.services.operation_test4_universe._git_history_rows",
        lambda root: [],
    )
    output = tmp_path / "universe.yaml"

    with pytest.raises(OperationTest4UniverseError, match="below minimum"):
        build_operation_test4_universe(
            root=tmp_path,
            output_path=output,
            minimum_count=70,
            maximum_count=100,
        )
    assert output.exists() is False