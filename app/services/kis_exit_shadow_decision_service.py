from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient, to_float
from app.core.constants import DEFAULT_GATE_LEVEL
from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.services.kis_dry_run_risk_service import (
    MARKET,
    OPEN_ORDER_STATUSES,
    PROVIDER,
    SELL,
    position_exit_threshold_reasons,
    position_pl_diagnostics,
)
from app.services.kis_order_sync_service import KisOrderSyncService, serialize_kis_order
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "shadow_exit_dry_run"
SOURCE = "kis_exit_shadow_decision"
SOURCE_TYPE = "dry_run_sell_simulation"
TRIGGER_SOURCE = "shadow_exit"

_SHADOW_GATING_NOTES = [
    "shadow_exit_only",
    "dry_run_sell_simulation",
    "no_broker_submit",
    "no_manual_submit",
    "manual_confirm_required",
    "kis_live_auto_sell_disabled",
    "scheduler_real_orders_disabled",
]


@dataclass(frozen=True)
class _ShadowCandidate:
    symbol: str | None
    qty: float | None
    current_price: float | None
    trigger: str
    trigger_source: str
    reason: str
    risk_flags: list[str]
    gating_notes: list[str]
    priority: int
    action: str = "hold"
    suggested_quantity: float | None = None
    position: dict[str, Any] | None = None
    pl_diagnostics: dict[str, Any] | None = None


