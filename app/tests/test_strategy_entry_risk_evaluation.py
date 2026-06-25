from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import KisOrderValidationLog, OrderLog, RuntimeSetting
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


def test_evaluate_entry_returns_target_aware_decision(client):
    test_client, _ = client

    response = test_client.post(
        "/strategy/risk/evaluate-entry",
        json={
            "provider": "kis",
            "market": "KR",
            "symbol": "005930",
            "side": "buy",
            "requested_notional_krw": 20_000,
            "buy_score": 80,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approved"] is True
    assert body["active_profile"] == "safe"
    assert body["profile_thresholds"]["buy_score_threshold"] == 75
    assert body["safety"]["validation_called"] is False


def test_evaluate_entry_does_not_submit_validate_or_mutate_settings(client):
    test_client, db_session = client
    before_settings = db_session.query(RuntimeSetting).count()

    response = test_client.post(
        "/strategy/risk/evaluate-entry",
        json={
            "symbol": "005930",
            "side": "buy",
            "requested_notional_krw": 20_000,
            "buy_score": 80,
        },
    )

    assert response.status_code == 200
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0
    assert db_session.query(RuntimeSetting).count() == before_settings
    safety = response.json()["safety"]
    assert safety["broker_submit_called"] is False
    assert safety["manual_submit_called"] is False
    assert safety["setting_changed"] is False
