import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.constants import (
    BLOCK_NEAR_MARKET_CLOSE_DEFAULT,
    KILL_SWITCH_DEFAULT,
    MAX_TRADES_PER_DAY,
    MIN_CONFIDENCE_TO_TRADE,
)
from app.db.models import OrderLog


class RiskService:
    def evaluate(self, db: Session, *, symbol: str, action: str, confidence: float) -> dict:
        flags: list[str] = []

        if KILL_SWITCH_DEFAULT:
            flags.append("kill_switch_active")

        now = datetime.now(timezone.utc)
        if BLOCK_NEAR_MARKET_CLOSE_DEFAULT and now.hour == 19 and now.minute >= 45:
            flags.append("near_market_close_block")

        if confidence < MIN_CONFIDENCE_TO_TRADE and action in ("buy", "sell"):
            flags.append("confidence_below_threshold")

        today = now.date()
        daily_count = (
            db.query(OrderLog)
            .filter(OrderLog.symbol == symbol)
            .filter(OrderLog.created_at >= datetime(today.year, today.month, today.day, tzinfo=timezone.utc))
            .count()
        )

        if daily_count >= MAX_TRADES_PER_DAY:
            flags.append("max_trades_per_day_reached")

        # placeholder flags for next stage
        flags.append("daily_loss_guard_placeholder")

        approved = len([f for f in flags if not f.endswith("_placeholder")]) == 0
        return {
            "approved": approved,
            "risk_flags": json.dumps(flags, ensure_ascii=False),
        }