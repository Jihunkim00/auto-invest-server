from __future__ import annotations

import json

from app.db.models import AgentChatOrderAction
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


def test_audit_metadata_contains_linkage_and_no_secret_markers(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    calls = _Calls()
    service = AgentChatLiveOrderService(
        kis_client_factory=lambda db: _FakeKisClient(),
        validation_service_factory=lambda client: _FakeValidationService(calls),
        manual_order_service_factory=lambda client: _FakeManualOrderService(calls),
    )
    _enable(db_session)
    conversation_key = AgentChatService().create_conversation(
        db_session,
        request=AgentChatConversationCreateRequest(title="audit"),
    )["conversation"]["conversation_key"]
    action = service.prepare(
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
        user_message_id=101,
    )["action"]

    response = service.confirm(
        db_session,
        action_id=action["action_id"],
        request=AgentChatLiveOrderConfirmRequest(
            confirmation=True,
            confirmation_token=action["confirmation_token"],
            user_acknowledged_live_order=True,
        ),
    )

    audit = response["live_order_action"]["audit"]
    assert audit["requested_by"] == "agent_chat"
    assert audit["conversation_key"] == conversation_key
    assert audit["user_message_id"] == 101
    assert audit["confirmation_method"] == "confirmation_card"
    assert audit["confirmation_token_hash"]
    assert audit["submit_result_summary"]["real_order_submitted"] is True
    assert response["live_order_action"]["related_order_id"] is not None

    row = db_session.get(AgentChatOrderAction, action["action_id"])
    raw = json.dumps(
        {
            "action": response["live_order_action"],
            "request": row.request_payload_json,
            "response": row.response_payload_json,
            "safety": row.safety_payload_json,
        },
        ensure_ascii=False,
    ).lower()
    for marker in [
        "real-app-secret",
        "secret-access-token",
        "secret-approval-key",
        "kis_app_secret",
        "access_token",
        "approval_key",
    ]:
        assert marker not in raw


def _enable(db_session):
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": False,
            "kill_switch": False,
            "agent_chat_live_order_enabled": True,
            "agent_chat_live_order_kis_enabled": True,
            "agent_chat_live_order_buy_enabled": True,
            "agent_chat_live_order_max_orders_per_day": 3,
            "agent_chat_live_order_max_notional_pct": 1.0,
            "agent_chat_live_order_max_notional_krw": 1000000,
        },
    )
