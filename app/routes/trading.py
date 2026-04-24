import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.constants import DEFAULT_GATE_LEVEL
from app.db.database import get_db
from app.services.position_lifecycle_service import ENTRY_SCAN_MODE
from app.services.trading_orchestrator_service import TradingOrchestratorService
from app.services.watchlist_research_service import WatchlistResearchService
from app.services.watchlist_service import WatchlistService

router = APIRouter(prefix="/trading", tags=["trading"])


@router.post("/run-once")
def run_once(
    symbol: str = Query(default="AAPL", min_length=1),
    trigger_source: str = Query(default="manual"),
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    svc = TradingOrchestratorService()
    return svc.run(
        db,
        symbol=symbol.upper(),
        trigger_source=trigger_source,
        gate_level=gate_level,
        request_payload={"source_endpoint": "/trading/run-once"},
    )


@router.post("/run-watchlist-once")
def run_watchlist_once(
    trigger_source: str = Query(default="manual"),
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    alpaca_base = str(settings.alpaca_base_url or "").lower()
    if "paper" not in alpaca_base:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Live Alpaca endpoint disabled for run-watchlist-once",
        )

    watchlist = WatchlistService()
    research_service = WatchlistResearchService()
    analysis = watchlist.analyze(gate_level=gate_level)
    watchlist_rows = analysis.get("watchlist") or []
    top_candidate_count = settings.watchlist_top_candidates_for_research
    quant_weight = settings.watchlist_quant_weight
    research_weight = settings.watchlist_research_weight
    min_entry_score = settings.watchlist_min_entry_score
    min_quant_score = settings.watchlist_min_quant_score
    min_research_score = settings.watchlist_min_research_score
    strong_entry_score = settings.watchlist_strong_entry_score
    min_score_gap = settings.watchlist_min_score_gap
    max_sell_score = settings.watchlist_max_sell_score

    quant_candidates = sorted(
        watchlist_rows,
        key=lambda row: float(row.get("quant_score", 0)),
        reverse=True,
    )[:top_candidate_count]
    top_quant_candidates = [
        {
            "symbol": candidate["symbol"],
            "quant_score": candidate["quant_score"],
            "quant_reason": candidate.get("quant_reason"),
        }
        for candidate in quant_candidates
    ]

    researched_candidates: list[dict[str, object]] = []
    for candidate in quant_candidates:
        symbol = candidate["symbol"].upper()
        scored_candidate, indicators = watchlist._score_symbol(symbol, gate_level=gate_level)
        research = research_service.analyze_candidate(
            db=db,
            symbol=symbol,
            indicators=indicators,
            gate_level=gate_level,
        )
        researched_candidate = {
            **scored_candidate,
            **research,
        }
        researched_candidate["final_entry_score"] = round(
            researched_candidate["quant_score"] * quant_weight
            + researched_candidate["market_research_score"] * research_weight,
            2,
        )
        researched_candidates.append(researched_candidate)

    final_candidates = sorted(
        researched_candidates,
        key=lambda row: float(row.get("final_entry_score", 0)),
        reverse=True,
    )
    final_best_candidate = final_candidates[0] if final_candidates else None
    second_final_candidate = final_candidates[1] if len(final_candidates) > 1 else None
    final_score_gap = round(
        float(final_best_candidate.get("final_entry_score", 0))
        - float(second_final_candidate.get("final_entry_score", 0))
        if second_final_candidate
        else 0.0,
        2,
    )
    candidate_symbol = final_best_candidate["symbol"].upper() if final_best_candidate else None

    svc = TradingOrchestratorService()
    parent_run_key = f"watchlist_{uuid.uuid4().hex[:12]}"
    parent_run_log = svc._create_run_log(
        db,
        run_key=parent_run_key,
        trigger_source=trigger_source,
        symbol=candidate_symbol or "WATCHLIST",
        mode="watchlist_trade_trigger",
        gate_level=gate_level,
        stage="orchestration",
        result="pending",
        reason="watchlist_run_started",
        request_payload={
            "source_endpoint": "/trading/run-watchlist-once",
            "watchlist_analysis": analysis,
            "researched_candidates": researched_candidates,
            "final_best_candidate": final_best_candidate,
        },
    )

    trigger_block_reason = None
    sell_score_value = None
    if final_best_candidate is not None:
        sell_score_value = final_best_candidate.get("sell_score")
        if sell_score_value is None:
            sell_score_value = float(final_best_candidate.get("quant_sell_score", 100))

    should_trade = False
    if not final_best_candidate:
        trigger_block_reason = "no_best_candidate"
    elif float(final_best_candidate.get("final_entry_score", 0)) < min_entry_score:
        trigger_block_reason = "final_score_below_min_entry"
    elif float(final_best_candidate.get("quant_score", 0)) < min_quant_score:
        trigger_block_reason = "quant_score_too_low"
    elif float(final_best_candidate.get("market_research_score", 0)) < min_research_score:
        trigger_block_reason = "research_score_too_low"
    elif final_score_gap < min_score_gap:
        trigger_block_reason = "weak_final_score_gap"
    elif not bool(final_best_candidate.get("has_indicators")):
        trigger_block_reason = "missing_indicators"
    elif final_best_candidate.get("event_risk") == "high":
        trigger_block_reason = "high_event_risk"
    elif final_best_candidate.get("gpt_action_hint") == "block_entry":
        trigger_block_reason = "gpt_blocked_entry"
    elif sell_score_value is not None and sell_score_value > max_sell_score:
        trigger_block_reason = "sell_pressure_too_high"
    else:
        should_trade = True

    result = {
        "watchlist_source": analysis["watchlist_source"],
        "configured_symbol_count": analysis["configured_symbol_count"],
        "analyzed_symbol_count": analysis["analyzed_symbol_count"],
        "max_watchlist_size": analysis["max_watchlist_size"],
        "watchlist": analysis["watchlist"],
        "quant_candidates_count": len(quant_candidates),
        "researched_candidates_count": len(researched_candidates),
        "top_quant_candidates": top_quant_candidates,
        "researched_candidates": researched_candidates,
        "final_best_candidate": final_best_candidate,
        "second_final_candidate": second_final_candidate,
        "final_score_gap": final_score_gap,
        "best_score": float(final_best_candidate.get("final_entry_score", 0)) if final_best_candidate else 0.0,
        "min_entry_score": min_entry_score,
        "strong_entry_score": strong_entry_score,
        "min_score_gap": min_score_gap,
        "max_sell_score": max_sell_score,
        "should_trade": should_trade,
        "triggered_symbol": None,
        "trigger_block_reason": trigger_block_reason,
    }

    if not should_trade:
        trade_result = {
            "action": "hold",
            "risk_approved": False,
            "order_id": None,
            "reason": trigger_block_reason,
        }
        response_payload = {
            **analysis,
            "triggered_symbol": None,
            "trade_result": trade_result,
            "trigger_block_reason": trigger_block_reason,
            "quant_candidates_count": len(quant_candidates),
            "researched_candidates_count": len(researched_candidates),
            "top_quant_candidates": top_quant_candidates,
            "researched_candidates": researched_candidates,
            "final_best_candidate": final_best_candidate,
            "second_final_candidate": second_final_candidate,
            "final_score_gap": final_score_gap,
            "best_score": float(final_best_candidate.get("final_entry_score", 0)) if final_best_candidate else 0.0,
            "min_entry_score": min_entry_score,
            "strong_entry_score": strong_entry_score,
            "min_score_gap": min_score_gap,
            "max_sell_score": max_sell_score,
        }
        result["trade_result"] = trade_result
        result["run"] = svc._finish(
            db,
            parent_run_log,
            stage="done",
            result="skipped",
            reason=trigger_block_reason,
            response_payload=response_payload,
        )
        return result

    symbol = candidate_symbol
    position = svc.trading_service.broker.get_position(symbol)
    if position is not None:
        child_mode = "position_management"
        allowed_actions = ["hold", "sell"]
        enforce_entry_limits = False
    else:
        child_mode = ENTRY_SCAN_MODE
        allowed_actions = ["hold", "buy"]
        enforce_entry_limits = True

    child_result = svc._run_symbol_child(
        db,
        trigger_source=trigger_source,
        symbol=symbol,
        mode=child_mode,
        allowed_actions=allowed_actions,
        gate_level=gate_level,
        parent_run_key=parent_run_key,
        symbol_role="watchlist_candidate",
        enforce_entry_limits=enforce_entry_limits,
        request_payload={
            "final_best_candidate": final_best_candidate,
            "watchlist_source": analysis["watchlist_source"],
            "source": "watchlist_trigger",
        },
    )

    child_payload = child_result.get("response_payload") or {}
    risk_data = child_payload.get("risk") or {}
    trade_result = {
        "action": child_payload.get("action"),
        "risk_approved": bool(risk_data.get("approved", False)),
        "order_id": child_result.get("order_id"),
        "reason": child_payload.get("reason") or child_result.get("reason"),
    }
    response_payload = {
        **analysis,
        "triggered_symbol": symbol,
        "trade_result": trade_result,
        "child_run": child_result,
        "final_best_candidate": final_best_candidate,
        "second_final_candidate": second_final_candidate,
        "final_score_gap": final_score_gap,
    }

    result["trade_result"] = trade_result
    result["triggered_symbol"] = symbol
    result["run"] = svc._finish(
        db,
        parent_run_log,
        stage="done",
        result=child_result.get("result", "skipped"),
        reason="watchlist_trade_completed",
        response_payload=response_payload,
    )
    return result