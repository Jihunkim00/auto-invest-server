from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.db.models import AgentChatOrderAction, AgentChatMessage, OrderLog
from app.schemas.agent_chat import AgentChatConversationCreateRequest
from app.schemas.agent_chat_live_order import (
    AgentChatLiveOrderCancelRequest,
    AgentChatLiveOrderConfirmRequest,
)
from app.schemas.agent_chat_orchestrator import AgentChatIntent, AgentChatIntentCategory
from app.services.agent_chat_live_order_service import AgentChatLiveOrderService
from app.services.agent_chat_service import AgentChatService
from app.services.kis_order_validation_service import (
    KisOrderPreview,
    KisOrderValidationResult,
)
from app.services.runtime_setting_service import RuntimeSettingService


def test_prepare_live_order_creates_pending_confirmation_only(db_session):
    conversation_key = _conversation(db_session)
    calls = _Calls()
    service = _service(calls=calls)
    _enable_chat_live_order(db_session)

    prepared = service.prepare(
        db_session,
        intent=_intent(),
        conversation_key=conversation_key,
        user_message_id=10,
    )

    assert prepared["created"] is True
    action = prepared["action"]
    assert action["status"] == "pending_confirmation"
    assert action["symbol"] == "005930"
    assert action["side"] == "buy"
    assert action["quantity"] == 1
    assert prepared["safety"]["real_order_submitted"] is False
    assert prepared["safety"]["validation_called"] is False
    assert prepared["safety"]["broker_submit_called"] is False
    assert prepared["safety"]["manual_submit_called"] is False
    assert db_session.query(AgentChatOrderAction).count() == 1
    assert db_session.query(OrderLog).count() == 0
    assert calls.validation == 0
    assert calls.manual_submit == 0


def test_prepare_live_order_default_settings_block_without_pending_action(db_session):
    conversation_key = _conversation(db_session)
    service = _service()

    prepared = service.prepare(
        db_session,
        intent=_intent(),
        conversation_key=conversation_key,
        user_message_id=10,
    )

    assert prepared["created"] is False
    assert prepared["data"]["live_order_feature_disabled"] is True
    assert prepared["safety"]["real_order_submitted"] is False
    assert db_session.query(AgentChatOrderAction).count() == 0
    assert db_session.query(OrderLog).count() == 0


