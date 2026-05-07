from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.core.constants import DEFAULT_GATE_LEVEL
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.services.kis_dry_run_risk_service import (
    HOLD,
    MARKET,
    PROVIDER,
    KisDryRunRiskDecision,
    KisDryRunRiskService,
)
from app.services.kis_watchlist_preview_service import KisWatchlistPreviewService


MODE = "kis_dry_run_auto"
SIMULATED_ORDER_STATUS = "DRY_RUN_SIMULATED"
SIMULATED_BROKER_STATUS = "SIMULATED"
MANUAL_TRIGGER_SOURCE = "manual_kis_dry_run_auto"
SCHEDULER_TRIGGER_SOURCE = "scheduler_kis_dry_run_auto"

_SENSITIVE_KEYS = {
    "appkey",
    "app_key",
    "appsecret",
    "app_secret",
    "secret",
    "access_token",
    "approval_key",
    "authorization",
    "cano",
    "account_no",
    "account_number",
    "kis_account_no",
}


class KisDryRunAutoService:
    """KIS shadow trading pipeline that persists simulated records only."""

    def __init__(
        self,
        client: KisClient,
        *,
        preview_service: KisWatchlistPreviewService | None = None,
        risk_service: KisDryRunRiskService | None = None,
        db: Session | None = None,
    ):
        self.client = client
        self.db = db
        self.preview_service = preview_service or KisWatchlistPreviewService(client, db=db)
        self.risk_service = risk_service or KisDryRunRiskService()

    def run_once(
        self,
        db: Session,
        *,
        gate_level: int = DEFAULT_GATE_LEVEL,
        trigger_source: str = MANUAL_TRIGGER_SOURCE,
    ) -> dict[str, Any]:
        preview = self.preview_service.run_preview(
            include_gpt=True,
            gate_level=gate_level,
            db=db,
        )
        preview = _sanitize_payload(preview)
        decision = self.risk_service.evaluate(db, preview=preview, gate_level=gate_level)

        parent_run = self._create_parent_run(
            db,
            preview=preview,
            decision=decision,
            gate_level=gate_level,
            trigger_source=trigger_source,
        )
        child_runs = self._create_child_runs(
            db,
            preview=preview,
            parent_run=parent_run,
            gate_level=gate_level,
            trigger_source=trigger_source,
        )

        order: OrderLog | None = None
        signal = self._create_signal(db, decision=decision, trigger_source=trigger_source, gate_level=gate_level)
        if decision.approved and decision.action in {"buy", "sell"} and decision.symbol:
            order = self._create_simulated_order(db, decision=decision, signal_id=signal.id)
            signal.related_order_id = order.id
            signal.signal_status = "simulated"
            db.commit()
            db.refresh(signal)

        result = "simulated_order_created" if order is not None else "skipped"
        response_payload = self._response_payload(
            preview=preview,
            decision=decision,
            signal=signal,
            order=order,
            result=result,
            trigger_source=trigger_source,
            child_runs=child_runs,
        )
        self._finish_parent_run(
            db,
            parent_run,
            result=result,
            reason=decision.reason,
            response_payload=response_payload,
            signal_id=signal.id,
            order_id=order.id if order is not None else None,
        )
        response_payload["run"] = _serialize_run(parent_run)
        return response_payload

    def _create_parent_run(
        self,
        db: Session,
        *,
        preview: dict[str, Any],
        decision: KisDryRunRiskDecision,
        gate_level: int,
        trigger_source: str,
    ) -> TradeRunLog:
        symbol = decision.symbol or _candidate_symbol(preview.get("final_best_candidate")) or "WATCHLIST"
        run = TradeRunLog(
            run_key=f"kis_dry_run_{uuid.uuid4().hex[:12]}",
            trigger_source=trigger_source,
            symbol=symbol,
            mode=MODE,
            gate_level=gate_level,
            stage="analysis",
            result="pending",
            reason="kis_dry_run_started",
            request_payload=_json(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": MODE,
                    "dry_run": True,
                    "simulated": True,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                    "gate_level": gate_level,
                    "trigger_source": trigger_source,
                    "final_best_candidate": preview.get("final_best_candidate"),
                    "final_ranked_candidates": preview.get("final_ranked_candidates"),
                    "entry_candidate_symbol": preview.get("entry_candidate_symbol"),
                    "held_positions": preview.get("held_positions"),
                    "market_session": preview.get("market_session"),
                    "risk_decision": decision.to_dict(),
                }
            ),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def _create_child_runs(
        self,
        db: Session,
        *,
        preview: dict[str, Any],
        parent_run: TradeRunLog,
        gate_level: int,
        trigger_source: str,
    ) -> list[dict[str, Any]]:
        raw_items = preview.get("portfolio_preview_items") or preview.get("child_runs") or []
        if not isinstance(raw_items, list):
            return []

        child_runs: list[dict[str, Any]] = []
        for index, item in enumerate(raw_items):
            if not isinstance(item, dict):
                continue
            symbol = _candidate_symbol(item) or f"KR{index + 1}"
            child = TradeRunLog(
                run_key=f"{parent_run.run_key}_child_{index + 1}",
                parent_run_key=parent_run.run_key,
                trigger_source=trigger_source,
                symbol=symbol,
                mode=str(item.get("mode") or "kis_dry_run_preview")[:30],
                symbol_role=str(item.get("symbol_role") or "")[:30] or None,
                gate_level=gate_level,
                stage="done",
                result="previewed",
                reason="kis_dry_run_child_preview",
                request_payload=_json(
                    {
                        "provider": PROVIDER,
                        "market": MARKET,
                        "dry_run": True,
                        "simulated": True,
                        "real_order_submitted": False,
                        "item": item,
                    }
                ),
                response_payload=_json(
                    {
                        "provider": PROVIDER,
                        "market": MARKET,
                        "dry_run": True,
                        "simulated": True,
                        "real_order_submitted": False,
                        "broker_submit_called": False,
                        "manual_submit_called": False,
                        "action": "hold",
                        "result": "previewed",
                    }
                ),
            )
            db.add(child)
            db.commit()
            db.refresh(child)
            child_runs.append(_serialize_run(child))
        return child_runs

    def _create_signal(
        self,
        db: Session,
        *,
        decision: KisDryRunRiskDecision,
        trigger_source: str,
        gate_level: int,
    ) -> SignalLog:
        candidate = decision.candidate or {}
        action = decision.action if decision.approved else HOLD
        signal = SignalLog(
            symbol=decision.symbol or _candidate_symbol(candidate) or "WATCHLIST",
            action=action,
            buy_score=_score(candidate, "final_buy_score", "final_entry_score", "quant_buy_score"),
            sell_score=_score(candidate, "final_sell_score", "quant_sell_score", "ai_sell_score"),
            confidence=_score(candidate, "confidence"),
            reason=decision.reason,
            indicator_payload=_json(candidate.get("indicator_payload") or {}),
            quant_buy_score=_score(candidate, "quant_buy_score", "quant_score"),
            quant_sell_score=_score(candidate, "quant_sell_score"),
            ai_buy_score=_score(candidate, "ai_buy_score"),
            ai_sell_score=_score(candidate, "ai_sell_score"),
            final_buy_score=_score(candidate, "final_buy_score", "final_entry_score", "score"),
            final_sell_score=_score(candidate, "final_sell_score"),
            quant_reason=_text(candidate.get("quant_reason")),
            ai_reason=_text(candidate.get("ai_reason") or candidate.get("gpt_reason")),
            risk_flags=_json(decision.risk_flags),
            approved_by_risk=decision.approved,
            signal_status="simulated" if decision.approved else "skipped",
            trigger_source=trigger_source,
            gate_level=gate_level,
            hard_block_reason=decision.trigger_block_reason,
            hard_blocked=not decision.approved,
            gating_notes=_json(decision.gating_notes),
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)
        return signal

    def _create_simulated_order(
        self,
        db: Session,
        *,
        decision: KisDryRunRiskDecision,
        signal_id: int,
    ) -> OrderLog:
        now = datetime.now(timezone.utc)
        request_payload = {
            "provider": PROVIDER,
            "market": MARKET,
            "dry_run": True,
            "simulated": True,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "source": MODE,
            "signal_id": signal_id,
            "symbol": decision.symbol,
            "side": decision.action,
            "qty": decision.qty,
            "notional": decision.notional,
            "estimated_price": decision.estimated_price,
            "risk_decision": decision.to_dict(),
        }
        response_payload = _invariant_payload(
            {
                "message": "KIS dry-run simulated order created.",
                "internal_status": SIMULATED_ORDER_STATUS,
                "broker_status": SIMULATED_BROKER_STATUS,
            }
        )
        order = OrderLog(
            broker=PROVIDER,
            market=MARKET,
            symbol=decision.symbol or "UNKNOWN",
            side=decision.action,
            order_type="market",
            qty=decision.qty,
            requested_qty=decision.qty,
            notional=decision.notional,
            broker_order_id=None,
            kis_odno=None,
            internal_status=InternalOrderStatus.DRY_RUN_SIMULATED.value,
            broker_status=SIMULATED_BROKER_STATUS,
            broker_order_status=SIMULATED_BROKER_STATUS,
            submitted_at=now,
            request_payload=_json(request_payload),
            response_payload=_json(response_payload),
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    def _response_payload(
        self,
        *,
        preview: dict[str, Any],
        decision: KisDryRunRiskDecision,
        signal: SignalLog,
        order: OrderLog | None,
        result: str,
        trigger_source: str,
        child_runs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        candidate = decision.candidate or {}
        payload = {
            "provider": PROVIDER,
            "market": MARKET,
            "mode": MODE,
            "dry_run": True,
            "simulated": True,
            "real_order_submitted": False,
            "trigger_source": trigger_source,
            "result": result,
            "action": decision.action,
            "triggered_symbol": decision.symbol if order is not None else None,
            "signal_id": signal.id,
            "order_id": order.id if order is not None else None,
            "broker_order_id": None,
            "kis_odno": None,
            "reason": decision.reason,
            "risk_flags": decision.risk_flags,
            "gating_notes": decision.gating_notes,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "trigger_block_reason": decision.trigger_block_reason,
            "quant_buy_score": _score(candidate, "quant_buy_score", "quant_score"),
            "quant_sell_score": _score(candidate, "quant_sell_score"),
            "ai_buy_score": _score(candidate, "ai_buy_score"),
            "ai_sell_score": _score(candidate, "ai_sell_score"),
            "confidence": _score(candidate, "confidence"),
            "final_buy_score": _score(candidate, "final_buy_score", "final_entry_score", "score"),
            "final_sell_score": _score(candidate, "final_sell_score"),
            "final_entry_score": decision.final_entry_score,
            "final_score_gap": decision.final_score_gap,
            "final_best_candidate": preview.get("final_best_candidate"),
            "final_ranked_candidates": preview.get("final_ranked_candidates") or [],
            "child_runs": child_runs,
            "trade_result": {
                "action": decision.action,
                "risk_approved": decision.approved,
                "approved_by_risk": decision.approved,
                "order_id": order.id if order is not None else None,
                "reason": decision.reason,
                "real_order_submitted": False,
            },
        }
        return _sanitize_payload(payload)

    def _finish_parent_run(
        self,
        db: Session,
        run: TradeRunLog,
        *,
        result: str,
        reason: str,
        response_payload: dict[str, Any],
        signal_id: int,
        order_id: int | None,
    ) -> None:
        run.stage = "done"
        run.result = result
        run.reason = reason
        run.signal_id = signal_id
        run.order_id = order_id
        run.response_payload = _json(response_payload)
        db.commit()
        db.refresh(run)


def _invariant_payload(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "provider": PROVIDER,
        "market": MARKET,
        "dry_run": True,
        "simulated": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "broker_order_id": None,
        "kis_odno": None,
    }
    payload.update(extra or {})
    return payload


def _serialize_run(row: TradeRunLog) -> dict[str, Any]:
    return {
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


def _candidate_symbol(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    symbol = str(value.get("symbol") or "").strip().upper()
    return symbol or None


def _score(candidate: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = candidate.get(key)
        if value is None:
            continue
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            continue
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json(payload: Any) -> str:
    return json.dumps(_sanitize_payload(payload), ensure_ascii=False, default=str)


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if _is_sensitive_key(normalized):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = _sanitize_payload(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_payload(item) for item in value]
    return value


def _is_sensitive_key(normalized_key: str) -> bool:
    if normalized_key in _SENSITIVE_KEYS:
        return True
    return any(token in normalized_key for token in ("appsecret", "access_token", "approval_key"))
