from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.agent_live_prefill import (
    AgentManualTicketPrefillRequest,
    AgentManualTicketPrefillResponse,
)
from app.services.agent_live_prefill_service import AgentLivePrefillService
from app.services.agent_plan_service import AgentPlanNotFound


router = APIRouter(prefix="/agent", tags=["agent"])


@router.post(
    "/plans/{plan_id}/prepare-manual-ticket",
    response_model=AgentManualTicketPrefillResponse,
)
def prepare_agent_manual_ticket(
    plan_id: int,
    payload: AgentManualTicketPrefillRequest = Body(default_factory=AgentManualTicketPrefillRequest),
    db: Session = Depends(get_db),
):
    try:
        return AgentLivePrefillService().prepare_manual_ticket(db, plan_id=plan_id, request=payload)
    except AgentPlanNotFound:
        raise HTTPException(status_code=404, detail="agent_plan_not_found")
