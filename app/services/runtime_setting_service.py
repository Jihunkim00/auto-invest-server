from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.constants import DEFAULT_GATE_LEVEL, MAX_TRADES_PER_DAY, NEAR_CLOSE_MINUTES
from app.db.models import OrderLog, RuntimeSetting


KR_TZ = ZoneInfo("Asia/Seoul")
CONSERVATIVE_LIVE_ORDER_LIMIT = 1
CONSERVATIVE_MAX_NOTIONAL_PCT = 0.03
KIS_BUY_EXECUTION_FLAGS = (
    "kis_scheduler_buy_enabled",
    "kis_scheduler_allow_limited_auto_buy",
    "kis_live_auto_buy_enabled",
    "kis_limited_auto_buy_enabled",
)


class RuntimeSettingService:
    def __init__(self):
        self.settings = get_settings()

    def _defaults(self) -> dict[str, Any]:
        return {
            "bot_enabled": True,
            "dry_run": bool(self.settings.dry_run),
            "kill_switch": False,
            "scheduler_enabled": False,
            "default_symbol": self.settings.default_symbol.upper(),
            "default_gate_level": DEFAULT_GATE_LEVEL,
            "max_trades_per_day": MAX_TRADES_PER_DAY,
            "global_daily_entry_limit": 2,
            "per_symbol_daily_entry_limit": 1,
            "per_slot_new_entry_limit": 1,
            "max_open_positions": 3,
            "near_close_block_minutes": NEAR_CLOSE_MINUTES,
            "same_direction_cooldown_minutes": 120,
            "kis_live_auto_enabled": False,
            "kis_live_auto_buy_enabled": False,
            "kis_live_auto_sell_enabled": False,
            "kis_live_auto_requires_manual_confirm": True,
            "kis_live_auto_max_orders_per_day": 1,
            "kis_live_auto_max_notional_pct": 0.03,
            "kis_limited_auto_sell_enabled": False,
            "kis_limited_auto_stop_loss_enabled": False,
            "kis_limited_auto_take_profit_enabled": False,
            "kis_limited_auto_sell_stop_loss_enabled": False,
            "kis_limited_auto_sell_take_profit_enabled": False,
            "kis_limited_auto_sell_requires_queue_review": True,
            "kis_limited_auto_sell_max_orders_per_day": 1,
            "kis_limited_auto_sell_max_notional_pct": 0.03,
            "kis_limited_auto_sell_min_shadow_occurrences": 1,
            "kis_limited_auto_sell_allow_manual_review_trigger": False,
            "kis_limited_auto_sell_allow_take_profit_trigger": False,
            "kis_limited_auto_buy_enabled": False,
            "kis_limited_auto_buy_readiness_enabled": True,
            "kis_limited_auto_buy_shadow_enabled": True,
            "kis_limited_auto_buy_requires_shadow_review": True,
            "kis_limited_auto_buy_max_orders_per_day": 1,
            "kis_limited_auto_buy_max_notional_pct": 0.03,
            "kis_limited_auto_buy_min_cash_buffer_krw": 0.0,
            "kis_limited_auto_buy_requires_existing_sell_guards": True,
            "kis_limited_auto_buy_min_final_score": 75.0,
            "kis_limited_auto_buy_min_confidence": 0.70,
            "kis_limited_auto_buy_max_positions": 3,
            "kis_limited_auto_buy_block_if_position_exists": True,
            "kis_limited_auto_buy_block_if_open_order_exists": True,
            "kis_limited_auto_buy_allow_reentry_same_day": False,
            "kis_limited_auto_buy_require_market_open": True,
            "kis_limited_auto_buy_no_new_entry_after": "14:50",
            "kis_limited_auto_buy_allow_gpt_hard_block": False,
            "kis_scheduler_enabled": False,
            "kis_scheduler_dry_run": True,
            "kis_scheduler_live_enabled": False,
            "kis_scheduler_allow_real_orders": False,
            "kis_scheduler_configured_allow_real_orders": False,
            "kis_scheduler_buy_enabled": False,
            "kis_scheduler_sell_enabled": False,
            "kis_scheduler_allow_limited_auto_buy": False,
            "kis_scheduler_allow_limited_auto_sell": False,
            "kis_scheduler_max_live_orders_per_day": CONSERVATIVE_LIVE_ORDER_LIMIT,
            "kis_scheduler_live_requires_dry_run_false": True,
            "kis_scheduler_live_respect_kill_switch": True,
        }

    def get_or_create(self, db: Session) -> RuntimeSetting:
        row = db.query(RuntimeSetting).first()
        if row:
            return row

        defaults = self._defaults()
        row = RuntimeSetting(**defaults)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def get_settings(self, db: Session) -> dict[str, Any]:
        row = self.get_or_create(db)
        return self._settings_from_row(row)

    def get_settings_read_only(self, db: Session) -> dict[str, Any]:
        row = db.query(RuntimeSetting).first()
        if row:
            return self._settings_from_row(row)

        settings = self._defaults()
        settings["updated_at"] = None
        return self._finalize_settings(settings)

    def _settings_from_row(self, row: RuntimeSetting) -> dict[str, Any]:
        settings = {
            "bot_enabled": bool(row.bot_enabled),
            "dry_run": bool(row.dry_run),
            "kill_switch": bool(row.kill_switch),
            "scheduler_enabled": bool(row.scheduler_enabled),
            "default_symbol": row.default_symbol,
            "default_gate_level": int(row.default_gate_level),
            "max_trades_per_day": int(row.max_trades_per_day),
            "global_daily_entry_limit": int(row.global_daily_entry_limit),
            "per_symbol_daily_entry_limit": int(row.per_symbol_daily_entry_limit),
            "per_slot_new_entry_limit": int(row.per_slot_new_entry_limit),
            "max_open_positions": int(row.max_open_positions),
            "near_close_block_minutes": int(row.near_close_block_minutes),
            "same_direction_cooldown_minutes": int(row.same_direction_cooldown_minutes),
            "kis_live_auto_enabled": bool(row.kis_live_auto_enabled),
            "kis_live_auto_buy_enabled": bool(row.kis_live_auto_buy_enabled),
            "kis_live_auto_sell_enabled": bool(row.kis_live_auto_sell_enabled),
            "kis_live_auto_requires_manual_confirm": bool(
                row.kis_live_auto_requires_manual_confirm
            ),
            "kis_live_auto_max_orders_per_day": int(
                row.kis_live_auto_max_orders_per_day
            ),
            "kis_live_auto_max_notional_pct": float(
                row.kis_live_auto_max_notional_pct
            ),
            "kis_limited_auto_sell_enabled": bool(
                row.kis_limited_auto_sell_enabled
            ),
            "kis_limited_auto_stop_loss_enabled": bool(
                row.kis_limited_auto_stop_loss_enabled
            ),
            "kis_limited_auto_take_profit_enabled": bool(
                row.kis_limited_auto_take_profit_enabled
            ),
            "kis_limited_auto_sell_stop_loss_enabled": bool(
                row.kis_limited_auto_sell_stop_loss_enabled
            ),
            "kis_limited_auto_sell_take_profit_enabled": bool(
                row.kis_limited_auto_sell_take_profit_enabled
            ),
            "kis_limited_auto_sell_requires_queue_review": bool(
                row.kis_limited_auto_sell_requires_queue_review
            ),
            "kis_limited_auto_sell_max_orders_per_day": int(
                row.kis_limited_auto_sell_max_orders_per_day
            ),
            "kis_limited_auto_sell_max_notional_pct": float(
                row.kis_limited_auto_sell_max_notional_pct
            ),
            "kis_limited_auto_sell_min_shadow_occurrences": int(
                row.kis_limited_auto_sell_min_shadow_occurrences
            ),
            "kis_limited_auto_sell_allow_manual_review_trigger": bool(
                row.kis_limited_auto_sell_allow_manual_review_trigger
            ),
            "kis_limited_auto_sell_allow_take_profit_trigger": bool(
                row.kis_limited_auto_sell_allow_take_profit_trigger
            ),
            "kis_limited_auto_buy_enabled": bool(row.kis_limited_auto_buy_enabled),
            "kis_limited_auto_buy_readiness_enabled": bool(
                row.kis_limited_auto_buy_readiness_enabled
            ),
            "kis_limited_auto_buy_shadow_enabled": bool(
                row.kis_limited_auto_buy_shadow_enabled
            ),
            "kis_limited_auto_buy_requires_shadow_review": bool(
                row.kis_limited_auto_buy_requires_shadow_review
            ),
            "kis_limited_auto_buy_max_orders_per_day": int(
                row.kis_limited_auto_buy_max_orders_per_day
            ),
            "kis_limited_auto_buy_max_notional_pct": float(
                row.kis_limited_auto_buy_max_notional_pct
            ),
            "kis_limited_auto_buy_min_cash_buffer_krw": float(
                row.kis_limited_auto_buy_min_cash_buffer_krw
            ),
            "kis_limited_auto_buy_requires_existing_sell_guards": bool(
                row.kis_limited_auto_buy_requires_existing_sell_guards
            ),
            "kis_limited_auto_buy_min_final_score": float(
                row.kis_limited_auto_buy_min_final_score
            ),
            "kis_limited_auto_buy_min_confidence": float(
                row.kis_limited_auto_buy_min_confidence
            ),
            "kis_limited_auto_buy_max_positions": int(
                row.kis_limited_auto_buy_max_positions
            ),
            "kis_limited_auto_buy_block_if_position_exists": bool(
                row.kis_limited_auto_buy_block_if_position_exists
            ),
            "kis_limited_auto_buy_block_if_open_order_exists": bool(
                row.kis_limited_auto_buy_block_if_open_order_exists
            ),
            "kis_limited_auto_buy_allow_reentry_same_day": bool(
                row.kis_limited_auto_buy_allow_reentry_same_day
            ),
            "kis_limited_auto_buy_require_market_open": bool(
                row.kis_limited_auto_buy_require_market_open
            ),
            "kis_limited_auto_buy_no_new_entry_after": str(
                row.kis_limited_auto_buy_no_new_entry_after or "14:50"
            ),
            "kis_limited_auto_buy_allow_gpt_hard_block": bool(
                row.kis_limited_auto_buy_allow_gpt_hard_block
            ),
            "kis_scheduler_enabled": bool(row.kis_scheduler_enabled),
            "kis_scheduler_dry_run": bool(row.kis_scheduler_dry_run),
            "kis_scheduler_live_enabled": bool(row.kis_scheduler_live_enabled),
            "kis_scheduler_allow_real_orders": bool(
                row.kis_scheduler_allow_real_orders
            ),
            "kis_scheduler_configured_allow_real_orders": bool(
                row.kis_scheduler_configured_allow_real_orders
            ),
            "kis_scheduler_buy_enabled": bool(row.kis_scheduler_buy_enabled),
            "kis_scheduler_sell_enabled": bool(row.kis_scheduler_sell_enabled),
            "kis_scheduler_allow_limited_auto_buy": bool(
                row.kis_scheduler_allow_limited_auto_buy
            ),
            "kis_scheduler_allow_limited_auto_sell": bool(
                row.kis_scheduler_allow_limited_auto_sell
            ),
            "kis_scheduler_max_live_orders_per_day": int(
                row.kis_scheduler_max_live_orders_per_day
            ),
            "kis_scheduler_live_requires_dry_run_false": bool(
                row.kis_scheduler_live_requires_dry_run_false
            ),
            "kis_scheduler_live_respect_kill_switch": bool(
                row.kis_scheduler_live_respect_kill_switch
            ),
            "updated_at": row.updated_at,
        }
        return self._finalize_settings(settings)

    def _finalize_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        settings["trade_limits"] = self._trade_limits(settings)
        settings["kis_limited_auto_sell_requires_valid_cost_basis"] = True
        stop_loss_enabled = bool(
            settings["kis_limited_auto_stop_loss_enabled"]
            or settings["kis_limited_auto_sell_stop_loss_enabled"]
        )
        take_profit_enabled = bool(
            settings["kis_limited_auto_take_profit_enabled"]
            or settings["kis_limited_auto_sell_take_profit_enabled"]
        )
        settings["kis_limited_auto_stop_loss_enabled"] = stop_loss_enabled
        settings["kis_limited_auto_sell_stop_loss_enabled"] = stop_loss_enabled
        settings["kis_limited_auto_take_profit_enabled"] = take_profit_enabled
        settings["kis_limited_auto_sell_take_profit_enabled"] = take_profit_enabled
        settings["kis_limited_auto_take_profit_readiness_enabled"] = True
        settings["kis_limited_auto_sell_take_profit_readiness_enabled"] = True
        settings["kis_limited_auto_take_profit_requires_valid_cost_basis"] = True
        settings["kis_limited_auto_sell_take_profit_requires_valid_cost_basis"] = True
        settings["kis_limited_auto_take_profit_min_profit_pct"] = 0.03
        settings["kis_limited_auto_sell_take_profit_min_profit_pct"] = 0.03
        return settings

    def get_trade_limits_for_market(
        self,
        db: Session,
        *,
        market: str,
        broker: str,
    ) -> dict[str, Any]:
        settings = self.get_settings(db)
        normalized_market = str(market or "").strip().upper()
        limits = settings["trade_limits"].get(normalized_market)
        if limits is None:
            return {
                "market": normalized_market,
                "broker": str(broker or "").strip().lower(),
                "global_daily_entry_limit": settings["global_daily_entry_limit"],
                "per_symbol_daily_entry_limit": settings["per_symbol_daily_entry_limit"],
                "max_open_positions": settings["max_open_positions"],
                "same_direction_cooldown_minutes": settings[
                    "same_direction_cooldown_minutes"
                ],
                "source": "global_fallback",
            }
        return limits

    def get_kis_scheduler_runtime_state(self, db: Session) -> dict[str, Any]:
        settings = self.get_settings(db)
        return self._kis_scheduler_runtime_state(settings)

    def get_kis_scheduler_runtime_state_read_only(
        self,
        db: Session,
    ) -> dict[str, Any]:
        settings = self.get_settings_read_only(db)
        return self._kis_scheduler_runtime_state(settings)

    def get_kis_risk_summary_read_only(self, db: Session) -> dict[str, Any]:
        settings = self.get_settings_read_only(db)
        return self._kis_risk_summary(
            settings,
            daily_live_order_count=self._daily_kis_live_order_count(db),
        )

    def _kis_scheduler_runtime_state(self, settings: dict[str, Any]) -> dict[str, Any]:
        kis_enabled = bool(getattr(self.settings, "kis_enabled", False))
        kis_real_order_enabled = bool(
            getattr(self.settings, "kis_real_order_enabled", False)
        )
        scheduler_enabled = bool(settings["scheduler_enabled"])
        kis_scheduler_enabled = bool(settings["kis_scheduler_enabled"])
        kis_scheduler_dry_run = bool(settings["kis_scheduler_dry_run"])
        kis_scheduler_allow_real_orders = bool(
            settings["kis_scheduler_allow_real_orders"]
        )
        kis_scheduler_configured_allow_real_orders = bool(
            settings["kis_scheduler_configured_allow_real_orders"]
        )
        kis_scheduler_buy_enabled = bool(settings["kis_scheduler_buy_enabled"])
        kis_scheduler_sell_enabled = bool(settings["kis_scheduler_sell_enabled"])
        kis_scheduler_allow_limited_auto_buy = bool(
            settings["kis_scheduler_allow_limited_auto_buy"]
        )
        kis_scheduler_allow_limited_auto_sell = bool(
            settings["kis_scheduler_allow_limited_auto_sell"]
        )
        kis_scheduler_live_enabled = bool(settings["kis_scheduler_live_enabled"])
        kis_scheduler_max_live_orders_per_day = int(
            settings["kis_scheduler_max_live_orders_per_day"]
            or CONSERVATIVE_LIVE_ORDER_LIMIT
        )
        dry_run = bool(settings["dry_run"])
        kill_switch = bool(settings["kill_switch"])
        real_orders_allowed = (
            kis_scheduler_allow_real_orders
            and kis_scheduler_configured_allow_real_orders
            and kis_enabled
            and kis_real_order_enabled
            and not kis_scheduler_dry_run
            and not dry_run
            and not kill_switch
        )
        live_scheduler_ready = (
            kis_scheduler_live_enabled
            and scheduler_enabled
            and kis_scheduler_enabled
            and real_orders_allowed
            and (
                kis_scheduler_allow_limited_auto_buy
                or kis_scheduler_allow_limited_auto_sell
            )
        )
        return {
            "scheduler_enabled": scheduler_enabled,
            "kis_scheduler_enabled": kis_scheduler_enabled,
            "kis_scheduler_dry_run": kis_scheduler_dry_run,
            "kis_scheduler_allow_real_orders": kis_scheduler_allow_real_orders,
            "kis_scheduler_configured_allow_real_orders": (
                kis_scheduler_configured_allow_real_orders
            ),
            "kis_scheduler_buy_enabled": kis_scheduler_buy_enabled,
            "kis_scheduler_sell_enabled": kis_scheduler_sell_enabled,
            "kis_scheduler_allow_limited_auto_buy": kis_scheduler_allow_limited_auto_buy,
            "kis_scheduler_allow_limited_auto_sell": kis_scheduler_allow_limited_auto_sell,
            "kis_scheduler_max_live_orders_per_day": kis_scheduler_max_live_orders_per_day,
            "kis_scheduler_live_enabled": kis_scheduler_live_enabled,
            "kis_scheduler_live_requires_dry_run_false": bool(
                settings["kis_scheduler_live_requires_dry_run_false"]
            ),
            "kis_scheduler_live_respect_kill_switch": bool(
                settings["kis_scheduler_live_respect_kill_switch"]
            ),
            "dry_run": dry_run,
            "kill_switch": kill_switch,
            "kis_enabled": kis_enabled,
            "kis_real_order_enabled": kis_real_order_enabled,
            "real_orders_allowed": real_orders_allowed,
            "live_scheduler_ready": live_scheduler_ready,
            "real_order_scheduler_enabled": live_scheduler_ready,
        }

    def _kis_risk_summary(
        self,
        settings: dict[str, Any],
        *,
        daily_live_order_count: int | None,
    ) -> dict[str, Any]:
        dry_run = bool(settings["dry_run"])
        kill_switch = bool(settings["kill_switch"])
        scheduler_enabled = bool(settings["scheduler_enabled"])
        kis_scheduler_enabled = bool(settings["kis_scheduler_enabled"])
        kis_scheduler_dry_run = bool(settings["kis_scheduler_dry_run"])
        kis_scheduler_live_enabled = bool(settings["kis_scheduler_live_enabled"])
        allow_real_orders = bool(settings["kis_scheduler_allow_real_orders"])
        configured_allow_real_orders = bool(
            settings["kis_scheduler_configured_allow_real_orders"]
        )
        scheduler_sell_enabled = bool(settings["kis_scheduler_sell_enabled"])
        scheduler_allow_limited_auto_sell = bool(
            settings["kis_scheduler_allow_limited_auto_sell"]
        )
        live_auto_sell_enabled = bool(settings["kis_live_auto_sell_enabled"])
        limited_auto_sell_enabled = bool(settings["kis_limited_auto_sell_enabled"])
        stop_loss_enabled = bool(
            settings["kis_limited_auto_stop_loss_enabled"]
            or settings["kis_limited_auto_sell_stop_loss_enabled"]
        )
        take_profit_enabled = bool(
            settings["kis_limited_auto_take_profit_enabled"]
            or settings["kis_limited_auto_sell_take_profit_enabled"]
        )
        sell_gate_enabled = bool(stop_loss_enabled or take_profit_enabled)

        buy_flags = {
            name: bool(settings.get(name, False)) for name in KIS_BUY_EXECUTION_FLAGS
        }
        enabled_buy_flags = [name for name, enabled in buy_flags.items() if enabled]
        buy_gate_enabled = bool(enabled_buy_flags)

        scheduler_live_requested = bool(
            kis_scheduler_live_enabled
            or allow_real_orders
            or configured_allow_real_orders
            or scheduler_sell_enabled
            or scheduler_allow_limited_auto_sell
            or bool(settings["kis_scheduler_buy_enabled"])
            or bool(settings["kis_scheduler_allow_limited_auto_buy"])
        )
        live_requested = bool(
            scheduler_live_requested
            or live_auto_sell_enabled
            or limited_auto_sell_enabled
            or buy_gate_enabled
        )
        scheduler_path_enabled = bool(
            scheduler_enabled and kis_scheduler_enabled and kis_scheduler_live_enabled
        )
        sell_execution_configured = bool(
            scheduler_path_enabled
            and scheduler_sell_enabled
            and scheduler_allow_limited_auto_sell
            and live_auto_sell_enabled
            and sell_gate_enabled
        )
        kis_enabled = bool(getattr(self.settings, "kis_enabled", False))
        kis_real_order_enabled = bool(
            getattr(self.settings, "kis_real_order_enabled", False)
        )
        real_order_prereqs_met = bool(
            allow_real_orders
            and configured_allow_real_orders
            and not kis_scheduler_dry_run
            and not dry_run
            and not kill_switch
            and kis_enabled
            and kis_real_order_enabled
        )
        live_sell_armed = bool(sell_execution_configured and real_order_prereqs_met)
        live_buy_armed = bool(
            buy_gate_enabled and not dry_run and not kill_switch and kis_enabled
        )
        sell_only_mode = bool(sell_execution_configured and not buy_gate_enabled)

        daily_live_order_limit = max(
            0,
            int(
                settings["kis_scheduler_max_live_orders_per_day"]
                or CONSERVATIVE_LIVE_ORDER_LIMIT
            ),
        )
        daily_live_order_remaining = (
            max(0, daily_live_order_limit - daily_live_order_count)
            if daily_live_order_count is not None
            else None
        )
        max_notional_pct = float(
            settings["kis_limited_auto_sell_max_notional_pct"]
            or CONSERVATIVE_MAX_NOTIONAL_PCT
        )

        risky_flags: list[str] = list(enabled_buy_flags)
        if (
            kis_scheduler_live_enabled
            and (bool(settings["kis_scheduler_buy_enabled"]) or buy_gate_enabled)
        ):
            risky_flags.append("scheduler_live_with_buy_execution_enabled")
        if daily_live_order_limit > CONSERVATIVE_LIVE_ORDER_LIMIT:
            risky_flags.append("kis_scheduler_max_live_orders_per_day_high")
        if (
            int(settings["kis_limited_auto_sell_max_orders_per_day"] or 0)
            > CONSERVATIVE_LIVE_ORDER_LIMIT
        ):
            risky_flags.append("kis_limited_auto_sell_max_orders_per_day_high")
        if (
            int(settings["kis_live_auto_max_orders_per_day"] or 0)
            > CONSERVATIVE_LIVE_ORDER_LIMIT
        ):
            risky_flags.append("kis_live_auto_max_orders_per_day_high")
        if (
            float(settings["kis_limited_auto_sell_max_notional_pct"] or 0)
            > CONSERVATIVE_MAX_NOTIONAL_PCT
        ):
            risky_flags.append("kis_limited_auto_sell_max_notional_pct_high")
        if (
            float(settings["kis_live_auto_max_notional_pct"] or 0)
            > CONSERVATIVE_MAX_NOTIONAL_PCT
        ):
            risky_flags.append("kis_live_auto_max_notional_pct_high")
        risky_flags = _dedupe(risky_flags)

        blocking_flags: list[str] = []
        if live_requested:
            if dry_run:
                blocking_flags.append("dry_run_true")
            if scheduler_live_requested and kis_scheduler_dry_run:
                blocking_flags.append("kis_scheduler_dry_run_true")
            if kill_switch:
                blocking_flags.append("kill_switch_enabled")
            if scheduler_live_requested and not scheduler_enabled:
                blocking_flags.append("runtime_scheduler_disabled")
            if scheduler_live_requested and not kis_scheduler_enabled:
                blocking_flags.append("kis_scheduler_disabled")
            if scheduler_live_requested and not allow_real_orders:
                blocking_flags.append("kis_scheduler_allow_real_orders_false")
            if scheduler_live_requested and not configured_allow_real_orders:
                blocking_flags.append("configured_allow_real_orders_false")
            if scheduler_live_requested and not kis_enabled:
                blocking_flags.append("kis_disabled")
            if scheduler_live_requested and not kis_real_order_enabled:
                blocking_flags.append("kis_real_order_disabled")
        blocking_flags = _dedupe(blocking_flags)

        all_live_flags_off = not any(
            [
                kis_scheduler_live_enabled,
                allow_real_orders,
                configured_allow_real_orders,
                scheduler_sell_enabled,
                scheduler_allow_limited_auto_sell,
                live_auto_sell_enabled,
                limited_auto_sell_enabled,
                stop_loss_enabled,
                take_profit_enabled,
                buy_gate_enabled,
            ]
        )
        safe_mode_active = bool(dry_run and all_live_flags_off)
        if blocking_flags:
            warning_level = "blocked"
        elif buy_gate_enabled:
            warning_level = "dangerous_mixed"
        elif live_sell_armed and sell_only_mode:
            warning_level = "armed_sell_only"
        else:
            warning_level = "safe"

        return {
            "live_sell_armed": live_sell_armed,
            "live_buy_armed": live_buy_armed,
            "sell_only_mode": sell_only_mode,
            "daily_live_order_limit": daily_live_order_limit,
            "daily_live_order_remaining": daily_live_order_remaining,
            "max_notional_pct": max_notional_pct,
            "dry_run": dry_run,
            "kill_switch": kill_switch,
            "safe_mode_active": safe_mode_active,
            "risky_flags": risky_flags,
            "blocking_flags": blocking_flags,
            "warning_level": warning_level,
            "sell_gate_enabled": sell_gate_enabled,
            "buy_gate_enabled": buy_gate_enabled,
        }

    def _daily_kis_live_order_count(self, db: Session) -> int:
        start_utc, end_utc = _kr_day_bounds_utc(datetime.now(UTC))
        submitted_statuses = [
            "SUBMITTED",
            "ACCEPTED",
            "PENDING",
            "PARTIALLY_FILLED",
            "FILLED",
        ]
        return int(
            db.query(OrderLog)
            .filter(OrderLog.broker == "kis")
            .filter(OrderLog.created_at >= start_utc)
            .filter(OrderLog.created_at < end_utc)
            .filter(OrderLog.internal_status.in_(submitted_statuses))
            .filter(
                or_(
                    OrderLog.request_payload.like("%limited_auto_buy%"),
                    OrderLog.request_payload.like("%limited_auto_sell%"),
                    OrderLog.request_payload.like("%kis_limited_auto%"),
                    OrderLog.response_payload.like("%limited_auto_buy%"),
                    OrderLog.response_payload.like("%limited_auto_sell%"),
                    OrderLog.response_payload.like("%kis_limited_auto%"),
                )
            )
            .count()
            or 0
        )

    def _trade_limits(self, settings: dict[str, Any]) -> dict[str, Any]:
        base = {
            "global_daily_entry_limit": settings["global_daily_entry_limit"],
            "per_symbol_daily_entry_limit": settings["per_symbol_daily_entry_limit"],
            "max_open_positions": settings["max_open_positions"],
            "same_direction_cooldown_minutes": settings[
                "same_direction_cooldown_minutes"
            ],
            "source": "global_fallback",
        }
        return {
            "US": {
                **base,
                "market": "US",
                "broker": "alpaca",
            },
            "KR": {
                **base,
                "market": "KR",
                "broker": "kis",
                "manual_order_qty_cap": int(
                    getattr(self.settings, "kis_max_manual_order_qty", 1)
                ),
                "manual_order_amount_cap_krw": int(
                    getattr(self.settings, "kis_max_manual_order_amount_krw", 100000)
                ),
            },
        }

    def update_settings(self, db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        row = self.get_or_create(db)
        _sync_bool_alias(
            payload,
            "kis_limited_auto_stop_loss_enabled",
            "kis_limited_auto_sell_stop_loss_enabled",
        )
        _sync_bool_alias(
            payload,
            "kis_limited_auto_take_profit_enabled",
            "kis_limited_auto_sell_take_profit_enabled",
        )

        for key in (
            "bot_enabled",
            "dry_run",
            "kill_switch",
            "scheduler_enabled",
            "default_symbol",
            "default_gate_level",
            "max_trades_per_day",
            "global_daily_entry_limit",
            "per_symbol_daily_entry_limit",
            "per_slot_new_entry_limit",
            "max_open_positions",
            "near_close_block_minutes",
            "same_direction_cooldown_minutes",
            "kis_live_auto_enabled",
            "kis_live_auto_buy_enabled",
            "kis_live_auto_sell_enabled",
            "kis_live_auto_requires_manual_confirm",
            "kis_live_auto_max_orders_per_day",
            "kis_live_auto_max_notional_pct",
            "kis_limited_auto_sell_enabled",
            "kis_limited_auto_stop_loss_enabled",
            "kis_limited_auto_take_profit_enabled",
            "kis_limited_auto_sell_stop_loss_enabled",
            "kis_limited_auto_sell_take_profit_enabled",
            "kis_limited_auto_sell_requires_queue_review",
            "kis_limited_auto_sell_max_orders_per_day",
            "kis_limited_auto_sell_max_notional_pct",
            "kis_limited_auto_sell_min_shadow_occurrences",
            "kis_limited_auto_sell_allow_manual_review_trigger",
            "kis_limited_auto_sell_allow_take_profit_trigger",
            "kis_limited_auto_buy_enabled",
            "kis_limited_auto_buy_readiness_enabled",
            "kis_limited_auto_buy_shadow_enabled",
            "kis_limited_auto_buy_requires_shadow_review",
            "kis_limited_auto_buy_max_orders_per_day",
            "kis_limited_auto_buy_max_notional_pct",
            "kis_limited_auto_buy_min_cash_buffer_krw",
            "kis_limited_auto_buy_requires_existing_sell_guards",
            "kis_limited_auto_buy_min_final_score",
            "kis_limited_auto_buy_min_confidence",
            "kis_limited_auto_buy_max_positions",
            "kis_limited_auto_buy_block_if_position_exists",
            "kis_limited_auto_buy_block_if_open_order_exists",
            "kis_limited_auto_buy_allow_reentry_same_day",
            "kis_limited_auto_buy_require_market_open",
            "kis_limited_auto_buy_no_new_entry_after",
            "kis_limited_auto_buy_allow_gpt_hard_block",
            "kis_scheduler_enabled",
            "kis_scheduler_dry_run",
            "kis_scheduler_live_enabled",
            "kis_scheduler_allow_real_orders",
            "kis_scheduler_configured_allow_real_orders",
            "kis_scheduler_buy_enabled",
            "kis_scheduler_sell_enabled",
            "kis_scheduler_allow_limited_auto_buy",
            "kis_scheduler_allow_limited_auto_sell",
            "kis_scheduler_max_live_orders_per_day",
            "kis_scheduler_live_requires_dry_run_false",
            "kis_scheduler_live_respect_kill_switch",
        ):
            if key not in payload:
                continue

            value = payload[key]
            if key == "default_symbol" and value:
                value = str(value).upper()
            setattr(row, key, value)

        db.commit()
        db.refresh(row)
        return self.get_settings(db)

    def set_bot_enabled(self, db: Session, enabled: bool) -> dict[str, Any]:
        return self.update_settings(db, {"bot_enabled": enabled})

    def set_kill_switch(self, db: Session, enabled: bool) -> dict[str, Any]:
        return self.update_settings(db, {"kill_switch": enabled})

    def set_scheduler_enabled(self, db: Session, enabled: bool) -> dict[str, Any]:
        return self.update_settings(db, {"scheduler_enabled": enabled})


def _sync_bool_alias(payload: dict[str, Any], primary: str, alias: str) -> None:
    primary_set = primary in payload
    alias_set = alias in payload
    if not primary_set and not alias_set:
        return

    value = payload[primary] if primary_set else payload[alias]
    payload[primary] = bool(value)
    payload[alias] = bool(value)


def _kr_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    local = now_utc.astimezone(KR_TZ)
    start_local = datetime.combine(local.date(), time.min, tzinfo=KR_TZ)
    end_local = start_local + timedelta(days=1)
    return _naive_utc(start_local), _naive_utc(end_local)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(UTC)
    return value.replace(tzinfo=None)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
