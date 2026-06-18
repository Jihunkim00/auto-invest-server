from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.agent_operations import AgentReviewQueueStateRequest
from app.services.agent_operations_service import (
    AgentOperationsService,
    AgentReviewQueueItemNotFound,
)


router = APIRouter(prefix="/agent/operations", tags=["agent-operations"])


@router.get("/summary")
def get_agent_operations_summary(db: Session = Depends(get_db)):
    return AgentOperationsService().summary(db)


@router.get("/review-queue")
def get_agent_review_queue(
    status: str | None = Query(default="open", max_length=20),
    queue_type: str | None = Query(default="all", max_length=40),
    conversation_key: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return AgentOperationsService().review_queue(
        db,
        status=status,
        queue_type=queue_type,
        conversation_key=conversation_key,
        limit=limit,
    )


@router.post("/review-queue/{queue_key}/reviewed")
def mark_agent_review_queue_item_reviewed(
    queue_key: str,
    payload: AgentReviewQueueStateRequest = Body(
        default_factory=AgentReviewQueueStateRequest
    ),
    db: Session = Depends(get_db),
):
    try:
        return AgentOperationsService().mark_reviewed(
            db,
            queue_key=queue_key,
            request=payload,
        )
    except AgentReviewQueueItemNotFound:
        raise HTTPException(status_code=404, detail="agent_review_queue_item_not_found")


@router.post("/review-queue/{queue_key}/dismiss")
def dismiss_agent_review_queue_item(
    queue_key: str,
    payload: AgentReviewQueueStateRequest = Body(
        default_factory=AgentReviewQueueStateRequest
    ),
    db: Session = Depends(get_db),
):
    try:
        return AgentOperationsService().dismiss(
            db,
            queue_key=queue_key,
            request=payload,
        )
    except AgentReviewQueueItemNotFound:
        raise HTTPException(status_code=404, detail="agent_review_queue_item_not_found")
