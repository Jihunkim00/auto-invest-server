from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, PositionLifecycle, TradeRunLog
from app.main import app
from app.services.automation_profile_buy_scheduler_service import (
    AutomationProfileBuySchedulerService,
)
from app.services.automation_profile_service import AutomationProfileService
import app.services.profile_aware_guarded_live_auto_exit_service as guarded_exit_module
import app.routes.kis as kis_route
import app.routes.scheduler as scheduler_route
from app.tests.integration.test_kis_automation_scheduler_registration import (
    _canonical_scheduler,
)
from app.tests.integration.test_kis_automation_scheduler_replay import (
    CUSTOM_PROFILE_KEY,
    FakeKisClient,
    SYMBOL,
    UTC_NOW,
    build_harness,
    candidate,
)


pytestmark = pytest.mark.usefixtures('fake_kis_admin_credentials')


def _canonical_position_harness(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    *,
    current_price: float,
    quantity: int = 6,
    market_open: bool = True,
):
    harness = build_harness(
        db_session,
        monkeypatch,
        mode='live',
        candidates=[candidate(price=current_price)],
        market_open=market_open,
    )
    monkeypatch.setattr(
        guarded_exit_module,
        'MarketSessionService',
        lambda: harness.market_sessions,
    )
    profile = harness.profiles.get(db_session, CUSTOM_PROFILE_KEY)
    settings = json.loads(profile.settings_json or '{}')
    settings.setdefault('exit', {}).update(
        {
            'stop_loss_enabled': True,
            'stop_loss_pct': 2.0,
            'take_profit_enabled': True,
            'take_profit_pct': 8.0,
        }
    )
    profile.settings_json = json.dumps(settings)
    profile.stop_loss_pct = -0.02
    profile.take_profit_pct = 0.08
    db_session.commit()
    harness.runtime.settings = SimpleNamespace(
        kis_enabled=True,
        kis_real_order_enabled=True,
    )
    harness.client.positions = [
        {
            'symbol': SYMBOL,
            'qty': quantity,
            'current_price': current_price,
            'avg_entry_price': 80000.0,
            'cost_basis': 80000.0 * quantity,
        }
    ]
    return harness, _canonical_scheduler(harness, monkeypatch)


def test_canonical_stop_loss_sells_current_broker_quantity_and_skips_buy(
    db_session,
    monkeypatch,
):
    harness, scheduler = _canonical_position_harness(
        db_session,
        monkeypatch,
        current_price=78320.0,
    )

    result = scheduler.run_once(slot='09:10', now=UTC_NOW)
    sell = result['position_management']['sell_result']

    assert result['result'] == 'SELL_SUBMITTED', result
    assert sell['exit_trigger'] == 'stop_loss'
    assert sell['stop_loss_pct'] == -0.02
    assert sell['take_profit_pct'] == 0.08
    assert sell['threshold_source'] == 'active_automation_profile'
    assert sell['quantity'] == 6
    assert harness.broker.sell_calls == [{'symbol': SYMBOL, 'qty': 6}]
    assert harness.broker.buy_calls == []
    assert result['profile_buy']['reason'] == 'position_management_priority_buy_skipped'
    assert sell['safety']['manual_submit_called'] is False


