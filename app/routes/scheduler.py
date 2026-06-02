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
from app.db.models import TradeRunLog
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/status")
def get_scheduler_status(db: Session = Depends(get_db)):
    get_settings()
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
    kr_risk_summary = runtime_service.get_kis_risk_summary_read_only(db)

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

    return {
        "runtime_scheduler_enabled": bool(runtime_state["scheduler_enabled"]),
        "US": {
            "enabled_for_scheduler": bool(us.get("enabled_for_scheduler", False)),
            "timezone": us.get("timezone", "America/New_York"),
            "slots": us.get("entry_slots", []),
            "next_slot_name": us_next_slot["name"],
            "next_slot_time_local": us_next_slot["time_local"],
            "last_scheduler_run_at": us_last_run["created_at"],
            "last_scheduler_run_result": us_last_run["result"],
            "last_scheduler_run_reason": us_last_run["reason"],
            "last_scheduler_run_id": us_last_run["id"],
        },
        "KR": {
            "enabled_for_scheduler": kr_enabled_for_scheduler,
            "kr_scheduler_any_enabled": kr_scheduler_any_enabled,
            "kr_live_scheduler_enabled_effective": kr_live_scheduler_enabled_effective,
            "kr_dry_run_scheduler_enabled_effective": kr_dry_run_scheduler_enabled_effective,
            "enabled_for_scheduler_block_reasons": kr_enabled_for_scheduler_block_reasons,
            "timezone": kr.get("timezone", "Asia/Seoul"),
            "slots": kr.get("entry_slots", []),
            "next_slot_name": kr_next_slot["name"],
            "next_slot_time_local": kr_next_slot["time_local"],
            "last_scheduler_run_at": kr_last_run["created_at"],
            "last_scheduler_run_result": kr_last_run["result"],
            "last_scheduler_run_reason": kr_last_run["reason"],
            "last_scheduler_run_id": kr_last_run["id"],
            "last_scheduler_run_mode": kr_last_run["mode"],
            "last_scheduler_run_trigger_source": kr_last_run["trigger_source"],
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
            "risk_summary": kr_risk_summary,
        },
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
