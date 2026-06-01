from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.database import get_db
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.scheduler_service import scheduler_service

router = APIRouter()


@router.get("/health")
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "app": "auto-invest-server",
        "app_name": settings.app_name,
        "env": settings.app_env,
        "timestamp": datetime.now(UTC).isoformat(),
        "version": settings.app_version or None,
    }


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    settings = get_settings()
    runtime_settings: dict[str, Any] | None = None
    db_connected = False

    try:
        db.execute(text("SELECT 1"))
        db_connected = True
        runtime_settings = RuntimeSettingService().get_settings_read_only(db)
    except Exception:
        runtime_settings = None

    return {
        "status": "ok" if db_connected and runtime_settings is not None else "degraded",
        "app": "auto-invest-server",
        "timestamp": datetime.now(UTC).isoformat(),
        "db_connected": db_connected,
        "scheduler_runtime_enabled": bool(
            runtime_settings.get("scheduler_enabled", False)
            if runtime_settings
            else False
        ),
        "scheduler_thread_alive": scheduler_service.is_running(),
        "kis_config_present": _kis_config_present(settings),
        "alpaca_config_present": _alpaca_config_present(settings),
        "safe_mode_summary": _safe_mode_summary(settings, runtime_settings),
    }


def _safe_mode_summary(
    settings: Any,
    runtime_settings: dict[str, Any] | None,
) -> dict[str, bool]:
    if runtime_settings is None:
        return {
            "dry_run": bool(getattr(settings, "dry_run", True)),
            "kill_switch": False,
            "kis_scheduler_enabled": False,
            "kis_live_auto_sell_enabled": False,
            "kis_live_auto_buy_enabled": False,
        }

    return {
        "dry_run": bool(runtime_settings["dry_run"]),
        "kill_switch": bool(runtime_settings["kill_switch"]),
        "kis_scheduler_enabled": bool(runtime_settings["kis_scheduler_enabled"]),
        "kis_live_auto_sell_enabled": bool(
            runtime_settings["kis_live_auto_sell_enabled"]
        ),
        "kis_live_auto_buy_enabled": bool(
            runtime_settings["kis_live_auto_buy_enabled"]
        ),
    }


def _kis_config_present(settings: Any) -> bool:
    return _all_present(
        getattr(settings, "kis_app_key", None),
        getattr(settings, "kis_app_secret", None),
        getattr(settings, "kis_account_no", None),
        getattr(settings, "kis_account_product_code", None),
        getattr(settings, "kis_base_url", None),
    )


def _alpaca_config_present(settings: Any) -> bool:
    return _all_present(
        getattr(settings, "alpaca_api_key", None),
        getattr(settings, "alpaca_secret_key", None),
        getattr(settings, "alpaca_base_url", None),
    )


def _all_present(*values: Any) -> bool:
    return all(str(value or "").strip() for value in values)
