from __future__ import annotations

import json
import math
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.brokers.kis_broker import KisBroker
from app.core.enums import InternalOrderStatus
from app.db.models import (
    OrderLog,
    SignalLog,
    StrategyLiveAutoBuyAttempt,
    TradeRunLog,
)
from app.schemas.strategy_live_auto_buy import (
    ProfileAwareGuardedLiveAutoBuyRunRequest,
)
from app.services.kis_order_sync_service import KisOrderSyncService
from app.services.kis_order_validation_service import (
    KisOrderValidationRequest,
    KisOrderValidationService,
    record_kis_order_validation,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.profile_aware_dry_run_auto_buy_service import (
    MODE as DRY_RUN_MODE,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.strategy_profile_service import StrategyProfileService
from app.services.target_aware_risk_service import TargetAwareRiskService


MODE = "strategy_live_auto_buy"
TRIGGER_SOURCE = "profile_aware_guarded_live_auto_buy"
PROVIDER = "kis"
MARKET = "KR"
KR_TZ = ZoneInfo("Asia/Seoul")

SUBMITTED_ATTEMPT_STATUSES = {
    "submitted",
    "filled",
    "sync_required",
}
OPEN_ORDER_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
    "PENDING_SUBMIT",
}


class ProfileAwareGuardedLiveAutoBuyService:
    """Manual one-shot live buy path gated by recent dry-run evidence."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        broker: Any | None = None,
        validation_service: Any | None = None,
        order_sync_service: Any | None = None,
        runtime_settings: RuntimeSettingService | None = None,
        strategy_profiles: StrategyProfileService | None = None,
        target_risk_service: TargetAwareRiskService | None = None,
        positions_loader: Callable[[Session], list[dict[str, Any]]] | None = None,
        balance_loader: Callable[[Session], dict[str, Any]] | None = None,
        open_orders_loader: Callable[[Session], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.client = client
        self.broker = broker or (KisBroker(client) if client is not None else None)
        self.validation_service = validation_service or (
            KisOrderValidationService(client) if client is not None else None
        )
        self.order_sync_service = order_sync_service or (
            KisOrderSyncService(client) if client is not None else None
        )
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.strategy_profiles = strategy_profiles or StrategyProfileService()
        self.target_risk_service = target_risk_service or TargetAwareRiskService()
        self.positions_loader = positions_loader
        self.balance_loader = balance_loader
        self.open_orders_loader = open_orders_loader

    def readiness(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
        symbol: str | None = None,
        source_dry_run_id: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc_now(now)
        settings = self.runtime_settings.get_settings_read_only(db)
        profile = self._active_profile(db)
        allowed_profiles = _allowed_profiles(settings)
        global_settings = self._global_settings()
        orders_used_today = self._orders_used_today(db, now_utc=now_utc)
        max_orders = max(0, int(settings.get("strategy_live_auto_buy_max_orders_per_day") or 0))
        checks: list[dict[str, Any]] = []
        risk_flags: list[str] = []
        gating_notes: list[str] = []
        primary: str | None = None

        def gate(key: str, ok: bool, reason: str, message: str) -> None:
            nonlocal primary
            checks.append(_check(key, ok, message, reason=reason))
            if not ok:
                primary = primary or reason
                risk_flags.append(reason)
                gating_notes.append(message)

        scheduler_live_enabled = bool(settings.get("strategy_live_auto_buy_scheduler_enabled"))
        gate(
            "strategy_live_auto_buy_enabled",
            bool(settings.get("strategy_live_auto_buy_enabled")),
            "strategy_live_auto_buy_disabled",
            "strategy_live_auto_buy_enabled is false.",
        )
        gate(
            "dry_run_false",
            not bool(settings.get("dry_run")),
            "dry_run_enabled",
            "Runtime dry_run must be false before guarded live auto buy can run.",
        )
        gate(
            "kill_switch_false",
            not bool(settings.get("kill_switch")),
            "kill_switch_enabled",
            "Kill switch must be false.",
        )
        gate(
            "kis_enabled",
            bool(getattr(global_settings, "kis_enabled", False)),
            "kis_disabled",
            "KIS must be enabled.",
        )
        gate(
            "kis_real_order_enabled",
            bool(getattr(global_settings, "kis_real_order_enabled", False)),
            "kis_real_order_disabled",
            "KIS real-order setting must be enabled.",
        )
        gate(
            "scheduler_live_disabled",
            not scheduler_live_enabled,
            "strategy_live_auto_buy_scheduler_enabled",
            "Scheduler live auto-buy must remain disabled for PR74.",
        )
        profile_name = str(profile.get("profile_name") or "")
        profile_allowed = profile_name in allowed_profiles and (
            profile_name != "aggressive"
            or bool(settings.get("strategy_live_auto_buy_allow_aggressive"))
        )
        gate(
            "active_profile_allowed",
            profile_allowed,
            "active_profile_not_allowed",
            f"Active profile {profile_name or 'unknown'} is not allowed for guarded live auto buy.",
        )

        dry_run = self._recent_dry_run(
            db,
            provider=provider,
            market=market,
            symbol=symbol,
            source_dry_run_id=source_dry_run_id,
            ttl_minutes=int(settings.get("strategy_live_auto_buy_recent_dry_run_ttl_minutes") or 30),
            now_utc=now_utc,
        )
        gate(
            "recent_dry_run_would_buy",
            bool(dry_run.get("accepted")),
            str(dry_run.get("block_reason") or "recent_dry_run_missing"),
            str(dry_run.get("message") or "Recent dry-run would_buy evidence is required."),
        )
        gate(
            "daily_auto_buy_limit",
            orders_used_today < max_orders,
            "daily_live_auto_buy_limit_reached",
            f"Guarded live auto buy used {orders_used_today}/{max_orders} orders today.",
        )

        plan: dict[str, Any] = {}
        if primary is None and dry_run.get("accepted"):
            try:
                account = self._account_snapshot(db)
            except ValueError as exc:
                reason = _account_block_reason(exc)
                gate("account_snapshot", False, reason, str(exc))
            else:
                position_count = len([item for item in account["positions"] if _position_qty(item) > 0])
                max_positions = int(profile.get("max_positions") or 0)
                gate(
                    "max_positions",
                    position_count < max_positions,
                    "max_positions_reached",
                    f"Current KIS positions are {position_count}/{max_positions}.",
                )
                selected_symbol = str(dry_run["payload"].get("selected_symbol") or "")
                gate(
                    "duplicate_position",
                    not _has_position(account["positions"], selected_symbol),
                    "position_already_exists",
                    "A position already exists for the dry-run selected symbol.",
                )
                gate(
                    "open_duplicate_order",
                    not self._has_open_order(db, selected_symbol, account["open_orders"]),
                    "duplicate_open_order",
                    "An open KIS buy order already exists for the dry-run selected symbol.",
                )
            if primary is None:
                target_risk = self._target_risk(db, dry_run["payload"], profile)
                risk_flags.extend(_strings(target_risk.get("risk_flags")))
                gating_notes.extend(_strings(target_risk.get("gating_notes")))
                gate(
                    "target_aware_risk",
                    target_risk.get("approved") is True,
                    str(target_risk.get("block_reason") or "target_risk_rejected"),
                    "Target-aware risk must approve the live entry.",
                )
                if primary is None:
                    plan = self._order_plan(
                        settings=settings,
                        profile=profile,
                        dry_run_payload=dry_run["payload"],
                        target_risk=target_risk,
                        requested_notional_krw=None,
                    )
                    gate(
                        "notional_and_quantity",
                        bool(plan.get("quantity", 0) > 0),
                        str(plan.get("block_reason") or "quantity_zero"),
                        "Calculated live order quantity must be greater than zero.",
                    )
                    cash = _cash(account["balance"])
                    gate(
                        "cash_sufficient",
                        cash is not None and cash >= float(plan.get("estimated_notional_krw") or 0),
                        "insufficient_cash",
                        "Available KIS cash must cover the guarded live buy estimate.",
                    )

        return sanitize_kis_payload(
            {
                "enabled": bool(settings.get("strategy_live_auto_buy_enabled")),
                "ready": primary is None,
                "provider": str(provider or PROVIDER).lower(),
                "market": str(market or MARKET).upper(),
                "active_profile": profile_name,
                "allowed_profiles": allowed_profiles,
                "dry_run": bool(settings.get("dry_run")),
                "kill_switch": bool(settings.get("kill_switch")),
                "kis_enabled": bool(getattr(global_settings, "kis_enabled", False)),
                "kis_real_order_enabled": bool(
                    getattr(global_settings, "kis_real_order_enabled", False)
                ),
                "scheduler_live_enabled": scheduler_live_enabled,
                "recent_dry_run_required": bool(
                    settings.get("strategy_live_auto_buy_requires_recent_dry_run")
                ),
                "recent_dry_run_found": bool(dry_run.get("found")),
                "recent_dry_run_age_minutes": dry_run.get("age_minutes"),
                "recent_dry_run_ttl_minutes": int(
                    settings.get("strategy_live_auto_buy_recent_dry_run_ttl_minutes") or 30
                ),
                "selected_symbol": (
                    dry_run.get("payload", {}).get("selected_symbol")
                    if isinstance(dry_run.get("payload"), dict)
                    else None
                ),
                "max_orders_per_day": max_orders,
                "orders_used_today": orders_used_today,
                "orders_remaining_today": max(0, max_orders - orders_used_today),
                "max_notional_krw": float(
                    settings.get("strategy_live_auto_buy_max_notional_krw") or 0
                ),
                "max_notional_pct": float(
                    settings.get("strategy_live_auto_buy_max_notional_pct") or 0
                ),
                "primary_block_reason": primary,
                "checks": checks,
                "risk_flags": _dedupe(risk_flags),
                "gating_notes": _dedupe(gating_notes),
                "safety": _safety(read_only=True),
            }
        )

    def run_once(
        self,
        db: Session,
        request: ProfileAwareGuardedLiveAutoBuyRunRequest | dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        payload = (
            request
            if isinstance(request, ProfileAwareGuardedLiveAutoBuyRunRequest)
            else ProfileAwareGuardedLiveAutoBuyRunRequest.model_validate(request)
        )
        now_utc = _utc_now(now)
        existing = self._idempotent_attempt(db, payload)
        if existing is not None:
            return self._response_from_attempt(existing, idempotent_replay=True)

        safety = _safety()
        settings = self.runtime_settings.get_settings(db)
        global_settings = self._global_settings()
        profile = self._active_profile(db)
        profile_name = str(profile.get("profile_name") or "safe")
        allowed_profiles = _allowed_profiles(settings)

        base_request = payload.model_dump(mode="json")
        if bool(settings.get("strategy_live_auto_buy_requires_operator_confirm")) and payload.confirm_operator_ack is not True:
            return self._blocked(
                db,
                request_payload=base_request,
                status="blocked",
                block_reason="confirm_operator_ack_required",
                safety=safety,
                active_profile=profile_name,
                trigger_source=payload.trigger_source,
                client_request_id=payload.client_request_id,
            )
        if not bool(settings.get("strategy_live_auto_buy_enabled")):
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason="strategy_live_auto_buy_disabled", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)
        if bool(settings.get("dry_run")):
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason="dry_run_enabled", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)
        if bool(settings.get("kill_switch")):
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason="kill_switch_enabled", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)
        if not bool(getattr(global_settings, "kis_enabled", False)):
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason="kis_disabled", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)
        if not bool(getattr(global_settings, "kis_real_order_enabled", False)):
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason="kis_real_order_disabled", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)
        if bool(settings.get("strategy_live_auto_buy_scheduler_enabled")):
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason="strategy_live_auto_buy_scheduler_enabled", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)
        if profile_name not in allowed_profiles or (
            profile_name == "aggressive"
            and not bool(settings.get("strategy_live_auto_buy_allow_aggressive"))
        ):
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason="active_profile_not_allowed", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)

        dry_run = self._recent_dry_run(
            db,
            provider=payload.provider,
            market=payload.market,
            symbol=payload.symbol,
            source_dry_run_id=payload.source_dry_run_id,
            ttl_minutes=int(settings.get("strategy_live_auto_buy_recent_dry_run_ttl_minutes") or 30),
            now_utc=now_utc,
        )
        if not dry_run.get("accepted"):
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason=str(dry_run.get("block_reason") or "recent_dry_run_missing"), safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id, dry_run=dry_run)

        orders_used_today = self._orders_used_today(db, now_utc=now_utc)
        max_orders = max(0, int(settings.get("strategy_live_auto_buy_max_orders_per_day") or 0))
        if orders_used_today >= max_orders:
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason="daily_live_auto_buy_limit_reached", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id, dry_run=dry_run)

        symbol = str(dry_run["payload"].get("selected_symbol") or "")
        try:
            account = self._account_snapshot(db)
        except ValueError as exc:
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason=_account_block_reason(exc), safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id, dry_run=dry_run)
        max_positions = int(profile.get("max_positions") or 0)
        if len([item for item in account["positions"] if _position_qty(item) > 0]) >= max_positions:
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason="max_positions_reached", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id, dry_run=dry_run)
        if _has_position(account["positions"], symbol):
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason="position_already_exists", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id, dry_run=dry_run)
        if self._has_open_order(db, symbol, account["open_orders"]):
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason="duplicate_open_order", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id, dry_run=dry_run)

        target_risk = self._target_risk(db, dry_run["payload"], profile)
        if target_risk.get("approved") is not True:
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason=str(target_risk.get("block_reason") or "target_risk_rejected"), safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id, dry_run=dry_run, target_risk=target_risk)

        plan = self._order_plan(
            settings=settings,
            profile=profile,
            dry_run_payload=dry_run["payload"],
            target_risk=target_risk,
            requested_notional_krw=payload.max_notional_krw,
        )
        if int(plan.get("quantity") or 0) <= 0:
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason=str(plan.get("block_reason") or "quantity_zero"), safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id, dry_run=dry_run, target_risk=target_risk, plan=plan)

        cash = _cash(account["balance"])
        if cash is None or cash < float(plan.get("estimated_notional_krw") or 0):
            return self._blocked(db, request_payload=base_request, status="blocked", block_reason="insufficient_cash", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id, dry_run=dry_run, target_risk=target_risk, plan=plan)

        safety["validation_called"] = True
        validation = self._validate_order(db, payload, dry_run, plan, target_risk)
        if validation.get("validated_for_submission") is not True:
            return self._blocked(
                db,
                request_payload=base_request,
                status="validation_failed",
                block_reason=str(
                    validation.get("primary_block_reason")
                    or (validation.get("block_reasons") or ["validation_failed"])[0]
                ),
                safety=safety,
                active_profile=profile_name,
                trigger_source=payload.trigger_source,
                client_request_id=payload.client_request_id,
                dry_run=dry_run,
                target_risk=target_risk,
                validation=validation,
                plan=plan,
            )

        return self._submit(
            db,
            request_payload=base_request,
            run_request=payload,
            dry_run=dry_run,
            profile=profile,
            target_risk=target_risk,
            validation=validation,
            plan=plan,
            safety=safety,
            now_utc=now_utc,
        )

    def recent(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
        limit: int = 20,
    ) -> dict[str, Any]:
        rows = (
            db.query(StrategyLiveAutoBuyAttempt)
            .filter(StrategyLiveAutoBuyAttempt.provider == str(provider).lower())
            .filter(StrategyLiveAutoBuyAttempt.market == str(market).upper())
            .order_by(
                StrategyLiveAutoBuyAttempt.created_at.desc(),
                StrategyLiveAutoBuyAttempt.id.desc(),
            )
            .limit(max(1, min(int(limit or 20), 100)))
            .all()
        )
        return sanitize_kis_payload(
            {
                "provider": str(provider).lower(),
                "market": str(market).upper(),
                "count": len(rows),
                "items": [self._attempt_item(row) for row in rows],
                "safety": _safety(read_only=True),
            }
        )

    def sync_attempt(self, db: Session, attempt_id: int) -> dict[str, Any]:
        attempt = db.get(StrategyLiveAutoBuyAttempt, int(attempt_id))
        if attempt is None:
            raise ValueError("strategy_live_auto_buy_attempt_not_found")
        if not attempt.related_order_id:
            response = self._response_from_attempt(attempt)
            response["safety"] = {**_safety(read_only=True), "sync_only": True}
            return response
        if self.order_sync_service is None:
            raise ValueError("kis_order_sync_service_unavailable")
        order = self.order_sync_service.sync_order(db, int(attempt.related_order_id))
        status = _attempt_status_from_order(order)
        attempt.status = status
        attempt.broker_order_id = order.broker_order_id or order.kis_odno
        attempt.synced_at = datetime.now(UTC)
        response = {
            **self._response_from_attempt(attempt),
            "status": status,
            "broker_order_id": attempt.broker_order_id,
            "broker_status": order.broker_status or order.broker_order_status,
            "internal_status": order.internal_status,
            "safety": {**_safety(read_only=True), "sync_only": True},
        }
        attempt.response_payload = _json(response)
        db.commit()
        db.refresh(attempt)
        return sanitize_kis_payload(response)

    def _blocked(
        self,
        db: Session,
        *,
        request_payload: dict[str, Any],
        status: str,
        block_reason: str,
        safety: dict[str, Any],
        active_profile: str | None,
        trigger_source: str,
        client_request_id: str | None,
        dry_run: dict[str, Any] | None = None,
        target_risk: dict[str, Any] | None = None,
        validation: dict[str, Any] | None = None,
        plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        dry_payload = (dry_run or {}).get("payload") if isinstance(dry_run, dict) else {}
        response = self._run_response(
            status=status,
            action="blocked",
            active_profile=active_profile,
            symbol=(dry_payload or {}).get("selected_symbol"),
            symbol_name=(dry_payload or {}).get("selected_symbol_name"),
            source_dry_run_id=(dry_run or {}).get("trade_run_id") if isinstance(dry_run, dict) else None,
            source_signal_id=(dry_payload or {}).get("signal_id") if isinstance(dry_payload, dict) else None,
            source_trade_run_id=(dry_run or {}).get("trade_run_id") if isinstance(dry_run, dict) else None,
            target_risk_approved=bool((target_risk or {}).get("approved")),
            validation_approved=bool((validation or {}).get("validated_for_submission")),
            submitted=False,
            quantity=int((plan or {}).get("quantity") or 0) or None,
            estimated_price=(plan or {}).get("estimated_price"),
            submitted_notional_krw=(plan or {}).get("estimated_notional_krw"),
            block_reason=block_reason,
            risk_flags=_dedupe([block_reason, *_strings((target_risk or {}).get("risk_flags"))]),
            gating_notes=_dedupe(_strings((target_risk or {}).get("gating_notes")) + [block_reason]),
            safety=safety,
        )
        attempt = self._save_attempt(
            db,
            response=response,
            request_payload=request_payload,
            status=status,
            trigger_source=trigger_source,
            client_request_id=client_request_id,
            target_risk=target_risk,
            validation=validation,
        )
        response["attempt_id"] = attempt.id
        attempt.response_payload = _json(response)
        db.commit()
        return sanitize_kis_payload(response)

    def _submit(
        self,
        db: Session,
        *,
        request_payload: dict[str, Any],
        run_request: ProfileAwareGuardedLiveAutoBuyRunRequest,
        dry_run: dict[str, Any],
        profile: dict[str, Any],
        target_risk: dict[str, Any],
        validation: dict[str, Any],
        plan: dict[str, Any],
        safety: dict[str, Any],
        now_utc: datetime,
    ) -> dict[str, Any]:
        if self.broker is None:
            return self._blocked(db, request_payload=request_payload, status="failed", block_reason="kis_broker_unavailable", safety=safety, active_profile=profile.get("profile_name"), trigger_source=run_request.trigger_source, client_request_id=run_request.client_request_id, dry_run=dry_run, target_risk=target_risk, validation=validation, plan=plan)

        dry_payload = dry_run["payload"]
        symbol = str(dry_payload.get("selected_symbol") or "")
        order = self._create_order_log(
            db,
            request_payload=request_payload,
            run_request=run_request,
            dry_run=dry_run,
            profile=profile,
            target_risk=target_risk,
            validation=validation,
            plan=plan,
            internal_status=InternalOrderStatus.REQUESTED.value,
            safety=safety,
        )
        attempt_response = self._run_response(
            status="submitting",
            action="submitting",
            active_profile=profile.get("profile_name"),
            symbol=symbol,
            symbol_name=dry_payload.get("selected_symbol_name"),
            source_dry_run_id=dry_run.get("trade_run_id"),
            source_signal_id=dry_payload.get("signal_id"),
            source_trade_run_id=dry_run.get("trade_run_id"),
            target_risk_approved=True,
            validation_approved=True,
            submitted=False,
            quantity=int(plan["quantity"]),
            estimated_price=plan.get("estimated_price"),
            submitted_notional_krw=plan.get("estimated_notional_krw"),
            related_order_id=order.id,
            internal_status=order.internal_status,
            risk_flags=_strings(target_risk.get("risk_flags")),
            gating_notes=_strings(target_risk.get("gating_notes")),
            safety=safety,
        )
        attempt = self._save_attempt(
            db,
            response=attempt_response,
            request_payload=request_payload,
            status="submitting",
            trigger_source=run_request.trigger_source,
            client_request_id=run_request.client_request_id,
            target_risk=target_risk,
            validation=validation,
            related_order_id=order.id,
        )
        safety["broker_submit_called"] = True
        try:
            broker_response = self.broker.submit_market_buy(
                symbol=symbol,
                qty=int(plan["quantity"]),
            )
        except Exception as exc:
            safety["real_order_submitted"] = False
            order.internal_status = InternalOrderStatus.UNKNOWN_STALE.value
            order.broker_status = "sync_required"
            order.broker_order_status = "sync_required"
            order.error_message = _safe_error(exc)
            order.response_payload = _json(
                {
                    "mode": MODE,
                    "status": "sync_required",
                    "error": _safe_error(exc),
                    "safety": safety,
                }
            )
            response = self._run_response(
                status="sync_required",
                action="sync_required",
                active_profile=profile.get("profile_name"),
                symbol=symbol,
                symbol_name=dry_payload.get("selected_symbol_name"),
                source_dry_run_id=dry_run.get("trade_run_id"),
                source_signal_id=dry_payload.get("signal_id"),
                source_trade_run_id=dry_run.get("trade_run_id"),
                target_risk_approved=True,
                validation_approved=True,
                submitted=False,
                quantity=int(plan["quantity"]),
                estimated_price=plan.get("estimated_price"),
                submitted_notional_krw=plan.get("estimated_notional_krw"),
                related_order_id=order.id,
                internal_status=order.internal_status,
                block_reason="broker_submit_sync_required",
                risk_flags=["broker_submit_sync_required"],
                gating_notes=["Broker submit raised after call; manual sync is required before retry."],
                attempt_id=attempt.id,
                safety=safety,
            )
            attempt.status = "sync_required"
            attempt.block_reason = "broker_submit_sync_required"
            attempt.response_payload = _json(response)
            db.commit()
            return sanitize_kis_payload(response)

        broker_order_id = _extract_broker_order_id(broker_response)
        broker_status = _extract_broker_status(broker_response)
        safety["real_order_submitted"] = True
        order.internal_status = InternalOrderStatus.SUBMITTED.value
        order.broker_status = broker_status
        order.broker_order_status = broker_status
        order.broker_order_id = broker_order_id
        order.kis_odno = broker_order_id
        order.submitted_at = now_utc
        signal = self._save_signal(
            db,
            dry_run=dry_run,
            profile=profile,
            target_risk=target_risk,
            plan=plan,
            order_id=order.id,
        )
        run = self._save_run(
            db,
            request_payload=request_payload,
            dry_run=dry_run,
            profile=profile,
            target_risk=target_risk,
            validation=validation,
            plan=plan,
            order_id=order.id,
            signal_id=signal.id,
        )
        response = self._run_response(
            status="submitted",
            action="submitted",
            active_profile=profile.get("profile_name"),
            symbol=symbol,
            symbol_name=dry_payload.get("selected_symbol_name"),
            source_dry_run_id=dry_run.get("trade_run_id"),
            source_signal_id=dry_payload.get("signal_id"),
            source_trade_run_id=dry_run.get("trade_run_id"),
            target_risk_approved=True,
            validation_approved=True,
            submitted=True,
            quantity=int(plan["quantity"]),
            estimated_price=plan.get("estimated_price"),
            submitted_notional_krw=plan.get("estimated_notional_krw"),
            related_order_id=order.id,
            broker_order_id=broker_order_id,
            broker_status=broker_status,
            internal_status=order.internal_status,
            risk_flags=_strings(target_risk.get("risk_flags")),
            gating_notes=_dedupe(
                [
                    "All guarded live auto buy gates passed.",
                    *_strings(target_risk.get("gating_notes")),
                ]
            ),
            attempt_id=attempt.id,
            signal_id=signal.id,
            trade_run_id=run.id,
            safety=safety,
        )
        order.response_payload = _json({**response, "kis_response": broker_response})
        signal.related_order_id = order.id
        run.response_payload = _json(response)
        attempt.status = "submitted"
        attempt.related_order_id = order.id
        attempt.broker_order_id = broker_order_id
        attempt.submitted_at = now_utc
        attempt.response_payload = _json(response)
        db.commit()
        return sanitize_kis_payload(response)

    def _validate_order(
        self,
        db: Session,
        payload: ProfileAwareGuardedLiveAutoBuyRunRequest,
        dry_run: dict[str, Any],
        plan: dict[str, Any],
        target_risk: dict[str, Any],
    ) -> dict[str, Any]:
        if self.validation_service is None:
            return {
                "validated_for_submission": False,
                "block_reasons": ["kis_validation_service_unavailable"],
            }
        dry_payload = dry_run["payload"]
        request = KisOrderValidationRequest(
            market=payload.market,
            symbol=str(dry_payload.get("selected_symbol") or ""),
            side="buy",
            qty=int(plan["quantity"]),
            order_type="market",
            dry_run=True,
            reason="strategy guarded live auto buy pre-submit validation",
            source_metadata={
                "source_context": TRIGGER_SOURCE,
                "mode": MODE,
                "source_dry_run_id": dry_run.get("trade_run_id"),
                "source_signal_id": dry_payload.get("signal_id"),
                "active_profile": target_risk.get("active_profile"),
            },
        )
        result = self.validation_service.validate(request)
        try:
            record_kis_order_validation(db, request=request, result=result)
        except Exception:
            pass
        return sanitize_kis_payload(result.to_dict() if hasattr(result, "to_dict") else dict(result))

    def _recent_dry_run(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
        symbol: str | None,
        source_dry_run_id: int | None,
        ttl_minutes: int,
        now_utc: datetime,
    ) -> dict[str, Any]:
        query = db.query(TradeRunLog).filter(TradeRunLog.mode == DRY_RUN_MODE)
        if source_dry_run_id is not None:
            query = query.filter(TradeRunLog.id == int(source_dry_run_id))
        rows = (
            query.order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .limit(100)
            .all()
        )
        normalized_symbol = str(symbol or "").strip().upper()
        for row in rows:
            payload = _parse_object(row.response_payload)
            if not payload:
                continue
            if str(payload.get("provider") or "").lower() != str(provider).lower():
                continue
            if str(payload.get("market") or "").upper() != str(market).upper():
                continue
            if payload.get("action") != "would_buy":
                if source_dry_run_id is not None:
                    return {"found": True, "accepted": False, "block_reason": "source_dry_run_not_would_buy", "payload": payload, "trade_run_id": row.id}
                continue
            selected_symbol = str(payload.get("selected_symbol") or "").upper()
            if normalized_symbol and selected_symbol != normalized_symbol:
                return {"found": True, "accepted": False, "block_reason": "symbol_mismatch_recent_dry_run", "payload": payload, "trade_run_id": row.id}
            created = _aware_utc(row.created_at)
            age = max(0.0, (now_utc - created).total_seconds() / 60.0)
            if age > ttl_minutes:
                return {"found": True, "accepted": False, "block_reason": "recent_dry_run_expired", "payload": payload, "trade_run_id": row.id, "age_minutes": round(age, 2)}
            return {"found": True, "accepted": True, "payload": payload, "trade_run_id": row.id, "age_minutes": round(age, 2)}
        return {"found": False, "accepted": False, "block_reason": "recent_dry_run_missing"}

    def _target_risk(
        self,
        db: Session,
        dry_run_payload: dict[str, Any],
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        return self.target_risk_service.evaluate_entry(
            db,
            {
                "provider": PROVIDER,
                "market": MARKET,
                "symbol": str(dry_run_payload.get("selected_symbol") or "UNKNOWN"),
                "side": "buy",
                "requested_notional_krw": dry_run_payload.get("recommended_notional_krw")
                or profile.get("max_order_notional_krw"),
                "buy_score": dry_run_payload.get("buy_score")
                or dry_run_payload.get("final_score"),
                "sell_score": dry_run_payload.get("sell_score"),
                "confidence": dry_run_payload.get("confidence"),
                "trigger_source": TRIGGER_SOURCE,
                "dry_run": False,
            },
            profile_name=str(profile.get("profile_name") or "safe"),
        )

    def _order_plan(
        self,
        *,
        settings: dict[str, Any],
        profile: dict[str, Any],
        dry_run_payload: dict[str, Any],
        target_risk: dict[str, Any],
        requested_notional_krw: float | None,
    ) -> dict[str, Any]:
        price = _float(dry_run_payload.get("simulated_price"))
        if price is None or price <= 0:
            return {"quantity": 0, "block_reason": "estimated_price_unavailable"}
        target_notional = _float(target_risk.get("approved_notional_krw"))
        if target_notional is None or target_notional <= 0:
            target_notional = _float(target_risk.get("recommended_notional_krw")) or 0.0
        caps = [
            target_notional,
            _float(profile.get("max_order_notional_krw")) or 0.0,
            _float(settings.get("strategy_live_auto_buy_max_notional_krw")) or 0.0,
        ]
        total_assets = _float(target_risk.get("total_assets_krw"))
        pct = _float(settings.get("strategy_live_auto_buy_max_notional_pct")) or 0.0
        if total_assets and pct:
            caps.append(total_assets * pct)
        if requested_notional_krw is not None:
            caps.append(float(requested_notional_krw))
        approved = max(0.0, min(value for value in caps if value is not None and value >= 0))
        quantity = math.floor(approved / price) if price > 0 else 0
        estimated = round(quantity * price, 2)
        return {
            "requested_notional_krw": requested_notional_krw,
            "approved_notional_krw": round(approved, 2),
            "quantity": quantity,
            "estimated_price": price,
            "estimated_notional_krw": estimated,
            "block_reason": "quantity_zero" if quantity <= 0 else None,
        }

    def _account_snapshot(self, db: Session) -> dict[str, Any]:
        try:
            positions = (
                self.positions_loader(db)
                if self.positions_loader is not None
                else self.client.list_positions()
            )
        except Exception as exc:
            raise ValueError(f"positions_unavailable: {_safe_error(exc)}") from exc
        try:
            balance = (
                self.balance_loader(db)
                if self.balance_loader is not None
                else self.client.get_account_balance()
            )
        except Exception as exc:
            raise ValueError(f"balance_unavailable: {_safe_error(exc)}") from exc
        try:
            open_orders = (
                self.open_orders_loader(db)
                if self.open_orders_loader is not None
                else self.client.list_open_orders()
            )
        except Exception as exc:
            raise ValueError(f"open_orders_unavailable: {_safe_error(exc)}") from exc
        return {
            "positions": positions if isinstance(positions, list) else [],
            "balance": balance if isinstance(balance, dict) else {},
            "open_orders": open_orders if isinstance(open_orders, list) else [],
        }

    def _orders_used_today(self, db: Session, *, now_utc: datetime) -> int:
        start_utc, end_utc = _kr_day_bounds_utc(now_utc)
        return (
            db.query(StrategyLiveAutoBuyAttempt)
            .filter(StrategyLiveAutoBuyAttempt.provider == PROVIDER)
            .filter(StrategyLiveAutoBuyAttempt.market == MARKET)
            .filter(StrategyLiveAutoBuyAttempt.status.in_(sorted(SUBMITTED_ATTEMPT_STATUSES)))
            .filter(StrategyLiveAutoBuyAttempt.created_at >= start_utc)
            .filter(StrategyLiveAutoBuyAttempt.created_at < end_utc)
            .count()
        )

    def _has_open_order(
        self,
        db: Session,
        symbol: str,
        broker_open_orders: list[dict[str, Any]],
    ) -> bool:
        normalized = str(symbol or "").strip().upper()
        if not normalized:
            return False
        for item in broker_open_orders:
            if str(item.get("symbol") or item.get("pdno") or "").strip().upper() != normalized:
                continue
            side = str(item.get("side") or item.get("sll_buy_dvsn_cd_name") or "").lower()
            if not side or "buy" in side or "매수" in side:
                return True
        return (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.market == MARKET)
            .filter(OrderLog.symbol == normalized)
            .filter(OrderLog.side == "buy")
            .filter(OrderLog.internal_status.in_(sorted(OPEN_ORDER_STATUSES)))
            .count()
            > 0
        )

    def _active_profile(self, db: Session) -> dict[str, Any]:
        row = self.strategy_profiles.active_profile(db)
        return self.strategy_profiles.serialize_profile(row)

    def _global_settings(self) -> Any:
        return getattr(self.runtime_settings, "settings", None)

    def _idempotent_attempt(
        self,
        db: Session,
        payload: ProfileAwareGuardedLiveAutoBuyRunRequest,
    ) -> StrategyLiveAutoBuyAttempt | None:
        if not payload.client_request_id:
            return None
        return (
            db.query(StrategyLiveAutoBuyAttempt)
            .filter(StrategyLiveAutoBuyAttempt.provider == payload.provider)
            .filter(StrategyLiveAutoBuyAttempt.market == payload.market)
            .filter(StrategyLiveAutoBuyAttempt.client_request_id == payload.client_request_id)
            .order_by(StrategyLiveAutoBuyAttempt.created_at.desc(), StrategyLiveAutoBuyAttempt.id.desc())
            .first()
        )

    def _save_attempt(
        self,
        db: Session,
        *,
        response: dict[str, Any],
        request_payload: dict[str, Any],
        status: str,
        trigger_source: str,
        client_request_id: str | None,
        target_risk: dict[str, Any] | None = None,
        validation: dict[str, Any] | None = None,
        related_order_id: int | None = None,
    ) -> StrategyLiveAutoBuyAttempt:
        attempt = StrategyLiveAutoBuyAttempt(
            provider=PROVIDER,
            market=MARKET,
            active_profile=response.get("active_profile"),
            symbol=response.get("symbol"),
            symbol_name=response.get("symbol_name"),
            status=status,
            trigger_source=trigger_source or "manual",
            client_request_id=client_request_id,
            source_dry_run_id=response.get("source_dry_run_id"),
            source_signal_id=response.get("source_signal_id"),
            source_trade_run_id=response.get("source_trade_run_id"),
            requested_notional_krw=response.get("submitted_notional_krw"),
            approved_notional_krw=response.get("submitted_notional_krw"),
            quantity=response.get("quantity"),
            estimated_price=response.get("estimated_price"),
            estimated_notional_krw=response.get("submitted_notional_krw"),
            target_risk_result=_json(target_risk or {}),
            validation_result=_json(validation or {}),
            related_order_id=related_order_id or response.get("related_order_id"),
            broker_order_id=response.get("broker_order_id"),
            block_reason=response.get("block_reason"),
            risk_flags=_json(response.get("risk_flags") or []),
            gating_notes=_json(response.get("gating_notes") or []),
            safety_flags=_json(response.get("safety") or {}),
            request_payload=_json(request_payload),
            response_payload=_json(response),
        )
        db.add(attempt)
        db.flush()
        return attempt

    def _create_order_log(
        self,
        db: Session,
        *,
        request_payload: dict[str, Any],
        run_request: ProfileAwareGuardedLiveAutoBuyRunRequest,
        dry_run: dict[str, Any],
        profile: dict[str, Any],
        target_risk: dict[str, Any],
        validation: dict[str, Any],
        plan: dict[str, Any],
        internal_status: str,
        safety: dict[str, Any],
    ) -> OrderLog:
        dry_payload = dry_run["payload"]
        row = OrderLog(
            broker=PROVIDER,
            market=MARKET,
            symbol=str(dry_payload.get("selected_symbol") or ""),
            side="buy",
            order_type="market",
            time_in_force="day",
            qty=float(plan["quantity"]),
            requested_qty=float(plan["quantity"]),
            remaining_qty=float(plan["quantity"]),
            notional=float(plan.get("estimated_notional_krw") or 0),
            internal_status=internal_status,
            request_payload=_json(
                {
                    **request_payload,
                    "mode": MODE,
                    "trigger_source": TRIGGER_SOURCE,
                    "operator_trigger_source": run_request.trigger_source,
                    "source_dry_run_id": dry_run.get("trade_run_id"),
                    "source_signal_id": dry_payload.get("signal_id"),
                    "active_profile": profile.get("profile_name"),
                    "target_risk_result": target_risk,
                    "validation_result": validation,
                    "quantity": plan["quantity"],
                    "estimated_price": plan["estimated_price"],
                    "estimated_notional_krw": plan["estimated_notional_krw"],
                    "safety": safety,
                    "real_order_submitted": False,
                    "validation_called": True,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                }
            ),
        )
        db.add(row)
        db.flush()
        return row

    def _save_signal(
        self,
        db: Session,
        *,
        dry_run: dict[str, Any],
        profile: dict[str, Any],
        target_risk: dict[str, Any],
        plan: dict[str, Any],
        order_id: int,
    ) -> SignalLog:
        dry_payload = dry_run["payload"]
        signal = SignalLog(
            symbol=str(dry_payload.get("selected_symbol") or ""),
            action="buy",
            buy_score=_float(dry_payload.get("buy_score")),
            sell_score=_float(dry_payload.get("sell_score")),
            confidence=_float(dry_payload.get("confidence")),
            reason="guarded_live_auto_buy_submitted",
            final_buy_score=_float(dry_payload.get("final_score")),
            risk_flags=_json(_strings(target_risk.get("risk_flags"))),
            approved_by_risk=True,
            position_size_pct=_float(
                (target_risk.get("profile_thresholds") or {}).get("max_order_notional_pct")
            ),
            related_order_id=order_id,
            signal_status="submitted",
            trigger_source=TRIGGER_SOURCE,
            gate_profile_name=str(profile.get("profile_name") or ""),
            hard_blocked=False,
            gating_notes=_json(_strings(target_risk.get("gating_notes"))),
        )
        db.add(signal)
        db.flush()
        return signal

    def _save_run(
        self,
        db: Session,
        *,
        request_payload: dict[str, Any],
        dry_run: dict[str, Any],
        profile: dict[str, Any],
        target_risk: dict[str, Any],
        validation: dict[str, Any],
        plan: dict[str, Any],
        order_id: int,
        signal_id: int,
    ) -> TradeRunLog:
        run = TradeRunLog(
            run_key=f"strategy_live_buy_{uuid.uuid4().hex[:12]}",
            trigger_source=TRIGGER_SOURCE,
            symbol=str(dry_run["payload"].get("selected_symbol") or ""),
            mode=MODE,
            stage="done",
            result="submitted",
            reason="guarded_live_auto_buy_submitted",
            signal_id=signal_id,
            order_id=order_id,
            request_payload=_json(
                {
                    **request_payload,
                    "mode": MODE,
                    "source_dry_run_id": dry_run.get("trade_run_id"),
                    "active_profile": profile.get("profile_name"),
                    "target_risk_result": target_risk,
                    "validation_result": validation,
                    "order_plan": plan,
                    "real_order_submitted": True,
                    "validation_called": True,
                    "broker_submit_called": True,
                    "manual_submit_called": False,
                }
            ),
        )
        db.add(run)
        db.flush()
        return run

    def _run_response(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "status": kwargs.get("status"),
            "action": kwargs.get("action"),
            "provider": PROVIDER,
            "market": MARKET,
            "active_profile": kwargs.get("active_profile"),
            "symbol": kwargs.get("symbol"),
            "symbol_name": kwargs.get("symbol_name"),
            "source_dry_run_id": kwargs.get("source_dry_run_id"),
            "source_signal_id": kwargs.get("source_signal_id"),
            "source_trade_run_id": kwargs.get("source_trade_run_id"),
            "target_risk_approved": bool(kwargs.get("target_risk_approved")),
            "validation_approved": bool(kwargs.get("validation_approved")),
            "submitted": bool(kwargs.get("submitted")),
            "quantity": kwargs.get("quantity"),
            "estimated_price": kwargs.get("estimated_price"),
            "submitted_notional_krw": kwargs.get("submitted_notional_krw"),
            "related_order_id": kwargs.get("related_order_id"),
            "broker_order_id": kwargs.get("broker_order_id"),
            "broker_status": kwargs.get("broker_status"),
            "internal_status": kwargs.get("internal_status"),
            "block_reason": kwargs.get("block_reason"),
            "risk_flags": _dedupe(kwargs.get("risk_flags") or []),
            "gating_notes": _dedupe(kwargs.get("gating_notes") or []),
            "attempt_id": kwargs.get("attempt_id"),
            "signal_id": kwargs.get("signal_id"),
            "trade_run_id": kwargs.get("trade_run_id"),
            "safety": kwargs.get("safety") or _safety(),
        }

    def _response_from_attempt(
        self,
        attempt: StrategyLiveAutoBuyAttempt,
        *,
        idempotent_replay: bool = False,
    ) -> dict[str, Any]:
        payload = _parse_object(attempt.response_payload)
        if not payload:
            payload = self._attempt_item(attempt)
        payload["attempt_id"] = attempt.id
        safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
        if idempotent_replay:
            safety = {**safety, "idempotent_replay": True}
        payload["safety"] = safety
        return sanitize_kis_payload(payload)

    def _attempt_item(self, attempt: StrategyLiveAutoBuyAttempt) -> dict[str, Any]:
        payload = _parse_object(attempt.response_payload)
        if payload:
            payload.setdefault("attempt_id", attempt.id)
            payload.setdefault("created_at", _iso(attempt.created_at))
            return payload
        return {
            "attempt_id": attempt.id,
            "status": attempt.status,
            "provider": attempt.provider,
            "market": attempt.market,
            "active_profile": attempt.active_profile,
            "symbol": attempt.symbol,
            "symbol_name": attempt.symbol_name,
            "source_dry_run_id": attempt.source_dry_run_id,
            "quantity": attempt.quantity,
            "estimated_price": attempt.estimated_price,
            "submitted_notional_krw": attempt.estimated_notional_krw,
            "related_order_id": attempt.related_order_id,
            "broker_order_id": attempt.broker_order_id,
            "block_reason": attempt.block_reason,
            "risk_flags": _parse_list(attempt.risk_flags),
            "gating_notes": _parse_list(attempt.gating_notes),
            "safety": _parse_object(attempt.safety_flags),
            "created_at": _iso(attempt.created_at),
            "submitted_at": _iso(attempt.submitted_at),
            "synced_at": _iso(attempt.synced_at),
        }


def _allowed_profiles(settings: dict[str, Any]) -> list[str]:
    value = settings.get("strategy_live_auto_buy_allowed_profiles")
    if isinstance(value, list):
        profiles = [str(item).strip() for item in value if str(item).strip()]
    else:
        profiles = []
    return profiles or ["safe", "balanced"]


def _safety(*, read_only: bool = False) -> dict[str, Any]:
    return {
        "read_only": read_only,
        "real_order_submitted": False,
        "validation_called": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "scheduler_changed": False,
        "setting_changed": False,
        "dry_run_changed": False,
        "kill_switch_changed": False,
        "kis_real_order_changed": False,
    }


def _check(key: str, ok: bool, message: str, *, reason: str) -> dict[str, Any]:
    return {
        "key": key,
        "ok": bool(ok),
        "severity": "ok" if ok else "block",
        "reason": None if ok else reason,
        "message": message,
    }


def _account_block_reason(exc: ValueError) -> str:
    reason = str(exc).split(":", 1)[0].strip()
    return reason or "account_snapshot_unavailable"


def _has_position(positions: list[dict[str, Any]], symbol: str) -> bool:
    normalized = str(symbol or "").strip().upper()
    return any(
        str(item.get("symbol") or item.get("pdno") or "").strip().upper() == normalized
        and _position_qty(item) > 0
        for item in positions
    )


def _position_qty(item: dict[str, Any]) -> float:
    return _float(item.get("qty") or item.get("quantity") or item.get("hldg_qty")) or 0.0


def _cash(balance: dict[str, Any]) -> float | None:
    for key in ("cash", "available_cash", "dnca_tot_amt", "ord_psbl_cash"):
        value = _float(balance.get(key))
        if value is not None:
            return value
    return None


def _extract_broker_order_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("order_id", "broker_order_id", "kis_odno", "odno", "ODNO"):
        raw = value.get(key)
        if raw:
            return str(raw)
    output = value.get("output")
    if isinstance(output, dict):
        return _extract_broker_order_id(output)
    return None


def _extract_broker_status(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("status", "broker_status", "rt_cd", "msg_cd"):
            raw = value.get(key)
            if raw is not None:
                return str(raw)
    return "submitted"


def _attempt_status_from_order(order: OrderLog) -> str:
    status = str(order.internal_status or "").upper()
    if status == InternalOrderStatus.FILLED.value:
        return "filled"
    if status in {InternalOrderStatus.REJECTED.value, InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value}:
        return "rejected"
    if status == InternalOrderStatus.FAILED.value:
        return "failed"
    if status in {InternalOrderStatus.UNKNOWN_STALE.value, InternalOrderStatus.SYNC_FAILED.value}:
        return "sync_required"
    return "submitted"


def _kr_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    local = _utc_now(now_utc).astimezone(KR_TZ)
    start_local = datetime.combine(local.date(), time.min, tzinfo=KR_TZ)
    end_local = start_local + timedelta(days=1)
    return _naive_utc(start_local), _naive_utc(end_local)


def _utc_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(UTC)
    return value.replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _json(value: Any) -> str:
    return json.dumps(sanitize_kis_payload(value), ensure_ascii=False, default=str)


def _parse_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _parse_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 240:
        text = f"{text[:240]}..."
    return f"{exc.__class__.__name__}: {text}"
