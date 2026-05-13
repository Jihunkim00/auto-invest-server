import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import MarketAnalysis, OrderLog, SignalLog
from app.services.gpt_risk_context import gpt_context_from_market_analysis

router = APIRouter(prefix="/logs", tags=["logs"])


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


def _signal_gpt_context(db: Session, row: SignalLog) -> dict | None:
    if row.market_analysis_id is None:
        return None
    analysis = db.get(MarketAnalysis, row.market_analysis_id)
    if analysis is None:
        return None
    return gpt_context_from_market_analysis(analysis)


@router.get("/orders")
def get_order_logs(
    symbol: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(OrderLog)

    if symbol:
        query = query.filter(OrderLog.symbol == symbol)

    rows = query.order_by(OrderLog.created_at.desc()).limit(limit).all()

    return [
        {
            "id": row.id,
            "symbol": row.symbol,
            "side": row.side,
            "order_type": row.order_type,
            "notional": row.notional,
            "qty": row.qty,
            "internal_status": row.internal_status,
            "broker_status": row.broker_status,
            "filled_qty": row.filled_qty,
            "filled_avg_price": row.filled_avg_price,
            "submitted_at": row.submitted_at,
            "filled_at": row.filled_at,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/signals")
def get_signal_logs(
    symbol: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(SignalLog)

    if symbol:
        query = query.filter(SignalLog.symbol == symbol)

    rows = query.order_by(SignalLog.created_at.desc()).limit(limit).all()

    return [
        {
            "id": row.id,
            "symbol": row.symbol,
            "action": row.action,
            "buy_score": row.buy_score,
            "sell_score": row.sell_score,
            "confidence": row.confidence,
            "regime_confidence": row.gpt_market_confidence,
            "quant_buy_score": row.quant_buy_score,
            "quant_sell_score": row.quant_sell_score,
            "ai_buy_score": row.ai_buy_score,
            "ai_sell_score": row.ai_sell_score,
            "final_buy_score": row.final_buy_score,
            "final_sell_score": row.final_sell_score,
            "reason": row.reason,
            "quant_reason": row.quant_reason,
            "ai_reason": row.ai_reason,
            "indicator_payload": row.indicator_payload,
            "risk_flags": _parse_json_array(row.risk_flags),
            "gpt_context": _signal_gpt_context(db, row),
            "approved_by_risk": row.approved_by_risk,
            "signal_status": row.signal_status,
            "gate_level": row.gate_level,
            "gate_profile_name": row.gate_profile_name,
            "hard_block_reason": row.hard_block_reason,
            "hard_blocked": bool(row.hard_blocked),
            "gating_notes": _parse_json_array(row.gating_notes),
            "related_order_id": row.related_order_id,
            "created_at": row.created_at,
        }
        for row in rows
    ]
