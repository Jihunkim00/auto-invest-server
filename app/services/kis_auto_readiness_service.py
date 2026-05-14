from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.core.constants import MAX_DAILY_LOSS_PCT
from app.db.models import OrderLog, SignalLog
from app.services.kis_order_sync_service import KisOrderSyncService
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService


PROVIDER = "kis"
MARKET = "KR"
MODE = "kis_live_auto_readiness"
PREFLIGHT_MODE = "kis_live_auto_preflight"
PR15_FINAL_BLOCKER = "pr15_no_live_auto_submit_path"
KR_TZ = ZoneInfo("Asia/Seoul")


class KisAutoReadinessService:
    """Read-only KIS live auto readiness gate.

    This service only evaluates future readiness signals. It deliberately has no
    live submit path and does not call manual order submission.
    """

    def __init__(
        self,
        client: KisClient,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
    ):
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()

    def readiness(self, db: Session) -> dict[str, Any]:
        return self._build_readiness(db, preflight=False)

    def preflight_once(self, db: Session) -> dict[str, Any]:
        return self._build_readiness(db, preflight=True)

    def _build_readiness(self, db: Session, *, preflight: bool) -> dict[str, Any]:
        runtime = self.runtime_settings.get_settings(db)
        settings = self.client.settings
        scheduler = _scheduler_settings(settings)
        market_session = self._market_session()
        account_state = self._fetch_account_state(db) if preflight else None
        trade_limit = self._trade_limit_status(db, runtime=runtime)
        daily_loss_ok = self._daily_loss_ok(account_state, preflight=preflight)
        gpt_context_available = self._gpt_context_available(db)

        live_auto_enabled = bool(runtime.get("kis_live_auto_enabled", False))
        buy_auto_enabled = bool(runtime.get("kis_live_auto_buy_enabled", False))
        sell_auto_enabled = bool(runtime.get("kis_live_auto_sell_enabled", False))
        requires_manual_confirm = bool(
            runtime.get("kis_live_auto_requires_manual_confirm", True)
        )

        checks = {
            "dry_run": bool(runtime.get("dry_run", True)),
            "kill_switch": bool(runtime.get("kill_switch", False)),
            "kis_enabled": bool(getattr(settings, "kis_enabled", False)),
            "kis_real_order_enabled": bool(
                getattr(settings, "kis_real_order_enabled", False)
            ),
            "kis_scheduler_enabled": scheduler["enabled"],
            "kis_scheduler_allow_real_orders": scheduler["allow_real_orders"],
            "market_open": market_session.get("is_market_open") is True,
            "entry_allowed_now": market_session.get("is_entry_allowed_now") is True,
            "daily_loss_ok": daily_loss_ok,
            "trade_limit_ok": trade_limit["ok"],
            "gpt_context_available": gpt_context_available,
            "risk_engine_ok": True,
            "live_auto_buy_enabled": buy_auto_enabled,
            "live_auto_sell_enabled": sell_auto_enabled,
        }
        if preflight:
            checks["account_state_available"] = bool(
                account_state and account_state.get("fetch_success")
            )
            checks["held_position_available"] = bool(
                account_state and account_state.get("position_count", 0) > 0
            )

        future_ready = (
            live_auto_enabled
            and (buy_auto_enabled or sell_auto_enabled)
            and checks["dry_run"] is False
            and checks["kill_switch"] is False
            and checks["kis_enabled"] is True
            and checks["kis_real_order_enabled"] is True
            and checks["market_open"] is True
            and checks["entry_allowed_now"] is True
            and checks["daily_loss_ok"] is True
            and checks["trade_limit_ok"] is True
            and checks["risk_engine_ok"] is True
        )
        if preflight:
            future_ready = future_ready and checks["account_state_available"] is True

        reason = self._reason(
            live_auto_enabled=live_auto_enabled,
            buy_auto_enabled=buy_auto_enabled,
            sell_auto_enabled=sell_auto_enabled,
            checks=checks,
            future_ready=future_ready,
        )

        payload: dict[str, Any] = {
            "provider": PROVIDER,
            "market": MARKET,
            "mode": PREFLIGHT_MODE if preflight else MODE,
            "preflight": preflight,
            "checked_at": datetime.now(UTC).isoformat(),
            "auto_order_ready": False,
            "future_auto_order_ready": bool(future_ready),
            "live_auto_enabled": live_auto_enabled,
            "real_order_submit_allowed": False,
            "reason": reason,
            "checks": checks,
            "safety": {
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "scheduler_real_order_enabled": False,
                "requires_manual_confirm": requires_manual_confirm,
                "no_broker_submit": True,
                "preflight_only": preflight,
            },
            "runtime": {
                "dry_run": checks["dry_run"],
                "kill_switch": checks["kill_switch"],
                "scheduler_enabled": bool(runtime.get("scheduler_enabled", False)),
                "kis_live_auto_enabled": live_auto_enabled,
                "kis_live_auto_buy_enabled": buy_auto_enabled,
                "kis_live_auto_sell_enabled": sell_auto_enabled,
                "kis_live_auto_requires_manual_confirm": requires_manual_confirm,
                "kis_live_auto_max_orders_per_day": int(
                    runtime.get("kis_live_auto_max_orders_per_day", 1)
                ),
                "kis_live_auto_max_notional_pct": float(
                    runtime.get("kis_live_auto_max_notional_pct", 0.03)
                ),
            },
            "scheduler": {
                "enabled": scheduler["enabled"],
                "dry_run": scheduler["dry_run"],
                "configured_allow_real_orders": scheduler["allow_real_orders"],
                "real_orders_allowed": False,
            },
            "future_paths": {
                "buy": {
                    "visible": True,
                    "enabled": buy_auto_enabled,
                    "would_execute": False,
                    "reason": "buy_auto_disabled"
                    if not buy_auto_enabled
                    else PR15_FINAL_BLOCKER,
                },
                "sell": {
                    "visible": True,
                    "enabled": sell_auto_enabled,
                    "would_execute": False,
                    "reason": "sell_auto_disabled"
                    if not sell_auto_enabled
                    else PR15_FINAL_BLOCKER,
                },
            },
            "limits": trade_limit,
            "market_session": _public_market_session(market_session),
            "blocked_by": _blocked_by(
                reason=reason,
                checks=checks,
                live_auto_enabled=live_auto_enabled,
                buy_auto_enabled=buy_auto_enabled,
                sell_auto_enabled=sell_auto_enabled,
            ),
            "order_id": None,
            "broker_order_id": None,
            "kis_odno": None,
        }
        if account_state is not None:
            payload["account_state"] = account_state
        return sanitize_kis_payload(payload)

    def _market_session(self) -> dict[str, Any]:
        try:
            return self.session_service.get_session_status(MARKET)
        except Exception as exc:
            return {
                "market": MARKET,
                "is_market_open": False,
                "is_entry_allowed_now": False,
                "error": _safe_error(exc),
            }

    def _fetch_account_state(self, db: Session) -> dict[str, Any]:
        warnings: list[str] = []
        balance: dict[str, Any] | None = None
        positions: list[dict[str, Any]] = []
        open_orders: list[dict[str, Any]] = []
        recent_orders: list[dict[str, Any]] = []

        try:
            raw_balance = self.client.get_account_balance()
            if isinstance(raw_balance, dict):
                balance = raw_balance
            else:
                warnings.append("balance_unexpected_shape")
        except Exception as exc:
            warnings.append(f"balance_unavailable:{exc.__class__.__name__}")

        try:
            raw_positions = self.client.list_positions()
            positions = [item for item in raw_positions if isinstance(item, dict)]
        except Exception as exc:
            warnings.append(f"positions_unavailable:{exc.__class__.__name__}")

        try:
            raw_open_orders = self.client.list_open_orders()
            open_orders = [item for item in raw_open_orders if isinstance(item, dict)]
        except Exception as exc:
            warnings.append(f"open_orders_unavailable:{exc.__class__.__name__}")

        try:
            rows = KisOrderSyncService.recent_orders(
                db,
                limit=20,
                include_rejected=True,
            )
            recent_orders = [
                {
                    "order_id": row.id,
                    "symbol": row.symbol,
                    "side": row.side,
                    "internal_status": row.internal_status,
                    "broker_order_id": row.broker_order_id,
                    "kis_odno": row.kis_odno,
                }
                for row in rows
            ]
        except Exception as exc:
            warnings.append(f"recent_orders_unavailable:{exc.__class__.__name__}")

        return sanitize_kis_payload(
            {
                "provider": PROVIDER,
                "market": MARKET,
                "fetch_success": not warnings,
                "balance": balance,
                "balance_available": isinstance(balance, dict),
                "position_count": len(positions),
                "open_order_count": len(open_orders),
                "recent_order_count": len(recent_orders),
                "positions": positions,
                "open_orders": open_orders,
                "recent_orders": recent_orders,
                "warnings": warnings,
            }
        )

    def _daily_loss_ok(
        self,
        account_state: dict[str, Any] | None,
        *,
        preflight: bool,
    ) -> bool:
        if account_state is None:
            return True
        balance_available = bool(account_state.get("balance_available"))
        if not balance_available:
            return not preflight
        balance = account_state.get("balance")
        if not isinstance(balance, dict):
            return not preflight
        equity = _first_float(
            balance,
            "total_asset_value",
            "total_equity",
            "equity",
            "stock_evaluation_amount",
        )
        unrealized_pl = _first_float(balance, "unrealized_pl", "daily_pnl")
        if equity is None or equity <= 0 or unrealized_pl is None:
            return True
        return unrealized_pl > -(equity * MAX_DAILY_LOSS_PCT)

    def _trade_limit_status(
        self,
        db: Session,
        *,
        runtime: dict[str, Any],
    ) -> dict[str, Any]:
        max_orders = max(1, _safe_int(runtime.get("kis_live_auto_max_orders_per_day"), 1))
        start_utc, end_utc = _today_window_utc()
        count = (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.market == MARKET)
            .filter(OrderLog.created_at >= start_utc)
            .filter(OrderLog.created_at < end_utc)
            .filter(
                or_(
                    OrderLog.kis_odno.is_not(None),
                    OrderLog.broker_order_id.is_not(None),
                )
            )
            .count()
        )
        return {
            "ok": int(count or 0) < max_orders,
            "orders_today": int(count or 0),
            "max_orders_per_day": max_orders,
            "max_notional_pct": float(
                runtime.get("kis_live_auto_max_notional_pct", 0.03)
            ),
        }

    def _gpt_context_available(self, db: Session) -> bool:
        if bool(getattr(self.client.settings, "openai_api_key", None)):
            return True
        row = (
            db.query(SignalLog)
            .filter(SignalLog.trigger_source.like("%kis%"))
            .filter(
                or_(
                    SignalLog.ai_reason.is_not(None),
                    SignalLog.gpt_entry_allowed.is_not(None),
                    SignalLog.gpt_entry_bias.is_not(None),
                    SignalLog.gpt_market_confidence.is_not(None),
                )
            )
            .order_by(SignalLog.created_at.desc(), SignalLog.id.desc())
            .first()
        )
        return row is not None

    @staticmethod
    def _reason(
        *,
        live_auto_enabled: bool,
        buy_auto_enabled: bool,
        sell_auto_enabled: bool,
        checks: dict[str, bool],
        future_ready: bool,
    ) -> str:
        if not live_auto_enabled:
            return "live_auto_disabled_by_default"
        if not (buy_auto_enabled or sell_auto_enabled):
            return "live_auto_buy_sell_disabled"
        if checks.get("dry_run") is True:
            return "runtime_dry_run_true"
        if checks.get("kill_switch") is True:
            return "kill_switch_enabled"
        if checks.get("kis_enabled") is not True:
            return "kis_disabled"
        if checks.get("kis_real_order_enabled") is not True:
            return "kis_real_order_disabled"
        if checks.get("market_open") is not True:
            return "market_closed"
        if checks.get("entry_allowed_now") is not True:
            return "entry_not_allowed_now"
        if checks.get("daily_loss_ok") is not True:
            return "daily_loss_check_failed"
        if checks.get("trade_limit_ok") is not True:
            return "trade_limit_reached"
        if checks.get("account_state_available") is False:
            return "account_state_unavailable"
        if future_ready:
            return PR15_FINAL_BLOCKER
        return "readiness_blocked"


