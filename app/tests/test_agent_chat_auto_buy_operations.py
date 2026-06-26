from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import (
    AgentChatOrderAction,
    KisOrderValidationLog,
    OrderLog,
    StrategyLiveAutoBuyAttempt,
)
from app.main import app
from app.routes.agent_chat import get_agent_chat_orchestrator_service
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService
from app.services.agent_chat_tool_executor import AgentChatToolExecutor
from app.tests.test_agent_chat_strategy_dry_run_auto_buy import _router_settings


class FakeOperationsStatusService:
    def __init__(self):
        self.calls = 0

    def status(self, db, **kwargs):
        self.calls += 1
        return {
            "provider": "kis",
            "market": "KR",
            "active_profile": "safe",
            "auto_buy_stage": "live_readiness_blocked",
            "next_operator_action": "enable_prerequisites_manually",
            "dry_run": {
                "recent_found": True,
                "latest_action": "would_buy",
                "latest_symbol": "005930",
                "latest_score": 80,
                "latest_time": "2026-06-26T01:00:00Z",
                "would_buy_count_today": 1,
                "blocked_count_today": 0,
                "summary": {"total": 1, "would_buy": 1},
            },
            "live_readiness": {
                "ready": False,
                "enabled": True,
                "primary_block_reason": "target_risk_rejected",
                "recent_dry_run_required": True,
                "recent_dry_run_found": True,
                "dry_run_status": "would_buy",
                "kill_switch": False,
                "kis_real_order_enabled": True,
                "target_risk_ready": False,
                "orders_remaining_today": 1,
            },
            "live_attempts": {
                "latest_status": None,
                "submitted_count_today": 0,
                "blocked_count_today": 0,
                "sync_required_count": 0,
                "recent": [],
            },
            "risk": {
                "entry_allowed": False,
                "size_multiplier": 0.5,
                "target_progress_pct": 88.0,
                "daily_loss_limit_hit": False,
                "monthly_loss_limit_hit": False,
            },
            "safety": {
                "read_only": True,
                "validation_called": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "setting_changed": False,
                "scheduler_changed": False,
            },
        }


@pytest.fixture()
def client(db_session):
    operations_service = FakeOperationsStatusService()

    def override_get_db():
        yield db_session

    def orchestrator_service():
        return AgentChatOrchestratorService(
            intent_router=AgentChatIntentRouterService(settings=_router_settings()),
            tool_executor=AgentChatToolExecutor(
                auto_buy_operations_service_factory=lambda db: operations_service,
            ),
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_agent_chat_orchestrator_service] = (
        orchestrator_service
    )
    try:
        yield TestClient(app), db_session, operations_service
    finally:
        app.dependency_overrides.clear()


def test_agent_chat_auto_buy_operations_status_is_read_only(client):
    test_client, db_session, operations_service = client

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "Show auto buy operations status",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["intent"]["category"] == "strategy_auto_buy_operations_status_query"
    assert body["selected_tools"][0]["tool_name"] == (
        "strategy_auto_buy_operations_status_lookup"
    )
    assert body["tool_results"][0]["result_type"] == (
        "strategy_auto_buy_operations_status"
    )
    assert body["tool_results"][0]["data"]["auto_buy_stage"] == (
        "live_readiness_blocked"
    )
    assert body["tool_results"][0]["data"]["safety"]["read_only"] is True
    assert body["tool_results"][0]["safety"]["read_only"] is True
    assert body["live_order_action"] is None
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["validation_called"] is False
    assert body["safety"]["broker_submit_called"] is False
    assert db_session.query(AgentChatOrderAction).count() == 0
    assert db_session.query(StrategyLiveAutoBuyAttempt).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0
    assert db_session.query(OrderLog).count() == 0
    assert operations_service.calls == 1
    card = body["result_cards"][0]
    assert card["card_type"] == "strategy_auto_buy_operations_status"
    assert "AUTO BUY OPS" in card["badges"]
    assert "READ ONLY" in card["badges"]
    assert "NO CHAT EXECUTION" in card["badges"]
    assert "NO VALIDATION" in card["badges"]
    assert "NO BROKER SUBMIT" in card["badges"]


def test_agent_chat_auto_buy_next_action_uses_operations_lookup(client):
    test_client, _, _ = client

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "What is the auto buy next action for the operator?",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["intent"]["category"] == "strategy_auto_buy_next_action_query"
    assert body["selected_tools"][0]["tool_name"] == (
        "strategy_auto_buy_operations_status_lookup"
    )
    assert body["answer"]["answer_type"] == (
        "strategy_auto_buy_operations_answer"
    )
    assert "enable_prerequisites_manually" in body["answer"]["text"]


def test_agent_chat_auto_buy_block_reason_does_not_create_live_order_action(client):
    test_client, db_session, _ = client

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "Why is auto buy operations blocked?",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["intent"]["category"] == "strategy_auto_buy_block_reason_query"
    assert body["selected_tools"][0]["tool_name"] == (
        "strategy_auto_buy_operations_status_lookup"
    )
    assert body["tool_results"][0]["data"]["live_readiness"][
        "primary_block_reason"
    ] == "target_risk_rejected"
    assert body["live_order_action"] is None
    assert db_session.query(AgentChatOrderAction).count() == 0
    assert db_session.query(StrategyLiveAutoBuyAttempt).count() == 0
