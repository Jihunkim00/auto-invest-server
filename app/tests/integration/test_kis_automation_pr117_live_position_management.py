from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog
from app.main import app
from app.services.automation_profile_buy_scheduler_service import (
    AutomationProfileBuySchedulerService,
)
import app.services.profile_aware_guarded_live_auto_exit_service as guarded_exit_module
import app.routes.kis as kis_route
import app.routes.scheduler as scheduler_route
from app.tests.integration.test_kis_automation_scheduler_registration import (
    _canonical_scheduler,
)
from app.tests.integration.test_kis_automation_scheduler_replay import (
    CUSTOM_PROFILE_KEY,
    SYMBOL,
    UTC_NOW,
    build_harness,
    candidate,
)


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

    assert result['result'] == 'SELL_SUBMITTED'
    assert sell['exit_trigger'] == 'stop_loss'
    assert sell['stop_loss_pct'] == -0.02
    assert sell['take_profit_pct'] == 0.08
    assert sell['threshold_source'] == 'active_automation_profile'
    assert sell['quantity'] == 6
    assert harness.broker.sell_calls == [{'symbol': SYMBOL, 'qty': 6}]
    assert harness.broker.buy_calls == []
    assert result['profile_buy']['reason'] == 'position_management_priority_buy_skipped'
    assert sell['safety']['manual_submit_called'] is False


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
def test_persisted_kis_buy_statuses_count_as_today_new_entry(
    db_session,
    monkeypatch,
    status,
):
    harness = build_harness(db_session, monkeypatch, mode='live')
    _persist_buy_today(db_session, status=status)

    result = harness.profile_buy.readiness(db_session, now=UTC_NOW)

    assert result['max_new_entries_per_day'] == 1
    assert result['new_entries_used'] == 1
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
