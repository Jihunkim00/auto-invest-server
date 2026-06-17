from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.agent_execution import AgentPlanScheduleRequest, AgentScheduleCancelRequest
from app.services.agent_plan_service import AgentPlanNotFound
from app.services.agent_schedule_service import AgentScheduleJobNotFound, AgentScheduleService


router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/plans/{plan_id}/schedule")
def create_agent_schedule(
    plan_id: int,
    payload: AgentPlanScheduleRequest = Body(default_factory=AgentPlanScheduleRequest),
    db: Session = Depends(get_db),
):
    try:
        return AgentScheduleService().create_schedule(db, plan_id=plan_id, request=payload)
    except AgentPlanNotFound:
        raise HTTPException(status_code=404, detail="agent_plan_not_found")


@router.get("/schedules")
def list_agent_schedules(
    status: str | None = Query(default=None, max_length=40),
    conversation_id: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return AgentScheduleService().list_schedules(
        db,
        status=status,
        conversation_id=conversation_id,
        limit=limit,
    )


@router.get("/schedules/{schedule_id}")
def get_agent_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
):
    try:
        return AgentScheduleService().get_schedule(db, schedule_id=schedule_id)
    except AgentScheduleJobNotFound:
        raise HTTPException(status_code=404, detail="agent_schedule_not_found")


@router.post("/schedules/{schedule_id}/cancel")
def cancel_agent_schedule(
    schedule_id: int,
    payload: AgentScheduleCancelRequest = Body(default_factory=AgentScheduleCancelRequest),
    db: Session = Depends(get_db),
):
    try:
        return AgentScheduleService().cancel_schedule(db, schedule_id=schedule_id, reason=payload.reason)
    except AgentScheduleJobNotFound:
        raise HTTPException(status_code=404, detail="agent_schedule_not_found")


@router.post("/schedules/run-due-once")
def run_due_agent_schedules_once(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return AgentScheduleService().run_due_once(db, limit=limit)

