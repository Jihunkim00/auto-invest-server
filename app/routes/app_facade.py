from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import get_db
from app.schemas.operation_test import (
    OperatorForcedOneShareBuyRequest,
    OperatorForcedOneShareBuyResponse,
)
from app.schemas.operation_mode import (
    OperationModeChangeRequest,
    OperationModeChangeResponse,
    OperationModeStatusResponse,
)
from app.services.operation_mode_service import (
    OperationModeService,
    OperationModeTransitionBlocked,
)
from app.services.operator_forced_one_share_buy_service import (
    OperatorForcedOneShareBuyService,
)


router = APIRouter(prefix="/app", tags=["app-facade"])


def get_operation_mode_service() -> OperationModeService:
    return OperationModeService()


def get_operator_forced_one_share_buy_service(
    db: Session = Depends(get_db),
) -> OperatorForcedOneShareBuyService:
    return OperatorForcedOneShareBuyService(_kis_client(db))


@router.get("/operation-mode", response_model=OperationModeStatusResponse)
def get_operation_mode(
    provider: str | None = Query(default=None, max_length=20),
    market: str | None = Query(default=None, max_length=10),
    db: Session = Depends(get_db),
    service: OperationModeService = Depends(get_operation_mode_service),
):
    try:
        return service.get_status(db, provider=provider, market=market)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/operation-mode", response_model=OperationModeChangeResponse)
def change_operation_mode(
    payload: OperationModeChangeRequest,
    db: Session = Depends(get_db),
    service: OperationModeService = Depends(get_operation_mode_service),
):
    try:
        return service.change_mode(
            db,
            target_mode=payload.mode,
            acknowledged=payload.acknowledged,
            reason=payload.reason,
            changed_by="api",
            provider=payload.provider,
            market=payload.market,
        )
    except OperationModeTransitionBlocked as exc:
        return JSONResponse(status_code=409, content=exc.payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/operation-test3/operator-forced-one-share-buy",
    response_model=OperatorForcedOneShareBuyResponse,
)
def operator_forced_one_share_buy(
    payload: OperatorForcedOneShareBuyRequest,
    db: Session = Depends(get_db),
    service: OperatorForcedOneShareBuyService = Depends(
        get_operator_forced_one_share_buy_service
    ),
):
    result = service.run(db, payload)
    status_code = 200 if result.get("real_order_submitted") is True else 409
    return JSONResponse(status_code=status_code, content=result)


def _kis_client(db: Session) -> KisClient:
    settings = get_settings()
    return KisClient(settings, KisAuthManager(settings, db))
