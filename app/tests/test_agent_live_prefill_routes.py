from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import AgentPlan, AuthApprovalRequest
from app.main import app
from app.schemas.agent_command import SCHEMA_VERSION


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _create_plan(client, payload, *, conversation_id="route-pr59"):
    response = client.post(
        "/agent/plans",
        json={
            "command": {
                "schema_version": SCHEMA_VERSION,
                "market": "KR",
                "provider": "kis",
                **payload,
            },
            "conversation_id": conversation_id,
            "expires_in_minutes": 60,
        },
    )
    assert response.status_code == 200
    return response.json()["plan"]


def _approve_latest_auth(db_session, plan_id: int) -> AuthApprovalRequest:
    row = (
        db_session.query(AuthApprovalRequest)
        .filter(AuthApprovalRequest.plan_id == plan_id)
        .order_by(AuthApprovalRequest.created_at.desc(), AuthApprovalRequest.id.desc())
        .one()
    )
    now = datetime.now(UTC)
    row.status = "approved"
    row.approved_at = now
    row.updated_at = now
    plan = db_session.get(AgentPlan, plan_id)
    plan.approved_auth_request_id = row.id
    db_session.commit()
    return row


def test_prepare_manual_ticket_route_returns_ready_prefill_and_run(client):
    plan = _create_plan(
        client,
        {
            "command_type": "PREPARE_MANUAL_SELL_TICKET",
            "domain": "order",
            "intent": "prepare_sell_ticket",
            "symbol": "005930",
            "side": "sell",
            "quantity": 3,
        },
    )

    response = client.post(
        f"/agent/plans/{plan['id']}/prepare-manual-ticket",
        json={"operator_note": "route prefill"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "manual_ticket_prefill_ready"
    assert body["prefill"]["symbol"] == "005930"
    assert body["prefill"]["qty"] == 3
    assert body["prefill"]["dry_run"] is True
    assert body["prefill"]["confirm_live"] is False
    assert body["safety"]["validation_called"] is False

    runs = client.get(f"/agent/plans/{plan['id']}/runs")
    assert runs.status_code == 200
    assert runs.json()["count"] == 1
    assert runs.json()["runs"][0]["execution_mode"] == "agent_manual_prefill"


def test_prepare_manual_ticket_route_requires_approved_auth(client):
    plan = _create_plan(
        client,
        {
            "command_type": "REQUEST_LIVE_ORDER_SUBMIT",
            "domain": "order",
            "intent": "request_live_order",
            "symbol": "005930",
            "side": "buy",
            "quantity": 1,
        },
    )

    response = client.post(f"/agent/plans/{plan['id']}/prepare-manual-ticket", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "auth_required"
    assert body["prefill"] is None
    assert body["auth"]["status"] == "pending"


def test_prepare_manual_ticket_route_accepts_approved_auth(client, db_session):
    plan = _create_plan(
        client,
        {
            "command_type": "REQUEST_LIVE_ORDER_SUBMIT",
            "domain": "order",
            "intent": "request_live_order",
            "symbol": "005930",
            "side": "buy",
            "quantity": 1,
        },
    )
    auth = _approve_latest_auth(db_session, plan["id"])

    response = client.post(f"/agent/plans/{plan['id']}/prepare-manual-ticket", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "manual_ticket_prefill_ready"
    assert body["auth"]["approval_request_id"] == auth.id
    assert body["prefill"]["source_metadata"]["auth_approval_request_id"] == auth.id


def test_prepare_manual_ticket_unknown_plan_returns_404(client):
    response = client.post("/agent/plans/999999/prepare-manual-ticket", json={})

    assert response.status_code == 404
    assert response.json()["detail"] == "agent_plan_not_found"
