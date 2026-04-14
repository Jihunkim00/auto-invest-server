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
from app.db.models import MarketAnalysis
from app.services.market_gate_schema import parse_market_gate_response
from app.services.reference_site_cache_service import ReferenceSiteCacheService
from app.services.reference_site_service import ReferenceSiteService
from app.services.web_content_service import WebContentService

logger = logging.getLogger(__name__)


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
        self.market_gate_min_confidence = settings.market_gate_min_confidence

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
    ) -> dict[str, Any]:
        fallback = self._rule_based_analysis(indicators)
        context = self._load_context_from_cache(db, symbol)

        if not indicators:
            return self._with_metadata(
                fallback,
                context=context,
                gpt_used=False,
                fallback_used=True,
                fallback_reason="insufficient indicators",
            )

        if not self.client:
            return self._with_metadata(
                fallback,
                context=context,
                gpt_used=False,
                fallback_used=True,
                fallback_reason="OPENAI_API_KEY missing",
            )

        try:
            candidate = self._call_openai(
                symbol=symbol,
                indicators=indicators,
                context=context,
            )
            logger.info("OpenAI raw candidate payload: %s", candidate)

            normalized = self._normalize_candidate(candidate)
            logger.info("OpenAI normalized candidate payload: %s", normalized)

            parsed = parse_market_gate_response(normalized)
            logger.info("Schema-validated market gate response: %s", parsed)

            hardened = self._apply_guardrails(parsed, fallback)
            logger.info("Final hardened market gate response: %s", hardened)

            return self._with_metadata(
                hardened,
                context=context,
                gpt_used=True,
                fallback_used=False,
            )
        except Exception as e:
            logger.exception("OpenAI market analysis failed: %s", e)
            return self._with_metadata(
                fallback,
                context=context,
                gpt_used=False,
                fallback_used=True,
                fallback_reason=self._safe_exc_message(e),
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

    def _rule_based_analysis(self, indicators: dict[str, Any]) -> dict[str, Any]:
        if not indicators:
            return {
                "market_regime": "unknown",
                "entry_bias": "neutral",
                "entry_allowed": False,
                "market_confidence": 0.20,
                "reason": "Insufficient indicator history; conservative HOLD-safe fallback.",
            }

        ema20 = float(indicators.get("ema20", 0) or 0)
        ema50 = float(indicators.get("ema50", 0) or 0)
        rsi = float(indicators.get("rsi", 50) or 50)
        short_momentum = float(indicators.get("short_momentum", 0) or 0)
        price = max(float(indicators.get("price", 0) or 0), 1e-9)

        trend_up = ema20 > ema50
        momentum_ok = short_momentum > 0
        rsi_mid = 45 <= rsi <= 70

        allowed = bool(trend_up and momentum_ok and rsi_mid)
        spread = abs(ema20 - ema50) / price
        regime = "trend" if spread > 0.002 else "range"
        confidence = 0.70 if allowed else 0.45

        return {
            "market_regime": regime,
            "entry_bias": "long" if trend_up else "neutral",
            "entry_allowed": allowed,
            "market_confidence": confidence,
            "reason": (
                "Conservative quant-first gate active; "
                "entry blocked unless trend, momentum, and RSI alignment hold."
            ),
        }

    def _build_prompt(
        self,
        symbol: str,
        indicators: dict[str, Any],
        context: MarketGateContext,
    ) -> tuple[str, str]:
        system_prompt = (
            "You are a conservative market-entry gate assistant for an auto-trading MVP.\n"
            "Quant indicators are primary. Website context is secondary and may be stale or noisy.\n"
            "Default to hold-safe behavior.\n"
            "If quant and website context conflict, prefer no entry.\n"
            "If confidence is unclear, set entry_allowed to false.\n"
            "Do not approve orders. The risk engine is the final authority.\n"
            "Return JSON only. No markdown fences. No commentary outside JSON.\n"
            "Use exactly these keys and allowed values:\n"
            "- market_regime: one of ['unknown', 'range', 'trend']\n"
            "- entry_bias: one of ['neutral', 'long']\n"
            "- entry_allowed: boolean\n"
            "- market_confidence: number between 0 and 1\n"
            "- reason: string\n"
        )

        prompt_payload = {
            "symbol": symbol,
            "indicators": indicators,
            "cached_site_summaries": context.cached_site_summaries,
            "notes": {
                "website_context_secondary": True,
                "used_cache": context.used_cache,
                "refreshed_this_run": context.refreshed_this_run,
                "summary_count": len(context.cached_site_summaries),
                "default_behavior": "hold_safe",
            },
        }

        user_prompt = json.dumps(prompt_payload, ensure_ascii=False)
        return system_prompt, user_prompt

    def _call_openai(
        self,
        *,
        symbol: str,
        indicators: dict[str, Any],
        context: MarketGateContext,
    ) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("OpenAI client is not initialized")

        system_prompt, user_prompt = self._build_prompt(symbol, indicators, context)

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
        logger.info("OpenAI output_text: %s", raw_text)

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
            "volatile": "range",
        }
        result["market_regime"] = regime_map.get(regime, "unknown")

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
        }
        result["entry_bias"] = bias_map.get(bias, "neutral")

        entry_allowed = result.get("entry_allowed", False)
        if isinstance(entry_allowed, str):
            result["entry_allowed"] = entry_allowed.strip().lower() == "true"
        else:
            result["entry_allowed"] = bool(entry_allowed)

        try:
            confidence = float(result.get("market_confidence", 0) or 0)
        except Exception:
            confidence = 0.0

        if confidence > 1.0:
            # Best effort: if model returns 70 instead of 0.70
            confidence = confidence / 100.0

        result["market_confidence"] = max(0.0, min(confidence, 1.0))

        reason = str(result.get("reason", "") or "").strip()
        result["reason"] = reason or "Model returned no reason."

        return result

    def _apply_guardrails(
        self,
        payload: dict[str, Any],
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        result = dict(payload)

        try:
            result["market_confidence"] = float(result.get("market_confidence", 0) or 0)
        except Exception:
            result["market_confidence"] = 0.0

        if result["market_confidence"] < self.market_gate_min_confidence:
            result["entry_allowed"] = False

        trend_up = fallback.get("entry_bias") == "long"
        if not trend_up:
            result["entry_allowed"] = False

        if not bool(result.get("entry_allowed", False)):
            result["entry_allowed"] = False
            result["entry_bias"] = "neutral"

        result["reason"] = str(result.get("reason", "") or "").strip()
        if not result["reason"]:
            result["reason"] = (
                "Model returned no reason; conservative HOLD-safe fallback applied."
            )

        return result

    def _with_metadata(
        self,
        payload: dict[str, Any],
        *,
        context: MarketGateContext,
        gpt_used: bool,
        fallback_used: bool,
        fallback_reason: str | None = None,
    ) -> dict[str, Any]:
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
        result["audit"] = {
            "gpt_used": gpt_used,
            "fallback_used": fallback_used,
            "used_cached_website_context": context.used_cache,
            "refreshed_cache_this_run": context.refreshed_this_run,
            "site_summary_count": len(context.cached_site_summaries),
            "fallback_reason": fallback_reason,
        }
        result["site_summaries"] = context.cached_site_summaries
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
            market_confidence=float(payload.get("market_confidence", 0) or 0),
            risk_note=payload.get("risk_note") or payload.get("reason"),
            macro_summary=payload.get("macro_summary"),
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
    ) -> MarketAnalysis:
        payload = self.analyze(db, symbol, indicators)
        return self.save_analysis(db, symbol, payload)