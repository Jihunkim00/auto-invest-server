from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.constants import DEFAULT_GATE_LEVEL, MAX_TRADES_PER_DAY, NEAR_CLOSE_MINUTES
from app.db.models import RuntimeSetting


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
            "kis_limited_auto_sell_stop_loss_enabled": False,
            "kis_limited_auto_sell_take_profit_enabled": False,
            "kis_limited_auto_sell_requires_queue_review": True,
            "kis_limited_auto_sell_max_orders_per_day": 1,
            "kis_limited_auto_sell_max_notional_pct": 0.03,
            "kis_limited_auto_sell_min_shadow_occurrences": 1,
            "kis_limited_auto_sell_allow_manual_review_trigger": False,
            "kis_limited_auto_sell_allow_take_profit_trigger": False,
            "kis_limited_auto_buy_enabled": False,
            "kis_limited_auto_buy_shadow_enabled": True,
            "kis_limited_auto_buy_requires_shadow_review": True,
            "kis_limited_auto_buy_max_orders_per_day": 1,
            "kis_limited_auto_buy_max_notional_pct": 0.03,
            "kis_limited_auto_buy_min_final_score": 75.0,
            "kis_limited_auto_buy_min_confidence": 0.70,
            "kis_limited_auto_buy_max_positions": 3,
            "kis_limited_auto_buy_block_if_position_exists": True,
            "kis_limited_auto_buy_block_if_open_order_exists": True,
            "kis_limited_auto_buy_allow_reentry_same_day": False,
            "kis_limited_auto_buy_require_market_open": True,
            "kis_limited_auto_buy_no_new_entry_after": "14:50",
            "kis_limited_auto_buy_allow_gpt_hard_block": False,
            "kis_scheduler_live_enabled": False,
            "kis_scheduler_allow_real_orders": False,
            "kis_scheduler_allow_limited_auto_buy": False,
            "kis_scheduler_allow_limited_auto_sell": False,
            "kis_scheduler_max_live_orders_per_day": 2,
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
            "kis_scheduler_live_enabled": bool(row.kis_scheduler_live_enabled),
            "kis_scheduler_allow_real_orders": bool(
                row.kis_scheduler_allow_real_orders
            ),
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
        settings["trade_limits"] = self._trade_limits(settings)
        settings["kis_scheduler_enabled"] = bool(
            getattr(self.settings, "kis_scheduler_enabled", False)
        )
        settings["kis_scheduler_dry_run"] = bool(
            getattr(self.settings, "kis_scheduler_dry_run", True)
        )
        settings["kis_scheduler_configured_allow_real_orders"] = bool(
            getattr(self.settings, "kis_scheduler_allow_real_orders", False)
        )
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
            "kis_limited_auto_sell_stop_loss_enabled",
            "kis_limited_auto_sell_take_profit_enabled",
            "kis_limited_auto_sell_requires_queue_review",
            "kis_limited_auto_sell_max_orders_per_day",
            "kis_limited_auto_sell_max_notional_pct",
            "kis_limited_auto_sell_min_shadow_occurrences",
            "kis_limited_auto_sell_allow_manual_review_trigger",
            "kis_limited_auto_sell_allow_take_profit_trigger",
            "kis_limited_auto_buy_enabled",
            "kis_limited_auto_buy_shadow_enabled",
            "kis_limited_auto_buy_requires_shadow_review",
            "kis_limited_auto_buy_max_orders_per_day",
            "kis_limited_auto_buy_max_notional_pct",
            "kis_limited_auto_buy_min_final_score",
            "kis_limited_auto_buy_min_confidence",
            "kis_limited_auto_buy_max_positions",
            "kis_limited_auto_buy_block_if_position_exists",
            "kis_limited_auto_buy_block_if_open_order_exists",
            "kis_limited_auto_buy_allow_reentry_same_day",
            "kis_limited_auto_buy_require_market_open",
            "kis_limited_auto_buy_no_new_entry_after",
            "kis_limited_auto_buy_allow_gpt_hard_block",
            "kis_scheduler_live_enabled",
            "kis_scheduler_allow_real_orders",
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
