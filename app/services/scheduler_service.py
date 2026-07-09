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
from app.services.auto_buy_live_phase1_service import AutoBuyLivePhase1Service
from app.services.auto_sell_live_phase1_service import AutoSellLivePhase1Service
from app.services.position_management_dry_run_service import (
    PositionManagementDryRunService,
)
from app.services.auto_exit_candidate_service import AutoExitCandidateService
from app.services.position_exit_review_service import PositionExitReviewService
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.strategy_auto_buy_scheduler_service import (
    StrategyAutoBuySchedulerService,
)
from app.services.profile_aware_guarded_live_auto_buy_service import (
    ProfileAwareGuardedLiveAutoBuyService,
)
from app.services.profile_aware_guarded_live_auto_exit_service import (
    ProfileAwareGuardedLiveAutoExitService,
)
from app.services.strategy_risk_budget_service import StrategyRiskBudgetService
from app.services.target_aware_risk_service import TargetAwareRiskService
from app.services.trading_orchestrator_service import TradingOrchestratorService
from app.services.watchlist_run_service import WatchlistRunService

NY_TZ = ZoneInfo("America/New_York")
KR_TZ = ZoneInfo("Asia/Seoul")


class SchedulerService:
    def __init__(self):
        self.orchestrator = TradingOrchestratorService()
        self.runtime_settings = RuntimeSettingService()
        self.watchlist_run_service = WatchlistRunService()
        self.strategy_auto_buy_scheduler_service = StrategyAutoBuySchedulerService()
        self.position_management_slots = [
            ("position_management_dry_run_open_phase", 9, 0),
            ("position_management_dry_run_midday", 10, 25),
            ("position_management_dry_run_before_close", 14, 25),
        ]
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
        self._strategy_auto_buy_slots = [
            ("strategy_auto_buy_dry_run_open_phase", 9, 10),
            ("strategy_auto_buy_dry_run_midday", 10, 30),
            ("strategy_auto_buy_dry_run_before_close", 14, 30),
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

            for slot_name, hour, minute in self.position_management_slots:
                if now_kr.hour == hour and now_kr.minute == minute:
                    run_key = f"{kr_day_key}:KR:position_management_dry_run:{slot_name}"
                    if run_key not in self._slot_runs:
                        self._slot_runs.add(run_key)
                        self._run_position_management_dry_run_scheduled_once(slot_name)

            for slot_name, hour, minute in self._strategy_auto_buy_slots:
                if now_kr.hour == hour and now_kr.minute == minute:
                    run_key = f"{kr_day_key}:KR:strategy_auto_buy_dry_run:{slot_name}"
                    if run_key not in self._slot_runs:
                        self._slot_runs.add(run_key)
                        self._run_strategy_auto_buy_dry_run_scheduled_once(slot_name)

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

    def _run_strategy_auto_buy_dry_run_scheduled_once(self, slot_name: str):
        db = SessionLocal()
        try:
            buy_phase1_requested = self._phase1_scheduler_hook_requested(db)
            sell_phase1_requested = self._auto_sell_phase1_scheduler_hook_requested(db)
            phase1_requested = buy_phase1_requested or sell_phase1_requested
            kis_client = None
            auto_exit_candidates = None
            position_management_service = None
            position_result = None
            exit_review_service = None
            if phase1_requested:
                settings_obj = get_settings()
                kis_client = KisClient(settings_obj, KisAuthManager(settings_obj, db))
                exit_review_service = PositionExitReviewService(
                    kis_client,
                    runtime_settings=self.runtime_settings,
                )
                auto_exit_candidates = AutoExitCandidateService(exit_review_service)
                position_management_service = PositionManagementDryRunService(
                    auto_exit_candidates=auto_exit_candidates,
                    exit_review_service=exit_review_service,
                    runtime_settings=self.runtime_settings,
                )
                position_result = position_management_service.run_once(
                    db,
                    {
                        "provider": "kis",
                        "market": "KR",
                        "trigger_source": "auto_buy_live_phase1_positions_first",
                        "scheduler_slot": slot_name,
                    },
                    require_enabled=False,
                )
            sell_phase1_result = None
            if (
                sell_phase1_requested
                and kis_client is not None
                and auto_exit_candidates is not None
                and exit_review_service is not None
            ):
                sell_phase1_result = AutoSellLivePhase1Service(
                    runtime_settings=self.runtime_settings,
                    auto_exit_candidates=auto_exit_candidates,
                    exit_review_service=exit_review_service,
                    guarded_exit_service=self._phase1_guarded_sell_service(
                        db,
                        kis_client,
                    ),
                ).run_once(
                    db,
                    {
                        "provider": "kis",
                        "market": "KR",
                        "trigger_source": "scheduler_phase1",
                    },
                )
                if self._auto_sell_phase1_should_skip_buy(sell_phase1_result):
                    return {
                        "position_management": position_result,
                        "auto_sell_phase1": sell_phase1_result,
                        "dry_run": None,
                        "phase1": None,
                        "buy_skipped": True,
                    }
            dry_result = self.strategy_auto_buy_scheduler_service.run_dry_run_once(
                db,
                {
                    "provider": "kis",
                    "market": "KR",
                    "trigger_source": "strategy_auto_buy_dry_run",
                    "scheduler_slot": slot_name,
                },
            )
            phase1_result = None
            if (
                buy_phase1_requested
                and kis_client is not None
                and auto_exit_candidates is not None
                and position_management_service is not None
            ):
                guarded_buy = self._phase1_guarded_buy_service(db, kis_client)
                phase1_result = AutoBuyLivePhase1Service(
                    runtime_settings=self.runtime_settings,
                    guarded_buy_service=guarded_buy,
                    auto_exit_candidates=auto_exit_candidates,
                    position_management_service=position_management_service,
                ).run_once(
                    db,
                    {
                        "provider": "kis",
                        "market": "KR",
                        "trigger_source": "scheduler_phase1",
                    },
                )
            if phase1_result is not None:
                return {
                    "position_management": position_result,
                    "auto_sell_phase1": sell_phase1_result,
                    "dry_run": dry_result,
                    "phase1": phase1_result,
                }
            if sell_phase1_result is not None:
                return {
                    "position_management": position_result,
                    "auto_sell_phase1": sell_phase1_result,
                    "dry_run": dry_result,
                    "phase1": None,
                }
            return dry_result
        finally:
            db.close()

    def _phase1_scheduler_hook_requested(self, db) -> bool:
        settings = self.runtime_settings.get_settings_read_only(db)
        app_settings = get_settings()
        return bool(
            settings.get("auto_buy_live_phase1_enabled")
            and settings.get("auto_buy_live_phase1_allow_real_orders")
            and not settings.get("dry_run")
            and not settings.get("kill_switch")
            and getattr(app_settings, "kis_real_order_enabled", False)
        )

    def _auto_sell_phase1_scheduler_hook_requested(self, db) -> bool:
        settings = self.runtime_settings.get_settings_read_only(db)
        app_settings = get_settings()
        return bool(
            settings.get("auto_sell_live_phase1_enabled")
            and settings.get("auto_sell_live_phase1_allow_real_orders")
            and not settings.get("dry_run")
            and not settings.get("kill_switch")
            and getattr(app_settings, "kis_real_order_enabled", False)
        )

    def _auto_sell_phase1_should_skip_buy(self, result: dict | None) -> bool:
        if not isinstance(result, dict):
            return False
        status = str(result.get("result_status") or "")
        if status in {"submitted", "filled", "pending_sync"}:
            return True
        return bool(
            str(result.get("candidate_severity") or "") == "critical"
            and status
            in {
                "blocked",
                "dry_run_blocked",
                "rejected",
                "error",
                "pending_sync",
            }
        )

    def _phase1_guarded_buy_service(self, db, kis_client: KisClient):
        def positions(session):
            return kis_client.list_positions()

        def balance(session):
            return kis_client.get_account_balance()

        target_risk = TargetAwareRiskService(
            budget_service=StrategyRiskBudgetService(
                position_loader=lambda session, provider, market: positions(session),
                balance_loader=lambda session, provider, market: balance(session),
            )
        )
        return ProfileAwareGuardedLiveAutoBuyService(
            client=kis_client,
            runtime_settings=self.runtime_settings,
            target_risk_service=target_risk,
            positions_loader=positions,
            balance_loader=balance,
            open_orders_loader=lambda session: kis_client.list_open_orders(),
        )

    def _phase1_guarded_sell_service(self, db, kis_client: KisClient):
        return ProfileAwareGuardedLiveAutoExitService(
            client=kis_client,
            runtime_settings=self.runtime_settings,
            positions_loader=lambda session: kis_client.list_positions(),
            open_orders_loader=lambda session: kis_client.list_open_orders(),
        )

    def _run_position_management_dry_run_scheduled_once(self, slot_name: str):
        db = SessionLocal()
        try:
            settings_obj = get_settings()
            kis_client = KisClient(settings_obj, KisAuthManager(settings_obj, db))
            exit_review_service = PositionExitReviewService(
                kis_client,
                runtime_settings=self.runtime_settings,
            )
            return PositionManagementDryRunService(
                auto_exit_candidates=AutoExitCandidateService(exit_review_service),
                exit_review_service=exit_review_service,
                runtime_settings=self.runtime_settings,
            ).run_once(
                db,
                {
                    "provider": "kis",
                    "market": "KR",
                    "trigger_source": "position_management_dry_run",
                    "scheduler_slot": slot_name,
                },
                require_enabled=True,
            )
        finally:
            db.close()


scheduler_service = SchedulerService()