@pytest.mark.parametrize(('failure', 'block_reason'), [
    (None, None),
    ('positions', 'position_data_unavailable'),
    ('credentials', 'account_scope_mismatch'),
    ('environment', 'account_scope_mismatch'),
    ('mode', 'automation_mode_not_live'),
    ('kill_switch', 'kill_switch_enabled'),
    ('dry_run', 'dry_run_enabled'),
])
def test_admin_profile_stop_loss_monitor_uses_legacy_order_scope(
    db_session, monkeypatch, failure, block_reason,
):
    from app.brokers.base import KisApiError
    from app.routes.history import _serialize_run
    from app.services import automation_scheduler_service
    from app.services.kis_order_validation_service import KisOrderValidationService

    now = datetime(2026, 11, 23, 4, 0, tzinfo=UTC)
    symbol = '036460'
    harness, scheduler = _canonical_position_harness(db_session, monkeypatch, current_price=35250)
    harness.runtime.update_settings(db_session, {'scheduler_enabled': True})
    harness.clock.current = now
    harness.client.candidates = [candidate(symbol=symbol, price=35250)]
    harness.client.positions[0].update(
        symbol=symbol, avg_entry_price=38350, cost_basis=38350 * 6,
    )
    profile = harness.profiles.get(db_session, CUSTOM_PROFILE_KEY)
    profile.id = 5
    profile.owner_user_id = 1
    position = PositionLifecycle(
        id=5, owner_user_id=None, entry_order_id=-1, symbol=symbol,
        entry_price=38350, cost_basis=38350 * 6, quantity=6, status='open',
        opened_at=now - timedelta(days=3), stop_loss_threshold_pct=2.0,
        take_profit_threshold_pct=8.0,
    )
    db_session.add(position)
    if failure is None:
        db_session.add(OrderLog(
            id=97, broker='kis', market='KR', symbol=symbol, side='sell',
            order_type='market', qty=6, owner_user_id=1, profile_id=5,
            profile_key=CUSTOM_PROFILE_KEY,
            internal_status=InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value,
            error_message='account_scope_mismatch', created_at=now - timedelta(minutes=30),
        ))
    db_session.commit()
    monkeypatch.setattr(automation_scheduler_service, 'KisClient', lambda *_: harness.client)

    # Inject a read failure or a mode change after the initial live check.
    class ValidationFakeKisClient(FakeKisClient):
        def list_positions(self):
            if failure == 'positions':
                raise KisApiError('fake KIS balance unavailable')
            if failure == 'mode':
                harness.runtime.update_settings(db_session, {'automation_mode': 'test'})
            return super().list_positions()

        def build_domestic_order_payload(self, **kwargs):
            return {'CANO': self.settings.kis_account_no}

        def domestic_cash_order_tr_id(self, side):
            return 'fake-order-tr'

    validation_client = ValidationFakeKisClient(harness.clock, harness.client.candidates)
    validation_client.auth_manager = SimpleNamespace(require_configured=lambda: None)
    validation_client.positions = harness.client.positions
    harness.profile_buy.validation_service = KisOrderValidationService(
        validation_client, session_service=harness.market_sessions,
    )
    if failure in {'credentials', 'environment'}:
        override = {'kis_app_secret': 'fake-wrong-secret'} if failure == 'credentials' else {'kis_env': 'paper'}
        harness.client.settings = harness.client.settings.model_copy(update=override)
    if failure in {'kill_switch', 'dry_run'}:
        def jit_open_orders(db):
            harness.runtime.update_settings(db, {failure: True})
            return harness.client.list_open_orders()

        harness.profile_buy.execution_core.open_orders_loader = jit_open_orders

    result = scheduler._run_position_exit_monitor_once(now)
    assert result['status'] == 'checked', result.get('reason')
    item = result['items'][0]
    assert item['lifecycle_id'] == 5
    assert item['strategy_action'] == 'SELL_READY'
    run = db_session.get(TradeRunLog, item['run']['run_id'])
    history = _serialize_run(run)
    assert history['result'] == 'sell_ready'
    assert history['reason'] == 'stop_loss_triggered'
    assert history['execution_action'] == item['execution_action']
    assert history['execution_reason'] == item['execution_reason']
    exit_service = scheduler._profile_guarded_live_auto_exit_service(db_session)
    replay = exit_service.run_scheduler_once(db_session, scheduler_slot=item['scheduler_slot'], symbol=symbol, now=now)
    assert replay['safety']['idempotent_replay'] is True
    assert harness.client.external_kis_submit_count == validation_client.external_kis_submit_count == 0
    position = db_session.get(PositionLifecycle, 5)
    if failure:
        assert history['execution_action'] == 'BLOCKED'
        assert history['execution_reason'] == block_reason
        assert history['broker_submit_called'] is history['real_order_submitted'] is False
        assert harness.broker.sell_calls == []
        assert position.status == 'open'
    if failure == 'positions':
        assert db_session.query(OrderLog).count() == 0
    elif failure:
        order = db_session.query(OrderLog).one()
        assert order.owner_user_id == (1 if block_reason == 'account_scope_mismatch' else None)
        assert order.internal_status == InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value
        assert order.broker_order_id is order.submitted_at is order.filled_at is None
        assert not order.filled_qty
    else:
        assert item['execution_action'] == 'SUBMITTED', item['execution_reason']
        order = db_session.query(OrderLog).filter(OrderLog.id != 97).one()
        assert order.owner_user_id is position.owner_user_id is None
        assert (order.profile_id, order.profile_key) == (5, CUSTOM_PROFILE_KEY)
        assert json.loads(order.request_payload)['profile_owner_user_id'] == 1
        assert replay['owner_user_id'] == 1
        assert order.internal_status == InternalOrderStatus.FILLED.value
        assert order.filled_qty == 6
        assert harness.sync.calls == [order.id]
        assert harness.broker.sell_calls == [{'symbol': symbol, 'qty': 6}]
        old_order = db_session.get(OrderLog, 97)
        assert old_order.owner_user_id == 1
        assert old_order.internal_status == InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value
        assert old_order.broker_order_id is old_order.submitted_at is None


