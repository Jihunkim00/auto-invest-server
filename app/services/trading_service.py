import json

from sqlalchemy.orm import Session

from app.brokers.alpaca_client import AlpacaClient
from app.core.constants import SIGNAL_STATUS_APPROVED, SIGNAL_STATUS_EXECUTED, SIGNAL_STATUS_REJECTED, SIGNAL_STATUS_SKIPPED
from app.services.order_service import create_order_log, update_order_from_broker_response
from app.services.risk_service import RiskService
from app.services.signal_service import SignalService


class TradingService:
    def __init__(self):
        self.signal_service = SignalService()
        self.risk_service = RiskService()
        self.broker = AlpacaClient()

    def run_once(self, db: Session, *, symbol: str, trigger_source: str = "manual") -> dict:
        signal = self.signal_service.run(db, symbol=symbol, trigger_source=trigger_source)

        if signal.action != "buy":
            risk = {
                "approved": False,
                "risk_flags": ["hold_or_non_buy_action"],
                "position_size_pct": 0.0,
                "stop_loss_pct": 0.0,
                "take_profit_pct": 0.0,
            }
            signal.risk_flags = json.dumps(risk["risk_flags"], ensure_ascii=False)
            signal.approved_by_risk = False
            signal.signal_status = SIGNAL_STATUS_SKIPPED
            signal.related_order_id = None
            signal.position_size_pct = 0.0
            signal.planned_stop_loss_pct = 0.0
            signal.planned_take_profit_pct = 0.0
            db.commit()
            db.refresh(signal)
            return {
                "signal_id": signal.id,
                "action": signal.action,
                "executed": False,
                "signal_status": signal.signal_status,
                "reason": "signal action is HOLD/non-buy; execution skipped",
                "related_order_id": signal.related_order_id,
                "risk": risk,
            }

        risk = self.risk_service.evaluate(
            db,
            symbol=signal.symbol,
            action=signal.action,
            final_buy_score=float(signal.final_buy_score or 0),
        )

        signal.risk_flags = json.dumps(risk["risk_flags"], ensure_ascii=False)
        signal.approved_by_risk = risk["approved"]
        signal.position_size_pct = risk["position_size_pct"]
        signal.planned_stop_loss_pct = risk["stop_loss_pct"]
        signal.planned_take_profit_pct = risk["take_profit_pct"]

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

        latest = self.broker.get_latest_price(signal.symbol)
        account = self.broker.get_account()
        equity = float(account.equity)
        price = float(latest["price"]) if latest and latest.get("price") else 0.0
        qty = int((equity * float(risk["position_size_pct"])) / price) if price > 0 else 0

        if qty <= 0:
            risk["approved"] = False
            risk["risk_flags"].append("invalid_qty")
            signal.risk_flags = json.dumps(risk["risk_flags"], ensure_ascii=False)
            signal.approved_by_risk = False
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

        notional = round(qty * price, 2)
        local_order = create_order_log(
            db,
            symbol=signal.symbol,
            side="buy",
            order_type="market",
            time_in_force="day",
            qty=qty,
            notional=notional,
            limit_price=None,
            extended_hours=False,
            request_payload={
                "source": "trading_service",
                "signal_id": signal.id,
                "price": price,
                "qty": qty,
                "position_size_pct": risk["position_size_pct"],
                "planned_stop_loss_pct": risk["stop_loss_pct"],
                "planned_take_profit_pct": risk["take_profit_pct"],
            },
        )
        broker_order = self.broker.submit_market_buy_qty(symbol=signal.symbol, qty=qty)
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
            "order": {
                "qty": qty,
                "price": price,
                "notional": notional,
            },
        }