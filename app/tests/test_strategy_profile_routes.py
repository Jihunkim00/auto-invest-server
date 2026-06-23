from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_get_strategy_profiles_returns_presets_and_active_safe(client):
    response = client.get("/strategy/profiles")

    assert response.status_code == 200
    body = response.json()
    assert [item["profile_name"] for item in body["profiles"]] == [
        "safe",
        "balanced",
        "aggressive",
    ]
    assert body["active_profile"]["profile_name"] == "safe"
    assert body["profiles"][0]["is_active"] is True


def test_get_active_strategy_profile(client):
    response = client.get("/strategy/profiles/active")

    assert response.status_code == 200
    assert response.json()["active_profile"]["profile_name"] == "safe"


def test_apply_preset_requires_ack(client):
    response = client.post(
        "/strategy/profiles/apply-preset",
        json={
            "profile_name": "balanced",
            "confirm_operator_ack": False,
            "source": "settings_ui",
        },
    )

    assert response.status_code == 409
    assert client.get("/strategy/profiles/active").json()["active_profile"]["profile_name"] == "safe"


def test_apply_preset_changes_active_profile_with_ack(client):
    response = client.post(
        "/strategy/profiles/apply-preset",
        json={
            "profile_name": "balanced",
            "confirm_operator_ack": True,
            "source": "settings_ui",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["active_profile"]["profile_name"] == "balanced"
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["validation_called"] is False
    assert body["safety"]["scheduler_changed"] is False


def test_invalid_profile_blocks_update(client):
    response = client.post(
        "/strategy/profiles/apply-preset",
        json={
            "profile_name": "invalid",
            "confirm_operator_ack": True,
            "source": "settings_ui",
        },
    )

    assert response.status_code == 422
    assert client.get("/strategy/profiles/active").json()["active_profile"]["profile_name"] == "safe"


def test_monthly_progress_and_risk_budget_return_active_profile_thresholds(client):
    client.post(
        "/strategy/profiles/apply-preset",
        json={
            "profile_name": "aggressive",
            "confirm_operator_ack": True,
            "source": "settings_ui",
        },
    )

    progress = client.get("/strategy/monthly-progress")
    risk = client.get("/strategy/risk-budget")

    assert progress.status_code == 200
    assert progress.json()["active_profile"]["profile_name"] == "aggressive"
    assert progress.json()["target_min_pct"] == 0.05
    assert progress.json()["skeleton"] is True
    assert risk.status_code == 200
    assert risk.json()["monthly_max_loss_pct"] == -0.06
    assert risk.json()["max_order_notional_krw"] == 80000
    assert risk.json()["safety"]["real_order_submitted"] is False

