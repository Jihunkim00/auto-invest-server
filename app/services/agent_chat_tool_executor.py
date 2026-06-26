from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.brokers.alpaca_client import AlpacaClient
from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.schemas.agent_chat_orchestrator import AgentChatIntent
from app.schemas.agent_chat_tool import AgentChatToolCall, AgentChatToolResult, AgentChatToolSafety
from app.services.agent_chat_tool_registry import AgentChatToolRegistry
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.kis_watchlist_preview_service import KisWatchlistPreviewService
from app.services.profile_aware_dry_run_auto_buy_service import (
    ProfileAwareDryRunAutoBuyService,
)
from app.services.profile_aware_guarded_live_auto_buy_service import (
    ProfileAwareGuardedLiveAutoBuyService,
)
from app.services.profile_aware_guarded_live_auto_exit_service import (
    ProfileAwareGuardedLiveAutoExitService,
)
from app.services.strategy_auto_buy_operations_service import (
    StrategyAutoBuyOperationsService,
)
from app.services.strategy_risk_budget_service import StrategyRiskBudgetService
from app.services.strategy_profile_service import StrategyProfileService
from app.services.strategy_performance_service import StrategyPerformanceService
from app.services.target_aware_risk_service import TargetAwareRiskService


class AgentChatToolExecutor:
    def __init__(
        self,
        *,
        registry: AgentChatToolRegistry | None = None,
        kis_client_factory: Callable[[Session], KisClient] | None = None,
        alpaca_client_factory: Callable[[], AlpacaClient] | None = None,
        runtime_setting_service: RuntimeSettingService | None = None,
        strategy_profile_service: StrategyProfileService | None = None,
        strategy_performance_service: StrategyPerformanceService | None = None,
        target_aware_risk_service: TargetAwareRiskService | None = None,
        dry_run_auto_buy_service_factory: Callable[
            [Session], ProfileAwareDryRunAutoBuyService
        ]
        | None = None,
        live_auto_buy_service_factory: Callable[
            [Session], ProfileAwareGuardedLiveAutoBuyService
        ]
        | None = None,
        auto_buy_operations_service_factory: Callable[
            [Session], StrategyAutoBuyOperationsService
        ]
        | None = None,
        live_auto_exit_service_factory: Callable[
            [Session], ProfileAwareGuardedLiveAutoExitService
        ]
        | None = None,
    ) -> None:
        self.registry = registry or AgentChatToolRegistry()
        self.kis_client_factory = kis_client_factory or self._default_kis_client
        self.alpaca_client_factory = alpaca_client_factory or AlpacaClient
        self.runtime_setting_service = runtime_setting_service or RuntimeSettingService()
        self.strategy_profile_service = strategy_profile_service or StrategyProfileService()
        self.strategy_performance_service = strategy_performance_service or StrategyPerformanceService(
            position_loader=lambda db, provider, market: (
                self.kis_client_factory(db).list_positions()
                if provider == "kis" and market == "KR"
                else []
            ),
            strategy_profiles=self.strategy_profile_service,
        )
        self.target_aware_risk_service = (
            target_aware_risk_service or TargetAwareRiskService()
        )
        self.dry_run_auto_buy_service_factory = (
            dry_run_auto_buy_service_factory
            or self._default_dry_run_auto_buy_service
        )
        self.live_auto_buy_service_factory = (
            live_auto_buy_service_factory
            or self._default_live_auto_buy_service
        )
        self.auto_buy_operations_service_factory = (
            auto_buy_operations_service_factory
            or self._default_auto_buy_operations_service
        )
        self.live_auto_exit_service_factory = (
            live_auto_exit_service_factory
            or self._default_live_auto_exit_service
        )

    def execute_many(
        self,
        db: Session,
        *,
        calls: list[AgentChatToolCall],
        intent: AgentChatIntent,
    ) -> list[AgentChatToolResult]:
        return [self.execute(db, call=call, intent=intent) for call in calls]

    def execute(
        self,
        db: Session,
        *,
        call: AgentChatToolCall,
        intent: AgentChatIntent,
    ) -> AgentChatToolResult:
        tool = self.registry.get(call.tool_name)
        if tool is None:
            return self._unsupported(call.tool_name, "Tool is not allowlisted.")
        if not self.registry.can_auto_execute(tool.tool_name):
            return self._blocked(tool.tool_name, tool.mode, "Tool is not allowed to auto-execute from chat.")

        try:
            if tool.tool_name == "kis_price_lookup":
                return self._kis_price(call, intent, db)
            if tool.tool_name == "alpaca_price_lookup":
                return self._alpaca_price(call, intent)
            if tool.tool_name == "kis_positions_lookup":
                return self._kis_positions(db)
            if tool.tool_name == "kis_balance_lookup":
                return self._kis_balance(db)
            if tool.tool_name == "recent_orders_lookup":
                return self._recent_orders(db)
            if tool.tool_name == "recent_runs_lookup":
                return self._recent_runs(db)
            if tool.tool_name == "recent_signals_lookup":
                return self._recent_signals(db)
            if tool.tool_name == "ops_settings_lookup":
                return self._ops_settings(db)
            if tool.tool_name == "strategy_profiles_lookup":
                return self._strategy_profiles(db)
            if tool.tool_name == "active_strategy_profile_lookup":
                return self._active_strategy_profile(db)
            if tool.tool_name == "strategy_monthly_progress_lookup":
                return self._strategy_monthly_progress(db)
            if tool.tool_name == "strategy_risk_budget_lookup":
                return self._strategy_risk_budget(db)
            if tool.tool_name == "strategy_daily_performance_lookup":
                return self._strategy_daily_performance(db)
            if tool.tool_name == "strategy_monthly_performance_lookup":
                return self._strategy_monthly_performance(db)
            if tool.tool_name == "strategy_trade_performance_lookup":
                return self._strategy_trade_performance(db, call)
            if tool.tool_name == "strategy_target_progress_lookup":
                return self._strategy_target_progress(db, call)
            if tool.tool_name == "strategy_risk_state_lookup":
                return self._strategy_risk_state(db, intent)
            if tool.tool_name == "strategy_entry_risk_evaluate":
                return self._strategy_entry_risk(db, call, intent)
            if tool.tool_name == "strategy_order_sizing_lookup":
                return self._strategy_order_sizing(db, call, intent)
            if tool.tool_name == "strategy_dry_run_auto_buy_once":
                return self._strategy_dry_run_auto_buy_once(db, call, intent)
            if tool.tool_name == "strategy_dry_run_auto_buy_recent_lookup":
                return self._strategy_dry_run_auto_buy_recent(db, call, intent)
            if tool.tool_name == "strategy_dry_run_auto_buy_summary_lookup":
                return self._strategy_dry_run_auto_buy_summary(db, intent)
            if tool.tool_name == "strategy_live_auto_buy_readiness_lookup":
                return self._strategy_live_auto_buy_readiness(db, call, intent)
            if tool.tool_name == "strategy_auto_buy_operations_status_lookup":
                return self._strategy_auto_buy_operations_status(db, intent)
            if tool.tool_name == "strategy_live_auto_buy_recent_lookup":
                return self._strategy_live_auto_buy_recent(db, intent)
            if tool.tool_name == "strategy_live_auto_exit_readiness_lookup":
                return self._strategy_live_auto_exit_readiness(db, call, intent)
            if tool.tool_name == "strategy_live_auto_exit_recent_lookup":
                return self._strategy_live_auto_exit_recent(db, intent)
            if tool.tool_name == "strategy_exit_candidate_lookup":
                return self._strategy_exit_candidate(db, call, intent)
            if tool.tool_name == "watchlist_preview":
                return self._analysis_stub(tool.tool_name, "analysis")
            if tool.tool_name == "safe_symbol_analysis":
                return self._safe_symbol_analysis(call, intent)
        except Exception as exc:
            return self._failed(tool.tool_name, self._result_type_for_tool(tool.tool_name), self._safe_error(exc))

        return self._unsupported(tool.tool_name, "Tool has no executor implementation.")

    def _kis_price(
        self,
        call: AgentChatToolCall,
        intent: AgentChatIntent,
        db: Session,
    ) -> AgentChatToolResult:
        symbol = self._symbol(call, intent)
        if not symbol:
            return self._failed("kis_price_lookup", "price", "Missing symbol.")
        payload = self.kis_client_factory(db).get_domestic_stock_price(symbol)
        price = {
            "symbol": payload.get("symbol") or symbol,
            "name": payload.get("name") or intent.symbol_name or symbol,
            "price": payload.get("current_price"),
            "current_price": payload.get("current_price"),
            "currency": "KRW",
            "provider": "kis",
            "market": "KR",
            "timestamp": payload.get("timestamp"),
        }
        return self._success(
            "kis_price_lookup",
            "price",
            {"price": price},
            f"KIS read-only price lookup completed for {symbol}.",
        )

    def _alpaca_price(self, call: AgentChatToolCall, intent: AgentChatIntent) -> AgentChatToolResult:
        symbol = self._symbol(call, intent)
        if not symbol:
            return self._failed("alpaca_price_lookup", "price", "Missing symbol.")
        payload = self.alpaca_client_factory().get_latest_price(symbol)
        if not payload:
            return self._failed("alpaca_price_lookup", "price", "No latest price response.")
        price = {
            "symbol": payload.get("symbol") or symbol,
            "name": intent.symbol_name or symbol,
            "price": payload.get("price"),
            "current_price": payload.get("price"),
            "currency": "USD",
            "provider": "alpaca",
            "market": "US",
            "timestamp": payload.get("timestamp"),
        }
        return self._success(
            "alpaca_price_lookup",
            "price",
            {"price": price},
            f"Alpaca read-only price lookup completed for {symbol}.",
        )

    def _kis_positions(self, db: Session) -> AgentChatToolResult:
        positions = self.kis_client_factory(db).list_positions()
        data = {"provider": "kis", "market": "KR", "count": len(positions), "positions": positions}
        return self._success("kis_positions_lookup", "positions", data, f"Found {len(positions)} KIS positions.")

    def _kis_balance(self, db: Session) -> AgentChatToolResult:
        balance = self.kis_client_factory(db).get_account_balance()
        return self._success("kis_balance_lookup", "balance", {"balance": balance}, "KIS balance lookup completed.")

    def _recent_orders(self, db: Session, *, limit: int = 10) -> AgentChatToolResult:
        rows = db.query(OrderLog).order_by(OrderLog.created_at.desc(), OrderLog.id.desc()).limit(limit).all()
        data = {"count": len(rows), "orders": [self._order_summary(row) for row in rows]}
        return self._success("recent_orders_lookup", "orders", data, f"Found {len(rows)} recent orders.")

    def _recent_runs(self, db: Session, *, limit: int = 10) -> AgentChatToolResult:
        rows = db.query(TradeRunLog).order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc()).limit(limit).all()
        data = {"count": len(rows), "runs": [self._run_summary(row) for row in rows]}
        return self._success("recent_runs_lookup", "runs", data, f"Found {len(rows)} recent runs.")

    def _recent_signals(self, db: Session, *, limit: int = 10) -> AgentChatToolResult:
        rows = db.query(SignalLog).order_by(SignalLog.created_at.desc(), SignalLog.id.desc()).limit(limit).all()
        data = {"count": len(rows), "signals": [self._signal_summary(row) for row in rows]}
        return self._success("recent_signals_lookup", "signals", data, f"Found {len(rows)} recent signals.")

    def _ops_settings(self, db: Session) -> AgentChatToolResult:
        settings = self.runtime_setting_service.get_settings_read_only(db)
        keys = [
            "dry_run",
            "kill_switch",
            "bot_enabled",
            "scheduler_enabled",
            "kis_enabled",
            "kis_real_order_enabled",
            "kis_scheduler_enabled",
            "kis_scheduler_dry_run",
            "kis_scheduler_live_enabled",
            "kis_scheduler_allow_real_orders",
            "kis_live_auto_buy_enabled",
            "kis_live_auto_sell_enabled",
            "kis_limited_auto_buy_enabled",
            "kis_limited_auto_sell_enabled",
        ]
        data = {key: settings.get(key) for key in keys if key in settings}
        return self._success("ops_settings_lookup", "settings", {"settings": data}, "Read-only safety settings lookup completed.")

    def _strategy_profiles(self, db: Session) -> AgentChatToolResult:
        data = self.strategy_profile_service.list_profiles(db)
        return self._success(
            "strategy_profiles_lookup",
            "strategy_profiles",
            data,
            "Read-only strategy profiles lookup completed.",
        )

    def _active_strategy_profile(self, db: Session) -> AgentChatToolResult:
        active = self.strategy_profile_service.active_profile(db)
        data = {"active_profile": self.strategy_profile_service.serialize_profile(active)}
        return self._success(
            "active_strategy_profile_lookup",
            "strategy_profile",
            data,
            "Read-only active strategy profile lookup completed.",
        )

    def _strategy_monthly_progress(self, db: Session) -> AgentChatToolResult:
        return self._success(
            "strategy_monthly_progress_lookup",
            "strategy_monthly_progress",
            self.strategy_profile_service.monthly_progress(db),
            "Read-only strategy monthly progress lookup completed.",
        )

    def _strategy_risk_budget(self, db: Session) -> AgentChatToolResult:
        return self._success(
            "strategy_risk_budget_lookup",
            "strategy_risk_budget",
            self.strategy_profile_service.risk_budget(db),
            "Read-only strategy risk budget lookup completed.",
        )

    def _strategy_daily_performance(self, db: Session) -> AgentChatToolResult:
        return self._success(
            "strategy_daily_performance_lookup",
            "strategy_daily_performance",
            self.strategy_performance_service.daily(db),
            "Read-only daily strategy performance lookup completed.",
        )

    def _strategy_monthly_performance(self, db: Session) -> AgentChatToolResult:
        return self._success(
            "strategy_monthly_performance_lookup",
            "strategy_monthly_performance",
            self.strategy_performance_service.monthly(db),
            "Read-only monthly strategy performance lookup completed.",
        )

    def _strategy_trade_performance(
        self,
        db: Session,
        call: AgentChatToolCall,
    ) -> AgentChatToolResult:
        return self._success(
            "strategy_trade_performance_lookup",
            "strategy_trade_performance",
            self.strategy_performance_service.trades(
                db,
                symbol=str(call.arguments.get("symbol") or "") or None,
                limit=10,
            ),
            "Read-only trade performance lookup completed.",
        )

    def _strategy_target_progress(
        self,
        db: Session,
        call: AgentChatToolCall,
    ) -> AgentChatToolResult:
        return self._success(
            "strategy_target_progress_lookup",
            "strategy_target_progress",
            self.strategy_performance_service.monthly(
                db,
                profile_name=str(call.arguments.get("profile_name") or "") or None,
            ),
            "Read-only target and loss-budget progress lookup completed.",
        )

    def _strategy_risk_state(
        self,
        db: Session,
        intent: AgentChatIntent,
    ) -> AgentChatToolResult:
        data = self.target_aware_risk_service.risk_state(
            db,
            provider=str(intent.provider or "kis"),
            market=str(intent.market or "KR"),
        )
        return self._success(
            "strategy_risk_state_lookup",
            "strategy_risk_state",
            data,
            "Read-only target-aware strategy risk state lookup completed.",
        )

    def _strategy_entry_risk(
        self,
        db: Session,
        call: AgentChatToolCall,
        intent: AgentChatIntent,
    ) -> AgentChatToolResult:
        arguments = call.arguments
        data = self.target_aware_risk_service.evaluate_entry(
            db,
            {
                "provider": str(intent.provider or "kis"),
                "market": str(intent.market or "KR"),
                "symbol": self._symbol(call, intent) or "UNSPECIFIED",
                "side": str(intent.side or "buy")
                if str(intent.side or "").lower() in {"buy", "sell"}
                else "buy",
                "requested_notional_krw": arguments.get("requested_notional_krw")
                or intent.notional,
                "requested_notional_pct": arguments.get("requested_notional_pct"),
                "buy_score": arguments.get("buy_score"),
                "sell_score": arguments.get("sell_score"),
                "confidence": arguments.get("confidence"),
                "trigger_source": "agent_chat_read_only",
                "dry_run": True,
            },
        )
        return self._success(
            "strategy_entry_risk_evaluate",
            "strategy_entry_risk",
            data,
            "Read-only target-aware entry risk evaluation completed.",
        )

    def _strategy_order_sizing(
        self,
        db: Session,
        call: AgentChatToolCall,
        intent: AgentChatIntent,
    ) -> AgentChatToolResult:
        result = self._strategy_entry_risk(db, call, intent)
        return AgentChatToolResult(
            tool_name="strategy_order_sizing_lookup",
            status=result.status,
            result_type="strategy_order_sizing",
            data=result.data,
            summary="Read-only target-aware order sizing recommendation completed.",
            safety=result.safety,
        )

    def _strategy_dry_run_auto_buy_once(
        self,
        db: Session,
        call: AgentChatToolCall,
        intent: AgentChatIntent,
    ) -> AgentChatToolResult:
        data = self.dry_run_auto_buy_service_factory(db).run_once(
            db,
            {
                "provider": str(intent.provider or "kis"),
                "market": str(intent.market or "KR"),
                "profile_name": call.arguments.get("profile_name")
                or intent.requested_profile,
                "symbol": call.arguments.get("symbol") or intent.symbol,
                "max_candidates": 5,
                "trigger_source": "agent_chat",
                "use_watchlist": True,
                "save_logs": True,
            },
        )
        return self._success(
            "strategy_dry_run_auto_buy_once",
            "strategy_dry_run_auto_buy",
            data,
            "Profile-aware dry-run auto-buy simulation completed. No order or validation ran.",
            read_only=False,
        )

    def _strategy_dry_run_auto_buy_recent(
        self,
        db: Session,
        call: AgentChatToolCall,
        intent: AgentChatIntent,
    ) -> AgentChatToolResult:
        data = self.dry_run_auto_buy_service_factory(db).recent(
            db,
            provider=str(intent.provider or "kis"),
            market=str(intent.market or "KR"),
            profile_name=call.arguments.get("profile_name")
            or intent.requested_profile,
            symbol=call.arguments.get("symbol") or intent.symbol,
            limit=10,
        )
        return self._success(
            "strategy_dry_run_auto_buy_recent_lookup",
            "strategy_dry_run_auto_buy_recent",
            data,
            "Recent profile-aware dry-run auto-buy results loaded.",
        )

    def _strategy_dry_run_auto_buy_summary(
        self,
        db: Session,
        intent: AgentChatIntent,
    ) -> AgentChatToolResult:
        data = self.dry_run_auto_buy_service_factory(db).summary(
            db,
            provider=str(intent.provider or "kis"),
            market=str(intent.market or "KR"),
        )
        return self._success(
            "strategy_dry_run_auto_buy_summary_lookup",
            "strategy_dry_run_auto_buy_summary",
            data,
            "Profile-aware dry-run auto-buy summary loaded.",
        )

    def _strategy_live_auto_buy_readiness(
        self,
        db: Session,
        call: AgentChatToolCall,
        intent: AgentChatIntent,
    ) -> AgentChatToolResult:
        data = self.live_auto_buy_service_factory(db).readiness(
            db,
            provider="kis",
            market="KR",
            symbol=call.arguments.get("symbol") or intent.symbol,
        )
        return self._success(
            "strategy_live_auto_buy_readiness_lookup",
            "strategy_live_auto_buy_readiness",
            data,
            "Guarded live auto-buy readiness loaded. No validation or submit ran.",
        )

    def _strategy_live_auto_buy_recent(
        self,
        db: Session,
        intent: AgentChatIntent,
    ) -> AgentChatToolResult:
        data = self.live_auto_buy_service_factory(db).recent(
            db,
            provider="kis",
            market="KR",
            limit=10,
        )
        return self._success(
            "strategy_live_auto_buy_recent_lookup",
            "strategy_live_auto_buy_recent",
            data,
            "Recent guarded live auto-buy attempts loaded.",
        )

    def _strategy_auto_buy_operations_status(
        self,
        db: Session,
        intent: AgentChatIntent,
    ) -> AgentChatToolResult:
        data = self.auto_buy_operations_service_factory(db).status(
            db,
            provider="kis",
            market="KR",
        )
        return self._success(
            "strategy_auto_buy_operations_status_lookup",
            "strategy_auto_buy_operations_status",
            data,
            (
                "Read-only auto-buy operations status loaded. "
                "No validation, submit, run-once, scheduler, or settings path ran."
            ),
        )

    def _strategy_live_auto_exit_readiness(
        self,
        db: Session,
        call: AgentChatToolCall,
        intent: AgentChatIntent,
    ) -> AgentChatToolResult:
        symbol = self._kr_numeric_symbol(call, intent)
        data = self.live_auto_exit_service_factory(db).readiness(
            db,
            provider="kis",
            market="KR",
            symbol=symbol,
        )
        return self._success(
            "strategy_live_auto_exit_readiness_lookup",
            "strategy_live_auto_exit_readiness",
            data,
            "Guarded live auto-exit readiness loaded. No validation or submit ran.",
        )

    def _strategy_live_auto_exit_recent(
        self,
        db: Session,
        intent: AgentChatIntent,
    ) -> AgentChatToolResult:
        data = self.live_auto_exit_service_factory(db).recent(
            db,
            provider="kis",
            market="KR",
            limit=10,
        )
        return self._success(
            "strategy_live_auto_exit_recent_lookup",
            "strategy_live_auto_exit_recent",
            data,
            "Recent guarded live auto-exit attempts loaded.",
        )

    def _strategy_exit_candidate(
        self,
        db: Session,
        call: AgentChatToolCall,
        intent: AgentChatIntent,
    ) -> AgentChatToolResult:
        symbol = self._kr_numeric_symbol(call, intent)
        data = self.live_auto_exit_service_factory(db).readiness(
            db,
            provider="kis",
            market="KR",
            symbol=symbol,
        )
        return self._success(
            "strategy_exit_candidate_lookup",
            "strategy_exit_candidate",
            data,
            "Held-position exit candidates loaded. No validation or submit ran.",
        )

    def _analysis_stub(self, tool_name: str, result_type: str) -> AgentChatToolResult:
        data = {
            "analysis": {
                "action": "review",
                "note": "Analysis-only chat tool selected. No order or setting path was executed.",
            }
        }
        return self._success(tool_name, result_type, data, "Analysis-only tool selected. No mutation performed.", read_only=False)

    def _safe_symbol_analysis(
        self,
        call: AgentChatToolCall,
        intent: AgentChatIntent,
    ) -> AgentChatToolResult:
        symbol = self._symbol(call, intent)
        data = {
            "analysis": {
                "symbol": symbol,
                "action": "hold",
                "note": "Safe analysis mode selected. No order path was executed.",
            }
        }
        return self._success("safe_symbol_analysis", "analysis", data, "Safe symbol analysis selected.", read_only=False)

    def _success(
        self,
        tool_name: str,
        result_type: str,
        data: dict[str, Any],
        summary: str,
        *,
        read_only: bool = True,
    ) -> AgentChatToolResult:
        return AgentChatToolResult(
            tool_name=tool_name,
            status="success",
            result_type=result_type,
            data=data,
            summary=summary,
            safety=AgentChatToolSafety(read_only=read_only),
        )

    def _failed(self, tool_name: str, result_type: str, error_message: str) -> AgentChatToolResult:
        return AgentChatToolResult(
            tool_name=tool_name,
            status="failed",
            result_type=result_type,
            data={},
            summary=error_message,
            error_message=error_message,
            safety=AgentChatToolSafety(),
        )

    def _blocked(self, tool_name: str, result_type: str, summary: str) -> AgentChatToolResult:
        return AgentChatToolResult(
            tool_name=tool_name,
            status="blocked",
            result_type=result_type,
            data={},
            summary=summary,
            error_message=summary,
            safety=AgentChatToolSafety(),
        )

    def _unsupported(self, tool_name: str, summary: str) -> AgentChatToolResult:
        return AgentChatToolResult(
            tool_name=str(tool_name or "unknown"),
            status="unsupported",
            result_type="unsupported",
            data={},
            summary=summary,
            error_message=summary,
            safety=AgentChatToolSafety(),
        )

    def _result_type_for_tool(self, tool_name: str) -> str:
        mapping = {
            "kis_price_lookup": "price",
            "alpaca_price_lookup": "price",
            "kis_positions_lookup": "positions",
            "kis_balance_lookup": "balance",
            "recent_orders_lookup": "orders",
            "recent_runs_lookup": "runs",
            "recent_signals_lookup": "signals",
            "ops_settings_lookup": "settings",
            "strategy_profiles_lookup": "strategy_profiles",
            "active_strategy_profile_lookup": "strategy_profile",
            "strategy_monthly_progress_lookup": "strategy_monthly_progress",
            "strategy_risk_budget_lookup": "strategy_risk_budget",
            "strategy_daily_performance_lookup": "strategy_daily_performance",
            "strategy_monthly_performance_lookup": "strategy_monthly_performance",
            "strategy_trade_performance_lookup": "strategy_trade_performance",
            "strategy_target_progress_lookup": "strategy_target_progress",
            "strategy_risk_state_lookup": "strategy_risk_state",
            "strategy_entry_risk_evaluate": "strategy_entry_risk",
            "strategy_order_sizing_lookup": "strategy_order_sizing",
            "strategy_dry_run_auto_buy_once": "strategy_dry_run_auto_buy",
            "strategy_dry_run_auto_buy_recent_lookup": "strategy_dry_run_auto_buy_recent",
            "strategy_dry_run_auto_buy_summary_lookup": "strategy_dry_run_auto_buy_summary",
            "strategy_live_auto_buy_readiness_lookup": "strategy_live_auto_buy_readiness",
            "strategy_auto_buy_operations_status_lookup": "strategy_auto_buy_operations_status",
            "strategy_live_auto_buy_recent_lookup": "strategy_live_auto_buy_recent",
            "strategy_live_auto_exit_readiness_lookup": "strategy_live_auto_exit_readiness",
            "strategy_live_auto_exit_recent_lookup": "strategy_live_auto_exit_recent",
            "strategy_exit_candidate_lookup": "strategy_exit_candidate",
            "watchlist_preview": "analysis",
            "safe_symbol_analysis": "analysis",
        }
        return mapping.get(tool_name, "unsupported")

    def _symbol(self, call: AgentChatToolCall, intent: AgentChatIntent) -> str:
        return str(call.arguments.get("symbol") or intent.symbol or "").strip().upper()

    def _kr_numeric_symbol(
        self,
        call: AgentChatToolCall,
        intent: AgentChatIntent,
    ) -> str | None:
        symbol = self._symbol(call, intent)
        if not symbol.isdigit() or len(symbol) > 6:
            return None
        return symbol.zfill(6)

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

    def _default_dry_run_auto_buy_service(
        self,
        db: Session,
    ) -> ProfileAwareDryRunAutoBuyService:
        client = self.kis_client_factory(db)
        target_risk = TargetAwareRiskService(
            budget_service=StrategyRiskBudgetService(
                position_loader=lambda session, provider, market: (
                    client.list_positions()
                    if provider == "kis" and market == "KR"
                    else []
                ),
                balance_loader=lambda session, provider, market: (
                    client.get_account_balance()
                    if provider == "kis" and market == "KR"
                    else {}
                ),
            )
        )
        return ProfileAwareDryRunAutoBuyService(
            preview_service=KisWatchlistPreviewService(client, db=db),
            target_risk_service=target_risk,
        )

    def _default_live_auto_buy_service(
        self,
        db: Session,
    ) -> ProfileAwareGuardedLiveAutoBuyService:
        client = self.kis_client_factory(db)
        target_risk = TargetAwareRiskService(
            budget_service=StrategyRiskBudgetService(
                position_loader=lambda session, provider, market: (
                    client.list_positions()
                    if provider == "kis" and market == "KR"
                    else []
                ),
                balance_loader=lambda session, provider, market: (
                    client.get_account_balance()
                    if provider == "kis" and market == "KR"
                    else {}
                ),
            )
        )
        return ProfileAwareGuardedLiveAutoBuyService(
            client=client,
            target_risk_service=target_risk,
            positions_loader=lambda session: client.list_positions(),
            balance_loader=lambda session: client.get_account_balance(),
            open_orders_loader=lambda session: client.list_open_orders(),
        )

    def _default_auto_buy_operations_service(
        self,
        db: Session,
    ) -> StrategyAutoBuyOperationsService:
        return StrategyAutoBuyOperationsService(
            dry_run_service=self.dry_run_auto_buy_service_factory(db),
            live_auto_buy_service=self.live_auto_buy_service_factory(db),
            target_risk_service=self.target_aware_risk_service,
        )

    def _default_live_auto_exit_service(
        self,
        db: Session,
    ) -> ProfileAwareGuardedLiveAutoExitService:
        client = self.kis_client_factory(db)
        return ProfileAwareGuardedLiveAutoExitService(
            client=client,
            positions_loader=lambda session: client.list_positions(),
            open_orders_loader=lambda session: client.list_open_orders(),
        )

    def _safe_error(self, exc: Exception) -> str:
        text = str(exc).strip() or exc.__class__.__name__
        if len(text) > 240:
            return f"{exc.__class__.__name__}: {text[:240]}..."
        return text
