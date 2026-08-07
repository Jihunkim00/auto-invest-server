from pathlib import Path

import pytest

from app.services.operation_test4_watchlist import (
    OperationTest4WatchlistError,
    build_operation_test4_watchlist,
    load_operation_test4_watchlist,
    validate_quote,
)


class FakeQuoteClient:
    def __init__(self, quotes):
        self.quotes = quotes
        self.calls = []

    def get_domestic_stock_price(self, symbol):
        self.calls.append(symbol)
        return self.quotes[symbol]


def _source(path: Path, count: int = 50) -> Path:
    rows = [
        f"- symbol: '{index:06d}'\n  name: Name {index}\n  market: KOSPI"
        for index in range(1, count + 1)
    ]
    path.write_text(
        "market: KR\nsymbols:\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    return path


def test_watchlist_builder_writes_exactly_50_and_only_reads_quotes(tmp_path):
    source = _source(tmp_path / "source.yaml")
    output = tmp_path / "watchlist.yaml"
    client = FakeQuoteClient(
        {
            f"{index:06d}": {"current_price": 10_000, "name": f"Name {index}"}
            for index in range(1, 51)
        }
    )

    result = build_operation_test4_watchlist(
        root=tmp_path,
        source_path=source,
        output_path=output,
        client=client,
    )

    loaded = load_operation_test4_watchlist(output)
    assert result["configured_count"] == 50
    assert loaded["count"] == 50
    assert len({row["symbol"] for row in loaded["symbols"]}) == 50
    assert client.calls == [f"{index:06d}" for index in range(1, 51)]


def test_watchlist_quote_filters_price_and_instrument_types():
    assert validate_quote({"current_price": 1_000_000}).reasons == (
        "price_cap_exceeded",
    )
    assert validate_quote({"current_price": 10_000, "is_etf": True}).reasons == (
        "etf_excluded",
    )
    assert validate_quote({"current_price": 10_000, "name": "Example우"}).reasons == (
        "preferred_stock_excluded",
    )
    assert validate_quote(
        {"current_price": 10_000},
        source_name="Example우",
    ).reasons == ("preferred_stock_excluded",)
    assert validate_quote({"current_price": 0}).reasons == ("invalid_quote_price",)


def test_watchlist_builder_fails_closed_when_fewer_than_count_are_eligible(tmp_path):
    source = _source(tmp_path / "source.yaml")
    quotes = {
        f"{index:06d}": {"current_price": 10_000}
        for index in range(1, 50)
    }
    quotes["000050"] = {"current_price": 1_000_000}

    with pytest.raises(OperationTest4WatchlistError, match="eligible candidate count"):
        build_operation_test4_watchlist(
            root=tmp_path,
            source_path=source,
            output_path=tmp_path / "watchlist.yaml",
            client=FakeQuoteClient(quotes),
        )