from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import StrategyPerformanceSnapshot
from app.main import app
from app.routes.strategy_performance import get_strategy_performance_service
from app.services.strategy_performance_service import StrategyPerformanceService


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_strategy_performance_service] = lambda: (
        StrategyPerformanceService(position_loader=lambda db, provider, market: [])
    )
    try:
        yield TestClient(app), db_session
    finally:
        app.dependency_overrides.clear()


def test_daily_monthly_and_trades_routes_are_read_only(client):
    test_client, _ = client

    daily = test_client.get("/performance/daily")
    monthly = test_client.get("/performance/monthly")
    trades = test_client.get("/performance/trades")

    assert daily.status_code == 200
    assert monthly.status_code == 200
    assert trades.status_code == 200
    assert daily.json()["safety"]["real_order_submitted"] is False
    assert monthly.json()["safety"]["validation_called"] is False
    assert trades.json()["safety"]["scheduler_changed"] is False


def test_snapshot_route_saves_performance_snapshot_only(client):
    test_client, db_session = client

    response = test_client.post(
        "/performance/snapshot",
        json={
            "provider": "kis",
            "market": "KR",
            "period_type": "monthly",
        },
    )

    assert response.status_code == 200
    assert db_session.query(StrategyPerformanceSnapshot).count() == 1
    assert response.json()["safety"]["snapshot_write_only"] is True
    assert response.json()["safety"]["real_order_submitted"] is False
