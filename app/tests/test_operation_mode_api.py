from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.routes.app_facade import get_operation_mode_service
from app.services.operation_mode_service import OperationModeService
from app.services.runtime_setting_service import RuntimeSettingService
from app.tests.test_operation_mode_service import FakeRelease


@pytest.fixture()
def client(db_session):
    service = OperationModeService(
        runtime_settings=RuntimeSettingService(),
        automation_release_service=FakeRelease(blocking=["watchdog_unhealthy"]),
    )

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_operation_mode_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_get_operation_mode_endpoint(client):
    response = client.get("/app/operation-mode")

    assert response.status_code == 200
    body = response.json()
    assert body["requested_mode"] == "paper"
    assert body["effective_mode"] == "paper"
    assert body["requires_acknowledgement"]["live"] is True
    assert body["underlying_state"]["broker_submit_called"] is False


def test_put_operation_mode_paper_success(client):
    response = client.put(
        "/app/operation-mode",
        json={"mode": "paper", "reason": "paper api test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requested_mode"] == "paper"
    assert body["changed"] is False
    assert body["status"] == "unchanged"
    assert body["audit_id"] is not None


def test_put_operation_mode_live_requires_acknowledgement(client):
    response = client.put(
        "/app/operation-mode",
        json={"mode": "live", "acknowledged": False},
    )

    assert response.status_code == 422
    assert "acknowledged=true" in response.json()["detail"]


def test_put_operation_mode_live_blocked_returns_top_level_409(client):
    response = client.put(
        "/app/operation-mode",
        json={
            "mode": "live",
            "acknowledged": True,
            "reason": "blocked api test",
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["changed"] is False
    assert body["requested_mode"] == "live"
    assert body["status"] == "blocked"
    assert body["blocking_reasons"][0]["code"] == "watchdog_unhealthy"
    assert "detail" not in body


def test_put_operation_mode_rejects_unknown_mode(client):
    response = client.put(
        "/app/operation-mode",
        json={"mode": "production"},
    )

    assert response.status_code == 422