def test_confirm_submits_only_after_gates_pass(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    conversation_key = _conversation(db_session)
    calls = _Calls()
    service = _service(calls=calls)
    _enable_chat_live_order(db_session, dry_run=False, max_notional_pct=1.0)
    action = service.prepare(
        db_session,
        intent=_intent(),
        conversation_key=conversation_key,
        user_message_id=10,
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

    assert response["status"] == "submitted"
    assert response["safety"]["real_order_submitted"] is True
    assert response["safety"]["validation_called"] is True
    assert response["safety"]["manual_submit_called"] is True
    assert calls.validation == 1
    assert calls.manual_submit == 1
    action_row = db_session.get(AgentChatOrderAction, action["action_id"])
    assert action_row.status == "submitted"
    assert action_row.related_order_id is not None
    assert db_session.query(OrderLog).count() == 1
    assert (
        db_session.query(AgentChatMessage)
        .filter(AgentChatMessage.message_type == "live_order_submitted")
        .count()
        == 1
    )

    replay = service.confirm(
        db_session,
        action_id=action["action_id"],
        request=AgentChatLiveOrderConfirmRequest(
            confirmation=True,
            confirmation_token=action["confirmation_token"],
            user_acknowledged_live_order=True,
        ),
    )
    assert replay["status"] == "submitted"
    assert replay["safety"]["idempotent_replay"] is True
    assert calls.manual_submit == 1
    assert db_session.query(OrderLog).count() == 1


def test_confirm_blocked_when_dry_run_true(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    conversation_key = _conversation(db_session)
    calls = _Calls()
    service = _service(calls=calls)
    _enable_chat_live_order(db_session, dry_run=True, max_notional_pct=1.0)
    action = service.prepare(
        db_session,
        intent=_intent(),
        conversation_key=conversation_key,
        user_message_id=10,
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

    assert response["status"] == "blocked"
    assert response["safety"]["real_order_submitted"] is False
    assert response["safety"]["validation_called"] is False
    assert calls.validation == 0
    assert calls.manual_submit == 0
    assert db_session.query(OrderLog).count() == 0


def test_confirm_blocked_when_expired(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    conversation_key = _conversation(db_session)
    calls = _Calls()
    service = _service(calls=calls)
    _enable_chat_live_order(db_session, dry_run=False, max_notional_pct=1.0)
    action = service.prepare(
        db_session,
        intent=_intent(),
        conversation_key=conversation_key,
        user_message_id=10,
        now=datetime.now(UTC) - timedelta(minutes=10),
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

    assert response["status"] == "expired"
    assert response["answer"]["answer_type"] == "live_order_expired"
    assert calls.validation == 0
    assert calls.manual_submit == 0


def test_confirm_blocked_when_phrase_or_token_mismatch(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    conversation_key = _conversation(db_session)
    calls = _Calls()
    service = _service(calls=calls)
    _enable_chat_live_order(db_session, dry_run=False, max_notional_pct=1.0)
    action = service.prepare(
        db_session,
        intent=_intent(),
        conversation_key=conversation_key,
        user_message_id=10,
    )["action"]

    response = service.confirm(
        db_session,
        action_id=action["action_id"],
        request=AgentChatLiveOrderConfirmRequest(
            confirmation=True,
            confirmation_token="wrong",
            user_acknowledged_live_order=True,
        ),
    )

    assert response["status"] == "blocked"
    assert response["diagnostics"]["block_reason"] == "confirmation_mismatch"
    assert calls.validation == 0
    assert calls.manual_submit == 0


def test_cancel_pending_action_does_not_validate_or_submit(db_session):
    conversation_key = _conversation(db_session)
    calls = _Calls()
    service = _service(calls=calls)
    _enable_chat_live_order(db_session)
    action = service.prepare(
        db_session,
        intent=_intent(),
        conversation_key=conversation_key,
        user_message_id=10,
    )["action"]

    response = service.cancel(
        db_session,
        action_id=action["action_id"],
        request=AgentChatLiveOrderCancelRequest(reason="user cancelled"),
    )

    assert response["status"] == "cancelled"
    assert response["safety"]["real_order_submitted"] is False
    assert calls.validation == 0
    assert calls.manual_submit == 0
    assert db_session.query(OrderLog).count() == 0


def _conversation(db_session) -> str:
    return AgentChatService().create_conversation(
        db_session,
        request=AgentChatConversationCreateRequest(title="Live order test"),
    )["conversation"]["conversation_key"]


def _enable_chat_live_order(
    db_session,
    *,
    dry_run: bool = True,
    max_notional_pct: float = 1.0,
):
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": dry_run,
            "kill_switch": False,
            "agent_chat_live_order_enabled": True,
            "agent_chat_live_order_kis_enabled": True,
            "agent_chat_live_order_buy_enabled": True,
            "agent_chat_live_order_confirm_ttl_seconds": 120,
            "agent_chat_live_order_max_orders_per_day": 1,
            "agent_chat_live_order_max_notional_pct": max_notional_pct,
            "agent_chat_live_order_max_notional_krw": 1000000,
        },
    )


def _intent() -> AgentChatIntent:
    return AgentChatIntent(
        category=AgentChatIntentCategory.LIVE_ORDER_REQUEST,
        supported=True,
        confidence=0.9,
        market="KR",
        provider="kis",
        symbol="005930",
        symbol_name="Samsung Electronics",
        side="buy",
        quantity=1,
        currency="KRW",
        requires_manual_confirmation=True,
    )


def _service(calls: "_Calls | None" = None) -> AgentChatLiveOrderService:
    calls = calls or _Calls()
    return AgentChatLiveOrderService(
        kis_client_factory=lambda db: _FakeKisClient(),
        validation_service_factory=lambda client: _FakeValidationService(calls),
        manual_order_service_factory=lambda client: _FakeManualOrderService(calls),
    )


def _settings(**overrides) -> Settings:
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "kis_enabled": True,
        "kis_real_order_enabled": True,
        "kis_env": "prod",
        "kis_app_key": "real-app-key",
        "kis_app_secret": "real-app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_base_url": "https://openapi.koreainvestment.com:9443",
        "kis_access_token": "secret-access-token",
        "kis_approval_key": "secret-approval-key",
        "kis_require_confirmation": True,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _Calls:
    validation = 0
    manual_submit = 0


class _FakeKisClient:
    settings = _settings()

    def get_domestic_stock_price(self, symbol: str):
        return {
            "symbol": symbol,
            "name": "Samsung Electronics",
            "current_price": 72000.0,
        }


class _FakeValidationService:
    def __init__(self, calls: _Calls):
        self.calls = calls

    def validate(self, request, *, now=None):
        self.calls.validation += 1
        return KisOrderValidationResult(
            provider="kis",
            market="KR",
            environment="prod",
            dry_run=True,
            validated_for_submission=True,
            can_submit_later=True,
            symbol=request.symbol,
            company_name="Samsung Electronics",
            side=request.side,
            qty=request.qty,
            order_type=request.order_type,
            current_price=72000.0,
            estimated_amount=72000.0,
            available_cash=1000000.0,
            held_qty=None,
            warnings=[],
            block_reasons=[],
            market_session={
                "market": "KR",
                "is_market_open": True,
                "is_entry_allowed_now": True,
                "is_near_close": False,
                "no_new_entry_after": "15:00",
            },
            order_preview=KisOrderPreview(
                account_no_masked="****5678",
                product_code="01",
                symbol=request.symbol,
                side=request.side,
                qty=request.qty,
                order_type=request.order_type,
                kis_tr_id_preview="TTTC0802U",
                payload_preview={},
            ),
            source_metadata=request.source_metadata,
        )


class _FakeManualOrderService:
    def __init__(self, calls: _Calls):
        self.calls = calls

    def submit_manual(self, db_session, request, *, now=None):
        self.calls.manual_submit += 1
        row = OrderLog(
            broker="kis",
            market="KR",
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            qty=float(request.qty),
            internal_status="SUBMITTED",
            broker_order_id="0001234567",
            kis_odno="0001234567",
            submitted_at=(now or datetime.now(UTC)).replace(tzinfo=None),
        )
        db_session.add(row)
        db_session.commit()
        db_session.refresh(row)
        return 200, {
            "provider": "kis",
            "market": "KR",
            "real_order_submitted": True,
            "broker_submit_called": True,
            "manual_submit_called": True,
            "order_id": row.id,
            "order_log_id": row.id,
            "broker_order_id": "0001234567",
            "kis_odno": "0001234567",
            "symbol": request.symbol,
            "side": request.side,
            "qty": request.qty,
            "internal_status": "SUBMITTED",
        }
