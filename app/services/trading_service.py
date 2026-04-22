import json
import uuid

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
from app.db.models import TradeRunLog
from app.services.execution_guard_service import ExecutionGuardService
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
        self.execution_guard_service = ExecutionGuardService()

    @staticmethod
    def _safe_int_qty(raw_qty) -> int:
        try:
            return int(float(raw_qty or 0))
        except Exception:
            return 0

    def _execute_market_sell(
        self,
        db: Session,
        *,
        symbol: str,
        qty: int,
        source: str,
        request_payload: dict | None = None,
    ) -> dict:
        latest = self.broker.get_latest_price(symbol)
        price = float(latest["price"]) if latest and latest.get("price") else 0.0
        notional = round(qty * price, 2) if price > 0 else None

        local_order = create_order_log(
            db,
            symbol=symbol,
            side="sell",
            order_type="market",
            time_in_force="day",
            qty=qty,
            notional=notional,
            limit_price=None,
            extended_hours=False,
            request_payload={
                "source": source,
                "price": price,
                "qty": qty,
                "position_close": True,
                **(request_payload or {}),
            },
        )
        broker_order = self.broker.submit_market_sell(symbol=symbol, qty=qty)
        local_order = update_order_from_broker_response(db, local_order, broker_order)
        return {
            "order_id": local_order.id,
            "qty": qty,
            "price": price,
            "notional": notional,
        }

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
        mode: str | None = None,
        allowed_actions: list[str] | None = None,
    ) -> dict:
        signal = self.signal_service.run(
            db,
            symbol=symbol,
            trigger_source=trigger_source,
            gate_level=gate_level,
        )
        allowed_actions_set = {a.lower() for a in (allowed_actions or ["hold", "buy", "sell"])}
        original_action = signal.action
        if signal.action not in allowed_actions_set:
            signal.action = "hold"
            flags = _parse_json_array(signal.risk_flags)
            flags.append(f"action_suppressed_by_mode:{mode or 'unknown'}:{original_action}")
            signal.risk_flags = json.dumps(flags, ensure_ascii=False)
            signal.signal_status = SIGNAL_STATUS_SKIPPED
            signal.related_order_id = None
            db.commit()
            db.refresh(signal)

        if mode == "position_management" and signal.action == "hold":
            position = self.broker.get_position(signal.symbol)
            if position is not None:
                exit_eval = self.risk_service.evaluate_exit(
                    position=position,
                    final_sell_score=float(signal.final_sell_score or 0),
                    final_buy_score=float(signal.final_buy_score or 0),
                )
                if exit_eval["should_exit"]:
                    signal.action = "sell"
                    flags = _parse_json_array(signal.risk_flags)
                    flags.extend(exit_eval["reasons"])
                    signal.risk_flags = json.dumps(flags, ensure_ascii=False)
                    signal.signal_status = SIGNAL_STATUS_CREATED
                    db.commit()
                    db.refresh(signal)

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
            response["mode"] = mode
            response["allowed_actions"] = sorted(list(allowed_actions_set))
            response["original_action"] = original_action
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
                response["mode"] = mode
                response["allowed_actions"] = sorted(list(allowed_actions_set))
                response["original_action"] = original_action
                return response

            try:
                qty = self._safe_int_qty(getattr(position, "qty", 0))
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
                    response["mode"] = mode
                    response["allowed_actions"] = sorted(list(allowed_actions_set))
                    response["original_action"] = original_action
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
                        response["mode"] = mode
                        response["allowed_actions"] = sorted(list(allowed_actions_set))
                        response["original_action"] = original_action
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

                sell_result = self._execute_market_sell(
                    db,
                    symbol=signal.symbol,
                    qty=qty,
                    source="trading_service",
                    request_payload={"signal_id": signal.id},
                )
                signal.related_order_id = sell_result["order_id"]
                signal.signal_status = SIGNAL_STATUS_EXECUTED
                db.commit()
                db.refresh(signal)

                response = self._base_response(signal, result=RUN_RESULT_EXECUTED, stage="broker")
                response["risk"] = risk
                response["order"] = {
                    "side": "sell",
                    "qty": sell_result["qty"],
                    "price": sell_result["price"],
                    "notional": sell_result["notional"],
                }
                response["mode"] = mode
                response["allowed_actions"] = sorted(list(allowed_actions_set))
                response["original_action"] = original_action
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
                response["mode"] = mode
                response["allowed_actions"] = sorted(list(allowed_actions_set))
                response["original_action"] = original_action
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
            response["mode"] = mode
            response["allowed_actions"] = sorted(list(allowed_actions_set))
            response["original_action"] = original_action
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
                response["mode"] = mode
                response["allowed_actions"] = sorted(list(allowed_actions_set))
                response["original_action"] = original_action
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
                response["mode"] = mode
                response["allowed_actions"] = sorted(list(allowed_actions_set))
                response["original_action"] = original_action
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
            response["mode"] = mode
            response["allowed_actions"] = sorted(list(allowed_actions_set))
            response["original_action"] = original_action
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
            response["mode"] = mode
            response["allowed_actions"] = sorted(list(allowed_actions_set))
            response["original_action"] = original_action
            return response

    def manual_close_position(
        self,
        db: Session,
        *,
        symbol: str,
        trigger_source: str = "manual",
    ) -> dict:
        symbol = symbol.upper()
        run_log = TradeRunLog(
            run_key=f"manual_close_{symbol}_{uuid.uuid4().hex[:8]}",
            trigger_source=trigger_source,
            symbol=symbol,
            mode="position_management",
            symbol_role="open_position",
            stage="precheck",
            result="pending",
            reason="manual_close_requested",
            request_payload=json.dumps({"symbol": symbol, "source": trigger_source}, ensure_ascii=False),
        )
        db.add(run_log)
        db.commit()
        db.refresh(run_log)

        position = self.broker.get_position(symbol)
        if position is None:
            run_log.stage = "done"
            run_log.result = RUN_RESULT_SKIPPED
            run_log.reason = "no_open_position"
            db.commit()
            db.refresh(run_log)
            return {
                "result": RUN_RESULT_SKIPPED,
                "reason": "no_open_position",
                "symbol": symbol,
                "executed": False,
                "run_id": run_log.id,
                "order_id": None,
            }

        qty = self._safe_int_qty(getattr(position, "qty", 0))
        if qty <= 0:
            run_log.stage = "done"
            run_log.result = RUN_RESULT_SKIPPED
            run_log.reason = "invalid_position_qty_for_sell"
            db.commit()
            db.refresh(run_log)
            return {
                "result": RUN_RESULT_SKIPPED,
                "reason": "invalid_position_qty_for_sell",
                "symbol": symbol,
                "executed": False,
                "run_id": run_log.id,
                "order_id": None,
            }

        exit_guard = self.execution_guard_service.action_check(db, symbol, "sell", intent="exit")
        if not exit_guard["allowed"]:
            run_log.stage = "done"
            run_log.result = RUN_RESULT_SKIPPED
            run_log.reason = exit_guard["reason"]
            run_log.response_payload = json.dumps({"guard": exit_guard}, ensure_ascii=False)
            db.commit()
            db.refresh(run_log)
            return {
                "result": RUN_RESULT_SKIPPED,
                "reason": exit_guard["reason"],
                "symbol": symbol,
                "executed": False,
                "run_id": run_log.id,
                "order_id": None,
            }

        try:
            sell_result = self._execute_market_sell(
                db,
                symbol=symbol,
                qty=qty,
                source="manual_close",
                request_payload={"run_id": run_log.id, "trigger_source": trigger_source},
            )
            run_log.stage = "done"
            run_log.result = RUN_RESULT_EXECUTED
            run_log.reason = "manual_close_executed"
            run_log.order_id = sell_result["order_id"]
            run_log.response_payload = json.dumps(
                {
                    "symbol": symbol,
                    "qty": sell_result["qty"],
                    "price": sell_result["price"],
                    "notional": sell_result["notional"],
                },
                ensure_ascii=False,
            )
            db.commit()
            db.refresh(run_log)
            return {
                "result": RUN_RESULT_EXECUTED,
                "reason": "manual_close_executed",
                "symbol": symbol,
                "executed": True,
                "run_id": run_log.id,
                "order_id": sell_result["order_id"],
                "order": {
                    "side": "sell",
                    "qty": sell_result["qty"],
                    "price": sell_result["price"],
                    "notional": sell_result["notional"],
                },
            }
        except Exception as exc:
            run_log.stage = "done"
            run_log.result = RUN_RESULT_ERROR
            run_log.reason = str(exc)
            run_log.response_payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
            db.commit()
            db.refresh(run_log)
            return {
                "result": RUN_RESULT_ERROR,
                "reason": str(exc),
                "symbol": symbol,
                "executed": False,
                "run_id": run_log.id,
                "order_id": None,
            }
