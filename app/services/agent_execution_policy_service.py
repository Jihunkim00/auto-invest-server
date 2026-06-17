from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.db.models import AgentPlan
from app.schemas.agent_command import CommandType, RiskLevel
from app.services.agent_command_validator import AgentCommandValidator
from app.services.agent_scope_service import AgentScopeService


READ_ONLY_COMMANDS = {
    CommandType.SHOW_SYSTEM_STATUS.value,
    CommandType.SHOW_OPERATIONS_STATUS.value,
    CommandType.SHOW_RISK_STATUS.value,
    CommandType.SHOW_BROKER_STATUS.value,
    CommandType.SHOW_SCHEDULER_STATUS.value,
    CommandType.SHOW_SETTINGS.value,
    CommandType.SHOW_LOGS.value,
    CommandType.SHOW_RECENT_RUNS.value,
    CommandType.SHOW_RECENT_ORDERS.value,
    CommandType.SHOW_RECENT_SIGNALS.value,
    CommandType.SHOW_PORTFOLIO.value,
    CommandType.SHOW_POSITIONS.value,
    CommandType.SHOW_POSITION_DETAIL.value,
    CommandType.REFRESH_BALANCE.value,
    CommandType.REFRESH_POSITIONS.value,
    CommandType.REFRESH_OPEN_ORDERS.value,
    CommandType.SHOW_EXIT_REVIEW.value,
    CommandType.SHOW_EXIT_REVIEW_QUEUE.value,
}

ANALYSIS_COMMANDS = {
    CommandType.RUN_MARKET_ANALYSIS.value,
    CommandType.RUN_SINGLE_SYMBOL_ANALYSIS.value,
    CommandType.RUN_WATCHLIST_PREVIEW.value,
    CommandType.RUN_WATCHLIST_GPT_REVIEW.value,
}

EXIT_REVIEW_COMMANDS = {
    CommandType.RUN_EXIT_PREFLIGHT.value,
    CommandType.RUN_EXIT_SHADOW_DECISION.value,
}

LIMITED_AUTO_REVIEW_COMMANDS = {
    CommandType.SHOW_LIMITED_AUTO_SELL_READINESS.value,
    CommandType.RUN_LIMITED_AUTO_SELL_REVIEW.value,
    CommandType.SHOW_LIMITED_AUTO_BUY_READINESS.value,
    CommandType.RUN_LIMITED_AUTO_BUY_REVIEW.value,
}

PREFILL_COMMANDS = {
    CommandType.PREPARE_MANUAL_BUY_TICKET.value,
    CommandType.PREPARE_MANUAL_SELL_TICKET.value,
}

SAFE_SCHEDULE_COMMANDS = {
    CommandType.CREATE_ANALYSIS_SCHEDULE.value,
    CommandType.CREATE_EXIT_PREFLIGHT_SCHEDULE.value,
    CommandType.CREATE_WATCHLIST_PREVIEW_SCHEDULE.value,
}

LIVE_RISK_LEVELS = {
    RiskLevel.LIVE_ORDER.value,
    RiskLevel.LIVE_ORDER_POSSIBLE.value,
    RiskLevel.SCHEDULER_LIVE_ORDER.value,
}


@dataclass(frozen=True)
class AgentExecutionPolicyDecision:
    allowed: bool
    reason: str
    result_type: str
    execution_mode: str
    safe_execution_only: bool = True
    requires_future_pr: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "result_type": self.result_type,
            "execution_mode": self.execution_mode,
            "safe_execution_only": self.safe_execution_only,
            "requires_future_pr": self.requires_future_pr,
        }


