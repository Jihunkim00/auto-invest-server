from fastapi import APIRouter, HTTPException

from app.services.market_session_service import (
    MarketSessionError,
    MarketSessionService,
)

router = APIRouter(prefix="/market-sessions", tags=["market-sessions"])


@router.get("")
def list_market_sessions():
    service = MarketSessionService()
    try:
        return {
            "default_market": service.get_default_market_key(),
            "markets": service.list_sessions(),
        }
    except MarketSessionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{market}")
def get_market_session(market: str):
    service = MarketSessionService()
    try:
        return service.get_session(market).to_dict()
    except MarketSessionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{market}/status")
def get_market_session_status(market: str):
    service = MarketSessionService()
    try:
        return service.get_session_status(market)
    except MarketSessionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