def _scheduler_settings(settings: Any) -> dict[str, bool]:
    enabled = bool(
        getattr(settings, "kis_scheduler_enabled", False)
        or getattr(settings, "kr_scheduler_enabled", False)
    )
    dry_run = bool(getattr(settings, "kis_scheduler_dry_run", True))
    allow_real_orders = bool(
        getattr(settings, "kis_scheduler_allow_real_orders", False)
        or getattr(settings, "kr_scheduler_allow_real_orders", False)
    )
    return {
        "enabled": enabled,
        "dry_run": dry_run,
        "allow_real_orders": allow_real_orders,
    }


def _blocked_by(
    *,
    reason: str,
    checks: dict[str, bool],
    live_auto_enabled: bool,
    buy_auto_enabled: bool,
    sell_auto_enabled: bool,
) -> list[str]:
    blockers: list[str] = []
    if not live_auto_enabled:
        blockers.append("live_auto_disabled_by_default")
    if not buy_auto_enabled:
        blockers.append("buy_auto_disabled")
    if not sell_auto_enabled:
        blockers.append("sell_auto_disabled")
    if checks.get("dry_run") is True:
        blockers.append("runtime_dry_run_true")
    if checks.get("kill_switch") is True:
        blockers.append("kill_switch_enabled")
    for name in (
        "kis_enabled",
        "kis_real_order_enabled",
        "market_open",
        "entry_allowed_now",
        "daily_loss_ok",
        "trade_limit_ok",
        "account_state_available",
    ):
        if name in checks and checks[name] is not True:
            blockers.append(f"{name}_false")
    blockers.append(PR15_FINAL_BLOCKER)
    if reason and reason not in blockers:
        blockers.insert(0, reason)
    return _dedupe(blockers)


def _public_market_session(market_session: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "market",
        "timezone",
        "is_market_open",
        "is_entry_allowed_now",
        "is_near_close",
        "closure_reason",
        "closure_name",
        "effective_close",
        "no_new_entry_after",
        "local_time",
        "error",
    ]
    return {key: market_session.get(key) for key in keys if key in market_session}


def _today_window_utc(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or datetime.now(KR_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KR_TZ)
    local_now = current.astimezone(KR_TZ)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(UTC).replace(tzinfo=None),
        end_local.astimezone(UTC).replace(tzinfo=None),
    )


def _first_float(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            continue
    return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 160:
        text = f"{text[:160]}..."
    return f"{exc.__class__.__name__}: {text}"
