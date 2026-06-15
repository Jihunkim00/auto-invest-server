import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import MarketAnalysis, OrderLog, SignalLog
from app.services.gpt_risk_context import gpt_context_from_market_analysis
from app.services.kis_order_audit import (
    kis_order_source_fields,
    kis_order_source_metadata_from_payloads,
    live_order_audit_from_payloads,
    live_order_audit_summary_fields,
)

router = APIRouter(prefix="/logs", tags=["logs"])


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


def _parse_json_object(raw_value: str | None) -> dict:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def _signal_gpt_context(db: Session, row: SignalLog) -> dict | None:
    if row.market_analysis_id is None:
        return None
    analysis = db.get(MarketAnalysis, row.market_analysis_id)
    if analysis is None:
        return None
    return gpt_context_from_market_analysis(analysis)


@router.get("/orders")
def get_order_logs(
    symbol: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(OrderLog)

    if symbol:
        query = query.filter(OrderLog.symbol == symbol)

    rows = query.order_by(OrderLog.created_at.desc()).limit(limit).all()

    items = []
    for row in rows:
        request_payload = _parse_json_object(row.request_payload)
        response_payload = _parse_json_object(row.response_payload)
        source_fields = kis_order_source_fields(
            kis_order_source_metadata_from_payloads(request_payload, response_payload)
        )
        audit_fields = live_order_audit_summary_fields(
            live_order_audit_from_payloads(request_payload, response_payload)
        )
        items.append(
            {
            "id": row.id,
            "symbol": row.symbol,
            "side": row.side,
            "order_type": row.order_type,
            "notional": row.notional,
            "qty": row.qty,
            "internal_status": row.internal_status,
            "broker_status": row.broker_status,
            "filled_qty": row.filled_qty,
            "filled_avg_price": row.filled_avg_price,
            "submitted_at": row.submitted_at,
            "filled_at": row.filled_at,
            "created_at": row.created_at,
            **audit_fields,
            **source_fields,
        }
        )
    return items


@router.get("/signals")
def get_signal_logs(
    symbol: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(SignalLog)

    if symbol:
        query = query.filter(SignalLog.symbol == symbol)

    rows = query.order_by(SignalLog.created_at.desc()).limit(limit).all()

    items = []
    for row in rows:
        buy_shadow = str(row.trigger_source or "").lower() == "kis_buy_shadow"
        limited_auto_buy = (
            str(row.trigger_source or "").lower() == "kis_limited_auto_buy"
        )
        kis_signal = buy_shadow or str(row.trigger_source or "").lower().startswith("kis_")
        items.append(
            {
            "id": row.id,
            "provider": "kis" if kis_signal else "alpaca",
            "market": "KR" if kis_signal else "US",
            "mode": "shadow_buy_dry_run"
            if buy_shadow
            else ("limited_auto_buy" if limited_auto_buy else "signal"),
            "trigger_source": row.trigger_source,
            "symbol": row.symbol,
            "action": row.action,
            "result": row.signal_status,
            "buy_score": row.buy_score,
            "sell_score": row.sell_score,
            "confidence": row.confidence,
            "regime_confidence": row.gpt_market_confidence,
            "quant_buy_score": row.quant_buy_score,
            "quant_sell_score": row.quant_sell_score,
            "ai_buy_score": row.ai_buy_score,
            "ai_sell_score": row.ai_sell_score,
            "final_buy_score": row.final_buy_score,
            "final_sell_score": row.final_sell_score,
            "reason": row.reason,
            "quant_reason": row.quant_reason,
            "ai_reason": row.ai_reason,
            "indicator_payload": row.indicator_payload,
            "risk_flags": _parse_json_array(row.risk_flags),
            "gpt_context": _signal_gpt_context(db, row),
            "approved_by_risk": row.approved_by_risk,
            "signal_status": row.signal_status,
            "gate_level": row.gate_level,
            "gate_profile_name": row.gate_profile_name,
            "hard_block_reason": row.hard_block_reason,
            "hard_blocked": bool(row.hard_blocked),
            "gating_notes": _parse_json_array(row.gating_notes),
            "related_order_id": row.related_order_id,
            "dry_run": True if buy_shadow else None,
            "simulated": buy_shadow,
            "preview_only": buy_shadow,
            "real_order_submitted": False if buy_shadow else (row.related_order_id is not None if limited_auto_buy else None),
            "broker_submit_called": False if buy_shadow else (row.related_order_id is not None if limited_auto_buy else None),
            "manual_submit_called": False if buy_shadow or limited_auto_buy else None,
            "created_at": row.created_at,
        }
        )
    return items
