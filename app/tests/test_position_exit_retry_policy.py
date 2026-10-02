
from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import requests
from sqlalchemy.orm import sessionmaker

from app.brokers.base import KisApiError, KisAuthError, KisConfigurationError
from app.db.models import PositionExitRetryJob, StrategyLiveAutoExitAttempt, TradeRunLog
from app.services.account_snapshot_retry import retryable_kis_exit_read_error
from app.services.scheduler_service import AutomationSchedulerService
from app.services.runtime_setting_service import RuntimeSettingService
import app.services.automation_scheduler_service as scheduler_module

KST = ZoneInfo("Asia/Seoul")
PROFILE = {
    "id": 23,
    "owner_user_id": 41,
    "profile_key": "admin_kis_primary",
    "display_name": "Admin display name",
    "provider": "kis",
    "market": "KR",
    "status": "active",
    "enabled": True,
}


def _error(http_status: int) -> KisApiError:
    return KisApiError(
        "read failed",
        details={
            "http_status": http_status,
            "tr_id": "TTTC8434R",
            "path": "/uapi/domestic-stock/v1/trading/inquire-balance",
            "msg_cd": "E500",
            "appkey": "never persist this",
            "account_number": "12345678901",
        },
    )


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (_error(500), True),
        (_error(502), True),
        (_error(503), True),
        (_error(504), True),
        (requests.exceptions.Timeout("read timeout"), True),
        (requests.exceptions.ConnectionError("connection reset"), True),
        (_error(400), False),
        (_error(401), False),
        (_error(403), False),
        (_error(422), False),
        (KisAuthError("token expired"), False),
        (KisConfigurationError("invalid account config"), False),
        (RuntimeError("business validation rejected"), False),
    ],
)
def test_only_transient_read_errors_are_retryable(error, retryable):
    assert retryable_kis_exit_read_error(error) is retryable


def test_position_read_failure_persists_one_minute_retry_and_safe_profile_context(db_session):
    now = datetime(2026, 7, 30, 9, 30, tzinfo=KST)
    scheduler = AutomationSchedulerService(retry_now_provider=lambda: now)

    result = scheduler._position_snapshot_failure_result(
        db_session,
        profile=PROFILE,
        profile_id=PROFILE["id"],
        profile_key=PROFILE["profile_key"],
        scheduler_slot="09:30",
        now=now,
        error=_error(500),
    )

    job = db_session.query(PositionExitRetryJob).one()
    assert result["status"] == "retry_pending"
    assert result["position_state"] == "unknown"
    assert result["buy_execution_allowed"] is False
    assert job.status == "pending"
    assert job.retry_count == 0
    assert job.max_retries == 3
    assert scheduler._retry_datetime_to_kst(job.next_retry_at) == now + timedelta(minutes=1)
    assert job.owner_user_id == PROFILE["owner_user_id"]
    assert job.profile_id == PROFILE["id"]
    assert job.profile_key == PROFILE["profile_key"]
    assert job.symbol is None

    diagnostics = json.loads(job.diagnostics_json)
    assert diagnostics["read_operation"] == "positions"
    assert diagnostics["http_status"] == 500
    assert diagnostics["retry_index"] == 0
    assert diagnostics["max_retries"] == 3
    assert diagnostics["retry_scheduled_for"] == (now + timedelta(minutes=1)).isoformat()
    assert "appkey" not in job.diagnostics_json
    assert "12345678901" not in job.diagnostics_json

    restarted_scheduler = AutomationSchedulerService(retry_now_provider=lambda: now)
    active = restarted_scheduler._active_position_exit_retry_job(
        db_session,
        profile_id=PROFILE["id"],
        owner_user_id=PROFILE["owner_user_id"],
        profile_key=PROFILE["profile_key"],
    )
    assert active.id == job.id

    repeated = restarted_scheduler._position_snapshot_failure_result(
        db_session,
        profile=PROFILE,
        profile_id=PROFILE["id"],
        profile_key=PROFILE["profile_key"],
        scheduler_slot="09:30",
        now=now,
        error=_error(500),
    )
    assert repeated["retry"]["status"] == "pending"
    assert db_session.query(PositionExitRetryJob).count() == 1


