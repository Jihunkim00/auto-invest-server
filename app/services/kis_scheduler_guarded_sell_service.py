from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, TradeRunLog
from app.services.kis_dry_run_risk_service import MARKET, PROVIDER, SELL
from app.services.kis_limited_auto_sell_service import KisLimitedAutoSellService
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "kis_scheduler_guarded_sell"
TRIGGER_SOURCE = "scheduler_guarded_sell"
DEFAULT_SLOT_LABEL = "manual_guarded_sell"
KR_TZ = ZoneInfo("Asia/Seoul")
ALLOWED_REQUEST_TRIGGER_SOURCES = {"scheduler", "scheduler_manual_test"}
SELL_SLOT_KEYWORDS = (
    "sell",
    "exit",
    "position",
    "manage",
    "management",
    "close",
    "stop_loss",
    "take_profit",
)


class KisSchedulerGuardedSellService:
    """Sell-only scheduler wrapper for the existing guarded limited sell path."""

    def __init__(
        self,
        client: KisClient,
        *,
        limited_auto_sell_service: KisLimitedAutoSellService | None = None,
        runtime_settings: RuntimeSettingService | None = None,
    ):
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.limited_auto_sell_service = limited_auto_sell_service or KisLimitedAutoSellService(
            client,
            runtime_settings=self.runtime_settings,
            allow_scheduler_guarded_sell=True,
        )

    def status(
        self,
        db: Session,
        *,
        slot_label: str | None = None,
        trigger_source: str = "scheduler_manual_test",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc_now(now)
        runtime = self.runtime_settings.get_settings(db)
        checks = _checks(
            runtime,
            self.client.settings,
            slot_label=_slot_label(slot_label),
            requested_trigger_source=trigger_source,
        )
        block_reasons = _block_reasons(checks)
        daily_limit = _daily_limited_sell_state(db, runtime=runtime, now_utc=now_utc)
        return _payload(
            result="blocked" if block_reasons else "ready",
            action="hold",
            reason=block_reasons[0] if block_reasons else "scheduler_sell_gates_ready",
            slot_label=_slot_label(slot_label),
            requested_trigger_source=trigger_source,
            checks=checks,
            daily_limit=daily_limit,
            sell_result=None,
            block_reasons=block_reasons,
            created_at=now_utc.isoformat(),
            include_raw=False,
        )

    def run_once(
        self,
        db: Session,
        *,
        slot_label: str | None = None,
        trigger_source: str = "scheduler_manual_test",
        include_raw: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc_now(now)
        created_at = now_utc.isoformat()
        resolved_slot_label = _slot_label(slot_label)
        runtime = self.runtime_settings.get_settings(db)
        checks = _checks(
            runtime,
            self.client.settings,
            slot_label=resolved_slot_label,
            requested_trigger_source=trigger_source,
        )
        checks["scheduler_slot_submitted_count"] = _slot_submitted_count(
            db,
            slot_label=resolved_slot_label,
            now_utc=now_utc,
        )
        checks["scheduler_slot_dedupe_ok"] = (
            checks["scheduler_slot_submitted_count"] == 0
        )
        daily_limit = _daily_limited_sell_state(db, runtime=runtime, now_utc=now_utc)
        block_reasons = _block_reasons(checks)
        if block_reasons:
            payload = _payload(
                result="blocked",
                action="hold",
                reason=block_reasons[0],
                slot_label=resolved_slot_label,
                requested_trigger_source=trigger_source,
                checks=checks,
                daily_limit=daily_limit,
                sell_result=None,
                block_reasons=block_reasons,
                created_at=created_at,
                include_raw=include_raw,
            )
            return self._record_parent_run(db, payload=payload)

        sell_result = sanitize_kis_payload(
            self.limited_auto_sell_service.run_once(db, now=now_utc)
        )
        sell_blocks = _string_list(sell_result.get("block_reasons"))
        submitted = sell_result.get("real_order_submitted") is True
        if submitted:
            result = "submitted"
            action = "sell"
            reason = str(sell_result.get("reason") or "scheduler_guarded_sell_submitted")
            block_reasons = []
        else:
            result = "blocked" if sell_result.get("result") != "skipped" else "skipped"
            action = "hold"
            reason = str(
                sell_result.get("reason")
                or (sell_blocks[0] if sell_blocks else "no_sell_candidate")
            )
            block_reasons = sell_blocks or [reason]

        payload = _payload(
            result=result,
            action=action,
            reason=reason,
            slot_label=resolved_slot_label,
            requested_trigger_source=trigger_source,
            checks=checks,
            daily_limit=_daily_limited_sell_state(
                db,
                runtime=runtime,
                now_utc=now_utc,
            ),
            sell_result=sell_result,
            block_reasons=block_reasons,
            created_at=created_at,
            include_raw=include_raw,
        )
        return self._record_parent_run(db, payload=payload)

    def _record_parent_run(self, db: Session, *, payload: dict[str, Any]) -> dict[str, Any]:
        order_id = _int_or_none(payload.get("order_id"))
        run = TradeRunLog(
            run_key=f"kis_scheduler_guarded_sell_{uuid.uuid4().hex[:10]}",
            trigger_source=TRIGGER_SOURCE,
            symbol=str(payload.get("symbol") or "WATCHLIST"),
            mode=MODE,
            stage="done",
            result=str(payload.get("result") or "blocked"),
            reason=str(payload.get("reason") or ""),
            order_id=order_id,
            request_payload=_json(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": MODE,
                    "trigger_source": TRIGGER_SOURCE,
                    "requested_trigger_source": payload.get(
                        "requested_trigger_source"
                    ),
                    "slot_label": payload.get("slot_label"),
                    "sell_only": True,
                    "buy_execution_allowed": False,
                }
            ),
            response_payload=_json(payload),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        payload["run"] = {
            "run_id": run.id,
            "run_key": run.run_key,
            "trigger_source": run.trigger_source,
            "symbol": run.symbol,
            "mode": run.mode,
            "result": run.result,
            "reason": run.reason,
            "order_id": run.order_id,
            "created_at": run.created_at,
        }
        return sanitize_kis_payload(payload)


def _checks(
    runtime: dict[str, Any],
    settings: Any,
    *,
    slot_label: str,
    requested_trigger_source: str,
) -> dict[str, Any]:
    stop_loss_enabled = bool(
        runtime.get(
            "kis_limited_auto_stop_loss_enabled",
            runtime.get("kis_limited_auto_sell_stop_loss_enabled", False),
        )
    )
    take_profit_enabled = bool(
        runtime.get(
            "kis_limited_auto_take_profit_enabled",
            runtime.get("kis_limited_auto_sell_take_profit_enabled", False),
        )
    )
    configured_allow_real_orders = bool(
        runtime.get("kis_scheduler_configured_allow_real_orders", False)
    )
    scheduler_buy_enabled = bool(
        runtime.get(
            "kis_scheduler_buy_enabled",
            runtime.get("kis_scheduler_allow_limited_auto_buy", False),
        )
    )
    return {
        "scheduler_enabled": bool(runtime.get("scheduler_enabled", False)),
        "kis_scheduler_enabled": bool(runtime.get("kis_scheduler_enabled", False)),
        "kis_scheduler_dry_run": bool(runtime.get("kis_scheduler_dry_run", True)),
        "kis_scheduler_dry_run_false": bool(
            runtime.get("kis_scheduler_dry_run", True)
        )
        is False,
        "kis_scheduler_allow_real_orders": bool(
            runtime.get("kis_scheduler_allow_real_orders", False)
        ),
        "configured_kis_scheduler_allow_real_orders": configured_allow_real_orders,
        "kis_scheduler_sell_enabled": bool(
            runtime.get("kis_scheduler_sell_enabled", False)
        ),
        "kis_scheduler_buy_enabled": scheduler_buy_enabled,
        "buy_execution_allowed": False,
        "scheduler_buy_execution_blocked": True,
        "requested_trigger_source": requested_trigger_source,
        "trigger_source_allowed": requested_trigger_source
        in ALLOWED_REQUEST_TRIGGER_SOURCES,
        "slot_label": slot_label,
        "slot_allows_sell": _slot_allows_sell(slot_label),
        "dry_run": bool(runtime.get("dry_run", True)),
        "dry_run_false": bool(runtime.get("dry_run", True)) is False,
        "kill_switch": bool(runtime.get("kill_switch", False)),
        "kill_switch_false": bool(runtime.get("kill_switch", False)) is False,
        "kis_enabled": bool(getattr(settings, "kis_enabled", False)),
        "kis_real_order_enabled": bool(
            getattr(settings, "kis_real_order_enabled", False)
        ),
        "kis_live_auto_sell_enabled": bool(
            runtime.get("kis_live_auto_sell_enabled", False)
        ),
        "kis_limited_auto_stop_loss_enabled": stop_loss_enabled,
        "kis_limited_auto_sell_stop_loss_enabled": stop_loss_enabled,
        "kis_limited_auto_take_profit_enabled": take_profit_enabled,
        "kis_limited_auto_sell_take_profit_enabled": take_profit_enabled,
        "sell_trigger_enabled": stop_loss_enabled or take_profit_enabled,
    }


def _block_reasons(checks: dict[str, Any]) -> list[str]:
    ordered = [
        ("kis_scheduler_allow_real_orders", "scheduler_real_orders_disabled"),
        (
            "configured_kis_scheduler_allow_real_orders",
            "configured_scheduler_real_orders_disabled",
        ),
        ("kis_scheduler_sell_enabled", "scheduler_sell_disabled"),
        ("scheduler_enabled", "scheduler_disabled"),
        ("kis_scheduler_enabled", "kis_scheduler_disabled"),
        ("kis_scheduler_dry_run_false", "kis_scheduler_dry_run_true"),
        ("trigger_source_allowed", "scheduler_trigger_source_invalid"),
        ("slot_allows_sell", "scheduler_slot_not_sell_enabled"),
        ("scheduler_slot_dedupe_ok", "scheduler_slot_real_order_already_submitted"),
        ("dry_run_false", "runtime_dry_run_true"),
        ("kill_switch_false", "kill_switch_enabled"),
        ("kis_enabled", "kis_disabled"),
        ("kis_real_order_enabled", "kis_real_order_disabled"),
        ("kis_live_auto_sell_enabled", "kis_live_auto_sell_disabled"),
        ("sell_trigger_enabled", "scheduler_sell_trigger_disabled"),
    ]
    reasons: list[str] = []
    for key, reason in ordered:
        if key in checks and checks.get(key) is not True:
            reasons.append(reason)
    return _dedupe(reasons)


def _payload(
    *,
    result: str,
    action: str,
    reason: str,
    slot_label: str,
    requested_trigger_source: str,
    checks: dict[str, Any],
    daily_limit: dict[str, Any],
    sell_result: dict[str, Any] | None,
    block_reasons: list[str],
    created_at: str,
    include_raw: bool,
) -> dict[str, Any]:
    child = _without_raw(sell_result) if sell_result and not include_raw else sell_result
    submitted = bool((child or {}).get("real_order_submitted") is True)
    broker_called = bool((child or {}).get("broker_submit_called") is True)
    manual_called = bool((child or {}).get("manual_submit_called") is True)
    order_id = (child or {}).get("order_id") or (child or {}).get("order_log_id")
    symbol = (child or {}).get("symbol")
    duplicate_order_check = (child or {}).get("duplicate_order_check") or {
        "checked": child is not None,
        "duplicate_open_sell_order": None,
    }
    market_session = (child or {}).get("market_session") or {}
    primary_block_reason = block_reasons[0] if block_reasons else None
    safety = {
        "scheduler_sell_only": True,
        "sell_only": True,
        "buy_execution_allowed": False,
        "scheduler_buy_execution_blocked": True,
        "no_direct_broker_submit_from_scheduler": True,
        "no_direct_manual_submit_from_scheduler": True,
        "existing_limited_auto_sell_path_reused": True,
        "limited_auto_buy_not_called_in_submit_mode": True,
        "scheduler_real_orders_enabled": bool(
            checks.get("kis_scheduler_allow_real_orders")
            and checks.get("configured_kis_scheduler_allow_real_orders")
        ),
        "dry_run": bool(checks.get("dry_run")),
        "kill_switch": bool(checks.get("kill_switch")),
        "kis_real_order_enabled": bool(checks.get("kis_real_order_enabled")),
        "kis_live_auto_sell_enabled": bool(
            checks.get("kis_live_auto_sell_enabled")
        ),
        "kis_scheduler_allow_real_orders": bool(
            checks.get("kis_scheduler_allow_real_orders")
        ),
        "kis_scheduler_sell_enabled": bool(checks.get("kis_scheduler_sell_enabled")),
        "daily_limit_remaining": daily_limit.get("daily_limit_remaining"),
        "duplicate_order_check": duplicate_order_check,
        "market_session_check": {
            "checked": bool(market_session),
            "sell_session_allowed": (child or {}).get("sell_session_allowed"),
            "market_open": market_session.get("is_market_open"),
            "closure_reason": market_session.get("closure_reason"),
        },
        "real_order_submitted": submitted,
        "broker_submit_called": broker_called,
        "manual_submit_called": manual_called,
    }
    buy_result = {
        "result": "skipped",
        "action": "hold",
        "reason": "buy_scheduler_execution_disabled",
        "skipped_for_sell_only_scheduler": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "validation_called": False,
    }
    payload = {
        "status": "ok",
        "provider": PROVIDER,
        "market": MARKET,
        "mode": MODE,
        "source": MODE,
        "source_type": "scheduler_guarded_sell_execution",
        "trigger_source": TRIGGER_SOURCE,
        "requested_trigger_source": requested_trigger_source,
        "slot_label": slot_label,
        "sell_only": True,
        "scheduler_sell_only": True,
        "buy_execution_allowed": False,
        "scheduler_buy_execution_blocked": True,
        "scheduler_real_orders_enabled": safety["scheduler_real_orders_enabled"],
        "real_order_submit_allowed": submitted,
        "result": result,
        "action": action,
        "reason": reason,
        "primary_block_reason": primary_block_reason,
        "summary": {
            "result": result,
            "action": action,
            "primary_block_reason": primary_block_reason,
            "sell_only": True,
            "buy_execution_allowed": False,
            "scheduler_real_orders_enabled": safety[
                "scheduler_real_orders_enabled"
            ],
            "scheduler_sell_enabled": bool(checks.get("kis_scheduler_sell_enabled")),
            "daily_limit_remaining": daily_limit.get("daily_limit_remaining"),
            "symbol": symbol,
            "quantity": (child or {}).get("quantity") or (child or {}).get("qty"),
            "trigger": (child or {}).get("trigger") or (child or {}).get("exit_trigger"),
            "order_id": order_id,
            "broker_order_id": (child or {}).get("broker_order_id"),
            "kis_odno": (child or {}).get("kis_odno"),
        },
        "sell_result": child,
        "buy_result": buy_result,
        "block_reasons": block_reasons,
        "blocked_by": block_reasons,
        "safety": safety,
        "diagnostics": {
            "checks": checks,
            "daily_limit": daily_limit,
            "limited_auto_sell_result_available": child is not None,
            "buy_module": "skipped_for_sell_only_scheduler",
            "include_raw": include_raw,
        },
        "checks": checks,
        "daily_limit": daily_limit,
        "duplicate_order_check": duplicate_order_check,
        "market_session_check": safety["market_session_check"],
        "real_order_submitted": submitted,
        "broker_submit_called": broker_called,
        "manual_submit_called": manual_called,
        "order_id": order_id,
        "order_log_id": (child or {}).get("order_log_id") or order_id,
        "broker_order_id": (child or {}).get("broker_order_id"),
        "kis_odno": (child or {}).get("kis_odno"),
        "symbol": symbol,
        "company_name": (child or {}).get("company_name") or (child or {}).get("name"),
        "quantity": (child or {}).get("quantity") or (child or {}).get("qty"),
        "trigger": (child or {}).get("trigger") or (child or {}).get("exit_trigger"),
        "created_at": created_at,
    }
    return sanitize_kis_payload(payload)


def _daily_limited_sell_state(
    db: Session,
    *,
    runtime: dict[str, Any],
    now_utc: datetime,
) -> dict[str, Any]:
    max_orders = max(
        0,
        int(runtime.get("kis_limited_auto_sell_max_orders_per_day", 1) or 0),
    )
    start_utc, end_utc = _kr_day_bounds_utc(now_utc)
    rows = (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.side == SELL)
        .filter(OrderLog.created_at >= start_utc)
        .filter(OrderLog.created_at < end_utc)
        .all()
    )
    submitted_statuses = {
        InternalOrderStatus.SUBMITTED.value,
        InternalOrderStatus.ACCEPTED.value,
        InternalOrderStatus.PENDING.value,
        InternalOrderStatus.PARTIALLY_FILLED.value,
        InternalOrderStatus.FILLED.value,
    }
    total = 0
    for row in rows:
        if str(row.internal_status or "").upper() not in submitted_statuses:
            continue
        payload_text = " ".join(
            str(value or "")
            for value in (row.request_payload, row.response_payload, row.last_sync_payload)
        ).lower()
        if "limited_auto_sell" in payload_text or "kis_limited_auto" in payload_text:
            total += 1
    return {
        "max_orders_per_day": max_orders,
        "submitted_count_today": total,
        "daily_limit_remaining": max(0, max_orders - total),
        "daily_limit_reached": max_orders <= 0 or total >= max_orders,
    }


def _slot_submitted_count(
    db: Session,
    *,
    slot_label: str,
    now_utc: datetime,
) -> int:
    start_utc, end_utc = _kr_day_bounds_utc(now_utc)
    return int(
        db.query(TradeRunLog)
        .filter(TradeRunLog.mode == MODE)
        .filter(TradeRunLog.trigger_source == TRIGGER_SOURCE)
        .filter(TradeRunLog.result == "submitted")
        .filter(TradeRunLog.created_at >= start_utc)
        .filter(TradeRunLog.created_at < end_utc)
        .filter(TradeRunLog.response_payload.like(f"%{slot_label}%"))
        .count()
        or 0
    )


def _slot_label(value: str | None) -> str:
    text = str(value or "").strip()
    return text or DEFAULT_SLOT_LABEL


def _slot_allows_sell(slot_label: str) -> bool:
    normalized = slot_label.strip().lower().replace("-", "_")
    return any(keyword in normalized for keyword in SELL_SLOT_KEYWORDS)


def _without_raw(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_raw(item)
            for key, item in value.items()
            if key not in {"raw_payload", "raw", "request_payload", "response_payload"}
        }
    if isinstance(value, list):
        return [_without_raw(item) for item in value]
    return value


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


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _json(payload: Any) -> str:
    return json.dumps(sanitize_kis_payload(payload), ensure_ascii=False, default=str)
