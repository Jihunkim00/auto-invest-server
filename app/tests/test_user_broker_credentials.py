from __future__ import annotations

from datetime import UTC, datetime

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import User, UserBrokerCredential
from app.main import app
from app.services.auth_service import create_session
from app.services.broker_credential_crypto_service import (
    BrokerCredentialCryptoService,
)
from app.services.user_broker_credential_service import (
    UserBrokerCredentialService,
)
from app.services.user_broker_validation_service import (
    UserBrokerValidationService,
)
from app.routes.user_brokers import get_user_broker_credential_service


class _FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


class _FakeBrokerHttp:
    def __init__(self, *, kis_auth=True, kis_account=True, alpaca=True):
        self.kis_auth = kis_auth
        self.kis_account = kis_account
        self.alpaca = alpaca
        self.posts = []
        self.gets = []

    def post(self, url, data, headers, timeout):
        self.posts.append(
            {
                "url": url,
                "data": data,
                "headers": headers,
                "timeout": timeout,
            }
        )
        if self.kis_auth:
            return _FakeResponse(
                {
                    "access_token": "ephemeral-user-token",
                    "access_token_token_expired": "2099-01-01 00:00:00",
                }
            )
        return _FakeResponse(
            {"msg1": "authentication failed with secret-user-value"},
            status_code=401,
        )

    def get(self, url, **kwargs):
        self.gets.append({"url": url, **kwargs})
        if "alpaca.markets" in url:
            if self.alpaca:
                return _FakeResponse({"status": "ACTIVE"})
            return _FakeResponse({"message": "bad secret-user-value"}, status_code=401)
        if self.kis_account:
            return _FakeResponse({"rt_cd": "0", "output1": [], "output2": [{}]})
        return _FakeResponse(
            {"rt_cd": "1", "msg1": "account failed secret-user-value"},
            status_code=400,
        )


