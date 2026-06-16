from __future__ import annotations

from app.schemas.agent_command import SCHEMA_VERSION
from app.services.agent_command_validator import AgentCommandValidator


def _validate(payload):
    return AgentCommandValidator().validate_and_normalize(
        {
            "schema_version": SCHEMA_VERSION,
            "market": "KR",
            "provider": "kis",
            **payload,
        }
    )


def test_live_order_submit_is_auth_risk_and_pr56_blocked():
    command = _validate(
        {
            "command_type": "REQUEST_LIVE_ORDER_SUBMIT",
            "domain": "order",
            "intent": "submit_live_order",
            "symbol": "005930",
            "side": "buy",
            "quantity": 1,
        }
    )

    assert command.requires_auth is True
    assert command.requires_risk_approval is True
    assert command.risk_level.value == "live_order"
    assert command.execution_policy.requires_recent_validation is True
    assert command.execution_policy.requires_confirm_live is True
    assert command.execution_policy.allow_execution is False
    assert command.execution_policy.execution_blocked_in_pr56 is True
    assert command.safety.real_order_submitted is False


def test_kill_switch_and_dry_run_dangerous_values_require_auth():
    kill_switch_off = _validate(
        {
            "command_type": "SET_KILL_SWITCH",
            "domain": "safety",
            "intent": "set_kill_switch",
            "settings_change": {"key": "kill_switch", "value": False},
        }
    )
    dry_run_off = _validate(
        {
            "command_type": "SET_DRY_RUN",
            "domain": "settings",
            "intent": "set_dry_run",
            "settings_change": {"key": "dry_run", "value": False},
        }
    )

    assert kill_switch_off.requires_auth is True
    assert kill_switch_off.risk_level.value == "settings_dangerous"
    assert dry_run_off.requires_auth is True
    assert dry_run_off.risk_level.value == "settings_dangerous"
    assert kill_switch_off.safety.setting_changed is False
    assert dry_run_off.safety.setting_changed is False


def test_safety_increasing_settings_do_not_require_auth_but_still_do_not_execute():
    kill_switch_on = _validate(
        {
            "command_type": "SET_KILL_SWITCH",
            "domain": "safety",
            "intent": "set_kill_switch",
            "settings_change": {"key": "kill_switch", "value": True},
        }
    )
    dry_run_on = _validate(
        {
            "command_type": "SET_DRY_RUN",
            "domain": "settings",
            "intent": "set_dry_run",
            "settings_change": {"key": "dry_run", "value": True},
        }
    )

    assert kill_switch_on.requires_auth is False
    assert kill_switch_on.risk_level.value == "settings_safe"
    assert dry_run_on.requires_auth is False
    assert dry_run_on.risk_level.value == "settings_safe"
    assert kill_switch_on.execution_policy.execution_blocked_in_pr56 is True
    assert dry_run_on.safety.setting_changed is False


def test_auto_buy_enable_is_high_risk_auth_required_and_not_applied():
    command = _validate(
        {
            "command_type": "SET_KIS_LIVE_AUTO_BUY",
            "domain": "settings",
            "intent": "request_kis_live_auto_buy_enable",
            "settings_change": {"key": "kis_live_auto_buy_enabled", "value": True},
            "risk_change": {
                "key": "kis_live_auto_buy_enabled",
                "value": True,
                "direction": "increase_risk",
                "high_risk": True,
            },
        }
    )

    assert command.requires_auth is True
    assert command.requires_risk_approval is True
    assert command.high_risk is True
    assert command.risk_level.value == "settings_dangerous"
    assert command.safety.setting_changed is False
    assert command.execution_policy.execution_blocked_in_pr56 is True
