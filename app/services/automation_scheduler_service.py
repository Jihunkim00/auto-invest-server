from __future__ import annotations

"""The only production scheduler for Custom Profile automation.

Historical scheduler services remain callable through their compatibility
routes, but are intentionally never started by the application.
"""

import time
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.db.database import SessionLocal
from app.db.models import PositionLifecycle
from app.services.automation_execution_authority_service import (
    AutomationExecutionAuthorityService,
)
from app.services.scheduler_service import SchedulerService


KST = ZoneInfo("Asia/Seoul")
CRITICAL_EXIT_ACTIONS = {"SELL_READY", "STOP_LOSS", "TAKE_PROFIT", "EXIT_SIGNAL"}


class AutomationSchedulerService(SchedulerService):
    """Runs exactly one profile-defined KST automation tick per due slot."""

    def _run_loop(self) -> None:
        # Deliberately do not start the former US/KR, phase, soak, release,
        # dry-run, or lifecycle scheduler loops. They are diagnostics or
        # compatibility entry points, not production execution authorities.
        while not self._stop_event.is_set():
            now_kst = datetime.now(KST)
            self._last_heartbeat_at = datetime.now(UTC)
            self._next_profile_run_at = self._next_automation_run_at(now_kst)
            day_key = now_kst.date().isoformat()
            self._slot_runs = {
                key for key in self._slot_runs if key.startswith(f"{day_key}:KR:")
            }
            for slot, hour, minute in self._profile_slots(now_kst):
                if now_kst.hour != hour or now_kst.minute != minute:
                    continue
                run_key = f"{day_key}:KR:automation:{slot}"
                if run_key in self._slot_runs:
                    continue
                self._slot_runs.add(run_key)
                self._safe_call(self._run_automation_tick, slot, now_kst)
            self._last_tick_at = datetime.now(UTC)
            time.sleep(20)

    def _profile_slots(self, now_kst: datetime) -> list[tuple[str, int, int]]:
        db = SessionLocal()
        try:
            schedule = self.automation_profiles.selected_profile_schedule(db, now=now_kst)
            authority = AutomationExecutionAuthorityService(self.runtime_settings).snapshot(db)
            runtime = self.runtime_settings.get_settings_read_only(db)
            if (
                not schedule
                or schedule.get("status") != "active"
                or not authority.get("scheduler_allowed")
                or not runtime.get("automation_profile_scheduler_enabled")
            ):
                return []
            result: list[tuple[str, int, int]] = []
            for value in schedule.get("analysis_times") or []:
                slot = self._profile_scheduler_slot(str(value))
                if slot is None:
                    continue
                hour, minute = (int(item) for item in slot.split(":"))
                result.append((slot, hour, minute))
            return result
        finally:
            db.close()

    def _next_automation_run_at(self, now_kst: datetime) -> datetime | None:
        slots = self._profile_slots(now_kst)
        for _, hour, minute in slots:
            candidate = now_kst.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate > now_kst:
                return candidate
        if not slots:
            return None
        _, hour, minute = slots[0]
        return (now_kst.replace(hour=hour, minute=minute, second=0, microsecond=0)
                + __import__("datetime").timedelta(days=1))

    def run_once(self, *, slot: str | None = None, now: datetime | None = None) -> dict[str, Any]:
        current = now.astimezone(KST) if now and now.tzinfo else (now or datetime.now(KST))
        resolved_slot = self._profile_scheduler_slot(slot or f"{current.hour:02d}:{current.minute:02d}")
        if resolved_slot is None:
            return {"status": "blocked", "reason": "invalid_profile_slot"}
        return self._run_automation_tick(resolved_slot, current)

    def _run_automation_tick(self, slot_name: str, now: datetime | None = None) -> dict[str, Any]:
        db = SessionLocal()
        try:
            now_kst = (now or datetime.now(KST)).astimezone(KST)
            slot = self._profile_scheduler_slot(slot_name)
            authority = AutomationExecutionAuthorityService(self.runtime_settings).snapshot(db)
            runtime = self.runtime_settings.get_settings_read_only(db)
            schedule = self.automation_profiles.selected_profile_schedule(db, now=now_kst)
            if not authority.get("scheduler_allowed"):
                return self._create_scheduler_skip_log(
                    db, slot_name, "automation_mode_off", market="KR", provider="kis"
                )
            if not runtime.get("automation_profile_scheduler_enabled"):
                return self._create_scheduler_skip_log(
                    db, slot_name, "automation_disabled", market="KR", provider="kis"
                )
            if not schedule or schedule.get("status") != "active" or slot is None:
                return self._create_scheduler_skip_log(
                    db, slot_name, "active_profile_or_slot_unavailable", market="KR", provider="kis"
                )

            portfolio = self._manage_portfolio_first(db, slot=slot, now=now_kst)
            if self._critical_exit(portfolio):
                return self._create_scheduler_skip_log(
                    db, slot_name, "position_management_priority_buy_skipped",
                    market="KR", provider="kis",
                )

            dry_run = self.strategy_auto_buy_scheduler_service.run_dry_run_once(
                db,
                {
                    "provider": "kis",
                    "market": "KR",
                    "trigger_source": "automation_scheduler",
                    "scheduler_slot": slot,
                },
                now=now_kst,
            )
            mode = str(authority.get("automation_mode") or "test")
            if mode == "live":
                profile_buy = self._profile_buy_scheduler_service(db).run_once(
                    db,
                    dry_run.get("dry_run_result", dry_run) if isinstance(dry_run, dict) else dry_run,
                    scheduler_slot=slot,
                    trigger_source="automation_scheduler",
                    now=now_kst,
                    enforce_custom_profile_live_guard=True,
                )
            else:
                profile_buy = {
                    "status": "simulated" if mode == "paper" else "analyzed",
                    "action": "hold",
                    "reason": "paper_mode_no_broker_submit" if mode == "paper" else "test_mode_no_broker_submit",
                    "broker_submit_called": False,
                    "broker_buy_call_count": 0,
                    "real_external_kis_submit_count": 0,
                }
            return {
                "scheduler": "AutomationSchedulerService",
                "mode": mode,
                "profile_key": schedule.get("profile_key"),
                "slot": slot,
                "portfolio": portfolio,
                "dry_run": dry_run,
                "profile_buy": profile_buy,
            }
        finally:
            db.close()

    def _manage_portfolio_first(self, db, *, slot: str, now: datetime) -> dict[str, Any] | None:
        if not db.query(PositionLifecycle).filter(
            PositionLifecycle.status.in_(["open", "closing"])
        ).count():
            return {"managed_count": 0, "items": []}
        service = self._profile_buy_scheduler_service(db)
        lifecycle = getattr(service, "lifecycle_service", None)
        if lifecycle is None:
            return {"managed_count": 0, "items": [], "reason": "portfolio_service_unavailable"}
        return lifecycle.run_management_once(
            db,
            execute=False,
            trigger_source="automation_scheduler",
            scheduler_slot=slot,
            now=now,
        )

    @staticmethod
    def _critical_exit(result: dict[str, Any] | None) -> bool:
        return any(
            str(item.get("action") or "").upper() in CRITICAL_EXIT_ACTIONS
            for item in (result or {}).get("items", [])
            if isinstance(item, dict)
        )
