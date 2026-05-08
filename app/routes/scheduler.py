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
    kr_scheduler_enabled = bool(
        getattr(settings, "kis_scheduler_enabled", False)
        or getattr(settings, "kr_scheduler_enabled", False)
    )
    kr_scheduler_dry_run = bool(getattr(settings, "kis_scheduler_dry_run", True))
    kr_scheduler_allow_real_orders = bool(
        getattr(settings, "kis_scheduler_allow_real_orders", False)
        or getattr(settings, "kr_scheduler_allow_real_orders", False)
    )
    kr_live_order_prereqs_met = all(
        [
            kr_scheduler_allow_real_orders,
            bool(getattr(settings, "kis_real_order_enabled", False)),
            bool(getattr(settings, "kis_enabled", False)),
            bool(runtime.get("dry_run", True)) is False,
            bool(runtime.get("kill_switch", False)) is False,
            kr_scheduler_enabled,
            bool(kr.get("enabled_for_scheduler", False)),
            bool(kr_profile.get("enabled_for_trading", False)),
        ]
    )

    return {
        "runtime_scheduler_enabled": bool(runtime.get("scheduler_enabled", False)),
        "US": {
            "enabled_for_scheduler": bool(us.get("enabled_for_scheduler", False)),
            "timezone": us.get("timezone", "America/New_York"),
            "slots": us.get("entry_slots", []),
        },
        "KR": {
            "enabled_for_scheduler": bool(kr.get("enabled_for_scheduler", False))
            and kr_scheduler_enabled,
            "timezone": kr.get("timezone", "Asia/Seoul"),
            "slots": kr.get("entry_slots", []),
            "preview_only": True,
            "simulation_first": True,
            "kis_scheduler_enabled": kr_scheduler_enabled,
            "kis_scheduler_dry_run": kr_scheduler_dry_run,
            "kis_scheduler_allow_real_orders": kr_scheduler_allow_real_orders,
            "configured_live_order_prereqs_met": kr_live_order_prereqs_met,
            "dry_run_validation_scheduler_enabled": False,
            "real_orders_allowed": False,
            "real_order_scheduler_enabled": False,
        },
    }
