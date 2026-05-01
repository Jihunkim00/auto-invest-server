from datetime import UTC, datetime, timedelta
import json

import pytest

from app.brokers.base import KisConfigurationError
from app.brokers.kis_auth_manager import KisAuthManager
from app.config import Settings
from app.db.models import BrokerAuthToken


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "kis_app_key": "kis-app-key",
        "kis_app_secret": "kis-app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_base_url": "https://openapivts.koreainvestment.com:29443",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


def _add_token(
    db_session,
    *,
    token_type,
    token_value,
    expires_at,
    environment="paper",
):
    issued_at = datetime.now(UTC) - timedelta(minutes=5)
    row = BrokerAuthToken(
        provider="kis",
        token_type=token_type,
        token_value=token_value,
        expires_at=expires_at,
        issued_at=issued_at,
        environment=environment,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_kis_auth_manager_is_configured_false_when_credentials_missing(db_session):
    manager = KisAuthManager(_settings(kis_app_key=None, kis_app_secret=None), db_session)

    assert manager.is_configured() is False


def test_kis_auth_manager_require_configured_raises_when_missing(db_session):
    manager = KisAuthManager(_settings(kis_app_key=None), db_session)

    with pytest.raises(KisConfigurationError):
        manager.require_configured()


def test_unexpired_access_token_is_reused(db_session, monkeypatch):
    _add_token(
        db_session,
        token_type="access_token",
        token_value="cached-access-token",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    monkeypatch.setattr(
        "app.brokers.kis_auth_manager.requests.post",
        lambda *args, **kwargs: pytest.fail("cache hit should not call KIS"),
    )
    manager = KisAuthManager(_settings(), db_session)

    result = manager.get_valid_access_token()

    assert result.source == "cache"
    assert result.token == "cached-access-token"


def test_force_refresh_bypasses_cached_access_token(db_session, monkeypatch):
    _add_token(
        db_session,
        token_type="access_token",
        token_value="cached-access-token",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append({"url": url, "data": json.loads(data), "headers": headers})
        return _FakeResponse(
            {
                "access_token": "fresh-access-token",
                "access_token_token_expired": "2099-01-01 00:00:00",
            }
        )

    monkeypatch.setattr("app.brokers.kis_auth_manager.requests.post", fake_post)
    manager = KisAuthManager(_settings(), db_session)

    result = manager.get_valid_access_token(force_refresh=True)

    assert result.source == "issued"
    assert result.token == "fresh-access-token"
    assert calls[0]["url"].endswith("/oauth2/tokenP")
    assert calls[0]["data"]["grant_type"] == "client_credentials"
    assert calls[0]["data"]["appkey"] == "kis-app-key"
    assert calls[0]["data"]["appsecret"] == "kis-app-secret"


def test_expired_access_token_triggers_refresh(db_session, monkeypatch):
    _add_token(
        db_session,
        token_type="access_token",
        token_value="expired-access-token",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    def fake_post(url, data, headers, timeout):
        return _FakeResponse(
            {
                "access_token": "refreshed-access-token",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr("app.brokers.kis_auth_manager.requests.post", fake_post)
    manager = KisAuthManager(_settings(), db_session)

    result = manager.get_valid_access_token()

    assert result.source == "issued"
    assert result.token == "refreshed-access-token"


def test_access_token_expiring_within_refresh_buffer_is_refreshed(
    db_session,
    monkeypatch,
):
    _add_token(
        db_session,
        token_type="access_token",
        token_value="nearly-expired-access-token",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append(url)
        return _FakeResponse(
            {
                "access_token": "refreshed-buffer-token",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr("app.brokers.kis_auth_manager.requests.post", fake_post)
    manager = KisAuthManager(_settings(), db_session)

    result = manager.get_valid_access_token()

    assert result.source == "issued"
    assert result.token == "refreshed-buffer-token"
    assert calls


def test_access_token_missing_expiry_defaults_to_23_hours(db_session, monkeypatch):
    def fake_post(url, data, headers, timeout):
        return _FakeResponse({"access_token": "default-expiry-token"})

    monkeypatch.setattr("app.brokers.kis_auth_manager.requests.post", fake_post)
    manager = KisAuthManager(_settings(), db_session)

    before = datetime.now(UTC)
    result = manager.get_valid_access_token(force_refresh=True)
    after = datetime.now(UTC)

    assert result.expires_at is not None
    assert before + timedelta(hours=23) <= result.expires_at <= after + timedelta(
        hours=23,
        seconds=1,
    )


def test_token_status_reports_seconds_and_refresh_need(db_session):
    _add_token(
        db_session,
        token_type="access_token",
        token_value="status-access-token",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    manager = KisAuthManager(_settings(), db_session)

    status = manager.get_auth_status()

    assert status["has_access_token"] is True
    assert status["access_token_seconds_until_expiry"] > 3500
    assert status["access_token_needs_refresh"] is False
    assert "status-access-token" not in str(status)


def test_token_needs_refresh_true_for_expired_access_token(db_session):
    _add_token(
        db_session,
        token_type="access_token",
        token_value="expired-status-access-token",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    manager = KisAuthManager(_settings(), db_session)

    assert manager.token_needs_refresh("access_token") is True
    assert manager.seconds_until_expiry("access_token") == 0


def test_approval_key_cache_is_reused(db_session, monkeypatch):
    _add_token(
        db_session,
        token_type="approval_key",
        token_value="cached-approval-key",
        expires_at=None,
    )
    monkeypatch.setattr(
        "app.brokers.kis_auth_manager.requests.post",
        lambda *args, **kwargs: pytest.fail("cache hit should not call KIS"),
    )
    manager = KisAuthManager(_settings(), db_session)

    result = manager.get_valid_approval_key()

    assert result.source == "cache"
    assert result.token == "cached-approval-key"
    assert result.expires_at is None


def test_approval_key_force_refresh_uses_official_secretkey_payload(
    db_session, monkeypatch
):
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append({"url": url, "data": json.loads(data), "headers": headers})
        return _FakeResponse({"approval_key": "fresh-approval-key"})

    monkeypatch.setattr("app.brokers.kis_auth_manager.requests.post", fake_post)
    manager = KisAuthManager(_settings(), db_session)

    result = manager.get_valid_approval_key(force_refresh=True)

    assert result.source == "issued"
    assert result.token == "fresh-approval-key"
    assert calls[0]["url"].endswith("/oauth2/Approval")
    assert calls[0]["data"]["appkey"] == "kis-app-key"
    assert calls[0]["data"]["secretkey"] == "kis-app-secret"
    assert "appsecret" not in calls[0]["data"]


def test_token_values_are_not_exposed_in_status_or_repr(db_session, monkeypatch):
    def fake_post(url, data, headers, timeout):
        return _FakeResponse(
            {
                "access_token": "secret-fake-access-token",
                "access_token_token_expired": "2099-01-01 00:00:00",
            }
        )

    monkeypatch.setattr("app.brokers.kis_auth_manager.requests.post", fake_post)
    manager = KisAuthManager(_settings(), db_session)

    result = manager.get_valid_access_token(force_refresh=True)
    status = manager.get_auth_status()

    assert "secret-fake-access-token" not in repr(result)
    assert "secret-fake-access-token" not in str(status)
    assert status["has_access_token"] is True
