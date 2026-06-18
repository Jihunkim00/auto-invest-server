from __future__ import annotations

import json
from datetime import UTC, datetime

from app.db.models import AgentCommandLog, AgentPlan, AgentPlanRun
from app.schemas.agent_command import SCHEMA_VERSION
from app.services.agent_chat_service import AgentChatService
from app.services.agent_command_validator import AgentCommandValidator
from app.services.agent_execution_gateway import AgentExecutionGateway
from app.services.agent_live_prefill_service import AgentLivePrefillService
from app.services.agent_operations_service import AgentOperationsService
from app.services.agent_plan_service import AgentPlanService


def test_summary_counts_plans_auth_blocked_prefill_and_safe_runs(db_session):
    chat = AgentChatService().create_conversation(db_session)["conversation"]
    safe_plan = _create_plan(
        db_session,
        {"command_type": "SHOW_POSITIONS", "domain": "position", "intent": "show_positions"},
        conversation_id=chat["conversation_key"],
    )
    auth_plan = _create_plan(
        db_session,
        {
            "command_type": "CREATE_AGENT_PLAN",
            "domain": "agent",
            "intent": "conditional_buy_schedule",
            "symbol": "005930",
            "side": "buy",
            "budget": {"amount": 30000, "currency": "KRW", "mode": "max_notional"},
            "schedule": {
                "type": "once",
                "run_at": "2026-06-18T10:00:00+09:00",
                "timezone": "Asia/Seoul",
            },
        },
        conversation_id=chat["conversation_key"],
    )
    manual_plan = _create_plan(
        db_session,
        {
            "command_type": "PREPARE_MANUAL_BUY_TICKET",
            "domain": "order",
            "intent": "prepare_manual_buy_ticket",
            "symbol": "005930",
            "side": "buy",
            "quantity": 2,
        },
        conversation_id=chat["conversation_key"],
    )

    AgentExecutionGateway().run_plan(db_session, plan_id=safe_plan["id"])
    AgentExecutionGateway().run_plan(db_session, plan_id=auth_plan["id"])
    AgentLivePrefillService().prepare_manual_ticket(db_session, plan_id=manual_plan["id"])

    summary = AgentOperationsService().summary(db_session)

    assert summary["summary"]["total_plans"] == 3
    assert summary["summary"]["ready_for_review_count"] >= 2
    assert summary["summary"]["pending_auth_count"] == 1
    assert summary["summary"]["blocked_count"] >= 1
    assert summary["summary"]["prefill_ready_count"] == 1
    assert summary["summary"]["safe_run_completed_count"] == 1
    assert summary["summary"]["active_conversation_count"] == 1
    assert summary["summary"]["latest_conversation_key"] == chat["conversation_key"]
    assert summary["safety"] == {
        "read_only": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "validation_called": False,
        "setting_changed": False,
        "scheduler_changed": False,
    }


def test_review_queue_filters_auth_blocked_prefill_and_manual_candidates(db_session):
    chat = AgentChatService().create_conversation(db_session)["conversation"]
    auth_plan = _create_plan(
        db_session,
        {
            "command_type": "CREATE_AGENT_PLAN",
            "domain": "agent",
            "intent": "conditional_buy_schedule",
            "symbol": "005930",
            "side": "buy",
            "budget": {"amount": 30000, "currency": "KRW", "mode": "max_notional"},
            "schedule": {
                "type": "once",
                "run_at": "2026-06-18T10:00:00+09:00",
                "timezone": "Asia/Seoul",
            },
        },
        conversation_id=chat["conversation_key"],
    )
    manual_plan = _create_plan(
        db_session,
        {
            "command_type": "PREPARE_MANUAL_BUY_TICKET",
            "domain": "order",
            "intent": "prepare_manual_buy_ticket",
            "symbol": "005930",
            "side": "buy",
            "quantity": 2,
        },
        conversation_id=chat["conversation_key"],
    )
    AgentExecutionGateway().run_plan(db_session, plan_id=auth_plan["id"])
    AgentLivePrefillService().prepare_manual_ticket(db_session, plan_id=manual_plan["id"])

    service = AgentOperationsService()

    auth_items = service.review_queue(db_session, queue_type="auth_required")["items"]
    blocked_items = service.review_queue(db_session, queue_type="blocked")["items"]
    prefill_items = service.review_queue(db_session, queue_type="prefill_ready")["items"]
    candidates = service.review_queue(
        db_session,
        queue_type="manual_ticket_candidates",
        conversation_key=chat["conversation_key"],
    )["items"]

    assert any(item["plan_id"] == auth_plan["id"] for item in auth_items)
    assert any(item["blocked_reason"] for item in blocked_items)
    assert any(item["plan_id"] == manual_plan["id"] for item in prefill_items)
    assert any(item["can_prepare_ticket"] for item in candidates)
    assert all(item["conversation_key"] == chat["conversation_key"] for item in candidates)
    assert all("NO_AUTO_SUBMIT" in item["safety_badges"] for item in auth_items + blocked_items + prefill_items)


