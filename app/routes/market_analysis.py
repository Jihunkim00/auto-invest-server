from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.database import get_db
from app.db.models import MarketAnalysis
from app.services.gpt_market_service import GPTMarketService
from app.services.indicator_service import IndicatorService
from app.services.market_data_service import MarketDataService
from app.services.reference_site_cache_service import ReferenceSiteCacheService
from app.services.reference_site_service import ReferenceSiteService
from app.services.web_content_service import WebContentService
router = APIRouter(prefix="/market-analysis", tags=["market-analysis"])


@router.post("/run")
def run_market_analysis(symbol: str = Query(default="AAPL", min_length=1), db: Session = Depends(get_db)):
    mds = MarketDataService()
    ids = IndicatorService()
    svc = GPTMarketService()

    bars = mds.get_recent_bars(symbol.upper())
    indicators = ids.calculate(bars)
    row = svc.run_and_save(db, symbol.upper(), indicators)

    return {
        "id": row.id,
        "symbol": row.symbol,
        "market_regime": row.market_regime,
        "entry_bias": row.entry_bias,
        "entry_allowed": row.entry_allowed,
        "market_confidence": row.market_confidence,
        "reason": row.risk_note,
        "risk_note": row.risk_note,
        "macro_summary": row.macro_summary,
        "created_at": row.created_at,
    }
    
@router.post("/refresh-context")
def refresh_reference_context(symbol: str = Query(default="AAPL", min_length=1), db: Session = Depends(get_db)):
    settings = get_settings()
    site_service = ReferenceSiteService(settings.reference_sites_config_path)
    web_content_service = WebContentService(
        timeout_seconds=settings.reference_site_fetch_timeout_seconds,
        max_chars=settings.reference_site_max_summary_chars,
    )
    cache_service = ReferenceSiteCacheService(settings.reference_site_cache_ttl_minutes)

    sites = site_service.get_sites_for_symbol(symbol.upper())
    summaries = web_content_service.build_site_summaries(sites)
    saved = cache_service.upsert_summaries(db, symbol.upper(), summaries)

    return {
        "symbol": symbol.upper(),
        "configured_site_count": len(sites),
        "fetched_summary_count": len(summaries),
        "cached_summary_count": saved,
    }




@router.get("")
def list_market_analysis(
    symbol: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(MarketAnalysis)
    if symbol:
        query = query.filter(MarketAnalysis.symbol == symbol.upper())

    rows = query.order_by(MarketAnalysis.created_at.desc()).limit(limit).all()
    return [
        {
            "id": row.id,
            "symbol": row.symbol,
            "market_regime": row.market_regime,
            "entry_bias": row.entry_bias,
            "entry_allowed": row.entry_allowed,
            "market_confidence": row.market_confidence,
            "reason": row.risk_note,
            "risk_note": row.risk_note,
            "macro_summary": row.macro_summary,
            "created_at": row.created_at,
        }
        for row in rows
    ]