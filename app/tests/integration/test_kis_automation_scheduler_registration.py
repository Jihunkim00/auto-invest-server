from __future__ import annotations

import json
import threading
from datetime import UTC, datetime

import pytest

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, TradeRunLog
from app.services.scheduler_service import SchedulerService
from app.services.profile_aware_dry_run_auto_buy_service import CANONICAL_MODE
from app.services.automation_scheduler_service import (
    CANONICAL_JOB_ID,
    CANONICAL_STAGES,
    CANONICAL_TRIGGER_SOURCE,
    AutomationSchedulerService,
)
from app.tests.integration.test_kis_automation_scheduler_replay import (
    CUSTOM_PROFILE_KEY,
    SYMBOL,
    UTC_NOW,
    build_harness,
    candidate,
)
import app.services.automation_scheduler_service as automation_scheduler_module


def _canonical_scheduler(harness, monkeypatch):
    scheduler = AutomationSchedulerService()
    scheduler.runtime_settings = harness.runtime
    scheduler.automation_profiles = harness.profiles
    scheduler.profile_aware_dry_run_auto_buy_service = (
        harness.strategy_scheduler.dry_run_service
    )
    scheduler.automation_profile_buy_scheduler_service = harness.profile_buy
    monkeypatch.setattr(
        automation_scheduler_module,
        'SessionLocal',
        lambda: harness.db,
    )
    return scheduler


def test_live_all_gpt_failures_block_before_profile_buy_or_broker_submit(
    db_session,
    monkeypatch,
):
    failed = []
    for symbol, score in (("A", 72.0), ("B", 70.0), ("C", 68.0)):
        item = candidate(symbol=symbol, score=score)
        item.update(
            {
                "ai_buy_score": None,
                "final_buy_score": score,
                "final_score": score,
                "gpt_analysis_status": "failed",
                "gpt_used": False,
            }
        )
        failed.append(item)

    harness = build_harness(
        db_session,
        monkeypatch,
        mode="live",
        candidates=failed,
    )
    scheduler = _canonical_scheduler(harness, monkeypatch)

    result = scheduler.run_once(slot="09:10", now=UTC_NOW)
    dry_result = result["dry_run"]["dry_run_result"]

    assert result["result"] == "blocked"
    assert result["reason"] == "no_gpt_completed_execution_candidate"
    assert dry_result["execution_candidate_count"] == 0
    assert dry_result["execution_candidates"] == []
    assert result["profile_buy"]["broker_submit_called"] is False
    assert harness.validation.calls == []
    assert harness.broker.buy_calls == []
    assert harness.client.external_kis_submit_count == 0


def test_startup_registers_only_the_canonical_production_scheduler(
    monkeypatch,
):
    legacy_scheduler = SchedulerService()
    assert legacy_scheduler.production_trading_jobs() == []
    assert legacy_scheduler.start() is False
    assert legacy_scheduler.is_running() is False

    canonical_scheduler = AutomationSchedulerService()
    loop_started = threading.Event()

    def fake_loop() -> None:
        loop_started.set()
        canonical_scheduler._stop_event.wait(1.0)

    monkeypatch.setattr(canonical_scheduler, '_run_loop', fake_loop)

    assert canonical_scheduler.start() is True
    assert loop_started.wait(1.0)
    try:
        jobs = canonical_scheduler.production_trading_jobs()
        assert len(jobs) == 1
        assert jobs[0]['job_id'] == CANONICAL_JOB_ID
        assert jobs[0]['authority'] == 'AutomationSchedulerService'
        assert jobs[0]['provider'] == 'kis'
        assert jobs[0]['market'] == 'KR'
        assert jobs[0]['stages'] == CANONICAL_STAGES
        assert (
            canonical_scheduler.runtime_status()['production_trading_job_count']
            == 1
        )
    finally:
        canonical_scheduler.stop()


