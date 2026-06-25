from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import get_db
from app.schemas.strategy_dry_run_auto_buy import (
    ProfileAwareDryRunAutoBuyRequest,
    ProfileAwareDryRunAutoBuyResponse,
    ProfileAwareDryRunRecentResponse,
    ProfileAwareDryRunSummaryResponse,
)
from app.services.kis_watchlist_preview_service import KisWatchlistPreviewService
from app.services.profile_aware_dry_run_auto_buy_service import (
    ProfileAwareDryRunAutoBuyService,
)
from app.services.strategy_risk_budget_service import StrategyRiskBudgetService
from app.services.target_aware_risk_service import TargetAwareRiskService


router = APIRouter(prefix="/strategy/dry-run", tags=["strategy-dry-run"])


def get_profile_aware_dry_run_auto_buy_service(
    db: Session = Depends(get_db),
) -> (
    ProfileAwareDryRunAutoBuyService
):
    cache: dict[str, object] = {}

    def client(session: Session) -> KisClient:
        if "client" not in cache:
            settings = get_settings()
            cache["client"] = KisClient(
                settings,
                KisAuthManager(settings, session),
            )
        return cache["client"]  # type: ignore[return-value]

    def positions(db: Session, provider: str, market: str):
        if "positions" not in cache:
            cache["positions"] = (
                client(db).list_positions()
                if provider == "kis" and market == "KR"
                else []
            )
        return cache["positions"]  # type: ignore[return-value]

    def balance(db: Session, provider: str, market: str):
        if "balance" not in cache:
            cache["balance"] = (
                client(db).get_account_balance()
                if provider == "kis" and market == "KR"
                else {}
            )
        return cache["balance"]  # type: ignore[return-value]

    risk_service = TargetAwareRiskService(
        budget_service=StrategyRiskBudgetService(
            position_loader=positions,
            balance_loader=balance,
        )
    )
    return ProfileAwareDryRunAutoBuyService(
        preview_service=KisWatchlistPreviewService(client(db), db=db),
        target_risk_service=risk_service,
    )


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
