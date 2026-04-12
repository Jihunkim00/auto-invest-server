import json

from sqlalchemy.orm import Session

from app.db.models import MarketAnalysis


class GPTMarketService:
    """
    Conservative market-entry gate.
    MVP uses deterministic logic with GPT-compatible output schema.
    """

    def analyze(self, symbol: str, indicators: dict) -> dict:
        if not indicators:
            return {
                "market_regime": "unknown",
                "entry_bias": "neutral",
                "entry_allowed": False,
                "market_confidence": 0.2,
                "risk_note": "insufficient indicator history",
                "macro_summary": "Data limited; defaulting to HOLD.",
            }

        trend_up = indicators["ema20"] > indicators["ema50"]
        momentum_ok = indicators["short_momentum"] > 0
        rsi_mid = 45 <= indicators["rsi"] <= 70

        allowed = bool(trend_up and momentum_ok and rsi_mid)

        regime = "trend" if abs(indicators["ema20"] - indicators["ema50"]) / max(indicators["price"], 1e-9) > 0.002 else "range"
        bias = "long" if trend_up else "neutral"
        confidence = 0.7 if allowed else 0.45

        return {
            "market_regime": regime,
            "entry_bias": bias,
            "entry_allowed": allowed,
            "market_confidence": confidence,
            "risk_note": "Conservative gate active; entry blocked unless trend+momentum align.",
            "macro_summary": "Macro/news intentionally down-weighted for quant-first MVP.",
        }

    def save_analysis(self, db: Session, symbol: str, payload: dict) -> MarketAnalysis:
        row = MarketAnalysis(
            symbol=symbol.upper(),
            market_regime=payload.get("market_regime"),
            entry_bias=payload.get("entry_bias"),
            entry_allowed=bool(payload.get("entry_allowed", False)),
            market_confidence=float(payload.get("market_confidence", 0) or 0),
            risk_note=payload.get("risk_note"),
            macro_summary=payload.get("macro_summary"),
            raw_payload=json.dumps(payload, ensure_ascii=False),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def run_and_save(self, db: Session, symbol: str, indicators: dict) -> MarketAnalysis:
        payload = self.analyze(symbol, indicators)
        return self.save_analysis(db, symbol, payload)