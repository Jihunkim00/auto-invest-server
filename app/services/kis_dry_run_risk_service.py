from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.constants import (
    DECENT_SETUP_POSITION_PCT,
    MAX_DAILY_LOSS_PCT,
    MAX_POSITION_EQUITY_PCT,
    STRONG_SETUP_POSITION_PCT,
    WEAK_SETUP_POSITION_PCT,
)
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.technical_indicator_service import indicator_payload_is_quant_ready


PROVIDER = "kis"
MARKET = "KR"
BUY = "buy"
SELL = "sell"
HOLD = "hold"
KR_TZ = ZoneInfo("Asia/Seoul")
SIMULATED_ENTRY_STATUSES = {
    InternalOrderStatus.DRY_RUN_SIMULATED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}
OPEN_ORDER_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
    "PENDING_SUBMIT",
}


@dataclass(frozen=True)
class KisDryRunRiskDecision:
    approved: bool
    action: str
    symbol: str | None
    candidate: dict[str, Any] | None
    reason: str
    risk_flags: list[str]
    gating_notes: list[str]
    trigger_block_reason: str | None = None
    qty: float | None = None
    notional: float | None = None
    estimated_price: float | None = None
    final_entry_score: float | None = None
    final_score_gap: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "action": self.action,
            "symbol": self.symbol,
            "reason": self.reason,
            "risk_flags": self.risk_flags,
            "gating_notes": self.gating_notes,
            "trigger_block_reason": self.trigger_block_reason,
            "qty": self.qty,
            "notional": self.notional,
            "estimated_price": self.estimated_price,
            "final_entry_score": self.final_entry_score,
            "final_score_gap": self.final_score_gap,
        }


