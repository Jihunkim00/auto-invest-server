from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.brokers.kis_broker import KisBroker
from app.brokers.kis_client import KisClient
from app.core.constants import DEFAULT_GATE_LEVEL
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.services.gpt_hard_block_policy import should_apply_gpt_hard_block
from app.services.kis_buy_shadow_decision_service import (
    MODE as SHADOW_BUY_MODE,
    KisBuyShadowDecisionService,
)
from app.services.kis_dry_run_risk_service import BUY, MARKET, OPEN_ORDER_STATUSES, PROVIDER
from app.services.kis_order_audit import (
    LIMITED_AUTO_BUY_SOURCE,
    LIMITED_AUTO_BUY_SOURCE_TYPE,
    kis_order_source_fields,
)
from app.services.kis_order_sync_service import KisOrderSyncService, serialize_kis_order
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "limited_auto_buy"
SOURCE = LIMITED_AUTO_BUY_SOURCE
SOURCE_TYPE = LIMITED_AUTO_BUY_SOURCE_TYPE
TRIGGER_SOURCE = "kis_limited_auto_buy"
KR_TZ = ZoneInfo("Asia/Seoul")

LIVE_BUY_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}


@dataclass(frozen=True)
class _AutoBuyCandidate:
    symbol: str
    qty: int
    current_price: float
    notional: float
    final_score: float | None
    confidence: float | None
    quant_score: float | None
    gpt_buy_score: float | None
    reason: str
    risk_flags: list[str]
    gating_notes: list[str]
    audit_metadata: dict[str, Any]
    raw: dict[str, Any]


