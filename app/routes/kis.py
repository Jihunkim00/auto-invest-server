from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.brokers.base import KisApiError, KisAuthError, KisConfigurationError
from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.core.constants import DEFAULT_GATE_LEVEL
from app.db.models import OrderLog
from app.db.database import get_db
from app.services.kis_order_validation_service import (
    KisOrderValidationError,
    KisOrderValidationRequest,
    KisOrderValidationService,
    record_kis_order_validation,
)
from app.services.kis_manual_order_service import (
    KisManualOrderService,
    KisManualOrderSubmitRequest,
)
from app.services.kis_dry_run_auto_service import (
    MANUAL_TRIGGER_SOURCE,
    SCHEDULER_TRIGGER_SOURCE,
    KisDryRunAutoService,
)
from app.services.kis_scheduler_simulation_service import KisSchedulerSimulationService
from app.services.kis_live_exit_preflight_service import KisLiveExitPreflightService
from app.services.kis_exit_shadow_decision_service import KisExitShadowDecisionService
from app.services.kis_shadow_exit_review_service import KisShadowExitReviewService
from app.services.kis_shadow_exit_review_queue_service import (
    KisShadowExitReviewQueueService,
)
from app.services.kis_limited_auto_sell_service import KisLimitedAutoSellService
from app.services.kis_buy_shadow_decision_service import KisBuyShadowDecisionService
from app.services.kis_limited_auto_buy_service import KisLimitedAutoBuyService
from app.services.kis_limited_auto_buy_review_service import (
    KisLimitedAutoBuyReviewService,
)
from app.services.kis_limited_auto_buy_execution_review_service import (
    KisLimitedAutoBuyExecutionReviewService,
)
from app.services.kis_scheduler_live_service import KisSchedulerLiveService
from app.services.kis_scheduler_readiness_service import (
    KisSchedulerReadinessService,
)
from app.services.kis_scheduler_dry_run_orchestration_service import (
    KisSchedulerDryRunOrchestrationService,
)
from app.services.kis_single_symbol_trading_service import (
    KisSingleSymbolTradingRequest,
    KisSingleSymbolTradingService,
)
from app.services.kis_position_management_service import KisPositionManagementService
from app.services.kis_manual_cancel_service import KisManualCancelService
from app.services.kis_order_sync_service import (
    KisOrderSyncError,
    KisOrderSyncService,
    serialize_kis_order,
    summarize_kis_orders,
)
from app.services.kis_auto_readiness_service import KisAutoReadinessService
from app.services.kis_watchlist_preview_service import KisWatchlistPreviewService
from app.services.kis_watchlist_update_service import (
    KisWatchlistUpdateError,
    KisWatchlistUpdateService,
)
from app.services.market_profile_service import MarketProfileError
from app.services.market_session_service import MarketSessionError, MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService

router = APIRouter(prefix="/kis", tags=["kis"])


class KisShadowExitReviewQueueActionRequest(BaseModel):
    operator_note: str | None = None
    note: str | None = None

    def note_value(self) -> str | None:
        return self.operator_note if self.operator_note is not None else self.note


class KisSchedulerDryRunOrchestrationRequest(BaseModel):
    slot_label: str | None = None
    include_buy: bool = True
    include_sell: bool = True
    include_raw: bool = False