def test_canonical_take_profit_uses_eight_percent_and_full_exit(
    db_session,
    monkeypatch,
):
    harness, scheduler = _canonical_position_harness(
        db_session,
        monkeypatch,
        current_price=86480.0,
    )

    result = scheduler.run_once(slot='09:10', now=UTC_NOW)
    sell = result['position_management']['sell_result']

    assert result['result'] == 'SELL_SUBMITTED'
    assert sell['exit_trigger'] == 'take_profit'
    assert sell['take_profit_pct'] == 0.08
    assert sell['quantity'] == 6
    assert sell['submitted_notional_krw'] == 518880.0
    assert len(harness.broker.sell_calls) == 1
    assert harness.broker.buy_calls == []


def test_canonical_hold_has_no_broker_submit_and_no_buy_same_tick(
    db_session,
    monkeypatch,
):
    harness, scheduler = _canonical_position_harness(
        db_session,
        monkeypatch,
        current_price=78480.0,
    )

    result = scheduler.run_once(slot='09:10', now=UTC_NOW)
    sell = result['position_management']['sell_result']

    assert result['result'] == 'HOLD'
    assert sell['block_reason'] == 'no_exit_trigger'
    assert sell['submitted'] is False
    assert harness.broker.sell_calls == []
    assert harness.broker.buy_calls == []
    assert sell['safety']['validation_called'] is False


@pytest.mark.parametrize(
    'change, expected_reason',
    [
        ({'dry_run': True}, 'dry_run_enabled'),
        ({'kill_switch': True}, 'kill_switch_enabled'),
    ],
)
def test_canonical_live_sell_respects_runtime_kill_and_dry_run_gates(
    db_session,
    monkeypatch,
    change,
    expected_reason,
):
    harness, scheduler = _canonical_position_harness(
        db_session,
        monkeypatch,
        current_price=78320.0,
    )
    harness.runtime.update_settings(db_session, change)

    result = scheduler.run_once(slot='09:10', now=UTC_NOW)
    sell = result['position_management']['sell_result']

    assert result['result'] == 'blocked'
    assert sell['block_reason'] == expected_reason
    assert sell['submitted'] is False
    assert harness.broker.sell_calls == []
    assert harness.broker.buy_calls == []


def test_canonical_live_sell_respects_market_session_gate(db_session, monkeypatch):
    harness, scheduler = _canonical_position_harness(
        db_session,
        monkeypatch,
        current_price=78320.0,
        market_open=False,
    )

    result = scheduler.run_once(slot='09:10', now=UTC_NOW)
    sell = result['position_management']['sell_result']

    assert result['result'] == 'blocked'
    assert sell['block_reason'] == 'market_session_closed'
    assert harness.broker.sell_calls == []
    assert harness.broker.buy_calls == []


