from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import get_db
from app.schemas.strategy_live_auto_buy import (
    ProfileAwareGuardedLiveAutoBuyReadinessResponse,
    ProfileAwareGuardedLiveAutoBuyRecentResponse,
    ProfileAwareGuardedLiveAutoBuyRunRequest,
    ProfileAwareGuardedLiveAutoBuyRunResponse,
)
from app.services.profile_aware_guarded_live_auto_buy_service import (
    ProfileAwareGuardedLiveAutoBuyService,
)
from app.services.strategy_risk_budget_service import StrategyRiskBudgetService
from app.services.target_aware_risk_service import TargetAwareRiskService


router = APIRouter(prefix="/strategy/live", tags=["strategy-live"])


def get_profile_aware_guarded_live_auto_buy_service(
    db: Session = Depends(get_db),
) -> ProfileAwareGuardedLiveAutoBuyService:
    cache: dict[str, object] = {}

    def client(session: Session) -> KisClient:
        if "client" not in cache:
            settings = get_settings()
            cache["client"] = KisClient(
                settings,
                KisAuthManager(settings, session),
            )
        return cache["client"]  # type: ignore[return-value]

    def positions(session: Session, provider: str, market: str):
        if "positions" not in cache:
            cache["positions"] = (
                client(session).list_positions()
                if provider == "kis" and market == "KR"
                else []
            )
        return cache["positions"]  # type: ignore[return-value]

    def balance(session: Session, provider: str, market: str):
        if "balance" not in cache:
            cache["balance"] = (
                client(session).get_account_balance()
                if provider == "kis" and market == "KR"
                else {}
            )
        return cache["balance"]  # type: ignore[return-value]

    kis_client = client(db)
    target_risk = TargetAwareRiskService(
        budget_service=StrategyRiskBudgetService(
            position_loader=positions,
            balance_loader=balance,
        )
    )
    return ProfileAwareGuardedLiveAutoBuyService(
        client=kis_client,
        target_risk_service=target_risk,
        positions_loader=lambda session: positions(session, "kis", "KR"),
        balance_loader=lambda session: balance(session, "kis", "KR"),
        open_orders_loader=lambda session: kis_client.list_open_orders(),
    )


@router.get(
    "/auto-buy/readiness",
    response_model=ProfileAwareGuardedLiveAutoBuyReadinessResponse,
)
def get_guarded_live_auto_buy_readiness(
    provider: str = Query(default="kis", max_length=20),
    market: str = Query(default="KR", max_length=10),
    symbol: str | None = Query(default=None, max_length=20),
    source_dry_run_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    service: ProfileAwareGuardedLiveAutoBuyService = Depends(
        get_profile_aware_guarded_live_auto_buy_service
    ),
):
    return service.readiness(
        db,
        provider=provider,
        market=market,
        symbol=symbol,
        source_dry_run_id=source_dry_run_id,
    )


@router.post(
    "/auto-buy/run-once",
    response_model=ProfileAwareGuardedLiveAutoBuyRunResponse,
)
def run_guarded_live_auto_buy_once(
    payload: ProfileAwareGuardedLiveAutoBuyRunRequest,
    db: Session = Depends(get_db),
    service: ProfileAwareGuardedLiveAutoBuyService = Depends(
        get_profile_aware_guarded_live_auto_buy_service
    ),
):
    return service.run_once(db, payload)


@router.get(
    "/auto-buy/recent",
    response_model=ProfileAwareGuardedLiveAutoBuyRecentResponse,
)
def get_guarded_live_auto_buy_recent(
    provider: str = Query(default="kis", max_length=20),
    market: str = Query(default="KR", max_length=10),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    service: ProfileAwareGuardedLiveAutoBuyService = Depends(
        get_profile_aware_guarded_live_auto_buy_service
    ),
):
    return service.recent(db, provider=provider, market=market, limit=limit)


@router.post(
    "/auto-buy/{attempt_id}/sync",
    response_model=ProfileAwareGuardedLiveAutoBuyRunResponse,
)
def sync_guarded_live_auto_buy_attempt(
    attempt_id: int,
    db: Session = Depends(get_db),
    service: ProfileAwareGuardedLiveAutoBuyService = Depends(
        get_profile_aware_guarded_live_auto_buy_service
    ),
):
    try:
        return service.sync_attempt(db, attempt_id)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not_found" in message else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
