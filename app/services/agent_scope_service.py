from __future__ import annotations

import hashlib
import json
from typing import Any

from app.schemas.agent_command import AutoInvestCommand


class AgentScopeService:
    def build_scope(self, command: AutoInvestCommand) -> dict[str, Any]:
        command_json = command.model_dump(mode="json")
        execution_policy = command_json.get("execution_policy") or {}
        budget = command_json.get("budget") or None
        schedule = command_json.get("schedule") or None
        settings_change = command_json.get("settings_change") or None
        risk_change = command_json.get("risk_change") or None

        return self._normalize(
            {
                "schema_version": command_json.get("schema_version"),
                "command_type": command_json.get("command_type"),
                "domain": command_json.get("domain"),
                "intent": command_json.get("intent"),
                "market": command_json.get("market"),
                "provider": command_json.get("provider"),
                "symbol": command_json.get("symbol"),
                "side": command_json.get("side"),
                "quantity": command_json.get("quantity"),
                "budget": budget,
                "schedule": schedule,
                "settings_change": settings_change,
                "risk_change": risk_change,
                "portfolio_scope": command_json.get("portfolio_scope") or None,
                "execution_policy": {
                    "requires_auth": execution_policy.get("requires_auth"),
                    "requires_risk_approval": execution_policy.get("requires_risk_approval"),
                    "requires_confirm_live": execution_policy.get("requires_confirm_live"),
                    "requires_recent_validation": execution_policy.get("requires_recent_validation"),
                    "allow_live_order": execution_policy.get("allow_live_order"),
                    "allow_setting_change": execution_policy.get("allow_setting_change"),
                    "allow_scheduler_change": execution_policy.get("allow_scheduler_change"),
                },
                "risk_level": command_json.get("risk_level"),
                "live_order": {
                    "symbol": command_json.get("symbol"),
                    "side": command_json.get("side"),
                    "qty": command_json.get("quantity"),
                    "notional": self._budget_amount(budget),
                    "currency": self._budget_currency(budget),
                    "order_type": command_json.get("order_type"),
                    "provider": command_json.get("provider"),
                    "market": command_json.get("market"),
                    "time_in_force": command_json.get("time_in_force"),
                },
                "scheduler": {
                    "schedule_type": self._dict_get(schedule, "type"),
                    "run_at": self._dict_get(schedule, "run_at"),
                    "timezone": self._dict_get(schedule, "timezone"),
                    "recurrence": self._dict_get(schedule, "recurrence"),
                    "allowed_execution_window": self._dict_get(schedule, "allowed_execution_window"),
                    "max_executions": self._dict_get(schedule, "max_executions"),
                },
                "settings": {
                    "setting_name": self._dict_get(settings_change, "key"),
                    "old_value": self._dict_get(settings_change, "previous_value"),
                    "requested_new_value": self._dict_get(settings_change, "value"),
                    "risk_classification": command_json.get("risk_level"),
                },
                "risk_setting": {
                    "risk_limit_name": self._dict_get(risk_change, "key"),
                    "requested_value": self._dict_get(risk_change, "value"),
                    "direction": self._dict_get(risk_change, "direction"),
                },
            }
        )

    def hash_scope(self, scope: dict[str, Any]) -> str:
        canonical = self.canonical_json(scope)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def canonical_json(self, scope: dict[str, Any]) -> str:
        return json.dumps(
            self._normalize(scope),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def build_scope_with_hash(self, command: AutoInvestCommand) -> tuple[dict[str, Any], str]:
        scope = self.build_scope(command)
        return scope, self.hash_scope(scope)

    def _normalize(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): self._normalize(value.get(key)) for key in sorted(value)}
        if isinstance(value, list):
            return [self._normalize(item) for item in value]
        return value

    def _dict_get(self, value: dict[str, Any] | None, key: str) -> Any:
        if not isinstance(value, dict):
            return None
        return value.get(key)

    def _budget_amount(self, budget: dict[str, Any] | None) -> Any:
        return self._dict_get(budget, "amount")

    def _budget_currency(self, budget: dict[str, Any] | None) -> Any:
        return self._dict_get(budget, "currency")

