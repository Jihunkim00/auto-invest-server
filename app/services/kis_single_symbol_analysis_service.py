from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.core.constants import AI_WEIGHT, DEFAULT_GATE_LEVEL, QUANT_WEIGHT, get_gate_profile
from app.services.quant_signal_service import QuantSignalService
from app.services.technical_indicator_service import (
    EMPTY_TECHNICAL_INDICATORS,
    TechnicalIndicatorService,
    indicator_payload_is_quant_ready,
)
from app.services.watchlist_research_service import WatchlistResearchService


class KisSingleSymbolAnalysisService:
    """Read-only KIS/quant/market-GPT analysis for one Korean stock.

    This service deliberately stops at analysis. It never creates an order,
    calls validation, or invokes the single-symbol trading service.
    """

    def __init__(
        self,
        client: Any,
        *,
        settings: Any | None = None,
        indicator_service: TechnicalIndicatorService | None = None,
        quant_signal_service: QuantSignalService | None = None,
        research_service: WatchlistResearchService | None = None,
    ) -> None:
        self.client = client
        self.settings = settings or get_settings()
        self.indicator_service = indicator_service or TechnicalIndicatorService()
        self.quant_signal_service = quant_signal_service or QuantSignalService()
        self.research_service = research_service or WatchlistResearchService()

    def analyze(
        self,
        db,
        *,
        symbol: str,
        symbol_name: str | None = None,
        market: str = "KR",
        gate_level: int | None = None,
    ) -> dict[str, Any]:
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_market = str(market or "KR").strip().upper()
        resolved_gate_level = gate_level if gate_level is not None else DEFAULT_GATE_LEVEL
        base = self._base_result(
            symbol=normalized_symbol,
            symbol_name=symbol_name,
            market=normalized_market,
            gate_level=resolved_gate_level,
        )

        if not normalized_symbol:
            return self._unavailable(base, reason="market_data_unavailable", note="missing_symbol")
        if normalized_market != "KR":
            return self._unavailable(base, reason="market_data_unavailable", note="kis_analysis_requires_kr_market")

        try:
            quote = self.client.get_domestic_stock_price(normalized_symbol)
        except Exception as exc:
            return self._unavailable(
                base,
                reason="market_data_unavailable",
                note=self._safe_error(exc),
            )

        current_price = self._number(quote.get("current_price")) if isinstance(quote, dict) else None
        if current_price is None or current_price <= 0:
            return self._unavailable(
                {
                    **base,
                    "symbol_name": self._quote_name(quote, symbol_name),
                    "timestamp": self._quote_timestamp(quote),
                },
                reason="market_data_unavailable",
                note="current_price_unavailable",
            )

        enriched_base = {
            **base,
            "symbol_name": self._quote_name(quote, symbol_name),
            "current_price": current_price,
            "timestamp": self._quote_timestamp(quote),
        }

        try:
            bars = self.client.get_domestic_daily_bars(normalized_symbol, limit=120)
        except Exception as exc:
            return self._unavailable(
                enriched_base,
                reason="market_data_unavailable",
                note=self._safe_error(exc),
            )

        indicator_result = self.indicator_service.calculate(
            bars or [],
            current_price=current_price,
        )
        indicator_payload = dict(
            indicator_result.get("indicator_payload") or EMPTY_TECHNICAL_INDICATORS
        )
        indicator_status = str(
            indicator_result.get("indicator_status") or "insufficient_data"
        )
        bar_count = int(indicator_result.get("bar_count") or 0)
        result = {
            **enriched_base,
            "indicator_status": indicator_status,
            "indicator_bar_count": bar_count,
            "indicators": self._public_indicators(indicator_payload),
            "indicator_payload": indicator_payload,
        }

        if not indicator_payload_is_quant_ready(indicator_payload):
            return self._insufficient_data(result)

        quant = self.quant_signal_service.score(
            indicator_payload,
            gate_level=resolved_gate_level,
        )
        quant_buy = self._number(quant.get("quant_buy_score"))
        quant_sell = self._number(quant.get("quant_sell_score"))
        result.update(
            {
                "quant_buy_score": quant_buy,
                "quant_sell_score": quant_sell,
                "quant_reason": quant.get("quant_reason"),
                "quant_notes": self._string_list(quant.get("quant_notes")),
            }
        )

        try:
            research = self.research_service.analyze_candidate(
                db=db,
                symbol=normalized_symbol,
                indicators=indicator_payload,
                gate_level=resolved_gate_level,
                market=normalized_market,
            )
        except Exception as exc:
            return self._gpt_failure(
                result,
                quant=quant,
                note=self._safe_error(exc),
            )

        return self._complete(result, quant=quant, research=research)

    def _complete(
        self,
        result: dict[str, Any],
        *,
        quant: dict[str, Any],
        research: dict[str, Any],
    ) -> dict[str, Any]:
        gpt_context = research.get("gpt_context") if isinstance(research.get("gpt_context"), dict) else {}
        audit = gpt_context.get("audit") if isinstance(gpt_context.get("audit"), dict) else {}
        fallback_used = bool(research.get("fallback_used") or audit.get("fallback_used"))
        market_gpt_used = not fallback_used and bool(
            gpt_context.get("gpt_buy_score") is not None
            or gpt_context.get("gpt_sell_score") is not None
        )
        gpt_buy = self._number(gpt_context.get("gpt_buy_score")) if market_gpt_used else None
        gpt_sell = self._number(gpt_context.get("gpt_sell_score")) if market_gpt_used else None
        confidence = self._number(gpt_context.get("confidence")) if market_gpt_used else None
        if market_gpt_used and confidence is None:
            confidence = self._number(research.get("confidence"))
        final_buy = self._blend(result.get("quant_buy_score"), gpt_buy)
        final_sell = self._blend(result.get("quant_sell_score"), gpt_sell)
        risk_flags = self._string_list(research.get("risk_flags"))
        gating_notes = self._string_list(research.get("gating_notes"))
        reason = str(
            research.get("market_research_reason")
            or result.get("quant_reason")
            or "Analysis completed from KIS OHLCV data."
        ).strip()

        if fallback_used:
            risk_flags = self._dedupe([*risk_flags, "market_gpt_unavailable"])
            gating_notes = self._dedupe(
                [*gating_notes, "Market GPT failed or was unavailable; quant result was preserved."]
            )
            reason = "Market GPT analysis unavailable; quant result preserved and HOLD enforced."

        action = self._action(
            final_buy=final_buy,
            final_sell=final_sell,
            confidence=confidence,
            research=research,
            fallback_used=fallback_used,
        )
        if action == "hold" and not fallback_used:
            reason = self._hold_reason(reason, final_buy, final_sell, gate_level=result.get("gate_level"))

        result.update(
            {
                "result_type": "analysis_result",
                "analysis_only": True,
                "preview_only": True,
                "gpt_buy_score": gpt_buy,
                "gpt_sell_score": gpt_sell,
                "gpt_reason": gpt_context.get("reason") if market_gpt_used else None,
                "final_buy_score": final_buy,
                "final_sell_score": final_sell,
                "confidence": confidence,
                "action": action,
                "reason": reason,
                "risk_flags": self._dedupe(risk_flags),
                "gating_notes": self._dedupe(gating_notes),
                "market_gpt_used": market_gpt_used,
                "market_gpt_fallback_used": fallback_used,
                "market_gpt_reason": gpt_context.get("reason") if market_gpt_used else None,
                "gpt_used": market_gpt_used,
                "fallback_used": fallback_used,
                "market_model": getattr(self.settings, "openai_model", None),
                "market_reasoning_effort": getattr(
                    self.settings, "openai_reasoning_effort", None
                ),
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        )
        return result

    def _gpt_failure(
        self,
        result: dict[str, Any],
        *,
        quant: dict[str, Any],
        note: str,
    ) -> dict[str, Any]:
        result.update(
            {
                "result_type": "analysis_result",
                "analysis_only": True,
                "preview_only": True,
                "gpt_buy_score": None,
                "gpt_sell_score": None,
                "final_buy_score": self._number(quant.get("quant_buy_score")),
                "final_sell_score": self._number(quant.get("quant_sell_score")),
                "confidence": None,
                "action": "hold",
                "reason": "Market GPT analysis unavailable; quant result preserved and HOLD enforced.",
                "risk_flags": ["market_gpt_unavailable"],
                "gating_notes": [note, "Market GPT failed; no fabricated GPT score was used."],
                "market_gpt_used": False,
                "market_gpt_fallback_used": True,
                "gpt_used": False,
                "fallback_used": True,
                "market_model": getattr(self.settings, "openai_model", None),
                "market_reasoning_effort": getattr(
                    self.settings, "openai_reasoning_effort", None
                ),
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        )
        return result

    def _insufficient_data(self, result: dict[str, Any]) -> dict[str, Any]:
        result.update(
            {
                "result_type": "analysis_result",
                "analysis_only": True,
                "preview_only": True,
                "quant_buy_score": None,
                "quant_sell_score": None,
                "gpt_buy_score": None,
                "gpt_sell_score": None,
                "final_buy_score": None,
                "final_sell_score": None,
                "confidence": None,
                "action": "hold",
                "reason": "insufficient_data",
                "risk_flags": ["insufficient_data"],
                "gating_notes": [
                    "OHLCV history is insufficient for EMA/RSI/VWAP/ATR-based analysis.",
                    "Market GPT was not called because grounded indicator data was unavailable.",
                ],
                "market_gpt_used": False,
                "gpt_used": False,
                "fallback_used": True,
                "market_model": getattr(self.settings, "openai_model", None),
                "market_reasoning_effort": getattr(
                    self.settings, "openai_reasoning_effort", None
                ),
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        )
        return result

    def _unavailable(
        self,
        result: dict[str, Any],
        *,
        reason: str,
        note: str,
    ) -> dict[str, Any]:
        result.update(
            {
                "result_type": "analysis_result",
                "analysis_only": True,
                "preview_only": True,
                "current_price": result.get("current_price"),
                "indicators": self._public_indicators(EMPTY_TECHNICAL_INDICATORS),
                "indicator_payload": dict(EMPTY_TECHNICAL_INDICATORS),
                "quant_buy_score": None,
                "quant_sell_score": None,
                "gpt_buy_score": None,
                "gpt_sell_score": None,
                "final_buy_score": None,
                "final_sell_score": None,
                "confidence": None,
                "action": "hold",
                "reason": reason,
                "risk_flags": [reason],
                "gating_notes": [note, "No fabricated market data was used."],
                "market_gpt_used": False,
                "gpt_used": False,
                "fallback_used": True,
                "market_model": getattr(self.settings, "openai_model", None),
                "market_reasoning_effort": getattr(
                    self.settings, "openai_reasoning_effort", None
                ),
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        )
        return result

    def _base_result(
        self,
        *,
        symbol: str,
        symbol_name: str | None,
        market: str,
        gate_level: int,
    ) -> dict[str, Any]:
        return {
            "result_type": "analysis_result",
            "analysis_only": True,
            "preview_only": True,
            "symbol": symbol,
            "symbol_name": symbol_name or symbol or None,
            "market": market,
            "provider": "kis",
            "currency": "KRW",
            "current_price": None,
            "timestamp": None,
            "indicator_status": "unavailable",
            "indicator_bar_count": 0,
            "indicators": self._public_indicators(EMPTY_TECHNICAL_INDICATORS),
            "indicator_payload": dict(EMPTY_TECHNICAL_INDICATORS),
            "gate_level": gate_level,
        }

    def _action(
        self,
        *,
        final_buy: float | None,
        final_sell: float | None,
        confidence: float | None,
        research: dict[str, Any],
        fallback_used: bool,
    ) -> str:
        if fallback_used or final_buy is None or final_sell is None:
            return "hold"
        if bool(research.get("hard_blocked")) or research.get("entry_allowed") is False:
            return "hold"
        profile = get_gate_profile(research.get("gate_level") or DEFAULT_GATE_LEVEL)
        if (
            final_buy >= profile.min_buy_score
            and final_buy - final_sell >= profile.min_score_spread
            and (confidence is None or confidence >= profile.min_confidence_to_trade)
        ):
            return "buy"
        if (
            final_sell >= profile.min_sell_score
            and final_sell - final_buy >= profile.min_score_spread
        ):
            return "sell"
        return "hold"

    def _hold_reason(
        self,
        reason: str,
        final_buy: float | None,
        final_sell: float | None,
        gate_level: int | None = None,
    ) -> str:
        if final_buy is None or final_sell is None:
            return reason
        profile = get_gate_profile(gate_level or DEFAULT_GATE_LEVEL)
        if final_buy < profile.min_buy_score:
            return f"Entry threshold not met ({final_buy:.2f} < {profile.min_buy_score:.2f}); {reason}"
        return reason

    @staticmethod
    def _blend(quant_score: Any, gpt_score: Any) -> float | None:
        quant = KisSingleSymbolAnalysisService._number(quant_score)
        gpt = KisSingleSymbolAnalysisService._number(gpt_score)
        if quant is None and gpt is None:
            return None
        if quant is None:
            return round(gpt, 2)
        if gpt is None:
            return round(quant, 2)
        return round((quant * QUANT_WEIGHT) + (gpt * AI_WEIGHT), 2)

    @staticmethod
    def _public_indicators(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ema20": payload.get("ema20"),
            "ema50": payload.get("ema50"),
            "rsi": payload.get("rsi"),
            "vwap": payload.get("vwap"),
            "atr": payload.get("atr"),
            "volume_ratio": payload.get("volume_ratio"),
            "momentum": payload.get("momentum", payload.get("short_momentum")),
            "recent_return": payload.get("recent_return"),
            "price_position": payload.get("price_position"),
        }

    @staticmethod
    def _normalize_symbol(symbol: Any) -> str:
        value = str(symbol or "").strip().upper()
        return value.zfill(6) if value.isdigit() and len(value) < 6 else value

    @staticmethod
    def _quote_name(quote: Any, fallback: str | None) -> str | None:
        if isinstance(quote, dict):
            name = str(quote.get("name") or "").strip()
            if name:
                return name
        return str(fallback or "").strip() or None

    @staticmethod
    def _quote_timestamp(quote: Any) -> str | None:
        if not isinstance(quote, dict):
            return None
        value = quote.get("timestamp") or quote.get("updated_at")
        return str(value).strip() if value is not None else None

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            if value is None or str(value).strip() == "":
                return None
            numeric = float(str(value).replace(",", "").strip())
            return numeric if numeric == numeric and abs(numeric) != float("inf") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value if str(item).strip()]
        text = str(value or "").strip()
        return [text] if text else []

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            if value and value not in result:
                result.append(value)
        return result

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        text = str(exc).strip() or exc.__class__.__name__
        return f"{exc.__class__.__name__}: {text[:180]}"
