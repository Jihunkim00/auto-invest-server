import re

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services.market_profile_service import (
    MarketProfileError,
    MarketProfileService,
)
from app.services.reference_site_service import ReferenceSiteService
from app.services.watchlist_service import WatchlistService


def test_default_market_profile_is_us():
    service = MarketProfileService()

    profile = service.get_default_profile()

    assert profile.market == "US"
    assert service.get_default_market_key() == "US"


def test_us_profile_points_to_alpaca_usd_and_us_configs():
    profile = MarketProfileService().get_profile("US")

    assert profile.broker_provider == "alpaca"
    assert profile.currency == "USD"
    assert profile.timezone == "America/New_York"
    assert profile.watchlist_file == "config/watchlist_us.yaml"
    assert profile.reference_sites_file == "config/reference_sites_us.yaml"
    assert profile.symbol_format == "ticker"
    assert profile.enabled_for_trading is True


def test_us_watchlist_endpoint_includes_company_name_and_name():
    client = TestClient(app)

    response = client.get("/market-profiles/US/watchlist")

    assert response.status_code == 200
    body = response.json()
    assert body["market"] == "US"
    nvda = next(item for item in body["symbols"] if item["symbol"] == "NVDA")
    assert nvda["company_name"]
    assert nvda["company_name"] != "Unknown Company"
    assert nvda["name"] == nvda["company_name"]
    assert nvda["market"] == "US"
    assert nvda["broker"] == "alpaca"
    assert nvda["market_label"] == "미국"