class KisLimitedAutoBuyService:
    """Guarded, disabled-by-default KIS BUY-only auto execution path."""

    def __init__(
        self,
        client: KisClient,
        *,
        broker: KisBroker | None = None,
        shadow_service: KisBuyShadowDecisionService | None = None,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
    ):
        self.client = client
        self.broker = broker or KisBroker(client)
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()
        self.shadow_service = shadow_service or KisBuyShadowDecisionService(
            client,
            runtime_settings=self.runtime_settings,
            session_service=self.session_service,
        )

    def run_once(
        self,
        db: Session,
        *,
        gate_level: int = DEFAULT_GATE_LEVEL,
        now: datetime | None = None,
        scheduler_context: bool = False,
    ) -> dict[str, Any]:
        now_utc = _utc_now(now)
        created_at = now_utc.isoformat()
        runtime = self.runtime_settings.get_settings(db)
        settings = self.client.settings
        market_session = self._market_session(now_utc)
        checks = self._base_checks(
            runtime,
            settings,
            market_session,
            scheduler_context=scheduler_context,
        )
        safety = _safety(runtime, scheduler_context=scheduler_context)

        preliminary_reason = _first_failed_preliminary_reason(
            checks,
            scheduler_context=scheduler_context,
        )
        if preliminary_reason:
            return self._blocked(
                db,
                reason=preliminary_reason,
                checks=checks,
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                blocked_by=[preliminary_reason],
                scheduler_context=scheduler_context,
            )

        account_state = self._fetch_account_state(db)
        checks.update(
            {
                "account_state_available": bool(account_state.get("fetch_success")),
                "positions_available": bool(account_state.get("positions")) is not None,
                "cash_available": _account_cash(account_state) is not None,
                "account_equity_available": _account_equity(account_state) is not None,
            }
        )
        if checks["account_state_available"] is not True:
            return self._blocked(
                db,
                reason="broker_account_state_unavailable",
                checks=checks,
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                account_state=account_state,
                blocked_by=["broker_account_state_unavailable"],
                scheduler_context=scheduler_context,
            )

        shadow = self._shadow_decision(
            db,
            gate_level=gate_level,
            now_utc=now_utc,
        )
        checks["shadow_decision"] = shadow.get("decision") or shadow.get("result")
        checks["shadow_mode"] = shadow.get("mode")
        if str(checks["shadow_decision"] or "").lower() != "would_buy":
            reason = str(shadow.get("reason") or "shadow_buy_not_ready")
            return self._blocked(
                db,
                reason=reason,
                checks=checks,
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                account_state=account_state,
                shadow_result=shadow,
                blocked_by=[reason],
                scheduler_context=scheduler_context,
            )

        candidate, candidate_reason = _candidate_from_shadow(shadow)
        if candidate is None:
            reason = candidate_reason or "shadow_buy_candidate_missing"
            return self._blocked(
                db,
                reason=reason,
                checks=checks,
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                account_state=account_state,
                shadow_result=shadow,
                blocked_by=[reason],
                scheduler_context=scheduler_context,
            )

        gate_reason = self._candidate_gate_reason(
            db,
            candidate=candidate,
            account_state=account_state,
            runtime=runtime,
            now_utc=now_utc,
            checks=checks,
            shadow=shadow,
        )
        if gate_reason:
            return self._blocked(
                db,
                reason=gate_reason,
                checks=checks,
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                account_state=account_state,
                candidate=candidate,
                shadow_result=shadow,
                blocked_by=[gate_reason],
                scheduler_context=scheduler_context,
            )

        try:
            return self._submit_buy(
                db,
                candidate=candidate,
                checks=checks,
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                shadow_result=shadow,
                scheduler_context=scheduler_context,
            )
        except Exception as exc:
            return self._submission_failed(
                db,
                candidate=candidate,
                checks=checks,
                safety=safety,
                created_at=created_at,
                runtime=runtime,
                market_session=market_session,
                shadow_result=shadow,
                error=exc,
                scheduler_context=scheduler_context,
            )

    def _base_checks(
        self,
        runtime: dict[str, Any],
        settings: Any,
        market_session: dict[str, Any],
        *,
        scheduler_context: bool,
    ) -> dict[str, Any]:
        market_required = bool(
            runtime.get("kis_limited_auto_buy_require_market_open", True)
        )
        return {
            "kis_limited_auto_buy_enabled": bool(
                runtime.get("kis_limited_auto_buy_enabled", False)
            ),
            "kis_limited_auto_buy_requires_shadow_review": bool(
                runtime.get("kis_limited_auto_buy_requires_shadow_review", True)
            ),
            "dry_run": bool(runtime.get("dry_run", True)),
            "dry_run_false": bool(runtime.get("dry_run", True)) is False,
            "kill_switch": bool(runtime.get("kill_switch", False)),
            "kill_switch_false": bool(runtime.get("kill_switch", False)) is False,
            "kis_enabled": bool(getattr(settings, "kis_enabled", False)),
            "kis_real_order_enabled": bool(
                getattr(settings, "kis_real_order_enabled", False)
            ),
            "kis_live_auto_enabled": bool(runtime.get("kis_live_auto_enabled", False)),
            "kis_live_auto_buy_enabled": bool(
                runtime.get("kis_live_auto_buy_enabled", False)
            ),
            "kis_live_auto_sell_enabled": bool(
                runtime.get("kis_live_auto_sell_enabled", False)
            ),
            "market_open": (
                market_session.get("is_market_open") is True if market_required else True
            ),
            "entry_allowed_now": (
                market_session.get("is_entry_allowed_now") is True
                if market_required
                else True
            ),
            "auto_buy_enabled": bool(
                runtime.get("kis_limited_auto_buy_enabled", False)
            )
            and bool(runtime.get("kis_live_auto_buy_enabled", False)),
            "auto_sell_enabled": False,
            "scheduler_context": scheduler_context,
            "scheduler_live_enabled": bool(
                runtime.get("kis_scheduler_live_enabled", False)
            ),
            "scheduler_allow_real_orders": bool(
                runtime.get("kis_scheduler_allow_real_orders", False)
            ),
            "scheduler_allow_limited_auto_buy": bool(
                runtime.get("kis_scheduler_allow_limited_auto_buy", False)
            ),
            "scheduler_real_order_enabled": False,
            "configured_scheduler_real_order_enabled": bool(
                runtime.get("kis_scheduler_configured_allow_real_orders", False)
            ),
        }

    def _market_session(self, now_utc: datetime) -> dict[str, Any]:
        try:
            return self.session_service.get_session_status(MARKET, now=now_utc)
        except Exception as exc:
            return {
                "market": MARKET,
                "is_market_open": False,
                "is_entry_allowed_now": False,
                "error": _safe_error(exc),
            }

    def _fetch_account_state(self, db: Session) -> dict[str, Any]:
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
            state["positions"] = [_normalize_position(item) for item in self.client.list_positions()]
        except Exception as exc:
            state["fetch_success"] = False
            state["warnings"].append(f"positions_unavailable:{exc.__class__.__name__}")
        try:
            state["open_orders"] = [_normalize_order(item) for item in self.client.list_open_orders()]
        except Exception as exc:
            state["fetch_success"] = False
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

    def _shadow_decision(
        self,
        db: Session,
        *,
        gate_level: int,
        now_utc: datetime,
    ) -> dict[str, Any]:
        try:
            return sanitize_kis_payload(
                self.shadow_service.run_once(
                    db,
                    gate_level=gate_level,
                    now=now_utc,
                )
            )
        except TypeError:
            return sanitize_kis_payload(
                self.shadow_service.run_once(db, gate_level=gate_level)
            )

    def _candidate_gate_reason(
        self,
        db: Session,
        *,
        candidate: _AutoBuyCandidate,
        account_state: dict[str, Any],
        runtime: dict[str, Any],
        now_utc: datetime,
        checks: dict[str, Any],
        shadow: dict[str, Any],
    ) -> str | None:
        symbol = candidate.symbol.upper()
        if candidate.qty <= 0:
            checks["quantity_positive"] = False
            return "quantity_not_positive"
        checks["quantity_positive"] = True
        if candidate.current_price <= 0:
            checks["current_price_available"] = False
            return "current_price_unavailable"
        checks["current_price_available"] = True

        if bool(runtime.get("kis_limited_auto_buy_block_if_position_exists", True)):
            exists = symbol in _held_symbols(account_state)
            checks["position_exists"] = exists
            if exists:
                return "position_already_exists"
        if bool(runtime.get("kis_limited_auto_buy_block_if_open_order_exists", True)):
            exists = _open_order_exists(db, symbol=symbol, account_state=account_state)
            checks["open_order_exists"] = exists
            if exists:
                return "open_order_exists"

        max_positions = max(
            0,
            int(runtime.get("kis_limited_auto_buy_max_positions", 3) or 0),
        )
        checks["position_count"] = len(_held_symbols(account_state))
        checks["max_positions_ok"] = checks["position_count"] < max_positions
        if not checks["max_positions_ok"]:
            return "max_positions_reached"

        daily_count = _daily_buy_count(db, now_utc=now_utc)
        max_orders = max(
            0,
            int(runtime.get("kis_limited_auto_buy_max_orders_per_day", 1) or 0),
        )
        checks["daily_buy_count"] = daily_count
        checks["daily_buy_limit_ok"] = daily_count < max_orders
        if daily_count >= max_orders:
            return "daily_buy_limit_reached"

        if not bool(runtime.get("kis_limited_auto_buy_allow_reentry_same_day", False)):
            same_symbol_count = _daily_buy_count(db, now_utc=now_utc, symbol=symbol)
            checks["same_symbol_bought_today"] = same_symbol_count > 0
            if same_symbol_count > 0:
                return "same_day_reentry_blocked"

        cash = _account_cash(account_state)
        equity = _account_equity(account_state)
        checks["available_cash"] = cash
        checks["account_equity"] = equity
        if cash is None or cash <= 0:
            return "account_cash_unavailable"
        if candidate.notional > cash:
            checks["cash_sufficient"] = False
            return "insufficient_cash"
        checks["cash_sufficient"] = True
        if equity is None or equity <= 0:
            return "account_equity_unavailable"
        max_notional_pct = float(
            runtime.get("kis_limited_auto_buy_max_notional_pct", 0.03) or 0.03
        )
        max_notional = round(equity * max_notional_pct, 2)
        checks["max_notional"] = max_notional
        checks["notional_cap_ok"] = candidate.notional <= max_notional
        if candidate.notional > max_notional:
            return "notional_cap_exceeded"

        min_score = float(runtime.get("kis_limited_auto_buy_min_final_score", 75) or 75)
        min_confidence = float(
            runtime.get("kis_limited_auto_buy_min_confidence", 0.70) or 0.70
        )
        checks["score_threshold_ok"] = (
            candidate.final_score is not None and candidate.final_score >= min_score
        )
        checks["confidence_threshold_ok"] = (
            candidate.confidence is not None and candidate.confidence >= min_confidence
        )
        if not checks["score_threshold_ok"]:
            return "score_threshold_not_met"
        if not checks["confidence_threshold_ok"]:
            return "confidence_threshold_not_met"

        hard_block = _gpt_hard_block(candidate.raw)
        checks["gpt_hard_block_new_buy"] = hard_block
        if hard_block and not bool(
            runtime.get("kis_limited_auto_buy_allow_gpt_hard_block", False)
        ):
            return "gpt_hard_block_new_buy"

        review_required = bool(
            runtime.get("kis_limited_auto_buy_requires_shadow_review", True)
        )
        review_status = _shadow_review_status(db, symbol=symbol, shadow=shadow)
        checks["shadow_review_required"] = review_required
        checks["shadow_review_status"] = review_status
        if review_required and review_status != "reviewed":
            return "shadow_review_required"
        return None

    def _submit_buy(
        self,
        db: Session,
        *,
        candidate: _AutoBuyCandidate,
        checks: dict[str, Any],
        safety: dict[str, Any],
        created_at: str,
        runtime: dict[str, Any],
        market_session: dict[str, Any],
        shadow_result: dict[str, Any],
        scheduler_context: bool,
    ) -> dict[str, Any]:
        audit_metadata = _audit_metadata(
            candidate,
            created_at=created_at,
            runtime=runtime,
            submitted=False,
            scheduler_context=scheduler_context,
            shadow_result=shadow_result,
        )
        order = self._create_order_log(
            db,
            candidate=candidate,
            audit_metadata=audit_metadata,
            internal_status=InternalOrderStatus.REQUESTED.value,
            response_payload=None,
        )
        broker_response = self.broker.submit_market_buy(
            symbol=candidate.symbol,
            qty=candidate.qty,
        )
        broker_order_id = _extract_broker_order_id(broker_response)
        broker_status = _extract_broker_status(broker_response)
        submitted_audit = _audit_metadata(
            candidate,
            created_at=created_at,
            runtime=runtime,
            submitted=True,
            scheduler_context=scheduler_context,
            shadow_result=shadow_result,
        )
        payload = _base_payload(
            result="submitted",
            action=BUY,
            reason="Limited auto buy submitted after all safety gates passed.",
            checks=checks,
            safety=safety,
            created_at=created_at,
            runtime=runtime,
            market_session=market_session,
            candidate=candidate,
            blocked_by=[],
            audit_metadata=submitted_audit,
            shadow_result=shadow_result,
            scheduler_context=scheduler_context,
        )
        payload.update(
            {
                "order_id": order.id,
                "order_log_id": order.id,
                "broker_order_id": broker_order_id,
                "kis_odno": broker_order_id,
                "broker_order_status": broker_status,
                "broker_status": broker_status,
                "real_order_submitted": True,
                "broker_submit_called": True,
                "manual_submit_called": False,
                "auto_buy_enabled": True,
                "scheduler_real_order_enabled": scheduler_context,
            }
        )
        order.internal_status = InternalOrderStatus.SUBMITTED.value
        order.broker_status = broker_status
        order.broker_order_status = broker_status
        order.broker_order_id = broker_order_id
        order.kis_odno = broker_order_id
        order.requested_qty = float(candidate.qty)
        order.filled_qty = 0
        order.remaining_qty = float(candidate.qty)
        order.submitted_at = _naive_utc(datetime.now(UTC))
        order.response_payload = _json(
            {
                **payload,
                "kis_response": sanitize_kis_payload(broker_response),
            }
        )
        db.commit()
        db.refresh(order)
        signal = self._record_signal(
            db,
            payload=payload,
            candidate=candidate,
            related_order_id=order.id,
        )
        run = self._record_run(
            db,
            payload=payload,
            symbol=candidate.symbol,
            signal_id=signal.id,
            order_id=order.id,
        )
        payload["signal_id"] = signal.id
        payload["run"] = _serialize_run(run)
        return sanitize_kis_payload(payload)

    def _submission_failed(
        self,
        db: Session,
        *,
        candidate: _AutoBuyCandidate,
        checks: dict[str, Any],
        safety: dict[str, Any],
        created_at: str,
        runtime: dict[str, Any],
        market_session: dict[str, Any],
        shadow_result: dict[str, Any],
        error: Exception,
        scheduler_context: bool,
    ) -> dict[str, Any]:
        payload = _base_payload(
            result="blocked",
            action="hold",
            reason="broker_submit_failed",
            checks=checks,
            safety=safety,
            created_at=created_at,
            runtime=runtime,
            market_session=market_session,
            candidate=candidate,
            blocked_by=["broker_submit_failed"],
            audit_metadata=_audit_metadata(
                candidate,
                created_at=created_at,
                runtime=runtime,
                submitted=False,
                scheduler_context=scheduler_context,
                shadow_result=shadow_result,
            ),
            shadow_result=shadow_result,
            scheduler_context=scheduler_context,
        )
        payload.update(
            {
                "error": _safe_error(error),
                "broker_submit_called": True,
                "real_order_submitted": False,
                "manual_submit_called": False,
            }
        )
        signal = self._record_signal(db, payload=payload, candidate=candidate)
        run = self._record_run(
            db,
            payload=payload,
            symbol=candidate.symbol,
            signal_id=signal.id,
            order_id=None,
        )
        payload["signal_id"] = signal.id
        payload["run"] = _serialize_run(run)
        return sanitize_kis_payload(payload)

    def _blocked(
        self,
        db: Session,
        *,
        reason: str,
        checks: dict[str, Any],
        safety: dict[str, Any],
        created_at: str,
        runtime: dict[str, Any],
        market_session: dict[str, Any],
        account_state: dict[str, Any] | None = None,
        candidate: _AutoBuyCandidate | None = None,
        shadow_result: dict[str, Any] | None = None,
        blocked_by: list[str] | None = None,
        scheduler_context: bool,
    ) -> dict[str, Any]:
        payload = _base_payload(
            result="blocked",
            action="hold",
            reason=reason,
            checks=checks,
            safety=safety,
            created_at=created_at,
            runtime=runtime,
            market_session=market_session,
            candidate=candidate,
            blocked_by=blocked_by or [reason],
            audit_metadata=(
                _audit_metadata(
                    candidate,
                    created_at=created_at,
                    runtime=runtime,
                    submitted=False,
                    scheduler_context=scheduler_context,
                    shadow_result=shadow_result or {},
                )
                if candidate is not None
                else None
            ),
            shadow_result=shadow_result,
            scheduler_context=scheduler_context,
        )
        payload["account_state"] = _account_state_summary(account_state or {})
        signal = self._record_signal(db, payload=payload, candidate=candidate)
        run = self._record_run(
            db,
            payload=payload,
            symbol=candidate.symbol if candidate else "WATCHLIST",
            signal_id=signal.id,
            order_id=None,
        )
        payload["signal_id"] = signal.id
        payload["run"] = _serialize_run(run)
        return sanitize_kis_payload(payload)

    def _create_order_log(
        self,
        db: Session,
        *,
        candidate: _AutoBuyCandidate,
        audit_metadata: dict[str, Any],
        internal_status: str,
        response_payload: dict[str, Any] | None,
    ) -> OrderLog:
        source_fields = kis_order_source_fields(audit_metadata)
        row = OrderLog(
            broker=PROVIDER,
            market=MARKET,
            symbol=candidate.symbol,
            side=BUY,
            order_type="market",
            time_in_force="day",
            qty=float(candidate.qty),
            requested_qty=float(candidate.qty),
            remaining_qty=float(candidate.qty),
            notional=candidate.notional,
            internal_status=internal_status,
            extended_hours=False,
            request_payload=_json(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": MODE,
                    "source": SOURCE,
                    "source_type": SOURCE_TYPE,
                    "symbol": candidate.symbol,
                    "side": BUY,
                    "qty": candidate.qty,
                    "notional": candidate.notional,
                    "order_type": "market",
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                    **source_fields,
                }
            ),
            response_payload=_json(response_payload) if response_payload else None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def _record_signal(
        self,
        db: Session,
        *,
        payload: dict[str, Any],
        candidate: _AutoBuyCandidate | None,
        related_order_id: int | None = None,
    ) -> SignalLog:
        signal = SignalLog(
            symbol=(candidate.symbol if candidate else None) or "WATCHLIST",
            action=str(payload.get("action") or "hold"),
            buy_score=candidate.final_score if candidate else None,
            confidence=candidate.confidence if candidate else None,
            quant_buy_score=candidate.quant_score if candidate else None,
            ai_buy_score=candidate.gpt_buy_score if candidate else None,
            final_buy_score=candidate.final_score if candidate else None,
            reason=str(payload.get("reason") or "limited_auto_buy_blocked"),
            indicator_payload=_json((candidate.raw if candidate else {}) or {}),
            risk_flags=_json(payload.get("risk_flags") or []),
            approved_by_risk=payload.get("result") == "submitted",
            related_order_id=related_order_id,
            signal_status=MODE if payload.get("result") == "submitted" else "blocked",
            trigger_source=TRIGGER_SOURCE,
            hard_block_reason=(
                None
                if payload.get("result") == "submitted"
                else str(payload.get("reason") or "limited_auto_buy_blocked")
            ),
            hard_blocked=payload.get("result") != "submitted",
            gating_notes=_json(payload.get("gating_notes") or []),
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)
        return signal

    def _record_run(
        self,
        db: Session,
        *,
        payload: dict[str, Any],
        symbol: str,
        signal_id: int,
        order_id: int | None,
    ) -> TradeRunLog:
        run = TradeRunLog(
            run_key=f"kis_limited_auto_buy_{uuid.uuid4().hex[:10]}",
            trigger_source=TRIGGER_SOURCE,
            symbol=symbol,
            mode=MODE,
            stage="done",
            result=str(payload.get("result") or "blocked"),
            reason=str(payload.get("reason") or ""),
            signal_id=signal_id,
            order_id=order_id,
            request_payload=_json(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": MODE,
                    "source": SOURCE,
                    "source_type": SOURCE_TYPE,
                    "real_order_submitted": payload.get("real_order_submitted")
                    is True,
                    "broker_submit_called": payload.get("broker_submit_called")
                    is True,
                    "manual_submit_called": False,
                    "trigger_source": TRIGGER_SOURCE,
                }
            ),
            response_payload=_json(payload),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run


