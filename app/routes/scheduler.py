from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.database import get_db
from app.services.market_profile_service import MarketProfileService
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/status")
def get_scheduler_status(db: Session = Depends(get_db)):
    settings = get_settings()
    session_service = MarketSessionService()
    profile_service = MarketProfileService()
    runtime = RuntimeSettingService().get_settings(db)

    sessions = {item["market"]: item for item in session_service.list_sessions()}
    profiles = {item["market"]: item for item in profile_service.list_profiles()}

    us = sessions.get("US", {})
    kr = sessions.get("KR", {})
    kr_profile = profiles.get("KR", {})
    runtime_state = RuntimeSettingService().get_kis_scheduler_runtime_state(db)
    kr_scheduler_enabled = bool(runtime_state["kis_scheduler_enabled"])
    kr_scheduler_dry_run = bool(runtime_state["kis_scheduler_dry_run"])
    kr_scheduler_allow_real_orders = bool(
        runtime_state["kis_scheduler_allow_real_orders"]
    )
    kr_scheduler_configured_allow_real_orders = bool(
        runtime_state["kis_scheduler_configured_allow_real_orders"]
    )
    kr_session_enabled = bool(kr.get("enabled_for_scheduler", False))
    kr_live_order_prereqs_met = all(
        [
            runtime_state["real_orders_allowed"],
            bool(runtime_state["kis_enabled"]),
            bool(runtime_state["kis_real_order_enabled"]),
            bool(runtime_state["scheduler_enabled"]),
            kr_session_enabled,
            bool(kr_profile.get("enabled_for_trading", False)),
        ]
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

    kr_live_scheduler_enabled_effective = real_order_scheduler_enabled

    kr_dry_run_scheduler_enabled_effective = bool(
        runtime_state["scheduler_enabled"]
        and kr_scheduler_enabled
        and kr_scheduler_dry_run
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

        if not kr_live_scheduler_enabled_effective and not kr_dry_run_scheduler_enabled_effective:
            kr_enabled_for_scheduler_block_reasons.append("no_kr_scheduler_mode_enabled")

        if not kr_live_scheduler_enabled_effective:
            if not kis_scheduler_live_enabled:
                kr_enabled_for_scheduler_block_reasons.append("kis_scheduler_live_disabled")
            if kr_scheduler_dry_run:
                kr_enabled_for_scheduler_block_reasons.append("kis_scheduler_dry_run_true")
            if not kr_scheduler_allow_real_orders:
                kr_enabled_for_scheduler_block_reasons.append(
                    "kis_scheduler_allow_real_orders_false"
              )
            if not kr_scheduler_configured_allow_real_orders:
                kr_enabled_for_scheduler_block_reasons.append(
                    "configured_allow_real_orders_false"
              )

    return {
        "runtime_scheduler_enabled": bool(runtime_state["scheduler_enabled"]),
        "US": {
            "enabled_for_scheduler": bool(us.get("enabled_for_scheduler", False)),
            "timezone": us.get("timezone", "America/New_York"),
            "slots": us.get("entry_slots", []),
        },
        "KR": {
            "enabled_for_scheduler": kr_enabled_for_scheduler,
            "kr_scheduler_any_enabled": kr_scheduler_any_enabled,
            "kr_live_scheduler_enabled_effective": kr_live_scheduler_enabled_effective,
            "kr_dry_run_scheduler_enabled_effective": kr_dry_run_scheduler_enabled_effective,
            "enabled_for_scheduler_block_reasons": kr_enabled_for_scheduler_block_reasons,
            "timezone": kr.get("timezone", "Asia/Seoul"),
            "slots": kr.get("entry_slots", []),
            "preview_only": True,
            "simulation_first": True,
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
            "real_order_scheduler_enabled": bool(
                runtime_state["real_order_scheduler_enabled"]
            ),
        },
    }
