from __future__ import annotations

import json
import re
from datetime import UTC, datetime, time
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import (
    AgentChatConversation,
    AgentChatMessage,
    AgentPlan,
    AgentPlanRun,
    AgentReviewQueueState,
    AuthApprovalRequest,
)
from app.schemas.agent_operations import AgentReviewQueueStateRequest


class AgentReviewQueueItemNotFound(Exception):
    pass


class AgentOperationsService:
    safe_metadata_keys = {
        "command_type",
        "domain",
        "market",
        "provider",
        "symbol",
        "side",
        "risk_level",
        "status",
        "command_log_id",
        "plan_id",
        "plan_run_id",
        "conversation_key",
        "scope_hash",
        "blocked_reason",
        "user_visible_summary",
        "result_type",
    }
    sensitive_key_pattern = re.compile(
        r"(?i)\b("
        r"OPENAI_API_KEY|access_token|refresh_token|authorization|appsecret|"
        r"appkey|broker_secret|password|token_value|approval_token"
        r")\b\s*[:=]\s*(?:Bearer\s+)?([^\s,;}\]]+)"
    )
    bearer_pattern = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+")
    account_number_pattern = re.compile(r"\b\d{8,}\b")

    def summary(self, db: Session) -> dict[str, Any]:
        today_start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
        latest_plan = (
            db.query(AgentPlan)
            .order_by(AgentPlan.created_at.desc(), AgentPlan.id.desc())
            .first()
        )
        latest_run = (
            db.query(AgentPlanRun)
            .order_by(AgentPlanRun.created_at.desc(), AgentPlanRun.id.desc())
            .first()
        )
        latest_conversation = (
            db.query(AgentChatConversation)
            .order_by(
                AgentChatConversation.last_message_at.desc().nullslast(),
                AgentChatConversation.updated_at.desc(),
                AgentChatConversation.id.desc(),
            )
            .first()
        )
        blocked_runs = db.query(AgentPlanRun).filter(AgentPlanRun.status == "blocked").count()
        failed_runs = db.query(AgentPlanRun).filter(AgentPlanRun.status == "failed").count()
        failed_plans = db.query(AgentPlan).filter(AgentPlan.status == "failed").count()
        pending_auth = (
            db.query(AuthApprovalRequest)
            .filter(AuthApprovalRequest.status.in_(["pending", "requested"]))
            .count()
        )
        prefill_ready = (
            db.query(AgentPlanRun)
            .filter(
                AgentPlanRun.status == "completed",
                AgentPlanRun.result_type == "prefill_payload",
            )
            .count()
        )
        safe_completed = (
            db.query(AgentPlanRun)
            .filter(
                AgentPlanRun.status == "completed",
                AgentPlanRun.result_type != "prefill_payload",
            )
            .count()
        )
        active_plans = (
            db.query(AgentPlan)
            .filter(~AgentPlan.status.in_(["cancelled", "expired", "executed"]))
            .count()
        )
        summary = {
            "total_plans": db.query(AgentPlan).count(),
            "total_active_plans": active_plans,
            "active_plans": active_plans,
            "ready_for_review_count": db.query(AgentPlan)
            .filter(AgentPlan.status == "ready_for_review")
            .count(),
            "pending_auth_count": pending_auth,
            "auth_required_count": pending_auth,
            "blocked_count": db.query(AgentPlan).filter(AgentPlan.status == "blocked").count()
            + blocked_runs,
            "blocked_run_count": blocked_runs,
            "prefill_ready_count": prefill_ready,
            "safe_run_completed_count": safe_completed,
            "failed_count": failed_runs + failed_plans,
            "active_conversation_count": db.query(AgentChatConversation)
            .filter(AgentChatConversation.status == "active")
            .count(),
            "archived_conversation_count": db.query(AgentChatConversation)
            .filter(AgentChatConversation.status == "archived")
            .count(),
            "today_messages_count": db.query(AgentChatMessage)
            .filter(AgentChatMessage.created_at >= today_start)
            .count(),
            "latest_conversation_key": latest_conversation.conversation_key
            if latest_conversation
            else None,
            "latest_plan_id": latest_plan.id if latest_plan else None,
            "latest_run_id": latest_run.id if latest_run else None,
            "latest_plan_at": latest_plan.created_at if latest_plan else None,
            "latest_run_at": latest_run.created_at if latest_run else None,
        }
        return {"summary": summary, "safety": self._safety()}

    def review_queue(
        self,
        db: Session,
        *,
        status: str | None = "open",
        queue_type: str | None = "all",
        conversation_key: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        items = self._build_items(db, conversation_key=conversation_key)
        states = self._state_map(db, [item["queue_key"] for item in items])
        items = [self._apply_state(item, states.get(item["queue_key"])) for item in items]
        if queue_type and queue_type != "all":
            items = [item for item in items if item["queue_type"] == queue_type]
        if status and status != "all":
            items = [item for item in items if item["review_status"] == status]
        items.sort(key=self._sort_key, reverse=True)
        return {
            "count": len(items[:limit]),
            "items": items[:limit],
            "safety": self._safety(),
        }

    def mark_reviewed(
        self,
        db: Session,
        *,
        queue_key: str,
        request: AgentReviewQueueStateRequest | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._state_request(request)
        item = self._find_item(db, queue_key)
        state = self._upsert_state(
            db,
            item=item,
            status="reviewed",
            reviewer_note=payload.reviewer_note,
        )
        return {"state": self._serialize_state(state), "item": self._apply_state(item, state)}

    def dismiss(
        self,
        db: Session,
        *,
        queue_key: str,
        request: AgentReviewQueueStateRequest | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._state_request(request)
        item = self._find_item(db, queue_key)
        state = self._upsert_state(
            db,
            item=item,
            status="dismissed",
            reviewer_note=payload.reviewer_note,
        )
        return {"state": self._serialize_state(state), "item": self._apply_state(item, state)}

    def _build_items(
        self,
        db: Session,
        *,
        conversation_key: str | None = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        auth_query = db.query(AuthApprovalRequest).filter(
            AuthApprovalRequest.status.in_(["pending", "requested"])
        )
        if conversation_key:
            auth_query = auth_query.filter(AuthApprovalRequest.conversation_id == conversation_key)
        for auth in auth_query.order_by(AuthApprovalRequest.created_at.desc()).limit(100).all():
            plan = db.get(AgentPlan, auth.plan_id)
            items.append(self._auth_item(auth, plan))

        plan_query = db.query(AgentPlan)
        if conversation_key:
            plan_query = plan_query.filter(AgentPlan.conversation_id == conversation_key)
        for plan in plan_query.order_by(AgentPlan.created_at.desc(), AgentPlan.id.desc()).limit(150).all():
            item = self._plan_item(plan)
            if item is not None:
                items.append(item)

        run_query = db.query(AgentPlanRun)
        if conversation_key:
            run_query = run_query.filter(AgentPlanRun.conversation_id == conversation_key)
        for run in run_query.order_by(AgentPlanRun.created_at.desc(), AgentPlanRun.id.desc()).limit(150).all():
            plan = db.get(AgentPlan, run.plan_id)
            items.append(self._run_item(run, plan))

        message_query = db.query(AgentChatMessage).filter(
            AgentChatMessage.message_type.in_(
                ["manual_prefill_result", "safe_run_result", "auth_required", "blocked", "error"]
            )
        )
        if conversation_key:
            message_query = message_query.filter(AgentChatMessage.conversation_key == conversation_key)
        for message in (
            message_query.order_by(AgentChatMessage.created_at.desc(), AgentChatMessage.id.desc())
            .limit(100)
            .all()
        ):
            if message.plan_id or message.plan_run_id:
                continue
            items.append(self._chat_message_item(message))
        return items

    def _auth_item(
        self,
        auth: AuthApprovalRequest,
        plan: AgentPlan | None,
    ) -> dict[str, Any]:
        title = plan.plan_title if plan else "Authorization required"
        summary = auth.requested_action_summary or (plan.user_visible_summary if plan else "")
        return self._item(
            queue_key=f"auth_{auth.id}",
            item_type="auth_approval_request",
            queue_type="auth_required",
            priority="high",
            conversation_key=auth.conversation_id or (plan.conversation_id if plan else None),
            command_log_id=auth.command_log_id,
            plan_id=auth.plan_id,
            auth_approval_request_id=auth.id,
            command_type=plan.command_type if plan else None,
            domain=plan.domain if plan else None,
            market=plan.market if plan else None,
            provider=plan.provider if plan else None,
            symbol=plan.symbol if plan else None,
            side=plan.side if plan else None,
            risk_level=auth.risk_level,
            status=auth.status,
            title=title,
            summary=summary,
            blocked_reason="auth_required",
            safety_badges=["AUTH_REQUIRED", "NO_AUTO_SUBMIT", "MANUAL_APPROVAL_REQUIRED"],
            can_run_safe_action=False,
            can_prepare_ticket=False,
            created_at=auth.created_at,
            updated_at=auth.updated_at,
            metadata={
                "scope_hash": auth.scope_hash,
                "status": auth.status,
                "plan_id": auth.plan_id,
                "command_log_id": auth.command_log_id,
                "conversation_key": auth.conversation_id,
            },
        )

    def _plan_item(self, plan: AgentPlan) -> dict[str, Any] | None:
        queue_type = self._queue_type_for_plan(plan)
        if queue_type is None:
            return None
        priority = self._priority(queue_type, self._blocked_reason_from_plan(plan))
        return self._item(
            queue_key=f"plan_{plan.id}",
            item_type="agent_plan",
            queue_type=queue_type,
            priority=priority,
            conversation_key=plan.conversation_id,
            command_log_id=plan.command_log_id,
            plan_id=plan.id,
            command_type=plan.command_type,
            domain=plan.domain,
            market=plan.market,
            provider=plan.provider,
            symbol=plan.symbol,
            side=plan.side,
            risk_level=plan.risk_level,
            status=plan.status,
            title=plan.plan_title,
            summary=plan.user_visible_summary or plan.plan_summary,
            blocked_reason=self._blocked_reason_from_plan(plan),
            safety_badges=self._badges(queue_type),
            can_run_safe_action=self._can_run_safe_action(plan),
            can_prepare_ticket=self._can_prepare_ticket(plan),
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            metadata={
                "scope_hash": plan.scope_hash,
                "status": plan.status,
                "plan_id": plan.id,
                "command_log_id": plan.command_log_id,
                "conversation_key": plan.conversation_id,
                "user_visible_summary": plan.user_visible_summary,
            },
        )

    def _run_item(self, run: AgentPlanRun, plan: AgentPlan | None) -> dict[str, Any]:
        queue_type = self._queue_type_for_run(run)
        blocked_reason = self._blocked_reason_from_run(run)
        return self._item(
            queue_key=f"run_{run.id}",
            item_type="agent_plan_run",
            queue_type=queue_type,
            priority=self._priority(queue_type, blocked_reason),
            conversation_key=run.conversation_id or (plan.conversation_id if plan else None),
            command_log_id=run.command_log_id,
            plan_id=run.plan_id,
            plan_run_id=run.id,
            command_type=run.command_type,
            domain=run.domain,
            market=plan.market if plan else None,
            provider=plan.provider if plan else None,
            symbol=plan.symbol if plan else None,
            side=plan.side if plan else None,
            risk_level=plan.risk_level if plan else None,
            status=run.status,
            title=self._run_title(run, plan),
            summary=self._run_summary(run, plan),
            blocked_reason=blocked_reason,
            safety_badges=self._badges(queue_type),
            can_run_safe_action=False,
            can_prepare_ticket=queue_type == "prefill_ready",
            created_at=run.created_at,
            updated_at=run.completed_at or run.failed_at or run.created_at,
            metadata={
                "scope_hash": run.scope_hash,
                "status": run.status,
                "result_type": run.result_type,
                "plan_id": run.plan_id,
                "plan_run_id": run.id,
                "command_log_id": run.command_log_id,
                "conversation_key": run.conversation_id,
                "blocked_reason": blocked_reason,
            },
        )

    def _chat_message_item(self, message: AgentChatMessage) -> dict[str, Any]:
        queue_type = {
            "manual_prefill_result": "prefill_ready",
            "safe_run_result": "safe_run_completed",
            "auth_required": "auth_required",
            "blocked": "blocked",
            "error": "failed",
        }.get(message.message_type, "ready_for_review")
        return self._item(
            queue_key=f"chat_message_{message.id}",
            item_type="agent_chat_message",
            queue_type=queue_type,
            priority=self._priority(queue_type, None),
            conversation_key=message.conversation_key,
            command_log_id=message.command_log_id,
            plan_id=message.plan_id,
            plan_run_id=message.plan_run_id,
            command_type=self._parse_json_object(message.metadata_json).get("command_type"),
            status=message.status,
            title=self._message_title(message),
            summary=message.text,
            blocked_reason=self._parse_json_object(message.metadata_json).get("blocked_reason"),
            safety_badges=self._badges(queue_type),
            can_run_safe_action=False,
            can_prepare_ticket=queue_type == "prefill_ready" and bool(message.plan_id),
            created_at=message.created_at,
            updated_at=message.updated_at or message.created_at,
            metadata={
                "status": message.status,
                "plan_id": message.plan_id,
                "plan_run_id": message.plan_run_id,
                "command_log_id": message.command_log_id,
                "conversation_key": message.conversation_key,
            },
        )

    def _item(self, **kwargs: Any) -> dict[str, Any]:
        queue_key = kwargs["queue_key"]
        metadata = self._sanitize_metadata(kwargs.pop("metadata", {}))
        item = {
            "queue_id": queue_key,
            "queue_key": queue_key,
            "review_status": "open",
            "reviewer_note": None,
            **kwargs,
            "metadata": metadata,
        }
        item["title"] = self._sanitize_text(item.get("title") or "Agent review item", max_length=160)
        item["summary"] = self._sanitize_text(item.get("summary") or "", max_length=500)
        if item.get("blocked_reason") is not None:
            item["blocked_reason"] = self._sanitize_text(str(item["blocked_reason"]), max_length=160)
        return item

    def _queue_type_for_plan(self, plan: AgentPlan) -> str | None:
        status = str(plan.status or "")
        if status in {"pending_auth", "auth_required", "auth_requested"} or bool(plan.requires_auth):
            return "auth_required"
        if status == "blocked":
            return "blocked"
        if status == "failed":
            return "failed"
        if status == "ready_for_review":
            return "manual_ticket_candidates" if self._can_prepare_ticket(plan) else "ready_for_review"
        return None

    def _queue_type_for_run(self, run: AgentPlanRun) -> str:
        if run.status == "blocked":
            return "blocked"
        if run.status == "failed":
            return "failed"
        if run.status == "completed" and run.result_type == "prefill_payload":
            return "prefill_ready"
        if run.status == "completed":
            return "safe_run_completed"
        return "ready_for_review"

    def _can_prepare_ticket(self, plan: AgentPlan) -> bool:
        if bool(plan.requires_auth) or str(plan.status) in {"blocked", "cancelled", "expired"}:
            return False
        return (
            str(plan.command_type)
            in {"PREPARE_MANUAL_BUY_TICKET", "PREPARE_MANUAL_SELL_TICKET"}
            or str(plan.risk_level) == "prefill_only"
        )

    def _can_run_safe_action(self, plan: AgentPlan) -> bool:
        if self._can_prepare_ticket(plan):
            return False
        if bool(plan.requires_auth) or str(plan.status) in {"blocked", "cancelled", "expired"}:
            return False
        if bool(plan.allow_live_order or plan.allow_setting_change or plan.allow_scheduler_change):
            return False
        return str(plan.risk_level) in {"read_only", "analysis_only", "settings_safe"} or str(
            plan.domain
        ) in {"analysis", "portfolio", "position", "logs", "watchlist"}

    def _priority(self, queue_type: str, blocked_reason: str | None) -> str:
        reason = str(blocked_reason or "")
        if queue_type in {"auth_required", "failed"}:
            return "high"
        if queue_type == "blocked" and (
            "live" in reason or "scope_hash" in reason or "mismatch" in reason
        ):
            return "high"
        if queue_type in {"blocked", "prefill_ready", "ready_for_review", "manual_ticket_candidates"}:
            return "medium"
        return "low"

    def _badges(self, queue_type: str) -> list[str]:
        badges = ["NO_AUTO_SUBMIT"]
        if queue_type == "auth_required":
            return ["AUTH_REQUIRED", *badges]
        if queue_type == "blocked":
            return ["BLOCKED", *badges]
        if queue_type in {"prefill_ready", "manual_ticket_candidates"}:
            return ["PREFILL_ONLY", "MANUAL_VALIDATION_REQUIRED", "CONFIRM_LIVE_MANUAL", *badges]
        if queue_type == "safe_run_completed":
            return ["SAFE_EXECUTION_ONLY", *badges]
        if queue_type == "failed":
            return ["FAILED", *badges]
        return ["READY_FOR_REVIEW", *badges]

    def _blocked_reason_from_plan(self, plan: AgentPlan) -> str | None:
        if plan.cancellation_reason:
            return plan.cancellation_reason
        safety = self._parse_json_object(plan.safety_json)
        return safety.get("blocked_reason") or safety.get("reason")

    def _blocked_reason_from_run(self, run: AgentPlanRun) -> str | None:
        if run.error_message:
            return run.error_message
        response = self._parse_json_object(run.response_json)
        for path in [
            ("reason",),
            ("result", "reason"),
            ("policy", "reason"),
            ("result", "policy", "reason"),
        ]:
            value = self._nested(response, path)
            if value:
                return str(value)
        return None

    def _run_title(self, run: AgentPlanRun, plan: AgentPlan | None) -> str:
        if run.result_type == "prefill_payload" and run.status == "completed":
            return "Manual ticket prefill ready"
        if run.status == "completed":
            return "Safe action completed"
        if run.status == "blocked":
            return "Agent action blocked"
        if run.status == "failed":
            return "Agent action failed"
        return plan.plan_title if plan else run.command_type

    def _run_summary(self, run: AgentPlanRun, plan: AgentPlan | None) -> str:
        response = self._parse_json_object(run.response_json)
        for path in [("message",), ("result", "message"), ("prefill", "source_context")]:
            value = self._nested(response, path)
            if value:
                return str(value)
        if plan is not None:
            return plan.user_visible_summary or plan.plan_summary
        return f"{run.command_type} run status={run.status}"

    def _message_title(self, message: AgentChatMessage) -> str:
        if message.message_type == "manual_prefill_result":
            return "Manual ticket prefill result"
        if message.message_type == "safe_run_result":
            return "Safe run result"
        if message.message_type == "auth_required":
            return "Authorization required"
        if message.message_type == "blocked":
            return "Blocked chat result"
        if message.message_type == "error":
            return "Agent chat error"
        return "Agent chat review item"

    def _find_item(self, db: Session, queue_key: str) -> dict[str, Any]:
        for item in self._build_items(db, conversation_key=None):
            if item["queue_key"] == queue_key:
                return item
        existing = (
            db.query(AgentReviewQueueState)
            .filter(AgentReviewQueueState.queue_key == queue_key)
            .first()
        )
        if existing is not None:
            return {
                "queue_id": queue_key,
                "queue_key": queue_key,
                "item_type": existing.item_type,
                "queue_type": "all",
                "priority": "low",
                "review_status": existing.status,
                "reviewer_note": existing.reviewer_note,
                "conversation_key": None,
                "command_log_id": None,
                "plan_id": None,
                "plan_run_id": None,
                "auth_approval_request_id": None,
                "command_type": None,
                "domain": None,
                "market": None,
                "provider": None,
                "symbol": None,
                "side": None,
                "risk_level": None,
                "status": None,
                "title": "Archived review item",
                "summary": "The original review source is no longer in the open queue.",
                "blocked_reason": None,
                "safety_badges": ["NO_AUTO_SUBMIT"],
                "can_run_safe_action": False,
                "can_prepare_ticket": False,
                "created_at": existing.created_at,
                "updated_at": existing.updated_at,
                "metadata": {},
            }
        raise AgentReviewQueueItemNotFound(queue_key)

    def _upsert_state(
        self,
        db: Session,
        *,
        item: dict[str, Any],
        status: str,
        reviewer_note: str | None,
    ) -> AgentReviewQueueState:
        now = datetime.now(UTC)
        state = (
            db.query(AgentReviewQueueState)
            .filter(AgentReviewQueueState.queue_key == item["queue_key"])
            .first()
        )
        if state is None:
            state = AgentReviewQueueState(
                queue_key=item["queue_key"],
                item_type=item["item_type"],
                source_id=self._source_id(item),
                status="open",
                created_at=now,
            )
            db.add(state)
        state.status = status
        state.reviewer_note = self._sanitize_text(reviewer_note or "", max_length=500) or None
        state.reviewed_at = now if status == "reviewed" else state.reviewed_at
        state.dismissed_at = now if status == "dismissed" else state.dismissed_at
        state.updated_at = now
        db.commit()
        db.refresh(state)
        return state

    def _state_map(
        self,
        db: Session,
        queue_keys: list[str],
    ) -> dict[str, AgentReviewQueueState]:
        if not queue_keys:
            return {}
        rows = (
            db.query(AgentReviewQueueState)
            .filter(AgentReviewQueueState.queue_key.in_(queue_keys))
            .all()
        )
        return {row.queue_key: row for row in rows}

    def _apply_state(
        self,
        item: dict[str, Any],
        state: AgentReviewQueueState | None,
    ) -> dict[str, Any]:
        if state is None:
            return item
        updated = dict(item)
        updated["review_status"] = state.status
        updated["reviewer_note"] = state.reviewer_note
        return updated

    def _serialize_state(self, state: AgentReviewQueueState) -> dict[str, Any]:
        return {
            "queue_key": state.queue_key,
            "item_type": state.item_type,
            "source_id": state.source_id,
            "status": state.status,
            "reviewed_at": state.reviewed_at,
            "dismissed_at": state.dismissed_at,
            "reviewer_note": state.reviewer_note,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
        }

    def _source_id(self, item: dict[str, Any]) -> int | None:
        for key in ["plan_run_id", "auth_approval_request_id", "plan_id"]:
            value = item.get(key)
            if isinstance(value, int):
                return value
        return None

    def _sort_key(self, item: dict[str, Any]) -> tuple[int, float]:
        priority = {"high": 3, "medium": 2, "low": 1}.get(item["priority"], 0)
        dt = item.get("updated_at") or item.get("created_at")
        timestamp = dt.timestamp() if isinstance(dt, datetime) else 0.0
        return priority, timestamp

    def _state_request(
        self,
        request: AgentReviewQueueStateRequest | dict[str, Any] | None,
    ) -> AgentReviewQueueStateRequest:
        if request is None:
            return AgentReviewQueueStateRequest()
        if isinstance(request, AgentReviewQueueStateRequest):
            return request
        return AgentReviewQueueStateRequest.model_validate(request)

    def _sanitize_metadata(self, value: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, raw in value.items():
            if key not in self.safe_metadata_keys or raw is None:
                continue
            result[key] = self._sanitize_metadata_value(raw)
        return result

    def _sanitize_metadata_value(self, value: Any) -> Any:
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            return self._sanitize_text(value, max_length=300)
        if isinstance(value, dict):
            return {
                str(key)[:80]: self._sanitize_metadata_value(raw)
                for key, raw in value.items()
                if str(key) in self.safe_metadata_keys
            }
        if isinstance(value, list):
            return [self._sanitize_metadata_value(item) for item in value[:20]]
        return self._sanitize_text(str(value), max_length=300)

    def _sanitize_text(self, value: str, *, max_length: int) -> str:
        text = str(value or "")
        text = self.sensitive_key_pattern.sub("[REDACTED]", text)
        text = self.bearer_pattern.sub("Bearer [REDACTED]", text)
        text = self.account_number_pattern.sub("[REDACTED_NUMBER]", text)
        return text[:max_length]

    def _parse_json_object(self, raw_value: str | None) -> dict[str, Any]:
        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
        return {}

    def _nested(self, payload: dict[str, Any], path: tuple[str, ...]) -> Any:
        value: Any = payload
        for key in path:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return value

    def _safety(self) -> dict[str, bool]:
        return {
            "read_only": True,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "validation_called": False,
            "setting_changed": False,
            "scheduler_changed": False,
        }
