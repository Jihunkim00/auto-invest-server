import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.constants import DEFAULT_GATE_LEVEL
from app.db.database import get_db
from app.db.models import TradeRunLog
from app.services.trading_orchestrator_service import TradingOrchestratorService
from app.services.watchlist_run_service import WatchlistRunService

router = APIRouter(prefix="/trading", tags=["trading"])


def _parse_json_object(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def _serialize_latest_watchlist_payload(row: TradeRunLog) -> dict[str, Any] | None:
    request_payload = _parse_json_object(row.request_payload)
    response_payload = _parse_json_object(row.response_payload)
    watchlist_analysis = request_payload.get("watchlist_analysis")

    has_watchlist_data = (
        isinstance(response_payload.get("watchlist"), list)
        or isinstance(response_payload.get("final_ranked_candidates"), list)
        or isinstance(response_payload.get("researched_candidates"), list)
        or isinstance(watchlist_analysis, dict)
    )
    if not response_payload or not has_watchlist_data:
        return None

    item = dict(response_payload)
    if isinstance(watchlist_analysis, dict):
        for key in (
            "watchlist_source",
            "configured_symbol_count",
            "analyzed_symbol_count",
            "max_watchlist_size",
            "watchlist",
        ):
            if key in watchlist_analysis:
                item.setdefault(key, watchlist_analysis[key])

    researched_candidates = request_payload.get("researched_candidates")
    if isinstance(researched_candidates, list):
        item.setdefault("researched_candidates", researched_candidates)
        item.setdefault("researched_candidates_count", len(researched_candidates))

    final_best_candidate = request_payload.get("final_best_candidate")
    if isinstance(final_best_candidate, dict):
        item.setdefault("final_best_candidate", final_best_candidate)

    top_quant_candidates = item.get("top_quant_candidates")
    if isinstance(top_quant_candidates, list):
        item.setdefault("quant_candidates_count", len(top_quant_candidates))

    trade_result = item.get("trade_result")
    if not isinstance(trade_result, dict):
        trade_result = {
            "action": "hold",
            "risk_approved": False,
            "order_id": row.order_id,
            "reason": row.reason,
        }
        item["trade_result"] = trade_result

    action = str(trade_result.get("action") or "").lower()
    item.setdefault("should_trade", bool(item.get("triggered_symbol")) or action in {"buy", "sell"})
    item.setdefault("triggered_symbol", None)
    item.setdefault("trigger_block_reason", row.reason)
    item["run"] = {
        "run_id": row.id,
        "run_key": row.run_key,
        "parent_run_key": row.parent_run_key,
        "symbol_role": row.symbol_role,
        "trigger_source": row.trigger_source,
        "symbol": row.symbol,
        "mode": row.mode,
        "gate_level": row.gate_level,
        "stage": row.stage,
        "result": row.result,
        "reason": row.reason,
        "signal_id": row.signal_id,
        "order_id": row.order_id,
        "created_at": row.created_at,
    }
    return item


@router.get("/watchlist/latest")
def get_latest_watchlist_run(db: Session = Depends(get_db)):
    rows = (
        db.query(TradeRunLog)
        .filter(TradeRunLog.mode == "watchlist_trade_trigger")
        .filter(TradeRunLog.stage == "done")
        .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
        .limit(100)
        .all()
    )
    for row in rows:
        item = _serialize_latest_watchlist_payload(row)
        if item is not None:
            return {"has_data": True, "item": item}

    return {"has_data": False, "item": None}

@router.post("/run-once")
def run_once(
    symbol: str = Query(default="AAPL", min_length=1),
    trigger_source: str = Query(default="manual"),
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    svc = TradingOrchestratorService()
    return svc.run_single_symbol(
        db,
        symbol=symbol.upper(),
        trigger_source=trigger_source,
        gate_level=gate_level,
        request_payload={"source_endpoint": "/trading/run-once"},
    )


@router.post("/run-watchlist-once")
def run_watchlist_once(
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    svc = WatchlistRunService()
    try:
        return svc.run_once(
            db,
            trigger_source="manual",
            gate_level=gate_level,
            source_endpoint="/trading/run-watchlist-once",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
