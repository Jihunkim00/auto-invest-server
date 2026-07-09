from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, TradeRunLog
from app.schemas.position_exit_review import (
    AutoSellLivePhase1RunRequest,
    PositionSellPreflightRequest,
)
from app.schemas.strategy_live_auto_exit import (
    ProfileAwareGuardedLiveAutoExitRunRequest,
)
from app.services.auto_exit_candidate_service import AutoExitCandidateService
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.ops_production_readiness_service import (
    OpsProductionReadinessService,
)
from app.services.position_exit_review_service import PositionExitReviewService
from app.services.profile_aware_guarded_live_auto_exit_service import (
    ProfileAwareGuardedLiveAutoExitService,
)
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "auto_sell_live_phase1"
AUTOMATION_PHASE = "phase1_auto_sell"
PROVIDER = "kis"
MARKET = "KR"
KST = ZoneInfo("Asia/Seoul")
ALLOWED_TRIGGER_SOURCES = {"manual_phase1_test", "scheduler_phase1"}
BLOCKED_CANDIDATE_TYPES = {
    "duplicate_sell_conflict",
    "sync_required",
    "manual_review",
}
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
DUPLICATE_OPEN_ORDER_STATUSES = OPEN_ORDER_STATUSES - {
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
}
SYNC_REQUIRED_STATUSES = {
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
}


