from __future__ import annotations

from app.schemas.agent_chat_tool import AgentChatToolDefinition


class AgentChatToolRegistry:
    def __init__(self, tools: list[AgentChatToolDefinition] | None = None) -> None:
        self._tools = {tool.tool_name: tool for tool in (tools or _DEFAULT_TOOLS)}

    def list_tools(self, *, include_blocked: bool = True) -> list[AgentChatToolDefinition]:
        tools = list(self._tools.values())
        if include_blocked:
            return tools
        return [tool for tool in tools if tool.allowed_auto_execute and not tool.mutation]

    def tool_names(self, *, include_blocked: bool = True) -> list[str]:
        return [tool.tool_name for tool in self.list_tools(include_blocked=include_blocked)]

    def get(self, tool_name: str) -> AgentChatToolDefinition | None:
        return self._tools.get(str(tool_name or "").strip())

    def require(self, tool_name: str) -> AgentChatToolDefinition:
        tool = self.get(tool_name)
        if tool is None:
            raise KeyError(tool_name)
        return tool

    def can_auto_execute(self, tool_name: str) -> bool:
        tool = self.get(tool_name)
        if tool is None:
            return False
        return bool(tool.allowed_auto_execute and not tool.mutation and tool.mode in _AUTO_MODES)

    def is_blocked(self, tool_name: str) -> bool:
        tool = self.get(tool_name)
        return tool is None or tool.mode == "blocked" or not self.can_auto_execute(tool_name)


