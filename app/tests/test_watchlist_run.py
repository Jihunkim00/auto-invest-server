from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.database import get_db
from app.main import app


def _watchlist_entry(symbol: str, company_name: str, quant_score: float) -> dict[str, object]:
    return {
        "symbol": symbol,
        "company_name": company_name,
        "name": company_name,
        "entry_score": quant_score,
        "should_trade": False,
        "entry_ready": False,
        "action_hint": "watch",
        "block_reason": "score_threshold_not_met",
        "quant_score": quant_score,
        "quant_buy_score": quant_score,
        "quant_sell_score": 20.0,
        "ai_buy_score": 10.0,
        "ai_sell_score": 20.0,
        "quant_reason": "quant baseline",
        "ai_reason": "ai neutral",
        "has_indicators": True,
        "market": "US",
        "broker": "alpaca",
        "market_label": "미국",
    }


def _install_watchlist_run_fakes(monkeypatch):
    settings = get_settings()
    settings.alpaca_base_url = "https://paper-api.alpaca.markets"
    watchlist = [
        _watchlist_entry("NVDA", "NVIDIA Corporation", 72.0),
        _watchlist_entry("AAPL", "Apple Inc.", 68.0),
    ]

    def fake_analyze(self, gate_level):
        return {
            "watchlist": watchlist,
            "best_candidate": watchlist[0],
            "best_score": 72.0,
            "should_trade": False,
            "watchlist_source": "config/watchlist_us.yaml",
            "configured_symbol_count": len(watchlist),
            "analyzed_symbol_count": len(watchlist),
            "max_watchlist_size": 50,
        }

    def fake_score_symbol(self, symbol, gate_level):
        row = next(item for item in watchlist if item["symbol"] == symbol)
        return dict(row), {"dummy": True}

    def fake_gpt_analyze(self, db, symbol, indicators, gate_level):
        return {
            "market_confidence": 0.70,
            "entry_allowed": True,
            "hard_blocked": False,
            "market_regime": "range",
            "entry_bias": "neutral",
            "reason": "Research keeps the candidate on watch.",
            "audit": {"fallback_used": False},
        }

    monkeypatch.setattr(
        "app.services.watchlist_service.WatchlistService.analyze",
        fake_analyze,
    )
    monkeypatch.setattr(
        "app.services.watchlist_service.WatchlistService._score_symbol",
        fake_score_symbol,
    )
    monkeypatch.setattr(
        "app.services.gpt_market_service.GPTMarketService.analyze",
        fake_gpt_analyze,
    )


def _install_symbol_only_watchlist_run_fakes(monkeypatch):
    settings = get_settings()
    settings.alpaca_base_url = "https://paper-api.alpaca.markets"
    symbols = ["HON", "MU", "STX", "LRCX", "APP"]

    def row_for(symbol: str, score: float) -> dict[str, object]:
        return _watchlist_entry(symbol, symbol, score)

    watchlist = [row_for(symbol, 72.0 - index) for index, symbol in enumerate(symbols)]

    def fake_analyze(self, gate_level):
        return {
            "watchlist": watchlist,
            "best_candidate": watchlist[0],
            "best_score": 72.0,
            "should_trade": False,
            "watchlist_source": "config/watchlist.yaml",
            "configured_symbol_count": len(watchlist),
            "analyzed_symbol_count": len(watchlist),
            "max_watchlist_size": 50,
        }

    def fake_score_symbol(self, symbol, gate_level):
        row = next(item for item in watchlist if item["symbol"] == symbol)
        return dict(row), {"dummy": True}

    def fake_gpt_analyze(self, db, symbol, indicators, gate_level):
        return {
            "market_confidence": 0.70,
            "entry_allowed": True,
            "hard_blocked": False,
            "market_regime": "range",
            "entry_bias": "neutral",
            "reason": "Research keeps the candidate on watch.",
            "audit": {"fallback_used": False},
        }

    monkeypatch.setattr(
        "app.services.watchlist_service.WatchlistService.analyze",
        fake_analyze,
    )
    monkeypatch.setattr(
        "app.services.watchlist_service.WatchlistService._score_symbol",
        fake_score_symbol,
    )
    monkeypatch.setattr(
        "app.services.gpt_market_service.GPTMarketService.analyze",
        fake_gpt_analyze,
    )


def _client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_run_watchlist_once_candidates_include_company_name(monkeypatch, db_session):
    _install_watchlist_run_fakes(monkeypatch)
    try:
        with _client(db_session) as client:
            response = client.post("/trading/run-watchlist-once")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["watchlist"][0]["company_name"] == "NVIDIA Corporation"
    assert payload["top_quant_candidates"][0]["company_name"] == "NVIDIA Corporation"
    assert payload["top_quant_candidates"][0]["name"] == "NVIDIA Corporation"
    assert payload["researched_candidates"][0]["company_name"] == "NVIDIA Corporation"
    assert payload["final_ranked_candidates"][0]["company_name"] == "NVIDIA Corporation"
    assert payload["final_best_candidate"]["company_name"] == "NVIDIA Corporation"
    assert payload["tied_final_candidates"][0]["company_name"] == "NVIDIA Corporation"
    assert payload["near_tied_candidates"][0]["company_name"] == "NVIDIA Corporation"


def test_run_watchlist_once_symbol_only_candidates_use_static_company_names(monkeypatch, db_session):
    _install_symbol_only_watchlist_run_fakes(monkeypatch)
    try:
        with _client(db_session) as client:
            response = client.post("/trading/run-watchlist-once")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    by_symbol = {item["symbol"]: item for item in payload["researched_candidates"]}
    assert by_symbol["HON"]["company_name"] == "Honeywell International Inc."
    assert by_symbol["MU"]["company_name"] == "Micron Technology, Inc."
    assert by_symbol["STX"]["company_name"] == "Seagate Technology Holdings plc"
    assert by_symbol["LRCX"]["company_name"] == "Lam Research Corporation"
    assert by_symbol["APP"]["company_name"] == "AppLovin Corporation"
    assert payload["final_best_candidate"]["company_name"] == "Honeywell International Inc."
    assert payload["tied_final_candidates"][0]["company_name"] == "Honeywell International Inc."
    assert payload["near_tied_candidates"][0]["company_name"] == "Honeywell International Inc."


def test_latest_watchlist_run_includes_company_name(monkeypatch, db_session):
    _install_watchlist_run_fakes(monkeypatch)
    try:
        with _client(db_session) as client:
            post_response = client.post("/trading/run-watchlist-once")
            response = client.get("/trading/watchlist/latest")
    finally:
        app.dependency_overrides.clear()

    assert post_response.status_code == 200
    assert response.status_code == 200
    body = response.json()
    assert body["has_data"] is True
    item = body["item"]
    assert item["top_quant_candidates"][0]["company_name"] == "NVIDIA Corporation"
    assert item["researched_candidates"][0]["company_name"] == "NVIDIA Corporation"
    assert item["final_best_candidate"]["company_name"] == "NVIDIA Corporation"
