from types import SimpleNamespace

from app.db.models import SignalLog
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