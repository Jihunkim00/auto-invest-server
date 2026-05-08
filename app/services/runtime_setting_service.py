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
            "updated_at": row.updated_at,
        }
        settings["trade_limits"] = self._trade_limits(settings)
        settings["kis_scheduler_enabled"] = bool(
            getattr(self.settings, "kis_scheduler_enabled", False)
        )
        settings["kis_scheduler_dry_run"] = bool(
            getattr(self.settings, "kis_scheduler_dry_run", True)
        )
        settings["kis_scheduler_allow_real_orders"] = bool(
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
