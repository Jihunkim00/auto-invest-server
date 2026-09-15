from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.database import get_db
from app.db.models import SignalLog, StrategyProfile, TradeRunLog, User
from app.main import app
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.auth_service import create_session
from app.services.automation_profile_service import AutomationProfileService


def _user(db, username: str, role: str = 'user') -> User:
    row = User(username=username, role=role, enabled=True, setup_completed=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _request(key: str) -> AutomationProfileWriteRequest:
    return AutomationProfileWriteRequest(
        profile_key=key,
        name=key,
        provider='kis',
        market='KR',
        operation={'start_date': '2026-08-01', 'end_date': '2026-12-31'},
    )


def _client(db, user: User) -> TestClient:
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    client.cookies.set(get_settings().session_cookie_name, create_session(db, user))
    return client


def test_admin_owned_profiles_use_authenticated_admin_scope_and_global_runtime(db_session):
    # Deliberately make the Admin id non-default: ownership must come from the
    # authenticated role, never from a hardcoded numeric id.
    _user(db_session, 'before-admin')
    admin = _user(db_session, 'hotfix-admin', role='admin')
    regular = _user(db_session, 'hotfix-user')
    service = AutomationProfileService()
    system = service.create(db_session, _request('hotfix-system'))
    owned = service.create(db_session, _request('hotfix-admin-owned'), owner_user_id=admin.id)
    user_profile = service.create(db_session, _request('hotfix-user-owned'), owner_user_id=regular.id)

    service.activate(db_session, str(owned['id']), admin_user_id=admin.id)
    assert service.selected_profile(db_session).id == owned['id']

    client = _client(db_session, admin)
    try:
        listed = client.get('/strategy-profiles')
        assert listed.status_code == 200
        assert {item['id'] for item in listed.json()['profiles']} == {system['id'], owned['id']}
        assert listed.json()['selected_profile']['id'] == owned['id']
        assert client.get(f"/strategy-profiles/{owned['id']}").status_code == 200
        assert client.post(f"/strategy-profiles/{owned['id']}/validate").status_code == 200
        assert client.get(f"/strategy-profiles/{owned['id']}/readiness").status_code == 200
        assert client.get(f"/strategy-profiles/{owned['id']}/watchlist").status_code == 200
        assert client.get(f"/strategy-profiles/{owned['id']}/watchlist-diagnostics").status_code == 200
        assert client.get(f"/strategy-profiles/{user_profile['id']}").status_code == 404
        assert client.post(f"/strategy-profiles/{user_profile['id']}/validate").status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_admin_home_feed_includes_admin_and_system_but_not_regular_or_precondition_rows(db_session):
    admin = _user(db_session, 'feed-admin', role='admin')
    regular = _user(db_session, 'feed-user')
    base = datetime(2026, 9, 15, 1, 0, tzinfo=UTC)
    rows = [
        (None, '086790', base),
        (admin.id, '005930', base + timedelta(minutes=1)),
        (regular.id, '035420', base + timedelta(minutes=2)),
        (admin.id, 'NONE', base + timedelta(minutes=3)),
    ]
    for index, (owner, symbol, created_at) in enumerate(rows):
        db_session.add(TradeRunLog(
            owner_user_id=owner,
            run_key=f'hotfix-feed-{index}',
            trigger_source='automation_scheduler',
            symbol=symbol,
            mode='automation_scheduler_profile_analysis',
            stage='done',
            result='blocked',
            reason='live_trading_disabled' if symbol == 'NONE' else 'below_profile_buy_threshold',
            created_at=created_at,
        ))
    db_session.commit()

    client = _client(db_session, admin)
    try:
        response = client.get('/runs/automation/recent?limit=10')
        assert response.status_code == 200
        assert [item['symbol'] for item in response.json()['items']] == ['005930', '086790']
        assert [item['owner_user_id'] for item in response.json()['items']] == [admin.id, None]
    finally:
        app.dependency_overrides.pop(get_db, None)