from fastapi.testclient import TestClient
from datetime import UTC, datetime

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


def _request(
    key: str | None,
    name: str,
    *,
    client_request_id: str | None = None,
) -> AutomationProfileWriteRequest:
    return AutomationProfileWriteRequest(
        profile_key=key,
        name=name,
        provider='kis',
        market='KR',
        client_request_id=client_request_id,
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
        active_row = db_session.get(StrategyProfile, profile_a_id)
        assert active_row.enabled is True
        assert active_row.custom_status == 'active'
        assert active_row.is_active is False
        resolved = service.selected_owned_profile_schedule(
            db_session,
            owner_user_id=user_a.id,
            now=datetime(2026, 9, 15, 1, 0, tzinfo=UTC),
        )
        assert resolved is not None
        assert resolved['profile']['id'] == profile_a_id
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

def test_owner_profile_create_is_idempotent_but_allows_intentional_duplicates(db_session):
    user_a = _user(db_session, 'profile-idempotency-a')
    user_b = _user(db_session, 'profile-idempotency-b')
    service = AutomationProfileService()

    first = service.create(
        db_session, _request(None, 'Same settings', client_request_id='retry-a'),
        owner_user_id=user_a.id,
    )
    replay = service.create(
        db_session, _request(None, 'Same settings', client_request_id='retry-a'),
        owner_user_id=user_a.id,
    )
    assert replay['id'] == first['id']
    assert db_session.query(StrategyProfile).filter_by(owner_user_id=user_a.id).count() == 1

    intentional = service.create(
        db_session, _request(None, 'Same settings', client_request_id='retry-b'),
        owner_user_id=user_a.id,
    )
    assert intentional['id'] != first['id']
    assert db_session.query(StrategyProfile).filter_by(owner_user_id=user_a.id).count() == 2

    isolated = service.create(
        db_session, _request(None, 'Same settings', client_request_id='retry-a'),
        owner_user_id=user_b.id,
    )
    assert isolated['id'] != first['id']
    assert db_session.query(StrategyProfile).filter_by(owner_user_id=user_b.id).count() == 1

def test_admin_system_scope_rejects_user_profiles_for_all_profile_operations(db_session):
    admin = _user(db_session, 'profile-system-admin', role='admin')
    user_a = _user(db_session, 'profile-scope-a')
    user_b = _user(db_session, 'profile-scope-b')
    service = AutomationProfileService()

    system_profile = service.create(
        db_session,
        _request('system-scope-profile', 'System profile'),
    )
    profile_a = service.create(
        db_session,
        _request('user-a-scope-profile', 'User A profile'),
        owner_user_id=user_a.id,
    )
    profile_b = service.create(
        db_session,
        _request('user-b-scope-profile', 'User B profile'),
        owner_user_id=user_b.id,
    )
    service.activate(db_session, str(system_profile['id']))
    service.activate(
        db_session,
        str(profile_a['id']),
        owner_user_id=user_a.id,
    )
    db_session.expire_all()

    system_row = db_session.get(StrategyProfile, system_profile['id'])
    user_a_row = db_session.get(StrategyProfile, profile_a['id'])
    user_b_row = db_session.get(StrategyProfile, profile_b['id'])
    assert system_row.owner_user_id is None
    assert user_a_row.owner_user_id == user_a.id
    assert user_b_row.owner_user_id == user_b.id
    assert user_a_row.enabled is True
    assert user_a_row.custom_status == 'active'
    assert user_a_row.is_active is False
    assert service.selected_profile(db_session).id == system_profile['id']
    assert service.selected_owned_profile_schedule(
        db_session,
        owner_user_id=user_a.id,
        now=datetime(2026, 9, 15, 1, 0, tzinfo=UTC),
    )['profile']['id'] == profile_a['id']

    client_admin = _client(db_session, admin)
    client_a = _client(db_session, user_a)
    client_b = _client(db_session, user_b)
    try:
        assert [profile['id'] for profile in client_admin.get('/strategy-profiles').json()['profiles']] == [
            system_profile['id']
        ]
        assert [profile['id'] for profile in client_a.get('/users/me/automation-profiles').json()['profiles']] == [
            profile_a['id']
        ]
        assert [profile['id'] for profile in client_b.get('/users/me/automation-profiles').json()['profiles']] == [
            profile_b['id']
        ]

        def assert_profile_not_found(response):
            assert response.status_code == 404, response.text
            assert response.json()['detail']['code'] == 'profile_not_found'

        original_b = (
            user_b_row.display_name,
            user_b_row.enabled,
            user_b_row.custom_status,
            user_b_row.is_active,
        )
        runtime_before = RuntimeSettingService().get_settings_read_only(db_session)
        assert runtime_before['active_automation_profile_key'] == system_profile['profile_key']

        assert_profile_not_found(
            client_admin.get(f"/strategy-profiles/{profile_b['id']}")
        )
        assert_profile_not_found(
            client_admin.put(
                f"/strategy-profiles/{profile_b['id']}",
                json={'name': 'must not update user B'},
            )
        )
        assert_profile_not_found(
            client_admin.post(
                f"/strategy-profiles/{profile_b['id']}/activate",
                json={'confirm_operator_ack': True},
            )
        )
        assert_profile_not_found(
            client_admin.post(
                f"/strategy-profiles/{profile_b['id']}/pause",
                json={'confirm_operator_ack': True},
            )
        )
        assert_profile_not_found(
            client_admin.delete(f"/strategy-profiles/{profile_b['id']}")
        )
        assert_profile_not_found(
            client_admin.post(f"/strategy-profiles/{profile_b['id']}/validate")
        )
        assert_profile_not_found(
            client_admin.get(f"/strategy-profiles/{profile_b['id']}/readiness")
        )
        assert_profile_not_found(
            client_admin.post(
                f"/strategy-profiles/{profile_b['id']}/sizing-preview",
                json={},
            )
        )
        assert_profile_not_found(
            client_admin.get(f"/strategy-profiles/{profile_b['id']}/capital-state")
        )
        assert_profile_not_found(
            client_admin.get(f"/strategy-profiles/{profile_b['id']}/watchlist")
        )
        assert_profile_not_found(
            client_admin.get(
                f"/strategy-profiles/{profile_b['id']}/watchlist-diagnostics"
            )
        )
        assert_profile_not_found(
            client_admin.put(
                f"/strategy-profiles/{profile_b['id']}/watchlist",
                json={'universe': {'watchlist_size': 10}},
            )
        )

        db_session.expire_all()
        unchanged_b = db_session.get(StrategyProfile, profile_b['id'])
        assert (
            unchanged_b.display_name,
            unchanged_b.enabled,
            unchanged_b.custom_status,
            unchanged_b.is_active,
        ) == original_b
        assert (
            RuntimeSettingService()
            .get_settings_read_only(db_session)['active_automation_profile_key']
            == system_profile['profile_key']
        )
        assert service.selected_profile(db_session).id == system_profile['id']

        assert_profile_not_found(
            client_a.get(f"/users/me/automation-profiles/{profile_b['id']}")
        )
        assert_profile_not_found(
            client_a.get(f"/users/me/automation-profiles/{system_profile['id']}")
        )
        assert_profile_not_found(
            client_a.get(
                f"/users/me/automation-profiles/{profile_b['id']}/watchlist-diagnostics"
            )
        )
        assert_profile_not_found(
            client_a.get(
                f"/users/me/automation-profiles/{system_profile['id']}/watchlist-diagnostics"
            )
        )
        own_diagnostics = client_a.get(
            f"/users/me/automation-profiles/{profile_a['id']}/watchlist-diagnostics"
        )
        assert own_diagnostics.status_code == 200
        assert own_diagnostics.json() == {'snapshot': None, 'items': []}
    finally:
        app.dependency_overrides.pop(get_db, None)
def test_archiving_owned_profile_is_soft_and_owner_isolated(db_session):
    owner = _user(db_session, 'profile-archive-owner')
    other = _user(db_session, 'profile-archive-other')
    service = AutomationProfileService()
    admin = service.create(db_session, _request('archive-admin', 'Admin'))
    owned = service.create(
        db_session, _request('archive-owned', 'Owned'), owner_user_id=owner.id,
    )
    other_profile = service.create(
        db_session, _request('archive-other', 'Other'), owner_user_id=other.id,
    )
    service.activate(db_session, str(owned['id']), owner_user_id=owner.id)
    service.archive(db_session, str(owned['id']), owner_user_id=owner.id)

    archived = db_session.get(StrategyProfile, owned['id'])
    assert archived.enabled is False
    assert archived.is_active is False
    assert archived.custom_status == 'archived'
    assert service.selected_owned_profile_schedule(db_session, owner_user_id=owner.id) is None
    assert db_session.get(StrategyProfile, other_profile['id']).custom_status == 'disabled'
    assert db_session.get(StrategyProfile, admin['id']).custom_status == 'disabled'
