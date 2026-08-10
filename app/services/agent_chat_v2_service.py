from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.schemas.agent_chat_orchestrator import AgentChatIntent, AgentChatSendRequest
from app.schemas.agent_chat_v2 import AgentChatV2MessageRequest
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_live_order_service import AgentChatLiveOrderService
from app.services.agent_chat_orchestrator_service import AgentChatOrchestratorService


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
    ) -> None:
        self.intent_router = intent_router or AgentChatIntentRouterService()
        self.live_order_service = live_order_service or AgentChatLiveOrderService()
        self.orchestrator = orchestrator or AgentChatOrchestratorService()

    def send(self, db: Session, *, request: AgentChatV2MessageRequest) -> dict[str, Any]:
        context = dict(request.context or {})
        routed = self.intent_router.fallback_route(request.message, context)
        intent_name = self._intent_name(request.message, routed.category.value)

        legacy = self.orchestrator.send(
            db,
            request=AgentChatSendRequest.model_validate(request.legacy_payload()),
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
        )

    def _intent_name(self, message: str, category: str) -> str:
        text = str(message or "").strip().lower()
        if any(token in str(message or "") for token in ("안전장치", "킬스위치", "kill_switch", "dry_run", "드라이런", "설정 꺼", "설정 켜")):
            return "safety_block"
        if any(token in str(message or "") for token in ("사고 싶", "매수해", "팔고 싶", "매도해")):
            return "trade_prepare"
        if any(token in str(message or "") for token in ("왜 안 샀", "왜 안샀", "왜 매수 안", "오늘 왜 hold", "최근 판단", "자동매매 결과")):
            return "explain"
        if any(token in str(message or "") for token in ("포트폴리오", "보유 종목", "보유한 종목", "수익 중인 종목", "손실 큰 종목")):
            return "portfolio"
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
        return "explain" if text else "analyze"

    def _response(
        self,
        *,
        request: AgentChatV2MessageRequest,
        routed: AgentChatIntent,
        intent_name: str,
        legacy: dict[str, Any],
        preview: dict[str, Any] | None,
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
        message = self._user_message(
            intent_name=intent_name,
            legacy=legacy,
            symbol=symbol,
            symbol_name=symbol_name,
            order_preview=order_preview,
        )
        analysis = self._analysis_payload(data, legacy)
        risk = self._risk_payload(data, legacy)
        return {
            "intent": intent_name,
            "status": status,
            "message": message,
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
            "diagnostics": {
                "legacy_category": (legacy.get("intent") or {}).get("category"),
                "parser_status": (legacy.get("intent") or {}).get("parser_status"),
                "preview_created": bool(preview and preview.get("created") is True),
            },
        }

    def _user_message(
        self,
        *,
        intent_name: str,
        legacy: dict[str, Any],
        symbol: str | None,
        symbol_name: str | None,
        order_preview: dict[str, Any] | None,
    ) -> str:
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

    def _analysis_payload(self, data: dict[str, Any], legacy: dict[str, Any]) -> dict[str, Any]:
        raw = data.get("analysis")
        if not isinstance(raw, dict):
            run = legacy.get("run")
            raw = run.get("result") if isinstance(run, dict) and isinstance(run.get("result"), dict) else {}
        scores = {
            key: raw.get(key)
            for key in ("quant_buy", "ai_buy", "final_buy", "final_score", "required_score")
            if raw.get(key) is not None
        }
        risk_flags = raw.get("risk_flags") if isinstance(raw.get("risk_flags"), list) else []
        return {
            "symbol": raw.get("symbol"),
            "action": str(raw.get("action") or raw.get("decision") or "HOLD").upper(),
            "scores": scores,
            "confidence": raw.get("confidence"),
            "positive_factors": list(raw.get("positive_factors") or raw.get("positives") or [])[:3],
            "risk_flags": [str(item) for item in risk_flags[:3]],
            "gating_notes": list(raw.get("gating_notes") or [])[:3],
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
