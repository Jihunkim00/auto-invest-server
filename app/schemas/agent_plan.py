from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


AGENT_PLAN_SCHEMA_VERSION = "agent_plan_v1"


class AgentPlanSafetyFlags(BaseModel):
    execution_blocked_in_pr57: bool = True
    plan_executed: bool = False
    real_order_submitted: bool = False
    broker_submit_called: bool = False
    manual_submit_called: bool = False
    setting_changed: bool = False
    scheduler_changed: bool = False
    validation_called: bool = False
    broker_api_called: bool = False


class AgentPlanFromCommandRequest(BaseModel):
    plan_title: str | None = None
    expires_in_minutes: int = Field(default=60, ge=1, le=24 * 60)


class AgentPlanCancelRequest(BaseModel):
    reason: str | None = None


class AgentPlanCreateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    conversation_id: str | None = Field(default=None, max_length=120)
    command: dict[str, Any] | None = None
    plan_title: str | None = None
    expires_in_minutes: int = Field(default=60, ge=1, le=24 * 60)

