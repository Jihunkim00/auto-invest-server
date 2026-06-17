from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.agent_command import AutoInvestCommand, CommandType, RiskLevel
from app.services.agent_command_schema import (
    ANALYSIS_COMMAND_TYPES,
    DANGEROUS_ENABLE_COMMAND_TYPES,
    LIVE_ORDER_COMMAND_TYPES,
    LIVE_ORDER_SCHEDULER_COMMAND_TYPES,
    PREFILL_ONLY_COMMAND_TYPES,
    READ_ONLY_WITHOUT_AUTH_COMMAND_TYPES,
)


@dataclass(frozen=True)
class AgentPlanPolicyDecision:
    status: str
    requires_auth: bool
    requires_risk_approval: bool
    requires_confirm_live: bool
    requires_recent_validation: bool
    allow_live_order: bool
    allow_setting_change: bool
    allow_scheduler_change: bool
    auth_type: str | None
    plan_title: str
    plan_summary: str
    user_visible_summary: str
    user_visible_warning: str


class AgentPlanPolicyService:
    def decide(self, command: AutoInvestCommand, *, requested_title: str | None = None) -> AgentPlanPolicyDecision:
        command_type = command.command_type
        policy = command.execution_policy
        requires_auth = bool(command.requires_auth or policy.requires_auth)
        requires_risk_approval = bool(command.requires_risk_approval or policy.requires_risk_approval)
        requires_confirm_live = bool(policy.requires_confirm_live)
        requires_recent_validation = bool(policy.requires_recent_validation)
        allow_live_order = bool(policy.allow_live_order)
        allow_setting_change = bool(policy.allow_setting_change)
        allow_scheduler_change = bool(policy.allow_scheduler_change)

        auth_type = self.auth_type_for_command(command)
        if auth_type is not None:
            requires_auth = True

        if command.needs_clarification:
            status = "draft"
            requires_auth = False
        elif requires_auth:
            status = "pending_auth"
        elif self._is_ready_for_review(command):
            status = "ready_for_review"
        else:
            status = "draft"

        title = requested_title or self._default_title(command)
        summary = self._default_summary(command, status)
        visible_summary = command.user_visible_summary or summary
        warning = self._warning(command, auth_type)

        return AgentPlanPolicyDecision(
            status=status,
            requires_auth=requires_auth,
            requires_risk_approval=requires_risk_approval,
            requires_confirm_live=requires_confirm_live,
            requires_recent_validation=requires_recent_validation,
            allow_live_order=allow_live_order,
            allow_setting_change=allow_setting_change,
            allow_scheduler_change=allow_scheduler_change,
            auth_type=auth_type,
            plan_title=title,
            plan_summary=summary,
            user_visible_summary=visible_summary,
            user_visible_warning=warning,
        )

    def auth_type_for_command(self, command: AutoInvestCommand) -> str | None:
        command_type = command.command_type
        value = self._settings_value(command)

        if command_type in LIVE_ORDER_COMMAND_TYPES:
            return "live_order"
        if command_type in LIVE_ORDER_SCHEDULER_COMMAND_TYPES:
            return "live_order_schedule"
        if command_type == CommandType.CREATE_AGENT_PLAN and command.execution_policy.allow_live_order:
            return "live_order_schedule" if command.schedule else "live_order"
        if command_type == CommandType.SET_DRY_RUN and value is False:
            return "dry_run_off"
        if command_type == CommandType.SET_KILL_SWITCH and value is False:
            return "kill_switch_off"
        if command_type == CommandType.SET_KIS_SCHEDULER_REAL_ORDERS and value is not False:
            return "scheduler_real_order"
        if command_type in {CommandType.SET_KIS_LIVE_AUTO_BUY, CommandType.REQUEST_LIMITED_AUTO_BUY_ENABLE}:
            return "auto_buy_enable" if value is not False else None
        if command_type in {CommandType.SET_KIS_LIVE_AUTO_SELL, CommandType.REQUEST_LIMITED_AUTO_SELL_ENABLE}:
            return "auto_sell_enable" if value is not False else None
        if command_type in DANGEROUS_ENABLE_COMMAND_TYPES and value is not False:
            return "dangerous_setting_change"
        if command_type in {
            CommandType.SET_MAX_TRADES_PER_DAY,
            CommandType.SET_MAX_ORDER_SIZE,
            CommandType.SET_NO_NEW_ENTRY_AFTER,
            CommandType.SET_MAX_POSITION_SIZE,
            CommandType.SET_DAILY_LOSS_LIMIT,
            CommandType.REQUEST_RISK_SETTING_CHANGE,
        }:
            return "risk_limit_relaxation"
        if command.requires_auth:
            return "manual_confirmation"
        return None

    def _is_ready_for_review(self, command: AutoInvestCommand) -> bool:
        if command.command_type in READ_ONLY_WITHOUT_AUTH_COMMAND_TYPES:
            return True
        if command.command_type in ANALYSIS_COMMAND_TYPES:
            return True
        if command.command_type in PREFILL_ONLY_COMMAND_TYPES:
            return True
        if command.command_type.value.startswith("SHOW_"):
            return True
        if command.risk_level in {RiskLevel.READ_ONLY, RiskLevel.ANALYSIS_ONLY, RiskLevel.PREFILL_ONLY, RiskLevel.SETTINGS_SAFE}:
            return True
        return False

    def _settings_value(self, command: AutoInvestCommand) -> Any:
        if command.settings_change is None:
            return None
        return command.settings_change.value

    def _default_title(self, command: AutoInvestCommand) -> str:
        if command.symbol:
            return f"{command.command_type.value} for {command.symbol}"
        return command.command_type.value

    def _default_summary(self, command: AutoInvestCommand, status: str) -> str:
        return (
            f"{command.command_type.value} converted to AgentPlan with status={status}. "
            "PR57 stores the plan and does not execute it."
        )

    def _warning(self, command: AutoInvestCommand, auth_type: str | None) -> str:
        if auth_type is None:
            return "No live execution is available in PR57."
        return (
            f"{auth_type} requires explicit approval before any future execution gateway can use this plan. "
            "PR57 still blocks execution."
        )

