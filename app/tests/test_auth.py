from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.database import get_db
from app.db.models import AuthSession
from app.main import app


def _client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    return client


def test_admin_bootstrap_is_created_by_init_db(db_session):
    from app.services.auth_service import ensure_admin_user

    user = ensure_admin_user(db_session)

    assert user.username == "admin"
    assert user.role == "admin"
    assert user.enabled is True
    assert user.setup_completed is False
    assert user.password_hash is None


def test_setup_rejects_wrong_code_and_reuse(db_session):
    client = _client(db_session)
    try:
        wrong = client.post(
            "/auth/setup",
            json={
                "username": "admin",
                "setup_code": "wrong-code",
                "new_password": "new-password",
                "confirm_password": "new-password",
            },
        )
        assert wrong.status_code == 400

        success = client.post(
            "/auth/setup",
            json={
                "username": "admin",
                "setup_code": "autoinvest테스터",
                "new_password": "new-password",
                "confirm_password": "new-password",
            },
        )
        assert success.status_code == 200
        assert success.json()["user"]["setup_completed"] is True

        reused = client.post(
            "/auth/setup",
            json={
                "username": "admin",
                "setup_code": "autoinvest테스터",
                "new_password": "another-password",
                "confirm_password": "another-password",
            },
        )
        assert reused.status_code == 409
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_login_session_me_and_logout_use_hashed_db_token(db_session):
    client = _client(db_session)
    try:
        setup = client.post(
            "/auth/setup",
            json={
                "username": "admin",
                "setup_code": "autoinvest테스터",
                "new_password": "new-password",
                "confirm_password": "new-password",
            },
        )
        assert setup.status_code == 200

        invalid = client.post(
            "/auth/login",
            json={"username": "admin", "password": "wrong-password"},
        )
        assert invalid.status_code == 401

        login = client.post(
            "/auth/login",
            json={"username": "admin", "password": "new-password"},
        )
        assert login.status_code == 200
        assert login.json()["authenticated"] is True
        cookie_header = login.headers["set-cookie"]
        assert "HttpOnly" in cookie_header
        assert "SameSite=lax" in cookie_header
        assert "Secure" not in cookie_header

        session_token = client.cookies.get("auto_invest_session")
        assert session_token
        sessions = db_session.query(AuthSession).all()
        assert len(sessions) == 1
        assert sessions[0].session_token_hash != session_token
        assert len(sessions[0].session_token_hash) == 64

        me = client.get("/auth/me")
        assert me.status_code == 200
        assert me.json() == {
            "authenticated": True,
            "setup_required": False,
            "user": {
                "username": "admin",
                "role": "admin",
                "enabled": True,
                "setup_completed": True,
            },
        }

        logout = client.post("/auth/logout")
        assert logout.status_code == 200
        assert db_session.query(AuthSession).count() == 0
        assert client.get("/auth/me").json()["authenticated"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)


def _setup_and_login(client, password="old-password"):
    setup = client.post(
        "/auth/setup",
        json={
            "username": "admin",
            "setup_code": get_settings().initial_user_setup_code,
            "new_password": password,
            "confirm_password": password,
        },
    )
    assert setup.status_code == 200
    login = client.post(
        "/auth/login",
        json={"username": "admin", "password": password},
    )
    assert login.status_code == 200


def _login(client, password="old-password"):
    login = client.post(
        "/auth/login",
        json={"username": "admin", "password": password},
    )
    assert login.status_code == 200


