from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.database import get_db
from app.db.models import StrategyProfile, User
from app.main import app
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.auth_service import create_session
from app.services.automation_profile_service import AutomationProfileService
from app.services.runtime_setting_service import RuntimeSettingService


def _user(db_session, username: str, role: str = 'user') -> User:
    row = User(
        username=username,
        role=role,
        enabled=True,
        setup_completed=True,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _request(key: str, name: str) -> AutomationProfileWriteRequest:
    return AutomationProfileWriteRequest(
        profile_key=key,
        name=name,
        provider='kis',
        market='KR',
        operation={
            'start_date': '2026-08-01',
            'end_date': '2026-12-31',
        },
    )


def _client(db_session, user: User) -> TestClient:
    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    client.cookies.set(
        get_settings().session_cookie_name,
        create_session(db_session, user),
    )
    return client


def test_user_profile_crud_and_activation_are_owner_isolated(db_session):
    admin = _user(db_session, 'profile-admin', role='admin')
    user_a = _user(db_session, 'profile-a')
    user_b = _user(db_session, 'profile-b')
    service = AutomationProfileService()

    admin_profile = service.create(
        db_session,
        _request('admin-owned-profile', 'Admin profile'),
    )
    profile_a = service.create(
        db_session,
        _request('user-a-profile', 'User A profile'),
        owner_user_id=user_a.id,
    )
    profile_b = service.create(
        db_session,
        _request('user-b-profile', 'User B profile'),
        owner_user_id=user_b.id,
    )
    db_session.expire_all()
    admin_profile_id = admin_profile['id']
    profile_a_id = profile_a['id']
    profile_b_id = profile_b['id']

    client_a = _client(db_session, user_a)
    client_b = _client(db_session, user_b)
    client_admin = _client(db_session, admin)
    try:
        assert client_admin.get('/strategy-profiles').status_code == 200
        assert client_a.get('/strategy-profiles').status_code == 403
        assert client_a.post(
            '/strategy-profiles',
            json={'profile_key': 'blocked-global', 'name': 'Blocked'},
        ).status_code == 403
        listed_a = client_a.get('/users/me/automation-profiles')
        listed_b = client_b.get('/users/me/automation-profiles')
        assert listed_a.status_code == 200
        assert listed_b.status_code == 200
        assert [item['profile_key'] for item in listed_a.json()['profiles']] == [
            'user-a-profile'
        ]
        assert [item['profile_key'] for item in listed_b.json()['profiles']] == [
            'user-b-profile'
        ]

        assert client_a.get(
            f'/users/me/automation-profiles/{profile_b_id}',
        ).status_code == 404
        assert client_a.get(
            f'/users/me/automation-profiles/{admin_profile_id}',
        ).status_code == 404
        assert client_a.put(
            f'/users/me/automation-profiles/{profile_b_id}',
            json={'name': 'cross-user update'},
        ).status_code == 404
        assert client_a.post(
            f'/users/me/automation-profiles/{profile_b_id}/activate',
            json={'confirm_operator_ack': True},
        ).status_code == 404
        assert client_a.post(
            f'/users/me/automation-profiles/{admin_profile_id}/pause',
            json={'confirm_operator_ack': True},
        ).status_code == 404

        created = client_a.post(
            '/users/me/automation-profiles',
            json={
                'profile_key': 'user-a-created',
                'name': 'Created by A',
                'operation': {
                    'start_date': '2026-08-01',
                    'end_date': '2026-12-31',
                },
            },
        )
        assert created.status_code == 201, created.text
        created_row = db_session.get(StrategyProfile, created.json()['id'])
        assert created_row.owner_user_id == user_a.id
        assert 'user-a-created' in {
            item['profile_key']
            for item in client_a.get('/users/me/automation-profiles').json()[
                'profiles'
            ]
        }
        assert 'user-a-created' not in {
            item['profile_key']
            for item in client_b.get('/users/me/automation-profiles').json()[
                'profiles'
            ]
        }

        activated = client_a.post(
            f'/users/me/automation-profiles/{profile_a_id}/activate',
            json={'confirm_operator_ack': True},
        )
        assert activated.status_code == 200, activated.text
        assert activated.json()['status'] == 'active'
        db_session.expire_all()
        assert db_session.get(StrategyProfile, profile_b['id']).custom_status == (
            'disabled'
        )
        assert (
            RuntimeSettingService()
            .get_settings_read_only(db_session)
            .get('active_automation_profile_key')
            is None
        )

        assert client_b.post(
            f'/users/me/automation-profiles/{profile_b_id}/activate',
            json={'confirm_operator_ack': True},
        ).status_code == 200
        db_session.expire_all()
        assert db_session.get(StrategyProfile, profile_a['id']).custom_status == (
            'active'
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
