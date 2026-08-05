from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import get_db
from app.schemas.operation_test import (
    OperationTest3EnableRequest,
    OperationTest3MonitoringEnableRequest,
    OperationTest3PositionManagementRunRequest,
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
from app.services.operation_test3_position_management_service import (
    OperationTest3PositionManagementService,
)


router = APIRouter(prefix="/app", tags=["app-facade"])


def get_operation_mode_service() -> OperationModeService:
    return OperationModeService()


def get_operator_forced_one_share_buy_service(
    db: Session = Depends(get_db),
) -> OperatorForcedOneShareBuyService:
    return OperatorForcedOneShareBuyService(_kis_client(db))


def get_operation_test3_position_management_service(
    db: Session = Depends(get_db),
) -> OperationTest3PositionManagementService:
    return OperationTest3PositionManagementService(_kis_client(db))


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


@router.get("/operation-test3/status")
def get_operation_test3_status(
    db: Session = Depends(get_db),
    service: OperationTest3PositionManagementService = Depends(
        get_operation_test3_position_management_service
    ),
):
    return service.status(db)


@router.get("/operation-test3/position-management/live-readiness")
def operation_test3_position_management_live_readiness(
    db: Session = Depends(get_db),
    service: OperationTest3PositionManagementService = Depends(
        get_operation_test3_position_management_service
    ),
):
    return service.live_readiness(db)

@router.post("/operation-test3/position-management/preflight-once")
def operation_test3_position_management_preflight_once(
    payload: OperationTest3PositionManagementRunRequest | None = None,
    db: Session = Depends(get_db),
    service: OperationTest3PositionManagementService = Depends(
        get_operation_test3_position_management_service
    ),
):
    payload = payload or OperationTest3PositionManagementRunRequest()
    return service.preflight_once(db, slot_label=payload.slot_label)


@router.post("/operation-test3/position-management/run-once")
def operation_test3_position_management_run(
    payload: OperationTest3PositionManagementRunRequest | None = None,
    db: Session = Depends(get_db),
    service: OperationTest3PositionManagementService = Depends(
        get_operation_test3_position_management_service
    ),
):
    payload = payload or OperationTest3PositionManagementRunRequest()
    runner = getattr(service, "run" "_once")
    return runner(
        db,
        slot_label=payload.slot_label,
        include_raw=payload.include_raw,
    )


@router.post("/operation-test3/position-management/enable-monitoring")
def enable_monitoring_operation_test3_position_management(
    payload: OperationTest3MonitoringEnableRequest,
    db: Session = Depends(get_db),
    service: OperationTest3PositionManagementService = Depends(
        get_operation_test3_position_management_service
    ),
):
    result = service.enable_monitoring(db, confirmation=payload.confirmation)
    status_code = 200 if result.get("status") == "monitoring_enabled" else 409
    return JSONResponse(status_code=status_code, content=result)


@router.post("/operation-test3/position-management/enable")
def enable_live_operation_test3_position_management(
    payload: OperationTest3EnableRequest,
    db: Session = Depends(get_db),
    service: OperationTest3PositionManagementService = Depends(
        get_operation_test3_position_management_service
    ),
):
    result = service.enable(
        db,
        **{
            "confirm" "_live": getattr(payload, "confirm" "_live"),
            "confirmation": payload.confirmation,
        },
    )
    status_code = 200 if result.get("status") == "live_enabled" else 409
    return JSONResponse(status_code=status_code, content=result)


@router.post("/operation-test3/disable")
def disable_operation_test3(
    db: Session = Depends(get_db),
    service: OperationTest3PositionManagementService = Depends(
        get_operation_test3_position_management_service
    ),
):
    return service.disable(db)


def _kis_client(db: Session) -> KisClient:
    settings = get_settings()
    return KisClient(settings, KisAuthManager(settings, db))