def _first_failed_preliminary_reason(
    checks: dict[str, Any],
    *,
    scheduler_context: bool,
) -> str | None:
    ordered = [
        ("kis_limited_auto_buy_enabled", "limited_auto_buy_disabled"),
        ("dry_run_false", "runtime_dry_run_true"),
        ("kill_switch_false", "kill_switch_enabled"),
        ("kis_enabled", "kis_disabled"),
        ("kis_real_order_enabled", "kis_real_order_disabled"),
        ("kis_live_auto_enabled", "kis_live_auto_disabled"),
        ("kis_live_auto_buy_enabled", "kis_live_auto_buy_disabled"),
        ("market_open", "market_closed"),
        ("entry_allowed_now", "entry_not_allowed_now"),
    ]
    if scheduler_context:
        ordered = [
            ("scheduler_live_enabled", "kis_scheduler_live_disabled"),
            ("scheduler_allow_real_orders", "kis_scheduler_real_orders_disabled"),
            (
                "scheduler_allow_limited_auto_buy",
                "kis_scheduler_limited_auto_buy_disabled",
            ),
            *ordered,
        ]
    for key, reason in ordered:
        if checks.get(key) is not True:
            return reason
    return None


def _candidate_from_shadow(
    shadow: dict[str, Any],
) -> tuple[_AutoBuyCandidate | None, str | None]:
    candidate = shadow.get("candidate")
    if not isinstance(candidate, dict):
        return None, "shadow_buy_candidate_missing"
    symbol = _symbol(candidate)
    price = _safe_float(candidate.get("current_price"))
    qty = _safe_int(candidate.get("suggested_quantity"))
    notional = _safe_float(candidate.get("suggested_notional"))
    if not symbol:
        return None, "missing_symbol"
    if price is None or price <= 0:
        return None, "current_price_unavailable"
    if qty is None or qty <= 0:
        return None, "quantity_not_positive"
    if notional is None or notional <= 0:
        notional = round(float(qty) * float(price), 2)
    return (
        _AutoBuyCandidate(
            symbol=symbol,
            qty=qty,
            current_price=float(price),
            notional=float(notional),
            final_score=_safe_float(candidate.get("final_score")),
            confidence=_safe_float(candidate.get("confidence")),
            quant_score=_safe_float(candidate.get("quant_score")),
            gpt_buy_score=_safe_float(candidate.get("gpt_buy_score")),
            reason=str(candidate.get("reason") or shadow.get("reason") or ""),
            risk_flags=_string_list(candidate.get("risk_flags")),
            gating_notes=_string_list(candidate.get("gating_notes")),
            audit_metadata=dict(candidate.get("audit_metadata") or {}),
            raw=sanitize_kis_payload(candidate),
        ),
        None,
    )