def _settings(**overrides):
    values = {
        "alpaca_api_key": "admin-alpaca-key",
        "alpaca_secret_key": "admin-alpaca-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "broker_credential_master_key": Fernet.generate_key().decode("ascii"),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _client(db_session, user):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    token = create_session(db_session, user)
    client.cookies.set("auto_invest_session", token)
    return client


def _user(db_session, username):
    user = User(
        username=username,
        role="user",
        enabled=True,
        setup_completed=True,
        password_hash="test-only",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _service(settings, http=None):
    return UserBrokerCredentialService(
        crypto=BrokerCredentialCryptoService(settings),
        validator=UserBrokerValidationService(http_client=http or _FakeBrokerHttp()),
    )


def test_user_broker_credentials_are_encrypted_and_masked(db_session):
    user = _user(db_session, "user-a")
    service = _service(_settings())
    app.dependency_overrides[get_user_broker_credential_service] = lambda: service
    client = _client(db_session, user)

    try:
        response = client.put(
            "/users/me/brokers/kis",
            json={
                "environment": "paper",
                "app_key": "user-app-key-ABCD",
                "app_secret": "secret-user-value",
                "hts_id": "user-hts-id-ABCD",
                "account_no": "12345678",
                "account_product_code": "01",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is True
        assert body["app_key_masked"] == "****ABCD"
        assert body["hts_id_masked"] == "****ABCD"
        assert body["account_no_masked"] == "****5678"
        assert body["app_secret_configured"] is True
        assert "secret-user-value" not in response.text
        assert "user-app-key-ABCD" not in response.text
        assert "user-hts-id-ABCD" not in response.text
        assert "12345678" not in response.text

        row = db_session.query(UserBrokerCredential).one()
        assert row.user_id == user.id
        assert row.encryption_version == 1
        assert "secret-user-value" not in row.encrypted_payload
        assert "user-app-key-ABCD" not in row.encrypted_payload
        assert "user-hts-id-ABCD" not in row.encrypted_payload
        assert "12345678" not in row.encrypted_payload
        decrypted = service.crypto.decrypt(
            row.encrypted_payload,
            encryption_version=row.encryption_version,
        )
        assert decrypted["hts_id"] == "user-hts-id-ABCD"

        fetched = client.get("/users/me/brokers/kis")
        assert fetched.status_code == 200
        assert fetched.json()["app_key_masked"] == "****ABCD"
        assert fetched.json()["hts_id_masked"] == "****ABCD"
        assert "user-hts-id-ABCD" not in fetched.text
        assert "secret-user-value" not in fetched.text

        updated = client.put(
            "/users/me/brokers/kis",
            json={
                "environment": "live",
                "app_key": "new-app-key-WXYZ",
                "app_secret": "new-secret-value",
                "hts_id": "new-hts-id-IJKL",
                "account_no": "87654321",
                "account_product_code": "02",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["environment"] == "live"
        assert updated.json()["app_key_masked"] == "****WXYZ"
        assert updated.json()["hts_id_masked"] == "****IJKL"
        assert db_session.query(UserBrokerCredential).count() == 1

        deleted = client.delete("/users/me/brokers/kis")
        assert deleted.status_code == 200
        assert deleted.json() == {
            "ok": True,
            "provider": "kis",
            "deleted": True,
        }
        assert db_session.query(UserBrokerCredential).count() == 0
    finally:
        app.dependency_overrides.clear()


def test_user_broker_credentials_are_isolated_and_admin_is_rejected(db_session):
    user_a = _user(db_session, "user-a")
    user_b = _user(db_session, "user-b")
    admin = User(
        username="admin",
        role="admin",
        enabled=True,
        setup_completed=True,
        password_hash="test-only",
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)

    service = _service(_settings())
    app.dependency_overrides[get_user_broker_credential_service] = lambda: service
    client_a = _client(db_session, user_a)
    client_b = _client(db_session, user_b)
    client_admin = _client(db_session, admin)

    try:
        saved = client_a.put(
            "/users/me/brokers/alpaca",
            json={
                "environment": "paper",
                "api_key": "user-a-api-key",
                "secret_key": "user-a-secret",
            },
        )
        assert saved.status_code == 200

        assert client_b.get("/users/me/brokers/alpaca").json()["configured"] is False
        assert client_b.delete("/users/me/brokers/alpaca").status_code == 404
        assert client_a.get("/users/me/brokers/alpaca").json()["configured"] is True

        admin_response = client_admin.get("/users/me/brokers")
        assert admin_response.status_code == 403
        assert admin_response.json()["detail"] == "admin_uses_env_broker_credentials"
        assert db_session.query(UserBrokerCredential).count() == 1
    finally:
        app.dependency_overrides.clear()


def _override_db(db_session):
    def override_get_db():
        yield db_session

    return override_get_db

def test_unauthenticated_user_is_rejected(db_session):
    service = _service(_settings())
    app.dependency_overrides[get_user_broker_credential_service] = lambda: service
    app.dependency_overrides[get_db] = _override_db(db_session)
    client = TestClient(app)

    try:
        response = client.get("/users/me/brokers")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_missing_master_key_only_blocks_user_credential_surface(db_session):
    user = _user(db_session, "user-a")
    service = _service(_settings(broker_credential_master_key=None))
    app.dependency_overrides[get_user_broker_credential_service] = lambda: service
    client = _client(db_session, user)

    try:
        response = client.put(
            "/users/me/brokers/alpaca",
            json={
                "environment": "paper",
                "api_key": "key",
                "secret_key": "secret",
            },
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "broker_credential_encryption_not_configured"
    finally:
        app.dependency_overrides.clear()


def test_kis_validation_is_read_only_and_persists_safe_result(db_session):
    user = _user(db_session, "user-a")
    http = _FakeBrokerHttp()
    service = _service(_settings(), http)
    app.dependency_overrides[get_user_broker_credential_service] = lambda: service
    client = _client(db_session, user)

    try:
        saved = client.put(
            "/users/me/brokers/kis",
            json={
                "environment": "paper",
                "app_key": "user-app-key",
                "app_secret": "secret-user-value",
                "hts_id": "user-hts-id-ABCD",
                "account_no": "12345678",
                "account_product_code": "01",
            },
        )
        assert saved.status_code == 200

        validated = client.post("/users/me/brokers/kis/validate")
        assert validated.status_code == 200
        assert validated.json()["valid"] is True
        assert validated.json()["status"] == "success"
        assert len(http.posts) == 1
        assert len(http.gets) == 1
        assert all("submit" not in call["url"] for call in http.posts + http.gets)
        assert db_session.query(UserBrokerCredential).one().last_validation_status == "success"
        assert "ephemeral-user-token" not in validated.text
    finally:
        app.dependency_overrides.clear()


def test_kis_validation_accepts_legacy_payload_without_hts_id(db_session):
    user = _user(db_session, "user-legacy")
    settings = _settings()
    crypto = BrokerCredentialCryptoService(settings)
    db_session.add(
        UserBrokerCredential(
            user_id=user.id,
            provider="kis",
            environment="paper",
            encrypted_payload=crypto.encrypt(
                {
                    "environment": "paper",
                    "app_key": "legacy-app-key",
                    "app_secret": "legacy-app-secret",
                    "account_no": "12345678",
                    "account_product_code": "01",
                }
            ),
            encryption_version=1,
        )
    )
    db_session.commit()

    http = _FakeBrokerHttp()
    service = _service(settings, http)
    app.dependency_overrides[get_user_broker_credential_service] = lambda: service
    client = _client(db_session, user)

    try:
        fetched = client.get("/users/me/brokers/kis")
        assert fetched.status_code == 200
        assert fetched.json()["hts_id_masked"] is None
        validated = client.post("/users/me/brokers/kis/validate")
        assert validated.status_code == 200
        assert validated.json()["valid"] is True
        assert validated.json()["status"] == "success"
        assert len(http.posts) == 1
        assert len(http.gets) == 1
    finally:
        app.dependency_overrides.clear()

def test_validation_failure_is_safe_and_alpaca_uses_account_read_only_call(db_session):
    user = _user(db_session, "user-a")
    http = _FakeBrokerHttp(kis_auth=False, alpaca=False)
    service = _service(_settings(), http)
    app.dependency_overrides[get_user_broker_credential_service] = lambda: service
    client = _client(db_session, user)

    try:
        saved = client.put(
            "/users/me/brokers/alpaca",
            json={
                "environment": "live",
                "api_key": "user-api-key",
                "secret_key": "secret-user-value",
            },
        )
        assert saved.status_code == 200
        validated = client.post("/users/me/brokers/alpaca/validate")
        assert validated.status_code == 200
        assert validated.json()["valid"] is False
        assert validated.json()["message"] == "authentication_failed"
        assert len(http.gets) == 1
        assert http.gets[0]["url"] == "https://api.alpaca.markets/v2/account"
        assert "secret-user-value" not in validated.text
        assert db_session.query(UserBrokerCredential).one().last_validation_status == "failed"
    finally:
        app.dependency_overrides.clear()

