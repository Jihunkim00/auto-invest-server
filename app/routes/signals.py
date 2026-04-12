from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import SignalLog
from app.services.signal_service import SignalService

router = APIRouter(prefix="/signals", tags=["signals"])


@router.post("/run")
def run_signal(
    symbol: str = Query(default="AAPL", min_length=1),
    trigger_source: str = Query(default="manual"),
    db: Session = Depends(get_db),
):
    svc = SignalService()
    row = svc.run(db, symbol=symbol.upper(), trigger_source=trigger_source)
    return {
        "id": row.id,
        "symbol": row.symbol,
        "action": row.action,
        "confidence": row.confidence,
        "quant_buy_score": row.quant_buy_score,
        "quant_sell_score": row.quant_sell_score,
        "ai_buy_score": row.ai_buy_score,
        "ai_sell_score": row.ai_sell_score,
        "final_buy_score": row.final_buy_score,
        "final_sell_score": row.final_sell_score,
        "signal_status": row.signal_status,
        "created_at": row.created_at,
    }


@router.get("")
def list_signals(
    symbol: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(SignalLog)
    if symbol:
        query = query.filter(SignalLog.symbol == symbol.upper())

    rows = query.order_by(SignalLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": row.id,
            "symbol": row.symbol,
            "action": row.action,
            "confidence": row.confidence,
            "signal_status": row.signal_status,
            "approved_by_risk": row.approved_by_risk,
            "related_order_id": row.related_order_id,
            "created_at": row.created_at,
        }
        for row in rows
    ]