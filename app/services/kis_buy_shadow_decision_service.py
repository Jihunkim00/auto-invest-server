from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.core.constants import DEFAULT_GATE_LEVEL, MAX_DAILY_LOSS_PCT
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.services.gpt_hard_block_policy import should_apply_gpt_hard_block
from app.services.kis_dry_run_risk_service import BUY, HOLD, MARKET, OPEN_ORDER_STATUSES, PROVIDER
from app.services.kis_order_sync_service import KisOrderSyncService, serialize_kis_order
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.kis_watchlist_preview_service import KisWatchlistPreviewService
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "shadow_buy_dry_run"
SOURCE = "kis_buy_shadow_decision"
SOURCE_TYPE = "dry_run_buy_simulation"
TRIGGER_SOURCE = "kis_buy_shadow"
KR_TZ = ZoneInfo("Asia/Seoul")

BUY_ORDER_STATUSES = {
    InternalOrderStatus.DRY_RUN_SIMULATED.value,
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}

SHADOW_GATING_NOTES = [
    "shadow_buy_only",
    "dry_run_buy_simulation",
    "no_broker_submit",
    "no_manual_submit",
    "live_auto_buy_disabled",
    "scheduler_real_orders_disabled",
]


@dataclass(frozen=True)
class _BuyShadowCandidate:
    symbol: str
    market: str
    provider: str
    final_score: float | None
    confidence: float | None
    quant_score: float | None
    gpt_buy_score: float | None
    current_price: float | None
    suggested_notional: float | None
    suggested_quantity: int | None
    reason: str
    risk_flags: list[str]
    gating_notes: list[str]
    audit_metadata: dict[str, Any]
    raw: dict[str, Any]


