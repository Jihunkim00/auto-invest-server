from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, SignalLog
from app.services.order_sync_service import OrderSyncService
from app.services.runtime_setting_service import RuntimeSettingService

NY_TZ = ZoneInfo("America/New_York")


class ExecutionGuardService:
    def __init__(self):
        self.runtime_settings = RuntimeSettingService()
        self.order_sync = OrderSyncService()

    def precheck(self, db: Session, symbol: str, *, enforce_entry_limits: bool = True) -> dict:
        settings = self.runtime_settings.get_settings(db)
        symbol = symbol.upper()

        if not settings["bot_enabled"]:
            return self._blocked("precheck", "skipped", "bot_disabled", settings)

        if settings["kill_switch"]:
            return self._blocked("precheck", "rejected", "kill_switch_enabled", settings)

        if enforce_entry_limits:
            global_daily_entry_limit = max(0, int(settings["global_daily_entry_limit"]))
            if self._daily_entry_count(db) >= global_daily_entry_limit:
                return self._blocked("precheck", "skipped", "global_daily_entry_limit_reached", settings)

            per_symbol_daily_entry_limit = max(0, int(settings["per_symbol_daily_entry_limit"]))
            if self._daily_entry_count(db, symbol=symbol) >= per_symbol_daily_entry_limit:
                return self._blocked("precheck", "skipped", "per_symbol_daily_entry_limit_reached", settings)

        self.order_sync.sync_open_orders_for_symbol(db, symbol)
        if self.order_sync.has_conflicting_open_order(db, symbol):
            return self._blocked("precheck", "skipped", "conflicting_open_order_exists", settings)

        return {
            "allowed": True,
            "stage": "precheck",
            "result": "passed",
            "reason": "precheck_passed",
            "settings": settings,
        }

    def action_check(self, db: Session, symbol: str, action: str) -> dict:
        settings = self.runtime_settings.get_settings(db)
        symbol = symbol.upper()
        action = (action or "").lower()

        if action != "buy":
            return {
                "allowed": True,
                "stage": "precheck",
                "result": "passed",
                "reason": "action_guard_not_applicable",
                "settings": settings,
            }

        if self._is_near_close_blocked(settings["near_close_block_minutes"]):
            return self._blocked("precheck", "skipped", "near_market_close_entry_block", settings)

        cooldown_minutes = int(settings["same_direction_cooldown_minutes"])
        if cooldown_minutes > 0:
            cutoff = datetime.utcnow() - timedelta(minutes=cooldown_minutes)
            recent_buy = (
                db.query(SignalLog)
                .filter(
                    SignalLog.symbol == symbol,
                    SignalLog.signal_status == "executed",
                    SignalLog.action == "buy",
                    SignalLog.created_at >= cutoff,
                )
                .order_by(SignalLog.created_at.desc())
                .first()
            )
            if recent_buy:
                return self._blocked("precheck", "skipped", "same_direction_cooldown_active", settings)
            
        if self._daily_entry_count(db) >= max(0, int(settings["global_daily_entry_limit"])):
            return self._blocked("precheck", "skipped", "global_daily_entry_limit_reached", settings)

        if self._daily_entry_count(db, symbol=symbol) >= max(0, int(settings["per_symbol_daily_entry_limit"])):
            return self._blocked("precheck", "skipped", "per_symbol_daily_entry_limit_reached", settings)


        return {
            "allowed": True,
            "stage": "precheck",
            "result": "passed",
            "reason": "action_guard_passed",
            "settings": settings,
        }

    def _daily_entry_count(self, db: Session, symbol: str | None = None) -> int:
        start_utc, end_utc = self._day_bounds_utc()

        query = db.query(OrderLog).filter(
            OrderLog.side == "buy",
            OrderLog.created_at >= start_utc,
            OrderLog.created_at < end_utc,
            or_(
                OrderLog.internal_status == InternalOrderStatus.FILLED.value,
                OrderLog.internal_status == InternalOrderStatus.PARTIALLY_FILLED.value,
                OrderLog.broker_status.in_(["filled", "partially_filled", "partial_fill"]),
            ),
        )

        if symbol:
            query = query.filter(OrderLog.symbol == symbol.upper())

        return query.count()

    def _day_bounds_utc(self) -> tuple[datetime, datetime]:
        now_ny = datetime.now(NY_TZ)
        start_ny = now_ny.replace(hour=0, minute=0, second=0, microsecond=0)
        end_ny = start_ny + timedelta(days=1)
        start_utc = start_ny.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        end_utc = end_ny.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        return start_utc, end_utc

    def _is_near_close_blocked(self, near_close_block_minutes: int) -> bool:
        now_ny = datetime.now(NY_TZ)
        close_ny = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
        open_ny = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)

        if now_ny < open_ny or now_ny > close_ny:
            return True

        return now_ny >= close_ny - timedelta(minutes=max(0, int(near_close_block_minutes)))

    def _blocked(self, stage: str, result: str, reason: str, settings: dict) -> dict:
        return {
            "allowed": False,
            "stage": stage,
            "result": result,
            "reason": reason,
            "settings": settings,
        }