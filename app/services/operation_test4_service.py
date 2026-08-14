from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.core.enums import InternalOrderStatus
from app.db.models import (
    OperationTest4Cycle,
    OperationTest4EntryReservation,
    OrderLog,
    PositionLifecycle,
    TradeRunLog,
)
from app.services.kis_limited_auto_sell_service import KisLimitedAutoSellService
from app.services.kis_manual_order_service import (
    KIS_MANUAL_CONFIRMATION_PHRASE,
    KisManualOrderService,
    KisManualOrderSubmitRequest,
)
from app.services.kis_order_sync_service import KisOrderSyncService, serialize_kis_order
from app.services.kis_order_validation_service import (
    KisOrderValidationRequest,
    KisOrderValidationService,
    record_kis_order_validation,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.kis_account_state_cache_service import KisAccountStateCacheService
from app.services.kis_position_lifecycle_service import KisPositionLifecycleService
from app.services.kis_watchlist_preview_service import KisWatchlistPreviewService
from app.services.market_profile_service import MarketProfileService
from app.services.market_session_service import MarketSessionService
from app.services.operation_test4_next_session import (
    is_entry_slot as is_next_session_entry_slot,
    is_last_entry_slot as is_next_session_last_entry_slot,
    next_entry_slot_for_session,
    next_valid_kr_trading_date,
    parse_trading_date,
)
from app.services.operation_test4_sizing import calculate_operation_test4_sizing
from app.services.operation_test_live_mode_claim_service import (
    OperationTestLiveModeConflict,
)
from app.services.operation_test4_watchlist import (
    DEFAULT_COUNT,
    DEFAULT_PRICE_CAP_KRW,
    OperationTest4WatchlistError,
    build_operation_test4_watchlist,
    load_operation_test4_watchlist,
)
from app.services.runtime_setting_service import RuntimeSettingService


KR_TZ = ZoneInfo("Asia/Seoul")
PROVIDER = "kis"
MARKET = "KR"
OPERATION_TEST = "test4"
MODE = "operation_test4_live"
ENTRY_ENDPOINT = "/app/operation-test4/entry/run-once"
EXIT_ENDPOINT = "/app/operation-test4/reconcile-once"
ENTRY_CONFIRMATION = "RUN TEST4 LIVE ENTRY ONCE"
ENABLE_CONFIRMATION = "ENABLE TEST4 FULL CYCLE"
START_CONFIRMATION = "START TEST4 FULL CYCLE"
HOLD = "HOLD"
STOP_LOSS_READY = "STOP_LOSS_READY"
TAKE_PROFIT_READY = "TAKE_PROFIT_READY"
REVIEW = "REVIEW"
ENTRY_SLOTS = ("09:35", "11:30", "13:30")
POSITION_SLOTS = ("10:00", "12:00", "14:30")
ALL_SLOTS = ENTRY_SLOTS + POSITION_SLOTS
POSSIBLE_ORDER_MAX_AGE_SECONDS = 10.0
ACTIVE_CYCLE_STATUSES = (
    "entry_ready",
    "entry_submitted",
    "entry_pending",
    "position_open",
    "exit_ready",
    "exit_submitted",
    "review_required",
)
OPEN_ORDER_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
}
_ENTRY_SUBMIT_LOCK = threading.RLock()
_PREFLIGHT_PROGRESS_LOCK = threading.RLock()
_PREFLIGHT_PROGRESS: dict[str, Any] = {
    "preflight_running": False,
    "preflight_started_at": None,
    "preflight_finished_at": None,
    "current_stage": None,
    "last_progress_at": None,
    "analyzed_count": 0,
    "total_count": 0,
    "error": None,
}
SUBMITTED_STATUSES = OPEN_ORDER_STATUSES | {
    InternalOrderStatus.FILLED.value,
}
BUY_FLAGS = (
    "kis_live_auto_buy_enabled",
    "kis_limited_auto_buy_enabled",
    "kis_scheduler_buy_enabled",
    "kis_scheduler_allow_limited_auto_buy",
    "strategy_auto_buy_scheduler_enabled",
    "strategy_auto_buy_scheduler_allow_live_orders",
    "strategy_live_auto_buy_enabled",
    "strategy_live_auto_buy_scheduler_enabled",
    "auto_buy_live_phase1_enabled",
    "auto_buy_live_phase1_allow_real_orders",
)
OTHER_SCHEDULER_LIVE_FLAGS = BUY_FLAGS + (
    "kis_scheduler_live_enabled",
    "kis_scheduler_allow_real_orders",
    "kis_scheduler_configured_allow_real_orders",
    "kis_scheduler_sell_enabled",
    "kis_scheduler_allow_limited_auto_sell",
    "kis_live_auto_sell_enabled",
    "kis_limited_auto_sell_enabled",
    "auto_sell_live_phase1_enabled",
    "auto_sell_live_phase1_allow_real_orders",
    "operation_test3_enabled",
    "operation_test3_scheduler_enabled",
    "operation_test3_allow_real_orders",
    "operation_test3_position_management_enabled",
    "agent_chat_live_order_enabled",
    "agent_chat_live_order_kis_enabled",
    "agent_chat_live_order_buy_enabled",
    "automation_release_enabled",
    "automation_release_allow_live_phase1",
    "automation_release_scheduler_enabled",
    "portfolio_orchestrator_allow_live_orders",
)


class _Test4ProfileService:
    def __init__(self, watchlist_path: Path):
        self.watchlist_path = watchlist_path
        self.base = MarketProfileService()

    def get_profile(self, market: str | None = None):
        return self.base.get_profile(market)

    def normalize_symbol(self, symbol: str, market: str | None = None) -> str:
        return self.base.normalize_symbol(symbol, market)

    def load_reference_sites(self, market: str | None = None):
        return self.base.load_reference_sites(market)

    def load_watchlist(self, market: str | None = None):
        payload = load_operation_test4_watchlist(self.watchlist_path)
        return {
            "market": "KR",
            "currency": "KRW",
            "timezone": "Asia/Seoul",
            "watchlist_file": str(self.watchlist_path),
            "count": payload["count"],
            "symbols": payload["symbols"],
        }


