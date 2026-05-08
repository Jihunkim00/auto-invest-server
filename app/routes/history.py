from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import OrderLog, SignalLog, TradeRunLog

router = APIRouter(tags=["history"])


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


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _parse_json_array(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item).strip()]
    except Exception:
        return []
    return []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _infer_provider(*, broker: str | None = None, mode: str | None = None, trigger_source: str | None = None) -> str:
    broker_text = str(broker or "").strip().lower()
    if broker_text:
        return broker_text
    hint = f"{mode or ''} {trigger_source or ''}".lower()
    if "kis" in hint:
        return "kis"
    return "alpaca"


def _infer_market(provider: str, market: str | None = None) -> str:
    text = str(market or "").strip().upper()
    if text:
        return text
    return "KR" if provider.lower() == "kis" else "US"


def _payload_list(
    response_payload: dict[str, Any],
    trade_result: dict[str, Any],
    request_payload: dict[str, Any],
    key: str,
) -> list[str]:
    return (
        _string_list(response_payload.get(key))
        or _string_list(trade_result.get(key))
        or _string_list(request_payload.get(key))
    )


def _serialize_run(row: TradeRunLog) -> dict[str, Any]:
    request_payload = _parse_json_object(row.request_payload)
    response_payload = _parse_json_object(row.response_payload)
    trade_result = response_payload.get("trade_result")
    if not isinstance(trade_result, dict):
        trade_result = {}

    provider = str(
        _first_present(
            response_payload.get("provider"),
            trade_result.get("provider"),
            request_payload.get("provider"),
            _infer_provider(mode=row.mode, trigger_source=row.trigger_source),
        )
    )
    market = str(
        _first_present(
            response_payload.get("market"),
            trade_result.get("market"),
            request_payload.get("market"),
            _infer_market(provider),
        )
    )
    action = (
        response_payload.get("action")
        or trade_result.get("action")
        or ("hold" if row.result in {"skipped", "rejected"} else row.result)
    )
    reason = row.reason or response_payload.get("reason") or trade_result.get("reason")

    return {
        "id": row.id,
        "run_key": row.run_key,
        "provider": provider,
        "market": market,
        "symbol": row.symbol,
        "trigger_source": row.trigger_source,
        "mode": row.mode,
        "action": str(action or "hold"),
        "result": row.result,
        "reason": reason,
        "related_order_id": row.order_id,
        "order_id": row.order_id,
        "signal_id": row.signal_id,
        "gate_level": row.gate_level,
        "stage": row.stage,
        "symbol_role": row.symbol_role,
        "parent_run_key": row.parent_run_key,
        "created_at": row.created_at,
        "dry_run": _bool_or_none(
            _first_present(
                response_payload.get("dry_run"),
                trade_result.get("dry_run"),
                request_payload.get("dry_run"),
            )
        ),
        "simulated": _bool_or_none(
            _first_present(
                response_payload.get("simulated"),
                trade_result.get("simulated"),
                request_payload.get("simulated"),
            )
        )
        or False,
        "preview_only": _bool_or_none(
            _first_present(
                response_payload.get("preview_only"),
                trade_result.get("preview_only"),
                request_payload.get("preview_only"),
            )
        )
        or False,
        "real_order_submitted": _bool_or_none(
            _first_present(
                response_payload.get("real_order_submitted"),
                trade_result.get("real_order_submitted"),
                request_payload.get("real_order_submitted"),
            )
        ),
        "broker_submit_called": _bool_or_none(
            _first_present(
                response_payload.get("broker_submit_called"),
                trade_result.get("broker_submit_called"),
                request_payload.get("broker_submit_called"),
            )
        ),
        "manual_submit_called": _bool_or_none(
            _first_present(
                response_payload.get("manual_submit_called"),
                trade_result.get("manual_submit_called"),
                request_payload.get("manual_submit_called"),
            )
        ),
        "risk_flags": _payload_list(response_payload, trade_result, request_payload, "risk_flags"),
        "gating_notes": _payload_list(response_payload, trade_result, request_payload, "gating_notes"),
    }


