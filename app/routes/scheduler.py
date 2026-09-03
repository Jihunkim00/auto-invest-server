from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.database import get_db
from app.db.models import PositionLifecycle, TradeRunLog
from app.services.automation_profile_service import AutomationProfileService
from app.services.market_session_service import MarketSessionService
from app.services.operation_test3_position_management_service import (
    SCHEDULER_SLOTS_KST,
    SCHEDULER_TRIGGER_SOURCE,
    TRADE_RUN_PREFLIGHT_MODE,
    TRADE_RUN_RUN_MODE,
)
from app.services.automation_execution_authority_service import (
    AutomationExecutionAuthorityService,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.scheduler_service import scheduler_service

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


_CANONICAL_IGNORED_KIS_SCHEDULER_FLAGS = (
    "kis_scheduler_enabled",
    "kis_scheduler_live_enabled",
    "kis_scheduler_allow_real_orders",
    "kr_scheduler_enabled",
    "kr_scheduler_allow_real_orders",
    "kis_scheduler_buy_enabled",
    "kis_scheduler_sell_enabled",
    "kis_scheduler_allow_limited_auto_buy",
    "kis_scheduler_allow_limited_auto_sell",
    "scheduler_real_orders_disabled",
    "kr_scheduler_session_disabled",
)


def _canonical_scheduler_state(
    *,
    runtime: dict[str, Any],
    authority: dict[str, Any],
    profile_schedule: dict[str, Any] | None,
    scheduler_runtime: dict[str, Any],
    app_settings: Any,
) -> dict[str, Any]:
    profile = (profile_schedule or {}).get("profile") or {}
    profile_is_kis_kr = (
        str(profile.get("provider") or "").lower() == "kis"
        and str(profile.get("market") or "").upper() == "KR"
    )
    profile_active = bool(
        profile_schedule
        and profile_schedule.get("status") == "active"
        and profile.get("enabled") is True
        and profile_is_kis_kr
    )
    scheduler_registered = bool(
        scheduler_runtime.get("scheduler_authority")
        == "AutomationSchedulerService"
        and int(scheduler_runtime.get("production_trading_job_count") or 0) == 1
    )
    mode = str(authority.get("automation_mode") or "off").lower()
    canonical_active = bool(
        scheduler_registered
        and runtime.get("automation_profile_scheduler_enabled")
        and authority.get("scheduler_allowed")
        and profile_active
    )
    live_order_submission_enabled = bool(
        canonical_active
        and mode == "live"
        and authority.get("broker_submit_allowed")
        and not runtime.get("dry_run")
        and not runtime.get("kill_switch")
        and getattr(app_settings, "kis_enabled", False)
        and getattr(app_settings, "kis_real_order_enabled", False)
    )
    return {
        "scheduler": "AutomationSchedulerService",
        "authority": "AutomationSchedulerService",
        "registered": scheduler_registered,
        "active": canonical_active,
        "enabled": canonical_active,
        "mode": mode,
        "profile_key": profile_schedule.get("profile_key") if profile_schedule else None,
        "scheduler_allowed": bool(authority.get("scheduler_allowed")),
        "broker_submit_allowed": bool(authority.get("broker_submit_allowed")),
        "live_order_submission_enabled": live_order_submission_enabled,
        "legacy_readiness_diagnostic_only": True,
        "legacy_kis_scheduler_flags_ignored": list(
            _CANONICAL_IGNORED_KIS_SCHEDULER_FLAGS
        ),
        "blocking_reasons": [] if canonical_active else [
            "canonical_scheduler_inactive"
        ],
        "live_order_blocking_reasons": (
            []
            if live_order_submission_enabled
            else [
                reason
                for reason, blocked in (
                    ("automation_mode_not_live", mode != "live"),
                    ("dry_run_true", bool(runtime.get("dry_run"))),
                    ("kill_switch_enabled", bool(runtime.get("kill_switch"))),
                    (
                        "kis_disabled",
                        not bool(getattr(app_settings, "kis_enabled", False)),
                    ),
                    (
                        "kis_real_order_disabled",
                        not bool(
                            getattr(app_settings, "kis_real_order_enabled", False)
                        ),
                    ),
                )
                if blocked
            ]
        ),
    }


@router.get("/status")
def get_scheduler_status(db: Session = Depends(get_db)):
    app_settings = get_settings()
    session_service = MarketSessionService()
    runtime_service = RuntimeSettingService()

    sessions = {item["market"]: item for item in session_service.list_sessions()}

    us = sessions.get("US", {})
    kr = sessions.get("KR", {})
    runtime_state = runtime_service.get_kis_scheduler_runtime_state_read_only(db)
    kr_scheduler_enabled = bool(runtime_state["kis_scheduler_enabled"])
    kr_scheduler_dry_run = bool(runtime_state["kis_scheduler_dry_run"])
    kr_scheduler_allow_real_orders = bool(
        runtime_state["kis_scheduler_allow_real_orders"]
    )
    kr_scheduler_configured_allow_real_orders = bool(
        runtime_state["kis_scheduler_configured_allow_real_orders"]
    )
    kis_scheduler_live_enabled = bool(runtime_state["kis_scheduler_live_enabled"])
    kis_scheduler_allow_limited_auto_buy = bool(
        runtime_state["kis_scheduler_allow_limited_auto_buy"]
    )
    kis_scheduler_allow_limited_auto_sell = bool(
        runtime_state["kis_scheduler_allow_limited_auto_sell"]
    )
    live_scheduler_ready = bool(runtime_state["live_scheduler_ready"])
    real_orders_allowed = bool(runtime_state["real_orders_allowed"])
    real_order_scheduler_enabled = bool(runtime_state["real_order_scheduler_enabled"])
    us_next_slot = _next_slot(
        us.get("entry_slots", []),
        str(us.get("timezone", "America/New_York")),
    )
    kr_next_slot = _next_slot(
        kr.get("entry_slots", []),
        str(kr.get("timezone", "Asia/Seoul")),
    )
    us_last_run = _latest_scheduler_run(db, market="US")
    kr_last_run = _latest_scheduler_run(db, market="KR")
    runtime_settings = runtime_service.get_settings_read_only(db)
    automation_profiles = AutomationProfileService(runtime_settings=runtime_service)
    profile_state = automation_profiles.list_profiles(db)
    selected_profile = profile_state.get("selected_profile") or {}
    active_profile = profile_state.get("active_profile") or {}
    selected_profile_status = profile_state.get("selected_profile_status")
    profile_schedule = automation_profiles.selected_profile_schedule(db)
    scheduler_runtime = scheduler_service.runtime_status()
    canonical_authority = AutomationExecutionAuthorityService(
        runtime_service
    ).snapshot(db)
    canonical_scheduler = _canonical_scheduler_state(
        runtime=runtime_settings,
        authority=canonical_authority,
        profile_schedule=profile_schedule,
        scheduler_runtime=scheduler_runtime,
        app_settings=app_settings,
    )
    profile_effective_settings = selected_profile.get("effective_settings")
    if not isinstance(profile_effective_settings, dict):
        profile_effective_settings = selected_profile.get("settings") or {}
    profile_entry = profile_effective_settings.get("entry")
    if not isinstance(profile_entry, dict):
        profile_entry = {}
    profile_analysis_times = list(
        (profile_schedule or {}).get("analysis_times")
        or profile_entry.get("analysis_times")
        or []
    )
    effective_profile_analysis_times = list(
        profile_entry.get("analysis_times") or profile_analysis_times
    )
    profile_no_new_entry_after = str(
        profile_entry.get("no_new_entry_after") or "14:00"
    )
    profile_next_run_at = (profile_schedule or {}).get("next_run_at")
    profile_next_slot = _profile_next_slot(profile_next_run_at)
    kr_risk_summary = runtime_service.get_kis_risk_summary_read_only(db)
    legacy_risk_summary = kr_risk_summary
    current_operation_mode = runtime_service.current_operation_mode_read_only(db)
    legacy_current_operation_mode = current_operation_mode
    daily_live_order_remaining = kr_risk_summary.get("daily_live_order_remaining")
    daily_live_order_limit = kr_risk_summary.get("daily_live_order_limit")
    daily_order_count = (
        max(0, int(daily_live_order_limit) - int(daily_live_order_remaining))
        if daily_live_order_limit is not None and daily_live_order_remaining is not None
        else 0
    )
    active_position_count = db.query(PositionLifecycle).filter(
        PositionLifecycle.status.in_(["open", "closing"])
    ).count()
    live_order_remaining_ok = (
        daily_live_order_remaining is None or int(daily_live_order_remaining) > 0
    )
    live_buy_possible = bool(
        kr_risk_summary.get("live_buy_armed") and live_order_remaining_ok
    )
    live_sell_possible = bool(
        kr_risk_summary.get("live_sell_armed") and live_order_remaining_ok
    )
    user_friendly_summary = _user_friendly_summary(
        current_operation_mode,
        kr_risk_summary,
    )
    warning_message = _warning_message(current_operation_mode, kr_risk_summary)
    warning_level = str(kr_risk_summary.get("warning_level") or "safe")

    kr_live_scheduler_enabled_effective = real_order_scheduler_enabled
    us_no_new_entry_after = str(
        us.get("no_new_entry_after")
        or runtime_settings.get("us_no_new_entry_after")
        or "15:45"
    )
    kr_no_new_entry_after = str(
        runtime_settings.get("kr_no_new_entry_after")
        or runtime_settings.get("kis_limited_auto_buy_no_new_entry_after")
        or "14:50"
    )
    legacy_kr_no_new_entry_after = kr_no_new_entry_after
    legacy_kr_next_slot = dict(kr_next_slot)
    effective_kr_next_slot = kr_next_slot
    if canonical_scheduler["active"]:
        kr_no_new_entry_after = profile_no_new_entry_after
        effective_kr_next_slot = profile_next_slot

    kr_dry_run_scheduler_enabled_effective = bool(
        runtime_state["scheduler_enabled"]
        and kr_scheduler_enabled
        and kr_scheduler_dry_run
    )

    operation_test3 = _operation_test3_summary(
        db,
        runtime_settings=runtime_settings,
        runtime_state=runtime_state,
    )

    kr_scheduler_any_enabled = bool(
        kr_live_scheduler_enabled_effective
        or kr_dry_run_scheduler_enabled_effective
    )

    kr_enabled_for_scheduler = bool(
        runtime_state["scheduler_enabled"]
        and kr_scheduler_any_enabled
    )
    kr_enabled_for_scheduler_block_reasons: list[str] = []

    if not kr_enabled_for_scheduler:
        if not bool(runtime_state["scheduler_enabled"]):
            kr_enabled_for_scheduler_block_reasons.append("runtime_scheduler_disabled")

        if not kr_scheduler_enabled:
            kr_enabled_for_scheduler_block_reasons.append("kis_scheduler_disabled")

        if (
            not kr_live_scheduler_enabled_effective
            and not kr_dry_run_scheduler_enabled_effective
        ):
            kr_enabled_for_scheduler_block_reasons.append("no_kr_scheduler_mode_enabled")

        if not kr_live_scheduler_enabled_effective:
            if not kis_scheduler_live_enabled:
                kr_enabled_for_scheduler_block_reasons.append(
                    "kis_scheduler_live_disabled"
                )
            if kr_scheduler_dry_run:
                kr_enabled_for_scheduler_block_reasons.append(
                    "kis_scheduler_dry_run_true"
                )
            if bool(runtime_state["dry_run"]):
                kr_enabled_for_scheduler_block_reasons.append("runtime_dry_run_true")
            if bool(runtime_state["kill_switch"]):
                kr_enabled_for_scheduler_block_reasons.append("kill_switch_enabled")
            if not bool(runtime_state["kis_enabled"]):
                kr_enabled_for_scheduler_block_reasons.append("kis_api_disabled")
            if not bool(runtime_state["kis_real_order_enabled"]):
                kr_enabled_for_scheduler_block_reasons.append(
                    "kis_real_order_disabled"
                )
            if not kr_scheduler_allow_real_orders:
                kr_enabled_for_scheduler_block_reasons.append(
                    "kis_scheduler_allow_real_orders_false"
                )
            if not kr_scheduler_configured_allow_real_orders:
                kr_enabled_for_scheduler_block_reasons.append(
                    "configured_allow_real_orders_false"
                )
            if (
                not kis_scheduler_allow_limited_auto_buy
                and not kis_scheduler_allow_limited_auto_sell
            ):
                kr_enabled_for_scheduler_block_reasons.append(
                    "no_limited_auto_scheduler_path_enabled"
                )

    # The values above describe the historical KIS scheduler and are retained
    # for diagnostics. Once the canonical AutomationSchedulerService is
    # active, those values must not be allowed to become the effective KR
    # scheduler state shown by this compatibility endpoint.
    legacy_kr_scheduler_state = {
        "enabled_for_scheduler": kr_enabled_for_scheduler,
        "kr_scheduler_any_enabled": kr_scheduler_any_enabled,
        "kr_live_scheduler_enabled_effective": kr_live_scheduler_enabled_effective,
        "kr_dry_run_scheduler_enabled_effective": kr_dry_run_scheduler_enabled_effective,
        "real_orders_allowed": real_orders_allowed,
        "real_order_scheduler_enabled": real_order_scheduler_enabled,
        "live_scheduler_ready": live_scheduler_ready,
        "block_reasons": list(kr_enabled_for_scheduler_block_reasons),
        "schedule": {
            "slots": kr.get("entry_slots", []),
            "next_run": legacy_kr_next_slot,
            "no_new_entry_after": legacy_kr_no_new_entry_after,
        },
    }
    if canonical_scheduler["active"]:
        canonical_live = bool(canonical_scheduler["live_order_submission_enabled"])
        canonical_simulation = str(canonical_scheduler["mode"]) in {"test", "paper"}
        kr_live_scheduler_enabled_effective = canonical_live
        kr_dry_run_scheduler_enabled_effective = canonical_simulation
        kr_scheduler_any_enabled = True
        kr_enabled_for_scheduler = True
        kr_enabled_for_scheduler_block_reasons = []
        live_scheduler_ready = canonical_live
        real_orders_allowed = canonical_live
        real_order_scheduler_enabled = canonical_live
        live_buy_possible = canonical_live
        live_sell_possible = canonical_live
        if canonical_live:
            warning_level = "canonical_live"
            user_friendly_summary = (
                "Canonical AutomationSchedulerService is active for LIVE KIS "
                "automation. Legacy KIS scheduler readiness is diagnostic-only."
            )
            warning_message = (
                "Canonical AutomationSchedulerService is authoritative for LIVE "
                "KIS automation; legacy KIS scheduler flags are ignored."
            )
        else:
            warning_level = "canonical_active"
            user_friendly_summary = (
                "Canonical AutomationSchedulerService is active for canonical "
                f"{canonical_scheduler['mode'].upper()} KIS automation."
            )
            warning_message = (
                "Canonical AutomationSchedulerService is authoritative; legacy "
                "KIS scheduler readiness is diagnostic-only."
            )
        current_operation_mode = str(canonical_scheduler["mode"])
        kr_risk_summary = {
            **legacy_risk_summary,
            "live_buy_armed": canonical_live,
            "live_sell_armed": canonical_live,
            "blocking_flags": [],
            "warning_level": warning_level,
            "canonical_scheduler_active": True,
            "legacy_readiness_diagnostic_only": True,
        }

    return {
        **scheduler_runtime,
        "canonical_scheduler": canonical_scheduler,
        "canonical_scheduler_active": bool(canonical_scheduler["active"]),
        "canonical_automation_mode": canonical_scheduler["mode"],
        "legacy_kis_scheduler_state": {
            **legacy_kr_scheduler_state,
            "diagnostic_only": True,
        },
        "active_profile_key": active_profile.get("profile_key"),
        "active_profile_name": active_profile.get("name") or active_profile.get("display_name"),
        "active_profile_provider": active_profile.get("provider") or "kis",
        "active_profile_market": active_profile.get("market") or "KR",
        "active_profile_status": active_profile.get("status"),
        "selected_profile": selected_profile or None,
        "selected_profile_name": selected_profile.get("name") or selected_profile.get("display_name"),
        "selected_profile_provider": selected_profile.get("provider") or "kis",
        "selected_profile_market": selected_profile.get("market") or "KR",
        "selected_profile_start_date": (((selected_profile.get("effective_settings") or {}).get("operation") or {}).get("start_date")),
        "selected_profile_end_date": (((selected_profile.get("effective_settings") or {}).get("operation") or {}).get("end_date")),
        "selected_profile_status": selected_profile_status,
        "automation_selected": bool(profile_state.get("automation_selected")),
        "automation_enabled": bool(
            selected_profile.get("enabled")
            and selected_profile_status in {"scheduled", "active"}
        ),
        "profile_scheduler_enabled": bool(
            runtime_settings.get("automation_profile_scheduler_enabled")
            and selected_profile.get("enabled")
            and selected_profile_status in {"scheduled", "active"}
        ),
        "runtime_authorized": bool(real_orders_allowed),
        "daily_order_count": daily_order_count,
        "daily_order_limit": daily_live_order_limit,
        "active_position_count": int(active_position_count),
        "active_profile": active_profile or None,
        "legacy_current_operation_mode": legacy_current_operation_mode,
        "profile_analysis_times": profile_analysis_times,
        "effective_profile_analysis_times": effective_profile_analysis_times,
        "profile_no_new_entry_after": profile_no_new_entry_after,
        "profile_next_run_at": profile_next_run_at.isoformat() if profile_next_run_at is not None else None,
        "next_profile_run_at": profile_next_run_at.isoformat() if profile_next_run_at is not None else None,
        "display_next_run": _display_next_run(effective_kr_next_slot, "KST"),
        "profile_stop_loss_pct": (((profile_effective_settings.get("exit") or {}).get("stop_loss_pct"))),
        "profile_take_profit_pct": (((profile_effective_settings.get("exit") or {}).get("take_profit_pct"))),
        "current_operation_mode": current_operation_mode,
        "display_mode_label": (
            f"Canonical {current_operation_mode.upper()} Automation"
            if canonical_scheduler["active"]
            else _display_mode_label(current_operation_mode)
        ),
        "display_warning_level": warning_level,
        "user_friendly_summary": user_friendly_summary,
        "risk_summary": kr_risk_summary,
        "legacy_risk_summary": legacy_risk_summary,
        "global": {
            "scheduler_enabled": bool(
                runtime_state["scheduler_enabled"] or canonical_scheduler["active"]
            ),
            "dry_run": bool(runtime_state["dry_run"]),
            "kill_switch": bool(runtime_state["kill_switch"]),
            "safe_mode_active": bool(
                not canonical_scheduler["active"]
                and (
                    kr_risk_summary.get("safe_mode_active")
                    or current_operation_mode == "safe_mode"
                )
            ),
            "canonical_scheduler_active": bool(canonical_scheduler["active"]),
        },
        "alpaca": {
            "market": "US",
            "timezone": us.get("timezone", "America/New_York"),
            "scheduler_enabled": bool(
                runtime_state["scheduler_enabled"]
                and us.get("enabled_for_scheduler", False)
            ),
            "next_run": us_next_slot["time_local"],
            "next_slot_name": us_next_slot["name"],
            "no_new_entry_after": us_no_new_entry_after,
            "display_next_run": _display_next_run(us_next_slot, "ET"),
            "display_no_new_entry_after": f"{us_no_new_entry_after} ET",
            "live_order_possible": bool(
                not runtime_state["dry_run"] and not runtime_state["kill_switch"]
            ),
        },
        "kis": {
            "market": "KR",
            "timezone": kr.get("timezone", "Asia/Seoul"),
            "canonical_scheduler": canonical_scheduler,
            "canonical_scheduler_active": bool(canonical_scheduler["active"]),
            "scheduler_enabled": kr_enabled_for_scheduler,
            "next_run": effective_kr_next_slot["time_local"],
            "next_slot_name": effective_kr_next_slot["name"],
            "kr_no_new_entry_after": kr_no_new_entry_after,
            "profile_analysis_times": profile_analysis_times,
            "effective_profile_analysis_times": effective_profile_analysis_times,
            "profile_no_new_entry_after": profile_no_new_entry_after,
            "next_profile_run_at": profile_next_run_at.isoformat() if profile_next_run_at is not None else None,
            "display_next_run": _display_next_run(effective_kr_next_slot, "KST"),
            "display_no_new_entry_after": f"{kr_no_new_entry_after} KST",
            "live_buy_armed": bool(kr_risk_summary.get("live_buy_armed")),
            "live_sell_armed": bool(kr_risk_summary.get("live_sell_armed")),
            "live_buy_possible": live_buy_possible,
            "live_sell_possible": live_sell_possible,
            "warning_level": warning_level,
        },
        "next_run": {
            "US": us_next_slot,
            "KR": effective_kr_next_slot,
        },
        "live_order_possible": bool(live_buy_possible or live_sell_possible),
        "live_buy_possible": live_buy_possible,
        "live_sell_possible": live_sell_possible,
        "operation_test3": operation_test3,
        "daily_live_order_remaining": daily_live_order_remaining,
        "warning_message": warning_message,
        "runtime_scheduler_enabled": bool(
            runtime_state["scheduler_enabled"] or canonical_scheduler["active"]
        ),
        "US": {
            "enabled_for_scheduler": bool(us.get("enabled_for_scheduler", False)),
            "timezone": us.get("timezone", "America/New_York"),
            "slots": us.get("entry_slots", []),
            "market": "US",
            "broker": "alpaca",
            "no_new_entry_after": us_no_new_entry_after,
            "display_no_new_entry_after": f"{us_no_new_entry_after} ET",
            "next_slot_name": us_next_slot["name"],
            "next_slot_time_local": us_next_slot["time_local"],
            "display_next_run": _display_next_run(us_next_slot, "ET"),
            "last_scheduler_run_at": us_last_run["created_at"],
            "last_scheduler_run_result": us_last_run["result"],
            "last_scheduler_run_reason": us_last_run["reason"],
            "last_scheduler_run_id": us_last_run["id"],
        },
        "KR": {
            "enabled_for_scheduler": kr_enabled_for_scheduler,
            "canonical_scheduler": canonical_scheduler,
            "canonical_scheduler_active": bool(canonical_scheduler["active"]),
            "legacy_readiness_diagnostic_only": True,
            "legacy_enabled_for_scheduler": legacy_kr_scheduler_state[
                "enabled_for_scheduler"
            ],
            "legacy_enabled_for_scheduler_block_reasons": legacy_kr_scheduler_state[
                "block_reasons"
            ],
            "kr_scheduler_any_enabled": kr_scheduler_any_enabled,
            "kr_live_scheduler_enabled_effective": kr_live_scheduler_enabled_effective,
            "kr_dry_run_scheduler_enabled_effective": kr_dry_run_scheduler_enabled_effective,
            "enabled_for_scheduler_block_reasons": kr_enabled_for_scheduler_block_reasons,
            "timezone": kr.get("timezone", "Asia/Seoul"),
            "slots": profile_analysis_times if canonical_scheduler["active"] else kr.get("entry_slots", []),
            "market": "KR",
            "broker": "kis",
            "kr_no_new_entry_after": kr_no_new_entry_after,
            "no_new_entry_after": kr_no_new_entry_after,
            "profile_analysis_times": profile_analysis_times,
            "effective_profile_analysis_times": effective_profile_analysis_times,
            "profile_no_new_entry_after": profile_no_new_entry_after,
            "next_profile_run_at": profile_next_run_at.isoformat() if profile_next_run_at is not None else None,
            "display_no_new_entry_after": f"{kr_no_new_entry_after} KST",
            "next_slot_name": effective_kr_next_slot["name"],
            "next_slot_time_local": effective_kr_next_slot["time_local"],
            "display_next_run": _display_next_run(effective_kr_next_slot, "KST"),
            "last_scheduler_run_at": kr_last_run["created_at"],
            "last_scheduler_run_result": kr_last_run["result"],
            "last_scheduler_run_reason": kr_last_run["reason"],
            "last_scheduler_run_id": kr_last_run["id"],
            "last_scheduler_run_mode": kr_last_run["mode"],
            "last_scheduler_run_trigger_source": kr_last_run["trigger_source"],
            "preview_only": not bool(canonical_scheduler["active"]),
            "simulation_first": not bool(canonical_scheduler["active"]),
            "kis_scheduler_enabled": kr_scheduler_enabled,
            "kis_scheduler_dry_run": kr_scheduler_dry_run,
            "kis_scheduler_allow_real_orders": kr_scheduler_allow_real_orders,
            "kis_scheduler_configured_allow_real_orders": kr_scheduler_configured_allow_real_orders,
            "kis_scheduler_sell_enabled": bool(
                runtime_state["kis_scheduler_sell_enabled"]
            ),
            "kis_scheduler_buy_enabled": bool(
                runtime_state["kis_scheduler_buy_enabled"]
            ),
            "kis_scheduler_live_enabled": kis_scheduler_live_enabled,
            "kis_scheduler_allow_limited_auto_buy": kis_scheduler_allow_limited_auto_buy,
            "kis_scheduler_allow_limited_auto_sell": kis_scheduler_allow_limited_auto_sell,
            "kis_scheduler_max_live_orders_per_day": int(
                runtime_state["kis_scheduler_max_live_orders_per_day"]
            ),
            "live_scheduler_ready": live_scheduler_ready,
            "configured_live_order_prereqs_met": real_orders_allowed,
            "dry_run_validation_scheduler_enabled": kr_dry_run_scheduler_enabled_effective,
            "real_orders_allowed": real_orders_allowed,
            "real_order_scheduler_enabled": real_order_scheduler_enabled,
            "risk_summary": kr_risk_summary,
            "current_operation_mode": current_operation_mode,
            "user_friendly_summary": user_friendly_summary,
            "live_order_possible": bool(live_buy_possible or live_sell_possible),
            "live_buy_possible": live_buy_possible,
            "live_sell_possible": live_sell_possible,
            "live_buy_armed": bool(kr_risk_summary.get("live_buy_armed")),
            "live_sell_armed": bool(kr_risk_summary.get("live_sell_armed")),
            "daily_live_order_remaining": daily_live_order_remaining,
            "warning_message": warning_message,
        },
    }


def _operation_test3_summary(
    db: Session,
    *,
    runtime_settings: dict[str, Any],
    runtime_state: dict[str, Any],
) -> dict[str, Any]:
    enabled = bool(runtime_settings.get("operation_test3_enabled", False))
    scheduler_enabled = bool(runtime_settings.get("operation_test3_scheduler_enabled", False))
    position_management_enabled = bool(
        runtime_settings.get("operation_test3_position_management_enabled", False)
    )
    allow_real_orders = bool(runtime_settings.get("operation_test3_allow_real_orders", False))
    active_lifecycle_count = int(
        db.query(PositionLifecycle)
        .filter(PositionLifecycle.status.in_(["open", "closing"]))
        .count()
        or 0
    )
    next_run = _next_slot(
        [{"name": slot, "time": slot} for slot in SCHEDULER_SLOTS_KST],
        "Asia/Seoul",
    )
    latest_run = _latest_operation_test3_run(db)
    live_ready = bool(
        enabled
        and scheduler_enabled
        and position_management_enabled
        and allow_real_orders
        and not bool(runtime_settings.get("dry_run", True))
        and not bool(runtime_settings.get("kill_switch", False))
        and bool(runtime_state.get("kis_enabled", False))
        and bool(runtime_state.get("kis_real_order_enabled", False))
        and active_lifecycle_count == 1
    )
    return {
        "enabled": enabled,
        "scheduler_enabled": scheduler_enabled,
        "position_management_enabled": position_management_enabled,
        "allow_real_orders": allow_real_orders,
        "monitoring_only": bool(
            enabled
            and scheduler_enabled
            and position_management_enabled
            and not allow_real_orders
        ),
        "slots_kst": SCHEDULER_SLOTS_KST,
        "active_lifecycle_count": active_lifecycle_count,
        "next_run_kst": next_run["time_local"],
        "latest_run": _serialize_operation_test3_latest_run(latest_run),
        "live_ready": live_ready,
    }


def _latest_operation_test3_run(db: Session) -> TradeRunLog | None:
    return (
        db.query(TradeRunLog)
        .filter(
            or_(
                TradeRunLog.trigger_source == SCHEDULER_TRIGGER_SOURCE,
                TradeRunLog.mode.in_([TRADE_RUN_PREFLIGHT_MODE, TRADE_RUN_RUN_MODE]),
            )
        )
        .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
        .first()
    )


def _serialize_operation_test3_latest_run(row: TradeRunLog | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "trigger_source": row.trigger_source,
        "result": row.result,
        "reason": row.reason,
    }

def _user_friendly_summary(mode: str, risk_summary: dict[str, Any]) -> str:
    warning_level = str(risk_summary.get("warning_level") or "safe")
    if mode == "kis_sell_only_automation":
        return "KIS sell-only live automation is armed. Auto-buy is disabled."
    if mode == "full_live_test_mode":
        return "Full live test mode is armed. Live buy and live sell automation are enabled."
    if mode == "dry_run_simulation":
        return "Dry-run simulation is enabled. Scheduler checks can run without real orders."
    if mode == "manual_live_trading":
        return "Manual live trading is available while scheduler live orders are disabled."
    if warning_level == "blocked":
        blockers = ", ".join(risk_summary.get("blocking_flags") or [])
        return f"Live automation is requested but blocked: {blockers}."
    return "Safe mode is active. Scheduler live buy and sell automation are disabled."


def _warning_message(mode: str, risk_summary: dict[str, Any]) -> str:
    warning_level = str(risk_summary.get("warning_level") or "safe")
    if warning_level == "dangerous_mixed":
        return "LIVE BUY ARMED and LIVE SELL ARMED may be possible. Full live test mode is dangerous."
    if warning_level == "armed_sell_only":
        remaining = risk_summary.get("daily_live_order_remaining")
        remaining_text = "unknown" if remaining is None else str(remaining)
        return f"LIVE SELL ARMED. Auto-buy is disabled. Daily live orders remaining: {remaining_text}."
    if warning_level == "blocked":
        blockers = ", ".join(risk_summary.get("blocking_flags") or [])
        return f"Live automation is blocked by: {blockers}."
    if mode == "manual_live_trading":
        return "Manual KIS live order submit still requires explicit confirmation and backend validation."
    return "No scheduler live buy or sell automation is armed."


def _display_mode_label(mode: str) -> str:
    labels = {
        "safe_mode": "Safe Mode",
        "dry_run_simulation": "Dry-run Simulation",
        "manual_live_trading": "Manual Live Trading",
        "kis_sell_only_automation": "KIS Sell-only Automation",
        "full_live_test_mode": "Full Live Test Mode",
    }
    return labels.get(mode, mode)


def _display_next_run(slot: dict[str, str | None], timezone_label: str) -> str | None:
    time_local = slot.get("time_local")
    if not time_local:
        return None
    name = slot.get("name")
    prefix = f"{name} " if name else ""
    return f"{prefix}{time_local} {timezone_label}"


def _profile_next_slot(value: datetime | None) -> dict[str, str | None]:
    return {
        "name": "automation_profile" if value is not None else None,
        "time_local": value.isoformat(timespec="minutes") if value is not None else None,
    }


def _next_slot(slots: Any, timezone: str) -> dict[str, str | None]:
    parsed = _slot_items(slots)
    if not parsed:
        return {"name": None, "time_local": None}

    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo("UTC")

    now = datetime.now(tz)
    upcoming: list[tuple[datetime, str]] = []
    rollover: list[tuple[datetime, str]] = []
    for slot in parsed:
        name = slot["name"]
        time_text = slot["time"]
        hour, minute = _parse_slot_time(time_text)
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate >= now:
            upcoming.append((candidate, name))
        else:
            rollover.append((candidate + timedelta(days=1), name))

    candidate_time, name = min(upcoming or rollover, key=lambda item: item[0])
    return {
        "name": name,
        "time_local": candidate_time.isoformat(timespec="minutes"),
    }


def _slot_items(slots: Any) -> list[dict[str, str]]:
    if not isinstance(slots, list):
        return []
    items: list[dict[str, str]] = []
    for slot in slots:
        if isinstance(slot, dict):
            name = str(slot.get("name") or "").strip()
            time_text = str(slot.get("time") or "").strip()
        else:
            text = str(slot).strip()
            parts = text.split()
            name = parts[0] if parts else ""
            time_text = parts[-1] if len(parts) > 1 else ""
        if name and time_text:
            items.append({"name": name, "time": time_text})
    return items


def _parse_slot_time(value: str) -> tuple[int, int]:
    hour_text, minute_text = value.split(":", 1)
    return int(hour_text), int(minute_text)


def _latest_scheduler_run(db: Session, *, market: str) -> dict[str, Any]:
    rows = (
        db.query(TradeRunLog)
        .filter(
            or_(
                TradeRunLog.trigger_source.like("%scheduler%"),
                TradeRunLog.mode.like("%scheduler%"),
                TradeRunLog.request_payload.like("%scheduler_slot%"),
                TradeRunLog.response_payload.like("%scheduler_slot%"),
            )
        )
        .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
        .limit(100)
        .all()
    )

    for row in rows:
        request_payload = _parse_json_object(row.request_payload)
        response_payload = _parse_json_object(row.response_payload)
        if _infer_run_market(row, request_payload, response_payload) == market:
            return {
                "id": row.id,
                "created_at": row.created_at,
                "result": row.result,
                "reason": row.reason,
                "mode": row.mode,
                "trigger_source": row.trigger_source,
            }

    return {
        "id": None,
        "created_at": None,
        "result": None,
        "reason": None,
        "mode": None,
        "trigger_source": None,
    }


def _infer_run_market(
    row: TradeRunLog,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
) -> str:
    payload_market = _first_text(
        response_payload.get("market"),
        request_payload.get("market"),
    )
    if payload_market:
        return payload_market.upper()

    payload_provider = _first_text(
        response_payload.get("provider"),
        request_payload.get("provider"),
    )
    if payload_provider:
        return "KR" if payload_provider.lower() == "kis" else "US"

    hint = " ".join(
        [
            row.mode or "",
            row.trigger_source or "",
            row.run_key or "",
            row.symbol or "",
            json.dumps(request_payload, default=str),
            json.dumps(response_payload, default=str),
        ]
    ).lower()
    if "kis" in hint or '"market": "kr"' in hint or '"market":"kr"' in hint:
        return "KR"
    return "US"


def _parse_json_object(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None
