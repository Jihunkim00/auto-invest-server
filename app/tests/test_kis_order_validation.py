import pytest
from fastapi.testclient import TestClient

from app.brokers.base import KisApiError
from app.config import Settings
from app.db.database import get_db
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


def _patch_settings(monkeypatch, **overrides):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings(**overrides))


def _patch_price(monkeypatch, current_price=72000.0):
    def fake_price(self, symbol):
        assert symbol == "005930"
        return {"symbol": symbol, "current_price": current_price}

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_stock_price",
        fake_price,
    )


def _patch_balance(monkeypatch, cash=1_000_000.0):
    def fake_balance(self):
        return {"currency": "KRW", "cash": cash}

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        fake_balance,
    )


def _patch_positions(monkeypatch, positions):
    def fake_positions(self):
        return positions

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        fake_positions,
    )


def _fail_if_submit_order_is_called(monkeypatch):
    def fail_submit(*args, **kwargs):
        pytest.fail("KIS dry-run validation must not submit orders")

    monkeypatch.setattr("app.brokers.kis_client.KisClient.submit_order", fail_submit)


def _buy_payload(**overrides):
    payload = {
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


def test_validate_buy_market_order_success_with_sufficient_cash(monkeypatch, client):
    _patch_settings(monkeypatch, kis_enabled=False)
    _patch_price(monkeypatch, current_price=72000.0)
    _patch_balance(monkeypatch, cash=1_000_000.0)
    _fail_if_submit_order_is_called(monkeypatch)

    response = client.post("/kis/orders/validate", json=_buy_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "kis"
    assert body["environment"] == "prod"
    assert body["dry_run"] is True
    assert body["validated_for_submission"] is True
    assert body["can_submit_later"] is True
    assert body["current_price"] == 72000.0
    assert body["estimated_amount"] == 72000.0
    assert body["available_cash"] == 1000000.0
    assert body["block_reasons"] == []
    assert body["order_preview"]["kis_tr_id_preview"] == "TTTC0802U"
    assert body["order_preview"]["payload_preview"]["PDNO"] == "005930"
    assert body["order_preview"]["payload_preview"]["ORD_DVSN"] == "01"
    assert body["order_preview"]["payload_preview"]["ORD_QTY"] == "1"
    assert body["order_preview"]["payload_preview"]["ORD_UNPR"] == "0"


def test_validate_buy_blocked_with_insufficient_cash(monkeypatch, client):
    _patch_settings(monkeypatch)
    _patch_price(monkeypatch, current_price=72000.0)
    _patch_balance(monkeypatch, cash=1000.0)

    response = client.post("/kis/orders/validate", json=_buy_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["validated_for_submission"] is False
    assert body["can_submit_later"] is False
    assert body["block_reasons"] == ["insufficient_cash"]


def test_validate_buy_warns_and_blocks_when_cash_is_unknown(monkeypatch, client):
    _patch_settings(monkeypatch)
    _patch_price(monkeypatch, current_price=72000.0)

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        lambda self: {"currency": "KRW"},
    )

    response = client.post("/kis/orders/validate", json=_buy_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["validated_for_submission"] is False
    assert body["available_cash"] is None
    assert body["warnings"] == ["available_cash_unavailable"]
    assert body["block_reasons"] == ["available_cash_unavailable"]


def test_validate_sell_success_with_enough_held_qty(monkeypatch, client):
    _patch_settings(monkeypatch)
    _patch_price(monkeypatch, current_price=72000.0)
    _patch_positions(
        monkeypatch,
        [{"symbol": "005930", "qty": 3.0, "current_price": 72000.0}],
    )

    response = client.post("/kis/orders/validate", json=_sell_payload(qty=1))

    assert response.status_code == 200
    body = response.json()
    assert body["validated_for_submission"] is True
    assert body["can_submit_later"] is True
    assert body["held_qty"] == 3.0
    assert body["estimated_amount"] == 72000.0
    assert body["order_preview"]["kis_tr_id_preview"] == "TTTC0801U"


def test_validate_sell_blocked_when_no_position_exists(monkeypatch, client):
    _patch_settings(monkeypatch)
    _patch_price(monkeypatch, current_price=72000.0)
    _patch_positions(monkeypatch, [])

    response = client.post("/kis/orders/validate", json=_sell_payload(qty=1))

    assert response.status_code == 200
    body = response.json()
    assert body["validated_for_submission"] is False
    assert body["held_qty"] == 0.0
    assert body["block_reasons"] == ["no_position_for_symbol"]


def test_validate_sell_blocked_when_held_qty_is_too_low(monkeypatch, client):
    _patch_settings(monkeypatch)
    _patch_price(monkeypatch, current_price=72000.0)
    _patch_positions(monkeypatch, [{"symbol": "005930", "qty": 1.0}])

    response = client.post("/kis/orders/validate", json=_sell_payload(qty=2))

    assert response.status_code == 200
    body = response.json()
    assert body["validated_for_submission"] is False
    assert body["held_qty"] == 1.0
    assert body["block_reasons"] == ["insufficient_holdings"]


def test_validate_order_rejects_invalid_symbol(monkeypatch, client):
    _patch_settings(monkeypatch)

    response = client.post(
        "/kis/orders/validate",
        json=_buy_payload(symbol="AAPL"),
    )

    assert response.status_code == 422


def test_validate_order_rejects_non_positive_qty(monkeypatch, client):
    _patch_settings(monkeypatch)

    response = client.post("/kis/orders/validate", json=_buy_payload(qty=0))

    assert response.status_code == 422


def test_validate_order_rejects_dry_run_false(monkeypatch, client):
    _patch_settings(monkeypatch)

    response = client.post(
        "/kis/orders/validate",
        json=_buy_payload(dry_run=False),
    )

    assert response.status_code == 400
    assert "dry_run must be true" in response.json()["detail"]


def test_validate_order_rejects_unsupported_order_type(monkeypatch, client):
    _patch_settings(monkeypatch)

    response = client.post(
        "/kis/orders/validate",
        json=_buy_payload(order_type="limit", price=71000),
    )

    assert response.status_code == 400
    assert "Only market" in response.json()["detail"]


def test_order_payload_preview_masks_account_number(monkeypatch, client):
    _patch_settings(monkeypatch)
    _patch_price(monkeypatch, current_price=72000.0)
    _patch_balance(monkeypatch, cash=1_000_000.0)

    response = client.post("/kis/orders/validate", json=_buy_payload())

    assert response.status_code == 200
    body = response.json()
    preview = body["order_preview"]
    assert preview["account_no_masked"] == "12****78"
    assert preview["payload_preview"]["CANO"] == "12****78"
    assert "12345678" not in response.text


def test_validate_response_does_not_expose_secrets(monkeypatch, client):
    _patch_settings(monkeypatch)
    _patch_price(monkeypatch, current_price=72000.0)
    _patch_balance(monkeypatch, cash=1_000_000.0)

    response = client.post("/kis/orders/validate", json=_buy_payload())

    assert response.status_code == 200
    assert "real-app-key" not in response.text
    assert "real-app-secret" not in response.text
    assert "secret-access-token" not in response.text
    assert "secret-approval-key" not in response.text
    assert "access_token" not in response.text
    assert "approval_key" not in response.text


def test_validate_kis_api_error_returns_safe_502(monkeypatch, client):
    _patch_settings(monkeypatch)

    def fail_price(self, symbol):
        raise KisApiError("KIS read-only API returned error code EGW00001.")

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_stock_price",
        fail_price,
    )

    response = client.post("/kis/orders/validate", json=_buy_payload())

    assert response.status_code == 502
    assert response.json()["detail"] == "KIS read-only API returned error code EGW00001."
    assert "secret-access-token" not in response.text


def test_validate_endpoint_does_not_call_submit_order(monkeypatch, client):
    _patch_settings(monkeypatch)
    _patch_price(monkeypatch, current_price=72000.0)
    _patch_balance(monkeypatch, cash=1_000_000.0)
    _fail_if_submit_order_is_called(monkeypatch)

    response = client.post("/kis/orders/dry-run", json=_buy_payload())

    assert response.status_code == 200
    assert response.json()["validated_for_submission"] is True


def test_validate_missing_credentials_returns_safe_400(monkeypatch, client):
    _patch_settings(monkeypatch, kis_app_key=None, kis_app_secret=None)

    response = client.post("/kis/orders/validate", json=_buy_payload())

    assert response.status_code == 400
    assert "KIS configuration is incomplete" in response.json()["detail"]
