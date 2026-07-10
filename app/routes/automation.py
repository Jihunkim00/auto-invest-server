from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.routes.strategy_auto_buy_scheduler import get_auto_buy_live_phase1_service
from app.routes.strategy_positions import (
    get_auto_sell_live_phase1_service,
    get_position_management_dry_run_service,
)
from app.schemas.portfolio_orchestrator import (
    PortfolioOrchestratorResponse,
    PortfolioOrchestratorRunRequest,
)
from app.services.auto_buy_live_phase1_service import AutoBuyLivePhase1Service
from app.services.auto_sell_live_phase1_service import AutoSellLivePhase1Service
from app.services.ops_production_readiness_service import OpsProductionReadinessService
from app.services.portfolio_orchestrator_service import PortfolioOrchestratorService
from app.services.position_management_dry_run_service import PositionManagementDryRunService
from app.services.runtime_setting_service import RuntimeSettingService


router = APIRouter(prefix="/automation/portfolio", tags=["portfolio-automation"])


def get_portfolio_orchestrator_service(
    position_management_service: PositionManagementDryRunService = Depends(
        get_position_management_dry_run_service
    ),
    auto_sell_service: AutoSellLivePhase1Service = Depends(
        get_auto_sell_live_phase1_service
    ),
    auto_buy_service: AutoBuyLivePhase1Service = Depends(
        get_auto_buy_live_phase1_service
    ),
) -> PortfolioOrchestratorService:
    runtime_settings = RuntimeSettingService()
    return PortfolioOrchestratorService(
        runtime_settings=runtime_settings,
        readiness_service=OpsProductionReadinessService(
            runtime_settings=runtime_settings
        ),
        position_management_service=position_management_service,
        auto_sell_service=auto_sell_service,
        auto_buy_service=auto_buy_service,
    )


@router.post("/run-once", response_model=PortfolioOrchestratorResponse)
def run_portfolio_orchestrator_once(
    payload: PortfolioOrchestratorRunRequest | None = None,
    db: Session = Depends(get_db),
    service: PortfolioOrchestratorService = Depends(
        get_portfolio_orchestrator_service
    ),
):
    return service.run_once(db, payload)


@router.get("/latest", response_model=PortfolioOrchestratorResponse)
def get_latest_portfolio_orchestrator_run(
    provider: Literal["kis"] = Query(default="kis"),
    market: Literal["KR"] = Query(default="KR"),
    db: Session = Depends(get_db),
    service: PortfolioOrchestratorService = Depends(
        get_portfolio_orchestrator_service
    ),
):
    return service.latest(db, provider=provider, market=market)
