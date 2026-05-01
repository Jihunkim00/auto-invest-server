import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.main import app


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_kis_auth_status_returns_200_and_hides_secrets(monkeypatch, client):
    settings = _settings(
        kis_enabled=True,
        kis_app_key="real-app-key",
        kis_app_secret="real-app-secret",
        kis_account_no="12345678",
        kis_account_product_code="01",
        kis_base_url="https://openapivts.koreainvestment.com:29443",
        kis_access_token="env-access-token",
        kis_approval_key="env-approval-key",
    )
    monkeypatch.setattr("app.routes.brokers.get_settings", lambda: settings)

    response = client.get("/brokers/kis/auth/status")

    assert response.status_code == 200
    body = response.json()
    assert body["kis_enabled"] is True
    assert body["kis_configured"] is True
    assert body["kis_env"] == "paper"
    assert "real-app-key" not in response.text
    assert "real-app-secret" not in response.text
    assert "env-access-token" not in response.text
    assert "env-approval-key" not in response.text


def test_kis_access_token_missing_credentials_returns_safe_400(monkeypatch, client):
    monkeypatch.setattr("app.routes.brokers.get_settings", lambda: _settings())

    response = client.post("/brokers/kis/auth/access-token")

    assert response.status_code == 400
    assert "KIS configuration is incomplete" in response.json()["detail"]


def test_kis_approval_key_missing_credentials_returns_safe_400(monkeypatch, client):
    monkeypatch.setattr("app.routes.brokers.get_settings", lambda: _settings())

    response = client.post("/brokers/kis/auth/approval-key")

    assert response.status_code == 400
    assert "KIS configuration is incomplete" in response.json()["detail"]


def test_kis_access_token_endpoint_issues_without_exposing_token(
    monkeypatch, client
):
    settings = _settings(
        kis_app_key="real-app-key",
        kis_app_secret="real-app-secret",
        kis_account_no="12345678",
        kis_account_product_code="01",
        kis_base_url="https://openapivts.koreainvestment.com:29443",
    )
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append({"url": url, "data": json.loads(data)})
        return _FakeResponse(
            {
                "access_token": "secret-issued-access-token",
                "access_token_token_expired": "2099-01-01 00:00:00",
            }
        )

    monkeypatch.setattr("app.routes.brokers.get_settings", lambda: settings)
    monkeypatch.setattr("app.brokers.kis_auth_manager.requests.post", fake_post)

    response = client.post("/brokers/kis/auth/access-token")

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "access_token"
    assert body["issued"] is True
    assert body["source"] == "issued"
    assert body["has_token"] is True
    assert body["environment"] == "paper"
    assert "secret-issued-access-token" not in response.text
    assert calls[0]["url"].endswith("/oauth2/tokenP")


def test_kis_approval_key_endpoint_issues_without_exposing_key(
    monkeypatch, client
):
    settings = _settings(
        kis_app_key="real-app-key",
        kis_app_secret="real-app-secret",
        kis_account_no="12345678",
        kis_account_product_code="01",
        kis_base_url="https://openapivts.koreainvestment.com:29443",
    )

    def fake_post(url, data, headers, timeout):
        return _FakeResponse({"approval_key": "secret-issued-approval-key"})

    monkeypatch.setattr("app.routes.brokers.get_settings", lambda: settings)
    monkeypatch.setattr("app.brokers.kis_auth_manager.requests.post", fake_post)

    response = client.post("/brokers/kis/auth/approval-key")

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "approval_key"
    assert body["issued"] is True
    assert body["source"] == "issued"
    assert body["has_token"] is True
    assert body["expires_at"] is None
    assert "secret-issued-approval-key" not in response.text


def test_brokers_status_includes_token_presence_and_masks_account(
    monkeypatch, client
):
    settings = _settings(
        kis_enabled=True,
        kis_app_key="real-app-key",
        kis_app_secret="real-app-secret",
        kis_account_no="12345678",
        kis_account_product_code="01",
        kis_base_url="https://openapivts.koreainvestment.com:29443",
    )

    def fake_post(url, data, headers, timeout):
        return _FakeResponse(
            {
                "access_token": "status-secret-access-token",
                "access_token_token_expired": "2099-01-01 00:00:00",
            }
        )

    monkeypatch.setattr("app.routes.brokers.get_settings", lambda: settings)
    monkeypatch.setattr("app.brokers.kis_auth_manager.requests.post", fake_post)

    issue_response = client.post("/brokers/kis/auth/access-token")
    assert issue_response.status_code == 200
    status_response = client.get("/brokers/status")

    assert status_response.status_code == 200
    body = status_response.json()
    assert body["kis_account_no_masked"] == "12****78"
    assert body["kis_has_access_token"] is True
    assert body["kis_has_approval_key"] is False
    assert "12345678" not in status_response.text
    assert "status-secret-access-token" not in status_response.text
    assert "real-app-key" not in status_response.text
    assert "real-app-secret" not in status_response.text
