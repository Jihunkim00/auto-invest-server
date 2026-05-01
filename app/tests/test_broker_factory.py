import pytest
from fastapi.testclient import TestClient

from app.brokers.alpaca_broker import AlpacaBroker
from app.brokers.base import BrokerNotEnabledError
from app.brokers.factory import get_broker
from app.brokers.kis_broker import KisBroker
from app.brokers.kis_client import KisClient
from app.config import Settings
from app.main import app


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_default_broker_provider_is_alpaca():
    settings = _settings()

    assert settings.broker_provider == "alpaca"
    assert settings.dry_run is True


def test_kis_is_disabled_by_default():
    settings = _settings()

    assert settings.kis_enabled is False
    assert settings.kis_real_order_enabled is False
    assert settings.kis_env == "paper"


def test_broker_factory_returns_alpaca_by_default():
    broker = get_broker(_settings())

    assert isinstance(broker, AlpacaBroker)


def test_broker_factory_does_not_return_kis_when_disabled():
    settings = _settings(broker_provider="kis", kis_enabled=False)

    with pytest.raises(BrokerNotEnabledError):
        get_broker(settings)


def test_kis_missing_config_does_not_break_broker_status(monkeypatch):
    monkeypatch.setattr("app.routes.brokers.get_settings", lambda: _settings())

    with TestClient(app) as client:
        response = client.get("/brokers/status")

    assert response.status_code == 200
    body = response.json()
    assert body["active_provider"] == "alpaca"
    assert body["kis_enabled"] is False
    assert body["kis_configured"] is False
    assert body["kis_env"] == "paper"


def test_brokers_status_masks_sensitive_values(monkeypatch):
    settings = _settings(
        broker_provider="alpaca",
        kis_enabled=True,
        kis_app_key="real-app-key",
        kis_app_secret="real-app-secret",
        kis_account_no="12345678",
        kis_account_product_code="01",
        kis_hts_id="real-hts-id",
        kis_base_url="https://openapivts.koreainvestment.com:29443",
        kis_ws_url="wss://openapivts.koreainvestment.com:29443",
        kis_access_token="real-access-token",
        kis_approval_key="real-approval-key",
    )
    monkeypatch.setattr("app.routes.brokers.get_settings", lambda: settings)

    with TestClient(app) as client:
        response = client.get("/brokers/status")

    assert response.status_code == 200
    body = response.json()
    assert body["kis_configured"] is True
    assert body["kis_account_no_masked"] == "12****78"
    response_text = response.text
    assert "12345678" not in response_text
    assert "real-app-key" not in response_text
    assert "real-app-secret" not in response_text
    assert "real-access-token" not in response_text
    assert "real-approval-key" not in response_text


def test_kis_submit_market_buy_is_disabled():
    broker = KisBroker(KisClient(_settings()))

    with pytest.raises(BrokerNotEnabledError):
        broker.submit_market_buy("005930", notional=100000)


def test_kis_submit_market_sell_is_disabled():
    broker = KisBroker(KisClient(_settings()))

    with pytest.raises(BrokerNotEnabledError):
        broker.submit_market_sell("005930", qty=1)


def test_kis_client_domestic_cash_order_is_disabled_by_default():
    client = KisClient(_settings(kis_enabled=True))

    with pytest.raises(BrokerNotEnabledError):
        client.submit_domestic_cash_order(
            symbol="005930",
            side="buy",
            qty=1,
            order_type="market",
        )
