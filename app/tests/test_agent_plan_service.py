from __future__ import annotations

import json

from app.db.models import AgentCommandLog, AuthApprovalRequest
from app.schemas.agent_command import SCHEMA_VERSION
from app.services.agent_command_validator import AgentCommandValidator
from app.services.agent_plan_service import AgentPlanCommandLogNotFound, AgentPlanService


def _validate(payload):
    return AgentCommandValidator().validate_and_normalize(
        {
            "schema_version": SCHEMA_VERSION,
            "market": "KR",
            "provider": "kis",
            **payload,
        }
    )


def _value(value):
    return value.value if hasattr(value, "value") else value


def _store_command_log(db_session, payload, *, conversation_id="conv-pr57"):
    command = _validate(payload)
    row = AgentCommandLog(
        conversation_id=conversation_id,
        user_message=payload.get("intent", "test command"),
        parser_status="test",
        command_type=_value(command.command_type),
        domain=_value(command.domain),
        market=_value(command.market),
        provider=_value(command.provider),
        symbol=command.symbol,
        side=_value(command.side),
        risk_level=_value(command.risk_level),
        requires_auth=command.requires_auth,
        needs_clarification=command.needs_clarification,
        parsed_command_json=json.dumps(command.model_dump(mode="json"), ensure_ascii=False),
        safety_json=command.safety.model_dump_json(),
        model_name=None,
        schema_version=command.schema_version,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_read_only_command_log_creates_ready_plan_without_auth(db_session):
    row = _store_command_log(
        db_session,
        {
            "command_type": "SHOW_POSITIONS",
            "domain": "position",
            "intent": "show_positions",
        },
    )

    response = AgentPlanService().create_from_command_log(db_session, command_log_id=row.id)

    assert response["status"] == "plan_created"
    assert response["plan"]["status"] == "ready_for_review"
    assert response["plan"]["requires_auth"] is False
    assert response["auth"]["required"] is False
    assert response["safety"]["execution_blocked_in_pr57"] is True
    assert response["safety"]["real_order_submitted"] is False
    assert db_session.query(AuthApprovalRequest).count() == 0


def test_conditional_buy_command_creates_pending_auth_plan(db_session):
    row = _store_command_log(
        db_session,
        {
            "command_type": "CREATE_AGENT_PLAN",
            "domain": "agent",
            "intent": "conditional_buy_schedule",
            "symbol": "005930",
            "side": "buy",
            "budget": {"amount": 30000, "currency": "KRW", "mode": "max_notional"},
            "schedule": {"type": "once", "run_at": "2026-06-18T10:00:00+09:00", "timezone": "Asia/Seoul"},
        },
    )

    response = AgentPlanService().create_from_command_log(db_session, command_log_id=row.id)

    assert response["plan"]["status"] == "pending_auth"
    assert response["plan"]["risk_level"] == "live_order_possible"
    assert response["plan"]["requires_auth"] is True
    assert response["plan"]["requires_risk_approval"] is True
    assert response["plan"]["requires_confirm_live"] is True
    assert response["plan"]["requires_recent_validation"] is True
    assert response["plan"]["scope_hash"]
    assert response["auth"]["required"] is True
    assert response["auth"]["auth_type"] == "live_order_schedule"
    assert response["safety"]["plan_executed"] is False
    assert response["safety"]["broker_submit_called"] is False


def test_dry_run_off_creates_dangerous_setting_auth_request(db_session):
    row = _store_command_log(
        db_session,
        {
            "command_type": "SET_DRY_RUN",
            "domain": "settings",
            "intent": "set_dry_run",
            "settings_change": {"key": "dry_run", "value": False},
        },
    )

    response = AgentPlanService().create_from_command_log(db_session, command_log_id=row.id)

    assert response["plan"]["status"] == "pending_auth"
    assert response["plan"]["requires_auth"] is True
    assert response["auth"]["auth_type"] == "dry_run_off"
    assert response["safety"]["setting_changed"] is False


def test_kill_switch_on_is_safety_increasing_ready_plan(db_session):
    row = _store_command_log(
        db_session,
        {
            "command_type": "SET_KILL_SWITCH",
            "domain": "safety",
            "intent": "set_kill_switch",
            "settings_change": {"key": "kill_switch", "value": True},
        },
    )

    response = AgentPlanService().create_from_command_log(db_session, command_log_id=row.id)

    assert response["plan"]["status"] == "ready_for_review"
    assert response["plan"]["requires_auth"] is False
    assert response["auth"]["required"] is False
    assert response["safety"]["setting_changed"] is False


def test_kill_switch_off_requires_auth(db_session):
    row = _store_command_log(
        db_session,
        {
            "command_type": "SET_KILL_SWITCH",
            "domain": "safety",
            "intent": "set_kill_switch",
            "settings_change": {"key": "kill_switch", "value": False},
        },
    )

    response = AgentPlanService().create_from_command_log(db_session, command_log_id=row.id)

    assert response["plan"]["status"] == "pending_auth"
    assert response["plan"]["requires_auth"] is True
    assert response["auth"]["auth_type"] == "kill_switch_off"
    assert response["safety"]["setting_changed"] is False


def test_auto_buy_enable_requires_high_risk_auth(db_session):
    row = _store_command_log(
        db_session,
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
        },
    )

    response = AgentPlanService().create_from_command_log(db_session, command_log_id=row.id)

    assert response["plan"]["status"] == "pending_auth"
    assert response["plan"]["requires_auth"] is True
    assert response["plan"]["risk_level"] == "settings_dangerous"
    assert response["auth"]["auth_type"] == "auto_buy_enable"
    assert response["safety"]["execution_blocked_in_pr57"] is True
    assert response["safety"]["setting_changed"] is False


def test_plan_cancel_cancels_pending_auth_request(db_session):
    row = _store_command_log(
        db_session,
        {
            "command_type": "SET_DRY_RUN",
            "domain": "settings",
            "intent": "set_dry_run",
            "settings_change": {"key": "dry_run", "value": False},
        },
    )
    created = AgentPlanService().create_from_command_log(db_session, command_log_id=row.id)

    cancelled = AgentPlanService().cancel_plan(db_session, plan_id=created["plan"]["id"], reason="test cancel")

    assert cancelled["plan"]["status"] == "cancelled"
    assert cancelled["auth"]["status"] == "cancelled"
    assert cancelled["safety"]["plan_executed"] is False


def test_invalid_command_log_id_raises_not_found(db_session):
    try:
        AgentPlanService().create_from_command_log(db_session, command_log_id=999999)
    except AgentPlanCommandLogNotFound:
        pass
    else:
        raise AssertionError("expected AgentPlanCommandLogNotFound")

