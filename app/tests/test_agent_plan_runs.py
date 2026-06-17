from __future__ import annotations

from app.schemas.agent_command import SCHEMA_VERSION
from app.services.agent_execution_gateway import AgentExecutionGateway
from app.services.agent_plan_service import AgentPlanService


def _create_plan(db_session, payload, *, conversation_id="runs-test"):
    return AgentPlanService().create_from_command(
        db_session,
        command={
            "schema_version": SCHEMA_VERSION,
            "market": "KR",
            "provider": "kis",
            **payload,
        },
        conversation_id=conversation_id,
    )["plan"]


def test_plan_run_recent_and_detail_payloads_include_safety(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "SHOW_SETTINGS",
            "domain": "settings",
            "intent": "show_settings",
        },
        conversation_id="runs-conv",
    )
    gateway = AgentExecutionGateway()
    executed = gateway.run_plan(db_session, plan_id=plan["id"])

    by_plan = gateway.list_runs_for_plan(db_session, plan_id=plan["id"])
    recent = gateway.recent_runs(db_session, conversation_id="runs-conv")
    detail = gateway.get_run(db_session, plan_run_id=executed["plan_run_id"])

    assert by_plan["count"] == 1
    assert by_plan["runs"][0]["status"] == "completed"
    assert by_plan["safety"]["real_order_submitted"] is False
    assert recent["count"] == 1
    assert recent["runs"][0]["plan_run_id"] == executed["plan_run_id"]
    assert detail["run"]["result_type"] == "read_only_result"
    assert detail["run"]["safety"]["setting_changed"] is False
    assert detail["safety"]["broker_api_called"] is False

