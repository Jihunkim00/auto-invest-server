from datetime import datetime
from zoneinfo import ZoneInfo

from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.automation_profile_service import (
    AutomationProfileConflict,
    AutomationProfileService,
    AutomationProfileValidationError,
)
from app.services.symbol_search_service import SymbolSearchService
from app.services.strategy_profile_service import StrategyProfileService


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
    assert service.list_profiles(db_session)['active_profile']['profile_key'] == 'pr108-demo'

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


def test_profile_key_is_generated_when_omitted_and_stays_immutable(db_session):
    service = AutomationProfileService()
    payload = _request(name='Generated profile').model_dump()
    payload.pop('profile_key', None)

    first = service.create(db_session, AutomationProfileWriteRequest(**payload))
    second = service.create(db_session, AutomationProfileWriteRequest(**payload))

    assert first['profile_key'].startswith('aut_kis_')
    assert len(first['profile_key']) == len('aut_kis_') + 8
    assert first['profile_key'] != second['profile_key']
    assert first['profile_key_generated'] is True

    renamed = service.update(
        db_session,
        str(first['id']),
        AutomationProfileWriteRequest(name='Renamed profile'),
    )
    assert renamed['name'] == 'Renamed profile'
    assert renamed['profile_key'] == first['profile_key']

    activated = service.activate(db_session, str(first['id']))
    assert activated['profile']['profile_key'] == first['profile_key']
    runtime = service.runtime_settings.get_settings_read_only(db_session)
    assert runtime['active_automation_profile_key'] == first['profile_key']
    assert StrategyProfileService().active_profile(db_session).profile_key == first['profile_key']

    try:
        service.update(
            db_session,
            str(first['id']),
            AutomationProfileWriteRequest(profile_key='aut_kis_changed', name='Renamed again'),
        )
    except AutomationProfileConflict as exc:
        assert str(exc) == 'profile_key_is_immutable'
    else:
        raise AssertionError('generated profile key unexpectedly changed')


def test_kis_profile_runtime_uses_test4_hard_safety_floor(db_session):
    service = AutomationProfileService()
    created = service.create(
        db_session,
        _request(
            profile_key='below-hard-floor',
            capital={'max_order_notional_krw': 2_000_000, 'cash_only': False},
            entry={'min_final_score': 62, 'no_new_entry_after': '15:00'},
            exit={'stop_loss_pct': 8, 'take_profit_pct': 10},
            max_open_positions=3,
        ),
    )

    effective = created['effective_settings']
    assert effective['entry']['min_final_score'] == 65
    assert effective['entry']['no_new_entry_after'] == '14:00'
    assert effective['max_open_positions'] == 1
    assert effective['capital']['max_order_notional_krw'] == 1_000_000
    assert effective['capital']['cash_only'] is True
    assert effective['exit']['stop_loss_pct'] == 2
    assert effective['exit']['take_profit_pct'] == 10

    readiness = service.readiness(db_session, str(created['id']))
    assert readiness['effective_settings']['max_open_positions'] == 1
    assert readiness['requires_pr109_portfolio_engine'] is True
def test_future_selected_profile_is_scheduled_and_arms_profile_scheduler_only(db_session):
    service = AutomationProfileService()
    created = service.create(
        db_session,
        _request(
            profile_key='future-schedule',
            entry={
                'analysis_times': ['09:10', '11:30', '13:30'],
                'no_new_entry_after': '14:00',
            },
            operation={
                'start_date': '2099-08-24',
                'end_date': '2099-09-30',
                'weekdays_only': True,
                'timezone': 'Asia/Seoul',
            },
        ),
    )

    service.activate(db_session, str(created['id']))
    state = service.list_profiles(db_session)
    assert state['selected_profile']['profile_key'] == 'future-schedule'
    assert state['selected_profile_status'] == 'scheduled'
    assert state['active_profile'] is None
    assert state['automation_selected'] is True

    runtime = service.runtime_settings.get_settings_read_only(db_session)
    assert runtime['automation_profile_scheduler_enabled'] is True
    assert runtime['scheduler_enabled'] is False
    assert runtime['dry_run'] is True
    assert runtime['kill_switch'] is False

    schedule = service.selected_profile_schedule(
        db_session,
        now=datetime(2099, 8, 23, 12, tzinfo=ZoneInfo('Asia/Seoul')),
    )
    assert schedule['status'] == 'scheduled'
    assert schedule['analysis_times'] == ['09:10', '11:30', '13:30']
    assert schedule['next_run_at'].isoformat() == '2099-08-24T09:10:00+09:00'

    active_schedule = service.selected_profile_schedule(
        db_session,
        now=datetime(2099, 8, 24, 10, tzinfo=ZoneInfo('Asia/Seoul')),
    )
    assert active_schedule['status'] == 'active'
    assert active_schedule['next_run_at'].isoformat() == '2099-08-24T11:30:00+09:00'


def test_take_profit_outside_pr110_range_is_rejected(db_session):
    service = AutomationProfileService()
    for value in (0.5, 15.1):
        try:
            service.create(
                db_session,
                _request(
                    profile_key=f'invalid-tp-{value}',
                    exit={'take_profit_pct': value},
                ),
            )
        except AutomationProfileValidationError as exc:
            assert any(item['field'] == 'exit.take_profit_pct' for item in exc.errors)
        else:
            raise AssertionError('invalid take profit unexpectedly created')