from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.database import SessionLocal
from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.main import app


def make_watchlist_entry(symbol, quant_score):
    return {
        "symbol": symbol,
        "entry_score": 0.0,
        "should_trade": False,
        "quant_score": quant_score,
        "quant_buy_score": quant_score,
        "quant_sell_score": 20.0,
        "ai_buy_score": 10.0,
        "ai_sell_score": 20.0,
        "quant_reason": "quant baseline",
        "ai_reason": "ai neutral",
        "has_indicators": True,
    }


def test_trading_run_watchlist_once_holds_when_final_score_is_too_low(monkeypatch):
    settings = get_settings()
    settings.alpaca_base_url = "https://paper-api.alpaca.markets"

    symbols = [f"SYM{i}" for i in range(50)]
    watchlist = [make_watchlist_entry(symbol, quant_score=60.0) for symbol in symbols]

    def fake_analyze(self, gate_level):
        return {
            "watchlist": watchlist,
            "best_candidate": watchlist[0],
            "best_score": 60.0,
            "should_trade": False,
            "watchlist_source": "config/watchlist.yaml",
            "configured_symbol_count": 50,
            "analyzed_symbol_count": 50,
            "max_watchlist_size": 50,
        }

    def fake_score_symbol(self, symbol, gate_level):
        return (
            {
                "symbol": symbol,
                "entry_score": 60.0,
                "should_trade": False,
                "quant_score": 60.0,
                "quant_buy_score": 60.0,
                "quant_sell_score": 20.0,
                "ai_buy_score": 10.0,
                "ai_sell_score": 20.0,
                "quant_reason": "quant baseline",
                "ai_reason": "ai neutral",
                "has_indicators": True,
            },
            {"dummy": True},
        )

    def fake_gpt_analyze(self, db, symbol, indicators, gate_level):
        return {
            "market_confidence": 0.50,
            "entry_allowed": True,
            "hard_blocked": False,
            "market_regime": "range",
            "entry_bias": "neutral",
            "reason": "Research fallback with neutral signal.",
            "audit": {"fallback_used": True},
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

    with SessionLocal() as db:
        initial_runs = db.query(TradeRunLog).count()
        initial_signals = db.query(SignalLog).count()
        initial_orders = db.query(OrderLog).count()

    with TestClient(app) as client:
        trade_response = client.post("/trading/run-watchlist-once")
        assert trade_response.status_code == 200
        trade_payload = trade_response.json()

        assert trade_payload["should_trade"] is False
        assert trade_payload["triggered_symbol"] is None
        assert trade_payload["trigger_block_reason"] == "final_score_below_min_entry"
        assert trade_payload["quant_candidates_count"] == 5
        assert trade_payload["researched_candidates_count"] == 5
        assert trade_payload["final_score_gap"] == 0.0
        assert trade_payload["trade_result"]["action"] == "hold"
        assert trade_payload["trade_result"]["order_id"] is None
        assert trade_payload["trade_result"]["reason"] == "final_score_below_min_entry"

    with SessionLocal() as db:
        assert db.query(TradeRunLog).count() == initial_runs + 1
        assert db.query(SignalLog).count() == initial_signals
        assert db.query(OrderLog).count() == initial_orders


def test_trading_run_watchlist_once_executes_one_order_when_best_candidate_passes(monkeypatch):
    settings = get_settings()
    settings.alpaca_base_url = "https://paper-api.alpaca.markets"

    symbols = ["AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA", "TSLA", "NFLX", "INTC", "AMD"]
    watchlist = [make_watchlist_entry(symbol, quant_score=60.0 + i * 2) for i, symbol in enumerate(symbols)]

    def fake_analyze(self, gate_level):
        return {
            "watchlist": watchlist,
            "best_candidate": watchlist[-1],
            "best_score": 78.0,
            "should_trade": False,
            "watchlist_source": "config/watchlist.yaml",
            "configured_symbol_count": len(symbols),
            "analyzed_symbol_count": len(symbols),
            "max_watchlist_size": 50,
        }

    def fake_score_symbol(self, symbol, gate_level):
        quant_score = next(item["quant_score"] for item in watchlist if item["symbol"] == symbol)
        return (
            {
                "symbol": symbol,
                "entry_score": 0.0,
                "should_trade": False,
                "quant_score": quant_score,
                "quant_buy_score": quant_score,
                "quant_sell_score": 20.0,
                "ai_buy_score": 20.0,
                "ai_sell_score": 20.0,
                "quant_reason": "quant candidate",
                "ai_reason": "ai neutral",
                "has_indicators": True,
            },
            {"dummy": True},
        )

    def fake_gpt_analyze(self, db, symbol, indicators, gate_level):
        confidence = 0.88 if symbol == "AMD" else 0.70
        return {
            "market_confidence": confidence,
            "entry_allowed": True,
            "hard_blocked": False,
            "market_regime": "trend",
            "entry_bias": "long",
            "reason": "Positive market research.",
            "audit": {"fallback_used": False},
        }

    def fake_child_run(
        self,
        db,
        *,
        trigger_source,
        symbol,
        mode,
        allowed_actions,
        gate_level,
        parent_run_key,
        symbol_role,
        enforce_entry_limits,
        request_payload=None,
    ):
        return {
            "result": "executed",
            "order_id": 1,
            "response_payload": {
                "action": "buy",
                "reason": "risk approved",
                "risk": {"approved": True},
            },
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
    monkeypatch.setattr(
        "app.brokers.alpaca_client.AlpacaClient.get_position",
        lambda self, symbol: None,
    )
    monkeypatch.setattr(
        "app.services.trading_orchestrator_service.TradingOrchestratorService._run_symbol_child",
        fake_child_run,
    )

    with SessionLocal() as db:
        initial_runs = db.query(TradeRunLog).count()

    with TestClient(app) as client:
        trade_response = client.post("/trading/run-watchlist-once")
        assert trade_response.status_code == 200
        trade_payload = trade_response.json()

        assert trade_payload["should_trade"] is True
        assert trade_payload["triggered_symbol"] == "AMD"
        assert trade_payload["trade_result"]["action"] == "buy"
        assert trade_payload["trade_result"]["risk_approved"] is True
        assert trade_payload["trade_result"]["order_id"] == 1
        assert trade_payload["final_best_candidate"]["symbol"] == "AMD"
        assert trade_payload["quant_candidates_count"] == 5
        assert trade_payload["researched_candidates_count"] == 5

    with SessionLocal() as db:
        assert db.query(TradeRunLog).count() == initial_runs + 1
