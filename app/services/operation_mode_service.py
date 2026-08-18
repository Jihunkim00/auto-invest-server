from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import OperationModeAudit, RuntimeSetting
from app.services.automation_release_service import AutomationReleaseService
from app.services.kis_payload_sanitizer import sanitize_kis_payload, sanitize_kis_text
from app.services.runtime_setting_service import (
    CONSERVATIVE_LIVE_ORDER_LIMIT,
    CONSERVATIVE_MAX_NOTIONAL_PCT,
    RuntimeSettingService,
)


OPERATION_MODES = {"paper", "live", "paused"}
DEFAULT_PROVIDER = "kis"
DEFAULT_MARKET = "KR"
LIVE_PROVIDER = "kis"
LIVE_MARKET = "KR"

DISPLAY_LABELS = {
    "paper": "Paper operation",
    "live": "Live operation",
    "paused": "Paused operation",
}

REASON_MESSAGES = {
    "unsupported_provider": "Live operation currently supports provider=kis only.",
    "unsupported_market": "Live operation currently supports market=KR only.",
    "dry_run_enabled": "Dry-run is still enabled.",
    "kill_switch_enabled": "Kill switch is enabled.",
    "kis_disabled": "KIS integration is disabled.",
    "kis_real_order_disabled": "KIS real-order capability is disabled.",
    "production_readiness_not_ready": "Production readiness is not ready.",
    "production_readiness_blocked": "Production readiness is blocked.",
    "broker_sync_watchdog_blocked": "Broker sync watchdog is blocking live operation.",
    "broker_sync_unsafe": "Broker sync watchdog reports an unsafe state.",
    "broker_sync_unknown": "Broker sync watchdog state is unknown.",
    "automation_soak_kill_latch_active": "Automation soak kill latch is active.",
    "soak_recent_pass_missing": "A recent passing soak result is required.",
    "automation_release_disabled": "Automation release is not armed.",
    "automation_mode_not_phase1_live_ready": "Automation mode is not live-ready.",
    "portfolio_orchestrator_disabled": "Portfolio orchestrator is disabled.",
    "portfolio_orchestrator_live_orders_disabled": "Portfolio orchestrator live orders are disabled.",
    "auto_buy_live_phase1_disabled": "Live auto-buy phase 1 is disabled.",
    "auto_buy_live_phase1_real_orders_disabled": "Live auto-buy real orders are disabled.",
    "auto_sell_live_phase1_disabled": "Live auto-sell phase 1 is disabled.",
    "auto_sell_live_phase1_real_orders_disabled": "Live auto-sell real orders are disabled.",
    "pending_order_blocker_exists": "A pending order blocker exists.",
    "sync_required_order_exists": "An order requires broker synchronization.",
    "pending_sync_order_exists": "An order requires broker synchronization.",
    "stale_order_exists": "A stale order must be reviewed.",
    "duplicate_or_pending_order_conflict": "A duplicate or pending order conflict exists.",
    "position_mismatch_exists": "Local and broker positions need reconciliation.",
    "critical_exit_candidate_blocks_buy": "A critical exit candidate blocks new buy operation.",
    "daily_trade_limit_reached": "Daily trade limit is reached.",
    "daily_trade_limit_exhausted": "Daily trade limit is exhausted.",
    "release_live_phase1_gates_blocked": "Automation release live gates are blocked.",
    "live_preflight_failed": "Live preflight did not pass.",
    "release_status_unavailable": "Automation release status is unavailable.",
}

LIVE_RUNTIME_KEYS = (
    "kis_scheduler_live_enabled",
    "kis_scheduler_allow_real_orders",
    "kis_scheduler_configured_allow_real_orders",
    "kis_scheduler_buy_enabled",
    "kis_scheduler_sell_enabled",
    "kis_scheduler_allow_limited_auto_buy",
    "kis_scheduler_allow_limited_auto_sell",
    "kis_live_auto_buy_enabled",
    "kis_live_auto_sell_enabled",
    "kis_limited_auto_buy_enabled",
    "kis_limited_auto_sell_enabled",
    "agent_chat_live_order_enabled",
    "agent_chat_live_order_kis_enabled",
    "agent_chat_live_order_buy_enabled",
    "agent_chat_live_order_sell_enabled",
    "auto_buy_live_phase1_enabled",
    "auto_buy_live_phase1_allow_real_orders",
    "auto_sell_live_phase1_enabled",
    "auto_sell_live_phase1_allow_real_orders",
    "portfolio_orchestrator_allow_live_orders",
    "automation_release_enabled",
    "automation_release_allow_live_phase1",
)

