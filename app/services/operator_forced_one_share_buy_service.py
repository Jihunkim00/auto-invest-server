from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.core.constants import DEFAULT_GATE_LEVEL
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, TradeRunLog
from app.schemas.operation_test import OperatorForcedOneShareBuyRequest
from app.services.kis_dry_run_risk_service import BUY, MARKET, OPEN_ORDER_STATUSES, PROVIDER
from app.services.kis_manual_order_service import (
    KIS_MANUAL_CONFIRMATION_PHRASE,
    KisManualOrderService,
    KisManualOrderSubmitRequest,
)
from app.services.kis_order_sync_service import KisOrderSyncService, serialize_kis_order
from app.services.kis_order_validation_service import (
    KisOrderValidationRequest,
    KisOrderValidationService,
    record_kis_order_validation,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.kis_watchlist_preview_service import KisWatchlistPreviewService
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.technical_indicator_service import indicator_payload_is_quant_ready


MODE = "operator_forced_one_share_buy"
SOURCE = "kis_operator_forced_test_entry"
SOURCE_TYPE = "operator_forced_one_share_buy"
SOURCE_CONTEXT = "operator_forced_test_entry"
TRIGGER_SOURCE = "operator_forced_one_share_buy"
ENDPOINT = "/app/operation-test3/operator-forced-one-share-buy"
OPERATION_TEST = "test3"
OPERATOR_CONFIRMATION_PHRASE = "TEST3 LIVE BUY 1 SHARE"
FORCED_QTY = 1
MAX_NOTIONAL_KRW = 55_000.0
KR_TZ = ZoneInfo("Asia/Seoul")

LIVE_BUY_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}