def test_non_transient_or_post_called_exit_does_not_schedule_deferred_retry(db_session):
    now = datetime(2026, 7, 30, 9, 30, tzinfo=KST)
    scheduler = AutomationSchedulerService(retry_now_provider=lambda: now)

    rejected = scheduler._position_snapshot_failure_result(
        db_session,
        profile=PROFILE,
        profile_id=PROFILE["id"],
        profile_key=PROFILE["profile_key"],
        scheduler_slot="09:30",
        now=now,
        error=_error(401),
    )
    assert rejected["status"] == "failed"
    assert db_session.query(PositionExitRetryJob).count() == 0

    post_result = {
        "block_reason": "sell_submit_failed",
        "broker_submit_called": True,
        "safety": {
            "broker_submit_called": True,
            "read_failure": {"read_operation": "positions", "retryable": True},
        },
    }
    assert scheduler._schedule_position_exit_retry_from_result(
        db_session,
        result=post_result,
        profile=PROFILE,
        scheduler_slot="09:30",
        symbol="005930",
        now=now,
    ) is None
    assert db_session.query(PositionExitRetryJob).count() == 0


def _install_fake_retry_worker(db_session, monkeypatch, results):
    session_factory = sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    monkeypatch.setattr(scheduler_module, "SessionLocal", session_factory)

    runtime = RuntimeSettingService()
    runtime.update_settings(
        db_session,
        {
            "automation_mode": "live",
            "dry_run": False,
            "kill_switch": False,
            "automation_profile_scheduler_enabled": True,
        },
    )
    profiles = SimpleNamespace(
        selected_profile_schedule=lambda _db, now=None: {
            "status": "active",
            "profile_key": PROFILE["profile_key"],
            "profile": dict(PROFILE),
        }
    )
    monkeypatch.setattr(
        scheduler_module.AutomationExecutionAuthorityService,
        "snapshot",
        lambda self, db: {"scheduler_allowed": True, "automation_mode": "live"},
    )
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(scheduler_module, "KisClient", lambda *args, **kwargs: object())
    monkeypatch.setattr(scheduler_module, "KisAuthManager", lambda *args, **kwargs: object())
    monkeypatch.setattr(scheduler_module, "KisBroker", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        scheduler_module,
        "KisOrderValidationService",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        scheduler_module,
        "KisOrderSyncService",
        lambda *args, **kwargs: object(),
    )

    calls = []

    class FakeGuardedExitService:
        def __init__(self, *args, **kwargs):
            pass

        def run_scheduler_once(self, db, **kwargs):
            calls.append(kwargs)
            return results.pop(0)

    monkeypatch.setattr(
        scheduler_module,
        "ProfileAwareGuardedLiveAutoExitService",
        FakeGuardedExitService,
    )
    scheduler = AutomationSchedulerService(
        retry_now_provider=lambda: datetime(2026, 7, 30, 9, 31, tzinfo=KST)
    )
    scheduler.runtime_settings = runtime
    scheduler.automation_profiles = profiles
    return scheduler, calls


def _transient_retry_result():
    return {
        "status": "blocked",
        "block_reason": "positions_unavailable",
        "submitted": False,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "safety": {
            "broker_submit_called": False,
            "read_failure": {
                "read_operation": "positions",
                "http_status": 500,
                "retryable": True,
                "retry_succeeded": False,
            },
        },
    }


def _schedule_unknown_position_retry(db_session, scheduler, now):
    return scheduler._schedule_position_exit_retry(
        db_session,
        profile=PROFILE,
        profile_id=PROFILE["id"],
        profile_key=PROFILE["profile_key"],
        scheduler_slot="09:30",
        symbol="005930",
        exit_cycle_key="automation_scheduler:sell:admin_kis_primary:2026-07-30:09:30:005930",
        block_reason="positions_unavailable",
        read_failure={"read_operation": "positions", "http_status": 500, "retryable": True},
        now=now,
    )