def _base_payload(
    *,
    result: str,
    action: str,
    reason: str,
    checks: dict[str, Any],
    safety: dict[str, Any],
    created_at: str,
    runtime: dict[str, Any],
    market_session: dict[str, Any],
    candidate: _AutoBuyCandidate | None,
    blocked_by: list[str],
    audit_metadata: dict[str, Any] | None,
    shadow_result: dict[str, Any] | None,
    scheduler_context: bool,
) -> dict[str, Any]:
    payload = {
        "status": "ok",
        "provider": PROVIDER,
        "market": MARKET,
        "mode": MODE,
        "source": SOURCE,
        "source_type": SOURCE_TYPE,
        "trigger_source": TRIGGER_SOURCE,
        "result": result,
        "action": action,
        "reason": reason,
        "symbol": candidate.symbol if candidate else None,
        "quantity": candidate.qty if candidate else None,
        "qty": candidate.qty if candidate else None,
        "notional": candidate.notional if candidate else None,
        "final_score": candidate.final_score if candidate else None,
        "confidence": candidate.confidence if candidate else None,
        "quant_score": candidate.quant_score if candidate else None,
        "gpt_buy_score": candidate.gpt_buy_score if candidate else None,
        "current_price": candidate.current_price if candidate else None,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "auto_buy_enabled": False,
        "auto_sell_enabled": False,
        "scheduler_real_order_enabled": False,
        "order_id": None,
        "broker_order_id": None,
        "kis_odno": None,
        "checks": checks,
        "safety": safety,
        "blocked_by": blocked_by,
        "failed_checks": blocked_by,
        "risk_flags": _dedupe(
            ["limited_auto_buy", "buy_only"] + (candidate.risk_flags if candidate else [])
        ),
        "gating_notes": _dedupe(
            [
                "Limited auto buy is BUY-only.",
                "Auto buy is disabled by default.",
                "Scheduler live automation remains disabled unless explicitly gated.",
                "Manual submit service is not called.",
            ]
            + (candidate.gating_notes if candidate else [])
        ),
        "audit_metadata": audit_metadata,
        "shadow_result": _shadow_summary(shadow_result or {}),
        "scheduler_context": scheduler_context,
        "created_at": created_at,
        "checked_at": created_at,
        "market_session": _public_market_session(market_session, runtime),
    }
    if candidate is not None:
        payload["candidate"] = {
            "symbol": candidate.symbol,
            "market": MARKET,
            "provider": PROVIDER,
            "final_score": candidate.final_score,
            "confidence": candidate.confidence,
            "quant_score": candidate.quant_score,
            "gpt_buy_score": candidate.gpt_buy_score,
            "current_price": candidate.current_price,
            "suggested_notional": candidate.notional,
            "suggested_quantity": candidate.qty,
            "reason": candidate.reason,
            "risk_flags": candidate.risk_flags,
            "gating_notes": candidate.gating_notes,
            "audit_metadata": candidate.audit_metadata,
        }
    return sanitize_kis_payload(payload)


