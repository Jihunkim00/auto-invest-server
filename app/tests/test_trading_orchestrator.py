from types import SimpleNamespace

from app.db.models import SignalLog, TradeRunLog
from app.services.trading_orchestrator_service import TradingOrchestratorService
from app.services.trading_service import TradingService


class DummyBroker:
    def __init__(self, position=None):
        self._position = position

    def get_position(self, symbol):
        return self._position


def test_open_positions_managed_before_entry(monkeypatch, db_session):
    svc = TradingOrchestratorService()
    monkeypatch.setattr(svc.runtime_settings, "get_settings", lambda db: {
        "default_symbol": "AAPL",
        "max_open_positions": 3,
        "per_slot_new_entry_limit": 1,
        "default_gate_level": 2,
    })
    monkeypatch.setattr(svc.position_lifecycle, "resolve_portfolio", lambda **kwargs: {
        "mode_summary": "portfolio_management",
        "open_positions": [{"symbol": "AAPL", "qty": "1", "side": "long"}],
        "open_position_count": 1,
        "max_open_positions": 3,
        "portfolio_has_room": True,
        "entry_candidate_symbol": "MSFT",
        "can_scan_new_entry": True,
    })

    call_order = []

    def fake_child(*args, **kwargs):
        call_order.append((kwargs["symbol"], kwargs["symbol_role"]))
        return {"result": "skipped", "symbol": kwargs["symbol"], "symbol_role": kwargs["symbol_role"]}

    monkeypatch.setattr(svc, "_run_symbol_child", fake_child)

    result = svc.run(db_session, trigger_source="manual", symbol="MSFT")

    assert call_order == [("AAPL", "open_position"), ("MSFT", "entry_candidate")]
    assert result["portfolio"]["entry_evaluated"] is True


def test_max_open_positions_blocks_new_entry(monkeypatch, db_session):
    svc = TradingOrchestratorService()
    monkeypatch.setattr(svc.runtime_settings, "get_settings", lambda db: {
        "default_symbol": "AAPL",
        "max_open_positions": 1,
        "per_slot_new_entry_limit": 1,
        "default_gate_level": 2,
    })
    monkeypatch.setattr(svc.position_lifecycle, "resolve_portfolio", lambda **kwargs: {
        "mode_summary": "portfolio_management",
        "open_positions": [{"symbol": "AAPL", "qty": "1", "side": "long"}],
        "open_position_count": 1,
        "max_open_positions": 1,
        "portfolio_has_room": False,
        "entry_candidate_symbol": "MSFT",
        "can_scan_new_entry": False,
    })
    monkeypatch.setattr(svc, "_run_symbol_child", lambda *a, **k: {"result": "skipped"})

    result = svc.run(db_session, trigger_source="manual", symbol="MSFT")

    assert result["portfolio"]["entry_evaluated"] is False
    assert result["portfolio"]["entry_skip_reason"] == "max_open_positions_reached"


def test_per_slot_entry_limit_caps_entry_runs(monkeypatch, db_session):
    svc = TradingOrchestratorService()
    monkeypatch.setattr(svc.runtime_settings, "get_settings", lambda db: {
        "default_symbol": "AAPL",
        "max_open_positions": 3,
        "per_slot_new_entry_limit": 0,
        "default_gate_level": 2,
    })
    monkeypatch.setattr(svc.position_lifecycle, "resolve_portfolio", lambda **kwargs: {
        "mode_summary": "entry_scan",
        "open_positions": [],
        "open_position_count": 0,
        "max_open_positions": 3,
        "portfolio_has_room": True,
        "entry_candidate_symbol": "MSFT",
        "can_scan_new_entry": True,
    })

    run_calls = []
    monkeypatch.setattr(svc, "_run_symbol_child", lambda *a, **k: run_calls.append(1) or {"result": "skipped"})

    result = svc.run(db_session, trigger_source="manual", symbol="MSFT")

    assert run_calls == []
    assert result["portfolio"]["entry_skip_reason"] == "per_slot_new_entry_limit_reached"


