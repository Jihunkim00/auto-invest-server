from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.agent_execution import AgentPlanRunRequest
from app.services.agent_execution_gateway import AgentExecutionGateway, AgentPlanRunNotFound
from app.services.agent_plan_service import AgentPlanNotFound


router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/plans/{plan_id}/run")
def run_agent_plan(
    plan_id: int,
    payload: AgentPlanRunRequest = Body(default_factory=AgentPlanRunRequest),
    db: Session = Depends(get_db),
):
    try:
        return AgentExecutionGateway().run_plan(db, plan_id=plan_id, request=payload)
    except AgentPlanNotFound:
        raise HTTPException(status_code=404, detail="agent_plan_not_found")


@router.get("/plans/{plan_id}/runs")
def list_agent_plan_runs(
    plan_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    try:
        return AgentExecutionGateway().list_runs_for_plan(db, plan_id=plan_id, limit=limit)
    except AgentPlanNotFound:
        raise HTTPException(status_code=404, detail="agent_plan_not_found")


@router.get("/runs/recent")
def recent_agent_plan_runs(
    status: str | None = Query(default=None, max_length=40),
    conversation_id: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return AgentExecutionGateway().recent_runs(
        db,
        status=status,
        conversation_id=conversation_id,
        limit=limit,
    )


@router.get("/runs/{plan_run_id}")
def get_agent_plan_run(
    plan_run_id: int,
    db: Session = Depends(get_db),
):
    try:
        return AgentExecutionGateway().get_run(db, plan_run_id=plan_run_id)
    except AgentPlanRunNotFound:
        raise HTTPException(status_code=404, detail="agent_plan_run_not_found")

