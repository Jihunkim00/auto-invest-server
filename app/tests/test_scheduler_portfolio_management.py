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


def _patch_runtime(monkeypatch, *, max_open_positions=3, per_slot_new_entry_limit=1):
    settings = get_settings()
    monkeypatch.setattr(settings, "alpaca_base_url", "https://paper-api.alpaca.markets")
    monkeypatch.setattr(settings, "watchlist_top_candidates_for_research", 5)

    def fake_runtime(self, db):
        return {
            "default_symbol": "AAPL",
            "max_open_positions": max_open_positions,
            "per_slot_new_entry_limit": per_slot_new_entry_limit,
            "default_gate_level": 2,
            "global_daily_entry_limit": 10,
            "per_symbol_daily_entry_limit": 10,
        }

    monkeypatch.setattr(
        "app.services.runtime_setting_service.RuntimeSettingService.get_settings",
        fake_runtime,
    )


def _patch_watchlist(monkeypatch, symbol_scores: dict[str, float]):
    watchlist = [
        _watchlist_entry(symbol, score) for symbol, score in symbol_scores.items()
    ]

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
        return (_watchlist_entry(symbol.upper(), symbol_scores[symbol.upper()]), {"dummy": True})

    def fake_research(self, db, symbol, indicators, gate_level):
        return {
            "market_research_score": 85,
            "market_confidence": 0.85,
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


def _patch_positions(monkeypatch, symbols: list[str]):
    positions = [{"symbol": symbol, "qty": "1", "side": "long"} for symbol in symbols]
    monkeypatch.setattr(
        "app.services.position_lifecycle_service.PositionLifecycleService.list_open_positions",
        lambda self: positions,
    )


def _patch_child_runner(monkeypatch):
    calls = []

    def fake_child(
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
        call = {
            "symbol": symbol,
            "mode": mode,
            "allowed_actions": allowed_actions,
            "symbol_role": symbol_role,
            "enforce_entry_limits": enforce_entry_limits,
            "request_payload": request_payload or {},
        }
        calls.append(call)
        return {
            "result": "skipped",
            "symbol": symbol,
            "mode": mode,
            "allowed_actions": allowed_actions,
            "symbol_role": symbol_role,
            "order_id": None,
            "response_payload": {"action": "hold", "reason": "test child"},
        }

    monkeypatch.setattr(
        "app.services.trading_orchestrator_service.TradingOrchestratorService._run_symbol_child",
        fake_child,
    )
    return calls


def test_scheduler_manages_open_positions_up_to_max_without_new_entry(monkeypatch, db_session):
    _patch_runtime(monkeypatch, max_open_positions=3)
    _patch_positions(monkeypatch, ["GOOG", "HON", "AAPL", "MSFT"])
    _patch_watchlist(monkeypatch, {"NVDA": 90.0})
    calls = _patch_child_runner(monkeypatch)

    payload = WatchlistRunService().run_once(
        db_session,
        trigger_source="scheduler",
        scheduler_slot="midday",
    )

    assert [call["symbol"] for call in calls] == ["GOOG", "HON", "AAPL"]
    assert all(call["mode"] == "position_management" for call in calls)
    assert all(call["symbol_role"] == "open_position" for call in calls)
    assert all(call["allowed_actions"] == ["hold", "sell"] for call in calls)
    assert all(call["enforce_entry_limits"] is False for call in calls)
    assert payload["managed_symbols"] == ["GOOG", "HON", "AAPL"]
    assert payload["open_position_count"] == 4
    assert payload["max_open_positions"] == 3
    assert payload["entry_evaluated"] is False
    assert payload["entry_skip_reason"] == "max_open_positions_reached"


def test_scheduler_evaluates_one_new_entry_when_capacity_remains(monkeypatch, db_session):
    _patch_runtime(monkeypatch, max_open_positions=3)
    _patch_positions(monkeypatch, ["GOOG", "HON"])
    _patch_watchlist(monkeypatch, {"MSFT": 88.0})
    calls = _patch_child_runner(monkeypatch)

    payload = WatchlistRunService().run_once(
        db_session,
        trigger_source="scheduler",
        scheduler_slot="open_phase",
    )

    assert [call["symbol"] for call in calls] == ["GOOG", "HON", "MSFT"]
    assert calls[0]["mode"] == "position_management"
    assert calls[1]["mode"] == "position_management"
    assert calls[2]["mode"] == "entry_scan"
    assert calls[2]["allowed_actions"] == ["hold", "buy"]
    assert calls[2]["symbol_role"] == "watchlist_candidate"
    assert calls[2]["enforce_entry_limits"] is True
    assert payload["entry_candidate_symbol"] == "MSFT"
    assert payload["entry_evaluated"] is True


def test_scheduler_does_not_duplicate_open_best_candidate(monkeypatch, db_session):
    _patch_runtime(monkeypatch, max_open_positions=3)
    _patch_positions(monkeypatch, ["GOOG", "HON"])
    _patch_watchlist(monkeypatch, {"HON": 92.0, "MSFT": 86.0})
    calls = _patch_child_runner(monkeypatch)

    payload = WatchlistRunService().run_once(
        db_session,
        trigger_source="scheduler",
        scheduler_slot="before_close",
    )

    assert [call["symbol"] for call in calls] == ["GOOG", "HON", "MSFT"]
    assert calls[1]["mode"] == "position_management"
    assert calls[2]["mode"] == "entry_scan"
    assert payload["final_best_candidate"]["symbol"] == "HON"
    assert payload["entry_candidate_symbol"] == "MSFT"
    assert payload["entry_evaluated"] is True


def test_entry_limit_does_not_block_open_position_management(monkeypatch, db_session):
    _patch_runtime(monkeypatch, max_open_positions=3, per_slot_new_entry_limit=0)
    _patch_positions(monkeypatch, ["GOOG"])
    _patch_watchlist(monkeypatch, {"MSFT": 88.0})
    calls = _patch_child_runner(monkeypatch)

    payload = WatchlistRunService().run_once(
        db_session,
        trigger_source="scheduler",
        scheduler_slot="midday",
    )

    assert [call["symbol"] for call in calls] == ["GOOG"]
    assert calls[0]["mode"] == "position_management"
    assert calls[0]["enforce_entry_limits"] is False
    assert payload["entry_evaluated"] is False
    assert payload["entry_skip_reason"] == "per_slot_new_entry_limit_reached"


def test_event_risk_does_not_block_open_position_management(monkeypatch, db_session):
    _patch_runtime(monkeypatch, max_open_positions=3)
    _patch_positions(monkeypatch, ["GOOG"])
    _patch_watchlist(monkeypatch, {"GOOG": 90.0})
    calls = _patch_child_runner(monkeypatch)

    def blocked_event_risk(self, db, *, symbol, market, as_of_date=None, intent="entry"):
        return {
            "symbol": symbol,
            "market": market,
            "has_near_event": True,
            "event_type": "earnings",
            "event_date": "2026-05-04",
            "event_time_label": "after_close",
            "days_to_event": 1,
            "risk_level": "high",
            "entry_blocked": True,
            "scale_in_blocked": True,
            "position_size_multiplier": 0.0,
            "force_gate_level": 1,
            "reason": "earnings within restricted window",
            "source": "investing",
            "warnings": [],
        }

    monkeypatch.setattr(
        "app.services.event_risk_service.EventRiskService.get_event_risk",
        blocked_event_risk,
    )

    payload = WatchlistRunService().run_once(
        db_session,
        trigger_source="scheduler",
        scheduler_slot="midday",
    )

    assert [call["symbol"] for call in calls] == ["GOOG"]
    assert calls[0]["mode"] == "position_management"
    assert calls[0]["allowed_actions"] == ["hold", "sell"]
    assert calls[0]["enforce_entry_limits"] is False
    assert payload["entry_evaluated"] is False
    assert payload["entry_skip_reason"] == "no_non_open_entry_candidate"
