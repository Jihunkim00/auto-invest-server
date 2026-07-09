from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, StrategyAutoBuyPromotion, TradeRunLog
from app.schemas.strategy_auto_buy_scheduler import AutoBuyLivePhase1RunRequest
from app.schemas.strategy_live_auto_buy import (
    ProfileAwareGuardedLiveAutoBuyRunRequest,
)
from app.services.auto_exit_candidate_service import AutoExitCandidateService
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.ops_production_readiness_service import (
    OpsProductionReadinessService,
)
from app.services.position_management_dry_run_service import (
    PositionManagementDryRunService,
)
from app.services.profile_aware_guarded_live_auto_buy_service import (
    ProfileAwareGuardedLiveAutoBuyService,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.strategy_auto_buy_promotion_service import (
    ACTIVE_STATUSES,
    StrategyAutoBuyPromotionService,
)


MODE = "auto_buy_live_phase1"
AUTOMATION_PHASE = "phase1_auto_buy"
PROVIDER = "kis"
MARKET = "KR"
KST = ZoneInfo("Asia/Seoul")
ALLOWED_TRIGGER_SOURCES = {"manual_phase1_test", "scheduler_phase1"}
SYSTEM_APPROVED_STATUSES = {"pending", "acknowledged", "reviewed", "system_approved", "system-approved"}
SUBMITTED_RESULTS = {"submitted", "filled", "pending_sync"}
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
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
}


