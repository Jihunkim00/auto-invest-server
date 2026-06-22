from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, time, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.core.enums import InternalOrderStatus
from app.db.models import AgentChatOrderAction, OrderLog
from app.schemas.agent_chat_live_order import (
    AgentChatLiveOrderActionPayload,
    AgentChatLiveOrderAnswer,
    AgentChatLiveOrderCancelRequest,
    AgentChatLiveOrderConfirmRequest,
    AgentChatLiveOrderResponse,
)
from app.schemas.agent_chat_orchestrator import AgentChatIntent
from app.schemas.agent_chat_tool import AgentChatResultCard
from app.services.agent_chat_service import AgentChatService
from app.services.kis_manual_order_service import (
    KIS_MANUAL_CONFIRMATION_PHRASE,
    KisManualOrderService,
    KisManualOrderSubmitRequest,
)
from app.services.kis_order_validation_service import (
    KisOrderValidationRequest,
    KisOrderValidationService,
    record_kis_order_validation,
)
from app.services.kis_order_sync_service import (
    KisOrderSyncError,
    KisOrderSyncService,
    serialize_kis_order,
)
from app.services.kis_payload_sanitizer import sanitize_kis_text
from app.services.runtime_setting_service import RuntimeSettingService


KR_TZ = ZoneInfo("Asia/Seoul")
ACTION_TYPE = "chat_confirmed_live_order"
STATUS_PENDING = "pending_confirmation"
STATUS_CONFIRMING = "confirming"
STATUS_CONFIRMED = "confirmed"
STATUS_SUBMITTING = "submitting"
STATUS_SUBMITTED = "submitted"
STATUS_SYNC_REQUIRED = "sync_required"
STATUS_FILLED = "filled"
STATUS_PARTIALLY_FILLED = "partially_filled"
STATUS_REJECTED = "rejected"
STATUS_BLOCKED = "blocked"
STATUS_EXPIRED = "expired"
STATUS_CANCELLED = "cancelled"
STATUS_FAILED = "failed"
OPEN_ORDER_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
}
SUBMITTED_ACTION_STATUSES = {
    STATUS_SUBMITTED,
    STATUS_SYNC_REQUIRED,
    STATUS_FILLED,
    STATUS_PARTIALLY_FILLED,
}
TERMINAL_ACTION_STATUSES = {
    STATUS_SUBMITTED,
    STATUS_SYNC_REQUIRED,
    STATUS_FILLED,
    STATUS_PARTIALLY_FILLED,
    STATUS_REJECTED,
    STATUS_BLOCKED,
    STATUS_FAILED,
    STATUS_EXPIRED,
    STATUS_CANCELLED,
    STATUS_CONFIRMED,
    STATUS_CONFIRMING,
    STATUS_SUBMITTING,
}


class AgentChatLiveOrderNotFound(Exception):
    pass


