from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import BrokerAuthToken
from app.main import app


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "kis_enabled": False,
        "kis_env": "prod",
        "kis_app_key": "real-app-key",
        "kis_app_secret": "real-app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_base_url": "https://openapi.koreainvestment.com:9443",
        "kis_access_token": "secret-access-token",
        "kis_approval_key": "secret-approval-key",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


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
def _safe_kis(monkeypatch):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_stock_price",
        lambda self, symbol: {"symbol": symbol, "current_price": 72000.0},
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        lambda self: {"currency": "KRW", "cash": 1_000_000.0},
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [{"symbol": "005930", "qty": 3.0}],
    )
    monkeypatch.setattr(
        "app.services.kis_order_validation_service.MarketSessionService.get_session_status",
        lambda self, market, now=None: {
            "market": "KR",
            "timezone": "Asia/Seoul",
            "is_market_open": True,
            "is_entry_allowed_now": True,
            "is_near_close": False,
            "closure_reason": None,
            "closure_name": None,
            "regular_open": "09:00",
            "regular_close": "15:30",
            "effective_close": "15:30",
            "no_new_entry_after": "15:00",
        },
    )

    def fail_submit(*args, **kwargs):
        pytest.fail("KIS dry-run validation must not submit orders")

    monkeypatch.setattr("app.brokers.kis_client.KisClient.submit_order", fail_submit)


def _buy_payload(**overrides):
    payload = {
        "market": "KR",
        "symbol": "005930",
        "side": "buy",
        "qty": 1,
        "order_type": "market",
        "dry_run": True,
        "reason": "test dry-run validation",
    }
    payload.update(overrides)
    return payload


def _sell_payload(**overrides):
    payload = _buy_payload(side="sell")
    payload.update(overrides)
    return payload


