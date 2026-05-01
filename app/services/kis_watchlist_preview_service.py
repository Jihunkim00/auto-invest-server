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
    action: str = "hold"
    risk_flags: list[str] | None = None
    gating_notes: list[str] | None = None
    hard_block_reason: str | None = None


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

        trade_result = {
            "action": "hold",
            "risk_approved": False,
            "approved_by_risk": False,
            "order_id": None,
            "reason": "kr_trading_disabled",
            "risk_flags": ["kr_trading_disabled", "preview_only"],
            "gating_notes": [
                "Shared risk schema applied for preview; KIS trading is disabled."
            ],
        }

        return {
            "market": "KR",
            "provider": "kis",
            "currency": profile.currency,
            "timezone": profile.timezone,
            "dry_run": True,
            "preview_only": True,
            "trading_enabled": False,
            "gpt_analysis_included": gpt_used,
            "watchlist_source": watchlist.get("watchlist_file"),
            "watchlist_file": watchlist.get("watchlist_file"),
            "reference_sites_file": references.get("reference_sites_file"),
            "configured_symbol_count": len(configured_symbols),
            "analyzed_symbol_count": len(items),
            "max_watchlist_size": self.limit,
            "watchlist": items,
            "quant_candidates_count": 0,
            "researched_candidates_count": 0,
            "final_best_candidate": None,
            "second_final_candidate": None,
            "tied_final_candidates": [],
            "near_tied_candidates": [],
            "tie_breaker_applied": False,
            "final_candidate_selection_reason": (
                "KR preview only; trading disabled."
            ),
            "best_score": None,
            "final_score_gap": None,
            "min_entry_score": None,
            "min_score_gap": None,
            "should_trade": False,
            "triggered_symbol": None,
            "trigger_block_reason": "kr_trading_disabled",
            "final_entry_ready": False,
            "final_action_hint": "watch",
            "action": "hold",
            "order_id": None,
            "result": "preview_only",
            "reason": "kr_trading_disabled",
            "trade_result": trade_result,
            "market_session": self._public_session(market_session),
            "warnings": _dedupe(KR_DISABLED_REASONS + session_warnings),
            "top_quant_candidates": [],
            "researched_candidates": [],
            "final_ranked_candidates": items,
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
        risk_flags = ["kr_trading_disabled", "preview_only"]
        gating_notes = [
            "Shared signal/risk vocabulary is used for KR preview.",
            "KR preview uses the shared signal/risk vocabulary but trading is disabled.",
            "No real KIS order submitted.",
        ]
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
            if "gpt_unavailable" in gpt.warnings:
                risk_flags.append("gpt_unavailable")
            if gpt.risk_flags:
                risk_flags.extend(gpt.risk_flags)
            if gpt.gating_notes:
                gating_notes.extend(gpt.gating_notes)

        reason = (
            "Only current price is available; technical indicator score was not calculated."
            if indicator_status == "price_only"
            else "Current price and technical indicator data are unavailable."
        )
        note = (
            "Price-only preview; technical indicators not calculated yet."
            if indicator_status == "price_only"
            else "Insufficient data; technical indicators not calculated yet."
        )

        return {
            "symbol": symbol,
            "name": name or None,
            "market": listing_market,
            "currency": "KRW",
            "current_price": current_price,
            "score": None,
            "note": note,
            "indicator_status": indicator_status,
            "indicator_payload": dict(EMPTY_INDICATORS),
            "quant_buy_score": None,
            "quant_sell_score": None,
            "ai_buy_score": None,
            "ai_sell_score": None,
            "final_buy_score": None,
            "final_sell_score": None,
            "confidence": None,
            "action": "hold",
            "action_hint": self._normalize_action_hint(gpt.action_hint),
            "entry_ready": False,
            "trade_allowed": False,
            "approved_by_risk": False,
            "risk_flags": _dedupe(risk_flags),
            "gating_notes": _dedupe(gating_notes),
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
                action="hold",
                risk_flags=["gpt_unavailable"],
                gating_notes=["GPT advisory unavailable; price-only preview kept hold/watch."],
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
                action="hold",
                risk_flags=["gpt_unavailable"],
                gating_notes=["GPT advisory unavailable; price-only preview kept hold/watch."],
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
            "You are the same conservative, quant-first market advisory layer "
            "used by the US/Alpaca watchlist flow, with KR/KIS market context. "
            "This is read-only preview analysis only.\n"
            "Quant indicators are primary. GPT only explains or contextualizes "
            "the available data. Do not produce numeric scores unless real "
            "indicator values are provided in the prompt.\n"
            "Use KR market context, KRW, Asia/Seoul session context, KIS "
            "current price/account data, KIS Domestic Stock API, KRX, OpenDART, "
            "and KIND reference sources as secondary context. Do not rely "
            "primarily on news sentiment.\n"
            "Do not approve real trading, do not produce order payloads, and "
            "do not write buy/sell as executable instructions.\n"
            "If indicators are missing, say analysis is limited. If market is "
            "closed or holiday, mention it. Since KR trading is disabled, "
            "entry_ready and trade_allowed must be false.\n"
            "Return JSON only. Use keys: ai_buy_score, ai_sell_score, "
            "confidence, action, reason, risk_flags, gating_notes, "
            "hard_block_reason. Optional action_hint is allowed. action must "
            "be one of buy, sell, hold; default to hold."
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
                    "Keep ai_buy_score, ai_sell_score, and confidence null when indicators are missing.",
                    "Default action to hold and action_hint to watch unless there is strong avoid risk.",
                    "Never output executable buy/sell instructions.",
                    "entry_ready and trade_allowed are false because KR trading is disabled.",
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
        action = str(payload.get("action") or "hold").strip().lower()
        if action not in {"buy", "sell", "hold"}:
            action = "hold"
        if indicator_status != "ok":
            action = "hold"

        action_hint = str(payload.get("action_hint") or "").strip().lower()
        if not action_hint:
            action_hint = {
                "buy": "candidate",
                "sell": "avoid",
                "hold": "watch",
            }.get(action, "watch")
        if action_hint not in {"watch", "avoid", "candidate"}:
            action_hint = "watch"
        if indicator_status != "ok" and action_hint == "candidate":
            action_hint = "watch"
        reason = str(payload.get("reason") or payload.get("gpt_reason") or "").strip()
        risk_flags = _string_list(payload.get("risk_flags"))
        gating_notes = _string_list(payload.get("gating_notes"))
        hard_block_reason = payload.get("hard_block_reason")
        if hard_block_reason is not None:
            hard_block_reason = str(hard_block_reason)
        return KisGptPreview(
            gpt_used=True,
            action_hint=action_hint,
            gpt_reason=reason or "GPT advisory context only. No executable trade decision.",
            warnings=[],
            action=action,
            risk_flags=risk_flags,
            gating_notes=gating_notes,
            hard_block_reason=hard_block_reason,
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


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
