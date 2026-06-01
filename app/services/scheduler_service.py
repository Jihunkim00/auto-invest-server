from __future__ import annotations

import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.core.constants import DEFAULT_GATE_LEVEL
from app.db.database import SessionLocal
from app.services.kis_scheduler_simulation_service import KisSchedulerSimulationService
from app.services.kis_scheduler_live_service import KisSchedulerLiveService
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.trading_orchestrator_service import TradingOrchestratorService
from app.services.watchlist_run_service import WatchlistRunService

NY_TZ = ZoneInfo("America/New_York")
KR_TZ = ZoneInfo("Asia/Seoul")


class SchedulerService:
    def __init__(self):
        self.orchestrator = TradingOrchestratorService()
        self.runtime_settings = RuntimeSettingService()
        self.watchlist_run_service = WatchlistRunService()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._slot_runs: set[str] = set()
        self._us_slots = [
            ("open_phase", 9, 35),
            ("midday", 12, 0),
            ("before_close", 15, 40),
        ]
        self._kr_slots = [
            ("open_phase", 9, 5),
            ("midday", 11, 30),
            ("before_close", 14, 50),
        ]

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="trading-scheduler")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run_loop(self):
        while not self._stop_event.is_set():
            now_ny = datetime.now(NY_TZ)
            now_kr = datetime.now(KR_TZ)
            ny_day_key = now_ny.strftime("%Y-%m-%d")
            kr_day_key = now_kr.strftime("%Y-%m-%d")
            self._slot_runs = {
                k
                for k in self._slot_runs
                if k.startswith(ny_day_key) or k.startswith(kr_day_key)
            }

            for slot_name, hour, minute in self._us_slots:
                if now_ny.hour == hour and now_ny.minute == minute:
                    run_key = f"{ny_day_key}:US:{slot_name}"
                    if run_key not in self._slot_runs:
                        self._slot_runs.add(run_key)
                        self._run_us_scheduled_once(slot_name)

            for slot_name, hour, minute in self._kr_slots:
                if now_kr.hour == hour and now_kr.minute == minute:
                    run_key = f"{kr_day_key}:KR:{slot_name}"
                    if run_key not in self._slot_runs:
                        self._slot_runs.add(run_key)
                        self._run_kr_scheduled_once(slot_name)

            time.sleep(20)

    def _run_scheduled_once(self, slot_name: str):
        return self._run_us_scheduled_once(slot_name)

    def _create_scheduler_skip_log(
        self,
        db,
        slot_name: str,
        reason: str,
        market: str = "US",
        provider: str = "alpaca",
    ):
        run_log = self.orchestrator._create_run_log(
            db,
            run_key=f"scheduler_{datetime.now(NY_TZ).strftime('%Y%m%d_%H%M%S')}_{slot_name}",
            trigger_source="scheduler",
            symbol="WATCHLIST",
            mode="watchlist_trade_trigger",
            gate_level=DEFAULT_GATE_LEVEL,
            stage="orchestration",
            result="pending",
            reason=reason,
            request_payload={
                "scheduler_slot": slot_name,
                "source": "scheduler",
                "market": market,
                "provider": provider,
            },
        )
        self.orchestrator._finish(
            db,
            run_log,
            stage="done",
            result="skipped",
            reason=reason,
            response_payload={
                "scheduler_slot": slot_name,
                "reason": reason,
                "market": market,
                "provider": provider,
            },
        )
        return run_log

    def _run_us_scheduled_once(self, slot_name: str):
        db = SessionLocal()
        try:
            runtime_state = self.runtime_settings.get_kis_scheduler_runtime_state(db)
            if not runtime_state.get("scheduler_enabled", False):
                self._create_scheduler_skip_log(
                    db,
                    slot_name=slot_name,
                    reason="scheduler_disabled",
                    market="US",
                    provider="alpaca",
                )
                return

            self.watchlist_run_service.run_once(
                db,
                trigger_source="scheduler",
                gate_level=DEFAULT_GATE_LEVEL,
                source_endpoint="scheduler_service",
                scheduler_slot=slot_name,
            )
        finally:
            db.close()

    def _run_kr_scheduled_once(self, slot_name: str):
        db = SessionLocal()
        try:
            runtime_state = self.runtime_settings.get_kis_scheduler_runtime_state(db)
            if not runtime_state.get("scheduler_enabled", False):
                self._create_scheduler_skip_log(
                    db,
                    slot_name=slot_name,
                    reason="scheduler_disabled",
                    market="KR",
                    provider="kis",
                )
                return

            if not runtime_state.get("kis_scheduler_enabled", False):
                self._create_scheduler_skip_log(
                    db,
                    slot_name=slot_name,
                    reason="kis_scheduler_disabled",
                    market="KR",
                    provider="kis",
                )
                return

            settings_obj = get_settings()
            kis_client = KisClient(settings_obj, KisAuthManager(settings_obj, db))
            KisSchedulerSimulationService(
                kis_client,
                runtime_settings=self.runtime_settings,
            ).run_once(
                db,
                gate_level=DEFAULT_GATE_LEVEL,
                scheduler_slot=slot_name,
                require_enabled=True,
            )
            if runtime_state.get("kis_scheduler_live_enabled", False):
                KisSchedulerLiveService(
                    kis_client,
                    runtime_settings=self.runtime_settings,
                ).run_once(
                    db,
                    gate_level=DEFAULT_GATE_LEVEL,
                )
        finally:
            db.close()


scheduler_service = SchedulerService()