class OperationTest4Service:
    def __init__(
        self,
        client: KisClient,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
        watchlist_path: Path | None = None,
        preview_service: Any | None = None,
        limited_auto_sell_service: Any | None = None,
        manual_order_service: Any | None = None,
        validation_service: Any | None = None,
        lifecycle_service: Any | None = None,
        order_sync_service: Any | None = None,
        account_state_provider: Callable[..., dict[str, Any]] | None = None,
        candidate_provider: Callable[..., dict[str, Any]] | None = None,
        possible_order_provider: Callable[..., dict[str, Any]] | None = None,
        price_provider: Callable[..., dict[str, Any]] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()
        root = Path(__file__).resolve().parents[2]
        self.watchlist_path = watchlist_path or root / "config/watchlist_kr_test4.yaml"
        self.preview_service = preview_service or KisWatchlistPreviewService(
            client,
            profile_service=_Test4ProfileService(self.watchlist_path),
            session_service=self.session_service,
            limit=DEFAULT_COUNT,
            gpt_candidate_limit=5,
        )
        self.limited_auto_sell_service = limited_auto_sell_service
        self.manual_order_service = manual_order_service
        self.validation_service = validation_service
        self.lifecycle_service = lifecycle_service
        self.order_sync_service = order_sync_service
        self.account_state_provider = account_state_provider
        self.candidate_provider = candidate_provider
        self.possible_order_provider = possible_order_provider
        self.price_provider = price_provider
        self.now_provider = now_provider or (lambda: datetime.now(UTC))

    def arm_next_session(
        self,
        db: Session,
        *,
        confirm: bool,
        confirmation: str | None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Reserve the next KR session without enabling live execution."""

        if confirm is not True or str(confirmation or "").strip() != "ARM TEST4 NEXT SESSION":
            return sanitize_kis_payload(
                {
                    "status": "blocked",
                    "operation_test": OPERATION_TEST,
                    "arm_mode": "next_session",
                    "reason": "operator_confirmation_required",
                    "required_confirmation": "ARM TEST4 NEXT SESSION",
                    "immediate_order_execution": False,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                }
            )

        now_utc = _aware_utc(now or self.now_provider())
        runtime = self.runtime_settings.get_settings_read_only(db)
        live_test4_flags = (
            "operation_test4_enabled",
            "operation_test4_allow_real_entry",
            "operation_test4_allow_real_exit",
            "operation_test4_entry_enabled",
            "operation_test4_position_management_enabled",
        )
        conflicts = [
            key
            for key in OTHER_SCHEDULER_LIVE_FLAGS
            if runtime.get(key) is True
        ]
        if any(runtime.get(key) is True for key in live_test4_flags):
            conflicts.append("operation_test4_live_mode_active")
        if conflicts:
            return sanitize_kis_payload(
                {
                    "status": "blocked",
                    "operation_test": OPERATION_TEST,
                    "arm_mode": "next_session",
                    "reason": "other_scheduler_live_flags_enabled",
                    "blocking_reasons": _dedupe(conflicts),
                    "immediate_order_execution": False,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                }
            )

        try:
            calendar_service = getattr(self.session_service, "calendar_service", None)
            if calendar_service is None:
                from app.services.market_calendar_service import MarketCalendarService

                calendar_service = MarketCalendarService()
            target_date = next_valid_kr_trading_date(
                now_utc,
                calendar_service=calendar_service,
            )
        except Exception as exc:
            return sanitize_kis_payload(
                {
                    "status": "blocked",
                    "operation_test": OPERATION_TEST,
                    "arm_mode": "next_session",
                    "reason": "trading_calendar_unavailable",
                    "error": _safe_error(exc),
                    "immediate_order_execution": False,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                }
            )

        try:
            settings_after = self.runtime_settings.update_settings(
                db,
                {
                    # Overnight reservation is always safe. The existing
                    # live gates are lowered only by the JIT BUY_READY path.
                    "dry_run": True,
                    "kill_switch": True,
                    "operation_test4_enabled": False,
                    "operation_test4_scheduler_enabled": True,
                    "operation_test4_allow_real_entry": False,
                    "operation_test4_allow_real_exit": False,
                    "operation_test4_entry_enabled": False,
                    "operation_test4_position_management_enabled": False,
                    "operation_test4_stop_loss_enabled": True,
                    "operation_test4_take_profit_enabled": True,
                    "operation_test4_scheduler_arm_mode": "next_session",
                    "operation_test4_target_trading_date": target_date.isoformat(),
                    "operation_test4_scheduler_armed_at": now_utc,
                    "operation_test4_scheduler_last_error": None,
                    "operation_test4_scheduler_last_stage": "armed",
                    "operation_test4_scheduler_last_entry_decision": None,
                    "operation_test4_scheduler_last_evaluated_trade_date": None,
                    "operation_test4_scheduler_last_evaluated_slot_kst": None,
                    **{key: False for key in BUY_FLAGS},
                },
            )
        except OperationTestLiveModeConflict:
            return sanitize_kis_payload(
                {
                    "status": "blocked",
                    "operation_test": OPERATION_TEST,
                    "arm_mode": "next_session",
                    "reason": "operation_test3_active",
                    "immediate_order_execution": False,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                }
            )

        next_slot = next_entry_slot_for_session(
            now_utc,
            target_trading_date=target_date,
            enabled=True,
        )
        return sanitize_kis_payload(
            {
                "status": "armed",
                "operation_test": OPERATION_TEST,
                "confirmation_accepted": True,
                "arm_mode": "next_session",
                "test4_scheduler_armed": True,
                "target_trading_date": target_date.isoformat(),
                "entry_slots_kst": list(ENTRY_SLOTS),
                "next_entry_slot_kst": next_slot["next_entry_slot_kst"],
                "next_automatic_entry_run": next_slot["next_automatic_entry_run"],
                "master_scheduler_enabled": settings_after.get("scheduler_enabled") is True,
                "scheduler_effective": True,
                "immediate_order_execution": False,
                "runtime": self._runtime_snapshot(settings_after),
                "real_order_submitted": False,
                "broker_submit_called": False,
            }
        )

    def arm_today(
        self,
        db: Session,
        *,
        confirm: bool,
        confirmation: str | None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Reserve today's KR session before the first Test4 entry slot."""

        arm_mode = "same_day"
        required_confirmation = "ARM TEST4 TODAY"
        base_blocked = {
            "status": "blocked",
            "operation_test": OPERATION_TEST,
            "arm_mode": arm_mode,
            "immediate_order_execution": False,
            "real_order_submitted": False,
            "broker_submit_called": False,
        }

        if confirm is not True or confirmation != required_confirmation:
            return sanitize_kis_payload(
                {
                    **base_blocked,
                    "reason": "operator_confirmation_required",
                    "required_confirmation": required_confirmation,
                }
            )

        now_utc = _aware_utc(now or self.now_provider())
        now_kst = now_utc.astimezone(KR_TZ)
        first_entry_time = time(9, 35)
        if now_kst.time() >= first_entry_time:
            return sanitize_kis_payload(
                {
                    **base_blocked,
                    "reason": "same_day_arm_window_closed",
                    "detail": "same-day ARM is allowed only before 09:35 KST",
                }
            )

        try:
            calendar_service = getattr(self.session_service, "calendar_service", None)
            if calendar_service is None:
                from app.services.market_calendar_service import MarketCalendarService

                calendar_service = MarketCalendarService()
            target_date = now_kst.date()
            if target_date.weekday() >= 5 or calendar_service.is_holiday("KR", target_date):
                return sanitize_kis_payload(
                    {
                        **base_blocked,
                        "reason": "not_a_valid_kr_trading_day",
                        "target_trading_date": target_date.isoformat(),
                    }
                )
        except Exception as exc:
            return sanitize_kis_payload(
                {
                    **base_blocked,
                    "reason": "trading_calendar_unavailable",
                    "error": _safe_error(exc),
                }
            )

        runtime = self.runtime_settings.get_settings_read_only(db)
        live_test4_flags = (
            "operation_test4_enabled",
            "operation_test4_allow_real_entry",
            "operation_test4_allow_real_exit",
            "operation_test4_entry_enabled",
            "operation_test4_position_management_enabled",
        )
        conflicts = [
            key
            for key in OTHER_SCHEDULER_LIVE_FLAGS
            if runtime.get(key) is True
        ]
        if any(runtime.get(key) is True for key in live_test4_flags):
            conflicts.append("operation_test4_live_mode_active")
        if conflicts:
            return sanitize_kis_payload(
                {
                    **base_blocked,
                    "reason": "other_scheduler_live_flags_enabled",
                    "blocking_reasons": _dedupe(conflicts),
                }
            )

        if self._active_cycle(db) is not None:
            return sanitize_kis_payload(
                {**base_blocked, "reason": "active_cycle_exists"}
            )
        if self._active_lifecycles(db):
            return sanitize_kis_payload(
                {**base_blocked, "reason": "active_lifecycle_exists"}
            )

        account = self._read_account_state(require_fresh=True)
        if account.get("fetch_success") is not True:
            return sanitize_kis_payload(
                {
                    **base_blocked,
                    "reason": "account_state_unavailable",
                    "account": self._account_summary(account),
                }
            )
        if account.get("position_count", 0) > 0:
            return sanitize_kis_payload(
                {
                    **base_blocked,
                    "reason": "position_exists",
                    "account": self._account_summary(account),
                }
            )
        if account.get("open_order_count", 0) > 0:
            return sanitize_kis_payload(
                {
                    **base_blocked,
                    "reason": "open_order_exists",
                    "account": self._account_summary(account),
                }
            )
        if self._local_open_order_count(db) != 0:
            return sanitize_kis_payload(
                {**base_blocked, "reason": "local_open_order_exists"}
            )

        try:
            settings_after = self.runtime_settings.update_settings(
                db,
                {
                    # Reuse the overnight safe state. The existing scheduler
                    # promotes its gates only in the guarded BUY_READY path.
                    "dry_run": True,
                    "kill_switch": True,
                    "operation_test4_enabled": False,
                    "operation_test4_scheduler_enabled": True,
                    "operation_test4_allow_real_entry": False,
                    "operation_test4_allow_real_exit": False,
                    "operation_test4_entry_enabled": False,
                    "operation_test4_position_management_enabled": False,
                    "operation_test4_stop_loss_enabled": True,
                    "operation_test4_take_profit_enabled": True,
                    "operation_test4_scheduler_arm_mode": "next_session",
                    "operation_test4_target_trading_date": target_date.isoformat(),
                    "operation_test4_scheduler_armed_at": now_utc,
                    "operation_test4_scheduler_last_error": None,
                    "operation_test4_scheduler_last_stage": "armed",
                    "operation_test4_scheduler_last_entry_decision": None,
                    "operation_test4_scheduler_last_evaluated_trade_date": None,
                    "operation_test4_scheduler_last_evaluated_slot_kst": None,
                    **{key: False for key in BUY_FLAGS},
                },
            )
        except OperationTestLiveModeConflict:
            return sanitize_kis_payload(
                {**base_blocked, "reason": "operation_test3_active"}
            )

        next_slot = next_entry_slot_for_session(
            now_utc,
            target_trading_date=target_date,
            enabled=True,
        )
        return sanitize_kis_payload(
            {
                "status": "armed",
                "operation_test": OPERATION_TEST,
                "confirmation_accepted": True,
                "arm_mode": arm_mode,
                "test4_scheduler_armed": True,
                "target_trading_date": target_date.isoformat(),
                "entry_slots_kst": list(ENTRY_SLOTS),
                "next_entry_slot_kst": next_slot["next_entry_slot_kst"],
                "next_automatic_entry_run": next_slot["next_automatic_entry_run"],
                "master_scheduler_enabled": settings_after.get("scheduler_enabled") is True,
                "scheduler_effective": True,
                "immediate_order_execution": False,
                "runtime": self._runtime_snapshot(settings_after),
                "real_order_submitted": False,
                "broker_submit_called": False,
            }
        )

    def status(self, db: Session, *, now: datetime | None = None) -> dict[str, Any]:
        now_utc = _aware_utc(now or self.now_provider())
        runtime = self.runtime_settings.get_settings_read_only(db)
        active = self._active_cycle(db)
        account = self._read_account_state()
        daily_buy_limit = int(runtime.get("operation_test4_max_buy_orders_per_day", 3) or 3)
        daily_sell_limit = int(runtime.get("operation_test4_max_sell_orders_per_day", 3) or 3)
        daily_buy_count = self._daily_order_count(db, side="buy", now_utc=now_utc)
        daily_sell_count = self._daily_order_count(db, side="sell", now_utc=now_utc)
        scheduler_enabled = runtime.get("operation_test4_scheduler_enabled") is True
        arm_mode = str(runtime.get("operation_test4_scheduler_arm_mode") or "disarmed")
        target_trading_date = parse_trading_date(
            runtime.get("operation_test4_target_trading_date")
        )
        next_slot = _next_entry_slot_info(now_utc, enabled=scheduler_enabled)
        active_lifecycles = self._active_lifecycles(db)
        has_position_or_order = bool(
            active is not None
            or active_lifecycles
            or account.get("position_count", 0) > 0
            or account.get("open_order_count", 0) > 0
        )
        test4_scheduler_armed = bool(
            scheduler_enabled
            and arm_mode == "next_session"
            and target_trading_date is not None
        )
        if test4_scheduler_armed:
            next_slot = next_entry_slot_for_session(
                now_utc,
                target_trading_date=target_trading_date,
                enabled=True,
            )
            local_date = now_utc.astimezone(KR_TZ).date()
            if target_trading_date < local_date:
                automatic_entry_status = "blocked"
            elif has_position_or_order:
                automatic_entry_status = "position_management"
            elif runtime.get("operation_test4_scheduler_last_entry_decision") == HOLD:
                automatic_entry_status = (
                    "holding_waiting_next_slot"
                    if next_slot["next_entry_slot_kst"]
                    else "session_complete"
                )
            elif target_trading_date > local_date:
                automatic_entry_status = "armed_for_next_session"
            else:
                automatic_entry_status = "waiting_for_slot"
        elif arm_mode == "session_complete":
            automatic_entry_status = "session_complete"
        else:
            automatic_entry_status = (
                "disabled"
                if not scheduler_enabled
                else "position_management_only"
                if has_position_or_order
                else "scheduled"
            )
        progress = _preflight_progress_snapshot()
        payload = sanitize_kis_payload(
            {
                "provider": PROVIDER,
                "market": MARKET,
                "operation_test": OPERATION_TEST,
                "mode": "operation_test4_status",
                "status": "ok",
                "cycle": _serialize_cycle(active) if active else {},
                "active_cycle_count": int(active is not None),
                "account": self._account_summary(account),
                "runtime": self._runtime_snapshot(runtime),
                "scheduler": {
                    "position_slots_kst": list(POSITION_SLOTS),
                    "scheduler_enabled": scheduler_enabled,
                    "master_scheduler_enabled": runtime.get("scheduler_enabled") is True,
                    "test4_scheduler_armed": test4_scheduler_armed,
                    "scheduler_effective": test4_scheduler_armed or (
                        scheduler_enabled
                        and arm_mode in {"disarmed", "active_cycle"}
                    ),
                    "arm_mode": arm_mode,
                    "target_trading_date": (
                        target_trading_date.isoformat()
                        if target_trading_date is not None
                        else None
                    ),
                    "entry_slot_kst": ENTRY_SLOTS[0],
                    "entry_slots_kst": list(ENTRY_SLOTS),
                    "next_entry_slot_kst": next_slot["next_entry_slot_kst"],
                    "next_automatic_entry_run": next_slot["next_automatic_entry_run"],
                    "automatic_entry_status": automatic_entry_status,
                    "last_stage": runtime.get("operation_test4_scheduler_last_stage"),
                    "last_error": runtime.get("operation_test4_scheduler_last_error"),
                    "last_entry_decision": runtime.get(
                        "operation_test4_scheduler_last_entry_decision"
                    ),
                    "last_evaluated_trade_date": runtime.get(
                        "operation_test4_scheduler_last_evaluated_trade_date"
                    ),
                    "last_evaluated_slot_kst": runtime.get(
                        "operation_test4_scheduler_last_evaluated_slot_kst"
                    ),
                    "active_monitor_interval_seconds": 60,
                    "single_symbol": True,
                    "max_open_positions": 1,
                },
                "daily_buy_count": daily_buy_count,
                "daily_buy_limit": daily_buy_limit,
                "remaining_buy_capacity": max(0, daily_buy_limit - daily_buy_count),
                "daily_sell_count": daily_sell_count,
                "daily_sell_limit": daily_sell_limit,
                "remaining_sell_capacity": max(0, daily_sell_limit - daily_sell_count),
                **progress,
                "real_order_submitted": False,
                "broker_submit_called": False,
            }
        )
        return payload

    def readiness(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _aware_utc(now or self.now_provider())
        runtime = self.runtime_settings.get_settings_read_only(db)
        active_cycle = self._active_cycle(db)
        active_lifecycles = self._active_lifecycles(db)
        account = self._read_account_state()
        market_session = self._market_session(now_utc)
        watchlist = self._load_watchlist(
            price_cap_krw=float(runtime.get("operation_test4_price_cap_krw", DEFAULT_PRICE_CAP_KRW)),
            require_fresh=True,
            today_kst=now_utc.astimezone(KR_TZ).date(),
        )
        preview: dict[str, Any] = {}
        candidate: dict[str, Any] = {}
        checks: list[dict[str, Any]] = []
        blocking_reasons: list[str] = []
        review_reasons: list[str] = []

        def add(
            key: str,
            passed: bool,
            reason: str,
            *,
            category: str = "blocking",
            detail: Any | None = None,
            blocking: bool = True,
        ) -> None:
            checks.append(
                {
                    "key": key,
                    "check_name": key,
                    "passed": bool(passed),
                    "blocking": bool(blocking),
                    "detail": detail,
                }
            )
            if passed or not blocking:
                return
            if category == "review":
                review_reasons.append(reason)
            else:
                blocking_reasons.append(reason)

        settings = self.client.settings
        enabled_buy_flags = [key for key in BUY_FLAGS if runtime.get(key) is True]
        enabled_other_scheduler_flags = [
            key
            for key in OTHER_SCHEDULER_LIVE_FLAGS
            if runtime.get(key) is True
        ]
        now_kst = now_utc.astimezone(KR_TZ)
        time_allowed = time(9, 0) <= now_kst.time() < time(14, 0)
        active_position = active_cycle is not None and active_cycle.status == "position_open"
        local_open_order_count = self._local_open_order_count(db)
        daily_buy_count = self._daily_order_count(db, side="buy", now_utc=now_utc)
        daily_buy_limit = int(runtime.get("operation_test4_max_buy_orders_per_day", 3) or 3)
        entry_conditions = [
            ("operation_test4_enabled", runtime.get("operation_test4_enabled") is True, "operation_test4_disabled"),
            ("operation_test4_scheduler_enabled", runtime.get("operation_test4_scheduler_enabled") is True, "operation_test4_scheduler_disabled"),
            ("operation_test4_allow_real_entry", runtime.get("operation_test4_allow_real_entry") is True, "operation_test4_real_entry_disabled"),
            ("operation_test4_entry_enabled", runtime.get("operation_test4_entry_enabled") is True, "operation_test4_entry_disabled"),
            ("provider_is_kis_prod", _is_kis_prod(settings), "kis_prod_required"),
            ("kis_enabled", bool(getattr(settings, "kis_enabled", False)), "kis_disabled"),
            ("kis_real_order_enabled", bool(getattr(settings, "kis_real_order_enabled", False)), "kis_real_order_disabled"),
            ("dry_run_false", runtime.get("dry_run") is False, "dry_run_true"),
            ("kill_switch_false", runtime.get("kill_switch") is False, "kill_switch_enabled"),
            ("all_other_buy_flags_false", not enabled_buy_flags, "other_buy_flags_enabled"),
            (
                "all_other_scheduler_live_flags_false",
                not enabled_other_scheduler_flags,
                "other_scheduler_live_flags_enabled",
                    "blocking",
                    {"enabled_flags": enabled_other_scheduler_flags},
            ),
            ("account_readable", account.get("fetch_success") is True, "account_state_unavailable", "review"),
            ("equity_positive", _number(account.get("equity")) > 0, "equity_unavailable", "review"),
            ("position_count_zero", account.get("position_count") == 0, "position_exists"),
            ("active_lifecycle_zero", len(active_lifecycles) == 0, "active_lifecycle_exists"),
            ("open_order_count_zero", account.get("open_order_count") == 0, "open_order_exists"),
            ("local_open_order_count_zero", local_open_order_count == 0, "local_open_order_exists"),
            ("active_cycle_zero", active_cycle is None, "active_cycle_exists"),
            (
                "daily_buy_capacity_available",
                daily_buy_count < daily_buy_limit,
                "daily_buy_limit_reached",
                "blocking",
                {
                    "daily_buy_count": daily_buy_count,
                    "daily_buy_limit": daily_buy_limit,
                },
            ),
            ("market_open", market_session.get("is_market_open") is True, "market_closed"),
            ("entry_time_allowed", time_allowed, "entry_time_outside_window"),
            (
                "watchlist_snapshot_fresh",
                watchlist.get("fresh") is True,
                watchlist.get("error") or "test4_watchlist_stale",
            ),
            ("watchlist_exact_count", watchlist.get("count") == DEFAULT_COUNT, "watchlist_count_not_50"),
            (
                "watchlist_snapshot_selected_count",
                watchlist.get("selected_count") == DEFAULT_COUNT,
                "watchlist_selected_count_not_50",
            ),
        ]
        for item in entry_conditions:
            key, passed, reason, *extra = item
            category = extra[0] if extra and isinstance(extra[0], str) else "blocking"
            detail = extra[1] if len(extra) > 1 and isinstance(extra[1], dict) else None
            add(key, passed, reason, category=category, detail=detail)
        add(
            "orderable_cash_available_for_candidate",
            account.get("orderable_cash") is not None,
            "orderable_cash_unavailable",
            detail={
                "status": account.get("orderable_cash_status", "unavailable"),
                "deferred_to": "entry_preflight",
            },
            blocking=False,
        )
        add(
            "candidate_required",
            False,
            "candidate_required",
            detail={"heavy_analysis": "entry_preflight_only"},
            blocking=False,
        )

        exit_checks = [
            ("operation_test4_enabled", runtime.get("operation_test4_enabled") is True, "operation_test4_disabled"),
            ("operation_test4_scheduler_enabled", runtime.get("operation_test4_scheduler_enabled") is True, "operation_test4_scheduler_disabled"),
            ("operation_test4_allow_real_exit", runtime.get("operation_test4_allow_real_exit") is True, "operation_test4_real_exit_disabled"),
            ("operation_test4_position_management_enabled", runtime.get("operation_test4_position_management_enabled") is True, "operation_test4_position_management_disabled"),
            ("active_cycle_position_open", active_position, "position_cycle_not_open", "review"),
            ("active_lifecycle_exactly_one", len(active_lifecycles) == 1, "active_lifecycle_count_not_one", "review"),
            ("account_position_present", account.get("position_count") == 1, "broker_position_count_not_one", "review"),
            ("open_order_count_zero", account.get("open_order_count") == 0, "open_order_exists", "review"),
            ("market_open", market_session.get("is_market_open") is True, "market_closed"),
        ]
        exit_blocking: list[str] = []
        exit_review: list[str] = []
        for key, passed, reason, *extra in exit_checks:
            category = extra[0] if extra else "blocking"
            if not passed:
                (exit_review if category == "review" else exit_blocking).append(reason)

        entry_blocking = _dedupe(blocking_reasons)
        entry_review = _dedupe(review_reasons)
        if active_cycle is None and not active_lifecycles and account.get("position_count") == 0:
            exit_blocking = []
            exit_review = []
        else:
            exit_blocking = _dedupe(exit_blocking)
            exit_review = _dedupe(exit_review)
        entry_base_ready = not entry_blocking and not entry_review
        entry_ready = False
        exit_ready = bool(active_position) and not exit_blocking and not exit_review
        live_ready = exit_ready
        status = (
            "ready_for_preflight"
            if entry_base_ready and not exit_ready
            else "ready"
            if live_ready
            else "review_required"
            if entry_review or exit_review
            else "blocked"
        )
        payload = sanitize_kis_payload(
            {
                "status": status,
                "live_ready": live_ready,
                "entry_ready": entry_ready,
                "exit_ready": exit_ready,
                "entry_base_ready": entry_base_ready,
                "candidate_required": True,
                "provider": PROVIDER,
                "market": MARKET,
                "operation_test": OPERATION_TEST,
                "cycle": _serialize_cycle(active_cycle) if active_cycle else {},
                "account": self._account_summary(account),
                "watchlist": {
                    "configured_count": watchlist.get("count", 0),
                    "eligible_count": watchlist.get("selected_count", 0),
                    "price_cap_krw": runtime.get("operation_test4_price_cap_krw", DEFAULT_PRICE_CAP_KRW),
                    "path": str(self.watchlist_path),
                },
                "candidate": candidate or {
                    "symbol": None,
                    "current_price": None,
                    "quantity": None,
                    "estimated_notional": None,
                    "effective_position_pct": None,
                },
                "orderable_cash_status": account.get(
                    "orderable_cash_status", "unavailable"
                ),
                "heavy_analysis": {
                    "performed": False,
                    "deferred_to": "/app/operation-test4/entry/preflight-once",
                },
                "runtime": self._runtime_snapshot(runtime),
                "conflicting_live_flags": enabled_other_scheduler_flags,
                "market_session": _public_market_session(market_session),
                "checks": checks,
                "blocking_reasons": _dedupe(entry_blocking + exit_blocking),
                "review_reasons": _dedupe(entry_review + exit_review),
                "entry_blocking_reasons": entry_blocking,
                "entry_review_reasons": entry_review,
                "exit_blocking_reasons": exit_blocking,
                "exit_review_reasons": exit_review,
                "safety": {
                    "read_only": True,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                },
            }
        )
        payload["checks"] = [
            {**item, "key": item.get("check_name") or item.get("key")}
            for item in checks
        ]
        return payload

    def rebuild_watchlist(
        self,
        db: Session,
        *,
        count: int = DEFAULT_COUNT,
        price_cap_krw: float = DEFAULT_PRICE_CAP_KRW,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        del db
        try:
            result = build_operation_test4_watchlist(
                root=Path(__file__).resolve().parents[2],
                output_path=self.watchlist_path,
                count=count,
                price_cap_krw=price_cap_krw,
                client=self.client,
                now=now,
            )
        except OperationTest4WatchlistError as exc:
            details = dict(exc.details or {})
            return sanitize_kis_payload(
                {
                    "status": "blocked",
                    "operation_test": OPERATION_TEST,
                    "source_universe_count": details.get("source_universe_count", 0),
                    "quote_checked_count": details.get("quote_checked_count", 0),
                    "eligible_count": details.get("eligible_count", 0),
                    "selected_count": details.get("selected_count", 0),
                    "reserve_eligible_count": details.get("reserve_eligible_count", 0),
                    "excluded_count": details.get("excluded_count", 0),
                    "exclusion_reasons": details.get("exclusion_reasons", {}),
                    "exclusion_symbols": details.get("exclusion_symbols", []),
                    "output_file": str(self.watchlist_path),
                    "read_only": True,
                    "reason": str(exc),
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                }
            )
        return sanitize_kis_payload(
            {
                "status": "completed",
                "operation_test": OPERATION_TEST,
                "source_universe_count": result["source_universe_count"],
                "quote_checked_count": result["quote_checked_count"],
                "eligible_count": result["eligible_count"],
                "selected_count": result["selected_count"],
                "reserve_eligible_count": result["reserve_eligible_count"],
                "excluded_count": result["excluded_count"],
                "exclusion_reasons": result["exclusion_reasons"],
                "selected_symbols": result["selected_symbols"],
                "output_file": str(self.watchlist_path),
                "read_only": True,
                "real_order_submitted": False,
                "broker_submit_called": False,
            }
        )

    def enable_live(
        self,
        db: Session,
        *,
        confirm_live: bool,
        confirmation: str | None,
        now: datetime | None = None,
        activate_global_guards: bool = False,
        allowed_cycle_id: int | None = None,
    ) -> dict[str, Any]:
        if confirm_live is not True or str(confirmation or "").strip() != ENABLE_CONFIRMATION:
            return self._blocked_enable("operator_confirmation_required")
        now_utc = _aware_utc(now or self.now_provider())
        runtime = self.runtime_settings.get_settings_read_only(db)
        account = self._read_account_state(require_fresh=True)
        active_cycle = self._active_cycle(db)
        active_lifecycle_count = len(self._active_lifecycles(db))
        local_open_order_count = self._local_open_order_count(db)
        enabled_buy_flags = [key for key in BUY_FLAGS if runtime.get(key) is True]
        enabled_other_scheduler_flags = [
            key
            for key in OTHER_SCHEDULER_LIVE_FLAGS
            if runtime.get(key) is True
        ]
        settings = self.client.settings
        blockers: list[str] = []
        if not _is_kis_prod(settings):
            blockers.append("kis_prod_required")
        if not bool(getattr(settings, "kis_enabled", False)):
            blockers.append("kis_disabled")
        if not bool(getattr(settings, "kis_real_order_enabled", False)):
            blockers.append("kis_real_order_disabled")
        if account.get("fetch_success") is not True:
            blockers.append("account_state_unavailable")
        if account.get("position_count") != 0:
            blockers.append("position_exists")
        if active_lifecycle_count != 0:
            blockers.append("active_lifecycle_exists")
        if account.get("open_order_count") != 0:
            blockers.append("open_order_exists")
        if local_open_order_count != 0:
            blockers.append("local_open_order_exists")
        if active_cycle is not None and active_cycle.id != allowed_cycle_id:
            blockers.append("active_cycle_exists")
        test3_flags = (
            "operation_test3_enabled",
            "operation_test3_scheduler_enabled",
            "operation_test3_allow_real_orders",
            "operation_test3_position_management_enabled",
        )
        if any(runtime.get(key) is True for key in test3_flags):
            blockers.append("operation_test3_live_flags_enabled")
        daily_buy_limit = int(runtime.get("operation_test4_max_buy_orders_per_day", 3) or 3)
        if self._daily_order_count(db, side="buy", now_utc=now_utc) >= daily_buy_limit:
            blockers.append("daily_buy_limit_reached")
        if enabled_buy_flags:
            blockers.append("other_buy_flags_enabled")
        if enabled_other_scheduler_flags:
            blockers.append("other_scheduler_live_flags_enabled")
        if blockers:
            return sanitize_kis_payload(
                {
                    "status": "blocked",
                    "reason": blockers[0],
                    "blocking_reasons": _dedupe(blockers),
                    "immediate_order_execution": False,
                    "runtime": self._runtime_snapshot(runtime),
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                }
            )
        try:
            settings_after = self.runtime_settings.update_settings(
                db,
                {
                **(
                    {"dry_run": False, "kill_switch": False}
                    if activate_global_guards
                    else {}
                ),
                "operation_test4_enabled": True,
                "operation_test4_scheduler_enabled": True,
                "operation_test4_allow_real_entry": True,
                "operation_test4_allow_real_exit": True,
                "operation_test4_entry_enabled": True,
                "operation_test4_position_management_enabled": True,
                "operation_test4_stop_loss_enabled": True,
                "operation_test4_take_profit_enabled": True,
                "operation_test4_min_position_pct": 10.0,
                "operation_test4_max_position_pct": 100.0,
                "operation_test4_max_order_notional_krw": 1_000_000.0,
                "operation_test4_price_cap_krw": 1_000_000.0,
                "operation_test4_max_buy_orders_per_day": 3,
                "operation_test4_max_sell_orders_per_day": 3,
                "operation_test4_max_open_positions": 1,
                "operation_test4_allow_single_share_budget_bump": True,
                "operation_test4_cash_only": True,
                "operation_test4_no_new_entry_after": "14:00",
                    **{key: False for key in BUY_FLAGS},
                },
            )
        except OperationTestLiveModeConflict:
            return sanitize_kis_payload(
                {
                    "status": "blocked",
                    "reason": "operation_test3_active",
                    "immediate_order_execution": False,
                    "runtime": self._runtime_snapshot(
                        self.runtime_settings.get_settings_read_only(db)
                    ),
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                }
            )
        return sanitize_kis_payload(
            {
                "status": "live_enabled",
                "operation_test": OPERATION_TEST,
                "confirmation_accepted": True,
                "immediate_order_execution": False,
                "enabled_at": now_utc.isoformat(),
                "runtime": self._runtime_snapshot(settings_after),
                "dry_run_unchanged": settings_after.get("dry_run"),
                "kill_switch_unchanged": settings_after.get("kill_switch"),
                "real_order_submitted": False,
                "broker_submit_called": False,
            }
        )

    def disable(self, db: Session, *, reason: str = "operator_disarm") -> dict[str, Any]:
        settings = self._disarm(db, reason=reason)
        return sanitize_kis_payload(
            {
                "status": "disabled",
                "operation_test": OPERATION_TEST,
                "reason": reason,
                "runtime": self._runtime_snapshot(settings),
                "real_order_submitted": False,
                "broker_submit_called": False,
            }
        )

    def start_full_cycle(
        self,
        db: Session,
        *,
        confirm_live: bool,
        confirmation: str | None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        with _ENTRY_SUBMIT_LOCK:
            return self._start_full_cycle(
                db,
                confirm_live=confirm_live,
                confirmation=confirmation,
                now=now,
            )

    def _start_full_cycle(
        self,
        db: Session,
        *,
        confirm_live: bool,
        confirmation: str | None,
        now: datetime | None,
    ) -> dict[str, Any]:
        if (
            confirm_live is not True
            or str(confirmation or "").strip() != START_CONFIRMATION
        ):
            return sanitize_kis_payload(
                {
                    "status": "blocked",
                    "operation_test": OPERATION_TEST,
                    "action": HOLD,
                    "reason": "operator_confirmation_required",
                    "required_confirmation": START_CONFIRMATION,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                }
            )

        now_utc = _aware_utc(now or self.now_provider())
        existing_blockers = self._start_idempotency_blockers(db, now=now_utc)
        if existing_blockers:
            return sanitize_kis_payload(
                {
                    "status": "blocked",
                    "operation_test": OPERATION_TEST,
                    "action": HOLD,
                    "reason": existing_blockers[0],
                    "blocking_reasons": existing_blockers,
                    "runtime": self._runtime_snapshot(
                        self.runtime_settings.get_settings_read_only(db)
                    ),
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                }
            )

        _preflight_progress_start()
        _preflight_progress_update(stage="watchlist_rebuild")
        rebuilt = self.rebuild_watchlist(db, now=now_utc)
        if rebuilt.get("status") != "completed":
            _preflight_progress_update(
                stage="failed",
                error=str(rebuilt.get("reason") or "watchlist_rebuild_failed"),
            )
            _preflight_progress_finish(failed=True)
            return sanitize_kis_payload(
                {
                    "status": "blocked",
                    "operation_test": OPERATION_TEST,
                    "action": HOLD,
                    "reason": rebuilt.get("reason") or "watchlist_rebuild_failed",
                    "watchlist_rebuild": rebuilt,
                    "runtime": self._runtime_snapshot(
                        self.runtime_settings.get_settings_read_only(db)
                    ),
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                }
            )

        preflight = self.preflight_once(db, now=now_utc)
        if preflight.get("status") != "ready" or preflight.get("action") != "BUY_READY":
            return sanitize_kis_payload(
                {
                    "status": "hold",
                    "operation_test": OPERATION_TEST,
                    "action": HOLD,
                    "reason": (
                        preflight.get("blocking_reasons")
                        or preflight.get("review_reasons")
                        or ["candidate_gate_blocked"]
                    )[0],
                    "watchlist_rebuild": rebuilt,
                    "preflight": preflight,
                    "runtime": self._runtime_snapshot(
                        self.runtime_settings.get_settings_read_only(db)
                    ),
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                }
            )

        arm_state = {"armed": False}
        try:
            entry = self.entry_run_once(
                db,
                confirm_live=True,
                confirmation=ENTRY_CONFIRMATION,
                now=now_utc,
                trigger_source="operation_test4_start",
                _preflight=preflight,
                _arm_for_submit=True,
                _arm_state=arm_state,
            )
        except Exception as exc:
            runtime = self.runtime_settings.get_settings_read_only(db)
            if arm_state["armed"] is True:
                runtime = self._disarm(db, reason="start_entry_exception")
            return sanitize_kis_payload(
                {
                    "status": "blocked",
                    "operation_test": OPERATION_TEST,
                    "action": HOLD,
                    "reason": "start_entry_exception",
                    "error": _safe_error(exc),
                    "watchlist_rebuild": rebuilt,
                    "preflight": preflight,
                    "runtime": self._runtime_snapshot(runtime),
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                }
            )

        if arm_state["armed"] is True and entry.get("real_order_submitted") is not True:
            self._disarm(db, reason="start_entry_not_submitted")
        return sanitize_kis_payload(
            {
                "status": "entry_submitted"
                if entry.get("real_order_submitted") is True
                else "blocked",
                "operation_test": OPERATION_TEST,
                "action": "BUY_READY" if entry.get("real_order_submitted") is True else HOLD,
                "reason": entry.get("reason"),
                "watchlist_rebuild": rebuilt,
                "preflight": preflight,
                "entry": entry,
                "runtime": self._runtime_snapshot(
                    self.runtime_settings.get_settings_read_only(db)
                ),
                "real_order_submitted": entry.get("real_order_submitted") is True,
                "broker_submit_called": entry.get("broker_submit_called") is True,
                "manual_submit_called": entry.get("manual_submit_called") is True,
            }
        )

    def preflight_once(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        _preflight_progress_start()
        result: dict[str, Any] | None = None
        try:
            result = self._preflight_once(db, now=now)
            return result
        except Exception as exc:
            _preflight_progress_update(stage="failed", error=_safe_error(exc))
            raise
        finally:
            _preflight_progress_finish(failed=result is None)

    def _preflight_once(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _aware_utc(now or self.now_provider())
        _preflight_progress_update(stage="readiness")
        readiness = self.readiness(db, now=now_utc)

        preflight_ignored_blockers = {
            "operation_test4_disabled",
            "operation_test4_scheduler_disabled",
            "operation_test4_real_entry_disabled",
            "operation_test4_entry_disabled",
            "dry_run_true",
            "kill_switch_enabled",
        }

        preflight_blocking_reasons = [
            reason
            for reason in readiness.get("entry_blocking_reasons", [])
            if reason not in preflight_ignored_blockers
        ]

        preflight_review_reasons = list(
            readiness.get("entry_review_reasons", [])
        )

        if preflight_blocking_reasons or preflight_review_reasons:
            return sanitize_kis_payload(
                {
                    **readiness,
                    "mode": "operation_test4_preflight",
                    "preflight_only": True,
                    "status": "blocked",
                    "action": HOLD,
                    "blocking_reasons": preflight_blocking_reasons,
                    "review_reasons": preflight_review_reasons,
                    "safety": _read_only_safety(),
                }
            )

        runtime = self.runtime_settings.get_settings_read_only(db)
        account = self._read_account_state(require_fresh=True)
        _preflight_progress_update(stage="quant_analysis")
        preview, candidate = self._candidate_snapshot(
            db,
            account=account,
            runtime=runtime,
            now=now_utc,
        )
        _preflight_progress_update(
            analyzed_count=_int_or_none(preview.get("analyzed_symbol_count")) or 0,
            total_count=_int_or_none(preview.get("configured_symbol_count")) or 0,
            stage="final_decision",
        )
        sizing = candidate.get("sizing") if candidate else None
        preflight_account = dict(account)
        if candidate:
            preflight_account.update(
                {
                    "orderable_cash": candidate.get("orderable_cash"),
                    "orderable_cash_status": "ok"
                    if candidate.get("orderable_cash") is not None
                    else "unavailable",
                    "orderable_cash_source": (
                        candidate.get("possible_order", {}).get("source")
                    ),
                }
            )
        blocking_reasons = list(candidate.get("block_reasons") or []) if candidate else ["no_candidate"]
        action = "BUY_READY" if candidate and not blocking_reasons and sizing and sizing.get("status") == "ready" else HOLD
        status = "ready" if action == "BUY_READY" else "hold" if candidate else "blocked"
        return sanitize_kis_payload(
            {
                "status": status,
                "action": action,
                "provider": PROVIDER,
                "market": MARKET,
                "operation_test": OPERATION_TEST,
                "mode": "operation_test4_preflight",
                "analysis_mode": "operation_test4_heavy_preflight",
                "execution_decision": action,
                "preflight_only": True,
                "candidate_required": False,
                "watchlist": readiness.get("watchlist", {}),
                "checks": readiness.get("checks", []),
                "candidate": candidate or {
                    "symbol": None,
                    "current_price": None,
                    "final_buy_score": None,
                    "risk_flags": [],
                },
                "account": self._account_summary(preflight_account),
                "sizing": sizing or {
                    "quantity": 0,
                    "estimated_notional": 0,
                    "effective_position_pct": 0,
                    "broker_orderable_quantity": None,
                },
                "possible_order": candidate.get("possible_order") if candidate else None,
                "preview": {
                    "configured_count": preview.get("configured_symbol_count"),
                    "analyzed_count": preview.get("analyzed_symbol_count"),
                    "final_ranked_count": len(preview.get("final_ranked_candidates") or []),
                    "preview_only": preview.get("preview_only"),
                    "kr_trading_disabled": preview.get("kr_trading_disabled"),
                    "trading_enabled": preview.get("trading_enabled"),
                    "next_manual_action_hint": preview.get("next_manual_action_hint"),
                },
                "analysis": {
                    "source_preview_fields": {
                        "preview_only": preview.get("preview_only"),
                        "kr_trading_disabled": preview.get("kr_trading_disabled"),
                        "trading_enabled": preview.get("trading_enabled"),
                        "next_manual_action_hint": preview.get("next_manual_action_hint"),
                    }
                },
                "execution": {
                    "decision": action,
                    "block_reasons": _dedupe(blocking_reasons),
                    "trade_ready": action == "BUY_READY",
                },
                "preview_display": {
                    "preview_only": preview.get("preview_only"),
                    "kr_trading_disabled": preview.get("kr_trading_disabled"),
                    "trading_enabled": preview.get("trading_enabled"),
                    "next_manual_action_hint": preview.get("next_manual_action_hint"),
                },
                "blocking_reasons": _dedupe(blocking_reasons),
                "review_reasons": [],
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "safety": _read_only_safety(),
            }
        )

    def entry_run_once(
        self,
        db: Session,
        *,
        confirm_live: bool,
        confirmation: str | None,
        now: datetime | None = None,
        trigger_source: str = "operation_test4_run_once",
        entry_slot_kst: str | None = None,
        _preflight: dict[str, Any] | None = None,
        _arm_for_submit: bool = False,
        _arm_state: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        with _ENTRY_SUBMIT_LOCK:
            return self._entry_run_once(
                db,
                confirm_live=confirm_live,
                confirmation=confirmation,
                now=now,
                trigger_source=trigger_source,
                entry_slot_kst=entry_slot_kst,
                preflight=_preflight,
                arm_for_submit=_arm_for_submit,
                arm_state=_arm_state,
            )

    def _entry_run_once(
        self,
        db: Session,
        *,
        confirm_live: bool,
        confirmation: str | None,
        now: datetime | None,
        trigger_source: str,
        entry_slot_kst: str | None,
        preflight: dict[str, Any] | None,
        arm_for_submit: bool,
        arm_state: dict[str, bool] | None,
    ) -> dict[str, Any]:
        now_utc = _aware_utc(now or self.now_provider())
        entry_slot = (
            entry_slot_kst
            if entry_slot_kst in ENTRY_SLOTS
            else _entry_slot_for_time(now_utc)
        )
        if confirm_live is not True or str(confirmation or "").strip() != ENTRY_CONFIRMATION:
            return self._entry_blocked("operator_confirmation_required")
        now_kst = now_utc.astimezone(KR_TZ)
        if now_kst.time() < time(9, 0):
            return self._entry_blocked("entry_before_09_00")
        if now_kst.time() >= time(14, 0):
            return self._entry_blocked("entry_after_14_00")
        if preflight is None:
            readiness = self.readiness(db, now=now_utc)
            if readiness.get("entry_base_ready") is not True:
                return sanitize_kis_payload(
                    {
                        "status": "blocked",
                        "operation_test": OPERATION_TEST,
                        "result": HOLD,
                        "reason": (
                            readiness.get("blocking_reasons")
                            or readiness.get("review_reasons")
                            or ["readiness_not_ready"]
                        )[0],
                        "blocking_reasons": readiness.get("blocking_reasons", []),
                        "review_reasons": readiness.get("review_reasons", []),
                        "readiness": readiness,
                        "real_order_submitted": False,
                        "broker_submit_called": False,
                        "manual_submit_called": False,
                    }
                )
            preflight = self.preflight_once(db, now=now_utc)
        if preflight.get("status") != "ready" or preflight.get("action") != "BUY_READY":
            return sanitize_kis_payload(
                {
                    "status": "blocked" if preflight.get("status") == "blocked" else "ok",
                    "operation_test": OPERATION_TEST,
                    "result": HOLD,
                    "reason": (preflight.get("blocking_reasons") or ["candidate_gate_blocked"])[0],
                    "blocking_reasons": preflight.get("blocking_reasons", []),
                    "review_reasons": preflight.get("review_reasons", []),
                    "preflight": preflight,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                }
            )
        daily_buy_limit = int(
            self.runtime_settings.get_settings_read_only(db).get(
                "operation_test4_max_buy_orders_per_day", 3
            )
            or 3
        )
        if self._daily_order_count(db, side="buy", now_utc=now_utc) >= daily_buy_limit:
            return self._entry_blocked("daily_buy_limit_reached")

        runtime = self.runtime_settings.get_settings_read_only(db)
        next_session_target = (
            runtime.get("operation_test4_target_trading_date")
            if arm_for_submit
            and runtime.get("operation_test4_scheduler_arm_mode") == "next_session"
            else None
        )
        candidate = preflight.get("candidate") or {}
        fresh_price = self._current_price(
            symbol=str(candidate.get("symbol") or ""),
            fallback=_number(candidate.get("current_price")),
        )
        if fresh_price is None or fresh_price <= 0:
            return self._entry_blocked("current_price_unavailable")
        if fresh_price >= float(runtime.get("operation_test4_price_cap_krw", DEFAULT_PRICE_CAP_KRW)):
            return self._entry_blocked("price_cap_exceeded")
        candidate = {**candidate, "current_price": fresh_price}
        preflight_possible = candidate.get("possible_order") or {}
        if not _possible_order_is_fresh(
            preflight_possible,
            now=now_utc,
            max_age_seconds=POSSIBLE_ORDER_MAX_AGE_SECONDS,
        ):
            return self._entry_blocked("possible_order_snapshot_stale")
        latest_possible = self._possible_order(
            symbol=str(candidate.get("symbol") or ""),
            current_price=fresh_price,
        )
        conservative_possible = _conservative_possible_order(
            preflight_possible,
            latest_possible,
        )
        if conservative_possible.get("raw_status") != "ok":
            return self._entry_blocked(
                str(conservative_possible.get("error") or "possible_order_unavailable")
            )
        latest_cash = _number_or_none(conservative_possible.get("orderable_cash"))
        latest_quantity = _int_or_none(conservative_possible.get("orderable_quantity"))
        if latest_cash is None or latest_quantity is None:
            return self._entry_blocked("possible_order_unavailable")
        sizing = calculate_operation_test4_sizing(
            equity=_number(candidate.get("equity")),
            orderable_cash=latest_cash,
            current_price=_number(candidate.get("current_price")),
            min_position_pct=float(runtime.get("operation_test4_min_position_pct", 10.0)),
            max_position_pct=float(runtime.get("operation_test4_max_position_pct", 100.0)),
            max_order_notional_krw=float(runtime.get("operation_test4_max_order_notional_krw", 1_000_000.0)),
            price_cap_krw=float(runtime.get("operation_test4_price_cap_krw", 1_000_000.0)),
            broker_orderable_qty=latest_quantity,
            allow_single_share_budget_bump=bool(
                runtime.get("operation_test4_allow_single_share_budget_bump", True)
            ),
        )
        if not sizing.allowed:
            return self._entry_blocked(str(sizing.reason or "sizing_blocked"))
        candidate = {
            **candidate,
            "orderable_cash": latest_cash,
            "orderable_quantity": latest_quantity,
            "possible_order": conservative_possible,
            "sizing": {
                **sizing.as_dict(),
                "min_position_pct": runtime.get("operation_test4_min_position_pct", 10.0),
                "max_position_pct": runtime.get("operation_test4_max_position_pct", 100.0),
                "price_cap_krw": runtime.get("operation_test4_price_cap_krw", 1_000_000.0),
                "max_order_notional_krw": runtime.get("operation_test4_max_order_notional_krw", 1_000_000.0),
            },
        }
        sizing_payload = candidate["sizing"]
        validation = self._validate_entry(
            db,
            symbol=str(candidate.get("symbol") or ""),
            quantity=int(sizing_payload.get("quantity") or 0),
            now=now_utc,
            candidate=candidate,
        )
        if validation.get("valid") is not True:
            return self._entry_result(
                None,
                reason=str(validation.get("reason") or "validation_failed"),
                validation=validation,
            )

        if arm_for_submit:
            refreshed_candidate, refresh_reason = self._refresh_candidate_for_submit(
                candidate,
                runtime=runtime,
            )
            if refresh_reason is not None:
                return self._entry_blocked(refresh_reason)
            if int(refreshed_candidate["sizing"].get("quantity") or 0) != int(
                sizing_payload.get("quantity") or 0
            ):
                return self._entry_blocked("submit_sizing_changed")
            candidate = refreshed_candidate
            sizing_payload = candidate["sizing"]

        pre_arm_blockers = self._entry_submission_blockers(
            db,
            now=now_utc,
            require_live=not arm_for_submit,
        )
        if pre_arm_blockers:
            return self._entry_blocked(pre_arm_blockers[0])

        reservation = self._reserve_entry_submission(
            db,
            now=now_utc,
            entry_slot_kst=entry_slot,
        )
        if reservation is None:
            return self._entry_blocked("daily_entry_reservation_exists")

        cycle = self._create_entry_cycle(
            db,
            candidate=candidate,
            sizing=sizing_payload,
            now=now_utc,
            trigger_source=trigger_source,
        )
        self._bind_entry_reservation(db, reservation=reservation, cycle=cycle)
        # Persist the one-shot claim before any global live guard is lowered.
        self._mark_entry_reservation_submission_attempted(db, reservation=reservation)

        if arm_for_submit:
            arm_result = self.enable_live(
                db,
                confirm_live=True,
                confirmation=ENABLE_CONFIRMATION,
                now=now_utc,
                activate_global_guards=True,
                allowed_cycle_id=cycle.id,
            )
            if arm_result.get("status") != "live_enabled":
                self._review_and_disarm(
                    db,
                    cycle,
                    str(arm_result.get("reason") or "live_arm_blocked"),
                )
                return self._entry_result(
                    cycle,
                    reason=str(arm_result.get("reason") or "live_arm_blocked"),
                    validation=validation,
                )
            if arm_state is not None:
                arm_state["armed"] = True

        # This is the last safety read.  After it, the only operation is the
        # existing guarded manual-order submit path.
        final_submit_blockers = self._entry_submission_blockers(
            db,
            now=now_utc,
            require_live=True,
            allowed_cycle_id=cycle.id,
        )
        if final_submit_blockers:
            self._review_and_disarm(db, cycle, final_submit_blockers[0])
            return self._entry_result(
                cycle,
                reason=final_submit_blockers[0],
                validation=validation,
            )
        request = KisManualOrderSubmitRequest(
            market=MARKET,
            symbol=cycle.symbol,
            side="buy",
            qty=int(cycle.requested_quantity or 0),
            order_type="market",
            dry_run=False,
            confirm_live=True,
            confirmation=_manual_confirmation(self.client),
            reason="Operation Test 4 automated live entry",
            source_context=(
                "operation_test4_scheduler"
                if trigger_source == "operation_test4_scheduler"
                else "operation_test4_run_once"
            ),
            source_metadata={
                "source": "operation_test4_auto_entry",
                "source_type": "operation_test4_auto_entry",
                "source_context": (
                    "operation_test4_scheduler"
                    if trigger_source == "operation_test4_scheduler"
                    else "operation_test4_run_once"
                ),
                "audit_source_context": (
                    "operation_test4_scheduler"
                    if trigger_source == "operation_test4_scheduler"
                    else "operation_test4_run_once"
                ),
                "source_endpoint": ENTRY_ENDPOINT,
                "order_source": "operation_test4_auto_entry",
                "operation_test": OPERATION_TEST,
                "mode": MODE,
                "trigger_source": trigger_source,
                "real_order_submit_allowed": True,
                "auto_buy_enabled": True,
                "limited_auto_buy_enabled": False,
                "risk_flags": candidate.get("risk_flags") or [],
                "gating_notes": ["operation_test4_entry_gate_passed"],
            },
        )
        try:
            status_code, response = self._manual_submit(db, request, now_utc)
        except Exception as exc:
            cycle.status = "failed"
            cycle.manual_review_required = True
            cycle.last_error = _safe_error(exc)
            db.commit()
            settings = self._disarm(db, reason="entry_submit_exception")
            return self._entry_result(
                cycle,
                reason="entry_submit_exception",
                response={"error": _safe_error(exc)},
                runtime=settings,
            )

        response = sanitize_kis_payload(response or {})
        submitted = bool(
            status_code == 200
            and (
                response.get("real_order_submitted") is True
                or response.get("broker_order_id")
                or response.get("kis_odno")
            )
        )
        cycle.entry_order_id = _int_or_none(
            response.get("order_id") or response.get("order_log_id")
        )
        cycle.entry_broker_order_id = _text_or_none(
            response.get("broker_order_id") or response.get("kis_odno")
        )
        cycle.entry_submitted_at = _naive_utc(now_utc)
        cycle.status = "entry_submitted" if submitted else "failed"
        cycle.last_error = None if submitted else str(
            response.get("reason") or response.get("primary_block_reason") or "entry_submit_blocked"
        )
        cycle.manual_review_required = not submitted
        db.commit()
        if not submitted:
            settings = self._disarm(db, reason="entry_submit_blocked")
            return self._entry_result(
                cycle,
                reason=cycle.last_error or "entry_submit_blocked",
                response=response,
                runtime=settings,
                status_code=status_code,
            )

        order = db.get(OrderLog, cycle.entry_order_id) if cycle.entry_order_id else None
        if order is not None and str(order.internal_status or "").upper() == InternalOrderStatus.FILLED.value:
            promoted = self._promote_filled_entry(db, cycle, order, now=now_utc)
        else:
            cycle.status = "entry_pending"
            db.commit()
            promoted = {"promoted": False, "reason": "entry_pending"}
        if next_session_target and cycle.status in {"entry_pending", "position_open"}:
            self._activate_next_session_position_management(
                db,
                target_trading_date=str(next_session_target),
                session_complete=is_next_session_last_entry_slot(entry_slot),
            )
        return self._entry_result(
            cycle,
            reason="entry_submitted",
            response=response,
            validation=validation,
            promotion=promoted,
            status_code=status_code,
        )

    def reconcile_once(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _aware_utc(now or self.now_provider())
        cycle = self._active_cycle(db)
        if cycle is None:
            return sanitize_kis_payload(
                {
                    "status": "ok",
                    "operation_test": OPERATION_TEST,
                    "result": HOLD,
                    "reason": "no_active_cycle",
                    "cycle": {},
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                }
            )
        sync_result: dict[str, Any] = {}
        if cycle.entry_order_id and cycle.status in {"entry_submitted", "entry_pending"}:
            order = self._sync_order(db, int(cycle.entry_order_id))
            sync_result["entry_order"] = serialize_kis_order(order) if order else None
            if order is None:
                self._review_and_disarm(db, cycle, "entry_order_sync_unavailable")
            else:
                status = str(order.internal_status or "").upper()
                if status == InternalOrderStatus.FILLED.value:
                    sync_result["entry_promotion"] = self._promote_filled_entry(
                        db, cycle, order, now=now_utc
                    )
                elif status in {
                    InternalOrderStatus.REQUESTED.value,
                    InternalOrderStatus.SUBMITTED.value,
                    InternalOrderStatus.ACCEPTED.value,
                    InternalOrderStatus.PENDING.value,
                }:
                    cycle.status = "entry_pending"
                    db.commit()
                elif status == InternalOrderStatus.PARTIALLY_FILLED.value:
                    self._review_and_disarm(db, cycle, "entry_partially_filled")
                elif status in {
                    InternalOrderStatus.REJECTED.value,
                    InternalOrderStatus.CANCELED.value,
                    "CANCELLED",
                    InternalOrderStatus.EXPIRED.value,
                    InternalOrderStatus.FAILED.value,
                }:
                    cycle.status = "failed"
                    cycle.last_error = f"entry_{status.lower()}"
                    db.commit()
                    self._disarm(db, reason=cycle.last_error)
                else:
                    self._review_and_disarm(db, cycle, "entry_order_status_unknown")
        if cycle.exit_order_id and cycle.status == "exit_submitted":
            order = self._sync_order(db, int(cycle.exit_order_id))
            sync_result["exit_order"] = serialize_kis_order(order) if order else None
            if order is None:
                self._review_and_disarm(db, cycle, "exit_order_sync_unavailable")
            else:
                status = str(order.internal_status or "").upper()
                if status == InternalOrderStatus.FILLED.value:
                    sync_result["exit_close"] = self._close_after_exit(
                        db, cycle, order, now=now_utc
                    )
                elif status == InternalOrderStatus.PARTIALLY_FILLED.value:
                    self._review_and_disarm(db, cycle, "exit_partially_filled")
                elif status in {
                    InternalOrderStatus.REJECTED.value,
                    InternalOrderStatus.CANCELED.value,
                    "CANCELLED",
                    InternalOrderStatus.EXPIRED.value,
                    InternalOrderStatus.FAILED.value,
                }:
                    self._review_and_disarm(db, cycle, f"exit_{status.lower()}")
                elif status not in OPEN_ORDER_STATUSES:
                    self._review_and_disarm(db, cycle, "exit_order_status_unknown")
        db.refresh(cycle)
        return sanitize_kis_payload(
            {
                "status": "ok",
                "operation_test": OPERATION_TEST,
                "result": "reconciled",
                "cycle": _serialize_cycle(cycle),
                "sync": sync_result,
                "real_order_submitted": False,
                "broker_submit_called": False,
            }
        )

    def run_active_cycle_once(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _aware_utc(now or self.now_provider())
        cycle = self._active_cycle(db)
        if cycle is None:
            return sanitize_kis_payload(
                {
                    "status": "ok",
                    "operation_test": OPERATION_TEST,
                    "result": HOLD,
                    "reason": "no_active_cycle",
                    "cycle": {},
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                }
            )
        if cycle.status in {"entry_ready", "exit_ready"}:
            recovery_reason = f"{cycle.status}_recovery_required"
            self._review_and_disarm(db, cycle, recovery_reason)
            return self._cycle_result(cycle, reason=recovery_reason)
        if cycle.status in {"entry_submitted", "entry_pending", "exit_submitted"}:
            return self.reconcile_once(db, now=now_utc)
        if cycle.status == "position_open":
            return self._manage_exit(db, cycle, now=now_utc)
        return sanitize_kis_payload(
            {
                "status": "ok",
                "operation_test": OPERATION_TEST,
                "result": HOLD,
                "reason": "no_action_for_active_cycle",
                "cycle": _serialize_cycle(cycle),
                "real_order_submitted": False,
                "broker_submit_called": False,
            }
        )

    def _run_next_session_scheduler_once(
        self,
        db: Session,
        *,
        slot_label: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Evaluate an armed slot and hand BUY_READY to the guarded entry path."""
        now_utc = _aware_utc(now or self.now_provider())
        runtime = self.runtime_settings.get_settings_read_only(db)
        target_date = parse_trading_date(
            runtime.get("operation_test4_target_trading_date")
        )
        if target_date is None:
            self._record_next_session_state(
                db, stage="blocked", error="target_trading_date_unavailable"
            )
            self._disarm(db, reason="target_trading_date_unavailable")
            return self._next_session_result(
                status="blocked", reason="target_trading_date_unavailable", slot_label=slot_label
            )

        local_date = now_utc.astimezone(KR_TZ).date()
        if local_date < target_date:
            return self._next_session_result(
                status="ok",
                reason="waiting_for_target_trading_date",
                slot_label=slot_label,
                target_trading_date=target_date.isoformat(),
            )
        if local_date > target_date:
            self._record_next_session_state(
                db, stage="blocked", error="target_trading_date_expired"
            )
            self._disarm(db, reason="target_trading_date_expired")
            return self._next_session_result(
                status="blocked", reason="target_trading_date_expired", slot_label=slot_label
            )

        cycle = self._active_cycle(db)
        if cycle is not None:
            self._record_next_session_state(
                db, stage="position_management", decision=HOLD, error="active_cycle_exists"
            )
            return self._next_session_result(
                status="ok",
                reason="position_management_only",
                action=HOLD,
                slot_label=slot_label,
            )
        if self._active_lifecycles(db):
            self._record_next_session_state(
                db,
                stage="position_management",
                decision=HOLD,
                error="active_lifecycle_exists",
            )
            return self._next_session_result(
                status="ok",
                reason="position_management_only",
                action=HOLD,
                slot_label=slot_label,
            )
        if not is_next_session_entry_slot(slot_label):
            return self._next_session_result(
                status="ok", reason="no_action_for_scheduler_slot", slot_label=slot_label
            )

        if (
            runtime.get("operation_test4_scheduler_last_evaluated_trade_date")
            == local_date.isoformat()
            and runtime.get("operation_test4_scheduler_last_evaluated_slot_kst")
            == slot_label
        ):
            return self._next_session_result(
                status="ok",
                reason="duplicate_scheduler_tick",
                action=runtime.get("operation_test4_scheduler_last_entry_decision"),
                slot_label=slot_label,
            )

        self._record_next_session_state(
            db,
            stage="account_reconciliation",
            evaluated_date=local_date.isoformat(),
            evaluated_slot=slot_label,
        )
        account = self._read_account_state(require_fresh=True)
        if account.get("fetch_success") is not True:
            self._record_next_session_state(
                db,
                stage="blocked",
                decision=HOLD,
                error="account_state_unavailable",
                evaluated_date=local_date.isoformat(),
                evaluated_slot=slot_label,
            )
            return self._next_session_result(
                status="blocked",
                reason="account_state_unavailable",
                action=HOLD,
                slot_label=slot_label,
                account=self._account_summary(account),
            )
        if account.get("position_count", 0) > 0:
            reason = "position_exists"
            self._record_next_session_state(
                db,
                stage="position_management",
                decision=HOLD,
                error=reason,
                evaluated_date=local_date.isoformat(),
                evaluated_slot=slot_label,
            )
            return self._next_session_result(
                status="ok",
                reason=reason,
                action=HOLD,
                slot_label=slot_label,
                account=self._account_summary(account),
            )
        if account.get("open_order_count", 0) > 0 or self._local_open_order_count(db) > 0:
            reason = "open_order_exists"
            self._record_next_session_state(
                db,
                stage="blocked",
                decision=HOLD,
                error=reason,
                evaluated_date=local_date.isoformat(),
                evaluated_slot=slot_label,
            )
            return self._next_session_result(
                status="blocked",
                reason=reason,
                action=HOLD,
                slot_label=slot_label,
                account=self._account_summary(account),
            )

        runtime = self.runtime_settings.get_settings_read_only(db)
        price_cap = float(
            runtime.get("operation_test4_price_cap_krw", DEFAULT_PRICE_CAP_KRW)
        )
        self._record_next_session_state(
            db,
            stage="watchlist_preparation",
            evaluated_date=local_date.isoformat(),
            evaluated_slot=slot_label,
        )
        watchlist = self._load_watchlist(
            price_cap_krw=price_cap,
            require_fresh=True,
            today_kst=local_date,
        )
        rebuilt = None
        if not self._next_session_watchlist_ready(watchlist):
            rebuilt = self.rebuild_watchlist(
                db, count=DEFAULT_COUNT, price_cap_krw=price_cap, now=now_utc
            )
            if rebuilt.get("status") != "completed":
                reason = str(rebuilt.get("reason") or "watchlist_rebuild_failed")
                self._record_next_session_state(
                    db,
                    stage="blocked",
                    decision=HOLD,
                    error=reason,
                    evaluated_date=local_date.isoformat(),
                    evaluated_slot=slot_label,
                )
                return self._next_session_result(
                    status="blocked",
                    reason=reason,
                    action=HOLD,
                    slot_label=slot_label,
                    watchlist=watchlist,
                    watchlist_rebuild=rebuilt,
                )
            watchlist = self._load_watchlist(
                price_cap_krw=price_cap,
                require_fresh=True,
                today_kst=local_date,
            )
            if not self._next_session_watchlist_ready(watchlist):
                reason = "watchlist_rebuild_not_ready"
                self._record_next_session_state(
                    db,
                    stage="blocked",
                    decision=HOLD,
                    error=reason,
                    evaluated_date=local_date.isoformat(),
                    evaluated_slot=slot_label,
                )
                return self._next_session_result(
                    status="blocked",
                    reason=reason,
                    action=HOLD,
                    slot_label=slot_label,
                    watchlist=watchlist,
                    watchlist_rebuild=rebuilt,
                )

        self._record_next_session_state(
            db,
            stage="heavy_preflight",
            evaluated_date=local_date.isoformat(),
            evaluated_slot=slot_label,
        )
        preflight = self.preflight_once(db, now=now_utc)
        action = str(preflight.get("action") or HOLD)
        if preflight.get("status") != "ready" or action != "BUY_READY":
            reason = str(
                (
                    preflight.get("blocking_reasons")
                    or preflight.get("review_reasons")
                    or ["candidate_gate_blocked"]
                )[0]
            )
            self._record_next_session_state(
                db,
                stage="holding_waiting_next_slot",
                decision=HOLD,
                error=reason if preflight.get("status") == "blocked" else None,
                evaluated_date=local_date.isoformat(),
                evaluated_slot=slot_label,
            )
            if is_next_session_last_entry_slot(slot_label):
                completion = self._complete_next_session(
                    db, target_date=target_date, reason="session_complete"
                )
                return self._next_session_result(
                    status="ok",
                    reason="session_complete",
                    action=HOLD,
                    slot_label=slot_label,
                    preflight=preflight,
                    watchlist=watchlist,
                    watchlist_rebuild=rebuilt,
                    session_completion=completion,
                )
            return self._next_session_result(
                status="ok" if preflight.get("status") != "blocked" else "blocked",
                reason=reason,
                action=HOLD,
                slot_label=slot_label,
                preflight=preflight,
                watchlist=watchlist,
                watchlist_rebuild=rebuilt,
            )

        self._record_next_session_state(
            db,
            stage="buy_ready",
            decision="BUY_READY",
            evaluated_date=local_date.isoformat(),
            evaluated_slot=slot_label,
        )
        try:
            entry = self.entry_run_once(
                db,
                confirm_live=True,
                confirmation=ENTRY_CONFIRMATION,
                now=now_utc,
                trigger_source="operation_test4_scheduler",
                entry_slot_kst=slot_label,
                _preflight=preflight,
                _arm_for_submit=True,
            )
        except Exception as exc:
            reason = "next_session_entry_exception"
            self._record_next_session_state(
                db,
                stage="blocked",
                decision=HOLD,
                error=reason,
                evaluated_date=local_date.isoformat(),
                evaluated_slot=slot_label,
            )
            return self._next_session_result(
                status="blocked",
                reason=reason,
                action=HOLD,
                slot_label=slot_label,
                preflight=preflight,
                watchlist=watchlist,
                watchlist_rebuild=rebuilt,
                entry={"error": _safe_error(exc)},
                submit_path="operation_test4_existing_guarded_entry",
                live_execution_permission=False,
            )

        if entry.get("real_order_submitted") is True:
            self._record_next_session_state(
                db,
                stage="session_complete" if is_next_session_last_entry_slot(slot_label) else "buy_submitted",
                decision="BUY_READY",
                evaluated_date=local_date.isoformat(),
                evaluated_slot=slot_label,
            )
            return sanitize_kis_payload(
                {
                    **entry,
                    "action": "BUY_READY",
                    "slot_label": slot_label,
                    "target_trading_date": target_date.isoformat(),
                    "preflight": preflight,
                    "watchlist": watchlist,
                    "watchlist_rebuild": rebuilt,
                    "entry": entry,
                    "submit_path": "operation_test4_existing_guarded_entry",
                    "live_execution_permission": True,
                    "position_management_only_after_submit": True,
                    "session_complete": is_next_session_last_entry_slot(slot_label),
                }
            )

        reason = str(entry.get("reason") or "entry_submit_blocked")
        self._record_next_session_state(
            db,
            stage="buy_submit_blocked",
            decision=HOLD,
            error=reason,
            evaluated_date=local_date.isoformat(),
            evaluated_slot=slot_label,
        )
        if is_next_session_last_entry_slot(slot_label):
            completion = self._complete_next_session(
                db, target_date=target_date, reason="session_complete"
            )
            return self._next_session_result(
                status="blocked",
                reason=reason,
                action=HOLD,
                slot_label=slot_label,
                preflight=preflight,
                watchlist=watchlist,
                watchlist_rebuild=rebuilt,
                entry=entry,
                session_completion=completion,
                session_complete=True,
                session_completion_reason="session_complete",
                submit_path="operation_test4_existing_guarded_entry",
                live_execution_permission=False,
            )
        return self._next_session_result(
            status="blocked",
            reason=reason,
            action=HOLD,
            slot_label=slot_label,
            preflight=preflight,
            watchlist=watchlist,
            watchlist_rebuild=rebuilt,
            entry=entry,
            submit_path="operation_test4_existing_guarded_entry",
            live_execution_permission=False,
        )

    def _next_session_watchlist_ready(self, watchlist: dict[str, Any]) -> bool:
        return bool(
            watchlist.get("fresh") is True
            and watchlist.get("count") == DEFAULT_COUNT
            and watchlist.get("configured_count", DEFAULT_COUNT) == DEFAULT_COUNT
            and watchlist.get("selected_count") == DEFAULT_COUNT
        )

    def _persist_slot_decision_history(
        self,
        db: Session,
        *,
        result: dict[str, Any],
        slot_label: str,
        now: datetime | None,
    ) -> dict[str, Any]:
        if slot_label not in ENTRY_SLOTS:
            return result
        now_utc = _aware_utc(now or self.now_provider())
        runtime = self.runtime_settings.get_settings_read_only(db)
        trade_date = str(
            result.get("target_trading_date")
            or runtime.get("operation_test4_target_trading_date")
            or now_utc.astimezone(KR_TZ).date().isoformat()
        )
        history = self._build_slot_history_payload(
            result=result,
            trade_date=trade_date,
            slot_label=slot_label,
        )
        run_key = f"operation_test4_{trade_date}_{slot_label.replace(':', '')}"
        row = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.run_key == run_key)
            .filter(TradeRunLog.trigger_source == "operation_test4_scheduler")
            .first()
        )
        candidate_symbol = str(history.get("candidate_symbol") or "WATCHLIST")
        response_payload = sanitize_kis_payload(
            {
                "provider": PROVIDER,
                "market": MARKET,
                "operation_test": OPERATION_TEST,
                "mode": "operation_test4_slot_decision",
                "trigger_source": "operation_test4_scheduler",
                "action": history["action"],
                "result": history["result"],
                "reason": history["reason"],
                "real_order_submitted": history["real_order_submitted"],
                "broker_submit_called": history["broker_submit_called"],
                "slot_history": history,
            }
        )
        if row is None:
            row = TradeRunLog(
                run_key=run_key,
                trigger_source="operation_test4_scheduler",
                symbol=candidate_symbol,
                mode="operation_test4_slot_decision",
            )
            db.add(row)
        row.symbol = candidate_symbol
        row.stage = str(history.get("stage") or "completed")[:20]
        row.result = str(history["result"])[:40]
        row.reason = str(history["reason"] or "")[:500]
        row.request_payload = json.dumps(
            {
                "provider": PROVIDER,
                "market": MARKET,
                "operation_test": OPERATION_TEST,
                "trigger_source": "operation_test4_scheduler",
                "trade_date_kst": trade_date,
                "slot_kst": slot_label,
            },
            ensure_ascii=False,
            default=str,
        )
        row.response_payload = json.dumps(
            response_payload,
            ensure_ascii=False,
            default=str,
        )
        db.commit()
        db.refresh(row)
        result = dict(result)
        result["decision_history_id"] = row.id
        result["decision_history_run_key"] = run_key
        return result

    def _build_slot_history_payload(
        self,
        *,
        result: dict[str, Any],
        trade_date: str,
        slot_label: str,
    ) -> dict[str, Any]:
        preflight = result.get("preflight") if isinstance(result.get("preflight"), dict) else {}
        candidate = preflight.get("candidate") if isinstance(preflight.get("candidate"), dict) else {}
        account = preflight.get("account") if isinstance(preflight.get("account"), dict) else {}
        if not account and isinstance(result.get("account"), dict):
            account = result["account"]
        action = str(result.get("action") or preflight.get("action") or HOLD)
        reason = str(
            result.get("reason")
            or preflight.get("reason")
            or (preflight.get("blocking_reasons") or ["candidate_gate_blocked"])[0]
        )
        submitted = result.get("real_order_submitted") is True
        final_result = (
            "blocked"
            if result.get("status") == "blocked"
            else "buy_ready"
            if action == "BUY_READY"
            else "hold"
        )
        execution = preflight.get("execution") if isinstance(preflight.get("execution"), dict) else {}
        blocking = preflight.get("blocking_reasons") or []
        gating_notes = list(candidate.get("gating_notes") or [])
        gating_notes.extend(str(item) for item in blocking)
        risk_flags = list(candidate.get("risk_flags") or [])
        return {
            "operation_test": OPERATION_TEST,
            "provider": PROVIDER,
            "market": MARKET,
            "trade_date_kst": trade_date,
            "slot_kst": slot_label,
            "trigger_source": "operation_test4_scheduler",
            "run_key": f"operation_test4_{trade_date}_{slot_label.replace(':', '')}",
            "candidate_symbol": candidate.get("symbol"),
            "candidate_rank": candidate.get("rank") or candidate.get("candidate_rank"),
            "candidate_price": candidate.get("current_price") or candidate.get("price"),
            "candidate_name": candidate.get("name"),
            "quant_buy_score": candidate.get("quant_buy_score"),
            "quant_sell_score": candidate.get("quant_sell_score"),
            "ai_buy_score": candidate.get("ai_buy_score"),
            "ai_sell_score": candidate.get("ai_sell_score"),
            "gpt_buy_score": candidate.get("gpt_buy_score") or candidate.get("ai_buy_score"),
            "gpt_sell_score": candidate.get("gpt_sell_score") or candidate.get("ai_sell_score"),
            "confidence": candidate.get("confidence") or candidate.get("gpt_confidence"),
            "final_buy_score": candidate.get("final_buy_score"),
            "final_sell_score": candidate.get("final_sell_score"),
            "effective_min_entry_score": candidate.get("effective_min_entry_score")
            or getattr(get_settings(), "watchlist_min_entry_score", 65),
            "required_entry_score": candidate.get("required_entry_score")
            or getattr(get_settings(), "watchlist_min_entry_score", 65),
            "final_score_gap": candidate.get("final_score_gap") or preflight.get("final_score_gap"),
            "entry_ready": bool(execution.get("trade_ready") or action == "BUY_READY"),
            "trade_allowed": bool(execution.get("trade_ready") or action == "BUY_READY"),
            "should_trade": bool(execution.get("trade_ready") or action == "BUY_READY"),
            "action": action,
            "result": final_result,
            "reason": reason,
            "block_reason": reason if final_result == "blocked" or action == HOLD else None,
            "risk_flags": _dedupe([str(item) for item in risk_flags]),
            "gating_notes": _dedupe([str(item) for item in gating_notes]),
            "hard_block": bool(candidate.get("hard_block") or candidate.get("hard_block_reason")),
            "stage": result.get("stage") or result.get("last_stage") or (
                "buy_submitted" if submitted else "blocked" if final_result == "blocked" else "holding_waiting_next_slot"
            ),
            "account_state_status": account.get("account_state_status", "unavailable"),
            "account_state_failed_component": account.get("account_state_failed_component"),
            "account_state_attempt_count": account.get("account_state_attempt_count", 0),
            "account_state_retryable": account.get("account_state_retryable", False),
            "account_state_error_category": account.get("account_state_error_category"),
            "account_state_error_code": account.get("account_state_error_code"),
            "account_state_http_status": account.get("account_state_http_status"),
            "account_state_last_checked_at": account.get("account_state_last_checked_at"),
            "real_order_submitted": submitted,
            "broker_submit_called": result.get("broker_submit_called") is True,
            "order_id": result.get("order_id"),
            "broker_order_id": result.get("broker_order_id"),
        }

    def _record_next_session_state(
        self,
        db: Session,
        *,
        stage: str | None = None,
        decision: str | None = None,
        error: str | None = None,
        evaluated_date: str | None = None,
        evaluated_slot: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {}
        if stage is not None:
            payload["operation_test4_scheduler_last_stage"] = stage
        if decision is not None:
            payload["operation_test4_scheduler_last_entry_decision"] = decision
        if error is not None:
            payload["operation_test4_scheduler_last_error"] = error
        elif stage in {
            "armed",
            "account_reconciliation",
            "watchlist_preparation",
            "heavy_preflight",
            "buy_ready",
            "buy_submitted",
            "holding_waiting_next_slot",
            "position_management",
        }:
            payload["operation_test4_scheduler_last_error"] = None
        if evaluated_date is not None:
            payload["operation_test4_scheduler_last_evaluated_trade_date"] = evaluated_date
        if evaluated_slot is not None:
            payload["operation_test4_scheduler_last_evaluated_slot_kst"] = evaluated_slot
        if payload:
            self.runtime_settings.update_settings(db, payload)

    def _activate_next_session_position_management(
        self,
        db: Session,
        *,
        target_trading_date: str,
        session_complete: bool = False,
    ) -> dict[str, Any]:
        """Keep the armed session alive while the guarded cycle is managed."""
        settings = self.runtime_settings.update_settings(
            db,
            {
                "operation_test4_scheduler_enabled": True,
                "operation_test4_scheduler_arm_mode": "active_cycle",
                "operation_test4_target_trading_date": target_trading_date,
                "operation_test4_scheduler_last_stage": "session_complete" if session_complete else "buy_submitted",
                "operation_test4_scheduler_last_entry_decision": "BUY_READY",
                "operation_test4_scheduler_last_error": None,
            },
        )
        return self._runtime_snapshot(settings)
    def _complete_next_session(
        self,
        db: Session,
        *,
        target_date: date,
        reason: str,
    ) -> dict[str, Any]:
        settings = self.runtime_settings.update_settings(
            db,
            {
                "dry_run": True,
                "kill_switch": True,
                "operation_test4_enabled": False,
                "operation_test4_scheduler_enabled": False,
                "operation_test4_allow_real_entry": False,
                "operation_test4_allow_real_exit": False,
                "operation_test4_entry_enabled": False,
                "operation_test4_position_management_enabled": False,
                "operation_test4_stop_loss_enabled": False,
                "operation_test4_take_profit_enabled": False,
                "operation_test4_scheduler_arm_mode": "session_complete",
                "operation_test4_target_trading_date": target_date.isoformat(),
                "operation_test4_scheduler_last_stage": reason,
                "operation_test4_scheduler_last_error": None,
            },
        )
        return self._runtime_snapshot(settings)

    def _next_session_result(
        self,
        *,
        status: str,
        reason: str,
        action: str | None = None,
        slot_label: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        return sanitize_kis_payload(
            {
                "status": status,
                "operation_test": OPERATION_TEST,
                "result": action or reason,
                "action": action,
                "reason": reason,
                "slot_label": slot_label,
                "real_order_submitted": False,
                "broker_submit_called": False,
                **extra,
            }
        )

    def run_scheduler_once(
        self,
        db: Session,
        *,
        slot_label: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if slot_label not in ALL_SLOTS:
            return sanitize_kis_payload(
                {"status": "blocked", "reason": "invalid_scheduler_slot", "slot_label": slot_label}
            )
        runtime = self.runtime_settings.get_settings_read_only(db)
        if (
            runtime.get("operation_test4_scheduler_enabled") is True
            and runtime.get("operation_test4_scheduler_arm_mode") == "next_session"
        ):
            cycle = self._active_cycle(db)
            if cycle is not None:
                return self.run_active_cycle_once(db, now=now)
            result = self._run_next_session_scheduler_once(
                db, slot_label=slot_label, now=now
            )
            with _ENTRY_SUBMIT_LOCK:
                return self._persist_slot_decision_history(
                    db,
                    result=result,
                    slot_label=slot_label,
                    now=now,
                )
        cycle = self._active_cycle(db)
        if cycle is not None:
            return self.run_active_cycle_once(db, now=now)
        if slot_label in ENTRY_SLOTS:
            return self.entry_run_once(
                db,
                confirm_live=True,
                confirmation=ENTRY_CONFIRMATION,
                now=now,
                trigger_source="operation_test4_scheduler",
                entry_slot_kst=slot_label,
            )
        return sanitize_kis_payload(
            {
                "status": "ok",
                "operation_test": OPERATION_TEST,
                "result": HOLD,
                "reason": "no_action_for_scheduler_slot",
                "slot_label": slot_label,
                "cycle": _serialize_cycle(cycle) if cycle else {},
                "real_order_submitted": False,
                "broker_submit_called": False,
            }
        )

    def _manage_exit(
        self,
        db: Session,
        cycle: OperationTest4Cycle,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        lifecycle = db.get(PositionLifecycle, cycle.lifecycle_id) if cycle.lifecycle_id else None
        if lifecycle is None or lifecycle.status not in {"open", "closing"}:
            self._review_and_disarm(db, cycle, "lifecycle_missing_or_closed")
            return self._cycle_result(cycle, reason="lifecycle_missing_or_closed")
        account = self._read_account_state(require_fresh=True)
        position = _find_position(account.get("positions") or [], lifecycle.symbol)
        if position is None:
            self._review_and_disarm(db, cycle, "broker_position_missing")
            return self._cycle_result(cycle, reason="broker_position_missing")
        current_price = _number(
            position.get("current_price") or position.get("price") or position.get("stck_prpr")
        )
        entry_price = _number(lifecycle.entry_price)
        if current_price <= 0 or entry_price <= 0:
            self._review_and_disarm(db, cycle, "current_price_unavailable")
            return self._cycle_result(cycle, reason="current_price_unavailable")
        pl_pct = (current_price - entry_price) / entry_price * 100.0
        stop_triggered = bool(
            lifecycle.stop_loss_threshold_pct is not None
            and pl_pct <= -abs(float(lifecycle.stop_loss_threshold_pct))
        )
        take_triggered = bool(
            lifecycle.take_profit_threshold_pct is not None
            and pl_pct >= abs(float(lifecycle.take_profit_threshold_pct))
        )
        runtime = self.runtime_settings.get_settings_read_only(db)
        if not runtime.get("operation_test4_stop_loss_enabled", True):
            stop_triggered = False
        if not runtime.get("operation_test4_take_profit_enabled", True):
            take_triggered = False
        reason = STOP_LOSS_READY if stop_triggered else TAKE_PROFIT_READY if take_triggered else HOLD
        if reason == HOLD:
            lifecycle.last_price = current_price
            lifecycle.last_evaluated_at = _naive_utc(now)
            db.commit()
            return self._cycle_result(cycle, reason=HOLD, current_price=current_price)
        if account.get("open_order_count") != 0 or self._local_open_sell(db, lifecycle.symbol):
            self._review_and_disarm(db, cycle, "duplicate_open_sell_order")
            return self._cycle_result(cycle, reason="duplicate_open_sell_order")
        if self._daily_order_count(db, side="sell", now_utc=now) >= int(
            runtime.get("operation_test4_max_sell_orders_per_day", 3) or 3
        ):
            return self._cycle_result(cycle, reason="daily_sell_limit_reached", current_price=current_price)
        exit_reason = "stop_loss_triggered" if stop_triggered else "take_profit_triggered"
        claim = self._claim_exit_submission(db, cycle=cycle, exit_reason=exit_reason)
        if claim == "unavailable":
            self._review_and_disarm(db, cycle, "exit_claim_unavailable")
            return self._cycle_result(cycle, reason="exit_claim_unavailable")
        if claim != "claimed":
            db.refresh(cycle)
            return self._cycle_result(
                cycle,
                reason="exit_claimed_elsewhere",
                current_price=current_price,
            )
        try:
            service = self._limited_sell_service()
            response = sanitize_kis_payload(service.run_once(db, now=now))
        except Exception as exc:
            self._review_and_disarm(db, cycle, "exit_submit_exception", error=_safe_error(exc))
            return self._cycle_result(cycle, reason="exit_submit_exception")
        submitted = response.get("real_order_submitted") is True
        order_id = _int_or_none(response.get("order_id") or response.get("order_log_id"))
        if submitted:
            cycle.status = "exit_submitted"
            cycle.exit_order_id = order_id
            cycle.exit_reason = "stop_loss_triggered" if stop_triggered else "take_profit_triggered"
            db.commit()
            order = db.get(OrderLog, order_id) if order_id else None
            if order is not None and str(order.internal_status or "").upper() == InternalOrderStatus.FILLED.value:
                close_result = self._close_after_exit(db, cycle, order, now=now)
            else:
                close_result = {"closed": False, "reason": "exit_pending"}
            return self._cycle_result(
                cycle,
                reason=cycle.exit_reason or "exit_submitted",
                response=response,
                close=close_result,
                current_price=current_price,
            )
        self._review_and_disarm(
            db,
            cycle,
            str(response.get("reason") or "exit_submit_blocked"),
        )
        return self._cycle_result(cycle, reason=cycle.last_error or "exit_submit_blocked", response=response)

    def _candidate_snapshot(
        self,
        db: Session,
        *,
        account: dict[str, Any],
        runtime: dict[str, Any],
        now: datetime,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        _preflight_progress_update(stage="gpt_analysis")
        if self.candidate_provider is not None:
            preview = self.candidate_provider(db=db, now=now, read_only=True)
        else:
            try:
                preview = self.preview_service.run_preview(
                    include_gpt=True,
                    gate_level=2,
                    db=db,
                    record_run=False,
                    trigger_source="operation_test4_preflight",
                )
            except TypeError:
                preview = self.preview_service.run_preview(
                    include_gpt=True,
                    gate_level=2,
                    db=db,
                )
            except Exception as exc:
                preview = {"preview_error": _safe_error(exc), "final_ranked_candidates": []}
        preview = preview if isinstance(preview, dict) else {}
        candidates = preview.get("final_ranked_candidates") or preview.get("top_quant_candidates") or []
        if not isinstance(candidates, list):
            candidates = []
        _preflight_progress_update(stage="candidate_selection")
        selected: dict[str, Any] = {}
        fallback: dict[str, Any] = {}
        price_cap = _number(runtime.get("operation_test4_price_cap_krw") or DEFAULT_PRICE_CAP_KRW)
        for raw in candidates:
            if not isinstance(raw, dict):
                continue
            symbol = str(raw.get("symbol") or "").strip()
            if not symbol:
                continue
            if not fallback:
                fallback = dict(raw)
            candidate_price = _number(
                raw.get("current_price") or raw.get("price") or raw.get("stck_prpr")
            )
            if 0 < candidate_price < price_cap:
                selected = dict(raw)
                break
        if not selected:
            selected = fallback
        if not selected:
            return preview, {}

        symbol = str(selected.get("symbol") or "").strip()
        if not symbol:
            return preview, {}

        current_price = _number(
            selected.get("current_price")
            or selected.get("price")
            or selected.get("stck_prpr")
        )

        _preflight_progress_update(stage="possible_order")
        possible_order = self._possible_order(
            symbol=symbol,
            current_price=current_price,
        )
        possible_cash = _number_or_none(possible_order.get("orderable_cash"))
        possible_quantity = _int_or_none(possible_order.get("orderable_quantity"))
        score = _number_or_none(
            selected.get("final_buy_score")
            or selected.get("final_entry_score")
            or selected.get("score")
        )
        block_reasons = _candidate_block_reasons(
            selected,
            score=score,
            min_score=float(getattr(get_settings(), "watchlist_min_entry_score", 65)),
            score_gap=preview.get("final_score_gap"),
            min_score_gap=float(getattr(get_settings(), "watchlist_min_score_gap", 0)),
        )
        if possible_order.get("raw_status") != "ok":
            block_reasons.append("possible_order_unavailable")
        if possible_cash is None:
            block_reasons.append("orderable_cash_unavailable")
        if possible_quantity is None or possible_quantity <= 0:
            block_reasons.append("orderable_quantity_unavailable")
        sizing = calculate_operation_test4_sizing(
            equity=_number(account.get("equity")),
            orderable_cash=possible_cash or 0.0,
            current_price=current_price,
            min_position_pct=float(runtime.get("operation_test4_min_position_pct", 10.0)),
            max_position_pct=float(runtime.get("operation_test4_max_position_pct", 100.0)),
            max_order_notional_krw=float(runtime.get("operation_test4_max_order_notional_krw", 1_000_000.0)),
            price_cap_krw=float(runtime.get("operation_test4_price_cap_krw", 1_000_000.0)),
            broker_orderable_qty=possible_quantity,
            allow_single_share_budget_bump=bool(
                runtime.get("operation_test4_allow_single_share_budget_bump", True)
            ),
        )
        if not sizing.allowed:
            block_reasons.append(str(sizing.reason or "sizing_blocked"))
        block_reasons = _dedupe(block_reasons)
        raw_preview_reasons = [
            str(reason)
            for reason in selected.get("block_reasons") or []
            if str(reason) in {"preview_only", "kr_trading_disabled", "trading_disabled"}
        ]
        preview_display = {
            "preview_only": bool(selected.get("preview_only")) or "preview_only" in raw_preview_reasons,
            "kr_trading_disabled": bool(selected.get("kr_trading_disabled"))
            or "kr_trading_disabled" in raw_preview_reasons,
            "trading_enabled": selected.get("trading_enabled"),
            "next_manual_action_hint": selected.get("next_manual_action_hint"),
        }
        selected.update(
            {
                "symbol": symbol,
                "current_price": current_price or None,
                "final_buy_score": score,
                "block_reasons": block_reasons,
                "test4_block_reasons": block_reasons,
                "analysis_mode": "operation_test4_heavy_preflight",
                "execution_decision": "BUY_READY" if not block_reasons else HOLD,
                "preview_display": preview_display,
                "risk_flags": selected.get("risk_flags") or [],
                "equity": account.get("equity"),
                "cash": account.get("cash"),
                "withdrawable_cash": account.get("withdrawable_cash"),
                "d1_cash": account.get("d1_cash"),
                "d2_cash": account.get("d2_cash"),
                "orderable_cash": possible_cash,
                "orderable_quantity": possible_quantity,
                "possible_order": possible_order,
                "quantity": sizing.quantity,
                "estimated_notional": sizing.estimated_notional,
                "effective_position_pct": sizing.effective_position_pct,
                "sizing": {
                    **sizing.as_dict(),
                    "min_position_pct": runtime.get("operation_test4_min_position_pct", 10.0),
                    "max_position_pct": runtime.get("operation_test4_max_position_pct", 100.0),
                    "price_cap_krw": runtime.get("operation_test4_price_cap_krw", 1_000_000.0),
                    "max_order_notional_krw": runtime.get("operation_test4_max_order_notional_krw", 1_000_000.0),
                },
            }
        )
        _preflight_progress_update(
            analyzed_count=_int_or_none(preview.get("analyzed_symbol_count")) or 0,
            total_count=_int_or_none(preview.get("configured_symbol_count")) or 0,
            stage="final_decision",
        )
        return preview, selected

    def _possible_order(
        self,
        *,
        symbol: str,
        current_price: float,
    ) -> dict[str, Any]:
        try:
            if self.possible_order_provider is not None:
                result = self.possible_order_provider(
                    symbol=symbol,
                    order_type="market",
                    order_price=current_price,
                    side="buy",
                    market=MARKET,
                )
            else:
                result = self.client.get_domestic_possible_order(
                    symbol=symbol,
                    order_type="market",
                    order_price=current_price,
                    side="buy",
                    market=MARKET,
                )
        except Exception as exc:
            return {
                "raw_status": "error",
                "symbol": symbol,
                "order_type": "market",
                "reference_price": current_price,
                "orderable_cash": None,
                "orderable_quantity": None,
                "error": _safe_error(exc),
            }
        return result if isinstance(result, dict) else {
            "raw_status": "error",
            "symbol": symbol,
            "reference_price": current_price,
            "orderable_cash": None,
            "orderable_quantity": None,
            "error": "possible_order_invalid_response",
        }

    def _current_price(self, *, symbol: str, fallback: float) -> float | None:
        try:
            if self.price_provider is not None:
                payload = self.price_provider(symbol=symbol)
            else:
                reader = getattr(self.client, "get_domestic_stock_price", None)
                if not callable(reader):
                    return fallback if fallback > 0 else None
                payload = reader(symbol)
            if not isinstance(payload, dict):
                return None
            return _number_or_none(
                payload.get("current_price")
                or payload.get("price")
                or payload.get("stck_prpr")
            )
        except Exception:
            return None

    def _validate_entry(
        self,
        db: Session,
        *,
        symbol: str,
        quantity: int,
        now: datetime,
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        request = KisOrderValidationRequest(
            market=MARKET,
            symbol=symbol,
            side="buy",
            qty=quantity,
            order_type="market",
            dry_run=True,
            reason="Operation Test 4 automated entry validation",
            source_metadata={
                "source": "operation_test4_auto_entry",
                "source_type": "operation_test4_auto_entry",
                "source_endpoint": ENTRY_ENDPOINT,
                "order_source": "operation_test4_auto_entry",
                "operation_test": OPERATION_TEST,
                "mode": MODE,
                "source_context": "operation_test4_run_once",
                "final_score": candidate.get("final_buy_score"),
            },
        )
        try:
            validator = getattr(self, "validation_service", None) or KisOrderValidationService(
                self.client,
                session_service=self.session_service,
            )
            result = validator.validate(request, now=now)
            summary = result.to_dict() if hasattr(result, "to_dict") else dict(result)
            row = record_kis_order_validation(db, request=request, result=result)
            summary["validation_id"] = row.id
        except Exception as exc:
            return {"valid": False, "reason": "validation_failed", "error": _safe_error(exc)}
        valid = bool(
            getattr(result, "validated_for_submission", summary.get("validated_for_submission"))
        )
        return {
            "valid": valid,
            "reason": None if valid else "validation_failed",
            "summary": sanitize_kis_payload(summary),
        }

    def _promote_filled_entry(
        self,
        db: Session,
        cycle: OperationTest4Cycle,
        order: OrderLog,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        status = str(order.internal_status or "").upper()
        if status != InternalOrderStatus.FILLED.value:
            return {"promoted": False, "reason": "entry_not_filled"}
        filled_qty = _number(order.filled_qty or order.qty)
        average_price = _number(order.avg_fill_price or order.filled_avg_price)
        if filled_qty <= 0 or average_price <= 0:
            self._review_and_disarm(db, cycle, "filled_entry_data_unavailable")
            return {"promoted": False, "reason": "filled_entry_data_unavailable"}
        lifecycle_service = self.lifecycle_service or KisPositionLifecycleService(
            self.client,
            runtime_settings=self.runtime_settings,
            limited_auto_sell_service=self._limited_sell_service(),
        )
        try:
            result = lifecycle_service.sync_filled_buy(db, order, now=now)
        except Exception as exc:
            self._review_and_disarm(db, cycle, "lifecycle_creation_failed", error=_safe_error(exc))
            return {"promoted": False, "reason": "lifecycle_creation_failed"}
        lifecycle_payload = result.get("lifecycle") if isinstance(result, dict) else None
        lifecycle_id = _int_or_none(
            lifecycle_payload.get("id") if isinstance(lifecycle_payload, dict) else None
        )
        if lifecycle_id is None:
            self._review_and_disarm(
                db,
                cycle,
                str(result.get("reason") or "lifecycle_creation_failed"),
            )
            return {"promoted": False, "reason": result.get("reason")}
        cycle.entry_filled_quantity = filled_qty
        cycle.entry_average_fill_price = average_price
        cycle.entry_filled_at = _naive_utc(order.filled_at or now)
        cycle.lifecycle_id = lifecycle_id
        cycle.status = "position_open"
        cycle.last_error = None
        cycle.manual_review_required = False
        db.commit()
        self._lock_after_fill(db)
        db.refresh(cycle)
        return {"promoted": True, "reason": "position_open", "lifecycle_id": lifecycle_id}

    def _close_after_exit(
        self,
        db: Session,
        cycle: OperationTest4Cycle,
        order: OrderLog,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        account = self._read_account_state(require_fresh=True)
        lifecycle = db.get(PositionLifecycle, cycle.lifecycle_id) if cycle.lifecycle_id else None
        if account.get("fetch_success") is not True:
            self._review_and_disarm(db, cycle, "post_exit_position_sync_unavailable")
            return {"closed": False, "reason": "post_exit_position_sync_unavailable"}
        if lifecycle is not None:
            lifecycle.exit_order_id = order.id
            lifecycle.exit_order_status = InternalOrderStatus.FILLED.value
            lifecycle.exit_reason = cycle.exit_reason or lifecycle.exit_reason
            lifecycle.last_evaluated_at = _naive_utc(now)
            if account.get("position_count") == 0:
                lifecycle.status = "closed"
                lifecycle.closed_at = _naive_utc(now)
            else:
                self._review_and_disarm(db, cycle, "position_remains_after_exit_fill")
                return {"closed": False, "reason": "position_remains_after_exit_fill"}
        if account.get("open_order_count") != 0:
            self._review_and_disarm(db, cycle, "open_order_remains_after_exit_fill")
            return {"closed": False, "reason": "open_order_remains_after_exit_fill"}
        cycle.exit_order_id = order.id
        cycle.status = "completed"
        cycle.completed_at = _naive_utc(now)
        cycle.manual_review_required = False
        db.commit()
        runtime_before_close = self.runtime_settings.get_settings_read_only(db)
        target_date = parse_trading_date(
            runtime_before_close.get("operation_test4_target_trading_date")
        )
        preserve_next_session = bool(
            target_date is not None
            and runtime_before_close.get("operation_test4_scheduler_arm_mode")
            in {"next_session", "active_cycle"}
        )
        if preserve_next_session and runtime_before_close.get(
            "operation_test4_scheduler_last_evaluated_slot_kst"
        ) == "13:30":
            settings = self._complete_next_session(
                db, target_date=target_date, reason="session_complete"
            )
            close_reason = "session_complete"
        else:
            settings = self._disarm(
                db,
                reason="cycle_completed",
                preserve_next_session=preserve_next_session,
            )
            close_reason = "cycle_completed"
        return {
            "closed": True,
            "reason": close_reason,
            "runtime": self._runtime_snapshot(settings),
        }

    def _limited_sell_service(self) -> Any:
        if self.limited_auto_sell_service is not None:
            return self.limited_auto_sell_service
        self.limited_auto_sell_service = KisLimitedAutoSellService(
            self.client,
            runtime_settings=self.runtime_settings,
            operation_test4_mode=True,
            operation_test4_source_context="operation_test4_position_management",
        )
        return self.limited_auto_sell_service

    def _claim_exit_submission(
        self,
        db: Session,
        *,
        cycle: OperationTest4Cycle,
        exit_reason: str,
    ) -> str:
        """Atomically move one open cycle into the guarded sell-submit state."""
        try:
            claimed = (
                db.query(OperationTest4Cycle)
                .filter(OperationTest4Cycle.id == cycle.id)
                .filter(OperationTest4Cycle.status == "position_open")
                .update(
                    {
                        "status": "exit_ready",
                        "exit_reason": exit_reason,
                    },
                    synchronize_session=False,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            return "unavailable"
        if claimed != 1:
            return "already_claimed"
        db.refresh(cycle)
        return "claimed"

    def _create_entry_cycle(
        self,
        db: Session,
        *,
        candidate: dict[str, Any],
        sizing: dict[str, Any],
        now: datetime,
        trigger_source: str,
    ) -> OperationTest4Cycle:
        now_kst = now.astimezone(KR_TZ)
        cycle = OperationTest4Cycle(
            cycle_key=f"operation_test4_{now_kst.strftime('%Y%m%d')}_{uuid.uuid4().hex[:12]}",
            operation_test=OPERATION_TEST,
            provider=PROVIDER,
            market=MARKET,
            symbol=str(candidate.get("symbol") or ""),
            status="entry_ready",
            entry_trigger_source=trigger_source,
            min_position_pct=float(sizing.get("min_position_pct") or 10.0),
            max_position_pct=float(sizing.get("max_position_pct") or 100.0),
            price_cap_krw=float(sizing.get("price_cap_krw") or 1_000_000.0),
            max_order_notional_krw=float(
                sizing.get("max_order_notional_krw") or 1_000_000.0
            ),
            equity_at_entry=_number(candidate.get("equity")),
            orderable_cash_at_entry=_number(candidate.get("orderable_cash")),
            estimated_entry_price=_number(candidate.get("current_price")),
            requested_quantity=int(sizing.get("quantity") or 0),
            estimated_notional=_number(sizing.get("estimated_notional")),
            effective_position_pct=_number(sizing.get("effective_position_pct")),
            started_at=_naive_utc(now),
        )
        db.add(cycle)
        db.commit()
        db.refresh(cycle)
        return cycle

    def _reserve_entry_submission(
        self,
        db: Session,
        *,
        now: datetime,
        entry_slot_kst: str,
    ) -> OperationTest4EntryReservation | None:
        reservation = OperationTest4EntryReservation(
            trade_date_kst=now.astimezone(KR_TZ).date().isoformat(),
            entry_slot_kst=entry_slot_kst,
            reservation_token=uuid.uuid4().hex,
        )
        db.add(reservation)
        try:
            db.commit()
        except IntegrityError:
            # A unique KST-day/slot claim already exists (or persistence is
            # unsafe). Either case is fail-closed for this entry slot.
            db.rollback()
            return None
        db.refresh(reservation)
        return reservation

    def _bind_entry_reservation(
        self,
        db: Session,
        *,
        reservation: OperationTest4EntryReservation,
        cycle: OperationTest4Cycle,
    ) -> None:
        reservation.cycle_id = cycle.id
        db.commit()

    def _mark_entry_reservation_submission_attempted(
        self,
        db: Session,
        *,
        reservation: OperationTest4EntryReservation,
    ) -> None:
        reservation.submission_attempted = True
        db.commit()

    def _start_idempotency_blockers(
        self,
        db: Session,
        *,
        now: datetime,
    ) -> list[str]:
        blockers: list[str] = []
        if self._active_cycle(db) is not None:
            blockers.append("active_cycle_exists")
        if self._active_lifecycles(db):
            blockers.append("active_lifecycle_exists")
        account = self._read_account_state(require_fresh=True)
        if account.get("fetch_success") is not True:
            blockers.append("account_state_unavailable")
        else:
            if account.get("position_count") != 0:
                blockers.append("position_exists")
            if account.get("open_order_count") != 0:
                blockers.append("open_order_exists")
        if self._local_open_order_count(db) != 0:
            blockers.append("local_open_order_exists")
        runtime = self.runtime_settings.get_settings_read_only(db)
        daily_buy_limit = int(runtime.get("operation_test4_max_buy_orders_per_day", 3) or 3)
        if self._daily_order_count(db, side="buy", now_utc=now) >= daily_buy_limit:
            blockers.append("daily_buy_limit_reached")
        return _dedupe(blockers)

    def _entry_submission_blockers(
        self,
        db: Session,
        *,
        now: datetime,
        require_live: bool,
        allowed_cycle_id: int | None = None,
    ) -> list[str]:
        runtime = self.runtime_settings.get_settings_read_only(db)
        account = self._read_account_state(require_fresh=True)
        market_session = self._market_session(now)
        now_kst = now.astimezone(KR_TZ)
        blockers: list[str] = []
        settings = self.client.settings
        if now_kst.time() < time(9, 0) or now_kst.time() >= time(14, 0):
            blockers.append("entry_time_outside_window")
        if market_session.get("is_market_open") is not True:
            blockers.append("market_closed")
        if market_session.get("is_entry_allowed_now") is not True:
            blockers.append("market_entry_not_allowed")
        if not _is_kis_prod(settings):
            blockers.append("kis_prod_required")
        if not bool(getattr(settings, "kis_enabled", False)):
            blockers.append("kis_disabled")
        if not bool(getattr(settings, "kis_real_order_enabled", False)):
            blockers.append("kis_real_order_disabled")
        if account.get("fetch_success") is not True:
            blockers.append("account_state_unavailable")
        if account.get("position_count") != 0:
            blockers.append("position_exists")
        if account.get("open_order_count") != 0:
            blockers.append("open_order_exists")
        if self._local_open_order_count(db) != 0:
            blockers.append("local_open_order_exists")
        if self._active_lifecycles(db):
            blockers.append("active_lifecycle_exists")
        active_cycles = (
            db.query(OperationTest4Cycle)
            .filter(OperationTest4Cycle.status.in_(ACTIVE_CYCLE_STATUSES))
            .all()
        )
        if any(cycle.id != allowed_cycle_id for cycle in active_cycles):
            blockers.append("active_cycle_exists")
        daily_buy_limit = int(runtime.get("operation_test4_max_buy_orders_per_day", 3) or 3)
        if self._daily_order_count(db, side="buy", now_utc=now) >= daily_buy_limit:
            blockers.append("daily_buy_limit_reached")
        enabled_buy_flags = [key for key in BUY_FLAGS if runtime.get(key) is True]
        if enabled_buy_flags:
            blockers.append("other_buy_flags_enabled")
        test3_flags = (
            "operation_test3_enabled",
            "operation_test3_scheduler_enabled",
            "operation_test3_allow_real_orders",
            "operation_test3_position_management_enabled",
        )
        if any(runtime.get(key) is True for key in test3_flags):
            blockers.append("operation_test3_live_flags_enabled")
        enabled_other_scheduler_flags = [
            key
            for key in OTHER_SCHEDULER_LIVE_FLAGS
            if runtime.get(key) is True
        ]
        if enabled_other_scheduler_flags:
            blockers.append("other_scheduler_live_flags_enabled")
        if require_live:
            required_flags = (
                "operation_test4_enabled",
                "operation_test4_scheduler_enabled",
                "operation_test4_allow_real_entry",
                "operation_test4_entry_enabled",
            )
            if any(runtime.get(key) is not True for key in required_flags):
                blockers.append("operation_test4_live_arm_incomplete")
            if runtime.get("dry_run") is not False:
                blockers.append("dry_run_true")
            if runtime.get("kill_switch") is not False:
                blockers.append("kill_switch_enabled")
        return _dedupe(blockers)

    def _refresh_candidate_for_submit(
        self,
        candidate: dict[str, Any],
        *,
        runtime: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        symbol = str(candidate.get("symbol") or "").strip()
        fresh_price = self._current_price(
            symbol=symbol,
            fallback=_number(candidate.get("current_price")),
        )
        if not symbol or fresh_price is None or fresh_price <= 0:
            return candidate, "current_price_unavailable"
        price_cap = float(
            runtime.get("operation_test4_price_cap_krw", DEFAULT_PRICE_CAP_KRW)
        )
        if fresh_price >= price_cap:
            return candidate, "price_cap_exceeded"
        possible_order = self._possible_order(
            symbol=symbol,
            current_price=fresh_price,
        )
        if possible_order.get("raw_status") != "ok":
            return candidate, str(
                possible_order.get("error") or "possible_order_unavailable"
            )
        orderable_cash = _number_or_none(possible_order.get("orderable_cash"))
        orderable_quantity = _int_or_none(possible_order.get("orderable_quantity"))
        if orderable_cash is None or orderable_quantity is None:
            return candidate, "possible_order_unavailable"
        sizing = calculate_operation_test4_sizing(
            equity=_number(candidate.get("equity")),
            orderable_cash=orderable_cash,
            current_price=fresh_price,
            min_position_pct=float(runtime.get("operation_test4_min_position_pct", 10.0)),
            max_position_pct=float(runtime.get("operation_test4_max_position_pct", 100.0)),
            max_order_notional_krw=float(
                runtime.get("operation_test4_max_order_notional_krw", 1_000_000.0)
            ),
            price_cap_krw=price_cap,
            broker_orderable_qty=orderable_quantity,
            allow_single_share_budget_bump=bool(
                runtime.get("operation_test4_allow_single_share_budget_bump", True)
            ),
        )
        if not sizing.allowed:
            return candidate, str(sizing.reason or "sizing_blocked")
        return {
            **candidate,
            "current_price": fresh_price,
            "orderable_cash": orderable_cash,
            "orderable_quantity": orderable_quantity,
            "possible_order": possible_order,
            "sizing": {
                **sizing.as_dict(),
                "min_position_pct": runtime.get("operation_test4_min_position_pct", 10.0),
                "max_position_pct": runtime.get("operation_test4_max_position_pct", 100.0),
                "price_cap_krw": runtime.get("operation_test4_price_cap_krw", 1_000_000.0),
                "max_order_notional_krw": runtime.get(
                    "operation_test4_max_order_notional_krw", 1_000_000.0
                ),
            },
        }, None

    def _manual_submit(
        self,
        db: Session,
        request: KisManualOrderSubmitRequest,
        now: datetime,
    ) -> tuple[int, dict[str, Any]]:
        service = self.manual_order_service or KisManualOrderService(
            self.client,
            session_service=self.session_service,
            runtime_settings=self.runtime_settings,
        )
        return service.submit_manual(db, request, now=now)

    def _sync_order(self, db: Session, order_id: int) -> OrderLog | None:
        try:
            service = self.order_sync_service or KisOrderSyncService(self.client)
            return service.sync_order(db, order_id)
        except Exception:
            return db.get(OrderLog, order_id)

    def _lock_after_fill(self, db: Session) -> None:
        self.runtime_settings.update_settings(
            db,
            {
                "operation_test4_allow_real_entry": False,
                "operation_test4_entry_enabled": False,
                "operation_test4_allow_real_exit": True,
                "operation_test4_position_management_enabled": True,
                **{key: False for key in BUY_FLAGS},
            },
        )

    def _review_and_disarm(
        self,
        db: Session,
        cycle: OperationTest4Cycle,
        reason: str,
        *,
        error: str | None = None,
    ) -> None:
        cycle.status = "review_required"
        cycle.manual_review_required = True
        cycle.last_error = error or reason
        db.commit()
        self._disarm(db, reason=reason)

    def _disarm(
        self,
        db: Session,
        *,
        reason: str,
        preserve_next_session: bool = False,
    ) -> dict[str, Any]:
        before = self.runtime_settings.get_settings_read_only(db)
        keep_next_session = bool(
            preserve_next_session
            and before.get("operation_test4_scheduler_arm_mode") in {"next_session", "active_cycle"}
            and before.get("operation_test4_target_trading_date")
        )
        payload: dict[str, Any] = {
            "dry_run": True,
            "kill_switch": True,
            "operation_test4_enabled": False,
            "operation_test4_scheduler_enabled": keep_next_session,
            "operation_test4_allow_real_entry": False,
            "operation_test4_allow_real_exit": False,
            "operation_test4_entry_enabled": False,
            "operation_test4_position_management_enabled": False,
            "operation_test4_stop_loss_enabled": False,
            "operation_test4_take_profit_enabled": False,
            "operation_test4_scheduler_arm_mode": (
                "next_session" if keep_next_session else "disarmed"
            ),
            "operation_test4_target_trading_date": (
                before.get("operation_test4_target_trading_date")
                if keep_next_session
                else None
            ),
            "operation_test4_scheduler_last_stage": reason,
            "operation_test4_scheduler_last_entry_decision": None if keep_next_session else before.get("operation_test4_scheduler_last_entry_decision"),
            "operation_test4_scheduler_last_error": None if keep_next_session else reason,
            **{key: False for key in BUY_FLAGS},
        }
        return self.runtime_settings.update_settings(db, payload)
    def _active_cycle(self, db: Session) -> OperationTest4Cycle | None:
        return (
            db.query(OperationTest4Cycle)
            .filter(OperationTest4Cycle.status.in_(ACTIVE_CYCLE_STATUSES))
            .order_by(OperationTest4Cycle.created_at.desc(), OperationTest4Cycle.id.desc())
            .first()
        )

    def _active_lifecycles(self, db: Session) -> list[PositionLifecycle]:
        return (
            db.query(PositionLifecycle)
            .filter(PositionLifecycle.status.in_(["open", "closing"]))
            .order_by(PositionLifecycle.opened_at.asc(), PositionLifecycle.id.asc())
            .all()
        )

    def _entry_used_today(self, db: Session, now_utc: datetime) -> bool:
        start, end = _day_bounds_utc(now_utc)
        return (
            db.query(OperationTest4Cycle)
            .filter(
                or_(
                    and_(OperationTest4Cycle.started_at >= start, OperationTest4Cycle.started_at < end),
                    and_(OperationTest4Cycle.created_at >= start, OperationTest4Cycle.created_at < end),
                )
            )
            .filter(OperationTest4Cycle.entry_order_id.is_not(None))
            .first()
            is not None
        )

    def _daily_order_count(self, db: Session, *, side: str, now_utc: datetime) -> int:
        start, end = _day_bounds_utc(now_utc)
        rows = (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.side == side)
            .filter(OrderLog.created_at >= start)
            .filter(OrderLog.created_at < end)
            .filter(OrderLog.internal_status.in_(sorted(SUBMITTED_STATUSES)))
            .all()
        )
        count = 0
        for row in rows:
            payloads = [_json_object(row.request_payload), _json_object(row.response_payload)]
            if any(
                payload.get("operation_test") == OPERATION_TEST
                or str(payload.get("order_source") or "").startswith("operation_test4_")
                or str(payload.get("source") or "").startswith("operation_test4_")
                for payload in payloads
            ):
                count += 1
        return count

    def _local_open_order_count(self, db: Session) -> int:
        return int(
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.internal_status.in_(sorted(OPEN_ORDER_STATUSES)))
            .count()
            or 0
        )

    def _local_open_sell(self, db: Session, symbol: str) -> bool:
        return (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.side == "sell")
            .filter(OrderLog.symbol == symbol)
            .filter(OrderLog.internal_status.in_(sorted(OPEN_ORDER_STATUSES)))
            .first()
            is not None
        )

    def _read_account_state(self, *, require_fresh: bool = False) -> dict[str, Any]:
        if self.account_state_provider is not None:
            try:
                result = self.account_state_provider()
                normalized = _normalize_account_state(result)
            except TypeError:
                result = self.account_state_provider(self.client)
                normalized = _normalize_account_state(result)
            except Exception as exc:
                return _account_error(exc)
            if require_fresh and normalized.get("account_state_live_verified") is not True:
                blocked = _account_error(RuntimeError("account_state_stale_not_safe_for_live"))
                blocked.update(
                    {
                        key: normalized.get(key)
                        for key in (
                            "account_state_status",
                            "account_state_failed_component",
                            "account_state_attempt_count",
                            "account_state_retryable",
                            "account_state_error_category",
                            "account_state_error_code",
                            "account_state_http_status",
                            "account_state_last_checked_at",
                            "account_state_component_attempts",
                        )
                    }
                )
                return blocked
            return normalized
        cache = KisAccountStateCacheService.get_or_create(self.client)
        state = cache.get_account_state(
            read_only=True,
            require_fresh=require_fresh,
        )
        if state.get("fetch_success") is not True:
            fallback = _account_error(RuntimeError("account_state_unavailable"))
            fallback["warnings"] = list(state.get("warnings") or [])
            fallback["rate_limited"] = bool(state.get("rate_limited"))
            fallback["error_details"] = state.get("error_details") or {}
            fallback.update(
                {
                    key: state.get(key)
                    for key in (
                        "account_state_status",
                        "account_state_failed_component",
                        "account_state_attempt_count",
                        "account_state_retryable",
                        "account_state_error_category",
                        "account_state_error_code",
                        "account_state_http_status",
                        "account_state_last_checked_at",
                        "account_state_component_attempts",
                    )
                }
            )
            return fallback
        normalized = _normalize_account_state(state)
        if require_fresh and normalized.get("account_state_live_verified") is not True:
            blocked = _account_error(RuntimeError("account_state_stale_not_safe_for_live"))
            blocked.update(
                {
                    key: normalized.get(key)
                    for key in (
                        "account_state_status",
                        "account_state_failed_component",
                        "account_state_attempt_count",
                        "account_state_retryable",
                        "account_state_error_category",
                        "account_state_error_code",
                        "account_state_http_status",
                        "account_state_last_checked_at",
                        "account_state_component_attempts",
                    )
                }
            )
            return blocked
        return normalized

    def _load_watchlist(
        self,
        *,
        price_cap_krw: float | None = None,
        require_fresh: bool = False,
        today_kst: date | None = None,
    ) -> dict[str, Any]:
        try:
            payload = load_operation_test4_watchlist(
                self.watchlist_path,
                price_cap_krw=price_cap_krw,
                require_fresh=require_fresh,
                today_kst=today_kst,
            )
            payload["fresh"] = bool(require_fresh)
            return payload
        except OperationTest4WatchlistError as exc:
            return {
                "count": 0,
                "fresh": False,
                "error": str((exc.details or {}).get("reason") or "watchlist_invalid"),
            }

    def _market_session(self, now: datetime) -> dict[str, Any]:
        try:
            return self.session_service.get_session_status(MARKET, now=now)
        except Exception as exc:
            return {
                "market": MARKET,
                "is_market_open": False,
                "is_entry_allowed_now": False,
                "error": _safe_error(exc),
            }

    def _runtime_snapshot(self, runtime: dict[str, Any]) -> dict[str, Any]:
        return {
            key: runtime.get(key)
            for key in (
                "dry_run",
                "kill_switch",
                "operation_test4_enabled",
                "operation_test4_scheduler_enabled",
                "operation_test4_allow_real_entry",
                "operation_test4_allow_real_exit",
                "operation_test4_entry_enabled",
                "operation_test4_position_management_enabled",
                "operation_test4_stop_loss_enabled",
                "operation_test4_take_profit_enabled",
                "operation_test4_min_position_pct",
                "operation_test4_max_position_pct",
                "operation_test4_max_order_notional_krw",
                "operation_test4_price_cap_krw",
                "operation_test4_max_buy_orders_per_day",
                "operation_test4_max_sell_orders_per_day",
                "operation_test4_max_open_positions",
                "operation_test4_cash_only",
                "operation_test4_no_new_entry_after",
                "operation_test4_scheduler_arm_mode",
                "operation_test4_target_trading_date",
                "operation_test4_scheduler_armed_at",
                "operation_test4_scheduler_last_error",
                "operation_test4_scheduler_last_stage",
                "operation_test4_scheduler_last_entry_decision",
                "operation_test4_scheduler_last_evaluated_trade_date",
                "operation_test4_scheduler_last_evaluated_slot_kst",
            )
        }

    def _account_summary(self, account: dict[str, Any]) -> dict[str, Any]:
        return {
            "equity": account.get("equity", 0),
            "cash": account.get("cash"),
            "withdrawable_cash": account.get("withdrawable_cash"),
            "orderable_cash": account.get("orderable_cash"),
            "orderable_cash_status": account.get("orderable_cash_status", "unavailable"),
            "orderable_cash_source": account.get("orderable_cash_source"),
            "d1_cash": account.get("d1_cash"),
            "d2_cash": account.get("d2_cash"),
            "position_count": account.get("position_count", 0),
            "open_order_count": account.get("open_order_count", 0),
            "fetch_success": account.get("fetch_success") is True,
            "warnings": account.get("warnings", []),
            "account_state_status": account.get("account_state_status", "unavailable"),
            "account_state_failed_component": account.get("account_state_failed_component"),
            "account_state_attempt_count": account.get("account_state_attempt_count", 0),
            "account_state_retryable": account.get("account_state_retryable", False),
            "account_state_error_category": account.get("account_state_error_category"),
            "account_state_error_code": account.get("account_state_error_code"),
            "account_state_http_status": account.get("account_state_http_status"),
            "account_state_last_checked_at": account.get("account_state_last_checked_at"),
            "account_state_component_attempts": account.get("account_state_component_attempts") or {},
            "account_state_live_verified": account.get("account_state_live_verified") is True,
        }

    def _blocked_enable(self, reason: str) -> dict[str, Any]:
        return sanitize_kis_payload(
            {
                "status": "blocked",
                "operation_test": OPERATION_TEST,
                "reason": reason,
                "required_confirmation": ENABLE_CONFIRMATION,
                "immediate_order_execution": False,
                "real_order_submitted": False,
                "broker_submit_called": False,
            }
        )

    def _entry_blocked(self, reason: str) -> dict[str, Any]:
        return sanitize_kis_payload(
            {
                "status": "blocked",
                "operation_test": OPERATION_TEST,
                "result": HOLD,
                "reason": reason,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        )

    def _entry_result(self, cycle, *, reason: str, response=None, validation=None, promotion=None, runtime=None, status_code=None):
        return sanitize_kis_payload(
            {
                "status": "ok" if reason == "entry_submitted" else "blocked",
                "operation_test": OPERATION_TEST,
                "mode": MODE,
                "result": reason,
                "reason": reason,
                "cycle": _serialize_cycle(cycle),
                "response": response,
                "validation": validation,
                "promotion": promotion,
                "runtime": self._runtime_snapshot(runtime) if runtime else None,
                "status_code": status_code,
                "real_order_submitted": reason == "entry_submitted",
                "broker_submit_called": reason == "entry_submitted",
                "manual_submit_called": response is not None,
            }
        )

    def _cycle_result(self, cycle, *, reason: str, response=None, close=None, current_price=None):
        return sanitize_kis_payload(
            {
                "status": "ok",
                "operation_test": OPERATION_TEST,
                "mode": MODE,
                "result": reason,
                "reason": reason,
                "current_price": current_price,
                "cycle": _serialize_cycle(cycle),
                "response": response,
                "close": close,
                "real_order_submitted": bool(response and response.get("real_order_submitted") is True),
                "broker_submit_called": bool(response and response.get("broker_submit_called") is True),
                "manual_submit_called": bool(response and response.get("manual_submit_called") is True),
            }
        )


def _preflight_progress_start() -> None:
    now = datetime.now(UTC).isoformat()
    with _PREFLIGHT_PROGRESS_LOCK:
        _PREFLIGHT_PROGRESS.update(
            {
                "preflight_running": True,
                "preflight_started_at": now,
                "preflight_finished_at": None,
                "current_stage": "starting",
                "last_progress_at": now,
                "analyzed_count": 0,
                "total_count": 0,
                "error": None,
            }
        )


def _preflight_progress_update(
    *,
    stage: str | None = None,
    analyzed_count: int | None = None,
    total_count: int | None = None,
    error: str | None = None,
) -> None:
    now = datetime.now(UTC).isoformat()
    with _PREFLIGHT_PROGRESS_LOCK:
        if stage is not None:
            _PREFLIGHT_PROGRESS["current_stage"] = stage
        if analyzed_count is not None:
            _PREFLIGHT_PROGRESS["analyzed_count"] = max(0, int(analyzed_count))
        if total_count is not None:
            _PREFLIGHT_PROGRESS["total_count"] = max(0, int(total_count))
        if error is not None:
            _PREFLIGHT_PROGRESS["error"] = error
        _PREFLIGHT_PROGRESS["last_progress_at"] = now


def _preflight_progress_finish(*, failed: bool) -> None:
    now = datetime.now(UTC).isoformat()
    with _PREFLIGHT_PROGRESS_LOCK:
        _PREFLIGHT_PROGRESS["preflight_running"] = False
        _PREFLIGHT_PROGRESS["preflight_finished_at"] = now
        _PREFLIGHT_PROGRESS["current_stage"] = "failed" if failed else "completed"
        _PREFLIGHT_PROGRESS["last_progress_at"] = now


def _preflight_progress_snapshot() -> dict[str, Any]:
    with _PREFLIGHT_PROGRESS_LOCK:
        snapshot = dict(_PREFLIGHT_PROGRESS)
    total = int(snapshot.get("total_count") or 0)
    analyzed = int(snapshot.get("analyzed_count") or 0)
    snapshot["progress_pct"] = (
        round(min(100.0, analyzed * 100.0 / total), 2)
        if total > 0
        else None
    )
    return snapshot


def _next_entry_slot_info(now: datetime, *, enabled: bool) -> dict[str, str | None]:
    if not enabled:
        return {
            "next_entry_slot_kst": None,
            "next_automatic_entry_run": None,
        }
    local = now.astimezone(KR_TZ)
    for slot in ENTRY_SLOTS:
        hour, minute = (int(part) for part in slot.split(":"))
        if (local.hour, local.minute) < (hour, minute):
            run_at = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return {
                "next_entry_slot_kst": slot,
                "next_automatic_entry_run": run_at.isoformat(),
            }
    return {
        "next_entry_slot_kst": None,
        "next_automatic_entry_run": None,
    }


def _entry_slot_for_time(now: datetime) -> str:
    local = now.astimezone(KR_TZ)
    selected = ENTRY_SLOTS[0]
    for slot in ENTRY_SLOTS:
        hour, minute = (int(part) for part in slot.split(":"))
        if (local.hour, local.minute) >= (hour, minute):
            selected = slot
    return selected


def _candidate_block_reasons(
    candidate: dict[str, Any],
    *,
    score: float | None,
    min_score: float,
    score_gap: Any,
    min_score_gap: float,
) -> list[str]:
    reasons: list[str] = []
    if score is None:
        reasons.append("final_score_unavailable")
    elif score < min_score:
        reasons.append("final_score_gate_not_met")
    if score_gap is not None and _number(score_gap) < min_score_gap:
        reasons.append("final_score_gap_gate_not_met")
    if candidate.get("hard_block_reason"):
        reasons.append("gpt_hard_block")
    for reason in candidate.get("block_reasons") or []:
        if str(reason) not in {"preview_only", "kr_trading_disabled", "trading_disabled"}:
            reasons.append(str(reason))
    return _dedupe(reasons)


def _eligible_count(preview: dict[str, Any], runtime: dict[str, Any]) -> int:
    rows = preview.get("watchlist") or preview.get("items") or []
    cap = _number(runtime.get("operation_test4_price_cap_krw") or DEFAULT_PRICE_CAP_KRW)
    count = 0
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        price = _number(row.get("current_price") or row.get("price"))
        if 0 < price < cap and "current_price_unavailable" not in (row.get("block_reasons") or []):
            count += 1
    return count


def _normalize_account_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return _account_error(ValueError("account_state_invalid"))
    payload = dict(value)
    positions = payload.get("positions")
    open_orders = payload.get("open_orders")
    raw_balance = payload.get("balance")
    if (
        payload.get("fetch_success") is not True
        or not isinstance(positions, list)
        or not isinstance(open_orders, list)
        or (raw_balance is not None and not isinstance(raw_balance, dict))
        or not all(isinstance(row, dict) for row in positions)
        or not all(isinstance(row, dict) for row in open_orders)
    ):
        return _account_error(ValueError("account_state_invalid"))
    balance = raw_balance or {}
    equity = _first_number(payload, "equity")
    if equity is None:
        equity = _first_number(balance, "total_asset_value", "equity")
    orderable_cash = _first_number(payload, "orderable_cash")
    if orderable_cash is None:
        orderable_cash = _first_number(balance, "orderable_cash", "orderable_amount")
    held_positions = [
        row
        for row in positions
        if _number(row.get("qty")) > 0
    ]
    return {
        **payload,
        "fetch_success": True,
        "equity": equity or 0.0,
        "orderable_cash": orderable_cash,
        "orderable_cash_status": payload.get(
            "orderable_cash_status",
            "candidate_required" if orderable_cash is None else "ok",
        ),
        "orderable_cash_source": payload.get("orderable_cash_source"),
        "cash": _number_or_none(payload.get("cash"))
        if payload.get("cash") is not None
        else _number_or_none(balance.get("cash")),
        "withdrawable_cash": _number_or_none(payload.get("withdrawable_cash"))
        if payload.get("withdrawable_cash") is not None
        else _number_or_none(balance.get("withdrawable_cash")),
        "d1_cash": _number_or_none(payload.get("d1_cash"))
        if payload.get("d1_cash") is not None
        else _number_or_none(balance.get("d1_cash")),
        "d2_cash": _number_or_none(payload.get("d2_cash"))
        if payload.get("d2_cash") is not None
        else _number_or_none(balance.get("d2_cash")),
        "positions": held_positions,
        "open_orders": open_orders,
        "position_count": len(held_positions),
        "open_order_count": len(open_orders),
        "warnings": payload.get("warnings") or [],
        "account_state_live_verified": payload.get(
            "account_state_live_verified",
            payload.get("fetch_success") is True,
        ),
        "account_state_status": payload.get(
            "account_state_status",
            "available" if payload.get("fetch_success") is True else "unavailable",
        ),
        "account_state_failed_component": payload.get("account_state_failed_component"),
        "account_state_attempt_count": payload.get("account_state_attempt_count", 0),
        "account_state_retryable": payload.get("account_state_retryable", False),
        "account_state_error_category": payload.get("account_state_error_category"),
        "account_state_error_code": payload.get("account_state_error_code"),
        "account_state_http_status": payload.get("account_state_http_status"),
        "account_state_last_checked_at": payload.get("account_state_last_checked_at"),
        "account_state_component_attempts": payload.get("account_state_component_attempts") or {},
    }

def _account_error(exc: Exception) -> dict[str, Any]:
    return {
        "fetch_success": False,
        "equity": 0.0,
        "orderable_cash": None,
        "orderable_cash_status": "unavailable",
        "positions": [],
        "open_orders": [],
        "position_count": 0,
        "open_order_count": 0,
        "warnings": [f"account_state_unavailable:{exc.__class__.__name__}"],
        "account_state_live_verified": False,
        "account_state_status": "unavailable",
        "account_state_failed_component": "unknown",
        "account_state_attempt_count": 0,
        "account_state_retryable": False,
        "account_state_error_category": "unknown",
        "account_state_error_code": exc.__class__.__name__,
        "account_state_http_status": None,
        "account_state_last_checked_at": datetime.now(UTC).isoformat(),
        "account_state_component_attempts": {},
    }


def _find_position(positions: list[dict[str, Any]], symbol: str) -> dict[str, Any] | None:
    normalized = str(symbol or "").strip().upper()
    for position in positions:
        if str(position.get("symbol") or "").strip().upper() == normalized:
            return position
    return None


def _serialize_cycle(cycle: OperationTest4Cycle | None) -> dict[str, Any]:
    if cycle is None:
        return {}
    return {
        "id": cycle.id,
        "cycle_key": cycle.cycle_key,
        "operation_test": cycle.operation_test,
        "provider": cycle.provider,
        "market": cycle.market,
        "symbol": cycle.symbol,
        "status": cycle.status,
        "entry_trigger_source": cycle.entry_trigger_source,
        "min_position_pct": cycle.min_position_pct,
        "max_position_pct": cycle.max_position_pct,
        "price_cap_krw": cycle.price_cap_krw,
        "max_order_notional_krw": cycle.max_order_notional_krw,
        "equity_at_entry": cycle.equity_at_entry,
        "orderable_cash_at_entry": cycle.orderable_cash_at_entry,
        "estimated_entry_price": cycle.estimated_entry_price,
        "requested_quantity": cycle.requested_quantity,
        "estimated_notional": cycle.estimated_notional,
        "effective_position_pct": cycle.effective_position_pct,
        "entry_order_id": cycle.entry_order_id,
        "entry_broker_order_id": cycle.entry_broker_order_id,
        "entry_filled_quantity": cycle.entry_filled_quantity,
        "entry_average_fill_price": cycle.entry_average_fill_price,
        "lifecycle_id": cycle.lifecycle_id,
        "exit_order_id": cycle.exit_order_id,
        "exit_reason": cycle.exit_reason,
        "manual_review_required": bool(cycle.manual_review_required),
        "last_error": cycle.last_error,
        "started_at": _iso(cycle.started_at),
        "entry_submitted_at": _iso(cycle.entry_submitted_at),
        "entry_filled_at": _iso(cycle.entry_filled_at),
        "completed_at": _iso(cycle.completed_at),
        "created_at": _iso(cycle.created_at),
        "updated_at": _iso(cycle.updated_at),
    }


def _runtime_flags(runtime: dict[str, Any]) -> dict[str, Any]:
    return {key: runtime.get(key) for key in BUY_FLAGS}


def _public_market_session(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.get(key)
        for key in (
            "market",
            "timezone",
            "is_market_open",
            "is_entry_allowed_now",
            "is_holiday",
            "closure_reason",
            "regular_open",
            "regular_close",
            "no_new_entry_after",
        )
    }


def _is_kis_prod(settings: Any) -> bool:
    return str(getattr(settings, "kis_env", "") or "").strip().lower() in {
        "prod",
        "production",
        "real",
    }


def _manual_confirmation(client: Any) -> str:
    return str(
        getattr(client.settings, "kis_confirmation_phrase", KIS_MANUAL_CONFIRMATION_PHRASE)
        or KIS_MANUAL_CONFIRMATION_PHRASE
    )


def _day_bounds_utc(now: datetime) -> tuple[datetime, datetime]:
    local = now.astimezone(KR_TZ)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return _naive_utc(start), _naive_utc(start + timedelta(days=1))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    return _aware_utc(value).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number == number and abs(number) != float("inf") else 0.0


def _number_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _first_number(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _number_or_none(payload.get(key))
        if value is not None:
            return value
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value) if value else {}
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _safe_error(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {_text_or_none(str(exc)) or exc.__class__.__name__}"[:300]


def _read_only_safety() -> dict[str, Any]:
    return {
        "read_only": True,
        "preflight_only": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
    }


def _possible_order_is_fresh(
    payload: dict[str, Any],
    *,
    now: datetime,
    max_age_seconds: float,
) -> bool:
    if not isinstance(payload, dict) or payload.get("raw_status") != "ok":
        return False
    try:
        queried_at = datetime.fromisoformat(str(payload.get("queried_at") or ""))
    except ValueError:
        return False
    if queried_at.tzinfo is None:
        queried_at = queried_at.replace(tzinfo=UTC)
    age = (now - queried_at.astimezone(UTC)).total_seconds()
    return 0 <= age <= float(max_age_seconds)


def _conservative_possible_order(
    preflight: dict[str, Any],
    latest: dict[str, Any],
) -> dict[str, Any]:
    if preflight.get("raw_status") != "ok" or latest.get("raw_status") != "ok":
        return {
            "raw_status": "error",
            "error": "possible_order_unavailable",
            "orderable_cash": None,
            "orderable_quantity": None,
        }
    cash_values = [
        _number_or_none(preflight.get("orderable_cash")),
        _number_or_none(latest.get("orderable_cash")),
    ]
    quantity_values = [
        _int_or_none(preflight.get("orderable_quantity")),
        _int_or_none(latest.get("orderable_quantity")),
    ]
    if any(value is None for value in cash_values + quantity_values):
        return {
            "raw_status": "error",
            "error": "possible_order_unavailable",
            "orderable_cash": None,
            "orderable_quantity": None,
        }
    return {
        **latest,
        "raw_status": "ok",
        "orderable_cash": min(value for value in cash_values if value is not None),
        "orderable_quantity": min(
            value for value in quantity_values if value is not None
        ),
        "conservative_snapshot": True,
        "preflight_queried_at": preflight.get("queried_at"),
        "latest_queried_at": latest.get("queried_at"),
    }
