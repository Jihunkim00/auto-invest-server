import json

from sqlalchemy.orm import Session

from app.core.constants import (
    AI_WEIGHT,
    DEFAULT_BARS_LIMIT,
    DEFAULT_TIMEFRAME,
    FINAL_SCORE_ACTION_THRESHOLD,
    HOLD_SCORE_BAND,
    QUANT_WEIGHT,
    SIGNAL_STATUS_CREATED,
)
from app.db.models import SignalLog
from app.services.ai_signal_service import AISignalService
from app.services.gpt_market_service import GPTMarketService
from app.services.indicator_service import IndicatorService
from app.services.market_data_service import MarketDataService
from app.services.quant_signal_service import QuantSignalService


class SignalService:
    def __init__(self):
        self.market_data_service = MarketDataService()
        self.indicator_service = IndicatorService()
        self.gpt_market_service = GPTMarketService()
        self.quant_signal_service = QuantSignalService()
        self.ai_signal_service = AISignalService()

    @staticmethod
    def _resolve_action(final_buy: float, final_sell: float) -> tuple[str, float]:
        spread = final_buy - final_sell
        confidence = max(final_buy, final_sell)

        if abs(spread) < HOLD_SCORE_BAND:
            return "hold", confidence
        if final_buy >= FINAL_SCORE_ACTION_THRESHOLD and spread > 0:
            return "buy", confidence
        if final_sell >= FINAL_SCORE_ACTION_THRESHOLD and spread < 0:
            return "sell", confidence
        return "hold", confidence

    def run(self, db: Session, *, symbol: str, timeframe: str = DEFAULT_TIMEFRAME, trigger_source: str = "manual") -> SignalLog:
        symbol = symbol.upper()

        bars = self.market_data_service.get_recent_bars(symbol, limit=DEFAULT_BARS_LIMIT, timeframe=timeframe)
        indicators = self.indicator_service.calculate(bars)

        market_analysis = self.gpt_market_service.run_and_save(db, symbol, indicators)

        quant = self.quant_signal_service.score(indicators)
        ai = self.ai_signal_service.adjust(
            indicators=indicators,
            quant_buy_score=quant["quant_buy_score"],
            quant_sell_score=quant["quant_sell_score"],
        )

        final_buy = (quant["quant_buy_score"] * QUANT_WEIGHT) + (ai["ai_buy_score"] * AI_WEIGHT)
        final_sell = (quant["quant_sell_score"] * QUANT_WEIGHT) + (ai["ai_sell_score"] * AI_WEIGHT)

        action, confidence = self._resolve_action(final_buy, final_sell)

        if not market_analysis.entry_allowed and action == "buy":
            action = "hold"

        signal = SignalLog(
            symbol=symbol,
            action=action,
            buy_score=final_buy,
            sell_score=final_sell,
            confidence=confidence,
            reason=f"gpt_gate={market_analysis.entry_allowed}; quant+ai blended",
            indicator_payload=json.dumps(indicators, ensure_ascii=False),
            market_analysis_id=market_analysis.id,
            gpt_entry_allowed=market_analysis.entry_allowed,
            gpt_entry_bias=market_analysis.entry_bias,
            gpt_market_confidence=market_analysis.market_confidence,
            quant_buy_score=quant["quant_buy_score"],
            quant_sell_score=quant["quant_sell_score"],
            ai_buy_score=ai["ai_buy_score"],
            ai_sell_score=ai["ai_sell_score"],
            final_buy_score=final_buy,
            final_sell_score=final_sell,
            quant_reason=quant["quant_reason"],
            ai_reason=ai["ai_reason"],
            risk_flags=json.dumps([], ensure_ascii=False),
            approved_by_risk=None,
            signal_status=SIGNAL_STATUS_CREATED,
            trigger_source=trigger_source,
            timeframe=timeframe,
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)
        return signal