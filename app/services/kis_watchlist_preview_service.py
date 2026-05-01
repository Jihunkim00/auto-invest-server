from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from app.brokers.kis_client import KisClient, to_float
from app.config import get_settings
from app.services.market_profile_service import MarketProfileService
from app.services.market_session_service import MarketSessionService

KR_PREVIEW_LIMIT = 8
KR_DISABLED_REASONS = ["preview_only", "kr_trading_disabled"]
EMPTY_INDICATORS = {
    "ema20": None,
    "ema50": None,
    "rsi": None,
    "vwap": None,
    "atr": None,
    "volume_ratio": None,
    "momentum": None,
}


@dataclass(frozen=True)
class KisGptPreview:
    gpt_used: bool
    action_hint: str
    gpt_reason: str
    warnings: list[str]


class KisWatchlistPreviewService:
    """Read-only, quant-first KR watchlist preview.

    This service never submits orders, never calls the trading service, and
    never asks the risk engine for order approval.
    """

    def __init__(
        self,
        client: KisClient,
        *,
        profile_service: MarketProfileService | None = None,
        session_service: MarketSessionService | None = None,
        gpt_advisor: "KisPreviewGptAdvisor | None" = None,
        limit: int = KR_PREVIEW_LIMIT,
    ):
        self.client = client
        self.profile_service = profile_service or MarketProfileService()
        self.session_service = session_service or MarketSessionService()
        self.gpt_advisor = gpt_advisor or KisPreviewGptAdvisor()
        self.limit = max(1, min(int(limit), KR_PREVIEW_LIMIT))

    def run_preview(self, *, include_gpt: bool = True) -> dict[str, Any]:
        profile = self.profile_service.get_profile("KR")
        watchlist = self.profile_service.load_watchlist("KR")
        references = self.profile_service.load_reference_sites("KR")
        market_session = self.session_service.get_session_status("KR")
        session_warnings = self._session_warnings(market_session)
        configured_symbols = watchlist["symbols"][: self.limit]

        items = []
        gpt_used = False
        for raw in configured_symbols:
            item = self._preview_symbol(
                raw,
                market_session=market_session,
                session_warnings=session_warnings,
                reference_sources=references.get("sources") or [],
                include_gpt=include_gpt,
            )
            gpt_used = gpt_used or bool(item.get("gpt_used"))
            items.append(item)

        return {
            "market": "KR",
            "provider": "kis",
            "currency": profile.currency,
            "timezone": profile.timezone,
            "dry_run": True,
            "preview_only": True,
            "trading_enabled": False,
            "gpt_analysis_included": gpt_used,
            "watchlist_file": watchlist.get("watchlist_file"),
            "reference_sites_file": references.get("reference_sites_file"),
            "configured_symbol_count": len(configured_symbols),
            "analyzed_symbol_count": len(items),
            "quant_candidates_count": 0,
            "researched_candidates_count": 0,
            "final_best_candidate": None,
            "second_final_candidate": None,
            "tied_final_candidates": [],
            "near_tied_candidates": [],
            "tie_breaker_applied": False,
            "final_candidate_selection_reason": (
                "KR preview is price-only until KIS OHLCV indicators are available."
            ),
            "best_score": None,
            "final_score_gap": None,
            "should_trade": False,
            "triggered_symbol": None,
            "trigger_block_reason": "kr_trading_disabled",
            "action": "hold",
            "result": "preview_only",
            "reason": "kr_trading_disabled",
            "market_session": self._public_session(market_session),
            "warnings": _dedupe(KR_DISABLED_REASONS + session_warnings),
            "top_quant_candidates": [],
            "researched_candidates": [],
            "final_ranked_candidates": [],
            "items": items,
            "count": len(items),
        }

    def _preview_symbol(
        self,
        raw: dict[str, Any],
        *,
        market_session: dict[str, Any],
        session_warnings: list[str],
        reference_sources: list[dict[str, Any]],
        include_gpt: bool,
    ) -> dict[str, Any]:
        symbol = self.profile_service.normalize_symbol(raw.get("symbol"), "KR")
        name = str(raw.get("name") or "")
        listing_market = str(raw.get("market") or "KR")
        warnings = _dedupe(KR_DISABLED_REASONS + session_warnings)
        block_reasons = list(KR_DISABLED_REASONS)
        current_price: float | None = None
        price_error: str | None = None

        try:
            price = self.client.get_domestic_stock_price(symbol)
            current_price = to_float(price.get("current_price"))
            if not name:
                name = str(price.get("name") or "")
            if current_price <= 0:
                current_price = None
                warnings.append("current_price_unavailable")
                block_reasons.append("current_price_unavailable")
        except Exception as exc:
            warnings.append("current_price_unavailable")
            block_reasons.append("current_price_unavailable")
            price_error = _safe_error(exc)

        # TODO: Add KIS OHLCV/daily chart integration here. Until real bars are
        # available, do not calculate or display technical scores.
        indicator_status = "price_only" if current_price is not None else "insufficient_data"
        block_reason = (
            "insufficient_indicator_data"
            if current_price is not None
            else "current_price_unavailable"
        )
        if block_reason not in block_reasons:
            block_reasons.append(block_reason)

        gpt = KisGptPreview(
            gpt_used=False,
            action_hint="watch",
            gpt_reason="Advisory context only. No executable trade decision.",
            warnings=[],
        )
        if include_gpt:
            gpt = self.gpt_advisor.analyze(
                symbol=symbol,
                name=name,
                current_price=current_price,
                indicator_status=indicator_status,
                indicator_payload=EMPTY_INDICATORS,
                market_session=market_session,
                reference_sources=reference_sources,
            )
            warnings.extend(gpt.warnings)

        reason = (
            "Only current price is available; technical indicator score was not calculated."
            if indicator_status == "price_only"
            else "Current price and technical indicator data are unavailable."
        )

        return {
            "symbol": symbol,
            "name": name or None,
            "market": listing_market,
            "currency": "KRW",
            "current_price": current_price,
            "indicator_status": indicator_status,
            "indicator_payload": dict(EMPTY_INDICATORS),
            "quant_buy_score": None,
            "quant_sell_score": None,
            "ai_buy_score": None,
            "ai_sell_score": None,
            "final_buy_score": None,
            "final_sell_score": None,
            "confidence": None,
            "action_hint": self._normalize_action_hint(gpt.action_hint),
            "entry_ready": False,
            "trade_allowed": False,
            "block_reason": block_reason,
            "reason": reason,
            "gpt_reason": gpt.gpt_reason,
            "warnings": _dedupe(warnings),
            "block_reasons": _dedupe(block_reasons),
            "error": price_error,
            "gpt_used": gpt.gpt_used,
        }

    @staticmethod
    def _normalize_action_hint(value: str) -> str:
        normalized = str(value or "watch").strip().lower()
        if normalized in {"candidate", "watch", "avoid"}:
            return normalized
        if normalized in {"buy", "long", "enter"}:
            return "candidate"
        if normalized in {"sell", "short", "exit"}:
            return "avoid"
        return "watch"

    @staticmethod
    def _session_warnings(market_session: dict[str, Any]) -> list[str]:
        warnings = []
        if not market_session.get("is_market_open"):
            warnings.append("market_closed")
            closure_reason = market_session.get("closure_reason")
            if closure_reason:
                warnings.append(str(closure_reason))
        return warnings

    @staticmethod
    def _public_session(market_session: dict[str, Any]) -> dict[str, Any]:
        keys = [
            "market",
            "timezone",
            "is_market_open",
            "is_entry_allowed_now",
            "is_near_close",
            "closure_reason",
            "closure_name",
            "effective_close",
            "no_new_entry_after",
        ]
        return {key: market_session.get(key) for key in keys}


