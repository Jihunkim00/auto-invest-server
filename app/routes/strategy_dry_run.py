from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.strategy_dry_run_auto_buy import (
    ProfileAwareDryRunAutoBuyRequest,
    ProfileAwareDryRunAutoBuyResponse,
    ProfileAwareDryRunRecentResponse,
    ProfileAwareDryRunSummaryResponse,
)
from app.services.profile_aware_dry_run_auto_buy_service import (
    ProfileAwareDryRunAutoBuyService,
)
from app.services.profile_aware_dry_run_auto_buy_factory import (
    build_profile_aware_dry_run_auto_buy_service,
)


router = APIRouter(prefix="/strategy/dry-run", tags=["strategy-dry-run"])


def get_profile_aware_dry_run_auto_buy_service(
    db: Session = Depends(get_db),
) -> (
    ProfileAwareDryRunAutoBuyService
):
    return build_profile_aware_dry_run_auto_buy_service(db)


@router.post(
    "/auto-buy-once",
    response_model=ProfileAwareDryRunAutoBuyResponse,
)
def run_profile_aware_dry_run_auto_buy(
    payload: ProfileAwareDryRunAutoBuyRequest,
    db: Session = Depends(get_db),
    service: ProfileAwareDryRunAutoBuyService = Depends(
        get_profile_aware_dry_run_auto_buy_service
    ),
):
    return service.run_once(db, payload)


@router.get("/recent", response_model=ProfileAwareDryRunRecentResponse)
def get_profile_aware_dry_run_recent(
    provider: str = Query(default="kis", max_length=20),
    market: str = Query(default="KR", max_length=10),
    profile_name: str | None = Query(default=None, max_length=40),
    symbol: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    service: ProfileAwareDryRunAutoBuyService = Depends(
        get_profile_aware_dry_run_auto_buy_service
    ),
):
    return service.recent(
        db,
        provider=provider,
        market=market,
        profile_name=profile_name,
        symbol=symbol,
        limit=limit,
    )


@router.get("/summary", response_model=ProfileAwareDryRunSummaryResponse)
def get_profile_aware_dry_run_summary(
    provider: str = Query(default="kis", max_length=20),
    market: str = Query(default="KR", max_length=10),
    db: Session = Depends(get_db),
    service: ProfileAwareDryRunAutoBuyService = Depends(
        get_profile_aware_dry_run_auto_buy_service
    ),
):
    return service.summary(db, provider=provider, market=market)
