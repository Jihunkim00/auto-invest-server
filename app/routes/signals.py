import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.constants import DEFAULT_GATE_LEVEL
from app.db.database import get_db
from app.db.models import SignalLog
from app.services.signal_service import SignalService

router = APIRouter(prefix="/signals", tags=["signals"])


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
def run_signal(
    symbol: str = Query(default="AAPL", min_length=1),
    trigger_source: str = Query(default="manual"),
    gate_level: int = Query(default=DEFAULT_GATE_LEVEL, ge=1, le=4),
    db: Session = Depends(get_db),
):
    svc = SignalService()
    row = svc.run(db, symbol=symbol.upper(), trigger_source=trigger_source, gate_level=gate_level)
    return {
        "id": row.id,
        "symbol": row.symbol,
        "action": row.action,
        "confidence": row.confidence,
        "regime_confidence": row.gpt_market_confidence,
        "quant_buy_score": row.quant_buy_score,
        "quant_sell_score": row.quant_sell_score,
        "ai_buy_score": row.ai_buy_score,
        "ai_sell_score": row.ai_sell_score,
        "final_buy_score": row.final_buy_score,
        "final_sell_score": row.final_sell_score,
        "signal_status": row.signal_status,
        "gate_level": row.gate_level,
        "gate_profile_name": row.gate_profile_name,
        "hard_block_reason": row.hard_block_reason,
        "hard_blocked": bool(row.hard_blocked),
        "gating_notes": _parse_json_array(row.gating_notes),
        "approved_by_risk": row.approved_by_risk,
        "risk_flags": _parse_json_array(row.risk_flags),
        "position_size_pct": row.position_size_pct,
        "planned_stop_loss_pct": row.planned_stop_loss_pct,
        "planned_take_profit_pct": row.planned_take_profit_pct,
        "related_order_id": row.related_order_id,
        "created_at": row.created_at,
    }


@router.get("")
def list_signals(
    symbol: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(SignalLog)
    if symbol:
        query = query.filter(SignalLog.symbol == symbol.upper())

    rows = query.order_by(SignalLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": row.id,
            "symbol": row.symbol,
            "action": row.action,
            "confidence": row.confidence,
            "regime_confidence": row.gpt_market_confidence,
            "signal_status": row.signal_status,
            "gate_level": row.gate_level,
            "gate_profile_name": row.gate_profile_name,
            "hard_block_reason": row.hard_block_reason,
            "hard_blocked": bool(row.hard_blocked),
            "gating_notes": _parse_json_array(row.gating_notes),
            "approved_by_risk": row.approved_by_risk,
            "related_order_id": row.related_order_id,
            "risk_flags": _parse_json_array(row.risk_flags),
            "position_size_pct": row.position_size_pct,
            "planned_stop_loss_pct": row.planned_stop_loss_pct,
            "planned_take_profit_pct": row.planned_take_profit_pct,
            "created_at": row.created_at,
        }
        for row in rows
    ]
