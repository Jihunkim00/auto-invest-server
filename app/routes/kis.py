from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.brokers.base import KisApiError, KisAuthError, KisConfigurationError
from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import get_db

router = APIRouter(prefix="/kis", tags=["kis"])


@router.get("/market/price/{symbol}")
def get_kis_market_price(symbol: str, db: Session = Depends(get_db)):
    client = _client(db)
    try:
        return client.get_domestic_stock_price(symbol)
    except KisConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KisAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except KisApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/account/balance")
def get_kis_account_balance(db: Session = Depends(get_db)):
    client = _client(db)
    try:
        return client.get_account_balance()
    except KisConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KisAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except KisApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


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
        raise HTTPException(status_code=502, detail=str(exc))
    except KisApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


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
        raise HTTPException(status_code=502, detail=str(exc))
    except KisApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


def _client(db: Session) -> KisClient:
    settings = get_settings()
    return KisClient(settings, KisAuthManager(settings, db))