def test_canonical_sell_request_is_idempotent_per_profile_slot(db_session, monkeypatch):
    harness, scheduler = _canonical_position_harness(
        db_session,
        monkeypatch,
        current_price=78320.0,
    )

    first = scheduler.run_once(slot='09:10', now=UTC_NOW)
    scheduler._slot_runs.clear()
    second = scheduler.run_once(slot='09:10', now=UTC_NOW)

    assert first['result'] == 'SELL_SUBMITTED'
    assert second['position_management']['sell_result']['safety']['idempotent_replay'] is True
    assert len(harness.broker.sell_calls) == 1
    assert (
        db_session.query(OrderLog)
        .filter(OrderLog.side == 'sell')
        .count()
        == 1
    )


def test_canonical_daily_sell_cap_is_separate_from_buy_orders(db_session, monkeypatch):
    harness, scheduler = _canonical_position_harness(
        db_session,
        monkeypatch,
        current_price=78320.0,
    )
    db_session.add(
        OrderLog(
            broker='kis',
            market='KR',
            symbol='000000',
            side='buy',
            order_type='market',
            qty=1,
            requested_qty=1,
            internal_status='FILLED',
            created_at=datetime(2026, 8, 25, 0, 0),
        )
    )
    db_session.commit()

    first = scheduler.run_once(slot='09:10', now=UTC_NOW)
    sell_order = (
        db_session.query(OrderLog)
        .filter(OrderLog.side == 'sell')
        .one()
    )
    sell_order.created_at = datetime(2026, 8, 25, 0, 10)
    db_session.commit()
    scheduler._slot_runs.clear()
    second = scheduler.run_once(slot='09:30', now=UTC_NOW)

    assert first['result'] == 'SELL_SUBMITTED'
    assert second['result'] == 'blocked'
    assert second['position_management']['sell_result']['block_reason'] == (
        'daily_auto_sell_limit_reached'
    )
    assert len(harness.broker.sell_calls) == 1


def test_canonical_scheduler_ignores_legacy_kis_readiness_flags_for_buy(
    db_session,
    monkeypatch,
):
    harness = build_harness(
        db_session,
        monkeypatch,
        mode='live',
        candidates=[candidate(score=70.0)],
    )
    harness.runtime.update_settings(
        db_session,
        {
            'scheduler_enabled': False,
            'kis_scheduler_enabled': False,
            'kis_scheduler_live_enabled': False,
            'kis_scheduler_allow_real_orders': False,
            'kis_scheduler_configured_allow_real_orders': False,
            'kis_scheduler_buy_enabled': False,
            'kis_scheduler_sell_enabled': False,
            'kis_scheduler_allow_limited_auto_buy': False,
            'kis_scheduler_allow_limited_auto_sell': False,
        },
    )
    scheduler = _canonical_scheduler(harness, monkeypatch)

    result = scheduler.run_once(slot='09:10', now=UTC_NOW)

    assert result['result'] == 'LIVE_READY'
    assert result['execution_authority'] == 'LIVE'
    assert result['profile_buy']['status'] == 'filled'
    assert harness.broker.buy_calls == [{'symbol': SYMBOL, 'qty': 1}]
    gate = result['profile_buy']['live_order_gate']
    assert gate['source_of_truth'] == 'automation_mode'
    assert 'kis_scheduler_enabled' in gate['legacy_flags_ignored']
    assert 'kis_scheduler_allow_real_orders' in gate['legacy_flags_ignored']


def test_canonical_scheduler_ignores_legacy_kis_readiness_flags_for_sell(
    db_session,
    monkeypatch,
):
    harness, scheduler = _canonical_position_harness(
        db_session,
        monkeypatch,
        current_price=78320.0,
    )
    harness.runtime.update_settings(
        db_session,
        {
            'scheduler_enabled': False,
            'kis_scheduler_enabled': False,
            'kis_scheduler_live_enabled': False,
            'kis_scheduler_allow_real_orders': False,
            'kis_scheduler_configured_allow_real_orders': False,
            'kis_scheduler_buy_enabled': False,
            'kis_scheduler_sell_enabled': False,
            'kis_scheduler_allow_limited_auto_buy': False,
            'kis_scheduler_allow_limited_auto_sell': False,
        },
    )

    result = scheduler.run_once(slot='09:10', now=UTC_NOW)
    sell = result['position_management']['sell_result']

    assert result['result'] == 'SELL_SUBMITTED'
    assert sell['exit_trigger'] == 'stop_loss'
    assert sell['quantity'] == 6
    assert harness.broker.sell_calls == [{'symbol': SYMBOL, 'qty': 6}]
    assert harness.broker.buy_calls == []


