from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import AgentPlanRun, AgentScheduleJob
from app.schemas.agent_command import SCHEMA_VERSION
from app.services.agent_plan_service import AgentPlanService
from app.services.agent_schedule_service import AgentScheduleService


def _create_plan(db_session, payload, *, conversation_id="schedule-test"):
    return AgentPlanService().create_from_command(
        db_session,
        command={
            "schema_version": SCHEMA_VERSION,
            "market": "KR",
            "provider": "kis",
            **payload,
        },
        conversation_id=conversation_id,
    )["plan"]


def test_create_watchlist_preview_schedule_and_run_due_once(db_session):
    run_at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    plan = _create_plan(
        db_session,
        {
            "command_type": "CREATE_WATCHLIST_PREVIEW_SCHEDULE",
            "domain": "scheduler",
            "intent": "schedule_watchlist_preview",
            "schedule": {"type": "once", "run_at": run_at, "timezone": "UTC"},
        },
    )
    service = AgentScheduleService()

    created = service.create_schedule(db_session, plan_id=plan["id"])
    due = service.run_due_once(db_session, now=datetime.now(UTC))

    assert created["status"] == "schedule_created"
    assert created["safety"]["agent_schedule_created"] is True
    assert created["safety"]["scheduler_changed"] is False
    assert due["status"] == "run_due_once_completed"
    assert due["count"] == 1
    assert due["results"][0]["status"] == "executed_safe_action"
    job = db_session.query(AgentScheduleJob).one()
    assert job.status == "completed"
    assert job.run_count == 1
    run = db_session.query(AgentPlanRun).one()
    assert run.status == "completed"
    assert run.execution_mode == "agent_scheduled_safe_execution"
    assert run.result_type == "watchlist_preview_result"


def test_live_order_schedule_creation_is_blocked(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "REQUEST_LIVE_ORDER_SCHEDULE",
            "domain": "scheduler",
            "intent": "schedule_live_order",
            "symbol": "005930",
            "side": "buy",
            "quantity": 1,
            "schedule": {"type": "once", "run_at": datetime.now(UTC).isoformat(), "timezone": "UTC"},
        },
    )

    response = AgentScheduleService().create_schedule(db_session, plan_id=plan["id"])

    assert response["status"] == "blocked"
    assert response["reason"] == "scheduler_live_order_blocked_in_pr58"
    assert response["safety"]["scheduler_changed"] is False
    assert db_session.query(AgentScheduleJob).count() == 0
    run = db_session.query(AgentPlanRun).one()
    assert run.status == "blocked"
    assert run.result_type == "blocked_live_action"


def test_schedule_cancel_marks_job_cancelled(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "CREATE_ANALYSIS_SCHEDULE",
            "domain": "scheduler",
            "intent": "schedule_analysis",
            "symbol": "005930",
            "schedule": {"type": "once", "run_at": datetime.now(UTC).isoformat(), "timezone": "UTC"},
        },
    )
    service = AgentScheduleService()
    created = service.create_schedule(db_session, plan_id=plan["id"])

    cancelled = service.cancel_schedule(db_session, schedule_id=created["schedule"]["id"], reason="test")

    assert cancelled["status"] == "schedule_cancelled"
    assert cancelled["schedule"]["status"] == "cancelled"
    assert cancelled["safety"]["real_order_submitted"] is False

