from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import DEFAULT_GATE_LEVEL
from app.db.models import TradeRunLog
from app.services.execution_guard_service import ExecutionGuardService
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.trading_service import TradingService


class TradingOrchestratorService:
    def __init__(self):
        self.runtime_settings = RuntimeSettingService()
        self.guard = ExecutionGuardService()
        self.trading_service = TradingService()

    def run(
        self,
        db: Session,
        *,
        trigger_source: str,
        symbol: str | None = None,
        gate_level: int | None = None,
        request_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        settings = self.runtime_settings.get_settings(db)

        run_symbol = (symbol or settings["default_symbol"] or "AAPL").upper()
        run_gate_level = int(gate_level if gate_level is not None else settings.get("default_gate_level", DEFAULT_GATE_LEVEL))

        run_log = self._create_run_log(
            db,
            run_key=f"run_{uuid.uuid4().hex[:12]}",
            trigger_source=trigger_source,
            symbol=run_symbol,
            gate_level=run_gate_level,
            stage="precheck",
            result="pending",
            reason="started",
            request_payload=request_payload or {},
        )

        precheck = self.guard.precheck(db, run_symbol)
        if not precheck["allowed"]:
            return self._finish(
                db,
                run_log,
                stage=precheck["stage"],
                result=precheck["result"],
                reason=precheck["reason"],
                response_payload={"guard": precheck},
            )

        def _action_guard(signal_action: str, signal_obj) -> dict[str, Any] | None:
            action_guard = self.guard.action_check(db, run_symbol, signal_action)
            if action_guard["allowed"]:
                return None

            signal_obj.signal_status = "skipped"
            signal_obj.related_order_id = None
            signal_obj.risk_flags = json.dumps([action_guard["reason"]], ensure_ascii=False)
            db.commit()
            db.refresh(signal_obj)
            return {
                "result": action_guard["result"],
                "stage": action_guard["stage"],
                "reason": action_guard["reason"],
            }

        try:
            trading_result = self.trading_service.run_once(
                db,
                symbol=run_symbol,
                trigger_source=trigger_source,
                gate_level=run_gate_level,
                pre_execution_check_fn=_action_guard,
            )

            return self._finish(
                db,
                run_log,
                stage=trading_result.get("stage", "done"),
                result=trading_result.get("result", "error"),
                reason=trading_result.get("reason"),
                signal_id=trading_result.get("signal_id"),
                order_id=trading_result.get("related_order_id"),
                response_payload=trading_result,
            )
        except Exception as exc:
            return self._finish(
                db,
                run_log,
                stage="done",
                result="error",
                reason=str(exc),
                response_payload={"error": str(exc)},
            )

    def list_runs(self, db: Session, *, limit: int = 50, symbol: str | None = None) -> list[dict]:
        query = db.query(TradeRunLog)
        if symbol:
            query = query.filter(TradeRunLog.symbol == symbol.upper())
        rows = query.order_by(TradeRunLog.created_at.desc()).limit(limit).all()

        return [self._serialize_run(row) for row in rows]

    def _create_run_log(self, db: Session, **kwargs) -> TradeRunLog:
        row = TradeRunLog(
            run_key=kwargs["run_key"],
            trigger_source=kwargs["trigger_source"],
            symbol=kwargs["symbol"],
            gate_level=kwargs["gate_level"],
            stage=kwargs["stage"],
            result=kwargs["result"],
            reason=kwargs.get("reason"),
            request_payload=json.dumps(kwargs.get("request_payload") or {}, ensure_ascii=False),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def _finish(
        self,
        db: Session,
        run_log: TradeRunLog,
        *,
        stage: str,
        result: str,
        reason: str | None,
        response_payload: dict,
        signal_id: int | None = None,
        order_id: int | None = None,
    ) -> dict[str, Any]:
        run_log.stage = stage
        run_log.result = result
        run_log.reason = reason
        run_log.signal_id = signal_id
        run_log.order_id = order_id
        run_log.response_payload = json.dumps(response_payload or {}, ensure_ascii=False, default=str)
        db.commit()
        db.refresh(run_log)

        return {
            "run_id": run_log.id,
            "run_key": run_log.run_key,
            "trigger_source": run_log.trigger_source,
            "symbol": run_log.symbol,
            "gate_level": run_log.gate_level,
            "stage": run_log.stage,
            "result": run_log.result,
            "reason": run_log.reason,
            "signal_id": run_log.signal_id,
            "order_id": run_log.order_id,
            "created_at": run_log.created_at,
            "response_payload": response_payload,
        }

    def _serialize_run(self, row: TradeRunLog) -> dict[str, Any]:
        request_payload = {}
        response_payload = {}
        if row.request_payload:
            try:
                request_payload = json.loads(row.request_payload)
            except Exception:
                request_payload = {}
        if row.response_payload:
            try:
                response_payload = json.loads(row.response_payload)
            except Exception:
                response_payload = {}

        return {
            "id": row.id,
            "run_key": row.run_key,
            "trigger_source": row.trigger_source,
            "symbol": row.symbol,
            "gate_level": row.gate_level,
            "stage": row.stage,
            "result": row.result,
            "reason": row.reason,
            "signal_id": row.signal_id,
            "order_id": row.order_id,
            "request_payload": request_payload,
            "response_payload": response_payload,
            "created_at": row.created_at,
        }