@router.get("/manual-order/status")
def get_kis_manual_order_status(db: Session = Depends(get_db)):
    settings = get_settings()
    runtime = RuntimeSettingService().get_settings(db)
    market_session = MarketSessionService().get_session_status("KR")
    return {
        "provider": "kis",
        "market": "KR",
        "runtime_dry_run": bool(runtime.get("dry_run", True)),
        "kill_switch": bool(runtime.get("kill_switch", False)),
        "kis_enabled": bool(getattr(settings, "kis_enabled", False)),
        "kis_real_order_enabled": bool(
            getattr(settings, "kis_real_order_enabled", False)
        ),
        "market_open": market_session.get("is_market_open") is True,
        "entry_allowed_now": market_session.get("is_entry_allowed_now") is True,
        "no_new_entry_after": market_session.get("no_new_entry_after", "15:00"),
        "market_session": {
            "market": market_session.get("market"),
            "timezone": market_session.get("timezone"),
            "is_market_open": market_session.get("is_market_open") is True,
            "is_entry_allowed_now": market_session.get("is_entry_allowed_now") is True,
            "is_near_close": market_session.get("is_near_close") is True,
            "effective_close": market_session.get("effective_close"),
            "no_new_entry_after": market_session.get("no_new_entry_after", "15:00"),
        },
    }


@router.get("/market/price/{symbol}")
def get_kis_market_price(symbol: str, db: Session = Depends(get_db)):
    client = _client(db)
    try:
        return client.get_domestic_stock_price(symbol)
    except KisConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KisAuthError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc)})
    except KisApiError as exc:
        raise HTTPException(
            status_code=502, detail={"message": str(exc), "details": exc.details}
        )


@router.get("/market/bars/{symbol}")
def get_kis_market_bars(symbol: str, limit: int = 120, db: Session = Depends(get_db)):
    client = _client(db)
    try:
        bars = client.get_domestic_daily_bars(symbol, limit=limit)
        return {
            "provider": "kis",
            "environment": client.settings.kis_env,
            "symbol": symbol.strip(),
            "count": len(bars),
            "bars": bars,
        }
    except KisConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KisAuthError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc)})
    except KisApiError as exc:
        raise HTTPException(
            status_code=502, detail={"message": str(exc), "details": exc.details}
        )


@router.get("/account/balance")
def get_kis_account_balance(db: Session = Depends(get_db)):
    client = _client(db)
    try:
        return client.get_account_balance()
    except KisConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KisAuthError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc)})
    except KisApiError as exc:
        raise HTTPException(
            status_code=502, detail={"message": str(exc), "details": exc.details}
        )


@router.get("/account/positions")
def list_kis_positions(db: Session = Depends(get_db)):
    client = _client(db)
    try:
        positions = client.list_positions()
        return {
            "provider": "kis",
            "environment": client.settings.kis_env,
            "count": len(positions),
            "positions": positions,
        }
    except KisConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KisAuthError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc)})
    except KisApiError as exc:
        raise HTTPException(
            status_code=502, detail={"message": str(exc), "details": exc.details}
        )


@router.get("/account/open-orders")
def list_kis_open_orders(db: Session = Depends(get_db)):
    client = _client(db)
    try:
        orders = client.list_open_orders()
        return {
            "provider": "kis",
            "environment": client.settings.kis_env,
            "count": len(orders),
            "orders": orders,
        }
    except KisConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KisAuthError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc)})
    except KisApiError as exc:
        raise HTTPException(
            status_code=502, detail={"message": str(exc), "details": exc.details}
        )


@router.get("/positions/manage")
def manage_kis_positions(db: Session = Depends(get_db)):
    client = _client(db)
    service = KisPositionManagementService(client)
    try:
        return service.positions_manage(db)
    except KisConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KisAuthError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc)}) from exc
    except KisApiError as exc:
        raise HTTPException(
            status_code=502, detail={"message": str(exc), "details": exc.details}
        ) from exc
    except MarketProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketSessionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/positions/{symbol}/prepare-manual-sell")
def prepare_kis_position_manual_sell(symbol: str, db: Session = Depends(get_db)):
    client = _client(db)
    service = KisPositionManagementService(client)
    try:
        return service.prepare_manual_sell(db, symbol=symbol)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KisConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KisAuthError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc)}) from exc
    except KisApiError as exc:
        raise HTTPException(
            status_code=502, detail={"message": str(exc), "details": exc.details}
        ) from exc
    except MarketProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketSessionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/orders/validate")
