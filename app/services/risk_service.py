from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.brokers.alpaca_client import AlpacaClient
from app.core.constants import (
    BLOCK_NEAR_MARKET_CLOSE_DEFAULT,
    DECENT_SETUP_POSITION_PCT,
    KILL_SWITCH_DEFAULT,
    MAX_DAILY_LOSS_PCT,
    MAX_POSITION_EQUITY_PCT,
    MAX_TRADES_PER_DAY,
    NEAR_CLOSE_MINUTES,
    STRONG_SETUP_POSITION_PCT,
    WEAK_SETUP_POSITION_PCT,
)
from app.db.models import OrderLog


class RiskService:
    def __init__(self):
        self.broker = AlpacaClient()

    @staticmethod
    def _position_size_pct(final_buy_score: float) -> float:
        if final_buy_score >= 80:
            return STRONG_SETUP_POSITION_PCT
        if final_buy_score >= 70:
            return DECENT_SETUP_POSITION_PCT
        return WEAK_SETUP_POSITION_PCT

    @staticmethod
    def _is_near_market_close(now_utc: datetime) -> bool:
        # US equities close at 20:00 UTC during DST, 21:00 UTC during standard time.
        close_candidates = [(20, 0), (21, 0)]
        for hour, minute in close_candidates:
            close_dt = now_utc.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if close_dt - timedelta(minutes=NEAR_CLOSE_MINUTES) <= now_utc <= close_dt:
                return True
        return False

    def _estimated_daily_pnl(self, db: Session, symbol: str, day_start_utc: datetime) -> float:
        orders = (
            db.query(OrderLog)
            .filter(OrderLog.symbol == symbol)
            .filter(OrderLog.created_at >= day_start_utc)
            .all()
        )
        pnl = 0.0
        for order in orders:
            qty = float(order.filled_qty or order.qty or 0)
            px = float(order.filled_avg_price or 0)
            if qty <= 0 or px <= 0:
                continue
            notional = qty * px
            if order.side == "sell":
                pnl += notional
            elif order.side == "buy":
                pnl -= notional
        return pnl

    def evaluate(
        self,
        db: Session,
        *,
        symbol: str,
        action: str,
        final_buy_score: float,
    ) -> dict:
        flags: list[str] = []

        if action != "buy":
            flags.append("only_buy_execution_supported")

        if KILL_SWITCH_DEFAULT:
            flags.append("kill_switch_active")

        now = datetime.now(timezone.utc)
        if BLOCK_NEAR_MARKET_CLOSE_DEFAULT and self._is_near_market_close(now):
            flags.append("near_market_close_block")

        day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        daily_count = (
            db.query(OrderLog)
            .filter(OrderLog.symbol == symbol)
            .filter(OrderLog.created_at >= day_start)
            .count()
        )
        if daily_count >= MAX_TRADES_PER_DAY:
            flags.append("max_trades_per_day_reached")

        open_position = self.broker.get_position(symbol)
        if open_position is not None:
            flags.append("open_position_exists")

        same_direction_reentry = (
            db.query(OrderLog)
            .filter(OrderLog.symbol == symbol)
            .filter(OrderLog.side == "buy")
            .filter(OrderLog.created_at >= day_start)
            .count()
        )
        if same_direction_reentry > 0:
            flags.append("same_day_buy_reentry_blocked")

        account = self.broker.get_account()
        equity = float(account.equity)
        est_daily_pnl = self._estimated_daily_pnl(db, symbol, day_start)
        if est_daily_pnl <= -(equity * MAX_DAILY_LOSS_PCT):
            flags.append("daily_loss_limit_hit")

        approved = len(flags) == 0
        size_pct = min(self._position_size_pct(final_buy_score), MAX_POSITION_EQUITY_PCT) if approved else 0.0

        return {
            "approved": approved,
            "risk_flags": flags,
            "position_size_pct": round(size_pct, 4),
            "stop_loss_pct": 0.015 if approved else 0.0,
            "take_profit_pct": 0.03 if approved else 0.0,
            "daily_trade_count": daily_count,
            "estimated_daily_pnl": round(est_daily_pnl, 2),
        }
