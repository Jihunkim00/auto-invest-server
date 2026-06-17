from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import AgentCommandLog
from app.main import app
from app.schemas.agent_command import SCHEMA_VERSION
from app.services.agent_command_validator import AgentCommandValidator


@pytest.fixture(autouse=True)
def _disable_agent_openai(monkeypatch):
    settings = SimpleNamespace(
        openai_api_key=None,
        openai_model="test-agent-model",
        openai_reasoning_effort="low",
    )
    monkeypatch.setattr("app.services.agent_command_parser_service.get_settings", lambda: settings)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _value(value):
    return value.value if hasattr(value, "value") else value


def _store_command_log(db_session, payload, *, conversation_id="conv-route"):
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
        user_message=payload.get("intent", "route test command"),
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


def test_create_plan_from_command_route_and_get_lists(client, db_session):
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
        conversation_id="conv-route-live",
    )

    created = client.post(f"/agent/plans/from-command/{row.id}", json={"expires_in_minutes": 60})

    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "plan_created"
    assert body["plan"]["status"] == "pending_auth"
    assert body["plan"]["requires_auth"] is True
    assert body["auth"]["required"] is True
    assert body["auth"]["approval_request_id"] is not None
    assert body["plan"]["scope_hash"] == body["auth"]["scope_hash"]
    assert body["safety"]["execution_blocked_in_pr57"] is True
    assert body["safety"]["real_order_submitted"] is False

    plans = client.get("/agent/plans", params={"status": "pending_auth", "conversation_id": "conv-route-live"})
    assert plans.status_code == 200
    assert plans.json()["count"] == 1

    detail = client.get(f"/agent/plans/{body['plan']['id']}")
    assert detail.status_code == 200
    assert detail.json()["plan"]["scope"]["budget"]["amount"] == 30000

    auth_requests = client.get("/agent/auth/requests", params={"status": "pending"})
    assert auth_requests.status_code == 200
    auth_body = auth_requests.json()
    assert auth_body["count"] == 1
    assert auth_body["auth_requests"][0]["scope_hash"] == body["plan"]["scope_hash"]
    assert "token_hash" not in auth_body["auth_requests"][0]

    auth_detail = client.get(f"/agent/auth/requests/{body['auth']['approval_request_id']}")
    assert auth_detail.status_code == 200
    assert auth_detail.json()["auth_request"]["auth_type"] == "live_order_schedule"


def test_cancel_plan_route_cancels_pending_auth(client, db_session):
    row = _store_command_log(
        db_session,
        {
            "command_type": "SET_DRY_RUN",
            "domain": "settings",
            "intent": "set_dry_run",
            "settings_change": {"key": "dry_run", "value": False},
        },
    )
    created = client.post(f"/agent/plans/from-command/{row.id}", json={}).json()

    cancelled = client.post(f"/agent/plans/{created['plan']['id']}/cancel", json={"reason": "route cancel"})

    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["plan"]["status"] == "cancelled"
    assert body["auth"]["status"] == "cancelled"
    assert body["safety"]["plan_executed"] is False
    assert body["safety"]["setting_changed"] is False


def test_cancel_auth_request_route_does_not_execute_plan(client, db_session):
    row = _store_command_log(
        db_session,
        {
            "command_type": "SET_KILL_SWITCH",
            "domain": "safety",
            "intent": "set_kill_switch",
            "settings_change": {"key": "kill_switch", "value": False},
        },
    )
    created = client.post(f"/agent/plans/from-command/{row.id}", json={}).json()

    cancelled = client.post(
        f"/agent/auth/requests/{created['auth']['approval_request_id']}/cancel",
        json={"reason": "operator rejected"},
    )

    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["auth_request"]["status"] == "cancelled"
    assert body["safety"]["plan_executed"] is False
    assert body["safety"]["broker_api_called"] is False


def test_invalid_command_log_id_returns_404(client):
    response = client.post("/agent/plans/from-command/999999", json={})

    assert response.status_code == 404
    assert response.json()["detail"] == "agent_command_log_not_found"


def test_parse_endpoint_does_not_create_plan_automatically(client):
    parsed = client.post(
        "/agent/commands/parse",
        json={
            "conversation_id": "parse-no-plan",
            "message": "positions",
            "context": {"default_market": "KR", "default_provider": "kis"},
        },
    )

    assert parsed.status_code == 200
    assert parsed.json()["command_log_id"] is not None
    plans = client.get("/agent/plans", params={"conversation_id": "parse-no-plan"})
    assert plans.status_code == 200
    assert plans.json()["count"] == 0