class AgentChatLiveOrderService:
    def __init__(
        self,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        chat_service: AgentChatService | None = None,
        kis_client_factory: Callable[[Session], KisClient] | None = None,
        validation_service_factory: Callable[[KisClient], KisOrderValidationService] | None = None,
        manual_order_service_factory: Callable[[KisClient], KisManualOrderService] | None = None,
        order_sync_service_factory: Callable[[KisClient], KisOrderSyncService] | None = None,
    ) -> None:
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.chat_service = chat_service or AgentChatService()
        self.kis_client_factory = kis_client_factory or self._default_kis_client
        self.validation_service_factory = validation_service_factory or (
            lambda client: KisOrderValidationService(client)
        )
        self.manual_order_service_factory = manual_order_service_factory or (
            lambda client: KisManualOrderService(client)
        )
        self.order_sync_service_factory = order_sync_service_factory or (
            lambda client: KisOrderSyncService(client)
        )

    def prepare(
        self,
        db: Session,
        *,
        intent: AgentChatIntent,
        conversation_key: str,
        user_message_id: int | None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc_now(now)
        safety = _base_safety(real_order_submitted=False)
        settings = self.runtime_settings.get_settings(db)
        side = _normalize_side(intent.side)
        market = str(intent.market or "").strip().upper() or "KR"
        provider = str(intent.provider or "").strip().lower() or "kis"
        symbol = _normalize_symbol(intent.symbol)
        order_type = "market"
        safety["safety_controls"] = self._safety_controls(
            db,
            settings=settings,
            side=side,
            now_utc=now_utc,
        )

        if not self._prepare_flags_enabled(settings, provider=provider, side=side):
            return {
                "created": False,
                "reason": "agent_chat_live_order_disabled",
                "data": {
                    "direct_order_blocked": True,
                    "live_order_feature_disabled": True,
                    "block_reason": "agent_chat_live_order_disabled",
                    "safety_controls": safety["safety_controls"],
                },
                "safety": safety,
                "result_cards": [],
            }

        if market != "KR" or provider != "kis":
            return self._prepare_block("unsupported_provider_or_market", safety=safety)
        if not symbol or not re.fullmatch(r"\d{6}", symbol):
            return self._prepare_block("invalid_or_missing_kr_symbol", safety=safety)
        if side not in {"buy", "sell"}:
            return self._prepare_block("missing_buy_or_sell_side", safety=safety)
        if order_type == "market" and not bool(settings["agent_chat_live_order_allow_market_order"]):
            return self._prepare_block("market_order_disabled", safety=safety)

        estimated_price = None
        estimated_notional = None
        price_payload: dict[str, Any] = {}
        if bool(settings["agent_chat_live_order_requires_recent_price"]):
            try:
                price_payload = self.kis_client_factory(db).get_domestic_stock_price(symbol)
                estimated_price = _float_or_none(
                    price_payload.get("current_price") or price_payload.get("price")
                )
                safety["broker_api_called"] = True
            except Exception as exc:
                return self._prepare_block(
                    "recent_price_unavailable",
                    safety=safety,
                    detail=_safe_error(exc),
                )
            if estimated_price is None or estimated_price <= 0:
                return self._prepare_block("recent_price_unavailable", safety=safety)

        quantity = _whole_quantity(intent.quantity)
        notional = _float_or_none(intent.notional)
        if quantity is None and notional is not None and estimated_price:
            quantity = int(notional // estimated_price)
        if quantity is None or quantity < 1:
            return self._prepare_block("missing_or_invalid_quantity", safety=safety)
        if estimated_price is not None:
            estimated_notional = float(quantity) * float(estimated_price)

        ttl_seconds = max(30, min(3600, int(settings["agent_chat_live_order_confirm_ttl_seconds"] or 120)))
        expires_at = now_utc + timedelta(seconds=ttl_seconds)
        symbol_name = (
            str(price_payload.get("name") or "").strip()
            or str(intent.symbol_name or "").strip()
            or symbol
        )
        scope = {
            "action_type": ACTION_TYPE,
            "conversation_key": conversation_key,
            "provider": "kis",
            "market": "KR",
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "notional_amount": notional,
            "currency": "KRW",
            "created_at": _iso_utc(now_utc),
        }
        scope_hash = _scope_hash(scope)
        confirmation_phrase = f"{symbol} {side} {quantity} confirm"
        request_payload = {
            **scope,
            "symbol_name": symbol_name,
            "estimated_price": estimated_price,
            "estimated_notional": estimated_notional,
            "safety": {
                "prepare_only": True,
                "validation_called": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "real_order_submitted": False,
            },
        }
        row = AgentChatOrderAction(
            conversation_key=conversation_key,
            user_message_id=user_message_id,
            assistant_message_id=None,
            action_type=ACTION_TYPE,
            provider="kis",
            market="KR",
            symbol=symbol,
            symbol_name=symbol_name,
            side=side,
            order_type=order_type,
            quantity=float(quantity),
            notional_amount=notional,
            currency="KRW",
            estimated_price=estimated_price,
            estimated_notional=estimated_notional,
            status=STATUS_PENDING,
            scope_hash=scope_hash,
            confirmation_phrase=confirmation_phrase,
            expires_at=_naive_utc(expires_at),
            request_payload_json=_json(request_payload),
            safety_payload_json=_json(safety),
            created_at=_naive_utc(now_utc),
            updated_at=_naive_utc(now_utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        action = self.serialize_action(row)
        result_card = self.confirmation_card(action)
        safety["read_only"] = False
        safety["safe_execution_only"] = True
        return {
            "created": True,
            "action": action,
            "data": {
                "direct_order_blocked": False,
                "live_order_action": action,
                "safety": safety,
                "safety_controls": safety["safety_controls"],
            },
            "safety": safety,
            "result_cards": [result_card],
        }

    def update_assistant_message_id(
        self,
        db: Session,
        *,
        action_id: int,
        assistant_message_id: int | None,
    ) -> None:
        if assistant_message_id is None:
            return
        row = db.get(AgentChatOrderAction, action_id)
        if row is None:
            return
        row.assistant_message_id = assistant_message_id
        row.updated_at = _naive_utc(_utc_now())
        db.commit()

    def get(
        self,
        db: Session,
        *,
        action_id: int,
    ) -> dict[str, Any]:
        row = self._get_action(db, action_id)
        self._refresh_action_from_linked_order(db, row)
        return self.serialize_action(row, db=db)

    def recent(
        self,
        db: Session,
        *,
        limit: int = 20,
        status: str | None = None,
        symbol: str | None = None,
        conversation_key: str | None = None,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit or 20), 100))
        query = db.query(AgentChatOrderAction)
        if status:
            query = query.filter(AgentChatOrderAction.status == status.strip())
        if symbol:
            query = query.filter(AgentChatOrderAction.symbol == _normalize_symbol(symbol))
        if conversation_key:
            query = query.filter(AgentChatOrderAction.conversation_key == conversation_key.strip())
        rows = (
            query.order_by(AgentChatOrderAction.created_at.desc(), AgentChatOrderAction.id.desc())
            .limit(safe_limit)
            .all()
        )
        for row in rows:
            self._refresh_action_from_linked_order(db, row)
        return {
            "status": "ok",
            "count": len(rows),
            "actions": [self.serialize_action(row, db=db) for row in rows],
        }

    def sync(
        self,
        db: Session,
        *,
        action_id: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        row = self._get_action(db, action_id)
        now_utc = _utc_now(now)
        safety = _sync_safety()
        order = self._linked_order(db, row)
        if order is None:
            row.status = STATUS_SYNC_REQUIRED
            row.last_sync_at = _naive_utc(now_utc)
            row.last_sync_payload_json = _json(
                {
                    "sync_status": "missing_linked_order",
                    "related_order_id": row.related_order_id,
                    "broker_order_id": row.broker_order_id,
                }
            )
            row.safety_payload_json = _json({**safety, "original_order_submitted": False})
            row.last_state_change_at = _naive_utc(now_utc)
            row.updated_at = _naive_utc(now_utc)
            db.commit()
            db.refresh(row)
            response = self._response(
                row,
                status=STATUS_SYNC_REQUIRED,
                answer_type="live_order_status_sync_failed",
                text="Live order status sync needs manual review because no linked KIS order was found. No order was submitted.",
                safety={**safety, "original_order_submitted": False},
                order=None,
                diagnostics={"sync_reason": "linked_order_missing"},
                db=db,
            )
            self._append_result_message(db, row, response)
            return response.model_dump(mode="json")

        client = self.kis_client_factory(db)
        try:
            synced = self.order_sync_service_factory(client).sync_order(db, int(order.id))
        except KisOrderSyncError as exc:
            row.status = STATUS_SYNC_REQUIRED
            row.last_sync_at = _naive_utc(now_utc)
            row.last_sync_payload_json = _json({"sync_error": _safe_error(exc)})
            row.safety_payload_json = _json({**safety, "original_order_submitted": True})
            row.last_state_change_at = _naive_utc(now_utc)
            row.updated_at = _naive_utc(now_utc)
            db.commit()
            db.refresh(row)
            response = self._response(
                row,
                status=STATUS_SYNC_REQUIRED,
                answer_type="live_order_status_sync_failed",
                text="Live order status sync failed safely. No order was submitted.",
                safety={**safety, "original_order_submitted": True},
                order=self._order_payload(row, db=db),
                diagnostics={"sync_error": _safe_error(exc)},
                db=db,
            )
            self._append_result_message(db, row, response)
            return response.model_dump(mode="json")

        self._apply_order_status_to_action(row, synced, now_utc=now_utc)
        row.last_sync_payload_json = _json(serialize_kis_order(synced, include_sync_payload=True))
        row.safety_payload_json = _json({**safety, "original_order_submitted": True})
        row.updated_at = _naive_utc(now_utc)
        db.commit()
        db.refresh(row)
        response = self._response(
            row,
            status="synced",
            answer_type="live_order_status_synced",
            text=f"Live order status was synced. Current status is {row.status}.",
            safety={**safety, "original_order_submitted": True},
            order=self._order_payload(row, db=db),
            diagnostics={"sync_submitted_new_order": False},
            db=db,
        )
        self._append_result_message(db, row, response)
        return response.model_dump(mode="json")

    def confirm(
        self,
        db: Session,
        *,
        action_id: int,
        request: AgentChatLiveOrderConfirmRequest,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        row = self._get_action(db, action_id)
        now_utc = _utc_now(now)
        safety = _base_safety(real_order_submitted=False)
        settings = self.runtime_settings.get_settings(db)
        safety["safety_controls"] = self._safety_controls(
            db,
            settings=settings,
            side=row.side,
            now_utc=now_utc,
        )

        if row.related_order_id is not None or row.broker_order_id:
            self._refresh_action_from_linked_order(db, row)
            if self._linked_order(db, row) is None:
                row.status = STATUS_SYNC_REQUIRED
                row.last_state_change_at = _naive_utc(now_utc)
                row.updated_at = _naive_utc(now_utc)
                db.commit()
                db.refresh(row)
            response = self._response(
                row,
                status=row.status,
                answer_type=self._answer_type_for_status(row.status),
                text="This live order action already has a linked order. No duplicate order was sent.",
                safety={**safety, "idempotent_replay": True},
                order=self._order_payload(row, db=db),
                db=db,
            )
            return response.model_dump(mode="json")

        if row.status == STATUS_SUBMITTED:
            response = self._response(
                row,
                status=STATUS_SUBMITTED,
                answer_type="live_order_submitted",
                text="This live order action was already submitted. No duplicate order was sent.",
                safety={**safety, "idempotent_replay": True},
                order=self._order_payload(row, db=db),
                db=db,
            )
            return response.model_dump(mode="json")

        if row.status != STATUS_PENDING:
            response = self._response(
                row,
                status=row.status,
                answer_type=self._answer_type_for_status(row.status),
                text=f"This live order action is {row.status}; no order was submitted.",
                safety=safety,
                order=self._order_payload(row, db=db) if row.related_order_id else None,
                db=db,
            )
            return response.model_dump(mode="json")

        if _is_expired(row.expires_at, now_utc=now_utc):
            return self._block(
                db,
                row,
                status=STATUS_EXPIRED,
                answer_type="live_order_expired",
                reason="confirmation_expired",
                text="Live order confirmation expired. No order was submitted.",
                safety=safety,
                now_utc=now_utc,
            )

        if not self._confirmation_matches(row, request):
            return self._block(
                db,
                row,
                status=STATUS_BLOCKED,
                answer_type="live_order_blocked",
                reason="confirmation_mismatch",
                text="Live order confirmation did not match. No order was submitted.",
                safety=safety,
                now_utc=now_utc,
            )

        row.status = STATUS_CONFIRMING
        row.confirmed_at = _naive_utc(now_utc)
        row.last_state_change_at = _naive_utc(now_utc)
        row.updated_at = _naive_utc(now_utc)
        db.commit()
        db.refresh(row)

        settings_block = self._confirm_settings_block(row, settings)
        if settings_block is not None:
            return self._block(
                db,
                row,
                status=STATUS_BLOCKED,
                answer_type="live_order_blocked",
                reason=settings_block,
                text=f"Live order blocked by runtime safety gate: {settings_block}.",
                safety=safety,
                now_utc=now_utc,
            )

        if self._daily_action_count(db, now_utc=now_utc) >= max(
            0, int(settings["agent_chat_live_order_max_orders_per_day"] or 0)
        ):
            return self._block(
                db,
                row,
                status=STATUS_BLOCKED,
                answer_type="live_order_blocked",
                reason="agent_chat_daily_order_limit_reached",
                text="Live order blocked by Agent Chat daily order limit.",
                safety=safety,
                now_utc=now_utc,
            )

        duplicate = self._open_duplicate_order(db, row)
        if duplicate is not None:
            return self._block(
                db,
                row,
                status=STATUS_BLOCKED,
                answer_type="live_order_blocked",
                reason="duplicate_open_order_exists",
                text="Live order blocked because an open KIS order already exists for this symbol and side.",
                safety=safety,
                now_utc=now_utc,
                risk_payload={"duplicate_order_id": duplicate.id},
            )

        client = self.kis_client_factory(db)
        validation_result = None
        try:
            validation_request = KisOrderValidationRequest(
                market="KR",
                symbol=row.symbol,
                side=row.side,
                qty=int(row.quantity or 0),
                order_type=row.order_type,
                dry_run=True,
                reason="Agent Chat confirmed live order validation.",
                source_metadata=self._source_metadata(row),
            )
            validation_result = self.validation_service_factory(client).validate(
                validation_request,
                now=now_utc,
            )
            record_kis_order_validation(
                db,
                request=validation_request,
                result=validation_result,
            )
            safety["validation_called"] = True
            safety["safety_controls"] = self._safety_controls(
                db,
                settings=settings,
                side=row.side,
                validation=validation_result.to_dict(),
                now_utc=now_utc,
            )
            row.validation_payload_json = _json(validation_result.to_dict())
            db.commit()
        except Exception as exc:
            safety["validation_called"] = True
            return self._block(
                db,
                row,
                status=STATUS_BLOCKED,
                answer_type="live_order_blocked",
                reason="validation_failed",
                text=f"Live order validation failed. No order was submitted. Reason: {_safe_error(exc)}",
                safety=safety,
                now_utc=now_utc,
            )

        if validation_result.validated_for_submission is not True:
            return self._block(
                db,
                row,
                status=STATUS_BLOCKED,
                answer_type="live_order_blocked",
                reason="validation_blocked",
                text="Live order blocked by validation. No order was submitted.",
                safety={**safety, "risk_approved": False},
                now_utc=now_utc,
                risk_payload=validation_result.to_dict(),
            )

        risk_block = self._risk_block(row, validation_result.to_dict(), settings)
        if risk_block is not None:
            return self._block(
                db,
                row,
                status=STATUS_BLOCKED,
                answer_type="live_order_blocked",
                reason=risk_block,
                text=f"Live order blocked by Agent Chat risk gate: {risk_block}.",
                safety={**safety, "risk_approved": False},
                now_utc=now_utc,
                risk_payload=validation_result.to_dict(),
            )

        manual_request = KisManualOrderSubmitRequest(
            market="KR",
            symbol=row.symbol,
            side=row.side,
            qty=int(row.quantity or 0),
            order_type=row.order_type,
            dry_run=False,
            confirm_live=True,
            confirmation=self._manual_confirmation_phrase(client),
            reason="Agent Chat user-confirmed live order.",
            source_context="agent_chat_confirmed_live_order",
            source_metadata=self._source_metadata(row),
        )
        row.status = STATUS_SUBMITTING
        row.last_state_change_at = _naive_utc(now_utc)
        row.updated_at = _naive_utc(now_utc)
        row.safety_payload_json = _json({**safety, "validation_called": True, "risk_approved": True})
        db.commit()
        db.refresh(row)
        try:
            status_code, body = self.manual_order_service_factory(client).submit_manual(
                db,
                manual_request,
                now=now_utc,
            )
        except Exception as exc:
            return self._block(
                db,
                row,
                status=STATUS_FAILED,
                answer_type="live_order_blocked",
                reason="manual_submit_failed",
                text=f"KIS manual submit failed. No confirmed broker order is available. Reason: {_safe_error(exc)}",
                safety={
                    **safety,
                    "validation_called": True,
                    "risk_approved": True,
                    "manual_submit_called": True,
                },
                now_utc=now_utc,
            )

        real_submitted = body.get("real_order_submitted") is True
        safety.update(
            {
                "validation_called": True,
                "risk_approved": True,
                "real_order_submitted": real_submitted,
                "broker_submit_called": body.get("broker_submit_called") is True,
                "manual_submit_called": body.get("manual_submit_called") is True,
            }
        )
        row.related_order_id = _int_or_none(body.get("order_id") or body.get("order_log_id"))
        row.broker_order_id = _text_or_none(body.get("broker_order_id") or body.get("kis_odno"))
        row.response_payload_json = _json(body)
        row.safety_payload_json = _json(safety)
        row.updated_at = _naive_utc(now_utc)
        if real_submitted and status_code < 300:
            row.status = STATUS_SUBMITTED
            row.submitted_at = _naive_utc(now_utc)
            row.last_state_change_at = _naive_utc(now_utc)
            db.commit()
            db.refresh(row)
            response = self._response(
                row,
                status=STATUS_SUBMITTED,
                answer_type="live_order_submitted",
                text=(
                    f"Confirmed. KIS live {row.side} order for {row.symbol} "
                    f"{int(row.quantity or 0)} share(s) was submitted."
                ),
                safety=safety,
                order=self._order_payload(row, body=body),
                db=db,
            )
            self._append_result_message(db, row, response)
            return response.model_dump(mode="json")

        row.status = STATUS_BLOCKED if status_code < 500 else STATUS_FAILED
        row.last_state_change_at = _naive_utc(now_utc)
        db.commit()
        db.refresh(row)
        response = self._response(
            row,
            status=row.status,
            answer_type="live_order_blocked",
            text="KIS manual submit safety gate blocked the order. No broker order was submitted.",
            safety=safety,
            order=self._order_payload(row, body=body) if row.related_order_id else None,
            db=db,
        )
        self._append_result_message(db, row, response)
        return response.model_dump(mode="json")

    def cancel(
        self,
        db: Session,
        *,
        action_id: int,
        request: AgentChatLiveOrderCancelRequest | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        row = self._get_action(db, action_id)
        now_utc = _utc_now(now)
        safety = _base_safety(real_order_submitted=False)
        settings = self.runtime_settings.get_settings(db)
        safety["safety_controls"] = self._safety_controls(
            db,
            settings=settings,
            side=row.side,
            now_utc=now_utc,
        )
        if row.status != STATUS_PENDING:
            response = self._response(
                row,
                status=row.status,
                answer_type=self._answer_type_for_status(row.status),
                text=f"This live order action is {row.status}; no cancellation changed it.",
                safety=safety,
                order=self._order_payload(row, db=db) if row.related_order_id else None,
                db=db,
            )
            return response.model_dump(mode="json")

        row.status = STATUS_CANCELLED
        row.response_payload_json = _json(
            {"cancelled": True, "reason": (request.reason if request else None)}
        )
        row.safety_payload_json = _json(safety)
        row.last_state_change_at = _naive_utc(now_utc)
        row.updated_at = _naive_utc(now_utc)
        db.commit()
        db.refresh(row)
        response = self._response(
            row,
            status=STATUS_CANCELLED,
            answer_type="live_order_cancelled",
            text="Live order confirmation was cancelled. No validation or order submission ran.",
            safety=safety,
            order=None,
            db=db,
        )
        self._append_result_message(db, row, response)
        return response.model_dump(mode="json")

    def serialize_action(self, row: AgentChatOrderAction, *, db: Session | None = None) -> dict[str, Any]:
        order = self._linked_order(db, row) if db is not None else None
        safety = _parse_json_object(row.safety_payload_json)
        raw_controls = safety.get("safety_controls")
        safety_controls = raw_controls if isinstance(raw_controls, dict) else {}
        return AgentChatLiveOrderActionPayload(
            action_id=int(row.id),
            conversation_key=row.conversation_key,
            status=str(row.status),
            action_type=str(row.action_type or ACTION_TYPE),
            provider=str(row.provider or "kis"),
            market=str(row.market or "KR"),
            symbol=str(row.symbol or ""),
            symbol_name=_text_or_none(row.symbol_name),
            side=str(row.side or ""),
            order_type=str(row.order_type or "market"),
            quantity=row.quantity,
            notional_amount=row.notional_amount,
            currency=str(row.currency or "KRW"),
            estimated_price=row.estimated_price,
            estimated_notional=row.estimated_notional,
            expires_at=_iso_utc(row.expires_at),
            confirmation_phrase=None,
            confirmation_token=row.scope_hash,
            related_order_id=row.related_order_id,
            broker_order_id=row.broker_order_id,
            broker_status=_text_or_none(
                (order.broker_status if order is not None else None)
                or (order.broker_order_status if order is not None else None)
            ),
            internal_status=_text_or_none(order.internal_status if order is not None else None),
            last_sync_at=_iso_utc(
                row.last_sync_at
                or (order.last_synced_at if order is not None else None)
            ),
            last_sync_payload=_parse_json_object(row.last_sync_payload_json),
            audit=self._audit_payload(row),
            safety=safety,
            safety_controls=safety_controls,
        ).model_dump(mode="json")

    def confirmation_card(self, action: dict[str, Any]) -> AgentChatResultCard:
        symbol = str(action.get("symbol") or "")
        side = str(action.get("side") or "").upper()
        qty = action.get("quantity")
        return AgentChatResultCard(
            card_type="live_order_confirmation",
            title="Live Order Confirmation Required",
            subtitle="KIS / KR",
            primary_value=_money(action.get("estimated_notional"), "KRW"),
            badges=[
                "LIVE ORDER",
                "CONFIRM REQUIRED",
                "KIS",
                "VALIDATION REQUIRED",
                "RISK GATED",
                "NO SETTINGS CHANGE",
                "NO SCHEDULER CHANGE",
            ],
            rows=[
                {"label": "Symbol", "value": symbol},
                {"label": "Side", "value": side},
                {"label": "Quantity", "value": qty},
                {"label": "Estimated price", "value": _money(action.get("estimated_price"), "KRW")},
                {"label": "Expires at", "value": action.get("expires_at")},
            ],
            data=action,
        )

    def result_card(self, row: AgentChatOrderAction, response: AgentChatLiveOrderResponse) -> AgentChatResultCard:
        status = response.status.upper()
        badges = ["LIVE ORDER", "KIS", status, "NO SETTINGS CHANGE", "NO SCHEDULER CHANGE"]
        if response.status == STATUS_SUBMITTED:
            badges.append("SUBMITTED")
        if response.status in {STATUS_BLOCKED, STATUS_FAILED, STATUS_EXPIRED, STATUS_CANCELLED}:
            badges.append("BLOCKED" if response.status != STATUS_CANCELLED else "CANCELLED")
        return AgentChatResultCard(
            card_type="live_order_result",
            title="Live Order Result",
            subtitle=f"{row.symbol} / {row.side.upper()}",
            primary_value=status,
            badges=badges,
            rows=[
                {"label": "Action ID", "value": row.id},
                {"label": "Order ID", "value": row.related_order_id or "-"},
                {"label": "Broker order", "value": row.broker_order_id or "-"},
                {"label": "Real order submitted", "value": response.safety.get("real_order_submitted") is True},
            ],
            data=response.model_dump(mode="json"),
        )

    def _linked_order(self, db: Session | None, row: AgentChatOrderAction) -> OrderLog | None:
        if db is None:
            return None
        if row.related_order_id is not None:
            order = db.get(OrderLog, int(row.related_order_id))
            if order is not None:
                return order
        broker_order_id = _text_or_none(row.broker_order_id)
        if not broker_order_id:
            return None
        return (
            db.query(OrderLog)
            .filter(OrderLog.broker == "kis")
            .filter(
                (OrderLog.broker_order_id == broker_order_id)
                | (OrderLog.kis_odno == broker_order_id)
            )
            .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
            .first()
        )

    def _refresh_action_from_linked_order(
        self,
        db: Session,
        row: AgentChatOrderAction,
        *,
        now_utc: datetime | None = None,
    ) -> None:
        order = self._linked_order(db, row)
        if order is None:
            return
        changed = False
        if row.related_order_id != order.id:
            row.related_order_id = order.id
            changed = True
        broker_order_id = order.broker_order_id or order.kis_odno
        if broker_order_id and row.broker_order_id != broker_order_id:
            row.broker_order_id = broker_order_id
            changed = True
        next_status = self._action_status_from_internal_status(order.internal_status)
        if next_status and row.status != next_status:
            row.status = next_status
            row.last_state_change_at = _naive_utc(now_utc or _utc_now())
            changed = True
        if order.last_synced_at and row.last_sync_at != order.last_synced_at:
            row.last_sync_at = order.last_synced_at
            changed = True
        if changed:
            row.updated_at = _naive_utc(now_utc or _utc_now())
            db.commit()
            db.refresh(row)

    def _apply_order_status_to_action(
        self,
        row: AgentChatOrderAction,
        order: OrderLog,
        *,
        now_utc: datetime,
    ) -> None:
        row.related_order_id = order.id
        row.broker_order_id = order.broker_order_id or order.kis_odno or row.broker_order_id
        row.status = self._action_status_from_internal_status(order.internal_status)
        row.last_state_change_at = _naive_utc(now_utc)
        row.last_sync_at = order.last_synced_at or _naive_utc(now_utc)

    def _action_status_from_internal_status(self, internal_status: str | None) -> str:
        status = str(internal_status or "").strip().upper()
        if status == InternalOrderStatus.FILLED.value:
            return STATUS_FILLED
        if status == InternalOrderStatus.PARTIALLY_FILLED.value:
            return STATUS_PARTIALLY_FILLED
        if status in {
            InternalOrderStatus.REJECTED.value,
            InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value,
            InternalOrderStatus.FAILED.value,
        }:
            return STATUS_REJECTED
        if status in {InternalOrderStatus.CANCELED.value, "CANCELLED"}:
            return STATUS_CANCELLED
        if status in {
            InternalOrderStatus.SUBMITTED.value,
            InternalOrderStatus.ACCEPTED.value,
            InternalOrderStatus.PENDING.value,
            InternalOrderStatus.REQUESTED.value,
        }:
            return STATUS_SUBMITTED
        if status in {InternalOrderStatus.UNKNOWN_STALE.value, InternalOrderStatus.SYNC_FAILED.value}:
            return STATUS_SYNC_REQUIRED
        return STATUS_SUBMITTED if status else STATUS_SYNC_REQUIRED

    def _audit_payload(self, row: AgentChatOrderAction) -> dict[str, Any]:
        request_payload = _parse_json_object(row.request_payload_json)
        validation_payload = _parse_json_object(row.validation_payload_json)
        risk_payload = _parse_json_object(row.risk_payload_json)
        response_payload = _parse_json_object(row.response_payload_json)
        sync_payload = _parse_json_object(row.last_sync_payload_json)
        return _sanitize_payload(
            {
                "requested_by": "agent_chat",
                "conversation_key": row.conversation_key,
                "user_message_id": row.user_message_id,
                "assistant_message_id": row.assistant_message_id,
                "intent_category": "live_order_request",
                "selected_tool": "agent_chat_live_order_service",
                "confirmation_method": "confirmation_card",
                "confirmation_token_hash": _sha256_text(row.scope_hash),
                "scope_hash": row.scope_hash,
                "created_at": _iso_utc(row.created_at),
                "confirmed_at": _iso_utc(row.confirmed_at),
                "submitted_at": _iso_utc(row.submitted_at),
                "last_state_change_at": _iso_utc(row.last_state_change_at or row.updated_at),
                "last_sync_at": _iso_utc(row.last_sync_at),
                "runtime_settings_snapshot": _parse_json_object(row.safety_payload_json).get("safety_controls") or {},
                "validation_result_summary": _summary_payload(
                    validation_payload,
                    include_keys={
                        "validated_for_submission",
                        "estimated_amount",
                        "available_cash",
                        "block_reasons",
                        "warnings",
                    },
                ),
                "risk_gate_summary": _summary_payload(risk_payload),
                "submit_result_summary": _summary_payload(
                    response_payload,
                    include_keys={
                        "real_order_submitted",
                        "broker_submit_called",
                        "manual_submit_called",
                        "order_id",
                        "order_log_id",
                        "internal_status",
                    },
                ),
                "sync_result_summary": _summary_payload(
                    sync_payload,
                    include_keys={
                        "internal_status",
                        "broker_status",
                        "broker_order_status",
                        "sync_error",
                        "display_status",
                    },
                ),
                "request_summary": _summary_payload(
                    request_payload,
                    include_keys={"symbol", "side", "quantity", "currency", "order_type"},
                ),
            }
        )

    def _safety_controls(
        self,
        db: Session,
        *,
        settings: dict[str, Any],
        side: str,
        now_utc: datetime,
        validation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        global_settings = get_settings()
        market_session = validation.get("market_session") if isinstance(validation, dict) else {}
        if not isinstance(market_session, dict):
            market_session = {}
        max_orders = int(settings.get("agent_chat_live_order_max_orders_per_day") or 0)
        remaining = max(0, max_orders - self._daily_action_count(db, now_utc=now_utc))
        return {
            "dry_run": bool(settings.get("dry_run")),
            "kill_switch": bool(settings.get("kill_switch")),
            "kis_enabled": bool(getattr(global_settings, "kis_enabled", False)),
            "kis_real_order_enabled": bool(getattr(global_settings, "kis_real_order_enabled", False)),
            "agent_chat_live_order_enabled": bool(settings.get("agent_chat_live_order_enabled")),
            "agent_chat_live_order_kis_enabled": bool(settings.get("agent_chat_live_order_kis_enabled")),
            "agent_chat_live_order_buy_enabled": bool(settings.get("agent_chat_live_order_buy_enabled")),
            "agent_chat_live_order_sell_enabled": bool(settings.get("agent_chat_live_order_sell_enabled")),
            "side_enabled": bool(settings.get(f"agent_chat_live_order_{side}_enabled", False)),
            "market_open": market_session.get("is_market_open"),
            "entry_allowed_now": market_session.get("is_entry_allowed_now"),
            "no_new_entry_after": market_session.get("no_new_entry_after") or settings.get("kr_no_new_entry_after"),
            "daily_limit_remaining": remaining,
            "max_notional_limit": settings.get("agent_chat_live_order_max_notional_krw"),
            "max_notional_pct": settings.get("agent_chat_live_order_max_notional_pct"),
        }

    def _prepare_flags_enabled(self, settings: dict[str, Any], *, provider: str, side: str) -> bool:
        if provider != "kis":
            return False
        if not bool(settings["agent_chat_live_order_enabled"]):
            return False
        if not bool(settings["agent_chat_live_order_kis_enabled"]):
            return False
        if side == "buy" and not bool(settings["agent_chat_live_order_buy_enabled"]):
            return False
        if side == "sell" and not bool(settings["agent_chat_live_order_sell_enabled"]):
            return False
        return True

    def _confirm_settings_block(
        self,
        row: AgentChatOrderAction,
        settings: dict[str, Any],
    ) -> str | None:
        global_settings = get_settings()
        checks = {
            "agent_chat_live_order_enabled_false": bool(settings["agent_chat_live_order_enabled"]),
            "agent_chat_live_order_kis_enabled_false": bool(settings["agent_chat_live_order_kis_enabled"]),
            "dry_run_true": not bool(settings["dry_run"]),
            "kill_switch_true": not bool(settings["kill_switch"]),
            "kis_enabled_false": bool(getattr(global_settings, "kis_enabled", False)),
            "kis_real_order_enabled_false": bool(getattr(global_settings, "kis_real_order_enabled", False)),
            "requires_confirm_false": bool(settings["agent_chat_live_order_requires_confirm"]),
        }
        if row.side == "buy":
            checks["agent_chat_live_order_buy_enabled_false"] = bool(
                settings["agent_chat_live_order_buy_enabled"]
            )
        if row.side == "sell":
            checks["agent_chat_live_order_sell_enabled_false"] = bool(
                settings["agent_chat_live_order_sell_enabled"]
            )
        if row.order_type == "market":
            checks["market_order_disabled"] = bool(
                settings["agent_chat_live_order_allow_market_order"]
            )
        for reason, passed in checks.items():
            if not passed:
                return reason
        return None

    def _risk_block(
        self,
        row: AgentChatOrderAction,
        validation: dict[str, Any],
        settings: dict[str, Any],
    ) -> str | None:
        estimated = _float_or_none(
            validation.get("estimated_amount")
            or validation.get("estimated_notional")
            or row.estimated_notional
        )
        if estimated is None or estimated <= 0:
            return "estimated_notional_unavailable"
        max_krw = float(settings["agent_chat_live_order_max_notional_krw"] or 0)
        if max_krw > 0 and estimated > max_krw:
            return "agent_chat_max_notional_krw_exceeded"
        max_pct = float(settings["agent_chat_live_order_max_notional_pct"] or 0)
        available_cash = _float_or_none(validation.get("available_cash"))
        if row.side == "buy" and max_pct > 0 and available_cash and estimated > available_cash * max_pct:
            return "agent_chat_max_notional_pct_exceeded"
        return None

    def _daily_action_count(self, db: Session, *, now_utc: datetime) -> int:
        start_utc, end_utc = _kr_day_bounds_utc(now_utc)
        return (
            db.query(AgentChatOrderAction)
            .filter(AgentChatOrderAction.status.in_(sorted(SUBMITTED_ACTION_STATUSES)))
            .filter(AgentChatOrderAction.submitted_at >= start_utc)
            .filter(AgentChatOrderAction.submitted_at < end_utc)
            .count()
        )

    def _open_duplicate_order(
        self,
        db: Session,
        row: AgentChatOrderAction,
    ) -> OrderLog | None:
        return (
            db.query(OrderLog)
            .filter(OrderLog.broker == "kis")
            .filter(OrderLog.symbol == row.symbol)
            .filter(OrderLog.side == row.side)
            .filter(OrderLog.internal_status.in_(sorted(OPEN_ORDER_STATUSES)))
            .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
            .first()
        )

    def _confirmation_matches(
        self,
        row: AgentChatOrderAction,
        request: AgentChatLiveOrderConfirmRequest,
    ) -> bool:
        if request.confirmation is not True:
            return False
        if request.user_acknowledged_live_order is not True and not request.confirmation_phrase:
            return False
        phrase = str(request.confirmation_phrase or "").strip()
        token = str(request.confirmation_token or "").strip()
        return phrase == row.confirmation_phrase or token == row.scope_hash

    def _block(
        self,
        db: Session,
        row: AgentChatOrderAction,
        *,
        status: str,
        answer_type: str,
        reason: str,
        text: str,
        safety: dict[str, Any],
        now_utc: datetime,
        risk_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row.status = status
        row.risk_payload_json = _json(risk_payload or {"block_reason": reason})
        row.response_payload_json = _json({"status": status, "block_reason": reason})
        row.safety_payload_json = _json(safety)
        row.last_state_change_at = _naive_utc(now_utc)
        row.updated_at = _naive_utc(now_utc)
        db.commit()
        db.refresh(row)
        response = self._response(
            row,
            status=status,
            answer_type=answer_type,
            text=text,
            safety=safety,
            order=None,
            diagnostics={"block_reason": reason},
            db=db,
        )
        self._append_result_message(db, row, response)
        return response.model_dump(mode="json")

    def _response(
        self,
        row: AgentChatOrderAction,
        *,
        status: str,
        answer_type: str,
        text: str,
        safety: dict[str, Any],
        order: dict[str, Any] | None,
        diagnostics: dict[str, Any] | None = None,
        db: Session | None = None,
    ) -> AgentChatLiveOrderResponse:
        return AgentChatLiveOrderResponse(
            status=status,
            answer=AgentChatLiveOrderAnswer(text=text, answer_type=answer_type),
            live_order_action=AgentChatLiveOrderActionPayload.model_validate(
                self.serialize_action(row, db=db)
            ),
            order=order,
            safety=safety,
            diagnostics=diagnostics or {},
        )

    def _append_result_message(
        self,
        db: Session,
        row: AgentChatOrderAction,
        response: AgentChatLiveOrderResponse,
    ) -> None:
        status = "completed"
        if response.status in {STATUS_BLOCKED, STATUS_FAILED, STATUS_EXPIRED}:
            status = "blocked" if response.status != STATUS_FAILED else "failed"
        card = self.result_card(row, response)
        message = self.chat_service.append_message(
            db,
            conversation_key=row.conversation_key,
            request={
                "role": "assistant",
                "text": response.answer.text,
                "message_type": response.answer.answer_type,
                "status": status,
                "safety": response.safety,
                "metadata": {
                    "answer_type": response.answer.answer_type,
                    "live_order_action": self.serialize_action(row, db=db),
                    "live_order_result": response.model_dump(mode="json"),
                    "result_cards": [card.model_dump(mode="json")],
                    "available_actions": [],
                    "safety": response.safety,
                },
            },
        )["message"]
        response.assistant_message_id = message.get("id")

    def _source_metadata(self, row: AgentChatOrderAction) -> dict[str, Any]:
        request_payload = _parse_json_object(row.request_payload_json)
        safety_payload = _parse_json_object(row.safety_payload_json)
        return _sanitize_payload(
            {
                "source": "agent_chat_live_order",
                "source_type": "chat_confirmed_live_order",
                "source_context": "agent_chat_confirmed_live_order",
                "operator_action_source": "agent_chat_confirmation_card",
                "requested_by": "agent_chat",
                "agent_chat_order_action_id": row.id,
                "conversation_key": row.conversation_key,
                "user_message_id": row.user_message_id,
                "assistant_message_id": row.assistant_message_id,
                "intent_category": "live_order_request",
                "selected_tool": "agent_chat_live_order_service",
                "confirmation_method": "confirmation_card",
                "confirmation_token_hash": _sha256_text(row.scope_hash),
                "scope_hash": row.scope_hash,
                "runtime_settings_snapshot": safety_payload.get("safety_controls") or {},
                "symbol": row.symbol,
                "company_name": row.symbol_name,
                "side": row.side,
                "quantity": row.quantity,
                "estimated_price": row.estimated_price,
                "estimated_notional": row.estimated_notional,
                "manual_confirm_required": True,
                "real_order_submit_allowed": False,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "auto_buy_enabled": False,
                "auto_sell_enabled": False,
                "scheduler_real_order_enabled": False,
                "request_summary": {
                    "currency": request_payload.get("currency"),
                    "order_type": request_payload.get("order_type"),
                },
            }
        )

    def _order_payload(
        self,
        row: AgentChatOrderAction,
        *,
        body: dict[str, Any] | None = None,
        db: Session | None = None,
    ) -> dict[str, Any] | None:
        order = self._linked_order(db, row) if db is not None else None
        if row.related_order_id is None and body is None and order is None:
            return None
        if order is not None:
            return serialize_kis_order(order, include_sync_payload=False)
        return {
            "order_id": row.related_order_id or _int_or_none((body or {}).get("order_id")),
            "broker_order_id": row.broker_order_id or _text_or_none((body or {}).get("broker_order_id")),
            "symbol": row.symbol,
            "side": row.side,
            "quantity": row.quantity,
            "status": (body or {}).get("internal_status") or row.status,
        }

    def _get_action(self, db: Session, action_id: int) -> AgentChatOrderAction:
        row = db.get(AgentChatOrderAction, action_id)
        if row is None:
            raise AgentChatLiveOrderNotFound(str(action_id))
        return row

    def _prepare_block(
        self,
        reason: str,
        *,
        safety: dict[str, Any],
        detail: str | None = None,
    ) -> dict[str, Any]:
        data = {
            "direct_order_blocked": True,
            "block_reason": reason,
        }
        if detail:
            data["detail"] = detail
        return {
            "created": False,
            "reason": reason,
            "data": data,
            "safety": safety,
            "result_cards": [],
        }

    def _manual_confirmation_phrase(self, client: KisClient) -> str:
        return str(
            getattr(client.settings, "kis_confirmation_phrase", None)
            or KIS_MANUAL_CONFIRMATION_PHRASE
        )

    def _answer_type_for_status(self, status: str) -> str:
        return {
            STATUS_SUBMITTED: "live_order_submitted",
            STATUS_SYNC_REQUIRED: "live_order_status_sync_required",
            STATUS_FILLED: "live_order_filled",
            STATUS_PARTIALLY_FILLED: "live_order_partially_filled",
            STATUS_REJECTED: "live_order_rejected",
            STATUS_BLOCKED: "live_order_blocked",
            STATUS_CANCELLED: "live_order_cancelled",
            STATUS_EXPIRED: "live_order_expired",
            STATUS_FAILED: "live_order_blocked",
            STATUS_CONFIRMING: "live_order_blocked",
            STATUS_SUBMITTING: "live_order_blocked",
        }.get(status, "live_order_blocked")

    def _default_kis_client(self, db: Session) -> KisClient:
        settings = get_settings()
        return KisClient(settings, KisAuthManager(settings, db))


def _base_safety(*, real_order_submitted: bool) -> dict[str, Any]:
    return {
        "read_only": False,
        "safe_execution_only": True,
        "real_order_submitted": real_order_submitted,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "validation_called": False,
        "setting_changed": False,
        "scheduler_changed": False,
        "confirm_live_auto_checked": False,
        "broker_api_called": False,
        "mutation": False,
    }


def _sync_safety() -> dict[str, Any]:
    return {
        "read_only": True,
        "safe_execution_only": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "validation_called": False,
        "setting_changed": False,
        "scheduler_changed": False,
        "confirm_live_auto_checked": False,
        "broker_api_called": True,
        "mutation": False,
        "sync_submitted_new_order": False,
    }


def _utc_now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    return _utc_now(value).replace(tzinfo=None)


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _utc_now(value).isoformat().replace("+00:00", "Z")


def _is_expired(expires_at: datetime | None, *, now_utc: datetime) -> bool:
    if expires_at is None:
        return True
    return _utc_now(expires_at) <= now_utc


def _kr_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    local = _utc_now(now_utc).astimezone(KR_TZ)
    start_local = datetime.combine(local.date(), time.min, tzinfo=KR_TZ)
    end_local = start_local + timedelta(days=1)
    return _naive_utc(start_local), _naive_utc(end_local)


def _scope_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sha256_text(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json(payload: Any) -> str:
    return json.dumps(_sanitize_payload(payload), ensure_ascii=False, default=str)


def _parse_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _sanitize_payload(value: Any) -> Any:
    sensitive = {
        "access_token",
        "refresh_token",
        "authorization",
        "appsecret",
        "appkey",
        "password",
        "token_value",
        "approval_key",
        "approval_token",
        "kis_app_secret",
        "kis_access_token",
        "kis_approval_key",
        "kis_account_no",
        "CANO",
    }
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if str(key).lower() in {name.lower() for name in sensitive}:
                continue
            result[str(key)] = _sanitize_payload(item)
        return result
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, str):
        return sanitize_kis_text(value)
    return value


def _summary_payload(
    payload: dict[str, Any],
    *,
    include_keys: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload:
        return {}
    source = _sanitize_payload(payload)
    if include_keys:
        result = {
            key: source.get(key)
            for key in include_keys
            if source.get(key) is not None
        }
    else:
        result = source
    if "error_message" in result and result["error_message"] is not None:
        result["error_message"] = sanitize_kis_text(str(result["error_message"]))[:300]
    return result


def _normalize_symbol(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def _normalize_side(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"buy", "sell"} else "none"


def _whole_quantity(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if number < 1 or number != int(number):
        return None
    return int(number)


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _text_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _safe_error(exc: Exception) -> str:
    text = sanitize_kis_text(str(exc).strip() or exc.__class__.__name__)
    if len(text) > 200:
        text = f"{text[:200]}..."
    return f"{exc.__class__.__name__}: {text}"


def _money(value: Any, currency: str | None) -> str:
    number = _float_or_none(value)
    if number is None:
        return "-"
    if str(currency or "").upper() == "KRW":
        return f"KRW {number:,.0f}"
    return f"{number:,.2f}"
