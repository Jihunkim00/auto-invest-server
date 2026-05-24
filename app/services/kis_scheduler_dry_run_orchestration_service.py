from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.core.constants import DEFAULT_GATE_LEVEL
from app.db.models import OrderLog, TradeRunLog
from app.services.kis_limited_auto_buy_service import KisLimitedAutoBuyService
from app.services.kis_limited_auto_sell_service import KisLimitedAutoSellService
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.kis_scheduler_readiness_service import KisSchedulerReadinessService
from app.services.runtime_setting_service import RuntimeSettingService


PROVIDER = "kis"
MARKET = "KR"
MODE = "kis_scheduler_dry_run_orchestration"
TRIGGER_SOURCE = "scheduler_dry_run_orchestration"
DEFAULT_SLOT_LABEL = "manual_dry_run"


class KisSchedulerDryRunOrchestrationService:
    """Dry-run KIS scheduler orchestration for limited buy/sell modules."""

    def __init__(
        self,
        client: KisClient,
        *,
        readiness_service: KisSchedulerReadinessService | None = None,
        limited_auto_sell_service: Any | None = None,
        limited_auto_buy_service: Any | None = None,
        runtime_settings: RuntimeSettingService | None = None,
    ):
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.readiness_service = readiness_service or KisSchedulerReadinessService(
            client,
            runtime_settings=self.runtime_settings,
        )
        dry_runtime = _SchedulerDryRunRuntimeSettings(self.runtime_settings)
        self.limited_auto_sell_service = (
            limited_auto_sell_service
            or KisLimitedAutoSellService(client, runtime_settings=dry_runtime)
        )
        self.limited_auto_buy_service = (
            limited_auto_buy_service
            or KisLimitedAutoBuyService(client, runtime_settings=dry_runtime)
        )

    def run_once(
        self,
        db: Session,
        *,
        slot_label: str | None = None,
        include_buy: bool = True,
        include_sell: bool = True,
        include_raw: bool = False,
        gate_level: int = DEFAULT_GATE_LEVEL,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc_now(now)
        slot = str(slot_label or DEFAULT_SLOT_LABEL)
        order_log_count_before = db.query(OrderLog).count()
        child_runs: list[dict[str, Any]] = []
        requested_modules = ["scheduler_readiness", "portfolio_management"]
        if include_sell:
            requested_modules.append("limited_auto_sell")
        if include_buy:
            requested_modules.append("limited_auto_buy")

        readiness_payload = self._run_readiness(db, include_raw=include_raw)
        child_runs.append(
            _child_from_payload(
                "scheduler_readiness",
                readiness_payload,
                include_raw=include_raw,
                fallback_result="completed",
            )
        )
        child_runs.append(_portfolio_child(readiness_payload))

        sell_child: dict[str, Any] | None = None
        if include_sell:
            sell_child = self._run_sell_preflight(db, include_raw=include_raw)
            child_runs.append(sell_child)

        sell_review_required = bool(
            sell_child
            and (
                sell_child.get("action") == "sell_ready"
                or sell_child.get("primary_block_reason")
                in {
                    "stop_loss_candidate_ready_read_only",
                    "take_profit_readiness_only",
                }
                or _summary_int(sell_child, "ready_count") > 0
            )
        )

        if include_buy:
            if sell_review_required:
                child_runs.append(_buy_skipped_after_sell_review(include_raw=include_raw))
            else:
                child_runs.append(
                    self._run_buy_preflight(
                        db,
                        gate_level=gate_level,
                        include_raw=include_raw,
                    )
                )

        summary = _summary(child_runs, requested_modules=requested_modules)
        block_reasons = _block_reasons(readiness_payload, child_runs)
        primary_block_reason = block_reasons[0] if block_reasons else None
        summary["primary_block_reason"] = primary_block_reason
        summary["top_block_reasons"] = block_reasons[:5]
        summary["next_recommended_operator_action"] = _operator_action(summary)
        result = _parent_result(child_runs, requested_modules)
        order_log_count_after = db.query(OrderLog).count()
        no_order_log_created = order_log_count_after == order_log_count_before

        payload = sanitize_kis_payload(
            {
                "provider": PROVIDER,
                "market": MARKET,
                "mode": MODE,
                "trigger_source": TRIGGER_SOURCE,
                "slot_label": slot,
                "result": result,
                "readiness_only": True,
                "dry_run": True,
                "scheduler_real_orders_enabled": False,
                "real_order_submit_allowed": False,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "parent_run_id": None,
                "parent_run_key": None,
                "child_runs": child_runs,
                "summary": summary,
                "block_reasons": block_reasons,
                "safety": {
                    "scheduler_dry_run_orchestration": True,
                    "readiness_only": True,
                    "no_broker_submit": True,
                    "no_manual_submit": True,
                    "no_order_log_created": no_order_log_created,
                    "scheduler_real_orders_enabled": False,
                    "kis_scheduler_allow_real_orders": False,
                    "existing_buy_execution_unchanged": True,
                    "existing_sell_execution_unchanged": True,
                    "limited_buy_called_in_dry_run_mode": bool(include_buy),
                    "limited_sell_called_in_dry_run_mode": bool(include_sell),
                },
                "diagnostics": {
                    "checked_at": now_utc.isoformat(),
                    "slot_label": slot,
                    "include_buy": bool(include_buy),
                    "include_sell": bool(include_sell),
                    "include_raw": bool(include_raw),
                    "order_log_count_before": order_log_count_before,
                    "order_log_count_after": order_log_count_after,
                    "limited_services_called": {
                        "buy": bool(include_buy and not sell_review_required),
                        "sell": bool(include_sell),
                    },
                    "sell_review_required_before_buy": sell_review_required,
                },
            }
        )
        run = self._persist_parent(
            db,
            payload=payload,
            gate_level=gate_level,
            slot_label=slot,
            result=result,
            reason=primary_block_reason or "scheduler_dry_run_completed",
        )
        payload["parent_run_id"] = run.id
        payload["parent_run_key"] = run.run_key
        payload["parent_run"] = _serialize_run(run)
        run.response_payload = _json(payload)
        db.add(run)
        db.commit()
        return sanitize_kis_payload(payload)

    def _run_readiness(self, db: Session, *, include_raw: bool) -> dict[str, Any]:
        try:
            return self.readiness_service.readiness(
                db,
                include_modules=True,
                include_recent_runs=True,
                include_raw=include_raw,
            )
        except Exception as exc:
            return {
                "mode": "kis_scheduler_readiness",
                "trigger_source": "scheduler_readiness",
                "result": "blocked",
                "action": "hold",
                "status": "error",
                "primary_block_reason": "scheduler_readiness_unavailable",
                "block_reasons": [
                    "scheduler_readiness_unavailable",
                    _safe_error(exc),
                ],
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }

    def _run_sell_preflight(self, db: Session, *, include_raw: bool) -> dict[str, Any]:
        try:
            payload = self.limited_auto_sell_service.preflight_once(db)
            child = _child_from_payload(
                "limited_auto_sell",
                payload,
                include_raw=include_raw,
                fallback_result="completed",
            )
            child["summary"]["called_in_dry_run_mode"] = True
            return child
        except Exception as exc:
            return _error_child("limited_auto_sell", exc, include_raw=include_raw)

    def _run_buy_preflight(
        self,
        db: Session,
        *,
        gate_level: int,
        include_raw: bool,
    ) -> dict[str, Any]:
        try:
            payload = self.limited_auto_buy_service.preflight_once(
                db,
                gate_level=gate_level,
            )
            child = _child_from_payload(
                "limited_auto_buy",
                payload,
                include_raw=include_raw,
                fallback_result="completed",
            )
            child["summary"]["called_in_dry_run_mode"] = True
            return child
        except Exception as exc:
            return _error_child("limited_auto_buy", exc, include_raw=include_raw)

    def _persist_parent(
        self,
        db: Session,
        *,
        payload: dict[str, Any],
        gate_level: int,
        slot_label: str,
        result: str,
        reason: str,
    ) -> TradeRunLog:
        run = TradeRunLog(
            run_key=f"kis_scheduler_dry_run_{uuid.uuid4().hex[:10]}",
            trigger_source=TRIGGER_SOURCE,
            symbol="WATCHLIST",
            mode=MODE,
            gate_level=gate_level,
            stage="done",
            result=result,
            reason=reason,
            request_payload=_json(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": MODE,
                    "trigger_source": TRIGGER_SOURCE,
                    "slot_label": slot_label,
                    "readiness_only": True,
                    "dry_run": True,
                    "scheduler_real_orders_enabled": False,
                    "real_order_submit_allowed": False,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                }
            ),
            response_payload=_json(payload),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run


class _SchedulerDryRunRuntimeSettings:
    def __init__(self, runtime_settings: RuntimeSettingService):
        self.runtime_settings = runtime_settings

    def get_settings(self, db: Session) -> dict[str, Any]:
        runtime = dict(self.runtime_settings.get_settings(db))
        runtime.update(
            {
                "dry_run": True,
                "kis_scheduler_live_enabled": False,
                "kis_scheduler_allow_real_orders": False,
                "kis_scheduler_configured_allow_real_orders": False,
            }
        )
        return runtime


def _child_from_payload(
    module: str,
    payload: dict[str, Any],
    *,
    include_raw: bool,
    fallback_result: str,
) -> dict[str, Any]:
    block_reasons = _string_list(
        payload.get("block_reasons")
        or payload.get("blocked_by")
        or payload.get("failed_checks")
    )
    primary = _nullable_string(
        payload.get("primary_block_reason") or (block_reasons[0] if block_reasons else None)
    )
    result = str(payload.get("result") or fallback_result)
    action = str(payload.get("action") or "hold")
    summary = _child_summary(payload, module=module, block_reasons=block_reasons)
    child = {
        "module": module,
        "result": result,
        "action": action,
        "symbol": _symbol(payload),
        "status": str(payload.get("status") or result),
        "primary_block_reason": primary,
        "block_reasons": block_reasons,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "order_id": None,
        "source": str(payload.get("source") or module),
        "mode": str(payload.get("mode") or module),
        "trigger_source": str(payload.get("trigger_source") or module),
        "summary": summary,
    }
    if include_raw:
        child["raw_payload"] = sanitize_kis_payload(payload)
    return sanitize_kis_payload(child)


def _portfolio_child(readiness_payload: dict[str, Any]) -> dict[str, Any]:
    module = _dynamic_map(
        _dynamic_map(readiness_payload.get("modules")).get(
            "portfolio_position_management"
        )
    )
    return {
        "module": "portfolio_management",
        "result": "completed" if module.get("available", True) is not False else "blocked",
        "action": "review_positions",
        "symbol": None,
        "status": "read_only",
        "primary_block_reason": None
        if module.get("available", True) is not False
        else "portfolio_management_unavailable",
        "block_reasons": _string_list(module.get("block_reasons")),
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "order_id": None,
        "source": "portfolio_position_management",
        "mode": "portfolio_position_management",
        "trigger_source": TRIGGER_SOURCE,
        "summary": {
            "read_only": True,
            "available": module.get("available", True) is not False,
            "called_in_dry_run_mode": True,
        },
    }


def _buy_skipped_after_sell_review(*, include_raw: bool) -> dict[str, Any]:
    child = {
        "module": "limited_auto_buy",
        "result": "skipped",
        "action": "hold",
        "symbol": None,
        "status": "after_sell_review",
        "primary_block_reason": "sell_review_required_before_buy",
        "block_reasons": ["sell_review_required_before_buy"],
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "order_id": None,
        "source": "limited_auto_buy_preflight",
        "mode": "kis_limited_auto_buy_preflight",
        "trigger_source": TRIGGER_SOURCE,
        "summary": {
            "candidate_count": 0,
            "candidates_reviewed": 0,
            "ready_count": 0,
            "called_in_dry_run_mode": True,
            "skipped_after_sell_review": True,
        },
    }
    if include_raw:
        child["raw_payload"] = {
            "reason": "sell_review_required_before_buy",
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
        }
    return child


def _error_child(module: str, exc: Exception, *, include_raw: bool) -> dict[str, Any]:
    reason = f"{module}_unavailable"
    child = {
        "module": module,
        "result": "blocked",
        "action": "hold",
        "symbol": None,
        "status": "error",
        "primary_block_reason": reason,
        "block_reasons": [reason, _safe_error(exc)],
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "order_id": None,
        "source": module,
        "mode": module,
        "trigger_source": TRIGGER_SOURCE,
        "summary": {
            "candidate_count": 0,
            "candidates_reviewed": 0,
            "ready_count": 0,
            "called_in_dry_run_mode": True,
        },
    }
    if include_raw:
        child["raw_payload"] = {"error": _safe_error(exc)}
    return child


def _child_summary(
    payload: dict[str, Any],
    *,
    module: str,
    block_reasons: list[str],
) -> dict[str, Any]:
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    candidate_count = _int_or_zero(payload.get("candidate_count"))
    if not candidate_count:
        candidate_count = len(candidates)
    symbol = _symbol(payload)
    reviewed_symbols = _dedupe(
        [_symbol(item) for item in candidates if isinstance(item, dict)]
        + ([symbol] if symbol else [])
    )
    ready = _ready_count(payload, module=module)
    summary = {
        "candidate_count": candidate_count,
        "candidates_reviewed": candidate_count,
        "reviewed_symbols": reviewed_symbols,
        "ready_count": ready,
        "block_reasons": block_reasons,
        "real_order_submit_allowed": False,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
    }
    diagnostics = _dynamic_map(payload.get("diagnostics"))
    if "positions_evaluated" in diagnostics:
        summary["positions_evaluated"] = _int_or_zero(
            diagnostics.get("positions_evaluated")
        )
        summary["candidates_reviewed"] = max(
            candidate_count,
            _int_or_zero(diagnostics.get("positions_evaluated")),
        )
    if "run" in payload:
        summary["run"] = payload.get("run")
    return summary


def _ready_count(payload: dict[str, Any], *, module: str) -> int:
    action = str(payload.get("action") or "")
    result = str(payload.get("result") or "")
    reason = str(payload.get("reason") or "")
    if module == "limited_auto_sell":
        if action == "sell_ready" or reason in {
            "stop_loss_candidate_ready_read_only",
            "take_profit_readiness_only",
        }:
            return 1
    if module == "limited_auto_buy":
        if action == "buy_ready" or result == "ready":
            return 1
    return 0


def _summary(
    child_runs: list[dict[str, Any]],
    *,
    requested_modules: list[str],
) -> dict[str, Any]:
    completed = [
        str(child.get("module"))
        for child in child_runs
        if child.get("result") not in {"blocked", "error"}
    ]
    blocked = [
        str(child.get("module"))
        for child in child_runs
        if child.get("result") in {"blocked", "error"}
        or child.get("primary_block_reason")
    ]
    return {
        "modules_requested": requested_modules,
        "modules_completed": _dedupe(completed),
        "modules_blocked": _dedupe(blocked),
        "sell_candidates_reviewed": _module_reviewed(child_runs, "limited_auto_sell"),
        "buy_candidates_reviewed": _module_reviewed(child_runs, "limited_auto_buy"),
        "sell_ready_count": _module_ready(child_runs, "limited_auto_sell"),
        "buy_ready_count": _module_ready(child_runs, "limited_auto_buy"),
        "submitted_order_count": 0,
        "broker_submit_count": 0,
        "manual_submit_count": 0,
        "real_order_submit_allowed": False,
    }


def _module_reviewed(child_runs: list[dict[str, Any]], module: str) -> int:
    for child in child_runs:
        if child.get("module") == module:
            return _summary_int(child, "candidates_reviewed")
    return 0


def _module_ready(child_runs: list[dict[str, Any]], module: str) -> int:
    for child in child_runs:
        if child.get("module") == module:
            return _summary_int(child, "ready_count")
    return 0


def _summary_int(child: dict[str, Any], key: str) -> int:
    return _int_or_zero(_dynamic_map(child.get("summary")).get(key))


def _block_reasons(
    readiness_payload: dict[str, Any],
    child_runs: list[dict[str, Any]],
) -> list[str]:
    reasons = _string_list(readiness_payload.get("block_reasons"))
    reasons.extend(["scheduler_dry_run_only", "scheduler_real_orders_disabled"])
    for child in child_runs:
        reasons.extend(_string_list(child.get("block_reasons")))
        primary = _nullable_string(child.get("primary_block_reason"))
        if primary:
            reasons.append(primary)
    return _dedupe(reasons)


def _parent_result(
    child_runs: list[dict[str, Any]],
    requested_modules: list[str],
) -> str:
    if len(requested_modules) <= 2:
        return "blocked"
    if any(child.get("status") == "error" for child in child_runs):
        return "partial"
    return "completed"


def _operator_action(summary: dict[str, Any]) -> str:
    if _int_or_zero(summary.get("sell_ready_count")) > 0:
        return "review_sell_candidate_before_new_buy"
    if _int_or_zero(summary.get("buy_ready_count")) > 0:
        return "review_buy_candidate"
    if summary.get("primary_block_reason"):
        return "review_scheduler_readiness_blocks"
    return "monitor_next_scheduled_slot"


def _serialize_run(run: TradeRunLog) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "run_key": run.run_key,
        "trigger_source": run.trigger_source,
        "mode": run.mode,
        "result": run.result,
        "reason": run.reason,
        "created_at": run.created_at,
    }


def _symbol(payload: dict[str, Any]) -> str | None:
    raw = (
        payload.get("symbol")
        or _dynamic_map(payload.get("final_candidate")).get("symbol")
        or _dynamic_map(payload.get("candidate")).get("symbol")
    )
    text = str(raw or "").strip()
    return text or None


def _dynamic_map(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _nullable_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _utc_now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 180:
        text = f"{text[:180]}..."
    return f"{exc.__class__.__name__}: {text}"
