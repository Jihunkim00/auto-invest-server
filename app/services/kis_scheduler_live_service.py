from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.core.constants import DEFAULT_GATE_LEVEL
from app.db.models import OrderLog, TradeRunLog
from app.services.kis_dry_run_risk_service import MARKET, PROVIDER
from app.services.kis_limited_auto_buy_service import (
    MODE as LIMITED_AUTO_BUY_MODE,
    KisLimitedAutoBuyService,
)
from app.services.kis_limited_auto_sell_service import (
    MODE as LIMITED_AUTO_SELL_MODE,
    KisLimitedAutoSellService,
)
from app.services.kis_scheduler_guarded_sell_service import KisSchedulerGuardedSellService
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "kis_scheduler_live_once"
TRIGGER_SOURCE = "kis_scheduler_live"
KR_TZ = ZoneInfo("Asia/Seoul")


class KisSchedulerLiveService:
    """Disabled-by-default KIS live scheduler orchestration.

    This service never submits directly. It only invokes the guarded limited
    auto sell/buy services after scheduler-level gates pass.
    """

    def __init__(
        self,
        client: KisClient,
        *,
        limited_auto_sell_service: KisLimitedAutoSellService | None = None,
        limited_auto_buy_service: KisLimitedAutoBuyService | None = None,
        guarded_sell_service: KisSchedulerGuardedSellService | None = None,
        runtime_settings: RuntimeSettingService | None = None,
    ):
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.limited_auto_sell_service = limited_auto_sell_service or KisLimitedAutoSellService(
            client,
            runtime_settings=self.runtime_settings,
            allow_scheduler_guarded_sell=True,
        )
        self.guarded_sell_service = guarded_sell_service or KisSchedulerGuardedSellService(
            client,
            runtime_settings=self.runtime_settings,
            limited_auto_sell_service=self.limited_auto_sell_service,
        )
        self.limited_auto_buy_service = limited_auto_buy_service or KisLimitedAutoBuyService(
            client,
            runtime_settings=self.runtime_settings,
        )

    def status(self, db: Session) -> dict[str, Any]:
        runtime = self.runtime_settings.get_settings(db)
        checks = _checks(runtime, self.client.settings)
        return {
            "provider": PROVIDER,
            "market": MARKET,
            "mode": MODE,
            "kis_scheduler_live_enabled": checks["kis_scheduler_live_enabled"],
            "kis_scheduler_allow_real_orders": checks[
                "kis_scheduler_allow_real_orders"
            ],
            "kis_scheduler_allow_limited_auto_buy": checks[
                "kis_scheduler_allow_limited_auto_buy"
            ],
            "kis_scheduler_allow_limited_auto_sell": checks[
                "kis_scheduler_allow_limited_auto_sell"
            ],
            "kis_scheduler_max_live_orders_per_day": int(
                runtime.get("kis_scheduler_max_live_orders_per_day", 2) or 2
            ),
            "live_scheduler_ready": _first_block_reason(checks, runtime) is None,
            "checks": checks,
            "safety": _safety(runtime),
        }

    def run_once(
        self,
        db: Session,
        *,
        gate_level: int = DEFAULT_GATE_LEVEL,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc_now(now)
        created_at = now_utc.isoformat()
        runtime = self.runtime_settings.get_settings(db)
        checks = _checks(runtime, self.client.settings)
        safety = _safety(runtime)
        reason = _first_block_reason(checks, runtime)
        if reason:
            return self._persist(
                db,
                result="blocked",
                reason=reason,
                checks=checks,
                safety=safety,
                created_at=created_at,
                sell_result=None,
                buy_result=None,
                order_id=None,
                gate_level=gate_level,
            )

        max_orders = max(0, int(runtime.get("kis_scheduler_max_live_orders_per_day", 2) or 0))
        live_count = _daily_scheduler_live_order_count(db, now_utc=now_utc)
        checks["scheduler_live_order_count_today"] = live_count
        checks["scheduler_live_daily_limit_ok"] = live_count < max_orders
        if live_count >= max_orders:
            return self._persist(
                db,
                result="blocked",
                reason="scheduler_daily_live_order_limit_reached",
                checks=checks,
                safety=safety,
                created_at=created_at,
                sell_result=None,
                buy_result=None,
                order_id=None,
                gate_level=gate_level,
            )

        sell_result: dict[str, Any] | None = None
        buy_result: dict[str, Any] | None = None
        if checks["kis_scheduler_allow_limited_auto_sell"]:
            sell_result = sanitize_kis_payload(
                self.guarded_sell_service.run_once(
                    db,
                    trigger_source="scheduler",
                    now=now_utc,
                )
            )
            if sell_result.get("real_order_submitted") is True:
                return self._persist(
                    db,
                    result="submitted",
                    reason=str(sell_result.get("reason") or "scheduler_guarded_sell_submitted"),
                    checks=checks,
                    safety={**safety, "real_order_submitted": True, "broker_submit_called": True},
                    created_at=created_at,
                    sell_result=sell_result,
                    buy_result=None,
                    order_id=_int_or_none(sell_result.get("order_id")),
                    gate_level=gate_level,
                )

        if checks["kis_scheduler_allow_limited_auto_buy"]:
            buy_result = sanitize_kis_payload(
                self.limited_auto_buy_service.run_once(
                    db,
                    gate_level=gate_level,
                    now=now_utc,
                    scheduler_context=True,
                )
            )
            if buy_result.get("real_order_submitted") is True:
                return self._persist(
                    db,
                    result="submitted",
                    reason=str(buy_result.get("reason") or "limited_auto_buy_submitted"),
                    checks=checks,
                    safety={**safety, "real_order_submitted": True, "broker_submit_called": True},
                    created_at=created_at,
                    sell_result=sell_result,
                    buy_result=buy_result,
                    order_id=_int_or_none(buy_result.get("order_id")),
                    gate_level=gate_level,
                )

        reason = (
            str((sell_result or {}).get("reason") or "")
            or str((buy_result or {}).get("reason") or "")
            or "no_limited_auto_action"
        )
        return self._persist(
            db,
            result="no_action",
            reason=reason,
            checks=checks,
            safety=safety,
            created_at=created_at,
            sell_result=sell_result,
            buy_result=buy_result,
            order_id=None,
            gate_level=gate_level,
        )

    def _persist(
        self,
        db: Session,
        *,
        result: str,
        reason: str,
        checks: dict[str, Any],
        safety: dict[str, Any],
        created_at: str,
        sell_result: dict[str, Any] | None,
        buy_result: dict[str, Any] | None,
        order_id: int | None,
        gate_level: int,
    ) -> dict[str, Any]:
        submitted = result == "submitted"
        payload = sanitize_kis_payload(
            {
                "status": "ok",
                "provider": PROVIDER,
                "market": MARKET,
                "mode": MODE,
                "trigger_source": TRIGGER_SOURCE,
                "result": result,
                "action": "buy"
                if (buy_result or {}).get("real_order_submitted") is True
                else (
                    "sell"
                    if (sell_result or {}).get("real_order_submitted") is True
                    else "hold"
                ),
                "reason": reason,
                "real_order_submitted": submitted,
                "broker_submit_called": submitted,
                "manual_submit_called": False,
                "scheduler_real_order_enabled": submitted,
                "sell_result": sell_result,
                "buy_result": buy_result,
                "checks": checks,
                "safety": safety,
                "order_id": order_id,
                "created_at": created_at,
            }
        )
        run = TradeRunLog(
            run_key=f"kis_scheduler_live_{uuid.uuid4().hex[:10]}",
            trigger_source=TRIGGER_SOURCE,
            symbol=str(payload.get("symbol") or "WATCHLIST"),
            mode=MODE,
            gate_level=gate_level,
            stage="done",
            result=result,
            reason=reason,
            order_id=order_id,
            request_payload=json.dumps(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": MODE,
                    "trigger_source": TRIGGER_SOURCE,
                    "real_order_submitted": submitted,
                    "broker_submit_called": submitted,
                    "manual_submit_called": False,
                },
                ensure_ascii=False,
                default=str,
            ),
            response_payload=json.dumps(payload, ensure_ascii=False, default=str),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        payload["run"] = {
            "run_id": run.id,
            "run_key": run.run_key,
            "trigger_source": run.trigger_source,
            "result": run.result,
            "reason": run.reason,
            "created_at": run.created_at,
        }
        return sanitize_kis_payload(payload)


def _checks(runtime: dict[str, Any], settings: Any) -> dict[str, Any]:
    dry_run_required = bool(runtime.get("kis_scheduler_live_requires_dry_run_false", True))
    respect_kill_switch = bool(runtime.get("kis_scheduler_live_respect_kill_switch", True))
    return {
        "kis_scheduler_live_enabled": bool(
            runtime.get("kis_scheduler_live_enabled", False)
        ),
        "kis_scheduler_allow_real_orders": bool(
            runtime.get("kis_scheduler_allow_real_orders", False)
        ),
        "kis_scheduler_allow_limited_auto_buy": bool(
            runtime.get("kis_scheduler_allow_limited_auto_buy", False)
        ),
        "kis_scheduler_allow_limited_auto_sell": bool(
            runtime.get("kis_scheduler_allow_limited_auto_sell", False)
        ),
        "kis_scheduler_live_requires_dry_run_false": dry_run_required,
        "kis_scheduler_live_respect_kill_switch": respect_kill_switch,
        "dry_run": bool(runtime.get("dry_run", True)),
        "dry_run_false": bool(runtime.get("dry_run", True)) is False
        if dry_run_required
        else True,
        "kill_switch": bool(runtime.get("kill_switch", False)),
        "kill_switch_false": bool(runtime.get("kill_switch", False)) is False
        if respect_kill_switch
        else True,
        "kis_enabled": bool(getattr(settings, "kis_enabled", False)),
        "kis_real_order_enabled": bool(
            getattr(settings, "kis_real_order_enabled", False)
        ),
        "configured_kis_scheduler_allow_real_orders": bool(
            runtime.get("kis_scheduler_configured_allow_real_orders", False)
        ),
    }


def _first_block_reason(checks: dict[str, Any], runtime: dict[str, Any]) -> str | None:
    ordered = [
        ("kis_scheduler_live_enabled", "kis_scheduler_live_disabled"),
        ("kis_scheduler_allow_real_orders", "kis_scheduler_real_orders_disabled"),
        ("dry_run_false", "runtime_dry_run_true"),
        ("kill_switch_false", "kill_switch_enabled"),
        ("kis_enabled", "kis_disabled"),
        ("kis_real_order_enabled", "kis_real_order_disabled"),
    ]
    for key, reason in ordered:
        if checks.get(key) is not True:
            return reason
    if not (
        checks.get("kis_scheduler_allow_limited_auto_buy") is True
        or checks.get("kis_scheduler_allow_limited_auto_sell") is True
    ):
        return "scheduler_limited_auto_paths_disabled"
    if int(runtime.get("kis_scheduler_max_live_orders_per_day", 2) or 0) <= 0:
        return "scheduler_daily_live_order_limit_reached"
    return None


def _safety(runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "scheduler_real_order_enabled": False,
        "max_live_orders_per_day": int(
            runtime.get("kis_scheduler_max_live_orders_per_day", 2) or 2
        ),
        "buy_sell_limited": True,
        "kill_switch_protected": bool(
            runtime.get("kis_scheduler_live_respect_kill_switch", True)
        ),
        "dry_run_blocks_live": bool(
            runtime.get("kis_scheduler_live_requires_dry_run_false", True)
        ),
    }


def _daily_scheduler_live_order_count(db: Session, *, now_utc: datetime) -> int:
    start_utc, end_utc = _kr_day_bounds_utc(now_utc)
    return int(
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.created_at >= start_utc)
        .filter(OrderLog.created_at < end_utc)
        .filter(OrderLog.internal_status.in_(["SUBMITTED", "ACCEPTED", "PENDING", "PARTIALLY_FILLED", "FILLED"]))
        .filter(
            OrderLog.request_payload.like(f"%{LIMITED_AUTO_BUY_MODE}%")
            | OrderLog.request_payload.like("%limited_auto_buy%")
            | OrderLog.request_payload.like(f"%{LIMITED_AUTO_SELL_MODE}%")
            | OrderLog.response_payload.like(f"%{LIMITED_AUTO_BUY_MODE}%")
            | OrderLog.response_payload.like("%limited_auto_buy%")
            | OrderLog.response_payload.like(f"%{LIMITED_AUTO_SELL_MODE}%")
        )
        .count()
        or 0
    )


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
        return int(value)
    except (TypeError, ValueError):
        return None
