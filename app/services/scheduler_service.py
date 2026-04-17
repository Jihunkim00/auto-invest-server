from __future__ import annotations

import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from app.db.database import SessionLocal
from app.services.trading_orchestrator_service import TradingOrchestratorService

NY_TZ = ZoneInfo("America/New_York")


class SchedulerService:
    def __init__(self):
        self.orchestrator = TradingOrchestratorService()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._slot_runs: set[str] = set()
        self._slots = [
            ("open_phase", 9, 35),
            ("midday", 12, 0),
            ("before_close", 15, 40),
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

    def _run_loop(self):
        while not self._stop_event.is_set():
            now_ny = datetime.now(NY_TZ)
            day_key = now_ny.strftime("%Y-%m-%d")
            self._slot_runs = {k for k in self._slot_runs if k.startswith(day_key)}

            for slot_name, hour, minute in self._slots:
                if now_ny.hour == hour and now_ny.minute == minute:
                    run_key = f"{day_key}:{slot_name}"
                    if run_key not in self._slot_runs:
                        self._slot_runs.add(run_key)
                        self._run_scheduled_once(slot_name)

            time.sleep(20)

    def _run_scheduled_once(self, slot_name: str):
        db = SessionLocal()
        try:
            self.orchestrator.run(
                db,
                trigger_source="schedule",
                request_payload={"scheduler_slot": slot_name},
            )
        finally:
            db.close()


scheduler_service = SchedulerService()