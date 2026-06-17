from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AgentPlan, AgentPlanRun
from app.schemas.agent_execution import AgentExecutionSafetyFlags
from app.services.agent_execution_policy_service import AgentExecutionPolicyDecision


class AgentPlanRunService:
    def record_run(
        self,
        db: Session,
        *,
        plan: AgentPlan,
        policy: AgentExecutionPolicyDecision,
        request: dict[str, Any],
        response: dict[str, Any],
        status: str,
        safety: AgentExecutionSafetyFlags | None = None,
        error_message: str | None = None,
    ) -> AgentPlanRun:
        now = datetime.now(UTC)
        safety_payload = (safety or AgentExecutionSafetyFlags()).model_dump(mode="json")
        row = AgentPlanRun(
            plan_id=plan.id,
            plan_key=plan.plan_key,
            command_log_id=plan.command_log_id,
            conversation_id=plan.conversation_id,
            command_type=plan.command_type,
            domain=plan.domain,
            status=status,
            result_type=policy.result_type,
            started_at=now,
            completed_at=now if status == "completed" else None,
            failed_at=now if status == "failed" else None,
            error_message=error_message,
            request_json=self._json(request),
            response_json=self._json(response),
            safety_json=self._json(safety_payload),
            scope_hash=plan.scope_hash,
            execution_mode=policy.execution_mode,
            trigger_source=str(request.get("trigger_source") or "manual_agent_plan_run"),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def list_runs_for_plan(
        self,
        db: Session,
        *,
        plan_id: int,
        limit: int = 50,
    ) -> dict[str, Any]:
        rows = (
            db.query(AgentPlanRun)
            .filter(AgentPlanRun.plan_id == plan_id)
            .order_by(AgentPlanRun.created_at.desc(), AgentPlanRun.id.desc())
            .limit(limit)
            .all()
        )
        return {
            "count": len(rows),
            "runs": [self.serialize_run(row) for row in rows],
            "safety": AgentExecutionSafetyFlags().model_dump(mode="json"),
        }

    def recent_runs(
        self,
        db: Session,
        *,
        limit: int = 50,
        status: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        query = db.query(AgentPlanRun)
        if status:
            query = query.filter(AgentPlanRun.status == status)
        if conversation_id:
            query = query.filter(AgentPlanRun.conversation_id == conversation_id)
        rows = query.order_by(AgentPlanRun.created_at.desc(), AgentPlanRun.id.desc()).limit(limit).all()
        return {
            "count": len(rows),
            "runs": [self.serialize_run(row) for row in rows],
            "safety": AgentExecutionSafetyFlags().model_dump(mode="json"),
        }

    def get_run(self, db: Session, *, plan_run_id: int) -> AgentPlanRun | None:
        return db.get(AgentPlanRun, plan_run_id)

    def serialize_run(self, row: AgentPlanRun) -> dict[str, Any]:
        return {
            "id": row.id,
            "plan_run_id": row.id,
            "plan_id": row.plan_id,
            "plan_key": row.plan_key,
            "command_log_id": row.command_log_id,
            "conversation_id": row.conversation_id,
            "command_type": row.command_type,
            "domain": row.domain,
            "status": row.status,
            "result_type": row.result_type,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "failed_at": row.failed_at,
            "error_message": row.error_message,
            "request": self._parse_json_object(row.request_json),
            "response": self._parse_json_object(row.response_json),
            "safety": self._parse_json_object(row.safety_json),
            "scope_hash": row.scope_hash,
            "execution_mode": row.execution_mode,
            "trigger_source": row.trigger_source,
            "created_at": row.created_at,
        }

    def _json(self, payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, default=str)

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

