from __future__ import annotations

from app.config import Settings
from app.db.models import OrderLog
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
)


def test_prepare_never_calls_validation_or_manual_submit(db_session):
    calls = _Calls()
    service = AgentChatLiveOrderService(
        kis_client_factory=lambda db: _FakeKisClient(),
        validation_service_factory=lambda client: _FailValidationService(),
        manual_order_service_factory=lambda client: _FailManualOrderService(),
    )
    _enable_chat_live_order(db_session)

    prepared = service.prepare(
        db_session,
        intent=_intent(),
        conversation_key=_conversation(db_session),
        user_message_id=1,
    )

    assert prepared["created"] is True
    assert prepared["safety"]["validation_called"] is False
    assert prepared["safety"]["manual_submit_called"] is False
    assert calls.validation == 0
    assert calls.manual_submit == 0
    assert db_session.query(OrderLog).count() == 0


def test_confirm_blocks_duplicate_open_order_before_submit(monkeypatch, db_session):
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
    _enable_chat_live_order(db_session, dry_run=False)
    action = service.prepare(
        db_session,
        intent=_intent(),
        conversation_key=_conversation(db_session),
        user_message_id=1,
    )["action"]
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="buy",
            order_type="market",
            qty=1,
            internal_status="SUBMITTED",
        )
    )
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

    assert response["status"] == "blocked"
    assert response["diagnostics"]["block_reason"] == "duplicate_open_order_exists"
    assert response["safety"]["validation_called"] is False
    assert response["safety"]["real_order_submitted"] is False
    assert calls.validation == 0
    assert calls.manual_submit == 0


def _conversation(db_session) -> str:
    return AgentChatService().create_conversation(
        db_session,
        request=AgentChatConversationCreateRequest(title="safety"),
    )["conversation"]["conversation_key"]


def _enable_chat_live_order(db_session, *, dry_run: bool = True):
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": dry_run,
            "kill_switch": False,
            "agent_chat_live_order_enabled": True,
            "agent_chat_live_order_kis_enabled": True,
            "agent_chat_live_order_buy_enabled": True,
            "agent_chat_live_order_max_notional_pct": 1.0,
            "agent_chat_live_order_max_notional_krw": 1000000,
        },
    )


def _intent() -> AgentChatIntent:
    return AgentChatIntent(
        category=AgentChatIntentCategory.LIVE_ORDER_REQUEST,
        market="KR",
        provider="kis",
        symbol="005930",
        symbol_name="Samsung Electronics",
        side="buy",
        quantity=1,
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
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _FailValidationService:
    def validate(self, *args, **kwargs):
        raise AssertionError("validation must not run during prepare")


class _FailManualOrderService:
    def submit_manual(self, *args, **kwargs):
        raise AssertionError("manual submit must not run during prepare")
