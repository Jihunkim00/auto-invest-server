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


def test_watchlist_builder_selects_first_50_from_56_after_six_exclusions(tmp_path):
    source = _source(tmp_path / "source.yaml", count=56)
    quotes = {
        f"{index:06d}": {"current_price": 1_000_000 if index <= 6 else 10_000}
        for index in range(1, 57)
    }
    output = tmp_path / "watchlist.yaml"

    result = build_operation_test4_watchlist(
        root=tmp_path,
        source_path=source,
        output_path=output,
        client=FakeQuoteClient(quotes),
    )
    loaded = load_operation_test4_watchlist(output)

    assert result["source_universe_count"] == 56
    assert result["quote_checked_count"] == 56
    assert result["eligible_count"] == 50
    assert result["selected_count"] == 50
    assert result["reserve_eligible_count"] == 0
    assert result["exclusion_reasons"] == {"price_cap_exceeded": 6}
    assert loaded["selected_symbols"][0] == "000007"
    assert len(loaded["selected_symbols"]) == 50


def test_watchlist_builder_reports_remaining_eligible_reserve(tmp_path):
    source = _source(tmp_path / "universe.yaml", count=60)
    quotes = {
        f"{index:06d}": {"current_price": 10_000}
        for index in range(1, 61)
    }

    result = build_operation_test4_watchlist(
        root=tmp_path,
        source_path=source,
        output_path=tmp_path / "watchlist.yaml",
        client=FakeQuoteClient(quotes),
    )

    assert result["eligible_count"] == 60
    assert result["selected_count"] == 50
    assert result["reserve_eligible_count"] == 10
    assert result["selected_symbols"][-1] == "000050"


def test_watchlist_builder_fails_when_80_universe_has_only_44_eligible(tmp_path):
    source = _source(tmp_path / "universe.yaml", count=80)
    quotes = {
        f"{index:06d}": {"current_price": 10_000 if index <= 44 else 1_000_000}
        for index in range(1, 81)
    }

    with pytest.raises(OperationTest4WatchlistError, match="eligible candidate count") as raised:
        build_operation_test4_watchlist(
            root=tmp_path,
            source_path=source,
            output_path=tmp_path / "watchlist.yaml",
            client=FakeQuoteClient(quotes),
        )

    assert raised.value.details["source_universe_count"] == 80
    assert raised.value.details["quote_checked_count"] == 80
    assert raised.value.details["eligible_count"] == 44
    assert raised.value.details["selected_count"] == 0
    assert raised.value.details["exclusion_reasons"] == {"price_cap_exceeded": 36}