SNAPSHOT_KEYS = (
    "operation_mode_requested",
    "dry_run",
    "kill_switch",
    "scheduler_enabled",
    "automation_mode",
    "automation_release_enabled",
    "automation_release_allow_live_phase1",
    "automation_release_scheduler_enabled",
    "kis_scheduler_enabled",
    "kis_scheduler_dry_run",
    "kis_scheduler_live_enabled",
    "kis_scheduler_allow_real_orders",
    "kis_scheduler_configured_allow_real_orders",
    "kis_scheduler_buy_enabled",
    "kis_scheduler_sell_enabled",
    "kis_scheduler_allow_limited_auto_buy",
    "kis_scheduler_allow_limited_auto_sell",
    "agent_chat_live_order_enabled",
    "agent_chat_live_order_kis_enabled",
    "agent_chat_live_order_buy_enabled",
    "agent_chat_live_order_sell_enabled",
    "portfolio_orchestrator_enabled",
    "portfolio_orchestrator_allow_live_orders",
    "auto_buy_live_phase1_enabled",
    "auto_buy_live_phase1_allow_real_orders",
    "auto_sell_live_phase1_enabled",
    "auto_sell_live_phase1_allow_real_orders",
    "automation_soak_kill_latch_active",
    "automation_soak_last_successful_cycle_at",
    "broker_sync_watchdog_enabled",
    "broker_sync_watchdog_block_automation_on_unsafe",
)


class OperationModeTransitionBlocked(ValueError):
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__(str(payload.get("message") or "operation mode blocked"))


