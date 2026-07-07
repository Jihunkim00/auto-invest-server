from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, TradeRunLog
from app.main import app
from app.routes.agent_chat import get_agent_chat_orchestrator_service
from app.routes.strategy_positions import get_position_management_dry_run_service
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService
from app.services.agent_chat_tool_executor import AgentChatToolExecutor
from app.services.auto_exit_candidate_service import AutoExitCandidateService
from app.services.position_exit_review_service import PositionExitReviewService
from app.services.position_management_dry_run_service import (
    PositionManagementDryRunService,
)
from app.tests.test_agent_chat_strategy_dry_run_auto_buy import _router_settings


def _settings():
    return Settings(
        _env_file=None,
        alpaca_api_key="test-key",
        alpaca_secret_key="test-secret",
        alpaca_base_url="https://paper-api.alpaca.markets",
        kis_enabled=True,
        kis_env="prod",
        kis_app_key="real-app-key",
        kis_app_secret="real-app-secret",
        kis_account_no="12345678",
        kis_account_product_code="01",
        kis_base_url="https://openapi.koreainvestment.com:9443",
        kis_real_order_enabled=True,
        kis_scheduler_allow_real_orders=False,
        kr_scheduler_allow_real_orders=False,
    )


def _open_session(*args, **kwargs):
    return {
        "market": "KR",
        "timezone": "Asia/Seoul",
        "is_market_open": True,
        "is_entry_allowed_now": True,
        "is_near_close": False,
    }


def _position(**overrides):
    payload = {
        "symbol": "005930",
        "name": "Samsung Electronics",
        "qty": 3,
        "available_quantity": 3,
        "current_price": 9000,
        "avg_entry_price": 10000,
        "cost_basis": 30000,
        "current_value": 27000,
        "unrealized_pl": -3000,
    }
    payload.update(overrides)
    return payload


class _FakeKisClient:
    def __init__(
        self,
        positions: list[dict] | None = None,
        open_orders: list[dict] | None = None,
    ):
        self.settings = SimpleNamespace(
            kis_enabled=True,
            kis_real_order_enabled=True,
        )
        self.positions = list(positions if positions is not None else [_position()])
        self.open_orders = list(open_orders if open_orders is not None else [])

    def list_positions(self):
        return list(self.positions)

    def list_open_orders(self):
        return list(self.open_orders)


@pytest.fixture()
def client(monkeypatch, db_session):
    fake_client = _FakeKisClient()
    service = _service(fake_client)

    def override_get_db():
        yield db_session

    def override_service():
        return service

    monkeypatch.setattr("app.routes.strategy_positions.get_settings", _settings)
    monkeypatch.setattr(
        "app.services.position_exit_review_service.MarketSessionService.get_session_status",
        _open_session,
    )
    monkeypatch.setattr(
        "app.services.auto_exit_candidate_service.MarketSessionService.get_session_status",
        _open_session,
    )
    db_session.add(
        RuntimeSetting(
            dry_run=False,
            kill_switch=False,
            position_management_scheduler_enabled=False,
            position_management_scheduler_dry_run_only=True,
            position_management_scheduler_allow_live_orders=False,
        )
    )
    db_session.commit()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_position_management_dry_run_service] = override_service
    try:
        yield TestClient(app), db_session, fake_client
    finally:
        app.dependency_overrides.clear()


def _service(fake_client: _FakeKisClient) -> PositionManagementDryRunService:
    exit_review = PositionExitReviewService(fake_client)
    return PositionManagementDryRunService(
        auto_exit_candidates=AutoExitCandidateService(exit_review),
        exit_review_service=exit_review,
    )


def test_position_management_dry_run_endpoint_returns_safe_counts(client):
    test_client, db_session, _ = client

    response = test_client.post("/strategy/positions/management/run-dry-run-once")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] is not None
    assert body["dry_run_only"] is True
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["priority"] == "positions_first"
    assert body["entry_orders_allowed"] is False
    assert body["exit_orders_allowed"] is False
    assert body["dry_run_monitoring_only"] is True
    assert body["positions_checked"] == 1
    assert body["exit_candidate_count"] >= 1
    assert body["critical_candidate_count"] == 1
    assert body["simulated_sell_preflight_count"] == 1
    assert body["result_status"] == "completed"

    row = db_session.get(TradeRunLog, body["run_id"])
    assert row is not None
    assert row.mode == "position_management_dry_run"
    assert db_session.query(OrderLog).count() == 0


def test_position_management_surfaces_duplicate_sell_conflict(client):
    test_client, db_session, _ = client
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="sell",
            order_type="market",
            internal_status=InternalOrderStatus.REQUESTED.value,
        )
    )
    db_session.commit()

    body = test_client.post(
        "/strategy/positions/management/run-dry-run-once",
    ).json()

    assert body["duplicate_sell_conflict_count"] == 1
    assert any(
        item["candidate_type"] == "duplicate_sell_conflict"
        for item in body["candidates"]
    )
    assert body["simulated_sell_preflight_count"] == 0


