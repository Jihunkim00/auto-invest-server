from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.agent_chat_orchestrator import AgentChatIntent, AgentChatSendRequest
from app.schemas.agent_chat_v2 import AgentChatV2MessageRequest
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_live_order_service import AgentChatLiveOrderService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService
from app.services.agent_chat_privacy_service import (
    AgentChatContextPrivacyService,
    AgentChatPrivacyClass,
)


class AgentChatV2Service:
    """Small V2 facade over the existing guarded Agent Chat orchestration.

    V2 changes the response contract and user-facing intent names. It does not
    add a broker client or a second confirmation/submit implementation.
    """

    def __init__(
        self,
        *,
        orchestrator: AgentChatOrchestratorService | None = None,
        intent_router: AgentChatIntentRouterService | None = None,
        live_order_service: AgentChatLiveOrderService | None = None,
        answer_composer: Any | None = None,
        privacy_service: AgentChatContextPrivacyService | None = None,
    ) -> None:
        self.intent_router = intent_router or AgentChatIntentRouterService()
        self.live_order_service = live_order_service or AgentChatLiveOrderService()
        self.orchestrator = orchestrator or AgentChatOrchestratorService(
            intent_router=self.intent_router,
        )
        self.answer_composer = answer_composer
        self.privacy_service = privacy_service or AgentChatContextPrivacyService()

    def send(self, db: Session, *, request: AgentChatV2MessageRequest) -> dict[str, Any]:
        started = time.perf_counter()
        context = dict(request.context or {})
        routed = self.intent_router.route(message=request.message, context=context)
        router_gpt_called = bool(
            getattr(
                self.intent_router,
                "last_gpt_called",
                bool(getattr(self.intent_router, "client", None)),
            )
        )
        guarded = self.intent_router.fallback_route(request.message, context)
        if guarded.category.value in {
            "read_only_price_query",
            "affordability_query",
            "explain_indicator_query",
            "read_only_balance_query",
            "read_only_positions_query",
            "read_only_orders_query",
            "read_only_runs_query",
            "read_only_signals_query",
            "analysis_request",
            "dangerous_setting_request",
            "live_order_request",
        }:
            routed = guarded
        routed.router_gpt_called = router_gpt_called
        if router_gpt_called and not routed.model_name:
            routed.model_name = getattr(self.intent_router, "model_name", None)
        intent_name = self._intent_name(request.message, routed)

        legacy_payload = request.legacy_payload()
        legacy_context = dict(legacy_payload.get("context") or {})
        legacy_context["_v2_routed_intent"] = routed.model_dump(mode="json")
        legacy_payload["context"] = legacy_context
        legacy = self.orchestrator.send(
            db,
            request=AgentChatSendRequest.model_validate(legacy_payload),
        )

        preview = None
        if intent_name == "trade_prepare" and not legacy.get("live_order_action"):
            preview = self.live_order_service.prepare(
                db,
                intent=routed,
                conversation_key=str(legacy.get("conversation_key") or ""),
                user_message_id=legacy.get("user_message_id"),
                preview_only=True,
            )
            if preview.get("created") is True:
                action = dict(preview.get("action") or {})
                preview_readiness = self.live_order_service.readiness(db)
                legacy["live_order_action"] = action
                legacy["data"] = {
                    **dict(legacy.get("data") or {}),
                    "order_preview": action,
                    "readiness": preview_readiness,
                }
                legacy["available_actions"] = [
                    *list(legacy.get("available_actions") or []),
                    "confirm_live_order",
                    "cancel_live_order",
                ]
                self.live_order_service.update_assistant_message_id(
                    db,
                    action_id=int(action.get("action_id") or 0),
                    assistant_message_id=legacy.get("assistant_message_id"),
                )

        return self._response(
            request=request,
            routed=routed,
            intent_name=intent_name,
            legacy=legacy,
            preview=preview,
            started=started,
        )

    def _intent_name(self, message: str, routed: AgentChatIntent) -> str:
        category = routed.category.value
        text = str(message or "").strip().lower()
        if any(token in str(message or "") for token in ("안전장치", "킬스위치", "kill_switch", "dry_run", "드라이런", "설정 꺼", "설정 켜")):
            return "safety_block"
        if any(token in str(message or "") for token in ("사고 싶", "매수해", "팔고 싶", "매도해")):
            return "trade_prepare"
        if any(token in str(message or "") for token in ("왜 안 샀", "왜 안샀", "왜 매수 안", "오늘 왜 hold", "최근 판단", "자동매매 결과")):
            return "explain"
        if any(token in str(message or "") for token in ("포트폴리오", "보유 종목", "보유한 종목", "수익 중인 종목", "손실 큰 종목")):
            return "portfolio"
        if category == "affordability_query":
            return "affordability"
        if category == "explain_indicator_query":
            return "explain_indicator"
        if category == "read_only_price_query":
            return "quote"
        if category == "read_only_balance_query":
            return "account"
        if category == "read_only_orders_query":
            return "recent_activity"
        if any(token in str(message or "") for token in ("분석", "살만해", "analyze", "analysis")):
            return "analyze"
        if category in {"analysis_request", "watchlist_preview_request"}:
            return "analyze"
        if category in {"read_only_positions_query", "read_only_balance_query"}:
            return "portfolio"
        if category in {"read_only_runs_query", "read_only_signals_query", "read_only_daily_ops_summary_query"}:
            return "explain"
        if category in {"live_order_request", "manual_ticket_request"}:
            return "trade_prepare"
        if category == "dangerous_setting_request":
            return "safety_block"
        if category == "general_chat":
            return "general_chat"
        return "explain" if text else "general_chat"

    def _response(
        self,
        *,
        request: AgentChatV2MessageRequest,
        routed: AgentChatIntent,
        intent_name: str,
        legacy: dict[str, Any],
        preview: dict[str, Any] | None,
        started: float,
    ) -> dict[str, Any]:
        action = legacy.get("live_order_action")
        order_preview = self._order_preview(action)
        requires_confirmation = bool(
            intent_name == "trade_prepare"
            and isinstance(action, dict)
            and str(action.get("status") or "") in {"pending_confirmation", "pending"}
        )
        status = "completed"
        if intent_name == "trade_prepare":
            status = "confirmation_required" if requires_confirmation else "blocked"
        elif intent_name == "safety_block":
            status = "blocked"
        elif not bool((legacy.get("intent") or {}).get("supported", True)):
            status = "needs_clarification"
        elif str((legacy.get("answer") or {}).get("answer_type") or "") == "error":
            status = "error"
        elif intent_name == "quote":
            price_data = (legacy.get("data") or {}).get("price")
            if not isinstance(price_data, dict) or price_data.get("price", price_data.get("current_price")) is None:
                status = "error"

        safety = dict(legacy.get("safety") or {})
        safety["real_order_submitted"] = False
        safety["broker_submit_called"] = False
        safety["manual_submit_called"] = False
        safety["setting_changed"] = False
        safety["scheduler_changed"] = False
        if preview is not None:
            safety["preview_only"] = True

        data = dict(legacy.get("data") or {})
        symbol = str(
            (legacy.get("intent") or {}).get("symbol")
            or routed.symbol
            or ""
        ).strip() or None
        symbol_name = str(
            (legacy.get("intent") or {}).get("symbol_name")
            or routed.symbol_name
            or ""
        ).strip() or None
        baseline_message = self._user_message(
            intent_name=intent_name,
            legacy=legacy,
            symbol=symbol,
            symbol_name=symbol_name,
            order_preview=order_preview,
            user_text=request.message,
        )
        message, compose_diagnostics = self._compose_answer(
            request=request,
            routed=routed,
            intent_name=intent_name,
            legacy=legacy,
            data=data,
            baseline_message=baseline_message,
        )
        analysis = (
            {}
            if intent_name in {"quote", "account", "affordability", "explain_indicator", "general_chat"}
            else self._analysis_payload(data, legacy)
        )
        risk = self._risk_payload(data, legacy)
        selected_tools = legacy.get("selected_tools") or []
        tool_names = [
            item.get("tool_name") if isinstance(item, dict) else getattr(item, "tool_name", None)
            for item in selected_tools
        ]
        legacy_intent = legacy.get("intent") if isinstance(legacy.get("intent"), dict) else {}
        parser_status = str(legacy_intent.get("parser_status") or getattr(routed, "parser_status", "unknown"))
        intent_parser_fallback_used = bool(
            legacy_intent.get("fallback_used")
            or parser_status in {"fallback", "failed_fallback_used", "privacy_blocked_fallback"}
        )
        intent_parser_status = {
            "fallback": "deterministic_fallback",
            "failed_fallback_used": "deterministic_fallback_after_gpt_error",
        }.get(parser_status, parser_status)
        chat_gpt_fallback_used = bool(compose_diagnostics.get("fallback_used"))
        market_gpt_fallback_used = bool(analysis.get("market_gpt_fallback_used", False))
        diagnostics = {
            "legacy_category": (legacy.get("intent") or {}).get("category"),
            "parser_status": (legacy.get("intent") or {}).get("parser_status"),
            "intent_parser_status": intent_parser_status,
            "intent_parser_fallback_used": intent_parser_fallback_used,
            "preview_created": bool(preview and preview.get("created") is True),
            "intent": intent_name,
            "symbol": symbol,
            "tool": next((name for name in tool_names if name), None),
            "tool_names": [name for name in tool_names if name],
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "router_gpt_called": bool(getattr(routed, "router_gpt_called", False)),
            "router_provider": "openai" if getattr(routed, "router_gpt_called", False) else None,
            "router_model": routed.model_name,
            "chat_model": getattr(self.intent_router, "model_name", None),
            "chat_reasoning_effort": getattr(self.intent_router, "reasoning_effort", None),
            "chat_gpt_used": bool(compose_diagnostics.get("gpt_used")),
            "chat_gpt_fallback_used": chat_gpt_fallback_used,
            "market_model": analysis.get("market_model"),
            "market_reasoning_effort": analysis.get("market_reasoning_effort"),
            "market_gpt_used": bool(analysis.get("market_gpt_used", analysis.get("gpt_used", False))),
            "market_fallback_used": bool(analysis.get("fallback_used", False)),
            "market_gpt_fallback_used": market_gpt_fallback_used,
            **compose_diagnostics,
        }
        fallback_used = bool(compose_diagnostics.get("fallback_used"))
        market_gpt_used = bool(analysis.get("market_gpt_used", analysis.get("gpt_used", False)))
        market_fallback_used = bool(analysis.get("fallback_used", False))
        return {
            "intent": intent_name,
            "status": status,
            "message": message,
            "answer": message,
            "language": request.language,
            "conversation_key": legacy.get("conversation_key"),
            "symbol": symbol,
            "symbol_name": symbol_name,
            "market": (legacy.get("intent") or {}).get("market") or routed.market,
            "action": analysis.get("action"),
            "scores": analysis.get("scores", {}),
            "confidence": analysis.get("confidence"),
            "risk": risk,
            "readiness": data.get("readiness") if isinstance(data.get("readiness"), dict) else {},
            "analysis": analysis,
            "portfolio": self._portfolio_payload(data),
            "order_preview": order_preview,
            "requires_confirmation": requires_confirmation,
            "available_actions": legacy.get("available_actions") or [],
            "result_cards": legacy.get("result_cards") or [],
            "follow_up_suggestions": legacy.get("follow_up_suggestions") or [],
            "context_snapshot": legacy.get("context_snapshot") or {},
            "safety": safety,
            "data": data,
            "gpt_used": bool(compose_diagnostics.get("gpt_used")),
            "fallback_used": fallback_used,
            "market_gpt_used": market_gpt_used,
            "market_fallback_used": market_fallback_used,
            "chat_gpt_fallback_used": chat_gpt_fallback_used,
            "market_gpt_fallback_used": market_gpt_fallback_used,
            "trade_action": order_preview if intent_name == "trade_prepare" else None,
            "diagnostics": diagnostics,
        }

    def _user_message(
        self,
        *,
        intent_name: str,
        legacy: dict[str, Any],
        symbol: str | None,
        symbol_name: str | None,
        order_preview: dict[str, Any] | None,
        user_text: str = "",
    ) -> str:
        data = dict(legacy.get("data") or {})
        if intent_name == "quote":
            price = data.get("price") if isinstance(data.get("price"), dict) else {}
            value = price.get("price", price.get("current_price"))
            error = data.get("error") or price.get("error")
            label = symbol_name or price.get("name") or symbol or "해당 종목"
            if error or value is None:
                return f"{label} 현재가를 조회하지 못했습니다. 잠시 후 다시 시도해 주세요. 주문은 실행하지 않았습니다."
            currency = str(price.get("currency") or "KRW")
            return (
                f"{label}({symbol or price.get('symbol') or ''}) 현재가는 {self._money(value, currency)}입니다. "
                "실시간 read-only 조회만 수행했으며 주문은 실행하지 않았습니다."
            )
        if intent_name == "affordability":
            return self._affordability_message(data, legacy, symbol_name=symbol_name, symbol=symbol)
        if intent_name == "explain_indicator":
            return self._indicator_message(user_text)
        if intent_name in {"account", "general_chat"}:
            answer = str((legacy.get("answer") or {}).get("text") or "").strip()
            if answer:
                return answer
            return "계좌 정보를 조회할 수 있습니다. 현재 요청에서는 주문을 실행하지 않았습니다."
        if intent_name == "recent_activity":
            orders = data.get("orders") if isinstance(data.get("orders"), list) else []
            signals = data.get("signals") if isinstance(data.get("signals"), list) else []
            count = data.get("count", len(orders) or len(signals))
            return f"최근 활동 {int(count or 0)}건을 조회했습니다. 조회만 수행했으며 주문은 실행하지 않았습니다."
        if intent_name == "trade_prepare":
            if order_preview:
                label = symbol_name or symbol or "종목"
                return f"{label} 주문 준비가 완료되었습니다. 실제 주문은 확인 버튼 이후 backend가 다시 검증합니다."
            return "주문을 준비하지 못했습니다. 종목·매수/매도 방향·수량을 확인해 주세요. 실제 주문은 실행되지 않았습니다."
        if intent_name == "safety_block":
            return "안전 설정은 Agent가 변경할 수 없습니다. Settings/Admin에서 직접 확인해 주세요."
        if intent_name == "portfolio":
            portfolio = self._portfolio_payload(dict(legacy.get("data") or {}))
            return f"현재 보유 종목은 {portfolio.get('count', 0)}개입니다. 조회만 수행했으며 주문은 실행하지 않았습니다."
        if intent_name == "explain":
            runs = (legacy.get("data") or {}).get("runs")
            if isinstance(runs, list) and runs:
                first = runs[0] if isinstance(runs[0], dict) else {}
                action = str(first.get("action") or first.get("decision") or first.get("result") or "HOLD").upper()
                return f"최근 자동매매 판단은 {action}였습니다. 실제 decision/log를 기반으로 설명했으며 주문은 실행하지 않았습니다."
            return "최근 decision 기록을 조회했습니다. 주문은 실행하지 않았습니다."
        analysis = self._analysis_payload(dict(legacy.get("data") or {}), legacy)
        action = str(analysis.get("action") or "HOLD").upper()
        label = symbol_name or symbol or "해당 종목"
        return f"{label} 현재 판단은 {action}입니다. 분석만 수행했으며 자동 주문은 실행하지 않았습니다."

    def _affordability_message(
        self,
        data: dict[str, Any],
        legacy: dict[str, Any],
        *,
        symbol_name: str | None,
        symbol: str | None,
    ) -> str:
        price = data.get("price") if isinstance(data.get("price"), dict) else {}
        balance = data.get("balance") if isinstance(data.get("balance"), dict) else {}
        value = self._number(price.get("price", price.get("current_price")))
        cash = self._first_number(
            balance,
            "available_cash",
            "orderable_cash",
            "buying_power",
            "cash",
            "available_amount",
        )
        intent = legacy.get("intent") if isinstance(legacy.get("intent"), dict) else {}
        quantity = self._number(intent.get("quantity")) or 1
        label = symbol_name or price.get("name") or symbol or "해당 종목"
        if value is None:
            return f"{label} 현재가를 확인하지 못해 매수 가능 여부를 계산할 수 없습니다. 주문은 실행하지 않았습니다."
        required = value * quantity
        if cash is None:
            return f"{label} {int(quantity)}주 예상 금액은 {self._money(required, 'KRW')}입니다. 예수금을 확인하지 못했습니다."
        possible = cash >= required
        return (
            f"{label} {int(quantity)}주 예상 금액은 {self._money(required, 'KRW')}이고, "
            f"확인된 주문 가능 현금은 {self._money(cash, 'KRW')}라서 "
            f"{'매수 가능한 범위입니다' if possible else '현재 현금으로는 부족합니다'}. "
            "계산만 수행했으며 주문은 실행하지 않았습니다."
        )

    def _indicator_message(self, message: str) -> str:
        lowered = message.lower()
        if "rsi" in lowered or "상대강도" in message:
            return "RSI는 최근 상승·하락의 강도를 0~100으로 나타내는 모멘텀 지표입니다. 일반적으로 30 이하는 과매도, 70 이상은 과매수 신호로 참고하지만 단독 매매 신호로 사용하지 않습니다."
        if "vwap" in lowered:
            return "VWAP은 거래량을 반영한 평균 가격입니다. 현재가가 VWAP 위인지 아래인지로 해당 세션의 매수·매도 우위를 참고할 수 있지만, 단독 판단 기준은 아닙니다."
        if "atr" in lowered:
            return "ATR은 방향이 아니라 최근 가격 변동폭을 측정하는 지표입니다. 값이 클수록 변동성이 큰 상태라 손절·목표 폭을 해석할 때 참고합니다."
        if "ema" in lowered or "이동평균" in message:
            return "EMA는 최근 가격에 더 큰 가중치를 둔 이동평균입니다. 추세 방향을 부드럽게 확인하는 데 쓰며, 다른 지표와 함께 해석해야 합니다."
        return "RSI·VWAP·ATR·EMA 같은 지표의 의미와 해석 방법을 설명해 드릴 수 있습니다. 특정 지표 이름을 함께 알려 주세요."

    def _number(self, value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None

    def _first_number(self, data: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = self._number(data.get(key))
            if value is not None:
                return value
        for nested in data.values():
            if isinstance(nested, dict):
                value = self._first_number(nested, *keys)
                if value is not None:
                    return value
        return None

    def _money(self, value: Any, currency: str = "KRW") -> str:
        number = self._number(value)
        if number is None:
            return "확인 불가"
        if currency.upper() == "USD":
            return f"${number:,.2f}"
        return f"{number:,.0f}원"

    def _compose_answer(
        self,
        *,
        request: AgentChatV2MessageRequest,
        routed: AgentChatIntent,
        intent_name: str,
        legacy: dict[str, Any],
        data: dict[str, Any],
        baseline_message: str,
    ) -> tuple[str, dict[str, Any]]:
        """Compose only public analysis explanations; keep facts deterministic."""
        if intent_name not in {"analyze", "explain"}:
            return baseline_message, {
                "gpt_called": False,
                "gpt_used": False,
                "gpt_provider": None,
                "gpt_model": None,
                "gpt_result": "not_required",
                "fallback_used": False,
            }

        safe_message, message_class = self.privacy_service.redact_user_message(request.message)
        if safe_message is None:
            return baseline_message, {
                "gpt_called": False,
                "gpt_used": False,
                "gpt_provider": None,
                "gpt_model": None,
                "gpt_result": "privacy_blocked_user_message",
                "fallback_used": True,
                "fallback_reason": message_class.value,
                "privacy_class": message_class.value,
            }

        intent_payload = legacy.get("intent") if isinstance(legacy.get("intent"), dict) else {}
        public_context = self.privacy_service.public_context(
            intent_name=intent_name,
            symbol=str(intent_payload.get("symbol") or routed.symbol or "") or None,
            symbol_name=str(intent_payload.get("symbol_name") or routed.symbol_name or "") or None,
            market=str(intent_payload.get("market") or routed.market or "") or None,
            data=data,
        )
        context_class = self.privacy_service.classify(public_context)
        if context_class != AgentChatPrivacyClass.PUBLIC:
            return baseline_message, {
                "gpt_called": False,
                "gpt_used": False,
                "gpt_provider": None,
                "gpt_model": None,
                "gpt_result": "privacy_blocked_context",
                "fallback_used": True,
                "fallback_reason": "public_context_not_public",
                "privacy_class": context_class.value,
            }

        client = getattr(self.intent_router, "client", None)
        model_name = getattr(self.intent_router, "model_name", None)
        if client is None or not model_name:
            return baseline_message, {
                "gpt_called": False,
                "gpt_used": False,
                "gpt_provider": None,
                "gpt_model": model_name,
                "gpt_result": "not_configured",
                "fallback_used": False,
            }

        try:
            prompt_payload = {
                "user_message": safe_message,
                "public_context": public_context,
                "safety": {
                    "analysis_only": True,
                    "never_submit_orders": True,
                    "never_invent_missing_values": True,
                },
            }
            response = client.responses.create(
                model=model_name,
                reasoning={"effort": getattr(self.intent_router, "reasoning_effort", "low")},
                instructions=(
                    "You are the final answer composer for a Korean investment assistant. "
                    "Use only PUBLIC_CONTEXT and the user's public question. "
                    "Answer in concise natural Korean, explain the evidence and uncertainty, "
                    "never invent missing prices or scores, never reveal internal fields, "
                    "and never claim that an order was submitted."
                ),
                input=json.dumps(prompt_payload, ensure_ascii=False, default=str),
            )
            candidate = self._safe_gpt_answer(str(getattr(response, "output_text", "") or ""))
            if self.privacy_service.classify(candidate) != AgentChatPrivacyClass.PUBLIC:
                raise ValueError("gpt_output_privacy_rejected")
            return candidate, {
                "gpt_called": True,
                "gpt_used": True,
                "gpt_provider": "openai",
                "gpt_model": model_name,
                "gpt_result": "success",
                "fallback_used": False,
            }
        except Exception as exc:
            return baseline_message, {
                "gpt_called": True,
                "gpt_used": False,
                "gpt_provider": "openai",
                "gpt_model": model_name,
                "gpt_result": "fallback",
                "fallback_used": True,
                "fallback_reason": self._safe_exception_category(exc),
            }

    def _safe_gpt_answer(self, answer: str) -> str:
        value = answer.strip()
        if value.startswith(chr(96) * 3) and value.endswith(chr(96) * 3):
            value = value[3:-3].strip()
        if not value:
            raise ValueError("gpt_empty_output")
        if any(
            marker in value.lower()
            for marker in ("selected_tools", "tool_results", "internal_status", "parser_status")
        ):
            raise ValueError("gpt_internal_output_rejected")
        return value[:2400]

    def _safe_exception_category(self, error: Exception) -> str:
        text = str(error).lower()
        if "privacy" in text or "secret" in text or "account" in text:
            return "privacy_rejected"
        if "timeout" in text:
            return "timeout"
        if "empty" in text:
            return "empty_output"
        return "provider_error"

    def _analysis_payload(self, data: dict[str, Any], legacy: dict[str, Any]) -> dict[str, Any]:
        raw = data.get("analysis")
        if not isinstance(raw, dict):
            run = legacy.get("run")
            raw = run.get("result") if isinstance(run, dict) and isinstance(run.get("result"), dict) else {}
        raw = dict(raw)
        intent_payload = legacy.get("intent") if isinstance(legacy.get("intent"), dict) else {}
        symbol = raw.get("symbol") or intent_payload.get("symbol")
        action = str(raw.get("action") or raw.get("decision") or "HOLD").upper()
        score_sources = {
            "quant_buy": ("quant_buy", "quant_buy_score"),
            "quant_sell": ("quant_sell", "quant_sell_score"),
            "ai_buy": ("ai_buy", "gpt_buy_score", "ai_buy_score"),
            "ai_sell": ("ai_sell", "gpt_sell_score", "ai_sell_score"),
            "final_buy": ("final_buy", "final_buy_score"),
            "final_sell": ("final_sell", "final_sell_score"),
            "final_score": ("final_score", "final_buy_score"),
            "required_score": ("required_score",),
        }
        scores: dict[str, Any] = {}
        for output_key, source_keys in score_sources.items():
            value = next((raw.get(key) for key in source_keys if raw.get(key) is not None), None)
            if value is not None:
                scores[output_key] = value
        risk_flags = raw.get("risk_flags") if isinstance(raw.get("risk_flags"), list) else []
        return {
            **raw,
            "symbol": symbol,
            "action": action,
            "scores": scores,
            "confidence": raw.get("confidence"),
            "positive_factors": list(raw.get("positive_factors") or raw.get("positives") or [])[:3],
            "risk_flags": [str(item) for item in risk_flags[:5]],
            "gating_notes": list(raw.get("gating_notes") or [])[:5],
        }
    def _risk_payload(self, data: dict[str, Any], legacy: dict[str, Any]) -> dict[str, Any]:
        raw = data.get("risk") if isinstance(data.get("risk"), dict) else {}
        if not raw and isinstance(data.get("readiness"), dict):
            readiness = data["readiness"]
            raw = {
                "approved": bool(readiness.get("ready_for_chat_confirmed_live_order")),
                "block_reasons": readiness.get("blocking_reasons") or [],
            }
        if not raw:
            analysis = self._analysis_payload(data, legacy)
            raw = {
                "approved": str(analysis.get("action")) == "BUY",
                "block_reasons": analysis.get("risk_flags") or analysis.get("gating_notes") or [],
            }
        return {
            "approved": bool(raw.get("approved", False)),
            "block_reasons": list(raw.get("block_reasons") or raw.get("gating_notes") or [])[:5],
        }

    def _portfolio_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        positions = data.get("positions") if isinstance(data.get("positions"), list) else []
        balance = data.get("balance") if isinstance(data.get("balance"), dict) else {}
        return {
            "count": int(data.get("count", len(positions)) or 0),
            "positions": positions[:5],
            "cash": balance.get("cash"),
            "total_asset_value": balance.get("total_asset_value"),
            "currency": balance.get("currency") or "KRW",
        }

    def _order_preview(self, action: Any) -> dict[str, Any] | None:
        if not isinstance(action, dict):
            return None
        return {
            "action_id": action.get("action_id"),
            "broker": action.get("provider"),
            "provider": action.get("provider"),
            "market": action.get("market"),
            "symbol": action.get("symbol"),
            "symbol_name": action.get("symbol_name"),
            "side": action.get("side"),
            "quantity": action.get("quantity"),
            "order_type": action.get("order_type"),
            "estimated_price": action.get("estimated_price"),
            "estimated_notional": action.get("estimated_notional"),
            "currency": action.get("currency"),
            "action_type": action.get("action_type"),
            "conversation_key": action.get("conversation_key"),
            "confirmation_phrase": action.get("confirmation_phrase"),
            "confirmation_token": action.get("confirmation_token"),
            "safety_controls": action.get("safety_controls") or {},
            "risk_status": "pending_backend_revalidation",
            "validation_status": "confirmation_required",
            "expires_at": action.get("expires_at"),
            "status": action.get("status"),
        }
