from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query
from fastapi.responses import JSONResponse
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
from app.services.kis_order_sync_service import (
    KisOrderSyncError,
    KisOrderSyncService,
    serialize_kis_order,
)
from app.services.kis_watchlist_preview_service import KisWatchlistPreviewService
from app.services.market_profile_service import MarketProfileError
from app.services.market_session_service import MarketSessionError

router = APIRouter(prefix="/kis", tags=["kis"])


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
        raise HTTPException(status_code=502, detail={"message": str(exc), "details": exc.details})


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
        raise HTTPException(status_code=502, detail={"message": str(exc), "details": exc.details})


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
        raise HTTPException(status_code=502, detail={"message": str(exc), "details": exc.details})


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
        raise HTTPException(status_code=502, detail={"message": str(exc), "details": exc.details})


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
        raise HTTPException(status_code=502, detail={"message": str(exc), "details": exc.details})


@router.post("/orders/validate")
@router.post("/orders/dry-run")
def validate_kis_order(payload: KisOrderValidationRequest, db: Session = Depends(get_db)):
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
        raise HTTPException(status_code=502, detail={"message": str(exc), "details": exc.details}) from exc


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


@router.post("/watchlist/preview")
def preview_kis_watchlist(
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    client = _client(db)
    service = KisWatchlistPreviewService(client, db=db)
    try:
        return service.run_preview(include_gpt=True, gate_level=gate_level)
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
        payload = service.run_preview(include_gpt=True, gate_level=gate_level)
        payload["trigger_source"] = "manual_scheduler_preview"
        payload["scheduler_preview_only"] = True
        payload["real_order_submitted"] = False
        return payload
    except MarketProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketSessionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _client(db: Session) -> KisClient:
    settings = get_settings()
    return KisClient(settings, KisAuthManager(settings, db))