@pytest.mark.parametrize(
    ("results", "final_status", "expected_retry_count"),
    [
        ([
            _transient_retry_result(),
            _transient_retry_result(),
            {
                "status": "submitted",
                "submitted": True,
                "real_order_submitted": True,
                "broker_submit_called": True,
                "safety": {"broker_submit_called": True},
            },
        ], "resolved_submitted", 2),
        ([
            _transient_retry_result(),
            _transient_retry_result(),
            _transient_retry_result(),
        ], "exhausted", 3),
    ],
    ids=["retry3-submits-once", "original-plus-three-retries-exhaust"],
)
def test_due_retry_job_is_durable_bounded_and_uses_one_attempt_per_minute(
    db_session,
    monkeypatch,
    results,
    final_status,
    expected_retry_count,
):
    base = datetime(2026, 7, 30, 9, 30, tzinfo=KST)
    scheduler, calls = _install_fake_retry_worker(db_session, monkeypatch, results)
    job = _schedule_unknown_position_retry(db_session, scheduler, base)
    assert job.status == "pending"
    assert db_session.query(PositionExitRetryJob).count() == 1

    too_early = scheduler._dispatch_due_position_exit_retries(
        base + timedelta(seconds=59), asynchronous=False
    )
    assert too_early == []
    assert calls == []

    restarted = AutomationSchedulerService(
        retry_now_provider=lambda: base + timedelta(minutes=1)
    )
    restarted.runtime_settings = scheduler.runtime_settings
    restarted.automation_profiles = scheduler.automation_profiles
    for retry_number in range(1, 4):
        due = base + timedelta(minutes=retry_number)
        output = restarted._dispatch_due_position_exit_retries(
            due,
            asynchronous=False,
        )
        assert len(output) == 1
        db_session.expire_all()
        current = db_session.get(PositionExitRetryJob, job.id)
        if retry_number < 3:
            assert current.status == "pending"
            assert current.retry_count == retry_number
            assert restarted._retry_datetime_to_kst(current.next_retry_at) == due + timedelta(minutes=1)
        else:
            assert current.status == final_status
            assert current.retry_count == expected_retry_count

    assert [call["retry_index"] for call in calls] == [1, 2, 3]
    assert {call["exit_cycle_key"] for call in calls} == {job.exit_cycle_key}
    assert {call["symbol"] for call in calls} == {"005930"}
    if final_status == "resolved_submitted":
        assert output[0]["broker_submit_called"] is True
        assert current.status == "resolved_submitted"
    else:
        assert output[0]["broker_submit_called"] is False
        assert current.status == "exhausted"
        assert current.last_block_reason == "positions_unavailable"
        assert restarted._active_position_exit_retry_job(
            db_session,
            profile_id=PROFILE["id"],
            owner_user_id=PROFILE["owner_user_id"],
            profile_key=PROFILE["profile_key"],
        ) is None


def test_previous_submitted_exit_cancels_due_retry_before_another_submit(db_session, monkeypatch):
    base = datetime(2026, 7, 30, 9, 30, tzinfo=KST)
    scheduler, calls = _install_fake_retry_worker(db_session, monkeypatch, [_transient_retry_result()])
    job = _schedule_unknown_position_retry(db_session, scheduler, base)
    db_session.add(
        StrategyLiveAutoExitAttempt(
            provider="kis",
            market="KR",
            exit_cycle_key=job.exit_cycle_key,
            retry_index=0,
            status="accepted",
            trigger_source="automation_scheduler",
        )
    )
    db_session.commit()

    output = scheduler._dispatch_due_position_exit_retries(
        base + timedelta(minutes=1),
        asynchronous=False,
    )

    db_session.expire_all()
    saved = db_session.get(PositionExitRetryJob, job.id)
    assert saved.status == "resolved_existing_order"
    assert output[0]["reason"] == "previous_attempt_submit_or_sync_pending"
    assert calls == []



