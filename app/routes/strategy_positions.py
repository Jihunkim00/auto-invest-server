from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import get_db
from app.schemas.position_exit_review import (
    GuardedPositionSellRequest,
    GuardedPositionSellResponse,
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


@router.post(
    "/{symbol}/guarded-sell",
    response_model=GuardedPositionSellResponse,
)
def run_guarded_position_sell(
    symbol: str,
    payload: GuardedPositionSellRequest | None = None,
    db: Session = Depends(get_db),
    service: PositionExitReviewService = Depends(get_position_exit_review_service),
):
    request = payload or GuardedPositionSellRequest()
    return service.guarded_sell(db, symbol=symbol, request=request)


@router.get(
    "/sell-results/{attempt_id}",
    response_model=GuardedPositionSellResponse,
)
def get_guarded_position_sell_result(
    attempt_id: int,
    db: Session = Depends(get_db),
    service: PositionExitReviewService = Depends(get_position_exit_review_service),
):
    try:
        return service.guarded_sell_result(db, attempt_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/sell-results/{attempt_id}/sync",
    response_model=GuardedPositionSellResponse,
)
def sync_guarded_position_sell_result(
    attempt_id: int,
    db: Session = Depends(get_db),
    service: PositionExitReviewService = Depends(get_position_exit_review_service),
):
    try:
        return service.sync_guarded_sell_result(db, attempt_id)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not_found" in message else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