class KisExitShadowDecisionService:
    """Dry-run KIS exit decision layer for held positions only.

    This service answers which existing KIS holding would have been selected for
    an exit if live auto sell existed in the future. It never submits orders and
    deliberately has no dependency on the manual submit service.
    """

    def __init__(
        self,
        client: KisClient,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
    ):
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()

    def run_once(
        self,
        db: Session,
        *,
        gate_level: int = DEFAULT_GATE_LEVEL,
    ) -> dict[str, Any]:
        runtime = self.runtime_settings.get_settings(db)
        settings = self.client.settings
        account_state = self._fetch_account_state(db)
        market_session = self._market_session()
        positions = _held_positions(account_state.get("positions"))
        evaluated = self._evaluate_positions(db, positions=positions, account_state=account_state)
        candidate = self._select_candidate(evaluated)
        safety = _safety_payload()
        created_at = datetime.now(UTC).isoformat()

        configured_scheduler_allow_real_orders = bool(
            getattr(settings, "kis_scheduler_allow_real_orders", False)
            or getattr(settings, "kr_scheduler_allow_real_orders", False)
        )
        configured_auto_sell_enabled = bool(
            runtime.get("kis_live_auto_enabled", False)
            and runtime.get("kis_live_auto_sell_enabled", False)
        )
        candidate_payload = (
            _candidate_payload(candidate, created_at=created_at)
            if candidate is not None
            else None
        )
        decision = _decision(candidate)
        action = SELL if decision == "would_sell" else "hold"
        result = decision
        reason = _reason(candidate, held_position_exists=bool(positions))
        risk_flags = _dedupe(
            ["shadow_exit_only", "dry_run_sell_simulation"]
            + _account_warning_flags(account_state)
            + _string_list(candidate.risk_flags if candidate else [])
        )
        gating_notes = _dedupe(
            list(_SHADOW_GATING_NOTES)
            + _string_list(candidate.gating_notes if candidate else [])
        )
        checks = {
            "kis_enabled": bool(getattr(settings, "kis_enabled", False)),
            "kis_real_order_enabled": bool(getattr(settings, "kis_real_order_enabled", False)),
            "dry_run": True,
            "runtime_dry_run": bool(runtime.get("dry_run", True)),
            "kill_switch": bool(runtime.get("kill_switch", False)),
            "market_open": market_session.get("is_market_open") is True,
            "positions_available": bool(positions),
            "cost_basis_available": any(
                (item.pl_diagnostics or {}).get("exit_trigger_source") == "cost_basis"
                for item in evaluated
            ),
            "account_state_available": bool(account_state.get("fetch_success")),
            "shadow_exit_enabled": True,
            "real_order_submit_allowed": False,
            "configured_auto_sell_enabled": configured_auto_sell_enabled,
            "configured_scheduler_allow_real_orders": configured_scheduler_allow_real_orders,
        }
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
            "result": result,
            "reason": reason,
            "dry_run": True,
            "simulated": True,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "real_order_submit_allowed": False,
            "auto_buy_enabled": False,
            "auto_sell_enabled": False,
            "scheduler_real_order_enabled": False,
            "manual_confirm_required": True,
            "candidate": candidate_payload,
            "candidates": [candidate_payload] if candidate_payload else [],
            "candidate_count": 1 if candidate_payload else 0,
            "candidates_evaluated": [
                _candidate_payload(item, created_at=created_at, include_audit=False)
                for item in evaluated
            ],
            "checks": checks,
            "safety": safety,
            "risk_flags": risk_flags,
            "gating_notes": gating_notes,
            "created_at": created_at,
            "checked_at": created_at,
            "order_id": None,
            "broker_order_id": None,
            "kis_odno": None,
            "held_position_count": len(positions),
            "held_positions_evaluated": len(positions),
            "account_state": _account_state_summary(account_state),
            "market_session": _public_market_session(market_session),
            "runtime": {
                "dry_run": bool(runtime.get("dry_run", True)),
                "kill_switch": bool(runtime.get("kill_switch", False)),
                "scheduler_enabled": bool(runtime.get("scheduler_enabled", False)),
                "kis_live_auto_enabled": bool(runtime.get("kis_live_auto_enabled", False)),
                "kis_live_auto_buy_enabled": bool(
                    runtime.get("kis_live_auto_buy_enabled", False)
                ),
                "kis_live_auto_sell_enabled": bool(
                    runtime.get("kis_live_auto_sell_enabled", False)
                ),
                "kis_live_auto_requires_manual_confirm": bool(
                    runtime.get("kis_live_auto_requires_manual_confirm", True)
                ),
            },
            "scheduler": {
                "configured_allow_real_orders": configured_scheduler_allow_real_orders,
                "real_orders_allowed": False,
            },
        }

        signal = self._record_signal(
            db,
            payload=payload,
            candidate=candidate,
            gate_level=gate_level,
        )
        run = self._record_run(
            db,
            payload=payload,
            gate_level=gate_level,
            signal_id=signal.id,
        )
        payload["signal_id"] = signal.id
        payload["run"] = _serialize_run(run)
        return sanitize_kis_payload(payload)

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
                limit=20,
                include_rejected=True,
            )
            state["recent_orders"] = [serialize_kis_order(row) for row in rows]
        except Exception as exc:
            state["warnings"].append(f"recent_orders_unavailable:{exc.__class__.__name__}")

        return sanitize_kis_payload(state)

    def _market_session(self) -> dict[str, Any]:
        try:
            return self.session_service.get_session_status(MARKET)
        except Exception as exc:
            return {
                "market": MARKET,
                "is_market_open": False,
                "is_entry_allowed_now": False,
                "error": _safe_error(exc),
            }

    def _evaluate_positions(
        self,
        db: Session,
        *,
        positions: list[dict[str, Any]],
        account_state: dict[str, Any],
    ) -> list[_ShadowCandidate]:
        evaluated: list[_ShadowCandidate] = []
        for position in positions:
            symbol = _symbol(position)
            qty = _safe_float_or_none(position.get("qty"))
            current_price = _safe_float_or_none(position.get("current_price"))
            diagnostics = position_pl_diagnostics(position)
            duplicate_sell = _has_duplicate_open_sell(
                db,
                symbol=symbol,
                account_state=account_state,
            )
            if duplicate_sell:
                evaluated.append(
                    _ShadowCandidate(
                        symbol=symbol,
                        qty=qty,
                        suggested_quantity=qty if qty and qty > 0 else None,
                        current_price=current_price,
                        trigger="manual_review",
                        trigger_source="duplicate_open_sell_order",
                        reason="Existing open or stale KIS sell order requires manual review.",
                        risk_flags=[
                            "duplicate_open_sell_order",
                            "manual_review_required",
                        ],
                        gating_notes=[
                            "Shadow decision held because a KIS sell order is already open or stale."
                        ],
                        priority=1,
                        action="hold",
                        position=position,
                        pl_diagnostics=diagnostics,
                    )
                )
                continue

            if qty is None or qty <= 0:
                evaluated.append(
                    _ShadowCandidate(
                        symbol=symbol,
                        qty=qty,
                        suggested_quantity=None,
                        current_price=current_price,
                        trigger="manual_review",
                        trigger_source="qty_not_positive",
                        reason="Held-position quantity was not positive; shadow exit held.",
                        risk_flags=["qty_not_positive", "manual_review_required"],
                        gating_notes=[
                            "Shadow decision requires a positive held quantity before any future exit review."
                        ],
                        priority=1,
                        action="hold",
                        position=position,
                        pl_diagnostics=diagnostics,
                    )
                )
                continue

            threshold_reasons, diagnostics = position_exit_threshold_reasons(position)
            if threshold_reasons:
                reason = _ranked_threshold_reason(threshold_reasons)
                trigger = _trigger_for_reason(reason)
                evaluated.append(
                    _ShadowCandidate(
                        symbol=symbol,
                        qty=qty,
                        suggested_quantity=qty,
                        current_price=current_price,
                        trigger=trigger,
                        trigger_source="cost_basis_pl_pct",
                        reason=_would_sell_reason(trigger),
                        risk_flags=_dedupe(
                            threshold_reasons
                            + ["shadow_exit_only", "manual_confirm_required"]
                        ),
                        gating_notes=[
                            "Shadow decision only. No broker submit was attempted.",
                            "Manual confirmation would still be required before any live sell order.",
                        ],
                        priority=_priority_for_trigger(trigger),
                        action=SELL,
                        position=position,
                        pl_diagnostics=diagnostics,
                    )
                )
                continue

            warning = str(diagnostics.get("pl_input_warning") or "")
            if diagnostics.get("exit_trigger_source") != "cost_basis":
                evaluated.append(
                    _ShadowCandidate(
                        symbol=symbol,
                        qty=qty,
                        suggested_quantity=qty,
                        current_price=current_price,
                        trigger="manual_review",
                        trigger_source="insufficient_cost_basis",
                        reason=(
                            "Cost basis was missing or ambiguous, so stop-loss and "
                            "take-profit triggers were not evaluated."
                        ),
                        risk_flags=_dedupe(
                            [
                                "insufficient_cost_basis",
                                "manual_review_required",
                                warning,
                            ]
                        ),
                        gating_notes=[
                            "Shadow decision held because cost-basis P/L was unavailable.",
                            "Raw broker unrealized percent was recorded only as diagnostics.",
                        ],
                        priority=1,
                        action="hold",
                        position=position,
                        pl_diagnostics=diagnostics,
                    )
                )
                continue

            evaluated.append(
                _ShadowCandidate(
                    symbol=symbol,
                    qty=qty,
                    suggested_quantity=qty,
                    current_price=current_price,
                    trigger="none",
                    trigger_source="cost_basis_pl_pct",
                    reason="No stop-loss or take-profit shadow exit condition was met.",
                    risk_flags=["no_exit_condition"],
                    gating_notes=[
                        "Shadow decision held because no reliable exit condition was met."
                    ],
                    priority=0,
                    action="hold",
                    position=position,
                    pl_diagnostics=diagnostics,
                )
            )
        return evaluated

    @staticmethod
    def _select_candidate(evaluated: list[_ShadowCandidate]) -> _ShadowCandidate | None:
        actionable = [item for item in evaluated if item.action == SELL]
        if actionable:
            actionable.sort(
                key=lambda item: (
                    item.priority,
                    abs(_safe_float((item.pl_diagnostics or {}).get("unrealized_pl"), 0.0)),
                    _safe_float((item.pl_diagnostics or {}).get("current_value"), 0.0),
                ),
                reverse=True,
            )
            return actionable[0]

        manual_review = [item for item in evaluated if item.trigger == "manual_review"]
        if manual_review:
            manual_review.sort(
                key=lambda item: (
                    item.priority,
                    _safe_float((item.pl_diagnostics or {}).get("current_value"), 0.0),
                ),
                reverse=True,
            )
            return manual_review[0]
        return None

    def _record_signal(
        self,
        db: Session,
        *,
        payload: dict[str, Any],
        candidate: _ShadowCandidate | None,
        gate_level: int,
    ) -> SignalLog:
        signal = SignalLog(
            symbol=(candidate.symbol if candidate else None) or "WATCHLIST",
            action=str(payload.get("action") or "hold"),
            sell_score=_safe_float_or_none((candidate.position or {}).get("final_sell_score"))
            if candidate
            else None,
            reason=str(payload.get("reason") or "shadow_exit_hold"),
            indicator_payload=_json((candidate.position or {}).get("indicator_payload") or {})
            if candidate
            else _json({}),
            risk_flags=_json(payload.get("risk_flags") or []),
            approved_by_risk=payload.get("decision") == "would_sell",
            signal_status="shadow_exit" if candidate else "skipped",
            trigger_source=TRIGGER_SOURCE,
            gate_level=gate_level,
            hard_block_reason=None
            if payload.get("decision") == "would_sell"
            else str(payload.get("reason") or "shadow_exit_hold"),
            hard_blocked=payload.get("decision") != "would_sell",
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
        gate_level: int,
        signal_id: int,
    ) -> TradeRunLog:
        symbol = (
            (payload.get("candidate") or {}).get("symbol")
            if isinstance(payload.get("candidate"), dict)
            else None
        ) or "WATCHLIST"
        run = TradeRunLog(
            run_key=f"kis_exit_shadow_{uuid.uuid4().hex[:10]}",
            trigger_source=TRIGGER_SOURCE,
            symbol=str(symbol),
            mode=MODE,
            gate_level=gate_level,
            stage="done",
            result=str(payload.get("result") or "hold"),
            reason=str(payload.get("reason") or "shadow_exit_hold"),
            signal_id=signal_id,
            order_id=None,
            request_payload=_json(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": MODE,
                    "source": SOURCE,
                    "source_type": SOURCE_TYPE,
                    "trigger_source": TRIGGER_SOURCE,
                    "dry_run": True,
                    "simulated": True,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                    "real_order_submit_allowed": False,
                    "gate_level": gate_level,
                }
            ),
            response_payload=_json(payload),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run