def test_held_symbol_buy_signal_suppressed_in_position_management(monkeypatch, db_session):
    service = TradingService()
    service.broker = DummyBroker(position=None)

    signal = SignalLog(
        symbol="AAPL",
        action="buy",
        gate_level=2,
        gate_profile_name="conservative",
        gating_notes="[]",
        risk_flags="[]",
        final_sell_score=20,
        final_buy_score=70,
        signal_status="created",
    )
    db_session.add(signal)
    db_session.commit()
    db_session.refresh(signal)

    monkeypatch.setattr(service.signal_service, "run", lambda *a, **k: signal)

    result = service.run_once(
        db_session,
        symbol="AAPL",
        mode="position_management",
        allowed_actions=["hold", "sell"],
    )

    assert result["result"] == "skipped"
    assert result["action"] == "hold"
    assert result["original_action"] == "buy"


def test_trading_run_once_skips_hold_signal_when_threshold_not_met(monkeypatch, db_session):
    service = TradingService()

    signal = SignalLog(
        symbol="AAPL",
        action="hold",
        gate_level=2,
        gate_profile_name="conservative",
        gating_notes='["score_threshold_not_met"]',
        risk_flags="[]",
        final_sell_score=20,
        final_buy_score=50,
        signal_status="skipped",
    )
    db_session.add(signal)
    db_session.commit()
    db_session.refresh(signal)

    monkeypatch.setattr(service.signal_service, "run", lambda *a, **k: signal)

    result = service.run_once(db_session, symbol="AAPL", mode="entry_scan", allowed_actions=["hold", "buy"])

    assert result["result"] == "skipped"
    assert result["action"] == "hold"
    assert result["signal_status"] == "skipped"
    assert result["risk"]["approved"] is False
    assert result["related_order_id"] is None


def test_position_management_auto_exit_reasons_preserved_in_run_log(monkeypatch, db_session):
    class AutoExitBroker:
        def __init__(self):
            self.last_submit_qty = None

        def get_position(self, symbol):
            return SimpleNamespace(symbol=symbol, qty="2", unrealized_plpc=-0.02)

        def get_latest_price(self, symbol):
            return {"symbol": symbol, "price": 100.0}

        def submit_market_sell(self, symbol, qty):
            self.last_submit_qty = qty
            return SimpleNamespace(
                id="broker-order-1",
                client_order_id="client-1",
                status="filled",
                filled_qty=qty,
                filled_avg_price=100.0,
                submitted_at=None,
                filled_at=None,
                canceled_at=None,
                dict=lambda: {"id": "broker-order-1", "status": "filled"},
            )

    svc = TradingOrchestratorService()
    broker = AutoExitBroker()
    svc.trading_service.broker = broker

    signal = SignalLog(
        symbol="AAPL",
        action="hold",
        gate_level=2,
        gate_profile_name="conservative",
        gating_notes="[]",
        risk_flags="[]",
        final_sell_score=75,
        final_buy_score=20,
        signal_status="created",
    )
    db_session.add(signal)
    db_session.commit()
    db_session.refresh(signal)

    monkeypatch.setattr(svc.trading_service.signal_service, "run", lambda *a, **k: signal)
    monkeypatch.setattr(svc.runtime_settings, "get_settings", lambda db: {
        "default_symbol": "AAPL",
        "max_open_positions": 3,
        "per_slot_new_entry_limit": 1,
        "default_gate_level": 2,
    })
    monkeypatch.setattr(svc.position_lifecycle, "resolve_portfolio", lambda **kwargs: {
        "mode_summary": "portfolio_management",
        "open_positions": [{"symbol": "AAPL", "qty": "2", "side": "long"}],
        "open_position_count": 1,
        "max_open_positions": 3,
        "portfolio_has_room": True,
        "entry_candidate_symbol": "MSFT",
        "can_scan_new_entry": False,
    })
    monkeypatch.setattr(svc.guard, "precheck", lambda *a, **k: {"allowed": True})
    monkeypatch.setattr(svc.guard, "action_check", lambda *a, **k: {"allowed": True})

    result = svc.run(db_session, trigger_source="manual", symbol="AAPL")

    child = result["portfolio"]["child_runs"][0]
    assert child["response_payload"]["exit_reasons"] == ["stop_loss_triggered", "trend_breakdown_confirmed"]
    assert child["response_payload"]["exit_context"]["unrealized_plpc"] == -0.02

    child_run = (
        db_session.query(TradeRunLog)
        .filter(TradeRunLog.id == child["run_id"])
        .one()
    )
    assert '"exit_reasons": ["stop_loss_triggered", "trend_breakdown_confirmed"]' in child_run.response_payload
    assert '"unrealized_plpc": -0.02' in child_run.response_payload
