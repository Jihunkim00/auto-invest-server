from app.core.constants import get_gate_profile


class QuantSignalService:
    def score(self, indicators: dict, gate_level: int | None = None) -> dict:
        profile = get_gate_profile(gate_level)

        if not indicators:
            return {
                "quant_buy_score": 0.0,
                "quant_sell_score": 0.0,
                "quant_reason": "insufficient data",
                "quant_notes": ["no indicators"],
            }

        buy = 0.0
        sell = 0.0
        reasons: list[str] = []
        notes: list[str] = []

        ema20 = indicators["ema20"]
        ema50 = indicators["ema50"]
        price = indicators["price"]
        vwap = indicators["vwap"]
        rsi = indicators["rsi"]
        volume_ratio = indicators["volume_ratio"]
        short_momentum = indicators["short_momentum"]
        day_open = indicators["day_open"]

        above_ema20 = price >= ema20
        above_ema50 = price >= ema50
        above_vwap = price >= vwap

        if ema20 > ema50:
            buy += 18.0
            reasons.append("EMA20>EMA50 uptrend")
        else:
            sell += 16.0
            reasons.append("EMA20<=EMA50 down/range")

        alignment_hits = sum([above_ema20, above_ema50, above_vwap])
        if alignment_hits == 3:
            buy += 15.0
            reasons.append("price aligned above EMA20/EMA50/VWAP")
        elif alignment_hits == 2:
            buy += 10.0
            sell += 3.0
            reasons.append("partial trend alignment")
        elif alignment_hits == 1:
            buy += 4.0
            sell += 7.0
            reasons.append("weak trend alignment")
        else:
            sell += 14.0
            reasons.append("price below EMA20/EMA50/VWAP")

        if profile.strict_alignment == "strict" and alignment_hits < 3:
            sell += 12.0
            notes.append("strict alignment penalty")
        elif profile.strict_alignment == "moderate" and alignment_hits == 0:
            sell += 7.0
            notes.append("moderate alignment penalty")
        elif profile.strict_alignment == "loose" and alignment_hits == 0:
            sell += 3.0
            notes.append("loose alignment penalty")

        if 45 <= rsi <= 65:
            buy += 10.0
            reasons.append("RSI healthy for continuation")
        elif rsi >= 75:
            sell += 10.0
            reasons.append("RSI overbought")
        elif rsi <= 30:
            if profile.allow_oversold_bounce:
                buy += 10.0
                reasons.append("RSI oversold bounce candidate")
            else:
                sell += 4.0
                reasons.append("oversold without bounce policy")

        if volume_ratio >= 1.1:
            buy += 10.0
            reasons.append("volume confirmation")
        elif volume_ratio < 0.9:
            sell += profile.weak_volume_penalty
            notes.append(f"weak volume penalty={profile.weak_volume_penalty:.1f}")

        if short_momentum > 0.001:
            buy += 14.0
            reasons.append("short momentum positive")
        elif short_momentum < -0.001:
            sell += 11.0
            reasons.append("short momentum negative")
            if profile.level >= 3 and short_momentum > -0.003:
                buy += 4.0
                notes.append("early_recovery_momentum_credit")
        else:
            notes.append("momentum flat")
            if profile.level >= 3:
                buy += 3.0

        if price > day_open:
            buy += 5.0
        else:
            sell += 5.0

        if profile.level >= 3 and alignment_hits >= 1 and rsi <= 42 and short_momentum > -0.003:
            buy += 4.0
            notes.append("testing_mode_recovery_setup_credit")

        quant_buy = min(max(buy, 0.0), 100.0)
        quant_sell = min(max(sell, 0.0), 100.0)

        return {
            "quant_buy_score": round(quant_buy, 2),
            "quant_sell_score": round(quant_sell, 2),
            "quant_reason": "; ".join(reasons) or "neutral quant setup",
            "quant_notes": notes,
        }