from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app


def test_trading_run_once_uses_one_selected_entry_symbol(monkeypatch):
    calls = []

    def fail_list_positions(self):
        raise AssertionError("manual run-once must not scan portfolio positions")

    def fake_get_position(self, symbol):
        return None

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
        calls.append(
            {
                "trigger_source": trigger_source,
                "symbol": symbol,
                "mode": mode,
                "allowed_actions": allowed_actions,
                "gate_level": gate_level,
                "parent_run_key": parent_run_key,
                "symbol_role": symbol_role,
                "enforce_entry_limits": enforce_entry_limits,
                "request_payload": request_payload,
            }
        )
        return {
            "result": "skipped",
            "reason": "test_manual_entry_skip",
            "symbol": symbol,
            "gate_level": gate_level,
            "signal_id": 123,
            "order_id": None,
            "response_payload": {
                "action": "hold",
                "risk": {"approved": False},
            },
        }

    monkeypatch.setattr("app.brokers.alpaca_client.AlpacaClient.list_positions", fail_list_positions)
    monkeypatch.setattr("app.brokers.alpaca_client.AlpacaClient.get_position", fake_get_position)
    monkeypatch.setattr(
        "app.services.trading_orchestrator_service.TradingOrchestratorService._run_symbol_child",
        fake_child_run,
    )

    with TestClient(app) as client:
        response = client.post("/trading/run-once?symbol=msft&gate_level=3&trigger_source=manual")

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["symbol"] == "MSFT"
    assert calls[0]["gate_level"] == 3
    assert calls[0]["mode"] == "entry_scan"
    assert calls[0]["allowed_actions"] == ["hold", "buy"]
    assert calls[0]["symbol_role"] == "manual_single_symbol"
    assert calls[0]["enforce_entry_limits"] is True

    payload = response.json()
    assert payload["symbol"] == "MSFT"
    assert payload["gate_level"] == 3
    assert payload["order_id"] is None
    assert payload["response_payload"]["action"] == "hold"


def test_trading_run_once_uses_one_selected_open_position(monkeypatch):
    calls = []

    def fake_get_position(self, symbol):
        return SimpleNamespace(symbol=symbol, qty="2", side="long")

    def fake_child_run(self, db, **kwargs):
        calls.append(kwargs)
        return {
            "result": "skipped",
            "reason": "test_manual_position_skip",
            "symbol": kwargs["symbol"],
            "gate_level": kwargs["gate_level"],
            "order_id": None,
            "response_payload": {"action": "hold", "risk": {"approved": False}},
        }

    monkeypatch.setattr("app.brokers.alpaca_client.AlpacaClient.get_position", fake_get_position)
    monkeypatch.setattr(
        "app.services.trading_orchestrator_service.TradingOrchestratorService._run_symbol_child",
        fake_child_run,
    )

    with TestClient(app) as client:
        response = client.post("/trading/run-once?symbol=aapl&gate_level=2")

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["symbol"] == "AAPL"
    assert calls[0]["mode"] == "position_management"
    assert calls[0]["allowed_actions"] == ["hold", "sell"]
    assert calls[0]["symbol_role"] == "manual_single_symbol"
    assert calls[0]["enforce_entry_limits"] is False
