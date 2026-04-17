import json

from sqlalchemy.orm import Session

from app.brokers.alpaca_client import AlpacaClient
from app.core.constants import (
    RUN_RESULT_ERROR,
    RUN_RESULT_EXECUTED,
    RUN_RESULT_REJECTED,
    RUN_RESULT_SKIPPED,
    SIGNAL_STATUS_APPROVED,
    SIGNAL_STATUS_EXECUTED,
    SIGNAL_STATUS_REJECTED,
    SIGNAL_STATUS_SKIPPED,
)
from app.services.order_service import create_order_log, update_order_from_broker_response
from app.services.risk_service import RiskService
from app.services.signal_service import SignalService


def _parse_json_array(raw_value: str | None) -> list:
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        return []
    return []


class TradingService:
    def __init__(self):
        self.signal_service = SignalService()
        self.risk_service = RiskService()
        self.broker = AlpacaClient()

    def _base_response(self, signal, *, result: str, stage: str, reason: str | None = None) -> dict:
        return {
            "result": result,
            "stage": stage,
            "reason": reason,
            "signal_id": signal.id,
            "action": signal.action,
            "executed": result == RUN_RESULT_EXECUTED,
            "signal_status": signal.signal_status,
            "related_order_id": signal.related_order_id,
            "gate_level": signal.gate_level,
            "gate_profile_name": signal.gate_profile_name,
            "hard_block_reason": signal.hard_block_reason,
            "hard_blocked": bool(signal.hard_blocked),
            "gating_notes": _parse_json_array(signal.gating_notes),
            "risk_flags": _parse_json_array(signal.risk_flags),
        }

    def run_once(
        self,
        db: Session,
        *,
        symbol: str,
        trigger_source: str = "manual",
        gate_level: int | None = None,
        pre_execution_check_fn=None,
    ) -> dict:
        signal = self.signal_service.run(
            db,
            symbol=symbol,
            trigger_source=trigger_source,
            gate_level=gate_level,
        )

        if signal.action == "hold":
            risk = {
                "approved": False,
                "risk_flags": ["hold_signal"],
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
            response = self._base_response(
                signal,
                result=RUN_RESULT_SKIPPED,
                stage="signal",
                reason="signal action is HOLD; execution skipped",
            )
            response["risk"] = risk
            return response

        if signal.action == "sell":
            position = self.broker.get_position(signal.symbol)
            if position is None:
                risk = {
                    "approved": False,
                    "risk_flags": ["no_position_to_sell"],
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
                response = self._base_response(
                    signal,
                    result=RUN_RESULT_SKIPPED,
                    stage="signal",
                    reason="no position to sell",
                )
                response["risk"] = risk
                return response

            try:
                qty = int(float(getattr(position, "qty", 0) or 0))
                if qty <= 0:
                    risk = {
                        "approved": False,
                        "risk_flags": ["invalid_position_qty_for_sell"],
                        "position_size_pct": 0.0,
                        "stop_loss_pct": 0.0,
                        "take_profit_pct": 0.0,
                    }
                    signal.risk_flags = json.dumps(risk["risk_flags"], ensure_ascii=False)
                    signal.approved_by_risk = False
                    signal.signal_status = SIGNAL_STATUS_SKIPPED
                    signal.related_order_id = None
                    db.commit()
                    db.refresh(signal)
                    response = self._base_response(
                        signal,
                        result=RUN_RESULT_SKIPPED,
                        stage="signal",
                        reason="invalid position quantity for sell",
                    )
                    response["risk"] = risk
                    return response
                
                if pre_execution_check_fn:
                    guard_response = pre_execution_check_fn("sell", signal)
                    if guard_response:
                        db.refresh(signal)
                        response = self._base_response(
                            signal,
                            result=guard_response.get("result", RUN_RESULT_SKIPPED),
                            stage=guard_response.get("stage", "precheck"),
                            reason=guard_response.get("reason", "blocked by action guard"),
                        )
                        response["risk"] = {
                            "approved": False,
                            "risk_flags": [guard_response.get("reason", "blocked")],
                            "position_size_pct": 0.0,
                            "stop_loss_pct": 0.0,
                            "take_profit_pct": 0.0,
                        }
                        return response               

                risk = {
                    "approved": True,
                    "risk_flags": [],
                    "position_size_pct": 0.0,
                    "stop_loss_pct": 0.0,
                    "take_profit_pct": 0.0,
                }
                signal.risk_flags = json.dumps([], ensure_ascii=False)
                signal.approved_by_risk = True
                signal.position_size_pct = 0.0
                signal.planned_stop_loss_pct = 0.0
                signal.planned_take_profit_pct = 0.0
                signal.signal_status = SIGNAL_STATUS_APPROVED
                db.commit()

                latest = self.broker.get_latest_price(signal.symbol)
                price = float(latest["price"]) if latest and latest.get("price") else 0.0
                notional = round(qty * price, 2) if price > 0 else None

                local_order = create_order_log(
                    db,
                    symbol=signal.symbol,
                    side="sell",
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
                        "position_close": True,
                    },
                )
                broker_order = self.broker.submit_market_sell(symbol=signal.symbol, qty=qty)
                local_order = update_order_from_broker_response(db, local_order, broker_order)
                signal.related_order_id = local_order.id
                signal.signal_status = SIGNAL_STATUS_EXECUTED
                db.commit()
                db.refresh(signal)

                response = self._base_response(signal, result=RUN_RESULT_EXECUTED, stage="broker")
                response["risk"] = risk
                response["order"] = {
                    "side": "sell",
                    "qty": qty,
                    "price": price,
                    "notional": notional,
                }
                return response
            except Exception as exc:
                signal.signal_status = SIGNAL_STATUS_REJECTED
                flags = _parse_json_array(signal.risk_flags)
                flags.append("broker_or_internal_error")
                signal.risk_flags = json.dumps(flags, ensure_ascii=False)
                db.commit()
                db.refresh(signal)
                response = self._base_response(
                    signal,
                    result=RUN_RESULT_ERROR,
                    stage="broker",
                    reason=str(exc),
                )
                response["error"] = str(exc)
                return response

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
            response = self._base_response(
                signal,
                result=RUN_RESULT_REJECTED,
                stage="risk",
                reason="risk evaluation rejected execution",
            )
            response["risk"] = risk
            return response
        
        if pre_execution_check_fn:
            guard_response = pre_execution_check_fn(signal.action, signal)
            if guard_response:
                db.refresh(signal)
                response = self._base_response(
                    signal,
                    result=guard_response.get("result", RUN_RESULT_SKIPPED),
                    stage=guard_response.get("stage", "precheck"),
                    reason=guard_response.get("reason", "blocked by action guard"),
                )
                response["risk"] = risk
                return response


        try:
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
                response = self._base_response(
                    signal,
                    result=RUN_RESULT_REJECTED,
                    stage="risk",
                    reason="computed order quantity is invalid",
                )
                response["risk"] = risk
                return response

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

            response = self._base_response(signal, result=RUN_RESULT_EXECUTED, stage="broker")
            response["risk"] = risk
            response["order"] = {
                "side": "buy",
                "qty": qty,
                "price": price,
                "notional": notional,
            }
            return response
        except Exception as exc:
            signal.signal_status = SIGNAL_STATUS_REJECTED
            flags = _parse_json_array(signal.risk_flags)
            flags.append("broker_or_internal_error")
            signal.risk_flags = json.dumps(flags, ensure_ascii=False)
            db.commit()
            db.refresh(signal)
            response = self._base_response(
                signal,
                result=RUN_RESULT_ERROR,
                stage="broker",
                reason=str(exc),
            )
            response["error"] = str(exc)
            response["risk"] = risk
            return response