class KisPreviewGptAdvisor:
    def __init__(self, settings=None, client: OpenAI | None = None):
        self.settings = settings or get_settings()
        self.client = client
        if self.client is None and self.settings.openai_api_key:
            self.client = OpenAI(api_key=self.settings.openai_api_key)

    def analyze(
        self,
        *,
        symbol: str,
        name: str,
        current_price: float | None,
        indicator_status: str,
        indicator_payload: dict[str, Any],
        market_session: dict[str, Any],
        reference_sources: list[dict[str, Any]],
    ) -> KisGptPreview:
        if self.client is None:
            return KisGptPreview(
                gpt_used=False,
                action_hint="watch",
                gpt_reason=(
                    "GPT advisory unavailable; analysis is limited to KIS current price."
                ),
                warnings=["gpt_unavailable"],
            )

        try:
            payload = self._call_openai(
                symbol=symbol,
                name=name,
                current_price=current_price,
                indicator_status=indicator_status,
                indicator_payload=indicator_payload,
                market_session=market_session,
                reference_sources=reference_sources,
            )
            return self._normalize_payload(payload, indicator_status=indicator_status)
        except Exception as exc:
            return KisGptPreview(
                gpt_used=False,
                action_hint="watch",
                gpt_reason=(
                    "GPT advisory unavailable; quant/price-only fallback: "
                    f"{_safe_error(exc)}"
                ),
                warnings=["gpt_unavailable"],
            )

    def _call_openai(
        self,
        *,
        symbol: str,
        name: str,
        current_price: float | None,
        indicator_status: str,
        indicator_payload: dict[str, Any],
        market_session: dict[str, Any],
        reference_sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if self.client is None:
            raise ValueError("OpenAI client is not initialized.")

        system_prompt = (
            "You are a KR/KIS watchlist advisory assistant for a conservative "
            "personal dashboard. This is read-only preview analysis only.\n"
            "Quant indicators are primary. GPT only explains or contextualizes "
            "the available data. Do not produce numeric scores unless real "
            "indicator values are provided in the prompt.\n"
            "Use Korean market context, KRW, Asia/Seoul session context, KIS "
            "current price/account data, and official/reference sources as "
            "secondary context. Do not rely primarily on news sentiment.\n"
            "Do not approve real trading, do not produce order payloads, and "
            "do not write buy/sell as executable instructions.\n"
            "If indicators are missing, say analysis is limited. If market is "
            "closed or holiday, mention it. Since KR trading is disabled, "
            "entry_ready must be false.\n"
            "Return JSON only with keys: action_hint, gpt_reason. action_hint "
            "must be one of watch, avoid, candidate."
        )
        reference_context = [
            {
                "name": source.get("name"),
                "type": source.get("type"),
                "purpose": source.get("purpose"),
                "enabled": source.get("enabled"),
            }
            for source in reference_sources
            if isinstance(source, dict)
        ]
        user_prompt = json.dumps(
            {
                "market": "KR",
                "provider": "kis",
                "currency": "KRW",
                "timezone": "Asia/Seoul",
                "symbol": symbol,
                "name": name,
                "current_price": current_price,
                "indicator_status": indicator_status,
                "indicator_payload": indicator_payload,
                "trading_enabled": False,
                "preview_only": True,
                "market_session": market_session,
                "reference_sources": reference_context,
                "instructions": [
                    "Prefer quant indicators and KIS data.",
                    "If indicators are null, do not create a score.",
                    "Default action_hint to watch unless there is strong avoid risk.",
                    "Never output executable buy/sell instructions.",
                    "entry_ready is false because KR trading is disabled.",
                ],
            },
            ensure_ascii=False,
        )

        response = self.client.responses.create(
            model=self.settings.openai_model,
            reasoning={"effort": self.settings.openai_reasoning_effort},
            instructions=system_prompt,
            input=user_prompt,
        )
        raw_text = (response.output_text or "").strip()
        if not raw_text:
            raise ValueError("OpenAI returned empty output_text.")
        return _parse_json_object(raw_text)

    @staticmethod
    def _normalize_payload(payload: dict[str, Any], *, indicator_status: str) -> KisGptPreview:
        action_hint = str(payload.get("action_hint") or "watch").strip().lower()
        if action_hint not in {"watch", "avoid", "candidate"}:
            action_hint = "watch"
        if indicator_status != "ok" and action_hint == "candidate":
            action_hint = "watch"
        reason = str(payload.get("gpt_reason") or "").strip()
        return KisGptPreview(
            gpt_used=True,
            action_hint=action_hint,
            gpt_reason=reason or "GPT advisory context only. No executable trade decision.",
            warnings=[],
        )


def _parse_json_object(raw_text: str) -> dict[str, Any]:
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
            raise ValueError("Could not locate JSON object in GPT response.")
        text = text[start : end + 1]

    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("GPT response was not a JSON object.")
    return payload


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip()
    if not text:
        return exc.__class__.__name__
    if len(text) > 180:
        text = f"{text[:180]}..."
    return f"{exc.__class__.__name__}: {text}"


def _dedupe(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