def test_0930_has_one_canonical_run_and_no_legacy_automatic_runs(
    db_session,
    monkeypatch,
):
    run_at = datetime(2026, 9, 1, 0, 30, tzinfo=UTC)
    harness = build_harness(db_session, monkeypatch, now=run_at)
    profile = harness.profiles.get(db_session, CUSTOM_PROFILE_KEY)
    settings = json.loads(profile.settings_json or '{}')
    settings['entry']['analysis_times'] = ['09:30']
    profile.settings_json = json.dumps(settings)
    db_session.commit()

    canonical_scheduler = _canonical_scheduler(harness, monkeypatch)

    first = canonical_scheduler.run_once(slot='09:30', now=run_at)
    second = canonical_scheduler.run_once(slot='09:30', now=run_at)

    assert first['scheduler'] == 'AutomationSchedulerService'
    assert first['slot'] == '09:30'
    assert first['dry_run']['profile_key'] == CUSTOM_PROFILE_KEY
    assert first['dry_run']['scheduled_slot_key'] == (
        f'{CUSTOM_PROFILE_KEY}:2026-09-01:09:30'
    )
    assert second['reason'] == 'scheduler_slot_already_run'
    assert len(harness.broker.buy_calls) == 1
    assert harness.client.external_kis_submit_count == 0

    rows = db_session.query(TradeRunLog).all()
    sources = {str(row.trigger_source) for row in rows}
    modes = {str(row.mode) for row in rows}
    assert sum(
        row.trigger_source == CANONICAL_TRIGGER_SOURCE
        for row in rows
    ) == 1
    assert sources <= {
        'automation_scheduler',
        'automation_profile_scheduler',
    }
    assert modes <= {CANONICAL_MODE, 'automation_profile_scheduler_buy'}

    # The compatibility callback remains explicitly callable, but it is not
    # part of production startup registration.
    compatibility_result = harness.scheduler._run_strategy_auto_buy_dry_run_scheduled_once(
        'strategy_auto_buy_dry_run_open_phase',
        now=run_at,
    )
    assert compatibility_result is not None


def test_live_score_below_profile_threshold_is_blocked_without_submit(
    db_session, monkeypatch
):
    harness = build_harness(
        db_session,
        monkeypatch,
        mode='live',
        candidates=[candidate(score=62.5)],
    )
    scheduler = _canonical_scheduler(harness, monkeypatch)

    result = scheduler.run_once(slot='09:10', now=UTC_NOW)

    assert result['result'] == 'blocked'
    assert result['reason'] == 'below_profile_buy_threshold'
    assert result['effective_min_entry_score'] == 65.0
    assert result['dry_run']['final_buy_score'] == 62.5
    assert len(harness.broker.buy_calls) == 0
    assert json.loads(
        db_session.query(TradeRunLog)
        .filter(TradeRunLog.trigger_source == CANONICAL_TRIGGER_SOURCE)
        .one()
        .response_payload
    )['effective_min_entry_score'] == 65.0


def test_live_score_pass_is_canonical_live_ready_without_legacy_preview_markers(
    db_session, monkeypatch
):
    harness = build_harness(
        db_session,
        monkeypatch,
        mode='live',
        candidates=[candidate(score=70.0)],
    )
    scheduler = _canonical_scheduler(harness, monkeypatch)

    result = scheduler.run_once(slot='09:10', now=UTC_NOW)
    dry_run = result['dry_run']

    assert result['result'] == 'LIVE_READY'
    assert result['execution_mode'] == 'live'
    assert result['execution_authority'] == 'LIVE'
    assert result['submission_eligible'] is True
    assert dry_run['dry_run_only'] is False
    assert dry_run['preview_only'] is False
    assert 'dry_run_only' not in dry_run['risk_flags']
    assert 'kr_trading_disabled' not in dry_run['risk_flags']
    assert 'preview_only' not in dry_run['risk_flags']
    notes = ' '.join(dry_run['gating_notes']).lower()
    assert 'dry-run' not in notes
    assert 'preview' not in notes
    assert 'kr trading disabled' not in notes
    assert len(harness.broker.buy_calls) == 1
    assert harness.client.external_kis_submit_count == 0
    assert not any(
        str(row.internal_status).upper() == 'DRY_RUN_SIMULATED'
        for row in db_session.query(OrderLog).all()
    )


