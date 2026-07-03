from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import get_db
from app.schemas.position_exit_review import (
    PositionExitReviewResponse,
    PositionSellPreflightRequest,
    PositionSellPreflightResponse,
)
from app.services.position_exit_review_service import PositionExitReviewService


router = APIRouter(prefix="/strategy/positions", tags=["strategy-positions"])


def get_position_exit_review_service(
    db: Session = Depends(get_db),
) -> PositionExitReviewService:
    settings = get_settings()
    client = KisClient(settings, KisAuthManager(settings, db))
    return PositionExitReviewService(client)


@router.get(
    "/exit-review",
    response_model=PositionExitReviewResponse,
)
def get_position_exit_review(
    db: Session = Depends(get_db),
    service: PositionExitReviewService = Depends(get_position_exit_review_service),
):
    return service.exit_review(db)


@router.post(
    "/{symbol}/sell-preflight",
    response_model=PositionSellPreflightResponse,
)
def run_position_sell_preflight(
    symbol: str,
    payload: PositionSellPreflightRequest | None = None,
    db: Session = Depends(get_db),
    service: PositionExitReviewService = Depends(get_position_exit_review_service),
):
    request = payload or PositionSellPreflightRequest()
    return service.sell_preflight(db, symbol=symbol, request=request)
