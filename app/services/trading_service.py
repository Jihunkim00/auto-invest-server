from sqlalchemy.orm import Session

from app.brokers.alpaca_client import AlpacaClient
from app.core.constants import (
    DEFAULT_POSITION_EQUITY_PCT,
    MAX_POSITION_EQUITY_PCT,
    SIGNAL_STATUS_APPROVED,
    SIGNAL_STATUS_EXECUTED,
    SIGNAL_STATUS_REJECTED,
    SIGNAL_STATUS_SKIPPED,
)
from app.services.order_service import create_order_log, update_order_from_broker_response
from app.services.risk_service import RiskService
from app.services.signal_service import SignalService


class TradingService:
    def __init__(self):
        self.signal_service = SignalService()
        self.risk_service = RiskService()
        self.broker = AlpacaClient()

    def _calc_notional(self) -> float:
        account = self.broker.get_account()
        equity = float(account.equity)
        pct = min(DEFAULT_POSITION_EQUITY_PCT, MAX_POSITION_EQUITY_PCT)
        return max(round(equity * pct, 2), 10.0)

    def run_once(self, db: Session, *, symbol: str, trigger_source: str = "manual") -> dict:
        signal = self.signal_service.run(db, symbol=symbol, trigger_source=trigger_source)

        if signal.action == "hold":
            risk = {
                "approved": False,
                "risk_flags": '["hold_action"]',
            }
            signal.risk_flags = risk["risk_flags"]
            signal.approved_by_risk = False
            signal.signal_status = SIGNAL_STATUS_SKIPPED
            signal.related_order_id = None
            db.commit()
            db.refresh(signal)
            return {
                "signal_id": signal.id,
                "action": "hold",
                "executed": False,
                "signal_status": signal.signal_status,
                "reason": "signal action is HOLD; execution skipped",
                "related_order_id": signal.related_order_id,
                "risk": risk,
            }

        risk = self.risk_service.evaluate(
            db,
            symbol=signal.symbol,
            action=signal.action,
            confidence=float(signal.confidence or 0),
        )

        signal.risk_flags = risk["risk_flags"]
        signal.approved_by_risk = risk["approved"]

        if not risk["approved"]:
            signal.signal_status = SIGNAL_STATUS_REJECTED
            signal.related_order_id = None
            db.commit()
            db.refresh(signal)
            return {
                "signal_id": signal.id,
                "action": signal.action,
                "executed": False,
                "signal_status": signal.signal_status,
                "related_order_id": signal.related_order_id,
                "risk": risk,
            }

        signal.signal_status = SIGNAL_STATUS_APPROVED
        db.commit()

        if signal.action == "buy":
            notional = self._calc_notional()
            local_order = create_order_log(
                db,
                symbol=signal.symbol,
                side="buy",
                order_type="market",
                time_in_force="day",
                qty=None,
                notional=notional,
                limit_price=None,
                extended_hours=False,
                request_payload={"source": "trading_service", "signal_id": signal.id, "notional": notional},
            )
            broker_order = self.broker.submit_market_buy(symbol=signal.symbol, notional=notional)
            local_order = update_order_from_broker_response(db, local_order, broker_order)
            signal.related_order_id = local_order.id
        else:
            position = self.broker.get_position(signal.symbol)
            if position is None:
                signal.signal_status = SIGNAL_STATUS_SKIPPED
                db.commit()
                db.refresh(signal)
                return {"signal_id": signal.id, "action": "sell", "executed": False, "reason": "no_position"}

            qty = float(position.qty)
            local_order = create_order_log(
                db,
                symbol=signal.symbol,
                side="sell",
                order_type="market",
                time_in_force="day",
                qty=qty,
                notional=None,
                limit_price=None,
                extended_hours=False,
                request_payload={"source": "trading_service", "signal_id": signal.id, "qty": qty},
            )
            broker_order = self.broker.submit_market_sell(symbol=signal.symbol, qty=qty)
            local_order = update_order_from_broker_response(db, local_order, broker_order)
            signal.related_order_id = local_order.id

        signal.signal_status = SIGNAL_STATUS_EXECUTED
        db.commit()
        db.refresh(signal)

        return {
            "signal_id": signal.id,
            "action": signal.action,
            "executed": True,
            "signal_status": signal.signal_status,
            "related_order_id": signal.related_order_id,
            "risk": risk,
        }