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
    StrategyLiveAutoExitAttempt,
    TradeRunLog,
)
from app.schemas.strategy_live_auto_exit import (
    ProfileAwareGuardedLiveAutoExitRunRequest,
)
from app.services.kis_order_sync_service import KisOrderSyncService
from app.services.kis_order_validation_service import (
    KisOrderValidationRequest,
    KisOrderValidationService,
    record_kis_order_validation,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.strategy_profile_service import StrategyProfileService


MODE = "strategy_live_auto_exit"
TRIGGER_SOURCE = "profile_aware_guarded_live_auto_exit"
SOURCE_TYPE = "guarded_profile_exit"
PROVIDER = "kis"
MARKET = "KR"
SELL = "sell"
KR_TZ = ZoneInfo("Asia/Seoul")

SUBMITTED_ATTEMPT_STATUSES = {"submitted", "filled", "sync_required"}
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
EXIT_PRIORITY = {
    "stop_loss": 0,
    "monthly_loss_limit": 1,
    "max_holding_days": 2,
    "take_profit": 3,
    "target_hit_reduce": 4,
    "manual_review": 5,
    "none": 99,
}


class ProfileAwareGuardedLiveAutoExitService:
    """Manual one-shot guarded live sell path for held KIS positions."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        broker: Any | None = None,
        validation_service: Any | None = None,
        order_sync_service: Any | None = None,
        runtime_settings: RuntimeSettingService | None = None,
        strategy_profiles: StrategyProfileService | None = None,
        positions_loader: Callable[[Session], list[dict[str, Any]]] | None = None,
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
        self.positions_loader = positions_loader
        self.open_orders_loader = open_orders_loader

    def readiness(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
        symbol: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc_now(now)
        settings = self.runtime_settings.get_settings_read_only(db)
        global_settings = self._global_settings()
        profile = self._active_profile(db)
        profile_name = str(profile.get("profile_name") or "")
        allowed_profiles = _allowed_profiles(settings)
        orders_used_today = self._orders_used_today(db, now_utc=now_utc)
        max_orders = max(0, int(settings.get("strategy_live_auto_exit_max_orders_per_day") or 0))
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

        scheduler_live_enabled = bool(settings.get("strategy_live_auto_exit_scheduler_enabled"))
        profile_allowed = profile_name in allowed_profiles and (
            profile_name != "aggressive"
            or bool(settings.get("strategy_live_auto_exit_allow_aggressive"))
        )
        gate(
            "strategy_live_auto_exit_enabled",
            bool(settings.get("strategy_live_auto_exit_enabled")),
            "strategy_live_auto_exit_disabled",
            "strategy_live_auto_exit_enabled is false.",
        )
        gate(
            "dry_run_false",
            not bool(settings.get("dry_run")),
            "dry_run_enabled",
            "Runtime dry_run must be false before guarded live auto exit can run.",
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
            "strategy_live_auto_exit_scheduler_enabled",
            "Scheduler live auto-exit must remain disabled for PR75.",
        )
        gate(
            "active_profile_allowed",
            profile_allowed,
            "active_profile_not_allowed",
            f"Active profile {profile_name or 'unknown'} is not allowed for guarded live auto exit.",
        )
        gate(
            "daily_auto_exit_limit",
            orders_used_today < max_orders,
            "daily_live_auto_exit_limit_reached",
            f"Guarded live auto exit used {orders_used_today}/{max_orders} orders today.",
        )

        positions: list[dict[str, Any]] = []
        open_orders: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        selected: dict[str, Any] | None = None
        if bool(getattr(global_settings, "kis_enabled", False)) or self.positions_loader is not None:
            try:
                positions, open_orders = self._account_snapshot(db)
            except ValueError as exc:
                reason = _account_block_reason(exc)
                gate("account_snapshot", False, reason, str(exc))
            else:
                held_positions = _held_positions(positions, symbol=symbol)
                gate(
                    "held_position_exists",
                    bool(held_positions),
                    "no_held_position",
                    "A held KIS position is required for guarded live auto exit.",
                )
                candidates = self._evaluate_candidates(
                    db,
                    positions=held_positions,
                    open_orders=open_orders,
                    settings=settings,
                    profile=profile,
                    requested_symbol=symbol,
                    now_utc=now_utc,
                )
                selected = self._select_candidate(candidates)
                gate(
                    "eligible_exit_candidate",
                    selected is not None,
                    _candidate_block_reason(candidates),
                    "At least one eligible profile-aware exit candidate is required.",
                )
                if selected is not None:
                    gate(
                        "open_duplicate_sell_order",
                        not self._has_open_sell_order(db, selected["symbol"], open_orders),
                        "duplicate_open_sell_order",
                        "An open KIS sell order already exists for the selected symbol.",
                    )

        return sanitize_kis_payload(
            {
                "enabled": bool(settings.get("strategy_live_auto_exit_enabled")),
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
                "positions_count": len(_held_positions(positions, symbol=symbol)),
                "candidate_count": len(candidates),
                "selected_symbol": selected.get("symbol") if selected else None,
                "selected_trigger": selected.get("trigger") if selected else None,
                "max_orders_per_day": max_orders,
                "orders_used_today": orders_used_today,
                "orders_remaining_today": max(0, max_orders - orders_used_today),
                "primary_block_reason": primary,
                "checks": checks,
                "candidates": candidates,
                "risk_flags": _dedupe([*risk_flags, *_candidate_flags(candidates)]),
                "gating_notes": _dedupe([*gating_notes, *_candidate_notes(candidates)]),
                "safety": _safety(read_only=True),
            }
        )

    def run_once(
        self,
        db: Session,
        request: ProfileAwareGuardedLiveAutoExitRunRequest | dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        payload = (
            request
            if isinstance(request, ProfileAwareGuardedLiveAutoExitRunRequest)
            else ProfileAwareGuardedLiveAutoExitRunRequest.model_validate(request)
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
        request_payload = payload.model_dump(mode="json")

        if bool(settings.get("strategy_live_auto_exit_requires_operator_confirm")) and payload.confirm_operator_ack is not True:
            return self._blocked(db, request_payload=request_payload, status="blocked", block_reason="confirm_operator_ack_required", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)
        if not bool(settings.get("strategy_live_auto_exit_enabled")):
            return self._blocked(db, request_payload=request_payload, status="blocked", block_reason="strategy_live_auto_exit_disabled", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)
        if bool(settings.get("dry_run")):
            return self._blocked(db, request_payload=request_payload, status="blocked", block_reason="dry_run_enabled", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)
        if bool(settings.get("kill_switch")):
            return self._blocked(db, request_payload=request_payload, status="blocked", block_reason="kill_switch_enabled", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)
        if not bool(getattr(global_settings, "kis_enabled", False)):
            return self._blocked(db, request_payload=request_payload, status="blocked", block_reason="kis_disabled", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)
        if not bool(getattr(global_settings, "kis_real_order_enabled", False)):
            return self._blocked(db, request_payload=request_payload, status="blocked", block_reason="kis_real_order_disabled", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)
        if bool(settings.get("strategy_live_auto_exit_scheduler_enabled")):
            return self._blocked(db, request_payload=request_payload, status="blocked", block_reason="strategy_live_auto_exit_scheduler_enabled", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)
        if profile_name not in allowed_profiles or (
            profile_name == "aggressive"
            and not bool(settings.get("strategy_live_auto_exit_allow_aggressive"))
        ):
            return self._blocked(db, request_payload=request_payload, status="blocked", block_reason="active_profile_not_allowed", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)

        try:
            positions, open_orders = self._account_snapshot(db)
        except ValueError as exc:
            return self._blocked(db, request_payload=request_payload, status="blocked", block_reason=_account_block_reason(exc), safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id)
        candidates = self._evaluate_candidates(
            db,
            positions=_held_positions(positions, symbol=payload.symbol),
            open_orders=open_orders,
            settings=settings,
            profile=profile,
            requested_symbol=payload.symbol,
            now_utc=now_utc,
        )
        candidate = self._select_candidate(candidates)
        if candidate is None:
            return self._blocked(db, request_payload=request_payload, status="blocked", block_reason=_candidate_block_reason(candidates), safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id, candidates=candidates)

        orders_used_today = self._orders_used_today(db, now_utc=now_utc)
        max_orders = max(0, int(settings.get("strategy_live_auto_exit_max_orders_per_day") or 0))
        if orders_used_today >= max_orders:
            return self._blocked(db, request_payload=request_payload, status="blocked", block_reason="daily_live_auto_exit_limit_reached", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id, candidate=candidate, candidates=candidates)
        if self._has_open_sell_order(db, candidate["symbol"], open_orders):
            return self._blocked(db, request_payload=request_payload, status="blocked", block_reason="duplicate_open_sell_order", safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id, candidate=candidate, candidates=candidates)

        plan = self._exit_plan(settings=settings, candidate=candidate, requested_quantity=payload.quantity)
        if int(plan.get("quantity") or 0) <= 0:
            return self._blocked(db, request_payload=request_payload, status="blocked", block_reason=str(plan.get("block_reason") or "quantity_zero"), safety=safety, active_profile=profile_name, trigger_source=payload.trigger_source, client_request_id=payload.client_request_id, candidate=candidate, candidates=candidates, plan=plan)

        safety["validation_called"] = True
        validation = self._validate_order(db, payload, candidate, plan)
        if validation.get("validated_for_submission") is not True:
            return self._blocked(
                db,
                request_payload=request_payload,
                status="validation_failed",
                block_reason=str(
                    validation.get("primary_block_reason")
                    or (validation.get("block_reasons") or ["validation_failed"])[0]
                ),
                safety=safety,
                active_profile=profile_name,
                trigger_source=payload.trigger_source,
                client_request_id=payload.client_request_id,
                candidate=candidate,
                candidates=candidates,
                validation=validation,
                plan=plan,
            )

        return self._submit(
            db,
            request_payload=request_payload,
            run_request=payload,
            profile=profile,
            candidate=candidate,
            candidates=candidates,
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
            db.query(StrategyLiveAutoExitAttempt)
            .filter(StrategyLiveAutoExitAttempt.provider == str(provider).lower())
            .filter(StrategyLiveAutoExitAttempt.market == str(market).upper())
            .order_by(
                StrategyLiveAutoExitAttempt.created_at.desc(),
                StrategyLiveAutoExitAttempt.id.desc(),
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
        attempt = db.get(StrategyLiveAutoExitAttempt, int(attempt_id))
        if attempt is None:
            raise ValueError("strategy_live_auto_exit_attempt_not_found")
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
        candidate: dict[str, Any] | None = None,
        candidates: list[dict[str, Any]] | None = None,
        validation: dict[str, Any] | None = None,
        plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        selected = candidate or self._select_candidate(candidates or []) or _first_candidate(candidates)
        response = self._run_response(
            status=status,
            action="blocked",
            active_profile=active_profile,
            candidate=selected,
            validation_approved=bool((validation or {}).get("validated_for_submission")),
            submitted=False,
            quantity=int((plan or {}).get("quantity") or 0) or None,
            submitted_notional_krw=(plan or {}).get("approved_notional_krw"),
            block_reason=block_reason,
            risk_flags=_dedupe([block_reason, *_strings((selected or {}).get("risk_flags"))]),
            gating_notes=_dedupe(_strings((selected or {}).get("gating_notes")) + [block_reason]),
            safety=safety,
        )
        attempt = self._save_attempt(
            db,
            response=response,
            request_payload=request_payload,
            status=status,
            trigger_source=trigger_source,
            client_request_id=client_request_id,
            validation=validation,
            candidate=selected,
        )
        response["attempt_id"] = attempt.id
        attempt.response_payload = _json(response)
        db.commit()
        return sanitize_kis_payload(response)

    def _account_snapshot(self, db: Session) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        try:
            positions = (
                self.positions_loader(db)
                if self.positions_loader is not None
                else self.client.list_positions()
            )
        except Exception as exc:
            raise ValueError(f"positions_unavailable: {_safe_error(exc)}") from exc
        try:
            open_orders = (
                self.open_orders_loader(db)
                if self.open_orders_loader is not None
                else self.client.list_open_orders()
            )
        except Exception as exc:
            raise ValueError(f"open_orders_unavailable: {_safe_error(exc)}") from exc
        return (
            positions if isinstance(positions, list) else [],
            open_orders if isinstance(open_orders, list) else [],
        )

    def _evaluate_candidates(
        self,
        db: Session,
        *,
        positions: list[dict[str, Any]],
        open_orders: list[dict[str, Any]],
        settings: dict[str, Any],
        profile: dict[str, Any],
        requested_symbol: str | None,
        now_utc: datetime,
    ) -> list[dict[str, Any]]:
        candidates = [
            self._candidate_from_position(
                db,
                position,
                open_orders=open_orders,
                settings=settings,
                profile=profile,
                now_utc=now_utc,
            )
            for position in positions
            if not requested_symbol
            or _symbol(position) == str(requested_symbol).strip().upper()
        ]
        return sorted(
            candidates,
            key=lambda item: (
                0 if item.get("eligible") else 1,
                EXIT_PRIORITY.get(str(item.get("trigger") or "none"), 99),
                -abs(float(item.get("unrealized_pnl_pct") or 0)),
                str(item.get("symbol") or ""),
            ),
        )

    def _candidate_from_position(
        self,
        db: Session,
        position: dict[str, Any],
        *,
        open_orders: list[dict[str, Any]],
        settings: dict[str, Any],
        profile: dict[str, Any],
        now_utc: datetime,
    ) -> dict[str, Any]:
        symbol = _symbol(position) or ""
        quantity = int(math.floor(_position_qty(position)))
        current_price = _position_current_price(position)
        cost_basis = _position_cost_basis(position)
        current_value = _position_current_value(position, quantity=quantity, current_price=current_price)
        unrealized_pnl = (
            current_value - cost_basis
            if current_value is not None and cost_basis is not None
            else _float(position.get("unrealized_pl"))
        )
        unrealized_pnl_pct = (
            unrealized_pnl / cost_basis
            if unrealized_pnl is not None and cost_basis is not None and cost_basis > 0
            else None
        )
        position_age_days = _position_age_days(position, now_utc=now_utc)
        stop_loss_pct = _negative_threshold(profile.get("stop_loss_pct"), -0.012)
        take_profit_pct = _positive_threshold(profile.get("take_profit_pct"), 0.02)
        max_holding_days = int(profile.get("max_holding_days") or 0)
        duplicate_open_sell = self._has_open_sell_order(db, symbol, open_orders)
        requires_cost_basis = bool(settings.get("strategy_live_auto_exit_requires_cost_basis"))

        data_quality = {
            "quantity_valid": quantity > 0,
            "current_price_valid": current_price is not None and current_price > 0,
            "cost_basis_valid": cost_basis is not None and cost_basis > 0,
            "current_value_valid": current_value is not None and current_value > 0,
            "pnl_pct_calculated_from_cost_basis": (
                unrealized_pnl_pct is not None and cost_basis is not None and cost_basis > 0
            ),
        }
        risk_flags: list[str] = []
        gating_notes: list[str] = []
        block_reason: str | None = None
        trigger = "none"
        reason = "no_exit_trigger"

        if quantity <= 0:
            block_reason = "quantity_not_positive"
        elif current_price is None or current_price <= 0:
            block_reason = "current_price_unavailable"
        elif requires_cost_basis and (cost_basis is None or cost_basis <= 0):
            block_reason = "cost_basis_unavailable"
            risk_flags.append("insufficient_cost_basis")
        elif requires_cost_basis and unrealized_pnl_pct is None:
            block_reason = "missing_or_ambiguous_pl_basis"
            risk_flags.append("missing_or_ambiguous_pl_basis")
        elif duplicate_open_sell:
            block_reason = "duplicate_open_sell_order"
            risk_flags.append("duplicate_open_sell_order")

        if block_reason is None:
            if (
                bool(settings.get("strategy_live_auto_exit_allow_stop_loss"))
                and unrealized_pnl_pct is not None
                and unrealized_pnl_pct <= stop_loss_pct
            ):
                trigger = "stop_loss"
                reason = "stop_loss_threshold_reached"
                risk_flags.append("stop_loss_triggered")
            elif (
                bool(settings.get("strategy_live_auto_exit_allow_monthly_loss_exit"))
                and _monthly_loss_triggered(position, unrealized_pnl_pct)
            ):
                trigger = "monthly_loss_limit"
                reason = "monthly_loss_limit_exit"
                risk_flags.append("monthly_loss_limit")
            elif (
                bool(settings.get("strategy_live_auto_exit_allow_max_holding_days"))
                and position_age_days is not None
                and max_holding_days > 0
                and position_age_days >= max_holding_days
            ):
                trigger = "max_holding_days"
                reason = "max_holding_days_reached"
                risk_flags.append("max_holding_days")
            elif unrealized_pnl_pct is not None and unrealized_pnl_pct >= take_profit_pct:
                trigger = "take_profit"
                reason = "take_profit_threshold_reached"
                risk_flags.append("take_profit_triggered")
                if not bool(settings.get("strategy_live_auto_exit_allow_take_profit")):
                    block_reason = "take_profit_disabled"
                    gating_notes.append("Take-profit auto exit is disabled by default.")
            elif (
                bool(settings.get("strategy_live_auto_exit_allow_target_hit_reduce"))
                and _truthy(position.get("target_hit_reduce"))
            ):
                trigger = "target_hit_reduce"
                reason = "target_hit_reduce"
                risk_flags.append("target_hit_reduce")

        eligible = block_reason is None and trigger != "none"
        if not eligible and block_reason is None:
            block_reason = "no_exit_trigger"
        if eligible:
            gating_notes.append("Held position exit candidate passed profile-aware candidate gates.")
        else:
            gating_notes.append(f"Exit candidate blocked: {block_reason}.")

        return {
            "symbol": symbol,
            "symbol_name": _name(position),
            "quantity": max(0, quantity),
            "current_price": _round(current_price),
            "cost_basis": _round(cost_basis),
            "current_value": _round(current_value),
            "unrealized_pnl": _round(unrealized_pnl),
            "unrealized_pnl_pct": _round_ratio(unrealized_pnl_pct),
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "position_age_days": _round_ratio(position_age_days),
            "max_holding_days": max_holding_days,
            "trigger": trigger,
            "reason": reason,
            "eligible": eligible,
            "block_reason": None if eligible else block_reason,
            "risk_flags": _dedupe(risk_flags),
            "gating_notes": _dedupe(gating_notes),
            "data_quality": data_quality,
        }

    def _select_candidate(self, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        for candidate in candidates:
            if candidate.get("eligible") is True:
                return candidate
        return None

    def _exit_plan(
        self,
        *,
        settings: dict[str, Any],
        candidate: dict[str, Any],
        requested_quantity: int | None,
    ) -> dict[str, Any]:
        held_qty = int(candidate.get("quantity") or 0)
        current_price = _float(candidate.get("current_price"))
        if held_qty <= 0:
            return {"quantity": 0, "block_reason": "quantity_zero"}
        if current_price is None or current_price <= 0:
            return {"quantity": 0, "block_reason": "current_price_unavailable"}
        max_position_pct = max(
            0.0,
            min(float(settings.get("strategy_live_auto_exit_max_position_pct") or 0), 1.0),
        )
        max_notional = max(0.0, float(settings.get("strategy_live_auto_exit_max_notional_krw") or 0))
        min_quantity = max(1, int(settings.get("strategy_live_auto_exit_min_quantity") or 1))
        caps = [held_qty]
        if requested_quantity is not None:
            caps.append(max(0, int(requested_quantity)))
        if max_position_pct > 0:
            caps.append(max(1, math.floor(held_qty * max_position_pct)))
        if max_notional > 0:
            caps.append(max(0, math.floor(max_notional / current_price)))
        quantity = min(caps)
        if quantity > held_qty:
            quantity = held_qty
        if quantity < min_quantity:
            return {
                "quantity": 0,
                "held_quantity": held_qty,
                "block_reason": "quantity_below_minimum",
            }
        notional = round(quantity * current_price, 2)
        return {
            "quantity": int(quantity),
            "held_quantity": held_qty,
            "current_price": current_price,
            "requested_quantity": requested_quantity,
            "approved_notional_krw": notional,
            "block_reason": None,
        }

    def _validate_order(
        self,
        db: Session,
        payload: ProfileAwareGuardedLiveAutoExitRunRequest,
        candidate: dict[str, Any],
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        if self.validation_service is None:
            return {
                "validated_for_submission": False,
                "block_reasons": ["kis_validation_service_unavailable"],
            }
        request = KisOrderValidationRequest(
            market=payload.market,
            symbol=str(candidate.get("symbol") or ""),
            side=SELL,
            qty=int(plan["quantity"]),
            order_type="market",
            dry_run=True,
            reason="strategy guarded live auto exit pre-submit validation",
            source_metadata={
                "source_context": TRIGGER_SOURCE,
                "source_type": SOURCE_TYPE,
                "mode": MODE,
                "exit_trigger": candidate.get("trigger"),
                "exit_reason": candidate.get("reason"),
                "active_profile": candidate.get("active_profile"),
            },
        )
        result = self.validation_service.validate(request)
        try:
            record_kis_order_validation(db, request=request, result=result)
        except Exception:
            pass
        return sanitize_kis_payload(result.to_dict() if hasattr(result, "to_dict") else dict(result))

    def _orders_used_today(self, db: Session, *, now_utc: datetime) -> int:
        start_utc, end_utc = _kr_day_bounds_utc(now_utc)
        return (
            db.query(StrategyLiveAutoExitAttempt)
            .filter(StrategyLiveAutoExitAttempt.provider == PROVIDER)
            .filter(StrategyLiveAutoExitAttempt.market == MARKET)
            .filter(StrategyLiveAutoExitAttempt.status.in_(sorted(SUBMITTED_ATTEMPT_STATUSES)))
            .filter(StrategyLiveAutoExitAttempt.created_at >= start_utc)
            .filter(StrategyLiveAutoExitAttempt.created_at < end_utc)
            .count()
        )

    def _has_open_sell_order(
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
            if "sell" in side or "매도" in side or side in {"s", "01"}:
                return True
        return (
            db.query(OrderLog)
            .filter(OrderLog.broker == PROVIDER)
            .filter(OrderLog.market == MARKET)
            .filter(OrderLog.symbol == normalized)
            .filter(OrderLog.side == SELL)
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
        payload: ProfileAwareGuardedLiveAutoExitRunRequest,
    ) -> StrategyLiveAutoExitAttempt | None:
        if not payload.client_request_id:
            return None
        return (
            db.query(StrategyLiveAutoExitAttempt)
            .filter(StrategyLiveAutoExitAttempt.provider == payload.provider)
            .filter(StrategyLiveAutoExitAttempt.market == payload.market)
            .filter(StrategyLiveAutoExitAttempt.client_request_id == payload.client_request_id)
            .order_by(StrategyLiveAutoExitAttempt.created_at.desc(), StrategyLiveAutoExitAttempt.id.desc())
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
        validation: dict[str, Any] | None = None,
        candidate: dict[str, Any] | None = None,
        related_order_id: int | None = None,
    ) -> StrategyLiveAutoExitAttempt:
        attempt = StrategyLiveAutoExitAttempt(
            provider=PROVIDER,
            market=MARKET,
            active_profile=response.get("active_profile"),
            symbol=response.get("symbol"),
            symbol_name=response.get("symbol_name"),
            status=status,
            trigger_source=trigger_source or "manual",
            client_request_id=client_request_id,
            exit_trigger=response.get("exit_trigger"),
            exit_reason=response.get("exit_reason"),
            quantity=response.get("quantity"),
            current_price=response.get("current_price"),
            cost_basis=(candidate or {}).get("cost_basis"),
            unrealized_pnl=(candidate or {}).get("unrealized_pnl"),
            unrealized_pnl_pct=(candidate or {}).get("unrealized_pnl_pct"),
            stop_loss_pct=(candidate or {}).get("stop_loss_pct"),
            take_profit_pct=(candidate or {}).get("take_profit_pct"),
            max_holding_days=(candidate or {}).get("max_holding_days"),
            position_age_days=(candidate or {}).get("position_age_days"),
            requested_notional_krw=response.get("submitted_notional_krw"),
            approved_notional_krw=response.get("submitted_notional_krw"),
            target_risk_result=_json({"candidate": candidate or {}}),
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
        run_request: ProfileAwareGuardedLiveAutoExitRunRequest,
        profile: dict[str, Any],
        candidate: dict[str, Any],
        validation: dict[str, Any],
        plan: dict[str, Any],
        internal_status: str,
        safety: dict[str, Any],
    ) -> OrderLog:
        row = OrderLog(
            broker=PROVIDER,
            market=MARKET,
            symbol=str(candidate.get("symbol") or ""),
            side=SELL,
            order_type="market",
            time_in_force="day",
            qty=float(plan["quantity"]),
            requested_qty=float(plan["quantity"]),
            remaining_qty=float(plan["quantity"]),
            notional=float(plan.get("approved_notional_krw") or 0),
            internal_status=internal_status,
            request_payload=_json(
                {
                    **request_payload,
                    "mode": MODE,
                    "source": MODE,
                    "source_type": SOURCE_TYPE,
                    "trigger_source": TRIGGER_SOURCE,
                    "operator_trigger_source": run_request.trigger_source,
                    "active_profile": profile.get("profile_name"),
                    "exit_trigger": candidate.get("trigger"),
                    "exit_reason": candidate.get("reason"),
                    "candidate": candidate,
                    "validation_result": validation,
                    "quantity": plan["quantity"],
                    "current_price": plan["current_price"],
                    "approved_notional_krw": plan["approved_notional_krw"],
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
        candidate: dict[str, Any],
        profile: dict[str, Any],
        plan: dict[str, Any],
        order_id: int,
    ) -> SignalLog:
        signal = SignalLog(
            symbol=str(candidate.get("symbol") or ""),
            action=SELL,
            buy_score=None,
            sell_score=None,
            confidence=None,
            reason=str(candidate.get("reason") or "guarded_live_auto_exit_submitted"),
            final_sell_score=None,
            risk_flags=_json(_strings(candidate.get("risk_flags"))),
            approved_by_risk=True,
            position_size_pct=None,
            planned_stop_loss_pct=_float(candidate.get("stop_loss_pct")),
            planned_take_profit_pct=_float(candidate.get("take_profit_pct")),
            related_order_id=order_id,
            signal_status="submitted",
            trigger_source=TRIGGER_SOURCE,
            gate_profile_name=str(profile.get("profile_name") or ""),
            hard_blocked=False,
            gating_notes=_json(_strings(candidate.get("gating_notes"))),
        )
        db.add(signal)
        db.flush()
        return signal

    def _save_run(
        self,
        db: Session,
        *,
        request_payload: dict[str, Any],
        candidate: dict[str, Any],
        profile: dict[str, Any],
        validation: dict[str, Any],
        plan: dict[str, Any],
        order_id: int,
        signal_id: int,
    ) -> TradeRunLog:
        run = TradeRunLog(
            run_key=f"strategy_live_exit_{uuid.uuid4().hex[:12]}",
            trigger_source=TRIGGER_SOURCE,
            symbol=str(candidate.get("symbol") or ""),
            mode=MODE,
            stage="done",
            result="submitted",
            reason=str(candidate.get("reason") or "guarded_live_auto_exit_submitted"),
            signal_id=signal_id,
            order_id=order_id,
            request_payload=_json(
                {
                    **request_payload,
                    "mode": MODE,
                    "source_type": SOURCE_TYPE,
                    "active_profile": profile.get("profile_name"),
                    "candidate": candidate,
                    "validation_result": validation,
                    "plan": plan,
                }
            ),
            response_payload=_json(
                {
                    "mode": MODE,
                    "result": "submitted",
                    "symbol": candidate.get("symbol"),
                    "exit_trigger": candidate.get("trigger"),
                    "exit_reason": candidate.get("reason"),
                    "order_id": order_id,
                    "signal_id": signal_id,
                    "manual_submit_called": False,
                }
            ),
        )
        db.add(run)
        db.flush()
        return run

    def _run_response(self, **kwargs: Any) -> dict[str, Any]:
        candidate = kwargs.get("candidate") if isinstance(kwargs.get("candidate"), dict) else {}
        return {
            "status": kwargs.get("status"),
            "action": kwargs.get("action"),
            "provider": PROVIDER,
            "market": MARKET,
            "active_profile": kwargs.get("active_profile"),
            "symbol": kwargs.get("symbol") or candidate.get("symbol"),
            "symbol_name": kwargs.get("symbol_name") or candidate.get("symbol_name"),
            "exit_trigger": kwargs.get("exit_trigger") or candidate.get("trigger"),
            "exit_reason": kwargs.get("exit_reason") or candidate.get("reason"),
            "submitted": bool(kwargs.get("submitted")),
            "quantity": kwargs.get("quantity"),
            "current_price": kwargs.get("current_price") or candidate.get("current_price"),
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
        attempt: StrategyLiveAutoExitAttempt,
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

    def _attempt_item(self, attempt: StrategyLiveAutoExitAttempt) -> dict[str, Any]:
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
            "exit_trigger": attempt.exit_trigger,
            "exit_reason": attempt.exit_reason,
            "quantity": attempt.quantity,
            "current_price": attempt.current_price,
            "submitted_notional_krw": attempt.approved_notional_krw,
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

    def _submit(
        self,
        db: Session,
        *,
        request_payload: dict[str, Any],
        run_request: ProfileAwareGuardedLiveAutoExitRunRequest,
        profile: dict[str, Any],
        candidate: dict[str, Any],
        candidates: list[dict[str, Any]],
        validation: dict[str, Any],
        plan: dict[str, Any],
        safety: dict[str, Any],
        now_utc: datetime,
    ) -> dict[str, Any]:
        if self.broker is None:
            return self._blocked(db, request_payload=request_payload, status="failed", block_reason="kis_broker_unavailable", safety=safety, active_profile=profile.get("profile_name"), trigger_source=run_request.trigger_source, client_request_id=run_request.client_request_id, candidate=candidate, candidates=candidates, validation=validation, plan=plan)

        order = self._create_order_log(
            db,
            request_payload=request_payload,
            run_request=run_request,
            profile=profile,
            candidate=candidate,
            validation=validation,
            plan=plan,
            internal_status=InternalOrderStatus.REQUESTED.value,
            safety=safety,
        )
        attempt_response = self._run_response(
            status="submitting",
            action="submitting",
            active_profile=profile.get("profile_name"),
            candidate=candidate,
            validation_approved=True,
            submitted=False,
            quantity=int(plan["quantity"]),
            submitted_notional_krw=plan.get("approved_notional_krw"),
            related_order_id=order.id,
            internal_status=order.internal_status,
            risk_flags=_strings(candidate.get("risk_flags")),
            gating_notes=_strings(candidate.get("gating_notes")),
            safety=safety,
        )
        attempt = self._save_attempt(
            db,
            response=attempt_response,
            request_payload=request_payload,
            status="submitting",
            trigger_source=run_request.trigger_source,
            client_request_id=run_request.client_request_id,
            validation=validation,
            candidate=candidate,
            related_order_id=order.id,
        )
        safety["broker_submit_called"] = True
        try:
            broker_response = self.broker.submit_market_sell(
                symbol=str(candidate.get("symbol") or ""),
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
                candidate=candidate,
                validation_approved=True,
                submitted=False,
                quantity=int(plan["quantity"]),
                submitted_notional_krw=plan.get("approved_notional_krw"),
                related_order_id=order.id,
                internal_status=order.internal_status,
                block_reason="broker_submit_sync_required",
                risk_flags=["broker_submit_sync_required"],
                gating_notes=["Broker sell submit raised after call; manual sync is required before retry."],
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
            candidate=candidate,
            profile=profile,
            plan=plan,
            order_id=order.id,
        )
        run = self._save_run(
            db,
            request_payload=request_payload,
            candidate=candidate,
            profile=profile,
            validation=validation,
            plan=plan,
            order_id=order.id,
            signal_id=signal.id,
        )
        response = self._run_response(
            status="submitted",
            action="submitted",
            active_profile=profile.get("profile_name"),
            candidate=candidate,
            validation_approved=True,
            submitted=True,
            quantity=int(plan["quantity"]),
            submitted_notional_krw=plan.get("approved_notional_krw"),
            related_order_id=order.id,
            broker_order_id=broker_order_id,
            broker_status=broker_status,
            internal_status=order.internal_status,
            risk_flags=_strings(candidate.get("risk_flags")),
            gating_notes=_dedupe(
                [
                    "All guarded live auto exit gates passed.",
                    *_strings(candidate.get("gating_notes")),
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


def _allowed_profiles(settings: dict[str, Any]) -> list[str]:
    value = settings.get("strategy_live_auto_exit_allowed_profiles")
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


def _candidate_block_reason(candidates: list[dict[str, Any]]) -> str:
    for candidate in candidates:
        reason = str(candidate.get("block_reason") or "").strip()
        if reason:
            return reason
    return "no_exit_candidate"


def _candidate_flags(candidates: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for candidate in candidates:
        values.extend(_strings(candidate.get("risk_flags")))
        reason = str(candidate.get("block_reason") or "").strip()
        if reason:
            values.append(reason)
    return _dedupe(values)


def _candidate_notes(candidates: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for candidate in candidates:
        values.extend(_strings(candidate.get("gating_notes")))
    return _dedupe(values)


def _first_candidate(candidates: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not candidates:
        return None
    return candidates[0]


def _held_positions(
    positions: list[dict[str, Any]],
    *,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    normalized = str(symbol or "").strip().upper()
    return [
        item
        for item in positions
        if isinstance(item, dict)
        and _position_qty(item) > 0
        and (not normalized or _symbol(item) == normalized)
    ]


def _symbol(item: dict[str, Any]) -> str:
    for key in ("symbol", "pdno", "code", "stock_code", "stck_shrn_iscd"):
        raw = item.get(key)
        if raw is not None and str(raw).strip():
            text = str(raw).strip().upper()
            return text.zfill(6) if text.isdigit() and len(text) <= 6 else text
    return ""


def _name(item: dict[str, Any]) -> str | None:
    for key in ("symbol_name", "name", "prdt_name", "stock_name", "hts_kor_isnm"):
        raw = item.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return None


def _position_qty(item: dict[str, Any]) -> float:
    for key in ("qty", "quantity", "hldg_qty", "hold_qty", "ord_psbl_qty"):
        value = _float(item.get(key))
        if value is not None:
            return value
    return 0.0


def _position_current_price(item: dict[str, Any]) -> float | None:
    for key in (
        "current_price",
        "last_price",
        "price",
        "prpr",
        "now_pric",
        "stck_prpr",
        "evlu_pfls_amt_price",
    ):
        value = _float(item.get(key))
        if value is not None and value > 0:
            return value
    current_value = _position_current_value(item)
    qty = _position_qty(item)
    if current_value is not None and qty > 0:
        return current_value / qty
    return None


def _position_cost_basis(item: dict[str, Any]) -> float | None:
    for key in (
        "cost_basis",
        "purchase_amount",
        "buy_amount",
        "pchs_amt",
        "pchs_amt_smtl_amt",
        "tot_pchs_amt",
    ):
        value = _float(item.get(key))
        if value is not None and value > 0:
            return value
    qty = _position_qty(item)
    for key in ("avg_price", "average_price", "avg_entry_price", "pchs_avg_pric"):
        avg_price = _float(item.get(key))
        if avg_price is not None and avg_price > 0 and qty > 0:
            return avg_price * qty
    return None


def _position_current_value(
    item: dict[str, Any],
    *,
    quantity: int | None = None,
    current_price: float | None = None,
) -> float | None:
    for key in (
        "current_value",
        "market_value",
        "evaluation_amount",
        "evlu_amt",
        "evlu_pfls_amt",
    ):
        value = _float(item.get(key))
        if value is not None and value > 0:
            return value
    qty = float(quantity if quantity is not None else _position_qty(item))
    price = current_price if current_price is not None else _position_current_price(item)
    if qty > 0 and price is not None and price > 0:
        return qty * price
    return None


def _position_age_days(item: dict[str, Any], *, now_utc: datetime) -> float | None:
    for key in ("position_age_days", "holding_days", "hold_days"):
        value = _float(item.get(key))
        if value is not None:
            return value
    for key in ("entry_at", "entered_at", "buy_at", "created_at", "first_buy_at", "pchs_dt"):
        raw = item.get(key)
        parsed = _parse_position_datetime(raw)
        if parsed is not None:
            delta = _aware_utc(now_utc) - parsed
            return max(0.0, delta.total_seconds() / 86400)
    return None


def _parse_position_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _aware_utc(value)
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=KR_TZ).astimezone(UTC)
        except ValueError:
            pass
    try:
        return _aware_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def _monthly_loss_triggered(
    position: dict[str, Any],
    unrealized_pnl_pct: float | None,
) -> bool:
    for key in ("monthly_loss_limit_triggered", "monthly_loss_triggered", "monthly_loss_exit"):
        if _truthy(position.get(key)):
            return True
    threshold = _negative_threshold(
        position.get("monthly_loss_limit_pct") or position.get("monthly_loss_pct"),
        None,
    )
    return (
        threshold is not None
        and unrealized_pnl_pct is not None
        and unrealized_pnl_pct <= threshold
    )


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "y", "yes", "on"}


def _negative_threshold(value: Any, default: float | None) -> float | None:
    number = _float(value)
    if number is None:
        return default
    number = abs(number)
    if number > 1:
        number = number / 100
    return -number


def _positive_threshold(value: Any, default: float) -> float:
    number = _float(value)
    if number is None:
        return default
    number = abs(number)
    if number > 1:
        number = number / 100
    return number


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def _round(value: Any) -> float | None:
    number = _float(value)
    return None if number is None else round(number, 4)


def _round_ratio(value: Any) -> float | None:
    number = _float(value)
    return None if number is None else round(number, 6)


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


def _json(value: Any) -> str:
    return json.dumps(sanitize_kis_payload(value), ensure_ascii=False, default=str)


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 240:
        text = f"{text[:240]}..."
    return f"{exc.__class__.__name__}: {text}"


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
