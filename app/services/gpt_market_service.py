from __future__ import annotations

import json
from dataclasses import dataclass

import requests
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import MarketAnalysis
from app.services.market_gate_schema import MARKET_GATE_SCHEMA, parse_market_gate_response
from app.services.reference_site_cache_service import ReferenceSiteCacheService


@dataclass(slots=True)
class MarketGateContext:
    cached_site_summaries: list[dict]
    used_cache: bool


class GPTMarketService:
    """
    Quant-first market-entry gate. This service does not approve orders.
    Risk engine remains final authority.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.openai_api_key = settings.openai_api_key
        self.openai_model = settings.openai_model
        self.openai_reasoning_effort = settings.openai_reasoning_effort
        self.market_gate_min_confidence = settings.market_gate_min_confidence
        self.cache_service = ReferenceSiteCacheService(settings.reference_site_cache_ttl_minutes)

    def analyze(self, db: Session, symbol: str, indicators: dict) -> dict:
        fallback = self._rule_based_analysis(indicators)
        context = self._load_context_from_cache(db, symbol)

        if not indicators:
            return self._with_metadata(fallback, context=context, gpt_used=False, fallback_used=True, fallback_reason="insufficient indicators")

        if not self.openai_api_key:
            return self._with_metadata(fallback, context=context, gpt_used=False, fallback_used=True, fallback_reason="OPENAI_API_KEY missing")

        try:
            candidate = self._call_openai(symbol=symbol, indicators=indicators, context=context)
            parsed = parse_market_gate_response(candidate)
            hardened = self._apply_guardrails(parsed, fallback)
            return self._with_metadata(hardened, context=context, gpt_used=True, fallback_used=False)
        except Exception:
            return self._with_metadata(fallback, context=context, gpt_used=False, fallback_used=True, fallback_reason="OpenAI failure or schema parse failure")

    def _load_context_from_cache(self, db: Session, symbol: str) -> MarketGateContext:
        summaries, used_cache = self.cache_service.get_fresh_summaries(db, symbol)
        return MarketGateContext(cached_site_summaries=summaries, used_cache=used_cache)

    def _rule_based_analysis(self, indicators: dict) -> dict:
        if not indicators:
            return {
                "market_regime": "unknown",
                "entry_bias": "neutral",
                "entry_allowed": False,
                "market_confidence": 0.2,
                "reason": "Insufficient indicator history; conservative HOLD-safe fallback.",
            }

        trend_up = indicators.get("ema20", 0) > indicators.get("ema50", 0)
        momentum_ok = indicators.get("short_momentum", 0) > 0
        rsi = indicators.get("rsi", 50)
        rsi_mid = 45 <= rsi <= 70

        allowed = bool(trend_up and momentum_ok and rsi_mid)
        price = max(float(indicators.get("price", 0) or 0), 1e-9)
        spread = abs(float(indicators.get("ema20", 0) or 0) - float(indicators.get("ema50", 0) or 0)) / price
        regime = "trend" if spread > 0.002 else "range"
        confidence = 0.7 if allowed else 0.45

        return {
            "market_regime": regime,
            "entry_bias": "long" if trend_up else "neutral",
            "entry_allowed": allowed,
            "market_confidence": confidence,
            "reason": "Conservative quant-first gate active; entry blocked unless trend, momentum, and RSI alignment hold.",
        }

    def _build_prompt(self, symbol: str, indicators: dict, context: MarketGateContext) -> tuple[str, str]:
        system_prompt = (
            "You are a conservative market-entry gate assistant for an auto-trading MVP. "
            "Quant indicators are primary. Website context is secondary and may be stale/noisy. "
            "Default to hold-safe behavior. If quant/context conflict, prefer no entry. "
            "If confidence is unclear, set entry_allowed=false. "
            "This service does not approve orders; risk engine is final authority."
        )

        data = {
            "symbol": symbol,
            "indicators": indicators,
            "cached_site_summaries": context.cached_site_summaries,
            "notes": {
                "website_context_secondary": True,
                "used_cache": context.used_cache,
                "summary_count": len(context.cached_site_summaries),
            },
        }
        return system_prompt, json.dumps(data, ensure_ascii=False)

    def _call_openai(self, *, symbol: str, indicators: dict, context: MarketGateContext) -> dict:
        system_prompt, input_data = self._build_prompt(symbol, indicators, context)
        body = {
            "model": self.openai_model,
            "reasoning": {"effort": self.openai_reasoning_effort},
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": input_data}],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "market_gate_response",
                    "strict": True,
                    "schema": MARKET_GATE_SCHEMA,
                }
            },
        }

        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()
        text = self._extract_response_text(data)
        return json.loads(text)

    @staticmethod
    def _extract_response_text(payload: dict) -> str:
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    return content["text"]
        raise ValueError("missing output_text")

    def _apply_guardrails(self, payload: dict, fallback: dict) -> dict:
        result = dict(payload)
        if result["market_confidence"] < self.market_gate_min_confidence:
            result["entry_allowed"] = False

        trend_up = fallback.get("entry_bias") == "long"
        if not trend_up:
            result["entry_allowed"] = False

        if not result["entry_allowed"]:
            result["entry_bias"] = "neutral"

        return result

    def _with_metadata(
        self,
        payload: dict,
        *,
        context: MarketGateContext,
        gpt_used: bool,
        fallback_used: bool,
        fallback_reason: str | None = None,
    ) -> dict:
        reason = payload.get("reason", "")
        if fallback_reason:
            reason = f"{reason} | fallback: {fallback_reason}" if reason else f"fallback: {fallback_reason}"

        result = dict(payload)
        result["reason"] = reason
        result["risk_note"] = reason
        result["macro_summary"] = (
            f"cached reference context used ({len(context.cached_site_summaries)} summaries)"
            if context.used_cache
            else "no fresh cached reference context"
        )
        result["audit"] = {
            "gpt_used": gpt_used,
            "fallback_used": fallback_used,
            "used_cached_website_context": context.used_cache,
            "site_summary_count": len(context.cached_site_summaries),
        }
        result["site_summaries"] = context.cached_site_summaries
        return result

    def save_analysis(self, db: Session, symbol: str, payload: dict) -> MarketAnalysis:
        row = MarketAnalysis(
            symbol=symbol.upper(),
            market_regime=payload.get("market_regime"),
            entry_bias=payload.get("entry_bias"),
            entry_allowed=bool(payload.get("entry_allowed", False)),
            market_confidence=float(payload.get("market_confidence", 0) or 0),
            risk_note=payload.get("risk_note") or payload.get("reason"),
            macro_summary=payload.get("macro_summary"),
            raw_payload=json.dumps(payload, ensure_ascii=False),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def run_and_save(self, db: Session, symbol: str, indicators: dict) -> MarketAnalysis:
        payload = self.analyze(db, symbol, indicators)
        return self.save_analysis(db, symbol, payload)
