from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import get_db
from app.schemas.operation_test import (
    OperationTest4ConfirmationRequest,
    OperationTest4NextSessionArmRequest,
    OperationTest4WatchlistRebuildRequest,
)
from app.services.operation_test4_service import OperationTest4Service


router = APIRouter(prefix="/app/operation-test4", tags=["operation-test4"])


def get_operation_test4_service(
    db: Session = Depends(get_db),
) -> OperationTest4Service:
    settings = get_settings()
    return OperationTest4Service(
        KisClient(settings, KisAuthManager(settings, db))
    )


@router.get("/status")
def get_operation_test4_status(
    db: Session = Depends(get_db),
    service: OperationTest4Service = Depends(get_operation_test4_service),
):
    return service.status(db)


@router.get("/readiness")
def get_operation_test4_readiness(
    db: Session = Depends(get_db),
    service: OperationTest4Service = Depends(get_operation_test4_service),
):
    return service.readiness(db)


@router.post("/watchlist/rebuild")
def rebuild_operation_test4_watchlist(
    payload: OperationTest4WatchlistRebuildRequest | None = None,
    db: Session = Depends(get_db),
    service: OperationTest4Service = Depends(get_operation_test4_service),
):
    payload = payload or OperationTest4WatchlistRebuildRequest()
    try:
        return service.rebuild_watchlist(
            db,
            count=payload.count,
            price_cap_krw=payload.price_cap_krw,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/entry/preflight-once")
def operation_test4_entry_preflight_once(
    db: Session = Depends(get_db),
    service: OperationTest4Service = Depends(get_operation_test4_service),
):
    return service.preflight_once(db)


@router.post("/start")
def start_operation_test4_full_cycle(
    payload: OperationTest4ConfirmationRequest,
    db: Session = Depends(get_db),
    service: OperationTest4Service = Depends(get_operation_test4_service),
):
    result = service.start_full_cycle(
        db,
        confirm_live=payload.confirm_live,
        confirmation=payload.confirmation,
    )
    status_code = 409 if result.get("reason") == "operator_confirmation_required" else 200
    return JSONResponse(status_code=status_code, content=result)


@router.post("/scheduler/arm-next-session")
def arm_operation_test4_next_session(
    payload: OperationTest4NextSessionArmRequest,
    db: Session = Depends(get_db),
    service: OperationTest4Service = Depends(get_operation_test4_service),
):
    result = service.arm_next_session(
        db,
        confirm=payload.confirm,
        confirmation=payload.confirmation,
    )
    status_code = 200 if result.get("status") == "armed" else 409
    return JSONResponse(status_code=status_code, content=jsonable_encoder(result))


@router.post("/enable-live")
def enable_live_operation_test4(
    payload: OperationTest4ConfirmationRequest,
    db: Session = Depends(get_db),
    service: OperationTest4Service = Depends(get_operation_test4_service),
):
    result = service.enable_live(
        db,
        **{
            "confirm_live": payload.confirm_live,
            "confirmation": payload.confirmation,
        },
    )
    status_code = 200 if result.get("status") == "live_enabled" else 409
    return JSONResponse(status_code=status_code, content=result)


@router.post("/entry/run-once")
def operation_test4_entry_run_once(
    payload: OperationTest4ConfirmationRequest,
    db: Session = Depends(get_db),
    service: OperationTest4Service = Depends(get_operation_test4_service),
):
    result = service.entry_run_once(
        db,
        **{
            "confirm_live": payload.confirm_live,
            "confirmation": payload.confirmation,
        },
    )
    status_code = 200 if result.get("real_order_submitted") is True else 409
    return JSONResponse(status_code=status_code, content=result)


@router.post("/disable")
def disable_operation_test4(
    db: Session = Depends(get_db),
    service: OperationTest4Service = Depends(get_operation_test4_service),
):
    return service.disable(db)


@router.post("/reconcile-once")
def reconcile_operation_test4_once(
    db: Session = Depends(get_db),
    service: OperationTest4Service = Depends(get_operation_test4_service),
):
    return service.reconcile_once(db)