def test_position_management_surfaces_sync_required(client):
    test_client, db_session, _ = client
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="buy",
            order_type="market",
            internal_status=InternalOrderStatus.UNKNOWN_STALE.value,
            created_at=datetime.now(UTC) - timedelta(minutes=30),
        )
    )
    db_session.commit()

    body = test_client.post(
        "/strategy/positions/management/run-dry-run-once",
    ).json()

    assert body["sync_required_count"] == 1
    assert any(item["candidate_type"] == "sync_required" for item in body["candidates"])
    assert body["simulated_sell_preflight_count"] == 0


def test_position_management_dry_run_does_not_call_submit_paths(
    monkeypatch,
    client,
):
    test_client, db_session, _ = client

    def fail(*args, **kwargs):
        raise AssertionError("submit path must not be called")

    monkeypatch.setattr(
        "app.services.position_exit_review_service.PositionExitReviewService.guarded_sell",
        fail,
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        fail,
    )
    monkeypatch.setattr(
        "app.brokers.kis_broker.KisBroker.submit_market_sell",
        fail,
        raising=False,
    )

    body = test_client.post(
        "/strategy/positions/management/run-dry-run-once",
    ).json()

    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert db_session.query(OrderLog).count() == 0


def test_position_management_dry_run_does_not_create_runtime_settings(
    monkeypatch,
    db_session,
):
    monkeypatch.setattr(
        "app.services.position_exit_review_service.MarketSessionService.get_session_status",
        _open_session,
    )
    monkeypatch.setattr(
        "app.services.auto_exit_candidate_service.MarketSessionService.get_session_status",
        _open_session,
    )
    assert db_session.query(RuntimeSetting).count() == 0

    body = _service(_FakeKisClient()).run_once(
        db_session,
        {"include_sell_preflight": True},
    )

    assert body["result_status"] == "completed"
    assert body["simulated_sell_preflight_count"] == 1
    assert db_session.query(RuntimeSetting).count() == 0
    assert db_session.query(TradeRunLog).count() == 1
    assert db_session.query(OrderLog).count() == 0


def test_position_management_scheduler_default_disabled_blocks(db_session):
    fake_client = _FakeKisClient()
    db_session.add(
        RuntimeSetting(
            dry_run=False,
            kill_switch=False,
            position_management_scheduler_enabled=False,
            position_management_scheduler_dry_run_only=True,
            position_management_scheduler_allow_live_orders=False,
        )
    )
    db_session.commit()

    body = _service(fake_client).run_once(
        db_session,
        {"trigger_source": "position_management_dry_run"},
        require_enabled=True,
    )

    assert body["result_status"] == "blocked"
    assert body["primary_reason"] == "position_management_scheduler_disabled"
    assert body["dry_run_only"] is True
    assert body["scheduler_allow_live_orders"] is False
    assert body["exit_candidate_count"] == 0


def test_position_management_agent_chat_summarizes_latest_read_only(
    monkeypatch,
    client,
):
    test_client, db_session, _ = client
    run = test_client.post("/strategy/positions/management/run-dry-run-once").json()
    assert run["run_id"] is not None

    def orchestrator_service():
        return AgentChatOrchestratorService(
            intent_router=AgentChatIntentRouterService(settings=_router_settings()),
            tool_executor=AgentChatToolExecutor(
                kis_client_factory=lambda db: _FakeKisClient(),
            ),
        )

    app.dependency_overrides[get_agent_chat_orchestrator_service] = orchestrator_service
    try:
        response = test_client.post(
            "/agent/chat/send",
            json={
                "message": "Show position management dry-run status",
                "auto_create_conversation": True,
            },
        )
    finally:
        app.dependency_overrides.pop(get_agent_chat_orchestrator_service, None)

    body = response.json()
    assert response.status_code == 200
    assert body["intent"]["category"] == "strategy_position_management_dry_run_query"
    assert body["selected_tools"][0]["tool_name"] == "position_management_dry_run_latest_lookup"
    assert body["tool_results"][0]["result_type"] == "position_management_dry_run"
    assert body["tool_results"][0]["data"]["run_id"] == run["run_id"]
    assert body["live_order_action"] is None
    assert body["safety"]["broker_submit_called"] is False
    assert "did not start a dry-run" in body["answer"]["text"]


def test_position_management_service_has_no_direct_sell_submit_references():
    source = open(
        "app/services/position_management_dry_run_service.py",
        encoding="utf-8",
    ).read()
    forbidden = [
        "submit_market_sell",
        "submit_order",
        "submit_domestic_cash_order",
        "submit_manual(",
        "confirm_live",
        "liquidate",
        "force_sell",
        "auto_sell",
    ]
    for token in forbidden:
        assert token not in source
