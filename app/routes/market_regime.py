from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.market_regime import MarketRegimeResponse
from app.services.market_regime_service import MarketRegimeService


router = APIRouter(prefix="/market-regime", tags=["market-regime"])


@router.get("/current", response_model=MarketRegimeResponse)
def get_current_market_regime(db: Session = Depends(get_db)):
    # The API serves persisted data only and cannot submit broker orders.
    return MarketRegimeService().get_current_payload(db)
