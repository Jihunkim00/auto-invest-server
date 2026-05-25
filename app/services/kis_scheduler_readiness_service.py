from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, RuntimeSetting, TradeRunLog
from app.services.kis_limited_auto_buy_service import KisLimitedAutoBuyService
from app.services.kis_limited_auto_sell_service import KisLimitedAutoSellService
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService


PROVIDER = "kis"
MARKET = "KR"
MODE = "kis_scheduler_readiness"
KR_TZ = ZoneInfo("Asia/Seoul")

LIVE_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}


class KisSchedulerReadinessService:
    """Read-only KIS scheduler readiness and schedule audit."""

    def __init__(
        self,
        client: KisClient,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
        limited_auto_buy_service: Any | None = None,
        limited_auto_sell_service: Any | None = None,
    ):
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()
        self._limited_auto_buy_service = limited_auto_buy_service
        self._limited_auto_sell_service = limited_auto_sell_service

    def readiness(
        self,
        db: Session,
        *,
        include_modules: bool = True,
        include_recent_runs: bool = True,
        include_raw: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc_now(now)
        runtime, runtime_source = self._runtime_snapshot(db)
        scheduler = _scheduler_settings(self.client.settings, runtime)
        market_session, market_session_unknown = self._market_session(now_utc)
        schedule, next_slot, current_slot = self._schedule(
            runtime=runtime,
            scheduler=scheduler,
            now_utc=now_utc,
        )
        daily_limits = _daily_limits(db, runtime=runtime, now_utc=now_utc)
        modules, module_diagnostics = (
            self._modules(db, runtime=runtime, include_raw=include_raw)
            if include_modules
            else ({}, {"modules_included": False})
        )
        block_reasons = _block_reasons(
            runtime=runtime,
            scheduler=scheduler,
            market_session=market_session,
            market_session_unknown=market_session_unknown,
            runtime_source=runtime_source,
            modules=modules,
        )
        readiness_status = _readiness_status(
            block_reasons,
            scheduler=scheduler,
            modules=modules,
        )
        recent_runs = (
            _recent_scheduler_runs(db)
            if include_recent_runs
            else []
        )
        primary_block_reason = block_reasons[0] if block_reasons else None
        summary = {
            "scheduler_enabled": scheduler["scheduler_enabled"],
            "kis_scheduler_enabled": scheduler["kis_scheduler_enabled"],
            "kis_scheduler_dry_run": scheduler["kis_scheduler_dry_run"],
            "kis_scheduler_allow_real_orders": False,
            "configured_kis_scheduler_allow_real_orders": scheduler[
                "configured_kis_scheduler_allow_real_orders"
            ],
            "runtime_kis_scheduler_allow_real_orders": scheduler[
                "runtime_kis_scheduler_allow_real_orders"
            ],
            "scheduler_real_orders_enabled": False,
            "market_open": market_session.get("is_market_open") is True,
            "entry_allowed_now": market_session.get("is_entry_allowed_now") is True,
            "sell_session_allowed": _sell_session_allowed(market_session),
            "next_scheduled_slot": next_slot,
            "current_slot_label": current_slot,
            "real_order_submit_allowed": False,
            "readiness_status": readiness_status,
            "primary_block_reason": primary_block_reason,
            "block_reasons": block_reasons,
        }
        safety = {
            "readiness_only": True,
            "no_broker_submit_from_scheduler_readiness": True,
            "scheduler_real_orders_enabled": False,
            "kis_scheduler_allow_real_orders": False,
            "manual_submit_called": False,
            "broker_submit_called": False,
            "real_order_submitted": False,
            "live_auto_buy_default_safe": not bool(
                runtime.get("kis_live_auto_buy_enabled", False)
            ),
            "live_auto_sell_default_safe": not bool(
                runtime.get("kis_live_auto_sell_enabled", False)
            ),
            "kill_switch": bool(runtime.get("kill_switch", False)),
            "dry_run": bool(runtime.get("dry_run", True)),
            "runtime_defaults_safe": _runtime_defaults_safe(runtime, scheduler),
            "existing_buy_execution_unchanged": True,
            "existing_sell_execution_unchanged": True,
        }
        diagnostics: dict[str, Any] = {
            "checked_at": now_utc.isoformat(),
            "runtime_settings_source": runtime_source,
            "runtime_settings_missing": runtime_source == "missing_runtime_row",
            "market_session_unknown": market_session_unknown,
            "market_session": _public_market_session(market_session),
            "configured_scheduler": scheduler,
            "daily_limits": daily_limits,
            **module_diagnostics,
        }
        if include_raw:
            diagnostics["raw"] = {
                "runtime": runtime,
                "market_session": market_session,
            }

        payload = {
            "provider": PROVIDER,
            "market": MARKET,
            "mode": MODE,
            "readiness_only": True,
            "scheduler_real_orders_enabled": False,
            "real_order_submit_allowed": False,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "summary": summary,
            "schedule": schedule,
            "modules": modules,
            "block_reasons": block_reasons,
            "safety": safety,
            "recent_runs": recent_runs,
            "diagnostics": diagnostics,
        }
        return sanitize_kis_payload(payload)

    def _runtime_snapshot(self, db: Session) -> tuple[dict[str, Any], str]:
        defaults = dict(self.runtime_settings._defaults())
        row = db.query(RuntimeSetting).first()
        runtime = dict(defaults)
        source = "missing_runtime_row"
        if row is not None:
            source = "runtime_row"
            for key, default_value in defaults.items():
                value = getattr(row, key, None)
                if value is None:
                    continue
                runtime[key] = _coerce_like(value, default_value)
            runtime["updated_at"] = row.updated_at
        runtime["trade_limits"] = self.runtime_settings._trade_limits(runtime)
        runtime["kis_limited_auto_sell_requires_valid_cost_basis"] = True
        runtime["kis_limited_auto_stop_loss_enabled"] = bool(
            runtime.get("kis_limited_auto_sell_stop_loss_enabled", False)
        )
        runtime["kis_limited_auto_take_profit_enabled"] = bool(
            runtime.get("kis_limited_auto_sell_take_profit_enabled", False)
        )
        runtime["kis_limited_auto_take_profit_readiness_enabled"] = True
        runtime["kis_limited_auto_sell_take_profit_readiness_enabled"] = True
        runtime["kis_limited_auto_take_profit_requires_valid_cost_basis"] = True
        runtime["kis_limited_auto_sell_take_profit_requires_valid_cost_basis"] = True
        runtime["kis_limited_auto_take_profit_min_profit_pct"] = 0.03
        runtime["kis_limited_auto_sell_take_profit_min_profit_pct"] = 0.03
        runtime["kis_scheduler_enabled"] = bool(
            getattr(self.client.settings, "kis_scheduler_enabled", False)
            or getattr(self.client.settings, "kr_scheduler_enabled", False)
        )
        runtime["kis_scheduler_dry_run"] = bool(
            getattr(self.client.settings, "kis_scheduler_dry_run", True)
        )
        runtime["kis_scheduler_configured_allow_real_orders"] = bool(
            getattr(self.client.settings, "kis_scheduler_allow_real_orders", False)
            or getattr(self.client.settings, "kr_scheduler_allow_real_orders", False)
        )
        return runtime, source

    def _market_session(self, now_utc: datetime) -> tuple[dict[str, Any], bool]:
        try:
            return self.session_service.get_session_status(MARKET, now=now_utc), False
        except Exception as exc:
            return (
                {
                    "market": MARKET,
                    "timezone": "Asia/Seoul",
                    "is_market_open": False,
                    "is_entry_allowed_now": False,
                    "enabled_for_scheduler": False,
                    "error": _safe_error(exc),
                },
                True,
            )

    def _schedule(
        self,
        *,
        runtime: dict[str, Any],
        scheduler: dict[str, bool],
        now_utc: datetime,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None, str | None]:
        try:
            session = self.session_service.get_session(MARKET)
            slots = {slot.name: slot.time for slot in session.entry_slots}
            timezone = session.timezone
            market_enabled = bool(session.enabled_for_scheduler)
            force_manage_until = session.force_manage_until
        except Exception as exc:
            return (
                [
                    {
                        "slot_id": "kr_schedule_unavailable",
                        "label": "kr_schedule_unavailable",
                        "scheduled_time": None,
                        "timezone": "Asia/Seoul",
                        "purpose": "sell_readiness",
                        "enabled": False,
                        "real_order_allowed": False,
                        "dry_run_only": True,
                        "notes": [_safe_error(exc), "schedule_config_unavailable"],
                    }
                ],
                None,
                None,
            )

        enabled = bool(
            scheduler["scheduler_enabled"]
            and scheduler["kis_scheduler_enabled"]
            and market_enabled
        )
        items = [
            _schedule_item(
                slot_id="open_phase_entry_scan",
                label="open_phase",
                scheduled_time=slots.get("open_phase"),
                timezone=timezone,
                purpose="entry_scan",
                enabled=enabled,
            ),
            _schedule_item(
                slot_id="open_phase_buy_readiness",
                label="open_phase buy readiness",
                scheduled_time=slots.get("open_phase"),
                timezone=timezone,
                purpose="buy_readiness",
                enabled=enabled
                and bool(
                    runtime.get(
                        "kis_scheduler_buy_enabled",
                        runtime.get("kis_scheduler_allow_limited_auto_buy", False),
                    )
                ),
            ),
            _schedule_item(
                slot_id="midday_position_management",
                label="midday",
                scheduled_time=slots.get("midday"),
                timezone=timezone,
                purpose="position_management",
                enabled=enabled,
            ),
            _schedule_item(
                slot_id="before_close_stop_loss_check",
                label="before_close stop-loss",
                scheduled_time=slots.get("before_close"),
                timezone=timezone,
                purpose="stop_loss_check",
                enabled=enabled
                and bool(runtime.get("kis_scheduler_allow_limited_auto_sell", False)),
            ),
            _schedule_item(
                slot_id="before_close_take_profit_check",
                label="before_close take-profit",
                scheduled_time=slots.get("before_close"),
                timezone=timezone,
                purpose="take_profit_check",
                enabled=enabled
                and bool(runtime.get("kis_scheduler_allow_limited_auto_sell", False)),
            ),
            _schedule_item(
                slot_id="force_manage_sell_readiness",
                label="sell readiness",
                scheduled_time=force_manage_until or slots.get("before_close"),
                timezone=timezone,
                purpose="sell_readiness",
                enabled=enabled
                and bool(runtime.get("kis_scheduler_allow_limited_auto_sell", False)),
            ),
        ]
        next_slot, current_slot = _slot_state(items, now_utc=now_utc, timezone=timezone)
        return items, next_slot, current_slot

    def _modules(
        self,
        db: Session,
        *,
        runtime: dict[str, Any],
        include_raw: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        static_runtime = _StaticRuntimeSettings(runtime)
        diagnostics: dict[str, Any] = {"modules_included": True, "module_errors": []}
        modules: dict[str, Any] = {}

        try:
            sell_service = self._limited_auto_sell_service or KisLimitedAutoSellService(
                self.client,
                runtime_settings=static_runtime,
                session_service=self.session_service,
            )
            sell_status = sell_service.status(db)
            modules["limited_auto_sell"] = _limited_auto_sell_module(
                sell_status,
                runtime=runtime,
                include_raw=include_raw,
            )
        except Exception as exc:
            diagnostics["module_errors"].append(
                {"module": "limited_auto_sell", "error": _safe_error(exc)}
            )
            modules["limited_auto_sell"] = _unavailable_module(
                "/kis/limited-auto-sell/status",
                reason="limited_auto_sell_status_unavailable",
            )

        try:
            buy_service = self._limited_auto_buy_service or KisLimitedAutoBuyService(
                self.client,
                runtime_settings=static_runtime,
                session_service=self.session_service,
            )
            buy_status = buy_service.status(db)
            modules["limited_auto_buy"] = _limited_auto_buy_module(
                buy_status,
                runtime=runtime,
                include_raw=include_raw,
            )
        except Exception as exc:
            diagnostics["module_errors"].append(
                {"module": "limited_auto_buy", "error": _safe_error(exc)}
            )
            modules["limited_auto_buy"] = _unavailable_module(
                "/kis/limited-auto-buy/status",
                reason="limited_auto_buy_status_unavailable",
            )

        modules["portfolio_position_management"] = {
            "available": True,
            "read_only": True,
            "status_endpoint": "/kis/positions/manage",
            "ready_for_scheduler_dry_run": True,
            "ready_for_scheduler_real_order": False,
            "block_reasons": [],
        }
        modules["execution_review"] = {
            "available": True,
            "read_only": True,
            "status_endpoint": "/kis/limited-auto-buy/execution-review",
            "ready_for_scheduler_dry_run": True,
            "ready_for_scheduler_real_order": False,
            "block_reasons": [],
        }
        return modules, diagnostics


class _StaticRuntimeSettings:
    def __init__(self, runtime: dict[str, Any]):
        self.runtime = dict(runtime)

    def get_settings(self, db: Session) -> dict[str, Any]:
        return dict(self.runtime)


def _scheduler_settings(settings: Any, runtime: dict[str, Any]) -> dict[str, bool]:
    configured_allow = bool(
        getattr(settings, "kis_scheduler_allow_real_orders", False)
        or getattr(settings, "kr_scheduler_allow_real_orders", False)
        or runtime.get("kis_scheduler_configured_allow_real_orders", False)
    )
    runtime_allow = bool(runtime.get("kis_scheduler_allow_real_orders", False))
    return {
        "scheduler_enabled": bool(runtime.get("scheduler_enabled", False)),
        "kis_scheduler_enabled": bool(runtime.get("kis_scheduler_enabled", False)),
        "kis_scheduler_dry_run": bool(runtime.get("kis_scheduler_dry_run", True)),
        "configured_kis_scheduler_allow_real_orders": configured_allow,
        "runtime_kis_scheduler_allow_real_orders": runtime_allow,
        "scheduler_real_orders_enabled": False,
        "kis_scheduler_live_enabled": bool(
            runtime.get("kis_scheduler_live_enabled", False)
        ),
        "kis_scheduler_allow_limited_auto_buy": bool(
            runtime.get("kis_scheduler_allow_limited_auto_buy", False)
        ),
        "kis_scheduler_buy_enabled": bool(
            runtime.get("kis_scheduler_buy_enabled", False)
        ),
        "kis_scheduler_allow_limited_auto_sell": bool(
            runtime.get("kis_scheduler_allow_limited_auto_sell", False)
        ),
        "kis_enabled": bool(getattr(settings, "kis_enabled", False)),
        "kis_real_order_enabled": bool(
            getattr(settings, "kis_real_order_enabled", False)
        ),
    }


def _block_reasons(
    *,
    runtime: dict[str, Any],
    scheduler: dict[str, bool],
    market_session: dict[str, Any],
    market_session_unknown: bool,
    runtime_source: str,
    modules: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if bool(runtime.get("kill_switch", False)):
        reasons.append("kill_switch_enabled")
    if market_session_unknown:
        reasons.append("unknown_market_session")
    if runtime_source == "missing_runtime_row":
        reasons.append("scheduler_config_missing")
    if not scheduler["scheduler_enabled"]:
        reasons.append("scheduler_disabled")
    if not scheduler["kis_scheduler_enabled"]:
        reasons.append("kis_scheduler_disabled")
    if market_session.get("enabled_for_scheduler") is not True:
        reasons.append("kr_scheduler_session_disabled")
    if bool(runtime.get("dry_run", True)):
        reasons.append("runtime_dry_run_true")
    if not scheduler["configured_kis_scheduler_allow_real_orders"]:
        reasons.append("kis_scheduler_allow_real_orders_false")
    if not scheduler["runtime_kis_scheduler_allow_real_orders"]:
        reasons.append("runtime_kis_scheduler_allow_real_orders_false")
    reasons.append("scheduler_real_orders_disabled")
    if not scheduler["kis_scheduler_live_enabled"]:
        reasons.append("kis_scheduler_live_disabled")
    if not (
        scheduler["kis_scheduler_buy_enabled"]
        or scheduler["kis_scheduler_allow_limited_auto_buy"]
        or scheduler["kis_scheduler_allow_limited_auto_sell"]
    ):
        reasons.append("scheduler_limited_auto_paths_disabled")
    if not scheduler["kis_enabled"]:
        reasons.append("kis_disabled")
    if not scheduler["kis_real_order_enabled"]:
        reasons.append("kis_real_order_disabled")
    if market_session_unknown is False and market_session.get("is_market_open") is not True:
        reasons.append("market_closed")
    if (
        market_session_unknown is False
        and market_session.get("is_entry_allowed_now") is not True
    ):
        reasons.append("entry_not_allowed_now")
    for name in ("limited_auto_buy", "limited_auto_sell"):
        module = modules.get(name)
        if isinstance(module, dict) and module.get("available") is not True:
            reasons.append(f"{name}_unavailable")
    return _dedupe(reasons)


def _readiness_status(
    block_reasons: list[str],
    *,
    scheduler: dict[str, bool],
    modules: dict[str, Any],
) -> str:
    if "kill_switch_enabled" in block_reasons or "unknown_market_session" in block_reasons:
        return "BLOCKED"
    if (
        "scheduler_config_missing" in block_reasons
        or not scheduler["scheduler_enabled"]
        or not scheduler["kis_scheduler_enabled"]
        or "kr_scheduler_session_disabled" in block_reasons
    ):
        return "DISABLED"
    if modules and not any(
        isinstance(module, dict) and module.get("available") is True
        for module in modules.values()
    ):
        return "REVIEW_REQUIRED"
    if scheduler["kis_scheduler_dry_run"]:
        return "READY_FOR_DRY_RUN"
    return "REVIEW_REQUIRED" if block_reasons else "READY_FOR_DRY_RUN"


def _schedule_item(
    *,
    slot_id: str,
    label: str,
    scheduled_time: str | None,
    timezone: str,
    purpose: str,
    enabled: bool,
) -> dict[str, Any]:
    return {
        "slot_id": slot_id,
        "label": label,
        "scheduled_time": scheduled_time,
        "timezone": timezone,
        "purpose": purpose,
        "enabled": bool(enabled),
        "real_order_allowed": False,
        "dry_run_only": True,
        "notes": [
            "readiness_only",
            "real_order_allowed_false",
            "scheduler_would_call_readiness_only",
        ],
    }


def _slot_state(
    items: list[dict[str, Any]],
    *,
    now_utc: datetime,
    timezone: str,
) -> tuple[dict[str, Any] | None, str | None]:
    local_now = now_utc.astimezone(ZoneInfo(timezone))
    current_minutes = local_now.hour * 60 + local_now.minute
    timed_items = []
    current_label = None
    for item in items:
        minutes = _minutes_from_time(item.get("scheduled_time"))
        if minutes is None:
            continue
        timed_items.append((minutes, item))
        if minutes == current_minutes:
            current_label = str(item.get("label") or item.get("slot_id"))
    timed_items.sort(key=lambda value: value[0])
    for minutes, item in timed_items:
        if minutes >= current_minutes:
            return item, current_label
    return (timed_items[0][1] if timed_items else None), current_label


def _limited_auto_sell_module(
    status: dict[str, Any],
    *,
    runtime: dict[str, Any],
    include_raw: bool,
) -> dict[str, Any]:
    safety = _dynamic_map(status.get("safety"))
    daily_limit = _dynamic_map(status.get("daily_limit"))
    block_reasons = _string_list(status.get("block_reasons"))
    stop_loss_enabled = _bool(
        status.get("stop_loss_execution_enabled"),
        status.get("stop_loss_auto_sell_enabled"),
        safety.get("stop_loss_execution_enabled"),
        runtime.get("kis_limited_auto_sell_stop_loss_enabled"),
    )
    take_profit_enabled = _bool(
        status.get("take_profit_execution_enabled"),
        status.get("take_profit_auto_sell_enabled"),
        safety.get("take_profit_execution_enabled"),
        runtime.get("kis_limited_auto_sell_take_profit_enabled"),
    )
    module = {
        "available": True,
        "status_endpoint": "/kis/limited-auto-sell/status",
        "stop_loss_execution_enabled": stop_loss_enabled,
        "take_profit_execution_enabled": take_profit_enabled,
        "live_auto_sell_enabled": _bool(
            status.get("live_auto_sell_enabled"),
            runtime.get("kis_live_auto_sell_enabled"),
        ),
        "dry_run": _bool(status.get("dry_run"), runtime.get("dry_run", True)),
        "daily_limit_remaining": _int_or_none(
            status.get("daily_limit_remaining")
            or daily_limit.get("daily_limit_remaining")
        ),
        "ready_for_scheduler_dry_run": bool(
            not runtime.get("kill_switch", False)
            and (stop_loss_enabled or status.get("take_profit_readiness_enabled") is True)
        ),
        "ready_for_scheduler_real_order": False,
        "block_reasons": block_reasons,
    }
    if include_raw:
        module["raw_status"] = status
    return module


def _limited_auto_buy_module(
    status: dict[str, Any],
    *,
    runtime: dict[str, Any],
    include_raw: bool,
) -> dict[str, Any]:
    safety = _dynamic_map(status.get("safety"))
    block_reasons = _string_list(status.get("block_reasons"))
    module = {
        "available": True,
        "status_endpoint": "/kis/limited-auto-buy/status",
        "auto_buy_execution_enabled": _bool(
            status.get("auto_buy_enabled"),
            safety.get("auto_buy_execution_enabled"),
            runtime.get("kis_limited_auto_buy_enabled"),
        ),
        "live_auto_buy_enabled": _bool(
            status.get("live_auto_buy_enabled"),
            runtime.get("kis_live_auto_buy_enabled"),
        ),
        "dry_run": _bool(status.get("dry_run"), runtime.get("dry_run", True)),
        "daily_limit_remaining": _int_or_none(
            status.get("daily_buy_limit_remaining")
        ),
        "ready_for_scheduler_dry_run": bool(
            not runtime.get("kill_switch", False)
            and status.get("buy_readiness_enabled") is not False
        ),
        "ready_for_scheduler_real_order": False,
        "block_reasons": block_reasons,
    }
    if include_raw:
        module["raw_status"] = status
    return module


def _unavailable_module(endpoint: str, *, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "status_endpoint": endpoint,
        "ready_for_scheduler_dry_run": False,
        "ready_for_scheduler_real_order": False,
        "daily_limit_remaining": None,
        "block_reasons": [reason],
    }


def _daily_limits(
    db: Session,
    *,
    runtime: dict[str, Any],
    now_utc: datetime,
) -> dict[str, Any]:
    start_utc, end_utc = _kr_day_bounds_utc(now_utc)
    buy_count = _daily_side_count(db, side="buy", start_utc=start_utc, end_utc=end_utc)
    sell_count = _daily_side_count(db, side="sell", start_utc=start_utc, end_utc=end_utc)
    buy_limit = max(0, int(runtime.get("kis_limited_auto_buy_max_orders_per_day", 1) or 0))
    sell_limit = max(
        0,
        int(runtime.get("kis_limited_auto_sell_max_orders_per_day", 1) or 0),
    )
    scheduler_limit = max(
        0,
        int(runtime.get("kis_scheduler_max_live_orders_per_day", 2) or 0),
    )
    return {
        "buy": {
            "used": buy_count,
            "limit": buy_limit,
            "remaining": max(0, buy_limit - buy_count),
            "already_used": buy_count >= buy_limit if buy_limit > 0 else True,
        },
        "sell": {
            "used": sell_count,
            "limit": sell_limit,
            "remaining": max(0, sell_limit - sell_count),
            "already_used": sell_count >= sell_limit if sell_limit > 0 else True,
        },
        "scheduler_live": {
            "used": buy_count + sell_count,
            "limit": scheduler_limit,
            "remaining": max(0, scheduler_limit - buy_count - sell_count),
            "already_used": (buy_count + sell_count) >= scheduler_limit
            if scheduler_limit > 0
            else True,
        },
    }


def _daily_side_count(
    db: Session,
    *,
    side: str,
    start_utc: datetime,
    end_utc: datetime,
) -> int:
    return int(
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.side == side)
        .filter(OrderLog.created_at >= start_utc)
        .filter(OrderLog.created_at < end_utc)
        .filter(
            or_(
                OrderLog.internal_status.in_(sorted(LIVE_STATUSES)),
                OrderLog.broker_status.in_(["submitted", "filled"]),
            )
        )
        .count()
        or 0
    )


def _recent_scheduler_runs(db: Session, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        db.query(TradeRunLog)
        .filter(
            or_(
                TradeRunLog.trigger_source.like("%scheduler%"),
                TradeRunLog.mode.like("%scheduler%"),
                TradeRunLog.trigger_source.like("%preflight%"),
                TradeRunLog.mode.like("%preflight%"),
                TradeRunLog.trigger_source.like("%limited_auto%"),
                TradeRunLog.mode.like("%limited_auto%"),
            )
        )
        .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
        .limit(limit)
        .all()
    )
    return [_serialize_recent_run(row) for row in rows]


def _serialize_recent_run(row: TradeRunLog) -> dict[str, Any]:
    response_payload = _parse_json_object(row.response_payload)
    request_payload = _parse_json_object(row.request_payload)
    merged = {**request_payload, **response_payload}
    block_reasons = _string_list(
        merged.get("block_reasons")
        or merged.get("blocked_by")
        or merged.get("failed_checks")
    )
    if not block_reasons and str(row.result or "").lower() in {"blocked", "skipped"}:
        block_reasons = _string_list(row.reason)
    return sanitize_kis_payload(
        {
            "created_at": row.created_at,
            "trigger_source": row.trigger_source,
            "mode": row.mode,
            "result": row.result,
            "symbol": row.symbol,
            "action": str(merged.get("action") or "hold"),
            "real_order_submitted": merged.get("real_order_submitted") is True,
            "broker_submit_called": merged.get("broker_submit_called") is True,
            "manual_submit_called": merged.get("manual_submit_called") is True,
            "block_reasons": block_reasons,
        }
    )


def _public_market_session(market_session: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "market",
        "timezone",
        "is_market_open",
        "is_entry_allowed_now",
        "is_near_close",
        "closure_reason",
        "closure_name",
        "is_holiday",
        "regular_open",
        "regular_close",
        "effective_close",
        "no_new_entry_after",
        "local_time",
        "enabled_for_scheduler",
        "error",
    ]
    return {key: market_session.get(key) for key in keys if key in market_session}


def _runtime_defaults_safe(runtime: dict[str, Any], scheduler: dict[str, bool]) -> bool:
    return all(
        [
            bool(runtime.get("dry_run", True)),
            not bool(runtime.get("kis_live_auto_buy_enabled", False)),
            not bool(runtime.get("kis_live_auto_sell_enabled", False)),
            not bool(runtime.get("kis_limited_auto_buy_enabled", False)),
            not bool(runtime.get("kis_limited_auto_sell_enabled", False)),
            not scheduler["runtime_kis_scheduler_allow_real_orders"],
            not scheduler["scheduler_real_orders_enabled"],
        ]
    )


def _sell_session_allowed(market_session: dict[str, Any]) -> bool:
    closure_reason = str(market_session.get("closure_reason") or "")
    is_holiday = bool(market_session.get("is_holiday")) or closure_reason.startswith(
        "holiday_"
    )
    return market_session.get("is_market_open") is True and not is_holiday


def _minutes_from_time(value: Any) -> int | None:
    try:
        hour_text, minute_text = str(value or "").split(":", 1)
        parsed = time(hour=int(hour_text), minute=int(minute_text))
        return parsed.hour * 60 + parsed.minute
    except Exception:
        return None


def _kr_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    local = now_utc.astimezone(KR_TZ)
    start_local = datetime.combine(local.date(), time.min, tzinfo=KR_TZ)
    end_local = start_local + timedelta(days=1)
    return _naive_utc(start_local), _naive_utc(end_local)


def _utc_now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    return _utc_now(value).replace(tzinfo=None)


def _coerce_like(value: Any, default_value: Any) -> Any:
    if isinstance(default_value, bool):
        return bool(value)
    if isinstance(default_value, int) and not isinstance(default_value, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default_value
    if isinstance(default_value, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default_value
    return str(value) if isinstance(default_value, str) else value


def _dynamic_map(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _bool(*values: Any) -> bool:
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        text = str(value).strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
    return False


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_json_object(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 180:
        text = f"{text[:180]}..."
    return f"{exc.__class__.__name__}: {text}"
