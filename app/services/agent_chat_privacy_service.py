from __future__ import annotations

import re
from enum import Enum
from typing import Any


class AgentChatPrivacyClass(str, Enum):
    PUBLIC = "PUBLIC"
    PRIVATE_ACCOUNT = "PRIVATE_ACCOUNT"
    SECRET = "SECRET"


class AgentChatContextPrivacyService:
    """Classify and project chat context before each external model call."""

    SECRET_KEYS = frozenset(
        {
            "appkey",
            "appsecret",
            "access_token",
            "approval_key",
            "account_no",
            "account_number",
            "authorization",
            "token",
            "secret",
            "password",
            "openai_api_key",
        }
    )
    PRIVATE_KEYS = frozenset(
        {
            "cash",
            "available_cash",
            "orderable_cash",
            "buying_power",
            "positions",
            "holdings",
            "holding_quantity",
            "quantity",
            "qty",
            "average_cost",
            "avg_entry_price",
            "unrealized_pl",
            "order_history",
            "orders",
            "broker_order_id",
            "broker_order_ids",
            "account",
            "account_id",
            "account_identifier",
        }
    )
    PUBLIC_ANALYSIS_KEYS = frozenset(
        {
            "symbol",
            "symbol_name",
            "name",
            "market",
            "provider",
            "current_price",
            "price",
            "currency",
            "timestamp",
            "updated_at",
            "action",
            "decision",
            "final_score",
            "required_score",
            "quant_buy",
            "quant_sell",
            "ai_buy",
            "ai_sell",
            "confidence",
            "risk_flags",
            "positive_factors",
            "positives",
            "gating_notes",
            "block_reasons",
            "event_risk",
            "market_state",
            "session_state",
            "indicators",
            "ema20",
            "ema50",
            "rsi",
            "vwap",
            "atr",
            "volume_ratio",
            "momentum",
            "latest_analysis",
            "result",
            "reason",
        }
    )
    _SECRET_VALUE_PATTERNS = (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
        re.compile(r"(?i)\b(?:appkey|appsecret|access_token|approval_key|token|secret|password)\s*[:=]\s*[^\s,;]+"),
      re.compile(r"(?i)\b(?:account_no|account_number|account)\s*[:=]\s*[0-9-]{6,}"),
    )
    _PRIVATE_TEXT_PATTERNS = (
        re.compile(r"(?i)\b(?:cash|available_cash|orderable_cash|buying_power|positions|holdings|quantity|qty|average_cost|unrealized_pl|order_history|broker_order_id)\b"),
        re.compile(r"(?:계좌|잔고|예수금|보유 종목|포지션|평균단가|주문 내역|주문이력|평가손익|미실현손익)"),
    )
    _SECRET_TEXT_PATTERNS = (
        re.compile(r"(?i)\b(?:appkey|appsecret|access_token|approval_key|authorization|token|password|account_no|account_number)\b"),
    )
    ROUTER_PUBLIC_KEYS = frozenset(
        {"default_market", "default_provider", "timezone", "symbol", "symbol_name", "market", "provider", "source", "language", "locale"}
    )

    def classify(self, value: Any) -> AgentChatPrivacyClass:
        if isinstance(value, dict):
            result = AgentChatPrivacyClass.PUBLIC
            for key, child in value.items():
                key_class = self.classify_key(str(key))
                if key_class == AgentChatPrivacyClass.SECRET:
                    return key_class
                if key_class == AgentChatPrivacyClass.PRIVATE_ACCOUNT:
                    result = key_class
                child_class = self.classify(child)
                if child_class == AgentChatPrivacyClass.SECRET:
                    return child_class
                if child_class == AgentChatPrivacyClass.PRIVATE_ACCOUNT:
                    result = child_class
            return result
        if isinstance(value, (list, tuple)):
            result = AgentChatPrivacyClass.PUBLIC
            for item in value:
                item_class = self.classify(item)
                if item_class == AgentChatPrivacyClass.SECRET:
                    return item_class
                if item_class == AgentChatPrivacyClass.PRIVATE_ACCOUNT:
                    result = item_class
            return result
        if isinstance(value, str):
            if self._contains_secret_value(value):
                return AgentChatPrivacyClass.SECRET
            if self._contains_secret_text(value):
                return AgentChatPrivacyClass.SECRET
            if self._contains_private_text(value):
                return AgentChatPrivacyClass.PRIVATE_ACCOUNT
        return AgentChatPrivacyClass.PUBLIC

    def classify_key(self, key: str) -> AgentChatPrivacyClass:
        normalized = str(key or "").strip().lower().replace("-", "_")
        if normalized in self.SECRET_KEYS or any(token in normalized for token in ("appsecret", "access_token", "authorization")):
            return AgentChatPrivacyClass.SECRET
        if normalized in self.PRIVATE_KEYS:
            return AgentChatPrivacyClass.PRIVATE_ACCOUNT
        return AgentChatPrivacyClass.PUBLIC

    def redact_user_message(self, message: str) -> tuple[str | None, AgentChatPrivacyClass]:
        text = str(message or "")
        if not text:
            return text, AgentChatPrivacyClass.PUBLIC
        if self.classify(text) == AgentChatPrivacyClass.SECRET:
            if not self._contains_secret_value(text):
                return None, AgentChatPrivacyClass.SECRET
            redacted = text
            for pattern in self._SECRET_VALUE_PATTERNS:
                redacted = pattern.sub(self._redact_secret_match, redacted)
            if self._contains_secret_value(redacted):
                return None, AgentChatPrivacyClass.SECRET
            return redacted, AgentChatPrivacyClass.PUBLIC
        if self.classify(text) == AgentChatPrivacyClass.PRIVATE_ACCOUNT:
            return None, AgentChatPrivacyClass.PRIVATE_ACCOUNT
        return text, AgentChatPrivacyClass.PUBLIC

    def public_context(
        self,
        *,
        intent_name: str,
        symbol: str | None,
        symbol_name: str | None,
        market: str | None,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "intent": intent_name,
            "symbol": symbol,
            "symbol_name": symbol_name,
            "market": market,
        }
        if isinstance(data.get("price"), dict):
            context["price"] = self._public_projection(data["price"])
        if isinstance(data.get("analysis"), dict):
            context["analysis"] = self._public_projection(data["analysis"])
        if isinstance(data.get("risk"), dict):
            context["risk"] = self._public_projection(data["risk"])
        if isinstance(data.get("runs"), list):
            context["recent_decisions"] = [
                self._public_projection(item)
                for item in data["runs"][:3]
                if isinstance(item, dict)
            ]
        return self._drop_private(context)

    def public_router_context(self, context: dict[str, Any] | None) -> dict[str, Any]:
        value = context if isinstance(context, dict) else {}
        return self._public_router_projection(value)

    def _public_projection(self, value: Any) -> Any:
        if isinstance(value, dict):
            projected: dict[str, Any] = {}
            for key, child in value.items():
                key_name = str(key)
                normalized = key_name.strip().lower().replace("-", "_")
                if normalized not in self.PUBLIC_ANALYSIS_KEYS:
                    continue
                if self.classify_key(key_name) != AgentChatPrivacyClass.PUBLIC:
                    continue
                projected[key_name] = self._public_projection(child)
            return projected
        if isinstance(value, list):
            return [self._public_projection(item) for item in value[:10]]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def _drop_private(self, value: Any) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, child in value.items():
                if self.classify_key(str(key)) != AgentChatPrivacyClass.PUBLIC:
                    continue
                result[key] = self._drop_private(child)
            return result
        if isinstance(value, list):
            return [self._drop_private(item) for item in value]
        return value

    def _contains_secret_value(self, value: str) -> bool:
        return any(pattern.search(value) for pattern in self._SECRET_VALUE_PATTERNS)

    def _contains_private_text(self, value: str) -> bool:
        return any(pattern.search(value) for pattern in self._PRIVATE_TEXT_PATTERNS)

    def _contains_secret_text(self, value: str) -> bool:
        return any(pattern.search(value) for pattern in self._SECRET_TEXT_PATTERNS)

    def _redact_secret_match(self, match: re.Match[str]) -> str:
        value = match.group(0)
        if value.lower().startswith("bearer "):
            return "Bearer [REDACTED]"
        if ":" in value:
            return f"{value.split(':', 1)[0]}:[REDACTED]"
        if "=" in value:
            return f"{value.split('=', 1)[0]}=[REDACTED]"
        return "[REDACTED]"

    def _public_router_projection(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): self._public_router_projection(child)
                for key, child in value.items()
                if str(key).strip().lower().replace("-", "_") in self.ROUTER_PUBLIC_KEYS
                and self.classify_key(str(key)) == AgentChatPrivacyClass.PUBLIC
            }
        if isinstance(value, list):
            return [self._public_router_projection(item) for item in value[:10]]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)
