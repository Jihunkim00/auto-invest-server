from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import StrategyLiveAutoExitAttempt
from app.main import app
from app.routes.strategy_live_exit import (
    get_profile_aware_guarded_live_auto_exit_service,
)
from app.tests.test_strategy_live_auto_exit_service import (
    FakeBroker,
    enable_live_exit_settings,
    live_exit_service,
    stop_loss_position,
)


@pytest.fixture()
def client(db_session):
    broker = FakeBroker()
    route_service = live_exit_service(
        broker=broker,
        positions=[stop_loss_position()],
    )

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_profile_aware_guarded_live_auto_exit_service] = (
        lambda: route_service
    )
    try:
        yield TestClient(app), db_session, broker
    finally:
        app.dependency_overrides.clear()


def test_readiness_route_is_read_only_by_default(client):
    test_client, db_session, broker = client

    response = test_client.get("/strategy/live/auto-exit/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is False
    assert body["primary_block_reason"] == "strategy_live_auto_exit_disabled"
    assert body["candidate_count"] == 1
    assert body["candidates"][0]["trigger"] == "stop_loss"
    assert body["safety"]["read_only"] is True
    assert broker.calls == []
    assert db_session.query(StrategyLiveAutoExitAttempt).count() == 0


def test_run_once_route_rejects_unknown_fields(client):
    test_client, _, _ = client

    response = test_client.post(
        "/strategy/live/auto-exit/run-once",
        json={
            "confirm_operator_ack": True,
            "enable_scheduler": True,
        },
    )

    assert response.status_code == 422


def test_run_once_and_recent_routes(client):
    test_client, db_session, broker = client
    enable_live_exit_settings(db_session)

    run = test_client.post(
        "/strategy/live/auto-exit/run-once",
        json={
            "confirm_operator_ack": True,
            "trigger_source": "route-test",
            "client_request_id": "route-exit-once",
        },
    )
    recent = test_client.get("/strategy/live/auto-exit/recent?limit=5")

    assert run.status_code == 200
    assert run.json()["status"] == "submitted"
    assert run.json()["submitted"] is True
    assert broker.calls == [{"symbol": "005930", "qty": 3}]
    assert recent.status_code == 200
    assert recent.json()["count"] == 1
    assert recent.json()["items"][0]["status"] == "submitted"
    assert recent.json()["safety"]["read_only"] is True