def test_paper_score_pass_is_simulated_without_submit(db_session, monkeypatch):
    harness = build_harness(
        db_session,
        monkeypatch,
        mode='paper',
        candidates=[candidate(score=70.0)],
    )
    scheduler = _canonical_scheduler(harness, monkeypatch)

    result = scheduler.run_once(slot='09:10', now=UTC_NOW)

    assert result['result'] == 'PAPER_SIMULATED'
    assert result['execution_authority'] == 'PAPER'
    assert result['submission_eligible'] is False
    assert result['dry_run']['dry_run_only'] is True
    assert len(harness.broker.buy_calls) == 0
    assert harness.client.external_kis_submit_count == 0


def test_test_score_pass_is_simulated_without_submit(db_session, monkeypatch):
    harness = build_harness(
        db_session,
        monkeypatch,
        mode='test',
        candidates=[candidate(score=70.0)],
    )
    scheduler = _canonical_scheduler(harness, monkeypatch)

    result = scheduler.run_once(slot='09:10', now=UTC_NOW)

    assert result['result'] == 'TEST_SIMULATED'
    assert result['execution_authority'] == 'TEST'
    assert result['submission_eligible'] is False
    assert result['dry_run']['dry_run_only'] is True
    assert len(harness.broker.buy_calls) == 0
    assert harness.client.external_kis_submit_count == 0


@pytest.mark.parametrize(
    'case',
    [
        'kill_switch',
        'market_closed',
        'after_no_new_entry_after',
        'insufficient_cash',
        'existing_position',
        'duplicate_open_order',
        'possible_order_missing',
        'possible_order_stale',
        'daily_trade_limit_reached',
        'kis_validation_rejected',
    ],
)
def test_live_retained_hard_gate_failure_never_submits(
    db_session, monkeypatch, case
):
    now = UTC_NOW
    if case == 'after_no_new_entry_after':
        now = datetime(2026, 8, 25, 5, 10, tzinfo=UTC)
    harness = build_harness(
        db_session,
        monkeypatch,
        mode='live',
        candidates=[candidate(score=70.0)],
        market_open=case != 'market_closed',
        now=now,
    )
    if case == 'kill_switch':
        harness.runtime.update_settings(db_session, {'kill_switch': True})
    elif case == 'insufficient_cash':
        harness.client.cash = 1000.0
    elif case == 'existing_position':
        harness.client.positions = [{'symbol': SYMBOL, 'qty': 1}]
    elif case == 'duplicate_open_order':
        harness.client.open_orders = [{'symbol': SYMBOL, 'side': 'buy', 'qty': 1}]
    elif case == 'possible_order_missing':
        harness.client.possible_order_missing = True
    elif case == 'possible_order_stale':
        harness.client.possible_order_age_seconds = 11.0
    elif case == 'daily_trade_limit_reached':
        db_session.add(
            OrderLog(
                broker='kis',
                market='KR',
                symbol='000000',
                side='buy',
                order_type='market',
                qty=1,
                requested_qty=1,
                internal_status=InternalOrderStatus.FILLED.value,
                submitted_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        db_session.commit()
    elif case == 'kis_validation_rejected':
        harness.validation.approved = False

    scheduler = _canonical_scheduler(harness, monkeypatch)
    result = scheduler.run_once(slot='09:10', now=now)

    assert result['result'] == 'blocked'
    assert result['reason']
    assert result['submission_eligible'] is False
    assert len(harness.broker.buy_calls) == 0
    assert harness.client.external_kis_submit_count == 0
