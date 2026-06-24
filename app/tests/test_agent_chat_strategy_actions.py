from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import AgentChatStrategyAction, KisOrderValidationLog, OrderLog
from app.main import app
from app.routes.agent_chat import get_agent_chat_orchestrator_service
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.strategy_profile_service import StrategyProfileService


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    def orchestrator_service():
        return AgentChatOrchestratorService(
            intent_router=AgentChatIntentRouterService(settings=_router_settings()),
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_agent_chat_orchestrator_service] = orchestrator_service
    try:
        yield TestClient(app), db_session
    finally:
        app.dependency_overrides.clear()


def test_strategy_action_confirm_applies_profile(client):
    test_client, db_session = client
    action = _prepare_action(test_client, "보통형으로 설정해줘")

    response = test_client.post(
        f"/agent/chat/strategy-actions/{action['action_id']}/confirm",
        json={"confirmation": True, "confirm_operator_ack": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "applied"
    assert body["active_profile"]["profile_name"] == "balanced"
    assert body["safety"]["setting_changed"] is True
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["validation_called"] is False
    assert StrategyProfileService().active_profile(db_session).profile_name == "balanced"
    assert db_session.get(AgentChatStrategyAction, action["action_id"]).status == "applied"


def test_strategy_action_cancel_does_not_apply_profile(client):
    test_client, db_session = client
    action = _prepare_action(test_client, "고수익형으로 바꿔줘")

    response = test_client.post(
        f"/agent/chat/strategy-actions/{action['action_id']}/cancel",
        json={"reason": "test cancel"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["safety"]["setting_changed"] is False
    assert StrategyProfileService().active_profile(db_session).profile_name == "safe"
    assert db_session.get(AgentChatStrategyAction, action["action_id"]).status == "cancelled"


def test_strategy_action_confirm_does_not_submit_validate_or_change_scheduler_flags(client):
    test_client, db_session = client
    runtime = RuntimeSettingService()
    before = runtime.update_settings(
        db_session,
        {
            "dry_run": True,
            "kill_switch": False,
            "scheduler_enabled": False,
            "kis_scheduler_enabled": False,
            "kis_scheduler_live_enabled": False,
            "kis_scheduler_allow_real_orders": False,
            "kis_scheduler_buy_enabled": False,
            "kis_live_auto_buy_enabled": False,
        },
    )
    action = _prepare_action(test_client, "고수익형으로 바꿔줘")

    response = test_client.post(
        f"/agent/chat/strategy-actions/{action['action_id']}/confirm",
        json={"confirmation": True, "confirm_operator_ack": True},
    )
    after = runtime.get_settings(db_session)

    assert response.status_code == 200
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0
    for key in (
        "dry_run",
        "kill_switch",
        "scheduler_enabled",
        "kis_scheduler_enabled",
        "kis_scheduler_live_enabled",
        "kis_scheduler_allow_real_orders",
        "kis_scheduler_buy_enabled",
        "kis_live_auto_buy_enabled",
    ):
        assert after[key] == before[key]


def test_strategy_action_get_returns_pending_state(client):
    test_client, _ = client
    action = _prepare_action(test_client, "안정형으로 바꿔줘")

    response = test_client.get(f"/agent/chat/strategy-actions/{action['action_id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "pending_confirmation"
    assert response.json()["requested_profile"] == "safe"


def _prepare_action(test_client: TestClient, message: str) -> dict:
    response = test_client.post(
        "/agent/chat/send",
        json={"message": message, "auto_create_conversation": True},
    )
    assert response.status_code == 200
    return response.json()["strategy_action"]


def _router_settings():
    return type(
        "Settings",
        (),
        {
            "openai_api_key": None,
            "agent_chat_model": "test-agent-router",
            "agent_chat_reasoning_effort": "low",
            "agent_chat_temperature": None,
            "agent_chat_timeout_seconds": 1.0,
            "agent_chat_fallback_enabled": True,
        },
    )()

