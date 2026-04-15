import json

from sqlalchemy.orm import Session

from app.core.constants import (
    AI_WEIGHT,
    DEFAULT_BARS_LIMIT,
    DEFAULT_TIMEFRAME,
    QUANT_WEIGHT,
    SIGNAL_STATUS_CREATED,
    SIGNAL_STATUS_SKIPPED,
    get_gate_profile,
    resolve_gate_level,
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
    def _resolve_action(
        *,
        market_entry_allowed: bool,
        regime: str,
        quant_buy: float,
        quant_sell: float,
        ai_buy: float,
        ai_sell: float,
        final_buy: float,
        final_sell: float,
        gate_level: int,
    ) -> tuple[str, float, list[str]]:
        profile = get_gate_profile(gate_level)
        notes: list[str] = []
        confidence = min(max(max(final_buy, final_sell) / 100.0, 0.0), 1.0)

        if not market_entry_allowed:
            notes.append("market_entry_not_allowed")
            return "hold", confidence, notes

        if regime == "range" and not profile.allow_neutral_regime_entry:
            notes.append("neutral_regime_blocked_by_profile")
            return "hold", confidence, notes

        if confidence < profile.min_confidence_to_trade:
            notes.append("confidence_below_profile_min")

        buy_candidate = (
            quant_buy >= (profile.min_buy_score - 5)
            and ai_buy >= (profile.min_buy_score - 8)
            and final_buy >= profile.min_buy_score
            and (final_buy - final_sell) >= profile.min_score_spread
            and confidence >= profile.min_confidence_to_trade
        )
        sell_candidate = (
            quant_sell >= (profile.min_sell_score - 5)
            and ai_sell >= (profile.min_sell_score - 8)
            and final_sell >= profile.min_sell_score
            and (final_sell - final_buy) >= profile.min_score_spread
            and confidence >= max(profile.min_confidence_to_trade - 0.04, 0.45)
        )

        if buy_candidate:
            return "buy", confidence, notes
        if sell_candidate:
            return "sell", confidence, notes
        notes.append("score_threshold_not_met")
        return "hold", confidence, notes

    def run(
        self,
        db: Session,
        *,
        symbol: str,
        timeframe: str = DEFAULT_TIMEFRAME,
        trigger_source: str = "manual",
        gate_level: int | None = None,
    ) -> SignalLog:
        symbol = symbol.upper()
        resolved_gate_level = resolve_gate_level(gate_level)
        profile = get_gate_profile(resolved_gate_level)

        bars = self.market_data_service.get_recent_bars(symbol, limit=DEFAULT_BARS_LIMIT, timeframe=timeframe)
        indicators = self.indicator_service.calculate(bars)

        market_analysis = self.gpt_market_service.run_and_save(db, symbol, indicators, gate_level=resolved_gate_level)

        quant = self.quant_signal_service.score(indicators, gate_level=resolved_gate_level)
        ai = self.ai_signal_service.adjust(
            indicators=indicators,
            quant_buy_score=quant["quant_buy_score"],
            quant_sell_score=quant["quant_sell_score"],
        )

        final_buy = min(max((quant["quant_buy_score"] * QUANT_WEIGHT) + (ai["ai_buy_score"] * AI_WEIGHT), 0.0), 100.0)
        final_sell = min(max((quant["quant_sell_score"] * QUANT_WEIGHT) + (ai["ai_sell_score"] * AI_WEIGHT), 0.0), 100.0)

        action, confidence, action_notes = self._resolve_action(
            market_entry_allowed=bool(market_analysis.entry_allowed),
            regime=(market_analysis.market_regime or "unknown"),
            quant_buy=quant["quant_buy_score"],
            quant_sell=quant["quant_sell_score"],
            ai_buy=ai["ai_buy_score"],
            ai_sell=ai["ai_sell_score"],
            final_buy=final_buy,
            final_sell=final_sell,
            gate_level=resolved_gate_level,
        )
        is_hold = action == "hold"

        gating_notes = list(quant.get("quant_notes") or []) + action_notes
        signal = SignalLog(
            symbol=symbol,
            action=action,
            buy_score=final_buy,
            sell_score=final_sell,
            confidence=confidence,
            reason=(
                f"gate_level={resolved_gate_level}({profile.name}); gpt_gate={market_analysis.entry_allowed}; "
                "quant+ai blended"
            ),
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
            gate_level=resolved_gate_level,
            gate_profile_name=profile.name,
            hard_block_reason=market_analysis.hard_block_reason,
            gating_notes=json.dumps(gating_notes, ensure_ascii=False),
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)
        return signal