def _audit_metadata(
    candidate: _AutoBuyCandidate,
    *,
    created_at: str,
    runtime: dict[str, Any],
    submitted: bool,
    scheduler_context: bool,
    shadow_result: dict[str, Any],
) -> dict[str, Any]:
    return sanitize_kis_payload(
        {
            "source": SOURCE,
            "source_type": SOURCE_TYPE,
            "limited_auto_buy_checked_at": created_at,
            "trigger_source": TRIGGER_SOURCE,
            "symbol": candidate.symbol,
            "quantity": candidate.qty,
            "notional": candidate.notional,
            "current_price": candidate.current_price,
            "final_score": candidate.final_score,
            "confidence": candidate.confidence,
            "quant_score": candidate.quant_score,
            "gpt_buy_score": candidate.gpt_buy_score,
            "max_notional_pct": runtime.get("kis_limited_auto_buy_max_notional_pct"),
            "limited_auto_buy_enabled": bool(
                runtime.get("kis_limited_auto_buy_enabled", False)
            ),
            "auto_buy_enabled": submitted,
            "auto_sell_enabled": False,
            "scheduler_real_order_enabled": scheduler_context and submitted,
            "real_order_submit_allowed": True,
            "manual_confirm_required": False,
            "limited_auto_buy_real_order_submitted": submitted,
            "limited_auto_buy_broker_submit_called": submitted,
            "limited_auto_buy_manual_submit_called": False,
            "shadow_decision_run_key": _shadow_run_key(shadow_result),
            "shadow_review_status": _shadow_review_from_payload(shadow_result),
            "risk_flags": _dedupe(["limited_auto_buy", "buy_only"] + candidate.risk_flags),
            "gating_notes": _dedupe(
                ["guarded_entry", "manual_submit_not_called"] + candidate.gating_notes
            ),
        }
    )


