from __future__ import annotations

import json

from app.schemas.agent_chat_live_order import AgentChatLiveOrderConfirmRequest
from app.services.agent_chat_live_order_service import AgentChatLiveOrderService
from app.tests.test_agent_chat_live_order_safety import (
    _conversation,
    _enable_chat_live_order,
    _intent,
    _settings,
)
from app.tests.test_agent_chat_live_order_service import (
    _Calls,
    _FakeKisClient,
    _FakeManualOrderService,
    _FakeValidationService,
)


class _BlockedTargetRisk:
    def evaluate_entry(self, db, request):
        return {
            "approved": False,
            "action": "block",
            "symbol": "005930",
            "active_profile": "safe",
            "requested_notional_krw": 72_000,
            "approved_notional_krw": 0,
            "recommended_notional_krw": 0,
            "sizing_multiplier": 0,
            "block_reason": "monthly_loss_limit_hit",
            "risk_flags": ["monthly_loss_limit_hit"],
            "gating_notes": ["월 손실 한도에 도달했습니다."],
            "checks": [],
            "monthly_progress": {},
            "daily_progress": {},
            "profile_thresholds": {},
            "safety": {
                "real_order_submitted": False,
                "validation_called": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "setting_changed": False,
                "scheduler_changed": False,
            },
        }


def test_live_order_confirm_blocks_before_validation_when_target_risk_rejects(
    monkeypatch,
    db_session,
):
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    calls = _Calls()
    service = AgentChatLiveOrderService(
        kis_client_factory=lambda db: _FakeKisClient(),
        validation_service_factory=lambda client: _FakeValidationService(calls),
        manual_order_service_factory=lambda client: _FakeManualOrderService(calls),
        target_aware_risk_service=_BlockedTargetRisk(),
    )
    _enable_chat_live_order(db_session, dry_run=False)
    action = service.prepare(
        db_session,
        intent=_intent(),
        conversation_key=_conversation(db_session),
        user_message_id=1,
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
    assert response["diagnostics"]["block_reason"] == "monthly_loss_limit_hit"
    assert response["safety"]["validation_called"] is False
    assert response["safety"]["broker_submit_called"] is False
    assert response["safety"]["manual_submit_called"] is False
    assert calls.validation == 0
    assert calls.manual_submit == 0
    row = service._get_action(db_session, action["action_id"])
    risk_payload = json.loads(row.risk_payload_json)
    assert risk_payload["risk_flags"] == ["monthly_loss_limit_hit"]
    assert risk_payload["gating_notes"] == ["월 손실 한도에 도달했습니다."]
