import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import PositionLifecycle
from app.main import app
from app.routes.automation import get_automation_mode_control_service
from app.routes.strategy_auto_buy_scheduler import get_automation_profile_buy_scheduler_service
from app.services.runtime_setting_service import RuntimeSettingService

from app.tests.test_pr110_final_buy_readiness import (
    NOW,
    FakeKisClient,
    _build_service,
    _candidate,
)


LEGACY_FLAGS = {
    'dry_run',
    'kill_switch',
    'runtime_authorized',
    'live_order_possible',
    'kis_real_order_enabled',
    'strategy_live_auto_buy_enabled',
    'strategy_live_auto_buy_scheduler_enabled',
    'auto_buy_live_phase1_enabled',
}


def _set_mode(db, runtime, mode):
    runtime.update_settings(db, {'automation_mode': mode})


def _run(service, db, candidate=None):
    return service.run_once(
        db,
        [candidate or _candidate(70)],
        scheduler_slot='09:10',
        trigger_source='automation_profile_scheduler',
        now=NOW,
    )


@pytest.mark.parametrize(
    ('mode', 'expected_authority', 'expected_scheduler', 'expected_broker', 'expected_status', 'expected_can_submit'),
    [
        ('live', 'LIVE', True, True, 'live_ready', True),
        ('test', 'TEST', True, False, 'test_ready', False),
        ('off', 'OFF', False, False, 'off', False),
    ],
)
def test_mode_status_and_buy_readiness_share_one_authority_snapshot(
    db_session,
    mode,
    expected_authority,
    expected_scheduler,
    expected_broker,
    expected_status,
    expected_can_submit,
):
    service, runtime, _, _, broker, _, _, _ = _build_service(db_session)
    _set_mode(db_session, runtime, mode)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_automation_profile_buy_scheduler_service] = lambda: service
    try:
        client = TestClient(app)
        mode_response = client.get('/automation/mode/status')
        readiness_response = client.get('/strategy/auto-buy/scheduler/buy-readiness')
    finally:
        app.dependency_overrides.clear()

    assert mode_response.status_code == 200
    assert readiness_response.status_code == 200
    mode_status = mode_response.json()
    readiness = readiness_response.json()
    for payload in (mode_status, readiness):
        assert payload['execution_authority'] == expected_authority
        assert payload['scheduler_allowed'] is expected_scheduler
        assert payload['broker_submit_allowed'] is expected_broker
        assert payload['source_of_truth'] == 'automation_mode'
    assert mode_status['effective_status'] == expected_status
    assert mode_status['can_attempt_phase1_live'] is (mode == 'live')
    assert mode_status['can_submit_live_order'] is expected_can_submit
    assert broker.buy_calls == []


def test_test_mode_runs_full_profile_core_simulation_without_broker(db_session):
    service, runtime, _, client, broker, validation, sync, _ = _build_service(db_session)
    _set_mode(db_session, runtime, 'test')

    result = _run(service, db_session)

    assert result['status'] == 'filled'
    assert result['reason'] == 'buy_filled'
    assert result['live_order_gate']['automation_mode'] == 'test'
    assert result['live_order_gate']['broker_submit_allowed'] is False
    assert result['broker_buy_call_count'] == 0
    assert broker.buy_calls == []
    assert len(validation.calls) == 1
    assert len(sync.calls) == 1
    assert client.external_kis_submit_count == 0
    assert db_session.query(PositionLifecycle).one().status == 'open'


def test_live_mode_passes_hard_safety_and_submits_fake_broker_once(db_session):
    service, runtime, _, client, broker, validation, sync, _ = _build_service(db_session)
    _set_mode(db_session, runtime, 'live')

    result = _run(service, db_session)

    assert result['status'] == 'filled'
    assert result['broker_buy_call_count'] == 1
    assert len(broker.buy_calls) == 1
    assert len(validation.calls) == 1
    assert len(sync.calls) == 1
    assert client.external_kis_submit_count == 0
    assert db_session.query(PositionLifecycle).one().status == 'open'


