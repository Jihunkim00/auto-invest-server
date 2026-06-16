from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.schemas.agent_command import (
    SCHEMA_VERSION,
    AutoInvestCommand,
    CommandDomain,
    CommandType,
    Market,
    OrderSide,
    Provider,
)
from app.services.agent_policy_service import AgentPolicyService


class AgentCommandValidator:
    def __init__(self, policy_service: AgentPolicyService | None = None) -> None:
        self._policy_service = policy_service or AgentPolicyService()

    def is_candidate_payload(self, payload: dict[str, Any]) -> bool:
        command_type = payload.get("command_type")
        schema_version = payload.get("schema_version")
        return schema_version == SCHEMA_VERSION and self._coerce_command_type(command_type) is not None

    def validate_and_normalize(
        self,
        payload: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
        fallback_message: str | None = None,
    ) -> AutoInvestCommand:
        context = context or {}
        normalized = self._normalize_payload(payload, context=context)
        try:
            command = AutoInvestCommand.model_validate(normalized)
        except ValidationError:
            command = AutoInvestCommand.model_validate(
                self.safe_unknown_payload(fallback_message or "Unable to parse command.", context=context)
            )
        command = self._fill_clarification_if_needed(command)
        return self._policy_service.apply_policy(command)

    def safe_unknown_payload(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        return {
            "schema_version": SCHEMA_VERSION,
            "command_type": CommandType.CLARIFY_REQUEST.value,
            "domain": CommandDomain.UNKNOWN.value,
            "intent": "needs_clarification",
            "market": self._context_market(context),
            "provider": self._context_provider(context),
            "symbol": None,
            "side": OrderSide.UNKNOWN.value,
            "quantity": None,
            "budget": None,
            "schedule": None,
            "settings_change": None,
            "risk_change": None,
            "portfolio_scope": None,
            "needs_clarification": True,
            "clarification_question": "어떤 종목, 금액, 방향, 시점을 원하는지 더 구체적으로 알려주세요.",
            "user_visible_summary": "요청을 안전하게 실행 가능한 명령으로 확정하려면 추가 정보가 필요합니다.",
            "parser_confidence": 0.2,
            "raw_message": message,
        }

    def _normalize_payload(self, payload: dict[str, Any], *, context: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload or {})
        normalized["schema_version"] = normalized.get("schema_version") or SCHEMA_VERSION
        normalized["command_type"] = self._coerce_command_type(
            normalized.get("command_type")
        ) or CommandType.UNKNOWN.value
        normalized["domain"] = self._coerce_domain(normalized.get("domain"))
        normalized["market"] = self._coerce_market(normalized.get("market"), context)
        normalized["provider"] = self._coerce_provider(normalized.get("provider"), context)
        normalized["side"] = self._coerce_side(normalized.get("side"))
        normalized["intent"] = str(normalized.get("intent") or "unknown")
        normalized["symbol"] = self._normalize_symbol(normalized.get("symbol"))
        if "requires_auth" not in normalized:
            normalized["requires_auth"] = False
        if "requires_risk_approval" not in normalized:
            normalized["requires_risk_approval"] = False
        if "needs_clarification" not in normalized:
            normalized["needs_clarification"] = False
        if "parser_confidence" not in normalized:
            normalized["parser_confidence"] = 0.0
        return normalized

    def _fill_clarification_if_needed(self, command: AutoInvestCommand) -> AutoInvestCommand:
        order_like = command.command_type in {
            CommandType.PREPARE_MANUAL_BUY_TICKET,
            CommandType.PREPARE_MANUAL_SELL_TICKET,
            CommandType.REQUEST_LIVE_ORDER_SUBMIT,
            CommandType.CREATE_AGENT_PLAN,
        }
        missing_order_detail = order_like and (
            not command.symbol
            or command.side == OrderSide.UNKNOWN
            or (
                command.side == OrderSide.BUY
                and command.quantity is None
                and command.budget is None
            )
        )
        if command.command_type in {CommandType.UNKNOWN, CommandType.CLARIFY_REQUEST}:
            command.needs_clarification = True
        elif missing_order_detail:
            command.needs_clarification = True

        if command.needs_clarification and not command.clarification_question:
            command.clarification_question = "종목, 매수/매도 방향, 금액 또는 수량, 실행 시점을 확인해 주세요."
        return command

    def _coerce_command_type(self, value: Any) -> str | None:
        if isinstance(value, CommandType):
            return value.value
        raw = str(value or "").strip().upper()
        for command_type in CommandType:
            if raw == command_type.value:
                return command_type.value
        return None

    def _coerce_domain(self, value: Any) -> str:
        if isinstance(value, CommandDomain):
            return value.value
        raw = str(value or "").strip().lower()
        for domain in CommandDomain:
            if raw == domain.value:
                return domain.value
        return CommandDomain.UNKNOWN.value

    def _coerce_market(self, value: Any, context: dict[str, Any]) -> str:
        raw = str(value or "").strip().upper()
        if not raw:
            raw = self._context_market(context)
        for market in Market:
            if raw == market.value:
                return market.value
        return Market.UNKNOWN.value

    def _context_market(self, context: dict[str, Any]) -> str:
        raw = str(context.get("default_market") or context.get("market") or "").strip().upper()
        if raw in {Market.US.value, Market.KR.value, Market.ALL.value}:
            return raw
        return Market.UNKNOWN.value

    def _coerce_provider(self, value: Any, context: dict[str, Any]) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            raw = self._context_provider(context)
        for provider in Provider:
            if raw == provider.value:
                return provider.value
        return Provider.UNKNOWN.value

    def _context_provider(self, context: dict[str, Any]) -> str:
        raw = str(context.get("default_provider") or context.get("provider") or "").strip().lower()
        if raw in {Provider.ALPACA.value, Provider.KIS.value, Provider.ALL.value}:
            return raw
        return Provider.UNKNOWN.value

    def _coerce_side(self, value: Any) -> str:
        if isinstance(value, OrderSide):
            return value.value
        raw = str(value or "").strip().lower()
        for side in OrderSide:
            if raw == side.value:
                return side.value
        return OrderSide.NONE.value

    def _normalize_symbol(self, value: Any) -> str | None:
        raw = str(value or "").strip().upper()
        return raw or None
