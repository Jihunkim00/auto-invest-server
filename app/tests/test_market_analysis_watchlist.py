from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.db.database import SessionLocal
from app.db.models import OrderLog
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


def test_market_analysis_run_returns_single_symbol_analysis(monkeypatch):
    monkeypatch.setattr(
        MarketDataService,
        "get_recent_bars",
        lambda self, symbol, limit=120, timeframe="1Min": make_dummy_bars(),
    )

    def fake_gpt_analyze(self, db, symbol, indicators, gate_level=None):
        return {
            "market_regime": "trend",
            "entry_bias": "long",
            "entry_allowed": True,
            "regime_confidence": 0.72,
            "market_confidence": 0.72,
            "risk_note": "test analysis",
            "reason": "test analysis",
            "macro_summary": "test macro",
            "gate_level": gate_level,
            "gate_profile_name": "loose_test_mode",
            "hard_block_reason": None,
            "hard_blocked": False,
            "gating_notes": [],
        }

    monkeypatch.setattr(
        "app.services.gpt_market_service.GPTMarketService.analyze",
        fake_gpt_analyze,
    )

    client = TestClient(app)
    response = client.post("/market-analysis/run?symbol=aapl&gate_level=4")
    assert response.status_code == 200

    payload = response.json()
    assert payload["symbol"] == "AAPL"
    assert payload["gate_level"] == 4
    assert payload["has_indicators"] is True
    assert "entry_score" in payload
    assert "quant_score" in payload
    assert "buy_score" in payload
    assert "sell_score" in payload
    assert payload["action_hint"] in {"buy_candidate", "watch", "hold"}
    assert payload["reason"] == "test analysis"
    assert "price" in payload["indicators"]




def test_market_analysis_run_passes_explicit_and_default_market_to_gpt(monkeypatch):
    monkeypatch.setattr(
        MarketDataService,
        "get_recent_bars",
        lambda self, symbol, limit=120, timeframe="1Min": make_dummy_bars(),
    )
    calls = []

    def fake_run_and_save(self, db, symbol, indicators, gate_level=None, event_context=None, market="US"):
        calls.append({"symbol": symbol, "market": market, "gate_level": gate_level})
        return SimpleNamespace(
            id=len(calls),
            symbol=symbol,
            market_regime="trend",
            entry_bias="long",
            entry_allowed=True,
            market_confidence=0.72,
            risk_note="test analysis",
            macro_summary="test macro",
            gate_level=gate_level,
            gate_profile_name="test",
            hard_block_reason=None,
            hard_blocked=False,
            gating_notes="[]",
            created_at="2026-05-12T00:00:00Z",
        )

    monkeypatch.setattr(
        "app.services.gpt_market_service.GPTMarketService.run_and_save",
        fake_run_and_save,
    )

    client = TestClient(app)

    kr_response = client.post("/market-analysis/run?symbol=005930&market=KR&gate_level=2")
    assert kr_response.status_code == 200
    assert kr_response.json()["market"] == "KR"

    us_response = client.post("/market-analysis/run?symbol=aapl&gate_level=4")
    assert us_response.status_code == 200
    assert us_response.json()["market"] == "US"

    assert calls[0] == {"symbol": "005930", "market": "KR", "gate_level": 2}
    assert calls[1] == {"symbol": "AAPL", "market": "US", "gate_level": 4}


def test_market_analysis_run_returns_json_error(monkeypatch):
    def fail_bars(self, symbol, limit=120, timeframe="1Min"):
        raise RuntimeError("market data unavailable")

    monkeypatch.setattr(MarketDataService, "get_recent_bars", fail_bars)

    client = TestClient(app)
    response = client.post("/market-analysis/run?symbol=AAPL&gate_level=4")
    assert response.status_code == 502
    assert response.json()["detail"]["error"] == "market_analysis_failed"
    assert response.json()["detail"]["symbol"] == "AAPL"


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


def test_market_analysis_run_weak_setup_is_not_entry_ready(monkeypatch):
    monkeypatch.setattr(
        MarketDataService,
        "get_recent_bars",
        lambda self, symbol, limit=120, timeframe="1Min": make_dummy_bars(),
    )

    def weak_quant(self, indicators, gate_level=None):
        return {
            "quant_buy_score": 40.0,
            "quant_sell_score": 35.0,
            "quant_reason": "weak quant setup",
            "quant_notes": ["score_threshold_not_met"],
        }

    def neutral_ai(self, *, indicators, quant_buy_score, quant_sell_score):
        return {
            "ai_buy_score": 40.0,
            "ai_sell_score": 35.0,
            "ai_reason": "ai neutral",
        }

    def fake_gpt_analyze(self, db, symbol, indicators, gate_level=None):
        return {
            "market_regime": "range",
            "entry_bias": "neutral",
            "entry_allowed": True,
            "market_confidence": 0.70,
            "reason": "No strong long entry edge; setup lacks a clean long edge.",
            "gate_level": gate_level,
            "gate_profile_name": "conservative",
            "hard_block_reason": None,
            "hard_blocked": False,
            "gating_notes": [],
        }

    monkeypatch.setattr("app.services.quant_signal_service.QuantSignalService.score", weak_quant)
    monkeypatch.setattr("app.services.ai_signal_service.AISignalService.adjust", neutral_ai)
    monkeypatch.setattr("app.services.gpt_market_service.GPTMarketService.analyze", fake_gpt_analyze)

    with SessionLocal() as db:
        initial_orders = db.query(OrderLog).count()

    client = TestClient(app)
    response = client.post("/market-analysis/run?symbol=AAPL&gate_level=2")
    assert response.status_code == 200
    payload = response.json()
    assert payload["entry_ready"] is False
    assert payload["action_hint"] in {"hold", "watch"}
    assert payload["block_reason"] in {"market_research_blocked", "score_threshold_not_met"}

    with SessionLocal() as db:
        assert db.query(OrderLog).count() == initial_orders


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


def test_market_analysis_watchlist_does_not_mark_weak_holds_as_buy_candidates(monkeypatch):
    monkeypatch.setattr(
        MarketDataService,
        "get_recent_bars",
        lambda self, symbol, limit=120, timeframe="1Min": make_dummy_bars(),
    )

    def weak_quant(self, indicators, gate_level=None):
        return {
            "quant_buy_score": 42.0,
            "quant_sell_score": 30.0,
            "quant_reason": "weak quant setup",
            "quant_notes": ["score_threshold_not_met"],
        }

    def neutral_ai(self, *, indicators, quant_buy_score, quant_sell_score):
        return {
            "ai_buy_score": 42.0,
            "ai_sell_score": 30.0,
            "ai_reason": "ai neutral",
        }

    monkeypatch.setattr("app.services.quant_signal_service.QuantSignalService.score", weak_quant)
    monkeypatch.setattr("app.services.ai_signal_service.AISignalService.adjust", neutral_ai)

    with SessionLocal() as db:
        initial_orders = db.query(OrderLog).count()

    client = TestClient(app)
    response = client.post("/market-analysis/watchlist?gate_level=2")
    assert response.status_code == 200
    payload = response.json()

    assert payload["should_trade"] is False
    assert payload["best_candidate"]["entry_ready"] is False
    assert payload["best_candidate"]["action_hint"] != "buy_candidate"
    assert all(row["entry_ready"] is False for row in payload["watchlist"])
    assert all(row["action_hint"] != "buy_candidate" for row in payload["watchlist"])

    with SessionLocal() as db:
        assert db.query(OrderLog).count() == initial_orders
