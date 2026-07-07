from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import get_settings as get_app_settings
from app.db.models import (
    OrderLog,
    StrategyAutoBuyPromotion,
    StrategyLiveAutoBuyAttempt,
    StrategyLiveAutoExitAttempt,
    StrategyPerformanceSnapshot,
    StrategyProfile,
    TradeRunLog,
)
from app.services.runtime_setting_service import RuntimeSettingService


KST = ZoneInfo("Asia/Seoul")
SYNC_REQUIRED_STATUSES = {"UNKNOWN_STALE", "SYNC_FAILED"}
OPEN_ORDER_STATUSES = {"REQUESTED", "SUBMITTED", "ACCEPTED", "PENDING", "PARTIALLY_FILLED"}
SUBMITTED_ORDER_STATUSES = OPEN_ORDER_STATUSES | {"FILLED"}
FILLED_ORDER_STATUSES = {"FILLED"}
PARTIAL_ORDER_STATUSES = {"PARTIALLY_FILLED"}
REJECTED_ORDER_STATUSES = {"REJECTED", "FAILED", "REJECTED_BY_SAFETY_GATE"}
CANCELED_ORDER_STATUSES = {"CANCELED", "EXPIRED"}
BLOCKED_ATTEMPT_STATUSES = {
    "blocked",
    "failed",
    "rejected",
    "validation_failed",
    "safety_rejected",
    "rejected_by_safety_gate",
}


@dataclass
class _DayWindow:
    target_date: date
    start_utc: datetime
    end_utc: datetime


@dataclass
class _OpenLot:
    symbol: str
    qty: float
    price: float | None
    order_id: int | None
    filled_at: datetime | None