def _canonical_scheduler_for_tick(db_session, monkeypatch, *, positions_loader, events):
    session_factory = sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    monkeypatch.setattr(scheduler_module, "SessionLocal", session_factory)
    runtime = RuntimeSettingService()
    runtime.update_settings(
        db_session,
        {
            "automation_mode": "live",
            "dry_run": False,
            "kill_switch": False,
            "automation_profile_scheduler_enabled": True,
        },
    )
    schedule = {
        "status": "active",
        "profile_key": PROFILE["profile_key"],
        "analysis_times": ["09:30"],
        "profile": {
            **PROFILE,
            "effective_settings": {
                "max_open_positions": 1,
                "entry": {"no_new_entry_after": "14:00"},
            },
        },
    }
    profiles = SimpleNamespace(
        selected_profile_schedule=lambda _db, now=None: schedule,
    )
    monkeypatch.setattr(
        scheduler_module.AutomationExecutionAuthorityService,
        "snapshot",
        lambda self, db: {
            "scheduler_allowed": True,
            "automation_mode": "live",
            "execution_authority": "LIVE",
        },
    )
    monkeypatch.setattr(
        scheduler_module,
        "MarketSessionService",
        lambda: SimpleNamespace(
            get_session_status=lambda market, now=None: {
                "market": market,
                "is_market_open": True,
                "is_entry_allowed_now": True,
            }
        ),
    )
    scheduler = AutomationSchedulerService(retry_scheduler=lambda *args, **kwargs: True)
    scheduler.runtime_settings = runtime
    scheduler.automation_profiles = profiles
    scheduler._profile_buy_scheduler_service = lambda db: SimpleNamespace(
        positions_loader=positions_loader,
    )

    position = {"symbol": "005930", "qty": 1, "avg_entry_price": 10000}

    def manage_portfolio(db, *, slot, now, account_snapshot):
        events.append(("position_management", account_snapshot["positions"]))
        return {
            "broker_positions": [position],
            "items": [{"symbol": "005930", "action": "SELL_READY"}],
        }

    scheduler._manage_portfolio_first = manage_portfolio

    class FakeGuardedExit:
        def run_scheduler_once(self, db, **kwargs):
            events.append(("guarded_sell", kwargs))
            return {
                "status": "blocked",
                "block_reason": "dry_run_enabled",
                "submitted": False,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "safety": {
                    "validation_called": False,
                    "broker_submit_called": False,
                },
            }

    scheduler._profile_guarded_live_auto_exit_service = lambda db: FakeGuardedExit()
    scheduler._run_profile_analysis = lambda *args, **kwargs: events.append(("entry_analysis", kwargs))
    return scheduler


def test_canonical_scheduler_evaluates_sell_before_any_entry_analysis(db_session, monkeypatch):
    events = []
    position = {"symbol": "005930", "qty": 1, "avg_entry_price": 10000}
    scheduler = _canonical_scheduler_for_tick(
        db_session,
        monkeypatch,
        positions_loader=lambda db: [position],
        events=events,
    )

    result = scheduler._run_automation_tick(
        "09:30",
        now=datetime(2026, 7, 30, 9, 30, tzinfo=KST),
        slot_claimed=True,
    )

    assert [event[0] for event in events] == ["position_management", "guarded_sell"]
    assert events[0][1] == [position]
    assert events[1][1]["symbol"] == "005930"
    assert result["buy_execution_allowed"] is False
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False


def test_unknown_positions_state_persists_retry_and_blocks_entry_analysis(db_session, monkeypatch):
    events = []

    def positions_unavailable(_db):
        raise _error(500)

    scheduler = _canonical_scheduler_for_tick(
        db_session,
        monkeypatch,
        positions_loader=positions_unavailable,
        events=events,
    )
    now = datetime(2026, 7, 30, 9, 30, tzinfo=KST)

    result = scheduler._run_automation_tick(
        "09:30",
        now=now,
        slot_claimed=True,
    )

    job = db_session.query(PositionExitRetryJob).one()
    assert result["status"] == "retry_pending"
    assert result["position_state"] == "unknown"
    assert result["buy_execution_allowed"] is False
    assert job.status == "pending"
    assert job.last_block_reason == "positions_unavailable"
    assert events == []


