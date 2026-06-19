from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AgentChatToolMode = Literal["read_only", "analysis_only", "prefill_only", "blocked"]
AgentChatToolRiskLevel = Literal["low", "medium", "high", "critical"]
AgentChatToolStatus = Literal["success", "failed", "blocked", "unsupported"]


class AgentChatToolDefinition(BaseModel):
    tool_name: str
    display_name: str
    mode: AgentChatToolMode
    risk_level: AgentChatToolRiskLevel
    allowed_auto_execute: bool
    requires_auth: bool = False
    requires_manual_confirm: bool = False
    mutation: bool = False
    provider: str | None = None
    market: str | None = None
    description: str


class AgentChatToolCall(BaseModel):
    model_config = ConfigDict(extra="allow")

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None


class AgentChatToolSafety(BaseModel):
    read_only: bool = True
    mutation: bool = False
    real_order_submitted: bool = False
    broker_submit_called: bool = False
    manual_submit_called: bool = False
    validation_called: bool = False
    setting_changed: bool = False
    scheduler_changed: bool = False
    confirm_live_auto_checked: bool = False


class AgentChatToolResult(BaseModel):
    tool_name: str
    status: AgentChatToolStatus
    result_type: str
    data: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    error_message: str | None = None
    safety: AgentChatToolSafety = Field(default_factory=AgentChatToolSafety)


class AgentChatResultCard(BaseModel):
    model_config = ConfigDict(extra="allow")

    card_type: str
    title: str
    subtitle: str | None = None
    primary_value: str | None = None
    badges: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
