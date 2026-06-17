from __future__ import annotations

import hashlib

from app.db.models import AuthApprovalRequest, AuthApprovalToken
from app.schemas.agent_command import SCHEMA_VERSION
from app.services.agent_auth_gate_service import AgentAuthGateService
from app.services.agent_command_validator import AgentCommandValidator
from app.services.agent_plan_service import AgentPlanService


def test_auth_gate_stores_token_hash_and_never_serializes_raw_token(db_session):
    auth_gate = AgentAuthGateService(
        key_factory=lambda prefix: f"{prefix}_fixed",
        token_factory=lambda: "raw-secret-token",
    )
    service = AgentPlanService(auth_gate_service=auth_gate)
    command = AgentCommandValidator().validate_and_normalize(
        {
            "schema_version": SCHEMA_VERSION,
            "command_type": "SET_DRY_RUN",
            "domain": "settings",
            "intent": "set_dry_run",
            "market": "KR",
            "provider": "kis",
            "settings_change": {"key": "dry_run", "value": False},
        }
    )

    response = service.create_from_command(db_session, command=command, conversation_id="auth-gate")

    request = db_session.query(AuthApprovalRequest).one()
    token = db_session.query(AuthApprovalToken).one()
    expected_hash = hashlib.sha256("raw-secret-token".encode("utf-8")).hexdigest()
    serialized_request = auth_gate.serialize_request(request)

    assert response["auth"]["approval_key"] == "auth_fixed"
    assert token.token_hash == expected_hash
    assert token.token_hash != "raw-secret-token"
    assert "raw-secret-token" not in str(serialized_request)
    assert "token_hash" not in serialized_request
    assert "token" not in serialized_request


def test_cancel_auth_request_revokes_pending_token(db_session):
    auth_gate = AgentAuthGateService(
        key_factory=lambda prefix: f"{prefix}_cancel",
        token_factory=lambda: "cancel-token",
    )
    service = AgentPlanService(auth_gate_service=auth_gate)
    command = AgentCommandValidator().validate_and_normalize(
        {
            "schema_version": SCHEMA_VERSION,
            "command_type": "SET_KILL_SWITCH",
            "domain": "safety",
            "intent": "set_kill_switch",
            "market": "KR",
            "provider": "kis",
            "settings_change": {"key": "kill_switch", "value": False},
        }
    )
    created = service.create_from_command(db_session, command=command, conversation_id="auth-cancel")

    cancelled = service.cancel_auth_request(
        db_session,
        approval_request_id=created["auth"]["approval_request_id"],
        reason="operator cancel",
    )

    token = db_session.query(AuthApprovalToken).one()
    assert cancelled["auth_request"]["status"] == "cancelled"
    assert token.status == "revoked"
    assert token.revoked_at is not None

