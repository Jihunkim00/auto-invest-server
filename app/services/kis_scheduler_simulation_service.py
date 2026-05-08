from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.core.constants import DEFAULT_GATE_LEVEL
from app.db.models import TradeRunLog
from app.services.kis_dry_run_auto_service import (
    SCHEDULER_PORTFOLIO_TRIGGER_SOURCE,
    SCHEDULER_TRIGGER_SOURCE,
    KisDryRunAutoService,
)
from app.services.kis_order_sync_service import (
    KisOrderSyncService,
    serialize_kis_order,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.kis_watchlist_preview_service import KisWatchlistPreviewService
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "kis_scheduler_dry_run_auto"
MARKET = "KR"
PROVIDER = "kis"


class KisSchedulerSimulationService:
    """KIS scheduler orchestration for simulation-only automation.

    The service is intentionally dry-run only. It fetches read-only account
    state, runs the KIS watchlist/portfolio preview, then delegates simulated
    persistence to KisDryRunAutoService. It never calls any live order submit
    method and never uses the manual order ticket symbol.
    """

    def __init__(
        self,
        client: KisClient,
        *,
        preview_service: KisWatchlistPreviewService | None = None,
        dry_run_auto_service: KisDryRunAutoService | None = None,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
    ):
        self.client = client
        self.preview_service = preview_service or KisWatchlistPreviewService(client)
        self.dry_run_auto_service = dry_run_auto_service or KisDryRunAutoService(
            client,
            preview_service=self.preview_service,
        )
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()

    def status(self, db: Session) -> dict[str, Any]:
        settings = self._scheduler_settings()
        runtime = self.runtime_settings.get_settings(db)
        try:
            market_session = self.session_service.get_session_status(MARKET)
        except Exception as exc:
            market_session = {"error": _safe_error(exc)}

        return {
            "provider": PROVIDER,
            "market": MARKET,
            "enabled": settings["enabled"],
            "dry_run": True,
            "scheduler_dry_run": settings["dry_run"],
            "allow_real_orders": False,
            "configured_allow_real_orders": settings["allow_real_orders"],
            "real_orders_allowed": False,
            "runtime_scheduler_enabled": bool(runtime.get("scheduler_enabled", False)),
            "runtime_dry_run": bool(runtime.get("dry_run", True)),
            "kill_switch": bool(runtime.get("kill_switch", False)),
            "trigger_source": SCHEDULER_TRIGGER_SOURCE,
            "portfolio_trigger_source": SCHEDULER_PORTFOLIO_TRIGGER_SOURCE,
            "market_session": market_session,
            "safety": {
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "live_scheduler_orders_enabled": False,
            },
        }

    def run_once(
        self,
        db: Session,
        *,
        gate_level: int = DEFAULT_GATE_LEVEL,
        scheduler_slot: str | None = None,
        require_enabled: bool = False,
    ) -> dict[str, Any]:
        settings = self._scheduler_settings()
        runtime = self.runtime_settings.get_settings(db)
        if require_enabled and not settings["enabled"]:
            return self._persist_skip(
                db,
                gate_level=gate_level,
                scheduler_slot=scheduler_slot,
                reason="kis_scheduler_disabled",
                runtime=runtime,
                settings=settings,
            )

        if bool(runtime.get("kill_switch", False)):
            return self._persist_skip(
                db,
                gate_level=gate_level,
                scheduler_slot=scheduler_slot,
                reason="kill_switch_enabled",
                runtime=runtime,
                settings=settings,
            )

        account_state = self._fetch_account_state(db)
        preview = self.preview_service.run_preview(
            include_gpt=True,
            gate_level=gate_level,
            db=db,
        )
        preview = self._merge_account_state(preview, account_state)
        result = self.dry_run_auto_service.run_once(
            db,
            gate_level=gate_level,
            trigger_source=SCHEDULER_TRIGGER_SOURCE,
            preview_override=preview,
            account_state=account_state,
            child_trigger_source=SCHEDULER_PORTFOLIO_TRIGGER_SOURCE,
        )
        result.update(
            {
                "mode": MODE,
                "scheduler_slot": scheduler_slot,
                "scheduler_enabled": settings["enabled"],
                "scheduler_dry_run": True,
                "scheduler_allow_real_orders": False,
                "configured_allow_real_orders": settings["allow_real_orders"],
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "account_state": _account_state_summary(account_state),
                "trigger_sources": [
                    SCHEDULER_TRIGGER_SOURCE,
                    SCHEDULER_PORTFOLIO_TRIGGER_SOURCE,
                ],
            }
        )
        return sanitize_kis_payload(result)

    def _scheduler_settings(self) -> dict[str, bool]:
        settings = get_settings()
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

    def _fetch_account_state(self, db: Session) -> dict[str, Any]:
        state: dict[str, Any] = {
            "provider": PROVIDER,
            "market": MARKET,
            "balance": None,
            "positions": [],
            "open_orders": [],
            "recent_orders": [],
            "warnings": [],
            "gating_notes": [
                "KIS scheduler fetched read-only account state before simulation."
            ],
        }

        try:
            state["balance"] = self.client.get_account_balance()
        except Exception as exc:
            state["warnings"].append(f"balance_unavailable:{exc.__class__.__name__}")

        try:
            state["positions"] = [_normalize_position(item) for item in self.client.list_positions()]
        except Exception as exc:
            state["warnings"].append(f"positions_unavailable:{exc.__class__.__name__}")

        try:
            state["open_orders"] = [_normalize_order(item) for item in self.client.list_open_orders()]
        except Exception as exc:
            state["warnings"].append(f"open_orders_unavailable:{exc.__class__.__name__}")

        try:
            recent_rows = KisOrderSyncService.recent_orders(
                db,
                limit=20,
                include_rejected=True,
            )
            state["recent_orders"] = [serialize_kis_order(row) for row in recent_rows]
        except Exception as exc:
            state["warnings"].append(f"recent_orders_unavailable:{exc.__class__.__name__}")

        return sanitize_kis_payload(state)

    def _merge_account_state(
        self,
        preview: dict[str, Any],
        account_state: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(preview)
        positions = [item for item in account_state.get("positions", []) if isinstance(item, dict)]
        if positions and not payload.get("held_positions"):
            payload["held_positions"] = positions
            payload["managed_positions"] = positions
            payload["held_position_count"] = len(positions)
            payload["open_position_count"] = len(positions)
        held_symbols = {
            str(item).strip().upper()
            for item in payload.get("held_symbols", [])
            if str(item).strip()
        }
        for position in positions:
            symbol = str(position.get("symbol") or "").strip().upper()
            if symbol:
                held_symbols.add(symbol)
        if held_symbols:
            payload["held_symbols"] = sorted(held_symbols)
            payload["open_symbols"] = sorted(held_symbols)
        payload["account_state"] = account_state
        payload["risk_flags"] = _dedupe(
            _string_list(payload.get("risk_flags"))
            + [warning.split(":", 1)[0] for warning in _string_list(account_state.get("warnings"))]
        )
        payload["gating_notes"] = _dedupe(
            _string_list(payload.get("gating_notes"))
            + _string_list(account_state.get("gating_notes"))
        )
        return sanitize_kis_payload(payload)

    def _persist_skip(
        self,
        db: Session,
        *,
        gate_level: int,
        scheduler_slot: str | None,
        reason: str,
        runtime: dict[str, Any],
        settings: dict[str, bool],
    ) -> dict[str, Any]:
        payload = {
            "provider": PROVIDER,
            "market": MARKET,
            "mode": MODE,
            "dry_run": True,
            "simulated": True,
            "scheduler_slot": scheduler_slot,
            "scheduler_enabled": settings["enabled"],
            "scheduler_dry_run": True,
            "scheduler_allow_real_orders": False,
            "configured_allow_real_orders": settings["allow_real_orders"],
            "trigger_source": SCHEDULER_TRIGGER_SOURCE,
            "result": "skipped",
            "action": "hold",
            "reason": reason,
            "risk_flags": [reason, "dry_run_only"],
            "gating_notes": [
                "KIS scheduler simulation skipped before any order decision.",
                "No real KIS order submitted.",
            ],
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "order_id": None,
            "signal_id": None,
            "runtime": {
                "scheduler_enabled": bool(runtime.get("scheduler_enabled", False)),
                "dry_run": bool(runtime.get("dry_run", True)),
                "kill_switch": bool(runtime.get("kill_switch", False)),
            },
            "trigger_sources": [SCHEDULER_TRIGGER_SOURCE],
        }
        run = TradeRunLog(
            run_key=f"kis_scheduler_{uuid.uuid4().hex[:12]}",
            trigger_source=SCHEDULER_TRIGGER_SOURCE,
            symbol="WATCHLIST",
            mode=MODE,
            gate_level=gate_level,
            stage="done",
            result="skipped",
            reason=reason,
            request_payload=json.dumps(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": MODE,
                    "gate_level": gate_level,
                    "scheduler_slot": scheduler_slot,
                    "dry_run": True,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
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
        return payload


def _normalize_position(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    symbol = str(item.get("symbol") or item.get("pdno") or "").strip()
    if symbol.isdigit() and len(symbol) < 6:
        symbol = symbol.zfill(6)
    return {
        **item,
        "symbol": symbol.upper(),
    }


def _normalize_order(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    symbol = str(item.get("symbol") or item.get("pdno") or "").strip()
    if symbol.isdigit() and len(symbol) < 6:
        symbol = symbol.zfill(6)
    return {
        **item,
        "symbol": symbol.upper(),
    }


def _account_state_summary(account_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": PROVIDER,
        "market": MARKET,
        "balance_available": isinstance(account_state.get("balance"), dict),
        "position_count": len(account_state.get("positions") or []),
        "open_order_count": len(account_state.get("open_orders") or []),
        "recent_order_count": len(account_state.get("recent_orders") or []),
        "warnings": _string_list(account_state.get("warnings")),
    }


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


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
