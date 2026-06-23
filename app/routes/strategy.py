from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.strategy import StrategyProfileApplyRequest
from app.services.strategy_profile_service import (
    StrategyProfileAckRequired,
    StrategyProfileNotFound,
    StrategyProfileService,
)


router = APIRouter(prefix="/strategy", tags=["strategy"])


def get_strategy_profile_service() -> StrategyProfileService:
    return StrategyProfileService()


@router.get("/profiles")
def list_strategy_profiles(
    db: Session = Depends(get_db),
    service: StrategyProfileService = Depends(get_strategy_profile_service),
):
    return service.list_profiles(db)


@router.get("/profiles/active")
def get_active_strategy_profile(
    db: Session = Depends(get_db),
    service: StrategyProfileService = Depends(get_strategy_profile_service),
):
    return {"active_profile": service.serialize_profile(service.active_profile(db))}


@router.post("/profiles/apply-preset")
def apply_strategy_profile_preset(
    payload: StrategyProfileApplyRequest,
    db: Session = Depends(get_db),
    service: StrategyProfileService = Depends(get_strategy_profile_service),
):
    try:
        return service.apply_preset(
            db,
            profile_name=payload.profile_name,
            confirm_operator_ack=payload.confirm_operator_ack,
            source=payload.source,
        )
    except StrategyProfileAckRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StrategyProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="strategy_profile_not_found") from exc


@router.get("/monthly-progress")
def get_strategy_monthly_progress(
    db: Session = Depends(get_db),
    service: StrategyProfileService = Depends(get_strategy_profile_service),
):
    return service.monthly_progress(db)


@router.get("/risk-budget")
def get_strategy_risk_budget(
    db: Session = Depends(get_db),
    service: StrategyProfileService = Depends(get_strategy_profile_service),
):
    return service.risk_budget(db)