def test_review_queue_reviewed_and_dismiss_state_persists(db_session):
    plan = _create_plan(
        db_session,
        {"command_type": "SHOW_POSITIONS", "domain": "position", "intent": "show_positions"},
    )
    service = AgentOperationsService()
    key = f"plan_{plan['id']}"

    reviewed = service.mark_reviewed(
        db_session,
        queue_key=key,
        request={"reviewer_note": "checked"},
    )

    assert reviewed["state"]["status"] == "reviewed"
    assert reviewed["state"]["reviewer_note"] == "checked"
    assert all(item["queue_key"] != key for item in service.review_queue(db_session)["items"])
    assert any(
        item["queue_key"] == key
        for item in service.review_queue(db_session, status="reviewed")["items"]
    )

    dismissed = service.dismiss(db_session, queue_key=key, request={"reviewer_note": "skip"})

    assert dismissed["state"]["status"] == "dismissed"
    assert any(
        item["queue_key"] == key
        for item in service.review_queue(db_session, status="dismissed")["items"]
    )


def test_review_queue_sanitizes_secret_text_and_metadata(db_session):
    plan = _create_plan(
        db_session,
        {"command_type": "SHOW_POSITIONS", "domain": "position", "intent": "show_positions"},
    )
    row = db_session.get(AgentPlan, plan["id"])
    row.plan_title = "OPENAI_API_KEY=sk-secret account 123456789"
    row.user_visible_summary = "authorization: Bearer abc.def password=hunter2"
    row.safety_json = json.dumps(
        {"OPENAI_API_KEY": "sk-secret", "blocked_reason": "appsecret=secret"},
        ensure_ascii=False,
    )
    db_session.commit()

    item = AgentOperationsService().review_queue(db_session)["items"][0]

    assert "sk-secret" not in item["title"]
    assert "123456789" not in item["title"]
    assert "abc.def" not in item["summary"]
    assert "hunter2" not in item["summary"]
    assert "OPENAI_API_KEY" not in item["metadata"]
    assert "appsecret" not in json.dumps(item, default=str)


def test_summary_counts_failed_runs_without_mutating_plan(db_session):
    plan = _create_plan(
        db_session,
        {"command_type": "SHOW_POSITIONS", "domain": "position", "intent": "show_positions"},
    )
    row = db_session.get(AgentPlan, plan["id"])
    db_session.add(
        AgentPlanRun(
            plan_id=row.id,
            plan_key=row.plan_key,
            command_log_id=row.command_log_id,
            conversation_id=row.conversation_id,
            command_type=row.command_type,
            domain=row.domain,
            status="failed",
            result_type="error",
            started_at=datetime.now(UTC),
            failed_at=datetime.now(UTC),
            error_message="agent_safe_execution_error",
            request_json="{}",
            response_json=json.dumps({"reason": "agent_safe_execution_error"}),
            safety_json="{}",
            scope_hash=row.scope_hash,
            execution_mode="agent_safe_execution",
            trigger_source="test",
        )
    )
    db_session.commit()

    summary = AgentOperationsService().summary(db_session)["summary"]
    queue = AgentOperationsService().review_queue(db_session, queue_type="failed")["items"]

    assert summary["failed_count"] == 1
    assert queue[0]["priority"] == "high"
    assert queue[0]["can_run_safe_action"] is False
    assert queue[0]["can_prepare_ticket"] is False
    assert db_session.get(AgentPlan, plan["id"]).status == "ready_for_review"


def _create_plan(db_session, payload, *, conversation_id="conv-pr62"):
    command = AgentCommandValidator().validate_and_normalize(
        {
            "schema_version": SCHEMA_VERSION,
            "market": "KR",
            "provider": "kis",
            **payload,
        }
    )
    row = AgentCommandLog(
        conversation_id=conversation_id,
        user_message=payload.get("intent", "test command"),
        parser_status="test",
        command_type=_value(command.command_type),
        domain=_value(command.domain),
        market=_value(command.market),
        provider=_value(command.provider),
        symbol=command.symbol,
        side=_value(command.side),
        risk_level=_value(command.risk_level),
        requires_auth=command.requires_auth,
        needs_clarification=command.needs_clarification,
        parsed_command_json=json.dumps(command.model_dump(mode="json"), ensure_ascii=False),
        safety_json=command.safety.model_dump_json(),
        model_name=None,
        schema_version=command.schema_version,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return AgentPlanService().create_from_command_log(
        db_session,
        command_log_id=row.id,
    )["plan"]


def _value(value):
    return value.value if hasattr(value, "value") else value
