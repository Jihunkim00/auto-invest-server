import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.market_profile_service import (
    MarketProfileError,
    MarketProfileService,
)
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


def test_kr_profile_points_to_kis_krw_and_kr_configs():
    profile = MarketProfileService().get_profile("KR")

    assert profile.broker_provider == "kis"
    assert profile.currency == "KRW"
    assert profile.timezone == "Asia/Seoul"
    assert profile.watchlist_file == "config/watchlist_kr.yaml"
    assert profile.reference_sites_file == "config/reference_sites_kr.yaml"
    assert profile.symbol_format == "6_digit_numeric"
    assert profile.enabled_for_trading is False


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
    assert "005930" in symbols
    assert symbols
    assert all(re.fullmatch(r"\d{6}", symbol) for symbol in symbols)


def test_kr_watchlist_service_can_load_profile_symbols_without_analysis():
    service = WatchlistService(market="KR")

    assert service.symbols[0] == "005930"
    assert all(re.fullmatch(r"\d{6}", symbol) for symbol in service.symbols)


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
    assert markets["KR"]["enabled_for_trading"] is False


def test_kr_market_profile_endpoint_returns_kr_config():
    client = TestClient(app)

    response = client.get("/market-profiles/KR")

    assert response.status_code == 200
    body = response.json()
    assert body["market"] == "KR"
    assert body["currency"] == "KRW"
    assert body["enabled_for_trading"] is False


def test_kr_watchlist_endpoint_returns_six_digit_symbols():
    client = TestClient(app)

    response = client.get("/market-profiles/KR/watchlist")

    assert response.status_code == 200
    body = response.json()
    symbols = [item["symbol"] for item in body["symbols"]]
    assert body["market"] == "KR"
    assert "005930" in symbols
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
