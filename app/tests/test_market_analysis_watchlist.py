from fastapi.testclient import TestClient

from app.main import app
from app.services.market_data_service import MarketDataService


def test_market_analysis_watchlist_route_exists():
    client = TestClient(app)
    assert client.app.url_path_for("analyze_watchlist") == "/market-analysis/watchlist"


def test_market_analysis_watchlist_endpoint_calls_service(monkeypatch):
    def fake_analyze(self, gate_level):
        return {
            "watchlist": [],
            "best_candidate": None,
            "best_score": 0.0,
            "should_trade": False,
        }

    monkeypatch.setattr(
        "app.services.watchlist_service.WatchlistService.analyze",
        fake_analyze,
    )

    client = TestClient(app)
    response = client.post("/market-analysis/watchlist")
    assert response.status_code == 200
    payload = response.json()
    assert payload["watchlist"] == []
    assert payload["best_score"] == 0.0
    assert payload["should_trade"] is False


def make_dummy_bars():
    bars = []
    for i in range(60):
        bars.append(
            {
                "timestamp": f"2026-04-24T00:{i:02d}:00Z",
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 1000 + i * 10,
            }
        )
    return bars


def test_market_analysis_watchlist_reads_all_configured_symbols(monkeypatch):
    monkeypatch.setattr(
        MarketDataService,
        "get_recent_bars",
        lambda self, symbol, limit=120, timeframe="1Min": make_dummy_bars(),
    )

    client = TestClient(app)
    response = client.post("/market-analysis/watchlist")
    assert response.status_code == 200

    payload = response.json()
    assert payload["watchlist_source"] == "config/watchlist.yaml"
    assert payload["configured_symbol_count"] == 50
    assert payload["analyzed_symbol_count"] == 50
    assert payload["max_watchlist_size"] == 50
    assert len(payload["watchlist"]) == 50
    assert payload["best_candidate"] is not None
    assert "best_score" in payload
    assert "should_trade" in payload