def test_off_mode_blocks_scheduler_execution_and_broker_submit(db_session):
    service, runtime, _, _, broker, validation, _, _ = _build_service(db_session)
    _set_mode(db_session, runtime, 'off')

    result = _run(service, db_session)

    assert result['status'] == 'blocked'
    assert result['reason'] == 'automation_mode_off'
    assert broker.buy_calls == []
    assert validation.calls == []


class _FlipToOffValidation:
    def __init__(self, db, runtime):
        self.db = db
        self.runtime = runtime
        self.calls = []

    def validate(self, request, *, now=None):
        from app.tests.test_pr110_final_buy_readiness import FakeValidationResult

        self.calls.append(request)
        result = FakeValidationResult(request)
        self.runtime.update_settings(self.db, {'automation_mode': 'off'})
        return result


def test_live_to_off_before_final_submit_blocks_without_broker_call(db_session):
    service, runtime, _, client, broker, _, _, _ = _build_service(db_session)
    validation = _FlipToOffValidation(db_session, runtime)
    service.validation_service = validation
    service.execution_core.validation_service = validation
    _set_mode(db_session, runtime, 'live')

    result = _run(service, db_session)

    assert result['status'] == 'blocked'
    assert result['reason'] == 'automation_mode_off'
    assert result['broker_buy_call_count'] == 0
    assert broker.buy_calls == []
    assert len(validation.calls) == 1
    assert client.external_kis_submit_count == 0


@pytest.mark.parametrize(
    ('mode', 'legacy_value', 'expected_broker_calls'),
    [
        ('test', False, 0),
        ('test', True, 0),
        ('live', False, 1),
        ('live', True, 1),
    ],
)
def test_legacy_flags_do_not_change_automation_mode_meaning(
    db_session,
    mode,
    legacy_value,
    expected_broker_calls,
):
    service, runtime, _, _, broker, _, _, _ = _build_service(db_session)
    _set_mode(db_session, runtime, mode)
    runtime.update_settings(db_session, {key: legacy_value for key in LEGACY_FLAGS})

    result = _run(service, db_session)

    assert result['live_order_gate']['automation_mode'] == mode
    assert result['broker_buy_call_count'] == expected_broker_calls
    assert len(broker.buy_calls) == expected_broker_calls


def test_live_score_below_65_never_reaches_broker(db_session):
    service, runtime, _, _, broker, validation, _, _ = _build_service(db_session)
    _set_mode(db_session, runtime, 'live')

    result = _run(service, db_session, _candidate(64))

    assert result['reason'] == 'below_profile_buy_threshold'
    assert result['broker_buy_call_count'] == 0
    assert broker.buy_calls == []
    assert validation.calls == []


def test_live_stale_possible_order_never_reaches_broker(db_session):
    client = FakeKisClient(possible_age_seconds=11)
    service, runtime, _, _, broker, _, _, _ = _build_service(db_session, client=client)
    _set_mode(db_session, runtime, 'live')

    result = _run(service, db_session)

    assert result['reason'] == 'possible_order_snapshot_stale'
    assert result['broker_buy_call_count'] == 0
    assert broker.buy_calls == []


def test_live_duplicate_position_never_reaches_broker(db_session):
    client = FakeKisClient()
    client.positions = [{'symbol': '005930', 'qty': 1}]
    service, runtime, _, _, broker, _, _, _ = _build_service(db_session, client=client)
    _set_mode(db_session, runtime, 'live')

    result = _run(service, db_session)

    assert result['reason'] == 'max_positions_reached'
    assert result['broker_buy_call_count'] == 0
    assert broker.buy_calls == []


def test_readiness_reports_mode_authority_without_submitting(db_session):
    service, runtime, _, _, broker, _, _, _ = _build_service(db_session)
    _set_mode(db_session, runtime, 'test')

    result = service.readiness(db_session, now=NOW)

    assert result['buy_ready_except_score'] is True
    assert result['automation_mode'] == 'test'
    assert result['execution_authority'] == 'TEST'
    assert result['scheduler_allowed'] is True
    assert result['simulation_allowed'] is True
    assert result['broker_submit_allowed'] is False
    assert result['source_of_truth'] == 'automation_mode'
    assert broker.buy_calls == []