def _safety(runtime: dict[str, Any], *, scheduler_context: bool) -> dict[str, Any]:
    return {
        "max_orders_per_day": int(
            runtime.get("kis_limited_auto_buy_max_orders_per_day", 1) or 1
        ),
        "max_notional_pct": float(
            runtime.get("kis_limited_auto_buy_max_notional_pct", 0.03) or 0.03
        ),
        "max_positions": int(
            runtime.get("kis_limited_auto_buy_max_positions", 3) or 3
        ),
        "block_if_position_exists": bool(
            runtime.get("kis_limited_auto_buy_block_if_position_exists", True)
        ),
        "block_if_open_order_exists": bool(
            runtime.get("kis_limited_auto_buy_block_if_open_order_exists", True)
        ),
        "allow_reentry_same_day": bool(
            runtime.get("kis_limited_auto_buy_allow_reentry_same_day", False)
        ),
        "requires_shadow_review": bool(
            runtime.get("kis_limited_auto_buy_requires_shadow_review", True)
        ),
        "scheduler_context": scheduler_context,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "auto_buy_enabled": bool(runtime.get("kis_limited_auto_buy_enabled", False)),
        "auto_sell_enabled": False,
        "scheduler_real_order_enabled": False,
    }


def _shadow_review_status(
    db: Session,
    *,
    symbol: str,
    shadow: dict[str, Any],
) -> str:
    explicit = _shadow_review_from_payload(shadow)
    if explicit == "reviewed":
        return "reviewed"
    row = (
        db.query(TradeRunLog)
        .filter(TradeRunLog.mode == SHADOW_BUY_MODE)
        .filter(TradeRunLog.symbol == symbol.upper())
        .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
        .first()
    )
    if row is None:
        return explicit or "not_found"
    payload = _parse_json_object(row.response_payload)
    return _shadow_review_from_payload(payload) or "not_reviewed"


