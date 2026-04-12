class AISignalService:
    def adjust(self, *, indicators: dict, quant_buy_score: float, quant_sell_score: float) -> dict:
        # Conservative: AI can only add small nudges; cannot dominate quant core.
        ai_buy = 0.0
        ai_sell = 0.0
        reason = []

        if not indicators:
            return {"ai_buy_score": 0.0, "ai_sell_score": 0.0, "ai_reason": "ai skipped: insufficient indicators"}

        atr_ratio = indicators["atr"] / max(indicators["price"], 1e-9)
        if atr_ratio > 0.02:
            ai_sell += 10.0
            reason.append("volatility high; reduce entry aggression")

        if indicators["price"] < indicators["previous_low"] * 1.002:
            ai_sell += 5.0
            reason.append("price near recent low")

        if indicators["price"] > indicators["previous_high"] * 0.998:
            ai_buy += 5.0
            reason.append("price near recent breakout zone")

        # Guardrail: weak quant remains weak.
        if quant_buy_score < 45.0:
            ai_buy = min(ai_buy, 4.0)
        if quant_sell_score < 45.0:
            ai_sell = min(ai_sell, 4.0)

        return {
            "ai_buy_score": round(min(ai_buy, 20.0), 2),
            "ai_sell_score": round(min(ai_sell, 20.0), 2),
            "ai_reason": "; ".join(reason) if reason else "ai neutral",
        }