class AgentExecutionPolicyService:
    def __init__(
        self,
        *,
        scope_service: AgentScopeService | None = None,
        validator: AgentCommandValidator | None = None,
    ) -> None:
        self.scope_service = scope_service or AgentScopeService()
        self.validator = validator or AgentCommandValidator()

    def evaluate_run(self, plan: AgentPlan) -> AgentExecutionPolicyDecision:
        base = self._base_block_decision(plan)
        if base is not None:
            return base

        command_type = str(plan.command_type or "")
        if command_type in READ_ONLY_COMMANDS:
            return self._allow("read_only_result")
        if command_type in ANALYSIS_COMMANDS:
            return self._allow(
                "watchlist_preview_result"
                if command_type in {CommandType.RUN_WATCHLIST_PREVIEW.value, CommandType.RUN_WATCHLIST_GPT_REVIEW.value}
                else "analysis_result"
            )
        if command_type == CommandType.RUN_EXIT_PREFLIGHT.value:
            return self._allow("exit_preflight_result")
        if command_type == CommandType.RUN_EXIT_SHADOW_DECISION.value:
            return self._allow("shadow_decision_result")
        if command_type in LIMITED_AUTO_REVIEW_COMMANDS:
            return self._allow("analysis_result")
        if command_type in PREFILL_COMMANDS:
            return self._allow("prefill_payload")
        if command_type in SAFE_SCHEDULE_COMMANDS:
            return self._block(
                "use_schedule_endpoint_for_safe_agent_schedule",
                "unsupported_command",
            )
        return self._command_block_decision(plan)

    def evaluate_schedule(self, plan: AgentPlan) -> AgentExecutionPolicyDecision:
        base = self._base_block_decision(plan)
        if base is not None:
            return base

        command_type = str(plan.command_type or "")
        if command_type in SAFE_SCHEDULE_COMMANDS:
            return self._allow("watchlist_preview_result", execution_mode="agent_scheduled_safe_execution")
        if command_type == CommandType.REQUEST_LIVE_ORDER_SCHEDULE.value:
            return self._block(
                "scheduler_live_order_blocked_in_pr58",
                "blocked_live_action",
                execution_mode="blocked_live_execution",
                future_pr="PR59",
            )
        return self._command_block_decision(plan)

    def _base_block_decision(self, plan: AgentPlan) -> AgentExecutionPolicyDecision | None:
        status = str(plan.status or "").lower()
        if status == "cancelled":
            return self._block("plan_cancelled", "error")
        if status == "rejected":
            return self._block("plan_rejected", "error")
        if status == "expired" or self._is_expired(plan):
            return self._block("plan_expired", "error")
        if self._scope_hash_mismatch(plan):
            return self._block("scope_hash_mismatch", "error")
        return None

    def _command_block_decision(self, plan: AgentPlan) -> AgentExecutionPolicyDecision:
        command_type = str(plan.command_type or "")
        risk_level = str(plan.risk_level or "")
        domain = str(plan.domain or "")

        if command_type == CommandType.REQUEST_LIVE_ORDER_SCHEDULE.value or risk_level == RiskLevel.SCHEDULER_LIVE_ORDER.value:
            return self._block(
                "scheduler_live_order_blocked_in_pr58",
                "blocked_live_action",
                execution_mode="blocked_live_execution",
                future_pr="PR59",
            )
        if command_type == CommandType.VALIDATE_MANUAL_ORDER.value:
            return self._block("validation_execution_blocked_in_pr58", "blocked_live_action")
        if bool(plan.allow_live_order) or risk_level in LIVE_RISK_LEVELS:
            return self._block(
                "live_order_execution_blocked_in_pr58",
                "blocked_live_action",
                execution_mode="blocked_live_execution",
                future_pr="PR59",
            )
        if bool(plan.allow_setting_change) or risk_level == RiskLevel.SETTINGS_DANGEROUS.value:
            return self._block(
                "setting_change_blocked_in_pr58",
                "blocked_setting_change",
                execution_mode="blocked_setting_execution",
                future_pr="PR59",
            )
        if domain in {"settings", "risk", "safety"} and command_type not in READ_ONLY_COMMANDS:
            return self._block(
                "setting_change_blocked_in_pr58",
                "blocked_setting_change",
                execution_mode="blocked_setting_execution",
                future_pr="PR59",
            )
        if bool(plan.requires_auth):
            return self._block(
                "auth_required_but_not_executable_in_pr58",
                "unsupported_command",
                future_pr="PR59",
            )
        return self._block("command_not_safe_for_agent_gateway", "unsupported_command")

    def _allow(
        self,
        result_type: str,
        *,
        execution_mode: str = "agent_safe_execution",
    ) -> AgentExecutionPolicyDecision:
        return AgentExecutionPolicyDecision(
            allowed=True,
            reason="safe_command_allowed_in_pr58",
            result_type=result_type,
            execution_mode=execution_mode,
        )

    def _block(
        self,
        reason: str,
        result_type: str,
        *,
        execution_mode: str = "agent_safe_execution",
        future_pr: str | None = None,
    ) -> AgentExecutionPolicyDecision:
        return AgentExecutionPolicyDecision(
            allowed=False,
            reason=reason,
            result_type=result_type,
            execution_mode=execution_mode,
            requires_future_pr=future_pr,
        )

    def _scope_hash_mismatch(self, plan: AgentPlan) -> bool:
        try:
            payload = json.loads(plan.command_json or "{}")
            command = self.validator.validate_and_normalize(payload)
            _, current_hash = self.scope_service.build_scope_with_hash(command)
        except Exception:
            return True
        return current_hash != plan.scope_hash

    def _is_expired(self, plan: AgentPlan) -> bool:
        expires_at = plan.expires_at
        if expires_at is None:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        else:
            expires_at = expires_at.astimezone(UTC)
        return expires_at <= datetime.now(UTC)