def test_password_change_accepts_current_password_and_keeps_current_session(
    db_session,
):
    client = _client(db_session)
    other_client = _client(db_session)
    try:
        _setup_and_login(client)
        _login(other_client)
        changed = client.put(
            "/auth/password",
            json={
                "current_password": "old-password",
                "new_password": "new-password",
                "confirm_password": "new-password",
            },
        )
        assert changed.status_code == 200
        assert client.get("/auth/me").json()["authenticated"] is True
        assert db_session.query(AuthSession).count() == 1
        assert other_client.get("/auth/me").json()["authenticated"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_password_change_rejects_wrong_current_password(db_session):
    client = _client(db_session)
    try:
        _setup_and_login(client)
        response = client.put(
            "/auth/password",
            json={
                "current_password": "wrong-password",
                "new_password": "new-password",
                "confirm_password": "new-password",
            },
        )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_password_change_rejects_confirmation_mismatch(db_session):
    client = _client(db_session)
    try:
        _setup_and_login(client)
        response = client.put(
            "/auth/password",
            json={
                "current_password": "old-password",
                "new_password": "new-password",
                "confirm_password": "different-password",
            },
        )
        assert response.status_code == 400
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_password_change_replaces_login_password(db_session):
    client = _client(db_session)
    new_client = _client(db_session)
    try:
        _setup_and_login(client)
        changed = client.put(
            "/auth/password",
            json={
                "current_password": "old-password",
                "new_password": "new-password",
                "confirm_password": "new-password",
            },
        )
        assert changed.status_code == 200

        old_login = new_client.post(
            "/auth/login",
            json={"username": "admin", "password": "old-password"},
        )
        new_login = new_client.post(
            "/auth/login",
            json={"username": "admin", "password": "new-password"},
        )
        assert old_login.status_code == 401
        assert new_login.status_code == 200
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_password_change_requires_login(db_session):
    client = _client(db_session)
    try:
        response = client.put(
            "/auth/password",
            json={
                "current_password": "old-password",
                "new_password": "new-password",
                "confirm_password": "new-password",
            },
        )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_password_reset_accepts_setup_code_and_revokes_all_sessions(db_session):
    client = _client(db_session)
    other_client = _client(db_session)
    try:
        _setup_and_login(client)
        _login(other_client)

        reset = client.post(
            "/auth/reset-password",
            json={
                "username": "admin",
                "setup_code": get_settings().initial_user_setup_code,
                "new_password": "reset-password",
                "confirm_password": "reset-password",
            },
        )

        assert reset.status_code == 200
        assert reset.json()["authenticated"] is False
        assert db_session.query(AuthSession).count() == 0
        assert client.get("/auth/me").json()["authenticated"] is False
        assert other_client.get("/auth/me").json()["authenticated"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_password_reset_rejects_wrong_setup_code(db_session):
    client = _client(db_session)
    login_client = _client(db_session)
    try:
        _setup_and_login(client)
        response = client.post(
            "/auth/reset-password",
            json={
                "username": "admin",
                "setup_code": "wrong-code",
                "new_password": "reset-password",
                "confirm_password": "reset-password",
            },
        )

        assert response.status_code == 400
        assert _login(login_client) is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_password_reset_rejects_confirmation_mismatch(db_session):
    client = _client(db_session)
    try:
        _setup_and_login(client)
        response = client.post(
            "/auth/reset-password",
            json={
                "username": "admin",
                "setup_code": get_settings().initial_user_setup_code,
                "new_password": "reset-password",
                "confirm_password": "different-password",
            },
        )

        assert response.status_code == 400
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_password_reset_replaces_login_password(db_session):
    client = _client(db_session)
    login_client = _client(db_session)
    try:
        _setup_and_login(client)
        reset = client.post(
            "/auth/reset-password",
            json={
                "username": "admin",
                "setup_code": get_settings().initial_user_setup_code,
                "new_password": "reset-password",
                "confirm_password": "reset-password",
            },
        )
        assert reset.status_code == 200

        old_login = login_client.post(
            "/auth/login",
            json={"username": "admin", "password": "old-password"},
        )
        new_login = login_client.post(
            "/auth/login",
            json={"username": "admin", "password": "reset-password"},
        )
        assert old_login.status_code == 401
        assert new_login.status_code == 200
    finally:
        app.dependency_overrides.pop(get_db, None)
