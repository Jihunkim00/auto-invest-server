import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.constants import DEFAULT_GATE_LEVEL
from app.db.database import get_db
from app.db.models import MarketAnalysis
from app.services.ai_signal_service import AISignalService
from app.services.entry_readiness_service import evaluate_entry_readiness, market_research_blocks_entry
from app.services.gpt_market_service import GPTMarketService
from app.services.indicator_service import IndicatorService
from app.services.market_data_service import MarketDataService
from app.services.quant_signal_service import QuantSignalService
from app.services.reference_site_cache_service import ReferenceSiteCacheService
from app.services.reference_site_service import ReferenceSiteService
from app.services.watchlist_service import WatchlistService
from app.services.web_content_service import WebContentService

router = APIRouter(prefix="/market-analysis", tags=["market-analysis"])


def _parse_json_array(raw_value: str | None) -> list:
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        return []
    return []


@router.post("/run")
def run_market_analysis(
    symbol: str = Query(default="AAPL", min_length=1),
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    normalized_symbol = symbol.upper()
    mds = MarketDataService()
    ids = IndicatorService()
    quant_service = QuantSignalService()
    ai_service = AISignalService()
    svc = GPTMarketService()

    try:
        bars = mds.get_recent_bars(normalized_symbol)
        indicators = ids.calculate(bars)
        quant = quant_service.score(indicators, gate_level=gate_level)
        ai = ai_service.adjust(
            indicators=indicators,
            quant_buy_score=quant["quant_buy_score"],
            quant_sell_score=quant["quant_sell_score"],
        )
        entry_score = min(
            max((quant["quant_buy_score"] * 0.75) + (ai["ai_buy_score"] * 0.25), 0.0),
            100.0,
        )
        row = svc.run_and_save(db, normalized_symbol, indicators, gate_level=gate_level)
        market_research_blocked = market_research_blocks_entry(
            entry_allowed=bool(row.entry_allowed),
            hard_blocked=bool(row.hard_blocked),
            reason=row.risk_note,
            entry_bias=row.entry_bias,
        )
        readiness = evaluate_entry_readiness(
            has_indicators=bool(indicators),
            hard_blocked=bool(row.hard_blocked),
            entry_score=entry_score,
            buy_score=entry_score,
            sell_score=quant["quant_sell_score"],
            gate_level=gate_level,
            min_entry_score=get_settings().watchlist_min_entry_score,
            max_sell_score=get_settings().watchlist_max_sell_score,
            gating_notes=list(quant.get("quant_notes") or []),
            market_research_blocked=market_research_blocked,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "market_analysis_failed",
                "symbol": normalized_symbol,
                "gate_level": gate_level,
                "message": str(exc) or exc.__class__.__name__,
            },
        ) from exc

    return {
        "id": row.id,
        "symbol": row.symbol,
        "entry_score": round(entry_score, 2),
        "quant_score": quant["quant_buy_score"],
        "buy_score": quant["quant_buy_score"],
        "sell_score": quant["quant_sell_score"],
        "quant_buy_score": quant["quant_buy_score"],
        "quant_sell_score": quant["quant_sell_score"],
        "ai_buy_score": ai["ai_buy_score"],
        "ai_sell_score": ai["ai_sell_score"],
        "quant_reason": quant["quant_reason"],
        "quant_notes": list(quant.get("quant_notes") or []),
        "ai_reason": ai["ai_reason"],
        "action_hint": readiness["action_hint"],
        "action": "buy" if readiness["entry_ready"] else "hold",
        "soft_entry_allowed": readiness["soft_entry_allowed"],
        "entry_ready": readiness["entry_ready"],
        "trade_allowed": False,
        "block_reason": readiness["block_reason"],
        "market_research_blocked": market_research_blocked,
        "has_indicators": bool(indicators),
        "indicators": indicators,
        "market_regime": row.market_regime,
        "entry_bias": row.entry_bias,
        "entry_allowed": row.entry_allowed,
        "regime_confidence": row.market_confidence,
        "market_confidence": row.market_confidence,
        "gate_level": row.gate_level,
        "gate_profile_name": row.gate_profile_name,
        "hard_block_reason": row.hard_block_reason,
        "hard_blocked": bool(row.hard_blocked),
        "gating_notes": _parse_json_array(row.gating_notes),
        "reason": row.risk_note,
        "risk_note": row.risk_note,
        "macro_summary": row.macro_summary,
        "created_at": row.created_at,
    }


@router.post("/watchlist")
def analyze_watchlist(
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
):
    svc = WatchlistService()
    return svc.analyze(gate_level=gate_level)


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
            "regime_confidence": row.market_confidence,
            "market_confidence": row.market_confidence,
            "gate_level": row.gate_level,
            "gate_profile_name": row.gate_profile_name,
            "hard_block_reason": row.hard_block_reason,
            "hard_blocked": bool(row.hard_blocked),
            "gating_notes": _parse_json_array(row.gating_notes),
            "reason": row.risk_note,
            "risk_note": row.risk_note,
            "macro_summary": row.macro_summary,
            "created_at": row.created_at,
        }
        for row in rows
    ]
