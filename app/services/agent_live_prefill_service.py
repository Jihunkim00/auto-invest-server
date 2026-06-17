from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AgentPlan
from app.schemas.agent_execution import AgentExecutionSafetyFlags
from app.schemas.agent_live_prefill import AgentManualTicketPrefillRequest
from app.services.agent_live_execution_policy_service import (
    AgentLiveExecutionPolicyService,
    AgentLivePrefillPolicyDecision,
)
from app.services.agent_plan_run_service import AgentPlanRunService
from app.services.agent_plan_service import AgentPlanNotFound


class AgentLivePrefillService:
    def __init__(
        self,
        *,
        policy_service: AgentLiveExecutionPolicyService | None = None,
        run_service: AgentPlanRunService | None = None,
    ) -> None:
        self.policy_service = policy_service or AgentLiveExecutionPolicyService()
        self.run_service = run_service or AgentPlanRunService()

    def prepare_manual_ticket(
        self,
        db: Session,
        *,
        plan_id: int,
        request: AgentManualTicketPrefillRequest | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan = db.get(AgentPlan, plan_id)
        if plan is None:
            raise AgentPlanNotFound(plan_id)

        request_payload = self._request_payload(request)
        safety = AgentExecutionSafetyFlags(
            prefill_only=True,
            execution_blocked_for_live_actions=True,
            confirm_live_auto_checked=False,
        )
        policy = self.policy_service.evaluate_prefill(db, plan)
        if not policy.allowed:
            result = self._blocked_result(plan, policy)
            run = self.run_service.record_run(
                db,
                plan=plan,
                policy=policy,
                request=request_payload,
                response=result,
                status="blocked",
                safety=safety,
            )
            return self._response(
                status=policy.status,
                plan=plan,
                run_id=run.id,
                result=result,
                prefill=None,
                policy=policy,
                safety=safety,
            )

        prefill = self._build_prefill(plan, policy=policy)
        result = {
            "result_type": "prefill_payload",
            "prefill_ready": True,
            "prefill_only": True,
            "reason": policy.reason,
            "requires_user_review": True,
            "requires_user_validation": True,
            "requires_confirm_live": True,
            "policy": policy.as_dict(),
        }
        run = self.run_service.record_run(
            db,
            plan=plan,
            policy=policy,
            request=request_payload,
            response={"result": result, "prefill": prefill},
            status="completed",
            safety=safety,
        )
        return self._response(
            status="manual_ticket_prefill_ready",
            plan=plan,
            run_id=run.id,
            result=result,
            prefill=prefill,
            policy=policy,
            safety=safety,
        )

    def _build_prefill(self, plan: AgentPlan, *, policy: AgentLivePrefillPolicyDecision) -> dict[str, Any]:
        command = self._plan_command(plan)
        budget = command.get("budget") if isinstance(command.get("budget"), dict) else {}
        quantity = command.get("quantity")
        metadata = self._source_metadata(plan, policy=policy)
        return {
            "prefill_only": True,
            "provider": str(command.get("provider") or plan.provider or "").lower(),
            "market": str(command.get("market") or plan.market or "").upper(),
            "symbol": str(command.get("symbol") or plan.symbol or "").upper(),
            "side": str(command.get("side") or plan.side or "").lower(),
            "quantity": quantity,
            "qty": self._whole_number(quantity),
            "notional": budget.get("amount"),
            "currency": budget.get("currency"),
            "order_type": command.get("order_type") or "market",
            "dry_run": True,
            "confirm_live": False,
            "source_context": "agent_manual_prefill",
            "source_metadata": metadata,
        }

    def _blocked_result(self, plan: AgentPlan, policy: AgentLivePrefillPolicyDecision) -> dict[str, Any]:
        return {
            "result_type": "prefill_payload",
            "prefill_ready": False,
            "prefill_disabled": True,
            "blocked": True,
            "reason": policy.reason,
            "command_type": plan.command_type,
            "risk_level": plan.risk_level,
            "policy": policy.as_dict(),
        }

    def _response(
        self,
        *,
        status: str,
        plan: AgentPlan,
        run_id: int,
        result: dict[str, Any],
        prefill: dict[str, Any] | None,
        policy: AgentLivePrefillPolicyDecision,
        safety: AgentExecutionSafetyFlags,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "plan_id": plan.id,
            "plan_run_id": run_id,
            "command_type": plan.command_type,
            "result": result,
            "prefill": prefill,
            "auth": self._auth_summary(policy),
            "safety": safety.model_dump(mode="json"),
        }

    def _auth_summary(self, policy: AgentLivePrefillPolicyDecision) -> dict[str, Any]:
        auth_request = policy.auth_request
        if auth_request is None:
            return {"required": False}
        return {
            "required": True,
            "approval_request_id": auth_request.id,
            "status": auth_request.status,
            "auth_type": auth_request.auth_type,
            "scope_hash": auth_request.scope_hash,
            "expires_at": auth_request.expires_at,
            "approved_at": auth_request.approved_at,
            "used_at": auth_request.used_at,
        }

    def _source_metadata(
        self,
        plan: AgentPlan,
        *,
        policy: AgentLivePrefillPolicyDecision,
    ) -> dict[str, Any]:
        auth_request = policy.auth_request
        return {
            "source": "agent_plan",
            "source_type": "agent_manual_ticket_prefill",
            "source_context": "agent_manual_prefill",
            "operator_action_source": "agent_manual_prefill",
            "agent_plan_id": plan.id,
            "agent_plan_key": plan.plan_key,
            "command_log_id": plan.command_log_id,
            "conversation_id": plan.conversation_id,
            "command_type": plan.command_type,
            "domain": plan.domain,
            "plan_status": plan.status,
            "scope_hash": plan.scope_hash,
            "auth_approval_request_id": auth_request.id if auth_request is not None else None,
            "auth_type": auth_request.auth_type if auth_request is not None else None,
            "auth_status": auth_request.status if auth_request is not None else None,
            "requires_auth": bool(plan.requires_auth),
            "requires_user_review": True,
            "requires_user_validation": True,
            "requires_confirm_live": True,
        }

    def _request_payload(self, request: AgentManualTicketPrefillRequest | dict[str, Any] | None) -> dict[str, Any]:
        if request is None:
            return AgentManualTicketPrefillRequest().model_dump(mode="json")
        if isinstance(request, AgentManualTicketPrefillRequest):
            return request.model_dump(mode="json")
        return AgentManualTicketPrefillRequest.model_validate(request).model_dump(mode="json")

    def _plan_command(self, plan: AgentPlan) -> dict[str, Any]:
        try:
            parsed = json.loads(plan.command_json or "{}")
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
        return {}

    def _whole_number(self, value: Any) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number.is_integer():
            return int(number)
        return None
