from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings as get_app_settings
from app.db.database import get_db
from app.services.ops_production_readiness_service import (
    OpsProductionReadinessService,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.trading_orchestrator_service import TradingOrchestratorService
from app.services.trading_service import TradingService

router = APIRouter(prefix="/ops", tags=["ops"])


class RuntimeSettingsUpdateRequest(BaseModel):
    bot_enabled: bool | None = None
    dry_run: bool | None = None
    kill_switch: bool | None = None
    scheduler_enabled: bool | None = None
    us_scheduler_enabled: bool | None = None
    kr_scheduler_enabled: bool | None = None
    kr_scheduler_mode: Literal[
        "disabled",
        "dry_run",
        "sell_only_live",
        "full_live_test",
    ] | None = None
    default_symbol: str | None = Field(default=None, min_length=1, max_length=20)
    default_gate_level: int | None = Field(default=None, ge=1, le=4)
    max_trades_per_day: int | None = Field(default=None, ge=1, le=20)
    max_live_orders_per_day: int | None = Field(default=None, ge=0, le=20)
    max_positions: int | None = Field(default=None, ge=1, le=100)
    max_position_pct: float | None = Field(default=None, ge=0, le=1)
    max_order_notional_pct: float | None = Field(default=None, ge=0, le=1)
    daily_max_loss_pct: float | None = Field(default=None, ge=0, le=1)
    kr_no_new_entry_after: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    us_no_new_entry_after: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    no_new_entry_after: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    stop_loss_enabled: bool | None = None
    stop_loss_pct: float | None = Field(default=None, ge=0, le=1)
    take_profit_enabled: bool | None = None
    take_profit_pct: float | None = Field(default=None, ge=0, le=1)
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
    kis_limited_auto_sell_enabled: bool | None = None
    kis_limited_auto_stop_loss_enabled: bool | None = None
    kis_limited_auto_sell_stop_loss_enabled: bool | None = None
    kis_limited_auto_sell_take_profit_enabled: bool | None = None
    kis_limited_auto_take_profit_enabled: bool | None = None
    kis_limited_auto_sell_requires_queue_review: bool | None = None
    kis_limited_auto_sell_max_orders_per_day: int | None = Field(default=None, ge=1, le=20)
    kis_limited_auto_sell_max_notional_pct: float | None = Field(default=None, gt=0, le=1)
    kis_limited_auto_sell_min_shadow_occurrences: int | None = Field(default=None, ge=0, le=50)
    kis_limited_auto_sell_allow_manual_review_trigger: bool | None = None
    kis_limited_auto_sell_allow_take_profit_trigger: bool | None = None
    kis_limited_auto_buy_enabled: bool | None = None
    kis_limited_auto_buy_readiness_enabled: bool | None = None
    kis_limited_auto_buy_shadow_enabled: bool | None = None
    kis_limited_auto_buy_requires_shadow_review: bool | None = None
    kis_limited_auto_buy_max_orders_per_day: int | None = Field(default=None, ge=1, le=20)
    kis_limited_auto_buy_max_notional_pct: float | None = Field(default=None, gt=0, le=1)
    kis_limited_auto_buy_min_cash_buffer_krw: float | None = Field(default=None, ge=0)
    kis_limited_auto_buy_requires_existing_sell_guards: bool | None = None
    kis_limited_auto_buy_min_final_score: float | None = Field(default=None, ge=0, le=100)
    kis_limited_auto_buy_min_confidence: float | None = Field(default=None, ge=0, le=1)
    kis_limited_auto_buy_max_positions: int | None = Field(default=None, ge=0, le=100)
    kis_limited_auto_buy_block_if_position_exists: bool | None = None
    kis_limited_auto_buy_block_if_open_order_exists: bool | None = None
    kis_limited_auto_buy_allow_reentry_same_day: bool | None = None
    kis_limited_auto_buy_require_market_open: bool | None = None
    kis_limited_auto_buy_no_new_entry_after: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    kis_limited_auto_buy_allow_gpt_hard_block: bool | None = None
    strategy_live_auto_buy_enabled: bool | None = None
    strategy_live_auto_buy_requires_recent_dry_run: bool | None = None
    strategy_live_auto_buy_recent_dry_run_ttl_minutes: int | None = Field(default=None, ge=1, le=1440)
    strategy_live_auto_buy_max_orders_per_day: int | None = Field(default=None, ge=0, le=20)
    strategy_live_auto_buy_max_notional_krw: float | None = Field(default=None, ge=0)
    strategy_live_auto_buy_max_notional_pct: float | None = Field(default=None, ge=0, le=1)
    strategy_live_auto_buy_allowed_profiles: list[str] | None = None
    strategy_live_auto_buy_allow_aggressive: bool | None = None
    strategy_live_auto_buy_requires_operator_confirm: bool | None = None
    strategy_live_auto_buy_block_after_loss_limit: bool | None = None
    strategy_live_auto_buy_block_after_target_hit: bool | None = None
    strategy_live_auto_buy_scheduler_enabled: bool | None = None
    kis_scheduler_enabled: bool | None = None
    kis_scheduler_dry_run: bool | None = None
    kis_scheduler_live_enabled: bool | None = None
    kis_scheduler_allow_real_orders: bool | None = None
    kis_scheduler_configured_allow_real_orders: bool | None = None
    kis_scheduler_buy_enabled: bool | None = None
    kis_scheduler_sell_enabled: bool | None = None
    kis_scheduler_allow_limited_auto_buy: bool | None = None
    kis_scheduler_allow_limited_auto_sell: bool | None = None
    kis_scheduler_max_live_orders_per_day: int | None = Field(default=None, ge=0, le=20)
    kis_scheduler_live_requires_dry_run_false: bool | None = None
    kis_scheduler_live_respect_kill_switch: bool | None = None


class ApplyPresetRequest(BaseModel):
    preset: Literal[
        "safe_mode",
        "dry_run_simulation",
        "manual_live_trading",
        "kis_sell_only_automation",
        "full_live_test_mode",
    ]
    confirm_dangerous: bool = False


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


@router.get("/settings/catalog")
def get_settings_catalog(db: Session = Depends(get_db)):
    svc = RuntimeSettingService()
    return svc.settings_catalog(db)


@router.put("/settings")
def update_settings(payload: RuntimeSettingsUpdateRequest, db: Session = Depends(get_db)):
    svc = RuntimeSettingService()
    payload_values = payload.model_dump(exclude_none=True)
    deprecation_warnings: list[dict[str, str]] = []
    if "no_new_entry_after" in payload_values:
        deprecation_warnings.append(
            {
                "key": "no_new_entry_after",
                "replacement_key": "kr_no_new_entry_after",
                "message": (
                    "no_new_entry_after is deprecated. "
                    "Use kr_no_new_entry_after instead."
                ),
            }
        )
    try:
        settings = svc.update_settings(db, payload_values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    response: dict[str, Any] = {"result": "updated", "settings": settings}
    if deprecation_warnings:
        response["deprecation_warnings"] = deprecation_warnings
        response["warning_message"] = deprecation_warnings[0]["message"]
    return response


@router.post("/settings/apply-preset")
def apply_settings_preset(
    payload: ApplyPresetRequest,
    db: Session = Depends(get_db),
):
    svc = RuntimeSettingService()
    try:
        return svc.apply_preset(
            db,
            preset=payload.preset,
            confirm_dangerous=payload.confirm_dangerous,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/production-readiness")
def get_production_readiness(
    include_raw: bool = Query(default=False),
    days: int = Query(default=7, ge=1, le=365),
    include_recent: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    client = _kis_client(db)
    service = OpsProductionReadinessService(client)
    return service.readiness(
        db,
        include_raw=include_raw,
        days=days,
        include_recent=include_recent,
    )


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


def _kis_client(db: Session) -> KisClient:
    settings = get_app_settings()
    return KisClient(settings, KisAuthManager(settings, db))
