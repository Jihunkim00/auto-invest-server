import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, SignalLog, TradeRunLog
from app.main import app
from app.services.kis_dry_run_risk_service import normalize_exit_threshold_decimal


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


def _open_session():
    return {
        "market": "KR",
        "timezone": "Asia/Seoul",
        "is_market_open": True,
        "is_entry_allowed_now": True,
        "is_near_close": False,
        "closure_reason": None,
        "closure_name": None,
        "effective_close": "15:30",
        "no_new_entry_after": "15:00",
    }


def _balance(**overrides):
    payload = {
        "provider": "kis",
        "market": "KR",
        "currency": "KRW",
        "cash": 10_000_000,
        "total_asset_value": 20_000_000,
        "unrealized_pl": 0,
    }
    payload.update(overrides)
    return payload


def _position(**overrides):
    payload = {
        "symbol": "005930",
        "name": "Samsung",
        "qty": 2,
        "current_price": 72000,
        "avg_entry_price": 72000,
        "cost_basis": 144000,
        "market_value": 144000,
        "unrealized_pl": 0,
        "unrealized_plpc": 0,
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
def safe_preflight(monkeypatch, db_session):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.kis_live_exit_preflight_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _open_session(),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        lambda self: _balance(),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [_position()],
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_open_orders",
        lambda self: [],
    )
    db_session.add(RuntimeSetting(dry_run=False))
    db_session.commit()


