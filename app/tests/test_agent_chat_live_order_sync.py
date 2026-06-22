from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import AgentChatOrderAction, OrderLog
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


def test_sync_filled_order_updates_action_status(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    calls = _Calls()
    service = _service(calls, sync_status="FILLED")
    _enable(db_session)
    action = _confirmed_action(service, db_session)

    response = service.sync(db_session, action_id=action["action_id"])

    assert response["status"] == "synced"
    assert response["live_order_action"]["status"] == "filled"
    assert response["safety"]["manual_submit_called"] is False
    assert response["safety"]["broker_submit_called"] is False
    assert response["safety"]["sync_submitted_new_order"] is False
    assert calls.manual_submit == 1
    row = db_session.get(AgentChatOrderAction, action["action_id"])
    assert row.status == "filled"
    assert row.last_sync_at is not None


def test_sync_rejected_order_maps_to_rejected_without_submit(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    calls = _Calls()
    service = _service(calls, sync_status="REJECTED")
    _enable(db_session)
    action = _confirmed_action(service, db_session)
    calls.manual_submit = 0

    response = service.sync(db_session, action_id=action["action_id"])

    assert response["live_order_action"]["status"] == "rejected"
    assert response["safety"]["manual_submit_called"] is False
    assert calls.manual_submit == 0


def test_sync_missing_order_sets_sync_required_safely(db_session):
    calls = _Calls()
    service = _service(calls, sync_status="FILLED")
    _enable(db_session)
    conversation_key = AgentChatService().create_conversation(
        db_session,
        request=AgentChatConversationCreateRequest(title="missing order sync"),
    )["conversation"]["conversation_key"]
    row = AgentChatOrderAction(
        conversation_key=conversation_key,
        action_type="chat_confirmed_live_order",
        provider="kis",
        market="KR",
        symbol="005930",
        side="buy",
        order_type="market",
        quantity=1,
        currency="KRW",
        status="submitted",
        scope_hash="missing-order-scope",
        confirmation_phrase="005930 buy 1 confirm",
        expires_at=(datetime.now(UTC) + timedelta(minutes=5)).replace(tzinfo=None),
        related_order_id=9999,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    response = service.sync(db_session, action_id=row.id)

    assert response["status"] == "sync_required"
    assert response["safety"]["manual_submit_called"] is False
    assert calls.manual_submit == 0


class _FakeSyncService:
    def __init__(self, status: str):
        self.status = status

    def sync_order(self, db_session, order_id: int):
        row = db_session.get(OrderLog, order_id)
        row.internal_status = self.status
        row.broker_status = self.status
        row.broker_order_status = self.status
        row.last_synced_at = row.last_synced_at or row.submitted_at
        db_session.commit()
        db_session.refresh(row)
        return row


def _service(calls: _Calls, *, sync_status: str) -> AgentChatLiveOrderService:
    return AgentChatLiveOrderService(
        kis_client_factory=lambda db: _FakeKisClient(),
        validation_service_factory=lambda client: _FakeValidationService(calls),
        manual_order_service_factory=lambda client: _FakeManualOrderService(calls),
        order_sync_service_factory=lambda client: _FakeSyncService(sync_status),
    )


def _confirmed_action(service: AgentChatLiveOrderService, db_session) -> dict:
    conversation_key = AgentChatService().create_conversation(
        db_session,
        request=AgentChatConversationCreateRequest(title="sync"),
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
        user_message_id=10,
    )["action"]
    return service.confirm(
        db_session,
        action_id=action["action_id"],
        request=AgentChatLiveOrderConfirmRequest(
            confirmation=True,
            confirmation_token=action["confirmation_token"],
            user_acknowledged_live_order=True,
        ),
    )["live_order_action"]


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
