from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_broker import KisBroker
from app.brokers.kis_client import KisClient
from app.config import get_settings
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
from app.schemas.automation_mode_control import (
    AutomationModeOffRequest,
    AutomationModeSetRequest,
    AutomationModeStatusResponse,
)
from app.services.automation_mode_control_service import (
    AutomationModeAcknowledgementRequired,
    AutomationModeControlService,
)
from app.services.auto_buy_live_phase1_service import AutoBuyLivePhase1Service
from app.services.auto_sell_live_phase1_service import AutoSellLivePhase1Service
from app.services.broker_sync_watchdog_service import BrokerSyncWatchdogService
from app.services.ops_production_readiness_service import OpsProductionReadinessService
from app.services.portfolio_orchestrator_service import PortfolioOrchestratorService
from app.services.position_management_dry_run_service import PositionManagementDryRunService
from app.services.runtime_setting_service import RuntimeSettingService


router = APIRouter(tags=["automation"])
portfolio_router = APIRouter(
    prefix="/automation/portfolio",
    tags=["portfolio-automation"],
)
mode_router = APIRouter(
    prefix="/automation/mode",
    tags=["automation-mode"],
)


def get_portfolio_orchestrator_service(
    db: Session = Depends(get_db),
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

    def broker_factory(session: Session):
        settings = get_settings()
        return KisBroker(KisClient(settings, KisAuthManager(settings, session)))

    return PortfolioOrchestratorService(
        runtime_settings=runtime_settings,
        readiness_service=OpsProductionReadinessService(
            runtime_settings=runtime_settings
        ),
        position_management_service=position_management_service,
        auto_sell_service=auto_sell_service,
        auto_buy_service=auto_buy_service,
        broker_sync_watchdog_service=BrokerSyncWatchdogService(
            runtime_settings=runtime_settings,
            broker_factory=broker_factory,
        ),
    )


def get_automation_mode_control_service(
    db: Session = Depends(get_db),
) -> AutomationModeControlService:
    runtime_settings = RuntimeSettingService()

    def broker_factory(session: Session):
        settings = get_settings()
        return KisBroker(KisClient(settings, KisAuthManager(settings, session)))

    return AutomationModeControlService(
        runtime_settings=runtime_settings,
        readiness_service=OpsProductionReadinessService(
            runtime_settings=runtime_settings
        ),
        broker_sync_watchdog_service=BrokerSyncWatchdogService(
            runtime_settings=runtime_settings,
            broker_factory=broker_factory,
        ),
    )


@mode_router.get("/status", response_model=AutomationModeStatusResponse)
def get_automation_mode_status(
    db: Session = Depends(get_db),
    service: AutomationModeControlService = Depends(
        get_automation_mode_control_service
    ),
):
    try:
        return service.status(db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@mode_router.post("/set", response_model=AutomationModeStatusResponse)
def set_automation_mode(
    payload: AutomationModeSetRequest,
    db: Session = Depends(get_db),
    service: AutomationModeControlService = Depends(
        get_automation_mode_control_service
    ),
):
    try:
        return service.set_mode(
            db,
            automation_mode=payload.automation_mode,
            reason=payload.reason,
            operator_acknowledged_risks=payload.operator_acknowledged_risks,
            updated_by="api",
        )
    except AutomationModeAcknowledgementRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@mode_router.post("/off", response_model=AutomationModeStatusResponse)
def turn_automation_mode_off(
    payload: AutomationModeOffRequest | None = None,
    db: Session = Depends(get_db),
    service: AutomationModeControlService = Depends(
        get_automation_mode_control_service
    ),
):
    return service.turn_off(
        db,
        reason=(payload.reason if payload else None),
        updated_by="api",
    )


@portfolio_router.post("/run-once", response_model=PortfolioOrchestratorResponse)
def run_portfolio_orchestrator_once(
    payload: PortfolioOrchestratorRunRequest | None = None,
    db: Session = Depends(get_db),
    service: PortfolioOrchestratorService = Depends(
        get_portfolio_orchestrator_service
    ),
):
    return service.run_once(db, payload)


@portfolio_router.get("/latest", response_model=PortfolioOrchestratorResponse)
def get_latest_portfolio_orchestrator_run(
    provider: Literal["kis"] = Query(default="kis"),
    market: Literal["KR"] = Query(default="KR"),
    db: Session = Depends(get_db),
    service: PortfolioOrchestratorService = Depends(
        get_portfolio_orchestrator_service
    ),
):
    return service.latest(db, provider=provider, market=market)


router.include_router(mode_router)
router.include_router(portfolio_router)
