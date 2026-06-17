from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AgentPlan, AgentPlanRun, MarketAnalysis, OrderLog, RuntimeSetting, SignalLog, TradeRunLog
from app.schemas.agent_command import CommandType
from app.schemas.agent_execution import AgentExecutionSafetyFlags, AgentPlanRunRequest
from app.services.agent_execution_policy_service import AgentExecutionPolicyService, SAFE_SCHEDULE_COMMANDS
from app.services.agent_plan_run_service import AgentPlanRunService
from app.services.agent_plan_service import AgentPlanNotFound
from app.services.runtime_setting_service import RuntimeSettingService


class AgentPlanRunNotFound(Exception):
    pass


class AgentExecutionGateway:
    def __init__(
        self,
        *,
        policy_service: AgentExecutionPolicyService | None = None,
        run_service: AgentPlanRunService | None = None,
    ) -> None:
        self.policy_service = policy_service or AgentExecutionPolicyService()
        self.run_service = run_service or AgentPlanRunService()

    def run_plan(
        self,
        db: Session,
        *,
        plan_id: int,
        request: AgentPlanRunRequest | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan = db.get(AgentPlan, plan_id)
        if plan is None:
            raise AgentPlanNotFound(plan_id)

        request_payload = self._request_payload(request)
        safety = AgentExecutionSafetyFlags()
        if (
            request_payload.get("trigger_source") == "agent_schedule_due_once"
            and str(plan.command_type or "") in SAFE_SCHEDULE_COMMANDS
        ):
            policy = self.policy_service.evaluate_schedule(plan)
        else:
            policy = self.policy_service.evaluate_run(plan)
        if not policy.allowed:
            result = self._blocked_result(plan, policy)
            run = self.run_service.record_run(
                db,
                plan=plan,
                policy=policy,
                request=request_payload,
                response=result,
                status="blocked",
                safety=safety,
            )
            return self._response(
                status="blocked",
                plan=plan,
                run=run,
                result=result,
                safety=safety,
            )

        try:
            result = self._execute_safe_action(db, plan=plan, request=request_payload)
        except Exception as exc:
            policy = self.policy_service._block("agent_safe_execution_error", "error")
            result = {
                "result_type": "error",
                "reason": "agent_safe_execution_error",
                "message": self._safe_error(exc),
            }
            run = self.run_service.record_run(
                db,
                plan=plan,
                policy=policy,
                request=request_payload,
                response=result,
                status="failed",
                safety=safety,
                error_message=self._safe_error(exc),
            )
            return self._response(
                status="failed",
                plan=plan,
                run=run,
                result=result,
                safety=safety,
            )

        run = self.run_service.record_run(
            db,
            plan=plan,
            policy=policy,
            request=request_payload,
            response=result,
            status="completed",
            safety=safety,
        )
        return self._response(
            status="executed_safe_action",
            plan=plan,
            run=run,
            result=result,
            safety=safety,
        )

    def list_runs_for_plan(self, db: Session, *, plan_id: int, limit: int = 50) -> dict[str, Any]:
        if db.get(AgentPlan, plan_id) is None:
            raise AgentPlanNotFound(plan_id)
        return self.run_service.list_runs_for_plan(db, plan_id=plan_id, limit=limit)

    def recent_runs(
        self,
        db: Session,
        *,
        limit: int = 50,
        status: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        return self.run_service.recent_runs(
            db,
            limit=limit,
            status=status,
            conversation_id=conversation_id,
        )

    def get_run(self, db: Session, *, plan_run_id: int) -> dict[str, Any]:
        row = self.run_service.get_run(db, plan_run_id=plan_run_id)
        if row is None:
            raise AgentPlanRunNotFound(plan_run_id)
        return {
            "run": self.run_service.serialize_run(row),
            "safety": AgentExecutionSafetyFlags().model_dump(mode="json"),
        }

    def _execute_safe_action(
        self,
        db: Session,
        *,
        plan: AgentPlan,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        command_type = str(plan.command_type or "")
        command = self._plan_command(plan)
        if command_type in {
            CommandType.SHOW_SETTINGS.value,
            CommandType.SHOW_SYSTEM_STATUS.value,
            CommandType.SHOW_OPERATIONS_STATUS.value,
            CommandType.SHOW_RISK_STATUS.value,
            CommandType.SHOW_BROKER_STATUS.value,
            CommandType.SHOW_SCHEDULER_STATUS.value,
            CommandType.SHOW_LOGS.value,
            CommandType.SHOW_RECENT_RUNS.value,
            CommandType.SHOW_RECENT_ORDERS.value,
            CommandType.SHOW_RECENT_SIGNALS.value,
            CommandType.SHOW_PORTFOLIO.value,
            CommandType.SHOW_POSITIONS.value,
            CommandType.SHOW_POSITION_DETAIL.value,
            CommandType.REFRESH_BALANCE.value,
            CommandType.REFRESH_POSITIONS.value,
            CommandType.REFRESH_OPEN_ORDERS.value,
            CommandType.SHOW_EXIT_REVIEW.value,
            CommandType.SHOW_EXIT_REVIEW_QUEUE.value,
        }:
            return self._read_only_result(db, plan=plan, command=command)
        if command_type in {
            CommandType.CREATE_ANALYSIS_SCHEDULE.value,
            CommandType.RUN_MARKET_ANALYSIS.value,
            CommandType.RUN_SINGLE_SYMBOL_ANALYSIS.value,
        }:
            return self._analysis_result(db, plan=plan, command=command)
        if command_type in {
            CommandType.CREATE_WATCHLIST_PREVIEW_SCHEDULE.value,
            CommandType.RUN_WATCHLIST_PREVIEW.value,
            CommandType.RUN_WATCHLIST_GPT_REVIEW.value,
        }:
            return self._watchlist_preview_result(db, plan=plan)
        if command_type in {
            CommandType.CREATE_EXIT_PREFLIGHT_SCHEDULE.value,
            CommandType.RUN_EXIT_PREFLIGHT.value,
        }:
            return self._exit_preflight_result(db, plan=plan)
        if command_type == CommandType.RUN_EXIT_SHADOW_DECISION.value:
            return self._exit_shadow_result(db, plan=plan)
        if command_type in {
            CommandType.SHOW_LIMITED_AUTO_SELL_READINESS.value,
            CommandType.RUN_LIMITED_AUTO_SELL_REVIEW.value,
            CommandType.SHOW_LIMITED_AUTO_BUY_READINESS.value,
            CommandType.RUN_LIMITED_AUTO_BUY_REVIEW.value,
        }:
            return self._limited_auto_review_result(db, plan=plan)
        if command_type in {
            CommandType.PREPARE_MANUAL_BUY_TICKET.value,
            CommandType.PREPARE_MANUAL_SELL_TICKET.value,
        }:
            return self._prefill_payload(plan=plan, command=command)
        return {
            "result_type": "unsupported_command",
            "command_type": command_type,
            "reason": "command_not_safe_for_agent_gateway",
        }

    def _read_only_result(
        self,
        db: Session,
        *,
        plan: AgentPlan,
        command: dict[str, Any],
    ) -> dict[str, Any]:
        command_type = str(plan.command_type or "")
        if command_type == CommandType.SHOW_SETTINGS.value:
            return {
                "result_type": "read_only_result",
                "read_only": True,
                "settings": RuntimeSettingService().get_settings_read_only(db),
            }
        if command_type in {CommandType.SHOW_RECENT_RUNS.value, CommandType.SHOW_LOGS.value}:
            return {
                "result_type": "read_only_result",
                "read_only": True,
                "runs": [self._trade_run_summary(row) for row in self._recent_trade_runs(db)],
            }
        if command_type == CommandType.SHOW_RECENT_ORDERS.value:
            return {
                "result_type": "read_only_result",
                "read_only": True,
                "orders": [self._order_summary(row) for row in self._recent_orders(db)],
            }
        if command_type == CommandType.SHOW_RECENT_SIGNALS.value:
            return {
                "result_type": "read_only_result",
                "read_only": True,
                "signals": [self._signal_summary(row) for row in self._recent_signals(db)],
            }
        if command_type in {CommandType.SHOW_PORTFOLIO.value, CommandType.SHOW_POSITIONS.value, CommandType.SHOW_POSITION_DETAIL.value}:
            symbol = str(command.get("symbol") or plan.symbol or "").upper() or None
            return self._local_portfolio_snapshot(db, symbol=symbol)
        return {
            "result_type": "read_only_result",
            "read_only": True,
            "command_type": command_type,
            "message": "Read-only agent gateway result. No broker or settings action was attempted.",
            "counts": {
                "runtime_settings_rows": db.query(RuntimeSetting).count(),
                "recent_runs": db.query(TradeRunLog).count(),
                "recent_orders": db.query(OrderLog).count(),
                "recent_signals": db.query(SignalLog).count(),
            },
        }

    def _analysis_result(
        self,
        db: Session,
        *,
        plan: AgentPlan,
        command: dict[str, Any],
    ) -> dict[str, Any]:
        symbol = str(command.get("symbol") or plan.symbol or "").upper() or None
        query = db.query(MarketAnalysis)
        if symbol:
            query = query.filter(MarketAnalysis.symbol == symbol)
        latest = query.order_by(MarketAnalysis.created_at.desc(), MarketAnalysis.id.desc()).first()
        return {
            "result_type": "analysis_result",
            "analysis_only": True,
            "symbol": symbol,
            "latest_analysis": self._market_analysis_summary(latest) if latest else None,
            "message": "Analysis plan completed in PR58 safe mode without trading actions.",
            "preview_only": True,
        }

    def _watchlist_preview_result(self, db: Session, *, plan: AgentPlan) -> dict[str, Any]:
        latest_analysis = (
            db.query(MarketAnalysis)
            .order_by(MarketAnalysis.created_at.desc(), MarketAnalysis.id.desc())
            .limit(10)
            .all()
        )
        latest_signals = self._recent_signals(db, limit=10)
        return {
            "result_type": "watchlist_preview_result",
            "preview_only": True,
            "analysis_count": len(latest_analysis),
            "recent_analysis": [self._market_analysis_summary(row) for row in latest_analysis],
            "recent_signals": [self._signal_summary(row) for row in latest_signals],
            "message": "Watchlist preview completed from local analysis history. No trading path was called.",
            "command_type": plan.command_type,
        }

    def _exit_preflight_result(self, db: Session, *, plan: AgentPlan) -> dict[str, Any]:
        sell_orders = (
            db.query(OrderLog)
            .filter(OrderLog.side == "sell")
            .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
            .limit(10)
            .all()
        )
        return {
            "result_type": "exit_preflight_result",
            "preflight_only": True,
            "recent_sell_orders": [self._order_summary(row) for row in sell_orders],
            "message": "Exit preflight completed as a local review only. No manual sell flow was called.",
            "command_type": plan.command_type,
        }

    def _exit_shadow_result(self, db: Session, *, plan: AgentPlan) -> dict[str, Any]:
        rows = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.trigger_source == "shadow_exit")
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .limit(10)
            .all()
        )
        return {
            "result_type": "shadow_decision_result",
            "shadow_only": True,
            "recent_shadow_runs": [self._trade_run_summary(row) for row in rows],
            "message": "Exit shadow decision reviewed local shadow history only. No broker action was called.",
            "command_type": plan.command_type,
        }

    def _limited_auto_review_result(self, db: Session, *, plan: AgentPlan) -> dict[str, Any]:
        runtime = RuntimeSettingService().get_settings_read_only(db)
        related_runs = (
            db.query(TradeRunLog)
            .filter(
                TradeRunLog.mode.like("%limited_auto%")
            )
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .limit(10)
            .all()
        )
        return {
            "result_type": "analysis_result",
            "review_only": True,
            "command_type": plan.command_type,
            "runtime": {
                "kis_limited_auto_sell_enabled": bool(runtime.get("kis_limited_auto_sell_enabled", False)),
                "kis_limited_auto_buy_enabled": bool(runtime.get("kis_limited_auto_buy_enabled", False)),
                "kis_live_auto_buy_enabled": bool(runtime.get("kis_live_auto_buy_enabled", False)),
                "kis_scheduler_allow_real_orders": bool(runtime.get("kis_scheduler_allow_real_orders", False)),
            },
            "recent_limited_auto_runs": [self._trade_run_summary(row) for row in related_runs],
            "message": "Limited-auto review completed from read-only settings and local run history.",
        }

    def _prefill_payload(self, *, plan: AgentPlan, command: dict[str, Any]) -> dict[str, Any]:
        return {
            "result_type": "prefill_payload",
            "prefill_only": True,
            "symbol": command.get("symbol") or plan.symbol,
            "side": command.get("side") or plan.side,
            "quantity": command.get("quantity"),
            "budget": command.get("budget"),
            "market": command.get("market") or plan.market,
            "provider": command.get("provider") or plan.provider,
            "requires_user_validation": True,
            "requires_confirm_live": True,
            "submit_blocked_in_pr58": True,
            "message": "Manual ticket prefill returned only. No validation or live action was called.",
        }

    def _local_portfolio_snapshot(self, db: Session, *, symbol: str | None = None) -> dict[str, Any]:
        order_query = db.query(OrderLog)
        signal_query = db.query(SignalLog)
        if symbol:
            order_query = order_query.filter(OrderLog.symbol == symbol)
            signal_query = signal_query.filter(SignalLog.symbol == symbol)
        orders = order_query.order_by(OrderLog.created_at.desc(), OrderLog.id.desc()).limit(20).all()
        signals = signal_query.order_by(SignalLog.created_at.desc(), SignalLog.id.desc()).limit(20).all()
        return {
            "result_type": "read_only_result",
            "read_only": True,
            "source": "local_logs_only",
            "symbol": symbol,
            "positions": [],
            "position_source": "not_fetched_from_broker_in_pr58",
            "recent_orders": [self._order_summary(row) for row in orders],
            "recent_signals": [self._signal_summary(row) for row in signals],
        }

    def _blocked_result(self, plan: AgentPlan, policy: Any) -> dict[str, Any]:
        return {
            "result_type": policy.result_type,
            "blocked": True,
            "reason": policy.reason,
            "command_type": plan.command_type,
            "risk_level": plan.risk_level,
            "policy": policy.as_dict(),
        }

    def _response(
        self,
        *,
        status: str,
        plan: AgentPlan,
        run: AgentPlanRun,
        result: dict[str, Any],
        safety: AgentExecutionSafetyFlags,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "plan_id": plan.id,
            "plan_run_id": run.id,
            "command_type": plan.command_type,
            "result": result,
            "safety": safety.model_dump(mode="json"),
        }

    def _request_payload(self, request: AgentPlanRunRequest | dict[str, Any] | None) -> dict[str, Any]:
        if request is None:
            return AgentPlanRunRequest().model_dump(mode="json")
        if isinstance(request, AgentPlanRunRequest):
            return request.model_dump(mode="json")
        return AgentPlanRunRequest.model_validate(request).model_dump(mode="json")

    def _plan_command(self, plan: AgentPlan) -> dict[str, Any]:
        return self._parse_json_object(plan.command_json)

    def _recent_trade_runs(self, db: Session, *, limit: int = 20) -> list[TradeRunLog]:
        return db.query(TradeRunLog).order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc()).limit(limit).all()

    def _recent_orders(self, db: Session, *, limit: int = 20) -> list[OrderLog]:
        return db.query(OrderLog).order_by(OrderLog.created_at.desc(), OrderLog.id.desc()).limit(limit).all()

    def _recent_signals(self, db: Session, *, limit: int = 20) -> list[SignalLog]:
        return db.query(SignalLog).order_by(SignalLog.created_at.desc(), SignalLog.id.desc()).limit(limit).all()

    def _trade_run_summary(self, row: TradeRunLog) -> dict[str, Any]:
        return {
            "id": row.id,
            "run_key": row.run_key,
            "trigger_source": row.trigger_source,
            "symbol": row.symbol,
            "mode": row.mode,
            "stage": row.stage,
            "result": row.result,
            "reason": row.reason,
            "signal_id": row.signal_id,
            "order_id": row.order_id,
            "created_at": row.created_at,
        }

    def _order_summary(self, row: OrderLog) -> dict[str, Any]:
        return {
            "id": row.id,
            "broker": row.broker,
            "market": row.market,
            "symbol": row.symbol,
            "side": row.side,
            "order_type": row.order_type,
            "internal_status": row.internal_status,
            "broker_status": row.broker_status,
            "qty": row.qty,
            "notional": row.notional,
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

    def _market_analysis_summary(self, row: MarketAnalysis) -> dict[str, Any]:
        return {
            "id": row.id,
            "symbol": row.symbol,
            "market_regime": row.market_regime,
            "entry_bias": row.entry_bias,
            "entry_allowed": bool(row.entry_allowed),
            "market_confidence": row.market_confidence,
            "risk_note": row.risk_note,
            "created_at": row.created_at,
        }

    def _parse_json_object(self, raw_value: str | None) -> dict[str, Any]:
        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
        return {}

    def _safe_error(self, exc: Exception) -> str:
        text = str(exc).strip() or exc.__class__.__name__
        if len(text) > 240:
            text = f"{text[:240]}..."
        return f"{exc.__class__.__name__}: {text}"
