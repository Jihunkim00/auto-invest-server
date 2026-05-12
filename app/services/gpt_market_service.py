from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.constants import KILL_SWITCH_DEFAULT, get_gate_profile, resolve_gate_level
from app.db.models import MarketAnalysis
from app.services.market_gate_schema import parse_market_gate_response
from app.services.reference_site_cache_service import ReferenceSiteCacheService
from app.services.reference_site_service import ReferenceSiteService
from app.services.web_content_service import WebContentService

logger = logging.getLogger(__name__)


COMMON_SYSTEM_PROMPT = """
You are a quant-first market context and event-risk evaluator
for a conservative auto-trading system.

You do NOT approve trades.
The risk engine is the final authority.

Quant indicators are primary.
Your role is to evaluate whether macro, geopolitical, FX, energy,
political, regulatory, sector, earnings, revenue, flow, and event context
should penalize or block new buy entries.

Positive news must NOT directly approve a buy.
Negative, uncertain, or unstable context may reduce score or block new buy entries.

High or extreme event risk should block new buy entries.
Sell, stop-loss, take-profit, and risk-reduction actions must remain allowed.

Default behavior:
- If context is unclear, prefer HOLD.
- If quant and context conflict, do not increase risk.
- Use external context as a risk filter, not as a standalone buy signal.
- Earnings or earnings-call events are uncertainty risks, not bullish signals.
- Do not increase buy_score, action confidence, or entry confidence because of upcoming earnings.
- If event_context.entry_blocked is true, recommend hold or block_entry.
- If event_context.position_size_multiplier is below 1.0, mention reduced position sizing.
- Do not treat upcoming earnings as a reason to buy.

Return JSON only.
No markdown fences.
"""

KR_MARKET_SYSTEM_PROMPT = """
You are evaluating Korean stock market context for KIS Korean stock trading.

Market: KR
Broker: KIS
Currency: KRW
Trading style: conservative, quant-first, low-frequency, risk-controlled.

For Korean stocks, always evaluate:

1. USD/KRW FX risk
- Is USD/KRW rising sharply?
- Is KRW weakening?
- Does FX pressure imply foreign outflow risk?
- Rising USD/KRW generally increases risk-off pressure for Korean equities.

2. Previous US market session
- S&P 500, Nasdaq, Dow direction
- US tech/growth sentiment
- Whether US weakness may spill over to Korea

3. SOX semiconductor index and US semiconductor sentiment
- Important for Samsung Electronics, SK Hynix, semiconductor equipment,
  materials, and growth-sensitive Korean stocks.

4. KOSPI / KOSDAQ risk mood
- Broad market direction
- Market breadth
- Whether small caps or growth names are under pressure

5. Foreign and institutional investor flow
- Foreign net buying/selling
- Institutional net buying/selling
- Persistent foreign selling should increase entry penalty.

6. Geopolitical risk
- War, Middle East escalation, China/Taiwan tension, North Korea risk,
  shipping lane risk, sanctions, defense-related events.

7. Energy and commodity risk
- Oil price shock
- Gas, coal, lithium, copper, nickel, and other key commodity pressure
- Determine whether the symbol benefits or suffers from energy/commodity moves.

8. Korean political and regulatory risk (political/regulatory risk)
- Short-selling policy
- Tax policy
- Platform regulation
- Banking/insurance regulation
- Battery, semiconductor, defense, nuclear, bio, and AI policy changes

9. Sector fundamental and revenue trend
Evaluate whether the symbol's core business area shows improving,
stable, mixed, or weakening demand/revenue trend.

Examples:
- Semiconductor: DRAM/NAND price, HBM demand, AI server demand, CAPEX cycle
- Battery: EV demand, lithium price, cathode/anode margin, IRA/tariff risk
- Auto: FX benefit, US sales, EV/hybrid demand, labor issues
- Shipbuilding: order backlog, LNG carrier demand, newbuilding price
- Defense: export contracts, geopolitical demand, government budget
- Refining/Chemical: oil price, refining margin, naphtha, China demand
- Airline/Travel: FX, oil price, passenger demand, geopolitical risk
- Finance: rate path, NIM, delinquency, dividend policy
- Platform/Internet: ad revenue, regulation, AI cost, traffic
- Bio: clinical events, FDA/MFDS calendar, licensing deals, cash burn

10. Company-specific event risk
- Earnings shock
- Guidance cut
- Capital increase
- Major lawsuit
- Accounting issue
- Supply disruption
- Customer concentration risk
- Large insider or block sale
- Lock-up expiration

Use these only as risk adjustments.
Do not create a buy signal from positive news alone.

If external context is favorable, entry_penalty may be low.
If external context is mixed, apply moderate penalty.
If external context is high risk, block new buy entries.
Sell or exit actions must remain allowed.
"""

