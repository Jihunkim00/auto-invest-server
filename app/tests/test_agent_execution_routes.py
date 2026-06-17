from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
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


def _create_plan(client, payload):
    response = client.post(
        "/agent/plans",
        json={
            "command": {
                "schema_version": SCHEMA_VERSION,
                "market": "KR",
                "provider": "kis",
                **payload,
            },
            "conversation_id": "route-pr58",
            "expires_in_minutes": 60,
        },
    )
    assert response.status_code == 200
    return response.json()["plan"]


def test_run_routes_complete_and_return_recent_detail(client):
    plan = _create_plan(
        client,
        {
            "command_type": "SHOW_SETTINGS",
            "domain": "settings",
            "intent": "show_settings",
        },
    )

    run = client.post(
        f"/agent/plans/{plan['id']}/run",
        json={"dry_run": True, "operator_note": "route test"},
    )

    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "executed_safe_action"
    assert body["result"]["result_type"] == "read_only_result"
    assert body["safety"]["real_order_submitted"] is False

    by_plan = client.get(f"/agent/plans/{plan['id']}/runs")
    assert by_plan.status_code == 200
    assert by_plan.json()["count"] == 1

    recent = client.get("/agent/runs/recent", params={"conversation_id": "route-pr58"})
    assert recent.status_code == 200
    assert recent.json()["count"] == 1

    detail = client.get(f"/agent/runs/{body['plan_run_id']}")
    assert detail.status_code == 200
    assert detail.json()["run"]["status"] == "completed"


def test_live_order_run_route_is_blocked(client):
    plan = _create_plan(
        client,
        {
            "command_type": "REQUEST_LIVE_ORDER_SUBMIT",
            "domain": "order",
            "intent": "submit_live_order",
            "symbol": "005930",
            "side": "buy",
            "quantity": 1,
        },
    )

    run = client.post(f"/agent/plans/{plan['id']}/run", json={"dry_run": True})

    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "blocked"
    assert body["result"]["reason"] == "live_order_execution_blocked_in_pr58"
    assert body["safety"]["broker_submit_called"] is False


def test_schedule_routes_create_get_cancel_and_run_due(client):
    run_at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    plan = _create_plan(
        client,
        {
            "command_type": "CREATE_WATCHLIST_PREVIEW_SCHEDULE",
            "domain": "scheduler",
            "intent": "schedule_watchlist_preview",
            "schedule": {"type": "once", "run_at": run_at, "timezone": "UTC"},
        },
    )

    created = client.post(f"/agent/plans/{plan['id']}/schedule", json={})

    assert created.status_code == 200
    created_body = created.json()
    assert created_body["status"] == "schedule_created"
    assert created_body["safety"]["agent_schedule_created"] is True
    schedule_id = created_body["schedule"]["id"]

    listed = client.get("/agent/schedules", params={"conversation_id": "route-pr58"})
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    detail = client.get(f"/agent/schedules/{schedule_id}")
    assert detail.status_code == 200
    assert detail.json()["schedule"]["status"] == "active"

    due = client.post("/agent/schedules/run-due-once")
    assert due.status_code == 200
    assert due.json()["count"] == 1
    assert due.json()["results"][0]["status"] == "executed_safe_action"


def test_schedule_cancel_route(client):
    plan = _create_plan(
        client,
        {
            "command_type": "CREATE_ANALYSIS_SCHEDULE",
            "domain": "scheduler",
            "intent": "schedule_analysis",
            "symbol": "005930",
            "schedule": {"type": "once", "run_at": datetime.now(UTC).isoformat(), "timezone": "UTC"},
        },
    )
    created = client.post(f"/agent/plans/{plan['id']}/schedule", json={}).json()

    cancelled = client.post(f"/agent/schedules/{created['schedule']['id']}/cancel", json={"reason": "route cancel"})

    assert cancelled.status_code == 200
    assert cancelled.json()["schedule"]["status"] == "cancelled"
    assert cancelled.json()["safety"]["scheduler_changed"] is False


def test_run_unknown_plan_returns_404(client):
    response = client.post("/agent/plans/999999/run", json={})

    assert response.status_code == 404
    assert response.json()["detail"] == "agent_plan_not_found"

