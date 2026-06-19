from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import AgentChatConversation, AgentChatMessage
from app.schemas.agent_chat import (
    AgentChatConversationCreateRequest,
    AgentChatMessageAppendRequest,
)


class AgentChatConversationNotFound(Exception):
    pass


class AgentChatService:
    allowed_roles = {"user", "assistant", "system", "safety", "error"}
    allowed_message_types = {
        "plain_text",
        "command_parse",
        "plan_summary",
        "plan_review",
        "safe_run_result",
        "manual_prefill_result",
        "general_answer",
        "read_only_result",
        "analysis_summary",
        "manual_ticket_prepared",
        "auth_required",
        "blocked",
        "unsupported",
        "error",
    }
    allowed_statuses = {"pending", "completed", "failed", "blocked"}
    allowed_sources = {"flutter_dashboard", "api", "unknown"}
    allowed_metadata_keys = {
        "command_log_id",
        "plan_id",
        "plan_run_id",
        "auth_approval_request_id",
        "prefill_source_plan_id",
        "scope_hash",
        "command_type",
        "domain",
        "market",
        "provider",
        "symbol",
        "side",
        "risk_level",
        "parser_status",
        "model_name",
        "fallback_used",
        "prefill_status",
        "conversation_title",
        "safety",
        "safety_flags",
        "status",
        "message_type",
        "source",
        "intent_category",
        "answer_type",
        "available_actions",
        "read_only",
        "supported",
        "requires_plan",
        "requires_auth",
        "requires_manual_confirmation",
        "context_snapshot",
        "selected_tools",
        "tool_results",
        "result_cards",
        "follow_up_suggestions",
        "diagnostics",
    }
    allowed_safety_keys = {
        "read_only",
        "execution_blocked_in_pr56",
        "execution_blocked_in_pr57",
        "safe_execution_only",
        "execution_blocked_for_live_actions",
        "prefill_only",
        "plan_executed",
        "real_order_submitted",
        "broker_submit_called",
        "manual_submit_called",
        "confirm_live_auto_checked",
        "setting_changed",
        "scheduler_changed",
        "validation_called",
        "broker_api_called",
        "agent_schedule_created",
        "mutation",
    }
    sensitive_key_pattern = re.compile(
        r"(?i)\b("
        r"OPENAI_API_KEY|access_token|refresh_token|authorization|appsecret|"
        r"appkey|broker_secret|password|token_value|approval_token"
        r")\b\s*[:=]\s*(?:Bearer\s+)?([^\s,;}\]]+)"
    )
    bearer_pattern = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+")
    sensitive_key_names = {
        "openai_api_key",
        "access_token",
        "refresh_token",
        "authorization",
        "appsecret",
        "appkey",
        "broker_secret",
        "password",
        "token_value",
        "approval_token",
    }

    def create_conversation(
        self,
        db: Session,
        *,
        request: AgentChatConversationCreateRequest | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._conversation_request(request)
        now = datetime.now(UTC)
        conversation = AgentChatConversation(
            conversation_key=f"conv_{uuid4().hex}",
            title=self._sanitize_text(payload.title or "New Agent Chat", max_length=160),
            status="active",
            source=payload.source if payload.source in self.allowed_sources else "unknown",
            metadata_json=self._json(self.sanitize_metadata(payload.metadata)),
            created_at=now,
            updated_at=now,
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return {"conversation": self.serialize_conversation(conversation)}

    def list_conversations(
        self,
        db: Session,
        *,
        status: str | None = "active",
        limit: int = 20,
    ) -> dict[str, Any]:
        query = db.query(AgentChatConversation)
        if status:
            query = query.filter(AgentChatConversation.status == status)
        rows = (
            query.order_by(
                AgentChatConversation.last_message_at.desc().nullslast(),
                AgentChatConversation.updated_at.desc(),
                AgentChatConversation.id.desc(),
            )
            .limit(limit)
            .all()
        )
        return {
            "count": len(rows),
            "conversations": [self.serialize_conversation(row) for row in rows],
        }

    def get_conversation(self, db: Session, *, conversation_key: str) -> dict[str, Any]:
        conversation = self._conversation_or_raise(db, conversation_key)
        return {"conversation": self.serialize_conversation(conversation)}

    def list_messages(
        self,
        db: Session,
        *,
        conversation_key: str,
        limit: int = 100,
        before_id: int | None = None,
    ) -> dict[str, Any]:
        conversation = self._conversation_or_raise(db, conversation_key)
        query = db.query(AgentChatMessage).filter(
            AgentChatMessage.conversation_key == conversation.conversation_key
        )
        if before_id is not None:
            query = query.filter(AgentChatMessage.id < before_id)
        rows = query.order_by(AgentChatMessage.id.asc()).limit(limit).all()
        return {
            "count": len(rows),
            "messages": [self.serialize_message(row) for row in rows],
            "conversation": self.serialize_conversation(conversation),
        }

    def append_message(
        self,
        db: Session,
        *,
        conversation_key: str,
        request: AgentChatMessageAppendRequest | dict[str, Any],
    ) -> dict[str, Any]:
        conversation = self._conversation_or_raise(db, conversation_key)
        payload = self._message_request(request)
        now = datetime.now(UTC)
        safety = self.sanitize_safety(payload.safety)
        derived_metadata: dict[str, Any] = {"safety": safety}
        for key, value in {
            "command_log_id": payload.command_log_id,
            "plan_id": payload.plan_id,
            "plan_run_id": payload.plan_run_id,
            "auth_approval_request_id": payload.auth_approval_request_id,
            "prefill_source_plan_id": payload.prefill_source_plan_id,
            "parser_status": payload.parser_status,
            "model_name": payload.model_name,
        }.items():
            if value is not None:
                derived_metadata[key] = value
        metadata = self.sanitize_metadata({**payload.metadata, **derived_metadata})
        message = AgentChatMessage(
            conversation_id=conversation.id,
            conversation_key=conversation.conversation_key,
            role=payload.role if payload.role in self.allowed_roles else "assistant",
            message_type=(
                payload.message_type
                if payload.message_type in self.allowed_message_types
                else "plain_text"
            ),
            status=payload.status if payload.status in self.allowed_statuses else "completed",
            text=self._sanitize_text(payload.text),
            command_log_id=payload.command_log_id,
            plan_id=payload.plan_id,
            plan_run_id=payload.plan_run_id,
            auth_approval_request_id=payload.auth_approval_request_id,
            prefill_source_plan_id=payload.prefill_source_plan_id,
            model_name=self._safe_string(payload.model_name, 120),
            parser_status=self._safe_string(payload.parser_status, 40),
            safety_json=self._json(safety),
            metadata_json=self._json(metadata),
            created_at=now,
            updated_at=now,
        )
        conversation.last_message_at = now
        conversation.updated_at = now
        if (conversation.title or "New Agent Chat") == "New Agent Chat" and payload.role == "user":
            conversation.title = self._title_from_text(payload.text)

        db.add(message)
        db.commit()
        db.refresh(conversation)
        db.refresh(message)
        return {"message": self.serialize_message(message)}

    def archive_conversation(self, db: Session, *, conversation_key: str) -> dict[str, Any]:
        conversation = self._conversation_or_raise(db, conversation_key)
        now = datetime.now(UTC)
        conversation.status = "archived"
        conversation.archived_at = now
        conversation.updated_at = now
        db.commit()
        db.refresh(conversation)
        return {"conversation": self.serialize_conversation(conversation)}

    def clear_conversation(self, db: Session, *, conversation_key: str) -> dict[str, Any]:
        conversation = self._conversation_or_raise(db, conversation_key)
        now = datetime.now(UTC)
        conversation.status = "deleted"
        conversation.archived_at = now
        conversation.updated_at = now
        db.commit()
        db.refresh(conversation)
        return {"conversation": self.serialize_conversation(conversation)}

    def sanitize_metadata(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, Any] = {}
        for key, raw in value.items():
            normalized = str(key).strip()
            lowered = normalized.lower()
            if lowered in self.sensitive_key_names:
                continue
            if normalized not in self.allowed_metadata_keys:
                continue
            result[normalized] = self._sanitize_metadata_value(raw)
        return result

    def sanitize_safety(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, Any] = {}
        for key, raw in value.items():
            normalized = str(key).strip()
            lowered = normalized.lower()
            if lowered in self.sensitive_key_names:
                continue
            if normalized not in self.allowed_safety_keys:
                continue
            result[normalized] = self._sanitize_metadata_value(raw)
        return result

    def serialize_conversation(self, row: AgentChatConversation) -> dict[str, Any]:
        return {
            "id": row.id,
            "conversation_key": row.conversation_key,
            "title": row.title,
            "status": row.status,
            "source": row.source,
            "metadata": self._parse_json_object(row.metadata_json),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "archived_at": row.archived_at,
            "last_message_at": row.last_message_at,
        }

    def serialize_message(self, row: AgentChatMessage) -> dict[str, Any]:
        return {
            "id": row.id,
            "conversation_id": row.conversation_id,
            "conversation_key": row.conversation_key,
            "role": row.role,
            "message_type": row.message_type,
            "status": row.status,
            "text": row.text,
            "command_log_id": row.command_log_id,
            "plan_id": row.plan_id,
            "plan_run_id": row.plan_run_id,
            "run_id": row.plan_run_id,
            "auth_approval_request_id": row.auth_approval_request_id,
            "prefill_source_plan_id": row.prefill_source_plan_id,
            "model_name": row.model_name,
            "parser_status": row.parser_status,
            "safety": self._parse_json_object(row.safety_json),
            "metadata": self._parse_json_object(row.metadata_json),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _conversation_or_raise(self, db: Session, conversation_key: str) -> AgentChatConversation:
        row = (
            db.query(AgentChatConversation)
            .filter(AgentChatConversation.conversation_key == conversation_key)
            .first()
        )
        if row is None:
            raise AgentChatConversationNotFound(conversation_key)
        return row

    def _conversation_request(
        self,
        request: AgentChatConversationCreateRequest | dict[str, Any] | None,
    ) -> AgentChatConversationCreateRequest:
        if request is None:
            return AgentChatConversationCreateRequest()
        if isinstance(request, AgentChatConversationCreateRequest):
            return request
        return AgentChatConversationCreateRequest.model_validate(request)

    def _message_request(
        self,
        request: AgentChatMessageAppendRequest | dict[str, Any],
    ) -> AgentChatMessageAppendRequest:
        if isinstance(request, AgentChatMessageAppendRequest):
            return request
        return AgentChatMessageAppendRequest.model_validate(request)

    def _sanitize_metadata_value(self, value: Any) -> Any:
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            return self._sanitize_text(value, max_length=500)
        if isinstance(value, list):
            return [self._sanitize_metadata_value(item) for item in value[:25]]
        if isinstance(value, dict):
            sanitized = {}
            for key, raw in value.items():
                lowered = str(key).strip().lower()
                if lowered in self.sensitive_key_names:
                    continue
                sanitized[str(key)[:80]] = self._sanitize_metadata_value(raw)
            return sanitized
        return self._sanitize_text(str(value), max_length=500)

    def _sanitize_text(self, value: str, *, max_length: int = 4000) -> str:
        text = str(value or "")
        text = self.sensitive_key_pattern.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
        text = self.bearer_pattern.sub("Bearer [REDACTED]", text)
        return text[:max_length]

    def _title_from_text(self, text: str) -> str:
        sanitized = self._sanitize_text(text, max_length=80).strip()
        if not sanitized:
            return "New Agent Chat"
        return sanitized if len(sanitized) <= 60 else f"{sanitized[:57]}..."

    def _safe_string(self, value: str | None, max_length: int) -> str | None:
        if value is None:
            return None
        text = self._sanitize_text(value, max_length=max_length).strip()
        return text or None

    def _json(self, payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, default=str)

    def _parse_json_object(self, raw_value: str | None) -> dict[str, Any]:
        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
        return {}
