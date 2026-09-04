from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import get_db
from app.services.quant_ab_evaluation_service import QuantABEvaluationService
from app.services.quant_ab_outcome_label_service import QuantABOutcomeLabelService

router = APIRouter(prefix="/quant-ab", tags=["quant-ab-analytics"])


@router.post("/outcomes/label-mature")
def label_mature_quant_ab_outcomes(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Label mature observations using read-only KIS market data."""
    settings = get_settings()
    client = KisClient(settings, KisAuthManager(settings, db))
    service = QuantABOutcomeLabelService(client=client)
    # The service catches per-observation market-data failures and never calls
    # order, risk, or execution code.
    return service.label_mature_observations(db, limit=limit)


@router.get("/outcomes/recent")
def get_recent_quant_ab_outcomes(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    min_data_quality: float = Query(default=0.0, ge=0.0, le=1.0),
    trigger_source: str | None = Query(default=None),
    decision_slot: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return QuantABEvaluationService().recent(
        db,
        start_date=start_date,
        end_date=end_date,
        min_data_quality=min_data_quality,
        trigger_source=trigger_source,
        decision_slot=decision_slot,
        limit=limit,
    )


@router.get("/evaluation/summary")
def get_quant_ab_evaluation_summary(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    min_data_quality: float = Query(default=0.0, ge=0.0, le=1.0),
    trigger_source: str | None = Query(default=None),
    decision_slot: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return QuantABEvaluationService().summary(
        db,
        start_date=start_date,
        end_date=end_date,
        min_data_quality=min_data_quality,
        trigger_source=trigger_source,
        decision_slot=decision_slot,
    )


@router.get("/evaluation/score-buckets")
def get_quant_ab_score_buckets(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    min_data_quality: float = Query(default=0.0, ge=0.0, le=1.0),
    trigger_source: str | None = Query(default=None),
    decision_slot: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return QuantABEvaluationService().score_buckets(
        db,
        start_date=start_date,
        end_date=end_date,
        min_data_quality=min_data_quality,
        trigger_source=trigger_source,
        decision_slot=decision_slot,
    )