def test_preflight_does_not_call_kis_or_manual_submit(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_order",
        lambda *args, **kwargs: pytest.fail("preflight must not call submit_order"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("preflight must not call KIS cash submit"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("preflight must not call manual submit"),
    )

    response = client.post("/kis/live-exit/preflight-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False


def test_preflight_only_evaluates_held_positions(monkeypatch, client, db_session):
    db_session.query(RuntimeSetting).delete()
    db_session.add(RuntimeSetting(dry_run=False, default_symbol="999999"))
    db_session.commit()
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(
                symbol="005930",
                cost_basis=10000,
                market_value=9800,
                current_price=4900,
                unrealized_pl=-200,
                unrealized_plpc=-2,
            )
        ],
    )

    response = client.post("/kis/live-exit/preflight-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "sell"
    assert body["symbol"] == "005930"
    assert "999999" not in json.dumps(body)
    assert db_session.query(OrderLog).count() == 0


def test_preflight_never_creates_buy_action(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(
                symbol="005930",
                action="buy",
                final_buy_score=99,
                unrealized_plpc=0,
            )
        ],
    )

    response = client.post("/kis/live-exit/preflight-once", json={})

    assert response.status_code == 200
    assert response.json()["action"] == "hold"
    assert response.json()["action"] != "buy"


def test_preflight_returns_sell_when_stop_loss_triggered(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(
                cost_basis=10000,
                market_value=9800,
                current_price=4900,
                unrealized_pl=-200,
                unrealized_plpc=-2,
            )
        ],
    )

    response = client.post("/kis/live-exit/preflight-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "sell"
    assert body["reason"] == "stop_loss_triggered"
    assert body["unrealized_pl_pct"] == pytest.approx(-0.02)
    assert body["stop_loss_threshold_pct"] == pytest.approx(2.0)
    assert body["exit_trigger_source"] == "cost_basis"
    assert body["would_submit_if_enabled"] is True
    assert "live_scheduler_orders_disabled" in body["blocked_by"]


def test_preflight_returns_sell_when_take_profit_triggered(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(
                cost_basis=10000,
                market_value=10200,
                current_price=5100,
                unrealized_pl=200,
                unrealized_plpc=2,
            )
        ],
    )

    response = client.post("/kis/live-exit/preflight-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "sell"
    assert body["reason"] == "take_profit_triggered"
    assert body["unrealized_pl_pct"] == pytest.approx(0.02)
    assert body["take_profit_threshold_pct"] == pytest.approx(2.0)
    assert body["would_submit_if_enabled"] is True


def test_preflight_small_profit_amount_does_not_trigger_take_profit(
    monkeypatch, client
):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(
                symbol="091810",
                qty=11,
                current_price=897,
                avg_entry_price=0,
                cost_basis=9841,
                market_value=9867,
                unrealized_pl=26,
                unrealized_plpc=26,
            )
        ],
    )

    response = client.post("/kis/live-exit/preflight-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "hold"
    assert body["reason"] == "manual_review_required"
    assert body["would_submit_if_enabled"] is False
    assert body["cost_basis"] == pytest.approx(9841)
    assert body["current_value"] == pytest.approx(9867)
    assert body["unrealized_pl"] == pytest.approx(26)
    assert body["unrealized_pl_pct"] == pytest.approx(26 / 9841)
    assert body["unrealized_pl_pct"] * 100 == pytest.approx(0.2642, rel=0.01)
    assert "take_profit_triggered" not in body["risk_flags"]


def test_preflight_unrealized_pl_pct_uses_decimal_ratio(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(
                cost_basis=10000,
                market_value=10020,
                current_price=5010,
                unrealized_pl=20,
                unrealized_plpc=20,
            )
        ],
    )

    response = client.post("/kis/live-exit/preflight-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "hold"
    assert body["unrealized_pl_pct"] == pytest.approx(0.002)
    assert body["unrealized_pl_pct"] * 100 == pytest.approx(0.20)


def test_preflight_missing_cost_basis_does_not_trigger_take_profit(
    monkeypatch, client
):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(
                avg_entry_price=0,
                cost_basis=0,
                market_value=10200,
                current_price=5100,
                unrealized_pl=200,
                unrealized_plpc=2,
            )
        ],
    )

    response = client.post("/kis/live-exit/preflight-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "hold"
    assert body["reason"] == "manual_review_required"
    assert body["exit_trigger_source"] == "current_value_fallback"
    assert "cost_basis_unavailable_current_value_fallback" in body["risk_flags"]
    assert "take_profit_triggered" not in body["risk_flags"]


def test_exit_threshold_unit_normalization():
    assert normalize_exit_threshold_decimal(0.02, 0.03) == pytest.approx(0.02)
    assert normalize_exit_threshold_decimal(2, 0.03) == pytest.approx(0.02)
    assert normalize_exit_threshold_decimal("2", 0.03) == pytest.approx(0.02)
    assert normalize_exit_threshold_decimal(None, 0.03) == pytest.approx(0.03)


def test_preflight_returns_sell_when_risk_exit_triggered(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [_position(risk_flags=["risk_exit"])],
    )

    response = client.post("/kis/live-exit/preflight-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "sell"
    assert body["reason"] == "risk_exit"
    assert body["would_submit_if_enabled"] is True


def test_preflight_returns_hold_when_no_exit_condition_exists(client):
    response = client.post("/kis/live-exit/preflight-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "hold"
    assert body["reason"] == "manual_review_required"
    assert body["would_submit_if_enabled"] is False


def test_preflight_returns_no_held_position_message(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [],
    )

    response = client.post("/kis/live-exit/preflight-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "hold"
    assert body["message"] == "No held KIS position to evaluate."
    assert "no_held_position" in body["blocked_by"]


def test_preflight_flags_are_always_false_and_no_broker_ids(
    monkeypatch, client, db_session
):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(
                cost_basis=10000,
                market_value=9800,
                current_price=4900,
                unrealized_pl=-200,
                unrealized_plpc=-2,
            )
        ],
    )

    response = client.post("/kis/live-exit/preflight-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["live_order_submitted"] is False
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["kis_odno"] is None
    assert body["broker_order_id"] is None
    assert body["order_id"] is None
    assert db_session.query(OrderLog).count() == 0

    signal = db_session.query(SignalLog).one()
    run = db_session.query(TradeRunLog).one()
    assert signal.signal_status == "preflight"
    assert signal.related_order_id is None
    assert run.mode == "kis_live_exit_preflight"
    assert run.trigger_source == "manual_kis_live_exit_preflight"
    assert run.order_id is None
    run_payload = json.loads(run.response_payload)
    assert run_payload["real_order_submitted"] is False
    assert run_payload["broker_submit_called"] is False
    assert run_payload["manual_submit_called"] is False


def test_preflight_does_not_duplicate_open_sell_order(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(
                cost_basis=10000,
                market_value=9800,
                current_price=4900,
                unrealized_pl=-200,
                unrealized_plpc=-2,
            )
        ],
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_open_orders",
        lambda self: [{"symbol": "005930", "side": "sell", "status": "SUBMITTED"}],
    )

    response = client.post("/kis/live-exit/preflight-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "hold"
    assert body["reason"] == "stale_order_or_position_risk"
    assert "duplicate_open_sell_order" in body["blocked_by"]


def test_existing_manual_live_submit_path_remains_unchanged(client):
    response = client.post(
        "/kis/orders/submit-manual",
        json={
            "market": "KR",
            "symbol": "005930",
            "side": "buy",
            "qty": 1,
            "order_type": "market",
            "dry_run": False,
            "confirm_live": False,
        },
    )

    assert response.status_code in {400, 409}
    assert response.json()["real_order_submitted"] is False
