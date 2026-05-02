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
from app.services.event_risk_service import EventRiskService
from app.services.runtime_setting_service import RuntimeSettingService

ALPACA_ORDER_BROKERS = ("alpaca", "alpaca_paper")


class RiskService:
    def __init__(self):
        self.broker = AlpacaClient()
        self.runtime_settings = RuntimeSettingService()
        self.event_risk_service = EventRiskService()

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
        market: str = "US",
        event_risk: dict | None = None,
    ) -> dict:
        flags: list[str] = []
        non_blocking_flags: list[str] = []
        warnings: list[str] = []
        block_reasons: list[str] = []
        event_position_size_multiplier = 1.0

        if action != "buy":
            flags.append("only_buy_execution_supported")

        if KILL_SWITCH_DEFAULT:
            flags.append("kill_switch_active")

        now = datetime.now(timezone.utc)
        if BLOCK_NEAR_MARKET_CLOSE_DEFAULT and self._is_near_market_close(now):
            flags.append("near_market_close_block")

        broker = "alpaca"
        normalized_market = str(market or "US").strip().upper()
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

        resolved_event_risk = event_risk
        if resolved_event_risk is None and action == "buy":
            try:
                resolved_event_risk = self.event_risk_service.get_event_risk(
                    db,
                    symbol=symbol,
                    market=normalized_market,
                    intent="entry",
                )
            except Exception:
                resolved_event_risk = {
                    "symbol": symbol,
                    "market": normalized_market,
                    "has_near_event": False,
                    "entry_blocked": False,
                    "scale_in_blocked": False,
                    "position_size_multiplier": 1.0,
                    "warnings": ["event_data_unavailable"],
                }

        if action == "buy" and resolved_event_risk:
            warnings.extend(_string_list(resolved_event_risk.get("warnings")))
            if resolved_event_risk.get("entry_blocked") is True:
                flags.append("event_risk_entry_block")
                block_reasons.append("near_earnings_event")
            try:
                event_position_size_multiplier = float(
                    resolved_event_risk.get("position_size_multiplier", 1.0)
                )
            except (TypeError, ValueError):
                event_position_size_multiplier = 1.0
            event_position_size_multiplier = max(
                0.0,
                min(event_position_size_multiplier, 1.0),
            )
            if (
                resolved_event_risk.get("has_near_event") is True
                and event_position_size_multiplier < 1.0
                and resolved_event_risk.get("entry_blocked") is not True
            ):
                non_blocking_flags.append("event_risk_position_size_reduced")
            if resolved_event_risk.get("force_gate_level") == 1:
                non_blocking_flags.append("event_risk_force_gate_level_1")

        approved = len(flags) == 0
        size_pct = min(self._position_size_pct(final_buy_score), MAX_POSITION_EQUITY_PCT) if approved else 0.0
        if approved:
            size_pct *= event_position_size_multiplier

        return {
            "approved": approved,
            "risk_flags": flags + non_blocking_flags,
            "block_reasons": block_reasons,
            "reason": block_reasons[0] if block_reasons else ("approved" if approved else "risk_flags_present"),
            "position_size_pct": round(size_pct, 4),
            "stop_loss_pct": 0.015 if approved else 0.0,
            "take_profit_pct": 0.03 if approved else 0.0,
            "daily_trade_count": daily_count,
            "estimated_daily_pnl": round(est_daily_pnl, 2),
            "broker": broker,
            "market": normalized_market,
            "event_risk": resolved_event_risk,
            "warnings": _dedupe(warnings),
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


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
