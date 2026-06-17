from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import AgentPlan, AgentPlanRun, AuthApprovalRequest
from app.schemas.agent_command import SCHEMA_VERSION
from app.services.agent_auth_gate_service import AgentAuthGateService
from app.services.agent_live_prefill_service import AgentLivePrefillService
from app.services.agent_plan_service import AgentPlanService


def test_agent_manual_prefill_audit_omits_raw_auth_material(db_session):
    auth_gate = AgentAuthGateService(
        key_factory=lambda prefix: f"{prefix}_prefill",
        token_factory=lambda: "raw-secret-token",
    )
    plan_service = AgentPlanService(auth_gate_service=auth_gate)
    created = plan_service.create_from_command(
        db_session,
        command={
            "schema_version": SCHEMA_VERSION,
            "market": "KR",
            "provider": "kis",
            "command_type": "REQUEST_LIVE_ORDER_SUBMIT",
            "domain": "order",
            "intent": "request_live_order",
            "symbol": "005930",
            "side": "buy",
            "quantity": 1,
        },
        conversation_id="audit-pr59",
    )
    plan_id = created["plan"]["id"]
    auth = db_session.query(AuthApprovalRequest).filter(AuthApprovalRequest.plan_id == plan_id).one()
    auth.status = "approved"
    auth.approved_at = datetime.now(UTC)
    plan = db_session.get(AgentPlan, plan_id)
    plan.approved_auth_request_id = auth.id
    db_session.commit()

    response = AgentLivePrefillService().prepare_manual_ticket(db_session, plan_id=plan_id)

    run = db_session.query(AgentPlanRun).one()
    rendered_response = str(response)
    rendered_run = f"{run.request_json} {run.response_json} {run.safety_json}"
    assert "raw-secret-token" not in rendered_response
    assert "raw-secret-token" not in rendered_run
    assert "token_hash" not in rendered_response
    assert "token_hash" not in rendered_run
    assert response["prefill"]["source_metadata"]["source_type"] == "agent_manual_ticket_prefill"
    assert response["prefill"]["source_metadata"]["scope_hash"] == created["plan"]["scope_hash"]
    assert run.status == "completed"
    assert run.result_type == "prefill_payload"
    assert run.execution_mode == "agent_manual_prefill"
    assert response["safety"]["broker_api_called"] is False
