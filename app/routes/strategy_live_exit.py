from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import get_db
from app.schemas.strategy_live_auto_exit import (
    ProfileAwareGuardedLiveAutoExitReadinessResponse,
    ProfileAwareGuardedLiveAutoExitRecentResponse,
    ProfileAwareGuardedLiveAutoExitRunRequest,
    ProfileAwareGuardedLiveAutoExitRunResponse,
)
from app.services.profile_aware_guarded_live_auto_exit_service import (
    ProfileAwareGuardedLiveAutoExitService,
)


router = APIRouter(prefix="/strategy/live", tags=["strategy-live"])


def get_profile_aware_guarded_live_auto_exit_service(
    db: Session = Depends(get_db),
) -> ProfileAwareGuardedLiveAutoExitService:
    cache: dict[str, object] = {}

    def client(session: Session) -> KisClient:
        if "client" not in cache:
            settings = get_settings()
            cache["client"] = KisClient(
                settings,
                KisAuthManager(settings, session),
            )
        return cache["client"]  # type: ignore[return-value]

    def positions(session: Session) -> list[dict]:
        if "positions" not in cache:
            cache["positions"] = client(session).list_positions()
        return cache["positions"]  # type: ignore[return-value]

    def open_orders(session: Session) -> list[dict]:
        if "open_orders" not in cache:
            cache["open_orders"] = client(session).list_open_orders()
        return cache["open_orders"]  # type: ignore[return-value]

    kis_client = client(db)
    return ProfileAwareGuardedLiveAutoExitService(
        client=kis_client,
        positions_loader=positions,
        open_orders_loader=open_orders,
    )


@router.get(
    "/auto-exit/readiness",
    response_model=ProfileAwareGuardedLiveAutoExitReadinessResponse,
)
def get_guarded_live_auto_exit_readiness(
    provider: str = Query(default="kis", max_length=20),
    market: str = Query(default="KR", max_length=10),
    symbol: str | None = Query(default=None, max_length=20),
    db: Session = Depends(get_db),
    service: ProfileAwareGuardedLiveAutoExitService = Depends(
        get_profile_aware_guarded_live_auto_exit_service
    ),
):
    return service.readiness(
        db,
        provider=provider,
        market=market,
        symbol=symbol,
    )


@router.post(
    "/auto-exit/run-once",
    response_model=ProfileAwareGuardedLiveAutoExitRunResponse,
)
def run_guarded_live_auto_exit_once(
    payload: ProfileAwareGuardedLiveAutoExitRunRequest,
    db: Session = Depends(get_db),
    service: ProfileAwareGuardedLiveAutoExitService = Depends(
        get_profile_aware_guarded_live_auto_exit_service
    ),
):
    return service.run_once(db, payload)


@router.get(
    "/auto-exit/recent",
    response_model=ProfileAwareGuardedLiveAutoExitRecentResponse,
)
def get_guarded_live_auto_exit_recent(
    provider: str = Query(default="kis", max_length=20),
    market: str = Query(default="KR", max_length=10),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    service: ProfileAwareGuardedLiveAutoExitService = Depends(
        get_profile_aware_guarded_live_auto_exit_service
    ),
):
    return service.recent(db, provider=provider, market=market, limit=limit)


@router.post(
    "/auto-exit/{attempt_id}/sync",
    response_model=ProfileAwareGuardedLiveAutoExitRunResponse,
)
def sync_guarded_live_auto_exit_attempt(
    attempt_id: int,
    db: Session = Depends(get_db),
    service: ProfileAwareGuardedLiveAutoExitService = Depends(
        get_profile_aware_guarded_live_auto_exit_service
    ),
):
    try:
        return service.sync_attempt(db, attempt_id)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not_found" in message else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
