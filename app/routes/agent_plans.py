from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.agent_plan import AgentPlanCancelRequest, AgentPlanCreateRequest, AgentPlanFromCommandRequest
from app.services.agent_plan_service import (
    AgentPlanCommandLogNotFound,
    AgentPlanNotFound,
    AgentPlanService,
    AuthApprovalRequestNotFound,
)


router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/plans/from-command/{command_log_id}")
def create_agent_plan_from_command(
    command_log_id: int,
    payload: AgentPlanFromCommandRequest = Body(default_factory=AgentPlanFromCommandRequest),
    db: Session = Depends(get_db),
):
    try:
        return AgentPlanService().create_from_command_log(
            db,
            command_log_id=command_log_id,
            plan_title=payload.plan_title,
            expires_in_minutes=payload.expires_in_minutes,
        )
    except AgentPlanCommandLogNotFound:
        raise HTTPException(status_code=404, detail="agent_command_log_not_found")


@router.post("/plans")
def create_agent_plan(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    if "command" in payload:
        request = AgentPlanCreateRequest.model_validate(payload)
        command_payload = request.command or {}
        conversation_id = request.conversation_id
        plan_title = request.plan_title
        expires_in_minutes = request.expires_in_minutes
    else:
        command_payload = dict(payload)
        conversation_id = command_payload.pop("conversation_id", None)
        plan_title = command_payload.pop("plan_title", None)
        expires_in_minutes = int(command_payload.pop("expires_in_minutes", 60))

    return AgentPlanService().create_from_command(
        db,
        command=command_payload,
        conversation_id=conversation_id,
        plan_title=plan_title,
        expires_in_minutes=expires_in_minutes,
    )


@router.get("/plans")
def list_agent_plans(
    status: str | None = Query(default=None, max_length=40),
    conversation_id: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return AgentPlanService().list_plans(
        db,
        status=status,
        conversation_id=conversation_id,
        limit=limit,
    )


@router.get("/plans/{plan_id}")
def get_agent_plan(
    plan_id: int,
    db: Session = Depends(get_db),
):
    try:
        return AgentPlanService().get_plan(db, plan_id=plan_id)
    except AgentPlanNotFound:
        raise HTTPException(status_code=404, detail="agent_plan_not_found")


@router.post("/plans/{plan_id}/cancel")
def cancel_agent_plan(
    plan_id: int,
    payload: AgentPlanCancelRequest = Body(default_factory=AgentPlanCancelRequest),
    db: Session = Depends(get_db),
):
    try:
        return AgentPlanService().cancel_plan(db, plan_id=plan_id, reason=payload.reason)
    except AgentPlanNotFound:
        raise HTTPException(status_code=404, detail="agent_plan_not_found")


@router.get("/auth/requests")
def list_auth_requests(
    status: str | None = Query(default=None, max_length=40),
    conversation_id: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return AgentPlanService().list_auth_requests(
        db,
        status=status,
        conversation_id=conversation_id,
        limit=limit,
    )


@router.get("/auth/requests/{approval_request_id}")
def get_auth_request(
    approval_request_id: int,
    db: Session = Depends(get_db),
):
    try:
        return AgentPlanService().get_auth_request(db, approval_request_id=approval_request_id)
    except AuthApprovalRequestNotFound:
        raise HTTPException(status_code=404, detail="auth_approval_request_not_found")


@router.post("/auth/requests/{approval_request_id}/cancel")
def cancel_auth_request(
    approval_request_id: int,
    payload: AgentPlanCancelRequest = Body(default_factory=AgentPlanCancelRequest),
    db: Session = Depends(get_db),
):
    try:
        return AgentPlanService().cancel_auth_request(
            db,
            approval_request_id=approval_request_id,
            reason=payload.reason,
        )
    except AuthApprovalRequestNotFound:
        raise HTTPException(status_code=404, detail="auth_approval_request_not_found")

