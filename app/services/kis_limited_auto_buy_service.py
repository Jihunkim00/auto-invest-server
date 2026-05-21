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
from app.config import get_settings
from app.core.constants import DEFAULT_GATE_LEVEL
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.services.entry_readiness_service import evaluate_entry_readiness
from app.services.gpt_hard_block_policy import should_apply_gpt_hard_block
from app.services.kis_buy_shadow_decision_service import KisBuyShadowDecisionService
from app.services.kis_dry_run_risk_service import BUY, HOLD, MARKET, OPEN_ORDER_STATUSES, PROVIDER
from app.services.kis_order_sync_service import KisOrderSyncService, serialize_kis_order
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService


STATUS_MODE = "kis_limited_auto_buy_status"
PREFLIGHT_MODE = "kis_limited_auto_buy_preflight"
RUN_MODE = "kis_limited_auto_buy_run"
MODE = RUN_MODE
SOURCE = "kis_limited_auto_buy"
SOURCE_TYPE = "buy_readiness_only"
STATUS_TRIGGER_SOURCE = "limited_auto_buy_status"
PREFLIGHT_TRIGGER_SOURCE = "limited_auto_buy_preflight"
RUN_TRIGGER_SOURCE = "limited_auto_buy_run_once"
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
class _Context:
    runtime: dict[str, Any]
    settings: Any
    market_session: dict[str, Any]
    now_utc: datetime
    created_at: str
    gate_level: int
    scheduler_context: bool
    readiness_enabled: bool
    limited_auto_buy_configured: bool
    live_auto_buy_configured: bool
    scheduler_real_orders_configured: bool
    sell_guards_ready: bool
    no_new_entry_after: str
    no_new_entry_after_blocked: bool
    entry_allowed_now: bool


@dataclass(frozen=True)
class _BuyCandidate:
    symbol: str
    name: str | None
    current_price: float | None
    available_cash: float | None
    estimated_notional: float | None
    suggested_quantity: int
    max_notional_pct: float
    estimated_max_notional: float | None
    final_buy_score: float | None
    final_sell_score: float | None
    quant_buy_score: float | None
    quant_sell_score: float | None
    ai_buy_score: float | None
    ai_sell_score: float | None
    gpt_buy_score: float | None
    gpt_sell_score: float | None
    confidence: float | None
    gate_level: int
    required_buy_score: float
    effective_min_entry_score: float
    max_sell_score: float
    buy_sell_spread: float | None
    indicator_status: str | None
    indicator_bar_count: int | None
    technical_snapshot: dict[str, Any]
    entry_ready: bool
    duplicate_position: bool
    duplicate_open_order: bool
    cash_sufficient: bool
    market_session_allowed: bool
    no_new_entry_after_blocked: bool
    daily_buy_limit_remaining: int
    risk_flags: list[str]
    gating_notes: list[str]
    block_reasons: list[str]
    gpt_reason: str | None
    raw: dict[str, Any]