class DailyOpsSummaryService:
    """Read-only local daily operations summary.

    This service intentionally does not use broker clients, order sync services,
    validation services, or scheduler runners. It summarizes local DB state only.
    """

    def __init__(
        self,
        *,
        runtime_settings: RuntimeSettingService | None = None,
    ) -> None:
        self.runtime_settings = runtime_settings or RuntimeSettingService()

    def summary(
        self,
        db: Session,
        *,
        date_value: date | None = None,
        provider: str | None = None,
        market: str | None = None,
        include_details: bool = True,
    ) -> dict[str, Any]:
        normalized_provider = self._provider(provider)
        normalized_market = self._market(market, normalized_provider)
        window = self._window(date_value)
        generated_at = datetime.now(UTC)
        settings = self.runtime_settings.get_settings_read_only(db)
        app_settings = get_app_settings()
        active_profile = self._active_profile(db)

        orders_all = self._orders(db, provider=normalized_provider, market=normalized_market)
        orders_today = [
            row
            for row in orders_all
            if self._order_in_window(row, window.start_utc, window.end_utc)
        ]
        buy_attempts_all = self._attempts(
            db,
            StrategyLiveAutoBuyAttempt,
            provider=normalized_provider,
            market=normalized_market,
        )
        sell_attempts_all = self._attempts(
            db,
            StrategyLiveAutoExitAttempt,
            provider=normalized_provider,
            market=normalized_market,
        )
        promotions_all = self._promotions(
            db,
            provider=normalized_provider,
            market=normalized_market,
        )
        runs_today = self._scheduler_runs_today(db, window)
        buy_attempts_today = [
            row
            for row in buy_attempts_all
            if self._in_window(self._attempt_time(row), window.start_utc, window.end_utc)
        ]
        sell_attempts_today = [
            row
            for row in sell_attempts_all
            if self._in_window(self._attempt_time(row), window.start_utc, window.end_utc)
        ]
        promotions_today = [
            row
            for row in promotions_all
            if self._in_window(row.created_at, window.start_utc, window.end_utc)
        ]
        daily_snapshot = self._daily_snapshot(
            db,
            provider=normalized_provider,
            market=normalized_market,
            target_date=window.target_date,
        )

        pnl_summary = self._pnl_summary(
            orders_all,
            window=window,
            currency=self._currency(normalized_provider, normalized_market),
            daily_snapshot=daily_snapshot,
        )
        order_summary = self._order_summary(
            orders_today,
            generated_at=generated_at,
        )
        trade_activity = self._trade_activity(
            orders_today=orders_today,
            buy_attempts_today=buy_attempts_today,
            sell_attempts_today=sell_attempts_today,
            runs_today=runs_today,
        )
        promotion_summary = self._promotion_summary(
            promotions_all=promotions_all,
            promotions_today=promotions_today,
            generated_at=generated_at,
        )
        scheduler_summary = self._scheduler_summary(
            runs_today=runs_today,
            settings=settings,
            promotion_summary=promotion_summary,
        )
        reconciliation = self._reconciliation(
            orders_today=orders_today,
            order_summary=order_summary,
            pnl_summary=pnl_summary,
        )
        risk_summary = self._risk_summary(
            orders_today=orders_today,
            settings=settings,
            active_profile=active_profile,
            pnl_summary=pnl_summary,
            generated_at=generated_at,
        )

        details = (
            self._details(
                orders_today=orders_today,
                buy_attempts_today=buy_attempts_today,
                sell_attempts_today=sell_attempts_today,
                promotions_all=promotions_all,
                reconciliation=reconciliation,
            )
            if include_details
            else {}
        )

        return {
            "date": window.target_date.isoformat(),
            "timezone": "Asia/Seoul",
            "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
            "provider": normalized_provider,
            "market": normalized_market,
            "runtime_state": self._runtime_state(
                settings=settings,
                app_settings=app_settings,
                active_profile=active_profile,
            ),
            "trade_activity": trade_activity,
            "pnl_summary": pnl_summary,
            "order_summary": order_summary,
            "promotion_summary": promotion_summary,
            "scheduler_summary": scheduler_summary,
            "reconciliation": reconciliation,
            "risk_summary": risk_summary,
            "details": details,
            "safety": self._safety(),
        }

    def _runtime_state(
        self,
        *,
        settings: dict[str, Any],
        app_settings: Any,
        active_profile: StrategyProfile | None,
    ) -> dict[str, Any]:
        scheduler_enabled = bool(
            settings.get("strategy_auto_buy_scheduler_enabled")
            or settings.get("scheduler_enabled")
        )
        allow_live_orders = bool(settings.get("strategy_auto_buy_scheduler_allow_live_orders"))
        return {
            "dry_run": bool(settings.get("dry_run", True)),
            "kill_switch": bool(settings.get("kill_switch", False)),
            "kis_enabled": bool(getattr(app_settings, "kis_enabled", False)),
            "kis_real_order_enabled": bool(
                getattr(app_settings, "kis_real_order_enabled", False)
            ),
            "scheduler_enabled": scheduler_enabled,
            "scheduler_dry_run_only": bool(
                settings.get("strategy_auto_buy_scheduler_dry_run_only", True)
            ),
            "scheduler_real_orders_allowed": allow_live_orders is True,
            "bot_enabled": bool(settings.get("bot_enabled", True)),
            "active_profile": active_profile.profile_name if active_profile else None,
        }

    def _trade_activity(
        self,
        *,
        orders_today: list[OrderLog],
        buy_attempts_today: list[Any],
        sell_attempts_today: list[Any],
        runs_today: list[TradeRunLog],
    ) -> dict[str, Any]:
        buy_orders = [row for row in orders_today if self._side(row) == "buy"]
        sell_orders = [row for row in orders_today if self._side(row) == "sell"]
        blocked_attempts = [
            row
            for row in [*buy_attempts_today, *sell_attempts_today]
            if self._attempt_blocked(row)
        ]
        blocked_orders = [
            row for row in orders_today if self._status(row) in REJECTED_ORDER_STATUSES
        ]
        return {
            "guarded_buy_attempt_count": len(buy_attempts_today),
            "guarded_sell_attempt_count": len(sell_attempts_today),
            "submitted_buy_count": len(
                [
                    row
                    for row in buy_orders
                    if self._status(row) in SUBMITTED_ORDER_STATUSES
                    and not self._is_dry_run_order(row)
                ]
            ),
            "submitted_sell_count": len(
                [
                    row
                    for row in sell_orders
                    if self._status(row) in SUBMITTED_ORDER_STATUSES
                    and not self._is_dry_run_order(row)
                ]
            ),
            "filled_buy_count": len(
                [row for row in buy_orders if self._status(row) in FILLED_ORDER_STATUSES]
            ),
            "filled_sell_count": len(
                [row for row in sell_orders if self._status(row) in FILLED_ORDER_STATUSES]
            ),
            "blocked_attempt_count": len(blocked_attempts) + len(blocked_orders),
            "dry_run_simulated_count": len(
                [row for row in orders_today if self._is_dry_run_order(row)]
            )
            + len([row for row in runs_today if self._run_is_dry_simulation(row)]),
            "manual_live_count": len([row for row in orders_today if self._manual_live(row)]),
        }

    def _pnl_summary(
        self,
        orders_all: list[OrderLog],
        *,
        window: _DayWindow,
        currency: str,
        daily_snapshot: StrategyPerformanceSnapshot | None,
    ) -> dict[str, Any]:
        realized = 0.0
        basis = 0.0
        incomplete_count = 0
        closed_trade_count = 0
        audit_flags: list[str] = []
        lots_by_symbol: dict[str, deque[_OpenLot]] = defaultdict(deque)

        filled_orders = [
            row
            for row in orders_all
            if self._filled_quantity(row) > 0
            and not self._is_dry_run_order(row)
            and self._order_fill_time(row) is not None
            and self._aware_utc(self._order_fill_time(row)) < window.end_utc
        ]
        filled_orders.sort(
            key=lambda row: (
                self._aware_utc(self._order_fill_time(row)),
                int(row.id or 0),
            )
        )

        for row in filled_orders:
            side = self._side(row)
            symbol = str(row.symbol or "").strip().upper()
            qty = self._filled_quantity(row)
            if not symbol or qty <= 0:
                continue
            price = self._fill_price(row)
            fill_time = self._aware_utc(self._order_fill_time(row))
            if side == "buy":
                lots_by_symbol[symbol].append(
                    _OpenLot(
                        symbol=symbol,
                        qty=qty,
                        price=price,
                        order_id=row.id,
                        filled_at=fill_time,
                    )
                )
                continue
            if side != "sell":
                continue

            remaining = qty
            sell_is_today = window.start_utc <= fill_time < window.end_utc
            while remaining > 0:
                lot = lots_by_symbol[symbol][0] if lots_by_symbol[symbol] else None
                if lot is None:
                    if sell_is_today:
                        incomplete_count += 1
                        audit_flags.append("missing_matching_buy_fill")
                    break
                matched = min(remaining, lot.qty)
                if sell_is_today:
                    closed_trade_count += 1
                    if price is None or lot.price is None:
                        incomplete_count += 1
                        audit_flags.append("missing_fill_price")
                    else:
                        realized += (price - lot.price) * matched
                        basis += lot.price * matched
                lot.qty -= matched
                remaining -= matched
                if lot.qty <= 1e-9:
                    lots_by_symbol[symbol].popleft()

        open_position_count = len(
            [
                symbol
                for symbol, lots in lots_by_symbol.items()
                if symbol and sum(max(lot.qty, 0.0) for lot in lots) > 1e-9
            ]
        )
        unrealized_pl = (
            float(daily_snapshot.unrealized_pnl)
            if daily_snapshot is not None and daily_snapshot.unrealized_pnl is not None
            else None
        )
        total_position_value = self._snapshot_number(
            daily_snapshot,
            "total_position_value",
            "market_value",
            "stock_evaluation_amount",
        )
        cash = self._snapshot_number(daily_snapshot, "cash", "available_cash", "dnca_tot_amt")

        if open_position_count and unrealized_pl is None:
            incomplete_count += 1
            audit_flags.append("unrealized_pnl_unavailable_local_only")

        audit_flags = sorted(set(audit_flags))
        realized_pct = realized / basis if basis > 0 else None
        return {
            "currency": currency,
            "realized_pl": round(realized, 4),
            "realized_pl_pct": round(realized_pct, 6) if realized_pct is not None else None,
            "unrealized_pl": unrealized_pl,
            "total_position_value": total_position_value,
            "cash": cash,
            "closed_trade_count": closed_trade_count,
            "open_position_count": open_position_count,
            "incomplete_calculation_count": incomplete_count,
            "audit_flags": audit_flags,
            "data_source": "local_order_logs_and_cached_snapshots",
        }

    def _order_summary(
        self,
        orders_today: list[OrderLog],
        *,
        generated_at: datetime,
    ) -> dict[str, Any]:
        status_buckets = {
            "submitted": 0,
            "filled": 0,
            "partially_filled": 0,
            "rejected": 0,
            "canceled": 0,
            "pending_sync": 0,
            "unknown": 0,
        }
        sync_required = 0
        stale = 0
        latest: datetime | None = None
        for row in orders_today:
            if self._needs_sync(row):
                status_buckets["pending_sync"] += 1
                sync_required += 1
            else:
                status_buckets[self._status_bucket(row)] += 1
            if self._is_stale_order(row, generated_at=generated_at):
                stale += 1
            latest = self._max_dt(latest, self._latest_order_time(row))
        return {
            "total_orders_today": len(orders_today),
            "status_buckets": status_buckets,
            "sync_required_count": sync_required,
            "stale_order_count": stale,
            "latest_order_status_at": self._iso(latest),
        }

    def _promotion_summary(
        self,
        *,
        promotions_all: list[StrategyAutoBuyPromotion],
        promotions_today: list[StrategyAutoBuyPromotion],
        generated_at: datetime,
    ) -> dict[str, Any]:
        return {
            "created_today": len(promotions_today),
            "pending": len([row for row in promotions_all if self._promotion_status(row) == "pending"]),
            "reviewed": len(
                [
                    row
                    for row in promotions_all
                    if row.acknowledged_at is not None or row.dismissed_at is not None
                ]
            ),
            "acknowledged": len([row for row in promotions_all if row.acknowledged_at is not None]),
            "dismissed": len([row for row in promotions_all if row.dismissed_at is not None]),
            "converted": len(
                [
                    row
                    for row in promotions_all
                    if row.converted_at is not None
                    or row.converted_order_id is not None
                    or row.converted_live_attempt_id is not None
                ]
            ),
            "expired_or_stale": len(
                [row for row in promotions_all if self._promotion_expired_or_stale(row, generated_at)]
            ),
            "blocked_conversion_count": len(
                [
                    row
                    for row in promotions_all
                    if row.block_reason
                    or str(row.conversion_status or "").lower()
                    in {"blocked", "failed", "rejected"}
                ]
            ),
        }

    def _scheduler_summary(
        self,
        *,
        runs_today: list[TradeRunLog],
        settings: dict[str, Any],
        promotion_summary: dict[str, Any],
    ) -> dict[str, Any]:
        actions = [self._run_action(row) for row in runs_today]
        position_management_runs = [
            row
            for row in runs_today
            if "position_management_dry_run" in str(row.mode or "").lower()
        ]
        position_payloads = [self._json_obj(row.response_payload) for row in position_management_runs]
        return {
            "scheduler_enabled": bool(
                settings.get("strategy_auto_buy_scheduler_enabled")
                or settings.get("position_management_scheduler_enabled")
                or settings.get("scheduler_enabled")
            ),
            "dry_run_only": bool(settings.get("strategy_auto_buy_scheduler_dry_run_only", True)),
            "run_count_today": len(runs_today),
            "position_management_dry_run_count": len(position_management_runs),
            "position_management_exit_candidate_count": sum(
                int(payload.get("exit_candidate_count") or 0)
                for payload in position_payloads
            ),
            "position_management_critical_candidate_count": sum(
                int(payload.get("critical_candidate_count") or 0)
                for payload in position_payloads
            ),
            "would_buy_count": len([item for item in actions if item == "would_buy"]),
            "hold_count": len([item for item in actions if item == "hold"]),
            "skipped_count": len(
                [
                    item
                    for item in actions
                    if item in {"blocked", "skipped", "failed", "error"}
                ]
            ),
            "promotion_created_count": int(promotion_summary.get("created_today") or 0),
            "real_order_submitted": False,
        }

    def _reconciliation(
        self,
        *,
        orders_today: list[OrderLog],
        order_summary: dict[str, Any],
        pnl_summary: dict[str, Any],
    ) -> dict[str, Any]:
        missing_kis_odno = len(
            [
                row
                for row in orders_today
                if self._live_order_requiring_broker_id(row) and not row.kis_odno
            ]
        )
        missing_broker_order_id = len(
            [
                row
                for row in orders_today
                if self._live_order_requiring_broker_id(row) and not row.broker_order_id
            ]
        )
        local_pending_without_broker = len(
            [
                row
                for row in orders_today
                if self._status(row) in OPEN_ORDER_STATUSES
                and not self._is_dry_run_order(row)
                and not self._has_broker_status(row)
            ]
        )
        stale_sync_count = int(order_summary.get("stale_order_count") or 0)
        sync_required_count = int(order_summary.get("sync_required_count") or 0)
        warnings = ["local_summary_only_no_broker_read"]
        if sync_required_count:
            warnings.append("local_orders_require_status_sync")
        if local_pending_without_broker:
            warnings.append("local_pending_orders_missing_broker_status")
        if missing_kis_odno or missing_broker_order_id:
            warnings.append("live_order_missing_broker_identifier")
        if pnl_summary.get("incomplete_calculation_count"):
            warnings.append("pnl_calculation_incomplete")

        attention_count = (
            sync_required_count
            + local_pending_without_broker
            + missing_kis_odno
            + missing_broker_order_id
            + stale_sync_count
        )
        status = "attention_required" if attention_count else "warning"
        next_safe_actions = [
            "Review local orders and KIS order status in the Operations logs.",
            "Use the existing explicit sync controls outside this summary if operator review confirms it is safe.",
        ]
        if not attention_count:
            next_safe_actions = [
                "No local order mismatch requiring action was detected.",
                "Use existing read-only logs for drilldown; this endpoint will not sync or submit.",
            ]
        return {
            "status": status,
            "broker_read_available": False,
            "open_order_mismatch_count": 0,
            "local_pending_without_broker_status_count": local_pending_without_broker,
            "broker_order_without_local_link_count": 0,
            "missing_kis_odno_count": missing_kis_odno,
            "missing_broker_order_id_count": missing_broker_order_id,
            "stale_sync_count": stale_sync_count,
            "warnings": sorted(set(warnings)),
            "next_safe_actions": next_safe_actions,
        }

    def _risk_summary(
        self,
        *,
        orders_today: list[OrderLog],
        settings: dict[str, Any],
        active_profile: StrategyProfile | None,
        pnl_summary: dict[str, Any],
        generated_at: datetime,
    ) -> dict[str, Any]:
        live_trade_count = len(
            [
                row
                for row in orders_today
                if self._status(row) in SUBMITTED_ORDER_STATUSES
                and not self._is_dry_run_order(row)
            ]
        )
        limit = self._int_or_none(settings.get("max_trades_per_day"))
        remaining = max(limit - live_trade_count, 0) if limit is not None else None
        duplicate_count = self._duplicate_order_risk_count(orders_today)
        loss_status = self._daily_loss_limit_status(
            pnl_summary=pnl_summary,
            active_profile=active_profile,
        )
        max_positions = self._int_or_none(settings.get("max_open_positions"))
        open_positions = int(pnl_summary.get("open_position_count") or 0)
        return {
            "daily_trade_limit_used": live_trade_count,
            "daily_trade_limit_remaining": remaining,
            "daily_loss_limit_status": loss_status,
            "kill_switch_status": "on" if settings.get("kill_switch") else "off",
            "duplicate_order_risk_count": duplicate_count,
            "open_position_count": open_positions,
            "max_position_warning": (
                "max_open_positions_reached"
                if max_positions is not None and open_positions >= max_positions
                else None
            ),
            "no_new_entry_window_status": self._no_new_entry_window_status(
                settings=settings,
                generated_at=generated_at,
            ),
        }

    def _details(
        self,
        *,
        orders_today: list[OrderLog],
        buy_attempts_today: list[StrategyLiveAutoBuyAttempt],
        sell_attempts_today: list[StrategyLiveAutoExitAttempt],
        promotions_all: list[StrategyAutoBuyPromotion],
        reconciliation: dict[str, Any],
    ) -> dict[str, Any]:
        sync_required_items = [
            self._order_detail(row)
            for row in orders_today
            if self._needs_sync(row) or self._live_order_requiring_broker_id(row)
        ][:20]
        blocked_items = [
            self._attempt_detail(row, side="buy")
            for row in buy_attempts_today
            if self._attempt_blocked(row)
        ] + [
            self._attempt_detail(row, side="sell")
            for row in sell_attempts_today
            if self._attempt_blocked(row)
        ]
        return {
            "recent_orders": [
                self._order_detail(row)
                for row in sorted(
                    orders_today,
                    key=lambda item: (self._latest_order_time(item) or datetime.min, item.id or 0),
                    reverse=True,
                )[:10]
            ],
            "recent_promotions": [
                self._promotion_detail(row)
                for row in sorted(
                    promotions_all,
                    key=lambda item: (self._aware_utc(item.created_at), item.id or 0),
                    reverse=True,
                )[:10]
            ],
            "recent_guarded_buy_attempts": [
                self._attempt_detail(row, side="buy") for row in buy_attempts_today[:10]
            ],
            "recent_guarded_sell_attempts": [
                self._attempt_detail(row, side="sell") for row in sell_attempts_today[:10]
            ],
            "sync_required_items": sync_required_items,
            "blocked_items": blocked_items[:20],
            "lifecycle_summary_references": [
                {
                    "source": "local_orders",
                    "status": reconciliation.get("status"),
                    "broker_read_available": False,
                }
            ],
        }

    def _safety(self) -> dict[str, Any]:
        return {
            "read_only": True,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "validation_called": False,
            "sync_called": False,
            "setting_changed": False,
            "scheduler_changed": False,
            "order_state_mutated": False,
        }

    def _orders(self, db: Session, *, provider: str, market: str) -> list[OrderLog]:
        rows = db.query(OrderLog).filter(OrderLog.broker == provider).all()
        return [row for row in rows if self._row_market(row, provider) == market]

    def _attempts(self, db: Session, model: Any, *, provider: str, market: str) -> list[Any]:
        return (
            db.query(model)
            .filter(model.provider == provider, model.market == market)
            .order_by(model.created_at.desc(), model.id.desc())
            .all()
        )

    def _promotions(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
    ) -> list[StrategyAutoBuyPromotion]:
        return (
            db.query(StrategyAutoBuyPromotion)
            .filter(
                StrategyAutoBuyPromotion.provider == provider,
                StrategyAutoBuyPromotion.market == market,
            )
            .order_by(
                StrategyAutoBuyPromotion.created_at.desc(),
                StrategyAutoBuyPromotion.id.desc(),
            )
            .all()
        )

    def _scheduler_runs_today(self, db: Session, window: _DayWindow) -> list[TradeRunLog]:
        rows = db.query(TradeRunLog).order_by(TradeRunLog.created_at.desc()).all()
        return [
            row
            for row in rows
            if self._in_window(row.created_at, window.start_utc, window.end_utc)
            and self._is_scheduler_run(row)
        ]

    def _daily_snapshot(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
        target_date: date,
    ) -> StrategyPerformanceSnapshot | None:
        return (
            db.query(StrategyPerformanceSnapshot)
            .filter(
                StrategyPerformanceSnapshot.provider == provider,
                StrategyPerformanceSnapshot.market == market,
                StrategyPerformanceSnapshot.period_type == "daily",
                StrategyPerformanceSnapshot.period_key == target_date.isoformat(),
            )
            .order_by(StrategyPerformanceSnapshot.created_at.desc())
            .first()
        )

    def _active_profile(self, db: Session) -> StrategyProfile | None:
        return (
            db.query(StrategyProfile)
            .filter(StrategyProfile.is_active == True)  # noqa: E712
            .order_by(StrategyProfile.id.asc())
            .first()
        )

    def _window(self, date_value: date | None) -> _DayWindow:
        target = date_value or datetime.now(KST).date()
        start_local = datetime.combine(target, time.min, tzinfo=KST)
        end_local = start_local + timedelta(days=1)
        return _DayWindow(
            target_date=target,
            start_utc=start_local.astimezone(UTC),
            end_utc=end_local.astimezone(UTC),
        )

    def _provider(self, value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        return normalized or "kis"

    def _market(self, value: str | None, provider: str) -> str:
        normalized = str(value or "").strip().upper()
        if normalized:
            return normalized
        return "KR" if provider == "kis" else "US"

    def _currency(self, provider: str, market: str) -> str:
        return "KRW" if provider == "kis" and market == "KR" else "USD"

    def _row_market(self, row: OrderLog, provider: str) -> str:
        explicit = str(row.market or "").strip().upper()
        if explicit:
            return explicit
        return "KR" if provider == "kis" else "US"

    def _order_in_window(self, row: OrderLog, start: datetime, end: datetime) -> bool:
        return any(
            self._in_window(value, start, end)
            for value in (
                row.created_at,
                row.submitted_at,
                row.filled_at,
                row.canceled_at,
                row.updated_at,
            )
        )

    def _in_window(self, value: Any, start: datetime, end: datetime) -> bool:
        dt = self._aware_utc(value)
        return dt is not None and start <= dt < end

    def _aware_utc(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                return None
            value = parsed
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _iso(self, value: Any) -> str | None:
        dt = self._aware_utc(value)
        if dt is None:
            return None
        return dt.isoformat().replace("+00:00", "Z")

    def _json_obj(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if value is None:
            return {}
        try:
            parsed = json.loads(str(value))
        except Exception:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}

    def _payloads(self, row: Any) -> Iterable[dict[str, Any]]:
        for attr in ("request_payload", "response_payload", "last_sync_payload"):
            payload = self._json_obj(getattr(row, attr, None))
            if payload:
                yield payload

    def _payload_bool(self, row: Any, key: str) -> bool:
        for payload in self._payloads(row):
            if payload.get(key) is True:
                return True
        return False

    def _payload_number(self, row: Any, *keys: str) -> float | None:
        for payload in self._payloads(row):
            for key in keys:
                value = payload.get(key)
                if isinstance(value, dict):
                    continue
                parsed = self._float_or_none(value)
                if parsed is not None:
                    return parsed
        return None

    def _snapshot_number(
        self,
        snapshot: StrategyPerformanceSnapshot | None,
        *keys: str,
    ) -> float | None:
        if snapshot is None:
            return None
        payload = self._json_obj(snapshot.source_payload)
        for key in keys:
            value = payload.get(key)
            parsed = self._float_or_none(value)
            if parsed is not None:
                return parsed
        return None

    def _status(self, row: OrderLog) -> str:
        return str(row.internal_status or "").strip().upper()

    def _side(self, row: OrderLog) -> str:
        return str(row.side or "").strip().lower()

    def _status_bucket(self, row: OrderLog) -> str:
        status = self._status(row)
        if status in {"REQUESTED", "SUBMITTED", "ACCEPTED", "PENDING"}:
            return "submitted"
        if status in FILLED_ORDER_STATUSES:
            return "filled"
        if status in PARTIAL_ORDER_STATUSES:
            return "partially_filled"
        if status in REJECTED_ORDER_STATUSES:
            return "rejected"
        if status in CANCELED_ORDER_STATUSES:
            return "canceled"
        return "unknown"

    def _needs_sync(self, row: OrderLog) -> bool:
        status = self._status(row)
        broker_status = " ".join(
            [
                str(row.broker_status or ""),
                str(row.broker_order_status or ""),
                str(row.sync_error or ""),
            ]
        ).lower()
        if status in SYNC_REQUIRED_STATUSES:
            return True
        if "sync_required" in broker_status or "pending_sync" in broker_status:
            return True
        if (
            status in OPEN_ORDER_STATUSES
            and not self._is_dry_run_order(row)
            and (row.last_synced_at is None or not self._has_broker_status(row))
        ):
            return True
        return False

    def _has_broker_status(self, row: OrderLog) -> bool:
        return bool(str(row.broker_status or row.broker_order_status or "").strip())

    def _is_stale_order(self, row: OrderLog, *, generated_at: datetime) -> bool:
        if self._status(row) not in OPEN_ORDER_STATUSES and not self._needs_sync(row):
            return False
        latest = self._aware_utc(row.last_synced_at) or self._latest_order_time(row)
        if latest is None:
            return True
        return generated_at - latest > timedelta(minutes=30)

    def _live_order_requiring_broker_id(self, row: OrderLog) -> bool:
        return (
            self._status(row) in SUBMITTED_ORDER_STATUSES
            and not self._is_dry_run_order(row)
            and self._side(row) in {"buy", "sell"}
        )

    def _latest_order_time(self, row: OrderLog) -> datetime | None:
        latest: datetime | None = None
        for value in (row.updated_at, row.filled_at, row.submitted_at, row.canceled_at, row.created_at):
            latest = self._max_dt(latest, value)
        return latest

    def _order_fill_time(self, row: OrderLog) -> datetime | None:
        return self._aware_utc(row.filled_at) or self._aware_utc(row.submitted_at) or self._aware_utc(row.created_at)

    def _max_dt(self, first: Any, second: Any) -> datetime | None:
        left = self._aware_utc(first)
        right = self._aware_utc(second)
        if left is None:
            return right
        if right is None:
            return left
        return max(left, right)

    def _is_dry_run_order(self, row: OrderLog) -> bool:
        return (
            self._status(row) == "DRY_RUN_SIMULATED"
            or self._payload_bool(row, "dry_run")
            or self._payload_bool(row, "simulated")
            or self._payload_bool(row, "preview_only")
        )

    def _manual_live(self, row: OrderLog) -> bool:
        if self._is_dry_run_order(row):
            return False
        text = " ".join(
            [
                str(row.request_payload or ""),
                str(row.response_payload or ""),
                str(row.client_order_id or ""),
            ]
        ).lower()
        return self._payload_bool(row, "manual_submit_called") or "manual" in text

    def _filled_quantity(self, row: OrderLog) -> float:
        for value in (row.filled_qty, row.qty, row.requested_qty):
            parsed = self._float_or_none(value)
            if parsed is not None and parsed > 0:
                return parsed
        return 0.0

    def _fill_price(self, row: OrderLog) -> float | None:
        for value in (row.avg_fill_price, row.filled_avg_price, row.limit_price):
            parsed = self._float_or_none(value)
            if parsed is not None and parsed > 0:
                return parsed
        parsed = self._payload_number(
            row,
            "avg_fill_price",
            "filled_avg_price",
            "average_fill_price",
            "price",
            "current_price",
            "executed_price",
        )
        if parsed is not None and parsed > 0:
            return parsed
        notional = self._float_or_none(row.notional)
        qty = self._filled_quantity(row)
        if notional is not None and notional > 0 and qty > 0:
            return notional / qty
        return None

    def _attempt_time(self, row: Any) -> datetime | None:
        return (
            self._aware_utc(getattr(row, "submitted_at", None))
            or self._aware_utc(getattr(row, "created_at", None))
        )

    def _attempt_blocked(self, row: Any) -> bool:
        status = str(getattr(row, "status", "") or "").strip().lower()
        return status in BLOCKED_ATTEMPT_STATUSES or bool(getattr(row, "block_reason", None))

    def _promotion_status(self, row: StrategyAutoBuyPromotion) -> str:
        return str(row.status or "").strip().lower()

    def _promotion_expired_or_stale(
        self,
        row: StrategyAutoBuyPromotion,
        generated_at: datetime,
    ) -> bool:
        status = self._promotion_status(row)
        expires_at = self._aware_utc(row.expires_at)
        return status in {"expired", "stale"} or (
            status == "pending" and expires_at is not None and expires_at < generated_at
        )

    def _is_scheduler_run(self, row: TradeRunLog) -> bool:
        text = " ".join(
            [
                str(row.mode or ""),
                str(row.trigger_source or ""),
                str(row.request_payload or ""),
                str(row.response_payload or ""),
            ]
        ).lower()
        return (
            "strategy_auto_buy_scheduler" in text
            or "strategy_auto_buy_dry_run" in text
            or "position_management_dry_run" in text
        )

    def _run_action(self, row: TradeRunLog) -> str:
        payload = self._json_obj(row.response_payload)
        action = str(
            payload.get("action")
            or payload.get("dry_run_action")
            or payload.get("decision")
            or row.result
            or row.stage
            or ""
        ).strip().lower()
        if "would_buy" in action or "would buy" in action:
            return "would_buy"
        if "hold" in action:
            return "hold"
        if "skip" in action:
            return "skipped"
        if "block" in action:
            return "blocked"
        return action or "unknown"

    def _run_is_dry_simulation(self, row: TradeRunLog) -> bool:
        payload = self._json_obj(row.response_payload)
        return (
            "dry_run" in str(row.mode or "").lower()
            or "dry_run" in str(row.trigger_source or "").lower()
            or payload.get("dry_run") is True
            or payload.get("simulated") is True
        )

    def _duplicate_order_risk_count(self, orders_today: list[OrderLog]) -> int:
        counts: dict[tuple[str, str], int] = defaultdict(int)
        for row in orders_today:
            if self._status(row) not in OPEN_ORDER_STATUSES:
                continue
            if self._is_dry_run_order(row):
                continue
            key = (str(row.symbol or "").upper(), self._side(row))
            if key[0] and key[1]:
                counts[key] += 1
        return sum(max(count - 1, 0) for count in counts.values())

    def _daily_loss_limit_status(
        self,
        *,
        pnl_summary: dict[str, Any],
        active_profile: StrategyProfile | None,
    ) -> str:
        if active_profile is None:
            return "unknown"
        realized_pct = self._float_or_none(pnl_summary.get("realized_pl_pct"))
        if realized_pct is None:
            return "unknown"
        daily_limit = self._float_or_none(active_profile.daily_max_loss_pct)
        if daily_limit is None:
            return "unknown"
        return "breached" if realized_pct <= -abs(daily_limit) else "ok"

    def _no_new_entry_window_status(
        self,
        *,
        settings: dict[str, Any],
        generated_at: datetime,
    ) -> str:
        value = (
            settings.get("strategy_auto_buy_scheduler_no_new_entry_after")
            or settings.get("kis_limited_auto_buy_no_new_entry_after")
        )
        text = str(value or "").strip()
        if not text:
            return "unknown"
        try:
            hour, minute = [int(part) for part in text.split(":", 1)]
            cutoff = time(hour=hour, minute=minute)
        except Exception:
            return "unknown"
        return (
            "active"
            if generated_at.astimezone(KST).time() >= cutoff
            else "not_active"
        )

    def _order_detail(self, row: OrderLog) -> dict[str, Any]:
        return {
            "id": row.id,
            "provider": row.broker,
            "market": self._row_market(row, row.broker),
            "symbol": row.symbol,
            "side": self._side(row),
            "quantity": self._filled_quantity(row) or self._float_or_none(row.qty),
            "notional": self._float_or_none(row.notional),
            "internal_status": row.internal_status,
            "broker_status": row.broker_status or row.broker_order_status,
            "client_order_id": row.client_order_id,
            "broker_order_id_present": bool(row.broker_order_id),
            "kis_odno_present": bool(row.kis_odno),
            "last_synced_at": self._iso(row.last_synced_at),
            "created_at": self._iso(row.created_at),
            "updated_at": self._iso(row.updated_at),
            "needs_sync": self._needs_sync(row),
            "dry_run": self._is_dry_run_order(row),
        }

    def _attempt_detail(self, row: Any, *, side: str) -> dict[str, Any]:
        return {
            "id": getattr(row, "id", None),
            "side": side,
            "provider": getattr(row, "provider", None),
            "market": getattr(row, "market", None),
            "active_profile": getattr(row, "active_profile", None),
            "symbol": getattr(row, "symbol", None),
            "status": getattr(row, "status", None),
            "trigger_source": getattr(row, "trigger_source", None),
            "related_order_id": getattr(row, "related_order_id", None),
            "broker_order_id_present": bool(getattr(row, "broker_order_id", None)),
            "block_reason": getattr(row, "block_reason", None),
            "created_at": self._iso(getattr(row, "created_at", None)),
            "submitted_at": self._iso(getattr(row, "submitted_at", None)),
            "synced_at": self._iso(getattr(row, "synced_at", None)),
        }

    def _promotion_detail(self, row: StrategyAutoBuyPromotion) -> dict[str, Any]:
        return {
            "id": row.id,
            "provider": row.provider,
            "market": row.market,
            "active_profile": row.active_profile,
            "symbol": row.symbol,
            "status": row.status,
            "dry_run_action": row.dry_run_action,
            "final_score": self._float_or_none(row.final_score),
            "confidence": self._float_or_none(row.confidence),
            "block_reason": row.block_reason,
            "conversion_status": row.conversion_status,
            "converted_order_id": row.converted_order_id,
            "created_at": self._iso(row.created_at),
            "expires_at": self._iso(row.expires_at),
            "acknowledged_at": self._iso(row.acknowledged_at),
            "dismissed_at": self._iso(row.dismissed_at),
            "converted_at": self._iso(row.converted_at),
        }

    def _int_or_none(self, value: Any) -> int | None:
        try:
            return int(value)
        except Exception:
            return None

    def _float_or_none(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value).replace(",", ""))
        except Exception:
            return None
