from __future__ import annotations

from datetime import datetime
from typing import Any

from app.brokers.alpaca_client import AlpacaClient
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.core.constants import AI_WEIGHT, QUANT_WEIGHT, get_gate_profile
from app.services.kis_watchlist_preview_service import KisWatchlistPreviewService
from app.services.market_session_service import MarketSessionService
from app.services.quant_signal_service import QuantSignalService
from app.services.technical_indicator_service import TechnicalIndicatorService


class UserSymbolAnalysisService:
    """Analyze exactly one requested symbol without selecting a watchlist item."""

    def __init__(
        self,
        *,
        kis_preview_service: KisWatchlistPreviewService | None = None,
        kis_client: KisClient | None = None,
        alpaca_client: AlpacaClient | None = None,
        session_service: MarketSessionService | None = None,
        indicator_service: TechnicalIndicatorService | None = None,
        quant_signal_service: QuantSignalService | None = None,
    ) -> None:
        self.kis_client = kis_client or KisClient()
        self.kis_preview_service = kis_preview_service or KisWatchlistPreviewService(
            self.kis_client,
            session_service=session_service,
        )
        self.alpaca_client = alpaca_client or AlpacaClient()
        self.session_service = session_service or MarketSessionService()
        self.indicator_service = indicator_service or TechnicalIndicatorService()
        self.quant_signal_service = quant_signal_service or QuantSignalService()

    def analyze(
        self,
        db,
        *,
        provider: str,
        symbol: str,
        gate_level: int = 2,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        normalized_provider = str(provider or "").strip().lower()
        normalized_symbol = str(symbol or "").strip().upper()
        if normalized_provider == "kis":
            return self._analyze_kis(
                db,
                symbol=normalized_symbol,
                gate_level=gate_level,
                now=now,
            )
        if normalized_provider == "alpaca":
            return self._analyze_alpaca(symbol=normalized_symbol, gate_level=gate_level)
        raise ValueError("unsupported_trading_provider")

    def _analyze_kis(
        self,
        db,
        *,
        symbol: str,
        gate_level: int,
        now: datetime | None,
    ) -> dict[str, Any]:
        try:
            market_session = self.session_service.get_session_status("KR", now=now)
        except Exception:
            market_session = {
                "market": "KR",
                "is_market_open": False,
                "is_entry_allowed_now": False,
            }
        try:
            references = self.kis_preview_service.profile_service.load_reference_sites("KR")
            reference_sources = references.get("sources") or []
        except Exception:
            reference_sources = []
        try:
            warnings = self.kis_preview_service._session_warnings(market_session)
        except Exception:
            warnings = []
        try:
            result = self.kis_preview_service._preview_symbol(
                {"symbol": symbol, "market": "KR"},
                gate_level=gate_level,
                market_session=market_session,
                session_warnings=warnings,
                reference_sources=reference_sources,
                include_gpt=True,
                db=db,
            )
        except Exception as exc:
            return self._unavailable(symbol, "KR", "KRW", exc)
        payload = dict(result or {})
        payload.update(
            {
                "provider": "kis",
                "market": "KR",
                "currency": "KRW",
                "requested_symbol": symbol,
                "analyzed_symbol": str(payload.get("symbol") or symbol).upper(),
                "returned_symbol": str(payload.get("symbol") or symbol).upper(),
                "market_session": market_session,
            }
        )
        return payload

    def _analyze_alpaca(self, *, symbol: str, gate_level: int) -> dict[str, Any]:
        try:
            latest = self.alpaca_client.get_latest_price(symbol) or {}
            price = _number(latest.get("price"))
            raw_bars = self.alpaca_client.get_recent_bars(
                symbol,
                limit=120,
                timeframe="1Day",
            )
            bars = [_normalize_alpaca_bar(bar, symbol) for bar in raw_bars or []]
            bars = [bar for bar in bars if bar is not None]
            indicators = self.indicator_service.calculate(bars, current_price=price)
            indicator_payload = indicators.get("indicator_payload") or {}
            if indicators.get("indicator_status") in {"ok", "partial"}:
                quant = self.quant_signal_service.score(
                    indicator_payload,
                    gate_level=gate_level,
                )
                quant_buy = _number(quant.get("quant_buy_score"))
                quant_sell = _number(quant.get("quant_sell_score"))
                final_buy = _blend(quant_buy, None)
                final_sell = _blend(quant_sell, None)
                confidence = max(final_buy or 0.0, final_sell or 0.0) / 100.0
                profile = get_gate_profile(gate_level)
                action = (
                    "buy"
                    if final_buy is not None
                    and final_buy >= max(65.0, profile.min_buy_score)
                    and final_sell is not None
                    and final_buy - final_sell >= profile.min_score_spread
                    else "hold"
                )
                reason = quant.get("quant_reason") or "Alpaca OHLCV indicators calculated."
            else:
                quant = {}
                quant_buy = quant_sell = final_buy = final_sell = None
                confidence = None
                action = "hold"
                reason = "insufficient_indicator_data"
            return {
                "provider": "alpaca",
                "market": "US",
                "currency": "USD",
                "symbol": symbol,
                "requested_symbol": symbol,
                "analyzed_symbol": symbol,
                "returned_symbol": symbol,
                "current_price": price,
                "indicator_status": indicators.get("indicator_status"),
                "indicator_payload": indicator_payload,
                "indicator_bar_count": indicators.get("bar_count", 0),
                "quant_buy_score": quant_buy,
                "quant_sell_score": quant_sell,
                "final_buy_score": final_buy,
                "final_sell_score": final_sell,
                "score": final_buy,
                "confidence": confidence,
                "quant_reason": quant.get("quant_reason"),
                "ai_buy_score": None,
                "ai_sell_score": None,
                "action": action,
                "reason": reason,
                "hard_blocked": False,
                "risk_flags": [],
                "gating_notes": [],
                "market_session": self._us_session(),
            }
        except Exception as exc:
            return self._unavailable(symbol, "US", "USD", exc)

    def _us_session(self) -> dict[str, Any]:
        try:
            return self.session_service.get_session_status("US")
        except Exception:
            return {
                "market": "US",
                "is_market_open": False,
                "is_entry_allowed_now": False,
            }

    @staticmethod
    def _unavailable(symbol: str, market: str, currency: str, exc: Exception) -> dict[str, Any]:
        return {
            "provider": "kis" if market == "KR" else "alpaca",
            "market": market,
            "currency": currency,
            "symbol": symbol,
            "requested_symbol": symbol,
            "analyzed_symbol": symbol,
            "returned_symbol": symbol,
            "action": "hold",
            "reason": "analysis_unavailable",
            "block_reason": "analysis_unavailable",
            "hard_blocked": True,
            "risk_flags": ["analysis_unavailable"],
            "gating_notes": [f"{exc.__class__.__name__}: {str(exc)[:160]}"],
            "current_price": None,
            "final_buy_score": None,
            "final_sell_score": None,
            "confidence": None,
        }


def _normalize_alpaca_bar(bar: Any, symbol: str) -> dict[str, Any] | None:
    def value(name: str):
        if isinstance(bar, dict):
            return bar.get(name)
        return getattr(bar, name, None)

    timestamp = value("timestamp")
    close = _number(value("close"))
    if timestamp is None or close is None or close <= 0:
        return None
    return {
        "symbol": symbol,
        "timestamp": str(timestamp),
        "open": _number(value("open")) or close,
        "high": _number(value("high")) or close,
        "low": _number(value("low")) or close,
        "close": close,
        "volume": _number(value("volume")) or 0.0,
    }


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _blend(primary: float | None, secondary: float | None) -> float | None:
    if primary is None and secondary is None:
        return None
    if primary is None:
        return secondary
    if secondary is None:
        return primary
    return round((primary * QUANT_WEIGHT) + (secondary * AI_WEIGHT), 2)
