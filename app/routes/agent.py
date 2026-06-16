from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import AgentCommandLog
from app.services.agent_command_parser_service import AgentCommandParserService


router = APIRouter(prefix="/agent", tags=["agent"])


class AgentCommandParseRequest(BaseModel):
    conversation_id: str | None = Field(default=None, max_length=120)
    message: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


def _parse_json_object(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def _serialize_command_log(row: AgentCommandLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "user_message": row.user_message,
        "parser_status": row.parser_status,
        "command_type": row.command_type,
        "domain": row.domain,
        "market": row.market,
        "provider": row.provider,
        "symbol": row.symbol,
        "side": row.side,
        "risk_level": row.risk_level,
        "requires_auth": bool(row.requires_auth),
        "needs_clarification": bool(row.needs_clarification),
        "command": _parse_json_object(row.parsed_command_json),
        "safety": _parse_json_object(row.safety_json),
        "model_name": row.model_name,
        "schema_version": row.schema_version,
        "error_message": row.error_message,
        "created_at": row.created_at,
    }


@router.post("/commands/parse")
def parse_agent_command(
    payload: AgentCommandParseRequest,
    db: Session = Depends(get_db),
):
    service = AgentCommandParserService()
    return service.parse(
        db,
        message=payload.message,
        conversation_id=payload.conversation_id,
        context=payload.context,
    )


@router.get("/commands/recent")
def recent_agent_commands(
    conversation_id: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(AgentCommandLog)
    if conversation_id:
        query = query.filter(AgentCommandLog.conversation_id == conversation_id)
    rows = query.order_by(AgentCommandLog.created_at.desc(), AgentCommandLog.id.desc()).limit(limit).all()
    return {
        "count": len(rows),
        "commands": [_serialize_command_log(row) for row in rows],
    }


@router.get("/commands/{command_log_id}")
def get_agent_command(
    command_log_id: int,
    db: Session = Depends(get_db),
):
    row = db.get(AgentCommandLog, command_log_id)
    if row is None:
        raise HTTPException(status_code=404, detail="agent_command_log_not_found")
    return _serialize_command_log(row)
