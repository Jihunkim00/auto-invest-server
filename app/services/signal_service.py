import json

from sqlalchemy.orm import Session

from app.core.constants import (
    AI_WEIGHT,
    BUY_AI_MIN,
    BUY_FINAL_MIN,
    BUY_QUANT_MIN,
    DEFAULT_BARS_LIMIT,
    DEFAULT_TIMEFRAME,
    MIN_BUY_SELL_SPREAD,
    QUANT_WEIGHT,
    SELL_AI_MIN,
    SELL_FINAL_MIN,
    SELL_QUANT_MIN,
    SIGNAL_STATUS_CREATED,
    SIGNAL_STATUS_SKIPPED,
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
    def _resolve_action(*, market_entry_allowed: bool, quant_buy: float, quant_sell: float, ai_buy: float, ai_sell: float, final_buy: float, final_sell: float) -> tuple[str, float]:
        confidence = min(max(max(final_buy, final_sell) / 100.0, 0.0), 1.0)

        if not market_entry_allowed:
            return "hold", confidence

        buy_candidate = (
            quant_buy >= BUY_QUANT_MIN
            and ai_buy >= BUY_AI_MIN
            and final_buy >= BUY_FINAL_MIN
            and (final_buy - final_sell) >= MIN_BUY_SELL_SPREAD
        )
        sell_candidate = (
            quant_sell >= SELL_QUANT_MIN
            and ai_sell >= SELL_AI_MIN
            and final_sell >= SELL_FINAL_MIN
            and (final_sell - final_buy) >= MIN_BUY_SELL_SPREAD
        )

        if buy_candidate:
            return "buy", confidence
        if sell_candidate:
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

        final_buy = min(max((quant["quant_buy_score"] * QUANT_WEIGHT) + (ai["ai_buy_score"] * AI_WEIGHT), 0.0), 100.0)
        final_sell = min(max((quant["quant_sell_score"] * QUANT_WEIGHT) + (ai["ai_sell_score"] * AI_WEIGHT), 0.0), 100.0)

        action, confidence = self._resolve_action(
            market_entry_allowed=bool(market_analysis.entry_allowed),
            quant_buy=quant["quant_buy_score"],
            quant_sell=quant["quant_sell_score"],
            ai_buy=ai["ai_buy_score"],
            ai_sell=ai["ai_sell_score"],
            final_buy=final_buy,
            final_sell=final_sell,
        )

        is_hold = action == "hold"

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
            approved_by_risk=False if is_hold else None,
            related_order_id=None,
            signal_status=SIGNAL_STATUS_SKIPPED if is_hold else SIGNAL_STATUS_CREATED,
            trigger_source=trigger_source,
            timeframe=timeframe,
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)
        return signal
