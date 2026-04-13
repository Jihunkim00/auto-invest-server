from __future__ import annotations

import json

import requests
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import MarketAnalysis
from app.services.reference_site_service import ReferenceSiteService
from app.services.web_content_service import WebContentService


class GPTMarketService:
    """
    Quant-first market-entry gate.
    Reference-site context is optional and secondary.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.openai_api_key = settings.openai_api_key
        self.openai_model = settings.openai_model
        self.reference_site_service = ReferenceSiteService(settings.reference_sites_config_path)
        self.web_content_service = WebContentService()

    def analyze(self, symbol: str, indicators: dict) -> dict:
        fallback = self._rule_based_analysis(indicators)
        if not indicators:
            return fallback

        site_summaries: list[dict] = []
        try:
            sites = self.reference_site_service.get_sites_for_symbol(symbol)
            site_summaries = self.web_content_service.build_site_summaries(sites)
        except Exception:
            site_summaries = []

        if not self.openai_api_key:
            return self._with_context(fallback, site_summaries, "OpenAI key missing; using conservative rule-based gate.")

        try:
            gpt_payload = self._call_openai(symbol=symbol, indicators=indicators, site_summaries=site_summaries)
            validated = self._validate_payload(gpt_payload, fallback)
            return self._with_context(validated, site_summaries)
        except Exception:
            return self._with_context(fallback, site_summaries, "GPT failed; reverted to conservative rule-based gate.")

    def _rule_based_analysis(self, indicators: dict) -> dict:
        if not indicators:
            return {
                "market_regime": "unknown",
                "entry_bias": "neutral",
                "entry_allowed": False,
                "market_confidence": 0.2,
                "reason": "insufficient indicator history; HOLD-safe fallback",
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
            "reason": "Conservative quant-first gate active; entry blocked unless trend+momentum align.",
        }

    def _call_openai(self, *, symbol: str, indicators: dict, site_summaries: list[dict]) -> dict:
        prompt = {
            "symbol": symbol,
            "priority_rules": [
                "1) Quant indicators are primary.",
                "2) Risk-conservative interpretation.",
                "3) Website context is secondary and optional.",
                "4) Ambiguous outcomes must set entry_allowed=false.",
            ],
            "indicators": indicators,
            "website_context": site_summaries,
            "required_output_fields": [
                "market_regime",
                "entry_bias",
                "entry_allowed",
                "market_confidence",
                "reason",
            ],
            "output_format": "json_only",
        }

        body = {
            "model": self.openai_model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "You are a conservative market gate assistant for an auto-trading MVP. Return JSON only.",
                        }
                    ],
                },
                {"role": "user", "content": [{"type": "input_text", "text": json.dumps(prompt, ensure_ascii=False)}]},
            ],
        }

        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()
        text = self._extract_response_text(data)
        return json.loads(text)

    @staticmethod
    def _extract_response_text(payload: dict) -> str:
        output = payload.get("output", [])
        for item in output:
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    return content["text"]
        raise ValueError("missing output_text")

    @staticmethod
    def _validate_payload(payload: dict, fallback: dict) -> dict:
        if not isinstance(payload, dict):
            return fallback

        market_regime = str(payload.get("market_regime") or fallback["market_regime"]).lower()
        if market_regime not in {"trend", "range", "volatile", "unknown"}:
            market_regime = fallback["market_regime"]

        entry_bias = str(payload.get("entry_bias") or fallback["entry_bias"]).lower()
        if entry_bias not in {"long", "short", "neutral"}:
            entry_bias = fallback["entry_bias"]

        try:
            confidence = float(payload.get("market_confidence", fallback["market_confidence"]))
        except (TypeError, ValueError):
            confidence = float(fallback["market_confidence"])
        confidence = min(max(confidence, 0.0), 1.0)

        entry_allowed = bool(payload.get("entry_allowed", fallback["entry_allowed"]))
        reason = str(payload.get("reason") or fallback["reason"])[:600]

        if confidence < 0.55:
            entry_allowed = False

        return {
            "market_regime": market_regime,
            "entry_bias": entry_bias,
            "entry_allowed": entry_allowed,
            "market_confidence": confidence,
            "reason": reason,
        }

    @staticmethod
    def _with_context(payload: dict, site_summaries: list[dict], fallback_message: str | None = None) -> dict:
        message = payload.get("reason", "")
        if fallback_message:
            message = f"{message} | {fallback_message}" if message else fallback_message

        enriched = dict(payload)
        enriched["reason"] = message
        enriched["risk_note"] = message
        if site_summaries:
            enriched["macro_summary"] = f"used {len(site_summaries)} reference site summaries as secondary context"
        else:
            enriched["macro_summary"] = "no reference site context used"
        enriched["site_summaries"] = site_summaries
        return enriched

    def save_analysis(self, db: Session, symbol: str, payload: dict) -> MarketAnalysis:
        row = MarketAnalysis(
            symbol=symbol.upper(),
            market_regime=payload.get("market_regime"),
            entry_bias=payload.get("entry_bias"),
            entry_allowed=bool(payload.get("entry_allowed", False)),
            market_confidence=float(payload.get("market_confidence", 0) or 0),
            risk_note=payload.get("reason") or payload.get("risk_note"),
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