def _shadow_review_from_payload(payload: dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("shadow_review_status", "review_status", "operator_review_status"):
        text = str(payload.get(key) or "").strip().lower()
        if text:
            return text
    candidate = payload.get("candidate")
    if isinstance(candidate, dict):
        audit = candidate.get("audit_metadata")
        if isinstance(audit, dict):
            text = str(audit.get("shadow_review_status") or "").strip().lower()
            if text:
                return text
    return None


def _shadow_run_key(payload: dict[str, Any]) -> str | None:
    run = payload.get("run") if isinstance(payload, dict) else None
    if isinstance(run, dict):
        text = str(run.get("run_key") or "").strip()
        if text:
            return text
    return None


def _shadow_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return sanitize_kis_payload(
        {
            "mode": payload.get("mode"),
            "decision": payload.get("decision") or payload.get("result"),
            "reason": payload.get("reason"),
            "symbol": payload.get("symbol"),
            "run": payload.get("run"),
            "real_order_submitted": payload.get("real_order_submitted") is True,
            "broker_submit_called": payload.get("broker_submit_called") is True,
            "manual_submit_called": payload.get("manual_submit_called") is True,
        }
    )


def _open_order_exists(
    db: Session,
    *,
    symbol: str,
    account_state: dict[str, Any],
) -> bool:
    normalized = symbol.upper()
    for item in _dict_list(account_state.get("open_orders")):
        if _order_symbol(item) == normalized and _order_is_buy(item):
            return True
    for item in _dict_list(account_state.get("recent_orders")):
        if _order_symbol(item) == normalized and _order_status(item) in OPEN_ORDER_STATUSES:
            return True
    row = (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.symbol == normalized)
        .filter(OrderLog.side == BUY)
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
                OrderLog.internal_status.in_(sorted(LIVE_BUY_STATUSES)),
                OrderLog.broker_status.in_(["submitted", "filled"]),
            )
        )
    )
    if symbol:
        query = query.filter(OrderLog.symbol == symbol.upper())
    return int(query.count() or 0)