_DEFAULT_TOOLS = [
    AgentChatToolDefinition(
        tool_name="kis_price_lookup",
        display_name="KIS Price Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only current price lookup for Korean stocks through KIS.",
    ),
    AgentChatToolDefinition(
        tool_name="alpaca_price_lookup",
        display_name="Alpaca Price Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="alpaca",
        market="US",
        description="Read-only latest price lookup for US stocks through Alpaca.",
    ),
    AgentChatToolDefinition(
        tool_name="kis_positions_lookup",
        display_name="KIS Positions Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only KIS positions lookup.",
    ),
    AgentChatToolDefinition(
        tool_name="kis_balance_lookup",
        display_name="KIS Balance Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only KIS account balance lookup.",
    ),
    AgentChatToolDefinition(
        tool_name="recent_orders_lookup",
        display_name="Recent Orders Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        description="Read-only local recent order log lookup.",
    ),
    AgentChatToolDefinition(
        tool_name="recent_runs_lookup",
        display_name="Recent Runs Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        description="Read-only local recent trading run lookup.",
    ),
    AgentChatToolDefinition(
        tool_name="recent_signals_lookup",
        display_name="Recent Signals Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        description="Read-only local recent signal lookup.",
    ),
    AgentChatToolDefinition(
        tool_name="ops_settings_lookup",
        display_name="Operations Settings Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        description="Read-only runtime safety settings lookup.",
    ),
    AgentChatToolDefinition(
        tool_name="daily_ops_summary_lookup",
        display_name="Daily Operations Summary",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only local daily operations, P&L, order, promotion, scheduler, risk, and reconciliation summary. It never syncs, validates, submits, retries, or changes settings.",
    ),
    AgentChatToolDefinition(
        tool_name="operator_alerts_lookup",
        display_name="Operator Alerts Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only operator alert lookup from local DB state. It never syncs, validates, submits, changes settings, or runs a scheduler.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_profiles_lookup",
        display_name="Strategy Profiles Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        description="Read-only lookup for safe, balanced, and aggressive strategy profiles.",
    ),
    AgentChatToolDefinition(
        tool_name="active_strategy_profile_lookup",
        display_name="Active Strategy Profile Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        description="Read-only lookup for the currently active strategy profile.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_monthly_progress_lookup",
        display_name="Strategy Monthly Progress Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        description="Read-only skeleton lookup for active profile monthly target progress.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_risk_budget_lookup",
        display_name="Strategy Risk Budget Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        description="Read-only lookup for active profile order and loss limits.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_daily_performance_lookup",
        display_name="Strategy Daily Performance Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only daily realized, unrealized, and estimated net P&L lookup.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_monthly_performance_lookup",
        display_name="Strategy Monthly Performance Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only monthly P&L and active strategy target progress lookup.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_trade_performance_lookup",
        display_name="Strategy Trade Performance Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only FIFO best-effort trade performance lookup.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_target_progress_lookup",
        display_name="Strategy Target Progress Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only target progress and loss budget lookup.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_risk_state_lookup",
        display_name="Strategy Risk State Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only profile-aware and target-aware entry risk state lookup.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_entry_risk_evaluate",
        display_name="Strategy Entry Risk Evaluate",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only entry risk evaluation. It never validates or submits an order.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_order_sizing_lookup",
        display_name="Strategy Order Sizing Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only profile-aware order sizing recommendation.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_dry_run_auto_buy_once",
        display_name="Strategy Dry-Run Auto Buy Once",
        mode="analysis_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Runs one profile-aware dry-run buy simulation and writes simulation logs only.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_dry_run_auto_buy_recent_lookup",
        display_name="Strategy Dry-Run Auto Buy Recent",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only lookup for recent profile-aware dry-run auto-buy results.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_dry_run_auto_buy_summary_lookup",
        display_name="Strategy Dry-Run Auto Buy Summary",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only summary of profile-aware dry-run auto-buy results.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_live_auto_buy_readiness_lookup",
        display_name="Strategy Live Auto Buy Readiness",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only guarded live auto-buy readiness lookup. It never validates or submits orders.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_auto_buy_operations_status_lookup",
        display_name="Strategy Auto Buy Operations Status",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only operations status for dry-run evidence, guarded live readiness, attempts, and next operator action.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_auto_buy_scheduler_status_lookup",
        display_name="Strategy Auto Buy Scheduler Status",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only PR78 scheduled dry-run auto-buy status lookup. It never validates or submits orders.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_auto_buy_promotions_lookup",
        display_name="Strategy Auto Buy Promotions Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only promotion queue lookup for scheduler dry-run would_buy candidates. It never submits orders.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_live_auto_buy_recent_lookup",
        display_name="Strategy Live Auto Buy Recent",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only lookup for recent guarded live auto-buy attempts.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_live_auto_exit_readiness_lookup",
        display_name="Strategy Live Auto Exit Readiness",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only guarded live auto-exit readiness lookup. It never validates or submits orders.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_live_auto_exit_recent_lookup",
        display_name="Strategy Live Auto Exit Recent",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only lookup for recent guarded live auto-exit attempts.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_exit_candidate_lookup",
        display_name="Strategy Exit Candidate Lookup",
        mode="read_only",
        risk_level="low",
        allowed_auto_execute=True,
        provider="kis",
        market="KR",
        description="Read-only held-position exit candidate lookup. It never validates or submits orders.",
    ),
    AgentChatToolDefinition(
        tool_name="strategy_profile_change_prepare",
        display_name="Strategy Profile Change Prepare",
        mode="prefill_only",
        risk_level="medium",
        allowed_auto_execute=False,
        requires_manual_confirm=True,
        description="Creates a pending confirmation action for strategy profile changes. It never trades.",
    ),
    AgentChatToolDefinition(
        tool_name="watchlist_preview",
        display_name="Watchlist Preview",
        mode="analysis_only",
        risk_level="medium",
        allowed_auto_execute=True,
        description="Analysis-only watchlist preview. It never submits broker orders.",
    ),
    AgentChatToolDefinition(
        tool_name="safe_symbol_analysis",
        display_name="Safe Symbol Analysis",
        mode="analysis_only",
        risk_level="medium",
        allowed_auto_execute=True,
        description="Safe analysis-only single-symbol review. It never submits broker orders.",
    ),
    AgentChatToolDefinition(
        tool_name="manual_ticket_prefill",
        display_name="Manual Ticket Prefill",
        mode="prefill_only",
        risk_level="high",
        allowed_auto_execute=False,
        requires_manual_confirm=True,
        description="Manual order ticket prefill only. Validation and submit stay manual.",
    ),
    AgentChatToolDefinition(
        tool_name="live_order_request_blocker",
        display_name="Live Order Request Blocker",
        mode="blocked",
        risk_level="critical",
        allowed_auto_execute=False,
        requires_auth=True,
        requires_manual_confirm=True,
        description="Blocks chat-originated live order requests.",
    ),
    AgentChatToolDefinition(
        tool_name="settings_change_blocker",
        display_name="Settings Change Blocker",
        mode="blocked",
        risk_level="high",
        allowed_auto_execute=False,
        requires_auth=True,
        requires_manual_confirm=True,
        description="Blocks chat-originated runtime setting mutations.",
    ),
]

_AUTO_MODES = {"read_only", "analysis_only"}
