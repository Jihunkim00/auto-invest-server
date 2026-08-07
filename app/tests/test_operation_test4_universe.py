from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.services.operation_test4_universe import (
    OperationTest4UniverseError,
    build_operation_test4_universe,
    load_operation_test4_universe,
)


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
    loaded = load_operation_test4_universe(output)

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