def _held_positions(value: Any) -> list[dict[str, Any]]:
    positions = []
    if not isinstance(value, list):
        return positions
    for item in value:
        if not isinstance(item, dict):
            continue
        if _safe_float(item.get("qty"), 0.0) <= 0:
            continue
        positions.append(item)
    positions.sort(key=lambda item: str(item.get("symbol") or ""))
    return positions


def _normalize_position(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    raw_symbol = item.get("symbol") or item.get("pdno") or item.get("code")
    symbol = str(raw_symbol or "").strip()
    if symbol.isdigit() and len(symbol) < 6:
        symbol = symbol.zfill(6)
    return {
        **item,
        "symbol": symbol.upper(),
        "name": item.get("name") or item.get("prdt_name"),
        "qty": to_float(item.get("qty") or item.get("hldg_qty") or 0),
        "avg_entry_price": to_float(
            item.get("avg_entry_price") or item.get("pchs_avg_pric") or 0
        ),
        "current_price": to_float(
            item.get("current_price") or item.get("prpr") or item.get("stck_prpr") or 0
        ),
        "market_value": to_float(item.get("market_value") or item.get("evlu_amt") or 0),
        "cost_basis": to_float(
            item.get("cost_basis")
            or item.get("pchs_amt")
            or item.get("pchs_amt_smtl_amt")
            or 0
        ),
        "unrealized_pl": to_float(item.get("unrealized_pl") or item.get("evlu_pfls_amt") or 0),
        "unrealized_plpc": to_float(
            item.get("unrealized_plpc") or item.get("evlu_pfls_rt") or 0
        ),
    }


def _normalize_order(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    raw_symbol = item.get("symbol") or item.get("pdno") or item.get("code")
    symbol = str(raw_symbol or "").strip()
    if symbol.isdigit() and len(symbol) < 6:
        symbol = symbol.zfill(6)
    return {**item, "symbol": symbol.upper()}


def _has_duplicate_open_sell(
    db: Session,
    *,
    symbol: str | None,
    account_state: dict[str, Any],
) -> bool:
    if not symbol:
        return False
    normalized = symbol.upper()
    for order in _dict_list(account_state.get("open_orders")):
        if str(order.get("symbol") or "").strip().upper() != normalized:
            continue
        if _order_is_sell(order):
            return True
    for order in _dict_list(account_state.get("recent_orders")):
        if str(order.get("symbol") or "").strip().upper() != normalized:
            continue
        status = str(
            order.get("internal_status")
            or order.get("clear_status")
            or order.get("status")
            or ""
        ).upper()
        if status in OPEN_ORDER_STATUSES and _order_is_sell(order):
            return True
    row = (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.symbol == normalized)
        .filter(OrderLog.side == SELL)
        .filter(OrderLog.internal_status.in_(sorted(OPEN_ORDER_STATUSES)))
        .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
        .first()
    )
    return row is not None


def _order_is_sell(order: dict[str, Any]) -> bool:
    side = str(
        order.get("side")
        or order.get("order_side")
        or order.get("sll_buy_dvsn_cd_name")
        or order.get("sll_buy_dvsn_name")
        or ""
    ).strip().lower()
    if side in {"sell", "s"}:
        return True
    code = str(order.get("sll_buy_dvsn_cd") or order.get("sll_buy_dvsn") or "").strip()
    return code in {"01", "1"}


def _candidate_payload(
    candidate: _ShadowCandidate,
    *,
    created_at: str,
    include_audit: bool = True,
) -> dict[str, Any]:
    diagnostics = candidate.pl_diagnostics or {}
    payload: dict[str, Any] = {
        "symbol": candidate.symbol,
        "side": SELL,
        "quantity_available": candidate.qty,
        "suggested_quantity": candidate.suggested_quantity,
        "trigger": candidate.trigger,
        "trigger_source": candidate.trigger_source,
        "current_price": candidate.current_price,
        "cost_basis": diagnostics.get("cost_basis"),
        "current_value": diagnostics.get("current_value"),
        "unrealized_pl": diagnostics.get("unrealized_pl"),
        "unrealized_pl_pct": diagnostics.get("unrealized_pl_pct"),
        "diagnostic_unrealized_plpc": (candidate.position or {}).get("unrealized_plpc"),
        "reason": candidate.reason,
        "risk_flags": _dedupe(candidate.risk_flags),
        "gating_notes": _dedupe(list(_SHADOW_GATING_NOTES) + candidate.gating_notes),
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "real_order_submit_allowed": False,
        "manual_confirm_required": True,
        "auto_sell_enabled": False,
        "scheduler_real_order_enabled": False,
        "created_at": created_at,
    }
    if include_audit:
        payload["audit_metadata"] = {
            "source": SOURCE,
            "source_type": SOURCE_TYPE,
            "exit_trigger": candidate.trigger,
            "trigger_source": candidate.trigger_source,
            "unrealized_pl": diagnostics.get("unrealized_pl"),
            "unrealized_pl_pct": diagnostics.get("unrealized_pl_pct"),
            "cost_basis": diagnostics.get("cost_basis"),
            "current_value": diagnostics.get("current_value"),
            "current_price": candidate.current_price,
            "suggested_quantity": candidate.suggested_quantity,
            "risk_flags": _dedupe(candidate.risk_flags),
            "gating_notes": _dedupe(list(_SHADOW_GATING_NOTES) + candidate.gating_notes),
            "real_order_submit_allowed": False,
            "auto_sell_enabled": False,
            "scheduler_real_order_enabled": False,
            "manual_confirm_required": True,
            "shadow_real_order_submitted": False,
            "shadow_broker_submit_called": False,
            "shadow_manual_submit_called": False,
            "checked_at": created_at,
        }
    return payload


def _decision(candidate: _ShadowCandidate | None) -> str:
    if candidate is None:
        return "hold"
    if candidate.action == SELL:
        return "would_sell"
    if candidate.trigger == "manual_review":
        return "manual_review"
    return "hold"


def _reason(candidate: _ShadowCandidate | None, *, held_position_exists: bool) -> str:
    if candidate is None:
        if held_position_exists:
            return "no_exit_condition"
        return "no_held_position"
    if candidate.action == SELL:
        return f"would_sell_{candidate.trigger}"
    if candidate.trigger == "manual_review":
        return "manual_review_required"
    return "no_exit_condition"


def _safety_payload() -> dict[str, Any]:
    return {
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "real_order_submit_allowed": False,
        "auto_buy_enabled": False,
        "auto_sell_enabled": False,
        "scheduler_real_order_enabled": False,
        "manual_confirm_required": True,
        "no_broker_submit": True,
        "no_manual_submit": True,
        "dry_run_sell_simulation": True,
    }


def _ranked_threshold_reason(reasons: list[str]) -> str:
    if "stop_loss_triggered" in reasons:
        return "stop_loss_triggered"
    if "take_profit_triggered" in reasons:
        return "take_profit_triggered"
    return reasons[0]


def _trigger_for_reason(reason: str) -> str:
    if reason == "stop_loss_triggered":
        return "stop_loss"
    if reason == "take_profit_triggered":
        return "take_profit"
    return "manual_review"


def _priority_for_trigger(trigger: str) -> int:
    if trigger == "stop_loss":
        return 3
    if trigger == "take_profit":
        return 2
    if trigger == "manual_review":
        return 1
    return 0


def _would_sell_reason(trigger: str) -> str:
    return (
        "Shadow decision only. If live auto sell were enabled in the future, "
        f"this position would be reviewed for a manual-confirm {trigger} exit."
    )


def _account_state_summary(account_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": PROVIDER,
        "market": MARKET,
        "fetch_success": bool(account_state.get("fetch_success")),
        "balance_available": isinstance(account_state.get("balance"), dict),
        "position_count": len(account_state.get("positions") or []),
        "open_order_count": len(account_state.get("open_orders") or []),
        "recent_order_count": len(account_state.get("recent_orders") or []),
        "warnings": _string_list(account_state.get("warnings")),
    }


def _public_market_session(market_session: dict[str, Any]) -> dict[str, Any]:
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
        "local_time",
        "error",
    ]
    return {key: market_session.get(key) for key in keys if key in market_session}


def _serialize_run(row: TradeRunLog) -> dict[str, Any]:
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


def _symbol(value: dict[str, Any] | None) -> str | None:
    if not value:
        return None
    symbol = str(value.get("symbol") or "").strip().upper()
    return symbol or None


def _account_warning_flags(account_state: dict[str, Any]) -> list[str]:
    return [warning.split(":", 1)[0] for warning in _string_list(account_state.get("warnings"))]


def _safe_float(value: Any, default: float = 0.0) -> float:
    parsed = _safe_float_or_none(value)
    return default if parsed is None else parsed


def _safe_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if not value:
            continue
        if value not in result:
            result.append(value)
    return result


def _json(payload: Any) -> str:
    return json.dumps(sanitize_kis_payload(payload), ensure_ascii=False, default=str)


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 160:
        text = f"{text[:160]}..."
    return f"{exc.__class__.__name__}: {text}"
