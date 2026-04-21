from types import SimpleNamespace

from app.services.position_lifecycle_service import PositionLifecycleService


class FakeBroker:
    def __init__(self, positions):
        self._positions = positions

    def list_positions(self):
        return self._positions


def test_new_symbol_becomes_entry_candidate(monkeypatch):
    monkeypatch.setattr("app.services.position_lifecycle_service.AlpacaClient", lambda: FakeBroker([]))

    svc = PositionLifecycleService(max_open_positions=3)
    resolved = svc.resolve_portfolio(default_symbol="AAPL", requested_symbol="MSFT", max_open_positions=3)

    assert resolved["entry_candidate_symbol"] == "MSFT"
    assert resolved["can_scan_new_entry"] is True


def test_held_requested_symbol_is_not_new_entry_candidate(monkeypatch):
    positions = [SimpleNamespace(symbol="AAPL", qty="1", side="long")]
    monkeypatch.setattr("app.services.position_lifecycle_service.AlpacaClient", lambda: FakeBroker(positions))

    svc = PositionLifecycleService(max_open_positions=3)
    resolved = svc.resolve_portfolio(default_symbol="MSFT", requested_symbol="AAPL", max_open_positions=3)

    assert resolved["entry_candidate_symbol"] == "AAPL"
    assert resolved["can_scan_new_entry"] is False
