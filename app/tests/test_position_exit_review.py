from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting
from app.main import app


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "kis_enabled": True,
        "kis_env": "prod",
        "kis_app_key": "real-app-key",
        "kis_app_secret": "real-app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_base_url": "https://openapi.koreainvestment.com:9443",
        "kis_real_order_enabled": True,
        "kis_scheduler_allow_real_orders": False,
        "kr_scheduler_allow_real_orders": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _open_session(*, entry_allowed=True):
    return {
        "market": "KR",
        "timezone": "Asia/Seoul",
        "is_market_open": True,
        "is_entry_allowed_now": entry_allowed,
        "is_near_close": not entry_allowed,
        "closure_reason": None,
        "effective_close": "15:30",
        "no_new_entry_after": "15:00",
    }


def _position(**overrides):
    payload = {
        "symbol": "005930",
        "name": "Samsung",
        "qty": 2,
        "available_quantity": 2,
        "current_price": 4900,
        "avg_entry_price": 5000,
        "cost_basis": 10000,
        "market_value": 9800,
        "unrealized_pl": -200,
        "unrealized_plpc": -99,
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def safe_context(monkeypatch, db_session):
    monkeypatch.setattr("app.routes.strategy_positions.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.position_exit_review_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _open_session(),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [_position()],
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_open_orders",
        lambda self: [],
    )
    db_session.add(RuntimeSetting(dry_run=False, kill_switch=False))
    db_session.commit()


def test_exit_review_endpoint_returns_held_position_summary(client):
    response = client.get("/strategy/positions/exit-review")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "kis"
    assert body["market"] == "KR"
    assert body["total_position_value"] == pytest.approx(9800)
    assert body["total_unrealized_pl"] == pytest.approx(-200)
    assert body["total_unrealized_pl_pct"] == pytest.approx(-0.02)
    assert body["safety"]["read_only"] is True
    assert body["safety"]["real_order_submitted"] is False

    item = body["positions"][0]
    assert item["symbol"] == "005930"
    assert item["quantity"] == 2
    assert item["available_quantity"] == 2
    assert item["cost_basis"] == pytest.approx(10000)
    assert item["current_value"] == pytest.approx(9800)
    assert item["unrealized_pl_pct"] == pytest.approx(-0.02)
    assert item["stop_loss_triggered"] is True
    assert item["exit_review_status"] == "review_required"


def test_sell_preflight_allowed_result_does_not_create_order_or_call_submit(
    monkeypatch,
    client,
    db_session,
):
    for method in (
        "submit_market_sell",
        "submit_order",
        "submit_domestic_cash_order",
    ):
        monkeypatch.setattr(
            "app.brokers.kis_client.KisClient." + method,
            lambda *args, **kwargs: pytest.fail("preflight must stay read-only"),
            raising=False,
        )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("preflight must not use manual live flow"),
    )

    response = client.post(
        "/strategy/positions/005930/sell-preflight",
        json={"quantity_mode": "full", "confirm_live": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["preflight_status"] == "allowed"
    assert body["can_submit_after_confirmation"] is True
    assert body["final_confirmation_required"] is True
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["order_id"] is None
    assert body["broker_order_id"] is None
    assert body["kis_odno"] is None
    assert body["requested_quantity"] == pytest.approx(2)
    assert body["estimated_sell_notional"] == pytest.approx(9800)
    assert body["unrealized_pl_pct"] == pytest.approx(-0.02)
    assert db_session.query(OrderLog).count() == 0


def test_sell_preflight_blocks_when_position_does_not_exist(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [],
    )

    response = client.post("/strategy/positions/005930/sell-preflight", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["preflight_status"] == "blocked"
    assert body["position_exists"] is False
    assert body["primary_block_reason"] == "no_held_position"
    assert body["real_order_submitted"] is False


def test_sell_preflight_blocks_when_available_quantity_is_zero(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [_position(available_quantity=0)],
    )

    response = client.post("/strategy/positions/005930/sell-preflight", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["preflight_status"] == "blocked"
    assert body["available_quantity"] == 0
    assert body["primary_block_reason"] == "no_available_quantity"


def test_sell_preflight_blocks_duplicate_open_sell_order(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_open_orders",
        lambda self: [{"symbol": "005930", "side": "sell", "status": "SUBMITTED"}],
    )

    response = client.post("/strategy/positions/005930/sell-preflight", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["preflight_status"] == "blocked"
    assert body["primary_block_reason"] == "duplicate_open_sell_order"
    assert "duplicate_open_sell_order" in body["risk_flags"]


def test_sell_preflight_uses_cost_basis_pl_not_raw_percent(client):
    response = client.post("/strategy/positions/005930/sell-preflight", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["cost_basis"] == pytest.approx(10000)
    assert body["current_value"] == pytest.approx(9800)
    assert body["unrealized_pl"] == pytest.approx(-200)
    assert body["unrealized_pl_pct"] == pytest.approx(-0.02)


def test_kill_switch_blocks_sell_preflight(client, db_session):
    db_session.query(RuntimeSetting).delete()
    db_session.add(RuntimeSetting(dry_run=False, kill_switch=True))
    db_session.commit()

    response = client.post("/strategy/positions/005930/sell-preflight", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["preflight_status"] == "blocked"
    assert body["primary_block_reason"] == "kill_switch_enabled"
    assert body["kill_switch"] is True


def test_no_new_entry_window_does_not_block_exit_preflight(monkeypatch, client):
    monkeypatch.setattr(
        "app.services.position_exit_review_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _open_session(entry_allowed=False),
    )

    response = client.post("/strategy/positions/005930/sell-preflight", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["preflight_status"] == "allowed"
    assert body["market_session_allowed"] is True
    assert body["no_new_entry_window_allowed"] is True
    assert "after_no_new_entry_time" not in body["risk_flags"]
