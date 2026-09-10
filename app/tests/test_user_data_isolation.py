from app.db.database import get_db
from app.main import app
from fastapi.testclient import TestClient

from app.tests.test_user_data_foundation import _setup_admin


def _client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_user_settings_and_watchlists_are_isolated(db_session):
    admin = _client(db_session)
    try:
        _setup_admin(admin)
        assert admin.post('/admin/users', json={'username': 'test01'}).status_code == 201
        assert admin.post('/admin/users', json={'username': 'test02'}).status_code == 201

        assert admin.post(
            '/auth/register',
            json={
                'username': 'test01',
                'setup_code': 'autoinvest테스터',
                'new_password': 'one-password',
                'confirm_password': 'one-password',
            },
        ).status_code == 200
        assert admin.post(
            '/auth/register',
            json={
                'username': 'test02',
                'setup_code': 'autoinvest테스터',
                'new_password': 'two-password',
                'confirm_password': 'two-password',
            },
        ).status_code == 200

        first = _client(db_session)
        second = _client(db_session)
        try:
            assert first.post(
                '/auth/login',
                json={'username': 'test01', 'password': 'one-password'},
            ).status_code == 200
            assert second.post(
                '/auth/login',
                json={'username': 'test02', 'password': 'two-password'},
            ).status_code == 200

            assert first.put(
                '/users/me/settings',
                json={'settings': {'display_name': 'first'}},
            ).status_code == 200
            assert second.get('/users/me/settings').json()['settings'] == {}
            assert first.post('/users/me/watchlist', json={'symbol': '005930'}).status_code == 201
            assert second.get('/users/me/watchlist').json()['items'] == []
            assert first.get('/users/me/watchlist').json()['items'][0]['symbol'] == '005930'
            assert second.post('/admin/users', json={'username': 'test03'}).status_code == 403
            assert first.put(
                '/auth/password',
                json={
                    'current_password': 'one-password',
                    'new_password': 'one-new-password',
                    'confirm_password': 'one-new-password',
                },
            ).status_code == 200
        finally:
            app.dependency_overrides.pop(get_db, None)
    finally:
        app.dependency_overrides.pop(get_db, None)
