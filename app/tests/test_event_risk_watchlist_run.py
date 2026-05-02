from app.config import get_settings
from app.services.watchlist_run_service import WatchlistRunService


def _watchlist_entry(symbol: str, quant_score: float) -> dict:
    return {
        "symbol": symbol,
        "entry_score": quant_score,
        "should_trade": True,
        "entry_ready": True,
        "trade_allowed": False,
        "action_hint": "buy_candidate",
        "block_reason": None,
        "quant_score": quant_score,
        "quant_buy_score": quant_score,
        "quant_sell_score": 20.0,
        "ai_buy_score": 20.0,
        "ai_sell_score": 20.0,
        "quant_reason": "quant candidate",
        "ai_reason": "ai neutral",
        "has_indicators": True,
    }


def _event_risk(symbol: str, **overrides) -> dict:
    payload = {
        "symbol": symbol.upper(),
        "market": "US",
        "has_near_event": False,
        "event_type": None,
        "event_date": None,
        "event_time_label": "unknown",
        "days_to_event": None,
        "risk_level": "low",
        "entry_blocked": False,
        "scale_in_blocked": False,
        "position_size_multiplier": 1.0,
        "force_gate_level": None,
        "reason": "no structured event risk found",
        "source": None,
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def _patch_watchlist_run(
    monkeypatch,
    *,
    symbol_scores: dict[str, float],
    research_scores: dict[str, int] | None = None,
):
    settings = get_settings()
    monkeypatch.setattr(settings, "alpaca_base_url", "https://paper-api.alpaca.markets")
    monkeypatch.setattr(settings, "watchlist_top_candidates_for_research", len(symbol_scores))

    symbols = list(symbol_scores)
    watchlist = [_watchlist_entry(symbol, score) for symbol, score in symbol_scores.items()]
    research_scores = research_scores or {symbol: 80 for symbol in symbols}

    def fake_analyze(self, gate_level):
        return {
            "watchlist": watchlist,
            "best_candidate": watchlist[0] if watchlist else None,
            "best_score": watchlist[0]["quant_score"] if watchlist else 0.0,
            "should_trade": False,
            "watchlist_source": "config/watchlist.yaml",
            "configured_symbol_count": len(watchlist),
            "analyzed_symbol_count": len(watchlist),
            "max_watchlist_size": 50,
        }

    def fake_score_symbol(self, symbol, gate_level):
        score = symbol_scores[symbol.upper()]
        return (_watchlist_entry(symbol.upper(), score), {"dummy": True})

    def fake_research(self, db, symbol, indicators, gate_level):
        research_score = research_scores[symbol.upper()]
        return {
            "market_research_score": research_score,
            "market_confidence": research_score / 100,
            "event_risk": "low",
            "sector_context": "trend",
            "news_risk": "low",
            "macro_risk": "low",
            "gpt_action_hint": "allow_entry",
            "market_research_reason": "research allows entry",
            "hard_blocked": False,
            "soft_entry_allowed": True,
            "entry_allowed": True,
            "market_research_blocked": False,
            "fallback_used": False,
        }

    monkeypatch.setattr("app.services.watchlist_service.WatchlistService.analyze", fake_analyze)
    monkeypatch.setattr("app.services.watchlist_service.WatchlistService._score_symbol", fake_score_symbol)
    monkeypatch.setattr(
        "app.services.watchlist_research_service.WatchlistResearchService.analyze_candidate",
        fake_research,
    )


def _patch_event_risk(monkeypatch, event_by_symbol: dict[str, dict]):
    calls = []

    def fake_get_event_risk(
        self,
        db,
        *,
        symbol,
        market,
        as_of_date=None,
        intent="entry",
    ):
        calls.append({"symbol": symbol.upper(), "market": market, "intent": intent})
        return event_by_symbol.get(symbol.upper(), _event_risk(symbol))

    monkeypatch.setattr(
        "app.services.event_risk_service.EventRiskService.get_event_risk",
        fake_get_event_risk,
    )
    return calls


def test_watchlist_candidate_with_d_minus_one_earnings_is_not_tradable(
    monkeypatch,
    db_session,
):
    _patch_watchlist_run(monkeypatch, symbol_scores={"AAPL": 82.0})
    calls = _patch_event_risk(
        monkeypatch,
        {
            "AAPL": _event_risk(
                "AAPL",
                has_near_event=True,
                event_type="earnings",
                event_date="2026-05-04",
                event_time_label="after_close",
                days_to_event=1,
                risk_level="high",
                entry_blocked=True,
                scale_in_blocked=True,
                position_size_multiplier=0.0,
                force_gate_level=1,
                reason="earnings within restricted window",
                source="investing",
            )
        },
    )

    payload = WatchlistRunService().run_once(db_session)
    candidate = payload["final_best_candidate"]

    assert calls == [{"symbol": "AAPL", "market": "US", "intent": "entry"}]
    assert payload["should_trade"] is False
    assert payload["triggered_symbol"] is None
    assert payload["trigger_block_reason"] == "event_risk_entry_block"
    assert candidate["entry_ready"] is False
    assert candidate["should_trade"] is False
    assert candidate["block_reason"] == "event_risk_entry_block"
    assert candidate["structured_event_risk"]["entry_blocked"] is True
    assert candidate["event_risk_detail"]["entry_blocked"] is True
    assert payload["event_risk"]["entry_blocked"] is True
    assert "event_risk_entry_block" in candidate["risk_flags"]


def test_watchlist_candidate_with_d_minus_two_earnings_stays_visible_with_size_note(
    monkeypatch,
    db_session,
):
    _patch_watchlist_run(monkeypatch, symbol_scores={"AAPL": 80.0})
    _patch_event_risk(
        monkeypatch,
        {
            "AAPL": _event_risk(
                "AAPL",
                has_near_event=True,
                event_type="earnings",
                event_date="2026-05-05",
                event_time_label="before_open",
                days_to_event=2,
                risk_level="medium",
                entry_blocked=False,
                scale_in_blocked=True,
                position_size_multiplier=0.5,
                reason="earnings approaching",
                source="investing",
            )
        },
    )

    payload = WatchlistRunService().run_once(db_session)
    candidate = payload["final_ranked_candidates"][0]

    assert candidate["symbol"] == "AAPL"
    assert candidate["entry_ready"] is True
    assert candidate["block_reason"] is None
    assert candidate["final_entry_score"] == 80.0
    assert candidate["structured_event_risk"]["position_size_multiplier"] == 0.5
    assert "event_risk_position_size_reduced" in candidate["gating_notes"]
    assert "event_risk_position_size_reduced" in candidate["risk_flags"]
    assert payload["final_best_candidate"]["symbol"] == "AAPL"
    assert payload["structured_event_risk"]["position_size_multiplier"] == 0.5


def test_watchlist_no_event_keeps_existing_trade_selection(
    monkeypatch,
    db_session,
):
    _patch_watchlist_run(
        monkeypatch,
        symbol_scores={"AAPL": 82.0, "MSFT": 70.0},
        research_scores={"AAPL": 90, "MSFT": 65},
    )
    _patch_event_risk(monkeypatch, {})
    child_calls = []

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
        child_calls.append(
            {
                "symbol": symbol,
                "mode": mode,
                "request_payload": request_payload,
            }
        )
        return {
            "result": "executed",
            "order_id": 123,
            "response_payload": {
                "action": "buy",
                "reason": "risk approved",
                "risk": {"approved": True},
            },
        }

    monkeypatch.setattr("app.brokers.alpaca_client.AlpacaClient.get_position", lambda self, symbol: None)
    monkeypatch.setattr(
        "app.services.trading_orchestrator_service.TradingOrchestratorService._run_symbol_child",
        fake_child_run,
    )

    payload = WatchlistRunService().run_once(db_session)
    candidate = payload["final_best_candidate"]

    assert payload["should_trade"] is True
    assert payload["triggered_symbol"] == "AAPL"
    assert payload["trade_result"]["order_id"] == 123
    assert candidate["entry_ready"] is True
    assert candidate["block_reason"] is None
    assert candidate["final_entry_score"] == 84.0
    assert candidate["structured_event_risk"]["has_near_event"] is False
    assert "event_risk_position_size_reduced" not in candidate["gating_notes"]
    assert payload["event_risk"]["has_near_event"] is False
    assert child_calls[0]["request_payload"]["event_risk"]["has_near_event"] is False
