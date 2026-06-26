from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from app.config import get_settings
from app.schemas.agent_chat_orchestrator import (
    AgentChatIntent,
    AgentChatIntentCategory,
)
from app.schemas.agent_chat_tool import AgentChatToolCall
from app.services.agent_chat_tool_registry import AgentChatToolRegistry


AGENT_CHAT_ROUTER_SYSTEM_PROMPT = """
You are the intent and tool-candidate router for an Auto Invest chat agent.
Classify the user's natural language message and choose allowlisted tool candidates when useful.

Rules:
- Never execute trades.
- Never approve or submit live orders.
- Live-order wording must be category live_order_request.
- Read-only questions must be a read_only_* category.
- Dangerous setting changes must be dangerous_setting_request.
- Strategy profile and performance lookup, comparison, recommendation, target-progress, loss-budget, and profile-change requests must use strategy_* categories.
- Strategy entry permission, loss-limit, target-gate, and order-sizing questions must use strategy risk categories and read-only tools.
- Strategy dry-run auto-buy simulation requests may run simulation-only tools, but must never create a live-order action.
- Strategy live auto-buy questions must use read-only readiness/recent tools and must never execute run-once from chat.
- Strategy profile change requests must only prepare confirmation; never mutate active settings from a chat message alone.
- Choose only tool names from the provided allowlist.
- Do not choose executable tools for live orders, settings mutation, or scheduler mutation.
- For blocked live/settings requests choose the blocker tool candidate only.
- Unsupported requests must be unsupported.
- Ambiguous requests must be needs_clarification.
- Return JSON only. No markdown.
"""


