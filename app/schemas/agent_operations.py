from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentOperationsSummaryPayload(BaseModel):
    total_plans: int = 0
    total_active_plans: int = 0
    active_plans: int = 0
    ready_for_review_count: int = 0
    pending_auth_count: int = 0
    auth_required_count: int = 0
    blocked_count: int = 0
    blocked_run_count: int = 0
    prefill_ready_count: int = 0
    safe_run_completed_count: int = 0
    failed_count: int = 0
    active_conversation_count: int = 0
    archived_conversation_count: int = 0
    today_messages_count: int = 0
    latest_conversation_key: str | None = None
    latest_plan_id: int | None = None
    latest_run_id: int | None = None
    latest_plan_at: datetime | None = None
    latest_run_at: datetime | None = None


class AgentOperationsSafetyPayload(BaseModel):
    read_only: bool = True
    real_order_submitted: bool = False
    broker_submit_called: bool = False
    manual_submit_called: bool = False
    validation_called: bool = False
    setting_changed: bool = False
    scheduler_changed: bool = False


class AgentReviewQueueItemPayload(BaseModel):
    queue_id: str
    queue_key: str
    item_type: str
    queue_type: str
    priority: str
    review_status: str = "open"
    reviewer_note: str | None = None
    conversation_key: str | None = None
    command_log_id: int | None = None
    plan_id: int | None = None
    plan_run_id: int | None = None
    auth_approval_request_id: int | None = None
    command_type: str | None = None
    domain: str | None = None
    market: str | None = None
    provider: str | None = None
    symbol: str | None = None
    side: str | None = None
    risk_level: str | None = None
    status: str | None = None
    title: str
    summary: str
    blocked_reason: str | None = None
    safety_badges: list[str] = Field(default_factory=list)
    can_run_safe_action: bool = False
    can_prepare_ticket: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentReviewQueueStateRequest(BaseModel):
    reviewer_note: str | None = Field(default=None, max_length=500)


class AgentReviewQueueStatePayload(BaseModel):
    queue_key: str
    item_type: str
    source_id: int | None = None
    status: str
    reviewed_at: datetime | None = None
    dismissed_at: datetime | None = None
    reviewer_note: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
