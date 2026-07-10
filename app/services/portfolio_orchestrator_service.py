from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, time, timedelta
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, TradeRunLog
from app.schemas.portfolio_orchestrator import PortfolioOrchestratorRunRequest
from app.services.auto_buy_live_phase1_service import AutoBuyLivePhase1Service
from app.services.auto_sell_live_phase1_service import AutoSellLivePhase1Service
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.ops_production_readiness_service import OpsProductionReadinessService
from app.services.position_management_dry_run_service import PositionManagementDryRunService
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "portfolio_orchestrator"
PROVIDER = "kis"
MARKET = "KR"
KST = ZoneInfo("Asia/Seoul")

OPEN_ORDER_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
    "PENDING_SUBMIT",
}
SYNC_REQUIRED_STATUSES = {
    "UNKNOWN",
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
}
COUNTED_TRADE_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}
PHASE_SUBMITTED_STATUSES = {"submitted", "filled"}
PHASE_CRITICAL_STATUSES = {
    "blocked",
    "dry_run_blocked",
    "pending_sync",
    "rejected",
    "error",
}
PHASE_SAFE_NO_ACTION_STATUSES = {"disabled", "skipped"}
_RUN_LOCK = Lock()


class PortfolioOrchestratorService:
    """Coordinates existing safety services for one position-first cycle.

    Live execution remains owned exclusively by the phase-one buy and sell
    services. This layer performs global checks and invokes each phase at most
    once.
    """

    def __init__(
        self,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        readiness_service: OpsProductionReadinessService | None = None,
        position_management_service: PositionManagementDryRunService | None = None,
        auto_sell_service: AutoSellLivePhase1Service | None = None,
        auto_buy_service: AutoBuyLivePhase1Service | None = None,
    ) -> None:
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.readiness_service = readiness_service or OpsProductionReadinessService(
            runtime_settings=self.runtime_settings
        )
        self.position_management_service = position_management_service
        self.auto_sell_service = auto_sell_service
        self.auto_buy_service = auto_buy_service

    def run_once(
        self,
        db: Session,
        request: PortfolioOrchestratorRunRequest | dict[str, Any] | None = None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        payload = (
            request
            if isinstance(request, PortfolioOrchestratorRunRequest)
            else PortfolioOrchestratorRunRequest.model_validate(request or {})
        )
        with _RUN_LOCK:
            return self._run_once_locked(db, payload, now=now)

    def _run_once_locked(
        self,
        db: Session,
        payload: PortfolioOrchestratorRunRequest,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc(now)
        settings = self.runtime_settings.get_settings_read_only(db)
        enabled = bool(settings.get("portfolio_orchestrator_enabled", False))
        allow_live = bool(
            settings.get("portfolio_orchestrator_allow_live_orders", False)
        )
        daily_limit = max(0, _int(settings.get("max_trades_per_day"), 0))
        daily_used = self._daily_trade_count(
            db,
            provider=payload.provider,
            market=payload.market,
            now_utc=now_utc,
        )
        state = self._base_response(
            payload=payload,
            generated_at=now_utc,
            enabled=enabled,
            allow_live=allow_live,
            daily_used=daily_used,
            daily_limit=daily_limit,
        )

        def check(key: str, ok: bool, reason: str, detail: str) -> bool:
            state["checklist"].append(
                {
                    "key": key,
                    "ok": bool(ok),
                    "status": "pass" if ok else "fail",
                    "blocking": not bool(ok),
                    "reason": None if ok else reason,
                    "detail": detail,
                }
            )
            if not ok:
                state["risk_flags"].append(reason)
            return bool(ok)

        def finish(
            result_status: str,
            *,
            reason: str | None = None,
            next_safe_action: str | None = None,
        ) -> dict[str, Any]:
            state["result_status"] = result_status
            state["primary_block_reason"] = reason
            state["next_safe_action"] = next_safe_action or _next_safe_action(
                result_status,
                reason,
            )
            state["risk_flags"] = _dedupe(state["risk_flags"])
            state["gating_notes"] = _dedupe(state["gating_notes"])
            state["safety"] = {
                "positions_first": True,
                "single_action_limit": True,
                "direct_broker_execution_called": False,
                "direct_manual_execution_called": False,
                "phase_calls_only": True,
                "settings_changed": False,
                "scheduler_changed": False,
                "dry_run_changed": False,
                "kill_switch_changed": False,
                "kis_real_order_enabled_changed": False,
                "single_attempt_per_phase": True,
            }
            return self._save_run(
                db,
                payload=payload,
                response=state,
                now_utc=now_utc,
            )

        if not check(
            "portfolio_orchestrator_enabled",
            enabled,
            "portfolio_orchestrator_disabled",
            "The portfolio orchestrator must be explicitly enabled.",
        ):
            return finish(
                "disabled",
                reason="portfolio_orchestrator_disabled",
                next_safe_action="enable_portfolio_orchestrator_explicitly",
            )

        if not check(
            "kill_switch_false",
            not bool(settings.get("kill_switch")),
            "kill_switch_enabled",
            "The global kill switch must be false.",
        ):
            return finish("blocked", reason="kill_switch_enabled")

        positions_first_configured = bool(
            settings.get("portfolio_orchestrator_positions_first", True)
        )
        if not check(
            "positions_first_required",
            positions_first_configured,
            "positions_first_required",
            "Position management must precede every entry phase.",
        ):
            return finish("blocked", reason="positions_first_required")

        if payload.mode == "live_phase1_controlled":
            if not check(
                "portfolio_orchestrator_allow_live_orders",
                allow_live,
                "portfolio_orchestrator_live_orders_disabled",
                "The separate orchestrator live-order switch must be enabled.",
            ):
                return finish(
                    "blocked",
                    reason="portfolio_orchestrator_live_orders_disabled",
                )
            if not check(
                "dry_run_false",
                not bool(settings.get("dry_run", True)),
                "dry_run_enabled",
                "Controlled live mode requires the existing runtime dry-run flag to be false.",
            ):
                return finish("blocked", reason="dry_run_enabled")
            kis_enabled, kis_real_enabled = self._kis_runtime_flags()
            if not check(
                "kis_runtime_ready",
                kis_enabled and kis_real_enabled,
                "kis_real_order_disabled",
                "KIS and its existing real-order capability must already be enabled.",
            ):
                return finish("blocked", reason="kis_real_order_disabled")
        else:
            check(
                "dry_run_monitoring_mode",
                True,
                "dry_run_monitoring_mode_required",
                "Monitoring mode cannot invoke a live phase.",
            )

        readiness: dict[str, Any]
        try:
            readiness = self.readiness_service.readiness(
                db,
                provider=payload.provider,
                market=payload.market,
                include_details=False,
                include_recent=payload.mode == "live_phase1_controlled",
                now=now_utc,
            )
        except Exception as exc:
            reason = f"production_readiness_failed:{exc.__class__.__name__}"
            return finish("error", reason=reason)

        readiness_status = str(readiness.get("overall_status") or "unknown").lower()
        state["production_readiness_status"] = readiness_status
        if payload.mode == "dry_run_monitoring":
            readiness_ok = _monitoring_readiness_ok(readiness)
        else:
            readiness_ok = readiness_status == "ready"
        if not check(
            "production_readiness_acceptable",
            readiness_ok,
            "production_readiness_not_ready",
            f"Production readiness status is {readiness_status}.",
        ):
            return finish("blocked", reason="production_readiness_not_ready")

        conflicts = self._global_order_conflicts(
            db,
            provider=payload.provider,
            market=payload.market,
            now_utc=now_utc,
        )
        state["sync_required_count"] = conflicts["sync_required_count"]
        state["pending_order_conflict_count"] = conflicts[
            "pending_order_conflict_count"
        ]
        no_conflict = state["pending_order_conflict_count"] == 0
        if not check(
            "no_global_order_conflict",
            no_conflict,
            "global_order_conflict_exists",
            (
                "No pending, stale, unknown, or synchronization-required order may "
                "exist before a portfolio cycle."
            ),
        ):
            reason = (
                "sync_required_order_exists"
                if state["sync_required_count"] > 0
                else "pending_order_conflict_exists"
            )
            state["skipped_sell_reason"] = reason
            state["skipped_buy_reason"] = reason
            return finish("blocked", reason=reason)

        limit_available = daily_limit <= 0 or daily_used < daily_limit
        if not check(
            "daily_total_trade_limit_available",
            limit_available,
            "daily_total_trade_limit_reached",
            f"Global daily trade usage is {daily_used}/{daily_limit}.",
        ):
            state["skipped_sell_reason"] = "daily_total_trade_limit_reached"
            state["skipped_buy_reason"] = "daily_total_trade_limit_reached"
            return finish("blocked", reason="daily_total_trade_limit_reached")

        if self.position_management_service is None:
            return finish("error", reason="position_management_service_unavailable")
        try:
            raw_position_result = self.position_management_service.run_once(
                db,
                {
                    "provider": payload.provider,
                    "market": payload.market,
                    "trigger_source": "portfolio_orchestrator_positions_first",
                    "include_sell_preflight": True,
                },
                require_enabled=False,
                now=now_utc,
            )
        except Exception as exc:
            reason = f"position_management_failed:{exc.__class__.__name__}"
            return finish("error", reason=reason)

        position_result = _mapping(raw_position_result)
        state["position_management_result"] = position_result
        state["risk_flags"].extend(_strings(position_result.get("risk_flags")))
        state["gating_notes"].extend(_strings(position_result.get("gating_notes")))
        state["gating_notes"].append(
            "Position management completed before any entry phase was considered."
        )
        critical_count = max(
            0,
            _int(position_result.get("critical_candidate_count"), 0),
        )
        position_candidates = _candidate_list(position_result)
        critical_count = max(
            critical_count,
            sum(
                1
                for item in position_candidates
                if str(item.get("severity") or "").lower() == "critical"
            ),
        )
        candidate_count = max(
            critical_count,
            _int(position_result.get("exit_candidate_count"), 0),
            len(position_candidates),
        )
        position_sync_count = max(
            0,
            _int(position_result.get("sync_required_count"), 0),
            sum(
                1
                for item in position_candidates
                if str(item.get("candidate_type") or "").lower()
                == "sync_required"
                or bool(item.get("sync_required"))
            ),
        )
        state["critical_exit_candidate_count"] = critical_count
        state["sync_required_count"] = max(
            state["sync_required_count"],
            position_sync_count,
        )
        position_status = str(position_result.get("result_status") or "error").lower()
        if position_status in {"blocked", "error"}:
            reason = str(
                position_result.get("primary_reason")
                or "position_management_dry_run_blocked"
            )
            state["skipped_sell_reason"] = reason
            state["skipped_buy_reason"] = reason
            return finish(
                "error" if position_status == "error" else "blocked",
                reason=reason,
            )
        if position_status not in {"completed", "skipped"}:
            reason = "position_management_unexpected_result"
            state["skipped_sell_reason"] = reason
            state["skipped_buy_reason"] = reason
            return finish("error", reason=reason)
        position_safety_ok = (
            position_result.get("dry_run_only") is True
            and position_result.get("real_order_submitted") is not True
            and position_result.get("broker_submit_called") is not True
            and position_result.get("manual_submit_called") is not True
        )
        if not position_safety_ok:
            reason = "position_management_safety_invariant_failed"
            state["skipped_sell_reason"] = reason
            state["skipped_buy_reason"] = reason
            return finish("error", reason=reason)

        if position_sync_count > 0:
            reason = "position_management_sync_required"
            state["skipped_sell_reason"] = reason
            state["skipped_buy_reason"] = reason
            return finish("blocked", reason=reason)

        duplicate_conflict_count = max(
            0,
            _int(position_result.get("duplicate_sell_conflict_count"), 0),
            sum(
                1
                for item in position_candidates
                if str(item.get("candidate_type") or "").lower()
                == "duplicate_sell_conflict"
                or bool(item.get("open_sell_order_conflict"))
            ),
        )
        if duplicate_conflict_count > 0:
            reason = "position_management_duplicate_sell_conflict"
            state["pending_order_conflict_count"] = max(
                state["pending_order_conflict_count"],
                duplicate_conflict_count,
            )
            state["skipped_sell_reason"] = reason
            state["skipped_buy_reason"] = reason
            return finish("blocked", reason=reason)

        if payload.mode == "dry_run_monitoring":
            state["skipped_sell_reason"] = "dry_run_monitoring_mode"
            state["skipped_buy_reason"] = "dry_run_monitoring_mode"
            return finish(
                "dry_run_completed",
                next_safe_action="review_position_management_result",
            )

        blocked_preflight_count = max(
            0,
            _int(position_result.get("blocked_preflight_count"), 0),
        )
        if blocked_preflight_count > 0:
            reason = "position_management_preflight_blocked"
            state["risk_flags"].append(reason)
            state["skipped_sell_reason"] = reason
            state["skipped_buy_reason"] = reason
            return finish("blocked", reason=reason)

        sell_candidate = _select_sell_candidate(position_result)
        blocked_candidate_present = _has_blocked_exit_candidate(position_result)
        if candidate_count > 0:
            if self.auto_sell_service is None:
                state["skipped_sell_reason"] = "auto_sell_phase1_service_unavailable"
                state["skipped_buy_reason"] = "auto_sell_phase1_service_unavailable"
                return finish(
                    "error",
                    reason="auto_sell_phase1_service_unavailable",
                )
            try:
                sell_result = self.auto_sell_service.run_once(
                    db,
                    {
                        "provider": payload.provider,
                        "market": payload.market,
                        "symbol": _text(sell_candidate.get("symbol")),
                        "candidate_id": _text(sell_candidate.get("candidate_id")),
                        "trigger_source": "scheduler_phase1",
                        "language": payload.language,
                        "locale": payload.locale,
                    },
                    now=now_utc,
                )
            except Exception as exc:
                reason = f"auto_sell_phase1_failed:{exc.__class__.__name__}"
                state["skipped_buy_reason"] = reason
                return finish("error", reason=reason)

            state["auto_sell_phase1_result"] = _mapping(sell_result)
            self._merge_phase_result(state, sell_result)
            sell_status = str(sell_result.get("result_status") or "error").lower()
            sell_reason = _text(sell_result.get("primary_block_reason"))
            if _phase_submitted(sell_result):
                self._select_action(state, "auto_sell_phase1", sell_result, daily_limit)
                self._refresh_daily_usage(
                    state,
                    db,
                    provider=payload.provider,
                    market=payload.market,
                    now_utc=now_utc,
                    daily_limit=daily_limit,
                )
                state["skipped_buy_reason"] = "auto_sell_phase1_submitted"
                return finish(
                    "sell_submitted",
                    next_safe_action="sync_and_review_submitted_sell",
                )

            state["skipped_sell_reason"] = sell_reason or sell_status
            if _phase_result_ambiguous(sell_result):
                self._record_phase_attempt(state, sell_result)
                state["skipped_buy_reason"] = "auto_sell_phase1_broker_result_ambiguous"
                self._refresh_daily_usage(
                    state,
                    db,
                    provider=payload.provider,
                    market=payload.market,
                    now_utc=now_utc,
                    daily_limit=daily_limit,
                )
                return finish(
                    "blocked",
                    reason="auto_sell_phase1_broker_result_ambiguous",
                    next_safe_action="sync_and_review_sell_result",
                )
            if sell_status not in (
                PHASE_SAFE_NO_ACTION_STATUSES | PHASE_CRITICAL_STATUSES
            ):
                reason = "auto_sell_phase1_unexpected_result"
                state["skipped_buy_reason"] = reason
                return finish("error", reason=reason)
            skip_for_candidate = bool(
                settings.get("portfolio_orchestrator_skip_buy_if_sell_candidate", True)
            )
            critical_block = (
                critical_count > 0
                or blocked_candidate_present
                or sell_status in PHASE_CRITICAL_STATUSES
                or bool(
                    settings.get(
                        "portfolio_orchestrator_skip_buy_if_exit_critical",
                        True,
                    )
                    and critical_count > 0
                )
            )
            if critical_block or skip_for_candidate:
                reason = (
                    "critical_exit_candidate_unresolved"
                    if critical_count > 0
                    else (
                        "blocked_exit_candidate_unresolved"
                        if blocked_candidate_present
                        else sell_reason or "sell_candidate_requires_review"
                    )
                )
                state["skipped_buy_reason"] = reason
                result_status = (
                    "error" if sell_status == "error" else "blocked"
                )
                return finish(result_status, reason=reason)
        else:
            state["skipped_sell_reason"] = "no_exit_candidate"

        if self.auto_buy_service is None:
            state["skipped_buy_reason"] = "auto_buy_phase1_service_unavailable"
            return finish("error", reason="auto_buy_phase1_service_unavailable")
        try:
            buy_result = self.auto_buy_service.run_once(
                db,
                {
                    "provider": payload.provider,
                    "market": payload.market,
                    "trigger_source": "scheduler_phase1",
                    "language": payload.language,
                    "locale": payload.locale,
                },
                now=now_utc,
            )
        except Exception as exc:
            reason = f"auto_buy_phase1_failed:{exc.__class__.__name__}"
            state["skipped_buy_reason"] = reason
            return finish("error", reason=reason)

        state["auto_buy_phase1_result"] = _mapping(buy_result)
        self._merge_phase_result(state, buy_result)
        buy_status = str(buy_result.get("result_status") or "error").lower()
        buy_reason = _text(buy_result.get("primary_block_reason"))
        if _phase_submitted(buy_result):
            self._select_action(state, "auto_buy_phase1", buy_result, daily_limit)
            self._refresh_daily_usage(
                state,
                db,
                provider=payload.provider,
                market=payload.market,
                now_utc=now_utc,
                daily_limit=daily_limit,
            )
            return finish(
                "buy_submitted",
                next_safe_action="sync_and_review_submitted_buy",
            )

        state["skipped_buy_reason"] = buy_reason or buy_status
        if _phase_result_ambiguous(buy_result):
            self._record_phase_attempt(state, buy_result)
            self._refresh_daily_usage(
                state,
                db,
                provider=payload.provider,
                market=payload.market,
                now_utc=now_utc,
                daily_limit=daily_limit,
            )
            return finish(
                "blocked",
                reason="auto_buy_phase1_broker_result_ambiguous",
                next_safe_action="sync_and_review_buy_result",
            )
        if buy_status == "error":
            return finish("error", reason=buy_reason or "auto_buy_phase1_error")
        if buy_status in PHASE_CRITICAL_STATUSES:
            return finish(
                "blocked",
                reason=buy_reason or "auto_buy_phase1_blocked",
            )
        if buy_status not in PHASE_SAFE_NO_ACTION_STATUSES:
            return finish(
                "error",
                reason="auto_buy_phase1_unexpected_result",
            )
        return finish(
            "completed_no_action",
            next_safe_action=_text(buy_result.get("next_safe_action"))
            or "continue_monitoring",
        )

    def latest(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        row = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == MODE)
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .first()
        )
        if row is not None:
            response = _parse_object(row.response_payload)
            if response:
                response["run_id"] = response.get("run_id") or row.id
                return sanitize_kis_payload(response)

        payload = PortfolioOrchestratorRunRequest(
            provider=provider,
            market=market,
        )
        settings = self.runtime_settings.get_settings_read_only(db)
        enabled = bool(settings.get("portfolio_orchestrator_enabled", False))
        daily_limit = max(0, _int(settings.get("max_trades_per_day"), 0))
        daily_used = self._daily_trade_count(
            db,
            provider=payload.provider,
            market=payload.market,
            now_utc=_utc(now),
        )
        response = self._base_response(
            payload=payload,
            generated_at=_utc(now),
            enabled=enabled,
            allow_live=bool(
                settings.get("portfolio_orchestrator_allow_live_orders", False)
            ),
            daily_used=daily_used,
            daily_limit=daily_limit,
        )
        response["result_status"] = "completed_no_action" if enabled else "disabled"
        response["primary_block_reason"] = (
            None if enabled else "portfolio_orchestrator_disabled"
        )
        response["next_safe_action"] = (
            "run_dry_run_monitoring"
            if enabled
            else "enable_portfolio_orchestrator_explicitly"
        )
        response["safety"] = {
            "positions_first": True,
            "single_action_limit": True,
            "phase_calls_only": True,
            "read_only": True,
        }
        return sanitize_kis_payload(response)

    def latest_run(self, db: Session, **kwargs: Any) -> dict[str, Any]:
        return self.latest(db, **kwargs)

    def _base_response(
        self,
        *,
        payload: PortfolioOrchestratorRunRequest,
        generated_at: datetime,
        enabled: bool,
        allow_live: bool,
        daily_used: int,
        daily_limit: int,
    ) -> dict[str, Any]:
        return {
            "run_id": None,
            "generated_at": generated_at.isoformat(),
            "provider": payload.provider,
            "market": payload.market,
            "trigger_source": payload.trigger_source,
            "orchestrator_enabled": enabled,
            "allow_live_orders": allow_live,
            "mode": payload.mode,
            "positions_first": True,
            "max_actions_per_run": 1,
            "result_status": "completed_no_action",
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "action_taken": "none",
            "position_management_result": None,
            "auto_sell_phase1_result": None,
            "auto_buy_phase1_result": None,
            "skipped_buy_reason": None,
            "skipped_sell_reason": None,
            "daily_trade_limit_used": daily_used,
            "daily_trade_limit_remaining": _remaining(daily_limit, daily_used),
            "sync_required_count": 0,
            "critical_exit_candidate_count": 0,
            "pending_order_conflict_count": 0,
            "production_readiness_status": None,
            "risk_flags": [],
            "gating_notes": [
                "The orchestrator coordinates existing phase-one services only.",
                "At most one portfolio action may be selected in this cycle.",
            ],
            "checklist": [],
            "primary_block_reason": None,
            "next_safe_action": "review_orchestrator_result",
            "selected_symbol": None,
            "selected_candidate_id": None,
            "selected_promotion_id": None,
            "order_id": None,
            "broker_order_id": None,
            "kis_odno": None,
            "safety": {},
        }

    def _kis_runtime_flags(self) -> tuple[bool, bool]:
        app_settings = getattr(self.runtime_settings, "settings", None)
        return (
            bool(getattr(app_settings, "kis_enabled", False)),
            bool(getattr(app_settings, "kis_real_order_enabled", False)),
        )

    def _global_order_conflicts(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
        now_utc: datetime,
    ) -> dict[str, int]:
        rows = (
            db.query(OrderLog)
            .filter(OrderLog.broker == provider)
            .filter(or_(OrderLog.market == market, OrderLog.market.is_(None)))
            .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
            .limit(500)
            .all()
        )
        conflict_ids: set[int] = set()
        sync_ids: set[int] = set()
        for row in rows:
            status = str(row.internal_status or "").strip().upper()
            broker_text = " ".join(
                [
                    str(row.broker_status or ""),
                    str(row.broker_order_status or ""),
                    str(row.sync_error or ""),
                ]
            ).lower()
            row_id = int(row.id)
            needs_sync = (
                status in SYNC_REQUIRED_STATUSES
                or "sync_required" in broker_text
                or "pending_sync" in broker_text
            )
            stale_open = False
            if status in OPEN_ORDER_STATUSES and row.created_at is not None:
                stale_open = now_utc - _utc(row.created_at) > timedelta(hours=24)
            if needs_sync or stale_open:
                sync_ids.add(row_id)
            if status in OPEN_ORDER_STATUSES or needs_sync or stale_open:
                conflict_ids.add(row_id)
        return {
            "pending_order_conflict_count": len(conflict_ids),
            "sync_required_count": len(sync_ids),
        }

    def _daily_trade_count(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
        now_utc: datetime,
    ) -> int:
        start_utc, end_utc = _kr_day_bounds(now_utc)
        return (
            db.query(OrderLog)
            .filter(OrderLog.broker == provider)
            .filter(or_(OrderLog.market == market, OrderLog.market.is_(None)))
            .filter(OrderLog.created_at >= start_utc)
            .filter(OrderLog.created_at < end_utc)
            .filter(OrderLog.internal_status.in_(sorted(COUNTED_TRADE_STATUSES)))
            .count()
        )

    def _merge_phase_result(
        self,
        state: dict[str, Any],
        phase_result: dict[str, Any],
    ) -> None:
        state["risk_flags"].extend(_strings(phase_result.get("risk_flags")))
        state["gating_notes"].extend(_strings(phase_result.get("gating_notes")))
        state["real_order_submitted"] = bool(
            state["real_order_submitted"]
            or phase_result.get("real_order_submitted")
        )
        state["broker_submit_called"] = bool(
            state["broker_submit_called"]
            or phase_result.get("broker_submit_called")
        )
        state["manual_submit_called"] = bool(
            state["manual_submit_called"]
            or phase_result.get("manual_submit_called")
        )

    def _select_action(
        self,
        state: dict[str, Any],
        action: str,
        phase_result: dict[str, Any],
        daily_limit: int,
    ) -> None:
        state["action_taken"] = action
        state["real_order_submitted"] = True
        state["selected_symbol"] = _text(phase_result.get("selected_symbol"))
        state["selected_candidate_id"] = _text(
            phase_result.get("selected_candidate_id")
        )
        state["selected_promotion_id"] = _int_or_none(
            phase_result.get("selected_promotion_id")
        )
        state["order_id"] = _int_or_none(phase_result.get("order_id"))
        state["broker_order_id"] = _text(phase_result.get("broker_order_id"))
        state["kis_odno"] = _text(phase_result.get("kis_odno"))
        state["daily_trade_limit_used"] = int(state["daily_trade_limit_used"]) + 1
        state["daily_trade_limit_remaining"] = _remaining(
            daily_limit,
            int(state["daily_trade_limit_used"]),
        )

    def _record_phase_attempt(
        self,
        state: dict[str, Any],
        phase_result: dict[str, Any],
    ) -> None:
        state["selected_symbol"] = _text(phase_result.get("selected_symbol"))
        state["selected_candidate_id"] = _text(
            phase_result.get("selected_candidate_id")
        )
        state["selected_promotion_id"] = _int_or_none(
            phase_result.get("selected_promotion_id")
        )
        state["order_id"] = _int_or_none(phase_result.get("order_id"))
        state["broker_order_id"] = _text(phase_result.get("broker_order_id"))
        state["kis_odno"] = _text(phase_result.get("kis_odno"))

    def _refresh_daily_usage(
        self,
        state: dict[str, Any],
        db: Session,
        *,
        provider: str,
        market: str,
        now_utc: datetime,
        daily_limit: int,
    ) -> None:
        persisted_used = self._daily_trade_count(
            db,
            provider=provider,
            market=market,
            now_utc=now_utc,
        )
        state["daily_trade_limit_used"] = max(
            int(state["daily_trade_limit_used"]),
            persisted_used,
        )
        state["daily_trade_limit_remaining"] = _remaining(
            daily_limit,
            int(state["daily_trade_limit_used"]),
        )

    def _save_run(
        self,
        db: Session,
        *,
        payload: PortfolioOrchestratorRunRequest,
        response: dict[str, Any],
        now_utc: datetime,
    ) -> dict[str, Any]:
        safe_response = sanitize_kis_payload(response)
        row = TradeRunLog(
            run_key=f"portfolio_orchestrator_{uuid.uuid4().hex[:12]}",
            trigger_source=payload.trigger_source[:40],
            symbol=str(safe_response.get("selected_symbol") or "PORTFOLIO")[:20],
            mode=MODE,
            stage="done",
            result=str(safe_response.get("result_status") or "error")[:40],
            reason=_text(safe_response.get("primary_block_reason")),
            order_id=_int_or_none(safe_response.get("order_id")),
            request_payload=_json(
                {
                    **payload.model_dump(mode="json"),
                    "positions_first": True,
                    "max_actions_per_run": 1,
                }
            ),
            response_payload=_json(safe_response),
            created_at=now_utc.replace(tzinfo=None),
        )
        db.add(row)
        db.flush()
        safe_response["run_id"] = row.id
        row.response_payload = _json(safe_response)
        db.commit()
        return sanitize_kis_payload(safe_response)


def _phase_submitted(result: dict[str, Any]) -> bool:
    return bool(result.get("real_order_submitted"))


def _phase_result_ambiguous(result: dict[str, Any]) -> bool:
    status = str(result.get("result_status") or "").lower()
    return bool(
        result.get("broker_submit_called")
        or result.get("manual_submit_called")
        or status in (PHASE_SUBMITTED_STATUSES | {"pending_sync"})
    )


def _monitoring_readiness_ok(readiness: dict[str, Any]) -> bool:
    status = str(readiness.get("overall_status") or "unknown").lower()
    if status in {"ready", "warning"}:
        return True
    checklist = readiness.get("checklist")
    if status != "blocked" or not isinstance(checklist, list) or not checklist:
        return False
    live_only_blockers = {
        "dry_run_blocks_live_submit",
        "kis_real_order_enabled_for_live",
        "guarded_live_buy_ready",
        "guarded_live_sell_ready",
    }
    for item in checklist:
        if not isinstance(item, dict):
            return False
        failed = item.get("status") == "fail" or bool(item.get("blocking"))
        if failed and str(item.get("key") or "") not in live_only_blockers:
            return False
    return True


def _select_sell_candidate(position_result: dict[str, Any]) -> dict[str, Any]:
    items = _candidate_list(position_result)
    items.sort(
        key=lambda item: (
            0 if _sell_candidate_executable(item) else 1,
            0 if str(item.get("severity") or "").lower() == "critical" else 1,
            str(item.get("candidate_id") or ""),
        )
    )
    return items[0] if items else {}


def _candidate_list(position_result: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = position_result.get("candidates")
    if not isinstance(candidates, list):
        return []
    return [dict(item) for item in candidates if isinstance(item, dict)]


def _sell_candidate_executable(candidate: dict[str, Any]) -> bool:
    candidate_type = str(candidate.get("candidate_type") or "").lower()
    severity = str(candidate.get("severity") or "").lower()
    type_and_severity_allowed = (
        severity == "critical"
        and candidate_type
        in {"stop_loss", "take_profit", "trend_breakdown", "weak_momentum"}
    ) or (
        severity == "warning"
        and candidate_type in {"take_profit", "trend_breakdown"}
    )
    return (
        str(candidate.get("status") or "active").lower() == "active"
        and type_and_severity_allowed
        and candidate.get("can_run_sell_preflight") is not False
        and not bool(candidate.get("sync_required"))
        and not bool(candidate.get("open_sell_order_conflict"))
    )


def _has_blocked_exit_candidate(position_result: dict[str, Any]) -> bool:
    candidates = position_result.get("candidates")
    if not isinstance(candidates, list):
        return False
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        candidate_type = str(raw.get("candidate_type") or "").lower()
        if candidate_type in {"duplicate_sell_conflict", "sync_required", "manual_review"}:
            return True
        if bool(raw.get("sync_required")) or bool(raw.get("open_sell_order_conflict")):
            return True
    return False


def _next_safe_action(result_status: str, reason: str | None) -> str:
    if result_status == "disabled":
        return "enable_portfolio_orchestrator_explicitly"
    if reason in {"sync_required_order_exists", "position_management_sync_required"}:
        return "reconcile_orders_before_next_cycle"
    if reason == "pending_order_conflict_exists":
        return "wait_for_open_orders_to_settle"
    if reason == "daily_total_trade_limit_reached":
        return "wait_for_next_trading_day"
    if reason in {"kill_switch_enabled", "production_readiness_not_ready"}:
        return "review_global_safety_state"
    if result_status == "error":
        return "review_orchestrator_error"
    if result_status == "blocked":
        return "review_primary_block_reason"
    return "continue_monitoring"


def _kr_day_bounds(now_utc: datetime) -> tuple[datetime, datetime]:
    local = _utc(now_utc).astimezone(KST)
    start_local = datetime.combine(local.date(), time.min, tzinfo=KST)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC).replace(tzinfo=None), end_local.astimezone(
        UTC
    ).replace(tzinfo=None)


def _remaining(limit: int, used: int) -> int:
    return max(0, int(limit) - int(used)) if limit > 0 else 0


def _utc(value: Any | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value))
    except Exception:
        return datetime.now(UTC)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _parse_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json(value: Any) -> str:
    return json.dumps(sanitize_kis_payload(value), ensure_ascii=False, default=str)


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in values if str(item or "").strip()))