class OperatorForcedOneShareBuyService:
    """Operation-test-only one-share KIS buy path.

    This service deliberately does not participate in automatic buy selection
    or scheduler hooks. It reuses validation and manual submit for the actual
    order path after operator-only gates pass.
    """

    def __init__(
        self,
        client: KisClient,
        *,
        preview_service: KisWatchlistPreviewService | None = None,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
    ) -> None:
        self.client = client
        self.preview_service = preview_service or KisWatchlistPreviewService(client)
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()

    def run(
        self,
        db: Session,
        request: OperatorForcedOneShareBuyRequest | dict[str, Any],
        *,
        now: datetime | None = None,
        gate_level: int = DEFAULT_GATE_LEVEL,
    ) -> dict[str, Any]:
        payload = (
            request
            if isinstance(request, OperatorForcedOneShareBuyRequest)
            else OperatorForcedOneShareBuyRequest.model_validate(request)
        )
        now_utc = _aware_utc(now)
        symbol = str(payload.symbol or "").strip().upper()
        operator = str(payload.operator or "").strip()
        request_payload = {
            "provider": PROVIDER,
            "market": MARKET,
            "mode": MODE,
            "source": SOURCE,
            "source_type": SOURCE_TYPE,
            "source_context": SOURCE_CONTEXT,
            "trigger_source": TRIGGER_SOURCE,
            "source_endpoint": ENDPOINT,
            "operation_test": OPERATION_TEST,
            "forced_test_entry": True,
            "operator": operator,
            "operator_symbol": symbol,
            "symbol": symbol,
            "qty": FORCED_QTY,
            "max_notional_krw": MAX_NOTIONAL_KRW,
            "confirm_live": bool(payload.confirm_live),
            "confirmation_provided": bool(payload.confirmation),
            "reason": payload.reason,
            "gate_level": gate_level,
        }

        block_reasons: list[str] = []
        if payload.confirm_live is not True:
            block_reasons.append("confirm_live_required")
        if payload.confirmation != OPERATOR_CONFIRMATION_PHRASE:
            block_reasons.append("confirmation_mismatch")
        if not operator:
            block_reasons.append("operator_required")
        if not _valid_kr_symbol(symbol):
            block_reasons.append("symbol_must_be_6_digit_kr_code")

        if block_reasons:
            return self._blocked(
                db,
                now_utc=now_utc,
                request_payload=request_payload,
                symbol=symbol,
                reason=block_reasons[0],
                block_reasons=block_reasons,
            )

        runtime = self.runtime_settings.get_settings(db)
        settings = self.client.settings
        market_session = self._market_session(now_utc)
        account_state = self._account_state(db)
        daily_limit = self._daily_limit_state(db, now_utc=now_utc)

        block_reasons.extend(
            _runtime_block_reasons(
                runtime=runtime,
                settings=settings,
                market_session=market_session,
                account_state=account_state,
                daily_limit=daily_limit,
            )
        )

        candidate: dict[str, Any] | None = None
        preview: dict[str, Any] = {}
        if not block_reasons:
            preview = self._preview(db, gate_level=gate_level)
            candidate = _find_candidate(preview, symbol=symbol)
            if candidate is None:
                block_reasons.append("requested_symbol_not_technical_candidate")
            else:
                block_reasons.extend(_technical_filter_reasons(candidate))
                candidate_price = _candidate_price(candidate)
                if candidate_price is None:
                    block_reasons.append("current_price_unavailable")
                elif candidate_price * FORCED_QTY > MAX_NOTIONAL_KRW:
                    block_reasons.append("max_notional_krw_exceeded")

        if block_reasons:
            return self._blocked(
                db,
                now_utc=now_utc,
                request_payload=request_payload,
                symbol=symbol,
                reason=block_reasons[0],
                block_reasons=_dedupe(block_reasons),
                runtime=runtime,
                market_session=market_session,
                account_state=account_state,
                daily_limit=daily_limit,
                candidate=candidate,
                preview=preview,
            )

        assert candidate is not None
        metadata = _source_metadata(
            request_payload=request_payload,
            candidate=candidate,
            runtime=runtime,
            market_session=market_session,
            account_state=account_state,
            daily_limit=daily_limit,
            validation_summary=None,
            manual_submit_called=False,
            real_order_submitted=False,
            broker_submit_called=False,
        )
        validation_request = KisOrderValidationRequest(
            market=MARKET,
            symbol=symbol,
            side=BUY,
            qty=FORCED_QTY,
            order_type="market",
            dry_run=True,
            reason="operator forced one-share buy validation for operation test3",
            source_metadata=metadata,
        )
        validation_called = True
        try:
            validation_result = KisOrderValidationService(
                self.client,
                session_service=self.session_service,
            ).validate(validation_request, now=now_utc)
            validation_row = record_kis_order_validation(
                db,
                request=validation_request,
                result=validation_result,
            )
            validation_summary = sanitize_kis_payload(validation_result.to_dict())
            validation_summary["validation_id"] = validation_row.id
        except Exception as exc:
            return self._blocked(
                db,
                now_utc=now_utc,
                request_payload=request_payload,
                symbol=symbol,
                reason="validation_failed",
                block_reasons=["validation_failed"],
                runtime=runtime,
                market_session=market_session,
                account_state=account_state,
                daily_limit=daily_limit,
                candidate=candidate,
                preview=preview,
                validation_called=validation_called,
                error=_safe_error(exc),
            )

        validation_blocks = _validation_block_reasons(validation_summary)
        estimated_amount = _safe_float_or_none(validation_summary.get("estimated_amount"))
        if estimated_amount is None or estimated_amount <= 0:
            validation_blocks.append("estimated_notional_unavailable")
        elif estimated_amount > MAX_NOTIONAL_KRW:
            validation_blocks.append("max_notional_krw_exceeded")

        if validation_blocks:
            return self._blocked(
                db,
                now_utc=now_utc,
                request_payload=request_payload,
                symbol=symbol,
                reason=validation_blocks[0],
                block_reasons=_dedupe(validation_blocks),
                runtime=runtime,
                market_session=market_session,
                account_state=account_state,
                daily_limit=daily_limit,
                candidate=candidate,
                preview=preview,
                validation_called=validation_called,
                validation_summary=validation_summary,
            )

        pre_submit_state = self._account_state(db)
        pre_submit_blocks = _zero_position_open_order_reasons(pre_submit_state, db)
        if pre_submit_blocks:
            return self._blocked(
                db,
                now_utc=now_utc,
                request_payload=request_payload,
                symbol=symbol,
                reason=pre_submit_blocks[0],
                block_reasons=pre_submit_blocks,
                runtime=runtime,
                market_session=market_session,
                account_state=pre_submit_state,
                daily_limit=daily_limit,
                candidate=candidate,
                preview=preview,
                validation_called=validation_called,
                validation_summary=validation_summary,
            )

        submit_metadata = _source_metadata(
            request_payload=request_payload,
            candidate=candidate,
            runtime=runtime,
            market_session=market_session,
            account_state=pre_submit_state,
            daily_limit=daily_limit,
            validation_summary=validation_summary,
            manual_submit_called=True,
            real_order_submitted=False,
            broker_submit_called=False,
        )
        manual_confirmation = str(
            getattr(settings, "kis_confirmation_phrase", KIS_MANUAL_CONFIRMATION_PHRASE)
            or KIS_MANUAL_CONFIRMATION_PHRASE
        )
        manual_request = KisManualOrderSubmitRequest(
            market=MARKET,
            symbol=symbol,
            side=BUY,
            qty=FORCED_QTY,
            order_type="market",
            dry_run=False,
            confirm_live=True,
            confirmation=manual_confirmation,
            reason="operator forced one-share buy for operation test3",
            source_context=SOURCE_CONTEXT,
            source_metadata=submit_metadata,
        )

        status_code: int | None = None
        try:
            status_code, manual_response = KisManualOrderService(
                self.client,
                session_service=self.session_service,
                runtime_settings=self.runtime_settings,
            ).submit_manual(db, manual_request, now=now_utc)
        except Exception as exc:
            return self._blocked(
                db,
                now_utc=now_utc,
                request_payload=request_payload,
                symbol=symbol,
                reason="manual_submit_failed",
                block_reasons=["manual_submit_failed"],
                runtime=runtime,
                market_session=market_session,
                account_state=pre_submit_state,
                daily_limit=daily_limit,
                candidate=candidate,
                preview=preview,
                validation_called=validation_called,
                validation_summary=validation_summary,
                manual_submit_called=True,
                error=_safe_error(exc),
            )

        manual_response = sanitize_kis_payload(manual_response)
        broker_order_confirmed = bool(
            manual_response.get("broker_order_id") or manual_response.get("kis_odno")
        )
        submitted = bool(
            status_code == 200
            and (
                manual_response.get("real_order_submitted") is True
                or broker_order_confirmed
            )
        )
        if not submitted:
            return self._blocked(
                db,
                now_utc=now_utc,
                request_payload=request_payload,
                symbol=symbol,
                reason=str(
                    manual_response.get("primary_block_reason")
                    or manual_response.get("reason")
                    or "manual_submit_blocked"
                ),
                block_reasons=_dedupe(
                    _string_list(manual_response.get("failed_checks"))
                    + _string_list(manual_response.get("block_reasons"))
                    + ["manual_submit_blocked"]
                ),
                runtime=runtime,
                market_session=market_session,
                account_state=pre_submit_state,
                daily_limit=daily_limit,
                candidate=candidate,
                preview=preview,
                validation_called=validation_called,
                validation_summary=validation_summary,
                manual_submit_called=True,
                manual_submit_response=manual_response,
                status_code=status_code,
            )

        post_submit_settings = self._disable_buy_enable_position_management(db)
        order_id = _safe_int(manual_response.get("order_id") or manual_response.get("order_log_id"))
        sync_summary = self._sync_submitted_order(db, order_id=order_id)
        lifecycle = sync_summary.get("lifecycle")
        lifecycle_created = bool(
            isinstance(lifecycle, dict) and lifecycle.get("created") is True
        )
        response = _base_response(
            now_utc=now_utc,
            request_payload=request_payload,
            symbol=symbol,
            result="submitted",
            action=BUY,
            reason="operator_forced_one_share_buy_submitted",
            block_reasons=[],
            runtime=post_submit_settings,
            market_session=market_session,
            account_state=pre_submit_state,
            daily_limit=daily_limit,
            candidate=candidate,
            preview=preview,
            validation_called=validation_called,
            validation_summary=validation_summary,
            manual_submit_called=True,
            manual_submit_response=manual_response,
            real_order_submitted=True,
            broker_submit_called=True,
            order_id=order_id,
            broker_order_id=manual_response.get("broker_order_id"),
            kis_odno=manual_response.get("kis_odno"),
            status_code=status_code,
        )
        response.update(
            {
                "manual_submit_status_code": status_code,
                "auto_buy_disabled_after_submit": True,
                "position_management_only_enabled": True,
                "scheduler_auto_call_enabled": False,
                "post_submit_settings": _post_submit_settings_snapshot(
                    post_submit_settings
                ),
                "order_sync": sync_summary,
                "lifecycle": lifecycle or {"created": False, "reason": "not_filled_yet"},
                "lifecycle_created": lifecycle_created,
            }
        )
        self._record_run(
            db,
            now_utc=now_utc,
            request_payload=request_payload,
            response=response,
            symbol=symbol,
            order_id=order_id,
        )
        return sanitize_kis_payload(response)

    def _preview(self, db: Session, *, gate_level: int) -> dict[str, Any]:
        try:
            return sanitize_kis_payload(
                self.preview_service.run_preview(
                    include_gpt=True,
                    gate_level=gate_level,
                    db=db,
                    record_run=False,
                    trigger_source=TRIGGER_SOURCE,
                )
            )
        except TypeError:
            return sanitize_kis_payload(
                self.preview_service.run_preview(
                    include_gpt=True,
                    gate_level=gate_level,
                    db=db,
                )
            )

    def _market_session(self, now_utc: datetime) -> dict[str, Any]:
        try:
            return sanitize_kis_payload(
                self.session_service.get_session_status(MARKET, now=now_utc)
            )
        except Exception as exc:
            return {
                "market": MARKET,
                "timezone": "Asia/Seoul",
                "is_market_open": False,
                "is_entry_allowed_now": False,
                "error": _safe_error(exc),
            }

    def _account_state(self, db: Session) -> dict[str, Any]:
        state: dict[str, Any] = {
            "provider": PROVIDER,
            "market": MARKET,
            "balance": None,
            "positions": [],
            "open_orders": [],
            "db_open_order_count": 0,
            "warnings": [],
            "fetch_success": True,
        }
        try:
            state["balance"] = self.client.get_account_balance()
        except Exception as exc:
            state["fetch_success"] = False
            state["warnings"].append(f"balance_unavailable:{exc.__class__.__name__}")
        try:
            state["positions"] = [
                item for item in _dict_list(self.client.list_positions()) if _position_qty(item) > 0
            ]
        except Exception as exc:
            state["fetch_success"] = False
            state["warnings"].append(f"positions_unavailable:{exc.__class__.__name__}")
        try:
            state["open_orders"] = [
                item
                for item in _dict_list(self.client.list_open_orders())
                if _open_order_remaining(item) is None or _open_order_remaining(item) > 0
            ]
        except Exception as exc:
            state["fetch_success"] = False
            state["warnings"].append(f"open_orders_unavailable:{exc.__class__.__name__}")
        state["db_open_order_count"] = _db_open_order_count(db)
        return sanitize_kis_payload(state)

    def _daily_limit_state(self, db: Session, *, now_utc: datetime) -> dict[str, Any]:
        count = _daily_buy_count(db, now_utc=now_utc)
        return {
            "daily_buy_count": count,
            "daily_buy_limit": 1,
            "daily_buy_limit_remaining": max(0, 1 - count),
        }

    def _disable_buy_enable_position_management(self, db: Session) -> dict[str, Any]:
        payload = {
            "dry_run": False,
            "scheduler_enabled": False,
            "kis_scheduler_enabled": False,
            "kis_scheduler_dry_run": True,
            "kis_scheduler_live_enabled": False,
            "kis_scheduler_allow_real_orders": False,
            "kis_scheduler_configured_allow_real_orders": False,
            "kis_scheduler_buy_enabled": False,
            "kis_scheduler_allow_limited_auto_buy": False,
            "kis_scheduler_sell_enabled": False,
            "kis_scheduler_allow_limited_auto_sell": False,
            "kis_live_auto_buy_enabled": False,
            "kis_limited_auto_buy_enabled": False,
            "strategy_live_auto_buy_enabled": False,
            "strategy_live_auto_buy_scheduler_enabled": False,
            "strategy_auto_buy_scheduler_enabled": False,
            "strategy_auto_buy_scheduler_allow_live_orders": False,
            "auto_buy_live_phase1_enabled": False,
            "auto_buy_live_phase1_allow_real_orders": False,
            "portfolio_orchestrator_enabled": False,
            "portfolio_orchestrator_allow_live_orders": False,
            "position_management_scheduler_enabled": False,
            "kis_position_lifecycle_scheduler_enabled": False,
            "position_management_scheduler_dry_run_only": True,
            "position_management_scheduler_allow_live_orders": False,
            "kis_live_auto_sell_enabled": True,
            "kis_limited_auto_sell_enabled": True,
            "kis_limited_auto_stop_loss_enabled": True,
            "kis_limited_auto_sell_stop_loss_enabled": True,
            "kis_limited_auto_take_profit_enabled": False,
            "kis_limited_auto_sell_take_profit_enabled": False,
            "kis_limited_auto_sell_allow_take_profit_trigger": False,
            "kis_limited_auto_sell_max_orders_per_day": 1,
        }
        return self.runtime_settings.update_settings(db, payload)

    def _sync_submitted_order(
        self,
        db: Session,
        *,
        order_id: int | None,
    ) -> dict[str, Any]:
        if order_id is None:
            return {"attempted": False, "reason": "order_id_missing"}
        try:
            order = KisOrderSyncService(self.client).sync_order(db, order_id)
        except Exception as exc:
            return {
                "attempted": True,
                "reason": "order_sync_failed",
                "error": _safe_error(exc),
                "order_id": order_id,
            }
        order_payload = serialize_kis_order(order)
        lifecycle = _lifecycle_for_order(db, order_id)
        return {
            "attempted": True,
            "reason": "order_sync_completed",
            "order": order_payload,
            "lifecycle": lifecycle,
        }

    def _blocked(
        self,
        db: Session,
        *,
        now_utc: datetime,
        request_payload: dict[str, Any],
        symbol: str,
        reason: str,
        block_reasons: list[str],
        runtime: dict[str, Any] | None = None,
        market_session: dict[str, Any] | None = None,
        account_state: dict[str, Any] | None = None,
        daily_limit: dict[str, Any] | None = None,
        candidate: dict[str, Any] | None = None,
        preview: dict[str, Any] | None = None,
        validation_called: bool = False,
        validation_summary: dict[str, Any] | None = None,
        manual_submit_called: bool = False,
        manual_submit_response: dict[str, Any] | None = None,
        status_code: int | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        response = _base_response(
            now_utc=now_utc,
            request_payload=request_payload,
            symbol=symbol,
            result="blocked",
            action="blocked_buy",
            reason=reason,
            block_reasons=_dedupe(block_reasons),
            runtime=runtime,
            market_session=market_session,
            account_state=account_state,
            daily_limit=daily_limit,
            candidate=candidate,
            preview=preview,
            validation_called=validation_called,
            validation_summary=validation_summary,
            manual_submit_called=manual_submit_called,
            manual_submit_response=manual_submit_response,
            real_order_submitted=False,
            broker_submit_called=False,
            order_id=_safe_int(
                (manual_submit_response or {}).get("order_id")
                or (manual_submit_response or {}).get("order_log_id")
            ),
            broker_order_id=None,
            kis_odno=None,
            status_code=status_code,
            error=error,
        )
        self._record_run(
            db,
            now_utc=now_utc,
            request_payload=request_payload,
            response=response,
            symbol=symbol or "UNKNOWN",
            order_id=response.get("order_id"),
        )
        return sanitize_kis_payload(response)

    def _record_run(
        self,
        db: Session,
        *,
        now_utc: datetime,
        request_payload: dict[str, Any],
        response: dict[str, Any],
        symbol: str,
        order_id: int | None,
    ) -> TradeRunLog:
        run = TradeRunLog(
            run_key=f"{MODE}_{uuid.uuid4().hex[:10]}",
            trigger_source=TRIGGER_SOURCE,
            symbol=symbol or "UNKNOWN",
            mode=MODE,
            symbol_role="operator_requested_symbol",
            gate_level=_safe_int(request_payload.get("gate_level")),
            stage="done",
            result=str(response.get("result") or "blocked"),
            reason=str(response.get("reason") or ""),
            order_id=_safe_int(order_id),
            request_payload=_json(
                {
                    **request_payload,
                    "confirmation_provided": bool(
                        request_payload.get("confirmation_provided")
                    ),
                }
            ),
            response_payload=_json(response),
            created_at=_naive_utc(now_utc),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        response["run"] = {
            "id": run.id,
            "run_key": run.run_key,
            "mode": run.mode,
            "result": run.result,
            "reason": run.reason,
        }
        return run


def _base_response(
    *,
    now_utc: datetime,
    request_payload: dict[str, Any],
    symbol: str,
    result: str,
    action: str,
    reason: str | None,
    block_reasons: list[str],
    runtime: dict[str, Any] | None,
    market_session: dict[str, Any] | None,
    account_state: dict[str, Any] | None,
    daily_limit: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    preview: dict[str, Any] | None,
    validation_called: bool,
    validation_summary: dict[str, Any] | None,
    manual_submit_called: bool,
    manual_submit_response: dict[str, Any] | None,
    real_order_submitted: bool,
    broker_submit_called: bool,
    order_id: int | None,
    broker_order_id: str | None,
    kis_odno: str | None,
    status_code: int | None,
    error: str | None = None,
) -> dict[str, Any]:
    runtime_snapshot = _runtime_snapshot(runtime or {})
    candidate_payload = sanitize_kis_payload(candidate or {})
    audit_metadata = {
        "broker": PROVIDER,
        "market": MARKET,
        "source_endpoint": ENDPOINT,
        "source_context": SOURCE_CONTEXT,
        "order_source": SOURCE,
        "operator_action_source": SOURCE_CONTEXT,
        "current_operation_mode": (runtime or {}).get("current_operation_mode")
        or "unknown",
        "symbol": symbol,
        "side": BUY,
        "qty": FORCED_QTY,
        "forced_test_entry": True,
        "confirm_live": bool(request_payload.get("confirm_live")),
        "confirmation_dialog_shown": True,
        "user_confirmed_live_order": result == "submitted",
        "estimated_price": _candidate_price(candidate_payload),
        "estimated_notional": (
            _safe_float_or_none((validation_summary or {}).get("estimated_amount"))
            or _candidate_price(candidate_payload)
        ),
        "submit_allowed": result == "submitted",
        "real_order_submitted": real_order_submitted,
        "broker_submit_called": broker_submit_called,
        "manual_submit_called": manual_submit_called,
        "risk_flags": _dedupe(["forced_test_entry"] + block_reasons),
        "gating_notes": _dedupe(
            [
                SOURCE_TYPE,
                "operator_symbol_required",
                "quantity_forced_to_one",
                "max_notional_krw_55000",
                "auto_buy_disabled_after_submit",
                "scheduler_auto_call_forbidden",
            ]
            + block_reasons
        ),
    }
    response = {
        "status": "ok" if result == "submitted" else "blocked",
        "provider": PROVIDER,
        "market": MARKET,
        "mode": MODE,
        "source": SOURCE,
        "source_type": SOURCE_TYPE,
        "source_context": SOURCE_CONTEXT,
        "trigger_source": TRIGGER_SOURCE,
        "source_endpoint": ENDPOINT,
        "operation_test": OPERATION_TEST,
        "result": result,
        "action": action,
        "reason": reason,
        "primary_block_reason": block_reasons[0] if block_reasons else None,
        "block_reasons": block_reasons,
        "failed_checks": block_reasons,
        "forced_test_entry": True,
        "operator": request_payload.get("operator"),
        "operator_symbol": symbol,
        "symbol": symbol,
        "side": BUY,
        "qty": FORCED_QTY,
        "quantity": FORCED_QTY,
        "max_notional_krw": MAX_NOTIONAL_KRW,
        "estimated_notional": audit_metadata["estimated_notional"],
        "current_price": audit_metadata["estimated_price"],
        "confirm_live": bool(request_payload.get("confirm_live")),
        "confirmation_phrase_required": OPERATOR_CONFIRMATION_PHRASE,
        "validation_called": validation_called,
        "validation_summary": validation_summary or {},
        "manual_submit_called": manual_submit_called,
        "manual_submit_response": manual_submit_response or {},
        "real_order_submitted": real_order_submitted,
        "broker_submit_called": broker_submit_called,
        "order_id": order_id,
        "order_log_id": order_id,
        "broker_order_id": broker_order_id,
        "kis_odno": kis_odno,
        "manual_submit_status_code": status_code,
        "candidate": candidate_payload or None,
        "technical_filter_passed": bool(candidate_payload and not block_reasons),
        "preview_summary": _preview_summary(preview or {}),
        "market_session": sanitize_kis_payload(market_session or {}),
        "account_state": _account_state_summary(account_state or {}),
        "daily_limit": daily_limit or {},
        "runtime": runtime_snapshot,
        "auto_buy_disabled_after_submit": False,
        "position_management_only_enabled": False,
        "scheduler_auto_call_enabled": False,
        "scheduler_changed": False,
        "audit_metadata": sanitize_kis_payload(audit_metadata),
        "created_at": now_utc.isoformat(),
        "checked_at": now_utc.isoformat(),
    }
    if error:
        response["error"] = error
    return sanitize_kis_payload(response)


def _runtime_block_reasons(
    *,
    runtime: dict[str, Any],
    settings: Any,
    market_session: dict[str, Any],
    account_state: dict[str, Any],
    daily_limit: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if bool(runtime.get("dry_run", True)):
        reasons.append("dry_run_enabled")
    if bool(runtime.get("kill_switch", False)):
        reasons.append("kill_switch_enabled")
    if not bool(getattr(settings, "kis_enabled", False)):
        reasons.append("kis_disabled")
    if not bool(getattr(settings, "kis_real_order_enabled", False)):
        reasons.append("kis_real_order_disabled")
    if market_session.get("is_market_open") is not True:
        reasons.append("market_closed")
    if market_session.get("is_entry_allowed_now") is not True:
        reasons.append("buy_entry_not_allowed_now")
    reasons.extend(_zero_position_open_order_reasons(account_state, None))
    if int(daily_limit.get("daily_buy_limit_remaining") or 0) <= 0:
        reasons.append("forced_daily_buy_limit_reached")
    return _dedupe(reasons)


def _zero_position_open_order_reasons(
    account_state: dict[str, Any],
    db: Session | None,
) -> list[str]:
    reasons: list[str] = []
    if account_state.get("fetch_success") is False:
        reasons.append("account_state_unavailable")
    if len(_dict_list(account_state.get("positions"))) != 0:
        reasons.append("current_position_not_zero")
    if len(_dict_list(account_state.get("open_orders"))) != 0:
        reasons.append("open_order_not_zero")
    db_open_count = (
        _db_open_order_count(db) if db is not None else int(account_state.get("db_open_order_count") or 0)
    )
    if db_open_count != 0:
        reasons.append("local_open_order_not_zero")
    return _dedupe(reasons)


def _validation_block_reasons(validation_summary: dict[str, Any]) -> list[str]:
    if validation_summary.get("validated_for_submission") is True:
        return []
    reasons = _string_list(validation_summary.get("block_reasons"))
    reason = str(
        validation_summary.get("primary_block_reason")
        or validation_summary.get("reason")
        or ""
    ).strip()
    if reason:
        reasons.append(reason)
    return _dedupe(reasons or ["validation_failed"])


def _source_metadata(
    *,
    request_payload: dict[str, Any],
    candidate: dict[str, Any],
    runtime: dict[str, Any],
    market_session: dict[str, Any],
    account_state: dict[str, Any],
    daily_limit: dict[str, Any],
    validation_summary: dict[str, Any] | None,
    manual_submit_called: bool,
    real_order_submitted: bool,
    broker_submit_called: bool,
) -> dict[str, Any]:
    current_price = _candidate_price(candidate)
    estimated_notional = (
        _safe_float_or_none((validation_summary or {}).get("estimated_amount"))
        or (current_price * FORCED_QTY if current_price is not None else None)
    )
    return sanitize_kis_payload(
        {
            "source": SOURCE,
            "source_type": SOURCE_TYPE,
            "source_context": SOURCE_CONTEXT,
            "operator_action_source": SOURCE_CONTEXT,
            "trigger_source": TRIGGER_SOURCE,
            "mode": MODE,
            "forced_test_entry": True,
            "manual_confirm_required": True,
            "real_order_submit_allowed": True,
            "auto_buy_enabled": False,
            "auto_sell_enabled": True,
            "scheduler_real_order_enabled": False,
            "symbol": request_payload.get("symbol"),
            "company_name": _company_name(candidate),
            "quantity": FORCED_QTY,
            "suggested_quantity": FORCED_QTY,
            "current_price": current_price,
            "notional": estimated_notional,
            "estimated_amount": estimated_notional,
            "max_notional_pct": 0.0,
            "final_score": _score(candidate, "final_score", "final_entry_score", "final_buy_score"),
            "confidence": _score(candidate, "confidence", "gpt_confidence"),
            "quant_score": _score(candidate, "quant_score", "quant_buy_score"),
            "gpt_buy_score": _score(candidate, "gpt_buy_score", "ai_buy_score"),
            "limited_auto_buy_enabled": False,
            "limited_auto_buy_real_order_submitted": real_order_submitted,
            "limited_auto_buy_broker_submit_called": broker_submit_called,
            "limited_auto_buy_manual_submit_called": manual_submit_called,
            "real_order_submitted": real_order_submitted,
            "broker_submit_called": broker_submit_called,
            "manual_submit_called": manual_submit_called,
            "risk_flags": _dedupe(
                ["forced_test_entry", SOURCE_TYPE]
                + _string_list(candidate.get("risk_flags"))
            ),
            "gating_notes": _dedupe(
                [
                    "operator_forced_one_share_buy",
                    "technical_filter_passed",
                    "quantity_forced_to_one",
                    "max_notional_krw_55000",
                    "general_auto_buy_forbidden",
                    "scheduler_auto_call_forbidden",
                ]
                + _string_list(candidate.get("gating_notes"))
            ),
            "runtime_safety_snapshot": _runtime_snapshot(runtime),
            "market_session_snapshot": sanitize_kis_payload(market_session),
            "daily_limit": daily_limit,
            "trigger_flags": {
                "forced_test_entry": True,
                "operation_test": OPERATION_TEST,
                "confirm_live": bool(request_payload.get("confirm_live")),
                "position_count": len(_dict_list(account_state.get("positions"))),
                "open_order_count": len(_dict_list(account_state.get("open_orders"))),
            },
            "validation_summary": validation_summary or {},
        }
    )


def _find_candidate(preview: dict[str, Any], *, symbol: str) -> dict[str, Any] | None:
    for item in _preview_candidates(preview):
        if _symbol(item) == symbol:
            return sanitize_kis_payload(item)
    return None


def _preview_candidates(preview: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in (
        "final_ranked_candidates",
        "quant_candidates",
        "top_quant_candidates",
        "researched_candidates",
        "watchlist",
        "items",
    ):
        for item in _dict_list(preview.get(key)):
            symbol = _symbol(item)
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            candidates.append(item)
    return candidates


def _technical_filter_reasons(candidate: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    indicator_status = str(candidate.get("indicator_status") or "").strip().lower()
    indicator_payload = _indicator_payload(candidate)
    if indicator_status != "ok":
        reasons.append("technical_indicator_status_not_ok")
    if not indicator_payload_is_quant_ready(indicator_payload):
        reasons.append("technical_indicator_payload_not_ready")
    if _candidate_price(candidate) is None:
        reasons.append("current_price_unavailable")
    return _dedupe(reasons)


def _indicator_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    for key in ("indicator_payload", "technical_snapshot", "indicators"):
        value = candidate.get(key)
        if isinstance(value, dict):
            return dict(value)
    return {}


def _candidate_price(candidate: dict[str, Any] | None) -> float | None:
    if not candidate:
        return None
    indicator_payload = _indicator_payload(candidate)
    return _first_float(
        candidate.get("current_price"),
        candidate.get("price"),
        indicator_payload.get("price"),
        indicator_payload.get("close"),
    )


def _daily_buy_count(
    db: Session,
    *,
    now_utc: datetime,
) -> int:
    start_utc, end_utc = _kr_day_bounds_utc(now_utc)
    return (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.side == BUY)
        .filter(OrderLog.created_at >= start_utc)
        .filter(OrderLog.created_at < end_utc)
        .filter(
            or_(
                OrderLog.internal_status.in_(sorted(LIVE_BUY_STATUSES)),
                OrderLog.kis_odno.isnot(None),
                OrderLog.broker_order_id.isnot(None),
            )
        )
        .count()
    )


def _db_open_order_count(db: Session | None) -> int:
    if db is None:
        return 0
    return (
        db.query(OrderLog)
        .filter(OrderLog.broker == PROVIDER)
        .filter(OrderLog.internal_status.in_(sorted(OPEN_ORDER_STATUSES)))
        .count()
    )


def _lifecycle_for_order(db: Session, order_id: int) -> dict[str, Any] | None:
    from app.db.models import PositionLifecycle

    row = (
        db.query(PositionLifecycle)
        .filter(PositionLifecycle.entry_order_id == int(order_id))
        .first()
    )
    if row is None:
        return None
    return {
        "created": True,
        "reason": "filled_buy_lifecycle_created",
        "id": row.id,
        "symbol": row.symbol,
        "entry_order_id": row.entry_order_id,
        "entry_price": row.entry_price,
        "cost_basis": row.cost_basis,
        "quantity": row.quantity,
        "status": row.status,
    }


def _post_submit_settings_snapshot(settings: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "dry_run",
        "scheduler_enabled",
        "kis_scheduler_enabled",
        "kis_scheduler_live_enabled",
        "kis_scheduler_allow_real_orders",
        "kis_scheduler_buy_enabled",
        "kis_scheduler_allow_limited_auto_buy",
        "kis_live_auto_buy_enabled",
        "kis_limited_auto_buy_enabled",
        "strategy_live_auto_buy_enabled",
        "strategy_live_auto_buy_scheduler_enabled",
        "auto_buy_live_phase1_enabled",
        "auto_buy_live_phase1_allow_real_orders",
        "kis_live_auto_sell_enabled",
        "kis_limited_auto_sell_enabled",
        "kis_limited_auto_stop_loss_enabled",
        "kis_limited_auto_sell_stop_loss_enabled",
        "position_management_scheduler_enabled",
        "kis_position_lifecycle_scheduler_enabled",
        "position_management_scheduler_allow_live_orders",
    )
    return {key: settings.get(key) for key in keys if key in settings}


def _runtime_snapshot(settings: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "dry_run",
        "kill_switch",
        "current_operation_mode",
        "operation_mode_requested",
        "scheduler_enabled",
        "kis_scheduler_enabled",
        "kis_scheduler_live_enabled",
        "kis_scheduler_allow_real_orders",
        "kis_scheduler_configured_allow_real_orders",
        "kis_scheduler_buy_enabled",
        "kis_scheduler_allow_limited_auto_buy",
        "kis_live_auto_buy_enabled",
        "kis_limited_auto_buy_enabled",
        "strategy_live_auto_buy_enabled",
        "strategy_live_auto_buy_scheduler_enabled",
        "auto_buy_live_phase1_enabled",
        "auto_buy_live_phase1_allow_real_orders",
        "kis_live_auto_sell_enabled",
        "kis_limited_auto_sell_enabled",
        "position_management_scheduler_enabled",
        "kis_position_lifecycle_scheduler_enabled",
        "position_management_scheduler_allow_live_orders",
    )
    return {key: settings.get(key) for key in keys if key in settings}


def _account_state_summary(account_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "fetch_success": account_state.get("fetch_success") is not False,
        "position_count": len(_dict_list(account_state.get("positions"))),
        "open_order_count": len(_dict_list(account_state.get("open_orders"))),
        "db_open_order_count": int(account_state.get("db_open_order_count") or 0),
        "warnings": _string_list(account_state.get("warnings")),
    }


def _preview_summary(preview: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_count": len(_preview_candidates(preview)),
        "watchlist_source": preview.get("watchlist_source") or preview.get("watchlist_file"),
        "gpt_analysis_included": preview.get("gpt_analysis_included"),
        "trigger_source": preview.get("trigger_source"),
    }


def _valid_kr_symbol(symbol: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", str(symbol or "").strip()))


def _symbol(item: dict[str, Any]) -> str:
    return str(item.get("symbol") or item.get("code") or "").strip().upper()


def _company_name(item: dict[str, Any]) -> str | None:
    for key in ("company_name", "name", "company", "asset_name"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return None


def _position_qty(item: dict[str, Any]) -> float:
    return _safe_float(
        item.get("qty")
        or item.get("quantity")
        or item.get("hldg_qty")
        or item.get("holding_qty"),
        0.0,
    )


def _open_order_remaining(item: dict[str, Any]) -> float | None:
    return _first_float(
        item.get("remaining_qty"),
        item.get("unfilled_qty"),
        item.get("rmn_qty"),
        item.get("qty"),
    )


def _score(item: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _safe_float_or_none(item.get(key))
        if value is not None:
            return value
    return None


def _first_float(*values: Any) -> float | None:
    for value in values:
        parsed = _safe_float_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _safe_float(value: Any, default: float) -> float:
    parsed = _safe_float_or_none(value)
    return default if parsed is None else parsed


def _safe_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _kr_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    local = _aware_utc(now_utc).astimezone(KR_TZ)
    start_local = datetime.combine(local.date(), time.min, tzinfo=KR_TZ)
    end_local = start_local + timedelta(days=1)
    return _naive_utc(start_local), _naive_utc(end_local)


def _aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    return _aware_utc(value).replace(tzinfo=None)


def _json(value: Any) -> str:
    return json.dumps(sanitize_kis_payload(value), ensure_ascii=False, default=str)


def _safe_error(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    return text[:300]
