from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.brokers.alpaca_client import AlpacaClient
from app.core.constants import (
    BLOCK_NEAR_MARKET_CLOSE_DEFAULT,
    DECENT_SETUP_POSITION_PCT,
    KILL_SWITCH_DEFAULT,
    MAX_DAILY_LOSS_PCT,
    MAX_POSITION_EQUITY_PCT,
    NEAR_CLOSE_MINUTES,
    STRONG_SETUP_POSITION_PCT,
    WEAK_SETUP_POSITION_PCT,
)
from app.db.models import OrderLog
from app.services.runtime_setting_service import RuntimeSettingService

ALPACA_ORDER_BROKERS = ("alpaca", "alpaca_paper")


class RiskService:
    def __init__(self):
        self.broker = AlpacaClient()
        self.runtime_settings = RuntimeSettingService()

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

    @staticmethod
    def _broker_scoped_query(query, broker: str):
        normalized = str(broker or "").strip().lower()
        if normalized == "alpaca":
            return query.filter(OrderLog.broker.in_(ALPACA_ORDER_BROKERS))
        return query.filter(OrderLog.broker == normalized)

    def _daily_entry_count(
        self,
        db: Session,
        *,
        broker: str,
        day_start_utc: datetime,
        symbol: str | None = None,
    ) -> int:
        query = (
            db.query(OrderLog)
            .filter(OrderLog.side == "buy")
            .filter(OrderLog.created_at >= day_start_utc)
        )
        query = self._broker_scoped_query(query, broker)
        if symbol:
            query = query.filter(OrderLog.symbol == symbol.upper())
        return query.count()

    def _estimated_daily_pnl(
        self,
        db: Session,
        symbol: str,
        day_start_utc: datetime,
        *,
        broker: str,
    ) -> float:
        orders = (
            self._broker_scoped_query(db.query(OrderLog), broker)
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

        broker = "alpaca"
        day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        runtime_settings = self.runtime_settings.get_settings(db)
        global_daily_entry_limit = max(0, int(runtime_settings["global_daily_entry_limit"]))
        per_symbol_daily_entry_limit = max(0, int(runtime_settings["per_symbol_daily_entry_limit"]))
        
        daily_count = self._daily_entry_count(
            db,
            broker=broker,
            day_start_utc=day_start,
        )
        if daily_count >= global_daily_entry_limit:
            flags.append("global_daily_entry_limit_reached")

        open_position = self.broker.get_position(symbol)
        if open_position is not None:
            flags.append("open_position_exists")

        same_direction_reentry = self._daily_entry_count(
            db,
            broker=broker,
            day_start_utc=day_start,
            symbol=symbol,
        )
        if same_direction_reentry >= per_symbol_daily_entry_limit:
            flags.append("per_symbol_daily_entry_limit_reached")

        account = self.broker.get_account()
        equity = float(account.equity)
        est_daily_pnl = self._estimated_daily_pnl(
            db,
            symbol,
            day_start,
            broker=broker,
        )
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
            "broker": broker,
            "market": "US",
        }

    def evaluate_exit(
        self,
        *,
        position,
        final_sell_score: float,
        final_buy_score: float,
    ) -> dict:
        reasons: list[str] = []

        try:
            unrealized_plpc = float(getattr(position, "unrealized_plpc", 0) or 0)
        except Exception:
            unrealized_plpc = 0.0

        # Conservative first-pass exits:
        # 1) protect downside
        # 2) lock obvious gains
        # 3) confirm weakening trend/momentum
        if unrealized_plpc <= -0.015:
            reasons.append("stop_loss_triggered")
        if unrealized_plpc >= 0.03:
            reasons.append("take_profit_triggered")

        sell_dominance = float(final_sell_score or 0) - float(final_buy_score or 0)
        if float(final_sell_score or 0) >= 68.0 and sell_dominance >= 10.0:
            reasons.append("trend_breakdown_confirmed")

        return {
            "should_exit": len(reasons) > 0,
            "reasons": reasons,
            "unrealized_plpc": unrealized_plpc,
        }