class KisBuyShadowDecisionService:
    """Read-only KIS buy-side shadow decision layer.

    This service prepares future buy automation by selecting a hypothetical
    candidate and explaining gates. It deliberately has no broker wrapper and
    no dependency on the manual submit service.
    """

    def __init__(
        self,
        client: KisClient,
        *,
        preview_service: KisWatchlistPreviewService | None = None,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
    ):
        self.client = client
        self.preview_service = preview_service or KisWatchlistPreviewService(client)
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()

    def run_once(
        self,
        db: Session,
        *,
        gate_level: int = DEFAULT_GATE_LEVEL,
        now: datetime | None = None,
        preview_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc_now(now)
        created_at = now_utc.isoformat()
        runtime = self.runtime_settings.get_settings(db)
        settings = self.client.settings
        market_session = self._market_session(now_utc)
        preview = self._preview(db, gate_level=gate_level, preview_override=preview_override)
        account_state = self._fetch_account_state(db, preview=preview)
        checks = self._base_checks(
            runtime,
            settings,
            market_session,
            account_state,
        )

        candidate, block_reason, failed_checks = self._select_candidate(
            db,
            runtime=runtime,
            preview=preview,
            account_state=account_state,
            market_session=market_session,
            checks=checks,
            now_utc=now_utc,
        )
        decision = _decision(candidate, block_reason)
        action = BUY if decision == "would_buy" else HOLD
        reason = (
            candidate.reason
            if candidate is not None and decision == "would_buy"
            else block_reason or "no_shadow_buy_candidate"
        )
        candidate_payload = (
            _candidate_payload(candidate, reason=reason, created_at=created_at)
            if candidate is not None
            else None
        )
        risk_flags = _dedupe(
            ["shadow_buy_only", "dry_run_buy_simulation"]
            + _account_warning_flags(account_state)
            + _string_list(candidate.risk_flags if candidate else [])
            + failed_checks
        )
        gating_notes = _dedupe(
            list(SHADOW_GATING_NOTES)
            + _string_list(candidate.gating_notes if candidate else [])
            + _gating_notes_for_failed_checks(failed_checks)
        )
        checks.update(
            {
                "selected_candidate": candidate.symbol if candidate else None,
                "score_threshold_ok": "score_threshold" not in failed_checks,
                "confidence_threshold_ok": "confidence_threshold" not in failed_checks,
                "notional_cap_ok": "notional_cap" not in failed_checks,
                "entry_allowed_now": "entry_time" not in failed_checks,
            }
        )

        payload: dict[str, Any] = {
            "status": "ok",
            "provider": PROVIDER,
            "market": MARKET,
            "mode": MODE,
            "source": SOURCE,
            "source_type": SOURCE_TYPE,
            "trigger_source": TRIGGER_SOURCE,
            "decision": decision,
            "action": action,
            "result": decision,
            "reason": reason,
            "dry_run": True,
            "simulated": True,
            "preview_only": True,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "real_order_submit_allowed": False,
            "auto_buy_enabled": False,
            "auto_sell_enabled": False,
            "scheduler_real_order_enabled": False,
            "candidate": candidate_payload,
            "candidates": [candidate_payload] if candidate_payload else [],
            "candidate_count": 1 if candidate_payload else 0,
            "checks": checks,
            "failed_checks": failed_checks,
            "safety": _safety_payload(runtime),
            "risk_flags": risk_flags,
            "gating_notes": gating_notes,
            "created_at": created_at,
            "checked_at": created_at,
            "order_id": None,
            "broker_order_id": None,
            "kis_odno": None,
            "symbol": candidate.symbol if candidate else None,
            "final_score": candidate.final_score if candidate else None,
            "confidence": candidate.confidence if candidate else None,
            "quant_score": candidate.quant_score if candidate else None,
            "gpt_buy_score": candidate.gpt_buy_score if candidate else None,
            "current_price": candidate.current_price if candidate else None,
            "suggested_notional": candidate.suggested_notional if candidate else None,
            "suggested_quantity": candidate.suggested_quantity if candidate else None,
            "account_state": _account_state_summary(account_state),
            "market_session": _public_market_session(market_session, runtime),
        }
        signal = self._create_signal(
            db,
            payload=payload,
            candidate=candidate,
            gate_level=gate_level,
        )
        run = self._create_run(
            db,
            payload=payload,
            signal=signal,
            gate_level=gate_level,
        )
        payload["signal_id"] = signal.id
        payload["run"] = _serialize_run(run)
        db.commit()
        return payload

    def _preview(
        self,
        db: Session,
        *,
        gate_level: int,
        preview_override: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if preview_override is not None:
            return sanitize_kis_payload(dict(preview_override))
        try:
            payload = self.preview_service.run_preview(
                include_gpt=True,
                gate_level=gate_level,
                db=db,
                record_run=False,
                trigger_source=TRIGGER_SOURCE,
            )
            return sanitize_kis_payload(payload)
        except TypeError:
            payload = self.preview_service.run_preview(
                include_gpt=True,
                gate_level=gate_level,
                db=db,
            )
            return sanitize_kis_payload(payload)
        except Exception as exc:
            return {
                "provider": PROVIDER,
                "market": MARKET,
                "preview_error": _safe_error(exc),
                "final_ranked_candidates": [],
                "held_positions": [],
                "held_symbols": [],
                "risk_flags": ["preview_unavailable"],
                "gating_notes": ["KIS buy shadow could not load watchlist preview."],
            }

    def _market_session(self, now_utc: datetime) -> dict[str, Any]:
        try:
            return self.session_service.get_session_status(MARKET, now=now_utc)
        except Exception as exc:
            return {
                "market": MARKET,
                "timezone": "Asia/Seoul",
                "is_market_open": False,
                "is_entry_allowed_now": False,
                "error": _safe_error(exc),
            }

    def _fetch_account_state(
        self,
        db: Session,
        *,
        preview: dict[str, Any],
    ) -> dict[str, Any]:
        state: dict[str, Any] = {
            "provider": PROVIDER,
            "market": MARKET,
            "balance": None,
            "positions": [],
            "open_orders": [],
            "recent_orders": [],
            "warnings": [],
            "fetch_success": True,
        }
        try:
            state["balance"] = self.client.get_account_balance()
        except Exception as exc:
            state["fetch_success"] = False
            state["warnings"].append(f"balance_unavailable:{exc.__class__.__name__}")
        try:
            state["positions"] = [
                _normalize_position(item) for item in self.client.list_positions()
            ]
        except Exception as exc:
            state["warnings"].append(f"positions_unavailable:{exc.__class__.__name__}")
            state["positions"] = _dict_list(preview.get("held_positions"))
        try:
            state["open_orders"] = [
                _normalize_order(item) for item in self.client.list_open_orders()
            ]
        except Exception as exc:
            state["warnings"].append(f"open_orders_unavailable:{exc.__class__.__name__}")
        try:
            rows = KisOrderSyncService.recent_orders(
                db,
                limit=50,
                include_rejected=True,
            )
            state["recent_orders"] = [serialize_kis_order(row) for row in rows]
        except Exception as exc:
            state["warnings"].append(f"recent_orders_unavailable:{exc.__class__.__name__}")
        return sanitize_kis_payload(state)

    def _base_checks(
        self,
        runtime: dict[str, Any],
        settings: Any,
        market_session: dict[str, Any],
        account_state: dict[str, Any],
    ) -> dict[str, Any]:
        scheduler_real_orders = bool(
            getattr(settings, "kis_scheduler_allow_real_orders", False)
            or getattr(settings, "kr_scheduler_allow_real_orders", False)
        )
        held_count = len(_held_symbols({}, account_state))
        return {
            "kis_limited_auto_buy_enabled": bool(
                runtime.get("kis_limited_auto_buy_enabled", False)
            ),
            "kis_limited_auto_buy_shadow_enabled": bool(
                runtime.get("kis_limited_auto_buy_shadow_enabled", True)
            ),
            "kis_limited_auto_buy_requires_shadow_review": bool(
                runtime.get("kis_limited_auto_buy_requires_shadow_review", True)
            ),
            "kis_live_auto_enabled": bool(runtime.get("kis_live_auto_enabled", False)),
            "kis_live_auto_buy_enabled": bool(
                runtime.get("kis_live_auto_buy_enabled", False)
            ),
            "kis_enabled": bool(getattr(settings, "kis_enabled", False)),
            "kis_real_order_enabled": bool(
                getattr(settings, "kis_real_order_enabled", False)
            ),
            "dry_run": True,
            "runtime_dry_run": bool(runtime.get("dry_run", True)),
            "kill_switch": bool(runtime.get("kill_switch", False)),
            "market_open": market_session.get("is_market_open") is True,
            "entry_allowed_now": market_session.get("is_entry_allowed_now") is True,
            "position_count": held_count,
            "max_positions_ok": held_count
            < int(runtime.get("kis_limited_auto_buy_max_positions", 3) or 3),
            "daily_buy_limit_ok": True,
            "notional_cap_ok": True,
            "score_threshold_ok": True,
            "confidence_threshold_ok": True,
            "gpt_hard_block_new_buy": False,
            "auto_buy_enabled": False,
            "scheduler_real_order_enabled": False,
            "configured_scheduler_real_order_enabled": scheduler_real_orders,
            "scheduler_real_orders_disabled": scheduler_real_orders is False,
            "account_state_available": bool(account_state.get("fetch_success")),
            "real_order_submit_allowed": False,
        }

    def _select_candidate(
        self,
        db: Session,
        *,
        runtime: dict[str, Any],
        preview: dict[str, Any],
        account_state: dict[str, Any],
        market_session: dict[str, Any],
        checks: dict[str, Any],
        now_utc: datetime,
    ) -> tuple[_BuyShadowCandidate | None, str | None, list[str]]:
        failed: list[str] = []
        if not bool(runtime.get("kis_limited_auto_buy_shadow_enabled", True)):
            failed.append("shadow_disabled")
            return None, "shadow_buy_disabled", failed
        if bool(runtime.get("kill_switch", False)):
            failed.append("kill_switch")
            return None, "kill_switch_enabled", failed
        if bool(runtime.get("kis_limited_auto_buy_require_market_open", True)):
            if market_session.get("is_market_open") is not True:
                failed.append("market_session")
                return None, "market_closed", failed
            if market_session.get("is_entry_allowed_now") is not True:
                failed.append("entry_time")
                return None, "entry_not_allowed_now", failed

        candidates = _candidate_list(preview)
        if not candidates:
            failed.append("candidate")
            return None, "no_shadow_buy_candidate", failed

        held_symbols = _held_symbols(preview, account_state)
        max_positions = max(0, int(runtime.get("kis_limited_auto_buy_max_positions", 3) or 0))
        if len(held_symbols) >= max_positions:
            failed.append("max_positions")
            checks["max_positions_ok"] = False
            return None, "max_positions_reached", failed
        checks["max_positions_ok"] = True

        daily_count = _daily_buy_count(db, now_utc=now_utc)
        max_orders = max(
            0,
            int(runtime.get("kis_limited_auto_buy_max_orders_per_day", 1) or 0),
        )
        checks["daily_buy_count"] = daily_count
        checks["daily_buy_limit_ok"] = daily_count < max_orders
        if daily_count >= max_orders:
            failed.append("daily_buy_limit")
            return None, "daily_buy_limit_reached", failed

        equity = _account_equity(account_state)
        max_notional_pct = float(
            runtime.get("kis_limited_auto_buy_max_notional_pct", 0.03) or 0.03
        )
        max_notional = round(equity * max_notional_pct, 2) if equity else None
        checks["account_equity_available"] = equity is not None and equity > 0
        checks["max_notional"] = max_notional
        if max_notional is None or max_notional <= 0:
            failed.append("account_equity")
            return None, "account_equity_unavailable", failed

        block_reasons: list[str] = []
        for raw in candidates:
            symbol = _symbol(raw)
            if not symbol:
                block_reasons.append("missing_symbol")
                continue
            candidate_failed: list[str] = []
            if (
                bool(runtime.get("kis_limited_auto_buy_block_if_position_exists", True))
                and symbol in held_symbols
            ):
                candidate_failed.append("position_exists")
            if (
                bool(runtime.get("kis_limited_auto_buy_block_if_open_order_exists", True))
                and _open_order_exists(db, symbol=symbol, account_state=account_state)
            ):
                candidate_failed.append("open_order_exists")
            if (
                not bool(runtime.get("kis_limited_auto_buy_allow_reentry_same_day", False))
                and _daily_buy_count(db, now_utc=now_utc, symbol=symbol) > 0
            ):
                candidate_failed.append("same_day_reentry")

            hard_block = _gpt_hard_block(raw)
            checks["gpt_hard_block_new_buy"] = hard_block
            if hard_block and not bool(
                runtime.get("kis_limited_auto_buy_allow_gpt_hard_block", False)
            ):
                candidate_failed.append("gpt_hard_block")

            final_score = _score(raw, "final_score", "final_entry_score", "final_buy_score", "score")
            min_score = float(runtime.get("kis_limited_auto_buy_min_final_score", 75) or 75)
            if final_score is None or final_score < min_score:
                candidate_failed.append("score_threshold")

            quant_score = _score(raw, "quant_score", "quant_buy_score")
            if quant_score is None or quant_score < min_score:
                candidate_failed.append("quant_score_threshold")

            confidence = _score(raw, "confidence", "gpt_confidence")
            min_confidence = float(
                runtime.get("kis_limited_auto_buy_min_confidence", 0.70) or 0.70
            )
            if confidence is None or confidence < min_confidence:
                candidate_failed.append("confidence_threshold")

            price = _score(raw, "current_price", "price")
            if price is None or price <= 0:
                candidate_failed.append("current_price")
            elif price > max_notional:
                candidate_failed.append("notional_cap")

            if _daily_loss_limit_hit(account_state):
                candidate_failed.append("daily_loss_gate")

            if candidate_failed:
                block_reasons.extend(candidate_failed)
                continue

            qty = int(max_notional // float(price or 0))
            if qty <= 0:
                block_reasons.append("notional_cap")
                continue
            suggested_notional = round(float(qty) * float(price or 0), 2)
            candidate = _build_candidate(
                raw,
                symbol=symbol,
                final_score=final_score,
                confidence=confidence,
                quant_score=quant_score,
                suggested_notional=suggested_notional,
                suggested_quantity=qty,
            )
            return candidate, None, []

        reason = _first_priority_block(block_reasons)
        failed.extend(_failed_check_groups(block_reasons))
        if "position_exists" in block_reasons:
            checks["position_exists"] = True
        if "open_order_exists" in block_reasons:
            checks["open_order_exists"] = True
        return None, reason or "no_shadow_buy_candidate", failed

    def _create_signal(
        self,
        db: Session,
        *,
        payload: dict[str, Any],
        candidate: _BuyShadowCandidate | None,
        gate_level: int,
    ) -> SignalLog:
        signal = SignalLog(
            symbol=str(payload.get("symbol") or "WATCHLIST"),
            action=str(payload.get("action") or HOLD),
            buy_score=_score(candidate.raw if candidate else {}, "final_buy_score", "final_entry_score", "score"),
            sell_score=_score(candidate.raw if candidate else {}, "final_sell_score", "quant_sell_score"),
            confidence=_score(candidate.raw if candidate else {}, "confidence"),
            reason=str(payload.get("reason") or "shadow_buy_hold"),
            indicator_payload=_json((candidate.raw if candidate else {}).get("indicator_payload")),
            quant_buy_score=_score(candidate.raw if candidate else {}, "quant_buy_score", "quant_score"),
            quant_sell_score=_score(candidate.raw if candidate else {}, "quant_sell_score"),
            ai_buy_score=_score(candidate.raw if candidate else {}, "ai_buy_score", "gpt_buy_score"),
            ai_sell_score=_score(candidate.raw if candidate else {}, "ai_sell_score"),
            final_buy_score=_score(candidate.raw if candidate else {}, "final_buy_score", "final_entry_score", "score"),
            final_sell_score=_score(candidate.raw if candidate else {}, "final_sell_score"),
            quant_reason=str((candidate.raw if candidate else {}).get("quant_reason") or "") or None,
            ai_reason=str((candidate.raw if candidate else {}).get("gpt_reason") or "") or None,
            risk_flags=_json(payload.get("risk_flags") or []),
            approved_by_risk=False,
            related_order_id=None,
            signal_status="shadow_buy" if payload.get("decision") == "would_buy" else str(payload.get("decision") or "hold"),
            trigger_source=TRIGGER_SOURCE,
            gate_level=gate_level,
            gating_notes=_json(payload.get("gating_notes") or []),
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)
        return signal

    def _create_run(
        self,
        db: Session,
        *,
        payload: dict[str, Any],
        signal: SignalLog,
        gate_level: int,
    ) -> TradeRunLog:
        run = TradeRunLog(
            run_key=f"kis_buy_shadow_{uuid.uuid4().hex[:12]}",
            trigger_source=TRIGGER_SOURCE,
            symbol=str(payload.get("symbol") or "WATCHLIST"),
            mode=MODE,
            gate_level=gate_level,
            stage="done",
            result=str(payload.get("decision") or "hold"),
            reason=str(payload.get("reason") or "shadow_buy_hold"),
            signal_id=signal.id,
            order_id=None,
            request_payload=_json(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": MODE,
                    "source": SOURCE,
                    "source_type": SOURCE_TYPE,
                    "dry_run": True,
                    "simulated": True,
                    "preview_only": True,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                    "real_order_submit_allowed": False,
                    "gate_level": gate_level,
                    "trigger_source": TRIGGER_SOURCE,
                }
            ),
            response_payload=_json({**payload, "signal_id": signal.id}),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run


def _candidate_payload(
    candidate: _BuyShadowCandidate,
    *,
    reason: str,
    created_at: str,
) -> dict[str, Any]:
    payload = {
        "symbol": candidate.symbol,
        "market": candidate.market,
        "provider": candidate.provider,
        "final_score": candidate.final_score,
        "final_buy_score": _score(
            candidate.raw,
            "final_buy_score",
            "final_entry_score",
            "final_score",
            "score",
        ),
        "final_sell_score": _score(candidate.raw, "final_sell_score"),
        "confidence": candidate.confidence,
        "quant_score": candidate.quant_score,
        "quant_buy_score": _score(candidate.raw, "quant_buy_score", "quant_score"),
        "quant_sell_score": _score(candidate.raw, "quant_sell_score"),
        "ai_buy_score": _score(candidate.raw, "ai_buy_score", "gpt_buy_score"),
        "ai_sell_score": _score(candidate.raw, "ai_sell_score", "gpt_sell_score"),
        "gpt_buy_score": candidate.gpt_buy_score,
        "gpt_sell_score": _score(candidate.raw, "gpt_sell_score", "ai_sell_score"),
        "gpt_context": candidate.raw.get("gpt_context") or {},
        "current_price": candidate.current_price,
        "suggested_notional": candidate.suggested_notional,
        "suggested_quantity": candidate.suggested_quantity,
        "company_name": (
            candidate.raw.get("company_name")
            or candidate.raw.get("company")
            or candidate.raw.get("name")
        ),
        "indicator_status": candidate.raw.get("indicator_status"),
        "indicator_payload": candidate.raw.get("indicator_payload") or {},
        "indicator_bar_count": candidate.raw.get("indicator_bar_count"),
        "gate_level": candidate.raw.get("gate_level"),
        "gpt_reason": candidate.raw.get("gpt_reason"),
        "reason": reason,
        "risk_flags": candidate.risk_flags,
        "gating_notes": candidate.gating_notes,
        "audit_metadata": candidate.audit_metadata,
        "created_at": created_at,
    }
    return sanitize_kis_payload(payload)


def _build_candidate(
    raw: dict[str, Any],
    *,
    symbol: str,
    final_score: float | None,
    confidence: float | None,
    quant_score: float | None,
    suggested_notional: float,
    suggested_quantity: int,
) -> _BuyShadowCandidate:
    current_price = _score(raw, "current_price", "price")
    risk_flags = _dedupe(
        ["shadow_buy_only"] + _string_list(raw.get("risk_flags"))
    )
    gating_notes = _dedupe(
        list(SHADOW_GATING_NOTES) + _string_list(raw.get("gating_notes"))
    )
    audit_metadata = {
        "source": SOURCE,
        "source_type": SOURCE_TYPE,
        "real_order_submit_allowed": False,
        "auto_buy_enabled": False,
        "scheduler_real_order_enabled": False,
        "symbol": symbol,
        "final_score": final_score,
        "confidence": confidence,
        "quant_score": quant_score,
        "suggested_notional": suggested_notional,
        "suggested_quantity": suggested_quantity,
    }
    return _BuyShadowCandidate(
        symbol=symbol,
        market=str(raw.get("market") or MARKET),
        provider=PROVIDER,
        final_score=final_score,
        confidence=confidence,
        quant_score=quant_score,
        gpt_buy_score=_score(raw, "gpt_buy_score", "ai_buy_score"),
        current_price=current_price,
        suggested_notional=suggested_notional,
        suggested_quantity=suggested_quantity,
        reason="Shadow buy candidate only. No broker submit.",
        risk_flags=risk_flags,
        gating_notes=gating_notes,
        audit_metadata=audit_metadata,
        raw=sanitize_kis_payload(raw),
    )


def _candidate_list(preview: dict[str, Any]) -> list[dict[str, Any]]:
    raw = preview.get("final_ranked_candidates")
    candidates = [item for item in _dict_list(raw) if _symbol(item)]
    if candidates:
        candidates.sort(
            key=lambda item: _score(item, "final_score", "final_entry_score", "final_buy_score", "score") or -1,
            reverse=True,
        )
        return candidates
    best = preview.get("final_best_candidate")
    if isinstance(best, dict) and _symbol(best):
        return [best]
    return []


def _decision(candidate: _BuyShadowCandidate | None, reason: str | None) -> str:
    if candidate is not None:
        return "would_buy"
    if reason in {
        "no_shadow_buy_candidate",
        "score_threshold_not_met",
        "confidence_threshold_not_met",
        "quant_score_threshold_not_met",
    }:
        return "hold"
    return "blocked" if reason else "hold"


def _first_priority_block(reasons: list[str]) -> str:
    priority = [
        "position_exists",
        "open_order_exists",
        "same_day_reentry",
        "max_positions",
        "daily_buy_limit",
        "daily_loss_gate",
        "market_session",
        "entry_time",
        "gpt_hard_block",
        "current_price",
        "account_equity",
        "notional_cap",
        "quant_score_threshold",
        "score_threshold",
        "confidence_threshold",
    ]
    reason_set = set(reasons)
    for item in priority:
        if item in reason_set:
            return {
                "position_exists": "position_already_exists",
                "open_order_exists": "open_order_exists",
                "same_day_reentry": "same_day_reentry_blocked",
                "max_positions": "max_positions_reached",
                "daily_buy_limit": "daily_buy_limit_reached",
                "daily_loss_gate": "daily_loss_gate_failed",
                "market_session": "market_closed",
                "entry_time": "entry_not_allowed_now",
                "gpt_hard_block": "gpt_hard_block_new_buy",
                "current_price": "current_price_unavailable",
                "account_equity": "account_equity_unavailable",
                "notional_cap": "notional_cap_exceeded",
                "quant_score_threshold": "quant_score_threshold_not_met",
                "score_threshold": "score_threshold_not_met",
                "confidence_threshold": "confidence_threshold_not_met",
            }[item]
    return reasons[0] if reasons else "no_shadow_buy_candidate"


def _failed_check_groups(reasons: list[str]) -> list[str]:
    mapping = {
        "position_exists": "position",
        "open_order_exists": "open_order",
        "same_day_reentry": "daily_reentry",
        "max_positions": "max_positions",
        "daily_buy_limit": "daily_buy_limit",
        "daily_loss_gate": "daily_loss",
        "market_session": "market_session",
        "entry_time": "entry_time",
        "gpt_hard_block": "gpt_hard_block",
        "current_price": "current_price",
        "account_equity": "account_equity",
        "notional_cap": "notional_cap",
        "quant_score_threshold": "quant_score_threshold",
        "score_threshold": "score_threshold",
        "confidence_threshold": "confidence_threshold",
    }
    return _dedupe([mapping.get(reason, reason) for reason in reasons])


def _gating_notes_for_failed_checks(failed: list[str]) -> list[str]:
    notes = []
    for item in failed:
        notes.append(f"shadow_buy_blocked:{item}")
    return notes


def _safety_payload(runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "read_only": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "real_order_submit_allowed": False,
        "auto_buy_enabled": False,
        "auto_sell_enabled": False,
        "scheduler_real_order_enabled": False,
        "live_auto_buy_enabled": False,
        "limited_auto_buy_enabled": bool(
            runtime.get("kis_limited_auto_buy_enabled", False)
        ),
        "shadow_buy_enabled": bool(
            runtime.get("kis_limited_auto_buy_shadow_enabled", True)
        ),
        "max_orders_per_day": int(
            runtime.get("kis_limited_auto_buy_max_orders_per_day", 1) or 1
        ),
        "max_notional_pct": float(
            runtime.get("kis_limited_auto_buy_max_notional_pct", 0.03) or 0.03
        ),
    }


def _public_market_session(
    market_session: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    return {
        "market": market_session.get("market", MARKET),
        "timezone": market_session.get("timezone", "Asia/Seoul"),
        "is_market_open": market_session.get("is_market_open") is True,
        "is_entry_allowed_now": market_session.get("is_entry_allowed_now") is True,
        "no_new_entry_after": runtime.get(
            "kis_limited_auto_buy_no_new_entry_after", "14:50"
        ),
        "closure_reason": market_session.get("closure_reason"),
        "local_time": market_session.get("local_time"),
    }


def _account_state_summary(account_state: dict[str, Any]) -> dict[str, Any]:
    balance = account_state.get("balance") if isinstance(account_state.get("balance"), dict) else {}
    return sanitize_kis_payload(
        {
            "provider": PROVIDER,
            "market": MARKET,
            "fetch_success": bool(account_state.get("fetch_success")),
            "position_count": len(_dict_list(account_state.get("positions"))),
            "open_order_count": len(_dict_list(account_state.get("open_orders"))),
            "recent_order_count": len(_dict_list(account_state.get("recent_orders"))),
            "cash": _first_float(balance, "cash", "available_cash", "dnca_tot_amt"),
            "total_asset_value": _account_equity(account_state),
            "warnings": _string_list(account_state.get("warnings")),
        }
    )


def _held_symbols(preview: dict[str, Any], account_state: dict[str, Any]) -> set[str]:
    symbols = {
        _symbol(item)
        for item in _dict_list(account_state.get("positions"))
        if _symbol(item)
    }
    symbols.update(
        str(item or "").strip().upper()
        for item in _string_list(preview.get("held_symbols"))
        if str(item or "").strip()
    )
    for item in _dict_list(preview.get("held_positions")):
        symbol = _symbol(item)
        if symbol:
            symbols.add(symbol)
    return symbols


def _open_order_exists(
    db: Session,
    *,
    symbol: str,
    account_state: dict[str, Any],
) -> bool:
    normalized = symbol.upper()
    for item in _dict_list(account_state.get("open_orders")):
        if _order_symbol(item) == normalized:
            return True
    for item in _dict_list(account_state.get("recent_orders")):
        if _order_symbol(item) == normalized and _order_status(item) in OPEN_ORDER_STATUSES:
            return True
    row = (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.symbol == normalized)
        .filter(OrderLog.internal_status.in_(sorted(OPEN_ORDER_STATUSES)))
        .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
        .first()
    )
    return row is not None


def _daily_buy_count(
    db: Session,
    *,
    now_utc: datetime,
    symbol: str | None = None,
) -> int:
    start_utc, end_utc = _kr_day_bounds_utc(now_utc)
    query = (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.side == BUY)
        .filter(OrderLog.created_at >= start_utc)
        .filter(OrderLog.created_at < end_utc)
        .filter(
            or_(
                OrderLog.internal_status.in_(sorted(BUY_ORDER_STATUSES)),
                OrderLog.broker_status.in_(["SIMULATED", "submitted", "filled"]),
            )
        )
    )
    if symbol:
        query = query.filter(OrderLog.symbol == symbol.upper())
    return int(query.count() or 0)


def _daily_loss_limit_hit(account_state: dict[str, Any]) -> bool:
    balance = account_state.get("balance")
    if not isinstance(balance, dict):
        return False
    equity = _account_equity(account_state)
    unrealized_pl = _first_float(balance, "unrealized_pl", "daily_pnl")
    if equity is None or equity <= 0 or unrealized_pl is None:
        return False
    return unrealized_pl <= -(equity * MAX_DAILY_LOSS_PCT)


def _account_equity(account_state: dict[str, Any]) -> float | None:
    balance = account_state.get("balance")
    if not isinstance(balance, dict):
        return None
    return _first_float(
        balance,
        "total_asset_value",
        "total_equity",
        "equity",
        "stock_evaluation_amount",
    )


def _gpt_hard_block(candidate: dict[str, Any]) -> bool:
    return should_apply_gpt_hard_block(candidate)


def _normalize_position(item: Any) -> dict[str, Any]:
    payload = dict(item) if isinstance(item, dict) else {}
    return sanitize_kis_payload(
        {
            **payload,
            "symbol": _symbol(payload),
            "qty": _score(payload, "qty", "quantity", "hldg_qty"),
            "current_price": _score(payload, "current_price", "price", "stck_prpr"),
        }
    )


def _normalize_order(item: Any) -> dict[str, Any]:
    payload = dict(item) if isinstance(item, dict) else {}
    return sanitize_kis_payload(
        {
            **payload,
            "symbol": _order_symbol(payload),
            "side": str(payload.get("side") or payload.get("action") or "").lower(),
            "status": _order_status(payload),
        }
    )


def _order_symbol(item: dict[str, Any]) -> str:
    return str(item.get("symbol") or item.get("pdno") or "").strip().upper()


def _order_status(item: dict[str, Any]) -> str:
    return str(
        item.get("internal_status")
        or item.get("clear_status")
        or item.get("status")
        or item.get("broker_status")
        or ""
    ).strip().upper()


def _symbol(item: dict[str, Any]) -> str:
    return str(item.get("symbol") or item.get("pdno") or "").strip().upper()


def _score(item: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(",", "")
        if not text or text == "null":
            continue
        try:
            return float(text)
        except ValueError:
            continue
    return None


def _first_float(item: dict[str, Any], *keys: str) -> float | None:
    return _score(item, *keys)


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _account_warning_flags(account_state: dict[str, Any]) -> list[str]:
    result = []
    for warning in _string_list(account_state.get("warnings")):
        name = warning.split(":", 1)[0]
        if name:
            result.append(name)
    return result


def _json(value: Any) -> str:
    return json.dumps(sanitize_kis_payload(value), ensure_ascii=False, default=str)


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip()
    return f"{exc.__class__.__name__}: {text}" if text else exc.__class__.__name__


def _utc_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _kr_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    local = _utc_now(now_utc).astimezone(KR_TZ)
    start = datetime.combine(local.date(), time.min, tzinfo=KR_TZ)
    end = start + timedelta(days=1)
    return start.astimezone(UTC), end.astimezone(UTC)


def _serialize_run(row: TradeRunLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_key": row.run_key,
        "trigger_source": row.trigger_source,
        "symbol": row.symbol,
        "mode": row.mode,
        "stage": row.stage,
        "result": row.result,
        "reason": row.reason,
        "signal_id": row.signal_id,
        "order_id": row.order_id,
        "created_at": row.created_at,
    }
