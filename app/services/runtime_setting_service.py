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
            "kill_switch": False,
            "default_symbol": self.settings.default_symbol.upper(),
            "default_gate_level": DEFAULT_GATE_LEVEL,
            "max_trades_per_day": MAX_TRADES_PER_DAY,
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
        return {
            "bot_enabled": bool(row.bot_enabled),
            "kill_switch": bool(row.kill_switch),
            "default_symbol": row.default_symbol,
            "default_gate_level": int(row.default_gate_level),
            "max_trades_per_day": int(row.max_trades_per_day),
            "near_close_block_minutes": int(row.near_close_block_minutes),
            "same_direction_cooldown_minutes": int(row.same_direction_cooldown_minutes),
            "updated_at": row.updated_at,
        }

    def update_settings(self, db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        row = self.get_or_create(db)

        for key in (
            "bot_enabled",
            "kill_switch",
            "default_symbol",
            "default_gate_level",
            "max_trades_per_day",
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