from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.trading_orchestrator_service import TradingOrchestratorService
from app.services.trading_service import TradingService

router = APIRouter(prefix="/ops", tags=["ops"])


class RuntimeSettingsUpdateRequest(BaseModel):
    bot_enabled: bool | None = None
    dry_run: bool | None = None
    kill_switch: bool | None = None
    scheduler_enabled: bool | None = None
    default_symbol: str | None = Field(default=None, min_length=1, max_length=20)
    default_gate_level: int | None = Field(default=None, ge=1, le=4)
    max_trades_per_day: int | None = Field(default=None, ge=1, le=20)
    global_daily_entry_limit: int | None = Field(default=None, ge=0, le=20)
    per_symbol_daily_entry_limit: int | None = Field(default=None, ge=0, le=20)
    per_slot_new_entry_limit: int | None = Field(default=None, ge=0, le=20)
    max_open_positions: int | None = Field(default=None, ge=1, le=100)
    near_close_block_minutes: int | None = Field(default=None, ge=0, le=120)
    same_direction_cooldown_minutes: int | None = Field(default=None, ge=0, le=1440)
    kis_live_auto_enabled: bool | None = None
    kis_live_auto_buy_enabled: bool | None = None
    kis_live_auto_sell_enabled: bool | None = None
    kis_live_auto_requires_manual_confirm: bool | None = None
    kis_live_auto_max_orders_per_day: int | None = Field(default=None, ge=1, le=20)
    kis_live_auto_max_notional_pct: float | None = Field(default=None, gt=0, le=1)


class RunNowRequest(BaseModel):
    symbol: str | None = Field(default=None, min_length=1, max_length=20)
    gate_level: int | None = Field(default=None, ge=1, le=4)

class ManualCloseResponse(BaseModel):
    result: str
    reason: str
    symbol: str
    executed: bool
    run_id: int
    order_id: int | None = None
    order: dict[str, Any] | None = None


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    svc = RuntimeSettingService()
    return svc.get_settings(db)


@router.put("/settings")
def update_settings(payload: RuntimeSettingsUpdateRequest, db: Session = Depends(get_db)):
    svc = RuntimeSettingService()
    settings = svc.update_settings(db, payload.model_dump(exclude_none=True))
    return {"result": "updated", "settings": settings}


@router.post("/run-now")
def run_now(payload: RunNowRequest, db: Session = Depends(get_db)):
    svc = TradingOrchestratorService()
    return svc.run(
        db,
        trigger_source="manual",
        symbol=payload.symbol,
        gate_level=payload.gate_level,
        request_payload=payload.model_dump(exclude_none=True),
    )

@router.post("/positions/{symbol}/close", response_model=ManualCloseResponse)
def manual_close_position(symbol: str, db: Session = Depends(get_db)):
    svc = TradingService()
    return svc.manual_close_position(db, symbol=symbol, trigger_source="manual_close")

@router.get("/runs")
def list_runs(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    svc = TradingOrchestratorService()
    rows = svc.list_runs(db, limit=limit, symbol=symbol)
    return {"count": len(rows), "runs": rows}


@router.post("/bot/on")
def bot_on(db: Session = Depends(get_db)):
    svc = RuntimeSettingService()
    return {"result": "updated", "settings": svc.set_bot_enabled(db, True)}


@router.post("/bot/off")
def bot_off(db: Session = Depends(get_db)):
    svc = RuntimeSettingService()
    return {"result": "updated", "settings": svc.set_bot_enabled(db, False)}

@router.post("/scheduler/on")
def scheduler_on(db: Session = Depends(get_db)):
    svc = RuntimeSettingService()
    return {"result": "updated", "settings": svc.set_scheduler_enabled(db, True)}




@router.post("/scheduler/off")
def scheduler_off(db: Session = Depends(get_db)):
    svc = RuntimeSettingService()
    return {"result": "updated", "settings": svc.set_scheduler_enabled(db, False)}


@router.post("/kill-switch/on")
def kill_switch_on(db: Session = Depends(get_db)):
    svc = RuntimeSettingService()
    return {"result": "updated", "settings": svc.set_kill_switch(db, True)}


@router.post("/kill-switch/off")
def kill_switch_off(db: Session = Depends(get_db)):
    svc = RuntimeSettingService()
    return {"result": "updated", "settings": svc.set_kill_switch(db, False)}
