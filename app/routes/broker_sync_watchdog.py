from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_broker import KisBroker
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import get_db
from app.schemas.broker_sync_watchdog import BrokerSyncWatchdogStatusResponse
from app.services.broker_sync_watchdog_service import BrokerSyncWatchdogService
from app.services.runtime_setting_service import RuntimeSettingService


router = APIRouter(prefix="/broker-sync/watchdog", tags=["broker-sync-watchdog"])


def get_broker_sync_watchdog_service(
    db: Session = Depends(get_db),
) -> BrokerSyncWatchdogService:
    runtime_settings = RuntimeSettingService()

    def broker_factory(session: Session):
        settings = get_settings()
        return KisBroker(KisClient(settings, KisAuthManager(settings, session)))

    return BrokerSyncWatchdogService(
        runtime_settings=runtime_settings,
        broker_factory=broker_factory,
    )


@router.get("/status", response_model=BrokerSyncWatchdogStatusResponse)
def get_broker_sync_watchdog_status(
    provider: Literal["kis"] = Query(default="kis"),
    market: Literal["KR"] = Query(default="KR"),
    db: Session = Depends(get_db),
    service: BrokerSyncWatchdogService = Depends(get_broker_sync_watchdog_service),
):
    try:
        return service.status(db, provider=provider, market=market)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/run-once", response_model=BrokerSyncWatchdogStatusResponse)
def run_broker_sync_watchdog_once(
    provider: Literal["kis"] = Query(default="kis"),
    market: Literal["KR"] = Query(default="KR"),
    db: Session = Depends(get_db),
    service: BrokerSyncWatchdogService = Depends(get_broker_sync_watchdog_service),
):
    try:
        return service.run_once(db, provider=provider, market=market)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/latest", response_model=BrokerSyncWatchdogStatusResponse)
def get_latest_broker_sync_watchdog_status(
    provider: Literal["kis"] = Query(default="kis"),
    market: Literal["KR"] = Query(default="KR"),
    db: Session = Depends(get_db),
    service: BrokerSyncWatchdogService = Depends(get_broker_sync_watchdog_service),
):
    try:
        return service.latest(db, provider=provider, market=market)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
