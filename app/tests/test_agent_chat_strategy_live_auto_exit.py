from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import (
    AgentChatOrderAction,
    KisOrderValidationLog,
    OrderLog,
    StrategyLiveAutoExitAttempt,
)
from app.main import app
from app.routes.agent_chat import get_agent_chat_orchestrator_service
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService
from app.services.agent_chat_tool_executor import AgentChatToolExecutor
from app.tests.test_agent_chat_strategy_dry_run_auto_buy import _router_settings
from app.tests.test_strategy_live_auto_exit_service import (
    FakeBroker,
    enable_live_exit_settings,
    live_exit_request,
    live_exit_service,
    stop_loss_position,
)


class _FakeKisClient:
    def __init__(self, positions: list[dict]):
        self.settings = SimpleNamespace(
            kis_enabled=True,
            kis_real_order_enabled=True,
        )
        self.positions = positions

    def list_positions(self):
        return list(self.positions)

    def list_open_orders(self):
        return []


def _candidate_position():
    position = stop_loss_position()
    cost_basis = position["quantity"] * position["avg_entry_price"]
    return {
        **position,
        "qty": position["quantity"],
        "available_quantity": position["quantity"],
        "cost_basis": cost_basis,
        "unrealized_pl": position["current_value"] - cost_basis,
    }


@pytest.fixture()
def client(db_session):
    broker = FakeBroker()
    chat_live_exit_service = live_exit_service(
        broker=broker,
        positions=[stop_loss_position()],
    )

    def override_get_db():
        yield db_session

    def orchestrator_service():
        return AgentChatOrchestratorService(
            intent_router=AgentChatIntentRouterService(settings=_router_settings()),
            tool_executor=AgentChatToolExecutor(
                kis_client_factory=lambda db: _FakeKisClient([_candidate_position()]),
                live_auto_exit_service_factory=lambda db: chat_live_exit_service,
            ),
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_agent_chat_orchestrator_service] = orchestrator_service
    try:
        yield TestClient(app), db_session, chat_live_exit_service, broker
    finally:
        app.dependency_overrides.clear()


def test_agent_chat_live_auto_exit_readiness_is_read_only(client):
    test_client, db_session, _, broker = client

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "Is strategy live auto exit readiness available?",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["intent"]["category"] == "strategy_live_auto_exit_readiness_query"
    assert body["selected_tools"][0]["tool_name"] == "strategy_live_auto_exit_readiness_lookup"
    assert body["tool_results"][0]["result_type"] == "strategy_live_auto_exit_readiness"
    assert body["tool_results"][0]["data"]["candidate_count"] == 1
    assert body["tool_results"][0]["data"]["safety"]["read_only"] is True
    assert body["live_order_action"] is None
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["validation_called"] is False
    assert body["safety"]["broker_submit_called"] is False
    assert broker.calls == []
    assert db_session.query(AgentChatOrderAction).count() == 0
    assert db_session.query(StrategyLiveAutoExitAttempt).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0
    assert db_session.query(OrderLog).count() == 0
    badges = body["result_cards"][0]["badges"]
    assert "READ ONLY" in badges
    assert "LIVE AUTO EXIT" in badges
    assert "NO CHAT EXECUTION" in badges
    assert "NO VALIDATION" in badges
    assert "NO BROKER SUBMIT" in badges


def test_agent_chat_exit_candidate_lookup_is_read_only(client):
    test_client, db_session, _, broker = client

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "Show strategy exit candidates for held positions",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["intent"]["category"] == "strategy_exit_candidate_query"
    assert body["selected_tools"][0]["tool_name"] == "strategy_exit_candidate_lookup"
    assert body["tool_results"][0]["result_type"] == "strategy_exit_candidate"
    assert body["tool_results"][0]["data"]["candidates"][0]["candidate_type"] == "stop_loss"
    assert body["live_order_action"] is None
    assert body["safety"]["validation_called"] is False
    assert broker.calls == []
    assert db_session.query(StrategyLiveAutoExitAttempt).count() == 0


def test_agent_chat_live_auto_exit_recent_does_not_submit_again(client):
    test_client, db_session, chat_live_exit_service, broker = client
    enable_live_exit_settings(db_session)
    submitted = chat_live_exit_service.run_once(
        db_session,
        live_exit_request(client_request_id="chat-exit-seed"),
    )
    assert submitted["status"] == "submitted"
    assert broker.calls == [{"symbol": "005930", "qty": 3}]

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "Show recent strategy live auto exit results",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["intent"]["category"] == "strategy_live_auto_exit_recent_query"
    assert body["selected_tools"][0]["tool_name"] == "strategy_live_auto_exit_recent_lookup"
    assert body["tool_results"][0]["data"]["count"] == 1
    assert body["tool_results"][0]["data"]["safety"]["read_only"] is True
    assert body["live_order_action"] is None
    assert broker.calls == [{"symbol": "005930", "qty": 3}]
    assert db_session.query(StrategyLiveAutoExitAttempt).count() == 1
    assert db_session.query(AgentChatOrderAction).count() == 0