def _serialize_order(row: OrderLog) -> dict[str, Any]:
    request_payload = _parse_json_object(row.request_payload)
    response_payload = _parse_json_object(row.response_payload)
    provider = _infer_provider(broker=row.broker)
    market = _infer_market(provider, row.market)
    source = str(request_payload.get("source") or response_payload.get("source") or "")
    simulated = (
        _bool_or_none(_first_present(response_payload.get("simulated"), request_payload.get("simulated")))
        or str(row.internal_status or "").upper() == "DRY_RUN_SIMULATED"
    )
    preview_only = _bool_or_none(
        _first_present(response_payload.get("preview_only"), request_payload.get("preview_only"))
    ) or False
    real_order_submitted = _bool_or_none(
        _first_present(
            response_payload.get("real_order_submitted"),
            request_payload.get("real_order_submitted"),
        )
    )
    if provider == "kis" and real_order_submitted is None:
        real_order_submitted = bool(
            not simulated
            and str(row.internal_status or "").upper()
            not in {"REJECTED_BY_SAFETY_GATE", "DRY_RUN_SIMULATED", "FAILED"}
            and (row.kis_odno or row.broker_order_id)
        )
    broker_submit_called = _bool_or_none(
        _first_present(
            response_payload.get("broker_submit_called"),
            request_payload.get("broker_submit_called"),
        )
    )
    if provider == "kis" and broker_submit_called is None and real_order_submitted is not None:
        broker_submit_called = bool(real_order_submitted)
    manual_submit_called = _bool_or_none(
        _first_present(
            response_payload.get("manual_submit_called"),
            request_payload.get("manual_submit_called"),
        )
    )
    if provider == "kis" and manual_submit_called is None:
        manual_submit_called = not simulated and source != "kis_dry_run_auto"
    risk_flags = _string_list(response_payload.get("risk_flags")) or _string_list(
        response_payload.get("block_reasons")
    )
    gating_notes = _string_list(response_payload.get("gating_notes")) or _string_list(
        response_payload.get("failed_checks")
    )
    return {
        "id": row.id,
        "order_id": row.id,
        "provider": provider,
        "broker": row.broker,
        "market": market,
        "mode": source or ("kis_dry_run_auto" if simulated else "manual_live_order"),
        "trigger_source": source or ("kis_dry_run_auto" if simulated else "manual"),
        "symbol": row.symbol,
        "side": row.side,
        "action": row.side,
        "result": row.internal_status,
        "reason": (
            row.error_message
            or response_payload.get("message")
            or response_payload.get("reason")
            or request_payload.get("reason")
            or ""
        ),
        "qty": row.qty,
        "notional": row.notional,
        "broker_order_id": row.broker_order_id,
        "kis_odno": row.kis_odno,
        "broker_status": row.broker_status,
        "broker_order_status": row.broker_order_status,
        "internal_status": row.internal_status,
        "signal_id": _first_present(request_payload.get("signal_id"), response_payload.get("signal_id")),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "submitted_at": row.submitted_at,
        "filled_at": row.filled_at,
        "dry_run": _bool_or_none(_first_present(response_payload.get("dry_run"), request_payload.get("dry_run"))),
        "simulated": simulated,
        "preview_only": preview_only,
        "real_order_submitted": real_order_submitted,
        "broker_submit_called": broker_submit_called,
        "manual_submit_called": manual_submit_called,
        "risk_flags": risk_flags,
        "gating_notes": gating_notes,
    }


def _serialize_signal(row: SignalLog) -> dict[str, Any]:
    provider = _infer_provider(mode=None, trigger_source=row.trigger_source)
    market = _infer_market(provider)
    simulated = provider == "kis" and str(row.signal_status or "").lower() == "simulated"
    return {
        "id": row.id,
        "run_key": None,
        "provider": provider,
        "market": market,
        "mode": "kis_dry_run_auto" if simulated else "signal",
        "trigger_source": row.trigger_source,
        "symbol": row.symbol,
        "action": row.action,
        "result": row.signal_status,
        "signal_status": row.signal_status,
        "buy_score": row.buy_score,
        "sell_score": row.sell_score,
        "final_buy_score": row.final_buy_score,
        "final_sell_score": row.final_sell_score,
        "confidence": row.confidence,
        "reason": row.reason,
        "related_order_id": row.related_order_id,
        "order_id": row.related_order_id,
        "gate_level": row.gate_level,
        "created_at": row.created_at,
        "dry_run": True if simulated else None,
        "simulated": simulated,
        "preview_only": False,
        "real_order_submitted": False if simulated else None,
        "broker_submit_called": False if simulated else None,
        "manual_submit_called": False if simulated else None,
        "risk_flags": _parse_json_array(row.risk_flags),
        "gating_notes": _parse_json_array(row.gating_notes),
    }


@router.get("/runs/recent")
def get_recent_runs(
    limit: int = Query(default=20, ge=1, le=200),
    symbol: str | None = Query(default=None, min_length=1),
    trigger_source: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
):
    query = db.query(TradeRunLog)
    if symbol:
        query = query.filter(TradeRunLog.symbol == symbol.upper())
    if trigger_source:
        query = query.filter(TradeRunLog.trigger_source == trigger_source)

    rows = query.order_by(TradeRunLog.created_at.desc()).limit(limit).all()
    return {"items": [_serialize_run(row) for row in rows]}


@router.get("/orders/recent")
def get_recent_orders(
    limit: int = Query(default=20, ge=1, le=200),
    symbol: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
):
    query = db.query(OrderLog)
    if symbol:
        query = query.filter(OrderLog.symbol == symbol.upper())

    rows = query.order_by(OrderLog.created_at.desc()).limit(limit).all()
    return {"items": [_serialize_order(row) for row in rows]}


@router.get("/signals/recent")
def get_recent_signals(
    limit: int = Query(default=20, ge=1, le=200),
    symbol: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
):
    query = db.query(SignalLog)
    if symbol:
        query = query.filter(SignalLog.symbol == symbol.upper())

    rows = query.order_by(SignalLog.created_at.desc()).limit(limit).all()
    return {"items": [_serialize_signal(row) for row in rows]}


@router.get("/logs/summary")
def get_logs_summary(db: Session = Depends(get_db)):
    latest_run = db.query(TradeRunLog).order_by(TradeRunLog.created_at.desc()).first()
    latest_order = db.query(OrderLog).order_by(OrderLog.created_at.desc()).first()
    latest_signal = db.query(SignalLog).order_by(SignalLog.created_at.desc()).first()

    return {
        "latest_run": _serialize_run(latest_run) if latest_run else None,
        "latest_order": _serialize_order(latest_order) if latest_order else None,
        "latest_signal": _serialize_signal(latest_signal) if latest_signal else None,
        "counts": {
            "runs": db.query(TradeRunLog).count(),
            "orders": db.query(OrderLog).count(),
            "signals": db.query(SignalLog).count(),
        },
    }
