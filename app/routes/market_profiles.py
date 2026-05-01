from fastapi import APIRouter, HTTPException

from app.services.market_profile_service import (
    MarketProfileError,
    MarketProfileService,
)

router = APIRouter(prefix="/market-profiles", tags=["market-profiles"])


@router.get("")
def list_market_profiles():
    service = MarketProfileService()
    try:
        return {
            "default_market": service.get_default_market_key(),
            "markets": service.list_profiles(),
        }
    except MarketProfileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{market}")
def get_market_profile(market: str):
    service = MarketProfileService()
    try:
        return service.get_profile(market).to_dict()
    except MarketProfileError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{market}/watchlist")
def get_market_watchlist(market: str):
    service = MarketProfileService()
    try:
        return service.load_watchlist(market)
    except MarketProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{market}/reference-sites")
def get_market_reference_sites(market: str):
    service = MarketProfileService()
    try:
        return service.load_reference_sites(market)
    except MarketProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