def test_us_watchlist_yaml_aliases_normalize_to_company_name(monkeypatch, tmp_path):
    path = tmp_path / "watchlist_us_aliases.yaml"
    path.write_text(
        "\n".join(
            [
                "symbols:",
                "  - symbol: NVDA",
                "    company_name: NVIDIA Corporation",
                "  - symbol: AAPL",
                "    name: Apple Inc.",
                "  - symbol: MSFT",
                "    company: Microsoft Corporation",
                "  - symbol: GOOGL",
                "    companyName: Alphabet Inc.",
                "  - ticker: AMD",
                "    company_name: Advanced Micro Devices, Inc.",
                "  - TSLA",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(get_settings(), "watchlist_us_path", str(path))

    payload = MarketProfileService().load_watchlist("US")

    by_symbol = {item["symbol"]: item for item in payload["symbols"]}
    assert by_symbol["NVDA"]["company_name"] == "NVIDIA Corporation"
    assert by_symbol["NVDA"]["name"] == "NVIDIA Corporation"
    assert by_symbol["AAPL"]["company_name"] == "Apple Inc."
    assert by_symbol["MSFT"]["company_name"] == "Microsoft Corporation"
    assert by_symbol["GOOGL"]["company_name"] == "Alphabet Inc."
    assert by_symbol["AMD"]["company_name"] == "Advanced Micro Devices, Inc."
    assert by_symbol["TSLA"]["company_name"] == "Tesla, Inc."
    assert by_symbol["TSLA"]["name"] == "Tesla, Inc."
    assert all(item["market"] == "US" for item in by_symbol.values())
    assert all(item["broker"] == "alpaca" for item in by_symbol.values())


def test_watchlist_service_metadata_aliases_use_symbol_fallback(monkeypatch, tmp_path):
    path = tmp_path / "watchlist_us_metadata.yaml"
    path.write_text(
        "\n".join(
            [
                "symbols:",
                "  - symbol: NVDA",
                "    company: NVIDIA Corporation",
                "  - ticker: AAPL",
                "    name: Apple Inc.",
                "  - MSFT",
                "  - ZZZZ",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(get_settings(), "watchlist_us_path", str(path))

    service = WatchlistService(market="US")

    assert service.symbols == ["NVDA", "AAPL", "MSFT", "ZZZZ"]
    assert service.symbol_metadata["NVDA"]["company_name"] == "NVIDIA Corporation"
    assert service.symbol_metadata["AAPL"]["company_name"] == "Apple Inc."
    assert service.symbol_metadata["MSFT"]["company_name"] == "Microsoft Corporation"
    assert service.symbol_metadata["ZZZZ"]["company_name"] == "ZZZZ"


def test_us_watchlist_symbol_only_yaml_uses_static_company_metadata(monkeypatch, tmp_path):
    path = tmp_path / "watchlist_us_symbols.yaml"
    path.write_text(
        "\n".join(
            [
                "symbols:",
                "  - NVDA",
                "  - HON",
                "  - MU",
                "  - STX",
                "  - LRCX",
                "  - APP",
                "  - ZZZZ",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(get_settings(), "watchlist_us_path", str(path))

    payload = MarketProfileService().load_watchlist("US")

    by_symbol = {item["symbol"]: item for item in payload["symbols"]}
    assert by_symbol["NVDA"]["company_name"] == "NVIDIA Corporation"
    assert by_symbol["HON"]["company_name"] == "Honeywell International Inc."
    assert by_symbol["MU"]["company_name"] == "Micron Technology, Inc."
    assert by_symbol["STX"]["company_name"] == "Seagate Technology Holdings plc"
    assert by_symbol["LRCX"]["company_name"] == "Lam Research Corporation"
    assert by_symbol["APP"]["company_name"] == "AppLovin Corporation"
    assert by_symbol["ZZZZ"]["company_name"] == "ZZZZ"


def test_kr_profile_points_to_kis_krw_and_kr_configs():
    profile = MarketProfileService().get_profile("KR")

    assert profile.broker_provider == "kis"
    assert profile.currency == "KRW"
    assert profile.timezone == "Asia/Seoul"
    assert profile.watchlist_file == "config/watchlist_kr.yaml"
    assert profile.reference_sites_file == "config/reference_sites_kr.yaml"
    assert profile.symbol_format == "6_digit_numeric"
    assert profile.enabled_for_trading is True


def test_existing_watchlist_loading_without_market_still_uses_us_default():
    service = WatchlistService()

    assert "AAPL" in service.symbols
    assert "MSFT" in service.symbols
    assert service._settings.watchlist_config_path == "config/watchlist.yaml"


def test_kr_watchlist_loading_returns_six_digit_symbols():
    payload = MarketProfileService().load_watchlist("KR")

    symbols = [item["symbol"] for item in payload["symbols"]]
    assert payload["market"] == "KR"
    assert payload["currency"] == "KRW"
    assert payload["count"] == 50
    assert "005930" in symbols
    assert "035420" in symbols
    assert symbols
    assert all(re.fullmatch(r"\d{6}", symbol) for symbol in symbols)


def test_kr_watchlist_service_can_load_profile_symbols_without_analysis():
    service = WatchlistService(market="KR")

    assert len(service.symbols) == 50
    assert "005930" in service.symbols
    assert "035420" in service.symbols
    assert all(re.fullmatch(r"\d{6}", symbol) for symbol in service.symbols)


def test_watchlist_candidate_payload_includes_configured_company_name(monkeypatch):
    service = WatchlistService(symbols=["AAPL"])
    service.symbol_metadata = {
        "AAPL": {
            "name": "Apple Inc.",
            "company_name": "Apple Inc.",
            "market": "US",
            "broker": "alpaca",
        }
    }
    monkeypatch.setattr(
        service.market_data_service,
        "get_recent_bars",
        lambda symbol: [{"close": 190}],
    )
    monkeypatch.setattr(
        service.indicator_service,
        "calculate",
        lambda bars: {"close": 190, "rsi": 55},
    )
    monkeypatch.setattr(
        service.quant_signal_service,
        "score",
        lambda indicators, gate_level=2: {
            "quant_buy_score": 70,
            "quant_sell_score": 10,
            "quant_reason": "ok",
            "quant_notes": [],
        },
    )
    monkeypatch.setattr(
        service.ai_signal_service,
        "adjust",
        lambda **kwargs: {
            "ai_buy_score": 70,
            "ai_sell_score": 10,
            "ai_reason": "ok",
        },
    )

    payload, _ = service._score_symbol("AAPL", gate_level=4)

    assert payload["name"] == "Apple Inc."
    assert payload["company_name"] == "Apple Inc."
    assert payload["market"] == "US"
    assert payload["broker"] == "alpaca"


def test_kr_symbol_validation_accepts_005930():
    service = MarketProfileService()

    assert service.validate_symbol_for_market("005930", "KR") is True
    assert service.normalize_symbol("005930", "KR") == "005930"


def test_kr_symbol_validation_rejects_aapl():
    with pytest.raises(MarketProfileError):
        MarketProfileService().validate_symbol_for_market("AAPL", "KR")


def test_us_symbol_validation_accepts_aapl():
    service = MarketProfileService()

    assert service.validate_symbol_for_market("AAPL", "US") is True
    assert service.normalize_symbol("aapl", "US") == "AAPL"


def test_market_profile_endpoint_returns_us_and_kr():
    client = TestClient(app)

    response = client.get("/market-profiles")

    assert response.status_code == 200
    body = response.json()
    assert body["default_market"] == "US"
    markets = {item["market"]: item for item in body["markets"]}
    assert set(markets) >= {"US", "KR"}
    assert markets["US"]["broker_provider"] == "alpaca"
    assert markets["KR"]["broker_provider"] == "kis"
    assert markets["KR"]["enabled_for_trading"] is True


def test_kr_market_profile_endpoint_returns_kr_config():
    client = TestClient(app)

    response = client.get("/market-profiles/KR")

    assert response.status_code == 200
    body = response.json()
    assert body["market"] == "KR"
    assert body["currency"] == "KRW"
    assert body["enabled_for_trading"] is True


def test_kr_watchlist_endpoint_returns_six_digit_symbols():
    client = TestClient(app)

    response = client.get("/market-profiles/KR/watchlist")

    assert response.status_code == 200
    body = response.json()
    symbols = [item["symbol"] for item in body["symbols"]]
    assert body["market"] == "KR"
    assert body["count"] == 50
    assert "005930" in symbols
    assert "035420" in symbols
    assert all(re.fullmatch(r"\d{6}", symbol) for symbol in symbols)


def test_kr_reference_sites_endpoint_returns_official_sources():
    client = TestClient(app)

    response = client.get("/market-profiles/KR/reference-sites")

    assert response.status_code == 200
    body = response.json()
    names = {item["name"] for item in body["sources"]}
    assert body["market"] == "KR"
    assert "KIS Domestic Stock API" in names
    assert "OpenDART" in names


def test_kr_reference_sources_are_metadata_not_web_fetch_sites():
    profile_service = MarketProfileService()

    references = profile_service.load_reference_sites("KR")
    fetchable_sites = ReferenceSiteService(market="KR").load_sites()

    assert references["market"] == "KR"
    assert references["count"] >= 4
    assert {source["name"] for source in references["sources"]} >= {
        "KIS Domestic Stock API",
        "KRX Listed Stock Information",
        "OpenDART",
        "KIND",
    }
    assert all("url" not in source for source in references["sources"])
    assert fetchable_sites == []