def test_scheduler_status_exposes_canonical_authority_over_legacy_readiness(
    db_session,
    monkeypatch,
):
    harness = build_harness(db_session, monkeypatch, mode='live')
    scheduler = _canonical_scheduler(harness, monkeypatch)
    settings = SimpleNamespace(kis_enabled=True, kis_real_order_enabled=True)
    harness.runtime.settings = settings
    monkeypatch.setattr(scheduler_route, 'scheduler_service', scheduler)
    monkeypatch.setattr(scheduler_route, 'get_settings', lambda: settings)
    monkeypatch.setattr(
        'app.services.runtime_setting_service.get_settings',
        lambda: settings,
    )

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        body = TestClient(app).get('/scheduler/status').json()
    finally:
        app.dependency_overrides.clear()

    assert body['canonical_scheduler_active'] is True
    assert body['canonical_scheduler']['authority'] == 'AutomationSchedulerService'
    assert body['current_operation_mode'] == 'live'
    assert body['legacy_current_operation_mode'] == 'manual_live_trading'
    assert body['display_mode_label'] == 'Canonical LIVE Automation'
    assert body['canonical_scheduler']['live_order_submission_enabled'] is True
    assert body['KR']['enabled_for_scheduler'] is True
    assert body['KR']['enabled_for_scheduler_block_reasons'] == []
    assert body['KR']['preview_only'] is False
    assert body['KR']['real_order_scheduler_enabled'] is True
    assert body['KR']['legacy_readiness_diagnostic_only'] is True
    assert body['KR']['legacy_enabled_for_scheduler'] is False
    assert 'kis_scheduler_disabled' in body['KR'][
        'legacy_enabled_for_scheduler_block_reasons'
    ]
    assert 'scheduler_real_orders_disabled' in body['canonical_scheduler'][
        'legacy_kis_scheduler_flags_ignored'
    ]


def _set_profile_schedule(
    harness,
    db_session,
    *,
    analysis_times=('10:30', '11:30', '13:30'),
    cutoff='14:00',
    take_profit=8.0,
):
    profile = harness.profiles.get(db_session, CUSTOM_PROFILE_KEY)
    settings = json.loads(profile.settings_json or '{}')
    settings.setdefault('entry', {}).update(
        {
            'analysis_times': list(analysis_times),
            'no_new_entry_after': cutoff,
            'max_new_entries_per_day': 1,
        }
    )
    settings.setdefault('exit', {}).update(
        {
            'stop_loss_pct': 2.0,
            'take_profit_pct': take_profit,
        }
    )
    profile.settings_json = json.dumps(settings)
    profile.stop_loss_pct = -0.02
    profile.take_profit_pct = take_profit / 100.0
    db_session.commit()


def test_active_profile_thresholds_are_used_by_read_only_kis_position_manage(
    db_session,
    monkeypatch,
):
    harness = build_harness(db_session, monkeypatch, mode='live')
    _set_profile_schedule(harness, db_session, take_profit=8.0)
    settings = SimpleNamespace(kis_enabled=True, kis_real_order_enabled=True)
    harness.client.settings = settings
    harness.client.positions = [
        {
            'symbol': '316140',
            'qty': 1,
            'current_price': 100.0,
            'avg_entry_price': 100.0,
            'cost_basis': 100.0,
        }
    ]
    monkeypatch.setattr(kis_route, '_client', lambda _db: harness.client)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).get('/kis/positions/manage')
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    item = body['positions'][0]
    assert body['read_only'] is True
    assert body['profile_stop_loss_pct'] == 2.0
    assert body['profile_take_profit_pct'] == 8.0
    assert body['threshold_source'] == 'active_automation_profile'
    assert item['profile_stop_loss_pct'] == 2.0
    assert item['profile_take_profit_pct'] == 8.0
    assert item['threshold_source'] == 'active_automation_profile'
    assert item['pl_diagnostics']['stop_loss_threshold_pct'] == 2.0
    assert item['pl_diagnostics']['take_profit_threshold_pct'] == 8.0
    assert any(
        'canonical AutomationSchedulerService owns LIVE exit execution' in note
        for note in item['gating_notes']
    )