US_MARKET_SYSTEM_PROMPT = """
You are evaluating US stock market context for Alpaca US stock trading.

Market: US
Broker: Alpaca
Currency: USD
Trading style: conservative, quant-first, low-frequency, risk-controlled.

For US stocks, always evaluate:

1. Major US index regime
- S&P 500
- Nasdaq
- Dow
- Russell 2000 if relevant
- Determine whether the market is risk-on, neutral, risk-off, or panic.

2. VIX and volatility regime
- Rising VIX increases market risk.
- Extreme volatility should block new buy entries unless quant setup is very strong
  and risk engine allows it.

3. Interest rate and bond yield risk
- 10-year Treasury yield
- 2-year Treasury yield
- Yield curve pressure
- Rising yields may pressure growth, tech, long-duration assets.

4. Federal Reserve and macro event risk
- FOMC
- CPI
- PPI
- Payrolls
- Unemployment
- Retail sales
- GDP
- ISM/PMI
- Fed speeches
High-impact macro event days should increase entry penalty.

5. USD and global liquidity
- DXY direction
- Dollar strength
- Liquidity tightening or easing signals

6. Sector and ETF context
Evaluate sector ETF context and sector-specific context using relevant ETFs or sector indexes.

Examples:
- Tech: QQQ, XLK, Nasdaq, AI capex cycle
- Semiconductors: SOX, SMH, Nvidia/AMD sentiment
- Financials: XLF, yield curve, credit risk
- Energy: XLE, oil/gas prices
- Healthcare/Biotech: XLV, XBI, FDA events
- Consumer discretionary: XLY, retail sales, consumer spending
- Industrials: XLI, orders, infrastructure cycle
- Small caps: IWM, rate sensitivity, liquidity

7. Earnings and guidance
- Revenue growth
- EPS trend
- Margin trend
- Guidance raise/cut
- Analyst revisions
- Post-earnings drift risk

8. Company-specific fundamentals
- Core revenue trend
- Business segment growth
- Customer concentration
- Backlog
- Pricing power
- Free cash flow
- Debt/refinancing risk

9. Geopolitical and energy risk
- War escalation
- Middle East oil shock
- China/Taiwan risk
- Sanctions
- Supply chain disruption

10. Political and regulatory risk
- Antitrust
- AI regulation
- Export controls
- Healthcare regulation
- Bank regulation
- Tax policy
- Tariffs
- Election-related policy uncertainty

Use these only as risk adjustments.
Do not create a buy signal from positive news alone.

If external context is favorable, entry_penalty may be low.
If external context is mixed, apply moderate penalty.
If external context is high risk, block new buy entries.
Sell or exit actions must remain allowed.
"""

RISK_LEVELS = {"unknown", "none", "low", "medium", "high", "extreme"}
RISK_PENALTY = {
    "unknown": 0,
    "none": 0,
    "low": 1,
    "medium": 3,
    "high": 6,
    "extreme": 999,
}


@dataclass(slots=True)
class MarketGateContext:
    cached_site_summaries: list[dict]
    used_cache: bool
    refreshed_this_run: bool = False


