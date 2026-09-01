from __future__ import annotations

"""Small canonical API adapters for the three trading product surfaces."""

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import get_db
from app.db.models import OrderLog, PositionLifecycle, SignalLog, TradeRunLog
from app.services.automation_execution_authority_service import (
    AutomationExecutionAuthorityService,
)
from app.services.automation_profile_service import AutomationProfileService
from app.services.kis_manual_order_service import (
    KisManualOrderService,
    KisManualOrderSubmitRequest,
)
from app.services.kis_order_validation_service import (
    KisOrderValidationRequest,
    KisOrderValidationService,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.scheduler_service import scheduler_service


router = APIRouter(tags=["canonical-trading"])


class AutomationSettingsRequest(BaseModel):
    enabled: bool | None = None
    mode: Literal["test", "paper", "live"] | None = None
    operator_acknowledged_risks: bool = False
    reason: str | None = Field(default=None, max_length=400)


class AutomationRunOnceRequest(BaseModel):
    slot: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")


def _client(db: Session) -> KisClient:
    settings = get_settings()
    return KisClient(settings, KisAuthManager(settings, db))


@router.get("/automation/status")
def automation_status(db: Session = Depends(get_db)):
    runtime = RuntimeSettingService()
    authority = AutomationExecutionAuthorityService(runtime).snapshot(db)
    profile = AutomationProfileService(runtime_settings=runtime).selected_profile_schedule(db)
    settings = runtime.get_settings_read_only(db)
    scheduler_runtime = scheduler_service.runtime_status()
    watchlist_refresh_status = {
        key: scheduler_runtime.get(key)
        for key in (
            'last_watchlist_refresh_at',
            'last_watchlist_refresh_result',
            'last_watchlist_refresh_reason',
            'source_universe_file',
            'source_universe_count',
            'source_kospi_count',
            'source_kosdaq_count',
            'configured_max_price_krw',
            'budget_max_price_krw',
            'effective_max_price_krw',
            'price_lookup_success_count',
            'price_lookup_failure_count',
            'eligible_kospi_count',
            'eligible_kosdaq_count',
            'selected_kospi_count',
            'selected_kosdaq_count',
            'final_watchlist_count',
            'max_price_in_final_watchlist',
            'over_budget_price_count',
            'watchlist_file',
            'backup_file',
            'maintenance_job_count',
        )
    }
    return {
        **watchlist_refresh_status,
        "scheduler": "AutomationSchedulerService",
        "enabled": bool(settings.get("automation_profile_scheduler_enabled")),
        "mode": authority.get("automation_mode"),
        "authority": authority,
        "active_profile": profile,
        "next_scheduled_run": scheduler_runtime.get("next_profile_run_at"),
        "latest_decision": scheduler_runtime.get("last_profile_run_result"),
        "production_trading_jobs": scheduler_runtime.get("production_trading_jobs", []),
        "production_trading_job_count": scheduler_runtime.get(
            "production_trading_job_count", 0
        ),
        "kill_switch": bool(settings.get("kill_switch")),
    }


@router.put("/automation/settings")
def update_automation_settings(
    payload: AutomationSettingsRequest,
    db: Session = Depends(get_db),
):
    if payload.mode == "live" and not payload.operator_acknowledged_risks:
        raise HTTPException(status_code=409, detail="live mode requires operator acknowledgement")
    runtime = RuntimeSettingService()
    current = runtime.get_settings_read_only(db)
    mode = payload.mode or str(current.get("automation_mode") or "test")
    enabled = bool(current.get("automation_profile_scheduler_enabled")) if payload.enabled is None else payload.enabled
    runtime.update_settings(
        db,
        {
            "automation_mode": mode,
            "automation_profile_scheduler_enabled": enabled,
            # Compatibility mirrors only; no scheduler decision reads them.
            "dry_run": mode != "live",
            "automation_mode_reason": payload.reason,
        },
    )
    return automation_status(db)


@router.post("/automation/run-once")
def automation_run_once(
    payload: AutomationRunOnceRequest | None = None,
):
    return scheduler_service.run_once(slot=(payload.slot if payload else None))


@router.get("/portfolio")
def portfolio(db: Session = Depends(get_db)):
    rows = (
        db.query(PositionLifecycle)
        .filter(PositionLifecycle.status.in_(["open", "closing"]))
        .order_by(PositionLifecycle.opened_at.desc(), PositionLifecycle.id.desc())
        .all()
    )
    return {
        "positions": [
            {
                "symbol": row.symbol,
                "qty": row.quantity,
                "average_price": row.entry_price,
                "current_price": row.last_price,
                "unrealized_pl": row.unrealized_pl,
                "unrealized_pl_pct": row.unrealized_pl_pct,
                "stop_loss_pct": row.stop_loss_threshold_pct,
                "take_profit_pct": row.take_profit_threshold_pct,
                "state": row.status,
            }
            for row in rows
        ]
    }


@router.post("/portfolio/{symbol}/analyze")
def analyze_portfolio_position(symbol: str, db: Session = Depends(get_db)):
    row = (
        db.query(PositionLifecycle)
        .filter(PositionLifecycle.symbol == symbol.upper())
        .filter(PositionLifecycle.status.in_(["open", "closing"]))
        .order_by(PositionLifecycle.id.desc())
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="position_not_found")
    return {"symbol": row.symbol, "state": row.status, "current_price": row.last_price,
            "stop_loss_pct": row.stop_loss_threshold_pct, "take_profit_pct": row.take_profit_threshold_pct}


@router.post("/trade/analyze")
def analyze_trade(payload: KisOrderValidationRequest, db: Session = Depends(get_db)):
    return KisOrderValidationService(_client(db)).validate(payload).to_dict()


def _manual_submit(payload: KisManualOrderSubmitRequest, side: str, db: Session):
    if payload.side.lower() != side:
        raise HTTPException(status_code=422, detail=f"side_must_be_{side}")
    status_code, body = KisManualOrderService(_client(db)).submit_manual(db, payload)
    if status_code >= 400:
        raise HTTPException(status_code=status_code, detail=body)
    return body


@router.post("/trade/buy")
def manual_buy(payload: KisManualOrderSubmitRequest, db: Session = Depends(get_db)):
    return _manual_submit(payload, "buy", db)


@router.post("/trade/sell")
def manual_sell(payload: KisManualOrderSubmitRequest, db: Session = Depends(get_db)):
    return _manual_submit(payload, "sell", db)
