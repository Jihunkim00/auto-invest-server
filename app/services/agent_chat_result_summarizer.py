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
            if primary.result_type in {"strategy_profile", "strategy_profiles"}:
                return self._strategy_profile_answer(intent, primary)
            if primary.result_type == "strategy_monthly_progress":
                return self._strategy_monthly_progress_answer(primary)
            if primary.result_type == "strategy_risk_budget":
                return self._strategy_risk_budget_answer(primary)
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
            elif result.result_type in {"orders", "runs", "signals"}:
                card = self._count_card(result)
            elif result.result_type in {
                "strategy_profile",
                "strategy_profiles",
                "strategy_monthly_progress",
                "strategy_risk_budget",
            }:
                card = self._strategy_card(result)
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

    def _strategy_card(self, result: AgentChatToolResult) -> AgentChatResultCard:
        data = result.data
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
