from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from app.brokers.kis_client import KisClient, to_float
from app.config import get_settings
from app.core.constants import AI_WEIGHT, DEFAULT_GATE_LEVEL, QUANT_WEIGHT
from app.db.models import TradeRunLog
from app.services.event_risk_service import EventRiskService
from app.services.market_profile_service import MarketProfileService
from app.services.market_session_service import MarketSessionService
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.quant_signal_service import QuantSignalService
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.technical_indicator_service import (
    EMPTY_TECHNICAL_INDICATORS,
    TechnicalIndicatorService,
    indicator_payload_is_quant_ready,
)

KR_PREVIEW_LIMIT = 8
KR_DISABLED_REASONS = ["preview_only", "kr_trading_disabled"]
EMPTY_INDICATORS = dict(EMPTY_TECHNICAL_INDICATORS)
SCOREABLE_INDICATOR_STATUSES = {"ok", "partial"}


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
    ai_buy_score: float | None = None
    ai_sell_score: float | None = None
    confidence: float | None = None


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
        indicator_service: TechnicalIndicatorService | None = None,
        quant_signal_service: QuantSignalService | None = None,
        event_risk_service: EventRiskService | None = None,
        db=None,
        limit: int = KR_PREVIEW_LIMIT,
    ):
        self.client = client
        self.db = db
        self.profile_service = profile_service or MarketProfileService()
        self.session_service = session_service or MarketSessionService()
        self.gpt_advisor = gpt_advisor or KisPreviewGptAdvisor()
        self.indicator_service = indicator_service or TechnicalIndicatorService()
        self.quant_signal_service = quant_signal_service or QuantSignalService()
        self.event_risk_service = event_risk_service or EventRiskService()
        self.runtime_setting_service = RuntimeSettingService()
        self.limit = max(1, min(int(limit), KR_PREVIEW_LIMIT))

    def run_preview(
        self,
        *,
        include_gpt: bool = True,
        gate_level: int = DEFAULT_GATE_LEVEL,
        db=None,
        record_run: bool = False,
        trigger_source: str = "manual_kis_preview",
    ) -> dict[str, Any]:
        db = db if db is not None else self.db
        settings = get_settings()
        profile = self.profile_service.get_profile("KR")
        watchlist = self.profile_service.load_watchlist("KR")
        references = self.profile_service.load_reference_sites("KR")
        market_session = self.session_service.get_session_status("KR")
        session_warnings = self._session_warnings(market_session)
        configured_symbols = watchlist["symbols"][: self.limit]
        runtime_settings = self._runtime_settings(db)
        max_open_positions = max(1, _safe_int(runtime_settings.get("max_open_positions"), 3))
        per_slot_new_entry_limit = max(
            0,
            _safe_int(runtime_settings.get("per_slot_new_entry_limit"), 1),
        )
        held_positions, position_warnings = self._load_held_positions(settings)
        managed_positions = held_positions[:max_open_positions]
        held_symbols = [position["symbol"] for position in held_positions]
        managed_symbols = [position["symbol"] for position in managed_positions]

        items = []
        gpt_used = False
        for raw in configured_symbols:
            item = self._preview_symbol(
                raw,
                gate_level=gate_level,
                market_session=market_session,
                session_warnings=session_warnings,
                reference_sources=references.get("sources") or [],
                include_gpt=include_gpt,
                db=db,
            )
            gpt_used = gpt_used or bool(item.get("gpt_used"))
            items.append(item)

        final_ranked_candidates = self._rank_final_candidates(items)
        quant_candidates = self._rank_quant_candidates(items)
        researched_candidates = [
            item
            for item in final_ranked_candidates
            if item.get("gpt_used") and item.get("quant_buy_score") is not None
        ]
        final_best_candidate = (
            final_ranked_candidates[0]
            if final_ranked_candidates
            and self._candidate_score(final_ranked_candidates[0]) is not None
            else None
        )
        second_final_candidate = (
            final_ranked_candidates[1]
            if final_best_candidate is not None
            and len(final_ranked_candidates) > 1
            and self._candidate_score(final_ranked_candidates[1]) is not None
            else None
        )
        best_score = self._candidate_score(final_best_candidate)
        second_score = self._candidate_score(second_final_candidate)
        final_score_gap = (
            round(float(best_score) - float(second_score), 2)
            if best_score is not None and second_score is not None
            else (0.0 if best_score is not None else None)
        )
        tied_final_candidates = (
            [
                {"symbol": item.get("symbol"), "final_entry_score": self._candidate_score(item)}
                for item in final_ranked_candidates
                if self._candidate_score(item) == best_score
            ]
            if best_score is not None
            else []
        )
        near_tied_candidates = (
            [
                {"symbol": item.get("symbol"), "final_entry_score": self._candidate_score(item)}
                for item in final_ranked_candidates
                if self._candidate_score(item) is not None
                and abs(float(best_score) - float(self._candidate_score(item))) <= 1.0
            ]
            if best_score is not None
            else []
        )
        tie_breaker_applied = len(tied_final_candidates) > 1 or len(near_tied_candidates) > 1
        item_by_symbol = {str(item.get("symbol", "")): item for item in items}
        entry_candidate_item = None
        entry_candidate_symbol = None
        entry_evaluated = False
        entry_skip_reason = None
        if position_warnings:
            entry_skip_reason = "kis_positions_unavailable"
        elif len(held_positions) >= max_open_positions:
            entry_skip_reason = "max_open_positions_reached"
        elif per_slot_new_entry_limit <= 0:
            entry_skip_reason = "per_slot_new_entry_limit_reached"
        else:
            held_symbol_set = set(held_symbols)
            for item in final_ranked_candidates:
                symbol = str(item.get("symbol") or "")
                if symbol and symbol not in held_symbol_set:
                    entry_candidate_item = item
                    entry_candidate_symbol = symbol
                    entry_evaluated = True
                    break
            if entry_candidate_symbol is None:
                entry_skip_reason = "no_non_held_entry_candidate"

        portfolio_preview_items = [
            self._portfolio_preview_item(
                item_by_symbol.get(position["symbol"]),
                symbol=position["symbol"],
                mode="position_management_preview",
                symbol_role="held_position",
                allowed_actions=["hold", "sell"],
                position=position,
            )
            for position in managed_positions
        ]
        if entry_candidate_item is not None:
            portfolio_preview_items.append(
                self._portfolio_preview_item(
                    entry_candidate_item,
                    symbol=entry_candidate_symbol,
                    mode="entry_scan_preview",
                    symbol_role="watchlist_candidate",
                    allowed_actions=["hold", "buy"],
                    position=None,
                )
            )

        portfolio_event_risk = (
            entry_candidate_item.get("event_risk")
            if entry_candidate_item is not None
            else (final_best_candidate.get("event_risk") if final_best_candidate is not None else None)
        )
        portfolio_risk_flags = _dedupe(
            ["kr_trading_disabled", "preview_only"]
            + _string_list(entry_candidate_item.get("risk_flags") if entry_candidate_item else None)
        )
        portfolio_gating_notes = _dedupe(
            ["KIS scheduler portfolio concept is preview-only; no real order submitted."]
            + _string_list(entry_candidate_item.get("gating_notes") if entry_candidate_item else None)
        )

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

        payload = {
            "market": "KR",
            "provider": "kis",
            "gate_level": gate_level,
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
            "quant_candidates_count": len(quant_candidates),
            "researched_candidates_count": len(researched_candidates),
            "final_best_candidate": final_best_candidate,
            "second_final_candidate": second_final_candidate,
            "tied_final_candidates": tied_final_candidates,
            "near_tied_candidates": near_tied_candidates,
            "tie_breaker_applied": tie_breaker_applied,
            "final_candidate_selection_reason": (
                "KR preview ranked by grounded KIS OHLCV scores; trading disabled."
                if final_best_candidate is not None
                else "KR preview only; trading disabled."
            ),
            "best_score": best_score,
            "final_score_gap": final_score_gap,
            "min_entry_score": settings.watchlist_min_entry_score if best_score is not None else None,
            "min_score_gap": settings.watchlist_min_score_gap if best_score is not None else None,
            "should_trade": False,
            "triggered_symbol": None,
            "trigger_block_reason": "kr_trading_disabled",
            "managed_symbols": managed_symbols,
            "held_symbols": held_symbols,
            "open_symbols": held_symbols,
            "held_positions": held_positions,
            "managed_positions": managed_positions,
            "held_position_count": len(held_positions),
            "open_position_count": len(held_positions),
            "max_open_positions": max_open_positions,
            "entry_candidate_symbol": entry_candidate_symbol,
            "entry_evaluated": entry_evaluated,
            "entry_skip_reason": entry_skip_reason,
            "event_risk": portfolio_event_risk,
            "risk_flags": portfolio_risk_flags,
            "gating_notes": portfolio_gating_notes,
            "child_runs": portfolio_preview_items,
            "portfolio_preview_items": portfolio_preview_items,
            "final_entry_ready": False,
            "final_action_hint": "watch",
            "action": "hold",
            "order_id": None,
            "result": "preview_only",
            "reason": "kr_trading_disabled",
            "trade_result": trade_result,
            "market_session": self._public_session(market_session),
            "warnings": _dedupe(KR_DISABLED_REASONS + session_warnings + position_warnings),
            "top_quant_candidates": quant_candidates,
            "researched_candidates": researched_candidates,
            "final_ranked_candidates": final_ranked_candidates,
            "items": items,
            "count": len(items),
        }
        if record_run and db is not None:
            run = _record_preview_run(
                db,
                payload=payload,
                gate_level=gate_level,
                trigger_source=trigger_source,
            )
            payload["run"] = _serialize_preview_run(run)
        return payload

    def _runtime_settings(self, db) -> dict[str, Any]:
        try:
            if db is not None:
                return self.runtime_setting_service.get_settings(db)
        except Exception:
            pass
        return self.runtime_setting_service._defaults()

    def _load_held_positions(self, settings) -> tuple[list[dict[str, Any]], list[str]]:
        if not bool(getattr(settings, "kis_enabled", False)):
            return [], ["kis_positions_unavailable"]
        if not getattr(settings, "kis_account_no", None):
            return [], ["kis_positions_unavailable"]
        try:
            raw_positions = self.client.list_positions()
        except Exception:
            return [], ["kis_positions_unavailable"]

        positions = []
        for raw in raw_positions:
            position = _normalize_kis_position(raw)
            if position and _safe_float(position.get("qty"), 0.0) > 0:
                positions.append(position)
        positions.sort(key=lambda item: str(item.get("symbol") or ""))
        return positions, []

    def _portfolio_preview_item(
        self,
        item: dict[str, Any] | None,
        *,
        symbol: str | None,
        mode: str,
        symbol_role: str,
        allowed_actions: list[str],
        position: dict[str, Any] | None,
    ) -> dict[str, Any]:
        normalized_symbol = self.profile_service.normalize_symbol(symbol, "KR")
        payload = dict(item or {})
        if not payload:
            payload = {
                "symbol": normalized_symbol,
                "name": (position or {}).get("name"),
                "current_price": (position or {}).get("current_price"),
                "currency": "KRW",
                "score": None,
                "final_entry_score": None,
                "entry_ready": False,
                "trade_allowed": False,
                "approved_by_risk": False,
                "action": "hold",
                "action_hint": "watch",
                "risk_flags": ["kr_trading_disabled", "preview_only"],
                "gating_notes": [
                    "KIS held-position management preview only; no real order submitted."
                ],
                "block_reason": "kr_trading_disabled",
                "block_reasons": list(KR_DISABLED_REASONS),
                "warnings": list(KR_DISABLED_REASONS),
                "event_risk": _empty_event_risk(symbol=normalized_symbol, market="KR"),
            }

        payload.update(
            {
                "symbol": normalized_symbol,
                "mode": mode,
                "symbol_role": symbol_role,
                "allowed_actions": allowed_actions,
                "position": position,
                "preview_only": True,
                "dry_run": True,
                "trading_enabled": False,
                "order_id": None,
                "real_order_submitted": False,
            }
        )
        payload["risk_flags"] = _dedupe(
            _string_list(payload.get("risk_flags")) + ["kr_trading_disabled", "preview_only"]
        )
        payload["gating_notes"] = _dedupe(
            _string_list(payload.get("gating_notes"))
            + ["KIS portfolio management is preview-only; no real order submitted."]
        )
        return payload

    def _preview_symbol(
        self,
        raw: dict[str, Any],
        *,
        gate_level: int,
        market_session: dict[str, Any],
        session_warnings: list[str],
        reference_sources: list[dict[str, Any]],
        include_gpt: bool,
        db,
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
            price = self._get_normalized_price_snapshot(symbol)
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

        bars: list[dict[str, Any]] = []
        bar_error: str | None = None
        try:
            bars = self.client.get_domestic_daily_bars(symbol, limit=120)
        except Exception as exc:
            warnings.append("ohlcv_unavailable")
            bar_error = _safe_error(exc)

        indicator_result = self.indicator_service.calculate(
            bars,
            current_price=current_price,
        )
        indicator_status = str(indicator_result.get("indicator_status") or "price_only")
        indicator_payload = dict(
            indicator_result.get("indicator_payload") or EMPTY_INDICATORS
        )
        bar_count = int(indicator_result.get("bar_count") or 0)
        if current_price is None and indicator_status == "price_only":
            indicator_status = "insufficient_data"

        can_score = (
            indicator_status in SCOREABLE_INDICATOR_STATUSES
            and indicator_payload_is_quant_ready(indicator_payload)
        )
        if indicator_status in SCOREABLE_INDICATOR_STATUSES and not can_score:
            indicator_status = "insufficient_data"
        quant_buy_score: float | None = None
        quant_sell_score: float | None = None
        quant_reason: str | None = None
        quant_notes: list[str] = []

        if can_score:
            quant = self.quant_signal_service.score(
                indicator_payload,
                gate_level=gate_level,
            )
            quant_buy_score = _score_or_none(quant.get("quant_buy_score"))
            quant_sell_score = _score_or_none(quant.get("quant_sell_score"))
            quant_reason = str(quant.get("quant_reason") or "").strip() or None
            quant_notes = _string_list(quant.get("quant_notes"))
            gating_notes.append("KIS OHLCV indicators were used for quant scoring.")
            gating_notes.extend(quant_notes)

        block_reason = "kr_trading_disabled" if can_score else "insufficient_indicator_data"
        if current_price is None and not can_score:
            block_reason = "current_price_unavailable"
        if block_reason not in block_reasons:
            block_reasons.append(block_reason)

        event_risk = self._event_risk_for_symbol(
            db,
            symbol=symbol,
            market_session=market_session,
        )
        warnings.extend(_string_list(event_risk.get("warnings")))
        if event_risk.get("has_near_event"):
            risk_flags.append("structured_event_risk")
            gating_notes.append("Structured earnings-event risk is advisory only for KR preview.")
            if event_risk.get("entry_blocked"):
                risk_flags.append("event_risk_entry_block")
                block_reasons.append("near_earnings_event")
                gating_notes.append("Upcoming earnings event blocks new entries under the event-risk policy.")
            elif _safe_float(event_risk.get("position_size_multiplier"), 1.0) < 1.0:
                risk_flags.append("event_risk_position_size_reduced")
                gating_notes.append("Upcoming earnings event reduces hypothetical entry size.")

        gpt = KisGptPreview(
            gpt_used=False,
            action_hint="watch",
            gpt_reason=(
                "\u0047\u0050\u0054 \ucc38\uace0 \ud574\uc11d "
                "\uc804\uc6a9\uc785\ub2c8\ub2e4. \uc2e4\ud589 \uac00\ub2a5\ud55c "
                "\ub9e4\ub9e4 \uacb0\uc815\uc774 \uc544\ub2d9\ub2c8\ub2e4."
            ),
            warnings=[],
        )
        if include_gpt:
            gpt = self.gpt_advisor.analyze(
                symbol=symbol,
                name=name,
                current_price=current_price,
                indicator_status=indicator_status,
                indicator_payload=indicator_payload if can_score else dict(EMPTY_INDICATORS),
                market_session=market_session,
                reference_sources=reference_sources,
                event_context=event_risk if event_risk.get("has_near_event") else None,
            )
            gpt = self._ensure_korean_gpt_preview(
                gpt,
                indicator_status=indicator_status,
                indicator_payload=indicator_payload,
                market_session=market_session,
            )
            warnings.extend(gpt.warnings)
            if "gpt_unavailable" in gpt.warnings:
                risk_flags.append("gpt_unavailable")
            if gpt.risk_flags:
                risk_flags.extend(gpt.risk_flags)
            if gpt.gating_notes:
                gating_notes.extend(gpt.gating_notes)

        ai_buy_score = gpt.ai_buy_score if can_score else None
        ai_sell_score = gpt.ai_sell_score if can_score else None
        final_buy_score = self._blend_score(quant_buy_score, ai_buy_score)
        final_sell_score = self._blend_score(quant_sell_score, ai_sell_score)

        if indicator_status == "price_only":
            reason = "Only current price is available; technical indicator score was not calculated."
            note = "Price-only preview; technical indicators not calculated yet."
        elif not can_score:
            reason = "KIS OHLCV history is unavailable or insufficient for grounded scoring."
            note = "Insufficient data; technical indicators not calculated yet."
        else:
            reason = quant_reason or "KIS OHLCV quant indicators calculated for preview."
            note = "KIS OHLCV indicators available; quant score calculated for preview only."

        return {
            "symbol": symbol,
            "name": name or None,
            "market": listing_market,
            "currency": "KRW",
            "current_price": current_price,
            "score": final_buy_score,
            "final_entry_score": final_buy_score,
            "quant_score": quant_buy_score,
            "note": note,
            "indicator_status": indicator_status,
            "indicator_payload": indicator_payload,
            "indicator_bar_count": bar_count,
            "quant_buy_score": quant_buy_score,
            "quant_sell_score": quant_sell_score,
            "ai_buy_score": ai_buy_score,
            "ai_sell_score": ai_sell_score,
            "final_buy_score": final_buy_score,
            "final_sell_score": final_sell_score,
            "confidence": gpt.confidence if can_score else None,
            "quant_reason": quant_reason,
            "quant_notes": quant_notes,
            "action": "hold",
            "action_hint": "watch",
            "entry_ready": False,
            "final_entry_ready": False,
            "trade_allowed": False,
            "approved_by_risk": False,
            "should_trade": False,
            "trading_enabled": False,
            "order_id": None,
            "risk_flags": _dedupe(risk_flags),
            "gating_notes": _dedupe(gating_notes),
            "block_reason": block_reason,
            "reason": reason,
            "gpt_reason": gpt.gpt_reason,
            "event_risk": event_risk,
            "warnings": _dedupe(warnings),
            "block_reasons": _dedupe(block_reasons),
            "error": price_error or bar_error,
            "gpt_used": gpt.gpt_used,
            "gate_level": gate_level,
        }

    def _get_normalized_price_snapshot(self, symbol: str) -> dict[str, Any]:
        # Keep preview current_price aligned with /kis/market/price/{symbol}.
        # Preview code must not parse raw KIS quote fields directly.
        return self.client.get_domestic_stock_price(symbol)

    def _event_risk_for_symbol(
        self,
        db,
        *,
        symbol: str,
        market_session: dict[str, Any],
    ) -> dict[str, Any]:
        if db is None:
            return _empty_event_risk(
                symbol=symbol,
                market="KR",
                warnings=["event_data_unavailable"],
                reason="event risk unavailable without db session",
            )
        try:
            return self.event_risk_service.get_event_risk(
                db,
                symbol=symbol,
                market="KR",
                as_of_date=self._session_date(market_session),
                intent="entry",
            )
        except Exception:
            return _empty_event_risk(
                symbol=symbol,
                market="KR",
                warnings=["event_data_unavailable"],
                reason="event risk unavailable",
            )

    @staticmethod
    def _session_date(market_session: dict[str, Any]):
        raw_date = market_session.get("date") or market_session.get("current_date")
        if not raw_date:
            return None
        try:
            from datetime import date

            return date.fromisoformat(str(raw_date)[:10])
        except Exception:
            return None

    def _rank_final_candidates(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        indexed = list(enumerate(items))

        def sort_key(pair: tuple[int, dict[str, Any]]):
            index, item = pair
            score = self._candidate_score(item)
            return (
                0 if score is not None else 1,
                -float(score or 0.0),
                _safe_float(item.get("quant_sell_score"), 100.0),
                index,
            )

        return [item for _, item in sorted(indexed, key=sort_key)]

    def _rank_quant_candidates(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        indexed = [
            (index, item)
            for index, item in enumerate(items)
            if item.get("quant_buy_score") is not None
        ]

        def sort_key(pair: tuple[int, dict[str, Any]]):
            index, item = pair
            return (
                -_safe_float(item.get("quant_buy_score"), 0.0),
                _safe_float(item.get("quant_sell_score"), 100.0),
                index,
            )

        return [item for _, item in sorted(indexed, key=sort_key)]

    @staticmethod
    def _candidate_score(item: dict[str, Any] | None) -> float | None:
        if not item:
            return None
        final_score = _score_or_none(item.get("final_buy_score"))
        if final_score is not None:
            return final_score
        return _score_or_none(item.get("quant_buy_score"))

    @staticmethod
    def _blend_score(
        quant_score: float | None,
        ai_score: float | None,
    ) -> float | None:
        if quant_score is None:
            return None
        if ai_score is None:
            return round(float(quant_score), 2)
        blended = (float(quant_score) * QUANT_WEIGHT) + (float(ai_score) * AI_WEIGHT)
        return round(min(max(blended, 0.0), 100.0), 2)

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

    @staticmethod
    def _ensure_korean_gpt_preview(
        gpt: KisGptPreview,
        *,
        indicator_status: str,
        indicator_payload: dict[str, Any],
        market_session: dict[str, Any],
    ) -> KisGptPreview:
        if _contains_hangul(gpt.gpt_reason):
            return gpt
        return KisGptPreview(
            gpt_used=gpt.gpt_used,
            action_hint=gpt.action_hint,
            gpt_reason=_korean_advisory_fallback(
                indicator_status=indicator_status,
                indicator_payload=indicator_payload,
                market_session=market_session,
            ),
            warnings=list(gpt.warnings),
            action=gpt.action,
            risk_flags=list(gpt.risk_flags or []),
            gating_notes=list(gpt.gating_notes or []),
            hard_block_reason=gpt.hard_block_reason,
            ai_buy_score=gpt.ai_buy_score,
            ai_sell_score=gpt.ai_sell_score,
            confidence=gpt.confidence,
        )


def _record_preview_run(
    db,
    *,
    payload: dict[str, Any],
    gate_level: int,
    trigger_source: str,
) -> TradeRunLog:
    symbol = (
        _candidate_symbol(payload.get("entry_candidate_symbol"))
        or _candidate_symbol(payload.get("final_best_candidate"))
        or "WATCHLIST"
    )
    response_payload = _preview_log_payload(payload, gate_level=gate_level, trigger_source=trigger_source)
    run = TradeRunLog(
        run_key=f"kis_preview_{uuid.uuid4().hex[:12]}",
        trigger_source=trigger_source,
        symbol=symbol,
        mode="kis_watchlist_preview",
        gate_level=gate_level,
        stage="done",
        result=str(payload.get("result") or "preview_only"),
        reason=str(payload.get("reason") or payload.get("trigger_block_reason") or "kr_trading_disabled"),
        signal_id=None,
        order_id=None,
        request_payload=json.dumps(
            {
                "provider": "kis",
                "market": "KR",
                "mode": "kis_watchlist_preview",
                "dry_run": True,
                "preview_only": True,
                "simulated": False,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "gate_level": gate_level,
                "trigger_source": trigger_source,
            },
            ensure_ascii=False,
            default=str,
        ),
        response_payload=json.dumps(response_payload, ensure_ascii=False, default=str),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _preview_log_payload(
    payload: dict[str, Any],
    *,
    gate_level: int,
    trigger_source: str,
) -> dict[str, Any]:
    final_best = payload.get("final_best_candidate")
    ranked = payload.get("final_ranked_candidates")
    return sanitize_kis_payload(
        {
            "provider": "kis",
            "market": "KR",
            "mode": "kis_watchlist_preview",
            "dry_run": True,
            "preview_only": True,
            "simulated": False,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "trigger_source": trigger_source,
            "gate_level": gate_level,
            "result": payload.get("result") or "preview_only",
            "action": payload.get("action") or "hold",
            "reason": payload.get("reason") or payload.get("trigger_block_reason"),
            "trigger_block_reason": payload.get("trigger_block_reason"),
            "order_id": None,
            "signal_id": None,
            "configured_symbol_count": payload.get("configured_symbol_count"),
            "analyzed_symbol_count": payload.get("analyzed_symbol_count"),
            "quant_candidates_count": payload.get("quant_candidates_count"),
            "researched_candidates_count": payload.get("researched_candidates_count"),
            "final_best_candidate": final_best,
            "final_ranked_symbols": _candidate_symbols(ranked),
            "risk_flags": _string_list(payload.get("risk_flags")),
            "gating_notes": _string_list(payload.get("gating_notes")),
        }
    )


def _serialize_preview_run(row: TradeRunLog) -> dict[str, Any]:
    return {
        "run_id": row.id,
        "run_key": row.run_key,
        "trigger_source": row.trigger_source,
        "symbol": row.symbol,
        "mode": row.mode,
        "gate_level": row.gate_level,
        "stage": row.stage,
        "result": row.result,
        "reason": row.reason,
        "signal_id": row.signal_id,
        "order_id": row.order_id,
        "created_at": row.created_at,
    }


def _candidate_symbol(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("symbol")
    text = str(value or "").strip().upper()
    return text or None


def _candidate_symbols(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    symbols = []
    for item in value:
        symbol = _candidate_symbol(item)
        if symbol:
            symbols.append(symbol)
    return symbols


class KisPreviewGptAdvisor:
    def __init__(
        self,
        settings=None,
        client: OpenAI | None = None,
        advisory_language: str = "ko",
    ):
        self.settings = settings or get_settings()
        self.client = client
        self.advisory_language = advisory_language
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
        event_context: dict[str, Any] | None = None,
    ) -> KisGptPreview:
        if self.client is None:
            fallback_scope = (
                "quant-only KIS OHLCV preview"
                if indicator_status in SCOREABLE_INDICATOR_STATUSES
                else "price-only preview"
            )
            return KisGptPreview(
                gpt_used=False,
                action_hint="watch",
                gpt_reason=_korean_advisory_fallback(
                    indicator_status=indicator_status,
                    indicator_payload=indicator_payload,
                    market_session=market_session,
                ),
                warnings=["gpt_unavailable"],
                action="hold",
                risk_flags=["gpt_unavailable"],
                gating_notes=[f"GPT advisory unavailable; {fallback_scope} kept hold/watch."],
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
                event_context=event_context,
            )
            return self._normalize_payload(
                payload,
                indicator_status=indicator_status,
                indicator_payload=indicator_payload,
                market_session=market_session,
            )
        except Exception as exc:
            fallback_scope = (
                "quant-only KIS OHLCV preview"
                if indicator_status in SCOREABLE_INDICATOR_STATUSES
                else "price-only preview"
            )
            return KisGptPreview(
                gpt_used=False,
                action_hint="watch",
                gpt_reason=_korean_advisory_fallback(
                    indicator_status=indicator_status,
                    indicator_payload=indicator_payload,
                    market_session=market_session,
                ),
                warnings=["gpt_unavailable"],
                action="hold",
                risk_flags=["gpt_unavailable"],
                gating_notes=[f"GPT advisory unavailable; {fallback_scope} kept hold/watch."],
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
        event_context: dict[str, Any] | None = None,
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
            "Respond in Korean. Return reason and gpt_reason in Korean. "
            "Do not mix English and Korean except unavoidable technical terms "
            "like EMA20, RSI, VWAP, ATR, KRW, KIS, KRX, OpenDART, and KIND. "
            "Keep machine-readable fields such as risk_flags, gating_notes, "
            "hard_block_reason, action, and action_hint in stable English.\n"
            "Earnings or earnings-call events are uncertainty risks, not bullish signals. "
            "Do not increase buy_score, action confidence, or entry confidence because of upcoming earnings. "
            "If event_context.entry_blocked is true, recommend hold or block_entry. "
            "If event_context.position_size_multiplier is below 1.0, mention that position size should be reduced. "
            "Do not treat upcoming earnings as a reason to buy. The risk engine remains the final authority.\n"
            "Return JSON only. Use keys: ai_buy_score, ai_sell_score, "
            "confidence, action, reason, gpt_reason, risk_flags, gating_notes, "
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
        prompt_payload = {
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
                    "Respond in Korean.",
                    "Return gpt_reason in Korean.",
                    "Keep risk_flags, gating_notes, hard_block_reason, action, and action_hint machine-readable in English.",
                    "Do not treat upcoming earnings as bullish.",
                ],
        }
        if event_context:
            prompt_payload["event_context"] = _prompt_event_context(event_context)
        user_prompt = json.dumps(
            prompt_payload,
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
    def _normalize_payload(
        payload: dict[str, Any],
        *,
        indicator_status: str,
        indicator_payload: dict[str, Any],
        market_session: dict[str, Any],
    ) -> KisGptPreview:
        action = str(payload.get("action") or "hold").strip().lower()
        if action not in {"buy", "sell", "hold"}:
            action = "hold"
        has_scoreable_indicators = indicator_status in SCOREABLE_INDICATOR_STATUSES
        if not has_scoreable_indicators:
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
        if not has_scoreable_indicators and action_hint == "candidate":
            action_hint = "watch"
        reason = str(payload.get("gpt_reason") or payload.get("reason") or "").strip()
        if not _contains_hangul(reason):
            reason = _korean_advisory_fallback(
                indicator_status=indicator_status,
                indicator_payload=indicator_payload,
                market_session=market_session,
            )
        risk_flags = _string_list(payload.get("risk_flags"))
        gating_notes = _string_list(payload.get("gating_notes"))
        hard_block_reason = payload.get("hard_block_reason")
        if hard_block_reason is not None:
            hard_block_reason = str(hard_block_reason)
        ai_buy_score = _score_or_none(payload.get("ai_buy_score")) if has_scoreable_indicators else None
        ai_sell_score = _score_or_none(payload.get("ai_sell_score")) if has_scoreable_indicators else None
        confidence = _confidence_or_none(payload.get("confidence")) if has_scoreable_indicators else None
        return KisGptPreview(
            gpt_used=True,
            action_hint=action_hint,
            gpt_reason=reason,
            warnings=[],
            action=action,
            risk_flags=risk_flags,
            gating_notes=gating_notes,
            hard_block_reason=hard_block_reason,
            ai_buy_score=ai_buy_score,
            ai_sell_score=ai_sell_score,
            confidence=confidence,
        )


def _contains_hangul(value: Any) -> bool:
    return any("\uac00" <= char <= "\ud7a3" for char in str(value or ""))


def _korean_advisory_fallback(
    *,
    indicator_status: str,
    indicator_payload: dict[str, Any],
    market_session: dict[str, Any],
) -> str:
    if market_session.get("is_market_open") is not True:
        return (
            "현재 한국장은 휴장 또는 장외 시간으로 신규 진입을 평가하지 않습니다. "
            "지표는 참고용이며 실제 주문은 실행되지 않습니다."
        )

    if (
        indicator_status not in SCOREABLE_INDICATOR_STATUSES
        or not indicator_payload_is_quant_ready(indicator_payload)
    ):
        return (
            "현재가만 확인 가능하고 EMA, RSI, VWAP, ATR, 거래량 비율 등 핵심 지표가 "
            "부족해 정량 점수는 계산하지 않았습니다. KR 실거래가 비활성화되어 "
            "있으므로 관찰 대상으로만 표시합니다."
        )

    price = _safe_float(indicator_payload.get("price"), 0.0)
    ema20 = _safe_float(indicator_payload.get("ema20"), 0.0)
    ema50 = _safe_float(indicator_payload.get("ema50"), 0.0)
    rsi = _safe_float(indicator_payload.get("rsi"), 50.0)
    volume_ratio = _safe_float(indicator_payload.get("volume_ratio"), 1.0)

    if price > 0 and ema20 > 0 and ema50 > 0 and price >= ema20 and price >= ema50:
        trend_text = "현재가는 EMA20과 EMA50 위에 있어 중기 추세는 양호합니다."
    elif ema20 > 0 and ema50 > 0 and ema20 >= ema50:
        trend_text = "EMA20이 EMA50 이상으로 유지되어 추세 훼손은 제한적입니다."
    else:
        trend_text = "EMA20과 EMA50 기준 추세 확인은 아직 강하지 않습니다."

    rsi_text = (
        "RSI가 과열권에 가까워 추격 진입 신뢰도는 높지 않습니다."
        if rsi >= 65
        else "RSI는 과열권에서 벗어나 있지만 단독 매수 근거로 보기는 어렵습니다."
    )
    volume_text = (
        "거래량 확인이 약해 추가 확인이 필요합니다."
        if volume_ratio < 1.0
        else "거래량은 평균 이상이지만 KR 실거래는 비활성화되어 있습니다."
    )
    return (
        f"{trend_text} {rsi_text} {volume_text} "
        "이 결과는 정량 지표 우선의 참고용 preview이며 실제 주문은 실행되지 않습니다."
    )


def _empty_event_risk(
    *,
    symbol: str,
    market: str,
    warnings: list[str] | None = None,
    reason: str = "no structured event risk found",
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "market": market,
        "has_near_event": False,
        "event_type": None,
        "event_date": None,
        "event_time_label": "unknown",
        "days_to_event": None,
        "risk_level": "low",
        "entry_blocked": False,
        "scale_in_blocked": False,
        "position_size_multiplier": 1.0,
        "force_gate_level": None,
        "reason": reason,
        "source": None,
        "warnings": warnings or [],
    }


def _prompt_event_context(event_context: dict[str, Any]) -> dict[str, Any]:
    multiplier = _safe_float(event_context.get("position_size_multiplier"), 1.0)
    return {
        "has_near_event": bool(event_context.get("has_near_event")),
        "event_type": event_context.get("event_type"),
        "days_to_event": event_context.get("days_to_event"),
        "event_time_label": event_context.get("event_time_label"),
        "entry_blocked": bool(event_context.get("entry_blocked")),
        "scale_in_blocked": bool(event_context.get("scale_in_blocked")),
        "position_size_multiplier": multiplier,
        "risk_policy": (
            "block_new_entry"
            if event_context.get("entry_blocked")
            else ("reduce_position_size" if multiplier < 1.0 else "none")
        ),
    }


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _score_or_none(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:
        return None
    return round(min(max(numeric, 0.0), 100.0), 2)


def _confidence_or_none(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:
        return None
    if numeric > 1.0:
        numeric = numeric / 100.0
    return round(min(max(numeric, 0.0), 1.0), 4)


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


def _normalize_kis_position(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    raw_symbol = raw.get("symbol") or raw.get("pdno") or raw.get("code")
    symbol = str(raw_symbol or "").strip()
    if not symbol:
        return None
    if symbol.isdigit() and len(symbol) < 6:
        symbol = symbol.zfill(6)
    return {
        "symbol": symbol,
        "name": raw.get("name") or raw.get("prdt_name"),
        "qty": to_float(raw.get("qty") or raw.get("hldg_qty") or 0),
        "avg_entry_price": to_float(raw.get("avg_entry_price") or raw.get("pchs_avg_pric") or 0),
        "current_price": to_float(
            raw.get("current_price") or raw.get("prpr") or raw.get("stck_prpr") or 0
        ),
        "market_value": to_float(raw.get("market_value") or raw.get("evlu_amt") or 0),
        "unrealized_pl": to_float(raw.get("unrealized_pl") or raw.get("evlu_pfls_amt") or 0),
        "unrealized_plpc": to_float(raw.get("unrealized_plpc") or raw.get("evlu_pfls_rt") or 0),
    }
