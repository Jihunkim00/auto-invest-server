from __future__ import annotations

from app.schemas.agent_chat import AgentChatConversationCreateRequest
from app.schemas.agent_chat_live_order import AgentChatLiveOrderConfirmRequest
from app.schemas.agent_chat_orchestrator import AgentChatIntent, AgentChatIntentCategory
from app.services.agent_chat_live_order_service import AgentChatLiveOrderService
from app.services.agent_chat_service import AgentChatService
from app.services.runtime_setting_service import RuntimeSettingService
from app.tests.test_agent_chat_live_order_service import (
    _Calls,
    _FakeKisClient,
    _FakeManualOrderService,
    _FakeValidationService,
    _settings,
)


def test_prepare_response_includes_safety_controls(db_session):
    calls = _Calls()
    service = _service(calls)
    _enable(db_session, dry_run=True, kill_switch=True)

    prepared = _prepare(service, db_session)

    controls = prepared["action"]["safety_controls"]
    assert controls["dry_run"] is True
    assert controls["kill_switch"] is True
    assert controls["agent_chat_live_order_enabled"] is True
    assert controls["agent_chat_live_order_kis_enabled"] is True
    assert controls["agent_chat_live_order_buy_enabled"] is True
    assert controls["daily_limit_remaining"] >= 0
    assert controls["max_notional_limit"] == 1000000


def test_confirm_blocked_response_shows_dry_run_and_kill_switch(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    calls = _Calls()
    service = _service(calls)
    _enable(db_session, dry_run=True, kill_switch=True)
    action = _prepare(service, db_session)["action"]

    response = service.confirm(
        db_session,
        action_id=action["action_id"],
        request=AgentChatLiveOrderConfirmRequest(
            confirmation=True,
            confirmation_token=action["confirmation_token"],
            user_acknowledged_live_order=True,
        ),
    )

    controls = response["live_order_action"]["safety_controls"]
    assert response["status"] == "blocked"
    assert controls["dry_run"] is True
    assert controls["kill_switch"] is True
    assert response["safety"]["real_order_submitted"] is False
    assert calls.validation == 0
    assert calls.manual_submit == 0


def _service(calls: _Calls) -> AgentChatLiveOrderService:
    return AgentChatLiveOrderService(
        kis_client_factory=lambda db: _FakeKisClient(),
        validation_service_factory=lambda client: _FakeValidationService(calls),
        manual_order_service_factory=lambda client: _FakeManualOrderService(calls),
    )


def _prepare(service: AgentChatLiveOrderService, db_session) -> dict:
    conversation_key = AgentChatService().create_conversation(
        db_session,
        request=AgentChatConversationCreateRequest(title="emergency controls"),
    )["conversation"]["conversation_key"]
    return service.prepare(
        db_session,
        intent=AgentChatIntent(
            category=AgentChatIntentCategory.LIVE_ORDER_REQUEST,
            market="KR",
            provider="kis",
            symbol="005930",
            symbol_name="Samsung Electronics",
            side="buy",
            quantity=1,
        ),
        conversation_key=conversation_key,
        user_message_id=10,
    )


def _enable(db_session, *, dry_run: bool, kill_switch: bool):
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": dry_run,
            "kill_switch": kill_switch,
            "agent_chat_live_order_enabled": True,
            "agent_chat_live_order_kis_enabled": True,
            "agent_chat_live_order_buy_enabled": True,
            "agent_chat_live_order_max_orders_per_day": 3,
            "agent_chat_live_order_max_notional_pct": 1.0,
            "agent_chat_live_order_max_notional_krw": 1000000,
        },
    )
