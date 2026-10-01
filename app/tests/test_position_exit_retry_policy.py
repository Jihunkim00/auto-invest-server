
from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import requests
from sqlalchemy.orm import sessionmaker

from app.brokers.base import KisApiError, KisAuthError, KisConfigurationError
from app.db.models import PositionExitRetryJob, StrategyLiveAutoExitAttempt
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
    scheduler = AutomationSchedulerService()
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
