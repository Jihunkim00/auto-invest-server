from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AgentPlan, AuthApprovalRequest
from app.schemas.agent_command import CommandType, OrderSide, RiskLevel
from app.services.agent_command_validator import AgentCommandValidator
from app.services.agent_execution_policy_service import READ_ONLY_COMMANDS
from app.services.agent_scope_service import AgentScopeService


PREFILLABLE_LIVE_COMMANDS = {
    CommandType.CREATE_AGENT_PLAN.value,
    CommandType.PREPARE_MANUAL_BUY_TICKET.value,
    CommandType.PREPARE_MANUAL_SELL_TICKET.value,
    CommandType.REQUEST_LIVE_ORDER_SUBMIT.value,
}

BLOCKED_SETTING_COMMANDS = {
    CommandType.REQUEST_SETTING_CHANGE.value,
    CommandType.REQUEST_RISK_SETTING_CHANGE.value,
    CommandType.SET_DRY_RUN.value,
    CommandType.SET_KILL_SWITCH.value,
    CommandType.SET_BOT_ENABLED.value,
    CommandType.SET_SCHEDULER_ENABLED.value,
    CommandType.SET_DEFAULT_GATE_LEVEL.value,
    CommandType.SET_MAX_TRADES_PER_DAY.value,
    CommandType.SET_MAX_ORDER_SIZE.value,
    CommandType.SET_NO_NEW_ENTRY_AFTER.value,
    CommandType.SET_MAX_POSITION_SIZE.value,
    CommandType.SET_DAILY_LOSS_LIMIT.value,
    CommandType.SET_KIS_ENABLED.value,
    CommandType.SET_KIS_REAL_ORDER_ENABLED.value,
    CommandType.SET_KIS_SCHEDULER_ENABLED.value,
    CommandType.SET_KIS_SCHEDULER_REAL_ORDERS.value,
    CommandType.SET_KIS_LIMITED_AUTO_SELL.value,
    CommandType.SET_KIS_LIMITED_AUTO_BUY.value,
    CommandType.SET_KIS_LIVE_AUTO_BUY.value,
    CommandType.SET_KIS_LIVE_AUTO_SELL.value,
    CommandType.REQUEST_LIMITED_AUTO_SELL_ENABLE.value,
    CommandType.REQUEST_LIMITED_AUTO_BUY_ENABLE.value,
}


@dataclass(frozen=True)
class AgentLivePrefillPolicyDecision:
    allowed: bool
    reason: str
    result_type: str = "prefill_payload"
    execution_mode: str = "agent_manual_prefill"
    safe_execution_only: bool = True
    status: str = "blocked"
    auth_request: AuthApprovalRequest | None = None
    requires_future_pr: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "result_type": self.result_type,
            "execution_mode": self.execution_mode,
            "safe_execution_only": self.safe_execution_only,
            "status": self.status,
            "auth_request_id": self.auth_request.id if self.auth_request is not None else None,
            "auth_status": self.auth_request.status if self.auth_request is not None else None,
            "requires_future_pr": self.requires_future_pr,
        }