class KisDryRunRiskService:
    """Final approval layer for KIS dry-run simulation.

    This service deliberately returns approvals for simulated records only. It
    never submits broker orders and never depends on live-submit confirmation.
    """

    def __init__(self, runtime_settings: RuntimeSettingService | None = None):
        self.runtime_settings = runtime_settings or RuntimeSettingService()

    def evaluate(
        self,
        db: Session,
        *,
        preview: dict[str, Any],
        gate_level: int,
    ) -> KisDryRunRiskDecision:
        runtime = self.runtime_settings.get_settings(db)
        settings = get_settings()
        base_flags = _dedupe(["dry_run_only", PROVIDER] + _string_list(preview.get("risk_flags")))
        base_notes = _dedupe(
            ["KIS dry-run simulator only; no real order submitted."]
            + _string_list(preview.get("gating_notes"))
        )
        account_state = (
            preview.get("account_state") if isinstance(preview.get("account_state"), dict) else {}
        )

        if bool(runtime.get("kill_switch", False)):
            return self._blocked(
                "kill_switch_enabled",
                risk_flags=base_flags + ["kill_switch_active"],
                gating_notes=base_notes,
            )

        sell_decision = self._evaluate_sell(
            preview,
            runtime=runtime,
            settings=settings,
            account_state=account_state,
        )
        if sell_decision is not None:
            return sell_decision

        candidate = self._entry_candidate(preview)
        final_score_gap = _safe_float_or_none(preview.get("final_score_gap"))
        min_entry_score = _safe_float(
            preview.get("min_entry_score"), settings.watchlist_min_entry_score
        )
        min_score_gap = _safe_float(
            preview.get("min_score_gap"), settings.watchlist_min_score_gap
        )
        max_sell_score = _safe_float(
            preview.get("max_sell_score"), settings.watchlist_max_sell_score
        )

        if candidate is None:
            return self._blocked(
                "no_entry_candidate",
                risk_flags=base_flags,
                gating_notes=base_notes,
                final_score_gap=final_score_gap,
            )

        symbol = _symbol(candidate)
        final_entry_score = _entry_score(candidate)
        candidate_flags = _string_list(candidate.get("risk_flags"))
        candidate_notes = _string_list(candidate.get("gating_notes"))
        risk_flags = _dedupe(base_flags + candidate_flags)
        gating_notes = _dedupe(base_notes + candidate_notes)

        held_symbols = _held_symbol_set(preview, account_state)
        if symbol and symbol in held_symbols:
            return self._blocked(
                "symbol_already_held",
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags,
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )

        stale_or_open_order_reason = self._conflicting_order_reason(
            db,
            symbol=symbol,
            account_state=account_state,
        )
        if stale_or_open_order_reason:
            return self._blocked(
                stale_or_open_order_reason,
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags + [stale_or_open_order_reason],
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )

        market_session = preview.get("market_session") if isinstance(preview.get("market_session"), dict) else {}
        if market_session.get("is_market_open") is False:
            return self._blocked(
                "market_closed",
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags + ["market_closed"],
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )
        if market_session.get("is_entry_allowed_now") is not True:
            return self._blocked(
                "entry_not_allowed_now",
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags + ["after_no_new_entry_after"],
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )

        if self._daily_loss_limit_hit(account_state):
            return self._blocked(
                "daily_loss_limit_hit",
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags + ["daily_loss_limit_hit"],
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )

        global_daily_entry_limit = max(0, _safe_int(runtime.get("global_daily_entry_limit"), 0))
        if self._daily_entry_count(db) >= global_daily_entry_limit:
            return self._blocked(
                "global_daily_entry_limit_reached",
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags + ["global_daily_entry_limit_reached"],
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )

        per_symbol_daily_entry_limit = max(0, _safe_int(runtime.get("per_symbol_daily_entry_limit"), 0))
        if symbol and self._daily_entry_count(db, symbol=symbol) >= per_symbol_daily_entry_limit:
            return self._blocked(
                "per_symbol_daily_entry_limit_reached",
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags + ["per_symbol_daily_entry_limit_reached"],
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )

        if not self._has_scoreable_indicators(candidate):
            return self._blocked(
                "missing_indicators",
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags + ["missing_indicators"],
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )

        if final_entry_score is None or final_entry_score < min_entry_score:
            return self._blocked(
                "final_score_below_min_entry",
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags,
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )

        if final_score_gap is None or final_score_gap < min_score_gap:
            return self._blocked(
                "weak_final_score_gap",
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags,
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )

        sell_pressure = _sell_score(candidate)
        if sell_pressure is not None and sell_pressure > max_sell_score:
            return self._blocked(
                "sell_pressure_too_high",
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags + ["sell_pressure_too_high"],
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )

        if self._event_blocks_entry(candidate):
            return self._blocked(
                "event_risk_entry_block",
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags + ["event_risk_entry_block"],
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )

        if self._gpt_blocks_entry(candidate):
            return self._blocked(
                "gpt_blocked_entry",
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags + ["gpt_blocked_entry"],
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )

        held_count = max(_safe_int(preview.get("held_position_count"), 0), len(held_symbols))
        max_open_positions = max(
            1, _safe_int(runtime.get("max_open_positions"), _safe_int(preview.get("max_open_positions"), 3))
        )
        if held_count >= max_open_positions:
            return self._blocked(
                "max_open_positions_reached",
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags + ["max_open_positions_reached"],
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )

        per_slot_new_entry_limit = max(0, _safe_int(runtime.get("per_slot_new_entry_limit"), 1))
        if per_slot_new_entry_limit <= 0:
            return self._blocked(
                "per_slot_new_entry_limit_reached",
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags + ["per_slot_new_entry_limit_reached"],
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )

        price = _safe_float_or_none(candidate.get("current_price"))
        sizing = self._position_size(
            account_state,
            price=price,
            final_entry_score=final_entry_score,
        )
        if sizing["blocked_reason"]:
            return self._blocked(
                sizing["blocked_reason"],
                symbol=symbol,
                candidate=candidate,
                risk_flags=risk_flags + [sizing["blocked_reason"]],
                gating_notes=gating_notes,
                final_entry_score=final_entry_score,
                final_score_gap=final_score_gap,
            )
        qty = sizing["qty"] or 1.0
        return KisDryRunRiskDecision(
            approved=True,
            action=BUY,
            symbol=symbol,
            candidate={**candidate, "dry_run_entry_ready": True},
            reason="dry_run_risk_approved",
            risk_flags=_dedupe(risk_flags + ["simulated_only"]),
            gating_notes=_dedupe(
                gating_notes
                + [
                    "Dry-run risk approved a simulated buy.",
                    f"Position sizing used {sizing['position_size_pct']:.2%} of available equity.",
                ]
            ),
            qty=qty,
            notional=sizing["notional"] or _notional(qty, price),
            estimated_price=price,
            final_entry_score=final_entry_score,
            final_score_gap=final_score_gap,
        )

    def _evaluate_sell(
        self,
        preview: dict[str, Any],
        *,
        runtime: dict[str, Any],
        settings: Any,
        account_state: dict[str, Any],
    ) -> KisDryRunRiskDecision | None:
        max_sell_score = _safe_float(
            preview.get("max_sell_score"), settings.watchlist_max_sell_score
        )
        items = preview.get("portfolio_preview_items") or preview.get("child_runs") or []
        if not isinstance(items, list):
            return None

        managed_items: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            allowed = {str(value).lower() for value in _string_list(item.get("allowed_actions"))}
            if SELL not in allowed:
                continue
            managed_items.append(item)

        if not managed_items:
            return None

        market_session = preview.get("market_session") if isinstance(preview.get("market_session"), dict) else {}
        if market_session.get("is_market_open") is False:
            item = managed_items[0]
            return self._blocked(
                "market_closed",
                symbol=_symbol(item),
                candidate=item,
                risk_flags=_dedupe(
                    ["dry_run_only", "market_closed"] + _string_list(preview.get("risk_flags"))
                ),
                gating_notes=_dedupe(
                    ["KIS position simulation held because the market is closed."]
                    + _string_list(preview.get("gating_notes"))
                ),
            )

        sell_candidates: list[tuple[dict[str, Any], list[str]]] = []
        for item in managed_items:
            order_reason = self._conflicting_order_reason(
                None,
                symbol=_symbol(item),
                account_state=account_state,
                include_db=False,
            )
            if order_reason:
                return self._blocked(
                    order_reason,
                    symbol=_symbol(item),
                    candidate=item,
                    risk_flags=_dedupe(
                        ["dry_run_only", order_reason] + _string_list(preview.get("risk_flags"))
                    ),
                    gating_notes=_dedupe(
                        ["KIS position simulation held because a KIS order is already open or stale."]
                        + _string_list(preview.get("gating_notes"))
                    ),
                )
            exit_reasons = self._exit_reasons(item, max_sell_score=max_sell_score)
            if exit_reasons:
                sell_candidates.append((item, exit_reasons))

        if not sell_candidates:
            return None

        sell_candidates.sort(
            key=lambda row: (
                _exit_priority(row[1]),
                _safe_float(_sell_score(row[0]), 0.0),
            ),
            reverse=True,
        )
        candidate, exit_reasons = sell_candidates[0]
        symbol = _symbol(candidate)
        position = candidate.get("position") if isinstance(candidate.get("position"), dict) else {}
        qty = _safe_float(position.get("qty"), 1.0)
        if qty <= 0:
            qty = 1.0
        price = _safe_float_or_none(candidate.get("current_price")) or _safe_float_or_none(
            position.get("current_price")
        )
        return KisDryRunRiskDecision(
            approved=True,
            action=SELL,
            symbol=symbol,
            candidate={**candidate, "dry_run_exit_ready": True, "exit_reasons": exit_reasons},
            reason="dry_run_sell_risk_approved",
            risk_flags=_dedupe(
                ["dry_run_only", "simulated_only"]
                + exit_reasons
                + _string_list(preview.get("risk_flags"))
                + _string_list(candidate.get("risk_flags"))
            ),
            gating_notes=_dedupe(
                [
                    "Dry-run risk approved a simulated sell; entry caps do not block exits.",
                    f"Exit gates triggered: {', '.join(exit_reasons)}.",
                ]
                + _string_list(preview.get("gating_notes"))
                + _string_list(candidate.get("gating_notes"))
            ),
            qty=qty,
            notional=_notional(qty, price),
            estimated_price=price,
            final_entry_score=_entry_score(candidate),
            final_score_gap=_safe_float_or_none(preview.get("final_score_gap")),
        )

    def _exit_reasons(
        self,
        item: dict[str, Any],
        *,
        max_sell_score: float,
    ) -> list[str]:
        reasons: list[str] = []
        position = item.get("position") if isinstance(item.get("position"), dict) else {}
        unrealized_plpc = _position_pl_pct(position.get("unrealized_plpc"))
        if unrealized_plpc is not None and unrealized_plpc <= -0.015:
            reasons.append("stop_loss_triggered")
        if unrealized_plpc is not None and unrealized_plpc >= 0.03:
            reasons.append("take_profit_triggered")

        if self._has_scoreable_indicators(item):
            sell_score = _sell_score(item)
            buy_score = _entry_score(item)
            if sell_score is not None and sell_score >= max_sell_score:
                if buy_score is None or sell_score > buy_score:
                    reasons.append("sell_signal_triggered")
        return _dedupe(reasons)

    def _entry_candidate(self, preview: dict[str, Any]) -> dict[str, Any] | None:
        ranked = preview.get("final_ranked_candidates")
        entry_symbol = str(preview.get("entry_candidate_symbol") or "").upper()
        if isinstance(ranked, list) and entry_symbol:
            for item in ranked:
                if isinstance(item, dict) and _symbol(item) == entry_symbol:
                    return item

        candidate = preview.get("final_best_candidate")
        if isinstance(candidate, dict):
            return candidate

        if isinstance(ranked, list):
            for item in ranked:
                if isinstance(item, dict):
                    return item
        return None

    def _conflicting_order_reason(
        self,
        db: Session | None,
        *,
        symbol: str | None,
        account_state: dict[str, Any],
        include_db: bool = True,
    ) -> str | None:
        if not symbol:
            return None
        normalized_symbol = symbol.upper()
        for order in _dict_list(account_state.get("open_orders")):
            if str(order.get("symbol") or "").strip().upper() == normalized_symbol:
                return "conflicting_open_order_exists"
        for order in _dict_list(account_state.get("recent_orders")):
            if str(order.get("symbol") or "").strip().upper() != normalized_symbol:
                continue
            status = str(
                order.get("internal_status")
                or order.get("clear_status")
                or order.get("status")
                or ""
            ).upper()
            if status in OPEN_ORDER_STATUSES:
                return "stale_or_open_kis_order_exists"
        if include_db and db is not None:
            row = (
                db.query(OrderLog)
                .filter(OrderLog.broker == PROVIDER)
                .filter(OrderLog.symbol == normalized_symbol)
                .filter(OrderLog.internal_status.in_(sorted(OPEN_ORDER_STATUSES)))
                .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
                .first()
            )
            if row is not None:
                return "stale_or_open_kis_order_exists"
        return None

    def _daily_loss_limit_hit(self, account_state: dict[str, Any]) -> bool:
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

    def _daily_entry_count(self, db: Session, *, symbol: str | None = None) -> int:
        start_utc, end_utc = _kr_day_bounds_utc()
        query = (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.side == BUY)
            .filter(OrderLog.created_at >= start_utc)
            .filter(OrderLog.created_at < end_utc)
            .filter(
                or_(
                    OrderLog.internal_status.in_(sorted(SIMULATED_ENTRY_STATUSES)),
                    OrderLog.broker_status.in_(["SIMULATED", "submitted", "filled"]),
                )
            )
        )
        if symbol:
            query = query.filter(OrderLog.symbol == symbol.upper())
        return int(query.count() or 0)

    def _position_size(
        self,
        account_state: dict[str, Any],
        *,
        price: float | None,
        final_entry_score: float | None,
    ) -> dict[str, Any]:
        pct = _position_size_pct(final_entry_score or 0)
        if price is None or price <= 0:
            return {
                "blocked_reason": None,
                "qty": 1.0,
                "notional": None,
                "position_size_pct": pct,
            }
        balance = account_state.get("balance") if isinstance(account_state, dict) else {}
        if not isinstance(balance, dict):
            return {
                "blocked_reason": None,
                "qty": 1.0,
                "notional": _notional(1.0, price),
                "position_size_pct": pct,
            }
        equity = _first_float(
            balance,
            "total_asset_value",
            "total_equity",
            "equity",
            "stock_evaluation_amount",
        )
        cash = _first_float(balance, "cash", "available_cash", "dnca_tot_amt")
        if equity is None or equity <= 0:
            return {
                "blocked_reason": None,
                "qty": 1.0,
                "notional": _notional(1.0, price),
                "position_size_pct": pct,
            }
        target_notional = min(equity * pct, equity * MAX_POSITION_EQUITY_PCT)
        if cash is not None:
            target_notional = min(target_notional, cash)
        qty = int(target_notional // price)
        if qty <= 0:
            return {
                "blocked_reason": "insufficient_cash_for_min_order",
                "qty": None,
                "notional": None,
                "position_size_pct": pct,
            }
        return {
            "blocked_reason": None,
            "qty": float(qty),
            "notional": _notional(float(qty), price),
            "position_size_pct": pct,
        }

    def _has_scoreable_indicators(self, candidate: dict[str, Any]) -> bool:
        payload = candidate.get("indicator_payload")
        if not isinstance(payload, dict):
            return False
        status = str(candidate.get("indicator_status") or "").strip().lower()
        return status in {"ok", "partial"} and indicator_payload_is_quant_ready(payload)

    @staticmethod
    def _event_blocks_entry(candidate: dict[str, Any]) -> bool:
        flags = {item.lower() for item in _string_list(candidate.get("risk_flags"))}
        if "event_risk_entry_block" in flags:
            return True
        event = candidate.get("event_risk") or candidate.get("structured_event_risk")
        if isinstance(event, dict) and event.get("entry_blocked") is True:
            return True
        return False

    @staticmethod
    def _gpt_blocks_entry(candidate: dict[str, Any]) -> bool:
        flags = {item.lower() for item in _string_list(candidate.get("risk_flags"))}
        hint = str(
            candidate.get("gpt_action_hint") or candidate.get("action_hint") or ""
        ).strip().lower()
        return hint == "block_entry" or "gpt_blocked_entry" in flags

    @staticmethod
    def _blocked(
        reason: str,
        *,
        symbol: str | None = None,
        candidate: dict[str, Any] | None = None,
        risk_flags: list[str] | None = None,
        gating_notes: list[str] | None = None,
        final_entry_score: float | None = None,
        final_score_gap: float | None = None,
    ) -> KisDryRunRiskDecision:
        return KisDryRunRiskDecision(
            approved=False,
            action=HOLD,
            symbol=symbol,
            candidate=candidate,
            reason=reason,
            risk_flags=_dedupe(risk_flags or []),
            gating_notes=_dedupe(gating_notes or []),
            trigger_block_reason=reason,
            final_entry_score=final_entry_score,
            final_score_gap=final_score_gap,
        )


def _symbol(candidate: dict[str, Any] | None) -> str | None:
    if not candidate:
        return None
    value = str(candidate.get("symbol") or "").strip().upper()
    return value or None


def _entry_score(candidate: dict[str, Any]) -> float | None:
    for key in ("final_entry_score", "final_buy_score", "score", "quant_buy_score", "quant_score"):
        value = _safe_float_or_none(candidate.get(key))
        if value is not None:
            return value
    return None


def _sell_score(candidate: dict[str, Any]) -> float | None:
    for key in ("final_sell_score", "sell_score", "quant_sell_score", "ai_sell_score"):
        value = _safe_float_or_none(candidate.get(key))
        if value is not None:
            return value
    return None


def _notional(qty: float | None, price: float | None) -> float | None:
    if qty is None or price is None:
        return None
    return round(float(qty) * float(price), 2)


def _position_pl_pct(value: Any) -> float | None:
    parsed = _safe_float_or_none(value)
    if parsed is None:
        return None
    if abs(parsed) > 1.0:
        return parsed / 100.0
    return parsed


def _exit_priority(reasons: list[str]) -> int:
    if "stop_loss_triggered" in reasons:
        return 3
    if "take_profit_triggered" in reasons:
        return 2
    if "sell_signal_triggered" in reasons:
        return 1
    return 0


def _position_size_pct(final_buy_score: float) -> float:
    if final_buy_score >= 80:
        return min(STRONG_SETUP_POSITION_PCT, MAX_POSITION_EQUITY_PCT)
    if final_buy_score >= 70:
        return min(DECENT_SETUP_POSITION_PCT, MAX_POSITION_EQUITY_PCT)
    return min(WEAK_SETUP_POSITION_PCT, MAX_POSITION_EQUITY_PCT)


def _kr_day_bounds_utc() -> tuple[datetime, datetime]:
    now = datetime.now(KR_TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return (
        start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
        end.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
    )


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


def _held_symbol_set(preview: dict[str, Any], account_state: dict[str, Any]) -> set[str]:
    symbols = {str(item).upper() for item in _string_list(preview.get("held_symbols"))}
    for position in _dict_list(preview.get("held_positions")):
        symbol = str(position.get("symbol") or "").strip().upper()
        if symbol:
            symbols.add(symbol)
    for position in _dict_list(account_state.get("positions")):
        symbol = str(position.get("symbol") or "").strip().upper()
        if symbol:
            symbols.add(symbol)
    return symbols


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
        return [str(item) for item in value if str(item)]
    return [str(value)] if str(value) else []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
