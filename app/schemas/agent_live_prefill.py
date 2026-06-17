from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentManualTicketPrefillRequest(BaseModel):
    operator_note: str | None = Field(default=None, max_length=500)
    require_auth_approval: bool = True
    trigger_source: str = Field(default="agent_manual_prefill", max_length=60)


class AgentManualTicketPrefill(BaseModel):
    prefill_only: bool = True
    provider: str
    market: str
    symbol: str
    side: str
    quantity: float | None = None
    qty: int | None = None
    notional: float | None = None
    currency: str | None = None
    order_type: str = "market"
    dry_run: bool = True
    confirm_live: bool = False
    source_context: str = "agent_manual_prefill"
    source_metadata: dict[str, Any]


class AgentManualTicketPrefillResponse(BaseModel):
    status: str
    plan_id: int
    plan_run_id: int
    command_type: str
    result: dict[str, Any]
    prefill: AgentManualTicketPrefill | None = None
    auth: dict[str, Any]
    safety: dict[str, Any]
