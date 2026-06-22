from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import AgentChatOrderAction, OrderLog
from app.schemas.agent_chat import AgentChatConversationCreateRequest
from app.schemas.agent_chat_live_order import (
    AgentChatLiveOrderCancelRequest,
    AgentChatLiveOrderConfirmRequest,
)
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


def test_confirm_idempotent_submits_once(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    calls = _Calls()
    service = _service(calls)
    _enable(db_session, dry_run=False)
    action = _prepare(service, db_session)

    request = AgentChatLiveOrderConfirmRequest(
        confirmation=True,
        confirmation_token=action["confirmation_token"],
        user_acknowledged_live_order=True,
    )
    first = service.confirm(db_session, action_id=action["action_id"], request=request)
    second = service.confirm(db_session, action_id=action["action_id"], request=request)

    assert first["status"] == "submitted"
    assert second["status"] == "submitted"
    assert second["safety"]["idempotent_replay"] is True
    assert calls.manual_submit == 1
    assert db_session.query(OrderLog).count() == 1


def test_confirm_existing_related_order_does_not_resubmit(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    calls = _Calls()
    service = _service(calls)
    _enable(db_session, dry_run=False)
    action = _prepare(service, db_session)
    order = OrderLog(
        broker="kis",
        market="KR",
        symbol="005930",
        side="buy",
        order_type="market",
        qty=1,
        internal_status="SUBMITTED",
        broker_order_id="ODNO-EXISTING",
        kis_odno="ODNO-EXISTING",
        submitted_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    row = db_session.get(AgentChatOrderAction, action["action_id"])
    row.related_order_id = order.id
    row.broker_order_id = order.broker_order_id
    db_session.commit()

    response = service.confirm(
        db_session,
        action_id=action["action_id"],
        request=AgentChatLiveOrderConfirmRequest(
            confirmation=True,
            confirmation_token=action["confirmation_token"],
            user_acknowledged_live_order=True,
        ),
    )

    assert response["status"] == "submitted"
    assert response["safety"]["idempotent_replay"] is True
    assert calls.validation == 0
    assert calls.manual_submit == 0


def test_cancelled_action_cannot_confirm(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    calls = _Calls()
    service = _service(calls)
    _enable(db_session, dry_run=False)
    action = _prepare(service, db_session)

    service.cancel(
        db_session,
        action_id=action["action_id"],
        request=AgentChatLiveOrderCancelRequest(reason="operator cancelled"),
    )
    response = service.confirm(
        db_session,
        action_id=action["action_id"],
        request=AgentChatLiveOrderConfirmRequest(
            confirmation=True,
            confirmation_token=action["confirmation_token"],
            user_acknowledged_live_order=True,
        ),
    )

    assert response["status"] == "cancelled"
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
        request=AgentChatConversationCreateRequest(title="idempotency"),
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
    )["action"]


def _enable(db_session, *, dry_run: bool):
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": dry_run,
            "kill_switch": False,
            "agent_chat_live_order_enabled": True,
            "agent_chat_live_order_kis_enabled": True,
            "agent_chat_live_order_buy_enabled": True,
            "agent_chat_live_order_max_orders_per_day": 3,
            "agent_chat_live_order_max_notional_pct": 1.0,
            "agent_chat_live_order_max_notional_krw": 1000000,
        },
    )