def _entry_recovery_scheduler(db_session, monkeypatch, *, slot="09:50", positions=None):
    events, deferred = [], []
    clock = [datetime(2026, 7, 30, *map(int, slot.split(":")), tzinfo=KST)]
    scheduler = _canonical_scheduler_for_tick(
        db_session, monkeypatch,
        positions_loader=lambda db: positions or [], events=events,
    )
    scheduler.retry_now_provider = lambda: clock[0]
    scheduler.retry_scheduler = lambda key, callback, **kwargs: (
        deferred.append((key, callback, kwargs)) or True
    )
    schedule = scheduler.automation_profiles.selected_profile_schedule(db_session)
    schedule["analysis_times"] = [slot]
    scheduler._manage_portfolio_first = lambda db, **kwargs: (
        events.append(("position_management", kwargs)) or
        {"broker_positions": kwargs["account_snapshot"]["positions"], "items": []}
    )
    scheduler._account_snapshot_preflight = lambda db, **kwargs: (
        events.append(("account_preflight", kwargs)) or
        {"positions": kwargs["positions_override"], "balance": {"cash": 100000}, "open_orders": []}
    )
    scheduler._run_profile_analysis = lambda db, **kwargs: (
        events.append(("entry_analysis", kwargs)) or
        {"action": "would_buy", "submission_eligible": True, "risk_decision": {"approved": True}}
    )
    def fake_buy(db, analysis, **kwargs):
        events.append(("fake_buy_safety_pipeline", kwargs))
        return {"status": "submitted", "action": "buy", "broker_submit_called": True,
                "broker_buy_call_count": 1, "real_external_kis_submit_count": 0}
    scheduler._profile_buy_scheduler_service = lambda db: SimpleNamespace(
        positions_loader=lambda db: positions or [], run_once=fake_buy,
    )
    return scheduler, events, deferred, clock


@pytest.mark.parametrize("slot", ["09:50", "13:30"])
def test_entry_slot_position_retry_fresh_empty_recovers_exactly_once(db_session, monkeypatch, slot):
    scheduler, events, deferred, clock = _entry_recovery_scheduler(
        db_session, monkeypatch, slot=slot,
    )
    job = _schedule_unknown_position_retry(db_session, scheduler, clock[0] - timedelta(minutes=1))
    result = scheduler._run_automation_tick(slot, clock[0])
    repeated = scheduler._run_automation_tick(slot, clock[0], True)

    db_session.expire_all()
    assert db_session.get(PositionExitRetryJob, job.id).status == "resolved_hold"
    assert [event[0] for event in events] == [
        "position_management", "account_preflight", "entry_analysis", "fake_buy_safety_pipeline",
    ]
    assert result["recovered_from_position_retry"] is True
    assert result["original_scheduler_slot"] == slot
    assert repeated["reason"] == "scheduler_slot_already_run"
    assert deferred == []
    log = db_session.query(TradeRunLog).filter(TradeRunLog.mode == scheduler_module.ENTRY_SLOT_RECOVERY_MODE).one()
    payload = json.loads(log.response_payload)
    assert payload["recovered_from_position_retry"] is True
    assert payload["owner_user_id"] == PROFILE["owner_user_id"]
    assert payload["profile_id"] == PROFILE["id"]


def test_entry_slot_position_retry_held_positions_manage_before_entry(db_session, monkeypatch):
    held = {"symbol": "005930", "qty": 1, "avg_entry_price": 10000}
    scheduler, events, deferred, clock = _entry_recovery_scheduler(
        db_session, monkeypatch, positions=[held],
    )
    _schedule_unknown_position_retry(db_session, scheduler, clock[0] - timedelta(minutes=1))
    result = scheduler._run_automation_tick("09:50", clock[0])
    assert [event[0] for event in events] == ["position_management", "guarded_sell"]
    assert result["buy_execution_allowed"] is False
    assert not any(event[0] == "entry_analysis" for event in events)
    assert deferred == []


@pytest.mark.parametrize("slot", ["09:50", "13:30"])
def test_entry_slot_position_retry_grace_exhaustion_logs_blocked_without_submit(db_session, monkeypatch, slot):
    scheduler, events, deferred, clock = _entry_recovery_scheduler(db_session, monkeypatch, slot=slot)
    def fail(db):
        raise _error(500)
    scheduler._positions_first = fail
    _schedule_unknown_position_retry(db_session, scheduler, clock[0] - timedelta(minutes=1))
    pending = scheduler._run_automation_tick(slot, clock[0])
    assert pending["reason"] == "position_state_refresh_pending"
    assert len(deferred) == 1
    callback = deferred[0][1]
    for seconds in (20, 40, 60, 80, 100):
        clock[0] = datetime(2026, 7, 30, *map(int, slot.split(":")), tzinfo=KST) + timedelta(seconds=seconds)
        assert callback() == 20
    clock[0] += timedelta(seconds=20)
    assert callback() is None
    db_session.expire_all()
    log = db_session.query(TradeRunLog).filter(TradeRunLog.mode == scheduler_module.ENTRY_SLOT_RECOVERY_MODE).one()
    assert log.result == "blocked"
    assert log.reason == "position_state_unavailable_after_entry_slot_grace"
    public = json.loads(log.response_payload)
    assert public["buy_execution_allowed"] is False
    assert public["broker_submit_called"] is False
    assert public["real_order_submitted"] is False
    assert public["scheduler_slot"] == slot
    assert events == []
    assert len(deferred) == 1
    assert callback() is None


