from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.core.enums import InternalOrderStatus
from app.db.models import OperationTest4Cycle, OrderLog, PositionLifecycle
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
from app.services.kis_position_lifecycle_service import KisPositionLifecycleService
from app.services.kis_watchlist_preview_service import KisWatchlistPreviewService
from app.services.market_profile_service import MarketProfileService
from app.services.market_session_service import MarketSessionService
from app.services.operation_test4_sizing import calculate_operation_test4_sizing
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
HOLD = "HOLD"
STOP_LOSS_READY = "STOP_LOSS_READY"
TAKE_PROFIT_READY = "TAKE_PROFIT_READY"
REVIEW = "REVIEW"
ENTRY_SLOTS = ("09:35",)
POSITION_SLOTS = ("10:00", "12:00", "14:30")
ALL_SLOTS = ENTRY_SLOTS + POSITION_SLOTS
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
        self.now_provider = now_provider or (lambda: datetime.now(UTC))

    def status(self, db: Session, *, now: datetime | None = None) -> dict[str, Any]:
        runtime = self.runtime_settings.get_settings_read_only(db)
        active = self._active_cycle(db)
        account = self._read_account_state()
        return sanitize_kis_payload(
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
                    "entry_slot_kst": "09:35",
                    "position_slots_kst": list(POSITION_SLOTS),
                    "single_symbol": True,
                    "max_open_positions": 1,
                },
                "real_order_submitted": False,
                "broker_submit_called": False,
            }
        )

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
        watchlist = self._load_watchlist()
        preview, candidate = self._candidate_snapshot(
            db,
            account=account,
            runtime=runtime,
            now=now_utc,
        )
        entry_candidate = candidate.get("sizing") if candidate else None
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
        ) -> None:
            checks.append(
                {
                    "key": key,
                    "passed": bool(passed),
                    "blocking": True,
                    "detail": detail,
                }
            )
            if passed:
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
            ),
            ("account_readable", account.get("fetch_success") is True, "account_state_unavailable", "review"),
            ("equity_positive", _number(account.get("equity")) > 0, "equity_unavailable", "review"),
            ("orderable_cash_positive", _number(account.get("orderable_cash")) > 0, "orderable_cash_unavailable", "review"),
            ("position_count_zero", account.get("position_count") == 0, "position_exists"),
            ("active_lifecycle_zero", len(active_lifecycles) == 0, "active_lifecycle_exists"),
            ("open_order_count_zero", account.get("open_order_count") == 0, "open_order_exists"),
            ("active_cycle_zero", active_cycle is None, "active_cycle_exists"),
            ("daily_buy_count_zero", self._daily_order_count(db, side="buy", now_utc=now_utc) == 0, "daily_buy_already_used"),
            ("market_open", market_session.get("is_market_open") is True, "market_closed"),
            ("entry_time_allowed", time_allowed, "entry_time_outside_window"),
            ("watchlist_exact_count", watchlist.get("count") == DEFAULT_COUNT, "watchlist_count_not_50"),
            ("watchlist_eligible_count", _eligible_count(preview, runtime) == DEFAULT_COUNT, "watchlist_eligible_count_below_50", "review"),
            ("candidate_selected", bool(candidate), "no_candidate"),
            ("candidate_score_gate", not candidate or not candidate.get("block_reasons"), "candidate_gate_blocked"),
            ("sizing_ready", bool(entry_candidate and entry_candidate.get("status") == "ready"), "sizing_blocked"),
        ]
        for item in entry_conditions:
            key, passed, reason, *extra = item
            category = extra[0] if extra else "blocking"
            add(key, passed, reason, category=category)

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
        entry_ready = not entry_blocking and not entry_review
        exit_ready = bool(active_position) and not exit_blocking and not exit_review
        live_ready = entry_ready or exit_ready
        status = (
            "ready"
            if live_ready
            else "review_required"
            if entry_review or exit_review
            else "blocked"
        )
        return sanitize_kis_payload(
            {
                "status": status,
                "live_ready": live_ready,
                "entry_ready": entry_ready,
                "exit_ready": exit_ready,
                "provider": PROVIDER,
                "market": MARKET,
                "operation_test": OPERATION_TEST,
                "cycle": _serialize_cycle(active_cycle) if active_cycle else {},
                "account": self._account_summary(account),
                "watchlist": {
                    "configured_count": watchlist.get("count", 0),
                    "eligible_count": _eligible_count(preview, runtime),
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
                "runtime": self._runtime_snapshot(runtime),
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

    def rebuild_watchlist(
        self,
        db: Session,
        *,
        count: int = DEFAULT_COUNT,
        price_cap_krw: float = DEFAULT_PRICE_CAP_KRW,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        del db
        result = build_operation_test4_watchlist(
            root=Path(__file__).resolve().parents[2],
            output_path=self.watchlist_path,
            count=count,
            price_cap_krw=price_cap_krw,
            client=self.client,
            now=now,
        )
        return sanitize_kis_payload(
            {
                "status": "rebuilt",
                "operation_test": OPERATION_TEST,
                "watchlist": result,
                "safety": {
                    "read_only_quotes_only": True,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                },
            }
        )

    def enable_live(
        self,
        db: Session,
        *,
        confirm_live: bool,
        confirmation: str | None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if confirm_live is not True or str(confirmation or "").strip() != ENABLE_CONFIRMATION:
            return self._blocked_enable("operator_confirmation_required")
        now_utc = _aware_utc(now or self.now_provider())
        runtime = self.runtime_settings.get_settings_read_only(db)
        account = self._read_account_state()
        active_cycle = self._active_cycle(db)
        active_lifecycle_count = len(self._active_lifecycles(db))
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
        if active_cycle is not None:
            blockers.append("active_cycle_exists")
        if self._daily_order_count(db, side="buy", now_utc=now_utc) != 0:
            blockers.append("daily_buy_already_used")
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
        settings_after = self.runtime_settings.update_settings(
            db,
            {
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
                "operation_test4_max_buy_orders_per_day": 1,
                "operation_test4_max_sell_orders_per_day": 1,
                "operation_test4_max_open_positions": 1,
                "operation_test4_allow_single_share_budget_bump": True,
                "operation_test4_cash_only": True,
                "operation_test4_no_new_entry_after": "14:00",
                **{key: False for key in BUY_FLAGS},
            },
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

    def preflight_once(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        result = self.readiness(db, now=now)
        result.update(
            {
                "mode": "operation_test4_preflight",
                "preflight_only": True,
                "safety": {
                    "read_only": True,
                    "preflight_only": True,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                },
            }
        )
        return sanitize_kis_payload(result)

    def entry_run_once(
        self,
        db: Session,
        *,
        confirm_live: bool,
        confirmation: str | None,
        now: datetime | None = None,
        trigger_source: str = "operation_test4_run_once",
    ) -> dict[str, Any]:
        now_utc = _aware_utc(now or self.now_provider())
        if confirm_live is not True or str(confirmation or "").strip() != ENTRY_CONFIRMATION:
            return self._entry_blocked("operator_confirmation_required")
        readiness = self.readiness(db, now=now_utc)
        if readiness.get("status") != "ready" or readiness.get("entry_ready") is not True:
            return sanitize_kis_payload(
                {
                    "status": "blocked",
                    "operation_test": OPERATION_TEST,
                    "result": HOLD,
                    "reason": (readiness.get("blocking_reasons") or readiness.get("review_reasons") or ["readiness_not_ready"])[0],
                    "blocking_reasons": readiness.get("blocking_reasons", []),
                    "review_reasons": readiness.get("review_reasons", []),
                    "readiness": readiness,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                }
            )
        now_kst = now_utc.astimezone(KR_TZ)
        if now_kst.time() < time(9, 0):
            return self._entry_blocked("entry_before_09_00")
        if now_kst.time() >= time(14, 0):
            return self._entry_blocked("entry_after_14_00")
        if self._entry_used_today(db, now_utc):
            return self._entry_blocked("daily_entry_already_used")

        candidate = readiness.get("candidate") or {}
        sizing_payload = candidate.get("sizing") or {}
        cycle = OperationTest4Cycle(
            cycle_key=f"operation_test4_{now_kst.strftime('%Y%m%d')}_{uuid.uuid4().hex[:12]}",
            operation_test=OPERATION_TEST,
            provider=PROVIDER,
            market=MARKET,
            symbol=str(candidate.get("symbol") or ""),
            status="entry_ready",
            entry_trigger_source=trigger_source,
            min_position_pct=float(sizing_payload.get("min_position_pct") or 10.0),
            max_position_pct=float(sizing_payload.get("max_position_pct") or 100.0),
            price_cap_krw=float(sizing_payload.get("price_cap_krw") or 1_000_000.0),
            max_order_notional_krw=float(sizing_payload.get("max_order_notional_krw") or 1_000_000.0),
            equity_at_entry=_number(candidate.get("equity")),
            orderable_cash_at_entry=_number(candidate.get("orderable_cash")),
            estimated_entry_price=_number(candidate.get("current_price")),
            requested_quantity=int(sizing_payload.get("quantity") or 0),
            estimated_notional=_number(sizing_payload.get("estimated_notional")),
            effective_position_pct=_number(sizing_payload.get("effective_position_pct")),
            started_at=_naive_utc(now_utc),
        )
        db.add(cycle)
        db.commit()
        db.refresh(cycle)

        validation = self._validate_entry(
            db,
            symbol=cycle.symbol,
            quantity=int(cycle.requested_quantity or 0),
            now=now_utc,
            candidate=candidate,
        )
        if validation.get("valid") is not True:
            cycle.status = "blocked"
            cycle.last_error = str(validation.get("reason") or "validation_failed")
            db.commit()
            return self._entry_result(cycle, reason=cycle.last_error, validation=validation)

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
        cycle = self._active_cycle(db)
        if cycle is not None and cycle.status in {"entry_submitted", "entry_pending", "exit_submitted"}:
            return self.reconcile_once(db, now=now)
        if slot_label in ENTRY_SLOTS and cycle is None:
            return self.entry_run_once(
                db,
                confirm_live=True,
                confirmation=ENTRY_CONFIRMATION,
                now=now,
                trigger_source="operation_test4_scheduler",
            )
        if slot_label in POSITION_SLOTS and cycle is not None and cycle.status == "position_open":
            return self._manage_exit(db, cycle, now=_aware_utc(now or self.now_provider()))
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
        account = self._read_account_state()
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
            runtime.get("operation_test4_max_sell_orders_per_day", 1) or 1
        ):
            return self._cycle_result(cycle, reason="daily_sell_already_used", current_price=current_price)
        cycle.status = "exit_ready"
        cycle.exit_reason = "stop_loss_triggered" if stop_triggered else "take_profit_triggered"
        db.commit()
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
        selected: dict[str, Any] = {}
        for raw in candidates:
            if not isinstance(raw, dict):
                continue
            symbol = str(raw.get("symbol") or "").strip()
            if not symbol:
                continue
            selected = dict(raw)
            break
        if not selected:
            return preview, {}
        current_price = _number(
            selected.get("current_price")
            or selected.get("price")
            or selected.get("stck_prpr")
        )
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
        sizing = calculate_operation_test4_sizing(
            equity=_number(account.get("equity")),
            orderable_cash=_number(account.get("orderable_cash")),
            current_price=current_price,
            min_position_pct=float(runtime.get("operation_test4_min_position_pct", 10.0)),
            max_position_pct=float(runtime.get("operation_test4_max_position_pct", 100.0)),
            max_order_notional_krw=float(runtime.get("operation_test4_max_order_notional_krw", 1_000_000.0)),
            price_cap_krw=float(runtime.get("operation_test4_price_cap_krw", 1_000_000.0)),
            broker_orderable_qty=_number_or_none(selected.get("broker_orderable_qty")),
            allow_single_share_budget_bump=bool(
                runtime.get("operation_test4_allow_single_share_budget_bump", True)
            ),
        )
        if not sizing.allowed:
            block_reasons.append(str(sizing.reason or "sizing_blocked"))
        selected.update(
            {
                "symbol": symbol,
                "current_price": current_price or None,
                "final_buy_score": score,
                "block_reasons": _dedupe(block_reasons),
                "risk_flags": selected.get("risk_flags") or [],
                "equity": account.get("equity"),
                "orderable_cash": account.get("orderable_cash"),
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
        return preview, selected

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
        account = self._read_account_state()
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
        settings = self._disarm(db, reason="cycle_completed")
        return {
            "closed": True,
            "reason": "cycle_completed",
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

    def _disarm(self, db: Session, *, reason: str) -> dict[str, Any]:
        return self.runtime_settings.update_settings(
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
                "operation_test4_stop_loss_enabled": True,
                "operation_test4_take_profit_enabled": True,
                **{key: False for key in BUY_FLAGS},
            },
        )

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

    def _read_account_state(self) -> dict[str, Any]:
        if self.account_state_provider is not None:
            try:
                result = self.account_state_provider()
                return _normalize_account_state(result)
            except TypeError:
                result = self.account_state_provider(self.client)
                return _normalize_account_state(result)
            except Exception as exc:
                return _account_error(exc)
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                balance = self.client.get_account_balance()
                positions = self.client.list_positions()
                open_orders = self.client.list_open_orders()
                if not isinstance(balance, dict):
                    raise ValueError("account_balance_invalid")
                orderable_cash = _first_number(
                    balance,
                    "orderable_cash",
                    "orderable_amount",
                    "ord_psbl_cash",
                )
                if orderable_cash is None:
                    orderable_reader = getattr(self.client, "get_orderable_cash", None)
                    if callable(orderable_reader):
                        orderable_cash = _number_or_none(orderable_reader())
                return _normalize_account_state(
                    {
                        "fetch_success": orderable_cash is not None,
                        "balance": balance,
                        "equity": _first_number(balance, "total_asset_value", "equity"),
                        "orderable_cash": orderable_cash,
                        "positions": positions if isinstance(positions, list) else [],
                        "open_orders": open_orders if isinstance(open_orders, list) else [],
                        "warnings": [] if orderable_cash is not None else ["orderable_cash_unavailable"],
                    }
                )
            except Exception as exc:
                last_error = exc
        return _account_error(last_error or RuntimeError("account_state_unavailable"))

    def _load_watchlist(self) -> dict[str, Any]:
        try:
            return load_operation_test4_watchlist(self.watchlist_path)
        except OperationTest4WatchlistError as exc:
            return {"count": 0, "error": _safe_error(exc)}

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
            )
        }

    def _account_summary(self, account: dict[str, Any]) -> dict[str, Any]:
        return {
            "equity": account.get("equity", 0),
            "orderable_cash": account.get("orderable_cash", 0),
            "position_count": account.get("position_count", 0),
            "open_order_count": account.get("open_order_count", 0),
            "fetch_success": account.get("fetch_success") is True,
            "warnings": account.get("warnings", []),
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
    payload = value if isinstance(value, dict) else {}
    positions = payload.get("positions") or []
    open_orders = payload.get("open_orders") or []
    balance = payload.get("balance") or {}
    equity = _first_number(payload, "equity")
    if equity is None:
        equity = _first_number(balance, "total_asset_value", "equity")
    orderable_cash = _first_number(payload, "orderable_cash")
    if orderable_cash is None:
        orderable_cash = _first_number(balance, "orderable_cash", "orderable_amount")
    held_positions = [
        row
        for row in positions
        if isinstance(row, dict) and _number(row.get("qty")) > 0
    ]
    return {
        **payload,
        "fetch_success": payload.get("fetch_success", True) is True,
        "equity": equity or 0.0,
        "orderable_cash": orderable_cash or 0.0,
        "positions": held_positions,
        "open_orders": [row for row in open_orders if isinstance(row, dict)],
        "position_count": len(held_positions),
        "open_order_count": len([row for row in open_orders if isinstance(row, dict)]),
        "warnings": payload.get("warnings") or [],
    }


def _account_error(exc: Exception) -> dict[str, Any]:
    return {
        "fetch_success": False,
        "equity": 0.0,
        "orderable_cash": 0.0,
        "positions": [],
        "open_orders": [],
        "position_count": 0,
        "open_order_count": 0,
        "warnings": [f"account_state_unavailable:{exc.__class__.__name__}"],
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