class OperationModeService:
    def __init__(
        self,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        automation_release_service: AutomationReleaseService | None = None,
    ) -> None:
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.automation_release_service = (
            automation_release_service
            or AutomationReleaseService(runtime_settings=self.runtime_settings)
        )

    def get_status(
        self,
        db: Session,
        *,
        provider: str | None = None,
        market: str | None = None,
        requested_mode_override: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        safe_provider, safe_market = self._scope(provider=provider, market=market)
        now_utc = _utc(now)
        settings = self.runtime_settings.get_settings_read_only(db)
        related = self._related_statuses(
            db,
            provider=safe_provider,
            market=safe_market,
            now_utc=now_utc,
        )
        requested_mode = self._requested_mode(
            settings,
            override=requested_mode_override,
        )
        blocking = self._live_blocking_reasons(
            settings,
            related,
            provider=safe_provider,
            market=safe_market,
        )
        warnings = self._warnings(settings, related)
        effective_mode = self.derive_effective_mode(
            settings=settings,
            related_statuses=related,
            requested_mode=requested_mode,
            blocking_reasons=blocking,
        )
        drift = requested_mode != effective_mode
        response = {
            "requested_mode": requested_mode,
            "effective_mode": effective_mode,
            "display_label": DISPLAY_LABELS[effective_mode],
            "status": "blocked" if drift else "active",
            "safety_status": self._safety_status(
                requested_mode=requested_mode,
                effective_mode=effective_mode,
                blocking_reasons=blocking,
            ),
            "can_change_mode": True,
            "can_enter_paper": True,
            "can_enter_live": len(blocking) == 0,
            "can_enter_paused": True,
            "requires_acknowledgement": {
                "paper": False,
                "live": True,
                "paused": False,
            },
            "mode_drift_detected": drift,
            "blocking_reasons": [_reason_item(code) for code in blocking],
            "warnings": [_reason_item(code) for code in warnings],
            "underlying_state": self._underlying_state(
                settings,
                related,
                provider=safe_provider,
                market=safe_market,
            ),
            "last_changed_at": _iso(settings.get("operation_mode_changed_at")),
            "last_changed_by": _text(settings.get("operation_mode_changed_by")),
        }
        return sanitize_kis_payload(response)

    def preflight(
        self,
        db: Session,
        target_mode: str,
        *,
        provider: str | None = None,
        market: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        target = _mode(target_mode)
        return self.get_status(
            db,
            provider=provider,
            market=market,
            requested_mode_override=target,
            now=now,
        )

    def change_mode(
        self,
        db: Session,
        *,
        target_mode: str,
        acknowledged: bool,
        reason: str | None,
        changed_by: str = "api",
        provider: str | None = None,
        market: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        target = _mode(target_mode)
        if target == "live" and not acknowledged:
            raise ValueError("live mode requires acknowledged=true")

        safe_provider, safe_market = self._scope(provider=provider, market=market)
        now_utc = _utc(now)
        safe_reason = _safe_reason(reason)
        before_settings = self.runtime_settings.get_settings_read_only(db)
        previous_mode = self._requested_mode(before_settings)
        before_related = self._related_statuses(
            db,
            provider=safe_provider,
            market=safe_market,
            now_utc=now_utc,
        )
        before_state = self._underlying_state(
            before_settings,
            before_related,
            provider=safe_provider,
            market=safe_market,
        )
        current = self.get_status(
            db,
            provider=safe_provider,
            market=safe_market,
            now=now_utc,
        )
        if previous_mode == target and not current["mode_drift_detected"]:
            if not self._target_payload_needed(before_settings, target):
                audit = self._record_audit(
                    db,
                    previous_mode=previous_mode,
                    requested_mode=target,
                    effective_mode=current["effective_mode"],
                    status="unchanged",
                    changed_by=changed_by,
                    reason=safe_reason,
                    acknowledged=acknowledged,
                    provider=safe_provider,
                    market=safe_market,
                    blocking_reasons=current["blocking_reasons"],
                    warnings=current["warnings"],
                    before_state=before_state,
                    after_state=before_state,
                )
                db.commit()
                db.refresh(audit)
                return self._change_response(
                    changed=False,
                    previous_mode=previous_mode,
                    requested_mode=target,
                    effective_mode=current["effective_mode"],
                    status="unchanged",
                    safety_status=current["safety_status"],
                    message=f"Already in {DISPLAY_LABELS[target]} mode.",
                    blocking_reasons=current["blocking_reasons"],
                    warnings=current["warnings"],
                    audit_id=audit.id,
                    changed_at=_iso(audit.created_at),
                    underlying_state=before_state,
                )

        if target == "live":
            return self._change_to_live(
                db,
                previous_mode=previous_mode,
                acknowledged=acknowledged,
                reason=safe_reason,
                changed_by=changed_by,
                provider=safe_provider,
                market=safe_market,
                now_utc=now_utc,
                before_settings=before_settings,
                before_state=before_state,
            )

        return self._change_to_safe_mode(
            db,
            target_mode=target,
            previous_mode=previous_mode,
            acknowledged=acknowledged,
            reason=safe_reason,
            changed_by=changed_by,
            provider=safe_provider,
            market=safe_market,
            now_utc=now_utc,
            before_state=before_state,
        )

    def derive_effective_mode(
        self,
        *,
        settings: dict[str, Any],
        related_statuses: dict[str, Any],
        requested_mode: str,
        blocking_reasons: list[str] | None = None,
    ) -> str:
        requested = _mode(requested_mode)
        blocking = blocking_reasons or []
        release = related_statuses.get("release_status") or {}
        live_ready = bool(release.get("can_submit_live_order")) and not blocking
        kill_latch_active = bool(
            settings.get("automation_soak_kill_latch_active")
            or release.get("kill_latch_active")
            or (release.get("soak_status") or {}).get("kill_latch_active")
        )

        if requested == "paused":
            return "paused"
        if requested == "paper":
            if live_ready and self._has_live_runtime(settings):
                return "live"
            return "paper"
        if live_ready:
            return "live"
        if bool(settings.get("kill_switch")) or kill_latch_active:
            return "paused"
        if bool(settings.get("dry_run", True)):
            return "paper"
        return "paused"

    def _change_to_safe_mode(
        self,
        db: Session,
        *,
        target_mode: str,
        previous_mode: str,
        acknowledged: bool,
        reason: str | None,
        changed_by: str,
        provider: str,
        market: str,
        now_utc: datetime,
        before_state: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            row = self._get_or_create_row(db)
            payload = (
                self._paper_payload(row=row, now_utc=now_utc, reason=reason, changed_by=changed_by)
                if target_mode == "paper"
                else self._paused_payload(now_utc=now_utc, reason=reason, changed_by=changed_by)
            )
            self._apply_payload(row, payload)
            self._after_apply_transition(target_mode=target_mode, row=row)
            db.flush()
            after_settings = self.runtime_settings._settings_from_row(row)
            after_related = self._related_statuses(
                db,
                provider=provider,
                market=market,
                now_utc=now_utc,
            )
            status = self.get_status(
                db,
                provider=provider,
                market=market,
                requested_mode_override=target_mode,
                now=now_utc,
            )
            after_state = self._underlying_state(
                after_settings,
                after_related,
                provider=provider,
                market=market,
            )
            audit = self._record_audit(
                db,
                previous_mode=previous_mode,
                requested_mode=target_mode,
                effective_mode=status["effective_mode"],
                status=status["status"],
                changed_by=changed_by,
                reason=reason,
                acknowledged=acknowledged,
                provider=provider,
                market=market,
                blocking_reasons=status["blocking_reasons"],
                warnings=status["warnings"],
                before_state=before_state,
                after_state=after_state,
            )
            db.commit()
            db.refresh(audit)
            return self._change_response(
                changed=True,
                previous_mode=previous_mode,
                requested_mode=target_mode,
                effective_mode=status["effective_mode"],
                status=status["status"],
                safety_status=status["safety_status"],
                message=f"Changed to {DISPLAY_LABELS[target_mode]} mode.",
                blocking_reasons=status["blocking_reasons"],
                warnings=status["warnings"],
                audit_id=audit.id,
                changed_at=_iso(audit.created_at),
                underlying_state=after_state,
            )
        except Exception:
            db.rollback()
            raise

    def _change_to_live(
        self,
        db: Session,
        *,
        previous_mode: str,
        acknowledged: bool,
        reason: str | None,
        changed_by: str,
        provider: str,
        market: str,
        now_utc: datetime,
        before_settings: dict[str, Any],
        before_state: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            row = self._get_or_create_row(db)
            self._apply_payload(
                row,
                self._live_payload(now_utc=now_utc, reason=reason, changed_by=changed_by),
            )
            self._after_apply_transition(target_mode="live", row=row)
            db.flush()
            candidate_settings = self.runtime_settings._settings_from_row(row)
            candidate_related = self._related_statuses(
                db,
                provider=provider,
                market=market,
                now_utc=now_utc,
            )
            blocking = self._live_blocking_reasons(
                candidate_settings,
                candidate_related,
                provider=provider,
                market=market,
            )
            warnings = self._warnings(candidate_settings, candidate_related)
            if blocking:
                effective_mode = self.derive_effective_mode(
                    settings=before_settings,
                    related_statuses=candidate_related,
                    requested_mode="live",
                    blocking_reasons=blocking,
                )
                db.rollback()
                audit = self._record_audit(
                    db,
                    previous_mode=previous_mode,
                    requested_mode="live",
                    effective_mode=effective_mode,
                    status="blocked",
                    changed_by=changed_by,
                    reason=reason,
                    acknowledged=acknowledged,
                    provider=provider,
                    market=market,
                    blocking_reasons=[_reason_item(code) for code in blocking],
                    warnings=[_reason_item(code) for code in warnings],
                    before_state=before_state,
                    after_state=before_state,
                )
                db.commit()
                db.refresh(audit)
                payload = self._change_response(
                    changed=False,
                    previous_mode=previous_mode,
                    requested_mode="live",
                    effective_mode=effective_mode,
                    status="blocked",
                    safety_status="blocked",
                    message="Cannot enter live operation mode.",
                    blocking_reasons=[_reason_item(code) for code in blocking],
                    warnings=[_reason_item(code) for code in warnings],
                    audit_id=audit.id,
                    changed_at=_iso(audit.created_at),
                    underlying_state=before_state,
                )
                raise OperationModeTransitionBlocked(payload)

            after_state = self._underlying_state(
                candidate_settings,
                candidate_related,
                provider=provider,
                market=market,
            )
            audit = self._record_audit(
                db,
                previous_mode=previous_mode,
                requested_mode="live",
                effective_mode="live",
                status="active",
                changed_by=changed_by,
                reason=reason,
                acknowledged=acknowledged,
                provider=provider,
                market=market,
                blocking_reasons=[],
                warnings=[_reason_item(code) for code in warnings],
                before_state=before_state,
                after_state=after_state,
            )
            db.commit()
            db.refresh(audit)
            return self._change_response(
                changed=True,
                previous_mode=previous_mode,
                requested_mode="live",
                effective_mode="live",
                status="active",
                safety_status="ready",
                message="Changed to Live operation mode.",
                blocking_reasons=[],
                warnings=[_reason_item(code) for code in warnings],
                audit_id=audit.id,
                changed_at=_iso(audit.created_at),
                underlying_state=after_state,
            )
        except OperationModeTransitionBlocked:
            raise
        except Exception:
            db.rollback()
            raise

    def _related_statuses(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
        now_utc: datetime,
    ) -> dict[str, Any]:
        try:
            release_status = self.automation_release_service.preflight(
                db,
                provider=provider,
                market=market,
                now=now_utc,
            )
        except Exception as exc:
            release_status = {
                "effective_status": "unsafe",
                "can_submit_live_order": False,
                "blocking_reasons": ["release_status_unavailable"],
                "warning_reasons": [f"release_status:{exc.__class__.__name__}"],
                "broker_sync_status": {"sync_health": "unknown"},
                "soak_status": {"kill_latch_active": False},
                "production_readiness_status": "unknown",
            }
        return {"release_status": sanitize_kis_payload(release_status)}

    def _live_blocking_reasons(
        self,
        settings: dict[str, Any],
        related: dict[str, Any],
        *,
        provider: str,
        market: str,
    ) -> list[str]:
        reasons: list[str] = []
        if provider != LIVE_PROVIDER:
            reasons.append("unsupported_provider")
        if market != LIVE_MARKET:
            reasons.append("unsupported_market")

        release = related.get("release_status") or {}
        reasons.extend(_strings(release.get("blocking_reasons")))
        if bool(settings.get("kill_switch")) and "kill_switch_enabled" not in reasons:
            reasons.append("kill_switch_enabled")
        if bool(settings.get("automation_soak_kill_latch_active")):
            reasons.append("automation_soak_kill_latch_active")
        if not bool(release.get("can_submit_live_order")):
            if not reasons:
                reasons.append("live_preflight_failed")
        return _dedupe(reasons)

    def _warnings(
        self,
        settings: dict[str, Any],
        related: dict[str, Any],
    ) -> list[str]:
        release = related.get("release_status") or {}
        warnings = _strings(release.get("warning_reasons"))
        if self._has_live_runtime(settings) and str(settings.get("operation_mode_requested")) == "paper":
            warnings.append("mode_drift_live_flags_active")
        return _dedupe(warnings)

    def _underlying_state(
        self,
        settings: dict[str, Any],
        related: dict[str, Any],
        *,
        provider: str,
        market: str,
    ) -> dict[str, Any]:
        release = related.get("release_status") or {}
        watchdog = release.get("broker_sync_status") or {}
        soak = release.get("soak_status") or {}
        production_status = str(
            release.get("production_readiness_status")
            or (release.get("production_readiness") or {}).get("overall_status")
            or "unknown"
        ).lower()
        return {
            **self._snapshot(settings),
            "provider": provider,
            "market": market,
            "release_armed": bool(release.get("release_armed")),
            "release_effective_status": str(release.get("effective_status") or "unknown"),
            "release_can_submit_live_order": bool(release.get("can_submit_live_order")),
            "watchdog_healthy": str(watchdog.get("sync_health") or "unknown").lower()
            == "healthy",
            "watchdog_sync_health": str(watchdog.get("sync_health") or "unknown").lower(),
            "kill_latch_active": bool(
                settings.get("automation_soak_kill_latch_active")
                or release.get("kill_latch_active")
                or soak.get("kill_latch_active")
            ),
            "production_readiness_status": production_status,
            "production_ready": production_status == "ready",
            "broker_submit_called": False,
            "manual_submit_called": False,
            "real_order_submitted": False,
            "order_cancel_called": False,
        }

    def _snapshot(self, settings: dict[str, Any]) -> dict[str, Any]:
        return {
            key: _json_safe(settings.get(key))
            for key in SNAPSHOT_KEYS
            if key in settings
        }

    def _requested_mode(
        self,
        settings: dict[str, Any],
        *,
        override: str | None = None,
    ) -> str:
        if override is not None:
            return _mode(override)
        value = str(settings.get("operation_mode_requested") or "").strip().lower()
        if value in OPERATION_MODES:
            return value
        legacy = str(settings.get("current_operation_mode") or "").strip().lower()
        if legacy in {"manual_live_trading", "kis_sell_only_automation", "full_live_test_mode"}:
            return "live"
        if legacy in {"safe_mode", "dry_run_simulation"}:
            return "paper"
        return "paper"

    def _safety_status(
        self,
        *,
        requested_mode: str,
        effective_mode: str,
        blocking_reasons: list[str],
    ) -> str:
        if requested_mode == "live":
            return "ready" if effective_mode == "live" and not blocking_reasons else "blocked"
        if effective_mode == "paused":
            return "paused"
        return "paper"

    def _get_or_create_row(self, db: Session) -> RuntimeSetting:
        return self.runtime_settings.get_or_create(db, commit=False)

    def _apply_payload(self, row: RuntimeSetting, payload: dict[str, Any]) -> None:
        for key, value in payload.items():
            setattr(row, key, value)

    def _paper_payload(
        self,
        *,
        row: RuntimeSetting,
        now_utc: datetime,
        reason: str | None,
        changed_by: str,
    ) -> dict[str, Any]:
        automation_mode = str(getattr(row, "automation_mode", None) or "off")
        next_automation_mode = "dry_run_auto" if automation_mode == "phase1_live_ready" else automation_mode
        return {
            **self._mode_metadata("paper", now_utc=now_utc, reason=reason, changed_by=changed_by),
            "dry_run": True,
            "automation_mode": next_automation_mode,
            "automation_mode_updated_at": now_utc
            if next_automation_mode != automation_mode
            else getattr(row, "automation_mode_updated_at", None),
            "automation_mode_updated_by": changed_by[:80]
            if next_automation_mode != automation_mode
            else getattr(row, "automation_mode_updated_by", None),
            "automation_mode_reason": reason
            if next_automation_mode != automation_mode
            else getattr(row, "automation_mode_reason", None),
            "automation_release_enabled": False,
            "automation_release_disarmed_at": now_utc,
            "automation_release_reason": reason,
            "automation_release_allow_live_phase1": False,
            "automation_release_scheduler_enabled": False,
            "portfolio_orchestrator_allow_live_orders": False,
            "auto_buy_live_phase1_enabled": False,
            "auto_buy_live_phase1_allow_real_orders": False,
            "auto_sell_live_phase1_enabled": False,
            "auto_sell_live_phase1_allow_real_orders": False,
            "kis_scheduler_dry_run": True,
            "kis_scheduler_live_enabled": False,
            "kis_scheduler_allow_real_orders": False,
            "kis_scheduler_configured_allow_real_orders": False,
            "kis_scheduler_buy_enabled": False,
            "kis_scheduler_sell_enabled": False,
            "kis_scheduler_allow_limited_auto_buy": False,
            "kis_scheduler_allow_limited_auto_sell": False,
            "kis_live_auto_buy_enabled": False,
            "kis_live_auto_sell_enabled": False,
            "kis_limited_auto_buy_enabled": False,
            "kis_limited_auto_sell_enabled": False,
            "agent_chat_live_order_enabled": False,
            "agent_chat_live_order_kis_enabled": False,
            "agent_chat_live_order_buy_enabled": False,
            "agent_chat_live_order_sell_enabled": False,
            "strategy_live_auto_buy_enabled": False,
            "strategy_live_auto_buy_scheduler_enabled": False,
            "strategy_live_auto_exit_enabled": False,
            "strategy_live_auto_exit_scheduler_enabled": False,
            "position_management_scheduler_dry_run_only": True,
            "position_management_scheduler_allow_live_orders": False,
            "portfolio_orchestrator_positions_first": True,
            "portfolio_orchestrator_max_actions_per_run": 1,
            "portfolio_orchestrator_require_production_ready": True,
        }

    def _paused_payload(
        self,
        *,
        now_utc: datetime,
        reason: str | None,
        changed_by: str,
    ) -> dict[str, Any]:
        return {
            **self._mode_metadata("paused", now_utc=now_utc, reason=reason, changed_by=changed_by),
            "scheduler_enabled": False,
            "automation_mode": "off",
            "automation_mode_updated_at": now_utc,
            "automation_mode_updated_by": changed_by[:80],
            "automation_mode_reason": reason,
            "automation_release_enabled": False,
            "automation_release_disarmed_at": now_utc,
            "automation_release_reason": reason,
            "automation_release_allow_live_phase1": False,
            "automation_release_scheduler_enabled": False,
            "portfolio_orchestrator_enabled": False,
            "portfolio_orchestrator_allow_live_orders": False,
            "auto_buy_live_phase1_enabled": False,
            "auto_buy_live_phase1_allow_real_orders": False,
            "auto_sell_live_phase1_enabled": False,
            "auto_sell_live_phase1_allow_real_orders": False,
            "kis_scheduler_enabled": False,
            "kis_scheduler_dry_run": True,
            "kis_scheduler_live_enabled": False,
            "kis_scheduler_allow_real_orders": False,
            "kis_scheduler_configured_allow_real_orders": False,
            "kis_scheduler_buy_enabled": False,
            "kis_scheduler_sell_enabled": False,
            "kis_scheduler_allow_limited_auto_buy": False,
            "kis_scheduler_allow_limited_auto_sell": False,
            "kis_live_auto_buy_enabled": False,
            "kis_live_auto_sell_enabled": False,
            "kis_limited_auto_buy_enabled": False,
            "kis_limited_auto_sell_enabled": False,
            "agent_chat_live_order_enabled": False,
            "agent_chat_live_order_kis_enabled": False,
            "agent_chat_live_order_buy_enabled": False,
            "agent_chat_live_order_sell_enabled": False,
            "strategy_live_auto_buy_enabled": False,
            "strategy_live_auto_buy_scheduler_enabled": False,
            "strategy_live_auto_exit_enabled": False,
            "strategy_live_auto_exit_scheduler_enabled": False,
            "strategy_auto_buy_scheduler_enabled": False,
            "strategy_auto_buy_scheduler_dry_run_only": True,
            "strategy_auto_buy_scheduler_allow_live_orders": False,
            "position_management_scheduler_enabled": False,
            "position_management_scheduler_dry_run_only": True,
            "position_management_scheduler_allow_live_orders": False,
        }

    def _live_payload(
        self,
        *,
        now_utc: datetime,
        reason: str | None,
        changed_by: str,
    ) -> dict[str, Any]:
        return {
            **self._mode_metadata("live", now_utc=now_utc, reason=reason, changed_by=changed_by),
            "dry_run": False,
            "automation_mode": "phase1_live_ready",
            "automation_mode_updated_at": now_utc,
            "automation_mode_updated_by": changed_by[:80],
            "automation_mode_reason": reason,
            "automation_mode_requires_manual_review": True,
            "automation_release_enabled": True,
            "automation_release_mode": "controlled_phase1",
            "automation_release_armed_at": now_utc,
            "automation_release_armed_by": changed_by[:80],
            "automation_release_disarmed_at": None,
            "automation_release_reason": reason,
            "automation_release_require_soak_pass": True,
            "automation_release_require_watchdog_healthy": True,
            "automation_release_require_production_ready": True,
            "automation_release_require_kill_latch_clear": True,
            "automation_release_max_actions_per_cycle": 1,
            "automation_release_max_daily_auto_actions": 2,
            "automation_release_max_daily_auto_buys": 1,
            "automation_release_max_daily_auto_sells": 1,
            "automation_release_allow_live_phase1": True,
            "automation_release_scheduler_enabled": False,
            "portfolio_orchestrator_enabled": True,
            "portfolio_orchestrator_allow_live_orders": True,
            "portfolio_orchestrator_positions_first": True,
            "portfolio_orchestrator_max_actions_per_run": 1,
            "portfolio_orchestrator_require_production_ready": True,
            "portfolio_orchestrator_skip_buy_if_sync_required": True,
            "portfolio_orchestrator_skip_buy_if_exit_critical": True,
            "auto_buy_live_phase1_enabled": True,
            "auto_buy_live_phase1_allow_real_orders": True,
            "auto_buy_live_phase1_max_orders_per_day": CONSERVATIVE_LIVE_ORDER_LIMIT,
            "auto_buy_live_phase1_max_notional_pct": CONSERVATIVE_MAX_NOTIONAL_PCT,
            "auto_sell_live_phase1_enabled": True,
            "auto_sell_live_phase1_allow_real_orders": True,
            "auto_sell_live_phase1_max_orders_per_day": CONSERVATIVE_LIVE_ORDER_LIMIT,
            "position_management_scheduler_dry_run_only": True,
            "position_management_scheduler_allow_live_orders": False,
            "strategy_auto_buy_scheduler_dry_run_only": True,
            "strategy_auto_buy_scheduler_allow_live_orders": False,
            "kis_scheduler_dry_run": True,
            "kis_scheduler_live_enabled": False,
            "kis_scheduler_allow_real_orders": False,
            "kis_scheduler_configured_allow_real_orders": False,
            "kis_scheduler_buy_enabled": False,
            "kis_scheduler_sell_enabled": False,
            "kis_scheduler_allow_limited_auto_buy": False,
            "kis_scheduler_allow_limited_auto_sell": False,
            "kis_scheduler_max_live_orders_per_day": CONSERVATIVE_LIVE_ORDER_LIMIT,
        }

    def _mode_metadata(
        self,
        mode: str,
        *,
        now_utc: datetime,
        reason: str | None,
        changed_by: str,
    ) -> dict[str, Any]:
        return {
            "operation_mode_requested": mode,
            "operation_mode_changed_at": now_utc,
            "operation_mode_changed_by": str(changed_by or "api")[:80],
            "operation_mode_reason": reason,
        }

    def _record_audit(
        self,
        db: Session,
        *,
        previous_mode: str,
        requested_mode: str,
        effective_mode: str,
        status: str,
        changed_by: str,
        reason: str | None,
        acknowledged: bool,
        provider: str,
        market: str,
        blocking_reasons: list[Any],
        warnings: list[Any],
        before_state: dict[str, Any],
        after_state: dict[str, Any],
    ) -> OperationModeAudit:
        audit = OperationModeAudit(
            previous_mode=previous_mode,
            requested_mode=requested_mode,
            effective_mode=effective_mode,
            status=status,
            changed_by=str(changed_by or "api")[:80],
            reason=reason,
            acknowledged=bool(acknowledged),
            provider=provider,
            market=market,
            blocking_reasons_json=_json_dumps(blocking_reasons),
            warnings_json=_json_dumps(warnings),
            before_state_json=_json_dumps(before_state),
            after_state_json=_json_dumps(after_state),
        )
        db.add(audit)
        db.flush()
        return audit

    def _change_response(
        self,
        *,
        changed: bool,
        previous_mode: str,
        requested_mode: str,
        effective_mode: str,
        status: str,
        safety_status: str,
        message: str,
        blocking_reasons: list[Any],
        warnings: list[Any],
        audit_id: int | None,
        changed_at: str | None,
        underlying_state: dict[str, Any],
    ) -> dict[str, Any]:
        response = {
            "changed": changed,
            "previous_mode": previous_mode,
            "requested_mode": requested_mode,
            "effective_mode": effective_mode,
            "status": status,
            "safety_status": safety_status,
            "display_label": DISPLAY_LABELS[requested_mode],
            "message": message,
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
            "audit_id": audit_id,
            "changed_at": changed_at,
            "underlying_state": underlying_state,
        }
        return sanitize_kis_payload(response)

    def _has_live_runtime(self, settings: dict[str, Any]) -> bool:
        return bool(not settings.get("dry_run", True)) or any(
            bool(settings.get(key)) for key in LIVE_RUNTIME_KEYS
        )

    def _target_payload_needed(self, settings: dict[str, Any], target_mode: str) -> bool:
        if target_mode == "paper":
            return self._has_live_runtime(settings)
        if target_mode == "paused":
            return any(
                bool(settings.get(key))
                for key in (
                    "scheduler_enabled",
                    "kis_scheduler_enabled",
                    "kis_scheduler_live_enabled",
                    "automation_release_enabled",
                    "automation_release_allow_live_phase1",
                    "portfolio_orchestrator_enabled",
                    "portfolio_orchestrator_allow_live_orders",
                    "auto_buy_live_phase1_enabled",
                    "auto_buy_live_phase1_allow_real_orders",
                    "auto_sell_live_phase1_enabled",
                    "auto_sell_live_phase1_allow_real_orders",
                    "agent_chat_live_order_enabled",
                    "agent_chat_live_order_kis_enabled",
                    "agent_chat_live_order_buy_enabled",
                    "agent_chat_live_order_sell_enabled",
                    "strategy_auto_buy_scheduler_enabled",
                    "position_management_scheduler_enabled",
                )
            ) or str(settings.get("automation_mode") or "off") != "off"
        return False

    def _scope(
        self,
        *,
        provider: str | None,
        market: str | None,
    ) -> tuple[str, str]:
        safe_provider = str(provider or DEFAULT_PROVIDER).strip().lower()
        safe_market = str(market or DEFAULT_MARKET).strip().upper()
        return safe_provider, safe_market

    def _after_apply_transition(self, *, target_mode: str, row: RuntimeSetting) -> None:
        return None


def _mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    if mode not in OPERATION_MODES:
        raise ValueError(f"unsupported operation mode: {value}")
    return mode


def _utc(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    return str(value)


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _safe_reason(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return sanitize_kis_text(text[:400])


def _reason_item(code: str) -> dict[str, str]:
    return {
        "code": str(code),
        "message": REASON_MESSAGES.get(str(code), str(code).replace("_", " ")),
    }


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _json_dumps(value: Any) -> str:
    return json.dumps(_json_safe(sanitize_kis_payload(value)), ensure_ascii=False, sort_keys=True)
