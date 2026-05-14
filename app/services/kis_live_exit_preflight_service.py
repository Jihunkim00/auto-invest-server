from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient, to_float
from app.core.constants import DEFAULT_GATE_LEVEL, MAX_DAILY_LOSS_PCT
from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.services.kis_dry_run_risk_service import (
    MARKET,
    OPEN_ORDER_STATUSES,
    PROVIDER,
    SELL,
    KisDryRunRiskService,
    position_exit_threshold_reasons,
    position_pl_diagnostics,
)
from app.services.kis_order_sync_service import (
    KisOrderSyncService,
    serialize_kis_order,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "kis_live_exit_preflight"
TRIGGER_SOURCE = "manual_kis_live_exit_preflight"
FINAL_SUBMISSION_BLOCKERS = [
    "kis_scheduler_allow_real_orders_false",
    "live_scheduler_orders_disabled",
    "preflight_only_no_broker_submit",
]


@dataclass(frozen=True)
class _ExitCandidate:
    action: str
    symbol: str | None
    qty: float | None
    estimated_notional: float | None
    estimated_price: float | None
    reason: str
    risk_flags: list[str]
    gating_notes: list[str]
    blocked_by: list[str]
    position: dict[str, Any] | None = None
    pl_diagnostics: dict[str, Any] | None = None


class KisLiveExitPreflightService:
    """Read-only KIS held-position exit preflight.

    This service deliberately stops before broker submission. It evaluates only
    held KIS positions and returns whether an exit would be eligible if live
    exit automation were later enabled.
    """

    def __init__(
        self,
        client: KisClient,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
        risk_service: KisDryRunRiskService | None = None,
    ):
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()
        self.risk_service = risk_service or KisDryRunRiskService()

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
        candidate = self._select_candidate(
            db,
            positions=positions,
            account_state=account_state,
        )

        readiness_checks: list[dict[str, Any]] = []
        critical_blockers: list[str] = []

        def check(
            name: str,
            passed: bool,
            reason: str,
            *,
            critical: bool = True,
            detail: Any = None,
        ) -> None:
            item: dict[str, Any] = {
                "name": name,
                "passed": bool(passed),
                "reason": None if passed else reason,
            }
            if detail is not None:
                item["detail"] = detail
            readiness_checks.append(item)
            if critical and not passed:
                critical_blockers.append(reason)

        scheduler_allow_real = bool(
            getattr(settings, "kis_scheduler_allow_real_orders", False)
            or getattr(settings, "kr_scheduler_allow_real_orders", False)
        )
        market_exit_allowed = market_session.get("is_market_open") is True
        held_position_exists = bool(positions)
        qty_positive = candidate.qty is not None and candidate.qty > 0
        duplicate_sell_blocked = "duplicate_open_sell_order" in candidate.blocked_by
        account_fetch_success = bool(account_state.get("fetch_success"))
        balance_available = isinstance(account_state.get("balance"), dict)

        check(
            "kill_switch_false",
            bool(runtime.get("kill_switch", False)) is False,
            "kill_switch_enabled",
        )
        check(
            "kis_enabled",
            bool(getattr(settings, "kis_enabled", False)),
            "kis_disabled",
        )
        check(
            "kis_real_order_enabled",
            bool(getattr(settings, "kis_real_order_enabled", False)),
            "kis_real_order_disabled",
        )
        check(
            "runtime_dry_run_false",
            bool(runtime.get("dry_run", True)) is False,
            "runtime_dry_run_true",
        )
        check(
            "kis_scheduler_allow_real_orders_false",
            scheduler_allow_real is False,
            "kis_scheduler_allow_real_orders_true",
        )
        check(
            "live_scheduler_orders_enabled_false",
            True,
            "live_scheduler_orders_enabled",
            critical=False,
        )
        check(
            "market_open_or_exit_allowed",
            market_exit_allowed,
            "market_closed",
            detail=_public_market_session(market_session),
        )
        check(
            "broker_account_state_fetched_successfully",
            account_fetch_success,
            "broker_account_state_unavailable",
            detail=account_state.get("warnings"),
        )
        check(
            "held_position_exists",
            held_position_exists,
            "no_held_position",
        )
        check(
            "qty_positive",
            qty_positive,
            "qty_not_positive" if held_position_exists else "no_held_position",
        )
        check(
            "no_duplicate_open_sell_order",
            not duplicate_sell_blocked,
            "duplicate_open_sell_order",
        )
        check(
            "daily_loss_max_loss_check",
            balance_available,
            "balance_unavailable_for_loss_check",
            detail=_loss_check_detail(account_state),
        )

        candidate_has_exit = candidate.action == SELL
        if not candidate_has_exit:
            critical_blockers.extend(candidate.blocked_by)
        elif candidate.blocked_by:
            critical_blockers.extend(candidate.blocked_by)

        critical_blockers = _dedupe(critical_blockers)
        blocked_by = _dedupe(critical_blockers + FINAL_SUBMISSION_BLOCKERS)
        would_submit_if_enabled = candidate_has_exit and not critical_blockers

        message = _message_for_candidate(candidate, held_position_exists)
        risk_flags = _dedupe(
            [
                "exit_only",
                "preflight_only",
                "no_broker_submit",
            ]
            + candidate.risk_flags
            + critical_blockers
            + _account_warning_flags(account_state)
        )
        gating_notes = _dedupe(
            [
                "KIS live exit preflight only; no broker submit was attempted.",
                "KIS live scheduler order submission remains disabled.",
                "Manual confirmation is required before any live sell order.",
            ]
            + candidate.gating_notes
        )
        manual_candidates = _manual_exit_candidates(candidate)
        safety = {
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "scheduler_real_order_enabled": False,
            "auto_buy_enabled": False,
            "auto_sell_enabled": False,
            "manual_confirm_required": True,
            "requires_manual_confirm": True,
        }
        manual_order = {
            "submit_endpoint": "/kis/orders/manual-submit",
            "legacy_submit_endpoint": "/kis/orders/submit-manual",
            "validate_endpoint": "/kis/orders/validate",
            "requires_existing_manual_flow": True,
            "confirm_live_required": True,
            "real_order_submitted": False,
        }
        diagnostics = _preflight_diagnostics(
            candidate,
            positions=positions,
            critical_blockers=critical_blockers,
        )
        checked_at = datetime.now(UTC).isoformat()

        payload = {
            "status": "ok",
            "provider": PROVIDER,
            "market": MARKET,
            "mode": MODE,
            "execution_mode": "manual_confirm_only",
            "live_auto_enabled": False,
            "auto_buy_enabled": False,
            "auto_sell_enabled": False,
            "real_order_submit_allowed": False,
            "manual_confirm_required": True,
            "candidate_count": len(manual_candidates),
            "candidates": manual_candidates,
            "checked_at": checked_at,
            "safety": safety,
            "manual_order": manual_order,
            "diagnostics": diagnostics,
            "trigger_source": TRIGGER_SOURCE,
            "preflight": True,
            "simulated": False,
            "dry_run": False,
            "live_order_submitted": False,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "action": candidate.action,
            "symbol": candidate.symbol,
            "qty": candidate.qty,
            "estimated_notional": candidate.estimated_notional,
            "estimated_price": candidate.estimated_price,
            "cost_basis": (candidate.pl_diagnostics or {}).get("cost_basis"),
            "current_value": (candidate.pl_diagnostics or {}).get("current_value"),
            "unrealized_pl": (candidate.pl_diagnostics or {}).get("unrealized_pl"),
            "unrealized_pl_pct": (candidate.pl_diagnostics or {}).get("unrealized_pl_pct"),
            "take_profit_threshold_pct": (candidate.pl_diagnostics or {}).get(
                "take_profit_threshold_pct"
            ),
            "stop_loss_threshold_pct": (candidate.pl_diagnostics or {}).get(
                "stop_loss_threshold_pct"
            ),
            "exit_trigger_source": (candidate.pl_diagnostics or {}).get(
                "exit_trigger_source"
            ),
            "reason": candidate.reason,
            "message": message,
            "risk_flags": risk_flags,
            "gating_notes": gating_notes,
            "readiness_checks": readiness_checks,
            "readiness": readiness_checks,
            "would_submit_if_enabled": would_submit_if_enabled,
            "blocked_by": blocked_by,
            "result": "exit_candidate" if candidate_has_exit else "skipped",
            "order_id": None,
            "broker_order_id": None,
            "kis_odno": None,
            "held_position_count": len(positions),
            "held_positions_evaluated": len(positions),
            "candidate_actions": [candidate.action],
            "market_session": _public_market_session(market_session),
            "account_state": _account_state_summary(account_state),
            "runtime": {
                "dry_run": bool(runtime.get("dry_run", True)),
                "kill_switch": bool(runtime.get("kill_switch", False)),
                "scheduler_enabled": bool(runtime.get("scheduler_enabled", False)),
            },
            "live_scheduler_orders_enabled": False,
            "kis_scheduler_allow_real_orders": scheduler_allow_real,
        }

        signal = self._record_signal(
            db,
            payload=payload,
            candidate=candidate,
            gate_level=gate_level,
            would_submit_if_enabled=would_submit_if_enabled,
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

    def _select_candidate(
        self,
        db: Session,
        *,
        positions: list[dict[str, Any]],
        account_state: dict[str, Any],
    ) -> _ExitCandidate:
        if not positions:
            return _ExitCandidate(
                action="hold",
                symbol=None,
                qty=None,
                estimated_notional=None,
                estimated_price=None,
                reason="manual_review_required",
                risk_flags=["no_held_position", "manual_review_required"],
                gating_notes=["No held KIS position was available for exit evaluation."],
                blocked_by=["no_held_position"],
                pl_diagnostics=position_pl_diagnostics(None),
            )

        sell_candidates: list[_ExitCandidate] = []
        hold_candidates: list[_ExitCandidate] = []
        daily_loss_hit = _daily_loss_limit_hit(account_state)
        max_sell_score = _safe_float(
            getattr(self.client.settings, "watchlist_max_sell_score", None),
            25.0,
        )

        for position in positions:
            symbol = _symbol(position)
            qty = _safe_float_or_none(position.get("qty"))
            price = _safe_float_or_none(position.get("current_price"))
            pl_diagnostics = position_pl_diagnostics(position)
            notional = _safe_float_or_none(pl_diagnostics.get("current_value"))
            if notional is None:
                notional = _notional(qty, price)
            pl_warning = pl_diagnostics.get("pl_input_warning")
            duplicate_sell = _has_duplicate_open_sell(
                db,
                symbol=symbol,
                account_state=account_state,
            )
            if duplicate_sell:
                hold_candidates.append(
                    _ExitCandidate(
                        action="hold",
                        symbol=symbol,
                        qty=qty,
                        estimated_notional=notional,
                        estimated_price=price,
                        reason="stale_order_or_position_risk",
                        risk_flags=[
                            "stale_order_or_position_risk",
                            "duplicate_open_sell_order",
                        ],
                        gating_notes=[
                            "Held position has an open or stale sell order; preflight will not duplicate an exit."
                        ],
                        blocked_by=["duplicate_open_sell_order"],
                        position=position,
                        pl_diagnostics=pl_diagnostics,
                    )
                )
                continue

            if qty is None or qty <= 0:
                hold_candidates.append(
                    _ExitCandidate(
                        action="hold",
                        symbol=symbol,
                        qty=qty,
                        estimated_notional=notional,
                        estimated_price=price,
                        reason="stale_order_or_position_risk",
                        risk_flags=["stale_order_or_position_risk", "qty_not_positive"],
                        gating_notes=[
                            "Held-position quantity was not positive; manual review is required."
                        ],
                        blocked_by=["qty_not_positive"],
                        position=position,
                        pl_diagnostics=pl_diagnostics,
                    )
                )
                continue

            exit_reasons, pl_diagnostics = self._exit_reasons(
                position,
                max_sell_score=max_sell_score,
                daily_loss_hit=daily_loss_hit,
            )
            if exit_reasons:
                reason = exit_reasons[0]
                sell_risk_flags = list(exit_reasons)
                if pl_warning:
                    sell_risk_flags.append(str(pl_warning))
                sell_candidates.append(
                    _ExitCandidate(
                        action=SELL,
                        symbol=symbol,
                        qty=qty,
                        estimated_notional=notional,
                        estimated_price=price,
                        reason=reason,
                        risk_flags=sell_risk_flags,
                        gating_notes=[
                            f"Held KIS position matched exit preflight reason: {reason}."
                        ],
                        blocked_by=[],
                        position=position,
                        pl_diagnostics=pl_diagnostics,
                    )
                )
            else:
                risk_flags = ["manual_review_required"]
                blocked_by = ["no_exit_condition"]
                gating_notes = [
                    "Held KIS position did not meet stop-loss, take-profit, or risk-exit thresholds."
                ]
                if pl_warning:
                    risk_flags.append(str(pl_warning))
                    blocked_by = ["pl_inputs_ambiguous"]
                    gating_notes = [
                        "Held-position P/L inputs were missing or ambiguous; manual review is required."
                    ]
                hold_candidates.append(
                    _ExitCandidate(
                        action="hold",
                        symbol=symbol,
                        qty=qty,
                        estimated_notional=notional,
                        estimated_price=price,
                        reason="manual_review_required",
                        risk_flags=risk_flags,
                        gating_notes=gating_notes,
                        blocked_by=blocked_by,
                        position=position,
                        pl_diagnostics=pl_diagnostics,
                    )
                )

        if sell_candidates:
            sell_candidates.sort(
                key=lambda item: (
                    _exit_priority(item.risk_flags),
                    _safe_float(item.estimated_notional, 0.0),
                ),
                reverse=True,
            )
            return sell_candidates[0]
        return hold_candidates[0]

    def _exit_reasons(
        self,
        position: dict[str, Any],
        *,
        max_sell_score: float,
        daily_loss_hit: bool,
    ) -> tuple[list[str], dict[str, Any]]:
        item = {
            "symbol": _symbol(position),
            "current_price": position.get("current_price"),
            "position": position,
            "indicator_payload": position.get("indicator_payload"),
            "indicator_status": position.get("indicator_status"),
            "final_sell_score": position.get("final_sell_score"),
            "quant_sell_score": position.get("quant_sell_score"),
            "ai_sell_score": position.get("ai_sell_score"),
            "final_entry_score": position.get("final_entry_score"),
            "final_buy_score": position.get("final_buy_score"),
        }
        reasons, diagnostics = position_exit_threshold_reasons(position)
        for reason in self.risk_service._exit_reasons(  # noqa: SLF001 - reuse dry-run sell score exit.
            item,
            max_sell_score=max_sell_score,
        ):
            if reason == "sell_signal_triggered":
                reasons.append("risk_exit")
        flags = {flag.lower() for flag in _string_list(position.get("risk_flags"))}
        if "risk_exit" in flags or daily_loss_hit:
            reasons.append("risk_exit")
        if "manual_review_required" in flags:
            reasons.append("manual_review_required")
        return _dedupe([reason for reason in reasons if reason in _supported_exit_reasons()]), diagnostics

    def _record_signal(
        self,
        db: Session,
        *,
        payload: dict[str, Any],
        candidate: _ExitCandidate,
        gate_level: int,
        would_submit_if_enabled: bool,
    ) -> SignalLog:
        signal = SignalLog(
            symbol=candidate.symbol or "WATCHLIST",
            action=candidate.action,
            sell_score=_safe_float_or_none((candidate.position or {}).get("final_sell_score")),
            reason=candidate.reason,
            indicator_payload=json.dumps(
                (candidate.position or {}).get("indicator_payload") or {},
                ensure_ascii=False,
                default=str,
            ),
            risk_flags=_json(payload.get("risk_flags") or []),
            approved_by_risk=would_submit_if_enabled,
            signal_status="preflight" if candidate.action == SELL else "skipped",
            trigger_source=TRIGGER_SOURCE,
            gate_level=gate_level,
            hard_block_reason=(
                None if would_submit_if_enabled else _first_blocker(payload.get("blocked_by"))
            ),
            hard_blocked=not would_submit_if_enabled,
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
        run = TradeRunLog(
            run_key=f"kis_live_exit_preflight_{uuid.uuid4().hex[:8]}",
            trigger_source=TRIGGER_SOURCE,
            symbol=str(payload.get("symbol") or "WATCHLIST"),
            mode=MODE,
            gate_level=gate_level,
            stage="done",
            result=str(payload.get("result") or "skipped"),
            reason=str(payload.get("reason") or "manual_review_required"),
            signal_id=signal_id,
            order_id=None,
            request_payload=_json(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": MODE,
                    "trigger_source": TRIGGER_SOURCE,
                    "preflight": True,
                    "request_body": {},
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
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
        "unrealized_pl": to_float(
            item.get("unrealized_pl") or item.get("evlu_pfls_amt") or 0
        ),
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


def _daily_loss_limit_hit(account_state: dict[str, Any]) -> bool:
    balance = account_state.get("balance")
    if not isinstance(balance, dict):
        return False
    equity = _first_float(
        balance,
        "total_asset_value",
        "total_equity",
        "equity",
        "stock_evaluation_amount",
    )
    unrealized_pl = _first_float(balance, "unrealized_pl", "daily_pnl")
    if equity is None or equity <= 0 or unrealized_pl is None:
        return False
    return unrealized_pl <= -(equity * MAX_DAILY_LOSS_PCT)


def _loss_check_detail(account_state: dict[str, Any]) -> dict[str, Any]:
    balance = account_state.get("balance")
    if not isinstance(balance, dict):
        return {"available": False}
    equity = _first_float(
        balance,
        "total_asset_value",
        "total_equity",
        "equity",
        "stock_evaluation_amount",
    )
    unrealized_pl = _first_float(balance, "unrealized_pl", "daily_pnl")
    return {
        "available": True,
        "daily_loss_limit_hit": _daily_loss_limit_hit(account_state),
        "equity": equity,
        "unrealized_pl": unrealized_pl,
    }


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


def _message_for_candidate(candidate: _ExitCandidate, held_position_exists: bool) -> str:
    if not held_position_exists:
        return "No held KIS position to evaluate."
    if candidate.action == SELL:
        return (
            "Exit candidate found. Manual confirmation is required before any "
            "live sell order."
        )
    return "No held KIS position currently qualifies for live exit automation."


def _manual_exit_candidates(candidate: _ExitCandidate) -> list[dict[str, Any]]:
    if candidate.action != SELL:
        return []
    return [_manual_exit_candidate(candidate)]


def _manual_exit_candidate(candidate: _ExitCandidate) -> dict[str, Any]:
    diagnostics = candidate.pl_diagnostics or {}
    risk_flags = _dedupe(
        candidate.risk_flags
        + [
            "manual_confirm_required",
            "no_auto_submit",
        ]
    )
    gating_notes = _dedupe(
        candidate.gating_notes
        + [
            "manual_confirm_required",
            "no_auto_submit",
        ]
    )
    return {
        "symbol": candidate.symbol,
        "side": SELL,
        "quantity_available": candidate.qty,
        "suggested_quantity": candidate.qty,
        "current_price": candidate.estimated_price,
        "cost_basis": diagnostics.get("cost_basis"),
        "current_value": diagnostics.get("current_value"),
        "unrealized_pl": diagnostics.get("unrealized_pl"),
        "unrealized_pl_pct": diagnostics.get("unrealized_pl_pct"),
        "trigger": _manual_exit_trigger(candidate.reason),
        "trigger_source": _manual_exit_trigger_source(candidate),
        "severity": "review",
        "action_hint": "manual_confirm_sell",
        "reason": _manual_exit_reason(candidate.reason),
        "risk_flags": risk_flags,
        "gating_notes": gating_notes,
        "submit_ready": False,
        "manual_confirm_required": True,
        "real_order_submit_allowed": False,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "estimated_notional": candidate.estimated_notional,
        "diagnostics": diagnostics,
    }


def _manual_exit_trigger(reason: str) -> str:
    if reason == "stop_loss_triggered":
        return "stop_loss"
    if reason == "take_profit_triggered":
        return "take_profit"
    return "manual_review"


def _manual_exit_trigger_source(candidate: _ExitCandidate) -> str:
    diagnostics = candidate.pl_diagnostics or {}
    if (
        candidate.reason in {"stop_loss_triggered", "take_profit_triggered"}
        and diagnostics.get("exit_trigger_source") == "cost_basis"
    ):
        return "cost_basis_pl_pct"
    return str(diagnostics.get("exit_trigger_source") or "manual_review")


def _manual_exit_reason(reason: str) -> str:
    if reason == "stop_loss_triggered":
        return (
            "Position reached stop-loss review threshold. Manual confirmation "
            "is required before any live sell order."
        )
    if reason == "take_profit_triggered":
        return (
            "Position reached take-profit review threshold. Manual confirmation "
            "is required before any live sell order."
        )
    if reason == "risk_exit":
        return (
            "Position matched a risk-exit review condition. Manual confirmation "
            "is required before any live sell order."
        )
    return (
        "Position requires manual review. Manual confirmation is required "
        "before any live sell order."
    )


def _preflight_diagnostics(
    candidate: _ExitCandidate,
    *,
    positions: list[dict[str, Any]],
    critical_blockers: list[str],
) -> dict[str, Any]:
    diagnostics = candidate.pl_diagnostics or {}
    return {
        "candidate_selected": candidate.action == SELL,
        "candidate_action": candidate.action,
        "candidate_reason": candidate.reason,
        "positions_evaluated": len(positions),
        "pl_trigger_source": diagnostics.get("exit_trigger_source"),
        "pl_input_warning": diagnostics.get("pl_input_warning"),
        "critical_blockers": critical_blockers,
        "cost_basis_required_for_stop_loss_take_profit": True,
        "preflight_only_no_submit": True,
    }


def _supported_exit_reasons() -> set[str]:
    return {
        "stop_loss_triggered",
        "take_profit_triggered",
        "risk_exit",
        "stale_order_or_position_risk",
        "manual_review_required",
    }


def _exit_priority(reasons: list[str]) -> int:
    if "stop_loss_triggered" in reasons:
        return 5
    if "risk_exit" in reasons:
        return 4
    if "take_profit_triggered" in reasons:
        return 3
    if "stale_order_or_position_risk" in reasons:
        return 2
    if "manual_review_required" in reasons:
        return 1
    return 0


def _account_warning_flags(account_state: dict[str, Any]) -> list[str]:
    return [warning.split(":", 1)[0] for warning in _string_list(account_state.get("warnings"))]


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


def _notional(qty: float | None, price: float | None) -> float | None:
    if qty is None or price is None:
        return None
    return round(float(qty) * float(price), 2)


def _first_float(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _safe_float_or_none(payload.get(key))
        if value is not None:
            return value
    return None


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
        if value not in result:
            result.append(value)
    return result


def _first_blocker(value: Any) -> str | None:
    items = _string_list(value)
    return items[0] if items else None


def _json(payload: Any) -> str:
    return json.dumps(sanitize_kis_payload(payload), ensure_ascii=False, default=str)


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 160:
        text = f"{text[:160]}..."
    return f"{exc.__class__.__name__}: {text}"
