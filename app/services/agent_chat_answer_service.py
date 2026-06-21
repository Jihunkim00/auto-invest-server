from __future__ import annotations

from typing import Any

from app.schemas.agent_chat_orchestrator import (
    AgentChatAnswer,
    AgentChatIntent,
    AgentChatIntentCategory,
)


class AgentChatAnswerService:
    def compose(
        self,
        *,
        intent: AgentChatIntent,
        data: dict[str, Any] | None = None,
        plan: dict[str, Any] | None = None,
        run: dict[str, Any] | None = None,
        available_actions: list[str] | None = None,
    ) -> AgentChatAnswer:
        data = data or {}
        available_actions = available_actions or []
        category = intent.category

        if category == AgentChatIntentCategory.CAPABILITY_QUESTION:
            return AgentChatAnswer(
                text=(
                    "Auto Invest Agent Chat은 주식 현재가, 보유종목, 잔고, 최근 주문/실행 로그, "
                    "안전 분석, 수동 주문 티켓 준비를 도와줄 수 있습니다. "
                    "채팅에서는 주문·validation·confirm_live를 실행하지 않습니다."
                ),
                answer_type="general_answer",
            )

        if category == AgentChatIntentCategory.GENERAL_CHAT:
            return AgentChatAnswer(
                text=(
                    "Auto Invest 범위 안에서 질문해 주세요. 현재가 조회, 보유종목 조회, "
                    "최근 주문 기록, 안전 분석, 수동 주문 티켓 준비를 처리할 수 있습니다. "
                    "주문은 실행하지 않습니다."
                ),
                answer_type="general_answer",
            )

        if category == AgentChatIntentCategory.READ_ONLY_PRICE_QUERY:
            return self._price_answer(intent, data)

        if category == AgentChatIntentCategory.READ_ONLY_POSITIONS_QUERY:
            return self._positions_answer(data)

        if category == AgentChatIntentCategory.READ_ONLY_BALANCE_QUERY:
            return self._balance_answer(data)

        if category == AgentChatIntentCategory.READ_ONLY_ORDERS_QUERY:
            return self._orders_answer(data)

        if category == AgentChatIntentCategory.READ_ONLY_RUNS_QUERY:
            return self._runs_answer(data)

        if category == AgentChatIntentCategory.READ_ONLY_SIGNALS_QUERY:
            return self._signals_answer(data)

        if category == AgentChatIntentCategory.READ_ONLY_SETTINGS_QUERY:
            return self._settings_answer(data)

        if category == AgentChatIntentCategory.ANALYSIS_REQUEST:
            return self._analysis_answer(intent, plan=plan, run=run, data=data)

        if category == AgentChatIntentCategory.MANUAL_TICKET_REQUEST:
            return self._manual_ticket_answer(plan=plan, available_actions=available_actions)

        if category == AgentChatIntentCategory.LIVE_ORDER_REQUEST:
            return self._live_order_block_answer(
                intent=intent,
                data=data,
                plan=plan,
                available_actions=available_actions,
            )

        if category == AgentChatIntentCategory.DANGEROUS_SETTING_REQUEST:
            return AgentChatAnswer(
                text=(
                    "요청은 위험 설정 변경으로 분류했습니다. 채팅에서는 dry_run, kill_switch, "
                    "auto buy 같은 운영 설정을 변경하지 않습니다. "
                    "주문·validation·confirm_live도 실행하지 않습니다."
                ),
                answer_type="auth_required",
            )

        if category == AgentChatIntentCategory.SCHEDULER_REQUEST:
            return AgentChatAnswer(
                text=(
                    "스케줄러 관련 요청은 채팅에서 live 스케줄이나 실주문을 만들지 않습니다. "
                    "상태 조회나 안전한 plan review 흐름으로만 연결할 수 있으며 설정은 변경하지 않습니다."
                ),
                answer_type="blocked",
            )

        if category == AgentChatIntentCategory.NEEDS_CLARIFICATION:
            return AgentChatAnswer(
                text=(
                    "안전하게 처리하려면 종목, 시장, 매수/매도 방향, 금액 또는 수량을 더 구체적으로 알려주세요. "
                    "주문은 실행하지 않았습니다."
                ),
                answer_type="unsupported",
            )

        return AgentChatAnswer(
            text=(
                "현재 Auto Invest는 미국 주식 Alpaca paper와 한국 주식 KIS 중심으로 동작합니다. "
                "코인·선물·옵션·자동입출금은 지원하지 않습니다."
            ),
            answer_type="unsupported",
        )

    def _price_answer(self, intent: AgentChatIntent, data: dict[str, Any]) -> AgentChatAnswer:
        price = data.get("price") if isinstance(data.get("price"), dict) else {}
        error = data.get("error") or price.get("error")
        symbol = price.get("symbol") or intent.symbol or "해당 종목"
        name = price.get("name") or intent.symbol_name or symbol
        provider = str(price.get("provider") or intent.provider or "read-only").upper()
        if error:
            return AgentChatAnswer(
                text=(
                    f"{name}({symbol}) 현재가 조회에 실패했습니다. 사유: {error}. "
                    "주문·validation·confirm_live는 실행하지 않았습니다."
                ),
                answer_type="error",
            )
        value = price.get("price", price.get("current_price"))
        currency = price.get("currency") or ("KRW" if intent.market == "KR" else "USD")
        formatted = self._money(value, currency)
        return AgentChatAnswer(
            text=(
                f"{name}({symbol})는 {provider} 기준 현재가가 {formatted}입니다. "
                "이 작업은 read-only 가격 조회만 수행했으며, 주문·validation·confirm_live는 실행하지 않았습니다."
            ),
            answer_type="read_only_result",
        )

    def _positions_answer(self, data: dict[str, Any]) -> AgentChatAnswer:
        if data.get("error"):
            return AgentChatAnswer(
                text=(
                    f"보유종목 조회에 실패했습니다. 사유: {data['error']}. "
                    "주문·validation·confirm_live는 실행하지 않았습니다."
                ),
                answer_type="error",
            )
        positions = data.get("positions") if isinstance(data.get("positions"), list) else []
        count = int(data.get("count", len(positions)) or 0)
        provider = str(data.get("provider") or "KIS").upper()
        if count == 0:
            return AgentChatAnswer(
                text=(
                    f"현재 {provider} 보유종목은 없습니다. 조회만 수행했으며 "
                    "매도나 주문 검증은 실행하지 않았습니다."
                ),
                answer_type="read_only_result",
            )
        samples = []
        for item in positions[:3]:
            if not isinstance(item, dict):
                continue
            label = item.get("name") or item.get("symbol") or "종목"
            qty = item.get("qty") or item.get("quantity")
            samples.append(f"{label} {qty}주" if qty is not None else str(label))
        detail = f" {', '.join(samples)}를 보유 중입니다." if samples else ""
        return AgentChatAnswer(
            text=(
                f"현재 {provider} 보유종목은 {count}개입니다.{detail} "
                "조회만 수행했으며 매도나 주문 검증은 실행하지 않았습니다."
            ),
            answer_type="read_only_result",
        )

    def _balance_answer(self, data: dict[str, Any]) -> AgentChatAnswer:
        if data.get("error"):
            return AgentChatAnswer(
                text=(
                    f"잔고 조회에 실패했습니다. 사유: {data['error']}. "
                    "주문·validation·confirm_live는 실행하지 않았습니다."
                ),
                answer_type="error",
            )
        balance = data.get("balance") if isinstance(data.get("balance"), dict) else data
        currency = balance.get("currency") or "KRW"
        parts = []
        if balance.get("cash") is not None:
            parts.append(f"예수금 {self._money(balance.get('cash'), currency)}")
        if balance.get("total_asset_value") is not None:
            parts.append(f"총자산 {self._money(balance.get('total_asset_value'), currency)}")
        summary = ", ".join(parts) if parts else "잔고 정보를 조회했습니다"
        return AgentChatAnswer(
            text=(
                f"{summary}. read-only 조회만 수행했으며 "
                "주문·validation·confirm_live는 실행하지 않았습니다."
            ),
            answer_type="read_only_result",
        )

    def _orders_answer(self, data: dict[str, Any]) -> AgentChatAnswer:
        orders = data.get("orders") if isinstance(data.get("orders"), list) else []
        count = int(data.get("count", len(orders)) or 0)
        if count == 0:
            return AgentChatAnswer(
                text="최근 주문 기록은 없습니다. 조회만 수행했고 새 주문은 실행하지 않았습니다.",
                answer_type="read_only_result",
            )
        first = orders[0] if isinstance(orders[0], dict) else {}
        detail = ""
        if first:
            detail = (
                f" 최신 주문은 {first.get('symbol', '종목')} "
                f"{first.get('side', '')} / {first.get('internal_status') or first.get('status') or '상태 미상'}입니다."
            )
        return AgentChatAnswer(
            text=f"최근 주문 기록 {count}건을 조회했습니다.{detail} 새 주문은 실행하지 않았습니다.",
            answer_type="read_only_result",
        )

    def _runs_answer(self, data: dict[str, Any]) -> AgentChatAnswer:
        runs = data.get("runs") if isinstance(data.get("runs"), list) else []
        count = int(data.get("count", len(runs)) or 0)
        if count == 0:
            return AgentChatAnswer(
                text="최근 실행 로그는 없습니다. 조회만 수행했고 주문은 실행하지 않았습니다.",
                answer_type="read_only_result",
            )
        first = runs[0] if isinstance(runs[0], dict) else {}
        detail = ""
        if first:
            detail = f" 최신 실행은 {first.get('symbol', '종목')} / {first.get('result', '상태 미상')}입니다."
        return AgentChatAnswer(
            text=f"최근 실행 로그 {count}건을 조회했습니다.{detail} 주문은 실행하지 않았습니다.",
            answer_type="read_only_result",
        )

    def _signals_answer(self, data: dict[str, Any]) -> AgentChatAnswer:
        signals = data.get("signals") if isinstance(data.get("signals"), list) else []
        count = int(data.get("count", len(signals)) or 0)
        return AgentChatAnswer(
            text=f"최근 신호 {count}건을 조회했습니다. 조회만 수행했고 주문은 실행하지 않았습니다.",
            answer_type="read_only_result",
        )

    def _settings_answer(self, data: dict[str, Any]) -> AgentChatAnswer:
        settings = data.get("settings") if isinstance(data.get("settings"), dict) else {}
        dry_run = self._on_off(settings.get("dry_run"))
        kill_switch = self._on_off(settings.get("kill_switch"))
        scheduler = self._on_off(settings.get("scheduler_enabled"))
        return AgentChatAnswer(
            text=(
                f"현재 dry-run은 {dry_run}, kill switch는 {kill_switch}, scheduler는 {scheduler}입니다. "
                "이 상태 정보는 조회만 수행했으며 설정을 변경하지 않았습니다."
            ),
            answer_type="read_only_result",
        )

    def _analysis_answer(
        self,
        intent: AgentChatIntent,
        *,
        plan: dict[str, Any] | None,
        run: dict[str, Any] | None,
        data: dict[str, Any],
    ) -> AgentChatAnswer:
        if data.get("error"):
            return AgentChatAnswer(
                text=f"분석 요청 처리에 실패했습니다. 사유: {data['error']}. 주문은 실행하지 않았습니다.",
                answer_type="error",
            )
        symbol = intent.symbol or (plan or {}).get("symbol") or "해당 종목"
        result = run.get("result") if isinstance(run, dict) else {}
        latest = result.get("latest_analysis") if isinstance(result, dict) else None
        if isinstance(latest, dict) and latest:
            reason = latest.get("risk_note") or latest.get("reason") or "최근 분석 기록을 확인했습니다"
            return AgentChatAnswer(
                text=(
                    f"{symbol} 분석 요청으로 이해했습니다. 안전 분석만 수행했고 주문은 제출하지 않았습니다. "
                    f"요약: {reason}"
                ),
                answer_type="analysis_summary",
            )
        if plan:
            return AgentChatAnswer(
                text=(
                    f"{symbol} 안전 분석 plan을 만들었습니다. 주문·validation·confirm_live는 실행하지 않았습니다."
                ),
                answer_type="analysis_summary",
            )
        return AgentChatAnswer(
            text=(
                f"{symbol} 분석 요청으로 이해했지만 현재 사용할 수 있는 분석 결과가 충분하지 않습니다. "
                "주문은 실행하지 않았습니다."
            ),
            answer_type="analysis_summary",
        )

    def _manual_ticket_answer(
        self,
        *,
        plan: dict[str, Any] | None,
        available_actions: list[str],
    ) -> AgentChatAnswer:
        if plan:
            return AgentChatAnswer(
                text=(
                    "수동 주문 티켓 검토 계획을 준비했습니다. 주문은 실행하지 않았습니다. "
                    "Trading 화면에서 Validate와 confirm_live를 직접 진행해야 합니다."
                ),
                answer_type="manual_ticket_prepared",
            )
        return AgentChatAnswer(
            text=(
                "수동 주문 티켓을 준비하려면 종목, 매수/매도 방향, 금액 또는 수량이 필요합니다. "
                "주문은 실행하지 않았습니다."
            ),
            answer_type="unsupported",
        )

    def _live_order_block_answer(
        self,
        *,
        intent: AgentChatIntent,
        data: dict[str, Any],
        plan: dict[str, Any] | None,
        available_actions: list[str],
    ) -> AgentChatAnswer:
        action = data.get("live_order_action") if isinstance(data, dict) else None
        if isinstance(action, dict):
            symbol = action.get("symbol") or intent.symbol or "symbol"
            name = action.get("symbol_name") or intent.symbol_name or symbol
            side = str(action.get("side") or intent.side or "buy").upper()
            qty = action.get("quantity") or intent.quantity or 1
            notional = self._money(action.get("estimated_notional"), "KRW")
            return AgentChatAnswer(
                text=(
                    f"{name}({symbol}) {qty} share(s) {side} market order is ready for confirmation. "
                    f"Estimated notional is {notional}. Press Confirm Live Order to submit only after "
                    "backend validation and risk gates pass."
                ),
                answer_type="live_order_confirmation_required",
            )
        extra = (
            " 수동 주문 티켓 검토 계획까지만 준비했습니다."
            if plan
            else " 원하시면 수동 주문 티켓까지만 준비할 수 있습니다."
        )
        return AgentChatAnswer(
            text=(
                f"채팅에서는 실주문을 직접 제출할 수 없습니다.{extra} "
                "Trading 화면에서 Validate와 confirm_live를 직접 진행해야 합니다."
            ),
            answer_type="blocked",
        )

    def _on_off(self, value: Any) -> str:
        if value is True:
            return "ON"
        if value is False:
            return "OFF"
        return "UNKNOWN"

    def _money(self, value: Any, currency: str | None) -> str:
        try:
            number = float(value)
        except Exception:
            return "조회값 없음"
        currency = (currency or "").upper()
        if currency == "KRW":
            return f"₩{number:,.0f}"
        if currency == "USD":
            return f"${number:,.2f}"
        return f"{number:,.2f}"