class AgentLiveExecutionPolicyService:
    def __init__(
        self,
        *,
        scope_service: AgentScopeService | None = None,
        validator: AgentCommandValidator | None = None,
    ) -> None:
        self.scope_service = scope_service or AgentScopeService()
        self.validator = validator or AgentCommandValidator()

    def evaluate_prefill(self, db: Session, plan: AgentPlan) -> AgentLivePrefillPolicyDecision:
        base = self._base_block_decision(plan)
        if base is not None:
            return base

        command = self._validated_command(plan)
        if command is None:
            return self._block("scope_hash_mismatch")

        command_type = str(plan.command_type or "")
        if command_type == CommandType.REQUEST_LIVE_ORDER_SCHEDULE.value or bool(plan.allow_scheduler_change):
            return self._block("scheduler_live_order_not_prefillable", future_pr="future_scheduler_live_gateway")
        if command_type == CommandType.VALIDATE_MANUAL_ORDER.value:
            return self._block("validation_not_prefillable")
        if command_type in BLOCKED_SETTING_COMMANDS:
            return self._block("setting_change_not_prefillable")
        if bool(plan.allow_setting_change) or str(plan.domain or "") in {"settings", "risk", "safety"}:
            if command_type not in READ_ONLY_COMMANDS:
                return self._block("setting_change_not_prefillable")
        if command_type not in PREFILLABLE_LIVE_COMMANDS:
            return self._block("command_not_prefillable")
        if command_type == CommandType.CREATE_AGENT_PLAN.value and not bool(plan.allow_live_order):
            return self._block("agent_plan_not_live_order_capable")

        detail_block = self._order_detail_block(command.model_dump(mode="json"))
        if detail_block is not None:
            return detail_block

        auth = self._auth_decision(db, plan)
        if auth is not None:
            return auth

        return AgentLivePrefillPolicyDecision(
            allowed=True,
            reason="manual_ticket_prefill_ready",
            status="manual_ticket_prefill_ready",
            auth_request=self._latest_auth_request(db, plan_id=plan.id),
        )

    def _base_block_decision(self, plan: AgentPlan) -> AgentLivePrefillPolicyDecision | None:
        status = str(plan.status or "").lower()
        if status == "cancelled":
            return self._block("plan_cancelled")
        if status == "rejected":
            return self._block("plan_rejected")
        if status == "expired" or self._is_expired(plan):
            return self._block("plan_expired")
        if self._scope_hash_mismatch(plan):
            return self._block("scope_hash_mismatch")
        return None

    def _auth_decision(self, db: Session, plan: AgentPlan) -> AgentLivePrefillPolicyDecision | None:
        if not bool(plan.requires_auth):
            return None

        auth_request = self._latest_auth_request(db, plan_id=plan.id)
        if auth_request is None:
            return self._block("auth_required", status="auth_required")
        if self._is_auth_expired(auth_request):
            return self._block("auth_request_expired", auth_request=auth_request)
        if auth_request.scope_hash != plan.scope_hash:
            return self._block("auth_scope_mismatch", auth_request=auth_request)

        auth_status = str(auth_request.status or "").lower()
        if auth_status == "approved" and auth_request.used_at is None:
            return None
        if auth_status == "pending":
            return self._block("auth_required", status="auth_required", auth_request=auth_request)
        if auth_status in {"expired", "cancelled", "rejected", "used"}:
            return self._block(f"auth_request_{auth_status}", auth_request=auth_request)
        if auth_request.used_at is not None:
            return self._block("auth_request_used", auth_request=auth_request)
        return self._block("auth_not_approved", auth_request=auth_request)

    def _order_detail_block(self, command: dict[str, Any]) -> AgentLivePrefillPolicyDecision | None:
        provider = str(command.get("provider") or "").lower()
        market = str(command.get("market") or "").upper()
        side = str(command.get("side") or "").lower()
        symbol = str(command.get("symbol") or "").strip().upper()
        quantity = command.get("quantity")
        budget = command.get("budget") if isinstance(command.get("budget"), dict) else {}
        notional = budget.get("amount")

        if provider not in {"kis", "alpaca"}:
            return self._block("unsupported_provider_for_prefill")
        if market not in {"KR", "US"}:
            return self._block("unsupported_market_for_prefill")
        if provider == "kis" and market != "KR":
            return self._block("provider_market_mismatch")
        if provider == "alpaca" and market != "US":
            return self._block("provider_market_mismatch")
        if not symbol:
            return self._block("missing_symbol")
        if side not in {OrderSide.BUY.value, OrderSide.SELL.value}:
            return self._block("missing_side")
        if side == OrderSide.BUY.value and quantity is None and notional is None:
            return self._block("missing_order_size")
        if side == OrderSide.SELL.value and quantity is None:
            return self._block("missing_quantity_for_sell")
        return None

    def _latest_auth_request(self, db: Session, *, plan_id: int) -> AuthApprovalRequest | None:
        return (
            db.query(AuthApprovalRequest)
            .filter(AuthApprovalRequest.plan_id == plan_id)
            .order_by(AuthApprovalRequest.created_at.desc(), AuthApprovalRequest.id.desc())
            .first()
        )

    def _validated_command(self, plan: AgentPlan):
        try:
            payload = json.loads(plan.command_json or "{}")
            return self.validator.validate_and_normalize(payload)
        except Exception:
            return None

    def _scope_hash_mismatch(self, plan: AgentPlan) -> bool:
        command = self._validated_command(plan)
        if command is None:
            return True
        _, current_hash = self.scope_service.build_scope_with_hash(command)
        return current_hash != plan.scope_hash

    def _is_expired(self, plan: AgentPlan) -> bool:
        expires_at = plan.expires_at
        if expires_at is None:
            return False
        return self._as_utc(expires_at) <= datetime.now(UTC)

    def _is_auth_expired(self, auth_request: AuthApprovalRequest) -> bool:
        expires_at = auth_request.expires_at
        if expires_at is None:
            return False
        return self._as_utc(expires_at) <= datetime.now(UTC)

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _block(
        self,
        reason: str,
        *,
        status: str = "blocked",
        auth_request: AuthApprovalRequest | None = None,
        future_pr: str | None = None,
    ) -> AgentLivePrefillPolicyDecision:
        return AgentLivePrefillPolicyDecision(
            allowed=False,
            reason=reason,
            status=status,
            auth_request=auth_request,
            requires_future_pr=future_pr,
        )
