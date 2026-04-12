class QuantSignalService:
    def score(self, indicators: dict) -> dict:
        if not indicators:
            return {"quant_buy_score": 0.0, "quant_sell_score": 0.0, "quant_reason": "insufficient data"}

        buy = 0.0
        sell = 0.0
        reasons: list[str] = []

        if indicators["ema20"] > indicators["ema50"]:
            buy += 0.20
            reasons.append("EMA20>EMA50 uptrend")
        else:
            sell += 0.20
            reasons.append("EMA20<=EMA50 down/range")

        if indicators["price"] > indicators["vwap"]:
            buy += 0.15
            reasons.append("price above VWAP")
        else:
            sell += 0.15
            reasons.append("price below VWAP")

        rsi = indicators["rsi"]
        if 45 <= rsi <= 65:
            buy += 0.10
            reasons.append("RSI healthy for continuation")
        elif rsi >= 75:
            sell += 0.10
            reasons.append("RSI overbought")
        elif rsi <= 30:
            buy += 0.05
            reasons.append("RSI oversold bounce candidate")

        if indicators["volume_ratio"] >= 1.1:
            buy += 0.10
            reasons.append("volume confirmation")

        if indicators["short_momentum"] > 0.001:
            buy += 0.15
            reasons.append("short momentum positive")
        elif indicators["short_momentum"] < -0.001:
            sell += 0.15
            reasons.append("short momentum negative")

        if indicators["price"] > indicators["day_open"]:
            buy += 0.05
        else:
            sell += 0.05

        quant_buy = min(max(buy, 0.0), 1.0)
        quant_sell = min(max(sell, 0.0), 1.0)

        return {
            "quant_buy_score": quant_buy,
            "quant_sell_score": quant_sell,
            "quant_reason": "; ".join(reasons) or "neutral quant setup",
        }