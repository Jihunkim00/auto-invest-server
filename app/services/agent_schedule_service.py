from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import AgentPlan, AgentScheduleJob
from app.schemas.agent_execution import AgentExecutionSafetyFlags, AgentPlanScheduleRequest
from app.services.agent_execution_gateway import AgentExecutionGateway
from app.services.agent_execution_policy_service import AgentExecutionPolicyService
from app.services.agent_plan_run_service import AgentPlanRunService
from app.services.agent_plan_service import AgentPlanNotFound


class AgentScheduleJobNotFound(Exception):
    pass


class AgentScheduleService:
    def __init__(
        self,
        *,
        policy_service: AgentExecutionPolicyService | None = None,
        run_service: AgentPlanRunService | None = None,
        gateway: AgentExecutionGateway | None = None,
    ) -> None:
        self.policy_service = policy_service or AgentExecutionPolicyService()
        self.run_service = run_service or AgentPlanRunService()
        self.gateway = gateway or AgentExecutionGateway(policy_service=self.policy_service, run_service=self.run_service)

    def create_schedule(
        self,
        db: Session,
        *,
        plan_id: int,
        request: AgentPlanScheduleRequest | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan = db.get(AgentPlan, plan_id)
        if plan is None:
            raise AgentPlanNotFound(plan_id)
        request_payload = self._request_payload(request)
        safety = AgentExecutionSafetyFlags()
        policy = self.policy_service.evaluate_schedule(plan)
        if not policy.allowed:
            result = {
                "blocked": True,
                "reason": policy.reason,
                "command_type": plan.command_type,
                "policy": policy.as_dict(),
            }
            run = self.run_service.record_run(
                db,
                plan=plan,
                policy=policy,
                request=request_payload,
                response=result,
                status="blocked",
                safety=safety,
            )
            return {
                "status": "blocked",
                "plan_id": plan.id,
                "plan_run_id": run.id,
                "reason": policy.reason,
                "result": result,
                "safety": safety.model_dump(mode="json"),
            }

        schedule = self._schedule_payload(plan, request_payload)
        run_at = self._parse_datetime(schedule.get("run_at"))
        next_run_at = run_at or datetime.now(UTC)
        schedule_type = str(schedule.get("type") or "once").strip().lower() or "once"
        job = AgentScheduleJob(
            schedule_key=f"agent_sched_{uuid4().hex}",
            plan_id=plan.id,
            command_log_id=plan.command_log_id,
            conversation_id=plan.conversation_id,
            command_type=plan.command_type,
            domain=plan.domain,
            status="active",
            schedule_type=schedule_type,
            run_at=run_at,
            timezone=str(schedule.get("timezone") or "UTC"),
            recurrence_rule=self._optional_text(schedule.get("recurrence") or schedule.get("recurrence_rule")),
            next_run_at=next_run_at,
            max_runs=self._optional_int(schedule.get("max_runs") or schedule.get("max_executions")),
            run_count=0,
            scope_hash=plan.scope_hash,
            schedule_json=self._json(schedule),
            safety_json=AgentExecutionSafetyFlags(agent_schedule_created=True).model_dump_json(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return {
            "status": "schedule_created",
            "schedule": self.serialize_job(job),
            "safety": AgentExecutionSafetyFlags(agent_schedule_created=True).model_dump(mode="json"),
        }

    def list_schedules(
        self,
        db: Session,
        *,
        status: str | None = None,
        conversation_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        query = db.query(AgentScheduleJob)
        if status:
            query = query.filter(AgentScheduleJob.status == status)
        if conversation_id:
            query = query.filter(AgentScheduleJob.conversation_id == conversation_id)
        rows = query.order_by(AgentScheduleJob.created_at.desc(), AgentScheduleJob.id.desc()).limit(limit).all()
        return {
            "count": len(rows),
            "schedules": [self.serialize_job(row) for row in rows],
            "safety": AgentExecutionSafetyFlags().model_dump(mode="json"),
        }

    def get_schedule(self, db: Session, *, schedule_id: int) -> dict[str, Any]:
        job = db.get(AgentScheduleJob, schedule_id)
        if job is None:
            raise AgentScheduleJobNotFound(schedule_id)
        return {
            "schedule": self.serialize_job(job),
            "safety": AgentExecutionSafetyFlags().model_dump(mode="json"),
        }

    def cancel_schedule(self, db: Session, *, schedule_id: int, reason: str | None = None) -> dict[str, Any]:
        del reason
        job = db.get(AgentScheduleJob, schedule_id)
        if job is None:
            raise AgentScheduleJobNotFound(schedule_id)
        if job.status == "active":
            now = datetime.now(UTC)
            job.status = "cancelled"
            job.cancelled_at = now
            job.updated_at = now
            db.commit()
            db.refresh(job)
        return {
            "status": "schedule_cancelled",
            "schedule": self.serialize_job(job),
            "safety": AgentExecutionSafetyFlags().model_dump(mode="json"),
        }

    def run_due_once(self, db: Session, *, now: datetime | None = None, limit: int = 20) -> dict[str, Any]:
        now_utc = self._coerce_datetime(now) or datetime.now(UTC)
        due_rows = (
            db.query(AgentScheduleJob)
            .filter(AgentScheduleJob.status == "active")
            .filter(AgentScheduleJob.next_run_at <= now_utc)
            .order_by(AgentScheduleJob.next_run_at.asc(), AgentScheduleJob.id.asc())
            .limit(limit)
            .all()
        )
        results: list[dict[str, Any]] = []
        for job in due_rows:
            if job.scope_hash != self._plan_scope_hash(db, job.plan_id):
                results.append(
                    {
                        "schedule_id": job.id,
                        "status": "blocked",
                        "reason": "scope_hash_mismatch",
                    }
                )
                continue

            run_result = self.gateway.run_plan(
                db,
                plan_id=job.plan_id,
                request={
                    "dry_run": True,
                    "operator_note": "agent schedule due run",
                    "trigger_source": "agent_schedule_due_once",
                },
            )
            job.run_count = int(job.run_count or 0) + 1
            job.last_run_at = now_utc
            if self._should_complete(job):
                job.status = "completed"
                job.next_run_at = None
            else:
                job.next_run_at = self._next_run(job, now_utc)
            job.updated_at = now_utc
            db.commit()
            db.refresh(job)
            results.append(
                {
                    "schedule_id": job.id,
                    "schedule_key": job.schedule_key,
                    "status": run_result["status"],
                    "plan_run_id": run_result["plan_run_id"],
                    "command_type": job.command_type,
                    "safety": run_result["safety"],
                }
            )
        return {
            "status": "run_due_once_completed",
            "count": len(results),
            "results": results,
            "safety": AgentExecutionSafetyFlags().model_dump(mode="json"),
        }

    def serialize_job(self, job: AgentScheduleJob) -> dict[str, Any]:
        return {
            "id": job.id,
            "schedule_key": job.schedule_key,
            "plan_id": job.plan_id,
            "command_log_id": job.command_log_id,
            "conversation_id": job.conversation_id,
            "command_type": job.command_type,
            "domain": job.domain,
            "status": job.status,
            "schedule_type": job.schedule_type,
            "run_at": job.run_at,
            "timezone": job.timezone,
            "recurrence_rule": job.recurrence_rule,
            "next_run_at": job.next_run_at,
            "last_run_at": job.last_run_at,
            "max_runs": job.max_runs,
            "run_count": job.run_count,
            "scope_hash": job.scope_hash,
            "schedule": self._parse_json_object(job.schedule_json),
            "safety": self._parse_json_object(job.safety_json),
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "cancelled_at": job.cancelled_at,
        }

    def _request_payload(self, request: AgentPlanScheduleRequest | dict[str, Any] | None) -> dict[str, Any]:
        if request is None:
            return AgentPlanScheduleRequest().model_dump(mode="json")
        if isinstance(request, AgentPlanScheduleRequest):
            return request.model_dump(mode="json")
        return AgentPlanScheduleRequest.model_validate(request).model_dump(mode="json")

    def _schedule_payload(self, plan: AgentPlan, request: dict[str, Any]) -> dict[str, Any]:
        override = request.get("schedule")
        if isinstance(override, dict) and override:
            return dict(override)
        command = self._parse_json_object(plan.command_json)
        schedule = command.get("schedule")
        if isinstance(schedule, dict) and schedule:
            return dict(schedule)
        scope = self._parse_json_object(plan.scope_json)
        schedule = scope.get("schedule")
        if isinstance(schedule, dict) and schedule:
            return dict(schedule)
        return {"type": "once", "run_at": datetime.now(UTC).isoformat(), "timezone": "UTC"}

    def _plan_scope_hash(self, db: Session, plan_id: int) -> str | None:
        plan = db.get(AgentPlan, plan_id)
        return plan.scope_hash if plan is not None else None

    def _should_complete(self, job: AgentScheduleJob) -> bool:
        max_runs = job.max_runs
        if max_runs is not None and int(job.run_count or 0) >= max_runs:
            return True
        return str(job.schedule_type or "").lower() == "once"

    def _next_run(self, job: AgentScheduleJob, now: datetime) -> datetime | None:
        del now
        return None if str(job.schedule_type or "").lower() == "once" else job.next_run_at

    def _parse_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return self._coerce_datetime(value)
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return self._coerce_datetime(parsed)

    def _coerce_datetime(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _optional_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _optional_text(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

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