@pytest.mark.parametrize("slot", ["09:50", "13:30"])
def test_original_entry_slot_catches_up_after_background_resolved_hold(db_session, monkeypatch, slot):
    scheduler, events, deferred, clock = _entry_recovery_scheduler(db_session, monkeypatch, slot=slot)
    job = _schedule_unknown_position_retry(db_session, scheduler, clock[0] - timedelta(minutes=1))
    def fail(db):
        raise _error(500)
    scheduler._positions_first = fail
    assert scheduler._run_automation_tick(slot, clock[0])["buy_execution_allowed"] is False
    assert scheduler._run_automation_tick(slot, clock[0])["reason"] == "scheduler_slot_already_run"
    assert len(deferred) == 1
    job = db_session.get(PositionExitRetryJob, job.id)
    job.status = "resolved_hold"
    job.last_block_reason = "no_exit_candidate"
    db_session.commit()
    scheduler._positions_first = lambda db: []
    clock[0] += timedelta(minutes=1)
    assert deferred[0][1]() is None
    assert deferred[0][1]() is None
    assert sum(event[0] == "entry_analysis" for event in events) == 1
    assert sum(event[0] == "fake_buy_safety_pipeline" for event in events) == 1
    buy = next(event[1] for event in events if event[0] == "fake_buy_safety_pipeline")
    assert buy["scheduler_slot"] == slot
    assert buy["allow_retry_slot_replay"] is True
    assert buy["retry_started_at"].strftime("%H:%M") == slot


@pytest.mark.parametrize("operation", ["account_snapshot", "open_orders"])
def test_non_position_exit_retry_keeps_fail_closed_entry_policy(db_session, monkeypatch, operation):
    scheduler, events, deferred, clock = _entry_recovery_scheduler(db_session, monkeypatch)
    job = _schedule_unknown_position_retry(db_session, scheduler, clock[0])
    job.diagnostics_json = json.dumps({"read_operation": operation, "retryable": True})
    db_session.commit()
    result = scheduler._run_automation_tick("09:50", clock[0])
    assert result["reason"] == "kis_exit_read_retry_pending"
    assert result["buy_execution_allowed"] is False
    assert events == []
    assert deferred == []


@pytest.mark.parametrize("status", ["running", "pending"])
def test_entry_recovery_does_not_resolve_running_or_submitted_exit(db_session, monkeypatch, status):
    scheduler, events, deferred, clock = _entry_recovery_scheduler(db_session, monkeypatch)
    job = _schedule_unknown_position_retry(db_session, scheduler, clock[0])
    if status == "running":
        job.status = "running"
        job.claimed_at = clock[0].astimezone(scheduler_module.UTC)
    else:
        db_session.add(StrategyLiveAutoExitAttempt(
            exit_cycle_key=job.exit_cycle_key,
            retry_index=1, profile_key=PROFILE["profile_key"], symbol="005930",
            status="submitted", block_reason=None, safety_flags='{"broker_submit_called":true}',
        ))
    db_session.commit()
    result = scheduler._run_automation_tick("09:50", clock[0])
    db_session.expire_all()
    assert db_session.get(PositionExitRetryJob, job.id).status == status
    assert result["buy_execution_allowed"] is False
    assert result["broker_submit_called"] is False
    assert events == []


def test_no_active_retry_normal_entry_path_is_unchanged(db_session, monkeypatch):
    scheduler, events, deferred, clock = _entry_recovery_scheduler(db_session, monkeypatch)
    result = scheduler._run_automation_tick("09:50", clock[0])
    assert result["result"] == "LIVE_READY"
    assert "recovered_from_position_retry" not in result
    assert sum(event[0] == "entry_analysis" for event in events) == 1
    assert db_session.query(TradeRunLog).count() == 0
    assert deferred == []


