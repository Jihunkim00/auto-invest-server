from __future__ import annotations

import json
import math
import uuid
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.schemas.strategy_dry_run_auto_buy import (
    ProfileAwareDryRunAutoBuyRequest,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.kis_watchlist_preview_service import KisWatchlistPreviewService
from app.services.automation_observability import (
    candidate_gpt_quant_observability,
    gpt_result_counts,
)
from app.services.market_profile_service import MarketProfileService
from app.services.market_session_service import MarketSessionService
from app.services.profile_universe_service import (
    candidate_price,
    profile_price_exclusion_reason,
    profile_universe_bounds,
)
from app.services.strategy_profile_service import StrategyProfileService
from app.services.target_aware_risk_service import TargetAwareRiskService


MODE = "strategy_dry_run_auto_buy"
TRIGGER_SOURCE = "profile_aware_dry_run_auto_buy"
PROVIDER = "kis"
MARKET = "KR"
_KST = ZoneInfo("Asia/Seoul")


class ProfileAwareDryRunAutoBuyService:
    """Profile-aware KIS buy simulation with no validation or broker submit."""

    def __init__(
        self,
        *,
        preview_service: KisWatchlistPreviewService | None = None,
        strategy_profiles: StrategyProfileService | None = None,
        target_risk_service: TargetAwareRiskService | None = None,
        market_profiles: MarketProfileService | None = None,
        market_sessions: MarketSessionService | None = None,
    ) -> None:
        self.preview_service = preview_service
        self.strategy_profiles = strategy_profiles or StrategyProfileService()
        self.target_risk_service = target_risk_service or TargetAwareRiskService()
        self.market_profiles = market_profiles or MarketProfileService()
        self.market_sessions = market_sessions or MarketSessionService()

    def run_once(
        self,
        db: Session,
        request: ProfileAwareDryRunAutoBuyRequest | dict[str, Any],
        *,
        preview_override: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        payload = (
            request
            if isinstance(request, ProfileAwareDryRunAutoBuyRequest)
            else ProfileAwareDryRunAutoBuyRequest.model_validate(request)
        )
        now_utc = _utc_now(now)
        # Custom automation settings are the source of truth. ``profile_name``
        # remains the compatible legacy strategy/risk preset identity.
        profile_row = (
            self.strategy_profiles.get_profile(db, payload.automation_profile_key)
            if payload.automation_profile_key
            else (
                self.strategy_profiles.get_profile(db, payload.profile_name)
                if payload.profile_name
                else self.strategy_profiles.active_profile(db)
            )
        )
        profile = self.strategy_profiles.serialize_profile(profile_row)
        legacy_profile_name = (
            payload.profile_name
            or self.strategy_profiles.legacy_active_profile(db).profile_name
        )
        automation_profile_key = profile.get("profile_key")
        automation_profile_name = (
            profile.get("display_name") if automation_profile_key else None
        )
        risk_profile_name = automation_profile_key or profile["profile_name"]
        preview = self._preview(
            db,
            request=payload,
            preview_override=preview_override,
            profile=profile,
        )
        preview = self._apply_profile_universe(preview, profile=profile)
        candidates = self._candidate_list(
            preview,
            requested_symbol=payload.symbol,
            limit=payload.max_candidates,
        )
        market_session = (
            preview.get("market_session")
            if isinstance(preview.get("market_session"), dict)
            else self._market_session(now_utc)
        )
        evaluated = [
            self._evaluate_candidate(
                db,
                candidate,
                profile=profile,
                profile_name=risk_profile_name,
            )
            for candidate in candidates
        ]
        evaluated.sort(key=_candidate_sort_key)
        selected = _select_executable_candidate(evaluated, profile=profile)
        decision = self._decision(
            selected,
            market_session=market_session,
            profile=profile,
            preview=preview,
        )
        preview_failure_reason = self._preview_failure_reason(preview)
        if preview_failure_reason is not None and not evaluated:
            decision = {
                **decision,
                "reason": preview_failure_reason,
            }
        response = self._response(
            request=payload,
            profile=profile,
            preview=preview,
            evaluated=evaluated,
            selected=selected,
            decision=decision,
            legacy_profile_name=legacy_profile_name,
            automation_profile_key=automation_profile_key,
            automation_profile_name=automation_profile_name,
            now_utc=now_utc,
        )

        if payload.save_logs:
            signal = self._save_signal(db, response=response, selected=selected)
            order = (
                self._save_simulated_order(
                    db,
                    response=response,
                    signal_id=signal.id,
                )
                if response["action"] == "would_buy"
                else None
            )
            if order is not None:
                signal.related_order_id = order.id
            run = self._save_run(
                db,
                response=response,
                request=payload,
                signal_id=signal.id,
                order_id=order.id if order is not None else None,
            )
            db.commit()
            response["signal_id"] = signal.id
            response["trade_run_id"] = run.id
            response["simulated_order_id"] = order.id if order is not None else None
            run.response_payload = _json(response)
            db.commit()
        return sanitize_kis_payload(response)

    def recent(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
        profile_name: str | None = None,
        symbol: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        rows = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == MODE)
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .limit(max(1, min(int(limit or 20) * 4, 200)))
            .all()
        )
        items: list[dict[str, Any]] = []
        normalized_symbol = str(symbol or "").strip().upper()
        for row in rows:
            item = _parse_object(row.response_payload)
            if not item:
                continue
            if str(item.get("provider") or "").lower() != str(provider).lower():
                continue
            if str(item.get("market") or "").upper() != str(market).upper():
                continue
            if profile_name and item.get("active_profile") != profile_name:
                continue
            if normalized_symbol and item.get("selected_symbol") != normalized_symbol:
                continue
            item.setdefault("trade_run_id", row.id)
            item.setdefault("created_at", _iso(row.created_at))
            items.append(sanitize_kis_payload(item))
            if len(items) >= max(1, min(int(limit or 20), 100)):
                break
        return {
            "provider": str(provider).lower(),
            "market": str(market).upper(),
            "count": len(items),
            "items": items,
            "safety": _safety(),
        }

    def summary(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
    ) -> dict[str, Any]:
        recent = self.recent(
            db,
            provider=provider,
            market=market,
            limit=100,
        )
        now_local = datetime.now(_KST)
        month_key = f"{now_local.year:04d}-{now_local.month:02d}"
        today_key = now_local.date().isoformat()
        today_items: list[dict[str, Any]] = []
        month_items: list[dict[str, Any]] = []
        profiles: dict[str, dict[str, int]] = {}
        for item in recent["items"]:
            created = _parse_datetime(item.get("created_at"))
            local = created.astimezone(_KST) if created else None
            if local and local.date().isoformat() == today_key:
                today_items.append(item)
            if local and f"{local.year:04d}-{local.month:02d}" == month_key:
                month_items.append(item)
            profile = str(item.get("active_profile") or "unknown")
            bucket = profiles.setdefault(profile, _empty_counts())
            _increment(bucket, str(item.get("action") or "hold"))
        return {
            "provider": str(provider).lower(),
            "market": str(market).upper(),
            "today": {
                "date": today_key,
                **_counts(today_items),
            },
            "month": {
                "month": month_key,
                **_counts(month_items),
            },
            "profiles": profiles,
            "safety": _safety(),
        }

    def _preview(
        self,
        db: Session,
        *,
        request: ProfileAwareDryRunAutoBuyRequest,
        preview_override: dict[str, Any] | None,
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        if preview_override is not None:
            return _normalize_preview_payload(preview_override, status="override")
        if self.preview_service is None:
            return _unavailable_preview_payload("preview_service_unavailable")
        if request.symbol:
            return _normalize_preview_payload(
                self._single_symbol_preview(db, request.symbol),
                status="ok",
            )
        if not request.use_watchlist:
            return _normalize_preview_payload({
                "provider": PROVIDER,
                "market": MARKET,
                "final_ranked_candidates": [],
                "risk_flags": ["watchlist_disabled_for_request"],
                "gating_notes": ["No symbol was supplied and watchlist use was disabled."],
            }, status="disabled")
        try:
            min_price_krw, max_price_krw = profile_universe_bounds(profile)
            try:
                preview = self.preview_service.run_preview(
                    include_gpt=True,
                    db=db,
                    record_run=False,
                    trigger_source=TRIGGER_SOURCE,
                    min_price_krw=min_price_krw,
                    max_price_krw=max_price_krw,
                )
            except TypeError:
                preview = self.preview_service.run_preview(include_gpt=True, db=db)
            return _normalize_preview_payload(preview, status="ok")
        except Exception as exc:
            return _unavailable_preview_payload(
                "preview_unavailable",
                error=exc.__class__.__name__,
                note=f"Watchlist preview failed: {exc.__class__.__name__}",
            )

    def _apply_profile_universe(
        self,
        preview: dict[str, Any],
        *,
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        min_price_krw, max_price_krw = profile_universe_bounds(profile)
        candidate_keys = (
            'watchlist',
            'items',
            'top_quant_candidates',
            'researched_candidates',
            'final_ranked_candidates',
        )
        all_candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        excluded_symbols: set[str] = set()
        exclusion_counts = {
            str(key): int(value)
            for key, value in (preview.get('profile_exclusion_counts') or {}).items()
            if isinstance(value, (int, float))
        }

        for key in candidate_keys:
            values = preview.get(key)
            if not isinstance(values, list):
                continue
            for item in values:
                if not isinstance(item, dict):
                    continue
                symbol = str(item.get('symbol') or '').strip().upper()
                if not symbol or symbol in seen:
                    continue
                seen.add(symbol)
                all_candidates.append(item)

        eligible_symbols: set[str] = set()
        for item in all_candidates:
            symbol = str(item.get('symbol') or '').strip().upper()
            reason = profile_price_exclusion_reason(
                candidate_price(item),
                min_price_krw=min_price_krw,
                max_price_krw=max_price_krw,
            )
            if reason is None:
                eligible_symbols.add(symbol)
                continue
            excluded_symbols.add(symbol)
            exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1

        def keep_candidate(item: Any) -> bool:
            if not isinstance(item, dict):
                return False
            symbol = str(item.get('symbol') or '').strip().upper()
            return bool(symbol) and symbol not in excluded_symbols

        for key in candidate_keys:
            values = preview.get(key)
            if isinstance(values, list):
                preview[key] = [item for item in values if keep_candidate(item)]

        best = preview.get('final_best_candidate')
        if isinstance(best, dict) and not keep_candidate(best):
            preview['final_best_candidate'] = None
        target_symbols = preview.get('gpt_target_symbols')
        if isinstance(target_symbols, list):
            preview['gpt_target_symbols'] = [
                symbol
                for symbol in target_symbols
                if str(symbol).strip().upper() not in excluded_symbols
            ]
            preview['gpt_target_count'] = len(preview['gpt_target_symbols'])

        items = preview.get('items')
        if isinstance(items, list):
            preview['analyzed_symbol_count'] = len(items)
            preview['gpt_analyzed_symbol_count'] = sum(
                1 for item in items if isinstance(item, dict) and item.get('gpt_used')
            )

        existing_eligible = preview.get('profile_eligible_symbol_count')
        if not isinstance(existing_eligible, (int, float)):
            existing_eligible = len(eligible_symbols)
        existing_filtered = preview.get('profile_price_filtered_count')
        if not isinstance(existing_filtered, (int, float)):
            existing_filtered = 0
        preview['profile_eligible_symbol_count'] = int(existing_eligible)
        preview['profile_price_filtered_count'] = max(
            int(existing_filtered),
            len(excluded_symbols),
        )
        preview['profile_exclusion_counts'] = exclusion_counts
        return _normalize_preview_payload(
            preview,
            status=str(preview.get('preview_status') or 'ok'),
        )

    def _preview_failure_reason(self, preview: dict[str, Any]) -> str | None:
        flags = set(_strings(preview.get('risk_flags')))
        if 'preview_service_unavailable' in flags:
            return 'preview_service_unavailable'
        if 'preview_unavailable' in flags:
            return 'preview_unavailable'
        if str(preview.get('preview_status') or '').lower() == 'unavailable':
            return str(preview.get('preview_error') or 'preview_unavailable')
        return None

    def _single_symbol_preview(self, db: Session, symbol: str) -> dict[str, Any]:
        market_session = self._market_session(datetime.now(UTC))
        try:
            references = self.market_profiles.load_reference_sites(MARKET)
            reference_sources = references.get("sources") or []
        except Exception:
            reference_sources = []
        try:
            warnings = self.preview_service._session_warnings(market_session)
            candidate = self.preview_service._preview_symbol(
                {"symbol": symbol, "market": MARKET},
                gate_level=2,
                market_session=market_session,
                session_warnings=warnings,
                reference_sources=reference_sources,
                include_gpt=True,
                db=db,
            )
        except Exception as exc:
            candidate = {
                "symbol": symbol,
                "market": MARKET,
                "provider": PROVIDER,
                "reason": "analysis_unavailable",
                "risk_flags": ["analysis_unavailable"],
                "gating_notes": [f"Single-symbol analysis failed: {exc.__class__.__name__}"],
            }
        return sanitize_kis_payload(
            {
                "provider": PROVIDER,
                "market": MARKET,
                "market_session": market_session,
                "final_ranked_candidates": [candidate],
                "final_best_candidate": candidate,
                "configured_symbol_count": 1,
                "analyzed_symbol_count": 1,
            }
        )

    def _market_session(self, now_utc: datetime) -> dict[str, Any]:
        try:
            return self.market_sessions.get_session_status(MARKET, now=now_utc)
        except Exception as exc:
            return {
                "market": MARKET,
                "is_market_open": False,
                "is_entry_allowed_now": False,
                "error": exc.__class__.__name__,
            }

    def _candidate_list(
        self,
        preview: dict[str, Any],
        *,
        requested_symbol: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        values: list[Any] = []
        for key in (
            "final_ranked_candidates",
            "researched_candidates",
            "top_quant_candidates",
        ):
            raw = preview.get(key)
            if isinstance(raw, list):
                values.extend(raw)
        if isinstance(preview.get("final_best_candidate"), dict):
            values.insert(0, preview["final_best_candidate"])
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in values:
            if not isinstance(item, dict):
                continue
            symbol = _symbol(item)
            if not symbol or symbol in seen:
                continue
            if requested_symbol and symbol != requested_symbol:
                continue
            seen.add(symbol)
            result.append(sanitize_kis_payload(item))
            if len(result) >= limit:
                break
        return result

    def _evaluate_candidate(
        self,
        db: Session,
        candidate: dict[str, Any],
        *,
        profile: dict[str, Any],
        profile_name: str,
    ) -> dict[str, Any]:
        symbol = _symbol(candidate)
        buy_score = _score(
            candidate,
            "final_buy_score",
            "final_entry_score",
            "final_score",
            "score",
            "quant_buy_score",
        )
        final_score = _score(
            candidate,
            "final_entry_score",
            "final_buy_score",
            "final_score",
            "score",
        )
        price = _score(candidate, "current_price", "price", "close")
        target_risk = self.target_risk_service.evaluate_entry(
            db,
            {
                "provider": PROVIDER,
                "market": MARKET,
                "symbol": symbol or "UNKNOWN",
                "side": "buy",
                "requested_notional_krw": profile.get("max_order_notional_krw"),
                "buy_score": buy_score,
                "sell_score": _score(candidate, "final_sell_score", "quant_sell_score"),
                "confidence": _score(candidate, "confidence"),
                "trigger_source": TRIGGER_SOURCE,
                "dry_run": True,
            },
            profile_name=profile_name,
        )
        indicator_status = str(candidate.get("indicator_status") or "").lower()
        data_sufficient = (
            bool(symbol)
            and buy_score is not None
            and price is not None
            and price > 0
            and indicator_status not in {"insufficient", "price_only", "error"}
        )
        return {
            "symbol": symbol,
            "name": candidate.get("name"),
            "buy_score": buy_score,
            "sell_score": _score(candidate, "final_sell_score", "quant_sell_score"),
            "final_score": final_score,
            "confidence": _score(candidate, "confidence"),
            "price": price,
            "entry_ready": bool(
                candidate.get("entry_ready") or candidate.get("final_entry_ready")
            ),
            "atr_risk": _atr_risk(candidate, price),
            "volume_ratio": _score(
                candidate.get("indicator_payload")
                if isinstance(candidate.get("indicator_payload"), dict)
                else candidate,
                "volume_ratio",
            ),
            "data_sufficient": data_sufficient,
            "target_risk_approved": target_risk.get("approved") is True,
            "target_risk_result": target_risk,
            "quant_buy_score": candidate.get("quant_buy_score"),
            "quant_sell_score": candidate.get("quant_sell_score"),
            "ai_buy_score": candidate.get("ai_buy_score"),
            "ai_sell_score": candidate.get("ai_sell_score"),
            "final_buy_score": candidate.get("final_buy_score"),
            "final_sell_score": candidate.get("final_sell_score"),
            "gpt_analysis_status": str(
                candidate.get("gpt_analysis_status") or "not_run"
            ).strip().lower(),
            "gpt_used": bool(candidate.get("gpt_used")),
            "gpt_reason": candidate.get("gpt_reason"),
            "ai_reason": candidate.get("ai_reason"),
            "why_hold": candidate.get("why_hold"),
            "why_not_buy": candidate.get("why_not_buy"),
            "risk_flags": _dedupe(
                [
                    *_strings(candidate.get("risk_flags")),
                    *_strings(target_risk.get("risk_flags")),
                ]
            ),
            "gating_notes": _dedupe(
                [
                    *_strings(candidate.get("gating_notes")),
                    *_strings(target_risk.get("gating_notes")),
                ]
            ),
            "raw": candidate,
        }

    def _decision(
        self,
        selected: dict[str, Any] | None,
        *,
        market_session: dict[str, Any],
        profile: dict[str, Any],
        preview: dict[str, Any],
    ) -> dict[str, Any]:
        if selected is None:
            return {
                "action": "hold",
                "reason": "no_candidates",
                "target_risk_approved": False,
                "recommended_notional_krw": 0.0,
                "recommended_notional_pct": 0.0,
                "simulated_quantity": 0,
                "simulated_notional_krw": 0.0,
            }
        if market_session.get("is_market_open") is False:
            return self._blocked(selected, "market_closed", action="hold")
        if not selected["data_sufficient"]:
            return self._blocked(selected, "data_quality_blocked")
        threshold = float(profile.get("buy_score_threshold") or 0)
        if selected["buy_score"] is None or selected["buy_score"] < threshold:
            return self._blocked(selected, "below_profile_buy_threshold")
        target = selected["target_risk_result"]
        if target.get("approved") is not True:
            return self._blocked(
                selected,
                _risk_reason(str(target.get("block_reason") or "risk_blocked")),
            )
        price = float(selected["price"] or 0)
        recommended = max(
            0.0,
            float(
                target.get("approved_notional_krw")
                or target.get("recommended_notional_krw")
                or 0
            ),
        )
        quantity = math.floor(recommended / price) if price > 0 else 0
        if quantity <= 0:
            return self._blocked(selected, "simulated_quantity_zero")
        return {
            "action": "would_buy",
            "reason": "target_aware_risk_approved",
            "target_risk_approved": True,
            "recommended_notional_krw": recommended,
            "recommended_notional_pct": float(
                target.get("profile_thresholds", {}).get("max_order_notional_pct")
                or profile.get("max_order_notional_pct")
                or 0
            )
            * float(target.get("sizing_multiplier") or 1),
            "simulated_quantity": quantity,
            "simulated_notional_krw": round(quantity * price, 2),
        }

    def _blocked(
        self,
        selected: dict[str, Any],
        reason: str,
        *,
        action: str = "blocked",
    ) -> dict[str, Any]:
        target = selected.get("target_risk_result") or {}
        return {
            "action": action,
            "reason": reason,
            "target_risk_approved": target.get("approved") is True,
            "recommended_notional_krw": max(
                0.0,
                float(target.get("recommended_notional_krw") or 0),
            ),
            "recommended_notional_pct": 0.0,
            "simulated_quantity": 0,
            "simulated_notional_krw": 0.0,
        }

    def _response(
        self,
        *,
        request: ProfileAwareDryRunAutoBuyRequest,
        profile: dict[str, Any],
        preview: dict[str, Any],
        evaluated: list[dict[str, Any]],
        selected: dict[str, Any] | None,
        decision: dict[str, Any],
        legacy_profile_name: str,
        automation_profile_key: str | None,
        automation_profile_name: str | None,
        now_utc: datetime,
    ) -> dict[str, Any]:
        target = selected.get("target_risk_result") if selected else {}
        selected_observability = (
            candidate_gpt_quant_observability(
                selected.get("raw"),
                evaluated=selected,
            )
            if selected
            else {}
        )
        risk_flags = _dedupe(
            [
                "dry_run_only",
                "profile_aware",
                "target_aware",
                *_strings(preview.get("risk_flags")),
                *_strings(selected.get("risk_flags") if selected else []),
                *(([decision["reason"]]) if decision["action"] != "would_buy" else []),
            ]
        )
        gating_notes = _dedupe(
            [
                "Profile-aware dry-run simulation only; no real order submitted.",
                "KIS validation and broker submit were not called.",
                *_strings(preview.get("gating_notes")),
                *_strings(selected.get("gating_notes") if selected else []),
            ]
        )
        target_quality_notes = (
            _strings((target or {}).get("data_quality_notes"))
            if isinstance(target, dict)
            else []
        )
        target_quality_reasons = (
            _strings((target or {}).get("data_quality_reduction_reasons"))
            if isinstance(target, dict)
            else []
        )
        quality_notes = _dedupe(
            [
                *target_quality_notes,
                *(
                    ["candidate_data_insufficient"]
                    if selected and not selected["data_sufficient"]
                    else []
                ),
                *(
                    ["no_candidate_available"]
                    if selected is None
                    else []
                ),
            ]
        )
        return {
            "status": "ok",
            "action": decision["action"],
            "provider": str(request.provider).lower(),
            "market": str(request.market).upper(),
            "active_profile": profile["profile_name"],
            "profile_key": profile.get("profile_key") or profile["profile_name"],
            "profile_name": legacy_profile_name,
            "automation_profile_key": automation_profile_key,
            "automation_profile_name": automation_profile_name,
            "legacy_profile_name": legacy_profile_name,
            "profile_provider": profile.get("provider") or request.provider,
            "profile_market": profile.get("market") or request.market,
            "selected_symbol": selected.get("symbol") if selected else None,
            "selected_symbol_name": selected.get("name") if selected else None,
            "candidate_count": len(evaluated),
            **_preview_observability(preview, evaluated_count=len(evaluated)),
            "candidates": [_public_candidate(item) for item in evaluated],
            "buy_score": selected.get("buy_score") if selected else None,
            "final_buy_score": selected.get("final_score") if selected else None,
            "sell_score": selected.get("sell_score") if selected else None,
            "final_score": selected.get("final_score") if selected else None,
            "selected_quant_buy_score": selected_observability.get("quant_buy_score"),
            "selected_quant_sell_score": selected_observability.get("quant_sell_score"),
            "selected_ai_buy_score": selected_observability.get("ai_buy_score"),
            "selected_ai_sell_score": selected_observability.get("ai_sell_score"),
            "selected_gpt_analysis_status": selected_observability.get(
                "gpt_analysis_status"
            ),
            "selected_gpt_used": bool(selected_observability.get("gpt_used")),
            "selected_gpt_reason": selected_observability.get("gpt_reason"),
            "selected_final_buy_score": selected_observability.get(
                "final_buy_score"
            ),
            "selected_final_sell_score": selected_observability.get(
                "final_sell_score"
            ),
            "selected_confidence": selected_observability.get("confidence"),
            "selected_candidate_observability": selected_observability,
            "required_entry_score": float(profile.get("buy_score_threshold") or 0),
            "confidence": selected.get("confidence") if selected else None,
            "target_risk_approved": decision["target_risk_approved"],
            "target_risk_result": target or {},
            "recommended_notional_krw": decision["recommended_notional_krw"],
            "recommended_notional_pct": decision["recommended_notional_pct"],
            "simulated_quantity": decision["simulated_quantity"],
            "simulated_price": selected.get("price") if selected else None,
            "simulated_notional_krw": decision["simulated_notional_krw"],
            "reason": decision["reason"],
            "risk_flags": risk_flags,
            "gating_notes": gating_notes,
            "signal_id": None,
            "trade_run_id": None,
            "simulated_order_id": None,
            "data_quality": {
                "sufficient_for_would_buy": bool(
                    selected and selected["data_sufficient"]
                ),
                "notes": quality_notes,
                "limited": bool((target or {}).get("data_quality_limited"))
                if isinstance(target, dict)
                else False,
                "reduction_reasons": target_quality_reasons,
                "preview_error": preview.get("preview_error"),
            },
            "data_quality_limited": bool((target or {}).get("data_quality_limited"))
            if isinstance(target, dict)
            else False,
            "data_quality_notes": quality_notes,
            "data_quality_reduction_reasons": target_quality_reasons,
            "sizing_mode": (target or {}).get("sizing_mode", "equity_pct")
            if isinstance(target, dict)
            else "equity_pct",
            "fixed_budget_krw": float((target or {}).get("fixed_budget_krw") or 0)
            if isinstance(target, dict)
            else 0.0,
            "target_position_pct": float(
                (target or {}).get("target_position_pct") or 0
            )
            if isinstance(target, dict)
            else 0.0,
            "available_cash_krw": (target or {}).get("available_cash_krw")
            if isinstance(target, dict)
            else None,
            "total_assets_krw": (target or {}).get("total_assets_krw")
            if isinstance(target, dict)
            else None,
            "configured_max_order_notional_krw": float(
                (target or {}).get("configured_max_order_notional_krw") or 0
            )
            if isinstance(target, dict)
            else 0.0,
            "hard_max_order_notional_krw": float(
                (target or {}).get("hard_max_order_notional_krw") or 1_000_000
            )
            if isinstance(target, dict)
            else 1_000_000.0,
            "base_order_cap_krw": float(
                (target or {}).get("base_order_cap_krw") or 0
            )
            if isinstance(target, dict)
            else 0.0,
            "effective_max_order_notional_krw": float(
                (target or {}).get("effective_max_order_notional_krw") or 0
            )
            if isinstance(target, dict)
            else 0.0,
            "order_cap_source": (target or {}).get("order_cap_source", "equity_pct")
            if isinstance(target, dict)
            else "equity_pct",
            "safety": _safety(),
            "created_at": now_utc.isoformat(),
        }

    def _save_signal(
        self,
        db: Session,
        *,
        response: dict[str, Any],
        selected: dict[str, Any] | None,
    ) -> SignalLog:
        candidate = selected.get("raw") if selected else {}
        signal = SignalLog(
            symbol=str(response.get("selected_symbol") or "WATCHLIST"),
            action="buy" if response["action"] == "would_buy" else "hold",
            buy_score=response.get("buy_score"),
            sell_score=response.get("sell_score"),
            confidence=response.get("confidence"),
            reason=response["reason"],
            indicator_payload=_json(
                candidate.get("indicator_payload")
                if isinstance(candidate, dict)
                else {}
            ),
            quant_buy_score=_score(candidate, "quant_buy_score", "quant_score"),
            quant_sell_score=_score(candidate, "quant_sell_score"),
            ai_buy_score=_score(candidate, "ai_buy_score", "gpt_buy_score"),
            ai_sell_score=_score(candidate, "ai_sell_score", "gpt_sell_score"),
            final_buy_score=_score(
                candidate,
                "final_buy_score",
                "final_entry_score",
                "final_score",
            ) or response.get("final_score"),
            final_sell_score=_score(
                candidate,
                "final_sell_score",
                "final_score",
            ) or response.get("sell_score"),
            quant_reason=str(candidate.get("quant_reason") or "") or None,
            ai_reason=str(candidate.get("gpt_reason") or candidate.get("ai_reason") or "")
            or None,
            risk_flags=_json(response["risk_flags"]),
            approved_by_risk=response["target_risk_approved"],
            position_size_pct=response["recommended_notional_pct"],
            signal_status=response["action"],
            trigger_source=TRIGGER_SOURCE,
            # Keep the legacy signal column compatible; custom identity is
            # persisted in the run/order payload fields above.
            gate_profile_name=response["legacy_profile_name"],
            hard_block_reason=(
                response["reason"] if response["action"] != "would_buy" else None
            ),
            hard_blocked=response["action"] == "blocked",
            gating_notes=_json(response["gating_notes"]),
        )
        db.add(signal)
        db.flush()
        return signal

    def _save_simulated_order(
        self,
        db: Session,
        *,
        response: dict[str, Any],
        signal_id: int,
    ) -> OrderLog:
        order = OrderLog(
            broker=PROVIDER,
            market=MARKET,
            symbol=response["selected_symbol"],
            side="buy",
            order_type="market",
            qty=response["simulated_quantity"],
            requested_qty=response["simulated_quantity"],
            notional=response["simulated_notional_krw"],
            broker_order_id=None,
            kis_odno=None,
            internal_status=InternalOrderStatus.DRY_RUN_SIMULATED.value,
            broker_status="SIMULATED",
            broker_order_status="SIMULATED",
            submitted_at=datetime.now(UTC),
            request_payload=_json(
                {
                    "mode": MODE,
                    "trigger_source": TRIGGER_SOURCE,
                    "signal_id": signal_id,
                    "active_profile": response["active_profile"],
                    "profile_key": response.get("profile_key"),
                    "profile_name": response.get("profile_name"),
                    "automation_profile_key": response.get("automation_profile_key"),
                    "automation_profile_name": response.get("automation_profile_name"),
                    "legacy_profile_name": response.get("legacy_profile_name"),
                    "profile_provider": response.get("profile_provider"),
                    "profile_market": response.get("profile_market"),
                    "target_risk_result": response["target_risk_result"],
                    "simulated_quantity": response["simulated_quantity"],
                    "simulated_price": response["simulated_price"],
                    "simulated_notional_krw": response["simulated_notional_krw"],
                    "safety": _safety(),
                }
            ),
            response_payload=_json(
                {
                    "internal_status": "DRY_RUN_SIMULATED",
                    "broker_status": "SIMULATED",
                    "real_order_submitted": False,
                    "validation_called": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                }
            ),
        )
        db.add(order)
        db.flush()
        return order

    def _save_run(
        self,
        db: Session,
        *,
        response: dict[str, Any],
        request: ProfileAwareDryRunAutoBuyRequest,
        signal_id: int,
        order_id: int | None,
    ) -> TradeRunLog:
        run = TradeRunLog(
            run_key=f"strategy_dry_buy_{uuid.uuid4().hex[:12]}",
            trigger_source=TRIGGER_SOURCE,
            symbol=str(response.get("selected_symbol") or "WATCHLIST"),
            mode=MODE,
            stage="done",
            result=response["action"],
            reason=response["reason"],
            signal_id=signal_id,
            order_id=order_id,
            request_payload=_json(
                {
                    **request.model_dump(mode="json"),
                    "mode": MODE,
                    "active_profile": response["active_profile"],
                    "profile_key": response.get("profile_key"),
                    "profile_name": response.get("profile_name"),
                    "automation_profile_key": response.get("automation_profile_key"),
                    "automation_profile_name": response.get("automation_profile_name"),
                    "legacy_profile_name": response.get("legacy_profile_name"),
                    "profile_provider": response.get("profile_provider"),
                    "profile_market": response.get("profile_market"),
                    "dry_run": True,
                    "real_order_submitted": False,
                    "validation_called": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                }
            ),
            response_payload=_json(response),
        )
        db.add(run)
        db.flush()
        return run


def _candidate_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        0 if item.get("target_risk_approved") else 1,
        -float(item.get("final_score") or -1),
        -float(item.get("buy_score") or -1),
        float(item.get("atr_risk") if item.get("atr_risk") is not None else 999),
        -float(item.get("volume_ratio") or 0),
        str(item.get("symbol") or ""),
    )


def _public_candidate(item: dict[str, Any]) -> dict[str, Any]:
    public = candidate_gpt_quant_observability(item.get("raw"), evaluated=item)
    public.update(
        {
            "entry_ready": item.get("entry_ready"),
            "atr_risk": item.get("atr_risk"),
            "volume_ratio": item.get("volume_ratio"),
            "data_sufficient": item.get("data_sufficient"),
            "target_risk_approved": item.get("target_risk_approved"),
            "risk_flags": item.get("risk_flags") or [],
            "gating_notes": item.get("gating_notes") or [],
        }
    )
    return public


def _risk_reason(value: str) -> str:
    if value == "monthly_target_hit_entry_blocked":
        return "target_blocked"
    if value in {"daily_loss_limit_hit", "daily_trade_limit_hit"}:
        return "daily_limit_blocked"
    if value == "max_positions_hit":
        return "position_limit_blocked"
    if value == "performance_data_quality_limited":
        return "data_quality_blocked"
    return "risk_blocked"


def _atr_risk(candidate: dict[str, Any], price: float | None) -> float | None:
    indicators = (
        candidate.get("indicator_payload")
        if isinstance(candidate.get("indicator_payload"), dict)
        else candidate
    )
    atr = _score(indicators, "atr")
    if atr is None or price is None or price <= 0:
        return None
    return round(atr / price, 8)


def _symbol(value: dict[str, Any]) -> str | None:
    symbol = str(value.get("symbol") or "").strip().upper()
    return symbol or None


def _score(value: Any, *keys: str) -> float | None:
    if not isinstance(value, dict):
        return None
    for key in keys:
        raw = value.get(key)
        if raw is None:
            continue
        try:
            return float(str(raw).replace(",", ""))
        except Exception:
            continue
    return None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _safety() -> dict[str, Any]:
    return {
        "dry_run_only": True,
        "read_only": False,
        "real_order_submitted": False,
        "validation_called": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "scheduler_changed": False,
        "setting_changed": False,
        "live_order_action_created": False,
    }


def _json(value: Any) -> str:
    return json.dumps(
        sanitize_kis_payload(value),
        ensure_ascii=False,
        default=str,
    )


def _parse_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _normalize_preview_payload(
    value: Any,
    *,
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    payload = dict(value) if isinstance(value, dict) else {}
    payload.setdefault("provider", PROVIDER)
    payload.setdefault("market", MARKET)
    payload.setdefault("final_ranked_candidates", [])
    payload.setdefault("risk_flags", [])
    payload.setdefault("gating_notes", [])
    payload.setdefault("preview_status", status)
    payload.setdefault("preview_error", error)
    return sanitize_kis_payload(payload)


def _unavailable_preview_payload(
    reason: str,
    *,
    error: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    return _normalize_preview_payload(
        {
            "provider": PROVIDER,
            "market": MARKET,
            "final_ranked_candidates": [],
            "risk_flags": [reason],
            "gating_notes": [note or "Watchlist preview service is unavailable."],
        },
        status="unavailable",
        error=error or reason,
    )


def _select_executable_candidate(evaluated: list[dict[str, Any]], *, profile: dict[str, Any]) -> dict[str, Any] | None:
    threshold = max(65.0, float(profile.get('buy_score_threshold') or 0.0))
    for item in evaluated:
        score = item.get('buy_score')
        if score is None or float(score) < threshold:
            continue
        if not item.get('data_sufficient') or item.get('target_risk_approved') is not True:
            continue
        price = _score(item, 'price')
        target = item.get('target_risk_result')
        target = target if isinstance(target, dict) else {}
        approved = _score(target, 'approved_notional_krw', 'recommended_notional_krw')
        if price is None or price <= 0 or approved is None or approved <= 0:
            continue
        if math.floor(approved / price) < 1:
            continue
        return item
    return evaluated[0] if evaluated else None


def _preview_observability(
    preview: dict[str, Any],
    *,
    evaluated_count: int,
) -> dict[str, Any]:
    final_candidates = preview.get("final_ranked_candidates")
    if not isinstance(final_candidates, list):
        final_candidates = []
    quant_candidates = preview.get("quant_candidates_count")
    if not isinstance(quant_candidates, int):
        quant_candidates = len(preview.get("top_quant_candidates") or [])
    gpt_candidates = preview.get("gpt_target_count")
    if not isinstance(gpt_candidates, int):
        gpt_candidates = len(preview.get("gpt_target_symbols") or [])
    items = preview.get('items')
    if not isinstance(items, list):
        items = final_candidates
    gpt_items = [item for item in items if isinstance(item, dict)]
    gpt_counts = gpt_result_counts(gpt_items)
    quant_scored = preview.get('quant_scored_count')
    if not isinstance(quant_scored, int):
        quant_scored = sum(
            1
            for item in items
            if isinstance(item, dict)
            and _score(item, 'quant_buy_score', 'quant_score') is not None
        )
    eligible = preview.get('profile_eligible_symbol_count')
    if not isinstance(eligible, (int, float)):
        eligible = _preview_count(preview, 'analyzed_symbol_count', 'items')
    filtered = preview.get('profile_price_filtered_count')
    if not isinstance(filtered, (int, float)):
        filtered = 0
    exclusions = preview.get('profile_exclusion_counts')
    if not isinstance(exclusions, dict):
        exclusions = {}
    return {
        "configured_symbol_count": _preview_count(
            preview, "configured_symbol_count", "watchlist"
        ),
        "analyzed_symbol_count": _preview_count(
            preview, "analyzed_symbol_count", "items"
        ),
        "quant_candidate_count": int(quant_candidates or 0),
        "quant_scored_count": int(quant_scored or 0),
        "gpt_candidate_count": int(gpt_candidates or 0),
        "gpt_target_count": int(gpt_candidates or 0),
        **gpt_counts,
        "final_candidate_count": len(final_candidates),
        "final_ranked_count": len(final_candidates),
        "profile_eligible_symbol_count": int(eligible or 0),
        "profile_price_filtered_count": int(filtered or 0),
        "execution_candidate_count": int(evaluated_count),
        "profile_exclusion_counts": {
            str(key): int(value)
            for key, value in exclusions.items()
            if isinstance(value, (int, float))
        },
        "preview_status": str(preview.get("preview_status") or "unknown"),
        "preview_error": preview.get("preview_error"),
    }


def _preview_count(
    preview: dict[str, Any],
    key: str,
    fallback_key: str,
) -> int:
    value = preview.get(key)
    if isinstance(value, (int, float)):
        return int(value)
    fallback = preview.get(fallback_key)
    return len(fallback) if isinstance(fallback, list) else 0


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except Exception:
        return None


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.isoformat()


def _utc_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _empty_counts() -> dict[str, int]:
    return {
        "total": 0,
        "would_buy": 0,
        "hold": 0,
        "blocked": 0,
    }


def _increment(bucket: dict[str, int], action: str) -> None:
    bucket["total"] = bucket.get("total", 0) + 1
    key = action if action in {"would_buy", "hold", "blocked"} else "blocked"
    bucket[key] = bucket.get(key, 0) + 1


def _counts(items: list[dict[str, Any]]) -> dict[str, int]:
    result = _empty_counts()
    for item in items:
        _increment(result, str(item.get("action") or "hold"))
    return result