def _held_symbols(account_state: dict[str, Any]) -> set[str]:
    return {
        _symbol(item)
        for item in _dict_list(account_state.get("positions"))
        if _symbol(item)
    }


def _account_cash(account_state: dict[str, Any]) -> float | None:
    balance = account_state.get("balance")
    if not isinstance(balance, dict):
        return None
    return _first_float(
        balance,
        "cash",
        "available_cash",
        "buying_power",
        "dnca_tot_amt",
    )


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
            "qty": _safe_float(payload.get("qty") or payload.get("quantity") or payload.get("hldg_qty")),
            "current_price": _safe_float(payload.get("current_price") or payload.get("price") or payload.get("stck_prpr")),
        }
    )


def _normalize_order(item: Any) -> dict[str, Any]:
    payload = dict(item) if isinstance(item, dict) else {}
    return sanitize_kis_payload({**payload, "symbol": _symbol(payload)})


def _account_state_summary(account_state: dict[str, Any]) -> dict[str, Any]:
    return sanitize_kis_payload(
        {
            "provider": PROVIDER,
            "market": MARKET,
            "fetch_success": bool(account_state.get("fetch_success")),
            "position_count": len(_dict_list(account_state.get("positions"))),
            "open_order_count": len(_dict_list(account_state.get("open_orders"))),
            "recent_order_count": len(_dict_list(account_state.get("recent_orders"))),
            "cash": _account_cash(account_state),
            "total_asset_value": _account_equity(account_state),
            "warnings": _string_list(account_state.get("warnings")),
        }
    )


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


def _extract_broker_order_id(response: Any) -> str | None:
    if not isinstance(response, dict):
        return None
    for key in ("broker_order_id", "order_id", "ODNO", "odno", "kis_odno"):
        value = response.get(key)
        if value:
            return str(value)
    output = response.get("output")
    if isinstance(output, dict):
        for key in ("ODNO", "odno", "order_no"):
            value = output.get(key)
            if value:
                return str(value)
    return None


def _extract_broker_status(response: Any) -> str:
    if not isinstance(response, dict):
        return "submitted"
    return str(
        response.get("status")
        or response.get("broker_status")
        or response.get("msg1")
        or response.get("rt_cd")
        or "submitted"
    )


def _order_symbol(item: dict[str, Any]) -> str:
    return _symbol(item)


def _order_is_buy(item: dict[str, Any]) -> bool:
    side = str(
        item.get("side")
        or item.get("action")
        or item.get("sll_buy_dvsn_cd")
        or item.get("trad_dvsn_name")
        or ""
    ).strip().lower()
    return side in {"buy", "b", "02", "매수"} or "buy" in side or "매수" in side


def _order_status(item: dict[str, Any]) -> str:
    return str(
        item.get("internal_status")
        or item.get("clear_status")
        or item.get("status")
        or item.get("broker_status")
        or ""
    ).upper()


def _symbol(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    value = (
        item.get("symbol")
        or item.get("pdno")
        or item.get("ticker")
        or item.get("code")
        or ""
    )
    text = str(value).strip().upper()
    if text.isdigit() and len(text) < 6:
        text = text.zfill(6)
    return text


def _safe_float(value: Any, fallback: float | None = None) -> float | None:
    if value is None:
        return fallback
    try:
        text = str(value).replace(",", "").replace("%", "").strip()
        if not text:
            return fallback
        return float(text)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any) -> int | None:
    number = _safe_float(value)
    return int(number) if number is not None else None


def _first_float(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _safe_float(payload.get(key))
        if value is not None:
            return value
    return None


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _kr_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    local = now_utc.astimezone(KR_TZ)
    start_local = datetime.combine(local.date(), time.min, tzinfo=KR_TZ)
    end_local = start_local + timedelta(days=1)
    return _naive_utc(start_local), _naive_utc(end_local)


def _utc_now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    return _utc_now(value).replace(tzinfo=None)


def _json(value: Any) -> str:
    return json.dumps(sanitize_kis_payload(value), ensure_ascii=False, default=str)


def _parse_json_object(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def _serialize_run(row: TradeRunLog) -> dict[str, Any]:
    return {
        "run_id": row.id,
        "run_key": row.run_key,
        "trigger_source": row.trigger_source,
        "result": row.result,
        "reason": row.reason,
        "created_at": row.created_at,
    }


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 160:
        text = f"{text[:160]}..."
    return f"{exc.__class__.__name__}: {text}"
