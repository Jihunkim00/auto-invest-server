class AISignalService:
    def adjust(self, *, indicators: dict, quant_buy_score: float, quant_sell_score: float) -> dict:
        """AI layer refines scores but keeps quant as anchor."""
        if not indicators:
            return {"ai_buy_score": 0.0, "ai_sell_score": 0.0, "ai_reason": "ai skipped: insufficient indicators"}

        buy_delta = 0.0
        sell_delta = 0.0
        reason = []

        atr_ratio = indicators["atr"] / max(indicators["price"], 1e-9)
        if atr_ratio > 0.02:
            sell_delta += 10.0
            buy_delta -= 5.0
            reason.append("high volatility")

        if indicators["price"] < indicators["previous_low"] * 1.002:
            sell_delta += 8.0
            reason.append("near recent low support test")

        if indicators["price"] > indicators["previous_high"] * 0.998:
            buy_delta += 10.0
            reason.append("near breakout zone")

        if indicators["short_momentum"] > 0.002:
            buy_delta += 8.0
            reason.append("momentum acceleration")
        elif indicators["short_momentum"] < -0.002:
            sell_delta += 8.0
            reason.append("momentum deterioration")

        ai_buy = quant_buy_score + buy_delta - (sell_delta * 0.3)
        ai_sell = quant_sell_score + sell_delta - (buy_delta * 0.3)

        # Guardrail: AI should not overpower quant core.
        ai_buy = min(max(ai_buy, quant_buy_score - 15.0), quant_buy_score + 20.0)
        ai_sell = min(max(ai_sell, quant_sell_score - 15.0), quant_sell_score + 20.0)

        return {
            "ai_buy_score": round(min(max(ai_buy, 0.0), 100.0), 2),
            "ai_sell_score": round(min(max(ai_sell, 0.0), 100.0), 2),
            "ai_reason": "; ".join(reason) if reason else "ai neutral",
        }