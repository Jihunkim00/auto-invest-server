from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.automation_profile_service import (
    AutomationProfileService,
    AutomationProfileValidationError,
)
from app.services.symbol_search_service import SymbolSearchService


def _request(**overrides):
    payload = {
        'profile_key': 'pr108-demo',
        'name': 'PR108 Demo',
        'provider': 'kis',
        'market': 'KR',
        'capital': {'sizing_mode': 'equity_pct'},
        'operation': {'start_date': '2026-08-01', 'end_date': '2026-09-30'},
    }
    payload.update(overrides)
    return AutomationProfileWriteRequest(**payload)


def test_profile_crud_archive_and_activation_does_not_touch_legacy_state(db_session):
    service = AutomationProfileService()
    created = service.create(db_session, _request())
    assert created['profile_key'] == 'pr108-demo'
    assert created['status'] == 'disabled'

    activated = service.activate(db_session, str(created['id']))
    assert activated['status'] == 'active'
    assert activated['safety']['dry_run_changed'] is False
    assert activated['safety']['kill_switch_changed'] is False
    row = service.get(db_session, str(created['id']))
    assert row.is_active is False
    assert row.enabled is True

    paused = service.pause(db_session, str(created['id']))
    assert paused['status'] == 'paused'
    archived = service.archive(db_session, str(created['id']))
    assert archived['status'] == 'archived'
    assert service.list_profiles(db_session)['profiles'][0]['status'] == 'archived'


def test_profile_validation_rejects_duplicate_times_and_bad_period(db_session):
    service = AutomationProfileService()
    request = _request(
        profile_key='invalid-profile',
        entry={'analysis_times': ['09:10', '09:10'], 'no_new_entry_after': '99:00'},
        operation={'start_date': '2026-10-01', 'end_date': '2026-09-01'},
    )
    try:
        service.create(db_session, request)
    except AutomationProfileValidationError as exc:
        fields = {item['field'] for item in exc.errors}
        assert 'entry.analysis_times' in fields
        assert 'entry.no_new_entry_after' in fields
        assert 'operation.period' in fields
    else:
        raise AssertionError('invalid profile unexpectedly created')


def test_three_positions_are_configurable_but_readiness_requires_pr109(db_session):
    service = AutomationProfileService()
    created = service.create(db_session, _request(profile_key='three-position', max_open_positions=3))
    assert created['max_open_positions'] == 3
    assert created['multi_position_execution_supported'] is False
    assert created['requires_pr109_portfolio_engine'] is True
    readiness = service.readiness(db_session, str(created['id']))
    assert readiness['multi_position_execution_supported'] is False
    assert readiness['requires_pr109_portfolio_engine'] is True
    assert readiness['runtime_safety']['live_flags_unchanged'] is True


def test_sizing_preview_is_read_only_and_respects_cash_and_price(db_session):
    service = AutomationProfileService()
    created = service.create(db_session, _request(profile_key='sizing-profile'))
    result = service.sizing(
        db_session,
        str(created['id']),
        {
            'equity': 1_000_000,
            'orderable_cash': 500_000,
            'current_position_value': 0,
            'current_total_exposure': 0,
            'current_price': 10_000,
        },
    )
    assert result['sizing']['quantity'] == 10
    assert result['sizing']['estimated_notional'] == 100_000
    assert result['safety']['broker_submit_called'] is False


def test_symbol_search_returns_ambiguous_candidates_without_broker_calls():
    result = SymbolSearchService().search('삼성', market='KR')
    assert result['results']
    assert result['results'][0]['symbol'] == '005930'
    assert result['results'][0]['current_price'] is None


def test_profile_http_routes_cover_crud_validation_and_readiness(db_session):
    from fastapi.testclient import TestClient

    from app.db.database import get_db
    from app.main import app

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.post('/strategy-profiles', json={
                'profile_key': 'http-profile',
                'name': 'HTTP profile',
                'operation': {'start_date': '2026-08-01', 'end_date': '2026-09-30'},
            })
            assert response.status_code == 201, response.text
            profile_id = response.json()['id']
            assert client.get(f'/strategy-profiles/{profile_id}').status_code == 200
            assert client.post(f'/strategy-profiles/{profile_id}/activate', json={}).status_code == 409
            activated = client.post(
                f'/strategy-profiles/{profile_id}/activate',
                json={'confirm_operator_ack': True},
            )
            assert activated.status_code == 200, activated.text
            assert activated.json()['safety']['dry_run_changed'] is False
            assert client.get(f'/strategy-profiles/{profile_id}/readiness').status_code == 200
            archived = client.delete(f'/strategy-profiles/{profile_id}')
            assert archived.status_code == 200
            assert archived.json()['status'] == 'archived'
    finally:
        app.dependency_overrides.pop(get_db, None)
