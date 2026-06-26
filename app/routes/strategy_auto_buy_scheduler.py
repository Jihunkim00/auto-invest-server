from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.routes.strategy_dry_run import get_profile_aware_dry_run_auto_buy_service
from app.schemas.strategy_auto_buy_scheduler import (
    StrategyAutoBuyPromotionActionResponse,
    StrategyAutoBuyPromotionMarkConvertedRequest,
    StrategyAutoBuyPromotionsResponse,
    StrategyAutoBuySchedulerRunRequest,
    StrategyAutoBuySchedulerRunResponse,
    StrategyAutoBuySchedulerStatusResponse,
)
from app.services.profile_aware_dry_run_auto_buy_service import (
    ProfileAwareDryRunAutoBuyService,
)
from app.services.strategy_auto_buy_promotion_service import (
    StrategyAutoBuyPromotionService,
)
from app.services.strategy_auto_buy_scheduler_service import (
    StrategyAutoBuySchedulerService,
)


router = APIRouter(
    prefix="/strategy/auto-buy",
    tags=["strategy-auto-buy-scheduler"],
)


def get_strategy_auto_buy_promotion_service() -> StrategyAutoBuyPromotionService:
    return StrategyAutoBuyPromotionService()


def get_strategy_auto_buy_scheduler_service(
    dry_run_service: ProfileAwareDryRunAutoBuyService = Depends(
        get_profile_aware_dry_run_auto_buy_service
    ),
    promotion_service: StrategyAutoBuyPromotionService = Depends(
        get_strategy_auto_buy_promotion_service
    ),
) -> StrategyAutoBuySchedulerService:
    return StrategyAutoBuySchedulerService(
        dry_run_service=dry_run_service,
        promotion_service=promotion_service,
    )


@router.get("/scheduler/status", response_model=StrategyAutoBuySchedulerStatusResponse)
def get_strategy_auto_buy_scheduler_status(
    provider: str = Query(default="kis", max_length=20),
    market: str = Query(default="KR", max_length=10),
    db: Session = Depends(get_db),
    service: StrategyAutoBuySchedulerService = Depends(
        get_strategy_auto_buy_scheduler_service
    ),
):
    return service.status(db, provider=provider, market=market)


@router.post(
    "/scheduler/run-dry-run-once",
    response_model=StrategyAutoBuySchedulerRunResponse,
)
def run_strategy_auto_buy_scheduler_dry_run_once(
    payload: StrategyAutoBuySchedulerRunRequest | None = None,
    db: Session = Depends(get_db),
    service: StrategyAutoBuySchedulerService = Depends(
        get_strategy_auto_buy_scheduler_service
    ),
):
    return service.run_dry_run_once(db, payload)


@router.get("/promotions", response_model=StrategyAutoBuyPromotionsResponse)
def get_strategy_auto_buy_promotions(
    provider: str = Query(default="kis", max_length=20),
    market: str = Query(default="KR", max_length=10),
    status: str | None = Query(default=None, max_length=40),
    symbol: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    service: StrategyAutoBuyPromotionService = Depends(
        get_strategy_auto_buy_promotion_service
    ),
):
    return service.list(
        db,
        provider=provider,
        market=market,
        status=status,
        symbol=symbol,
        limit=limit,
    )


@router.post(
    "/promotions/{promotion_id}/acknowledge",
    response_model=StrategyAutoBuyPromotionActionResponse,
)
def acknowledge_strategy_auto_buy_promotion(
    promotion_id: int,
    db: Session = Depends(get_db),
    service: StrategyAutoBuyPromotionService = Depends(
        get_strategy_auto_buy_promotion_service
    ),
):
    try:
        return service.acknowledge(db, promotion_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/promotions/{promotion_id}/dismiss",
    response_model=StrategyAutoBuyPromotionActionResponse,
)
def dismiss_strategy_auto_buy_promotion(
    promotion_id: int,
    db: Session = Depends(get_db),
    service: StrategyAutoBuyPromotionService = Depends(
        get_strategy_auto_buy_promotion_service
    ),
):
    try:
        return service.dismiss(db, promotion_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/promotions/{promotion_id}/mark-converted",
    response_model=StrategyAutoBuyPromotionActionResponse,
)
def mark_strategy_auto_buy_promotion_converted(
    promotion_id: int,
    payload: StrategyAutoBuyPromotionMarkConvertedRequest,
    db: Session = Depends(get_db),
    service: StrategyAutoBuyPromotionService = Depends(
        get_strategy_auto_buy_promotion_service
    ),
):
    try:
        return service.mark_converted(
            db,
            promotion_id,
            promoted_to_live_attempt_id=payload.promoted_to_live_attempt_id,
            related_live_order_id=payload.related_live_order_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

