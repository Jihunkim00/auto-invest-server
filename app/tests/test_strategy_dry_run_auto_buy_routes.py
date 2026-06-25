from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.routes.strategy_dry_run import (
    get_profile_aware_dry_run_auto_buy_service,
)
from app.tests.test_strategy_dry_run_auto_buy_service import (
    candidate,
    preview,
    service,
)


class RouteService:
    def __init__(self):
        self.inner = service()

    def run_once(self, db, request):
        return self.inner.run_once(
            db,
            request,
            preview_override=preview(candidate()),
        )

    def recent(self, db, **kwargs):
        return self.inner.recent(db, **kwargs)

    def summary(self, db, **kwargs):
        return self.inner.summary(db, **kwargs)


@pytest.fixture()
def client(db_session):
    route_service = RouteService()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_profile_aware_dry_run_auto_buy_service] = (
        lambda: route_service
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_auto_buy_once_and_recent_routes(client):
    run = client.post(
        "/strategy/dry-run/auto-buy-once",
        json={"profile_name": "balanced"},
    )
    recent = client.get(
        "/strategy/dry-run/recent?provider=kis&market=KR&limit=20"
    )

    assert run.status_code == 200
    assert run.json()["action"] == "would_buy"
    assert run.json()["active_profile"] == "balanced"
    assert recent.status_code == 200
    assert recent.json()["count"] == 1
    assert recent.json()["items"][0]["selected_symbol"] == "005930"


def test_summary_route_returns_action_counts(client):
    client.post("/strategy/dry-run/auto-buy-once", json={})

    response = client.get("/strategy/dry-run/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["today"]["would_buy"] == 1
    assert body["month"]["total"] == 1
    assert body["profiles"]["safe"]["would_buy"] == 1
