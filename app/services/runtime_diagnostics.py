from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

from app.db.database import SessionLocal
from app.services.runtime_setting_service import RuntimeSettingService

LOGGER = logging.getLogger("app.runtime")


def configure_runtime_logging(settings: Any) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log_dir = str(getattr(settings, "log_dir", "") or "").strip()
    root_logger = logging.getLogger()
    if root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)
    LOGGER.setLevel(logging.INFO)

    if not log_dir:
        return

    log_path = Path(log_dir).expanduser()
    log_path.mkdir(parents=True, exist_ok=True)
    log_file = (log_path / "auto-invest-server.log").resolve()

    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            try:
                if Path(handler.baseFilename).resolve() == log_file:
                    return
            except Exception:
                continue

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root_logger.addHandler(file_handler)


def sanitized_database_url(database_url: str) -> str:
    try:
        return make_url(database_url).render_as_string(hide_password=True)
    except Exception:
        return _redact_url_fallback(database_url)


def log_startup_state(settings: Any, scheduler_service: Any) -> None:
    state = {
        "scheduler_enabled": None,
        "kis_scheduler_effective": None,
    }
    try:
        with SessionLocal() as db:
            runtime_service = RuntimeSettingService()
            runtime_state = runtime_service.get_kis_scheduler_runtime_state_read_only(db)
        kr_dry_run_effective = bool(
            runtime_state["scheduler_enabled"]
            and runtime_state["kis_scheduler_enabled"]
            and runtime_state["kis_scheduler_dry_run"]
        )
        state = {
            "scheduler_enabled": bool(runtime_state["scheduler_enabled"]),
            "kis_scheduler_effective": bool(
                runtime_state["scheduler_enabled"]
                and (
                    runtime_state["real_order_scheduler_enabled"]
                    or kr_dry_run_effective
                )
            ),
        }
    except Exception as exc:
        LOGGER.warning("startup runtime state unavailable: %s", exc)

    LOGGER.info(
        "startup app_env=%s database_url=%s scheduler_enabled=%s "
        "kis_scheduler_effective=%s scheduler_thread_alive=%s",
        getattr(settings, "app_env", None),
        sanitized_database_url(str(getattr(settings, "database_url", ""))),
        state["scheduler_enabled"],
        state["kis_scheduler_effective"],
        _scheduler_thread_alive(scheduler_service),
    )


def _scheduler_thread_alive(scheduler_service: Any) -> bool:
    is_running = getattr(scheduler_service, "is_running", None)
    if callable(is_running):
        return bool(is_running())
    thread = getattr(scheduler_service, "_thread", None)
    return bool(thread and thread.is_alive())


def _redact_url_fallback(database_url: str) -> str:
    if "://" not in database_url:
        return database_url
    scheme, rest = database_url.split("://", 1)
    if "@" not in rest:
        return database_url
    credentials, host = rest.split("@", 1)
    username = credentials.split(":", 1)[0]
    return f"{scheme}://{username}:***@{host}"
