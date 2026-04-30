from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import OrderLog, SignalLog, TradeRunLog

router = APIRouter(tags=["history"])


def _parse_json_object(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def _serialize_run(row: TradeRunLog) -> dict[str, Any]:
    response_payload = _parse_json_object(row.response_payload)
    trade_result = response_payload.get("trade_result")
    if not isinstance(trade_result, dict):
        trade_result = {}

    action = (
        response_payload.get("action")
        or trade_result.get("action")
        or ("hold" if row.result in {"skipped", "rejected"} else row.result)
    )
    reason = row.reason or response_payload.get("reason") or trade_result.get("reason")

    return {
        "id": row.id,
        "run_key": row.run_key,
        "symbol": row.symbol,
        "trigger_source": row.trigger_source,
        "mode": row.mode,
        "action": str(action or "hold"),
        "result": row.result,
        "reason": reason,
        "related_order_id": row.order_id,
        "order_id": row.order_id,
        "signal_id": row.signal_id,
        "gate_level": row.gate_level,
        "stage": row.stage,
        "symbol_role": row.symbol_role,
        "parent_run_key": row.parent_run_key,
        "created_at": row.created_at,
    }


def _serialize_order(row: OrderLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "side": row.side,
        "qty": row.qty,
        "notional": row.notional,
        "broker_order_id": row.broker_order_id,
        "broker_status": row.broker_status,
        "internal_status": row.internal_status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _serialize_signal(row: SignalLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_key": None,
        "symbol": row.symbol,
        "action": row.action,
        "signal_status": row.signal_status,
        "buy_score": row.buy_score,
        "sell_score": row.sell_score,
        "final_buy_score": row.final_buy_score,
        "final_sell_score": row.final_sell_score,
        "confidence": row.confidence,
        "reason": row.reason,
        "related_order_id": row.related_order_id,
        "gate_level": row.gate_level,
        "created_at": row.created_at,
    }


@router.get("/runs/recent")
def get_recent_runs(
    limit: int = Query(default=20, ge=1, le=200),
    symbol: str | None = Query(default=None, min_length=1),
    trigger_source: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
):
    query = db.query(TradeRunLog)
    if symbol:
        query = query.filter(TradeRunLog.symbol == symbol.upper())
    if trigger_source:
        query = query.filter(TradeRunLog.trigger_source == trigger_source)

    rows = query.order_by(TradeRunLog.created_at.desc()).limit(limit).all()
    return {"items": [_serialize_run(row) for row in rows]}


@router.get("/orders/recent")
def get_recent_orders(
    limit: int = Query(default=20, ge=1, le=200),
    symbol: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
):
    query = db.query(OrderLog)
    if symbol:
        query = query.filter(OrderLog.symbol == symbol.upper())

    rows = query.order_by(OrderLog.created_at.desc()).limit(limit).all()
    return {"items": [_serialize_order(row) for row in rows]}


@router.get("/signals/recent")
def get_recent_signals(
    limit: int = Query(default=20, ge=1, le=200),
    symbol: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
):
    query = db.query(SignalLog)
    if symbol:
        query = query.filter(SignalLog.symbol == symbol.upper())

    rows = query.order_by(SignalLog.created_at.desc()).limit(limit).all()
    return {"items": [_serialize_signal(row) for row in rows]}


@router.get("/logs/summary")
def get_logs_summary(db: Session = Depends(get_db)):
    latest_run = db.query(TradeRunLog).order_by(TradeRunLog.created_at.desc()).first()
    latest_order = db.query(OrderLog).order_by(OrderLog.created_at.desc()).first()
    latest_signal = db.query(SignalLog).order_by(SignalLog.created_at.desc()).first()

    return {
        "latest_run": _serialize_run(latest_run) if latest_run else None,
        "latest_order": _serialize_order(latest_order) if latest_order else None,
        "latest_signal": _serialize_signal(latest_signal) if latest_signal else None,
        "counts": {
            "runs": db.query(TradeRunLog).count(),
            "orders": db.query(OrderLog).count(),
            "signals": db.query(SignalLog).count(),
        },
    }
