from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting
from app.main import app
from app.routes.strategy_risk import get_target_aware_risk_service
from app.tests.test_target_aware_risk_service import _service


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_target_aware_risk_service] = lambda: _service()
    try:
        yield TestClient(app), db_session
    finally:
        app.dependency_overrides.clear()


def test_risk_state_returns_profile_daily_and_monthly_fields(client):
    test_client, _ = client

    response = test_client.get("/strategy/risk-state?provider=kis&market=KR")

    assert response.status_code == 200
    body = response.json()
    assert body["active_profile"] == "safe"
    assert body["current_month_return_pct"] == 0
    assert body["current_daily_return_pct"] == 0
    assert body["trades_remaining_today"] == 1
    assert body["safety"]["validation_called"] is False


def test_risk_state_is_read_only_and_does_not_submit_or_change_settings(client):
    test_client, db_session = client
    before_settings = db_session.query(RuntimeSetting).count()

    response = test_client.get("/strategy/risk-state")

    assert response.status_code == 200
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(RuntimeSetting).count() == before_settings
    assert response.json()["safety"]["real_order_submitted"] is False
    assert response.json()["safety"]["setting_changed"] is False
