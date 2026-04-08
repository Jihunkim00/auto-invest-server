from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import OrderLog, SignalLog

router = APIRouter(prefix="/logs", tags=["logs"])


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
            "reason": row.reason,
            "indicator_payload": row.indicator_payload,
            "related_order_id": row.related_order_id,
            "created_at": row.created_at,
        }
        for row in rows
    ]