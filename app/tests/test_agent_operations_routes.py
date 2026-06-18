from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.schemas.agent_command import SCHEMA_VERSION
from app.services.agent_command_validator import AgentCommandValidator
from app.services.agent_plan_service import AgentPlanService
from app.db.models import AgentCommandLog


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_agent_operations_summary_and_review_queue_routes(client, db_session):
    plan = _create_plan(
        db_session,
        {"command_type": "SHOW_POSITIONS", "domain": "position", "intent": "show_positions"},
    )

    summary = client.get("/agent/operations/summary")
    queue = client.get("/agent/operations/review-queue", params={"queue_type": "ready_for_review"})

    assert summary.status_code == 200
    assert summary.json()["summary"]["total_plans"] == 1
    assert summary.json()["safety"]["read_only"] is True
    assert summary.json()["safety"]["real_order_submitted"] is False
    assert queue.status_code == 200
    assert queue.json()["items"][0]["plan_id"] == plan["id"]
    assert queue.json()["items"][0]["can_run_safe_action"] is True


def test_agent_review_queue_reviewed_and_dismiss_routes(client, db_session):
    plan = _create_plan(
        db_session,
        {"command_type": "SHOW_POSITIONS", "domain": "position", "intent": "show_positions"},
    )
    key = f"plan_{plan['id']}"

    reviewed = client.post(
        f"/agent/operations/review-queue/{key}/reviewed",
        json={"reviewer_note": "checked"},
    )
    open_queue = client.get("/agent/operations/review-queue")
    reviewed_queue = client.get("/agent/operations/review-queue", params={"status": "reviewed"})
    dismissed = client.post(
        f"/agent/operations/review-queue/{key}/dismiss",
        json={"reviewer_note": "dismissed"},
    )

    assert reviewed.status_code == 200
    assert reviewed.json()["state"]["status"] == "reviewed"
    assert all(item["queue_key"] != key for item in open_queue.json()["items"])
    assert any(item["queue_key"] == key for item in reviewed_queue.json()["items"])
    assert dismissed.status_code == 200
    assert dismissed.json()["state"]["status"] == "dismissed"


def test_agent_review_queue_missing_key_returns_404(client):
    response = client.post(
        "/agent/operations/review-queue/missing/reviewed",
        json={"reviewer_note": "missing"},
    )

    assert response.status_code == 404


def _create_plan(db_session, payload, *, conversation_id="conv-pr62-route"):
    command = AgentCommandValidator().validate_and_normalize(
        {
            "schema_version": SCHEMA_VERSION,
            "market": "KR",
            "provider": "kis",
            **payload,
        }
    )
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
    return AgentPlanService().create_from_command_log(
        db_session,
        command_log_id=row.id,
    )["plan"]


def _value(value):
    return value.value if hasattr(value, "value") else value