class AutoSellLivePhase1Service:
    """Controlled phase-one live sell wrapper for PR92 exit candidates."""

    def __init__(
        self,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        auto_exit_candidates: AutoExitCandidateService | None = None,
        exit_review_service: PositionExitReviewService | None = None,
        guarded_exit_service: ProfileAwareGuardedLiveAutoExitService | None = None,
        readiness_service: OpsProductionReadinessService | None = None,
    ) -> None:
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.auto_exit_candidates = auto_exit_candidates
        self.exit_review_service = exit_review_service
        self.guarded_exit_service = (
            guarded_exit_service or ProfileAwareGuardedLiveAutoExitService()
        )
        self.readiness_service = readiness_service or OpsProductionReadinessService(
            runtime_settings=self.runtime_settings
        )

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
        enabled = bool(settings.get("auto_sell_live_phase1_enabled"))
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
        return self._response(
            generated_at=now_utc,
            provider=provider,
            market=market,
            trigger_source="status",
            auto_sell_live_enabled=enabled,
            result_status="disabled" if not enabled else "skipped",
            production_readiness_status=readiness_status,
            daily_auto_sell_count=self._daily_auto_sell_count(db, now_utc=now_utc),
            daily_auto_sell_limit=_int(
                settings.get("auto_sell_live_phase1_max_orders_per_day"),
                1,
            ),
            primary_block_reason=None if enabled else "auto_sell_live_phase1_disabled",
            next_safe_action="enable_phase1_explicitly" if not enabled else "run_phase1_check",
            latest_run=self.latest_run(db),
            checklist=[
                _check(
                    "auto_sell_live_phase1_enabled",
                    enabled,
                    "auto_sell_live_phase1_disabled",
                    "Phase-one auto-sell live mode is explicitly enabled.",
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
            "selected_candidate_id": payload.get("selected_candidate_id"),
            "selected_symbol": payload.get("selected_symbol"),
            "candidate_type": payload.get("candidate_type"),
            "candidate_severity": payload.get("candidate_severity"),
            "primary_block_reason": payload.get("primary_block_reason") or row.reason,
            "real_order_submitted": bool(payload.get("real_order_submitted")),
            "broker_submit_called": bool(payload.get("broker_submit_called")),
            "order_id": payload.get("order_id"),
            "broker_order_id": payload.get("broker_order_id"),
        }

    def run_once(
        self,
        db: Session,
        request: AutoSellLivePhase1RunRequest | dict[str, Any] | None = None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        payload = (
            request
            if isinstance(request, AutoSellLivePhase1RunRequest)
            else AutoSellLivePhase1RunRequest.model_validate(request or {})
        )
        if payload.trigger_source not in ALLOWED_TRIGGER_SOURCES:
            payload.trigger_source = "manual_phase1_test"

        now_utc = _utc(now)
        settings = self.runtime_settings.get_settings_read_only(db)
        global_settings = getattr(self.runtime_settings, "settings", None)
        checklist: list[dict[str, Any]] = []
        risk_flags: list[str] = []
        gating_notes: list[str] = []
        selected: dict[str, Any] | None = None
        preflight: dict[str, Any] = {}
        readiness: dict[str, Any] = {}
        daily_count = self._daily_auto_sell_count(db, now_utc=now_utc)
        daily_limit = max(
            0,
            _int(settings.get("auto_sell_live_phase1_max_orders_per_day"), 1),
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
                auto_sell_live_enabled=bool(
                    settings.get("auto_sell_live_phase1_enabled")
                ),
                result_status=result_status,
                selected_candidate_id=_candidate_value(selected, "candidate_id")
                or payload.candidate_id,
                selected_symbol=_candidate_value(selected, "symbol") or payload.symbol,
                candidate_type=_candidate_value(selected, "candidate_type"),
                candidate_severity=_candidate_value(selected, "severity"),
                production_readiness_status=readiness.get("overall_status"),
                sell_preflight_status=preflight.get("preflight_status"),
                order_id=order_id,
                available_quantity=_float(
                    preflight.get("available_quantity")
                    if preflight
                    else _candidate_value(selected, "available_quantity")
                ),
                daily_auto_sell_count=daily_count,
                daily_auto_sell_limit=daily_limit,
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
                symbol=response.get("selected_symbol") or "POSITIONS",
            )

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

        enabled = bool(settings.get("auto_sell_live_phase1_enabled"))
        if not self._gate(
            checklist,
            "auto_sell_live_phase1_enabled",
            enabled,
            "auto_sell_live_phase1_disabled",
            "Phase-one auto-sell live mode must be explicitly enabled.",
        ):
            return block(
                "auto_sell_live_phase1_disabled",
                result_status="disabled",
                next_safe_action="enable_phase1_explicitly",
            )

        allow_real = bool(settings.get("auto_sell_live_phase1_allow_real_orders"))
        if not self._gate(
            checklist,
            "auto_sell_live_phase1_allow_real_orders",
            allow_real,
            "auto_sell_live_phase1_real_orders_disabled",
            "A separate Phase 1 sell hard switch must allow real orders.",
        ):
            return block("auto_sell_live_phase1_real_orders_disabled")

        if payload.trigger_source == "manual_phase1_test" and payload.confirm_phase1_run is not True:
            if not self._gate(
                checklist,
                "manual_phase1_confirmation",
                False,
                "manual_phase1_confirmation_required",
                "Manual Phase 1 sell attempt requires confirm_phase1_run=true.",
            ):
                return block("manual_phase1_confirmation_required")

        if str(settings.get("auto_sell_live_phase1_provider") or PROVIDER).lower() != payload.provider:
            if not self._gate(
                checklist,
                "provider_scope",
                False,
                "provider_scope_mismatch",
                "Phase-one auto-sell provider scope must match the request.",
            ):
                return block("provider_scope_mismatch")

        readiness = self._production_readiness(db, payload, now_utc)
        readiness_status = str(readiness.get("overall_status") or "unknown").lower()
        require_ready = bool(
            settings.get("auto_sell_live_phase1_require_production_ready", True)
        )
        readiness_ok = readiness_status == "ready" or (
            not require_ready and readiness_status in {"ready", "warning"}
        )
        if not self._gate(
            checklist,
            "production_readiness_ready",
            readiness_ok,
            "production_readiness_not_ready",
            f"Production readiness status is {readiness_status}.",
        ):
            return block("production_readiness_not_ready")

        selected = self._select_candidate(db, payload, settings)
        if selected is None:
            return block(
                "no_eligible_exit_candidate",
                result_status="skipped",
                next_safe_action="continue_position_monitoring",
            )

        candidate_type = _candidate_value(selected, "candidate_type") or ""
        severity = _candidate_value(selected, "severity") or ""
        symbol = str(_candidate_value(selected, "symbol") or payload.symbol or "").upper()
        available_quantity = _float(_candidate_value(selected, "available_quantity"))
        requested_quantity = self._requested_quantity(selected)

        self._gate(
            checklist,
            "position_exists",
            bool(symbol and _float(_candidate_value(selected, "position_quantity")) > 0),
            "position_missing",
            "Candidate must come from a held position.",
        )
        if checklist[-1]["status"] != "pass":
            return block("position_missing")

        if not self._gate(
            checklist,
            "available_quantity_positive",
            available_quantity > 0,
            "available_quantity_zero",
            f"Available quantity is {available_quantity}.",
        ):
            return block("available_quantity_zero")

        requested_valid = requested_quantity > 0 and requested_quantity <= available_quantity
        if not self._gate(
            checklist,
            "requested_quantity_valid",
            requested_valid,
            "requested_quantity_invalid",
            f"Requested quantity is {requested_quantity}; available quantity is {available_quantity}.",
        ):
            return block("requested_quantity_invalid")

        if not self._gate(
            checklist,
            "duplicate_open_sell_order",
            not bool(selected.get("open_sell_order_conflict"))
            and not self._has_open_sell_order(db, symbol),
            "duplicate_open_sell_order",
            "No duplicate open sell order may exist for the selected symbol.",
        ):
            return block("duplicate_open_sell_order")

        if not self._gate(
            checklist,
            "pending_sync_order_absent",
            not bool(selected.get("sync_required"))
            and not self._has_pending_sync_order(db, symbol),
            "pending_sync_order_exists",
            "No pending-sync or stale order conflict may exist for the selected symbol.",
        ):
            return block("pending_sync_order_exists", result_status="pending_sync")

        if not self._gate(
            checklist,
            "candidate_fresh",
            True,
            "candidate_stale",
            "Candidate was generated by PR92 detection during this Phase 1 run.",
        ):
            return block("candidate_stale")

        allowed_types = set(_strings(settings.get("auto_sell_live_phase1_allowed_candidate_types")))
        allowed_types = allowed_types or {
            "stop_loss",
            "take_profit",
            "trend_breakdown",
            "weak_momentum",
        }
        type_allowed = candidate_type in allowed_types and candidate_type not in BLOCKED_CANDIDATE_TYPES
        if not self._gate(
            checklist,
            "candidate_type_allowed",
            type_allowed,
            f"candidate_type_not_allowed:{candidate_type or 'unknown'}",
            "Candidate type must be automation eligible.",
        ):
            return block(f"candidate_type_not_allowed:{candidate_type or 'unknown'}")

        severity_ok = severity == "critical" or (
            candidate_type in {"take_profit", "trend_breakdown"} and severity == "warning"
        )
        if not self._gate(
            checklist,
            "candidate_severity_allowed",
            severity_ok,
            "candidate_severity_not_eligible",
            "Candidate must be critical or explicitly accepted as warning risk-reduction.",
        ):
            return block("candidate_severity_not_eligible")

        quantity_policy_ok = candidate_type == "stop_loss" and severity == "critical"
        if not self._gate(
            checklist,
            "quantity_policy_allowed",
            quantity_policy_ok,
            "quantity_policy_manual_review",
            "Phase 1 automatically sells full available quantity only for critical stop-loss.",
        ):
            return block("quantity_policy_manual_review")

        if self.exit_review_service is None:
            return block("sell_preflight_unavailable")
        preflight = self.exit_review_service.sell_preflight(
            db,
            symbol=symbol,
            request=PositionSellPreflightRequest(
                provider=payload.provider,
                market=payload.market,
                quantity_mode="partial",
                quantity=requested_quantity,
                language=payload.language,
                locale=payload.locale,
            ),
        )
        preflight_ok = (
            str(preflight.get("preflight_status") or "").lower() == "allowed"
            and preflight.get("can_submit_after_confirmation") is True
            and preflight.get("position_exists") is True
            and _float(preflight.get("available_quantity")) > 0
            and _float(preflight.get("requested_quantity")) > 0
            and _float(preflight.get("requested_quantity")) <= _float(preflight.get("available_quantity"))
        )
        risk_flags.extend(_strings(preflight.get("risk_flags")))
        gating_notes.extend(_strings(preflight.get("gating_notes")))
        if not self._gate(
            checklist,
            "sell_preflight_passed",
            preflight_ok,
            preflight.get("primary_block_reason") or "sell_preflight_blocked",
            "Sell preflight must allow a final guarded sell submission.",
        ):
            return block(preflight.get("primary_block_reason") or "sell_preflight_blocked")

        if not self._gate(
            checklist,
            "market_session_allowed",
            bool(preflight.get("market_session_allowed")),
            "market_session_blocked",
            "Market session must allow sell exits.",
        ):
            return block("market_session_blocked")

        if not self._gate(
            checklist,
            "daily_auto_sell_limit",
            daily_count < daily_limit,
            "daily_auto_sell_limit_reached",
            f"Phase 1 auto-sell used {daily_count}/{daily_limit} orders today.",
        ):
            return block("daily_auto_sell_limit_reached")

        global_trade_count = self._daily_total_trade_count(db, now_utc=now_utc)
        global_limit = max(0, _int(settings.get("max_trades_per_day"), 0))
        if not self._gate(
            checklist,
            "daily_total_trade_limit",
            global_limit <= 0 or global_trade_count < global_limit,
            "daily_total_trade_limit_reached",
            f"Global daily trade count is {global_trade_count}/{global_limit}.",
        ):
            return block("daily_total_trade_limit_reached")

        risk_ok = not any(
            item in {"duplicate_open_sell_order", "sync_required", "incomplete_pl_inputs"}
            for item in _strings(selected.get("risk_flags"))
        )
        if not self._gate(
            checklist,
            "risk_engine_gate",
            risk_ok,
            "risk_engine_blocked",
            "Candidate risk flags must not contain sync, duplicate, or incomplete-data blockers.",
        ):
            return block("risk_engine_blocked")

        guarded_result = self.guarded_exit_service.run_once(
            db,
            ProfileAwareGuardedLiveAutoExitRunRequest(
                provider=payload.provider,
                market=payload.market,
                symbol=symbol,
                quantity=int(requested_quantity),
                confirm_operator_ack=True,
                trigger_source=MODE,
                client_request_id=f"{MODE}:{uuid.uuid4().hex}",
            ),
            now=now_utc,
        )
        result_status = _map_guarded_status(guarded_result)
        safety = guarded_result.get("safety") if isinstance(guarded_result.get("safety"), dict) else {}
        response = self._response(
            generated_at=now_utc,
            provider=payload.provider,
            market=payload.market,
            trigger_source=payload.trigger_source,
            auto_sell_live_enabled=True,
            result_status=result_status,
            real_order_submitted=bool(safety.get("real_order_submitted") or guarded_result.get("submitted")),
            broker_submit_called=bool(safety.get("broker_submit_called")),
            manual_submit_called=bool(safety.get("manual_submit_called")),
            selected_candidate_id=_candidate_value(selected, "candidate_id"),
            selected_symbol=symbol,
            candidate_type=candidate_type,
            candidate_severity=severity,
            production_readiness_status=readiness.get("overall_status"),
            sell_preflight_status=preflight.get("preflight_status"),
            order_id=_int_or_none(guarded_result.get("related_order_id")),
            broker_order_id=_text(guarded_result.get("broker_order_id")),
            kis_odno=_text(guarded_result.get("broker_order_id")),
            submitted_quantity=_float(guarded_result.get("quantity")),
            submitted_notional=_float(guarded_result.get("submitted_notional_krw")),
            available_quantity=_float(preflight.get("available_quantity")),
            daily_auto_sell_count=daily_count,
            daily_auto_sell_limit=daily_limit,
            risk_flags=_dedupe(risk_flags + _strings(guarded_result.get("risk_flags"))),
            gating_notes=_dedupe(
                gating_notes
                + _strings(guarded_result.get("gating_notes"))
                + ["No retry is attempted by phase-one auto-sell."]
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
                "phase1_auto_sell": True,
                "manual_submit_called": bool(safety.get("manual_submit_called")),
                "scheduler_changed": False,
                "setting_changed": False,
                "retry_attempted": False,
                "buy_submit_called": False,
            },
        )
        return self._save_run(
            db,
            request_payload=payload.model_dump(mode="json"),
            response=response,
            result=result_status,
            reason=response.get("primary_block_reason") or result_status,
            symbol=symbol,
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
        payload: AutoSellLivePhase1RunRequest,
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

    def _select_candidate(
        self,
        db: Session,
        payload: AutoSellLivePhase1RunRequest,
        settings: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self.auto_exit_candidates is None:
            return None
        candidates_payload = self.auto_exit_candidates.candidates(
            db,
            provider=payload.provider,
            market=payload.market,
            symbol=payload.symbol,
            include_details=True,
            min_severity="info",
        )
        candidates = _candidate_list(candidates_payload)
        if payload.candidate_id:
            candidates = [
                item
                for item in candidates
                if str(item.get("candidate_id") or "") == payload.candidate_id
            ]
        allowed_types = set(_strings(settings.get("auto_sell_live_phase1_allowed_candidate_types")))
        if allowed_types:
            candidates = [
                item
                for item in candidates
                if str(item.get("candidate_type") or "") in allowed_types
                or str(item.get("candidate_type") or "") in BLOCKED_CANDIDATE_TYPES
            ]
        candidates = [item for item in candidates if str(item.get("status") or "active") == "active"]
        candidates.sort(key=_candidate_priority)
        return candidates[0] if candidates else None

    def _requested_quantity(self, candidate: dict[str, Any]) -> float:
        return _float(candidate.get("available_quantity"))

    def _has_open_sell_order(self, db: Session, symbol: str) -> bool:
        normalized = str(symbol or "").strip().upper()
        if not normalized:
            return False
        return (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.market == MARKET)
            .filter(OrderLog.symbol == normalized)
            .filter(OrderLog.side == "sell")
            .filter(OrderLog.internal_status.in_(sorted(DUPLICATE_OPEN_ORDER_STATUSES)))
            .first()
            is not None
        )

    def _has_pending_sync_order(self, db: Session, symbol: str) -> bool:
        normalized = str(symbol or "").strip().upper()
        if not normalized:
            return False
        return (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.market == MARKET)
            .filter(OrderLog.symbol == normalized)
            .filter(OrderLog.internal_status.in_(sorted(SYNC_REQUIRED_STATUSES)))
            .first()
            is not None
        )

    def _daily_auto_sell_count(self, db: Session, *, now_utc: datetime) -> int:
        start, end = _day_bounds(now_utc)
        rows = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == MODE)
            .filter(TradeRunLog.created_at >= start)
            .filter(TradeRunLog.created_at < end)
            .all()
        )
        count = 0
        for row in rows:
            payload = _parse_object(row.response_payload)
            if payload.get("real_order_submitted") is True:
                count += 1
        return count

    def _daily_total_trade_count(self, db: Session, *, now_utc: datetime) -> int:
        start, end = _day_bounds(now_utc)
        return (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.market == MARKET)
            .filter(OrderLog.created_at >= start)
            .filter(OrderLog.created_at < end)
            .filter(
                OrderLog.internal_status.in_(
                    [
                        InternalOrderStatus.REQUESTED.value,
                        InternalOrderStatus.SUBMITTED.value,
                        InternalOrderStatus.ACCEPTED.value,
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
        auto_sell_live_enabled: bool,
        result_status: str,
        real_order_submitted: bool = False,
        broker_submit_called: bool = False,
        manual_submit_called: bool = False,
        selected_candidate_id: str | None = None,
        selected_symbol: str | None = None,
        candidate_type: str | None = None,
        candidate_severity: str | None = None,
        production_readiness_status: str | None = None,
        sell_preflight_status: str | None = None,
        order_id: int | None = None,
        broker_order_id: str | None = None,
        kis_odno: str | None = None,
        submitted_quantity: float | None = None,
        submitted_notional: float | None = None,
        available_quantity: float | None = None,
        daily_auto_sell_count: int = 0,
        daily_auto_sell_limit: int = 1,
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
                "auto_sell_live_enabled": bool(auto_sell_live_enabled),
                "result_status": result_status,
                "real_order_submitted": bool(real_order_submitted),
                "broker_submit_called": bool(broker_submit_called),
                "manual_submit_called": bool(manual_submit_called),
                "selected_candidate_id": selected_candidate_id,
                "selected_symbol": selected_symbol,
                "candidate_type": candidate_type,
                "candidate_severity": candidate_severity,
                "production_readiness_status": production_readiness_status,
                "sell_preflight_status": sell_preflight_status,
                "order_id": order_id,
                "broker_order_id": broker_order_id,
                "kis_odno": kis_odno,
                "submitted_quantity": submitted_quantity,
                "submitted_notional": submitted_notional,
                "available_quantity": available_quantity,
                "daily_auto_sell_count": daily_auto_sell_count,
                "daily_auto_sell_limit": daily_auto_sell_limit,
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
            run_key=f"auto_sell_live_phase1_{uuid.uuid4().hex[:12]}",
            trigger_source=str(response.get("trigger_source") or MODE)[:40],
            symbol=str(symbol or "POSITIONS")[:20],
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
                    "buy_submit_called": False,
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
        "phase1_auto_sell": True,
        "held_positions_only": True,
        "risk_reduction_only": True,
        "max_one_candidate_per_run": True,
        "max_one_order_per_run": True,
        "retry_attempted": False,
        "buy_submit_called": False,
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
        "short_sell_allowed": False,
        "liquidate_all_allowed": False,
    }


def _candidate_list(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    items = payload.get("candidates")
    if not isinstance(items, list):
        return []
    return [dict(item) for item in items if isinstance(item, dict)]


def _candidate_priority(item: dict[str, Any]) -> tuple[int, int, str]:
    ctype = str(item.get("candidate_type") or "")
    severity = str(item.get("severity") or "")
    priority = {
        "stop_loss": 0,
        "take_profit": 1,
        "trend_breakdown": 2,
        "weak_momentum": 3,
        "near_close_risk": 4,
        "duplicate_sell_conflict": 90,
        "sync_required": 91,
        "manual_review": 92,
    }.get(ctype, 99)
    severity_rank = {"critical": 0, "warning": 1, "info": 2}.get(severity, 9)
    return (priority, severity_rank, str(item.get("symbol") or ""))


def _candidate_value(candidate: dict[str, Any] | None, key: str) -> Any:
    if not isinstance(candidate, dict):
        return None
    return candidate.get(key)


def _map_guarded_status(value: dict[str, Any]) -> str:
    status = str(value.get("status") or "").lower()
    if status in {"submitted", "filled"}:
        return status
    if status in {"sync_required", "pending_sync"}:
        return "pending_sync"
    if status in {"validation_failed", "rejected"}:
        return "rejected"
    if status in {"failed", "error"}:
        return "error"
    if bool(value.get("submitted")):
        return "submitted"
    return "blocked"


def _next_safe_action(status: str, reason: str | None = None) -> str:
    if status in {"submitted", "filled", "pending_sync"}:
        return "review_order_status"
    if status == "dry_run_blocked":
        return "review_runtime_dry_run"
    if status == "disabled":
        return "enable_phase1_explicitly"
    if status == "skipped":
        return "continue_position_monitoring"
    if reason in {"pending_sync_order_exists", "broker_submit_sync_required"}:
        return "sync_order_state"
    if reason == "quantity_policy_manual_review":
        return "manual_review_required"
    return "review_blocker"


def _day_bounds(now_utc: datetime) -> tuple[datetime, datetime]:
    local = now_utc.astimezone(KST)
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(UTC).replace(tzinfo=None),
        end_local.astimezone(UTC).replace(tzinfo=None),
    )


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


def _naive_utc(value: datetime) -> datetime:
    return _utc(value).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _utc(value).isoformat()


def _parse_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None:
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
