from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import StrategyLiveAutoBuyAttempt
from app.main import app
from app.routes.strategy_live import get_profile_aware_guarded_live_auto_buy_service
from app.tests.test_strategy_live_auto_buy_service import (
    FakeBroker,
    add_dry_run,
    enable_live_settings,
    live_service,
)


@pytest.fixture()
def client(db_session):
    broker = FakeBroker()
    route_service = live_service(broker=broker)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_profile_aware_guarded_live_auto_buy_service] = (
        lambda: route_service
    )
    try:
        yield TestClient(app), db_session, broker
    finally:
        app.dependency_overrides.clear()


def test_readiness_route_is_read_only_by_default(client):
    test_client, db_session, broker = client

    response = test_client.get("/strategy/live/auto-buy/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is False
    assert body["primary_block_reason"] == "strategy_live_auto_buy_disabled"
    assert body["safety"]["read_only"] is True
    assert broker.calls == []
    assert db_session.query(StrategyLiveAutoBuyAttempt).count() == 0


def test_run_once_route_rejects_unknown_fields(client):
    test_client, _, _ = client

    response = test_client.post(
        "/strategy/live/auto-buy/run-once",
        json={
            "confirm_operator_ack": True,
            "enable_scheduler": True,
        },
    )

    assert response.status_code == 422


def test_run_once_and_recent_routes(client):
    test_client, db_session, broker = client
    enable_live_settings(db_session)
    dry_run = add_dry_run(db_session)

    run = test_client.post(
        "/strategy/live/auto-buy/run-once",
        json={
            "confirm_operator_ack": True,
            "source_dry_run_id": dry_run.id,
            "trigger_source": "route-test",
            "client_request_id": "route-once",
        },
    )
    recent = test_client.get("/strategy/live/auto-buy/recent?limit=5")

    assert run.status_code == 200
    assert run.json()["status"] == "submitted"
    assert run.json()["submitted"] is True
    assert broker.calls == [{"symbol": "005930", "qty": 3}]
    assert recent.status_code == 200
    assert recent.json()["count"] == 1
    assert recent.json()["items"][0]["status"] == "submitted"
    assert recent.json()["safety"]["read_only"] is True