def test_legacy_default_take_profit_cannot_override_active_profile_take_profit(
    db_session,
    monkeypatch,
):
    harness = build_harness(db_session, monkeypatch, mode='live')
    _set_profile_schedule(harness, db_session, take_profit=8.0)
    settings = SimpleNamespace(kis_enabled=True, kis_real_order_enabled=True)
    harness.client.settings = settings
    harness.client.positions = [
        {
            'symbol': '316140',
            'qty': 1,
            'current_price': 102.5,
            'avg_entry_price': 100.0,
            'cost_basis': 100.0,
        }
    ]
    monkeypatch.setattr(kis_route, '_client', lambda _db: harness.client)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        body = TestClient(app).get('/kis/positions/manage').json()
    finally:
        app.dependency_overrides.clear()

    item = body['positions'][0]
    assert item['take_profit_triggered'] is False
    assert item['pl_diagnostics']['take_profit_threshold_pct'] == 8.0
    assert item['pl_diagnostics']['take_profit_threshold_pct'] not in {2.0, 3.0}


def test_canonical_profile_schedule_is_effective_kr_schedule_and_legacy_is_diagnostic(
    db_session,
    monkeypatch,
):
    harness = build_harness(db_session, monkeypatch, mode='live')
    original_schedule_lookup = AutomationProfileService.selected_profile_schedule

    def selected_schedule_at_replay_time(self, db, *, now=None):
        return original_schedule_lookup(
            self,
            db,
            now=UTC_NOW if now is None else now,
        )

    monkeypatch.setattr(
        AutomationProfileService,
        'selected_profile_schedule',
        selected_schedule_at_replay_time,
    )
    _set_profile_schedule(harness, db_session)
    settings = SimpleNamespace(kis_enabled=True, kis_real_order_enabled=True)
    harness.runtime.settings = settings
    scheduler = _canonical_scheduler(harness, monkeypatch)
    monkeypatch.setattr(scheduler_route, 'scheduler_service', scheduler)
    monkeypatch.setattr(scheduler_route, 'get_settings', lambda: settings)
    monkeypatch.setattr(
        'app.services.runtime_setting_service.get_settings',
        lambda: settings,
    )

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        body = TestClient(app).get('/scheduler/status').json()
    finally:
        app.dependency_overrides.clear()

    assert body['canonical_scheduler_active'] is True
    assert body['profile_analysis_times'] == ['10:30', '11:30', '13:30']
    assert body['effective_profile_analysis_times'] == [
        '10:30',
        '11:30',
        '13:30',
    ]
    assert body['profile_no_new_entry_after'] == '14:00'
    assert body['KR']['slots'] == ['10:30', '11:30', '13:30']
    assert body['KR']['no_new_entry_after'] == '14:00'
    assert body['KR']['next_slot_name'] == 'automation_profile'
    assert body['display_next_run'].startswith('automation_profile ')
    legacy = body['legacy_kis_scheduler_state']['schedule']
    assert legacy['no_new_entry_after'] == '14:50'
    assert any('09:05' in str(slot) for slot in legacy['slots'])


def _persist_buy_today(db_session, *, status=InternalOrderStatus.FILLED.value):
    order = OrderLog(
        broker='kis',
        market='KR',
        symbol='316140',
        side='buy',
        order_type='market',
        qty=1,
        requested_qty=1,
        internal_status=status,
        submitted_at=UTC_NOW,
        kis_odno='ODNO-316140',
    )
    db_session.add(order)
    db_session.commit()
    return order


