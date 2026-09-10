from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.database import get_db
from app.db.models import User
from app.main import app


def _client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _setup_admin(client):
    setup = client.post(
        '/auth/setup',
        json={
            'username': 'admin',
            'setup_code': get_settings().initial_user_setup_code,
            'new_password': 'admin-password',
            'confirm_password': 'admin-password',
        },
    )
    assert setup.status_code == 200
    login = client.post(
        '/auth/login',
        json={'username': 'admin', 'password': 'admin-password'},
    )
    assert login.status_code == 200


def test_admin_user_cap_and_registration_flow(db_session):
    client = _client(db_session)
    try:
        _setup_admin(client)
        assert client.get('/admin/users').status_code == 200
        for username in ('test01', 'test02', 'test03', 'test04'):
            created = client.post('/admin/users', json={'username': username})
            assert created.status_code == 201
            assert created.json()['role'] == 'user'

        assert client.post('/admin/users', json={'username': 'test05'}).status_code == 409
        assert client.post(
            '/auth/register',
            json={
                'username': 'uncreated',
                'setup_code': get_settings().initial_user_setup_code,
                'new_password': 'password',
                'confirm_password': 'password',
            },
        ).status_code == 409

        registered = client.post(
            '/auth/register',
            json={
                'username': 'test01',
                'setup_code': get_settings().initial_user_setup_code,
                'new_password': 'user-password',
                'confirm_password': 'user-password',
            },
        )
        assert registered.status_code == 200
        assert registered.json()['user']['role'] == 'user'
        assert db_session.query(User).filter(User.username == 'test01').one().setup_completed

        user_client = _client(db_session)
        try:
            login = user_client.post(
                '/auth/login',
                json={'username': 'test01', 'password': 'user-password'},
            )
            assert login.status_code == 200
            assert login.json()['user']['role'] == 'user'
            assert user_client.get('/auth/me').json()['user']['role'] == 'user'
            assert user_client.get('/admin/users').status_code == 403
        finally:
            app.dependency_overrides.pop(get_db, None)
    finally:
        app.dependency_overrides.pop(get_db, None)
