from __future__ import annotations

from typing import Any

from app.schemas.agent_chat_orchestrator import AgentChatAnswer, AgentChatIntent
from app.schemas.agent_chat_tool import AgentChatResultCard, AgentChatToolResult


class AgentChatResultSummarizer:
    def summarize(
        self,
        *,
        intent: AgentChatIntent,
        tool_results: list[AgentChatToolResult],
        fallback_answer: AgentChatAnswer,
    ) -> dict[str, Any]:
        cards = self.result_cards(tool_results)
        suggestions = self.follow_up_suggestions(intent=intent, tool_results=tool_results)
        answer = self.answer_for_results(
            intent=intent,
            tool_results=tool_results,
            fallback_answer=fallback_answer,
        )
        return {
            "answer": answer,
            "result_cards": cards,
            "follow_up_suggestions": suggestions,
        }

    def answer_for_results(
        self,
        *,
        intent: AgentChatIntent,
        tool_results: list[AgentChatToolResult],
        fallback_answer: AgentChatAnswer,
    ) -> AgentChatAnswer:
        success = [result for result in tool_results if result.status == "success"]
        if success:
            primary = success[0]
            if primary.result_type == "price":
                return self._price_answer(intent, primary)
            if primary.result_type == "positions":
                return self._positions_answer(primary)
            if primary.result_type == "balance":
                return self._balance_answer(primary)
            if primary.result_type == "orders":
                return self._count_answer(primary, "\ucd5c\uadfc \uc8fc\ubb38", "read_only_result")
            if primary.result_type == "runs":
                return self._count_answer(primary, "\ucd5c\uadfc \uc2e4\ud589", "read_only_result")
            if primary.result_type == "signals":
                return self._count_answer(primary, "\ucd5c\uadfc \uc2e0\ud638", "read_only_result")
            if primary.result_type == "settings":
                return self._settings_answer(primary)
            if primary.result_type == "daily_ops_summary":
                return self._daily_ops_summary_answer(primary)
            if primary.result_type == "operator_alerts":
                return self._operator_alerts_answer(primary)
            if primary.result_type == "production_readiness":
                return self._production_readiness_answer(primary)
            if primary.result_type in {"strategy_profile", "strategy_profiles"}:
                return self._strategy_profile_answer(intent, primary)
            if primary.result_type == "strategy_monthly_progress":
                return self._strategy_monthly_progress_answer(primary)
            if primary.result_type == "strategy_risk_budget":
                return self._strategy_risk_budget_answer(primary)
            if primary.result_type == "strategy_daily_performance":
                return self._strategy_daily_performance_answer(primary)
            if primary.result_type in {
                "strategy_monthly_performance",
                "strategy_target_progress",
            }:
                return self._strategy_monthly_performance_answer(
                    intent,
                    primary,
                )
            if primary.result_type == "strategy_trade_performance":
                return self._strategy_trade_performance_answer(primary)
            if primary.result_type in {
                "strategy_risk_state",
                "strategy_entry_risk",
                "strategy_order_sizing",
            }:
                return self._strategy_risk_answer(primary)
            if primary.result_type in {
                "strategy_dry_run_auto_buy",
                "strategy_dry_run_auto_buy_recent",
                "strategy_dry_run_auto_buy_summary",
            }:
                return self._strategy_dry_run_auto_buy_answer(primary)
            if primary.result_type == "strategy_auto_buy_operations_status":
                return self._strategy_auto_buy_operations_answer(primary)
            if primary.result_type in {
                "strategy_auto_buy_scheduler_status",
                "strategy_auto_buy_promotions",
            }:
                return self._strategy_auto_buy_scheduler_answer(primary)
            if primary.result_type in {
                "strategy_live_auto_buy_readiness",
                "strategy_live_auto_buy_recent",
            }:
                return self._strategy_live_auto_buy_answer(primary)
            if primary.result_type in {
                "strategy_live_auto_exit_readiness",
                "strategy_live_auto_exit_recent",
            }:
                return self._strategy_live_auto_exit_answer(primary)
            if primary.result_type == "strategy_exit_candidate":
                return self._strategy_exit_candidate_answer(primary)
            if primary.result_type == "position_management_dry_run":
                return self._position_management_dry_run_answer(primary)
            if primary.result_type == "analysis":
                return self._analysis_answer(intent, primary)

        failed = [result for result in tool_results if result.status == "failed"]
        if failed:
            error = failed[0].error_message or failed[0].summary or "tool failed"
            return AgentChatAnswer(
                text=f"\uc694\uccad\ud55c \uc870\ud68c\ub97c \uc644\ub8cc\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4. \uc0ac\uc720: {error}. \uc8fc\ubb38\uc740 \uc2e4\ud589\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.",
                answer_type="error",
            )

        blocked = [result for result in tool_results if result.status == "blocked"]
        if blocked:
            return fallback_answer

        return fallback_answer

    def result_cards(self, tool_results: list[AgentChatToolResult]) -> list[AgentChatResultCard]:
        cards: list[AgentChatResultCard] = []
        for result in tool_results:
            if result.status != "success":
                continue
            if result.result_type == "price":
                card = self._price_card(result)
            elif result.result_type == "positions":
                card = self._positions_card(result)
            elif result.result_type == "balance":
                card = self._balance_card(result)
            elif result.result_type == "settings":
                card = self._settings_card(result)
            elif result.result_type == "daily_ops_summary":
                card = self._daily_ops_summary_card(result)
            elif result.result_type == "operator_alerts":
                card = self._operator_alerts_card(result)
            elif result.result_type == "production_readiness":
                card = self._production_readiness_card(result)
            elif result.result_type in {"orders", "runs", "signals"}:
                card = self._count_card(result)
            elif result.result_type in {
                "strategy_profile",
                "strategy_profiles",
                "strategy_monthly_progress",
                "strategy_risk_budget",
                "strategy_daily_performance",
                "strategy_monthly_performance",
                "strategy_target_progress",
                "strategy_trade_performance",
                "strategy_risk_state",
                "strategy_entry_risk",
                "strategy_order_sizing",
                "strategy_dry_run_auto_buy",
                "strategy_dry_run_auto_buy_recent",
                "strategy_dry_run_auto_buy_summary",
                "strategy_auto_buy_operations_status",
                "strategy_auto_buy_scheduler_status",
                "strategy_auto_buy_promotions",
                "strategy_live_auto_buy_readiness",
                "strategy_live_auto_buy_recent",
                "strategy_live_auto_exit_readiness",
                "strategy_live_auto_exit_recent",
            }:
                card = self._strategy_card(result)
            elif result.result_type == "strategy_exit_candidate":
                card = self._strategy_exit_candidate_card(result)
            elif result.result_type == "position_management_dry_run":
                card = self._position_management_dry_run_card(result)
            elif result.result_type == "analysis":
                card = self._analysis_card(result)
            else:
                card = None
            if card is not None:
                cards.append(card)
        return cards

    def follow_up_suggestions(
        self,
        *,
        intent: AgentChatIntent,
        tool_results: list[AgentChatToolResult],
    ) -> list[str]:
        if any(result.result_type == "price" and result.status == "success" for result in tool_results):
            return [
                "이 종목 분석해줘",
                "보유 여부 확인해줘",
                "최근 주문 기록 보여줘",
            ]
        if any(result.result_type == "positions" and result.status == "success" for result in tool_results):
            return [
                "첫 번째 종목 분석해줘",
                "최근 주문 기록 보여줘",
            ]
        if any(result.result_type == "analysis" and result.status == "success" for result in tool_results):
            return [
                "왜 HOLD인지 자세히 설명해줘",
                "수동 티켓만 준비해줘",
                "watchlist 다시 봐줘",
            ]
        if any(result.result_type.startswith("strategy_") and result.status == "success" for result in tool_results):
            return [
                "안정형으로 바꿔줘",
                "고수익형이랑 보통형 차이 알려줘",
                "이번 달 목표 진행률 알려줘",
            ]
        if intent.category.value == "live_order_request":
            return [
                "수동 티켓으로 준비해줘",
                "위험 조건 설명해줘",
            ]
        if intent.category.value in {"general_chat", "capability_question"}:
            return [
                "\uc0bc\uc131\uc804\uc790 \ud604\uc7ac\uac00 \uc54c\ub824\uc918",
                "\ub0b4 \ubcf4\uc720\uc885\ubaa9 \ubcf4\uc5ec\uc918",
            ]
        return []

    def _price_answer(self, intent: AgentChatIntent, result: AgentChatToolResult) -> AgentChatAnswer:
        price = result.data.get("price") if isinstance(result.data.get("price"), dict) else {}
        symbol = price.get("symbol") or intent.symbol or "\uc885\ubaa9"
        name = price.get("name") or intent.symbol_name or symbol
        provider = str(price.get("provider") or intent.provider or "read-only").upper()
        currency = price.get("currency") or ("KRW" if intent.market == "KR" else "USD")
        formatted = self._money(price.get("price", price.get("current_price")), currency)
        return AgentChatAnswer(
            text=(
                f"{name}({symbol})는 {provider} 기준 현재가가 {formatted}입니다. "
                "이 작업은 read-only 가격 조회만 수행했으며, "
                "주문·validation·confirm_live는 실행하지 않았습니다."
            ),
            answer_type="read_only_result",
        )

    def _positions_answer(self, result: AgentChatToolResult) -> AgentChatAnswer:
        positions = result.data.get("positions") if isinstance(result.data.get("positions"), list) else []
        count = int(result.data.get("count", len(positions)) or 0)
        samples = []
        for item in positions[:3]:
            if not isinstance(item, dict):
                continue
            label = item.get("name") or item.get("symbol") or "\uc885\ubaa9"
            qty = item.get("qty") or item.get("quantity")
            samples.append(f"{label} {qty}\uc8fc" if qty is not None else str(label))
        detail = f" {', '.join(samples)}를 보유 중입니다." if samples else ""
        provider = str(result.data.get("provider") or "KIS").upper()
        return AgentChatAnswer(
            text=(
                f"현재 {provider} 보유종목은 {count}개입니다.{detail} "
                "조회만 수행했으며 매도나 주문 검증은 실행하지 않았습니다."
            ),
            answer_type="read_only_result",
        )

    def _balance_answer(self, result: AgentChatToolResult) -> AgentChatAnswer:
        balance = result.data.get("balance") if isinstance(result.data.get("balance"), dict) else {}
        currency = balance.get("currency") or "KRW"
        parts = []
        if balance.get("cash") is not None:
            parts.append(f"\uc608\uc218\uae08 {self._money(balance.get('cash'), currency)}")
        if balance.get("total_asset_value") is not None:
            parts.append(f"\ucd1d\uc790\uc0b0 {self._money(balance.get('total_asset_value'), currency)}")
        summary = ", ".join(parts) if parts else "\uc794\uace0 \uc815\ubcf4\ub97c \uc870\ud68c\ud588\uc2b5\ub2c8\ub2e4"
        return AgentChatAnswer(
            text=f"{summary}. read-only \uc870\ud68c\ub9cc \uc218\ud589\ud588\uace0 \uc8fc\ubb38\uc740 \uc2e4\ud589\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.",
            answer_type="read_only_result",
        )

    def _count_answer(self, result: AgentChatToolResult, label: str, answer_type: str) -> AgentChatAnswer:
        count = int(result.data.get("count", 0) or 0)
        return AgentChatAnswer(
            text=f"{label} {count}\uac74\uc744 \uc870\ud68c\ud588\uc2b5\ub2c8\ub2e4. read-only \uc870\ud68c\ub9cc \uc218\ud589\ud588\uace0 \uc8fc\ubb38\uc740 \uc2e4\ud589\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.",
            answer_type=answer_type,
        )

    def _settings_answer(self, result: AgentChatToolResult) -> AgentChatAnswer:
        settings = result.data.get("settings") if isinstance(result.data.get("settings"), dict) else {}
        dry_run = self._on_off(settings.get("dry_run"))
        kill_switch = self._on_off(settings.get("kill_switch"))
        scheduler = self._on_off(settings.get("scheduler_enabled"))
        return AgentChatAnswer(
            text=(
                f"\ud604\uc7ac dry-run\uc740 {dry_run}, kill switch\ub294 {kill_switch}, "
                f"scheduler\ub294 {scheduler}\uc785\ub2c8\ub2e4. "
                "이 상태 정보는 조회만 수행했으며 설정을 변경하지 않았습니다."
            ),
            answer_type="read_only_result",
        )

    def _daily_ops_summary_answer(
        self,
        result: AgentChatToolResult,
    ) -> AgentChatAnswer:
        data = result.data
        trade = data.get("trade_activity") if isinstance(data.get("trade_activity"), dict) else {}
        pnl = data.get("pnl_summary") if isinstance(data.get("pnl_summary"), dict) else {}
        orders = data.get("order_summary") if isinstance(data.get("order_summary"), dict) else {}
        reconciliation = (
            data.get("reconciliation")
            if isinstance(data.get("reconciliation"), dict)
            else {}
        )
        currency = str(pnl.get("currency") or "KRW")
        text = (
            f"{data.get('date')} daily operations summary is "
            f"{reconciliation.get('status') or 'unknown'}. "
            f"Orders today: {orders.get('total_orders_today', 0)}, "
            f"sync required: {orders.get('sync_required_count', 0)}, "
            f"blocked attempts: {trade.get('blocked_attempt_count', 0)}, "
            f"realized P/L: {self._money(pnl.get('realized_pl'), currency)}. "
            "This lookup used local cached/log DB state only and did not sync, validate, retry, submit, trade, change settings, or run a scheduler."
        )
        return AgentChatAnswer(
            text=text,
            answer_type="read_only_result",
        )

    def _operator_alerts_answer(
        self,
        result: AgentChatToolResult,
    ) -> AgentChatAnswer:
        data = result.data
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        alerts = data.get("alerts") if isinstance(data.get("alerts"), list) else []
        first = alerts[0] if alerts and isinstance(alerts[0], dict) else {}
        text = (
            f"Operator alerts: {summary.get('active_alert_count', 0)} active, "
            f"{summary.get('critical_count', 0)} critical, "
            f"{summary.get('warning_count', 0)} warning, "
            f"{summary.get('sync_required_count', 0)} sync-required. "
        )
        if first:
            text += (
                f"Primary alert: {first.get('title') or first.get('reason_code')}; "
                f"next safe action: {first.get('next_safe_action') or 'review only'}. "
            )
        text += (
            "This lookup used local DB state only and did not sync, validate, "
            "submit, trade, change settings, or run a scheduler."
        )
        return AgentChatAnswer(
            text=text,
            answer_type="read_only_result",
        )

    def _production_readiness_answer(
        self,
        result: AgentChatToolResult,
    ) -> AgentChatAnswer:
        data = result.data
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        blockers = data.get("blocking_reasons") if isinstance(data.get("blocking_reasons"), list) else []
        actions = data.get("next_safe_actions") if isinstance(data.get("next_safe_actions"), list) else []
        blocker_text = ", ".join(str(item) for item in blockers[:3]) or "none"
        action_text = str(actions[0]) if actions else "Continue read-only review."
        text = (
            f"Production readiness is {data.get('overall_status') or 'unknown'} "
            f"with score {data.get('readiness_score', 0)}. "
            f"Checks: {summary.get('ready_count', 0)} ready, "
            f"{summary.get('warning_count', 0)} warning, "
            f"{summary.get('blocked_count', 0)} blocked, "
            f"{summary.get('unknown_count', 0)} unknown. "
            f"Primary blockers: {blocker_text}. "
            f"Next safe action: {action_text} "
            "This was a read-only readiness summary only."
        )
        return AgentChatAnswer(
            text=text,
            answer_type="read_only_result",
        )

    def _strategy_profile_answer(self, intent: AgentChatIntent, result: AgentChatToolResult) -> AgentChatAnswer:
        data = result.data
        profiles = data.get("profiles") if isinstance(data.get("profiles"), list) else []
        active = data.get("active_profile") if isinstance(data.get("active_profile"), dict) else {}
        requested = self._profile_from_list(profiles, getattr(intent, "requested_profile", None))
        if intent.category.value == "strategy_profile_compare":
            return AgentChatAnswer(
                text=(
                    "안정형은 월 1~2% 목표와 낮은 주문 비중, 보통형은 월 3~5% 목표와 중간 주문 비중, "
                    "고수익형은 월 5% 이상 목표와 더 공격적인 매수 기준을 사용합니다. "
                    "모든 프로필은 월간/일간 손실 한도와 kill switch를 우선합니다. 주문은 실행하지 않았습니다."
                ),
                answer_type="strategy_profile_answer",
            )
        if intent.category.value == "strategy_profile_recommendation":
            profile = requested or self._profile_from_list(profiles, "balanced") or active
            return AgentChatAnswer(
                text=(
                    f"{self._profile_label(profile)}을 추천합니다. 월 목표 범위는 {self._target_range(profile)}, "
                    f"월 최대 손실은 {self._pct(profile.get('monthly_max_loss_pct'))}, 1회 주문 한도는 "
                    f"{self._money(profile.get('max_order_notional_krw'))} 또는 총자산 "
                    f"{self._pct(profile.get('max_order_notional_pct'))}입니다. 주문은 실행하지 않았습니다."
                ),
                answer_type="strategy_profile_answer",
            )
        profile = requested or active
        return AgentChatAnswer(
            text=(
                f"현재 전략 프로필은 {self._profile_label(profile)}입니다. 월 목표 범위는 {self._target_range(profile)}, "
                f"월 손실 한도는 {self._pct(profile.get('monthly_max_loss_pct'))}, 일일 손실 한도는 "
                f"{self._pct(profile.get('daily_max_loss_pct'))}, 매수 기준 점수는 {profile.get('buy_score_threshold')}점입니다. "
                "조회만 수행했고 주문은 실행하지 않았습니다."
            ),
            answer_type="strategy_profile_answer",
        )

    def _strategy_monthly_progress_answer(self, result: AgentChatToolResult) -> AgentChatAnswer:
        data = result.data
        profile = data.get("active_profile") if isinstance(data.get("active_profile"), dict) else {}
        return AgentChatAnswer(
            text=(
                f"현재 {self._profile_label(profile)} 기준 월 목표 범위는 "
                f"{self._pct(data.get('target_min_pct'))}~{self._pct(data.get('target_max_pct'))}입니다. "
                f"PR70에서는 현재 월 수익률을 skeleton 값 {self._pct(data.get('current_month_return_pct'))}로 반환합니다. "
                "주문은 실행하지 않았습니다."
            ),
            answer_type="strategy_profile_answer",
        )

    def _strategy_risk_budget_answer(self, result: AgentChatToolResult) -> AgentChatAnswer:
        data = result.data
        profile = data.get("active_profile") if isinstance(data.get("active_profile"), dict) else {}
        return AgentChatAnswer(
            text=(
                f"현재 {self._profile_label(profile)} 리스크 예산은 월 손실 {self._pct(data.get('monthly_max_loss_pct'))}, "
                f"일일 손실 {self._pct(data.get('daily_max_loss_pct'))}, 1회 주문 한도 "
                f"{self._money(data.get('max_order_notional_krw'))} 또는 {self._pct(data.get('max_order_notional_pct'))}, "
                f"하루 최대 {data.get('max_trades_per_day')}회 거래입니다. 조회만 수행했고 주문은 실행하지 않았습니다."
            ),
            answer_type="strategy_profile_answer",
        )

    def _strategy_daily_performance_answer(
        self,
        result: AgentChatToolResult,
    ) -> AgentChatAnswer:
        data = result.data
        profile = data.get("active_profile") if isinstance(data.get("active_profile"), dict) else {}
        return AgentChatAnswer(
            text=(
                f"오늘 {self._profile_label(profile)} 기준 추정 손익은 "
                f"{self._money(data.get('net_pnl_estimated'))}입니다. "
                f"실현손익 {self._money(data.get('realized_pnl'))}, "
                f"평가손익 {self._money(data.get('unrealized_pnl'))}, "
                f"추정 수익률 {self._pct(data.get('pnl_pct'))}입니다. "
                "체결 수수료는 추정치이며 주문이나 validation은 실행하지 않았습니다."
            ),
            answer_type="strategy_performance_answer",
        )

    def _strategy_monthly_performance_answer(
        self,
        intent: AgentChatIntent,
        result: AgentChatToolResult,
    ) -> AgentChatAnswer:
        data = result.data
        profile = data.get("active_profile") if isinstance(data.get("active_profile"), dict) else {}
        current = self._number(data.get("current_month_return_pct"))
        minimum = self._number(data.get("monthly_target_min_pct"))
        remaining = max(minimum - current, 0.0)
        requested = getattr(intent, "requested_profile", None)
        basis_note = f" 요청한 {requested} 기준입니다." if requested else ""
        return AgentChatAnswer(
            text=(
                f"현재 활성 전략은 {self._profile_label(profile)}입니다. "
                f"월 목표는 {self._pct(data.get('monthly_target_min_pct'))}~"
                f"{self._pct(data.get('monthly_target_max_pct'))}이고, "
                f"현재 이번 달 추정 수익률은 {self._pct(current)}입니다. "
                f"최소 목표까지 {self._pct(remaining)}p 남았고 목표 진행률은 "
                f"{self._plain_pct(data.get('target_progress_pct'))}입니다. "
                f"월 손실 한도 사용률은 {self._plain_pct(data.get('loss_budget_used_pct'))}입니다."
                f"{basis_note} 실현손익과 평가손익을 합산한 추정값이며 주문은 실행하지 않았습니다."
            ),
            answer_type="strategy_performance_answer",
        )

    def _strategy_trade_performance_answer(
        self,
        result: AgentChatToolResult,
    ) -> AgentChatAnswer:
        items = result.data.get("items") if isinstance(result.data.get("items"), list) else []
        closed = [
            item for item in items
            if isinstance(item, dict) and item.get("realized_pnl") is not None
        ]
        if not closed:
            text = (
                "확정된 매수/매도 체결 쌍이 없어 실현손익을 계산하지 않았습니다. "
                "unmatched 또는 체결가 누락 주문은 임의 수익으로 처리하지 않습니다."
            )
        else:
            worst = min(closed, key=lambda item: float(item.get("realized_pnl") or 0))
            text = (
                f"최근 확정 거래 {len(closed)}건을 FIFO 방식으로 계산했습니다. "
                f"가장 큰 손실은 {worst.get('symbol')} "
                f"{self._money(worst.get('realized_pnl'))}입니다. "
                "이 조회는 read-only이며 주문을 실행하지 않았습니다."
            )
        return AgentChatAnswer(
            text=text,
            answer_type="strategy_performance_answer",
        )

    def _strategy_risk_answer(
        self,
        result: AgentChatToolResult,
    ) -> AgentChatAnswer:
        data = result.data
        profile = str(data.get("active_profile") or "safe")
        if result.result_type == "strategy_risk_state":
            allowed = bool(data.get("new_entries_allowed"))
            reason = data.get("primary_block_reason")
            suffix = (
                f" 주요 차단 사유는 {reason}입니다."
                if not allowed and reason
                else " 실제 주문은 종목별 buy score와 backend confirm gate를 통과해야 합니다."
            )
            text = (
                f"현재 활성 전략은 {profile}입니다. 이번 달 목표 진행률은 "
                f"{self._plain_pct(data.get('target_progress_pct'))}이고, "
                f"현재 신규 진입은 {'가능' if allowed else '차단'} 상태입니다.{suffix} "
                "조회만 수행했고 주문과 validation은 실행하지 않았습니다."
            )
        else:
            approved = bool(data.get("approved"))
            action = str(data.get("action") or "block")
            block_reason = data.get("block_reason")
            text = (
                f"현재 활성 전략은 {profile}입니다. 진입 평가는 "
                f"{'통과' if approved else '차단'}이며 action은 {action}입니다. "
                f"권장 주문금액은 {self._money(data.get('recommended_notional_krw'))}입니다."
            )
            if block_reason:
                text += f" 차단 사유는 {block_reason}입니다."
            text += " 이 평가는 read-only이며 주문과 validation을 실행하지 않았습니다."
        return AgentChatAnswer(
            text=text,
            answer_type="strategy_risk_answer",
        )

    def _strategy_dry_run_auto_buy_answer(
        self,
        result: AgentChatToolResult,
    ) -> AgentChatAnswer:
        data = result.data
        if result.result_type == "strategy_dry_run_auto_buy":
            profile = str(data.get("active_profile") or "safe")
            action = str(data.get("action") or "hold")
            symbol = str(data.get("selected_symbol") or "후보 없음")
            reason = str(data.get("reason") or "unknown")
            text = (
                f"{profile} 기준 dry-run 자동매수 판단 결과는 {action}입니다. "
                f"선택 후보는 {symbol}이고 사유는 {reason}입니다. "
                "주문은 제출되지 않았고 KIS validation과 broker submit도 호출하지 않았습니다."
            )
        elif result.result_type == "strategy_dry_run_auto_buy_recent":
            items = data.get("items") if isinstance(data.get("items"), list) else []
            latest = items[0] if items and isinstance(items[0], dict) else {}
            text = (
                f"최근 dry-run 자동매수 결과 {len(items)}건을 조회했습니다. "
                f"최신 결과는 {latest.get('selected_symbol') or '후보 없음'} / "
                f"{latest.get('action') or '없음'}입니다. 주문은 제출되지 않았습니다."
            )
        else:
            today = data.get("today") if isinstance(data.get("today"), dict) else {}
            text = (
                f"오늘 dry-run 자동매수는 총 {today.get('total', 0)}건이며 "
                f"would_buy {today.get('would_buy', 0)}건, "
                f"hold {today.get('hold', 0)}건, blocked {today.get('blocked', 0)}건입니다. "
                "모두 시뮬레이션이며 주문은 제출되지 않았습니다."
            )
        return AgentChatAnswer(
            text=text,
            answer_type="strategy_dry_run_auto_buy_answer",
        )

    def _strategy_live_auto_buy_answer(
        self,
        result: AgentChatToolResult,
    ) -> AgentChatAnswer:
        data = result.data
        if result.result_type == "strategy_live_auto_buy_recent":
            items = data.get("items") if isinstance(data.get("items"), list) else []
            latest = items[0] if items and isinstance(items[0], dict) else {}
            text = (
                f"Recent guarded live auto-buy attempts: {len(items)}. "
                f"Latest status is {latest.get('status') or 'none'} for "
                f"{latest.get('symbol') or latest.get('selected_symbol') or 'no symbol'}. "
                "This chat lookup did not validate or submit an order."
            )
        else:
            ready = bool(data.get("ready"))
            reason = data.get("primary_block_reason") or "none"
            profile = data.get("active_profile") or "unknown"
            symbol = data.get("selected_symbol") or "no recent dry-run symbol"
            text = (
                f"Guarded live auto-buy readiness is {'ready' if ready else 'blocked'} "
                f"for profile {profile}. Selected symbol: {symbol}. "
                f"Block reason: {reason}. Chat can only explain status; it cannot run live auto-buy."
            )
        return AgentChatAnswer(
            text=text,
            answer_type="strategy_live_auto_buy_answer",
        )

    def _strategy_auto_buy_operations_answer(
        self,
        result: AgentChatToolResult,
    ) -> AgentChatAnswer:
        data = result.data
        stage = str(data.get("auto_buy_stage") or "unknown")
        next_action = str(data.get("next_operator_action") or "no_action")
        readiness = data.get("live_readiness") if isinstance(data.get("live_readiness"), dict) else {}
        reason = readiness.get("primary_block_reason") or "none"
        text = (
            f"Auto-buy operations stage is {stage}. "
            f"Next operator action is {next_action}. "
            f"Primary block reason: {reason}. "
            "This chat lookup is read-only and did not run validation, submit, run-once, settings, or scheduler paths."
        )
        return AgentChatAnswer(
            text=text,
            answer_type="strategy_auto_buy_operations_answer",
        )

    def _strategy_auto_buy_scheduler_answer(
        self,
        result: AgentChatToolResult,
    ) -> AgentChatAnswer:
        data = result.data
        if result.result_type == "strategy_auto_buy_scheduler_status":
            enabled = self._on_off(data.get("enabled"))
            block = data.get("primary_block_reason") or "none"
            pending = data.get("pending_promotion_count", 0)
            return AgentChatAnswer(
                text=(
                    f"Scheduled dry-run auto-buy is {enabled}. "
                    f"Primary block reason: {block}. Pending promotions: {pending}. "
                    "PR78 scheduler discovery is dry-run only; no validation, broker submit, or live run-once ran from chat."
                ),
                answer_type="strategy_auto_buy_scheduler_answer",
            )
        items = data.get("items") if isinstance(data.get("items"), list) else []
        first = items[0] if items and isinstance(items[0], dict) else {}
        symbol = first.get("symbol") or "none"
        reason = first.get("promotion_reason") or first.get("block_reason") or "none"
        trace = first.get("trace_payload") if isinstance(first.get("trace_payload"), dict) else {}
        conversion = (
            first.get("conversion_status")
            or trace.get("conversion_status")
            or first.get("status")
            or "none"
        )
        sync = first.get("last_sync_status") or trace.get("last_sync_status") or "none"
        return AgentChatAnswer(
            text=(
                f"Promotion queue has {len(items)} visible candidate(s). "
                f"Latest candidate: {symbol}; reason: {reason}; "
                f"conversion: {conversion}; sync: {sync}. "
                "A promotion is not an order. Chat did not acknowledge, validate, submit, or run live auto-buy."
            ),
            answer_type="strategy_auto_buy_promotion_answer",
        )

    def _strategy_live_auto_exit_answer(
        self,
        result: AgentChatToolResult,
    ) -> AgentChatAnswer:
        data = result.data
        if result.result_type == "strategy_live_auto_exit_recent":
            items = data.get("items") if isinstance(data.get("items"), list) else []
            latest = items[0] if items and isinstance(items[0], dict) else {}
            text = (
                f"Recent guarded live auto-exit attempts: {len(items)}. "
                f"Latest status is {latest.get('status') or 'none'} for "
                f"{latest.get('symbol') or 'no symbol'}. "
                "This chat lookup did not validate or submit an order."
            )
        else:
            ready = bool(data.get("ready"))
            reason = data.get("primary_block_reason") or "none"
            profile = data.get("active_profile") or "unknown"
            selected = data.get("selected_symbol") or "no held-position candidate"
            candidate_count = data.get("candidate_count", 0)
            text = (
                f"Guarded live auto-exit readiness is {'ready' if ready else 'blocked'} "
                f"for profile {profile}. Selected symbol: {selected}. "
                f"Candidates: {candidate_count}. Block reason: {reason}. "
                "Chat can only explain status and candidates; it cannot run live auto-exit."
            )
        return AgentChatAnswer(
            text=text,
            answer_type="strategy_live_auto_exit_answer",
        )

    def _strategy_exit_candidate_answer(
        self,
        result: AgentChatToolResult,
    ) -> AgentChatAnswer:
        data = result.data
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        candidates = data.get("candidates") if isinstance(data.get("candidates"), list) else []
        first = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        text = (
            f"Auto exit candidates: {summary.get('candidate_count', len(candidates))}. "
            f"Critical: {summary.get('critical_count', 0)}, "
            f"warnings: {summary.get('warning_count', 0)}, "
            f"sync-required: {summary.get('sync_required_count', 0)}. "
        )
        if first:
            text += (
                f"Primary candidate: {first.get('symbol') or '-'} "
                f"{first.get('candidate_type') or 'review'}; "
                f"reason: {first.get('primary_reason') or '-'}; "
                f"next safe action: {first.get('next_safe_action') or 'review only'}. "
            )
        text += "This chat lookup did not run sell preflight or execute a sell order."
        return AgentChatAnswer(
            text=text,
            answer_type="strategy_exit_candidate_answer",
        )

    def _position_management_dry_run_answer(
        self,
        result: AgentChatToolResult,
    ) -> AgentChatAnswer:
        data = result.data
        text = (
            f"Position management dry-run status: {data.get('result_status') or 'unknown'}. "
            f"Positions checked: {data.get('positions_checked', 0)}, "
            f"exit candidates: {data.get('exit_candidate_count', 0)}, "
            f"critical: {data.get('critical_candidate_count', 0)}, "
            f"sync-required: {data.get('sync_required_count', 0)}. "
            f"Primary reason: {data.get('primary_reason') or 'none'}. "
            "This chat lookup did not start a dry-run, run guarded sell, or submit an order."
        )
        return AgentChatAnswer(
            text=text,
            answer_type="position_management_dry_run_answer",
        )

    def _analysis_answer(self, intent: AgentChatIntent, result: AgentChatToolResult) -> AgentChatAnswer:
        analysis = result.data.get("analysis") if isinstance(result.data.get("analysis"), dict) else {}
        symbol = analysis.get("symbol") or intent.symbol or "\uc774 \uc885\ubaa9"
        action = str(analysis.get("action") or "hold").upper()
        return AgentChatAnswer(
            text=(
                f"{symbol} 안전 분석만 수행했습니다. 주문은 제출하지 않았습니다. "
                f"현재 자동 판단은 {action}에 가깝습니다."
            ),
            answer_type="analysis_summary",
        )

    def _price_card(self, result: AgentChatToolResult) -> AgentChatResultCard | None:
        price = result.data.get("price") if isinstance(result.data.get("price"), dict) else {}
        if not price:
            return None
        symbol = str(price.get("symbol") or "").strip()
        name = str(price.get("name") or symbol or "\uc885\ubaa9").strip()
        provider = str(price.get("provider") or "").upper()
        currency = str(price.get("currency") or "").upper()
        rows = [
            {"label": "lookup", "value": "read-only lookup"},
            {"label": "order", "value": "no order submitted"},
        ]
        if price.get("timestamp"):
            rows.append({"label": "updated_at", "value": price.get("timestamp")})
        return AgentChatResultCard(
            card_type="price",
            title=f"{name} \ud604\uc7ac\uac00",
            subtitle=" · ".join(item for item in [symbol, provider] if item),
            primary_value=self._money(price.get("price", price.get("current_price")), currency),
            badges=["READ ONLY", provider or "DATA", "NO ORDER", "NO VALIDATION"],
            rows=rows,
            data=price,
        )

    def _positions_card(self, result: AgentChatToolResult) -> AgentChatResultCard:
        positions = result.data.get("positions") if isinstance(result.data.get("positions"), list) else []
        rows = []
        for item in positions[:5]:
            if not isinstance(item, dict):
                continue
            label = item.get("name") or item.get("symbol") or "\uc885\ubaa9"
            qty = item.get("qty") or item.get("quantity") or "-"
            details = [f"qty {qty}"]
            if item.get("market_value") is not None:
                details.append(f"value {item.get('market_value')}")
            if item.get("unrealized_pl") is not None:
                details.append(f"P/L {item.get('unrealized_pl')}")
            rows.append({"label": label, "value": " · ".join(details)})
        return AgentChatResultCard(
            card_type="positions",
            title="\ubcf4\uc720\uc885\ubaa9",
            subtitle=str(result.data.get("provider") or "KIS").upper(),
            primary_value=f"{result.data.get('count', len(positions))}\uac1c \uc885\ubaa9",
            badges=["READ ONLY", "NO ORDER", "NO VALIDATION"],
            rows=rows,
            data=result.data,
        )

    def _balance_card(self, result: AgentChatToolResult) -> AgentChatResultCard:
        balance = result.data.get("balance") if isinstance(result.data.get("balance"), dict) else {}
        currency = str(balance.get("currency") or "KRW")
        rows = []
        for key, label in (("cash", "\uc608\uc218\uae08"), ("total_asset_value", "\ucd1d\uc790\uc0b0")):
            if balance.get(key) is not None:
                rows.append({"label": label, "value": self._money(balance.get(key), currency)})
        return AgentChatResultCard(
            card_type="balance",
            title="Account Balance",
            primary_value=rows[0]["value"] if rows else None,
            badges=["READ ONLY", "NO ORDER"],
            rows=rows,
            data=balance,
        )

    def _settings_card(self, result: AgentChatToolResult) -> AgentChatResultCard:
        settings = result.data.get("settings") if isinstance(result.data.get("settings"), dict) else {}
        rows = [
            {"label": "dry_run", "value": self._on_off(settings.get("dry_run"))},
            {"label": "kill_switch", "value": self._on_off(settings.get("kill_switch"))},
            {"label": "scheduler_enabled", "value": self._on_off(settings.get("scheduler_enabled"))},
            {"label": "kis_real_order_enabled", "value": self._on_off(settings.get("kis_real_order_enabled"))},
            {"label": "kis_scheduler_enabled", "value": self._on_off(settings.get("kis_scheduler_enabled"))},
        ]
        return AgentChatResultCard(
            card_type="settings",
            title="System Status",
            badges=["READ ONLY", "NO SETTINGS CHANGE"],
            rows=rows,
            data=settings,
        )

    def _daily_ops_summary_card(self, result: AgentChatToolResult) -> AgentChatResultCard:
        data = result.data
        trade = data.get("trade_activity") if isinstance(data.get("trade_activity"), dict) else {}
        pnl = data.get("pnl_summary") if isinstance(data.get("pnl_summary"), dict) else {}
        orders = data.get("order_summary") if isinstance(data.get("order_summary"), dict) else {}
        promotions = data.get("promotion_summary") if isinstance(data.get("promotion_summary"), dict) else {}
        reconciliation = (
            data.get("reconciliation")
            if isinstance(data.get("reconciliation"), dict)
            else {}
        )
        currency = str(pnl.get("currency") or "KRW")
        return AgentChatResultCard(
            card_type="daily_ops_summary",
            title="Daily Operations Summary",
            subtitle=f"{str(data.get('provider') or '').upper()} / {data.get('market') or '-'} / {data.get('date') or '-'}",
            primary_value=str(reconciliation.get("status") or "UNKNOWN").upper(),
            badges=[
                "READ ONLY",
                "LOCAL DB ONLY",
                "NO SYNC",
                "NO VALIDATION",
                "NO BROKER SUBMIT",
                "NO SETTINGS CHANGE",
            ],
            rows=[
                {"label": "Orders today", "value": orders.get("total_orders_today", 0)},
                {"label": "Sync required", "value": orders.get("sync_required_count", 0)},
                {"label": "Realized P/L", "value": self._money(pnl.get("realized_pl"), currency)},
                {"label": "Unrealized P/L", "value": self._money(pnl.get("unrealized_pl"), currency)},
                {"label": "Promotions pending", "value": promotions.get("pending", 0)},
                {"label": "Blocked attempts", "value": trade.get("blocked_attempt_count", 0)},
            ],
            data=data,
        )

    def _operator_alerts_card(self, result: AgentChatToolResult) -> AgentChatResultCard:
        data = result.data
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        alerts = data.get("alerts") if isinstance(data.get("alerts"), list) else []
        first = alerts[0] if alerts and isinstance(alerts[0], dict) else {}
        return AgentChatResultCard(
            card_type="operator_alerts",
            title="Operator Alert Center",
            subtitle=f"{str(data.get('provider') or '').upper()} / {data.get('market') or '-'}",
            primary_value=str(summary.get("active_alert_count", 0)),
            badges=[
                "READ ONLY",
                "LOCAL DB ONLY",
                "NO SYNC",
                "NO VALIDATION",
                "NO BROKER SUBMIT",
                "NO SETTINGS CHANGE",
            ],
            rows=[
                {"label": "Critical", "value": summary.get("critical_count", 0)},
                {"label": "Warning", "value": summary.get("warning_count", 0)},
                {"label": "Sync required", "value": summary.get("sync_required_count", 0)},
                {"label": "Rejected orders", "value": summary.get("rejected_order_count", 0)},
                {"label": "Primary reason", "value": first.get("reason_code") or "-"},
                {"label": "Next safe action", "value": first.get("next_safe_action") or "-"},
            ],
            data=data,
        )

    def _production_readiness_card(self, result: AgentChatToolResult) -> AgentChatResultCard:
        data = result.data
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        return AgentChatResultCard(
            card_type="production_readiness",
            title="Production Readiness",
            subtitle=f"{str(data.get('provider') or '').upper()} / {data.get('market') or '-'}",
            primary_value=str(data.get("overall_status") or "unknown").upper(),
            badges=[
                "READ ONLY",
                "NO LIVE ORDERS",
                "AUTOMATION UNLOCK NOT ALLOWED",
            ],
            rows=[
                {"label": "Score", "value": data.get("readiness_score", 0)},
                {"label": "Blocked checks", "value": summary.get("blocked_count", 0)},
                {"label": "Warnings", "value": summary.get("warning_count", 0)},
                {"label": "Active alerts", "value": summary.get("active_alert_count", 0)},
                {"label": "Sync required", "value": summary.get("sync_required_alert_count", 0)},
                {"label": "Guarded buy", "value": summary.get("can_use_guarded_live_buy", False)},
                {"label": "Guarded sell", "value": summary.get("can_use_guarded_live_sell", False)},
            ],
            data={
                "overall_status": data.get("overall_status"),
                "readiness_score": data.get("readiness_score"),
                "summary": summary,
                "blocking_reasons": data.get("blocking_reasons") or [],
                "next_safe_actions": data.get("next_safe_actions") or [],
            },
        )

    def _count_card(self, result: AgentChatToolResult) -> AgentChatResultCard:
        title = {
            "orders": "Recent Orders",
            "runs": "Recent Runs",
            "signals": "Recent Signals",
        }.get(result.result_type, "Recent Activity")
        return AgentChatResultCard(
            card_type=result.result_type,
            title=title,
            primary_value=f"{result.data.get('count', 0)}",
            badges=["READ ONLY", "NO ORDER"],
            data=result.data,
        )

    def _analysis_card(self, result: AgentChatToolResult) -> AgentChatResultCard:
        analysis = result.data.get("analysis") if isinstance(result.data.get("analysis"), dict) else {}
        return AgentChatResultCard(
            card_type="analysis",
            title="Safe Analysis",
            primary_value=str(analysis.get("action") or "review").upper(),
            badges=["SAFE ANALYSIS", "NO ORDER", "NO VALIDATION"],
            data=analysis,
        )

    def _strategy_exit_candidate_card(
        self,
        result: AgentChatToolResult,
    ) -> AgentChatResultCard:
        data = result.data
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        candidates = data.get("candidates") if isinstance(data.get("candidates"), list) else []
        first = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        return AgentChatResultCard(
            card_type="strategy_exit_candidate",
            title="Auto Exit Candidates",
            subtitle=f"{str(data.get('provider') or 'kis').upper()} / {data.get('market') or 'KR'}",
            primary_value=str(summary.get("candidate_count", len(candidates))),
            badges=[
                "READ ONLY",
                "NO LIVE ORDERS",
                "NO BROKER SUBMIT",
                "PREFLIGHT HINT ONLY",
            ],
            rows=[
                {"label": "Critical", "value": summary.get("critical_count", 0)},
                {"label": "Warnings", "value": summary.get("warning_count", 0)},
                {"label": "Stop-loss", "value": summary.get("stop_loss_count", 0)},
                {"label": "Take-profit", "value": summary.get("take_profit_count", 0)},
                {"label": "Sync required", "value": summary.get("sync_required_count", 0)},
                {"label": "First symbol", "value": first.get("symbol") or "-"},
                {"label": "First reason", "value": first.get("primary_reason") or "-"},
            ],
            data=data,
        )

    def _position_management_dry_run_card(
        self,
        result: AgentChatToolResult,
    ) -> AgentChatResultCard:
        data = result.data
        actions = data.get("next_safe_actions") if isinstance(data.get("next_safe_actions"), list) else []
        return AgentChatResultCard(
            card_type="position_management_dry_run",
            title="Position Management Dry-Run",
            subtitle=f"{str(data.get('provider') or 'kis').upper()} / {data.get('market') or 'KR'}",
            primary_value=str(data.get("result_status") or "unknown").upper(),
            badges=[
                "DRY-RUN ONLY",
                "POSITIONS FIRST",
                "NO LIVE ORDERS",
                "NO BROKER SUBMIT",
                "NO SELL EXECUTION",
            ],
            rows=[
                {"label": "Positions checked", "value": data.get("positions_checked", 0)},
                {"label": "Exit candidates", "value": data.get("exit_candidate_count", 0)},
                {"label": "Critical", "value": data.get("critical_candidate_count", 0)},
                {"label": "Sync required", "value": data.get("sync_required_count", 0)},
                {"label": "Duplicate sells", "value": data.get("duplicate_sell_conflict_count", 0)},
                {"label": "Primary reason", "value": data.get("primary_reason") or "-"},
                {"label": "Next safe action", "value": actions[0] if actions else "-"},
            ],
            data=data,
        )

    def _strategy_card(self, result: AgentChatToolResult) -> AgentChatResultCard:
        data = result.data
        if result.result_type == "strategy_auto_buy_operations_status":
            dry_run = data.get("dry_run") if isinstance(data.get("dry_run"), dict) else {}
            readiness = data.get("live_readiness") if isinstance(data.get("live_readiness"), dict) else {}
            attempts = data.get("live_attempts") if isinstance(data.get("live_attempts"), dict) else {}
            stage = str(data.get("auto_buy_stage") or "unknown")
            badges = [
                "AUTO BUY OPS",
                "READ ONLY",
                "NO CHAT EXECUTION",
                "NO VALIDATION",
                "NO BROKER SUBMIT",
                "NO SCHEDULER",
                "NO AUTO RETRY",
            ]
            if dry_run.get("recent_found") is not True:
                badges.append("DRY RUN EVIDENCE REQUIRED")
            if readiness.get("target_risk_ready") is False:
                badges.append("TARGET RISK GATED")
            if readiness.get("ready") is True:
                badges.append("ONE SHOT LIVE BUY")
            return AgentChatResultCard(
                card_type="strategy_auto_buy_operations_status",
                title="Auto Buy Operations",
                subtitle=str(data.get("active_profile") or "KIS/KR").upper(),
                primary_value=stage.upper(),
                badges=badges,
                rows=[
                    {"label": "Next action", "value": data.get("next_operator_action") or "-"},
                    {"label": "Latest dry-run", "value": dry_run.get("latest_action") or "none"},
                    {"label": "Latest symbol", "value": dry_run.get("latest_symbol") or "-"},
                    {"label": "Block reason", "value": readiness.get("primary_block_reason") or "-"},
                    {"label": "Latest live attempt", "value": attempts.get("latest_status") or "none"},
                ],
                data=data,
            )
        if result.result_type == "strategy_auto_buy_scheduler_status":
            enabled = data.get("enabled") is True
            return AgentChatResultCard(
                card_type="strategy_auto_buy_scheduler_status",
                title="Scheduled Dry-Run Auto Buy",
                subtitle=str(data.get("active_profile") or "KIS/KR").upper(),
                primary_value="ENABLED" if enabled else "DISABLED",
                badges=[
                    "SCHEDULED DRY RUN",
                    "READ ONLY",
                    "NO LIVE SCHEDULER",
                    "NO VALIDATION",
                    "NO BROKER SUBMIT",
                    "OPERATOR CONFIRM REQUIRED",
                ],
                rows=[
                    {"label": "Runs today", "value": data.get("runs_today", 0)},
                    {"label": "Max runs", "value": data.get("max_runs_per_day", 0)},
                    {"label": "Next allowed", "value": data.get("next_allowed_run_at") or "-"},
                    {"label": "Block reason", "value": data.get("primary_block_reason") or "-"},
                    {"label": "Pending promotions", "value": data.get("pending_promotion_count", 0)},
                ],
                data=data,
            )
        if result.result_type == "strategy_auto_buy_promotions":
            items = data.get("items") if isinstance(data.get("items"), list) else []
            first = items[0] if items and isinstance(items[0], dict) else {}
            trace = first.get("trace_payload") if isinstance(first.get("trace_payload"), dict) else {}
            return AgentChatResultCard(
                card_type="strategy_auto_buy_promotions",
                title="Auto Buy Promotion Queue",
                subtitle=str(first.get("active_profile") or "KIS/KR").upper(),
                primary_value=str(first.get("symbol") or "NONE"),
                badges=[
                    "PROMOTION ONLY",
                    "READ ONLY",
                    "NO CHAT EXECUTION",
                    "NO VALIDATION",
                    "NO BROKER SUBMIT",
                    "REVIEW REQUIRED"
                    if first.get("review_required") is True
                    else "REVIEW STATUS",
                ],
                rows=[
                    {"label": "Visible candidates", "value": len(items)},
                    {"label": "Latest status", "value": first.get("status") or "none"},
                    {"label": "Review status", "value": first.get("review_status") or "-"},
                    {"label": "Reason", "value": first.get("promotion_reason") or "-"},
                    {
                        "label": "Score",
                        "value": (
                            (first.get("score_summary") or {}).get("label")
                            if isinstance(first.get("score_summary"), dict)
                            else first.get("final_score")
                            or first.get("buy_score")
                            or "-"
                        ),
                    },
                    {"label": "Expires", "value": first.get("expires_at") or "-"},
                    {"label": "Conversion block", "value": first.get("conversion_block_reason") or "-"},
                    {"label": "Live attempt", "value": first.get("converted_live_attempt_id") or first.get("promoted_to_live_attempt_id") or "-"},
                    {"label": "Order", "value": first.get("converted_order_id") or first.get("related_live_order_id") or "-"},
                    {"label": "Sync", "value": first.get("last_sync_status") or trace.get("last_sync_status") or "-"},
                ],
                data=data,
            )
        if result.result_type in {
            "strategy_live_auto_exit_readiness",
            "strategy_live_auto_exit_recent",
            "strategy_exit_candidate",
        }:
            if result.result_type == "strategy_live_auto_exit_recent":
                items = data.get("items") if isinstance(data.get("items"), list) else []
                card_data = items[0] if items and isinstance(items[0], dict) else {}
                primary = str(card_data.get("status") or "none").upper()
            else:
                card_data = data
                primary = "READY" if data.get("ready") is True else "BLOCKED"
            return AgentChatResultCard(
                card_type=result.result_type,
                title="Profile-Aware Guarded Live Auto Exit",
                subtitle=str(card_data.get("active_profile") or data.get("active_profile") or "KIS/KR").upper(),
                primary_value=primary,
                badges=[
                    "READ ONLY",
                    "LIVE AUTO EXIT",
                    "HELD POSITIONS ONLY",
                    "NO CHAT EXECUTION",
                    "NO VALIDATION",
                    "NO BROKER SUBMIT",
                ],
                rows=[
                    {"label": "Selected symbol", "value": card_data.get("selected_symbol") or card_data.get("symbol") or "-"},
                    {"label": "Selected trigger", "value": card_data.get("selected_trigger") or card_data.get("exit_trigger") or "-"},
                    {"label": "Block reason", "value": card_data.get("primary_block_reason") or card_data.get("block_reason") or "-"},
                    {"label": "Candidates", "value": card_data.get("candidate_count", "-")},
                    {"label": "Orders remaining", "value": card_data.get("orders_remaining_today", "-")},
                ],
                data=data,
            )
        if result.result_type in {
            "strategy_live_auto_buy_readiness",
            "strategy_live_auto_buy_recent",
        }:
            if result.result_type == "strategy_live_auto_buy_recent":
                items = data.get("items") if isinstance(data.get("items"), list) else []
                card_data = items[0] if items and isinstance(items[0], dict) else {}
                primary = str(card_data.get("status") or "none").upper()
            else:
                card_data = data
                primary = "READY" if data.get("ready") is True else "BLOCKED"
            return AgentChatResultCard(
                card_type=result.result_type,
                title="Profile-Aware Guarded Live Auto Buy",
                subtitle=str(card_data.get("active_profile") or data.get("active_profile") or "KIS/KR").upper(),
                primary_value=primary,
                badges=[
                    "READ ONLY",
                    "LIVE AUTO BUY",
                    "NO CHAT EXECUTION",
                    "NO VALIDATION",
                    "NO BROKER SUBMIT",
                ],
                rows=[
                    {"label": "Selected symbol", "value": card_data.get("selected_symbol") or card_data.get("symbol") or "-"},
                    {"label": "Block reason", "value": card_data.get("primary_block_reason") or card_data.get("block_reason") or "-"},
                    {"label": "Orders remaining", "value": card_data.get("orders_remaining_today", "-")},
                    {"label": "Recent dry-run found", "value": card_data.get("recent_dry_run_found", "-")},
                ],
                data=data,
            )
        if result.result_type in {
            "strategy_dry_run_auto_buy",
            "strategy_dry_run_auto_buy_recent",
            "strategy_dry_run_auto_buy_summary",
        }:
            card_data = data
            if result.result_type == "strategy_dry_run_auto_buy_recent":
                items = data.get("items") if isinstance(data.get("items"), list) else []
                card_data = items[0] if items and isinstance(items[0], dict) else {}
            action = str(card_data.get("action") or "summary").upper()
            return AgentChatResultCard(
                card_type=result.result_type,
                title="Profile-Aware Dry-Run Auto Buy",
                subtitle=str(card_data.get("active_profile") or "ALL").upper(),
                primary_value=action,
                badges=[
                    "DRY RUN ONLY",
                    "NO ORDER SUBMIT",
                    "NO VALIDATION",
                    "PROFILE AWARE",
                    "TARGET AWARE",
                    action,
                ],
                rows=[
                    {"label": "Selected symbol", "value": card_data.get("selected_symbol") or "-"},
                    {"label": "Reason", "value": card_data.get("reason") or "-"},
                    {"label": "Recommended notional", "value": self._money(card_data.get("recommended_notional_krw"))},
                    {"label": "Simulated quantity", "value": card_data.get("simulated_quantity") or 0},
                ],
                data=data,
            )
        if result.result_type in {
            "strategy_risk_state",
            "strategy_entry_risk",
            "strategy_order_sizing",
        }:
            allowed = bool(data.get("new_entries_allowed", data.get("approved", False)))
            flags = data.get("risk_flags") if isinstance(data.get("risk_flags"), list) else []
            badges = [
                "ENTRY ALLOWED" if allowed else "ENTRY BLOCKED",
                "PROFILE-AWARE",
                "READ ONLY",
                "NO ORDER SUBMIT",
            ]
            if any("size_reduced" in str(flag) or "capped" in str(flag) for flag in flags):
                badges.append("SIZE REDUCED")
            if data.get("target_hit") is True:
                badges.append("TARGET HIT")
            return AgentChatResultCard(
                card_type=result.result_type,
                title="Target-Aware Risk",
                subtitle=str(data.get("active_profile") or "").upper(),
                primary_value=(
                    self._money(data.get("recommended_notional_krw"))
                    if result.result_type != "strategy_risk_state"
                    else ("ENTRY ALLOWED" if allowed else "ENTRY BLOCKED")
                ),
                badges=badges,
                rows=[
                    {"label": "Block reason", "value": data.get("primary_block_reason") or data.get("block_reason") or "-"},
                    {"label": "Target progress", "value": self._plain_pct(data.get("target_progress_pct") or (data.get("monthly_progress") or {}).get("target_progress_pct"))},
                    {"label": "Daily return", "value": self._pct(data.get("current_daily_return_pct") or (data.get("daily_progress") or {}).get("current_daily_return_pct"))},
                    {"label": "Risk flags", "value": ", ".join(str(flag) for flag in flags) or "none"},
                ],
                data=data,
            )
        if result.result_type == "strategy_daily_performance":
            quality = data.get("data_quality") if isinstance(data.get("data_quality"), dict) else {}
            return AgentChatResultCard(
                card_type="strategy_daily_performance",
                title="Today P&L",
                subtitle=self._profile_label(data.get("active_profile") or {}),
                primary_value=self._money(data.get("net_pnl_estimated")),
                badges=["READ ONLY", "ESTIMATED", "NO ORDER", "NO VALIDATION"],
                rows=[
                    {"label": "Realized P&L", "value": self._money(data.get("realized_pnl"))},
                    {"label": "Unrealized P&L", "value": self._money(data.get("unrealized_pnl"))},
                    {"label": "Return", "value": self._pct(data.get("pnl_pct"))},
                    {"label": "Filled orders", "value": data.get("filled_orders_count")},
                    {"label": "Data quality", "value": ", ".join(quality.get("notes") or []) or "best effort"},
                ],
                data=data,
            )
        if result.result_type in {
            "strategy_monthly_performance",
            "strategy_target_progress",
        }:
            profile = data.get("active_profile") if isinstance(data.get("active_profile"), dict) else {}
            return AgentChatResultCard(
                card_type="strategy_monthly_performance",
                title="Strategy Monthly Progress",
                subtitle=self._profile_label(profile),
                primary_value=self._pct(data.get("current_month_return_pct")),
                badges=["READ ONLY", "ESTIMATED", "STRATEGY TARGET", "NO ORDER"],
                rows=[
                    {"label": "Target range", "value": self._target_range(profile)},
                    {"label": "Target progress", "value": self._plain_pct(data.get("target_progress_pct"))},
                    {"label": "Loss budget used", "value": self._plain_pct(data.get("loss_budget_used_pct"))},
                    {"label": "Target hit", "value": str(bool(data.get("target_hit")))},
                    {"label": "Loss limit hit", "value": str(bool(data.get("loss_limit_hit")))},
                ],
                data=data,
            )
        if result.result_type == "strategy_trade_performance":
            items = data.get("items") if isinstance(data.get("items"), list) else []
            rows = []
            for item in items[:5]:
                if not isinstance(item, dict):
                    continue
                pnl = item.get("realized_pnl")
                if pnl is None:
                    pnl = item.get("unrealized_pnl")
                rows.append({
                    "label": item.get("symbol") or "trade",
                    "value": f"{item.get('status')} · {self._money(pnl)}",
                })
            return AgentChatResultCard(
                card_type="strategy_trade_performance",
                title="Recent Trade Performance",
                primary_value=f"{data.get('count', len(items))}",
                badges=["READ ONLY", "FIFO ESTIMATED", "NO ORDER", "NO VALIDATION"],
                rows=rows,
                data=data,
            )
        if result.result_type == "strategy_monthly_progress":
            profile = data.get("active_profile") if isinstance(data.get("active_profile"), dict) else {}
            return AgentChatResultCard(
                card_type="strategy_profile",
                title="Strategy Monthly Progress",
                subtitle=self._profile_label(profile),
                primary_value=self._target_range(profile),
                badges=["PROFILE ONLY", "NO ORDER SUBMIT", "STRATEGY TARGET", str(profile.get("profile_name") or "").upper()],
                rows=[
                    {"label": "Current month return", "value": self._pct(data.get("current_month_return_pct"))},
                    {"label": "Target range", "value": self._target_range(profile)},
                    {"label": "Skeleton", "value": str(data.get("skeleton", True))},
                ],
                data=data,
            )
        if result.result_type == "strategy_risk_budget":
            profile = data.get("active_profile") if isinstance(data.get("active_profile"), dict) else {}
            return AgentChatResultCard(
                card_type="strategy_profile",
                title="Strategy Risk Budget",
                subtitle=self._profile_label(profile),
                primary_value=self._money(data.get("max_order_notional_krw")),
                badges=["PROFILE ONLY", "NO ORDER SUBMIT", "STRATEGY TARGET", str(profile.get("profile_name") or "").upper()],
                rows=[
                    {"label": "Monthly max loss", "value": self._pct(data.get("monthly_max_loss_pct"))},
                    {"label": "Daily max loss", "value": self._pct(data.get("daily_max_loss_pct"))},
                    {"label": "Trades per day", "value": data.get("max_trades_per_day")},
                    {"label": "Max positions", "value": data.get("max_positions")},
                ],
                data=data,
            )
        profiles = data.get("profiles") if isinstance(data.get("profiles"), list) else []
        profile = data.get("active_profile") if isinstance(data.get("active_profile"), dict) else {}
        if not profile and profiles:
            profile = profiles[0] if isinstance(profiles[0], dict) else {}
        return AgentChatResultCard(
            card_type="strategy_profile",
            title="Strategy Profile",
            subtitle=self._profile_label(profile),
            primary_value=self._target_range(profile),
            badges=["PROFILE ONLY", "NO ORDER SUBMIT", "STRATEGY TARGET", str(profile.get("profile_name") or "").upper()],
            rows=[
                {"label": "Monthly target", "value": self._target_range(profile)},
                {"label": "Monthly max loss", "value": self._pct(profile.get("monthly_max_loss_pct"))},
                {"label": "Daily max loss", "value": self._pct(profile.get("daily_max_loss_pct"))},
                {"label": "Order limit", "value": self._money(profile.get("max_order_notional_krw"))},
                {"label": "Buy score", "value": profile.get("buy_score_threshold")},
            ],
            data=data,
        )

    def _money(self, value: Any, currency: str | None = "KRW") -> str:
        try:
            number = float(value)
        except Exception:
            return "\uc870\ud68c\uac12 \uc5c6\uc74c"
        currency = str(currency or "").upper()
        if currency == "KRW":
            return f"\u20a9{number:,.0f}"
        if currency == "USD":
            return f"${number:,.2f}"
        return f"{number:,.2f}"

    def _number(self, value: Any) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0

    def _plain_pct(self, value: Any) -> str:
        return f"{self._number(value):.1f}%"

    def _on_off(self, value: Any) -> str:
        if value is True:
            return "ON"
        if value is False:
            return "OFF"
        return "UNKNOWN"

    def _profile_from_list(self, profiles: list[Any], profile_name: Any) -> dict[str, Any]:
        requested = str(profile_name or "").strip().lower()
        for item in profiles:
            if isinstance(item, dict) and str(item.get("profile_name") or "").lower() == requested:
                return item
        return {}

    def _profile_label(self, profile: dict[str, Any]) -> str:
        if not isinstance(profile, dict) or not profile:
            return "전략 프로필"
        display = str(profile.get("display_name") or "").strip()
        name = str(profile.get("profile_name") or "").strip()
        if display and name:
            return f"{display}({name})"
        return display or name or "전략 프로필"

    def _target_range(self, profile: dict[str, Any]) -> str:
        if not isinstance(profile, dict):
            return "-"
        return f"{self._pct(profile.get('monthly_target_min_pct'))}~{self._pct(profile.get('monthly_target_max_pct'))}"

    def _pct(self, value: Any) -> str:
        try:
            return f"{float(value) * 100:.1f}%"
        except Exception:
            return "-"
