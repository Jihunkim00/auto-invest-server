from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import AgentPlan, AuthApprovalRequest, AuthApprovalToken
from app.services.agent_plan_policy_service import AgentPlanPolicyDecision


class AgentAuthGateService:
    def __init__(
        self,
        *,
        key_factory: Callable[[str], str] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self._key_factory = key_factory or self._default_key
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))

    def create_request(
        self,
        db: Session,
        *,
        plan: AgentPlan,
        decision: AgentPlanPolicyDecision,
        expires_at: datetime,
    ) -> AuthApprovalRequest:
        request = AuthApprovalRequest(
            approval_key=self._key_factory("auth"),
            plan_id=plan.id,
            command_log_id=plan.command_log_id,
            conversation_id=plan.conversation_id,
            status="pending",
            auth_type=decision.auth_type or "manual_confirmation",
            risk_level=plan.risk_level,
            scope_hash=plan.scope_hash,
            scope_json=plan.scope_json,
            requested_action_summary=decision.plan_summary,
            user_visible_warning=decision.user_visible_warning,
            expires_at=expires_at,
            metadata_json=json.dumps(
                {
                    "pr": "PR57",
                    "execution_blocked_in_pr57": True,
                    "raw_token_returned": False,
                },
                ensure_ascii=False,
            ),
        )
        db.add(request)
        db.flush()

        raw_token = self._token_factory()
        token = AuthApprovalToken(
            approval_request_id=request.id,
            token_hash=self._hash_token(raw_token),
            token_type="approval_intent",
            status="pending",
            scope_hash=plan.scope_hash,
            expires_at=expires_at,
        )
        db.add(token)
        db.flush()
        return request

    def cancel_request(self, db: Session, request: AuthApprovalRequest, *, reason: str | None = None) -> AuthApprovalRequest:
        del reason
        if request.status == "pending":
            now = datetime.now(timezone.utc)
            request.status = "cancelled"
            request.cancelled_at = now
            request.updated_at = now
            self._revoke_tokens(db, request.id, now=now)
            db.commit()
            db.refresh(request)
        return request

    def cancel_pending_for_plan(self, db: Session, *, plan_id: int) -> list[AuthApprovalRequest]:
        pending_requests = (
            db.query(AuthApprovalRequest)
            .filter(AuthApprovalRequest.plan_id == plan_id, AuthApprovalRequest.status == "pending")
            .all()
        )
        now = datetime.now(timezone.utc)
        for request in pending_requests:
            request.status = "cancelled"
            request.cancelled_at = now
            request.updated_at = now
            self._revoke_tokens(db, request.id, now=now)
        return pending_requests

    def serialize_request(self, request: AuthApprovalRequest) -> dict[str, object]:
        return {
            "id": request.id,
            "approval_key": request.approval_key,
            "plan_id": request.plan_id,
            "command_log_id": request.command_log_id,
            "conversation_id": request.conversation_id,
            "status": request.status,
            "auth_type": request.auth_type,
            "risk_level": request.risk_level,
            "scope_hash": request.scope_hash,
            "scope": self._parse_json_object(request.scope_json),
            "requested_action_summary": request.requested_action_summary,
            "user_visible_warning": request.user_visible_warning,
            "expires_at": request.expires_at,
            "approved_at": request.approved_at,
            "rejected_at": request.rejected_at,
            "cancelled_at": request.cancelled_at,
            "used_at": request.used_at,
            "created_at": request.created_at,
            "updated_at": request.updated_at,
            "metadata": self._parse_json_object(request.metadata_json),
        }

    def summarize_for_plan_response(self, request: AuthApprovalRequest | None) -> dict[str, object]:
        if request is None:
            return {"required": False}
        return {
            "required": True,
            "approval_created": True,
            "approval_request_id": request.id,
            "approval_key": request.approval_key,
            "status": request.status,
            "auth_type": request.auth_type,
            "expires_at": request.expires_at,
            "scope_hash": request.scope_hash,
        }

    def _revoke_tokens(self, db: Session, approval_request_id: int, *, now: datetime) -> None:
        tokens = (
            db.query(AuthApprovalToken)
            .filter(AuthApprovalToken.approval_request_id == approval_request_id, AuthApprovalToken.status == "pending")
            .all()
        )
        for token in tokens:
            token.status = "revoked"
            token.revoked_at = now

    def _hash_token(self, raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    def _default_key(self, prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"

    def _parse_json_object(self, raw_value: str | None) -> dict[str, object]:
        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
        return {}

