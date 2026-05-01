from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app


class FakeBroker:
    def __init__(self, positions=None, orders=None):
        self.positions = positions or []
        self.orders = orders or []
        self.submit_called = False

    def list_positions(self):
        return self.positions

    def list_open_orders(self):
        return self.orders

    def submit_market_buy(self, *args, **kwargs):
        self.submit_called = True
        raise AssertionError("portfolio summary must not submit buy orders")

    def submit_market_sell(self, *args, **kwargs):
        self.submit_called = True
        raise AssertionError("portfolio summary must not submit sell orders")


def _client_with_broker(monkeypatch, broker):
    monkeypatch.setattr("app.routes.portfolio.AlpacaClient", lambda: broker)
    return TestClient(app)


def test_portfolio_summary_empty_portfolio(monkeypatch):
    broker = FakeBroker()
    client = _client_with_broker(monkeypatch, broker)

    response = client.get("/portfolio/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "USD"
    assert body["positions_count"] == 0
    assert body["pending_orders_count"] == 0
    assert body["total_cost_basis"] == 0
    assert body["total_market_value"] == 0
    assert body["total_unrealized_pl"] == 0
    assert body["total_unrealized_plpc"] == 0
    assert body["positions"] == []
    assert body["pending_orders"] == []


def test_portfolio_summary_one_holding_calculates_totals(monkeypatch):
    broker = FakeBroker(
        positions=[
            SimpleNamespace(
                symbol="AAPL",
                side="long",
                qty="2",
                avg_entry_price="180.0",
                current_price="186.2",
                market_value="372.4",
                unrealized_pl="12.4",
                unrealized_plpc="0.0344",
            )
        ]
    )
    client = _client_with_broker(monkeypatch, broker)

    response = client.get("/portfolio/summary")

    assert response.status_code == 200
    body = response.json()
    position = body["positions"][0]
    assert body["positions_count"] == 1
    assert position["symbol"] == "AAPL"
    assert position["qty"] == 2
    assert position["avg_entry_price"] == 180
    assert position["cost_basis"] == 360
    assert position["current_price"] == 186.2
    assert position["market_value"] == 372.4
    assert position["unrealized_pl"] == 12.4
    assert position["unrealized_plpc"] == 0.0344
    assert body["total_cost_basis"] == 360
    assert body["total_market_value"] == 372.4
    assert body["total_unrealized_pl"] == 12.4
    assert body["total_unrealized_plpc"] == pytest.approx(12.4 / 360)


def test_portfolio_summary_pending_buy_order_uses_notional_estimate(monkeypatch):
    broker = FakeBroker(
        orders=[
            SimpleNamespace(
                id="buy-order-1",
                symbol="AAPL",
                side="buy",
                order_type="market",
                status="accepted",
                qty=None,
                notional="100.0",
                limit_price=None,
                submitted_at="2026-05-01T12:00:00Z",
            )
        ]
    )
    client = _client_with_broker(monkeypatch, broker)

    response = client.get("/portfolio/summary")

    assert response.status_code == 200
    order = response.json()["pending_orders"][0]
    assert order["id"] == "buy-order-1"
    assert order["symbol"] == "AAPL"
    assert order["side"] == "buy"
    assert order["type"] == "market"
    assert order["status"] == "accepted"
    assert order["qty"] is None
    assert order["notional"] == 100.0
    assert order["estimated_amount"] == 100.0


def test_portfolio_summary_pending_sell_order_keeps_qty_and_status(monkeypatch):
    broker = FakeBroker(
        orders=[
            SimpleNamespace(
                id="sell-order-1",
                symbol="TSLA",
                side="sell",
                order_type="market",
                status="pending_new",
                qty="1",
                notional=None,
                limit_price=None,
                submitted_at="2026-05-01T12:05:00Z",
            )
        ]
    )
    client = _client_with_broker(monkeypatch, broker)

    response = client.get("/portfolio/summary")

    assert response.status_code == 200
    order = response.json()["pending_orders"][0]
    assert order["symbol"] == "TSLA"
    assert order["side"] == "sell"
    assert order["qty"] == 1
    assert order["status"] == "pending_new"
    assert order["estimated_amount"] is None


def test_portfolio_summary_is_read_only(monkeypatch):
    broker = FakeBroker(
        positions=[
            SimpleNamespace(
                symbol="AAPL",
                side="long",
                qty="1",
                avg_entry_price="100",
                current_price="101",
                market_value="101",
                unrealized_pl="1",
                unrealized_plpc="0.01",
            )
        ],
        orders=[
            SimpleNamespace(
                id="order-1",
                symbol="AAPL",
                side="buy",
                order_type="market",
                status="new",
                qty=None,
                notional="50",
                limit_price=None,
                submitted_at=None,
            )
        ],
    )
    client = _client_with_broker(monkeypatch, broker)

    response = client.get("/portfolio/summary")

    assert response.status_code == 200
    assert broker.submit_called is False


def test_portfolio_summary_filters_final_orders(monkeypatch):
    broker = FakeBroker(
        orders=[
            SimpleNamespace(
                id="filled-order",
                symbol="AAPL",
                side="buy",
                order_type="market",
                status="filled",
                qty="1",
                notional=None,
                limit_price=None,
                submitted_at=None,
            ),
            SimpleNamespace(
                id="rejected-order",
                symbol="AAPL",
                side="buy",
                order_type="market",
                status="rejected",
                qty="1",
                notional=None,
                limit_price=None,
                submitted_at=None,
            ),
        ]
    )
    client = _client_with_broker(monkeypatch, broker)

    response = client.get("/portfolio/summary")

    assert response.status_code == 200
    assert response.json()["pending_orders"] == []


def test_portfolio_summary_broker_error_returns_500(monkeypatch):
    class ExplodingBroker(FakeBroker):
        def list_positions(self):
            raise RuntimeError("alpaca unavailable")

    client = _client_with_broker(monkeypatch, ExplodingBroker())

    response = client.get("/portfolio/summary")

    assert response.status_code == 500
    assert "Failed to fetch portfolio summary" in response.json()["detail"]