@pytest.mark.parametrize("slot", ["09:50", "13:30"])
@pytest.mark.parametrize("deferred_recovery", [False, True])
def test_entry_slot_recovery_replays_actual_fake_broker_safety_pipeline(
    db_session, monkeypatch, slot, deferred_recovery,
):
    from app.tests.integration.test_kis_automation_scheduler_replay import build_harness
    now = datetime(2026, 8, 25, *map(int, slot.split(":")), tzinfo=KST)
    harness = build_harness(db_session, monkeypatch, now=now, analysis_times=(slot,))
    deferred = []
    scheduler = AutomationSchedulerService(
        retry_scheduler=lambda key, callback, **kwargs: deferred.append(callback) or True,
        retry_now_provider=harness.clock.now,
    )
    scheduler.runtime_settings = harness.runtime
    scheduler.automation_profiles = harness.profiles
    scheduler.automation_profile_buy_scheduler_service = harness.profile_buy
    scheduler.profile_aware_dry_run_auto_buy_service = harness.strategy_scheduler.dry_run_service
    monkeypatch.setattr(
        scheduler_module, "SessionLocal",
        sessionmaker(bind=db_session.get_bind(), expire_on_commit=False),
    )
    monkeypatch.setattr(scheduler_module, "MarketSessionService", lambda: harness.market_sessions)
    profile = harness.profiles.selected_profile_schedule(db_session, now=now)["profile"]
    job = scheduler._schedule_position_exit_retry(
        db_session, profile=profile, profile_id=profile["id"],
        profile_key=profile["profile_key"], scheduler_slot="position_exit_monitor",
        symbol=None, exit_cycle_key=f"monitor:{profile['profile_key']}:{slot}",
        block_reason="positions_unavailable",
        read_failure={"read_operation": "positions", "retryable": True, "http_status": 500},
        now=now - timedelta(minutes=1),
    )
    if deferred_recovery:
        def fail(db):
            raise _error(500)
        monkeypatch.setattr(scheduler, "_positions_first", fail)
    result = scheduler._run_automation_tick(slot, now)
    if deferred_recovery:
        assert result["buy_execution_allowed"] is False
        assert harness.broker.buy_calls == []
        monkeypatch.setattr(scheduler, "_positions_first", lambda db: harness.client.list_positions())
        harness.clock.current += timedelta(minutes=1)
        # Both workers are ready. Whichever claims the exit read owns it; a
        # stale queued worker cannot run after entry recovery resolves the job.
        assert deferred[0]() is None
        assert deferred[0]() is None
        assert scheduler._run_claimed_position_exit_retry_job(job.id, harness.clock.now())["status"] == "skipped"
    db_session.expire_all()
    assert db_session.get(PositionExitRetryJob, job.id).status == "resolved_hold"
    assert len(harness.preview.calls) == 1
    assert len(harness.validation.calls) == 1
    assert len(harness.broker.buy_calls) == 1
    assert harness.broker.sell_calls == []
    assert harness.client.external_kis_submit_count == 0
    assert harness.client.possible_order_calls == 1
    assert (harness.clock.now() - harness.client.last_possible_order_queried_at).total_seconds() <= 10
    from app.db.models import AutomationProfileBuyReservation
    assert db_session.query(AutomationProfileBuyReservation).count() == 1
    recovered = db_session.query(TradeRunLog).filter(TradeRunLog.mode == scheduler_module.ENTRY_SLOT_RECOVERY_MODE).one()
    assert json.loads(recovered.response_payload)["recovered_from_position_retry"] is True
    analysis = db_session.query(TradeRunLog).filter(
        TradeRunLog.mode == "automation_scheduler_profile_analysis",
    ).one()
    assert json.loads(analysis.response_payload)["original_scheduler_slot"] == slot


