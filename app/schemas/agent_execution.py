from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentExecutionSafetyFlags(BaseModel):
    safe_execution_only: bool = True
    execution_blocked_for_live_actions: bool = True
    prefill_only: bool = False
    real_order_submitted: bool = False
    broker_submit_called: bool = False
    manual_submit_called: bool = False
    confirm_live_auto_checked: bool = False
    setting_changed: bool = False
    scheduler_changed: bool = False
    validation_called: bool = False
    broker_api_called: bool = False
    agent_schedule_created: bool = False


class AgentPlanRunRequest(BaseModel):
    dry_run: bool = True
    operator_note: str | None = Field(default=None, max_length=500)
    trigger_source: str = Field(default="manual_agent_plan_run", max_length=60)


class AgentPlanScheduleRequest(BaseModel):
    operator_note: str | None = Field(default=None, max_length=500)
    schedule: dict[str, Any] | None = None
    trigger_source: str = Field(default="manual_agent_schedule_create", max_length=60)


class AgentScheduleCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

