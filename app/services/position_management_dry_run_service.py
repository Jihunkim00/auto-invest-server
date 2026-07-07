from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import TradeRunLog
from app.schemas.position_exit_review import PositionSellPreflightRequest
from app.schemas.position_management_dry_run import (
    PositionManagementDryRunRequest,
)
from app.services.auto_exit_candidate_service import AutoExitCandidateService
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.position_exit_review_service import PositionExitReviewService
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "position_management_dry_run"
TRIGGER_SOURCE = "position_management_dry_run"
PROVIDER = "kis"
MARKET = "KR"


class PositionManagementDryRunService:
    """Dry-run only held-position management loop.

    This service may read positions, detect exit candidates, and call the
    existing sell preflight path. It never calls guarded sell or broker/manual
    order submission paths.
    """

    def __init__(
        self,
        *,
        auto_exit_candidates: AutoExitCandidateService,
        exit_review_service: PositionExitReviewService,
        runtime_settings: RuntimeSettingService | None = None,
    ) -> None:
        self.auto_exit_candidates = auto_exit_candidates
        self.exit_review_service = exit_review_service
        self.runtime_settings = runtime_settings or RuntimeSettingService()

    def run_once(
        self,
        db: Session,
        request: PositionManagementDryRunRequest | dict[str, Any] | None = None,
        *,
        require_enabled: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        payload = (
            request
            if isinstance(request, PositionManagementDryRunRequest)
            else PositionManagementDryRunRequest.model_validate(request or {})
        )
        generated_at = _aware_utc(now)
        settings = self.runtime_settings.get_settings_read_only(db)
        request_payload = payload.model_dump(mode="json")
        scheduler_enabled = bool(settings.get("position_management_scheduler_enabled"))
        scheduler_dry_run_only = bool(
            settings.get("position_management_scheduler_dry_run_only", True)
        )
        scheduler_allow_live_orders = bool(
            settings.get("position_management_scheduler_allow_live_orders", False)
        )

        block_reason = self._scheduler_block_reason(
            require_enabled=require_enabled,
            scheduler_enabled=scheduler_enabled,
            scheduler_dry_run_only=scheduler_dry_run_only,
            scheduler_allow_live_orders=scheduler_allow_live_orders,
        )
        if block_reason is not None:
            response = self._response(
                generated_at=generated_at,
                request=payload,
                result_status="blocked",
                primary_reason=block_reason,
                risk_flags=[block_reason],
                gating_notes=[
                    "Position management scheduler is dry-run only.",
                    "No live sell scheduler or order submission path is available.",
                ],
                scheduler_enabled=scheduler_enabled,
                scheduler_dry_run_only=scheduler_dry_run_only,
                scheduler_allow_live_orders=False,
            )
            return self._save_run(
                db,
                request_payload=request_payload,
                response=response,
                result="blocked",
                reason=block_reason,
                symbol=payload.symbol or "POSITIONS",
                generated_at=generated_at,
            )

        try:
            candidates_payload = self.auto_exit_candidates.candidates(
                db,
                provider=payload.provider,
                market=payload.market,
                symbol=payload.symbol,
                include_details=True,
                min_severity="info",
            )
        except Exception as exc:
            reason = f"candidate_detection_failed:{exc.__class__.__name__}"
            response = self._response(
                generated_at=generated_at,
                request=payload,
                result_status="error",
                primary_reason=reason,
                risk_flags=["candidate_detection_failed"],
                gating_notes=[
                    "Candidate detection failed before any preflight simulation.",
                    "No order path was called.",
                ],
                scheduler_enabled=scheduler_enabled,
                scheduler_dry_run_only=scheduler_dry_run_only,
                scheduler_allow_live_orders=False,
            )
            return self._save_run(
                db,
                request_payload=request_payload,
                response=response,
                result="error",
                reason=reason,
                symbol=payload.symbol or "POSITIONS",
                generated_at=generated_at,
            )

        candidates = _candidate_list(candidates_payload)
        details = candidates_payload.get("details") if isinstance(candidates_payload, dict) else {}
        if not isinstance(details, dict):
            details = {}
        positions_checked = _int(details.get("position_count"), 0)
        preflight_results = (
            self._simulate_sell_preflights(db, candidates)
            if payload.include_sell_preflight
            else []
        )
        blocked_preflight_count = len(
            [
                item
                for item in preflight_results
                if str(item.get("preflight_status") or "").lower()
                in {"blocked", "review_required", "error"}
            ]
        )
        candidate_count = len(candidates)
        result_status = "completed"
        primary_reason = "position_management_dry_run_completed"
        if positions_checked <= 0:
            result_status = "skipped"
            primary_reason = "no_open_positions"
        elif candidate_count <= 0:
            primary_reason = "no_exit_candidates"

        risk_flags = _dedupe(
            [
                "dry_run_only",
                "positions_first",
                "exit_candidate_detected" if candidate_count else "",
                "critical_exit_candidate"
                if _count(candidates, "severity", "critical")
                else "",
                "sync_required"
                if _count(candidates, "candidate_type", "sync_required")
                else "",
                "duplicate_sell_conflict"
                if _count(candidates, "candidate_type", "duplicate_sell_conflict")
                else "",
            ]
        )
        gating_notes = _dedupe(
            [
                "Open positions are checked before any new-entry automation.",
                "Dry-run position management recorded candidate state only.",
                "Sell preflight simulation is read-only and operator-review only.",
                "No guarded sell execution was called.",
                "No broker or manual submit path was called.",
            ]
        )
        response = self._response(
            generated_at=generated_at,
            request=payload,
            result_status=result_status,
            primary_reason=primary_reason,
            risk_flags=risk_flags,
            gating_notes=gating_notes,
            positions_checked=positions_checked,
            candidates=candidates,
            preflight_results=preflight_results,
            blocked_preflight_count=blocked_preflight_count,
            scheduler_enabled=scheduler_enabled,
            scheduler_dry_run_only=scheduler_dry_run_only,
            scheduler_allow_live_orders=False,
        )
        return self._save_run(
            db,
            request_payload=request_payload,
            response=response,
            result=result_status,
            reason=primary_reason,
            symbol=payload.symbol or "POSITIONS",
            generated_at=generated_at,
        )

    def latest(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
    ) -> dict[str, Any]:
        row = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == MODE)
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .first()
        )
        if row is not None:
            payload = _parse_object(row.response_payload)
            if payload:
                payload["run_id"] = payload.get("run_id") or row.id
                return sanitize_kis_payload(payload)

        generated_at = datetime.now(UTC)
        settings = self.runtime_settings.get_settings_read_only(db)
        return self._response(
            generated_at=generated_at,
            request=PositionManagementDryRunRequest(
                provider=provider,
                market=market,
                trigger_source="position_management_dry_run_latest_lookup",
            ),
            result_status="skipped",
            primary_reason="no_recent_position_management_dry_run",
            risk_flags=["no_recent_run"],
            gating_notes=["No position management dry-run has been recorded yet."],
            scheduler_enabled=bool(settings.get("position_management_scheduler_enabled")),
            scheduler_dry_run_only=bool(
                settings.get("position_management_scheduler_dry_run_only", True)
            ),
            scheduler_allow_live_orders=False,
        )

    def _simulate_sell_preflights(
        self,
        db: Session,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for candidate in candidates:
            if candidate.get("can_run_sell_preflight") is not True:
                continue
            symbol = str(candidate.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            try:
                result = self.exit_review_service.sell_preflight(
                    db,
                    symbol=symbol,
                    request=PositionSellPreflightRequest(
                        provider=PROVIDER,
                        market=MARKET,
                        quantity_mode="full",
                        language="ko",
                        locale="ko-KR",
                    ),
                )
                results.append(
                    {
                        "symbol": symbol,
                        "candidate_id": candidate.get("candidate_id"),
                        "candidate_type": candidate.get("candidate_type"),
                        "preflight_status": result.get("preflight_status"),
                        "primary_block_reason": result.get("primary_block_reason"),
                        "can_submit_after_confirmation": False,
                        "real_order_submitted": False,
                        "broker_submit_called": False,
                        "manual_submit_called": False,
                        "next_required_action": result.get("next_required_action"),
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "symbol": symbol,
                        "candidate_id": candidate.get("candidate_id"),
                        "candidate_type": candidate.get("candidate_type"),
                        "preflight_status": "error",
                        "primary_block_reason": f"sell_preflight_failed:{exc.__class__.__name__}",
                        "can_submit_after_confirmation": False,
                        "real_order_submitted": False,
                        "broker_submit_called": False,
                        "manual_submit_called": False,
                    }
                )
        return results

    def _scheduler_block_reason(
        self,
        *,
        require_enabled: bool,
        scheduler_enabled: bool,
        scheduler_dry_run_only: bool,
        scheduler_allow_live_orders: bool,
    ) -> str | None:
        if require_enabled and not scheduler_enabled:
            return "position_management_scheduler_disabled"
        if not scheduler_dry_run_only:
            return "position_management_scheduler_dry_run_only_disabled"
        if scheduler_allow_live_orders:
            return "position_management_scheduler_live_orders_forbidden"
        return None

    def _response(
        self,
        *,
        generated_at: datetime,
        request: PositionManagementDryRunRequest,
        result_status: str,
        primary_reason: str | None,
        risk_flags: list[str],
        gating_notes: list[str],
        scheduler_enabled: bool,
        scheduler_dry_run_only: bool,
        scheduler_allow_live_orders: bool,
        positions_checked: int = 0,
        candidates: list[dict[str, Any]] | None = None,
        preflight_results: list[dict[str, Any]] | None = None,
        blocked_preflight_count: int = 0,
    ) -> dict[str, Any]:
        candidates = candidates or []
        preflight_results = preflight_results or []
        return sanitize_kis_payload(
            {
                "run_id": None,
                "generated_at": generated_at.isoformat(),
                "provider": request.provider,
                "market": request.market,
                "trigger_source": request.trigger_source,
                "dry_run_only": True,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "positions_checked": positions_checked,
                "exit_candidate_count": len(candidates),
                "critical_candidate_count": _count(candidates, "severity", "critical"),
                "warning_candidate_count": _count(candidates, "severity", "warning"),
                "simulated_sell_preflight_count": len(preflight_results),
                "blocked_preflight_count": blocked_preflight_count,
                "sync_required_count": _count(candidates, "candidate_type", "sync_required"),
                "duplicate_sell_conflict_count": _count(
                    candidates,
                    "candidate_type",
                    "duplicate_sell_conflict",
                ),
                "result_status": result_status,
                "primary_reason": primary_reason,
                "risk_flags": _dedupe(risk_flags),
                "gating_notes": _dedupe(gating_notes),
                "candidates": candidates,
                "sell_preflight_results": preflight_results,
                "next_safe_actions": _next_safe_actions(
                    result_status=result_status,
                    candidates=candidates,
                ),
                "priority": "positions_first",
                "entry_orders_allowed": False,
                "exit_orders_allowed": False,
                "dry_run_monitoring_only": True,
                "scheduler_enabled": scheduler_enabled,
                "scheduler_dry_run_only": scheduler_dry_run_only,
                "scheduler_allow_live_orders": False,
                "safety": _safety(),
            }
        )

    def _save_run(
        self,
        db: Session,
        *,
        request_payload: dict[str, Any],
        response: dict[str, Any],
        result: str,
        reason: str,
        symbol: str,
        generated_at: datetime,
    ) -> dict[str, Any]:
        row = TradeRunLog(
            run_key=f"position_management_dry_run_{uuid.uuid4().hex[:12]}",
            trigger_source=TRIGGER_SOURCE,
            symbol=symbol,
            mode=MODE,
            stage="done",
            result=result,
            reason=reason,
            request_payload=_json(
                {
                    **request_payload,
                    "mode": MODE,
                    "job_name": TRIGGER_SOURCE,
                    "dry_run_only": True,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                    "entry_orders_allowed": False,
                    "exit_orders_allowed": False,
                }
            ),
            response_payload=_json(response),
            created_at=_naive_utc(generated_at),
        )
        db.add(row)
        db.flush()
        response["run_id"] = row.id
        row.response_payload = _json(response)
        db.commit()
        return sanitize_kis_payload(response)


def _candidate_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("candidates") if isinstance(payload, dict) else []
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _count(items: list[dict[str, Any]], key: str, value: str) -> int:
    return len([item for item in items if str(item.get(key) or "") == value])


def _next_safe_actions(
    *,
    result_status: str,
    candidates: list[dict[str, Any]],
) -> list[str]:
    if result_status == "blocked":
        return ["Review dry-run scheduler settings; do not enable live position management."]
    if result_status == "error":
        return ["Review candidate detection errors and rerun the dry-run after the read path is healthy."]
    if not candidates:
        return ["Continue monitoring held positions before evaluating new entries."]
    actions = [
        "Review critical and warning exit candidates in Logs.",
        "Use sell preflight only from existing operator-reviewed controls.",
    ]
    if _count(candidates, "candidate_type", "sync_required"):
        actions.insert(0, "Review order sync-required items before any sell preflight.")
    if _count(candidates, "candidate_type", "duplicate_sell_conflict"):
        actions.insert(0, "Review duplicate open sell conflicts before any new exit workflow.")
    return _dedupe(actions)


def _safety() -> dict[str, Any]:
    return {
        "read_only": False,
        "dry_run_only": True,
        "positions_first": True,
        "entry_orders_allowed": False,
        "exit_orders_allowed": False,
        "allow_live_orders": False,
        "real_order_submit_allowed": False,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "guarded_sell_called": False,
        "setting_changed": False,
        "scheduler_changed": False,
        "dry_run_changed": False,
        "kill_switch_changed": False,
        "kis_real_order_changed": False,
    }


def _json(value: Any) -> str:
    return json.dumps(sanitize_kis_payload(value), ensure_ascii=False, default=str)


def _parse_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(UTC)
    return value.replace(tzinfo=None)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result
