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
from app.services.market_profile_service import MarketProfileService
from app.services.market_session_service import MarketSessionService
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
        profile_row = (
            self.strategy_profiles.get_profile(db, payload.profile_name)
            if payload.profile_name
            else self.strategy_profiles.active_profile(db)
        )
        profile = self.strategy_profiles.serialize_profile(profile_row)
        preview = self._preview(
            db,
            request=payload,
            preview_override=preview_override,
        )
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
                profile_name=profile["profile_name"],
            )
            for candidate in candidates
        ]
        evaluated.sort(key=_candidate_sort_key)
        selected = evaluated[0] if evaluated else None
        decision = self._decision(
            selected,
            market_session=market_session,
            profile=profile,
            preview=preview,
        )
        response = self._response(
            request=payload,
            profile=profile,
            preview=preview,
            evaluated=evaluated,
            selected=selected,
            decision=decision,
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
    ) -> dict[str, Any]:
        if preview_override is not None:
            return sanitize_kis_payload(dict(preview_override))
        if self.preview_service is None:
            return {
                "provider": PROVIDER,
                "market": MARKET,
                "final_ranked_candidates": [],
                "risk_flags": ["preview_service_unavailable"],
                "gating_notes": ["Watchlist preview service is unavailable."],
            }
        if request.symbol:
            return self._single_symbol_preview(db, request.symbol)
        if not request.use_watchlist:
            return {
                "provider": PROVIDER,
                "market": MARKET,
                "final_ranked_candidates": [],
                "risk_flags": ["watchlist_disabled_for_request"],
                "gating_notes": ["No symbol was supplied and watchlist use was disabled."],
            }
        try:
            return sanitize_kis_payload(
                self.preview_service.run_preview(
                    include_gpt=True,
                    db=db,
                    record_run=False,
                    trigger_source=TRIGGER_SOURCE,
                )
            )
        except TypeError:
            return sanitize_kis_payload(
                self.preview_service.run_preview(include_gpt=True, db=db)
            )
        except Exception as exc:
            return {
                "provider": PROVIDER,
                "market": MARKET,
                "final_ranked_candidates": [],
                "risk_flags": ["preview_unavailable"],
                "gating_notes": [f"Watchlist preview failed: {exc.__class__.__name__}"],
            }

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
        now_utc: datetime,
    ) -> dict[str, Any]:
        target = selected.get("target_risk_result") if selected else {}
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
        quality_notes = _dedupe(
            [
                *_strings(
                    (target or {}).get("risk_flags")
                    if isinstance(target, dict)
                    else []
                ),
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
            "selected_symbol": selected.get("symbol") if selected else None,
            "selected_symbol_name": selected.get("name") if selected else None,
            "candidate_count": len(evaluated),
            "candidates": [_public_candidate(item) for item in evaluated],
            "buy_score": selected.get("buy_score") if selected else None,
            "sell_score": selected.get("sell_score") if selected else None,
            "final_score": selected.get("final_score") if selected else None,
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
                "preview_error": preview.get("preview_error"),
            },
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
            final_buy_score=response.get("final_score"),
            final_sell_score=response.get("sell_score"),
            quant_reason=str(candidate.get("quant_reason") or "") or None,
            ai_reason=str(candidate.get("gpt_reason") or candidate.get("ai_reason") or "")
            or None,
            risk_flags=_json(response["risk_flags"]),
            approved_by_risk=response["target_risk_approved"],
            position_size_pct=response["recommended_notional_pct"],
            signal_status=response["action"],
            trigger_source=TRIGGER_SOURCE,
            gate_profile_name=response["active_profile"],
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
    return {
        key: item.get(key)
        for key in (
            "symbol",
            "name",
            "buy_score",
            "sell_score",
            "final_score",
            "confidence",
            "price",
            "entry_ready",
            "atr_risk",
            "volume_ratio",
            "data_sufficient",
            "target_risk_approved",
            "risk_flags",
            "gating_notes",
        )
    }


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
