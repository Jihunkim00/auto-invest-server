from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.agent_chat import (
    AgentChatConversationCreateRequest,
    AgentChatMessageAppendRequest,
)
from app.schemas.agent_chat_orchestrator import AgentChatSendRequest
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService
from app.services.agent_chat_service import (
    AgentChatConversationNotFound,
    AgentChatService,
)


router = APIRouter(prefix="/agent/chat", tags=["agent-chat"])


def _encoding_diagnostics_payload() -> dict:
    sample_korean = "삼성전자 현재가 조회"
    return {
        "status": "ok",
        "sample_korean": sample_korean,
        "sample_answer": "삼성전자(005930)는 KIS 기준 현재가가 ₩354,000입니다.",
        "sample_unicode_escape": sample_korean.encode("unicode_escape").decode("ascii"),
        "encoding_note": (
            "If this looks broken in PowerShell, set OutputEncoding to UTF-8 "
            "or inspect JSON with unicode escape."
        ),
        "safety": {
            "read_only": True,
            "real_order_submitted": False,
            "validation_called": False,
            "setting_changed": False,
            "scheduler_changed": False,
        },
    }


def get_agent_chat_orchestrator_service() -> AgentChatOrchestratorService:
    return AgentChatOrchestratorService()


@router.get("/diagnostics/encoding")
def get_agent_chat_encoding_diagnostics():
    return _encoding_diagnostics_payload()


@router.post("/send")
def send_agent_chat_message(
    payload: AgentChatSendRequest,
    db: Session = Depends(get_db),
    service: AgentChatOrchestratorService = Depends(get_agent_chat_orchestrator_service),
):
    try:
        return service.send(db, request=payload)
    except AgentChatConversationNotFound:
        raise HTTPException(status_code=404, detail="agent_chat_conversation_not_found")


@router.post("/conversations")
def create_agent_chat_conversation(
    payload: AgentChatConversationCreateRequest = Body(
        default_factory=AgentChatConversationCreateRequest
    ),
    db: Session = Depends(get_db),
):
    return AgentChatService().create_conversation(db, request=payload)


@router.get("/conversations")
def list_agent_chat_conversations(
    status: str | None = Query(default="active", max_length=20),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return AgentChatService().list_conversations(db, status=status, limit=limit)


@router.get("/conversations/{conversation_key}")
def get_agent_chat_conversation(
    conversation_key: str,
    db: Session = Depends(get_db),
):
    try:
        return AgentChatService().get_conversation(db, conversation_key=conversation_key)
    except AgentChatConversationNotFound:
        raise HTTPException(status_code=404, detail="agent_chat_conversation_not_found")


@router.get("/conversations/{conversation_key}/messages")
def list_agent_chat_messages(
    conversation_key: str,
    limit: int = Query(default=100, ge=1, le=300),
    before_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    try:
        return AgentChatService().list_messages(
            db,
            conversation_key=conversation_key,
            limit=limit,
            before_id=before_id,
        )
    except AgentChatConversationNotFound:
        raise HTTPException(status_code=404, detail="agent_chat_conversation_not_found")


@router.post("/conversations/{conversation_key}/messages")
def append_agent_chat_message(
    conversation_key: str,
    payload: AgentChatMessageAppendRequest,
    db: Session = Depends(get_db),
):
    try:
        return AgentChatService().append_message(
            db,
            conversation_key=conversation_key,
            request=payload,
        )
    except AgentChatConversationNotFound:
        raise HTTPException(status_code=404, detail="agent_chat_conversation_not_found")


@router.post("/conversations/{conversation_key}/archive")
def archive_agent_chat_conversation(
    conversation_key: str,
    db: Session = Depends(get_db),
):
    try:
        return AgentChatService().archive_conversation(db, conversation_key=conversation_key)
    except AgentChatConversationNotFound:
        raise HTTPException(status_code=404, detail="agent_chat_conversation_not_found")


@router.post("/conversations/{conversation_key}/clear")
def clear_agent_chat_conversation(
    conversation_key: str,
    db: Session = Depends(get_db),
):
    try:
        return AgentChatService().clear_conversation(db, conversation_key=conversation_key)
    except AgentChatConversationNotFound:
        raise HTTPException(status_code=404, detail="agent_chat_conversation_not_found")
