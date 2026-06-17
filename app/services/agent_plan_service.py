from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import AgentCommandLog, AgentPlan, AuthApprovalRequest
from app.schemas.agent_command import AutoInvestCommand
from app.schemas.agent_plan import AGENT_PLAN_SCHEMA_VERSION, AgentPlanSafetyFlags
from app.services.agent_auth_gate_service import AgentAuthGateService
from app.services.agent_command_validator import AgentCommandValidator
from app.services.agent_plan_policy_service import AgentPlanPolicyService
from app.services.agent_scope_service import AgentScopeService


class AgentPlanCommandLogNotFound(Exception):
    pass


class AgentPlanNotFound(Exception):
    pass


class AuthApprovalRequestNotFound(Exception):
    pass


class AgentPlanService:
    def __init__(
        self,
        *,
        validator: AgentCommandValidator | None = None,
        scope_service: AgentScopeService | None = None,
        policy_service: AgentPlanPolicyService | None = None,
        auth_gate_service: AgentAuthGateService | None = None,
    ) -> None:
        self.validator = validator or AgentCommandValidator()
        self.scope_service = scope_service or AgentScopeService()
        self.policy_service = policy_service or AgentPlanPolicyService()
        self.auth_gate_service = auth_gate_service or AgentAuthGateService()

    def create_from_command_log(
        self,
        db: Session,
        *,
        command_log_id: int,
        plan_title: str | None = None,
        expires_in_minutes: int = 60,
    ) -> dict[str, Any]:
        command_log = db.get(AgentCommandLog, command_log_id)
        if command_log is None:
            raise AgentPlanCommandLogNotFound(command_log_id)

        payload = self._parse_json_object(command_log.parsed_command_json)
        command = self.validator.validate_and_normalize(
            payload,
            fallback_message=command_log.user_message,
        )
        return self.create_from_command(
            db,
            command=command,
            conversation_id=command_log.conversation_id,
            command_log_id=command_log.id,
            plan_title=plan_title,
            expires_in_minutes=expires_in_minutes,
        )

    def create_from_command(
        self,
        db: Session,
        *,
        command: AutoInvestCommand | dict[str, Any],
        conversation_id: str | None = None,
        command_log_id: int | None = None,
        plan_title: str | None = None,
        expires_in_minutes: int = 60,
    ) -> dict[str, Any]:
        normalized_command = self._normalize_command(command)
        decision = self.policy_service.decide(normalized_command, requested_title=plan_title)
        scope, scope_hash = self.scope_service.build_scope_with_hash(normalized_command)
        scope_json = self.scope_service.canonical_json(scope)
        command_json = normalized_command.model_dump(mode="json")
        execution_policy_json = command_json.get("execution_policy") or {}
        safety = AgentPlanSafetyFlags()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=expires_in_minutes)

        plan = AgentPlan(
            plan_key=f"plan_{uuid4().hex}",
            conversation_id=conversation_id,
            command_log_id=command_log_id,
            schema_version=AGENT_PLAN_SCHEMA_VERSION,
            command_type=self._enum_value(normalized_command.command_type),
            domain=self._enum_value(normalized_command.domain),
            intent=normalized_command.intent,
            market=self._enum_value(normalized_command.market),
            provider=self._enum_value(normalized_command.provider),
            symbol=normalized_command.symbol,
            side=self._enum_value(normalized_command.side),
            risk_level=self._enum_value(normalized_command.risk_level),
            status=decision.status,
            plan_title=decision.plan_title,
            plan_summary=decision.plan_summary,
            user_visible_summary=decision.user_visible_summary,
            command_json=json.dumps(command_json, ensure_ascii=False),
            execution_policy_json=json.dumps(execution_policy_json, ensure_ascii=False),
            safety_json=safety.model_dump_json(),
            scope_json=scope_json,
            scope_hash=scope_hash,
            requires_auth=decision.requires_auth,
            requires_risk_approval=decision.requires_risk_approval,
            requires_confirm_live=decision.requires_confirm_live,
            requires_recent_validation=decision.requires_recent_validation,
            allow_live_order=decision.allow_live_order,
            allow_setting_change=decision.allow_setting_change,
            allow_scheduler_change=decision.allow_scheduler_change,
            expires_at=expires_at,
        )
        db.add(plan)
        db.flush()

        auth_request: AuthApprovalRequest | None = None
        if decision.requires_auth:
            auth_request = self.auth_gate_service.create_request(
                db,
                plan=plan,
                decision=decision,
                expires_at=expires_at,
            )

        db.commit()
        db.refresh(plan)
        if auth_request is not None:
            db.refresh(auth_request)

        return {
            "status": "plan_created",
            "plan": self.serialize_plan(plan),
            "auth": self.auth_gate_service.summarize_for_plan_response(auth_request),
            "safety": safety.model_dump(mode="json"),
        }

    def list_plans(
        self,
        db: Session,
        *,
        status: str | None = None,
        conversation_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        query = db.query(AgentPlan)
        if status:
            query = query.filter(AgentPlan.status == status)
        if conversation_id:
            query = query.filter(AgentPlan.conversation_id == conversation_id)
        rows = query.order_by(AgentPlan.created_at.desc(), AgentPlan.id.desc()).limit(limit).all()
        return {
            "count": len(rows),
            "plans": [self.serialize_plan(row, include_scope=False) for row in rows],
            "safety": AgentPlanSafetyFlags().model_dump(mode="json"),
        }

    def get_plan(self, db: Session, *, plan_id: int) -> dict[str, Any]:
        plan = db.get(AgentPlan, plan_id)
        if plan is None:
            raise AgentPlanNotFound(plan_id)
        auth_request = self._latest_auth_request(db, plan_id=plan.id)
        return {
            "plan": self.serialize_plan(plan),
            "auth": self.auth_gate_service.summarize_for_plan_response(auth_request),
            "safety": AgentPlanSafetyFlags().model_dump(mode="json"),
        }

    def cancel_plan(self, db: Session, *, plan_id: int, reason: str | None = None) -> dict[str, Any]:
        plan = db.get(AgentPlan, plan_id)
        if plan is None:
            raise AgentPlanNotFound(plan_id)

        now = datetime.now(timezone.utc)
        if plan.status not in {"cancelled", "executed"}:
            plan.status = "cancelled"
            plan.cancelled_at = now
            plan.cancellation_reason = reason or "cancelled_by_request"
            plan.updated_at = now
            self.auth_gate_service.cancel_pending_for_plan(db, plan_id=plan.id)
            db.commit()
            db.refresh(plan)

        auth_request = self._latest_auth_request(db, plan_id=plan.id)
        return {
            "status": "plan_cancelled",
            "plan": self.serialize_plan(plan),
            "auth": self.auth_gate_service.summarize_for_plan_response(auth_request),
            "safety": AgentPlanSafetyFlags().model_dump(mode="json"),
        }

    def list_auth_requests(
        self,
        db: Session,
        *,
        status: str | None = None,
        conversation_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        query = db.query(AuthApprovalRequest)
        if status:
            query = query.filter(AuthApprovalRequest.status == status)
        if conversation_id:
            query = query.filter(AuthApprovalRequest.conversation_id == conversation_id)
        rows = query.order_by(AuthApprovalRequest.created_at.desc(), AuthApprovalRequest.id.desc()).limit(limit).all()
        return {
            "count": len(rows),
            "auth_requests": [self.auth_gate_service.serialize_request(row) for row in rows],
            "safety": AgentPlanSafetyFlags().model_dump(mode="json"),
        }

    def get_auth_request(self, db: Session, *, approval_request_id: int) -> dict[str, Any]:
        request = db.get(AuthApprovalRequest, approval_request_id)
        if request is None:
            raise AuthApprovalRequestNotFound(approval_request_id)
        return {
            "auth_request": self.auth_gate_service.serialize_request(request),
            "safety": AgentPlanSafetyFlags().model_dump(mode="json"),
        }

    def cancel_auth_request(
        self,
        db: Session,
        *,
        approval_request_id: int,
        reason: str | None = None,
    ) -> dict[str, Any]:
        request = db.get(AuthApprovalRequest, approval_request_id)
        if request is None:
            raise AuthApprovalRequestNotFound(approval_request_id)
        request = self.auth_gate_service.cancel_request(db, request, reason=reason)
        return {
            "status": "auth_request_cancelled",
            "auth_request": self.auth_gate_service.serialize_request(request),
            "safety": AgentPlanSafetyFlags().model_dump(mode="json"),
        }

    def serialize_plan(self, plan: AgentPlan, *, include_scope: bool = True) -> dict[str, Any]:
        serialized = {
            "id": plan.id,
            "plan_key": plan.plan_key,
            "conversation_id": plan.conversation_id,
            "command_log_id": plan.command_log_id,
            "schema_version": plan.schema_version,
            "command_type": plan.command_type,
            "domain": plan.domain,
            "intent": plan.intent,
            "market": plan.market,
            "provider": plan.provider,
            "symbol": plan.symbol,
            "side": plan.side,
            "risk_level": plan.risk_level,
            "status": plan.status,
            "plan_title": plan.plan_title,
            "plan_summary": plan.plan_summary,
            "user_visible_summary": plan.user_visible_summary,
            "command": self._parse_json_object(plan.command_json),
            "execution_policy": self._parse_json_object(plan.execution_policy_json),
            "safety": self._parse_json_object(plan.safety_json),
            "scope_hash": plan.scope_hash,
            "requires_auth": bool(plan.requires_auth),
            "requires_risk_approval": bool(plan.requires_risk_approval),
            "requires_confirm_live": bool(plan.requires_confirm_live),
            "requires_recent_validation": bool(plan.requires_recent_validation),
            "allow_live_order": bool(plan.allow_live_order),
            "allow_setting_change": bool(plan.allow_setting_change),
            "allow_scheduler_change": bool(plan.allow_scheduler_change),
            "approved_auth_request_id": plan.approved_auth_request_id,
            "execution_blocked": True,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
            "expires_at": plan.expires_at,
            "cancelled_at": plan.cancelled_at,
            "cancellation_reason": plan.cancellation_reason,
        }
        if include_scope:
            serialized["scope"] = self._parse_json_object(plan.scope_json)
        return serialized

    def _latest_auth_request(self, db: Session, *, plan_id: int) -> AuthApprovalRequest | None:
        return (
            db.query(AuthApprovalRequest)
            .filter(AuthApprovalRequest.plan_id == plan_id)
            .order_by(AuthApprovalRequest.created_at.desc(), AuthApprovalRequest.id.desc())
            .first()
        )

    def _normalize_command(self, command: AutoInvestCommand | dict[str, Any]) -> AutoInvestCommand:
        if isinstance(command, AutoInvestCommand):
            payload = command.model_dump(mode="json")
        else:
            payload = dict(command)
        return self.validator.validate_and_normalize(payload)

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

    def _enum_value(self, value: Any) -> Any:
        if hasattr(value, "value"):
            return value.value
        return value