def test_validate_buy_market_order_success_with_sufficient_cash(client):
    response = client.post("/kis/orders/validate", json=_buy_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "kis"
    assert body["market"] == "KR"
    assert body["environment"] == "prod"
    assert body["dry_run"] is True
    assert body["validated_for_submission"] is True
    assert body["can_submit_later"] is True
    assert body["current_price"] == 72000.0
    assert body["estimated_amount"] == 72000.0
    assert body["available_cash"] == 1000000.0
    assert body["warnings"] == []
    assert body["block_reasons"] == []
    assert body["market_session"]["timezone"] == "Asia/Seoul"
    assert body["order_preview"]["kis_tr_id_preview"] == "TTTC0802U"
    assert body["order_preview"]["payload_preview"]["ORD_DVSN"] == "01"


def test_validate_buy_blocked_with_insufficient_cash(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        lambda self: {"currency": "KRW", "cash": 1000.0},
    )

    response = client.post("/kis/orders/validate", json=_buy_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["validated_for_submission"] is False
    assert body["can_submit_later"] is False
    assert body["block_reasons"] == ["insufficient_cash"]


def test_validate_buy_blocked_with_insufficient_cash_when_manual_caps_disabled(
    monkeypatch, client,
):
    monkeypatch.setattr(
        "app.routes.kis.get_settings",
        lambda: _settings(kis_max_manual_order_qty=0, kis_max_manual_order_amount_krw=0),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        lambda self: {"currency": "KRW", "cash": 1000.0},
    )

    response = client.post("/kis/orders/validate", json=_buy_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["validated_for_submission"] is False
    assert body["can_submit_later"] is False
    assert body["block_reasons"] == ["insufficient_cash"]


def test_validate_sell_success_with_enough_holdings(client):
    response = client.post("/kis/orders/validate", json=_sell_payload(qty=2))

    assert response.status_code == 200
    body = response.json()
    assert body["validated_for_submission"] is True
    assert body["held_qty"] == 3.0
    assert body["order_preview"]["kis_tr_id_preview"] == "TTTC0801U"


def test_validate_sell_blocked_when_no_position(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [],
    )

    response = client.post("/kis/orders/validate", json=_sell_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["validated_for_submission"] is False
    assert body["held_qty"] == 0.0
    assert body["block_reasons"] == ["no_position_for_symbol"]


def test_validate_sell_blocked_when_insufficient_holdings(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [{"symbol": "005930", "qty": 1.0}],
    )

    response = client.post("/kis/orders/validate", json=_sell_payload(qty=2))

    assert response.status_code == 200
    body = response.json()
    assert body["validated_for_submission"] is False
    assert body["held_qty"] == 1.0
    assert body["block_reasons"] == ["insufficient_holdings"]


def test_invalid_kr_symbol_is_rejected(client):
    response = client.post("/kis/orders/validate", json=_buy_payload(symbol="12345"))

    assert response.status_code == 400
    assert "6 numeric digits" in response.json()["detail"]


def test_aapl_is_rejected_for_kr(client):
    response = client.post("/kis/orders/validate", json=_buy_payload(symbol="AAPL"))

    assert response.status_code == 400
    assert "6 numeric digits" in response.json()["detail"]


def test_dry_run_false_is_rejected(client):
    response = client.post("/kis/orders/validate", json=_buy_payload(dry_run=False))

    assert response.status_code == 400
    assert "dry_run must be true" in response.json()["detail"]


def test_unsupported_order_type_is_rejected(client):
    response = client.post(
        "/kis/orders/validate",
        json=_buy_payload(order_type="limit"),
    )

    assert response.status_code == 400
    assert "Only market" in response.json()["detail"]


def test_response_masks_account_number_and_hides_secrets(client):
    response = client.post("/kis/orders/validate", json=_buy_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["order_preview"]["account_no_masked"] == "12****78"
    assert body["order_preview"]["payload_preview"]["CANO"] == "12****78"
    assert "12345678" not in response.text
    assert "real-app-secret" not in response.text
    assert "secret-access-token" not in response.text
    assert "secret-approval-key" not in response.text


def test_kis_enabled_false_still_allows_dry_run_validation(client):
    response = client.post("/kis/orders/dry-run", json=_buy_payload())

    assert response.status_code == 200
    assert response.json()["dry_run"] is True


def test_after_kr_no_new_entry_time_blocks_buy(monkeypatch, client):
    monkeypatch.setattr(
        "app.services.kis_order_validation_service.MarketSessionService.get_session_status",
        lambda self, market, now=None: {
            "market": "KR",
            "timezone": "Asia/Seoul",
            "is_market_open": True,
            "is_entry_allowed_now": False,
            "is_near_close": True,
            "closure_reason": None,
            "closure_name": None,
            "regular_open": "09:00",
            "regular_close": "15:30",
            "effective_close": "15:30",
            "no_new_entry_after": "15:00",
        },
    )

    response = client.post("/kis/orders/validate", json=_buy_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["validated_for_submission"] is False
    assert "after_no_new_entry_time" in body["warnings"]
    assert "after_no_new_entry_time" in body["block_reasons"]
    assert "near_close" in body["warnings"]


def test_holiday_closure_reason_is_returned(monkeypatch, client):
    monkeypatch.setattr(
        "app.services.kis_order_validation_service.MarketSessionService.get_session_status",
        lambda self, market, now=None: {
            "market": "KR",
            "timezone": "Asia/Seoul",
            "is_market_open": False,
            "is_entry_allowed_now": False,
            "is_near_close": False,
            "closure_reason": "holiday_labor_day",
            "closure_name": "Labor Day",
            "regular_open": "09:00",
            "regular_close": "15:30",
            "effective_close": "15:30",
            "no_new_entry_after": "15:00",
        },
    )

    response = client.post("/kis/orders/validate", json=_buy_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["validated_for_submission"] is False
    assert body["market_session"]["closure_reason"] == "holiday_labor_day"
    assert body["market_session"]["closure_name"] == "Labor Day"
    assert "market_closed" in body["block_reasons"]
    assert "market_closed_holiday_labor_day" in body["warnings"]


def test_dry_run_validation_refreshes_expired_token_lazily(
    monkeypatch,
    client,
    db_session,
):
    db_session.add(
        BrokerAuthToken(
            provider="kis",
            token_type="access_token",
            token_value="expired-access-token",
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
            issued_at=datetime.now(UTC) - timedelta(hours=24),
            environment="prod",
        )
    )
    db_session.commit()
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append(url)
        return _FakeResponse(
            {
                "access_token": "refreshed-access-token",
                "expires_in": 3600,
            }
        )

    def fake_price(self, symbol):
        token = self.get_access_token()
        assert token.token == "refreshed-access-token"
        return {"symbol": symbol, "current_price": 72000.0}

    monkeypatch.setattr("app.brokers.kis_auth_manager.requests.post", fake_post)
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_stock_price",
        fake_price,
    )

    response = client.post("/kis/orders/validate", json=_buy_payload())

    assert response.status_code == 200
    assert response.json()["validated_for_submission"] is True
    assert len(calls) == 1


class _FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body