@router.post("/orders/dry-run")
def validate_kis_order(
    payload: KisOrderValidationRequest, db: Session = Depends(get_db)
):
    client = _client(db)
    service = KisOrderValidationService(client)
    try:
        result = service.validate(payload)
        record_kis_order_validation(db, request=payload, result=result)
        return result.to_dict()
    except KisOrderValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KisConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KisAuthError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc)}) from exc
    except KisApiError as exc:
        raise HTTPException(
            status_code=502, detail={"message": str(exc), "details": exc.details}
        ) from exc


@router.post("/orders/manual-submit")
@router.post("/orders/submit-manual")
def submit_manual_kis_order(
    payload: KisManualOrderSubmitRequest,
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisManualOrderService(client)
    status_code, body = service.submit_manual(db, payload)
    return JSONResponse(status_code=status_code, content=body)


@router.get("/orders")
def list_recent_kis_orders(
    limit: int = Query(default=20, ge=1, le=100),
    include_rejected: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisOrderSyncService(client)
    rows = service.recent_orders(db, limit=limit, include_rejected=include_rejected)
    return {
        "provider": "kis",
        "count": len(rows),
        "orders": [serialize_kis_order(row) for row in rows],
    }


@router.get("/scheduler/status")
def get_kis_scheduler_status(db: Session = Depends(get_db)):
    client = _client(db)
    service = KisSchedulerSimulationService(client)
    payload = service.status(db)
    payload["live"] = KisSchedulerLiveService(client).status(db)
    return payload


@router.get("/scheduler/readiness")
def get_kis_scheduler_readiness(
    include_modules: bool = Query(default=True),
    include_recent_runs: bool = Query(default=True),
    include_raw: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisSchedulerReadinessService(client)
    return service.readiness(
        db,
        include_modules=include_modules,
        include_recent_runs=include_recent_runs,
        include_raw=include_raw,
    )


@router.post("/scheduler/run-dry-run-orchestration-once")
def run_kis_scheduler_dry_run_orchestration_once(
    payload: KisSchedulerDryRunOrchestrationRequest | None = None,
    db: Session = Depends(get_db),
):
    request = payload or KisSchedulerDryRunOrchestrationRequest()
    client = _client(db)
    service = KisSchedulerDryRunOrchestrationService(client)
    return service.run_once(
        db,
        slot_label=request.slot_label,
        include_buy=request.include_buy,
        include_sell=request.include_sell,
        include_raw=request.include_raw,
    )


@router.get("/orders/summary")
def get_kis_order_summary(db: Session = Depends(get_db)):
    return summarize_kis_orders(db)


@router.get("/orders/{order_id}")
def get_kis_order_detail(
    order_id: int,
    include_sync_payload: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    row = db.get(OrderLog, order_id)
    if row is None or str(row.broker or "").lower() != "kis":
        raise HTTPException(status_code=404, detail="KIS order not found.")
    return serialize_kis_order(row, include_sync_payload=include_sync_payload)


@router.post("/orders/sync-open")
def sync_open_kis_orders(db: Session = Depends(get_db)):
    client = _client(db)
    service = KisOrderSyncService(client)
    rows = service.sync_open_orders(db)
    return {
        "provider": "kis",
        "count": len(rows),
        "orders": [serialize_kis_order(row) for row in rows],
    }


@router.post("/orders/{order_id}/sync")
def sync_kis_order(order_id: int, db: Session = Depends(get_db)):
    client = _client(db)
    service = KisOrderSyncService(client)
    try:
        row = service.sync_order(db, order_id)
    except KisOrderSyncError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    return serialize_kis_order(row)


@router.post("/orders/{order_id}/cancel")
def cancel_kis_order(order_id: int, db: Session = Depends(get_db)):
    client = _client(db)
    service = KisManualCancelService(client)
    status_code, body = service.cancel_order(db, order_id)
    return JSONResponse(status_code=status_code, content=body)


@router.post("/watchlist/preview")
def preview_kis_watchlist(
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisWatchlistPreviewService(client, db=db)
    try:
        return service.run_preview(
            include_gpt=True,
            gate_level=gate_level,
            record_run=True,
            trigger_source="manual_kis_preview",
        )
    except MarketProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketSessionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/watchlist/kosdaq-top50/preview")
def preview_kis_kosdaq_top50_watchlist(db: Session = Depends(get_db)):
    client = _client(db)
    service = KisWatchlistUpdateService(client)
    try:
        return service.preview_kosdaq_top50()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KisConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KisAuthError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc)}) from exc
    except KisApiError as exc:
        raise HTTPException(
            status_code=502, detail={"message": str(exc), "details": exc.details}
        ) from exc
    except MarketProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/watchlist/kosdaq-top50/update")
def update_kis_kosdaq_top50_watchlist(db: Session = Depends(get_db)):
    client = _client(db)
    service = KisWatchlistUpdateService(client)
    try:
        return service.update_kosdaq_top50()
    except KisWatchlistUpdateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KisConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KisAuthError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc)}) from exc
    except KisApiError as exc:
        raise HTTPException(
            status_code=502, detail={"message": str(exc), "details": exc.details}
        ) from exc
    except MarketProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/trading/run-once")