class KisLimitedAutoBuyService:
    """Read-only KIS limited buy readiness and preflight service."""

    def __init__(
        self,
        client: KisClient,
        *,
        broker: Any | None = None,
        shadow_service: KisBuyShadowDecisionService | None = None,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
    ):
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()
        self.shadow_service = shadow_service or KisBuyShadowDecisionService(
            client,
            runtime_settings=self.runtime_settings,
            session_service=self.session_service,
        )
        self._unused_legacy_broker = broker

    def status(
        self,
        db: Session,
        *,
        now: datetime | None = None,
        gate_level: int = DEFAULT_GATE_LEVEL,
    ) -> dict[str, Any]:
        context = self._context(
            db,
            now=now,
            gate_level=gate_level,
            scheduler_context=False,
        )
        account_state = self._fetch_account_state(db)
        daily_limit = self._daily_limit_state(db, context=context, symbol=None)
        block_reasons = _status_block_reasons(
            context,
            account_state=account_state,
            daily_limit=daily_limit,
        )
        payload = _status_payload(
            context=context,
            account_state=account_state,
            daily_limit=daily_limit,
            block_reasons=block_reasons,
        )
        return sanitize_kis_payload(payload)

    def preflight_once(
        self,
        db: Session,
        *,
        gate_level: int = DEFAULT_GATE_LEVEL,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return self._readiness_once(
            db,
            gate_level=gate_level,
            now=now,
            mode=PREFLIGHT_MODE,
            trigger_source=PREFLIGHT_TRIGGER_SOURCE,
            record=True,
            scheduler_context=False,
        )

    def run_once(
        self,
        db: Session,
        *,
        gate_level: int = DEFAULT_GATE_LEVEL,
        now: datetime | None = None,
        scheduler_context: bool = False,
    ) -> dict[str, Any]:
        return self._readiness_once(
            db,
            gate_level=gate_level,
            now=now,
            mode=RUN_MODE,
            trigger_source=RUN_TRIGGER_SOURCE,
            record=True,
            scheduler_context=scheduler_context,
        )

    def _readiness_once(
        self,
        db: Session,
        *,
        gate_level: int,
        now: datetime | None,
        mode: str,
        trigger_source: str,
        record: bool,
        scheduler_context: bool,
    ) -> dict[str, Any]:
        context = self._context(
            db,
            now=now,
            gate_level=gate_level,
            scheduler_context=scheduler_context,
        )
        account_state = self._fetch_account_state(db)
        daily_limit = self._daily_limit_state(db, context=context, symbol=None)
        preliminary_blocks = _readiness_preliminary_blocks(
            context,
            account_state=account_state,
            daily_limit=daily_limit,
        )
        shadow_result: dict[str, Any] = {}
        candidate: _BuyCandidate | None = None
        candidate_raw: dict[str, Any] | None = None
        shadow_reason: str | None = None

        if not preliminary_blocks:
            shadow_result = self._shadow_decision(
                db,
                gate_level=gate_level,
                now_utc=context.now_utc,
            )
            candidate_raw = _select_shadow_candidate(shadow_result)
            shadow_reason = _shadow_block_reason(shadow_result)
            if candidate_raw:
                candidate = self._evaluate_candidate(
                    db,
                    raw=candidate_raw,
                    context=context,
                    account_state=account_state,
                    daily_limit=daily_limit,
                )
                daily_limit = self._daily_limit_state(
                    db,
                    context=context,
                    symbol=candidate.symbol,
                )
                candidate = self._evaluate_candidate(
                    db,
                    raw=candidate_raw,
                    context=context,
                    account_state=account_state,
                    daily_limit=daily_limit,
                )

        block_reasons = _decision_block_reasons(
            context=context,
            preliminary_blocks=preliminary_blocks,
            candidate=candidate,
            shadow_reason=shadow_reason,
        )
        entry_ready = candidate is not None and candidate.entry_ready and not preliminary_blocks
        if entry_ready:
            action = "buy_ready"
            result = "ready" if mode == PREFLIGHT_MODE else "readiness_only"
            reason = "buy_readiness_only"
            primary_block_reason = "auto_buy_execution_disabled"
        else:
            action = HOLD
            result = "blocked"
            reason = block_reasons[0] if block_reasons else "no_candidate"
            primary_block_reason = reason

        payload = _decision_payload(
            context=context,
            mode=mode,
            trigger_source=trigger_source,
            result=result,
            action=action,
            reason=reason,
            primary_block_reason=primary_block_reason,
            account_state=account_state,
            daily_limit=daily_limit,
            candidate=candidate,
            block_reasons=block_reasons,
            shadow_result=shadow_result,
        )
        if record:
            signal = self._record_signal(
                db,
                payload=payload,
                candidate=candidate,
                gate_level=gate_level,
            )
            run = self._record_run(
                db,
                payload=payload,
                candidate=candidate,
                mode=mode,
                trigger_source=trigger_source,
                gate_level=gate_level,
                signal_id=signal.id,
            )
            payload["signal_id"] = signal.id
            payload["run"] = _serialize_run(run)
        return sanitize_kis_payload(payload)

    def _context(
        self,
        db: Session,
        *,
        now: datetime | None,
        gate_level: int,
        scheduler_context: bool,
    ) -> _Context:
        now_utc = _utc_now(now)
        runtime = self.runtime_settings.get_settings(db)
        settings = self.client.settings
        market_session = self._market_session(now_utc)
        no_new_entry_after = str(
            runtime.get("kis_limited_auto_buy_no_new_entry_after") or "14:50"
        )
        no_new_blocked = _no_new_entry_after_blocked(now_utc, no_new_entry_after)
        market_required = bool(
            runtime.get("kis_limited_auto_buy_require_market_open", True)
        )
        entry_allowed_now = (
            market_session.get("is_market_open") is True
            and market_session.get("is_entry_allowed_now") is True
            and not no_new_blocked
        )
        if not market_required:
            entry_allowed_now = not no_new_blocked
        scheduler_real_orders_configured = bool(
            getattr(settings, "kis_scheduler_allow_real_orders", False)
            or getattr(settings, "kr_scheduler_allow_real_orders", False)
            or runtime.get("kis_scheduler_allow_real_orders", False)
        )
        return _Context(
            runtime=runtime,
            settings=settings,
            market_session=market_session,
            now_utc=now_utc,
            created_at=now_utc.isoformat(),
            gate_level=gate_level,
            scheduler_context=scheduler_context,
            readiness_enabled=bool(
                runtime.get("kis_limited_auto_buy_readiness_enabled", True)
            ),
            limited_auto_buy_configured=bool(
                runtime.get("kis_limited_auto_buy_enabled", False)
            ),
            live_auto_buy_configured=bool(
                runtime.get("kis_live_auto_buy_enabled", False)
            ),
            scheduler_real_orders_configured=scheduler_real_orders_configured,
            sell_guards_ready=_existing_sell_guards_ready(runtime),
            no_new_entry_after=no_new_entry_after,
            no_new_entry_after_blocked=no_new_blocked,
            entry_allowed_now=entry_allowed_now,
        )

    def _market_session(self, now_utc: datetime) -> dict[str, Any]:
        try:
            return self.session_service.get_session_status(MARKET, now=now_utc)
        except Exception as exc:
            return {
                "market": MARKET,
                "timezone": "Asia/Seoul",
                "is_market_open": False,
                "is_entry_allowed_now": False,
                "closure_reason": "session_unavailable",
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
            state["positions"] = [
                _normalize_position(item) for item in self.client.list_positions()
            ]
        except Exception as exc:
            state["fetch_success"] = False
            state["warnings"].append(f"positions_unavailable:{exc.__class__.__name__}")
        try:
            state["open_orders"] = [
                _normalize_order(item) for item in self.client.list_open_orders()
            ]
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
        except Exception as exc:
            return {
                "status": "error",
                "mode": "shadow_buy_dry_run",
                "result": "blocked",
                "reason": "candidate_source_unavailable",
                "error": _safe_error(exc),
                "candidate": None,
                "candidates": [],
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }

    def _daily_limit_state(
        self,
        db: Session,
        *,
        context: _Context,
        symbol: str | None,
    ) -> dict[str, Any]:
        limit = max(
            0,
            int(context.runtime.get("kis_limited_auto_buy_max_orders_per_day", 1) or 0),
        )
        count = _daily_buy_count(db, now_utc=context.now_utc)
        symbol_count = (
            _daily_buy_count(db, now_utc=context.now_utc, symbol=symbol)
            if symbol
            else 0
        )
        return {
            "daily_buy_count": count,
            "daily_buy_limit": limit,
            "daily_buy_limit_remaining": max(0, limit - count),
            "symbol_daily_buy_count": symbol_count,
            "same_symbol_bought_today": bool(symbol and symbol_count > 0),
        }

    def _evaluate_candidate(
        self,
        db: Session,
        *,
        raw: dict[str, Any],
        context: _Context,
        account_state: dict[str, Any],
        daily_limit: dict[str, Any],
    ) -> _BuyCandidate:
        symbol = _symbol(raw)
        cash = _account_cash(account_state)
        equity = _account_equity(account_state)
        cash_buffer = max(
            0.0,
            float(
                context.runtime.get("kis_limited_auto_buy_min_cash_buffer_krw", 0)
                or 0
            ),
        )
        max_notional_pct = float(
            context.runtime.get("kis_limited_auto_buy_max_notional_pct", 0.03)
            or 0.03
        )
        estimated_max_notional = _estimated_max_notional(
            cash=cash,
            equity=equity,
            pct=max_notional_pct,
            cash_buffer=cash_buffer,
        )
        current_price = _score(raw, "current_price", "price")
        suggested_quantity = _safe_int(
            raw.get("suggested_quantity") or raw.get("quantity") or raw.get("qty")
        )
        if suggested_quantity is None and current_price and estimated_max_notional:
            suggested_quantity = int(estimated_max_notional // current_price)
        suggested_quantity = int(suggested_quantity or 0)
        estimated_notional = _score(
            raw,
            "estimated_notional",
            "suggested_notional",
            "notional",
        )
        if estimated_notional is None and current_price and suggested_quantity > 0:
            estimated_notional = round(float(current_price) * suggested_quantity, 2)

        final_buy_score = _score(
            raw,
            "final_buy_score",
            "final_entry_score",
            "final_score",
            "score",
        )
        final_sell_score = _score(raw, "final_sell_score", "sell_score")
        quant_buy_score = _score(raw, "quant_buy_score", "quant_score")
        quant_sell_score = _score(raw, "quant_sell_score")
        ai_buy_score = _score(raw, "ai_buy_score", "gpt_buy_score")
        ai_sell_score = _score(raw, "ai_sell_score", "gpt_sell_score")
        confidence = _score(raw, "confidence", "gpt_confidence")
        required_buy_score = float(
            context.runtime.get("kis_limited_auto_buy_min_final_score", 75) or 75
        )
        max_sell_score = float(
            getattr(get_settings(), "watchlist_max_sell_score", 25) or 25
        )
        indicator_payload = _dynamic_map(
            raw.get("indicator_payload")
            or raw.get("technical_snapshot")
            or raw.get("indicators")
        )
        indicator_status = _nullable_string(raw.get("indicator_status"))
        indicator_bar_count = _safe_int(raw.get("indicator_bar_count"))
        technical_snapshot = _technical_snapshot(indicator_payload, raw)
        has_indicators = _has_indicators(
            indicator_status=indicator_status,
            indicator_payload=indicator_payload,
            indicator_bar_count=indicator_bar_count,
        )
        hard_block = _gpt_hard_block(raw)
        readiness = evaluate_entry_readiness(
            has_indicators=has_indicators,
            hard_blocked=hard_block,
            entry_score=float(final_buy_score or 0),
            buy_score=float(final_buy_score or 0),
            sell_score=float(final_sell_score or 0),
            gate_level=context.gate_level,
            min_entry_score=required_buy_score,
            max_sell_score=max_sell_score,
            gating_notes=_string_list(raw.get("gating_notes")),
            risk_flags=_string_list(raw.get("risk_flags")),
            action=raw.get("action"),
        )

        duplicate_position = symbol in _held_symbols(account_state)
        duplicate_open_order = _open_order_exists(
            db,
            symbol=symbol,
            account_state=account_state,
        )
        daily_remaining = int(daily_limit.get("daily_buy_limit_remaining") or 0)
        cash_sufficient = bool(
            cash is not None
            and estimated_notional is not None
            and estimated_notional > 0
            and cash - cash_buffer >= estimated_notional
        )
        block_reasons = _candidate_block_reasons(
            context=context,
            raw=raw,
            symbol=symbol,
            suggested_quantity=suggested_quantity,
            current_price=current_price,
            estimated_notional=estimated_notional,
            estimated_max_notional=estimated_max_notional,
            cash_sufficient=cash_sufficient,
            duplicate_position=duplicate_position,
            duplicate_open_order=duplicate_open_order,
            daily_limit=daily_limit,
            readiness=readiness,
            confidence=confidence,
        )
        entry_ready = not block_reasons
        risk_flags = _dedupe(
            ["limited_auto_buy", "buy_readiness_only"]
            + _string_list(raw.get("risk_flags"))
            + block_reasons
        )
        gating_notes = _dedupe(
            [
                "buy_readiness_only",
                "no_broker_order_path",
                "auto_buy_disabled",
                "scheduler_real_orders_disabled",
            ]
            + _string_list(raw.get("gating_notes"))
        )

        return _BuyCandidate(
            symbol=symbol,
            name=_candidate_name(raw),
            current_price=current_price,
            available_cash=cash,
            estimated_notional=estimated_notional,
            suggested_quantity=suggested_quantity,
            max_notional_pct=max_notional_pct,
            estimated_max_notional=estimated_max_notional,
            final_buy_score=final_buy_score,
            final_sell_score=final_sell_score,
            quant_buy_score=quant_buy_score,
            quant_sell_score=quant_sell_score,
            ai_buy_score=ai_buy_score,
            ai_sell_score=ai_sell_score,
            gpt_buy_score=ai_buy_score,
            gpt_sell_score=ai_sell_score,
            confidence=confidence,
            gate_level=context.gate_level,
            required_buy_score=required_buy_score,
            effective_min_entry_score=float(
                readiness.get("effective_min_entry_score") or required_buy_score
            ),
            max_sell_score=max_sell_score,
            buy_sell_spread=_safe_float_or_none(readiness.get("buy_sell_spread")),
            indicator_status=indicator_status,
            indicator_bar_count=indicator_bar_count,
            technical_snapshot=technical_snapshot,
            entry_ready=entry_ready,
            duplicate_position=duplicate_position,
            duplicate_open_order=duplicate_open_order,
            cash_sufficient=cash_sufficient,
            market_session_allowed=context.entry_allowed_now,
            no_new_entry_after_blocked=context.no_new_entry_after_blocked,
            daily_buy_limit_remaining=daily_remaining,
            risk_flags=risk_flags,
            gating_notes=gating_notes,
            block_reasons=block_reasons,
            gpt_reason=_nullable_string(raw.get("gpt_reason") or raw.get("reason")),
            raw=sanitize_kis_payload(raw),
        )

    def _record_signal(
        self,
        db: Session,
        *,
        payload: dict[str, Any],
        candidate: _BuyCandidate | None,
        gate_level: int,
    ) -> SignalLog:
        signal = SignalLog(
            symbol=(candidate.symbol if candidate else None) or "WATCHLIST",
            action=str(payload.get("action") or HOLD),
            buy_score=candidate.final_buy_score if candidate else None,
            sell_score=candidate.final_sell_score if candidate else None,
            confidence=candidate.confidence if candidate else None,
            quant_buy_score=candidate.quant_buy_score if candidate else None,
            quant_sell_score=candidate.quant_sell_score if candidate else None,
            ai_buy_score=candidate.ai_buy_score if candidate else None,
            ai_sell_score=candidate.ai_sell_score if candidate else None,
            final_buy_score=candidate.final_buy_score if candidate else None,
            final_sell_score=candidate.final_sell_score if candidate else None,
            reason=str(payload.get("reason") or ""),
            indicator_payload=_json(candidate.technical_snapshot if candidate else {}),
            risk_flags=_json(payload.get("risk_flags") or []),
            approved_by_risk=False,
            related_order_id=None,
            signal_status=str(payload.get("source_type") or SOURCE_TYPE),
            trigger_source=str(payload.get("trigger_source") or RUN_TRIGGER_SOURCE),
            gate_level=gate_level,
            hard_block_reason=str(payload.get("primary_block_reason") or "") or None,
            hard_blocked=bool(payload.get("result") != "ready"),
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
        candidate: _BuyCandidate | None,
        mode: str,
        trigger_source: str,
        gate_level: int,
        signal_id: int,
    ) -> TradeRunLog:
        run = TradeRunLog(
            run_key=f"kis_limited_auto_buy_{uuid.uuid4().hex[:10]}",
            trigger_source=trigger_source,
            symbol=(candidate.symbol if candidate else None) or "WATCHLIST",
            mode=mode,
            symbol_role="watchlist_candidate" if candidate else "watchlist",
            gate_level=gate_level,
            stage="done",
            result=str(payload.get("result") or "blocked"),
            reason=str(payload.get("reason") or ""),
            signal_id=signal_id,
            order_id=None,
            request_payload=_json(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "source": SOURCE,
                    "source_type": SOURCE_TYPE,
                    "mode": mode,
                    "trigger_source": trigger_source,
                    "gate_level": gate_level,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                    "validation_called": False,
                }
            ),
            response_payload=_json(payload),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run


def _status_payload(
    *,
    context: _Context,
    account_state: dict[str, Any],
    daily_limit: dict[str, Any],
    block_reasons: list[str],
) -> dict[str, Any]:
    cash = _account_cash(account_state)
    equity = _account_equity(account_state)
    max_notional_pct = float(
        context.runtime.get("kis_limited_auto_buy_max_notional_pct", 0.03) or 0.03
    )
    estimated_max_notional = _estimated_max_notional(
        cash=cash,
        equity=equity,
        pct=max_notional_pct,
        cash_buffer=float(
            context.runtime.get("kis_limited_auto_buy_min_cash_buffer_krw", 0) or 0
        ),
    )
    result = "blocked" if block_reasons else "ready"
    reason = block_reasons[0] if block_reasons else "buy_readiness_gates_ready"
    return {
        "status": "ok",
        "provider": PROVIDER,
        "market": MARKET,
        "mode": STATUS_MODE,
        "source": SOURCE,
        "source_type": "buy_readiness_status",
        "trigger_source": STATUS_TRIGGER_SOURCE,
        "result": result,
        "action": HOLD,
        "reason": reason,
        "primary_block_reason": block_reasons[0] if block_reasons else None,
        "live_auto_buy_enabled": False,
        "configured_live_auto_buy_enabled": context.live_auto_buy_configured,
        "limited_auto_buy_enabled": context.limited_auto_buy_configured,
        "buy_readiness_enabled": context.readiness_enabled,
        "dry_run": bool(context.runtime.get("dry_run", True)),
        "kill_switch": bool(context.runtime.get("kill_switch", False)),
        "kis_enabled": bool(getattr(context.settings, "kis_enabled", False)),
        "kis_real_order_enabled": bool(
            getattr(context.settings, "kis_real_order_enabled", False)
        ),
        "scheduler_real_orders_enabled": False,
        "configured_scheduler_real_orders_enabled": (
            context.scheduler_real_orders_configured
        ),
        "market_open": context.market_session.get("is_market_open") is True,
        "entry_allowed_now": context.entry_allowed_now,
        "no_new_entry_after": context.no_new_entry_after,
        "no_new_entry_after_blocked": context.no_new_entry_after_blocked,
        "cash_available": cash,
        "daily_buy_count": daily_limit["daily_buy_count"],
        "daily_buy_limit": daily_limit["daily_buy_limit"],
        "daily_buy_limit_remaining": daily_limit["daily_buy_limit_remaining"],
        "max_notional_pct": max_notional_pct,
        "estimated_max_notional": estimated_max_notional,
        "auto_order_ready": False,
        "real_order_submit_allowed": False,
        "block_reasons": block_reasons,
        "blocked_by": block_reasons,
        "failed_checks": block_reasons,
        "human_readable_status": _human_status(result, reason, block_reasons),
        "supported_triggers": {"buy": "readiness_only"},
        "candidate_count": 0,
        "candidates": [],
        "final_candidate": None,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "validation_called": False,
        "order_id": None,
        "broker_order_id": None,
        "kis_odno": None,
        "auto_buy_execution_enabled": False,
        "safety": _safety_payload(context, source_type="buy_readiness_status"),
        "checks": _checks_payload(context, account_state=account_state),
        "diagnostics": {
            "status_only": True,
            "account_state": _account_state_summary(account_state),
            "runtime_snapshot": _runtime_snapshot(context),
            "market_session_snapshot": _public_market_session(context),
        },
        "market_session": _public_market_session(context),
        "account_state": _account_state_summary(account_state),
        "created_at": context.created_at,
        "checked_at": context.created_at,
    }


def _decision_payload(
    *,
    context: _Context,
    mode: str,
    trigger_source: str,
    result: str,
    action: str,
    reason: str,
    primary_block_reason: str | None,
    account_state: dict[str, Any],
    daily_limit: dict[str, Any],
    candidate: _BuyCandidate | None,
    block_reasons: list[str],
    shadow_result: dict[str, Any],
) -> dict[str, Any]:
    candidate_payload = _candidate_payload(candidate) if candidate else None
    candidates = [candidate_payload] if candidate_payload else []
    metadata = _source_metadata(
        context=context,
        mode=mode,
        trigger_source=trigger_source,
        candidate=candidate,
        block_reasons=block_reasons,
        account_state=account_state,
        daily_limit=daily_limit,
    )
    risk_flags = _dedupe(
        ["limited_auto_buy", "buy_readiness_only", "no_real_order_submitted"]
        + _string_list(candidate.risk_flags if candidate else [])
        + block_reasons
    )
    gating_notes = _dedupe(
        [
            "buy_readiness_only",
            "auto_buy_disabled",
            "scheduler_real_orders_disabled",
            "no_broker_order_path",
        ]
        + _string_list(candidate.gating_notes if candidate else [])
    )
    return sanitize_kis_payload(
        {
            "status": "ok",
            "provider": PROVIDER,
            "market": MARKET,
            "mode": mode,
            "source": SOURCE,
            "source_type": SOURCE_TYPE,
            "trigger_source": trigger_source,
            "result": result,
            "action": action,
            "reason": reason,
            "primary_block_reason": primary_block_reason,
            "human_readable_status": _human_status(result, reason, block_reasons),
            "candidate_count": len(candidates),
            "candidates": candidates,
            "final_candidate": candidate_payload,
            "candidate": candidate_payload,
            "symbol": candidate.symbol if candidate else None,
            "company_name": candidate.name if candidate else None,
            "name": candidate.name if candidate else None,
            "quantity": candidate.suggested_quantity if candidate else None,
            "qty": candidate.suggested_quantity if candidate else None,
            "current_price": candidate.current_price if candidate else None,
            "estimated_notional": candidate.estimated_notional if candidate else None,
            "notional": candidate.estimated_notional if candidate else None,
            "suggested_quantity": candidate.suggested_quantity if candidate else None,
            "final_buy_score": candidate.final_buy_score if candidate else None,
            "final_sell_score": candidate.final_sell_score if candidate else None,
            "final_score": candidate.final_buy_score if candidate else None,
            "quant_buy_score": candidate.quant_buy_score if candidate else None,
            "quant_sell_score": candidate.quant_sell_score if candidate else None,
            "quant_score": candidate.quant_buy_score if candidate else None,
            "ai_buy_score": candidate.ai_buy_score if candidate else None,
            "ai_sell_score": candidate.ai_sell_score if candidate else None,
            "gpt_buy_score": candidate.gpt_buy_score if candidate else None,
            "gpt_sell_score": candidate.gpt_sell_score if candidate else None,
            "confidence": candidate.confidence if candidate else None,
            "gate_level": context.gate_level,
            "required_buy_score": (
                candidate.required_buy_score if candidate else None
            ),
            "effective_min_entry_score": (
                candidate.effective_min_entry_score if candidate else None
            ),
            "buy_sell_spread": candidate.buy_sell_spread if candidate else None,
            "cash_available": _account_cash(account_state),
            "daily_buy_count": daily_limit["daily_buy_count"],
            "daily_buy_limit": daily_limit["daily_buy_limit"],
            "daily_buy_limit_remaining": daily_limit["daily_buy_limit_remaining"],
            "max_notional_pct": float(
                context.runtime.get("kis_limited_auto_buy_max_notional_pct", 0.03)
                or 0.03
            ),
            "estimated_max_notional": (
                candidate.estimated_max_notional if candidate else None
            ),
            "live_auto_buy_enabled": False,
            "configured_live_auto_buy_enabled": context.live_auto_buy_configured,
            "limited_auto_buy_enabled": context.limited_auto_buy_configured,
            "buy_readiness_enabled": context.readiness_enabled,
            "dry_run": bool(context.runtime.get("dry_run", True)),
            "kill_switch": bool(context.runtime.get("kill_switch", False)),
            "kis_enabled": bool(getattr(context.settings, "kis_enabled", False)),
            "kis_real_order_enabled": bool(
                getattr(context.settings, "kis_real_order_enabled", False)
            ),
            "scheduler_real_orders_enabled": False,
            "market_open": context.market_session.get("is_market_open") is True,
            "entry_allowed_now": context.entry_allowed_now,
            "no_new_entry_after": context.no_new_entry_after,
            "no_new_entry_after_blocked": context.no_new_entry_after_blocked,
            "auto_order_ready": False,
            "real_order_submit_allowed": False,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "validation_called": False,
            "order_id": None,
            "order_log_id": None,
            "broker_order_id": None,
            "kis_odno": None,
            "block_reasons": block_reasons,
            "blocked_by": block_reasons,
            "failed_checks": block_reasons,
            "risk_flags": risk_flags,
            "gating_notes": gating_notes,
            "safety": _safety_payload(context, source_type=SOURCE_TYPE),
            "checks": _checks_payload(context, account_state=account_state),
            "diagnostics": {
                "readiness_only": True,
                "candidate_source": _shadow_summary(shadow_result),
                "runtime_snapshot": _runtime_snapshot(context),
                "market_session_snapshot": _public_market_session(context),
                "cash_snapshot": _cash_snapshot(account_state),
                "duplicate_order_check": {
                    "duplicate_position": bool(
                        candidate and candidate.duplicate_position
                    ),
                    "duplicate_open_buy_order": bool(
                        candidate and candidate.duplicate_open_order
                    ),
                },
                "daily_limit_summary": daily_limit,
            },
            "source_metadata": metadata,
            "audit_metadata": metadata,
            "market_session": _public_market_session(context),
            "account_state": _account_state_summary(account_state),
            "supported_triggers": {"buy": "readiness_only"},
            "created_at": context.created_at,
            "checked_at": context.created_at,
        }
    )


def _candidate_payload(candidate: _BuyCandidate | None) -> dict[str, Any] | None:
    if candidate is None:
        return None
    status = "BUY READY" if candidate.entry_ready else _candidate_status(candidate)
    return sanitize_kis_payload(
        {
            "symbol": candidate.symbol,
            "company": candidate.name,
            "company_name": candidate.name,
            "name": candidate.name,
            "provider": PROVIDER,
            "market": MARKET,
            "current_price": candidate.current_price,
            "available_cash": candidate.available_cash,
            "cash_available": candidate.available_cash,
            "estimated_notional": candidate.estimated_notional,
            "suggested_notional": candidate.estimated_notional,
            "suggested_quantity": candidate.suggested_quantity,
            "quantity": candidate.suggested_quantity,
            "max_notional_pct": candidate.max_notional_pct,
            "estimated_max_notional": candidate.estimated_max_notional,
            "final_buy_score": candidate.final_buy_score,
            "final_sell_score": candidate.final_sell_score,
            "final_score": candidate.final_buy_score,
            "quant_buy_score": candidate.quant_buy_score,
            "quant_sell_score": candidate.quant_sell_score,
            "quant_score": candidate.quant_buy_score,
            "ai_buy_score": candidate.ai_buy_score,
            "ai_sell_score": candidate.ai_sell_score,
            "gpt_buy_score": candidate.gpt_buy_score,
            "gpt_sell_score": candidate.gpt_sell_score,
            "confidence": candidate.confidence,
            "gate_level": candidate.gate_level,
            "required_buy_score": candidate.required_buy_score,
            "effective_min_entry_score": candidate.effective_min_entry_score,
            "buy_sell_spread": candidate.buy_sell_spread,
            "indicator_status": candidate.indicator_status,
            "indicator_bar_count": candidate.indicator_bar_count,
            "technical_snapshot": candidate.technical_snapshot,
            "entry_ready": candidate.entry_ready,
            "status": status,
            "trade_allowed": False,
            "buy_readiness_only": True,
            "buy_actionable": False,
            "duplicate_position": candidate.duplicate_position,
            "duplicate_open_order": candidate.duplicate_open_order,
            "duplicate_open_buy_order": candidate.duplicate_open_order,
            "cash_sufficient": candidate.cash_sufficient,
            "market_session_allowed": candidate.market_session_allowed,
            "no_new_entry_after_blocked": candidate.no_new_entry_after_blocked,
            "daily_buy_limit_remaining": candidate.daily_buy_limit_remaining,
            "risk_flags": candidate.risk_flags,
            "gating_notes": candidate.gating_notes,
            "block_reasons": candidate.block_reasons,
            "gpt_reason": candidate.gpt_reason,
            "raw": candidate.raw,
        }
    )


def _source_metadata(
    *,
    context: _Context,
    mode: str,
    trigger_source: str,
    candidate: _BuyCandidate | None,
    block_reasons: list[str],
    account_state: dict[str, Any],
    daily_limit: dict[str, Any],
) -> dict[str, Any]:
    return sanitize_kis_payload(
        {
            "source": SOURCE,
            "source_type": SOURCE_TYPE,
            "mode": mode,
            "trigger_source": trigger_source,
            "symbol": candidate.symbol if candidate else None,
            "suggested_quantity": candidate.suggested_quantity if candidate else None,
            "estimated_notional": (
                candidate.estimated_notional if candidate else None
            ),
            "final_buy_score": candidate.final_buy_score if candidate else None,
            "final_sell_score": candidate.final_sell_score if candidate else None,
            "quant_buy_score": candidate.quant_buy_score if candidate else None,
            "quant_sell_score": candidate.quant_sell_score if candidate else None,
            "confidence": candidate.confidence if candidate else None,
            "gate_level": context.gate_level,
            "block_reasons": block_reasons,
            "runtime_snapshot": _runtime_snapshot(context),
            "market_session_snapshot": _public_market_session(context),
            "cash_snapshot": _cash_snapshot(account_state),
            "duplicate_position": bool(candidate and candidate.duplicate_position),
            "duplicate_open_buy_order": bool(
                candidate and candidate.duplicate_open_order
            ),
            "daily_limit_summary": daily_limit,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "validation_called": False,
        }
    )


def _safety_payload(context: _Context, *, source_type: str) -> dict[str, Any]:
    return {
        "source": SOURCE,
        "source_type": source_type,
        "buy_readiness_only": True,
        "auto_buy_execution_enabled": False,
        "auto_buy_enabled": False,
        "live_auto_buy_enabled": False,
        "configured_live_auto_buy_enabled": context.live_auto_buy_configured,
        "limited_auto_buy_enabled": context.limited_auto_buy_configured,
        "buy_readiness_enabled": context.readiness_enabled,
        "real_order_submit_allowed": False,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "validation_called": False,
        "scheduler_real_orders_enabled": False,
        "configured_scheduler_real_orders_enabled": (
            context.scheduler_real_orders_configured
        ),
        "dry_run": bool(context.runtime.get("dry_run", True)),
        "kill_switch": bool(context.runtime.get("kill_switch", False)),
        "kis_real_order_enabled": bool(
            getattr(context.settings, "kis_real_order_enabled", False)
        ),
        "max_orders_per_day": int(
            context.runtime.get("kis_limited_auto_buy_max_orders_per_day", 1) or 1
        ),
        "max_notional_pct": float(
            context.runtime.get("kis_limited_auto_buy_max_notional_pct", 0.03)
            or 0.03
        ),
        "min_cash_buffer_krw": float(
            context.runtime.get("kis_limited_auto_buy_min_cash_buffer_krw", 0) or 0
        ),
        "requires_existing_sell_guards": bool(
            context.runtime.get(
                "kis_limited_auto_buy_requires_existing_sell_guards", True
            )
        ),
        "existing_sell_guards_ready": context.sell_guards_ready,
        "no_real_order_submitted": True,
    }


def _checks_payload(
    context: _Context,
    *,
    account_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "kis_limited_auto_buy_readiness_enabled": context.readiness_enabled,
        "kis_limited_auto_buy_enabled": context.limited_auto_buy_configured,
        "kis_live_auto_buy_enabled": context.live_auto_buy_configured,
        "dry_run": bool(context.runtime.get("dry_run", True)),
        "dry_run_blocks_real_submit": bool(context.runtime.get("dry_run", True)),
        "kill_switch": bool(context.runtime.get("kill_switch", False)),
        "kill_switch_false": not bool(context.runtime.get("kill_switch", False)),
        "kis_enabled": bool(getattr(context.settings, "kis_enabled", False)),
        "kis_real_order_enabled": bool(
            getattr(context.settings, "kis_real_order_enabled", False)
        ),
        "scheduler_real_orders_enabled": False,
        "configured_scheduler_real_orders_enabled": (
            context.scheduler_real_orders_configured
        ),
        "market_open": context.market_session.get("is_market_open") is True,
        "entry_allowed_now": context.entry_allowed_now,
        "no_new_entry_after": context.no_new_entry_after,
        "no_new_entry_after_blocked": context.no_new_entry_after_blocked,
        "account_state_available": bool(account_state.get("fetch_success")),
        "cash_available": _account_cash(account_state),
        "positions_count": len(_dict_list(account_state.get("positions"))),
        "open_orders_count": len(_dict_list(account_state.get("open_orders"))),
        "requires_existing_sell_guards": bool(
            context.runtime.get(
                "kis_limited_auto_buy_requires_existing_sell_guards", True
            )
        ),
        "existing_sell_guards_ready": context.sell_guards_ready,
    }


def _status_block_reasons(
    context: _Context,
    *,
    account_state: dict[str, Any],
    daily_limit: dict[str, Any],
) -> list[str]:
    reasons = _readiness_preliminary_blocks(
        context,
        account_state=account_state,
        daily_limit=daily_limit,
    )
    reasons.extend(_execution_block_reasons(context))
    return _dedupe(reasons)


def _readiness_preliminary_blocks(
    context: _Context,
    *,
    account_state: dict[str, Any],
    daily_limit: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    runtime = context.runtime
    market_required = bool(runtime.get("kis_limited_auto_buy_require_market_open", True))
    if not context.readiness_enabled:
        reasons.append("buy_readiness_disabled")
    if bool(runtime.get("kill_switch", False)):
        reasons.append("kill_switch_enabled")
    if not bool(getattr(context.settings, "kis_enabled", False)):
        reasons.append("kis_disabled")
    if market_required and context.market_session.get("is_market_open") is not True:
        reasons.append("market_closed")
    if market_required and context.market_session.get("is_entry_allowed_now") is not True:
        reasons.append("buy_entry_not_allowed_now")
    if context.no_new_entry_after_blocked:
        reasons.append("no_new_entry_after_blocked")
    if (
        bool(runtime.get("kis_limited_auto_buy_requires_existing_sell_guards", True))
        and not context.sell_guards_ready
    ):
        reasons.append("existing_sell_guards_not_ready")
    if bool(account_state) and account_state.get("fetch_success") is False:
        reasons.append("account_state_unavailable")
    if int(daily_limit.get("daily_buy_limit_remaining") or 0) <= 0:
        reasons.append("daily_buy_limit_reached")
    return _dedupe(reasons)


def _execution_block_reasons(context: _Context) -> list[str]:
    reasons = ["auto_buy_execution_disabled"]
    if not context.live_auto_buy_configured:
        reasons.append("live_auto_buy_disabled")
    else:
        reasons.append("live_auto_buy_must_remain_disabled")
    if not context.limited_auto_buy_configured:
        reasons.append("limited_auto_buy_disabled")
    if bool(context.runtime.get("dry_run", True)):
        reasons.append("dry_run_blocks_real_submit")
    if not bool(getattr(context.settings, "kis_real_order_enabled", False)):
        reasons.append("kis_real_order_disabled")
    reasons.append("scheduler_real_orders_disabled")
    return _dedupe(reasons)


def _decision_block_reasons(
    *,
    context: _Context,
    preliminary_blocks: list[str],
    candidate: _BuyCandidate | None,
    shadow_reason: str | None,
) -> list[str]:
    if preliminary_blocks:
        return _dedupe(preliminary_blocks + _execution_block_reasons(context))
    if candidate is None:
        return _dedupe([shadow_reason or "no_candidate"] + _execution_block_reasons(context))
    if candidate.block_reasons:
        return _dedupe(candidate.block_reasons + _execution_block_reasons(context))
    return _dedupe(_execution_block_reasons(context))


def _candidate_block_reasons(
    *,
    context: _Context,
    raw: dict[str, Any],
    symbol: str,
    suggested_quantity: int,
    current_price: float | None,
    estimated_notional: float | None,
    estimated_max_notional: float | None,
    cash_sufficient: bool,
    duplicate_position: bool,
    duplicate_open_order: bool,
    daily_limit: dict[str, Any],
    readiness: dict[str, Any],
    confidence: float | None,
) -> list[str]:
    reasons: list[str] = []
    if not symbol:
        reasons.append("missing_symbol")
    block_reason = _nullable_string(readiness.get("block_reason"))
    if block_reason:
        reasons.append(block_reason)
    min_confidence = float(
        context.runtime.get("kis_limited_auto_buy_min_confidence", 0.70) or 0.70
    )
    if confidence is None or confidence < min_confidence:
        reasons.append("confidence_threshold_not_met")
    if current_price is None or current_price <= 0:
        reasons.append("current_price_unavailable")
    if suggested_quantity <= 0:
        reasons.append("insufficient_cash")
    if estimated_notional is None or estimated_notional <= 0:
        reasons.append("insufficient_cash")
    if not cash_sufficient:
        reasons.append("insufficient_cash")
    if estimated_max_notional is not None and estimated_notional is not None:
        if estimated_notional > estimated_max_notional and cash_sufficient:
            reasons.append("notional_cap_exceeded")
    if duplicate_position:
        reasons.append("duplicate_position")
    if duplicate_open_order:
        reasons.append("duplicate_open_buy_order")
    if int(daily_limit.get("daily_buy_limit_remaining") or 0) <= 0:
        reasons.append("daily_buy_limit_reached")
    if daily_limit.get("same_symbol_bought_today") and not bool(
        context.runtime.get("kis_limited_auto_buy_allow_reentry_same_day", False)
    ):
        reasons.append("same_day_reentry_blocked")
    if context.market_session.get("is_market_open") is not True and bool(
        context.runtime.get("kis_limited_auto_buy_require_market_open", True)
    ):
        reasons.append("market_closed")
    if not context.entry_allowed_now:
        reasons.append("buy_entry_not_allowed_now")
    if context.no_new_entry_after_blocked:
        reasons.append("no_new_entry_after_blocked")
    if should_apply_gpt_hard_block(raw) and not bool(
        context.runtime.get("kis_limited_auto_buy_allow_gpt_hard_block", False)
    ):
        reasons.append("gpt_hard_block_new_buy")
    return _dedupe(_normalize_block_reasons(reasons))


def _normalize_block_reasons(reasons: list[str]) -> list[str]:
    mapping = {
        "hard_blocked": "gpt_hard_block_new_buy",
        "entry_not_allowed_now": "buy_entry_not_allowed_now",
        "entry_time": "buy_entry_not_allowed_now",
        "position_already_exists": "duplicate_position",
        "position_exists": "duplicate_position",
        "open_order_exists": "duplicate_open_buy_order",
        "open_buy_order_exists": "duplicate_open_buy_order",
        "current_price": "current_price_unavailable",
        "quantity_not_positive": "insufficient_cash",
        "notional_cap": "notional_cap_exceeded",
    }
    return [mapping.get(reason, reason) for reason in reasons if reason]


def _select_shadow_candidate(shadow: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("final_candidate", "candidate"):
        value = shadow.get(key)
        if isinstance(value, dict) and _symbol(value):
            return sanitize_kis_payload(value)
    candidates = shadow.get("candidates")
    if isinstance(candidates, list):
        for item in candidates:
            if isinstance(item, dict) and _symbol(item):
                return sanitize_kis_payload(item)
    return None


def _shadow_block_reason(shadow: dict[str, Any]) -> str | None:
    reason = _nullable_string(
        shadow.get("primary_block_reason")
        or shadow.get("reason")
        or shadow.get("block_reason")
    )
    if reason and reason not in {"Shadow buy candidate only. No broker submit."}:
        return _normalize_block_reasons([reason])[0]
    failed = _string_list(shadow.get("failed_checks") or shadow.get("block_reasons"))
    if failed:
        return _normalize_block_reasons(failed)[0]
    return None


def _shadow_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return sanitize_kis_payload(
        {
            "mode": payload.get("mode"),
            "decision": payload.get("decision") or payload.get("result"),
            "reason": payload.get("reason"),
            "symbol": payload.get("symbol"),
            "candidate_count": payload.get("candidate_count"),
            "real_order_submitted": payload.get("real_order_submitted") is True,
            "broker_submit_called": payload.get("broker_submit_called") is True,
            "manual_submit_called": payload.get("manual_submit_called") is True,
            "run": payload.get("run"),
        }
    )


def _candidate_status(candidate: _BuyCandidate) -> str:
    if candidate.entry_ready:
        return "BUY READY"
    if candidate.block_reasons:
        if any(
            reason
            in {
                "score_threshold_not_met",
                "buy_sell_spread_too_weak",
                "sell_pressure_too_high",
                "confidence_threshold_not_met",
            }
            for reason in candidate.block_reasons
        ):
            return "WATCH"
        return "BLOCKED"
    return "HOLD"


def _existing_sell_guards_ready(runtime: dict[str, Any]) -> bool:
    if not bool(runtime.get("kis_limited_auto_buy_requires_existing_sell_guards", True)):
        return True
    limited_sell = bool(runtime.get("kis_limited_auto_sell_enabled", False))
    stop_loss = bool(runtime.get("kis_limited_auto_sell_stop_loss_enabled", False))
    take_profit = bool(
        runtime.get(
            "kis_limited_auto_take_profit_enabled",
            runtime.get("kis_limited_auto_sell_take_profit_enabled", False),
        )
    )
    take_profit_readiness = bool(
        runtime.get(
            "kis_limited_auto_take_profit_readiness_enabled",
            runtime.get("kis_limited_auto_sell_take_profit_readiness_enabled", True),
        )
    )
    return limited_sell and (stop_loss or take_profit or take_profit_readiness)


def _estimated_max_notional(
    *,
    cash: float | None,
    equity: float | None,
    pct: float,
    cash_buffer: float,
) -> float | None:
    values: list[float] = []
    if equity is not None and equity > 0:
        values.append(float(equity) * float(pct))
    if cash is not None and cash > 0:
        values.append(max(0.0, float(cash) - float(cash_buffer)))
    if not values:
        return None
    return round(min(values), 2)


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


def _cash_snapshot(account_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "cash_available": _account_cash(account_state),
        "account_equity": _account_equity(account_state),
        "fetch_success": bool(account_state.get("fetch_success")),
        "warnings": _string_list(account_state.get("warnings")),
    }


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


def _runtime_snapshot(context: _Context) -> dict[str, Any]:
    runtime = context.runtime
    return {
        "kis_live_auto_buy_enabled": bool(
            runtime.get("kis_live_auto_buy_enabled", False)
        ),
        "kis_limited_auto_buy_enabled": bool(
            runtime.get("kis_limited_auto_buy_enabled", False)
        ),
        "kis_limited_auto_buy_readiness_enabled": bool(
            runtime.get("kis_limited_auto_buy_readiness_enabled", True)
        ),
        "kis_limited_auto_buy_max_orders_per_day": int(
            runtime.get("kis_limited_auto_buy_max_orders_per_day", 1) or 1
        ),
        "kis_limited_auto_buy_max_notional_pct": float(
            runtime.get("kis_limited_auto_buy_max_notional_pct", 0.03) or 0.03
        ),
        "kis_limited_auto_buy_min_cash_buffer_krw": float(
            runtime.get("kis_limited_auto_buy_min_cash_buffer_krw", 0) or 0
        ),
        "kis_limited_auto_buy_requires_existing_sell_guards": bool(
            runtime.get("kis_limited_auto_buy_requires_existing_sell_guards", True)
        ),
        "dry_run": bool(runtime.get("dry_run", True)),
        "kill_switch": bool(runtime.get("kill_switch", False)),
        "kis_scheduler_allow_real_orders": bool(
            runtime.get("kis_scheduler_allow_real_orders", False)
        ),
    }


def _public_market_session(context: _Context) -> dict[str, Any]:
    session = context.market_session
    return {
        "market": session.get("market", MARKET),
        "timezone": session.get("timezone", "Asia/Seoul"),
        "is_market_open": session.get("is_market_open") is True,
        "is_entry_allowed_now": session.get("is_entry_allowed_now") is True,
        "entry_allowed_now": context.entry_allowed_now,
        "no_new_entry_after": context.no_new_entry_after,
        "no_new_entry_after_blocked": context.no_new_entry_after_blocked,
        "closure_reason": session.get("closure_reason"),
        "local_time": session.get("local_time"),
    }


def _technical_snapshot(
    indicator_payload: dict[str, Any],
    raw: dict[str, Any],
) -> dict[str, Any]:
    source = indicator_payload or raw
    return {
        "EMA20": _score(source, "ema20", "EMA20"),
        "EMA50": _score(source, "ema50", "EMA50"),
        "VWAP": _score(source, "vwap", "VWAP"),
        "RSI": _score(source, "rsi", "RSI"),
        "ATR": _score(source, "atr", "ATR"),
        "volume_ratio": _score(source, "volume_ratio", "volumeRatio"),
        "recent_return": _score(source, "recent_return", "recentReturn"),
        "momentum": _score(source, "momentum"),
        "price_position": (
            source.get("price_position")
            or source.get("pricePosition")
            or raw.get("price_position")
        ),
    }


def _has_indicators(
    *,
    indicator_status: str | None,
    indicator_payload: dict[str, Any],
    indicator_bar_count: int | None,
) -> bool:
    normalized = str(indicator_status or "").strip().lower()
    if normalized in {"missing", "insufficient_data", "price_only", "unavailable", "error"}:
        return False
    if indicator_bar_count is not None and indicator_bar_count <= 0:
        return False
    keys = {"ema20", "ema50", "vwap", "rsi", "atr", "volume_ratio"}
    has_payload_values = any(indicator_payload.get(key) is not None for key in keys)
    if normalized in {"ready", "scoreable", "full", "ok"} and has_payload_values:
        return True
    return bool(has_payload_values)


def _gpt_hard_block(candidate: dict[str, Any]) -> bool:
    return should_apply_gpt_hard_block(candidate)


def _normalize_position(item: Any) -> dict[str, Any]:
    payload = dict(item) if isinstance(item, dict) else {}
    return sanitize_kis_payload(
        {
            **payload,
            "symbol": _symbol(payload),
            "qty": _safe_float_or_none(
                payload.get("qty")
                or payload.get("quantity")
                or payload.get("hldg_qty")
            ),
            "current_price": _safe_float_or_none(
                payload.get("current_price")
                or payload.get("price")
                or payload.get("stck_prpr")
            ),
        }
    )


def _normalize_order(item: Any) -> dict[str, Any]:
    payload = dict(item) if isinstance(item, dict) else {}
    return sanitize_kis_payload({**payload, "symbol": _symbol(payload)})


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
    return side in {"buy", "b", "02"} or "buy" in side


def _order_status(item: dict[str, Any]) -> str:
    return str(
        item.get("internal_status")
        or item.get("clear_status")
        or item.get("status")
        or item.get("broker_status")
        or ""
    ).upper()


def _candidate_name(item: dict[str, Any]) -> str | None:
    for key in ("company_name", "company", "name", "kor_name", "hts_kor_isnm"):
        value = _nullable_string(item.get(key))
        if value:
            return value
    return None


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


def _score(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _safe_float_or_none(payload.get(key))
        if value is not None:
            return value
    return None


def _safe_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).replace(",", "").replace("%", "").strip()
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    number = _safe_float_or_none(value)
    return int(number) if number is not None else None


def _first_float(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _safe_float_or_none(payload.get(key))
        if value is not None:
            return value
    return None


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dynamic_map(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _nullable_string(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or text.lower() == "none":
        return None
    return text


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _no_new_entry_after_blocked(now_utc: datetime, cutoff: str) -> bool:
    try:
        hour_text, minute_text = str(cutoff or "14:50").split(":", 1)
        cutoff_time = time(hour=int(hour_text), minute=int(minute_text))
    except Exception:
        cutoff_time = time(hour=14, minute=50)
    local = _utc_now(now_utc).astimezone(KR_TZ)
    return local.time() >= cutoff_time


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


def _serialize_run(row: TradeRunLog) -> dict[str, Any]:
    return {
        "run_id": row.id,
        "run_key": row.run_key,
        "trigger_source": row.trigger_source,
        "result": row.result,
        "reason": row.reason,
        "created_at": row.created_at,
    }


def _human_status(result: str, reason: str, block_reasons: list[str]) -> str:
    if result in {"ready", "readiness_only"} and reason == "buy_readiness_only":
        return "BUY READY, but auto buy execution is disabled."
    if reason == "no_candidate":
        return "No limited buy candidate is ready."
    if block_reasons:
        return f"Blocked: {block_reasons[0]}."
    return str(reason or result)


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 160:
        text = f"{text[:160]}..."
    return f"{exc.__class__.__name__}: {text}"
