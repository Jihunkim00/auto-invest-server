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
                "\uc774 \uc885\ubaa9\uc744 \uac04\ub2e8\ud788 \ubd84\uc11d\ud574\uc904\uae4c\uc694?",
                "\ubcf4\uc720 \uc911\uc778\uc9c0 \ud655\uc778\ud574\uc904\uae4c\uc694?",
            ]
        if any(result.result_type == "positions" and result.status == "success" for result in tool_results):
            return [
                "\uccab \ubc88\uc9f8 \uc885\ubaa9\uc744 \ubd84\uc11d\ud574\uc904\uae4c\uc694?",
                "\ucd5c\uadfc \uc8fc\ubb38 \ub0b4\uc5ed\ub3c4 \ubcf4\uc5ec\ub4dc\ub9b4\uae4c\uc694?",
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
                f"{name}\ub294 {symbol}\ub85c \uc870\ud68c\ud588\uc2b5\ub2c8\ub2e4. "
                f"\ud604\uc7ac\uac00\ub294 {formatted}\uc785\ub2c8\ub2e4. "
                f"{provider} read-only \uc870\ud68c\ub9cc \uc218\ud589\ud588\uace0 \uc8fc\ubb38\uc740 \uc2e4\ud589\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4."
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
        detail = f" \uc8fc\uc694 \ubcf4\uc720: {', '.join(samples)}." if samples else ""
        return AgentChatAnswer(
            text=f"\ud604\uc7ac \uc870\ud68c\ub41c \ubcf4\uc720\uc885\ubaa9\uc740 {count}\uac1c\uc785\ub2c8\ub2e4.{detail} \uc870\ud68c\ub9cc \uc218\ud589\ud588\uace0 \uc8fc\ubb38\uc740 \uc2e4\ud589\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.",
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
                f"scheduler\ub294 {scheduler}\uc785\ub2c8\ub2e4. \uc124\uc815\uc740 \uc870\ud68c\ub9cc \ud588\uace0 \ubcc0\uacbd\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4."
            ),
            answer_type="read_only_result",
        )

    def _analysis_answer(self, intent: AgentChatIntent, result: AgentChatToolResult) -> AgentChatAnswer:
        analysis = result.data.get("analysis") if isinstance(result.data.get("analysis"), dict) else {}
        symbol = analysis.get("symbol") or intent.symbol or "\uc774 \uc885\ubaa9"
        action = str(analysis.get("action") or "hold").upper()
        return AgentChatAnswer(
            text=(
                f"{symbol} \ubd84\uc11d \uc694\uccad\uc73c\ub85c \uc774\ud574\ud588\uc2b5\ub2c8\ub2e4. "
                f"\uc548\uc804 \ubd84\uc11d\ub9cc \uc218\ud589\ud588\uace0 \uc8fc\ubb38\uc740 \uc81c\ucd9c\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4. "
                f"\ud604\uc7ac \uc790\ub3d9 \ud310\ub2e8\uc740 {action}\uc5d0 \uac00\uae5d\uc2b5\ub2c8\ub2e4."
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
        return AgentChatResultCard(
            card_type="price",
            title=f"{name} \ud604\uc7ac\uac00",
            subtitle=" · ".join(item for item in [symbol, provider] if item),
            primary_value=self._money(price.get("price", price.get("current_price")), currency),
            badges=["READ ONLY", provider or "DATA", "NO ORDER"],
            data=price,
        )

    def _positions_card(self, result: AgentChatToolResult) -> AgentChatResultCard:
        positions = result.data.get("positions") if isinstance(result.data.get("positions"), list) else []
        rows = []
        for item in positions[:5]:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "label": item.get("name") or item.get("symbol") or "\uc885\ubaa9",
                    "value": item.get("qty") or item.get("quantity") or "-",
                }
            )
        return AgentChatResultCard(
            card_type="positions",
            title="KIS \ubcf4\uc720\uc885\ubaa9",
            primary_value=f"{result.data.get('count', len(positions))}\uac1c \uc885\ubaa9",
            badges=["READ ONLY", "NO ORDER"],
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
        ]
        return AgentChatResultCard(
            card_type="settings",
            title="Safety Status",
            badges=["READ ONLY", "NO CHANGE"],
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
            badges=["ANALYSIS ONLY", "NO ORDER"],
            data=analysis,
        )

    def _money(self, value: Any, currency: str | None) -> str:
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
