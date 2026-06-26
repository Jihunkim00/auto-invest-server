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


class FakeSchedulerStatusService:
    def __init__(self):
        self.status_calls = 0

    def status(self, db, **kwargs):
        self.status_calls += 1
        return {
            "enabled": False,
            "dry_run_only": True,
            "allow_live_orders": False,
            "active_profile": "safe",
            "allowed_profiles": ["safe", "balanced"],
            "runs_today": 0,
            "max_runs_per_day": 3,
            "next_allowed_run_at": None,
            "min_minutes_between_runs": 60,
            "market_open": True,
            "after_no_new_entry_time": False,
            "primary_block_reason": "scheduler_disabled",
            "pending_promotion_count": 1,
            "latest_scheduler_run": None,
            "schedule_slots": ["09:10", "10:30", "14:30"],
            "safety": {
                "read_only": True,
                "validation_called": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "setting_changed": False,
                "scheduler_changed": False,
            },
        }

    def run_dry_run_once(self, db, request):
        raise AssertionError("Agent Chat must not run scheduler dry-run")


class FakePromotionQueueService:
    def __init__(self):
        self.list_calls = 0

    def list(self, db, **kwargs):
        self.list_calls += 1
        return {
            "provider": "kis",
            "market": "KR",
            "count": 1,
            "items": [
                {
                    "id": 1,
                    "provider": "kis",
                    "market": "KR",
                    "active_profile": "safe",
                    "symbol": "005930",
                    "symbol_name": "Samsung Electronics",
                    "status": "pending",
                    "promotion_reason": "target_aware_risk_approved",
                    "source_dry_run_trade_run_id": 22,
                    "dry_run_action": "would_buy",
                    "final_score": 82,
                    "recommended_notional_krw": 30000,
                    "simulated_quantity": 3,
                    "expires_at": "2026-06-26T01:45:00+00:00",
                    "risk_flags": ["dry_run_only"],
                    "gating_notes": ["promotion only"],
                    "request_payload": {},
                    "response_payload": {},
                }
            ],
            "safety": {
                "read_only": True,
                "validation_called": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "setting_changed": False,
                "scheduler_changed": False,
            },
        }

    def acknowledge(self, db, promotion_id):
        raise AssertionError("Agent Chat must not acknowledge promotions in PR78")

    def dismiss(self, db, promotion_id):
        raise AssertionError("Agent Chat must not dismiss promotions in PR78")


@pytest.fixture()
def client(db_session):
    scheduler = FakeSchedulerStatusService()
    promotions = FakePromotionQueueService()

    def override_get_db():
        yield db_session

    def orchestrator_service():
        return AgentChatOrchestratorService(
            intent_router=AgentChatIntentRouterService(settings=_router_settings()),
            tool_executor=AgentChatToolExecutor(
                auto_buy_scheduler_service_factory=lambda db: scheduler,
                auto_buy_promotion_service_factory=lambda db: promotions,
            ),
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_agent_chat_orchestrator_service] = (
        orchestrator_service
    )
    try:
        yield TestClient(app), db_session, scheduler, promotions
    finally:
        app.dependency_overrides.clear()


def test_agent_chat_scheduler_status_query_is_read_only(client):
    test_client, db_session, scheduler, _ = client

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "Show auto buy scheduler status",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["intent"]["category"] == "strategy_auto_buy_scheduler_status_query"
    assert body["selected_tools"][0]["tool_name"] == (
        "strategy_auto_buy_scheduler_status_lookup"
    )
    assert body["tool_results"][0]["result_type"] == (
        "strategy_auto_buy_scheduler_status"
    )
    assert body["tool_results"][0]["data"]["allow_live_orders"] is False
    assert body["tool_results"][0]["safety"]["read_only"] is True
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["validation_called"] is False
    assert body["safety"]["broker_submit_called"] is False
    assert body["safety"]["manual_submit_called"] is False
    assert body["safety"]["scheduler_changed"] is False
    assert scheduler.status_calls == 1
    assert db_session.query(AgentChatOrderAction).count() == 0
    assert db_session.query(StrategyLiveAutoBuyAttempt).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0
    assert db_session.query(OrderLog).count() == 0
    card = body["result_cards"][0]
    assert card["card_type"] == "strategy_auto_buy_scheduler_status"
    assert "SCHEDULED DRY RUN" in card["badges"]
    assert "NO LIVE SCHEDULER" in card["badges"]
    assert "NO VALIDATION" in card["badges"]
    assert "NO BROKER SUBMIT" in card["badges"]


def test_agent_chat_promotion_queue_query_is_read_only(client):
    test_client, db_session, _, promotions = client

    response = test_client.post(
        "/agent/chat/send",
        json={
            "message": "What is in the auto buy promotion queue?",
            "auto_create_conversation": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["intent"]["category"] == "strategy_auto_buy_promotion_queue_query"
    assert body["selected_tools"][0]["tool_name"] == (
        "strategy_auto_buy_promotions_lookup"
    )
    assert body["tool_results"][0]["result_type"] == "strategy_auto_buy_promotions"
    assert body["tool_results"][0]["data"]["items"][0]["symbol"] == "005930"
    assert body["live_order_action"] is None
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["validation_called"] is False
    assert body["safety"]["broker_submit_called"] is False
    assert promotions.list_calls == 1
    assert db_session.query(AgentChatOrderAction).count() == 0
    assert db_session.query(StrategyLiveAutoBuyAttempt).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0
    assert db_session.query(OrderLog).count() == 0
    card = body["result_cards"][0]
    assert card["card_type"] == "strategy_auto_buy_promotions"
    assert "PROMOTION ONLY" in card["badges"]
    assert "NO CHAT EXECUTION" in card["badges"]
    assert "NO VALIDATION" in card["badges"]
    assert "NO BROKER SUBMIT" in card["badges"]