class AutoBuyLivePhase1Service:
    """Controlled phase-one automation wrapper for promotion-queue live buys."""

    def __init__(
        self,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        promotion_service: StrategyAutoBuyPromotionService | None = None,
        guarded_buy_service: ProfileAwareGuardedLiveAutoBuyService | None = None,
        readiness_service: OpsProductionReadinessService | None = None,
        auto_exit_candidates: AutoExitCandidateService | None = None,
        position_management_service: PositionManagementDryRunService | None = None,
    ) -> None:
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.promotion_service = promotion_service or StrategyAutoBuyPromotionService()
        self.guarded_buy_service = guarded_buy_service or ProfileAwareGuardedLiveAutoBuyService()
        self.readiness_service = readiness_service or OpsProductionReadinessService(
            runtime_settings=self.runtime_settings
        )
        self.auto_exit_candidates = auto_exit_candidates
        self.position_management_service = position_management_service

    def status(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc(now)
        settings = self.runtime_settings.get_settings_read_only(db)
        latest = self.latest_run(db)
        readiness_status = None
        try:
            readiness_status = str(
                self.readiness_service.readiness(
                    db,
                    provider=provider,
                    market=market,
                    include_details=False,
                    include_recent=False,
                    now=now_utc,
                ).get("overall_status")
                or ""
            ) or None
        except Exception:
            readiness_status = "unknown"
        enabled = bool(settings.get("auto_buy_live_phase1_enabled"))
        return self._response(
            generated_at=now_utc,
            provider=provider,
            market=market,
            trigger_source="status",
            auto_buy_live_enabled=enabled,
            result_status="disabled" if not enabled else "skipped",
            production_readiness_status=readiness_status,
            daily_auto_buy_count=self._daily_auto_buy_count(db, now_utc=now_utc),
            daily_auto_buy_limit=_int(
                settings.get("auto_buy_live_phase1_max_orders_per_day"),
                1,
            ),
            primary_block_reason=None if enabled else "auto_buy_live_phase1_disabled",
            next_safe_action="enable_phase1_explicitly" if not enabled else "run_phase1_check",
            latest_run=latest,
            checklist=[
                _check(
                    "auto_buy_live_phase1_enabled",
                    enabled,
                    "auto_buy_live_phase1_disabled",
                    "Phase-one auto-buy live mode is explicitly enabled.",
                )
            ],
            safety=_safety(read_only=True),
        )

    def latest_run(self, db: Session) -> dict[str, Any] | None:
        row = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == MODE)
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .first()
        )
        if row is None:
            return None
        payload = _parse_object(row.response_payload)
        return {
            "run_id": row.id,
            "generated_at": _iso(row.created_at),
            "trigger_source": row.trigger_source,
            "result_status": payload.get("result_status") or row.result,
            "selected_promotion_id": payload.get("selected_promotion_id"),
            "selected_symbol": payload.get("selected_symbol"),
            "primary_block_reason": payload.get("primary_block_reason") or row.reason,
            "real_order_submitted": bool(payload.get("real_order_submitted")),
            "broker_submit_called": bool(payload.get("broker_submit_called")),
            "order_id": payload.get("order_id"),
            "broker_order_id": payload.get("broker_order_id"),
        }

    def run_once(
        self,
        db: Session,
        request: AutoBuyLivePhase1RunRequest | dict[str, Any] | None = None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        payload = (
            request
            if isinstance(request, AutoBuyLivePhase1RunRequest)
            else AutoBuyLivePhase1RunRequest.model_validate(request or {})
        )
        now_utc = _utc(now)
        settings = self.runtime_settings.get_settings_read_only(db)
        global_settings = getattr(self.runtime_settings, "settings", None)
        checklist: list[dict[str, Any]] = []
        risk_flags: list[str] = []
        gating_notes: list[str] = []
        selected: StrategyAutoBuyPromotion | None = None
        preflight: dict[str, Any] = {}
        readiness: dict[str, Any] = {}
        daily_count = self._daily_auto_buy_count(db, now_utc=now_utc)
        daily_limit = max(
            0,
            _int(settings.get("auto_buy_live_phase1_max_orders_per_day"), 1),
        )

        def block(
            reason: str,
            *,
            result_status: str = "blocked",
            next_safe_action: str | None = None,
            order_id: int | None = None,
        ) -> dict[str, Any]:
            risk_flags.append(reason)
            response = self._response(
                generated_at=now_utc,
                provider=payload.provider,
                market=payload.market,
                trigger_source=payload.trigger_source,
                auto_buy_live_enabled=bool(
                    settings.get("auto_buy_live_phase1_enabled")
                ),
                result_status=result_status,
                selected_promotion_id=selected.id if selected is not None else payload.promotion_id,
                selected_symbol=selected.symbol if selected is not None else None,
                candidate_score=_candidate_score(selected),
                production_readiness_status=readiness.get("overall_status"),
                preflight_status=preflight.get("preflight_status"),
                order_id=order_id,
                max_allowed_notional=_max_allowed_notional(settings, preflight),
                daily_auto_buy_count=daily_count,
                daily_auto_buy_limit=daily_limit,
                risk_flags=_dedupe(risk_flags),
                gating_notes=_dedupe(gating_notes),
                checklist=checklist,
                primary_block_reason=reason,
                next_safe_action=next_safe_action or _next_safe_action(result_status, reason),
            )
            return self._save_run(
                db,
                request_payload=payload.model_dump(mode="json"),
                response=response,
                result=result_status,
                reason=reason,
                symbol=response.get("selected_symbol") or "PROMOTION",
            )

        if payload.trigger_source not in ALLOWED_TRIGGER_SOURCES:
            payload.trigger_source = "manual_phase1_test"

        if not self._gate(
            checklist,
            "kill_switch_false",
            not bool(settings.get("kill_switch")),
            "kill_switch_enabled",
            "Kill switch must be false.",
        ):
            return block("kill_switch_enabled")

        if not self._gate(
            checklist,
            "dry_run_false",
            not bool(settings.get("dry_run")),
            "dry_run_enabled",
            "Runtime dry_run must be false before live submit.",
        ):
            return block("dry_run_enabled", result_status="dry_run_blocked")

        kis_ready = bool(getattr(global_settings, "kis_enabled", False)) and bool(
            getattr(global_settings, "kis_real_order_enabled", False)
        )
        if not self._gate(
            checklist,
            "kis_real_order_enabled",
            kis_ready,
            "kis_real_order_disabled",
            "KIS must be enabled and KIS real orders must be enabled.",
        ):
            return block("kis_real_order_disabled")

        enabled = bool(settings.get("auto_buy_live_phase1_enabled"))
        if not self._gate(
            checklist,
            "auto_buy_live_phase1_enabled",
            enabled,
            "auto_buy_live_phase1_disabled",
            "Phase-one auto-buy live mode is explicitly enabled.",
        ):
            return block("auto_buy_live_phase1_disabled", result_status="disabled")

        hard_switch = bool(settings.get("auto_buy_live_phase1_allow_real_orders"))
        if not self._gate(
            checklist,
            "auto_buy_live_phase1_allow_real_orders",
            hard_switch,
            "auto_buy_live_phase1_real_orders_not_allowed",
            "The extra phase-one real-order hard switch is enabled.",
        ):
            return block("auto_buy_live_phase1_real_orders_not_allowed")

        configured_provider = str(
            settings.get("auto_buy_live_phase1_provider") or PROVIDER
        ).lower()
        if not self._gate(
            checklist,
            "auto_buy_live_phase1_provider",
            configured_provider == payload.provider,
            "auto_buy_live_phase1_provider_mismatch",
            f"Phase-one provider is configured for {configured_provider}.",
        ):
            return block("auto_buy_live_phase1_provider_mismatch")

        readiness = self._production_readiness(db, payload, now_utc)
        readiness_status = str(readiness.get("overall_status") or "unknown")
        production_ready_required = bool(
            settings.get("auto_buy_live_phase1_require_production_ready", True)
        )
        production_ready = (not production_ready_required) or readiness_status == "ready"
        if not self._gate(
            checklist,
            "production_readiness_ready",
            production_ready,
            "production_readiness_not_ready",
            f"Production readiness status is {readiness_status}.",
        ):
            gating_notes.extend(_strings(readiness.get("blocking_reasons")))
            return block("production_readiness_not_ready")

        scheduler_limited = not bool(
            settings.get("strategy_auto_buy_scheduler_allow_live_orders")
        ) and not bool(settings.get("strategy_live_auto_buy_scheduler_enabled"))
        if not self._gate(
            checklist,
            "general_scheduler_live_path_disabled",
            scheduler_limited,
            "general_scheduler_live_path_enabled",
            "General scheduler live auto-buy remains disabled; only phase one is allowed.",
        ):
            return block("general_scheduler_live_path_enabled")

        conflicts = self._order_conflicts(db, now_utc=now_utc)
        if not self._gate(
            checklist,
            "no_pending_sync_orders",
            conflicts["pending_sync_count"] == 0,
            "pending_sync_order_exists",
            f"Pending-sync order count is {conflicts['pending_sync_count']}.",
        ):
            return block("pending_sync_order_exists", result_status="pending_sync")

        if not self._gate(
            checklist,
            "no_unknown_or_stale_order_conflicts",
            conflicts["unknown_or_stale_count"] == 0,
            "unknown_or_stale_order_conflict",
            f"Unknown/stale order conflict count is {conflicts['unknown_or_stale_count']}.",
        ):
            return block("unknown_or_stale_order_conflict", result_status="pending_sync")

        position_gate = self._positions_first_gate(db, payload, now_utc)
        if not self._gate(
            checklist,
            "no_critical_auto_exit_candidates",
            position_gate["critical_exit_count"] == 0,
            "critical_exit_candidate_exists",
            f"Critical exit candidate count is {position_gate['critical_exit_count']}.",
        ):
            gating_notes.extend(_strings(position_gate.get("gating_notes")))
            return block("critical_exit_candidate_exists")

        if not self._gate(
            checklist,
            "position_management_dry_run_clear",
            position_gate["position_management_blockers"] == 0,
            "position_management_dry_run_blocker",
            "Latest position-management dry-run has no critical blockers.",
        ):
            gating_notes.extend(_strings(position_gate.get("gating_notes")))
            return block("position_management_dry_run_blocker")

        if not self._gate(
            checklist,
            "daily_auto_buy_limit",
            daily_count < daily_limit,
            "daily_auto_buy_limit_reached",
            f"Phase-one auto-buy usage is {daily_count}/{daily_limit}.",
        ):
            return block("daily_auto_buy_limit_reached")

        global_trade_count = self._daily_total_trade_count(db, now_utc=now_utc)
        global_trade_limit = max(0, _int(settings.get("max_trades_per_day"), 0))
        if not self._gate(
            checklist,
            "global_daily_trade_limit",
            global_trade_limit <= 0 or global_trade_count < global_trade_limit,
            "global_daily_trade_limit_reached",
            f"Global daily trade usage is {global_trade_count}/{global_trade_limit}.",
        ):
            return block("global_daily_trade_limit_reached")

        selected_result = self._select_promotion(
            db,
            payload=payload,
            settings=settings,
            now_utc=now_utc,
        )
        selected = selected_result.get("row")
        if not selected_result.get("accepted"):
            reason = str(selected_result.get("block_reason") or "no_eligible_promotion")
            self._gate(
                checklist,
                "eligible_promotion_selected",
                False,
                reason,
                "One fresh eligible promotion is selected from the scheduler queue.",
            )
            return block(
                reason,
                result_status="skipped" if reason == "no_eligible_promotion" else "blocked",
            )
        self._gate(
            checklist,
            "eligible_promotion_selected",
            True,
            "no_eligible_promotion",
            "One fresh eligible promotion is selected from the scheduler queue.",
        )

        duplicate_symbol_count = self._duplicate_open_buy_count(
            db,
            symbol=str(selected.symbol or ""),
        )
        if not self._gate(
            checklist,
            "no_duplicate_open_buy_order",
            duplicate_symbol_count == 0,
            "duplicate_open_buy_order",
            f"Open buy orders for selected symbol: {duplicate_symbol_count}.",
        ):
            return block("duplicate_open_buy_order", result_status="pending_sync")

        preflight = self.guarded_buy_service.preflight(
            db,
            {
                "promotion_id": selected.id,
                "provider": payload.provider,
                "market": payload.market,
                "symbol": selected.symbol,
                "source_dry_run_id": selected.source_dry_run_trade_run_id,
                "max_notional_krw": _max_allowed_notional(settings, {}),
                "language": payload.language,
                "locale": payload.locale,
            },
            now=now_utc,
        )
        risk_flags.extend(_strings(preflight.get("risk_flags")))
        gating_notes.extend(_strings(preflight.get("gating_notes")))
        phase1_system_approved = _phase1_system_approved(selected, settings)
        preflight_passed = preflight.get("primary_block_reason") is None and (
            preflight.get("preflight_status") == "allowed"
            or (
                preflight.get("preflight_status") == "review_required"
                and phase1_system_approved
            )
        )
        if not self._gate(
            checklist,
            "buy_preflight_passed",
            preflight_passed,
            str(preflight.get("primary_block_reason") or "promotion_review_required"),
            "Guarded live-buy preflight has no blocking failures.",
        ):
            return block(
                str(preflight.get("primary_block_reason") or "promotion_review_required")
            )

        if not self._gate(
            checklist,
            "max_notional_and_position_sizing",
            _float(preflight.get("estimated_quantity")) is not None
            and _float(preflight.get("estimated_quantity")) > 0,
            "quantity_zero",
            "Preflight position sizing produced a positive quantity.",
        ):
            return block("quantity_zero")

        market_allowed = preflight.get("market_session_allowed") is True
        if not self._gate(
            checklist,
            "market_session_allows_new_entry",
            market_allowed,
            str(preflight.get("market_session_block_reason") or "market_closed"),
            "Market session allows a new entry.",
        ):
            return block(str(preflight.get("market_session_block_reason") or "market_closed"))

        no_new_entry_ok = not _checklist_failed(
            preflight,
            "no_new_entry_window_allowed",
        )
        if not self._gate(
            checklist,
            "no_new_entry_after_allows_entry",
            no_new_entry_ok,
            "after_no_new_entry_time",
            "No-new-entry cutoff still allows a new entry.",
        ):
            return block("after_no_new_entry_time")

        risk_gate_ok = not _checklist_failed(preflight, "risk_gate_passed")
        if not self._gate(
            checklist,
            "risk_engine_gates_passed",
            risk_gate_ok,
            str(preflight.get("primary_block_reason") or "target_risk_rejected"),
            "Risk engine gates passed in guarded live-buy preflight.",
        ):
            return block(str(preflight.get("primary_block_reason") or "target_risk_rejected"))

        submit_request = ProfileAwareGuardedLiveAutoBuyRunRequest(
            provider=payload.provider,
            market=payload.market,
            symbol=selected.symbol,
            confirm_operator_ack=True,
            promotion_id=selected.id,
            source_dry_run_id=selected.source_dry_run_trade_run_id,
            max_notional_krw=_max_allowed_notional(settings, preflight),
            trigger_source=MODE,
            client_request_id=f"{MODE}:{uuid.uuid4().hex}",
        )
        guarded_result = self.guarded_buy_service.run_once(
            db,
            submit_request,
            now=now_utc,
        )
        result_status = _map_guarded_result_status(guarded_result)
        safety = guarded_result.get("safety") if isinstance(guarded_result.get("safety"), dict) else {}
        response = self._response(
            generated_at=now_utc,
            provider=payload.provider,
            market=payload.market,
            trigger_source=payload.trigger_source,
            auto_buy_live_enabled=True,
            result_status=result_status,
            real_order_submitted=bool(safety.get("real_order_submitted") or guarded_result.get("submitted")),
            broker_submit_called=bool(safety.get("broker_submit_called")),
            manual_submit_called=bool(safety.get("manual_submit_called")),
            selected_promotion_id=selected.id,
            selected_symbol=selected.symbol,
            candidate_score=_candidate_score(selected),
            production_readiness_status=readiness.get("overall_status"),
            preflight_status=str(preflight.get("preflight_status") or ""),
            order_id=_int_or_none(guarded_result.get("related_order_id")),
            broker_order_id=_text(guarded_result.get("broker_order_id")),
            kis_odno=_text(guarded_result.get("broker_order_id")),
            submitted_quantity=_float(guarded_result.get("quantity")),
            submitted_notional=_float(guarded_result.get("submitted_notional_krw")),
            max_allowed_notional=_max_allowed_notional(settings, preflight),
            daily_auto_buy_count=daily_count,
            daily_auto_buy_limit=daily_limit,
            risk_flags=_dedupe(risk_flags + _strings(guarded_result.get("risk_flags"))),
            gating_notes=_dedupe(
                gating_notes
                + _strings(guarded_result.get("gating_notes"))
                + ["No retry is attempted by phase-one auto-buy."]
            ),
            checklist=checklist,
            primary_block_reason=_text(guarded_result.get("block_reason")),
            next_safe_action=_next_safe_action(
                result_status,
                _text(guarded_result.get("block_reason")),
            ),
            safety={
                **_safety(read_only=False),
                **safety,
                "phase1_auto_buy": True,
                "manual_submit_called": bool(safety.get("manual_submit_called")),
                "scheduler_changed": False,
                "setting_changed": False,
                "retry_attempted": False,
                "sell_submit_called": False,
            },
        )
        return self._save_run(
            db,
            request_payload=payload.model_dump(mode="json"),
            response=response,
            result=result_status,
            reason=response.get("primary_block_reason") or result_status,
            symbol=response.get("selected_symbol") or "PROMOTION",
            order_id=response.get("order_id"),
        )

    def _gate(
        self,
        checklist: list[dict[str, Any]],
        key: str,
        ok: bool,
        reason: str,
        detail: str,
    ) -> bool:
        checklist.append(_check(key, ok, reason, detail))
        return bool(ok)

    def _production_readiness(
        self,
        db: Session,
        payload: AutoBuyLivePhase1RunRequest,
        now_utc: datetime,
    ) -> dict[str, Any]:
        try:
            result = self.readiness_service.readiness(
                db,
                provider=payload.provider,
                market=payload.market,
                include_details=True,
                include_recent=True,
                now=now_utc,
            )
            return dict(result) if isinstance(result, dict) else {}
        except Exception as exc:
            return {
                "overall_status": "unknown",
                "blocking_reasons": [f"production_readiness_error:{exc.__class__.__name__}"],
            }

    def _positions_first_gate(
        self,
        db: Session,
        payload: AutoBuyLivePhase1RunRequest,
        now_utc: datetime,
    ) -> dict[str, Any]:
        critical_exit_count = 0
        blockers = 0
        notes: list[str] = []
        if self.auto_exit_candidates is not None:
            try:
                candidates_payload = self.auto_exit_candidates.candidates(
                    db,
                    provider=payload.provider,
                    market=payload.market,
                    include_details=True,
                    min_severity="info",
                )
                summary = candidates_payload.get("summary")
                if isinstance(summary, dict):
                    critical_exit_count = _int(summary.get("critical_count"), 0)
                    blockers += _int(summary.get("sync_required_count"), 0)
                    blockers += _int(summary.get("duplicate_sell_block_count"), 0)
                notes.extend(_strings(candidates_payload.get("safety_flags")))
            except Exception as exc:
                blockers += 1
                notes.append(f"auto_exit_candidates_unavailable:{exc.__class__.__name__}")

        if self.position_management_service is not None:
            try:
                latest = self.position_management_service.latest(
                    db,
                    provider=payload.provider,
                    market=payload.market,
                )
                reason = str(latest.get("primary_reason") or latest.get("primary_block_reason") or "")
                if latest.get("result_status") == "error":
                    blockers += 1
                if _int(latest.get("critical_candidate_count"), 0) > 0:
                    blockers += _int(latest.get("critical_candidate_count"), 0)
                if _int(latest.get("blocked_preflight_count"), 0) > 0:
                    blockers += _int(latest.get("blocked_preflight_count"), 0)
                if reason == "no_recent_position_management_dry_run":
                    notes.append("No recent position-management dry-run exists; direct exit-candidate gate was used.")
            except Exception as exc:
                notes.append(f"position_management_latest_unavailable:{exc.__class__.__name__}")
        return {
            "critical_exit_count": critical_exit_count,
            "position_management_blockers": blockers,
            "gating_notes": notes,
        }

    def _select_promotion(
        self,
        db: Session,
        *,
        payload: AutoBuyLivePhase1RunRequest,
        settings: dict[str, Any],
        now_utc: datetime,
    ) -> dict[str, Any]:
        if payload.promotion_id is not None:
            row = db.get(StrategyAutoBuyPromotion, int(payload.promotion_id))
            if row is None:
                return {"accepted": False, "block_reason": "promotion_not_found"}
            return self._promotion_candidate_result(row, settings=settings, now_utc=now_utc)

        rows = (
            db.query(StrategyAutoBuyPromotion)
            .filter(StrategyAutoBuyPromotion.provider == payload.provider)
            .filter(StrategyAutoBuyPromotion.market == payload.market)
            .filter(StrategyAutoBuyPromotion.status.in_(sorted(ACTIVE_STATUSES)))
            .order_by(
                StrategyAutoBuyPromotion.final_score.desc().nullslast(),
                StrategyAutoBuyPromotion.buy_score.desc().nullslast(),
                StrategyAutoBuyPromotion.confidence.desc().nullslast(),
                StrategyAutoBuyPromotion.created_at.desc(),
                StrategyAutoBuyPromotion.id.desc(),
            )
            .limit(50)
            .all()
        )
        for row in rows:
            result = self._promotion_candidate_result(
                row,
                settings=settings,
                now_utc=now_utc,
            )
            if result.get("accepted"):
                return result
        return {"accepted": False, "block_reason": "no_eligible_promotion"}

    def _promotion_candidate_result(
        self,
        row: StrategyAutoBuyPromotion,
        *,
        settings: dict[str, Any],
        now_utc: datetime,
    ) -> dict[str, Any]:
        item = self.promotion_service.item(row)
        raw_status = str(row.status or "").strip()
        if raw_status not in SYSTEM_APPROVED_STATUSES:
            return {
                "accepted": False,
                "block_reason": _promotion_block_reason(raw_status),
                "row": row,
                "item": item,
            }
        if row.expires_at is not None and _utc(row.expires_at) <= now_utc:
            return {
                "accepted": False,
                "block_reason": "promotion_expired",
                "row": row,
                "item": item,
            }
        if item.get("expired") or item.get("stale"):
            return {
                "accepted": False,
                "block_reason": "promotion_expired",
                "row": row,
                "item": item,
            }
        if row.converted_live_attempt_id or row.converted_order_id:
            return {
                "accepted": False,
                "block_reason": "promotion_already_converted",
                "row": row,
                "item": item,
            }
        if not _phase1_system_approved(row, settings):
            return {
                "accepted": False,
                "block_reason": "score_threshold_not_met",
                "row": row,
                "item": item,
            }
        if str(row.dry_run_action or "") != "would_buy":
            return {
                "accepted": False,
                "block_reason": "promotion_not_would_buy",
                "row": row,
                "item": item,
            }
        return {"accepted": True, "row": row, "item": item}

    def _order_conflicts(self, db: Session, *, now_utc: datetime) -> dict[str, int]:
        rows = (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.market == MARKET)
            .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
            .limit(200)
            .all()
        )
        pending_sync = 0
        unknown_or_stale = 0
        for row in rows:
            status = str(row.internal_status or "").strip().upper()
            broker_text = " ".join(
                [
                    str(row.broker_status or ""),
                    str(row.broker_order_status or ""),
                    str(row.sync_error or ""),
                ]
            ).lower()
            if status in SYNC_REQUIRED_STATUSES or "sync_required" in broker_text or "pending_sync" in broker_text:
                pending_sync += 1
            if status in {"UNKNOWN", InternalOrderStatus.UNKNOWN_STALE.value}:
                unknown_or_stale += 1
                continue
            if status in OPEN_ORDER_STATUSES and row.created_at is not None:
                if now_utc - _utc(row.created_at) > timedelta(hours=24):
                    unknown_or_stale += 1
        return {
            "pending_sync_count": pending_sync,
            "unknown_or_stale_count": unknown_or_stale,
        }

    def _duplicate_open_buy_count(self, db: Session, *, symbol: str) -> int:
        normalized = str(symbol or "").strip().upper()
        if not normalized:
            return 0
        return (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.market == MARKET)
            .filter(OrderLog.symbol == normalized)
            .filter(OrderLog.side == "buy")
            .filter(OrderLog.internal_status.in_(sorted(OPEN_ORDER_STATUSES)))
            .count()
        )

    def _daily_auto_buy_count(self, db: Session, *, now_utc: datetime) -> int:
        start_utc, end_utc = _kr_day_bounds_utc(now_utc)
        rows = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == MODE)
            .filter(TradeRunLog.created_at >= start_utc)
            .filter(TradeRunLog.created_at < end_utc)
            .all()
        )
        count = 0
        for row in rows:
            if str(row.result or "") in SUBMITTED_RESULTS:
                count += 1
                continue
            payload = _parse_object(row.response_payload)
            if payload.get("real_order_submitted") is True:
                count += 1
        return count

    def _daily_total_trade_count(self, db: Session, *, now_utc: datetime) -> int:
        start_utc, end_utc = _kr_day_bounds_utc(now_utc)
        return (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.market == MARKET)
            .filter(OrderLog.created_at >= start_utc)
            .filter(OrderLog.created_at < end_utc)
            .filter(
                OrderLog.internal_status.in_(
                    [
                        InternalOrderStatus.SUBMITTED.value,
                        InternalOrderStatus.ACCEPTED.value,
                        InternalOrderStatus.PENDING.value,
                        InternalOrderStatus.PARTIALLY_FILLED.value,
                        InternalOrderStatus.FILLED.value,
                    ]
                )
            )
            .count()
        )

    def _response(
        self,
        *,
        generated_at: datetime,
        provider: str,
        market: str,
        trigger_source: str,
        auto_buy_live_enabled: bool,
        result_status: str,
        real_order_submitted: bool = False,
        broker_submit_called: bool = False,
        manual_submit_called: bool = False,
        selected_promotion_id: int | None = None,
        selected_symbol: str | None = None,
        candidate_score: float | None = None,
        production_readiness_status: str | None = None,
        preflight_status: str | None = None,
        order_id: int | None = None,
        broker_order_id: str | None = None,
        kis_odno: str | None = None,
        submitted_quantity: float | None = None,
        submitted_notional: float | None = None,
        max_allowed_notional: float | None = None,
        daily_auto_buy_count: int = 0,
        daily_auto_buy_limit: int = 1,
        risk_flags: list[str] | None = None,
        gating_notes: list[str] | None = None,
        checklist: list[dict[str, Any]] | None = None,
        primary_block_reason: str | None = None,
        next_safe_action: str = "review_result",
        latest_run: dict[str, Any] | None = None,
        safety: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return sanitize_kis_payload(
            {
                "run_id": None,
                "generated_at": generated_at.isoformat(),
                "provider": str(provider or PROVIDER).lower(),
                "market": str(market or MARKET).upper(),
                "trigger_source": trigger_source,
                "automation_phase": AUTOMATION_PHASE,
                "auto_buy_live_enabled": bool(auto_buy_live_enabled),
                "result_status": result_status,
                "real_order_submitted": bool(real_order_submitted),
                "broker_submit_called": bool(broker_submit_called),
                "manual_submit_called": bool(manual_submit_called),
                "selected_promotion_id": selected_promotion_id,
                "selected_symbol": selected_symbol,
                "candidate_score": candidate_score,
                "production_readiness_status": production_readiness_status,
                "preflight_status": preflight_status,
                "order_id": order_id,
                "broker_order_id": broker_order_id,
                "kis_odno": kis_odno,
                "submitted_quantity": submitted_quantity,
                "submitted_notional": submitted_notional,
                "max_allowed_notional": max_allowed_notional,
                "daily_auto_buy_count": daily_auto_buy_count,
                "daily_auto_buy_limit": daily_auto_buy_limit,
                "risk_flags": _dedupe(risk_flags or []),
                "gating_notes": _dedupe(gating_notes or []),
                "checklist": checklist or [],
                "primary_block_reason": primary_block_reason,
                "next_safe_action": next_safe_action,
                "latest_run": latest_run,
                "safety": safety or _safety(read_only=False),
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
        order_id: int | None = None,
    ) -> dict[str, Any]:
        row = TradeRunLog(
            run_key=f"auto_buy_live_phase1_{uuid.uuid4().hex[:12]}",
            trigger_source=str(response.get("trigger_source") or MODE)[:40],
            symbol=str(symbol or "PROMOTION")[:20],
            mode=MODE,
            stage="done",
            result=result,
            reason=reason,
            order_id=order_id,
            request_payload=_json(
                {
                    **request_payload,
                    "mode": MODE,
                    "automation_phase": AUTOMATION_PHASE,
                    "real_order_submitted": bool(response.get("real_order_submitted")),
                    "broker_submit_called": bool(response.get("broker_submit_called")),
                    "manual_submit_called": bool(response.get("manual_submit_called")),
                    "retry_attempted": False,
                    "sell_submit_called": False,
                }
            ),
            response_payload=_json(response),
            created_at=_naive_utc(_utc(response.get("generated_at"))),
        )
        db.add(row)
        db.flush()
        response["run_id"] = row.id
        row.response_payload = _json(response)
        db.commit()
        return sanitize_kis_payload(response)


def _check(key: str, ok: bool, reason: str, detail: str) -> dict[str, Any]:
    return {
        "key": key,
        "ok": bool(ok),
        "status": "pass" if ok else "fail",
        "blocking": not bool(ok),
        "reason": None if ok else reason,
        "detail": detail,
    }


def _safety(*, read_only: bool) -> dict[str, Any]:
    return {
        "read_only": read_only,
        "phase1_auto_buy": True,
        "promotion_queue_only": True,
        "max_one_candidate_per_run": True,
        "max_one_order_per_run": True,
        "retry_attempted": False,
        "sell_submit_called": False,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "setting_changed": False,
        "scheduler_changed": False,
        "dry_run_changed": False,
        "kill_switch_changed": False,
        "kis_real_order_changed": False,
        "strategy_profile_changed": False,
        "agent_chat_triggered": False,
    }


def _phase1_system_approved(
    row: StrategyAutoBuyPromotion,
    settings: dict[str, Any],
) -> bool:
    score = _candidate_score(row)
    confidence = _float(row.confidence)
    min_score = _float(settings.get("kis_limited_auto_buy_min_final_score")) or 75.0
    min_confidence = _float(settings.get("kis_limited_auto_buy_min_confidence")) or 0.70
    return (
        score is not None
        and score >= min_score
        and confidence is not None
        and confidence >= min_confidence
    )


def _candidate_score(row: StrategyAutoBuyPromotion | None) -> float | None:
    if row is None:
        return None
    return _float(row.final_score) if row.final_score is not None else _float(row.buy_score)


def _promotion_block_reason(status: str) -> str:
    if status == "dismissed":
        return "promotion_dismissed"
    if status == "expired":
        return "promotion_expired"
    if "converted" in status or status.startswith("live_order"):
        return "promotion_already_converted"
    if status == "conversion_blocked":
        return "promotion_conversion_blocked"
    return "promotion_not_eligible"


def _max_allowed_notional(
    settings: dict[str, Any],
    preflight: dict[str, Any],
) -> float | None:
    caps: list[float] = []
    for value in (
        settings.get("auto_buy_live_phase1_max_notional_krw"),
        preflight.get("max_notional_krw"),
        preflight.get("proposed_notional_krw"),
    ):
        parsed = _float(value)
        if parsed is not None and parsed > 0:
            caps.append(parsed)
    return round(min(caps), 2) if caps else None


def _checklist_failed(preflight: dict[str, Any], key: str) -> bool:
    items = preflight.get("checklist") if isinstance(preflight, dict) else []
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, dict) or item.get("key") != key:
            continue
        return item.get("status") == "fail" or item.get("blocking") is True
    return False


def _map_guarded_result_status(result: dict[str, Any]) -> str:
    status = str(result.get("status") or result.get("action") or "").lower()
    if status == "submitted":
        return "submitted"
    if status == "filled":
        return "filled"
    if status in {"sync_required", "pending_sync"}:
        return "pending_sync"
    if status in {"validation_failed", "rejected", "failed"}:
        return "rejected"
    if status == "blocked":
        return "blocked"
    return "error" if status else "error"


def _next_safe_action(result_status: str, reason: str | None) -> str:
    if result_status == "disabled":
        return "enable_phase1_explicitly"
    if result_status == "dry_run_blocked":
        return "review_dry_run_setting_without_changing_it_automatically"
    if result_status == "pending_sync":
        return "sync_order_status_before_any_new_entry"
    if result_status == "submitted":
        return "monitor_order_sync"
    if result_status == "filled":
        return "review_position_lifecycle"
    if result_status == "skipped":
        return "wait_for_fresh_promotion"
    if reason in {"critical_exit_candidate_exists", "position_management_dry_run_blocker"}:
        return "review_positions_first"
    return "review_block_reason"


def _kr_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    local = _utc(now_utc).astimezone(KST)
    start_local = datetime.combine(local.date(), time.min, tzinfo=KST)
    end_local = start_local + timedelta(days=1)
    return _naive_utc(start_local), _naive_utc(end_local)


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


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int(value: Any, fallback: int) -> int:
    parsed = _int_or_none(value)
    return parsed if parsed is not None else fallback


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _utc(value: Any = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except Exception:
            return datetime.now(UTC)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    return datetime.now(UTC)


def _naive_utc(value: datetime) -> datetime:
    return _utc(value).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else _utc(value).isoformat()
