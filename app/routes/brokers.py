from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.brokers.base import KisAuthError, KisConfigurationError
from app.brokers.factory import get_broker_status
from app.brokers.kis_auth_manager import KisAuthManager, KisTokenResult
from app.config import get_settings
from app.db.database import get_db

router = APIRouter(prefix="/brokers", tags=["brokers"])


@router.get("/status")
def broker_status(db: Session = Depends(get_db)):
    return get_broker_status(get_settings(), db)


@router.get("/kis/auth/status")
def kis_auth_status(db: Session = Depends(get_db)):
    manager = KisAuthManager(get_settings(), db)
    return manager.get_auth_status()


@router.post("/kis/auth/access-token")
def issue_kis_access_token(
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    manager = KisAuthManager(get_settings(), db)
    try:
        result = manager.get_valid_access_token(force_refresh=force_refresh)
        return _safe_token_response(result)
    except KisConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KisAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/kis/auth/approval-key")
def issue_kis_approval_key(
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    manager = KisAuthManager(get_settings(), db)
    try:
        result = manager.get_valid_approval_key(force_refresh=force_refresh)
        return _safe_token_response(result)
    except KisConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KisAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


def _safe_token_response(result: KisTokenResult) -> dict:
    return {
        "token_type": result.token_type,
        "issued": result.source == "issued",
        "source": result.source,
        "has_token": bool(result.token),
        "expires_at": result.expires_at.isoformat() if result.expires_at else None,
        "environment": result.environment,
    }
