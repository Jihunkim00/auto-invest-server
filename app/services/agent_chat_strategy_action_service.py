from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import AgentChatStrategyAction
from app.schemas.agent_chat_orchestrator import AgentChatIntent
from app.schemas.agent_chat_strategy import (
    AgentChatStrategyActionAnswer,
    AgentChatStrategyActionConfirmRequest,
    AgentChatStrategyActionPayload,
    AgentChatStrategyActionResponse,
)
from app.schemas.agent_chat_tool import AgentChatResultCard
from app.services.agent_chat_service import AgentChatService
from app.services.strategy_profile_service import (
    StrategyProfileAckRequired,
    StrategyProfileNotFound,
    StrategyProfileService,
)


STATUS_PENDING = "pending_confirmation"
STATUS_CONFIRMED = "confirmed"
STATUS_APPLIED = "applied"
STATUS_CANCELLED = "cancelled"
STATUS_EXPIRED = "expired"
STATUS_BLOCKED = "blocked"
STATUS_FAILED = "failed"
ACTION_TYPE = "strategy_profile_apply"
CONFIRM_TTL_MINUTES = 15


class AgentChatStrategyActionNotFound(Exception):
    pass


class AgentChatStrategyActionService:
    def __init__(
        self,
        *,
        strategy_profiles: StrategyProfileService | None = None,
        chat_service: AgentChatService | None = None,
    ) -> None:
        self.strategy_profiles = strategy_profiles or StrategyProfileService()
        self.chat_service = chat_service or AgentChatService()

    def prepare(
        self,
        db: Session,
        *,
        intent: AgentChatIntent,
        conversation_key: str,
        user_message_id: int | None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        requested_profile = _normalize_profile(getattr(intent, "requested_profile", None))
        if requested_profile is None:
            requested_profile = _profile_from_message_context(intent)
        if requested_profile is None:
            return {
                "created": False,
                "data": {"error": "strategy_profile_not_resolved"},
                "safety": _strategy_safety(setting_changed=False),
                "result_cards": [],
            }

        now_utc = _utc_now(now)
        active = self.strategy_profiles.active_profile(db)
        requested = self.strategy_profiles.get_profile(db, requested_profile)
        token = uuid4().hex
        row = AgentChatStrategyAction(
            conversation_key=conversation_key,
            user_message_id=user_message_id,
            assistant_message_id=None,
            action_type=ACTION_TYPE,
            requested_profile=requested.profile_name,
            current_profile=active.profile_name,
            status=STATUS_PENDING,
            confirmation_token_hash=_sha256(token),
            expires_at=_naive_utc(now_utc + timedelta(minutes=CONFIRM_TTL_MINUTES)),
            safety_flags=_json(_strategy_safety(setting_changed=False)),
            created_at=_naive_utc(now_utc),
            updated_at=_naive_utc(now_utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        action = self.serialize_action(row, db=db)
        card = self.strategy_action_card(action)
        return {
            "created": True,
            "strategy_action": action,
            "data": {
                "strategy_action": action,
                "requested_profile": action.get("requested_profile_payload"),
                "active_profile": self.strategy_profiles.serialize_profile(active),
            },
            "available_actions": [
                "confirm_strategy_profile",
                "cancel_strategy_profile_action",
            ],
            "safety": _strategy_safety(setting_changed=False),
            "result_cards": [card],
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
        row = db.get(AgentChatStrategyAction, action_id)
        if row is None:
            return
        row.assistant_message_id = assistant_message_id
        row.updated_at = _naive_utc(_utc_now())
        db.commit()

    def get(self, db: Session, *, action_id: int) -> dict[str, Any]:
        row = self._get_action(db, action_id)
        self._expire_if_needed(db, row)
        return self.serialize_action(row, db=db)

    def confirm(
        self,
        db: Session,
        *,
        action_id: int,
        request: AgentChatStrategyActionConfirmRequest,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        row = self._get_action(db, action_id)
        now_utc = _utc_now(now)
        if row.status != STATUS_PENDING:
            return self._blocked_response(
                db,
                row,
                status=STATUS_BLOCKED,
                answer_type="strategy_profile_blocked",
                text=f"이 전략 변경 action은 현재 {row.status} 상태라 적용할 수 없습니다.",
                reason="action_not_pending",
                now_utc=now_utc,
            )
        if _is_expired(row.expires_at, now_utc=now_utc):
            row.status = STATUS_EXPIRED
            row.updated_at = _naive_utc(now_utc)
            db.commit()
            return self._blocked_response(
                db,
                row,
                status=STATUS_EXPIRED,
                answer_type="strategy_profile_expired",
                text="전략 변경 확인 시간이 만료되었습니다. 다시 요청해 주세요.",
                reason="expired",
                now_utc=now_utc,
            )
        if request.confirmation is not True or request.confirm_operator_ack is not True:
            return self._blocked_response(
                db,
                row,
                status=STATUS_BLOCKED,
                answer_type="strategy_profile_blocked",
                text="전략 프로필을 적용하려면 명시적인 확인이 필요합니다.",
                reason="confirmation_missing",
                now_utc=now_utc,
            )

        try:
            result = self.strategy_profiles.apply_preset(
                db,
                profile_name=row.requested_profile,
                confirm_operator_ack=True,
                source="agent_chat",
            )
            row.status = STATUS_APPLIED
            row.confirmed_at = _naive_utc(now_utc)
            row.result_payload = _json(result)
            row.safety_flags = _json(result.get("safety") or _strategy_safety(setting_changed=True))
            row.updated_at = _naive_utc(now_utc)
            db.commit()
            db.refresh(row)
        except (StrategyProfileAckRequired, StrategyProfileNotFound, ValueError) as exc:
            row.status = STATUS_FAILED
            row.result_payload = _json({"error": str(exc)})
            row.safety_flags = _json(_strategy_safety(setting_changed=False))
            row.updated_at = _naive_utc(now_utc)
            db.commit()
            db.refresh(row)
            return self._blocked_response(
                db,
                row,
                status=STATUS_FAILED,
                answer_type="strategy_profile_blocked",
                text=f"전략 프로필 적용에 실패했습니다. 사유: {exc}",
                reason="apply_failed",
                now_utc=now_utc,
            )

        active = result.get("active_profile")
        text = (
            f"{active.get('display_name', row.requested_profile)} 전략이 적용되었습니다. "
            "이 설정은 주문을 즉시 실행하지 않습니다."
        )
        response = AgentChatStrategyActionResponse(
            status=STATUS_APPLIED,
            answer=AgentChatStrategyActionAnswer(
                text=text,
                answer_type="strategy_profile_applied",
            ),
            strategy_action=AgentChatStrategyActionPayload.model_validate(
                self.serialize_action(row, db=db)
            ),
            active_profile=active,
            safety=result.get("safety") or _strategy_safety(setting_changed=True),
            diagnostics={
                "audit_id": result.get("audit_id"),
                "real_order_submitted": False,
                "validation_called": False,
                "scheduler_changed": False,
            },
        )
        self._append_result_message(db, row, response)
        return response.model_dump(mode="json")

    def cancel(
        self,
        db: Session,
        *,
        action_id: int,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        row = self._get_action(db, action_id)
        now_utc = _utc_now(now)
        if row.status != STATUS_PENDING:
            return self._blocked_response(
                db,
                row,
                status=STATUS_BLOCKED,
                answer_type="strategy_profile_blocked",
                text=f"이 전략 변경 action은 현재 {row.status} 상태라 취소할 수 없습니다.",
                reason="action_not_pending",
                now_utc=now_utc,
            )
        row.status = STATUS_CANCELLED
        row.cancelled_at = _naive_utc(now_utc)
        row.result_payload = _json({"reason": reason or "operator_cancelled"})
        row.safety_flags = _json(_strategy_safety(setting_changed=False))
        row.updated_at = _naive_utc(now_utc)
        db.commit()
        db.refresh(row)
        response = AgentChatStrategyActionResponse(
            status=STATUS_CANCELLED,
            answer=AgentChatStrategyActionAnswer(
                text="전략 프로필 변경 요청을 취소했습니다. 현재 active profile은 변경되지 않았습니다.",
                answer_type="strategy_profile_cancelled",
            ),
            strategy_action=AgentChatStrategyActionPayload.model_validate(
                self.serialize_action(row, db=db)
            ),
            safety=_strategy_safety(setting_changed=False),
            diagnostics={"cancel_reason": reason or "operator_cancelled"},
        )
        self._append_result_message(db, row, response)
        return response.model_dump(mode="json")

    def serialize_action(self, row: AgentChatStrategyAction, *, db: Session | None = None) -> dict[str, Any]:
        active_profile = None
        requested_payload = None
        if db is not None:
            try:
                active_profile = self.strategy_profiles.serialize_profile(
                    self.strategy_profiles.active_profile(db)
                )
            except Exception:
                active_profile = None
            try:
                requested_payload = self.strategy_profiles.serialize_profile(
                    self.strategy_profiles.get_profile(db, row.requested_profile)
                )
            except Exception:
                requested_payload = None
        return {
            "action_id": row.id,
            "conversation_key": row.conversation_key,
            "user_message_id": row.user_message_id,
            "assistant_message_id": row.assistant_message_id,
            "action_type": row.action_type,
            "requested_profile": row.requested_profile,
            "current_profile": row.current_profile,
            "status": row.status,
            "expires_at": row.expires_at,
            "confirmed_at": row.confirmed_at,
            "cancelled_at": row.cancelled_at,
            "active_profile": active_profile,
            "requested_profile_payload": requested_payload,
            "result_payload": _parse_json_object(row.result_payload),
            "safety": _parse_json_object(row.safety_flags) or _strategy_safety(setting_changed=False),
            "audit": _audit_payload(row),
        }

    def strategy_action_card(self, action: dict[str, Any]) -> AgentChatResultCard:
        requested = action.get("requested_profile_payload") or {}
        profile_name = str(action.get("requested_profile") or "").upper()
        return AgentChatResultCard(
            card_type="strategy_profile_action",
            title="Strategy Profile Confirmation",
            subtitle="프로필 변경은 확인 후에만 적용됩니다.",
            primary_value=requested.get("display_name") or profile_name,
            badges=[
                "PROFILE ONLY",
                "NO ORDER SUBMIT",
                "CONFIRM REQUIRED",
                "STRATEGY TARGET",
                profile_name,
            ],
            rows=[
                {"label": "Requested", "value": requested.get("display_name") or action.get("requested_profile")},
                {"label": "Monthly target", "value": _target_range(requested)},
                {"label": "Monthly max loss", "value": _pct(requested.get("monthly_max_loss_pct"))},
                {"label": "Daily max loss", "value": _pct(requested.get("daily_max_loss_pct"))},
                {"label": "Order limit", "value": _money(requested.get("max_order_notional_krw"))},
                {"label": "Status", "value": action.get("status")},
            ],
            data=action,
        )

    def _blocked_response(
        self,
        db: Session,
        row: AgentChatStrategyAction,
        *,
        status: str,
        answer_type: str,
        text: str,
        reason: str,
        now_utc: datetime,
    ) -> dict[str, Any]:
        safety = _strategy_safety(setting_changed=False)
        row.result_payload = _json({"block_reason": reason})
        row.safety_flags = _json(safety)
        row.updated_at = _naive_utc(now_utc)
        db.commit()
        db.refresh(row)
        response = AgentChatStrategyActionResponse(
            status=status,
            answer=AgentChatStrategyActionAnswer(text=text, answer_type=answer_type),
            strategy_action=AgentChatStrategyActionPayload.model_validate(
                self.serialize_action(row, db=db)
            ),
            safety=safety,
            diagnostics={"block_reason": reason},
        )
        self._append_result_message(db, row, response)
        return response.model_dump(mode="json")

    def _append_result_message(
        self,
        db: Session,
        row: AgentChatStrategyAction,
        response: AgentChatStrategyActionResponse,
    ) -> None:
        status = "completed"
        if response.status in {STATUS_BLOCKED, STATUS_FAILED, STATUS_EXPIRED}:
            status = "blocked" if response.status != STATUS_FAILED else "failed"
        card = self.strategy_action_card(self.serialize_action(row, db=db))
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
                    "strategy_action": self.serialize_action(row, db=db),
                    "strategy_action_result": response.model_dump(mode="json"),
                    "active_profile": (
                        response.active_profile.model_dump(mode="json")
                        if hasattr(response.active_profile, "model_dump")
                        else response.active_profile
                    ),
                    "result_cards": [card.model_dump(mode="json")],
                    "available_actions": [],
                    "safety": response.safety,
                },
            },
        )["message"]
        response.assistant_message_id = message.get("id")

    def _get_action(self, db: Session, action_id: int) -> AgentChatStrategyAction:
        row = db.get(AgentChatStrategyAction, action_id)
        if row is None:
            raise AgentChatStrategyActionNotFound(str(action_id))
        return row

    def _expire_if_needed(self, db: Session, row: AgentChatStrategyAction) -> None:
        if row.status != STATUS_PENDING:
            return
        if not _is_expired(row.expires_at, now_utc=_utc_now()):
            return
        row.status = STATUS_EXPIRED
        row.updated_at = _naive_utc(_utc_now())
        row.safety_flags = _json(_strategy_safety(setting_changed=False))
        db.commit()
        db.refresh(row)


def _profile_from_message_context(intent: AgentChatIntent) -> str | None:
    return _normalize_profile(getattr(intent, "requested_profile", None))


def _normalize_profile(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"safe", "balanced", "aggressive"}:
        return text
    return None


def _strategy_safety(*, setting_changed: bool) -> dict[str, Any]:
    return {
        "read_only": False,
        "safe_execution_only": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "validation_called": False,
        "setting_changed": setting_changed,
        "scheduler_changed": False,
        "confirm_live_auto_checked": False,
        "broker_api_called": False,
        "mutation": setting_changed,
    }


def _audit_payload(row: AgentChatStrategyAction) -> dict[str, Any]:
    return {
        "action_id": row.id,
        "action_type": row.action_type,
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _target_range(profile: dict[str, Any]) -> str:
    return f"{_pct(profile.get('monthly_target_min_pct'))} ~ {_pct(profile.get('monthly_target_max_pct'))}"


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return "-"


def _money(value: Any) -> str:
    try:
        return f"KRW {float(value):,.0f}"
    except Exception:
        return "-"


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _parse_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    return _utc_now(value).replace(tzinfo=None)


def _is_expired(expires_at: datetime | None, *, now_utc: datetime) -> bool:
    if expires_at is None:
        return True
    return _utc_now(expires_at) <= _utc_now(now_utc)