class AgentChatIntentRouterService:
    def __init__(
        self,
        *,
        openai_client: Any | None = None,
        settings: Any | None = None,
        tool_registry: AgentChatToolRegistry | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.tool_registry = tool_registry or AgentChatToolRegistry()
        self.model_name = getattr(
            self.settings,
            "agent_chat_model",
            getattr(self.settings, "openai_model", "gpt-5.4-mini"),
        )
        self.reasoning_effort = getattr(
            self.settings,
            "agent_chat_reasoning_effort",
            getattr(self.settings, "openai_reasoning_effort", "low"),
        )
        self.temperature = getattr(self.settings, "agent_chat_temperature", None)
        self.timeout_seconds = getattr(self.settings, "agent_chat_timeout_seconds", 20.0)
        self.fallback_enabled = getattr(self.settings, "agent_chat_fallback_enabled", True)
        if openai_client is not None:
            self.client = openai_client
        else:
            api_key = getattr(self.settings, "openai_api_key", None)
            self.client = OpenAI(api_key=api_key, timeout=self.timeout_seconds) if api_key else None

    def route(self, *, message: str, context: dict[str, Any] | None = None) -> AgentChatIntent:
        context = context or {}
        clean_message = str(message or "").strip()
        gpt_failed = False
        if self.client:
            try:
                return self._route_with_gpt(clean_message, context)
            except Exception:
                if not self.fallback_enabled:
                    raise
                gpt_failed = True
        return self.fallback_route(
            clean_message,
            context,
            parser_status="failed_fallback_used" if gpt_failed else "fallback",
        )

    def fallback_route(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        *,
        parser_status: str = "fallback",
    ) -> AgentChatIntent:
        context = context or {}
        text = str(message or "").strip()
        lowered = text.lower()
        symbol_info = self._detect_symbol(text)
        if symbol_info is None and self._should_use_context_symbol(text, lowered):
            symbol_info = self._symbol_info_from_context(context)
        market = self._resolve_market(context, symbol_info)
        provider = self._resolve_provider(context, market)
        amount = self._parse_amount(text)
        quantity = self._parse_quantity(text, symbol_info)
        side = self._detect_side(text)
        base = {
            "market": market,
            "provider": provider,
            "symbol": symbol_info.get("symbol") if symbol_info else None,
            "symbol_name": symbol_info.get("name") if symbol_info else None,
            "side": side,
            "quantity": quantity,
            "notional": amount,
                "currency": ("KRW" if market == "KR" else "USD") if amount is not None and market in {"KR", "US"} else None,
            "requested_profile": self._detect_strategy_profile(text),
            "target_monthly_return_pct": self._detect_target_monthly_return_pct(text),
            "fallback_used": True,
            "parser_status": parser_status,
        }

        if not text:
            return self._intent(
                AgentChatIntentCategory.NEEDS_CLARIFICATION,
                confidence=0.4,
                reason="Empty message.",
                supported=False,
                **base,
            )

        strategy_intent = self._strategy_intent(text, lowered, base)
        if strategy_intent is not None:
            return strategy_intent

        if self._is_settings_status_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.READ_ONLY_SETTINGS_QUERY,
                confidence=0.88,
                reason="User is asking for read-only runtime safety status.",
                **base,
            )

        if self._is_dangerous_setting_request(text):
            return self._intent(
                AgentChatIntentCategory.DANGEROUS_SETTING_REQUEST,
                confidence=0.9,
                reason="User requested a dangerous runtime setting change.",
                supported=True,
                requires_auth=True,
                requires_manual_confirmation=True,
                **base,
            )

        if self._is_unsupported(text):
            return self._intent(
                AgentChatIntentCategory.UNSUPPORTED,
                confidence=0.86,
                reason="Requested market/action is outside the supported Auto Invest scope.",
                supported=False,
                **base,
            )

        if self._is_manual_ticket_request(text):
            return self._intent(
                AgentChatIntentCategory.MANUAL_TICKET_REQUEST,
                confidence=0.88,
                reason="User asked to prepare a manual order ticket.",
                supported=bool(symbol_info),
                requires_plan=True,
                requires_manual_confirmation=True,
                **base,
            )

        if self._is_exit_review_request(text, lowered):
            return self._intent(
                AgentChatIntentCategory.EXIT_REVIEW_REQUEST,
                confidence=0.84 if symbol_info else 0.62,
                reason="User is asking for a safe exit review.",
                supported=bool(symbol_info),
                requires_plan=bool(symbol_info),
                **base,
            )

        if self._is_live_order_request(text):
            return self._intent(
                AgentChatIntentCategory.LIVE_ORDER_REQUEST,
                confidence=0.88,
                reason="User asked for a direct live order.",
                supported=True,
                requires_plan=bool(symbol_info),
                requires_manual_confirmation=True,
                **base,
            )

        if self._is_positions_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.READ_ONLY_POSITIONS_QUERY,
                confidence=0.9,
                reason="User is asking for current positions.",
                **base,
            )

        if self._is_balance_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.READ_ONLY_BALANCE_QUERY,
                confidence=0.88,
                reason="User is asking for account balance.",
                **base,
            )

        if self._is_orders_query(text):
            return self._intent(
                AgentChatIntentCategory.READ_ONLY_ORDERS_QUERY,
                confidence=0.87,
                reason="User is asking for recent order history.",
                **base,
            )

        if self._is_runs_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.READ_ONLY_RUNS_QUERY,
                confidence=0.86,
                reason="User is asking for recent execution logs.",
                **base,
            )

        if self._is_signals_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.READ_ONLY_SIGNALS_QUERY,
                confidence=0.84,
                reason="User is asking for recent signals.",
                **base,
            )

        if self._is_price_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.READ_ONLY_PRICE_QUERY,
                confidence=0.9 if symbol_info else 0.62,
                reason="User is asking for a current stock price.",
                supported=bool(symbol_info),
                **base,
            )

        if self._is_watchlist_preview_request(text, lowered):
            return self._intent(
                AgentChatIntentCategory.WATCHLIST_PREVIEW_REQUEST,
                confidence=0.82,
                reason="User is asking for a safe watchlist preview.",
                **base,
            )

        if self._is_analysis_request(text, lowered):
            return self._intent(
                AgentChatIntentCategory.ANALYSIS_REQUEST,
                confidence=0.86 if symbol_info else 0.64,
                reason="User is asking for safe analysis.",
                supported=bool(symbol_info),
                requires_plan=bool(symbol_info),
                **base,
            )

        if self._is_scheduler_request(text, lowered):
            return self._intent(
                AgentChatIntentCategory.SCHEDULER_REQUEST,
                confidence=0.78,
                reason="User is asking about scheduler behavior.",
                requires_plan=True,
                **base,
            )

        if self._is_capability_question(text, lowered):
            return self._intent(
                AgentChatIntentCategory.CAPABILITY_QUESTION,
                confidence=0.9,
                reason="User is asking what Auto Invest chat can do.",
                market=None,
                provider=None,
                symbol=None,
                symbol_name=None,
                side="none",
                notional=None,
                currency=None,
                fallback_used=True,
                parser_status=parser_status,
            )

        return self._intent(
            AgentChatIntentCategory.GENERAL_CHAT,
            confidence=0.65,
            reason="General chat within the Auto Invest assistant.",
            market=None,
            provider=None,
            symbol=None,
            symbol_name=None,
            side="none",
            notional=None,
            currency=None,
            fallback_used=True,
            parser_status=parser_status,
        )

    def _route_with_gpt(self, message: str, context: dict[str, Any]) -> AgentChatIntent:
        prompt_payload = {
            "message": message,
            "context": context,
            "categories": [category.value for category in AgentChatIntentCategory],
            "available_tools": [
                tool.model_dump(mode="json")
                for tool in self.tool_registry.list_tools(include_blocked=True)
            ],
            "required_output_shape": {
                "category": "one category string",
                "supported": "boolean",
                "confidence": "number 0..1",
                "market": "KR, US, ALL, UNKNOWN, or null",
                "provider": "kis, alpaca, all, unknown, or null",
                "symbol": "normalized symbol or null",
                "symbol_name": "company display name or null",
                "side": "buy, sell, none, or unknown",
                "quantity": "number or null",
                "notional": "number or null",
                "currency": "KRW, USD, or null",
                "requested_profile": "safe, balanced, aggressive, or null for strategy requests",
                "target_monthly_return_pct": "number or null",
                "requires_plan": "boolean",
                "requires_auth": "boolean",
                "requires_manual_confirmation": "boolean",
                "reason": "short English reason",
                "selected_tools": [
                    {
                        "tool_name": "allowlisted tool name",
                        "arguments": "object",
                        "reason": "short English reason",
                    }
                ],
            },
            "safety": {
                "live_orders_never_execute": True,
                "dangerous_settings_never_mutate": True,
                "flutter_openai_direct_call_forbidden": True,
            },
        }
        request_payload = {
            "model": self.model_name,
            "reasoning": {"effort": self.reasoning_effort},
            "instructions": AGENT_CHAT_ROUTER_SYSTEM_PROMPT,
            "input": json.dumps(prompt_payload, ensure_ascii=False),
        }
        if self.temperature is not None and self._model_supports_temperature(self.model_name):
            request_payload["temperature"] = self.temperature
        try:
            response = self.client.responses.create(**request_payload)
        except Exception as exc:
            if "temperature" in request_payload and self._is_unsupported_temperature_error(exc):
                retry_payload = dict(request_payload)
                retry_payload.pop("temperature", None)
                response = self.client.responses.create(**retry_payload)
            else:
                raise
        payload = self._parse_json_text((response.output_text or "").strip())
        intent = self._normalize_gpt_payload(payload, message=message, context=context)
        intent.fallback_used = False
        intent.parser_status = "gpt"
        intent.model_name = self.model_name
        return intent

    def _normalize_gpt_payload(
        self,
        payload: dict[str, Any],
        *,
        message: str,
        context: dict[str, Any],
    ) -> AgentChatIntent:
        fallback = self.fallback_route(message, context)
        category = self._category(payload.get("category")) or fallback.category
        symbol_info = self._detect_symbol(
            " ".join(
                str(value or "")
                for value in (payload.get("symbol"), payload.get("symbol_name"))
            )
        )
        symbol = self._safe_symbol(payload.get("symbol")) or (symbol_info.get("symbol") if symbol_info else None)
        market = self._safe_market(payload.get("market"))
        if market is None:
            market = "KR" if symbol and re.fullmatch(r"\d{6}", symbol) else self._resolve_market(context, symbol_info)
        provider = self._safe_provider(payload.get("provider")) or self._resolve_provider(context, market)
        side = self._safe_side(payload.get("side"))
        symbol_name = self._safe_text(payload.get("symbol_name"), 80)
        if not symbol_name and symbol_info:
            symbol_name = symbol_info.get("name")
        intent = AgentChatIntent(
            category=category,
            supported=bool(payload.get("supported", True)),
            confidence=self._clamp_float(payload.get("confidence"), 0.0, 1.0),
            market=market,
            provider=provider,
            symbol=symbol,
            symbol_name=symbol_name,
            side=side,
            quantity=self._float_or_none(payload.get("quantity")),
            notional=self._float_or_none(payload.get("notional")),
            currency=self._safe_text(payload.get("currency"), 8),
            requested_profile=self._safe_strategy_profile(payload.get("requested_profile"))
            or self._detect_strategy_profile(message),
            target_monthly_return_pct=self._float_or_none(payload.get("target_monthly_return_pct"))
            or self._detect_target_monthly_return_pct(message),
            requires_plan=bool(payload.get("requires_plan", False)),
            requires_auth=bool(payload.get("requires_auth", False)),
            requires_manual_confirmation=bool(payload.get("requires_manual_confirmation", False)),
            reason=self._safe_text(payload.get("reason"), 240),
            selected_tools=self._normalize_tool_calls(payload.get("selected_tools")),
        )
        if not intent.selected_tools:
            intent.selected_tools = self._tools_for_intent(intent)
        return intent

    def _parse_json_text(self, raw_text: str) -> dict[str, Any]:
        if not raw_text:
            raise ValueError("OpenAI returned empty output_text")
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("Could not locate JSON object in OpenAI response")
            text = text[start : end + 1]
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("OpenAI response JSON was not an object")
        return parsed

    def _intent(self, category: AgentChatIntentCategory, **kwargs: Any) -> AgentChatIntent:
        selected_tools = kwargs.pop("selected_tools", None)
        intent = AgentChatIntent(category=category, **kwargs)
        if selected_tools is None:
            intent.selected_tools = self._tools_for_intent(intent)
        else:
            intent.selected_tools = self._normalize_tool_calls(selected_tools)
        return intent

    def _detect_symbol(self, text: str) -> dict[str, str] | None:
        compact = re.sub(r"\s+", "", str(text or ""))
        upper_text = str(text or "").upper()
        aliases = {
            "삼성전자": ("005930", "삼성전자", "KR", "kis"),
            "삼전": ("005930", "삼성전자", "KR", "kis"),
            "SAMSUNG ELECTRONICS": ("005930", "Samsung Electronics", "KR", "kis"),
            "005930": ("005930", "삼성전자", "KR", "kis"),
            "AAPL": ("AAPL", "Apple", "US", "alpaca"),
            "애플": ("AAPL", "Apple", "US", "alpaca"),
            "APPLE": ("AAPL", "Apple", "US", "alpaca"),
            "NVDA": ("NVDA", "NVIDIA", "US", "alpaca"),
            "엔비디아": ("NVDA", "NVIDIA", "US", "alpaca"),
            "NVIDIA": ("NVDA", "NVIDIA", "US", "alpaca"),
            "MSFT": ("MSFT", "Microsoft", "US", "alpaca"),
            "마이크로소프트": ("MSFT", "Microsoft", "US", "alpaca"),
            "MICROSOFT": ("MSFT", "Microsoft", "US", "alpaca"),
        }
        for alias, (symbol, name, market, provider) in aliases.items():
            if alias in upper_text or alias in compact:
                return {"symbol": symbol, "name": name, "market": market, "provider": provider}
        six_digit = re.search(r"\b\d{6}\b", str(text or ""))
        if six_digit:
            return {
                "symbol": six_digit.group(0),
                "name": six_digit.group(0),
                "market": "KR",
                "provider": "kis",
            }
        us_symbol = re.search(r"\b[A-Z]{1,5}\b", upper_text)
        if us_symbol:
            candidate = us_symbol.group(0)
            if candidate not in {"KR", "US", "KIS", "GPT", "API", "ETF", "RUN", "HOLD", "BUY", "SELL"}:
                return {"symbol": candidate, "name": candidate, "market": "US", "provider": "alpaca"}
        return None

    def _symbol_info_from_context(self, context: dict[str, Any]) -> dict[str, str] | None:
        symbol = str(context.get("last_symbol") or "").strip().upper()
        if not symbol:
            symbol = str(context.get("first_position_symbol") or "").strip().upper()
        if not symbol:
            snapshot = context.get("context_snapshot")
            if isinstance(snapshot, dict):
                symbol = str(snapshot.get("last_symbol") or snapshot.get("first_position_symbol") or "").strip().upper()
        if not symbol:
            return None
        market = str(context.get("last_market") or "").strip().upper()
        provider = str(context.get("last_provider") or "").strip().lower()
        snapshot = context.get("context_snapshot")
        if isinstance(snapshot, dict):
            market = market or str(snapshot.get("last_market") or "").strip().upper()
            provider = provider or str(snapshot.get("last_provider") or "").strip().lower()
        if not market:
            market = "KR" if re.fullmatch(r"\d{6}", symbol) else "US"
        if not provider:
            provider = "kis" if market == "KR" else "alpaca"
        name = str(context.get("last_symbol_name") or "").strip()
        if not name:
            name = str(context.get("first_position_name") or "").strip()
        if isinstance(snapshot, dict):
            name = name or str(snapshot.get("last_symbol_name") or snapshot.get("first_position_name") or "").strip()
        return {"symbol": symbol, "name": name or symbol, "market": market, "provider": provider}

    def _should_use_context_symbol(self, text: str, lowered: str) -> bool:
        if not str(text or "").strip():
            return False
        if self._is_price_query(text, lowered) or self._is_analysis_request(text, lowered):
            return True
        return any(
            token in text
            for token in ["그거", "이거", "그럼", "해당 종목", "방금 본", "본 종목", "첫 번째", "첫번째", "보유 중인"]
        )

    def _strategy_intent(
        self,
        text: str,
        lowered: str,
        base: dict[str, Any],
    ) -> AgentChatIntent | None:
        if self._is_strategy_live_auto_buy_recent_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_LIVE_AUTO_BUY_RECENT_QUERY,
                confidence=0.95,
                reason="User is asking for recent guarded live auto-buy attempts.",
                **base,
            )
        if self._is_strategy_live_auto_buy_block_reason_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_LIVE_AUTO_BUY_BLOCK_REASON_QUERY,
                confidence=0.95,
                reason="User is asking why guarded live auto-buy is blocked.",
                **base,
            )
        if self._is_strategy_live_auto_buy_readiness_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_LIVE_AUTO_BUY_READINESS_QUERY,
                confidence=0.95,
                reason="User is asking for guarded live auto-buy readiness.",
                **base,
            )
        if self._is_strategy_dry_run_reason_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_DRY_RUN_AUTO_BUY_REASON_QUERY,
                confidence=0.95,
                reason="User is asking why a dry-run auto-buy was blocked.",
                **base,
            )
        if self._is_strategy_dry_run_recent_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_DRY_RUN_AUTO_BUY_RECENT_QUERY,
                confidence=0.95,
                reason="User is asking for recent dry-run auto-buy results.",
                **base,
            )
        if self._is_strategy_dry_run_summary_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_DRY_RUN_AUTO_BUY_SUMMARY_QUERY,
                confidence=0.93,
                reason="User is asking for a dry-run auto-buy summary.",
                **base,
            )
        if self._is_strategy_dry_run_request(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_DRY_RUN_AUTO_BUY_REQUEST,
                confidence=0.95,
                reason="User requested a profile-aware dry-run auto-buy simulation.",
                **base,
            )
        if self._is_strategy_loss_limit_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_LOSS_LIMIT_QUERY,
                confidence=0.95,
                reason="User is asking about daily or monthly strategy loss limits.",
                **base,
            )
        if self._is_strategy_target_gate_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_TARGET_GATE_QUERY,
                confidence=0.94,
                reason="User is asking how target progress affects entry risk.",
                **base,
            )
        if self._is_strategy_order_sizing_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_ORDER_SIZING_QUERY,
                confidence=0.94,
                reason="User is asking for profile-aware order sizing.",
                **base,
            )
        if self._is_strategy_entry_risk_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_ENTRY_RISK_QUERY,
                confidence=0.94,
                reason="User is asking whether a new entry is currently allowed.",
                **base,
            )
        if self._is_strategy_risk_state_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_RISK_STATE_QUERY,
                confidence=0.92,
                reason="User is asking for the current target-aware risk state.",
                **base,
            )
        if self._is_strategy_daily_performance_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_DAILY_PERFORMANCE_QUERY,
                confidence=0.94,
                reason="User is asking for today's strategy performance.",
                **base,
            )
        if self._is_strategy_trade_performance_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_TRADE_PERFORMANCE_QUERY,
                confidence=0.92,
                reason="User is asking for trade-level performance.",
                **base,
            )
        if self._is_strategy_loss_budget_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_LOSS_BUDGET_QUERY,
                confidence=0.93,
                reason="User is asking how much loss budget has been used.",
                **base,
            )
        if self._is_strategy_target_progress_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_TARGET_PROGRESS_QUERY,
                confidence=0.94,
                reason="User is asking how much remains to a strategy target.",
                **base,
            )
        if self._is_strategy_monthly_performance_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_MONTHLY_PERFORMANCE_QUERY,
                confidence=0.94,
                reason="User is asking for current monthly strategy performance.",
                **base,
            )
        if self._is_strategy_monthly_progress_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_MONTHLY_PROGRESS_QUERY,
                confidence=0.9,
                reason="User is asking for active strategy monthly progress.",
                **base,
            )
        if self._is_strategy_risk_budget_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_RISK_BUDGET_QUERY,
                confidence=0.9,
                reason="User is asking for active strategy risk budget.",
                **base,
            )
        if self._is_strategy_compare(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_PROFILE_COMPARE,
                confidence=0.9,
                reason="User is asking to compare strategy profiles.",
                **base,
            )
        if self._is_strategy_recommendation(text, lowered):
            requested_profile = base.get("requested_profile") or self._recommend_profile_for_text(text, lowered)
            return self._intent(
                AgentChatIntentCategory.STRATEGY_PROFILE_RECOMMENDATION,
                confidence=0.88,
                reason="User is asking for a strategy profile recommendation.",
                requested_profile=requested_profile,
                **{key: value for key, value in base.items() if key != "requested_profile"},
            )
        if self._is_strategy_change_request(text, lowered):
            requested_profile = base.get("requested_profile") or self._recommend_profile_for_text(text, lowered)
            return self._intent(
                AgentChatIntentCategory.STRATEGY_PROFILE_CHANGE_REQUEST,
                confidence=0.9 if requested_profile else 0.62,
                reason="User is asking to prepare a strategy profile change.",
                supported=bool(requested_profile),
                requires_manual_confirmation=True,
                requested_profile=requested_profile,
                **{key: value for key, value in base.items() if key != "requested_profile"},
            )
        if self._is_strategy_profile_query(text, lowered):
            return self._intent(
                AgentChatIntentCategory.STRATEGY_PROFILE_QUERY,
                confidence=0.88,
                reason="User is asking about strategy profiles.",
                **base,
            )
        return None

    def _is_strategy_dry_run_request(self, text: str, lowered: str) -> bool:
        dry_context = (
            "dry-run" in lowered
            or "dry run" in lowered
            or "시뮬레이션" in text
            or "자동매수" in text
            or (
                self._detect_strategy_profile(text) is not None
                and any(
                    token in text
                    for token in ["샀을까", "살 것 같아", "매수 가능해"]
                )
            )
        )
        return dry_context and any(
            token in text
            for token in [
                "돌려봐",
                "실행",
                "샀을까",
                "살 것 같아",
                "후보 있어",
                "매수 가능해",
            ]
        )

    def _is_strategy_dry_run_recent_query(
        self,
        text: str,
        lowered: str,
    ) -> bool:
        return (
            ("dry-run" in lowered or "dry run" in lowered or "시뮬레이션" in text)
            and any(token in text for token in ["최근", "결과 보여", "뭐였어", "내역"])
        )

    def _is_strategy_dry_run_summary_query(
        self,
        text: str,
        lowered: str,
    ) -> bool:
        return (
            ("dry-run" in lowered or "dry run" in lowered or "자동매수" in text)
            and any(token in text for token in ["요약", "몇 건", "통계"])
        )

    def _is_strategy_dry_run_reason_query(
        self,
        text: str,
        lowered: str,
    ) -> bool:
        return (
            ("dry-run" in lowered or "dry run" in lowered or "자동매수" in text)
            and any(token in text for token in ["왜", "막혔", "차단", "실패"])
        )

    def _is_strategy_live_auto_buy_context(self, text: str, lowered: str) -> bool:
        return (
            "live auto buy" in lowered
            or "guarded live auto buy" in lowered
            or "strategy live auto buy" in lowered
            or "실전 자동매수" in text
            or "실전 자동 매수" in text
            or ("live" in lowered and "auto buy" in lowered)
        )

    def _is_strategy_live_auto_buy_recent_query(
        self,
        text: str,
        lowered: str,
    ) -> bool:
        if not self._is_strategy_live_auto_buy_context(text, lowered):
            return False
        return any(
            token in lowered
            for token in ["recent", "latest", "history", "result", "results"]
        ) or any(token in text for token in ["최근", "결과", "이력", "보여"])

    def _is_strategy_live_auto_buy_block_reason_query(
        self,
        text: str,
        lowered: str,
    ) -> bool:
        if not self._is_strategy_live_auto_buy_context(text, lowered):
            return False
        return any(
            token in lowered for token in ["why", "blocked", "block reason"]
        ) or any(token in text for token in ["왜", "막", "차단", "blocked"])

    def _is_strategy_live_auto_buy_readiness_query(
        self,
        text: str,
        lowered: str,
    ) -> bool:
        if not self._is_strategy_live_auto_buy_context(text, lowered):
            return False
        return any(
            token in lowered
            for token in [
                "ready",
                "readiness",
                "status",
                "available",
                "enabled",
                "limit",
            ]
        ) or any(token in text for token in ["준비", "상태", "가능", "한도", "켜"])

    def _is_strategy_loss_limit_query(self, text: str, lowered: str) -> bool:
        return (
            "loss limit" in lowered
            or "daily loss" in lowered
            or "monthly loss" in lowered
            or (
                "손실 한도" in text
                and any(token in text for token in ["오늘", "이번 달", "괜찮", "남았", "도달"])
            )
        )

    def _is_strategy_target_gate_query(self, text: str, lowered: str) -> bool:
        return (
            "target gate" in lowered
            or "target hit" in lowered
            or (
                "목표" in text
                and any(token in text for token in ["달성하면", "달성 후", "근접", "주문 크기", "진입"])
            )
            or ("연속 손실" in text and any(token in text for token in ["주문", "크기", "줄여"]))
        )

    def _is_strategy_order_sizing_query(self, text: str, lowered: str) -> bool:
        return (
            "order sizing" in lowered
            or "order size" in lowered
            or any(
                token in text
                for token in [
                    "얼마까지 주문",
                    "주문금액이 줄",
                    "주문 금액이 줄",
                    "주문 크기",
                    "권장 주문",
                ]
            )
        )

    def _is_strategy_entry_risk_query(self, text: str, lowered: str) -> bool:
        return (
            "can i buy" in lowered
            or "entry allowed" in lowered
            or "new entry" in lowered
            or any(
                token in text
                for token in [
                    "지금 매수해도",
                    "신규 진입 가능",
                    "지금 주문 가능",
                    "왜 매수가 막",
                    "왜 주문이 막",
                ]
            )
        )

    def _is_strategy_risk_state_query(self, text: str, lowered: str) -> bool:
        return (
            "risk state" in lowered
            or "entry risk" in lowered
            or "리스크 상태" in text
            or ("신규 진입" in text and any(token in text for token in ["상태", "가능"]))
        )

    def _is_strategy_daily_performance_query(self, text: str, lowered: str) -> bool:
        return (
            "daily pnl" in lowered
            or "today pnl" in lowered
            or ("오늘" in text and any(token in text for token in ["손익", "수익률", "손실 한도"]))
        )

    def _is_strategy_monthly_performance_query(self, text: str, lowered: str) -> bool:
        return (
            "monthly pnl" in lowered
            or "monthly return" in lowered
            or ("이번 달" in text and any(token in text for token in ["수익률", "손익", "성과"]))
        )

    def _is_strategy_target_progress_query(self, text: str, lowered: str) -> bool:
        return (
            "target progress" in lowered
            or "target remaining" in lowered
            or (
                "목표" in text
                and any(token in text for token in ["얼마나 남", "몇 퍼센트 남", "달성", "진행"])
            )
        )

    def _is_strategy_trade_performance_query(self, text: str, lowered: str) -> bool:
        return (
            "trade performance" in lowered
            or "recent trade return" in lowered
            or (
                "거래" in text
                and any(token in text for token in ["수익률", "손실", "실현손익", "제일"])
            )
            or ("실현손익" in text and "평가손익" in text)
        )

    def _is_strategy_loss_budget_query(self, text: str, lowered: str) -> bool:
        return (
            "loss budget" in lowered
            or ("손실 한도" in text and any(token in text for token in ["얼마나", "썼", "괜찮", "도달"]))
        )

    def _is_strategy_monthly_progress_query(self, text: str, lowered: str) -> bool:
        return (
            "monthly progress" in lowered
            or "이번 달 목표 진행" in text
            or "목표 진행률" in text
            or ("이번 달" in text and "목표" in text and "전략" in text)
        )

    def _is_strategy_risk_budget_query(self, text: str, lowered: str) -> bool:
        return (
            "risk budget" in lowered
            or "리스크 예산" in text
            or "위험 예산" in text
            or (("손실 한도" in text or "주문 한도" in text) and self._mentions_strategy(text, lowered))
        )

    def _is_strategy_compare(self, text: str, lowered: str) -> bool:
        if "strategy" in lowered and any(token in lowered for token in ["compare", "difference", "vs"]):
            return True
        if any(token in text for token in ["차이", "비교", "다른 점", "vs", "VS"]):
            return any(profile in text for profile in ["안정형", "보통형", "고수익형", "safe", "balanced", "aggressive"])
        return False

    def _is_strategy_recommendation(self, text: str, lowered: str) -> bool:
        if not self._mentions_strategy(text, lowered) and not any(token in text for token in ["월 3~5", "월 5", "손실이 걱정"]):
            return False
        return (
            "recommend" in lowered
            or any(token in text for token in ["추천", "좋아", "괜찮", "뭐 써", "뭐가", "어떤 프로필", "목표면", "손실이 걱정"])
        )

    def _is_strategy_change_request(self, text: str, lowered: str) -> bool:
        if not self._mentions_strategy(text, lowered) and self._recommend_profile_for_text(text, lowered) is None:
            return False
        if any(token in text for token in ["뭐야", "뭐 써", "어떤", "추천", "차이", "비교", "괜찮아", "알려줘", "보여줘"]):
            return False
        return (
            "set strategy" in lowered
            or "change strategy" in lowered
            or any(token in text for token in ["바꿔", "바꾸", "변경", "설정", "적용", "해줘", "싶어", "운용하고 싶어", "가자", "목표로"])
        )

    def _is_strategy_profile_query(self, text: str, lowered: str) -> bool:
        if not self._mentions_strategy(text, lowered):
            return False
        return (
            "profile" in lowered
            or "strategy" in lowered
            or any(token in text for token in ["현재 전략", "지금 안정형", "목표 수익률", "어떤 조건", "뭐야", "설명", "보여줘", "조회"])
        )

    def _mentions_strategy(self, text: str, lowered: str) -> bool:
        return (
            "strategy" in lowered
            or "profile" in lowered
            or any(token in text for token in ["전략", "프로필", "안정형", "보통형", "고수익형", "목표 수익률", "월 목표"])
        )

    def _detect_strategy_profile(self, text: str) -> str | None:
        lowered = str(text or "").lower()
        compact = re.sub(r"\s+", "", str(text or ""))
        if (
            "balanced" in lowered
            or "보통형" in text
            or "보통" in text
            or "월3~5" in compact
            or "월3-5" in compact
            or "3~5%" in text
            or "3~5프로" in text
        ):
            return "balanced"
        if (
            "aggressive" in lowered
            or "고수익형" in text
            or "고수익" in text
            or "공격" in text
            or "5% 이상" in text
            or "5프로 이상" in text
            or "월5프로이상" in compact
            or "월5%이상" in compact
        ):
            return "aggressive"
        if "safe" in lowered or "안정형" in text or "안전" in text or "보수" in text:
            return "safe"
        return None

    def _recommend_profile_for_text(self, text: str, lowered: str) -> str | None:
        detected = self._detect_strategy_profile(text)
        if detected:
            return detected
        if "손실" in text and any(token in text for token in ["걱정", "줄", "낮", "안전"]):
            return "safe"
        if "3~5" in text or "3-5" in text:
            return "balanced"
        if "5%" in text or "5프로" in text or "공격" in text:
            return "aggressive"
        return None

    def _detect_target_monthly_return_pct(self, text: str) -> float | None:
        compact = str(text or "").replace(" ", "")
        match = re.search(r"월(\d+(?:\.\d+)?)(?:%|프로)", compact)
        if not match:
            return None
        try:
            return float(match.group(1)) / 100
        except Exception:
            return None

    def _tools_for_intent(self, intent: AgentChatIntent) -> list[AgentChatToolCall]:
        category = intent.category
        symbol = str(intent.symbol or "").strip().upper()
        provider = str(intent.provider or "").strip().lower()
        if category == AgentChatIntentCategory.READ_ONLY_PRICE_QUERY:
            tool_name = "kis_price_lookup" if provider == "kis" or intent.market == "KR" else "alpaca_price_lookup"
            return [self._tool_call(tool_name, {"symbol": symbol}, "User asked for a current price.")]
        if category == AgentChatIntentCategory.READ_ONLY_POSITIONS_QUERY:
            return [self._tool_call("kis_positions_lookup", {}, "User asked for current positions.")]
        if category == AgentChatIntentCategory.READ_ONLY_BALANCE_QUERY:
            return [self._tool_call("kis_balance_lookup", {}, "User asked for account balance.")]
        if category == AgentChatIntentCategory.READ_ONLY_ORDERS_QUERY:
            return [self._tool_call("recent_orders_lookup", {}, "User asked for recent orders.")]
        if category == AgentChatIntentCategory.READ_ONLY_RUNS_QUERY:
            return [self._tool_call("recent_runs_lookup", {}, "User asked for recent runs.")]
        if category == AgentChatIntentCategory.READ_ONLY_SIGNALS_QUERY:
            return [self._tool_call("recent_signals_lookup", {}, "User asked for recent signals.")]
        if category == AgentChatIntentCategory.READ_ONLY_SETTINGS_QUERY:
            return [self._tool_call("ops_settings_lookup", {}, "User asked for runtime safety status.")]
        if category == AgentChatIntentCategory.STRATEGY_PROFILE_QUERY:
            tool_name = "active_strategy_profile_lookup" if not intent.requested_profile else "strategy_profiles_lookup"
            return [self._tool_call(tool_name, {"profile_name": intent.requested_profile}, "User asked about strategy profiles.")]
        if category == AgentChatIntentCategory.STRATEGY_PROFILE_COMPARE:
            return [self._tool_call("strategy_profiles_lookup", {}, "User asked to compare strategy profiles.")]
        if category == AgentChatIntentCategory.STRATEGY_PROFILE_RECOMMENDATION:
            return [self._tool_call("strategy_profiles_lookup", {"requested_profile": intent.requested_profile}, "User asked for a strategy recommendation.")]
        if category == AgentChatIntentCategory.STRATEGY_MONTHLY_PROGRESS_QUERY:
            return [self._tool_call("strategy_monthly_progress_lookup", {}, "User asked for monthly strategy target progress.")]
        if category == AgentChatIntentCategory.STRATEGY_RISK_BUDGET_QUERY:
            return [self._tool_call("strategy_risk_budget_lookup", {}, "User asked for strategy risk budget.")]
        if category == AgentChatIntentCategory.STRATEGY_DAILY_PERFORMANCE_QUERY:
            return [self._tool_call("strategy_daily_performance_lookup", {}, "User asked for today's P&L.")]
        if category == AgentChatIntentCategory.STRATEGY_MONTHLY_PERFORMANCE_QUERY:
            return [self._tool_call("strategy_monthly_performance_lookup", {}, "User asked for monthly P&L.")]
        if category == AgentChatIntentCategory.STRATEGY_TRADE_PERFORMANCE_QUERY:
            return [self._tool_call("strategy_trade_performance_lookup", {"symbol": symbol}, "User asked for trade performance.")]
        if category in {
            AgentChatIntentCategory.STRATEGY_TARGET_PROGRESS_QUERY,
            AgentChatIntentCategory.STRATEGY_LOSS_BUDGET_QUERY,
        }:
            return [self._tool_call("strategy_target_progress_lookup", {"profile_name": intent.requested_profile}, "User asked for target or loss-budget progress.")]
        if category in {
            AgentChatIntentCategory.STRATEGY_RISK_STATE_QUERY,
            AgentChatIntentCategory.STRATEGY_LOSS_LIMIT_QUERY,
            AgentChatIntentCategory.STRATEGY_TARGET_GATE_QUERY,
        }:
            return [self._tool_call("strategy_risk_state_lookup", {}, "User asked for target-aware risk state.")]
        if category == AgentChatIntentCategory.STRATEGY_ENTRY_RISK_QUERY:
            return [
                self._tool_call(
                    "strategy_entry_risk_evaluate",
                    {"requested_notional_krw": intent.notional},
                    "User asked for a read-only entry risk evaluation.",
                )
            ]
        if category == AgentChatIntentCategory.STRATEGY_ORDER_SIZING_QUERY:
            return [
                self._tool_call(
                    "strategy_order_sizing_lookup",
                    {"requested_notional_krw": intent.notional},
                    "User asked for a read-only order sizing recommendation.",
                )
            ]
        if category == AgentChatIntentCategory.STRATEGY_DRY_RUN_AUTO_BUY_REQUEST:
            return [
                self._tool_call(
                    "strategy_dry_run_auto_buy_once",
                    {
                        "profile_name": intent.requested_profile,
                        "symbol": symbol,
                    },
                    "User requested a profile-aware dry-run buy simulation.",
                )
            ]
        if category in {
            AgentChatIntentCategory.STRATEGY_DRY_RUN_AUTO_BUY_RECENT_QUERY,
            AgentChatIntentCategory.STRATEGY_DRY_RUN_AUTO_BUY_REASON_QUERY,
        }:
            return [
                self._tool_call(
                    "strategy_dry_run_auto_buy_recent_lookup",
                    {
                        "profile_name": intent.requested_profile,
                        "symbol": symbol,
                    },
                    "User asked for recent dry-run buy results.",
                )
            ]
        if category == AgentChatIntentCategory.STRATEGY_DRY_RUN_AUTO_BUY_SUMMARY_QUERY:
            return [
                self._tool_call(
                    "strategy_dry_run_auto_buy_summary_lookup",
                    {},
                    "User asked for a dry-run buy summary.",
                )
            ]
        if category in {
            AgentChatIntentCategory.STRATEGY_LIVE_AUTO_BUY_READINESS_QUERY,
            AgentChatIntentCategory.STRATEGY_LIVE_AUTO_BUY_BLOCK_REASON_QUERY,
        }:
            return [
                self._tool_call(
                    "strategy_live_auto_buy_readiness_lookup",
                    {"symbol": symbol},
                    "User asked for guarded live auto-buy readiness.",
                )
            ]
        if category == AgentChatIntentCategory.STRATEGY_LIVE_AUTO_BUY_RECENT_QUERY:
            return [
                self._tool_call(
                    "strategy_live_auto_buy_recent_lookup",
                    {},
                    "User asked for recent guarded live auto-buy attempts.",
                )
            ]
        if category == AgentChatIntentCategory.STRATEGY_PROFILE_CHANGE_REQUEST:
            return [self._tool_call("strategy_profile_change_prepare", {"requested_profile": intent.requested_profile}, "User asked to prepare a strategy profile change.")]
        if category in {AgentChatIntentCategory.ANALYSIS_REQUEST, AgentChatIntentCategory.EXIT_REVIEW_REQUEST}:
            return [self._tool_call("safe_symbol_analysis", {"symbol": symbol}, "User asked for safe analysis.")]
        if category == AgentChatIntentCategory.WATCHLIST_PREVIEW_REQUEST:
            return [self._tool_call("watchlist_preview", {}, "User asked for a watchlist preview.")]
        if category == AgentChatIntentCategory.MANUAL_TICKET_REQUEST:
            return [self._tool_call("manual_ticket_prefill", {"symbol": symbol}, "Manual ticket review is required.")]
        if category == AgentChatIntentCategory.LIVE_ORDER_REQUEST:
            return [self._tool_call("live_order_request_blocker", {"symbol": symbol}, "Live orders are blocked from chat.")]
        if category in {AgentChatIntentCategory.DANGEROUS_SETTING_REQUEST, AgentChatIntentCategory.SCHEDULER_REQUEST}:
            return [self._tool_call("settings_change_blocker", {}, "Settings or scheduler changes are blocked from chat.")]
        return []

    def _tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        reason: str,
    ) -> AgentChatToolCall:
        clean_args = {key: value for key, value in arguments.items() if value not in (None, "")}
        return AgentChatToolCall(tool_name=tool_name, arguments=clean_args, reason=reason)

    def _normalize_tool_calls(self, value: Any) -> list[AgentChatToolCall]:
        if not isinstance(value, list):
            return []
        calls: list[AgentChatToolCall] = []
        for item in value[:4]:
            if not isinstance(item, dict):
                continue
            tool_name = self._safe_text(item.get("tool_name"), 80)
            if not tool_name:
                continue
            args = item.get("arguments")
            calls.append(
                AgentChatToolCall(
                    tool_name=tool_name,
                    arguments=dict(args) if isinstance(args, dict) else {},
                    reason=self._safe_text(item.get("reason"), 240),
                )
            )
        return calls

    def _resolve_market(self, context: dict[str, Any], symbol_info: dict[str, str] | None) -> str:
        if symbol_info and symbol_info.get("market"):
            return symbol_info["market"]
        snapshot = context.get("context_snapshot")
        raw = str(
            context.get("last_market")
            or (snapshot.get("last_market") if isinstance(snapshot, dict) else None)
            or context.get("default_market")
            or context.get("market")
            or ""
        ).strip().upper()
        if raw in {"US", "KR", "ALL"}:
            return raw
        return "UNKNOWN"

    def _resolve_provider(self, context: dict[str, Any], market: str) -> str:
        if market == "KR":
            return "kis"
        if market == "US":
            return "alpaca"
        snapshot = context.get("context_snapshot")
        raw = str(
            context.get("last_provider")
            or (snapshot.get("last_provider") if isinstance(snapshot, dict) else None)
            or context.get("default_provider")
            or context.get("provider")
            or ""
        ).strip().lower()
        if raw in {"alpaca", "kis", "all"}:
            return raw
        return "unknown"

    def _detect_side(self, text: str) -> str:
        lowered = text.lower()
        if any(token in text for token in ["매도", "팔", "전량"]) or "sell" in lowered:
            return "sell"
        if any(token in text for token in ["매수", "사줘", "사는", "사 "]) or "buy" in lowered:
            return "buy"
        return "none"

    def _parse_amount(self, text: str) -> float | None:
        compact = str(text or "").replace(",", "")
        man = re.search(r"(\d+(?:\.\d+)?)\s*만\s*원?", compact)
        if man:
            return float(man.group(1)) * 10000
        won = re.search(r"(\d+(?:\.\d+)?)\s*원", compact)
        if won:
            return float(won.group(1))
        dollar = re.search(r"\$\s*(\d+(?:\.\d+)?)", compact)
        if dollar:
            return float(dollar.group(1))
        dollar_word = re.search(r"(\d+(?:\.\d+)?)\s*달러", compact)
        if dollar_word:
            return float(dollar_word.group(1))
        return None

    def _parse_quantity(
        self,
        text: str,
        symbol_info: dict[str, str] | None,
    ) -> float | None:
        symbol = str((symbol_info or {}).get("symbol") or "").strip()
        for match in re.finditer(r"\b(\d{1,5})\b", str(text or "")):
            value = match.group(1)
            if value == symbol:
                continue
            try:
                number = int(value)
            except Exception:
                continue
            if 1 <= number <= 10000:
                return float(number)
        return None

    def _is_price_query(self, text: str, lowered: str) -> bool:
        return any(token in text for token in ["가격", "현재가", "주가", "얼마"]) or "price" in lowered

    def _is_positions_query(self, text: str, lowered: str) -> bool:
        return any(token in text for token in ["보유종목", "보유 종목", "포지션", "들고 있어", "보유 중", "가지고 있어"]) or "positions" in lowered

    def _is_balance_query(self, text: str, lowered: str) -> bool:
        return any(token in text for token in ["잔고", "현금", "계좌 상태", "예수금", "평가손익", "손익"]) or "balance" in lowered or "cash" in lowered

    def _is_orders_query(self, text: str) -> bool:
        return "주문" in text and any(token in text for token in ["기록", "내역", "최근", "오늘", "보여", "조회"])

    def _is_runs_query(self, text: str, lowered: str) -> bool:
        return (
            any(token in text for token in ["실행 로그", "실행 기록", "런 기록"])
            or "run log" in lowered
            or "runs" in lowered
            or ("run" in lowered and any(token in text for token in ["결과", "기록", "로그", "마지막", "최근"]))
            or ("최근" in text and any(token in text for token in ["매수 안", "hold", "HOLD", "이유"]))
        )

    def _is_signals_query(self, text: str, lowered: str) -> bool:
        return "신호" in text or "시그널" in text or "signals" in lowered

    def _is_analysis_request(self, text: str, lowered: str) -> bool:
        return any(token in text for token in ["살만", "분석", "봐줘", "검토", "진입 괜찮"]) or "analysis" in lowered or "analyze" in lowered

    def _is_manual_ticket_request(self, text: str) -> bool:
        return any(token in text for token in ["티켓", "주문서", "주문 표"]) and any(token in text for token in ["준비", "만들", "작성"])

    def _is_live_order_request(self, text: str) -> bool:
        lowered = text.lower()
        direct_tokens = ["사줘", "매수해", "바로 매수", "팔아", "매도해", "전량 매도", "주문 넣어", "주문해"]
        return any(token in text for token in direct_tokens) or "buy now" in lowered or "sell now" in lowered

    def _is_dangerous_setting_request(self, text: str) -> bool:
        lowered = text.lower()
        dangerous = (
            "dry run" in lowered
            or "kill switch" in lowered
            or "auto buy" in lowered
            or "드라이런" in text
            or "드라이 런" in text
            or "킬스위치" in text
            or "킬 스위치" in text
            or "자동 매수" in text
        )
        mutate = any(token in lowered for token in ["off", "on", "disable", "enable"]) or any(
            token in text for token in ["꺼", "끄", "켜", "활성", "비활성"]
        )
        return dangerous and mutate

    def _is_settings_status_query(self, text: str, lowered: str) -> bool:
        mentions_setting = (
            "dry run" in lowered
            or "dry-run" in lowered
            or "kill switch" in lowered
            or "scheduler" in lowered
            or "드라이런" in text
            or "드라이 런" in text
            or "킬스위치" in text
            or "킬 스위치" in text
            or "봇" in text
            or "스케줄러" in text
            or "시스템 상태" in text
        )
        status_word = (
            "status" in lowered
            or "enabled" in lowered
            or "켜져" in text
            or "꺼져" in text
            or "상태" in text
            or "확인" in text
            or "어떻게" in text
            or "알려" in text
        )
        return mentions_setting and status_word

    def _is_scheduler_request(self, text: str, lowered: str) -> bool:
        return "스케줄" in text or "scheduler" in lowered

    def _is_capability_question(self, text: str, lowered: str) -> bool:
        return any(token in text for token in ["뭐 할 수", "무엇을 할 수", "기능", "도움"]) or "what can you" in lowered or "help" == lowered

    def _is_unsupported(self, text: str) -> bool:
        lowered = text.lower()
        return (
            any(token in text for token in ["비트코인", "선물", "100배", "롱", "숏", "옵션", "코인", "은행", "자동입금", "해외선물"])
            or "crypto" in lowered
            or "futures" in lowered
            or "option" in lowered
        )

    def _is_watchlist_preview_request(self, text: str, lowered: str) -> bool:
        return any(token in text for token in ["워치리스트", "후보 종목", "후보"]) or "watchlist" in lowered

    def _is_exit_review_request(self, text: str, lowered: str) -> bool:
        return (
            any(token in text for token in ["팔아야", "매도해야", "정리해야", "나가야", "매도 검토", "청산 검토"])
            or "exit review" in lowered
            or "sell review" in lowered
        )

    def _category(self, value: Any) -> AgentChatIntentCategory | None:
        raw = str(value or "").strip()
        for category in AgentChatIntentCategory:
            if raw == category.value:
                return category
        return None

    def _safe_market(self, value: Any) -> str | None:
        raw = str(value or "").strip().upper()
        return raw if raw in {"KR", "US", "ALL", "UNKNOWN"} else None

    def _safe_provider(self, value: Any) -> str | None:
        raw = str(value or "").strip().lower()
        return raw if raw in {"kis", "alpaca", "all", "unknown"} else None

    def _safe_strategy_profile(self, value: Any) -> str | None:
        raw = str(value or "").strip().lower()
        return raw if raw in {"safe", "balanced", "aggressive"} else None

    def _safe_side(self, value: Any) -> str:
        raw = str(value or "").strip().lower()
        return raw if raw in {"buy", "sell", "none", "unknown"} else "none"

    def _safe_symbol(self, value: Any) -> str | None:
        raw = str(value or "").strip().upper()
        return raw or None

    def _safe_text(self, value: Any, max_length: int) -> str | None:
        text = str(value or "").strip()
        return text[:max_length] if text else None

    def _float_or_none(self, value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(value)
        except Exception:
            return None

    def _clamp_float(self, value: Any, min_value: float, max_value: float) -> float:
        try:
            number = float(value)
        except Exception:
            number = min_value
        return max(min_value, min(number, max_value))

    def _model_supports_temperature(self, model_name: str | None) -> bool:
        return not str(model_name or "").strip().lower().startswith("gpt-5")

    def _is_unsupported_temperature_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "unsupported parameter" in message and "temperature" in message