def test_background_exit_worker_and_two_entry_recoveries_race_without_duplicate_orders(
    tmp_path, monkeypatch,
):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import create_engine
    from app.db.database import Base
    from app.tests.integration.test_kis_automation_scheduler_replay import build_harness

    engine = create_engine(f"sqlite:///{(tmp_path / 'entry_slot_race.db').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    db = sessions()
    entered, release = threading.Event(), threading.Event()
    executor = ThreadPoolExecutor(max_workers=2)
    try:
        now = datetime(2026, 8, 25, 9, 50, tzinfo=KST)
        harness = build_harness(db, monkeypatch, now=now, analysis_times=("09:50",))
        callbacks = []
        scheduler = AutomationSchedulerService(
            retry_scheduler=lambda key, callback, **kwargs: callbacks.append(callback) or True,
            retry_now_provider=harness.clock.now,
        )
        scheduler.runtime_settings = harness.runtime
        scheduler.automation_profiles = harness.profiles
        scheduler.automation_profile_buy_scheduler_service = harness.profile_buy
        scheduler.profile_aware_dry_run_auto_buy_service = harness.strategy_scheduler.dry_run_service
        monkeypatch.setattr(scheduler_module, "SessionLocal", sessions)
        monkeypatch.setattr(scheduler_module, "MarketSessionService", lambda: harness.market_sessions)
        monkeypatch.setattr(scheduler_module, "KisAuthManager", lambda *args: object())
        monkeypatch.setattr(scheduler_module, "KisClient", lambda *args: harness.client)
        monkeypatch.setattr(scheduler_module, "KisBroker", lambda *args: harness.broker)
        monkeypatch.setattr(scheduler_module, "KisOrderValidationService", lambda *args: harness.validation)
        monkeypatch.setattr(scheduler_module, "KisOrderSyncService", lambda *args: harness.sync)
        class FakeGuardedExit:
            def __init__(self, **kwargs):
                pass
            def run_scheduler_once(self, db, **kwargs):
                entered.set()
                assert release.wait(timeout=5)
                return {"status": "blocked", "block_reason": "no_exit_candidate",
                        "broker_submit_called": False, "real_order_submitted": False}
        monkeypatch.setattr(scheduler_module, "ProfileAwareGuardedLiveAutoExitService", FakeGuardedExit)
        profile = harness.profiles.selected_profile_schedule(db, now=now)["profile"]
        job = scheduler._schedule_position_exit_retry(
            db, profile=profile, profile_id=profile["id"], profile_key=profile["profile_key"],
            scheduler_slot="position_exit_monitor", symbol=None, exit_cycle_key="background-race",
            block_reason="positions_unavailable",
            read_failure={"read_operation": "positions", "retryable": True, "http_status": 500},
            now=now - timedelta(minutes=1),
        )
        job.status = "running"
        job.claimed_at = now.astimezone(scheduler_module.UTC)
        db.commit()
        worker = executor.submit(
            scheduler._run_claimed_position_exit_retry_job, job.id, now,
            expected_claimed_at=now.astimezone(scheduler_module.UTC),
        )
        assert entered.wait(timeout=5)
        pending = scheduler._run_automation_tick("09:50", now)
        assert pending["buy_execution_allowed"] is False
        assert harness.preview.calls == []
        assert len(callbacks) == 1
        release.set()
        assert worker.result(timeout=5)["status"] == "resolved_hold"
        harness.clock.current += timedelta(minutes=1)
        first = executor.submit(callbacks[0])
        second = executor.submit(callbacks[0])
        assert first.result(timeout=10) is None
        assert second.result(timeout=10) is None
        assert len(harness.preview.calls) == 1
        assert len(harness.broker.buy_calls) == 1
        assert harness.broker.sell_calls == []
        assert harness.client.external_kis_submit_count == 0
        db.expire_all()
        assert db.get(PositionExitRetryJob, job.id).status == "resolved_hold"
        assert db.query(TradeRunLog).filter(TradeRunLog.mode == scheduler_module.ENTRY_SLOT_RECOVERY_MODE).count() == 1
    finally:
        release.set()
        executor.shutdown(wait=True)
        db.close()
        engine.dispose()


def test_stale_exit_worker_claim_token_cannot_execute_entry_owned_retry(db_session, monkeypatch):
    scheduler, events, deferred, clock = _entry_recovery_scheduler(db_session, monkeypatch)
    job = _schedule_unknown_position_retry(db_session, scheduler, clock[0])
    job.status = "running"
    job.claimed_at = clock[0].astimezone(scheduler_module.UTC)
    db_session.commit()
    result = scheduler._run_claimed_position_exit_retry_job(
        job.id, clock[0],
        expected_claimed_at=(clock[0] - timedelta(minutes=1)).astimezone(scheduler_module.UTC),
    )
    assert result["reason"] == "retry_job_not_running"
    assert events == []
    db_session.expire_all()
    assert db_session.get(PositionExitRetryJob, job.id).status == "running"
