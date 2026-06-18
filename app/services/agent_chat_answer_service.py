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
                    "저는 Auto Invest의 읽기 전용 조회, 최근 주문/실행 로그 요약, "
                    "보유종목/잔고 확인, 안전한 분석 계획 생성, 수동 주문 티켓 준비를 도와줄 수 있습니다. "
                    "채팅에서는 주문을 실행하지 않고 validation도 자동 호출하지 않습니다."
                ),
                answer_type="general_answer",
            )

        if category == AgentChatIntentCategory.GENERAL_CHAT:
            return AgentChatAnswer(
                text=(
                    "Auto Invest 범위 안에서 질문해 주세요. 예: 현재가 조회, 보유종목 조회, "
                    "최근 주문 기록, 안전한 종목 분석, 수동 주문 티켓 준비를 처리할 수 있습니다. "
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

        if category == AgentChatIntentCategory.ANALYSIS_REQUEST:
            return self._analysis_answer(intent, plan=plan, run=run, data=data)

        if category == AgentChatIntentCategory.MANUAL_TICKET_REQUEST:
            return self._manual_ticket_answer(plan=plan, available_actions=available_actions)

        if category == AgentChatIntentCategory.LIVE_ORDER_REQUEST:
            return self._live_order_block_answer(plan=plan, available_actions=available_actions)

        if category == AgentChatIntentCategory.DANGEROUS_SETTING_REQUEST:
            return AgentChatAnswer(
                text=(
                    "이 요청은 위험 설정 변경으로 분류했습니다. 채팅에서는 dry_run, kill_switch, "
                    "auto buy 같은 런타임 설정을 직접 변경하지 않습니다. 별도 인증/승인 흐름에서만 "
                    "검토해야 합니다. 주문은 실행하지 않았고 validation도 호출하지 않았습니다."
                ),
                answer_type="auth_required",
            )

        if category == AgentChatIntentCategory.SCHEDULER_REQUEST:
            return AgentChatAnswer(
                text=(
                    "스케줄러 관련 요청은 채팅에서 바로 live 스케줄이나 실주문을 만들지 않습니다. "
                    "읽기 전용 상태 확인이나 안전한 plan review 흐름으로만 연결할 수 있습니다. "
                    "설정은 변경하지 않았습니다."
                ),
                answer_type="blocked",
            )

        if category == AgentChatIntentCategory.NEEDS_CLARIFICATION:
            return AgentChatAnswer(
                text=(
                    "요청을 안전하게 처리하려면 종목, 시장, 매수/매도 방향, 금액 또는 수량을 더 구체적으로 알려주세요. "
                    "주문은 실행하지 않았습니다."
                ),
                answer_type="unsupported",
            )

        return AgentChatAnswer(
            text=(
                "현재 이 요청은 Auto Invest 채팅에서 지원하지 않는 범위입니다. "
                "지원 범위는 주식 가격/보유종목/잔고/주문 기록 조회, 안전한 분석, 수동 주문 티켓 준비입니다. "
                "주문은 실행하지 않았습니다."
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
                    "주문은 실행하지 않았고 validation도 호출하지 않았습니다."
                ),
                answer_type="error",
            )
        value = price.get("price", price.get("current_price"))
        currency = price.get("currency") or ("KRW" if intent.market == "KR" else "USD")
        formatted = self._money(value, currency)
        return AgentChatAnswer(
            text=(
                f"{name}는 {symbol}로 조회됩니다. 현재가는 {formatted}입니다. "
                f"이 조회는 {provider} read-only 경로 기준이며 주문은 실행하지 않았습니다."
            ),
            answer_type="read_only_result",
        )

    def _positions_answer(self, data: dict[str, Any]) -> AgentChatAnswer:
        if data.get("error"):
            return AgentChatAnswer(
                text=f"보유종목 조회에 실패했습니다. 사유: {data['error']}. 주문은 실행하지 않았습니다.",
                answer_type="error",
            )
        positions = data.get("positions") if isinstance(data.get("positions"), list) else []
        count = int(data.get("count", len(positions)) or 0)
        if count == 0:
            return AgentChatAnswer(
                text="현재 조회된 보유종목이 없습니다. 이 조회는 read-only이며 주문은 실행하지 않았습니다.",
                answer_type="read_only_result",
            )
        samples = []
        for item in positions[:3]:
            if not isinstance(item, dict):
                continue
            label = item.get("name") or item.get("symbol") or "종목"
            qty = item.get("qty") or item.get("quantity")
            samples.append(f"{label} {qty}주" if qty is not None else str(label))
        suffix = f" 주요 보유: {', '.join(samples)}." if samples else ""
        return AgentChatAnswer(
            text=f"현재 조회된 보유종목은 {count}개입니다.{suffix} 주문은 실행하지 않았습니다.",
            answer_type="read_only_result",
        )

    def _balance_answer(self, data: dict[str, Any]) -> AgentChatAnswer:
        if data.get("error"):
            return AgentChatAnswer(
                text=f"잔고 조회에 실패했습니다. 사유: {data['error']}. 주문은 실행하지 않았습니다.",
                answer_type="error",
            )
        balance = data.get("balance") if isinstance(data.get("balance"), dict) else data
        cash = balance.get("cash")
        total = balance.get("total_asset_value")
        currency = balance.get("currency") or "KRW"
        parts = []
        if cash is not None:
            parts.append(f"현금 {self._money(cash, currency)}")
        if total is not None:
            parts.append(f"총자산 {self._money(total, currency)}")
        summary = ", ".join(parts) if parts else "잔고 요약을 가져왔습니다"
        return AgentChatAnswer(
            text=f"{summary}. 이 조회는 read-only이며 주문은 실행하지 않았습니다.",
            answer_type="read_only_result",
        )

    def _orders_answer(self, data: dict[str, Any]) -> AgentChatAnswer:
        orders = data.get("orders") if isinstance(data.get("orders"), list) else []
        count = int(data.get("count", len(orders)) or 0)
        if count == 0:
            return AgentChatAnswer(
                text="최근 주문 기록이 없습니다. 이 조회는 read-only이며 주문은 실행하지 않았습니다.",
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
            text=f"최근 주문 기록 {count}건을 찾았습니다.{detail} 주문은 실행하지 않았습니다.",
            answer_type="read_only_result",
        )

    def _runs_answer(self, data: dict[str, Any]) -> AgentChatAnswer:
        runs = data.get("runs") if isinstance(data.get("runs"), list) else []
        count = int(data.get("count", len(runs)) or 0)
        if count == 0:
            return AgentChatAnswer(
                text="최근 실행 로그가 없습니다. 이 조회는 read-only이며 주문은 실행하지 않았습니다.",
                answer_type="read_only_result",
            )
        first = runs[0] if isinstance(runs[0], dict) else {}
        detail = ""
        if first:
            detail = f" 최신 실행은 {first.get('symbol', '종목')} / {first.get('result', '상태 미상')}입니다."
        return AgentChatAnswer(
            text=f"최근 실행 로그 {count}건을 찾았습니다.{detail} 주문은 실행하지 않았습니다.",
            answer_type="read_only_result",
        )

    def _signals_answer(self, data: dict[str, Any]) -> AgentChatAnswer:
        signals = data.get("signals") if isinstance(data.get("signals"), list) else []
        count = int(data.get("count", len(signals)) or 0)
        return AgentChatAnswer(
            text=f"최근 시그널 {count}건을 조회했습니다. 이 조회는 read-only이며 주문은 실행하지 않았습니다.",
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
                    f"{symbol} 분석 요청으로 이해했습니다. 안전한 분석 조회만 실행했고 주문은 제출하지 않았습니다. "
                    f"요약: {reason}"
                ),
                answer_type="analysis_summary",
            )
        if plan:
            return AgentChatAnswer(
                text=(
                    f"{symbol} 분석 요청으로 이해했습니다. 안전한 분석 plan을 만들었고 주문은 제출하지 않았습니다. "
                    "validation은 호출하지 않았고 confirm_live는 자동 체크하지 않았습니다."
                ),
                answer_type="analysis_summary",
            )
        return AgentChatAnswer(
            text=(
                f"{symbol} 분석 요청으로 이해했지만 현재 사용할 수 있는 분석 경로가 충분하지 않습니다. "
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
                "수동 주문 티켓을 준비하려면 종목과 매수/매도 방향, 금액 또는 수량이 필요합니다. "
                "주문은 실행하지 않았습니다."
            ),
            answer_type="unsupported",
        )

    def _live_order_block_answer(
        self,
        *,
        plan: dict[str, Any] | None,
        available_actions: list[str],
    ) -> AgentChatAnswer:
        extra = " 대신 수동 주문 티켓 검토 계획만 준비했습니다." if plan else " 대신 수동 주문 티켓 흐름으로만 준비할 수 있습니다."
        return AgentChatAnswer(
            text=(
                f"채팅에서는 실주문을 직접 제출할 수 없습니다.{extra} "
                "주문은 실행하지 않았고 validation은 호출하지 않았습니다. "
                "confirm_live는 자동 체크하지 않았습니다."
            ),
            answer_type="blocked",
        )

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