def run_kis_single_symbol_trading_once(
    payload: KisSingleSymbolTradingRequest,
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisSingleSymbolTradingService(client)
    try:
        return service.run_once(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketSessionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/scheduler/run-preview-once")
def run_kis_scheduler_preview_once(
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisWatchlistPreviewService(client, db=db)
    try:
        payload = service.run_preview(
            include_gpt=True,
            gate_level=gate_level,
            record_run=True,
            trigger_source="manual_scheduler_preview",
        )
        payload["trigger_source"] = "manual_scheduler_preview"
        payload["scheduler_preview_only"] = True
        payload["real_order_submitted"] = False
        return payload
    except MarketProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketSessionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/auto/dry-run-once")
def run_kis_auto_dry_run_once(
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisDryRunAutoService(client, db=db)
    try:
        return service.run_once(
            db,
            gate_level=gate_level,
            trigger_source=MANUAL_TRIGGER_SOURCE,
        )
    except MarketProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketSessionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/auto/readiness")
def get_kis_auto_readiness(db: Session = Depends(get_db)):
    client = _client(db)
    service = KisAutoReadinessService(client)
    return service.readiness(db)


@router.post("/auto/preflight-once")
def run_kis_auto_preflight_once(db: Session = Depends(get_db)):
    client = _client(db)
    service = KisAutoReadinessService(client)
    return service.preflight_once(db)


@router.post("/scheduler/run-dry-run-once")
def run_kis_scheduler_dry_run_once(
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisDryRunAutoService(client, db=db)
    try:
        return service.run_once(
            db,
            gate_level=gate_level,
            trigger_source=SCHEDULER_TRIGGER_SOURCE,
        )
    except MarketProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/scheduler/run-dry-run-auto-once")
def run_kis_scheduler_dry_run_auto_once(
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisSchedulerSimulationService(client)
    try:
        return service.run_once(
            db,
            gate_level=gate_level,
            scheduler_slot="manual_dry_run_auto_once",
            require_enabled=False,
        )
    except MarketProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketSessionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/live-exit/preflight-once")
@router.post("/scheduler/live-exit-preflight-once")
def run_kis_live_exit_preflight_once(
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisLiveExitPreflightService(client)
    return service.run_once(db, gate_level=gate_level)


@router.post("/exit-shadow/run-once")
def run_kis_exit_shadow_once(
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisExitShadowDecisionService(client)
    return service.run_once(db, gate_level=gate_level)


@router.get("/exit-shadow/review")
def get_kis_exit_shadow_review(
    limit: int = Query(default=20, ge=1, le=100),
    days: int = Query(default=30, ge=1, le=365),
    symbol: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
):
    service = KisShadowExitReviewService()
    return service.review(db, limit=limit, days=days, symbol=symbol)


@router.get("/exit-shadow/review-queue")
def get_kis_exit_shadow_review_queue(
    limit: int = Query(default=50, ge=1, le=100),
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    service = KisShadowExitReviewQueueService()
    return service.queue(db, limit=limit, days=days)


@router.post("/exit-shadow/review-queue/{queue_id}/mark-reviewed")
def mark_kis_exit_shadow_queue_item_reviewed(
    queue_id: str,
    payload: KisShadowExitReviewQueueActionRequest | None = None,
    db: Session = Depends(get_db),
):
    service = KisShadowExitReviewQueueService()
    return service.mark_reviewed(
        db,
        queue_id=queue_id,
        operator_note=payload.note_value() if payload is not None else None,
    )


@router.post("/exit-shadow/review-queue/{queue_id}/dismiss")
def dismiss_kis_exit_shadow_queue_item(
    queue_id: str,
    payload: KisShadowExitReviewQueueActionRequest | None = None,
    db: Session = Depends(get_db),
):
    service = KisShadowExitReviewQueueService()
    return service.dismiss(
        db,
        queue_id=queue_id,
        operator_note=payload.note_value() if payload is not None else None,
    )


@router.post("/limited-auto-sell/run-once")
def run_kis_limited_auto_sell_once(db: Session = Depends(get_db)):
    client = _client(db)
    service = KisLimitedAutoSellService(client)
    return service.run_once(db)


@router.get("/limited-auto-sell/status")
def get_kis_limited_auto_sell_status(db: Session = Depends(get_db)):
    client = _client(db)
    service = KisLimitedAutoSellService(client)
    return service.status(db)


@router.post("/limited-auto-sell/preflight-once")
def run_kis_limited_auto_sell_preflight_once(db: Session = Depends(get_db)):
    client = _client(db)
    service = KisLimitedAutoSellService(client)
    return service.preflight_once(db)


@router.post("/limited-auto-buy/run-once")
def run_kis_limited_auto_buy_once(
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisLimitedAutoBuyService(client)
    return service.run_once(db, gate_level=gate_level)


@router.get("/limited-auto-buy/review")
def get_kis_limited_auto_buy_review(
    limit: int = Query(default=20, ge=1, le=100),
    days: int = Query(default=30, ge=1, le=365),
    symbol: str | None = Query(default=None),
    include_raw: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    service = KisLimitedAutoBuyReviewService()
    return service.review(
        db,
        limit=limit,
        days=days,
        symbol=symbol,
        include_raw=include_raw,
    )


@router.get("/limited-auto-buy/execution-review")
def get_kis_limited_auto_buy_execution_review(
    limit: int = Query(default=20, ge=1, le=100),
    days: int = Query(default=30, ge=1, le=365),
    symbol: str | None = Query(default=None),
    include_raw: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    service = KisLimitedAutoBuyExecutionReviewService()
    return service.review(
        db,
        limit=limit,
        days=days,
        symbol=symbol,
        include_raw=include_raw,
    )


@router.get("/limited-auto-buy/status")
def get_kis_limited_auto_buy_status(
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisLimitedAutoBuyService(client)
    return service.status(db, gate_level=gate_level)


@router.post("/limited-auto-buy/preflight-once")
def run_kis_limited_auto_buy_preflight_once(
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisLimitedAutoBuyService(client)
    return service.preflight_once(db, gate_level=gate_level)


@router.post("/scheduler/run-live-once")
def run_kis_scheduler_live_once(
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisSchedulerLiveService(client)
    return service.run_once(db, gate_level=gate_level)


@router.post("/buy-shadow/run-once")
def run_kis_buy_shadow_once(
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisBuyShadowDecisionService(client)
    return service.run_once(db, gate_level=gate_level)


def _client(db: Session) -> KisClient:
    settings = get_settings()
    return KisClient(settings, KisAuthManager(settings, db))
