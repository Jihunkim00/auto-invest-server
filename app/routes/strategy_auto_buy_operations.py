from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.routes.strategy_dry_run import get_profile_aware_dry_run_auto_buy_service
from app.routes.strategy_live import get_profile_aware_guarded_live_auto_buy_service
from app.schemas.strategy_auto_buy_operations import (
    StrategyAutoBuyOperationsStatusResponse,
)
from app.services.profile_aware_dry_run_auto_buy_service import (
    ProfileAwareDryRunAutoBuyService,
)
from app.services.profile_aware_guarded_live_auto_buy_service import (
    ProfileAwareGuardedLiveAutoBuyService,
)
from app.services.strategy_auto_buy_operations_service import (
    StrategyAutoBuyOperationsService,
)


router = APIRouter(
    prefix="/strategy/auto-buy/operations",
    tags=["strategy-auto-buy-operations"],
)


def get_strategy_auto_buy_operations_service(
    dry_run_service: ProfileAwareDryRunAutoBuyService = Depends(
        get_profile_aware_dry_run_auto_buy_service
    ),
    live_auto_buy_service: ProfileAwareGuardedLiveAutoBuyService = Depends(
        get_profile_aware_guarded_live_auto_buy_service
    ),
) -> StrategyAutoBuyOperationsService:
    return StrategyAutoBuyOperationsService(
        dry_run_service=dry_run_service,
        live_auto_buy_service=live_auto_buy_service,
    )


@router.get("/status", response_model=StrategyAutoBuyOperationsStatusResponse)
def get_strategy_auto_buy_operations_status(
    provider: str = Query(default="kis", max_length=20),
    market: str = Query(default="KR", max_length=10),
    db: Session = Depends(get_db),
    service: StrategyAutoBuyOperationsService = Depends(
        get_strategy_auto_buy_operations_service
    ),
):
    return service.status(db, provider=provider, market=market)