class GPTMarketService:
    """
    Quant-first market-entry gate.
    This service never approves orders directly.
    The risk engine remains the final authority.
    """

    def __init__(self) -> None:
        settings = get_settings()

        self.openai_api_key = settings.openai_api_key
        self.openai_model = settings.openai_model
        self.openai_reasoning_effort = settings.openai_reasoning_effort

        self.cache_service = ReferenceSiteCacheService(
            settings.reference_site_cache_ttl_minutes
        )
        self.reference_site_service = ReferenceSiteService(
            settings.reference_sites_config_path
        )
        self.web_content_service = WebContentService(
            timeout_seconds=settings.reference_site_fetch_timeout_seconds,
            max_chars=settings.reference_site_max_summary_chars,
        )

        self.client: OpenAI | None = (
            OpenAI(api_key=self.openai_api_key) if self.openai_api_key else None
        )

    def analyze(
        self,
        db: Session,
        symbol: str,
        indicators: dict[str, Any],
        gate_level: int | None = None,
        event_context: dict[str, Any] | None = None,
        market: str = "US",
    ) -> dict[str, Any]:
        resolved_gate_level = resolve_gate_level(gate_level)
        profile = get_gate_profile(resolved_gate_level)
        fallback = self._rule_based_analysis(indicators, resolved_gate_level)
        context = self._load_context_from_cache(db, symbol)

        if not indicators:
            return self._with_metadata(
                fallback,
                context=context,
                gpt_used=False,
                fallback_used=True,
                fallback_reason="insufficient indicators",
                gate_level=resolved_gate_level,
                event_context=event_context,
            )

        if not self.client:
            return self._with_metadata(
                fallback,
                context=context,
                gpt_used=False,
                fallback_used=True,
                fallback_reason="OPENAI_API_KEY missing",
                gate_level=resolved_gate_level,
                event_context=event_context,
            )

        try:
            candidate = self._call_openai(
                symbol=symbol,
                indicators=indicators,
                context=context,
                gate_level=resolved_gate_level,
                gate_profile_name=profile.name,
                event_context=event_context,
                market=market,
            )
            normalized = self._normalize_candidate(candidate)
            parsed = parse_market_gate_response(normalized)
            hardened = self._apply_guardrails(
                parsed,
                fallback,
                indicators=indicators,
                gate_level=resolved_gate_level,
            )

            return self._with_metadata(
                hardened,
                context=context,
                gpt_used=True,
                fallback_used=False,
                gate_level=resolved_gate_level,
                event_context=event_context,
            )
        except Exception as e:
            logger.exception("OpenAI market analysis failed: %s", e)
            return self._with_metadata(
                fallback,
                context=context,
                gpt_used=False,
                fallback_used=True,
                fallback_reason=self._safe_exc_message(e),
                gate_level=resolved_gate_level,
                event_context=event_context,
            )

    def _load_context_from_cache(self, db: Session, symbol: str) -> MarketGateContext:
        summaries, used_cache = self.cache_service.get_fresh_summaries(db, symbol)
        if used_cache:
            return MarketGateContext(
                cached_site_summaries=summaries,
                used_cache=True,
                refreshed_this_run=False,
            )

        refreshed_count = self._best_effort_refresh_cache(db, symbol)
        if refreshed_count > 0:
            summaries, used_cache = self.cache_service.get_fresh_summaries(db, symbol)
            return MarketGateContext(
                cached_site_summaries=summaries,
                used_cache=used_cache,
                refreshed_this_run=True,
            )

        return MarketGateContext(
            cached_site_summaries=summaries,
            used_cache=False,
            refreshed_this_run=False,
        )

    def _best_effort_refresh_cache(self, db: Session, symbol: str) -> int:
        try:
            sites = self.reference_site_service.get_sites_for_symbol(symbol)
            if not sites:
                logger.info("No enabled reference sites found for symbol=%s", symbol)
                return 0

            summaries = self.web_content_service.build_site_summaries(sites)
            if not summaries:
                logger.info(
                    "Reference site fetch returned no summaries for symbol=%s",
                    symbol,
                )
                return 0

            upserted = self.cache_service.upsert_summaries(db, symbol, summaries)
            logger.info(
                "Reference site cache refreshed for symbol=%s, summaries=%s",
                symbol,
                upserted,
            )
            return upserted
        except Exception as e:
            logger.exception("Best-effort reference cache refresh failed: %s", e)
            return 0

    def _rule_based_analysis(
        self,
        indicators: dict[str, Any],
        gate_level: int,
    ) -> dict[str, Any]:
        profile = get_gate_profile(gate_level)
        if not indicators:
            return {
                "market_regime": "unknown",
                "entry_bias": "neutral",
                "entry_allowed": False,
                "regime_confidence": 0.20,
                "hard_block_reason": "insufficient_indicators",
                "hard_blocked": True,
                "gating_notes": ["Insufficient indicator history"],
                "reason": "Insufficient indicator history; HOLD-safe fallback.",
            }

        ema20 = float(indicators.get("ema20", 0) or 0)
        ema50 = float(indicators.get("ema50", 0) or 0)
        rsi = float(indicators.get("rsi", 50) or 50)
        short_momentum = float(indicators.get("short_momentum", 0) or 0)
        volume_ratio = float(indicators.get("volume_ratio", 1) or 1)
        vwap = float(indicators.get("vwap", 0) or 0)
        price = max(float(indicators.get("price", 0) or 0), 1e-9)

        notes: list[str] = []
        score = 62.0

        trend_up = ema20 > ema50
        if trend_up:
            score += 10.0
        else:
            score -= 10.0
            notes.append("ema20_below_ema50")

        below_levels = sum([price < ema20, price < ema50, price < vwap])
        score -= below_levels * 6.0
        if below_levels:
            notes.append(f"below_key_levels={below_levels}")

        if short_momentum < -0.003:
            score -= 10.0
            notes.append("negative_momentum")
        elif short_momentum > 0.001:
            score += 8.0

        if volume_ratio < 0.9:
            score -= profile.weak_volume_penalty
            notes.append("weak_volume")
        elif volume_ratio > 1.1:
            score += 6.0

        bearish_extreme = (not trend_up) and short_momentum < -0.006 and rsi < 35 and below_levels >= 2
        if bearish_extreme and profile.bearish_is_hard_block:
            return {
                "market_regime": "trend",
                "entry_bias": "neutral",
                "entry_allowed": False,
                "regime_confidence": 0.30,
                "hard_block_reason": "extreme_bearish_regime",
                "hard_blocked": True,
                "gating_notes": notes + ["hard_block_extreme_bearish_regime"],
                "reason": "Hard-blocked: extreme bearish regime under strict profile.",
            }

        regime = "trend" if abs(ema20 - ema50) / price > 0.002 else "range"
        if regime == "range" and not profile.allow_neutral_regime_entry:
            score -= 14.0
            notes.append("neutral_regime_penalty")

        if rsi <= 30 and not profile.allow_oversold_bounce:
            score -= 8.0
            notes.append("oversold_bounce_disabled")

        regime_confidence = max(0.2, min(score / 100.0, 0.95))
        entry_allowed = regime_confidence >= max(profile.min_confidence_to_trade - 0.07, 0.45)

        return {
            "market_regime": regime,
            "entry_bias": "long" if trend_up else "neutral",
            "entry_allowed": entry_allowed,
            "regime_confidence": regime_confidence,
            "hard_block_reason": None,
            "hard_blocked": False,
            "gating_notes": notes,
            "reason": "Rule-based market gate scored with penalty model (non-hard-block factors penalized).",
        }

    def _build_system_prompt(self, market: str) -> str:
        market = (market or "US").upper()
        if market == "KR":
            return COMMON_SYSTEM_PROMPT + "\n\n" + KR_MARKET_SYSTEM_PROMPT
        if market == "US":
            return COMMON_SYSTEM_PROMPT + "\n\n" + US_MARKET_SYSTEM_PROMPT
        return COMMON_SYSTEM_PROMPT

    def _build_prompt(
        self,
        symbol: str,
        indicators: dict[str, Any],
        context: MarketGateContext,
        gate_level: int,
        gate_profile_name: str,
        event_context: dict[str, Any] | None = None,
        market: str = "US",
    ) -> tuple[str, str]:
        market = (market or "US").upper()
        system_prompt = self._build_system_prompt(market)

        prompt_payload = {
            "market": market,
            "symbol": symbol,
            "indicators": indicators,
            "cached_site_summaries": context.cached_site_summaries,
            "gate_config": {
                "gate_level": gate_level,
                "gate_profile_name": gate_profile_name,
            },
            "scoring_rules": {
                "quant_is_primary": True,
                "gpt_is_risk_filter": True,
                "positive_news_cannot_directly_approve_buy": True,
                "negative_context_can_penalize_or_block_new_buy": True,
                "sell_or_exit_must_remain_allowed": True,
            },
            "required_output": {
                "market_risk_regime": ["risk_on", "neutral", "risk_off", "panic"],
                "event_risk_level": ["none", "low", "medium", "high", "extreme"],
                "entry_penalty": "integer from 0 to 30, or 999 for hard block",
                "hard_block_new_buy": "boolean",
                "allow_sell_or_exit": "boolean and should normally be true",
            },
            "notes": {
                "website_context_secondary": True,
                "used_cache": context.used_cache,
                "refreshed_this_run": context.refreshed_this_run,
                "summary_count": len(context.cached_site_summaries),
            },
        }
        if event_context:
            prompt_payload["event_context"] = {
                "has_near_event": bool(event_context.get("has_near_event")),
                "event_type": event_context.get("event_type"),
                "days_to_event": event_context.get("days_to_event"),
                "event_time_label": event_context.get("event_time_label"),
                "entry_blocked": bool(event_context.get("entry_blocked")),
                "scale_in_blocked": bool(event_context.get("scale_in_blocked")),
                "position_size_multiplier": event_context.get("position_size_multiplier", 1.0),
                "risk_policy": (
                    "block_new_entry"
                    if event_context.get("entry_blocked")
                    else (
                        "reduce_position_size"
                        if float(event_context.get("position_size_multiplier") or 1.0) < 1.0
                        else "none"
                    )
                ),
            }

        user_prompt = json.dumps(prompt_payload, ensure_ascii=False)
        return system_prompt, user_prompt

    def _call_openai(
        self,
        *,
        symbol: str,
        indicators: dict[str, Any],
        context: MarketGateContext,
        gate_level: int,
        gate_profile_name: str,
        event_context: dict[str, Any] | None = None,
        market: str = "US",
    ) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("OpenAI client is not initialized")

        system_prompt, user_prompt = self._build_prompt(
            symbol,
            indicators,
            context,
            gate_level,
            gate_profile_name,
            event_context,
            market,
        )

        try:
            response = self.client.responses.create(
                model=self.openai_model,
                reasoning={"effort": self.openai_reasoning_effort},
                instructions=system_prompt,
                input=user_prompt,
            )
        except AuthenticationError:
            raise
        except (RateLimitError, APITimeoutError, APIConnectionError, BadRequestError):
            raise

        raw_text = (response.output_text or "").strip()


        if not raw_text:
            raise ValueError("OpenAI returned empty output_text")

        return self._parse_json_text(raw_text)

    def _parse_json_text(self, raw_text: str) -> dict[str, Any]:
        text = raw_text.strip()

        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError(f"Could not locate JSON object in response: {raw_text}")
            text = text[start : end + 1]

        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("Parsed OpenAI response is not a JSON object")

        return payload

    def _normalize_candidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)

        market = str(result.get("market", "") or "").strip().upper()
        if market:
            result["market"] = market

        symbol = str(result.get("symbol", "") or "").strip().upper()
        if symbol:
            result["symbol"] = symbol

        regime = str(result.get("market_regime", "") or "").strip().lower()
        regime_map = {
            "unknown": "unknown",
            "range": "range",
            "ranging": "range",
            "sideways": "range",
            "neutral": "range",
            "flat": "range",
            "trend": "trend",
            "trending": "trend",
            "trend_up": "trend",
            "trend_down": "trend",
            "uptrend": "trend",
            "downtrend": "trend",
            "bullish": "trend",
            "bearish": "trend",
            "volatile": "volatile",
        }
        technical_regime = str(result.get("technical_market_regime", "") or "").strip().lower()
        result["market_regime"] = regime_map.get(regime, regime_map.get(technical_regime, "unknown"))
        result["technical_market_regime"] = regime_map.get(technical_regime, result["market_regime"])
        if result["technical_market_regime"] == "volatile":
            result["technical_market_regime"] = "unknown"

        market_risk_regime = str(result.get("market_risk_regime", "") or "").strip().lower()
        if market_risk_regime not in {"risk_on", "neutral", "risk_off", "panic"}:
            market_risk_regime = "neutral"
        result["market_risk_regime"] = market_risk_regime

        bias = str(result.get("entry_bias", "") or "").strip().lower()
        bias_map = {
            "long": "long",
            "buy": "long",
            "bullish": "long",
            "neutral": "neutral",
            "hold": "neutral",
            "flat": "neutral",
            "none": "neutral",
            "no_entry": "neutral",
            "block_entry": "neutral",
        }
        result["entry_bias"] = bias_map.get(bias, "neutral")

        entry_allowed = result.get("entry_allowed", False)
        if isinstance(entry_allowed, str):
            entry_allowed = entry_allowed.strip().lower() == "true"
        result["entry_allowed"] = bool(entry_allowed)

        hard_block_new_buy = result.get("hard_block_new_buy", False)
        if isinstance(hard_block_new_buy, str):
            hard_block_new_buy = hard_block_new_buy.strip().lower() == "true"
        result["hard_block_new_buy"] = bool(hard_block_new_buy)

        allow_sell_or_exit = result.get("allow_sell_or_exit", True)
        if isinstance(allow_sell_or_exit, str):
            allow_sell_or_exit = allow_sell_or_exit.strip().lower() != "false"
        result["allow_sell_or_exit"] = bool(allow_sell_or_exit)

        for key in (
            "event_risk_level",
            "fx_risk_level",
            "geopolitical_risk_level",
            "energy_risk_level",
            "political_regulatory_risk_level",
            "macro_risk_level",
            "valuation_risk_level",
        ):
            value = str(result.get(key, "none") or "none").strip().lower()
            result[key] = value if value in RISK_LEVELS else "none"

        for key in ("sector_fundamental_trend", "revenue_trend_context"):
            value = str(result.get(key, "unknown") or "unknown").strip().lower()
            result[key] = value if value in {"improving", "stable", "mixed", "weakening", "unknown"} else "unknown"

        for key in ("flow_signal", "earnings_revision_signal"):
            value = str(result.get(key, "unknown") or "unknown").strip().lower()
            result[key] = value if value in {"positive", "neutral", "negative", "unknown"} else "unknown"

        result["entry_penalty"] = self._normalized_entry_penalty(result)
        if result["entry_penalty"] == 999 or result["event_risk_level"] == "extreme":
            result["hard_block_new_buy"] = True
            result["entry_allowed"] = False
        elif result["hard_block_new_buy"]:
            result["entry_allowed"] = False

        for score_key in ("gpt_buy_score", "gpt_sell_score", "ai_buy_score", "ai_sell_score"):
            if score_key in result:
                result[score_key] = self._clamp_float(result.get(score_key), 0.0, 100.0)

        confidence_source = result.get("market_confidence", result.get("confidence", result.get("regime_confidence", 0)))
        confidence = self._clamp_float(confidence_source, 0.0, 100.0)
        if confidence > 1.0:
            confidence = confidence / 100.0
        confidence = max(0.0, min(confidence, 1.0))
        result["market_confidence"] = confidence
        result["confidence"] = confidence

        for list_key in ("affected_sectors", "risk_flags", "gating_notes"):
            raw = result.get(list_key)
            if isinstance(raw, list):
                result[list_key] = [str(item)[:120] for item in raw if str(item).strip()]
            elif raw:
                result[list_key] = [str(raw)[:120]]
            else:
                result[list_key] = []

        reason = str(result.get("reason", "") or "").strip()
        result["reason"] = reason or "Model returned no reason."

        return result

    def _normalized_entry_penalty(self, result: dict[str, Any]) -> int:
        explicit = result.get("entry_penalty")
        try:
            penalty = int(float(explicit))
        except Exception:
            penalty = 0

        risk_keys = (
            "fx_risk_level",
            "geopolitical_risk_level",
            "energy_risk_level",
            "political_regulatory_risk_level",
            "macro_risk_level",
            "valuation_risk_level",
            "event_risk_level",
        )
        risk_penalties = [RISK_PENALTY.get(str(result.get(key, "none")).lower(), 0) for key in risk_keys]
        if any(value >= 999 for value in risk_penalties) or penalty >= 999:
            return 999

        flow_signal = str(result.get("flow_signal", "unknown") or "unknown").lower()
        sector_trend = str(result.get("sector_fundamental_trend", "unknown") or "unknown").lower()
        revenue_trend = str(result.get("revenue_trend_context", "unknown") or "unknown").lower()
        earnings_signal = str(result.get("earnings_revision_signal", "unknown") or "unknown").lower()
        context_penalty = sum(risk_penalties)
        context_penalty += {"negative": 3, "neutral": 1, "unknown": 1, "positive": 0}.get(flow_signal, 0)
        context_penalty += {"weakening": 3, "mixed": 2, "unknown": 1, "stable": 0, "improving": 0}.get(sector_trend, 0)
        context_penalty += {"weakening": 3, "mixed": 2, "unknown": 1, "stable": 0, "improving": 0}.get(revenue_trend, 0)
        context_penalty += {"negative": 3, "neutral": 1, "unknown": 1, "positive": 0}.get(earnings_signal, 0)
        return max(0, min(max(penalty, context_penalty), 30))

    def _clamp_float(self, value: Any, min_value: float, max_value: float) -> float:
        try:
            number = float(value)
        except Exception:
            number = min_value
        return max(min_value, min(number, max_value))

    def _apply_guardrails(
        self,
        payload: dict[str, Any],
        fallback: dict[str, Any],
        *,
        indicators: dict[str, Any],
        gate_level: int,
    ) -> dict[str, Any]:
        profile = get_gate_profile(gate_level)
        result = dict(payload)

        gpt_conf = float(result.get("market_confidence", 0) or 0)
        fallback_conf = float(fallback.get("regime_confidence", 0) or 0)
        entry_penalty = int(result.get("entry_penalty", 0) or 0)
        penalty_confidence = 1.0 if entry_penalty >= 999 else min(entry_penalty, 30) / 100.0
        # GPT is a risk filter: it may lower but must not raise the quant-first fallback confidence.
        result["regime_confidence"] = round(max(0.0, min(fallback_conf, gpt_conf if gpt_conf > 0 else fallback_conf) - penalty_confidence), 4)

        notes = list(fallback.get("gating_notes") or [])
        notes.extend(result.get("gating_notes") or [])
        if gpt_conf < 0.35:
            notes.append("low_gpt_confidence")
        if entry_penalty:
            notes.append(f"gpt_entry_penalty={entry_penalty}")

        hard_block_reason = fallback.get("hard_block_reason")
        if KILL_SWITCH_DEFAULT:
            hard_block_reason = "kill_switch_active"

        event_risk_level = str(result.get("event_risk_level", "none") or "none").lower()
        if result.get("hard_block_new_buy"):
            hard_block_reason = hard_block_reason or "gpt_hard_block_new_buy"
        if event_risk_level == "extreme":
            result["hard_block_new_buy"] = True
            hard_block_reason = hard_block_reason or "extreme_event_risk"
        elif event_risk_level == "high":
            notes.append("high_event_risk_entry_penalty")
            if gate_level <= 2 or entry_penalty >= 6:
                result["entry_allowed"] = False
                result["entry_bias"] = "neutral"

        if hard_block_reason:
            result["entry_allowed"] = False
            result["entry_bias"] = "neutral"
            notes.append(f"hard_block={hard_block_reason}")
        else:
            bearish_penalty = 0.0
            trend_up = bool(indicators.get("ema20", 0) > indicators.get("ema50", 0))
            if not trend_up and not profile.bearish_is_hard_block:
                bearish_penalty = 0.07
                notes.append("bearish_regime_score_penalty")

            effective_conf = max(0.0, result["regime_confidence"] - bearish_penalty)
            risk_allowed = result.get("entry_allowed") is not False
            threshold_allowed = effective_conf >= max(profile.min_confidence_to_trade - 0.08, 0.45)
            result["entry_allowed"] = bool(risk_allowed and threshold_allowed)
            result["entry_bias"] = "long" if result["entry_allowed"] else "neutral"
            result["regime_confidence"] = round(effective_conf, 4)

        result["allow_sell_or_exit"] = True if result.get("allow_sell_or_exit") is not False else False
        result["hard_block_reason"] = hard_block_reason
        result["hard_blocked"] = bool(hard_block_reason)
        result["gating_notes"] = notes
        if not result.get("reason"):
            result["reason"] = "Market gate evaluated by profile-aware guardrails."

        return result

    def _with_metadata(
        self,
        payload: dict[str, Any],
        *,
        context: MarketGateContext,
        gpt_used: bool,
        fallback_used: bool,
        gate_level: int,
        fallback_reason: str | None = None,
        event_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        profile = get_gate_profile(gate_level)
        reason = str(payload.get("reason", "") or "").strip()
        if fallback_reason:
            reason = (
                f"{reason} | fallback: {fallback_reason}"
                if reason
                else f"fallback: {fallback_reason}"
            )

        result = dict(payload)
        result["reason"] = reason
        result["risk_note"] = reason
        result["macro_summary"] = (
            f"cached reference context used ({len(context.cached_site_summaries)} summaries)"
            if context.used_cache
            else "no fresh cached reference context"
        )
        result["gate_level"] = gate_level
        result["gate_profile_name"] = profile.name
        result["hard_blocked"] = bool(result.get("hard_block_reason"))
        result["market_confidence"] = result.get("regime_confidence", result.get("market_confidence", 0.0))
        result["audit"] = {
            "gpt_used": gpt_used,
            "fallback_used": fallback_used,
            "used_cached_website_context": context.used_cache,
            "refreshed_cache_this_run": context.refreshed_this_run,
            "site_summary_count": len(context.cached_site_summaries),
            "fallback_reason": fallback_reason,
        }
        result["site_summaries"] = context.cached_site_summaries
        if event_context:
            result["event_context"] = event_context
        return result

    def _safe_exc_message(self, exc: Exception) -> str:
        text = str(exc).strip()
        if not text:
            return exc.__class__.__name__
        if len(text) > 240:
            return f"{exc.__class__.__name__}: {text[:240]}..."
        return f"{exc.__class__.__name__}: {text}"

    def save_analysis(
        self,
        db: Session,
        symbol: str,
        payload: dict[str, Any],
    ) -> MarketAnalysis:
        row = MarketAnalysis(
            symbol=symbol.upper(),
            market_regime=payload.get("market_regime"),
            entry_bias=payload.get("entry_bias"),
            entry_allowed=bool(payload.get("entry_allowed", False)),
            market_confidence=float(payload.get("regime_confidence", payload.get("market_confidence", 0)) or 0),
            risk_note=payload.get("risk_note") or payload.get("reason"),
            macro_summary=payload.get("macro_summary"),
            gate_level=payload.get("gate_level"),
            gate_profile_name=payload.get("gate_profile_name"),
            hard_block_reason=payload.get("hard_block_reason"),
            hard_blocked=bool(payload.get("hard_blocked", False)),
            gating_notes=json.dumps(payload.get("gating_notes") or [], ensure_ascii=False),
            raw_payload=json.dumps(payload, ensure_ascii=False),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def run_and_save(
        self,
        db: Session,
        symbol: str,
        indicators: dict[str, Any],
        gate_level: int | None = None,
        event_context: dict[str, Any] | None = None,
        market: str = "US",
    ) -> MarketAnalysis:
        market = (market or "US").upper()
        if event_context:
            kwargs: dict[str, Any] = {"gate_level": gate_level, "event_context": event_context}
            if market != "US":
                kwargs["market"] = market
            payload = self.analyze(db, symbol, indicators, **kwargs)
        else:
            kwargs = {"gate_level": gate_level}
            if market != "US":
                kwargs["market"] = market
            payload = self.analyze(db, symbol, indicators, **kwargs)
        return self.save_analysis(db, symbol, payload)