@pytest.mark.parametrize(
    'status',
    [
        InternalOrderStatus.FILLED.value,
        InternalOrderStatus.UNKNOWN_STALE.value,
        InternalOrderStatus.SYNC_FAILED.value,
    ],
)
def test_persisted_kis_buy_statuses_reserve_today_entry_capacity(
    db_session,
    monkeypatch,
    status,
):
    harness = build_harness(db_session, monkeypatch, mode='live')
    _persist_buy_today(db_session, status=status)

    result = harness.profile_buy.readiness(db_session, now=UTC_NOW)

    assert result['max_new_entries_per_day'] == 1
    confirmed = int(status == InternalOrderStatus.FILLED.value)
    assert result['new_entries_used'] == confirmed
    assert result['unresolved_entry_count'] == 1 - confirmed
    assert result['new_entries_remaining'] == 0


def _recreated_profile_buy(harness):
    return AutomationProfileBuySchedulerService(
        client=harness.client,
        broker=harness.broker,
        validation_service=harness.validation,
        order_sync_service=harness.sync,
        runtime_settings=harness.runtime,
        strategy_profiles=harness.profiles,
        target_risk_service=harness.profile_buy.target_risk_service,
        positions_loader=lambda _db: harness.client.list_positions(),
        balance_loader=lambda _db: harness.client.get_account_balance(),
        open_orders_loader=lambda _db: harness.client.list_open_orders(),
        execution_core=harness.profile_buy.execution_core,
    )


def test_recreated_profile_scheduler_reads_persisted_entry_count(
    db_session,
    monkeypatch,
):
    harness = build_harness(db_session, monkeypatch, mode='live')
    _persist_buy_today(db_session)
    recreated = _recreated_profile_buy(harness)

    result = recreated.readiness(db_session, now=UTC_NOW)

    assert result['new_entries_used'] == 1
    assert result['new_entries_remaining'] == 0


def test_sell_order_does_not_consume_new_entry_limit(
    db_session,
    monkeypatch,
):
    harness = build_harness(db_session, monkeypatch, mode='live')
    _persist_buy_today(db_session)
    db_session.add(
        OrderLog(
            broker='kis',
            market='KR',
            symbol='316140',
            side='sell',
            order_type='market',
            qty=1,
            requested_qty=1,
            internal_status=InternalOrderStatus.FILLED.value,
            submitted_at=UTC_NOW + timedelta(minutes=1),
        )
    )
    db_session.commit()

    result = harness.profile_buy.readiness(db_session, now=UTC_NOW)

    assert result['new_entries_used'] == 1
    assert result['new_entries_remaining'] == 0


def test_sold_same_day_position_still_blocks_second_profile_buy(
    db_session,
    monkeypatch,
):
    harness = build_harness(db_session, monkeypatch, mode='live')
    _set_profile_schedule(
        harness,
        db_session,
        analysis_times=('09:10', '11:30'),
    )
    first = harness.profile_buy.run_once(
        db_session,
        [candidate(score=70.0)],
        scheduler_slot='09:10',
        now=UTC_NOW,
        trusted_scheduler_authority=True,
    )
    assert first['status'] == 'filled'
    db_session.add(
        OrderLog(
            broker='kis',
            market='KR',
            symbol=SYMBOL,
            side='sell',
            order_type='market',
            qty=1,
            requested_qty=1,
            internal_status=InternalOrderStatus.FILLED.value,
            submitted_at=UTC_NOW + timedelta(minutes=2),
        )
    )
    db_session.commit()
    harness.client.positions = []

    second = harness.profile_buy.run_once(
        db_session,
        [candidate(score=70.0)],
        scheduler_slot='11:30',
        now=UTC_NOW + timedelta(hours=2, minutes=20),
        trusted_scheduler_authority=True,
    )

    assert second['reason'] == 'daily_new_entry_limit_reached'
    assert second['new_entries_used'] == 1
    assert second['new_entries_remaining'] == 0
    assert len(harness.broker.buy_calls) == 1


def test_next_kst_trading_day_resets_persisted_profile_entry_count(
    db_session,
    monkeypatch,
):
    harness = build_harness(db_session, monkeypatch, mode='live')
    _persist_buy_today(db_session)
    next_kst_day = UTC_NOW + timedelta(days=1)

    result = harness.profile_buy.readiness(db_session, now=next_kst_day)

    assert result['entry_trade_date_kst'] == '2026-08-26'
    assert result['new_entries_used'] == 0
    assert result['new_entries_remaining'] == 1
