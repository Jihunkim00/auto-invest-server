from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.brokers.alpaca_client import AlpacaClient
from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.schemas.agent_chat import AgentChatConversationCreateRequest
from app.schemas.agent_chat_orchestrator import (
    AgentChatAnswer,
    AgentChatIntent,
    AgentChatIntentCategory,
    AgentChatSafetyFlags,
    AgentChatSendRequest,
    AgentChatSendResponse,
)
from app.schemas.agent_command import CommandDomain, CommandType, OrderSide, SCHEMA_VERSION
from app.schemas.agent_execution import AgentPlanRunRequest
from app.services.agent_chat_answer_service import AgentChatAnswerService
from app.services.agent_chat_context_service import AgentChatContextService
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_live_order_service import AgentChatLiveOrderService
from app.services.agent_chat_result_summarizer import AgentChatResultSummarizer
from app.services.agent_chat_service import AgentChatConversationNotFound, AgentChatService
from app.services.agent_chat_strategy_action_service import AgentChatStrategyActionService
from app.services.agent_chat_tool_executor import AgentChatToolExecutor
from app.services.agent_chat_tool_registry import AgentChatToolRegistry
from app.services.agent_execution_gateway import AgentExecutionGateway
from app.services.agent_plan_service import AgentPlanService


class AgentChatOrchestratorService:
    def __init__(
        self,
        *,
        chat_service: AgentChatService | None = None,
        intent_router: AgentChatIntentRouterService | None = None,
        answer_service: AgentChatAnswerService | None = None,
        context_service: AgentChatContextService | None = None,
        result_summarizer: AgentChatResultSummarizer | None = None,
        tool_registry: AgentChatToolRegistry | None = None,
        tool_executor: AgentChatToolExecutor | None = None,
        plan_service: AgentPlanService | None = None,
        execution_gateway: AgentExecutionGateway | None = None,
        live_order_service: AgentChatLiveOrderService | None = None,
        strategy_action_service: AgentChatStrategyActionService | None = None,
        kis_client_factory: Callable[[Session], KisClient] | None = None,
        alpaca_client_factory: Callable[[], AlpacaClient] | None = None,
    ) -> None:
        self.chat_service = chat_service or AgentChatService()
        self.intent_router = intent_router or AgentChatIntentRouterService()
        self.answer_service = answer_service or AgentChatAnswerService()
        self.context_service = context_service or AgentChatContextService()
        self.result_summarizer = result_summarizer or AgentChatResultSummarizer()
        self.tool_registry = tool_registry or AgentChatToolRegistry()
        self.plan_service = plan_service or AgentPlanService()
        self.execution_gateway = execution_gateway or AgentExecutionGateway()
        self.kis_client_factory = kis_client_factory or self._default_kis_client
        self.alpaca_client_factory = alpaca_client_factory or AlpacaClient
        self.live_order_service = live_order_service or AgentChatLiveOrderService(
            kis_client_factory=self.kis_client_factory,
        )
        self.strategy_action_service = strategy_action_service or AgentChatStrategyActionService()
        self.tool_executor = tool_executor or AgentChatToolExecutor(
            registry=self.tool_registry,
            kis_client_factory=self.kis_client_factory,
            alpaca_client_factory=self.alpaca_client_factory,
        )

    def send(self, db: Session, *, request: AgentChatSendRequest) -> dict[str, Any]:
        context = request.context_dict()
        context["language"] = request.language
        context["locale"] = request.locale
        context["language_instruction"] = self._language_instruction(request.language)
        conversation_key = self._resolve_conversation_key(db, request=request)
        previous_context = self.context_service.load_context(
            db,
            conversation_key=conversation_key,
        )
        if previous_context:
            context = {**context, **previous_context, "context_snapshot": previous_context}
        user_message = self.chat_service.append_message(
            db,
            conversation_key=conversation_key,
            request={
                "role": "user",
                "text": request.message,
                "message_type": "plain_text",
                "metadata": {
                    "source": str(context.get("source") or "api"),
                    "conversation_title": request.message,
                    "language": request.language,
                    "locale": request.locale,
                    "language_instruction": context["language_instruction"],
                },
            },
        )["message"]

        intent = self.intent_router.route(message=request.message, context=context)
        action = self._handle_intent(
            db,
            intent=intent,
            conversation_key=conversation_key,
            user_message_id=user_message.get("id"),
        )
        base_answer = self.answer_service.compose(
            intent=intent,
            data=action["data"],
            plan=action.get("plan"),
            run=action.get("run"),
            available_actions=action["available_actions"],
        )
        summary = self.result_summarizer.summarize(
            intent=intent,
            tool_results=action["tool_results"],
            fallback_answer=base_answer,
        )
        answer = summary["answer"]
        action["result_cards"] = [
            *(action.get("result_cards") or []),
            *summary["result_cards"],
        ]
        action["follow_up_suggestions"] = summary["follow_up_suggestions"]
        action["context_snapshot"] = self.context_service.build_snapshot(
            intent=intent,
            tool_results=action["tool_results"],
            previous=previous_context,
        )
        safety = action["safety"]
        diagnostics = self._diagnostics(
            intent=intent,
            answer=answer,
            action=action,
        )
        diagnostics["language"] = request.language
        diagnostics["locale"] = request.locale
        diagnostics["language_instruction"] = context["language_instruction"]
        assistant_message = self.chat_service.append_message(
            db,
            conversation_key=conversation_key,
            request={
                "role": "assistant",
                "text": answer.text,
                "message_type": answer.answer_type,
                "status": self._message_status(answer),
                "command_log_id": action.get("command_log_id"),
                "plan_id": (action.get("plan") or {}).get("id"),
                "plan_run_id": (action.get("run") or {}).get("plan_run_id"),
                "model_name": intent.model_name,
                "parser_status": intent.parser_status,
                "safety": safety.model_dump(mode="json"),
                "metadata": self._assistant_metadata(
                    intent=intent,
                    answer=answer,
                    action=action,
                    safety=safety,
                    diagnostics=diagnostics,
                ),
            },
        )["message"]
        live_order_action = action.get("live_order_action")
        if isinstance(live_order_action, dict) and live_order_action.get("action_id"):
            self.live_order_service.update_assistant_message_id(
                db,
                action_id=int(live_order_action["action_id"]),
                assistant_message_id=assistant_message.get("id"),
            )
        strategy_action = action.get("strategy_action")
        if isinstance(strategy_action, dict) and strategy_action.get("action_id"):
            self.strategy_action_service.update_assistant_message_id(
                db,
                action_id=int(strategy_action["action_id"]),
                assistant_message_id=assistant_message.get("id"),
            )

        response = AgentChatSendResponse(
            conversation_key=conversation_key,
            language=request.language,
            locale=request.locale,
            user_message_id=user_message.get("id"),
            assistant_message_id=assistant_message.get("id"),
            intent=intent,
            answer=answer,
            data=action["data"],
            command=action.get("command"),
            plan=action.get("plan"),
            run=action.get("run"),
            live_order_action=live_order_action,
            strategy_action=strategy_action,
            available_actions=action["available_actions"],
            safety=safety,
            context_snapshot=action["context_snapshot"],
            selected_tools=action["selected_tools"],
            tool_results=action["tool_results"],
            result_cards=action["result_cards"],
            follow_up_suggestions=action["follow_up_suggestions"],
            diagnostics=diagnostics,
            answer_type=answer.answer_type,
            fallback_used=intent.fallback_used,
        )
        return response.model_dump(mode="json")

    def _resolve_conversation_key(
        self,
        db: Session,
        *,
        request: AgentChatSendRequest,
    ) -> str:
        key = str(request.conversation_key or "").strip()
        if key:
            self.chat_service.get_conversation(db, conversation_key=key)
            return key
        if not request.auto_create_conversation:
            raise AgentChatConversationNotFound("missing_conversation_key")
        created = self.chat_service.create_conversation(
            db,
            request=AgentChatConversationCreateRequest(
                title=request.message[:80],
                source="flutter_dashboard",
                metadata={"source": "flutter_dashboard"},
            ),
        )
        return created["conversation"]["conversation_key"]

    def _handle_intent(
        self,
        db: Session,
        *,
        intent: AgentChatIntent,
        conversation_key: str,
        user_message_id: int | None = None,
    ) -> dict[str, Any]:
        safety = self._base_safety(intent)
        selected_tools = intent.selected_tools
        category = intent.category
        if category == AgentChatIntentCategory.STRATEGY_PROFILE_CHANGE_REQUEST:
            return self._strategy_profile_change_action(
                db,
                intent=intent,
                conversation_key=conversation_key,
                user_message_id=user_message_id,
                selected_tools=selected_tools,
            )
        tool_results = self.tool_executor.execute_many(
            db,
            calls=selected_tools,
            intent=intent,
        ) if selected_tools else []
        self._merge_tool_safety(safety, tool_results)
        if category in {
            AgentChatIntentCategory.READ_ONLY_PRICE_QUERY,
            AgentChatIntentCategory.READ_ONLY_POSITIONS_QUERY,
            AgentChatIntentCategory.READ_ONLY_BALANCE_QUERY,
            AgentChatIntentCategory.READ_ONLY_ORDERS_QUERY,
            AgentChatIntentCategory.READ_ONLY_RUNS_QUERY,
            AgentChatIntentCategory.READ_ONLY_SIGNALS_QUERY,
            AgentChatIntentCategory.READ_ONLY_SETTINGS_QUERY,
            AgentChatIntentCategory.READ_ONLY_DAILY_OPS_SUMMARY_QUERY,
            AgentChatIntentCategory.READ_ONLY_OPERATOR_ALERTS_QUERY,
            AgentChatIntentCategory.READ_ONLY_PRODUCTION_READINESS_QUERY,
            AgentChatIntentCategory.STRATEGY_PROFILE_QUERY,
            AgentChatIntentCategory.STRATEGY_PROFILE_COMPARE,
            AgentChatIntentCategory.STRATEGY_PROFILE_RECOMMENDATION,
            AgentChatIntentCategory.STRATEGY_MONTHLY_PROGRESS_QUERY,
            AgentChatIntentCategory.STRATEGY_RISK_BUDGET_QUERY,
            AgentChatIntentCategory.STRATEGY_DAILY_PERFORMANCE_QUERY,
            AgentChatIntentCategory.STRATEGY_MONTHLY_PERFORMANCE_QUERY,
            AgentChatIntentCategory.STRATEGY_TARGET_PROGRESS_QUERY,
            AgentChatIntentCategory.STRATEGY_TRADE_PERFORMANCE_QUERY,
            AgentChatIntentCategory.STRATEGY_LOSS_BUDGET_QUERY,
            AgentChatIntentCategory.STRATEGY_RISK_STATE_QUERY,
            AgentChatIntentCategory.STRATEGY_ENTRY_RISK_QUERY,
            AgentChatIntentCategory.STRATEGY_ORDER_SIZING_QUERY,
            AgentChatIntentCategory.STRATEGY_LOSS_LIMIT_QUERY,
            AgentChatIntentCategory.STRATEGY_TARGET_GATE_QUERY,
            AgentChatIntentCategory.STRATEGY_DRY_RUN_AUTO_BUY_REQUEST,
            AgentChatIntentCategory.STRATEGY_DRY_RUN_AUTO_BUY_RECENT_QUERY,
            AgentChatIntentCategory.STRATEGY_DRY_RUN_AUTO_BUY_SUMMARY_QUERY,
            AgentChatIntentCategory.STRATEGY_DRY_RUN_AUTO_BUY_REASON_QUERY,
            AgentChatIntentCategory.STRATEGY_AUTO_BUY_OPERATIONS_STATUS_QUERY,
            AgentChatIntentCategory.STRATEGY_AUTO_BUY_NEXT_ACTION_QUERY,
            AgentChatIntentCategory.STRATEGY_AUTO_BUY_BLOCK_REASON_QUERY,
            AgentChatIntentCategory.STRATEGY_AUTO_BUY_SCHEDULER_STATUS_QUERY,
            AgentChatIntentCategory.STRATEGY_AUTO_BUY_PROMOTION_QUEUE_QUERY,
            AgentChatIntentCategory.STRATEGY_AUTO_BUY_PROMOTION_REASON_QUERY,
            AgentChatIntentCategory.STRATEGY_LIVE_AUTO_BUY_READINESS_QUERY,
            AgentChatIntentCategory.STRATEGY_LIVE_AUTO_BUY_RECENT_QUERY,
            AgentChatIntentCategory.STRATEGY_LIVE_AUTO_BUY_BLOCK_REASON_QUERY,
            AgentChatIntentCategory.STRATEGY_LIVE_AUTO_EXIT_READINESS_QUERY,
            AgentChatIntentCategory.STRATEGY_LIVE_AUTO_EXIT_RECENT_QUERY,
            AgentChatIntentCategory.STRATEGY_LIVE_AUTO_EXIT_BLOCK_REASON_QUERY,
            AgentChatIntentCategory.STRATEGY_EXIT_CANDIDATE_QUERY,
        }:
            return self._action(
                data=self._data_from_tool_results(tool_results),
                safety=safety,
                selected_tools=selected_tools,
                tool_results=tool_results,
            )
        if category in {
            AgentChatIntentCategory.ANALYSIS_REQUEST,
            AgentChatIntentCategory.EXIT_REVIEW_REQUEST,
        }:
            return self._with_tool_audit(
                self._analysis_action(db, intent=intent, conversation_key=conversation_key),
                selected_tools=selected_tools,
                tool_results=tool_results,
            )
        if category == AgentChatIntentCategory.WATCHLIST_PREVIEW_REQUEST:
            return self._action(
                data=self._data_from_tool_results(tool_results),
                safety=safety,
                selected_tools=selected_tools,
                tool_results=tool_results,
            )
        if category == AgentChatIntentCategory.MANUAL_TICKET_REQUEST:
            return self._with_tool_audit(
                self._manual_ticket_action(db, intent=intent, conversation_key=conversation_key),
                selected_tools=selected_tools,
                tool_results=tool_results,
            )
        if category == AgentChatIntentCategory.LIVE_ORDER_REQUEST:
            return self._with_tool_audit(
                self._live_order_action(
                    db,
                    intent=intent,
                    conversation_key=conversation_key,
                    user_message_id=user_message_id,
                ),
                selected_tools=selected_tools,
                tool_results=tool_results,
            )
        if category in {
            AgentChatIntentCategory.DANGEROUS_SETTING_REQUEST,
            AgentChatIntentCategory.SCHEDULER_REQUEST,
            AgentChatIntentCategory.UNSUPPORTED,
            AgentChatIntentCategory.NEEDS_CLARIFICATION,
            AgentChatIntentCategory.GENERAL_CHAT,
            AgentChatIntentCategory.CAPABILITY_QUESTION,
        }:
            return self._action(
                data=self._data_from_tool_results(tool_results),
                safety=safety,
                selected_tools=selected_tools,
                tool_results=tool_results,
            )
        return self._action(
            data=self._data_from_tool_results(tool_results),
            safety=safety,
            selected_tools=selected_tools,
            tool_results=tool_results,
        )

    def _lookup_price(self, db: Session, intent: AgentChatIntent) -> dict[str, Any]:
        symbol = str(intent.symbol or "").strip().upper()
        if not symbol:
            return {"error": "종목을 확인할 수 없습니다."}
        market = str(intent.market or "").upper()
        provider = str(intent.provider or "").lower()
        if market == "KR" or provider == "kis":
            try:
                payload = self.kis_client_factory(db).get_domestic_stock_price(symbol)
                return {
                    "price": {
                        "symbol": payload.get("symbol") or symbol,
                        "name": payload.get("name") or intent.symbol_name or symbol,
                        "price": payload.get("current_price"),
                        "current_price": payload.get("current_price"),
                        "currency": "KRW",
                        "provider": "kis",
                        "timestamp": payload.get("timestamp"),
                    }
                }
            except Exception as exc:
                return {"price": {"symbol": symbol, "name": intent.symbol_name}, "error": self._safe_error(exc)}
        if market == "US" or provider == "alpaca":
            try:
                payload = self.alpaca_client_factory().get_latest_price(symbol)
                if not payload:
                    return {"price": {"symbol": symbol}, "error": "현재 US 단건 가격 조회 응답이 없습니다."}
                return {
                    "price": {
                        "symbol": payload.get("symbol") or symbol,
                        "name": intent.symbol_name or symbol,
                        "price": payload.get("price"),
                        "current_price": payload.get("price"),
                        "currency": "USD",
                        "provider": "alpaca",
                        "timestamp": payload.get("timestamp"),
                    }
                }
            except Exception as exc:
                return {"price": {"symbol": symbol, "name": intent.symbol_name}, "error": self._safe_error(exc)}
        return {"price": {"symbol": symbol, "name": intent.symbol_name}, "error": "지원하지 않는 가격 조회 provider입니다."}

    def _lookup_positions(self, db: Session, intent: AgentChatIntent) -> dict[str, Any]:
        market = str(intent.market or "").upper()
        provider = str(intent.provider or "").lower()
        if market == "KR" or provider == "kis":
            try:
                positions = self.kis_client_factory(db).list_positions()
                return {"provider": "kis", "market": "KR", "count": len(positions), "positions": positions}
            except Exception as exc:
                return {"provider": "kis", "market": "KR", "count": 0, "positions": [], "error": self._safe_error(exc)}
        try:
            rows = self.alpaca_client_factory().list_positions()
            positions = [
                {
                    "symbol": str(getattr(row, "symbol", "") or "").upper(),
                    "qty": getattr(row, "qty", None),
                    "market_value": getattr(row, "market_value", None),
                    "unrealized_pl": getattr(row, "unrealized_pl", None),
                    "current_price": getattr(row, "current_price", None),
                }
                for row in rows
            ]
            return {"provider": "alpaca", "market": "US", "count": len(positions), "positions": positions}
        except Exception as exc:
            return {"provider": "alpaca", "market": "US", "count": 0, "positions": [], "error": self._safe_error(exc)}

    def _lookup_balance(self, db: Session, intent: AgentChatIntent) -> dict[str, Any]:
        market = str(intent.market or "").upper()
        provider = str(intent.provider or "").lower()
        if market == "KR" or provider == "kis":
            try:
                return {"balance": self.kis_client_factory(db).get_account_balance()}
            except Exception as exc:
                return {"balance": {}, "error": self._safe_error(exc)}
        try:
            account = self.alpaca_client_factory().get_account()
            return {
                "balance": {
                    "provider": "alpaca",
                    "market": "US",
                    "currency": "USD",
                    "cash": getattr(account, "cash", None),
                    "total_asset_value": getattr(account, "portfolio_value", None),
                }
            }
        except Exception as exc:
            return {"balance": {}, "error": self._safe_error(exc)}

    def _recent_orders(self, db: Session, *, limit: int = 10) -> dict[str, Any]:
        rows = db.query(OrderLog).order_by(OrderLog.created_at.desc(), OrderLog.id.desc()).limit(limit).all()
        return {"count": len(rows), "orders": [self._order_summary(row) for row in rows]}

    def _recent_runs(self, db: Session, *, limit: int = 10) -> dict[str, Any]:
        rows = db.query(TradeRunLog).order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc()).limit(limit).all()
        return {"count": len(rows), "runs": [self._run_summary(row) for row in rows]}

    def _recent_signals(self, db: Session, *, limit: int = 10) -> dict[str, Any]:
        rows = db.query(SignalLog).order_by(SignalLog.created_at.desc(), SignalLog.id.desc()).limit(limit).all()
        return {"count": len(rows), "signals": [self._signal_summary(row) for row in rows]}

    def _strategy_profile_change_action(
        self,
        db: Session,
        *,
        intent: AgentChatIntent,
        conversation_key: str,
        user_message_id: int | None,
        selected_tools: list[Any],
    ) -> dict[str, Any]:
        safety = self._base_safety(intent)
        safety.read_only = False
        prepared = self.strategy_action_service.prepare(
            db,
            intent=intent,
            conversation_key=conversation_key,
            user_message_id=user_message_id,
        )
        prepared_safety = prepared.get("safety")
        if isinstance(prepared_safety, dict):
            for key, value in prepared_safety.items():
                if hasattr(safety, key):
                    setattr(safety, key, value)
        if prepared.get("created") is True:
            return self._action(
                data=dict(prepared.get("data") or {}),
                strategy_action=dict(prepared.get("strategy_action") or {}),
                available_actions=list(prepared.get("available_actions") or []),
                safety=safety,
                selected_tools=selected_tools,
                tool_results=[],
                result_cards=list(prepared.get("result_cards") or []),
            )
        return self._action(
            data=dict(prepared.get("data") or {"error": "strategy_profile_not_resolved"}),
            safety=safety,
            selected_tools=selected_tools,
            tool_results=[],
        )

    def _analysis_action(
        self,
        db: Session,
        *,
        intent: AgentChatIntent,
        conversation_key: str,
    ) -> dict[str, Any]:
        safety = self._base_safety(intent)
        safety.read_only = False
        if not intent.symbol:
            return self._action(data={"error": "분석할 종목을 확인할 수 없습니다."}, safety=safety)
        command = self._analysis_command(intent)
        try:
            created = self.plan_service.create_from_command(
                db,
                command=command,
                conversation_id=conversation_key,
                plan_title=f"Safe analysis for {intent.symbol}",
            )
            plan = created["plan"]
            run = self.execution_gateway.run_plan(
                db,
                plan_id=plan["id"],
                request=AgentPlanRunRequest(
                    dry_run=True,
                    operator_note="Agent chat safe analysis request.",
                    trigger_source="agent_chat_orchestrator",
                ),
            )
            return self._action(
                data={"analysis": run.get("result", {})},
                command=command,
                plan=plan,
                run=run,
                safety=safety,
            )
        except Exception as exc:
            return self._action(data={"error": self._safe_error(exc)}, command=command, safety=safety)

    def _manual_ticket_action(
        self,
        db: Session,
        *,
        intent: AgentChatIntent,
        conversation_key: str,
    ) -> dict[str, Any]:
        safety = self._base_safety(intent)
        safety.read_only = False
        if not intent.symbol:
            return self._action(data={"error": "티켓을 준비할 종목을 확인할 수 없습니다."}, safety=safety)
        command = self._manual_ticket_command(intent)
        try:
            created = self.plan_service.create_from_command(
                db,
                command=command,
                conversation_id=conversation_key,
                plan_title=f"Prepare manual ticket for {intent.symbol}",
            )
            return self._action(
                data={"prefill_ready": created["plan"].get("status") == "ready_for_review"},
                command=command,
                plan=created["plan"],
                available_actions=["prepare_manual_ticket", "open_trading_ticket"],
                safety=safety,
            )
        except Exception as exc:
            return self._action(data={"error": self._safe_error(exc)}, command=command, safety=safety)

    def _live_order_action(
        self,
        db: Session,
        *,
        intent: AgentChatIntent,
        conversation_key: str,
        user_message_id: int | None,
    ) -> dict[str, Any]:
        safety = self._base_safety(intent)
        safety.read_only = False
        if not intent.symbol:
            return self._action(data={"direct_order_blocked": True}, safety=safety)
        prepared = self.live_order_service.prepare(
            db,
            intent=intent,
            conversation_key=conversation_key,
            user_message_id=user_message_id,
        )
        prepared_safety = prepared.get("safety")
        if isinstance(prepared_safety, dict):
            for key, value in prepared_safety.items():
                if hasattr(safety, key):
                    setattr(safety, key, value)
        if prepared.get("created") is True:
            action = dict(prepared.get("action") or {})
            return self._action(
                data=dict(prepared.get("data") or {}),
                live_order_action=action,
                available_actions=["confirm_live_order", "cancel_live_order"],
                safety=safety,
                result_cards=list(prepared.get("result_cards") or []),
            )
        command = self._manual_ticket_command(intent)
        try:
            created = self.plan_service.create_from_command(
                db,
                command=command,
                conversation_id=conversation_key,
                plan_title=f"Blocked live request; manual ticket only for {intent.symbol}",
            )
            return self._action(
                data={"direct_order_blocked": True},
                command=command,
                plan=created["plan"],
                available_actions=["prepare_manual_ticket", "open_trading_ticket"],
                safety=safety,
            )
        except Exception as exc:
            return self._action(
                data={"direct_order_blocked": True, "error": self._safe_error(exc)},
                command=command,
                safety=safety,
            )

    def _analysis_command(self, intent: AgentChatIntent) -> dict[str, Any]:
        market = intent.market or ("KR" if str(intent.symbol or "").isdigit() else "US")
        return {
            "schema_version": SCHEMA_VERSION,
            "command_type": CommandType.RUN_SINGLE_SYMBOL_ANALYSIS.value,
            "domain": CommandDomain.ANALYSIS.value,
            "intent": "single_symbol_analysis",
            "market": market,
            "provider": intent.provider or ("kis" if market == "KR" else "alpaca"),
            "symbol": intent.symbol,
            "side": OrderSide.NONE.value,
            "user_visible_summary": f"{intent.symbol} 분석 plan입니다. 주문은 실행하지 않습니다.",
            "parser_confidence": intent.confidence,
        }

    def _manual_ticket_command(self, intent: AgentChatIntent) -> dict[str, Any]:
        side = intent.side if intent.side in {"buy", "sell"} else "buy"
        market = intent.market or ("KR" if str(intent.symbol or "").isdigit() else "US")
        provider = intent.provider or ("kis" if market == "KR" else "alpaca")
        currency = intent.currency or ("KRW" if market == "KR" else "USD")
        command_type = (
            CommandType.PREPARE_MANUAL_SELL_TICKET.value
            if side == "sell"
            else CommandType.PREPARE_MANUAL_BUY_TICKET.value
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "command_type": command_type,
            "domain": CommandDomain.ORDER.value,
            "intent": f"prepare_manual_{side}_ticket",
            "market": market,
            "provider": provider,
            "symbol": intent.symbol,
            "side": side,
            "quantity": intent.quantity,
            "budget": {
                "amount": intent.notional,
                "currency": currency,
                "mode": "max_notional",
            }
            if intent.notional is not None
            else None,
            "user_visible_summary": (
                f"{intent.symbol} 수동 {side} 티켓을 준비합니다. "
                "채팅에서는 주문, validation, confirm_live를 실행하지 않습니다."
            ),
            "parser_confidence": intent.confidence,
        }

    def _action(
        self,
        *,
        data: dict[str, Any],
        safety: AgentChatSafetyFlags,
        command: dict[str, Any] | None = None,
        plan: dict[str, Any] | None = None,
        run: dict[str, Any] | None = None,
        live_order_action: dict[str, Any] | None = None,
        strategy_action: dict[str, Any] | None = None,
        available_actions: list[str] | None = None,
        command_log_id: int | None = None,
        selected_tools: list[Any] | None = None,
        tool_results: list[Any] | None = None,
        result_cards: list[Any] | None = None,
        follow_up_suggestions: list[str] | None = None,
        context_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "data": data,
            "command": command,
            "plan": plan,
            "run": run,
            "live_order_action": live_order_action,
            "strategy_action": strategy_action,
            "available_actions": available_actions or [],
            "safety": safety,
            "command_log_id": command_log_id,
            "selected_tools": selected_tools or [],
            "tool_results": tool_results or [],
            "result_cards": result_cards or [],
            "follow_up_suggestions": follow_up_suggestions or [],
            "context_snapshot": context_snapshot or {},
        }

    def _with_tool_audit(
        self,
        action: dict[str, Any],
        *,
        selected_tools: list[Any],
        tool_results: list[Any],
    ) -> dict[str, Any]:
        action["selected_tools"] = selected_tools
        action["tool_results"] = tool_results
        action.setdefault("result_cards", [])
        action.setdefault("follow_up_suggestions", [])
        action.setdefault("context_snapshot", {})
        self._merge_tool_safety(action["safety"], tool_results)
        return action

    def _data_from_tool_results(self, tool_results: list[Any]) -> dict[str, Any]:
        for result in tool_results:
            if getattr(result, "status", None) == "success":
                data = getattr(result, "data", None)
                return dict(data) if isinstance(data, dict) else {}
        for result in tool_results:
            data = getattr(result, "data", None)
            if isinstance(data, dict) and data:
                return dict(data)
        return {}

    def _merge_tool_safety(
        self,
        safety: AgentChatSafetyFlags,
        tool_results: list[Any],
    ) -> None:
        for result in tool_results:
            tool_safety = getattr(result, "safety", None)
            if tool_safety is None:
                continue
            safety.read_only = safety.read_only and bool(tool_safety.read_only)
            safety.mutation = safety.mutation or bool(tool_safety.mutation)
            safety.real_order_submitted = safety.real_order_submitted or bool(tool_safety.real_order_submitted)
            safety.broker_submit_called = safety.broker_submit_called or bool(tool_safety.broker_submit_called)
            safety.manual_submit_called = safety.manual_submit_called or bool(tool_safety.manual_submit_called)
            safety.validation_called = safety.validation_called or bool(tool_safety.validation_called)
            safety.setting_changed = safety.setting_changed or bool(tool_safety.setting_changed)
            safety.scheduler_changed = safety.scheduler_changed or bool(tool_safety.scheduler_changed)
            safety.confirm_live_auto_checked = safety.confirm_live_auto_checked or bool(tool_safety.confirm_live_auto_checked)

    def _base_safety(self, intent: AgentChatIntent) -> AgentChatSafetyFlags:
        read_only_categories = {
            AgentChatIntentCategory.GENERAL_CHAT,
            AgentChatIntentCategory.CAPABILITY_QUESTION,
            AgentChatIntentCategory.READ_ONLY_PRICE_QUERY,
            AgentChatIntentCategory.READ_ONLY_POSITIONS_QUERY,
            AgentChatIntentCategory.READ_ONLY_BALANCE_QUERY,
            AgentChatIntentCategory.READ_ONLY_ORDERS_QUERY,
            AgentChatIntentCategory.READ_ONLY_RUNS_QUERY,
            AgentChatIntentCategory.READ_ONLY_SIGNALS_QUERY,
            AgentChatIntentCategory.READ_ONLY_SETTINGS_QUERY,
            AgentChatIntentCategory.READ_ONLY_DAILY_OPS_SUMMARY_QUERY,
            AgentChatIntentCategory.READ_ONLY_OPERATOR_ALERTS_QUERY,
            AgentChatIntentCategory.READ_ONLY_PRODUCTION_READINESS_QUERY,
            AgentChatIntentCategory.STRATEGY_PROFILE_QUERY,
            AgentChatIntentCategory.STRATEGY_PROFILE_COMPARE,
            AgentChatIntentCategory.STRATEGY_PROFILE_RECOMMENDATION,
            AgentChatIntentCategory.STRATEGY_MONTHLY_PROGRESS_QUERY,
            AgentChatIntentCategory.STRATEGY_RISK_BUDGET_QUERY,
            AgentChatIntentCategory.STRATEGY_DAILY_PERFORMANCE_QUERY,
            AgentChatIntentCategory.STRATEGY_MONTHLY_PERFORMANCE_QUERY,
            AgentChatIntentCategory.STRATEGY_TARGET_PROGRESS_QUERY,
            AgentChatIntentCategory.STRATEGY_TRADE_PERFORMANCE_QUERY,
            AgentChatIntentCategory.STRATEGY_LOSS_BUDGET_QUERY,
            AgentChatIntentCategory.STRATEGY_AUTO_BUY_OPERATIONS_STATUS_QUERY,
            AgentChatIntentCategory.STRATEGY_AUTO_BUY_NEXT_ACTION_QUERY,
            AgentChatIntentCategory.STRATEGY_AUTO_BUY_BLOCK_REASON_QUERY,
            AgentChatIntentCategory.STRATEGY_AUTO_BUY_SCHEDULER_STATUS_QUERY,
            AgentChatIntentCategory.STRATEGY_AUTO_BUY_PROMOTION_QUEUE_QUERY,
            AgentChatIntentCategory.STRATEGY_AUTO_BUY_PROMOTION_REASON_QUERY,
            AgentChatIntentCategory.STRATEGY_LIVE_AUTO_EXIT_READINESS_QUERY,
            AgentChatIntentCategory.STRATEGY_LIVE_AUTO_EXIT_RECENT_QUERY,
            AgentChatIntentCategory.STRATEGY_LIVE_AUTO_EXIT_BLOCK_REASON_QUERY,
            AgentChatIntentCategory.STRATEGY_EXIT_CANDIDATE_QUERY,
            AgentChatIntentCategory.UNSUPPORTED,
            AgentChatIntentCategory.NEEDS_CLARIFICATION,
        }
        return AgentChatSafetyFlags(read_only=intent.category in read_only_categories)

    def _assistant_metadata(
        self,
        *,
        intent: AgentChatIntent,
        answer: AgentChatAnswer,
        action: dict[str, Any],
        safety: AgentChatSafetyFlags,
        diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        plan = action.get("plan") or {}
        run = action.get("run") or {}
        return {
            "intent_category": intent.category.value,
            "answer_type": answer.answer_type,
            "market": intent.market,
            "provider": intent.provider,
            "symbol": intent.symbol,
            "side": intent.side,
            "parser_status": intent.parser_status,
            "model_name": intent.model_name,
            "fallback_used": intent.fallback_used,
            "plan_id": plan.get("id"),
            "plan_run_id": run.get("plan_run_id"),
            "live_order_action": action.get("live_order_action"),
            "strategy_action": action.get("strategy_action"),
            "available_actions": action.get("available_actions") or [],
            "safety": safety.model_dump(mode="json"),
            "context_snapshot": action.get("context_snapshot") or {},
            "selected_tools": [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in action.get("selected_tools") or []
            ],
            "tool_results": [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in action.get("tool_results") or []
            ],
            "result_cards": [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in action.get("result_cards") or []
            ],
            "follow_up_suggestions": action.get("follow_up_suggestions") or [],
            "diagnostics": diagnostics,
        }

    def _diagnostics(
        self,
        *,
        intent: AgentChatIntent,
        answer: AgentChatAnswer,
        action: dict[str, Any],
    ) -> dict[str, Any]:
        answer_text = answer.text or ""
        contains_mojibake = self._contains_mojibake_marker(answer_text)
        router = "gpt" if intent.parser_status == "gpt" else "fallback"
        return {
            "encoding_safe": not contains_mojibake,
            "answer_contains_mojibake_marker": contains_mojibake,
            "model_name": intent.model_name,
            "router": router,
            "fallback_used": intent.fallback_used,
            "tool_count": len(action.get("tool_results") or []),
            "result_card_count": len(action.get("result_cards") or []),
        }

    def _language_instruction(self, language: str) -> str:
        if language == "en":
            return "Respond in English. Do not translate tickers, IDs, enum values, indicators, or broker API field names."
        return "Respond in Korean. Do not translate tickers, IDs, enum values, indicators, or broker API field names."

    def _contains_mojibake_marker(self, text: str) -> bool:
        markers = tuple(chr(code) for code in (0x00EC, 0x00EB, 0x00EA, 0xFFFD, 0xCC59, 0xCC58, 0xCC57))
        return any(marker in text for marker in markers)

    def _message_status(self, answer: AgentChatAnswer) -> str:
        if answer.answer_type == "error":
            return "failed"
        if answer.answer_type in {"blocked", "auth_required", "unsupported"}:
            return "blocked"
        return "completed"

    def _order_summary(self, row: OrderLog) -> dict[str, Any]:
        return {
            "id": row.id,
            "broker": row.broker,
            "market": row.market,
            "symbol": row.symbol,
            "side": row.side,
            "order_type": row.order_type,
            "qty": row.qty,
            "notional": row.notional,
            "internal_status": row.internal_status,
            "broker_status": row.broker_status,
            "created_at": row.created_at,
        }

    def _run_summary(self, row: TradeRunLog) -> dict[str, Any]:
        return {
            "id": row.id,
            "run_key": row.run_key,
            "trigger_source": row.trigger_source,
            "symbol": row.symbol,
            "mode": row.mode,
            "stage": row.stage,
            "result": row.result,
            "reason": row.reason,
            "created_at": row.created_at,
        }

    def _signal_summary(self, row: SignalLog) -> dict[str, Any]:
        return {
            "id": row.id,
            "symbol": row.symbol,
            "action": row.action,
            "buy_score": row.buy_score,
            "sell_score": row.sell_score,
            "confidence": row.confidence,
            "reason": row.reason,
            "signal_status": row.signal_status,
            "trigger_source": row.trigger_source,
            "created_at": row.created_at,
        }

    def _default_kis_client(self, db: Session) -> KisClient:
        settings = get_settings()
        return KisClient(settings, KisAuthManager(settings, db))

    def _safe_error(self, exc: Exception) -> str:
        text = str(exc).strip() or exc.__class__.__name__
        if len(text) > 240:
            return f"{exc.__class__.__name__}: {text[:240]}..."
        return text
