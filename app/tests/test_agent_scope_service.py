from __future__ import annotations

from app.schemas.agent_command import SCHEMA_VERSION
from app.services.agent_command_validator import AgentCommandValidator
from app.services.agent_scope_service import AgentScopeService


def _command(amount: float):
    return AgentCommandValidator().validate_and_normalize(
        {
            "schema_version": SCHEMA_VERSION,
            "command_type": "CREATE_AGENT_PLAN",
            "domain": "agent",
            "intent": "conditional_buy_schedule",
            "market": "KR",
            "provider": "kis",
            "symbol": "005930",
            "side": "buy",
            "budget": {"amount": amount, "currency": "KRW", "mode": "max_notional"},
            "schedule": {"type": "once", "run_at": "2026-06-18T10:00:00+09:00", "timezone": "Asia/Seoul"},
        }
    )


def test_scope_hash_is_stable_for_same_command():
    service = AgentScopeService()
    scope_a, hash_a = service.build_scope_with_hash(_command(30000))
    scope_b, hash_b = service.build_scope_with_hash(_command(30000))

    assert scope_a == scope_b
    assert hash_a == hash_b
    assert len(hash_a) == 64


def test_scope_hash_changes_when_amount_changes():
    service = AgentScopeService()
    _, hash_a = service.build_scope_with_hash(_command(30000))
    _, hash_b = service.build_scope_with_hash(_command(40000))

    assert hash_a != hash_b

