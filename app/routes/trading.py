from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.trading_service import TradingService

router = APIRouter(prefix="/trading", tags=["trading"])


@router.post("/run-once")
def run_once(
    symbol: str = Query(default="AAPL", min_length=1),
    trigger_source: str = Query(default="manual"),
    db: Session = Depends(get_db),
):
    svc = TradingService()
    return svc.run_once(db, symbol=symbol.upper(), trigger_source=trigger_source)