from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import get_db
from app.schemas.strategy_risk import (
    StrategyEntryRiskEvaluationRequest,
    StrategyEntryRiskEvaluationResponse,
    StrategyRiskStateResponse,
)
from app.services.strategy_risk_budget_service import StrategyRiskBudgetService
from app.services.target_aware_risk_service import TargetAwareRiskService


router = APIRouter(prefix="/strategy", tags=["strategy-risk"])


def get_target_aware_risk_service() -> TargetAwareRiskService:
    cache: dict[str, object] = {}

    def client(db: Session) -> KisClient | None:
        if "client" not in cache:
            settings = get_settings()
            candidate = KisClient(settings, KisAuthManager(settings, db))
            cache["client"] = candidate if candidate.is_configured() else None
        value = cache.get("client")
        return value if isinstance(value, KisClient) else None

    def positions(db: Session, provider: str, market: str):
        candidate = client(db)
        if provider != "kis" or market != "KR" or candidate is None:
            return []
        if "positions" not in cache:
            cache["positions"] = candidate.list_positions()
        value = cache.get("positions")
        return value if isinstance(value, list) else []

    def balance(db: Session, provider: str, market: str):
        candidate = client(db)
        if provider != "kis" or market != "KR" or candidate is None:
            return {}
        if "balance" not in cache:
            cache["balance"] = candidate.get_account_balance()
        value = cache.get("balance")
        return value if isinstance(value, dict) else {}

    return TargetAwareRiskService(
        budget_service=StrategyRiskBudgetService(
            position_loader=positions,
            balance_loader=balance,
        )
    )


@router.get("/risk-state", response_model=StrategyRiskStateResponse)
def get_strategy_risk_state(
    provider: str = Query(default="kis", max_length=20),
    market: str = Query(default="KR", max_length=10),
    db: Session = Depends(get_db),
    service: TargetAwareRiskService = Depends(get_target_aware_risk_service),
):
    return service.risk_state(
        db,
        provider=provider,
        market=market,
    )


@router.post(
    "/risk/evaluate-entry",
    response_model=StrategyEntryRiskEvaluationResponse,
)
def evaluate_strategy_entry_risk(
    payload: StrategyEntryRiskEvaluationRequest,
    db: Session = Depends(get_db),
    service: TargetAwareRiskService = Depends(get_target_aware_risk_service),
):
    return service.evaluate_entry(db, payload)
