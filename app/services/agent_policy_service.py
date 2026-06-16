from __future__ import annotations

from app.schemas.agent_command import (
    AutoInvestCommand,
    CommandDomain,
    CommandType,
    ExecutionPolicyPayload,
    RiskLevel,
    SafetyFlagsPayload,
)
from app.services.agent_command_schema import (
    ANALYSIS_COMMAND_TYPES,
    DANGEROUS_ENABLE_COMMAND_TYPES,
    LIMITED_AUTO_COMMAND_TYPES,
    LIVE_ORDER_COMMAND_TYPES,
    LIVE_ORDER_SCHEDULER_COMMAND_TYPES,
    PREFILL_ONLY_COMMAND_TYPES,
    READ_ONLY_WITHOUT_AUTH_COMMAND_TYPES,
    SCHEDULER_COMMAND_TYPES,
    SETTING_COMMAND_TYPES,
)


PR56_BLOCK_REASON = "PR56 parses commands only and never executes live trading, scheduler, or settings actions."


class AgentPolicyService:
    def apply_policy(self, command: AutoInvestCommand) -> AutoInvestCommand:
        command.safety = SafetyFlagsPayload()

        requires_auth = False
        requires_risk_approval = False
        requires_recent_validation = False
        requires_confirm_live = False
        allow_live_order = False
        allow_setting_change = False
        allow_scheduler_change = False
        high_risk = False
        risk_level = self._default_risk_level(command)

        if command.command_type in LIVE_ORDER_COMMAND_TYPES:
            risk_level = RiskLevel.LIVE_ORDER
            requires_auth = True
            requires_risk_approval = True
            requires_recent_validation = True
            requires_confirm_live = True
            allow_live_order = True

        elif command.command_type in LIVE_ORDER_SCHEDULER_COMMAND_TYPES:
            risk_level = RiskLevel.SCHEDULER_LIVE_ORDER
            requires_auth = True
            requires_risk_approval = True
            requires_recent_validation = True
            requires_confirm_live = True
            allow_live_order = True
            allow_scheduler_change = True

        elif command.command_type == CommandType.CREATE_AGENT_PLAN:
            risk_level = RiskLevel.LIVE_ORDER_POSSIBLE
            requires_auth = True
            requires_risk_approval = True
            requires_recent_validation = True
            requires_confirm_live = True
            allow_live_order = True
            allow_scheduler_change = bool(command.schedule)

        elif command.command_type in PREFILL_ONLY_COMMAND_TYPES:
            risk_level = RiskLevel.PREFILL_ONLY

        elif command.command_type in SETTING_COMMAND_TYPES or command.command_type in LIMITED_AUTO_COMMAND_TYPES:
            allow_setting_change = True
            risk_level = self._settings_risk_level(command)
            requires_auth = self._settings_requires_auth(command)
            requires_risk_approval = self._settings_requires_risk_approval(command)
            high_risk = self._settings_is_high_risk(command)

        elif command.command_type in SCHEDULER_COMMAND_TYPES:
            allow_scheduler_change = command.command_type != CommandType.SHOW_SCHEDULES
            risk_level = RiskLevel.SETTINGS_DANGEROUS if allow_scheduler_change else RiskLevel.READ_ONLY
            requires_auth = allow_scheduler_change
            requires_risk_approval = allow_scheduler_change

        elif command.command_type in READ_ONLY_WITHOUT_AUTH_COMMAND_TYPES:
            requires_auth = False

        elif command.command_type.value.startswith("SHOW_"):
            risk_level = RiskLevel.READ_ONLY
            requires_auth = False

        if command.needs_clarification:
            allow_live_order = False
            allow_setting_change = False
            allow_scheduler_change = False
            requires_recent_validation = False
            requires_confirm_live = False

        command.risk_level = risk_level
        command.requires_auth = requires_auth
        command.requires_risk_approval = requires_risk_approval
        command.high_risk = high_risk
        command.execution_policy = ExecutionPolicyPayload(
            allow_execution=False,
            allow_live_order=allow_live_order,
            allow_setting_change=allow_setting_change,
            allow_scheduler_change=allow_scheduler_change,
            requires_auth=requires_auth,
            requires_risk_approval=requires_risk_approval,
            requires_recent_validation=requires_recent_validation,
            requires_confirm_live=requires_confirm_live,
            execution_blocked_in_pr56=True,
            reason=PR56_BLOCK_REASON,
        )
        return command

    def _default_risk_level(self, command: AutoInvestCommand) -> RiskLevel:
        if command.command_type in READ_ONLY_WITHOUT_AUTH_COMMAND_TYPES:
            if command.command_type in ANALYSIS_COMMAND_TYPES:
                return RiskLevel.ANALYSIS_ONLY
            return RiskLevel.READ_ONLY
        if command.command_type.value.startswith("SHOW_"):
            return RiskLevel.READ_ONLY
        if command.command_type in ANALYSIS_COMMAND_TYPES:
            return RiskLevel.ANALYSIS_ONLY
        if command.domain == CommandDomain.LOGS:
            return RiskLevel.READ_ONLY
        return RiskLevel.UNKNOWN

    def _settings_risk_level(self, command: AutoInvestCommand) -> RiskLevel:
        if self._settings_requires_auth(command) or self._settings_requires_risk_approval(command):
            return RiskLevel.SETTINGS_DANGEROUS
        return RiskLevel.SETTINGS_SAFE

    def _settings_requires_auth(self, command: AutoInvestCommand) -> bool:
        value = self._settings_value(command)
        if command.command_type in DANGEROUS_ENABLE_COMMAND_TYPES and value is not False:
            return True
        if command.command_type == CommandType.REQUEST_LIMITED_AUTO_SELL_ENABLE:
            return True
        if command.command_type == CommandType.REQUEST_LIMITED_AUTO_BUY_ENABLE:
            return True
        if command.command_type in {CommandType.SET_DRY_RUN, CommandType.SET_KILL_SWITCH}:
            return value is False
        if command.command_type in {
            CommandType.SET_MAX_TRADES_PER_DAY,
            CommandType.SET_MAX_ORDER_SIZE,
            CommandType.SET_NO_NEW_ENTRY_AFTER,
            CommandType.SET_MAX_POSITION_SIZE,
            CommandType.SET_DAILY_LOSS_LIMIT,
            CommandType.REQUEST_RISK_SETTING_CHANGE,
        }:
            return True
        return False

    def _settings_requires_risk_approval(self, command: AutoInvestCommand) -> bool:
        value = self._settings_value(command)
        if command.command_type in DANGEROUS_ENABLE_COMMAND_TYPES and value is not False:
            return True
        if command.command_type in {
            CommandType.REQUEST_SETTING_CHANGE,
            CommandType.REQUEST_RISK_SETTING_CHANGE,
            CommandType.REQUEST_LIMITED_AUTO_SELL_ENABLE,
            CommandType.REQUEST_LIMITED_AUTO_BUY_ENABLE,
            CommandType.SET_MAX_TRADES_PER_DAY,
            CommandType.SET_MAX_ORDER_SIZE,
            CommandType.SET_NO_NEW_ENTRY_AFTER,
            CommandType.SET_MAX_POSITION_SIZE,
            CommandType.SET_DAILY_LOSS_LIMIT,
        }:
            return True
        if command.command_type in {CommandType.SET_DRY_RUN, CommandType.SET_KILL_SWITCH}:
            return value is False
        return False

    def _settings_is_high_risk(self, command: AutoInvestCommand) -> bool:
        value = self._settings_value(command)
        if command.command_type in {
            CommandType.SET_KIS_LIVE_AUTO_BUY,
            CommandType.SET_KIS_LIVE_AUTO_SELL,
            CommandType.REQUEST_LIMITED_AUTO_BUY_ENABLE,
            CommandType.SET_KIS_REAL_ORDER_ENABLED,
            CommandType.SET_KIS_SCHEDULER_REAL_ORDERS,
        }:
            return value is not False
        return bool(command.risk_change and command.risk_change.high_risk)

    def _settings_value(self, command: AutoInvestCommand):
        if command.settings_change is None:
            return None
        return command.settings_change.value
