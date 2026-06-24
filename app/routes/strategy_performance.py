from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import get_db
from app.schemas.strategy_performance import StrategyPerformanceSnapshotRequest
from app.services.strategy_performance_service import StrategyPerformanceService


router = APIRouter(prefix="/performance", tags=["strategy-performance"])


def _position_loader(db: Session, provider: str, market: str):
    if provider != "kis" or market != "KR":
        return []
    settings = get_settings()
    client = KisClient(settings, KisAuthManager(settings, db))
    if not client.is_configured():
        return []
    return client.list_positions()


def get_strategy_performance_service() -> StrategyPerformanceService:
    return StrategyPerformanceService(position_loader=_position_loader)


@router.get("/daily")
def get_daily_performance(
    provider: str = Query(default="kis", max_length=20),
    market: str = Query(default="KR", max_length=10),
    date_value: date | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
    service: StrategyPerformanceService = Depends(get_strategy_performance_service),
):
    return service.daily(
        db,
        provider=provider,
        market=market,
        date_value=date_value,
    )


@router.get("/monthly")
def get_monthly_performance(
    provider: str = Query(default="kis", max_length=20),
    market: str = Query(default="KR", max_length=10),
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    profile_name: str | None = Query(default=None, max_length=40),
    db: Session = Depends(get_db),
    service: StrategyPerformanceService = Depends(get_strategy_performance_service),
):
    return service.monthly(
        db,
        provider=provider,
        market=market,
        month=month,
        profile_name=profile_name,
    )


@router.get("/trades")
def get_trade_performance(
    provider: str = Query(default="kis", max_length=20),
    market: str = Query(default="KR", max_length=10),
    symbol: str | None = Query(default=None, max_length=20),
    status: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    service: StrategyPerformanceService = Depends(get_strategy_performance_service),
):
    return service.trades(
        db,
        provider=provider,
        market=market,
        symbol=symbol,
        status=status,
        limit=limit,
    )


@router.post("/snapshot")
def create_performance_snapshot(
    payload: StrategyPerformanceSnapshotRequest,
    db: Session = Depends(get_db),
    service: StrategyPerformanceService = Depends(get_strategy_performance_service),
):
    try:
        return service.snapshot(
            db,
            provider=payload.provider,
            market=payload.market,
            period_type=payload.period_type,
            period_key=payload.period_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
