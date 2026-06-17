from __future__ import annotations

from app.db.models import AgentPlan, AgentPlanRun, OrderLog
from app.schemas.agent_command import SCHEMA_VERSION
from app.services.agent_execution_gateway import AgentExecutionGateway
from app.services.agent_plan_service import AgentPlanService


def _create_plan(db_session, payload, *, conversation_id="gateway-test"):
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


def test_show_positions_plan_run_completes_and_logs_no_submit(db_session):
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="buy",
            order_type="market",
            internal_status="DRY_RUN_SIMULATED",
            qty=1,
            request_payload="{}",
            response_payload="{}",
        )
    )
    db_session.commit()
    plan = _create_plan(
        db_session,
        {
            "command_type": "SHOW_POSITIONS",
            "domain": "position",
            "intent": "show_positions",
        },
    )

    response = AgentExecutionGateway().run_plan(db_session, plan_id=plan["id"])

    assert response["status"] == "executed_safe_action"
    assert response["result"]["result_type"] == "read_only_result"
    assert response["result"]["source"] == "local_logs_only"
    assert response["safety"]["safe_execution_only"] is True
    assert response["safety"]["real_order_submitted"] is False
    assert response["safety"]["broker_submit_called"] is False
    assert response["safety"]["manual_submit_called"] is False
    assert db_session.query(AgentPlanRun).count() == 1
    run = db_session.query(AgentPlanRun).one()
    assert run.status == "completed"
    assert run.result_type == "read_only_result"


def test_watchlist_preview_plan_run_returns_safe_preview(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "RUN_WATCHLIST_PREVIEW",
            "domain": "watchlist",
            "intent": "watchlist_preview",
        },
    )

    response = AgentExecutionGateway().run_plan(db_session, plan_id=plan["id"])

    assert response["status"] == "executed_safe_action"
    assert response["result"]["result_type"] == "watchlist_preview_result"
    assert response["result"]["preview_only"] is True
    assert response["safety"]["real_order_submitted"] is False
    assert response["safety"]["broker_api_called"] is False


def test_single_symbol_analysis_plan_run_is_analysis_only(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "RUN_SINGLE_SYMBOL_ANALYSIS",
            "domain": "analysis",
            "intent": "single_symbol_analysis",
            "symbol": "005930",
        },
    )

    response = AgentExecutionGateway().run_plan(db_session, plan_id=plan["id"])

    assert response["status"] == "executed_safe_action"
    assert response["result"]["result_type"] == "analysis_result"
    assert response["result"]["analysis_only"] is True
    assert response["result"]["symbol"] == "005930"
    assert response["safety"]["validation_called"] is False


def test_exit_preflight_plan_run_is_preflight_only(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "RUN_EXIT_PREFLIGHT",
            "domain": "exit",
            "intent": "exit_preflight",
        },
    )

    response = AgentExecutionGateway().run_plan(db_session, plan_id=plan["id"])

    assert response["status"] == "executed_safe_action"
    assert response["result"]["result_type"] == "exit_preflight_result"
    assert response["result"]["preflight_only"] is True
    assert response["safety"]["manual_submit_called"] is False


def test_manual_sell_ticket_plan_returns_prefill_only_payload(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "PREPARE_MANUAL_SELL_TICKET",
            "domain": "order",
            "intent": "prepare_manual_sell_ticket",
            "symbol": "005930",
            "side": "sell",
            "quantity": 2,
        },
    )

    response = AgentExecutionGateway().run_plan(db_session, plan_id=plan["id"])

    assert response["status"] == "executed_safe_action"
    assert response["result"]["result_type"] == "prefill_payload"
    assert response["result"]["prefill_only"] is True
    assert response["result"]["submit_blocked_in_pr58"] is True
    assert response["safety"]["validation_called"] is False
    assert response["safety"]["manual_submit_called"] is False


def test_live_order_plan_run_is_blocked_and_logged(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "REQUEST_LIVE_ORDER_SUBMIT",
            "domain": "order",
            "intent": "submit_live_order",
            "symbol": "005930",
            "side": "buy",
            "quantity": 1,
        },
    )

    response = AgentExecutionGateway().run_plan(db_session, plan_id=plan["id"])

    assert response["status"] == "blocked"
    assert response["result"]["reason"] == "live_order_execution_blocked_in_pr58"
    assert response["result"]["result_type"] == "blocked_live_action"
    assert response["safety"]["real_order_submitted"] is False
    run = db_session.query(AgentPlanRun).one()
    assert run.status == "blocked"
    assert run.execution_mode == "blocked_live_execution"


def test_dangerous_setting_plan_run_is_blocked(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "SET_DRY_RUN",
            "domain": "settings",
            "intent": "set_dry_run",
            "settings_change": {"key": "dry_run", "value": False},
        },
    )

    response = AgentExecutionGateway().run_plan(db_session, plan_id=plan["id"])

    assert response["status"] == "blocked"
    assert response["result"]["reason"] == "setting_change_blocked_in_pr58"
    assert response["result"]["result_type"] == "blocked_setting_change"
    assert response["safety"]["setting_changed"] is False


def test_safety_increasing_setting_still_does_not_mutate_in_pr58(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "SET_KILL_SWITCH",
            "domain": "safety",
            "intent": "set_kill_switch",
            "settings_change": {"key": "kill_switch", "value": True},
        },
    )

    response = AgentExecutionGateway().run_plan(db_session, plan_id=plan["id"])

    assert response["status"] == "blocked"
    assert response["result"]["reason"] == "setting_change_blocked_in_pr58"
    assert response["safety"]["setting_changed"] is False


def test_cancelled_plan_cannot_run(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "SHOW_SETTINGS",
            "domain": "settings",
            "intent": "show_settings",
        },
    )
    AgentPlanService().cancel_plan(db_session, plan_id=plan["id"], reason="test")

    response = AgentExecutionGateway().run_plan(db_session, plan_id=plan["id"])

    assert response["status"] == "blocked"
    assert response["result"]["reason"] == "plan_cancelled"


def test_scope_hash_mismatch_blocks_run(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "SHOW_SETTINGS",
            "domain": "settings",
            "intent": "show_settings",
        },
    )
    row = db_session.get(AgentPlan, plan["id"])
    row.scope_hash = "0" * 64
    db_session.commit()

    response = AgentExecutionGateway().run_plan(db_session, plan_id=plan["id"])

    assert response["status"] == "blocked"
    assert response["result"]["reason"] == "scope_hash_mismatch"


def test_forbidden_methods_are_not_called_for_blocked_live_plan(db_session, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("forbidden execution path called")

    monkeypatch.setattr("app.services.kis_manual_order_service.KisManualOrderService.submit_manual", fail)
    monkeypatch.setattr("app.brokers.kis_client.KisClient.submit_order", fail)
    monkeypatch.setattr("app.services.runtime_setting_service.RuntimeSettingService.update_settings", fail)
    plan = _create_plan(
        db_session,
        {
            "command_type": "REQUEST_LIVE_ORDER_SUBMIT",
            "domain": "order",
            "intent": "submit_live_order",
            "symbol": "005930",
            "side": "buy",
            "quantity": 1,
        },
    )

    response = AgentExecutionGateway().run_plan(db_session, plan_id=plan["id"])

    assert response["status"] == "blocked"
    assert response["safety"]["real_order_submitted"] is False

