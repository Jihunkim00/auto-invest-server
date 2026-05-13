from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.entry_readiness_service import market_research_blocks_entry
from app.services.gpt_market_service import GPTMarketService
from app.services.gpt_risk_context import build_gpt_context


@dataclass
class MarketResearchResult:
    market_research_score: int
    event_risk: str
    sector_context: str
    news_risk: str
    macro_risk: str
    gpt_action_hint: str
    market_research_reason: str
    market_confidence: float
    hard_blocked: bool
    entry_allowed: bool


class WatchlistResearchService:
    def __init__(self, gpt_service: GPTMarketService | None = None) -> None:
        self._gpt_service = gpt_service or GPTMarketService()
        self._settings = get_settings()

    def analyze_candidate(
        self,
        db: Session,
        symbol: str,
        indicators: dict[str, Any],
        gate_level: int,
    ) -> dict[str, Any]:
        analysis = self._gpt_service.analyze(
            db=db,
            symbol=symbol.upper(),
            indicators=indicators,
            gate_level=gate_level,
        )

        fallback_used = bool(analysis.get("audit", {}).get("fallback_used"))
        market_confidence = float(analysis.get("market_confidence", 0.0) or 0.0)
        hard_blocked = bool(analysis.get("hard_blocked"))
        entry_allowed = bool(analysis.get("entry_allowed"))
        reason = str(analysis.get("reason", "") or "").strip()
        gpt_context = build_gpt_context(analysis, reason=reason)

        research_blocks_entry = market_research_blocks_entry(
            entry_allowed=entry_allowed,
            hard_blocked=hard_blocked,
            reason=reason,
            entry_bias=analysis.get("entry_bias"),
        )

        if fallback_used:
            research_score = 50
            gpt_action_hint = "neutral"
            if research_blocks_entry:
                gpt_action_hint = "block_entry"
        else:
            research_score = self._normalize_score(market_confidence)
            if research_blocks_entry:
                gpt_action_hint = "block_entry"
            else:
                gpt_action_hint = "allow_entry"

        event_risk = self._derive_event_risk(market_confidence, hard_blocked)
        news_risk = self._derive_news_risk(market_confidence, hard_blocked)
        macro_risk = self._derive_macro_risk(market_confidence, analysis.get("market_regime"))
        sector_context = self._derive_sector_context(analysis.get("market_regime"), analysis.get("entry_bias"))

        return {
            "market_research_score": research_score,
            "market_confidence": market_confidence,
            "event_risk": event_risk,
            "event_risk_level": gpt_context.get("event_risk_level"),
            "sector_context": sector_context,
            "news_risk": news_risk,
            "macro_risk": macro_risk,
            "gpt_action_hint": gpt_action_hint,
            "market_research_reason": reason or "No research reason provided.",
            "gpt_context": gpt_context,
            "entry_penalty": gpt_context.get("entry_penalty"),
            # Surface the GPT penalty for UI/audit without changing existing watchlist score math.
            "entry_penalty_observed": gpt_context.get("entry_penalty"),
            "hard_block_new_buy": bool(gpt_context.get("hard_block_new_buy", False)),
            "allow_sell_or_exit": bool(gpt_context.get("allow_sell_or_exit", True)),
            "risk_flags": list(gpt_context.get("risk_flags") or []),
            "gating_notes": list(gpt_context.get("gating_notes") or []),
            "hard_blocked": hard_blocked,
            "soft_entry_allowed": bool(entry_allowed and not hard_blocked),
            "entry_allowed": entry_allowed,
            "market_research_blocked": research_blocks_entry,
            "fallback_used": fallback_used,
        }

    def _normalize_score(self, value: float) -> int:
        return int(max(0, min(round(value * 100), 100)))

    def _derive_event_risk(self, market_confidence: float, hard_blocked: bool) -> str:
        if hard_blocked or market_confidence < 0.35:
            return "high"
        if market_confidence < 0.60:
            return "medium"
        return "low"

    def _derive_news_risk(self, market_confidence: float, hard_blocked: bool) -> str:
        if hard_blocked or market_confidence < 0.35:
            return "high"
        if market_confidence < 0.65:
            return "medium"
        return "low"

    def _derive_macro_risk(self, market_confidence: float, market_regime: str | None) -> str:
        if market_regime == "unknown" or market_confidence < 0.45:
            return "high"
        if market_confidence < 0.60:
            return "medium"
        return "low"

    def _derive_sector_context(self, market_regime: str | None, entry_bias: str | None) -> str:
        regime = str(market_regime or "unknown").lower()
        bias = str(entry_bias or "neutral").lower()
        if regime == "trend":
            return f"Trend-driven sector context with {bias} bias."
        if regime == "range":
            return f"Range-bound sector context with {bias} bias."
        return f"Sector context unknown with {bias} bias."
