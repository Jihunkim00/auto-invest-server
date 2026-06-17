from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import AgentPlan, AgentPlanRun, AuthApprovalRequest
from app.schemas.agent_command import SCHEMA_VERSION
from app.services.agent_live_prefill_service import AgentLivePrefillService
from app.services.agent_plan_service import AgentPlanService


def _create_plan(db_session, payload, *, conversation_id="prefill-service"):
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


def _latest_auth(db_session, plan_id: int) -> AuthApprovalRequest:
    row = (
        db_session.query(AuthApprovalRequest)
        .filter(AuthApprovalRequest.plan_id == plan_id)
        .order_by(AuthApprovalRequest.created_at.desc(), AuthApprovalRequest.id.desc())
        .one()
    )
    return row


def _approve_latest_auth(db_session, plan_id: int) -> AuthApprovalRequest:
    row = _latest_auth(db_session, plan_id)
    now = datetime.now(UTC)
    row.status = "approved"
    row.approved_at = now
    row.updated_at = now
    plan = db_session.get(AgentPlan, plan_id)
    plan.approved_auth_request_id = row.id
    db_session.commit()
    db_session.refresh(row)
    return row


def test_manual_buy_prefill_payload_logs_completed_run_without_live_flags(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "PREPARE_MANUAL_BUY_TICKET",
            "domain": "order",
            "intent": "prepare_buy_ticket",
            "symbol": "005930",
            "side": "buy",
            "budget": {"amount": 30000, "currency": "KRW", "mode": "max_notional"},
        },
    )

    response = AgentLivePrefillService().prepare_manual_ticket(db_session, plan_id=plan["id"])

    assert response["status"] == "manual_ticket_prefill_ready"
    assert response["result"]["result_type"] == "prefill_payload"
    assert response["prefill"]["provider"] == "kis"
    assert response["prefill"]["market"] == "KR"
    assert response["prefill"]["symbol"] == "005930"
    assert response["prefill"]["side"] == "buy"
    assert response["prefill"]["notional"] == 30000
    assert response["prefill"]["dry_run"] is True
    assert response["prefill"]["confirm_live"] is False
    assert response["prefill"]["source_metadata"]["agent_plan_id"] == plan["id"]
    assert response["safety"]["prefill_only"] is True
    assert response["safety"]["real_order_submitted"] is False
    assert response["safety"]["broker_submit_called"] is False
    assert response["safety"]["manual_submit_called"] is False
    assert response["safety"]["validation_called"] is False
    assert response["safety"]["confirm_live_auto_checked"] is False

    run = db_session.query(AgentPlanRun).one()
    assert run.status == "completed"
    assert run.result_type == "prefill_payload"
    assert run.execution_mode == "agent_manual_prefill"
    assert run.trigger_source == "agent_manual_prefill"


def test_manual_sell_prefill_includes_quantity(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "PREPARE_MANUAL_SELL_TICKET",
            "domain": "order",
            "intent": "prepare_sell_ticket",
            "symbol": "005930",
            "side": "sell",
            "quantity": 2,
        },
    )

    response = AgentLivePrefillService().prepare_manual_ticket(db_session, plan_id=plan["id"])

    assert response["status"] == "manual_ticket_prefill_ready"
    assert response["prefill"]["side"] == "sell"
    assert response["prefill"]["quantity"] == 2
    assert response["prefill"]["qty"] == 2


def test_pending_auth_live_plan_returns_auth_required_without_prefill(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "REQUEST_LIVE_ORDER_SUBMIT",
            "domain": "order",
            "intent": "request_live_order",
            "symbol": "005930",
            "side": "buy",
            "quantity": 1,
        },
    )

    response = AgentLivePrefillService().prepare_manual_ticket(db_session, plan_id=plan["id"])

    assert response["status"] == "auth_required"
    assert response["prefill"] is None
    assert response["result"]["prefill_ready"] is False
    assert response["result"]["reason"] == "auth_required"
    assert response["auth"]["required"] is True
    assert response["auth"]["status"] == "pending"
    run = db_session.query(AgentPlanRun).one()
    assert run.status == "blocked"
    assert run.result_type == "prefill_payload"
    assert run.execution_mode == "agent_manual_prefill"


def test_approved_live_plan_with_matching_scope_returns_ready_prefill(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "REQUEST_LIVE_ORDER_SUBMIT",
            "domain": "order",
            "intent": "request_live_order",
            "symbol": "005930",
            "side": "buy",
            "quantity": 1,
        },
    )
    auth = _approve_latest_auth(db_session, plan["id"])

    response = AgentLivePrefillService().prepare_manual_ticket(db_session, plan_id=plan["id"])

    assert response["status"] == "manual_ticket_prefill_ready"
    assert response["auth"]["approval_request_id"] == auth.id
    assert response["auth"]["status"] == "approved"
    assert response["prefill"]["source_metadata"]["auth_approval_request_id"] == auth.id
    assert response["prefill"]["confirm_live"] is False


def test_approved_auth_with_scope_mismatch_is_blocked(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "REQUEST_LIVE_ORDER_SUBMIT",
            "domain": "order",
            "intent": "request_live_order",
            "symbol": "005930",
            "side": "buy",
            "quantity": 1,
        },
    )
    auth = _approve_latest_auth(db_session, plan["id"])
    auth.scope_hash = "0" * 64
    db_session.commit()

    response = AgentLivePrefillService().prepare_manual_ticket(db_session, plan_id=plan["id"])

    assert response["status"] == "blocked"
    assert response["prefill"] is None
    assert response["result"]["reason"] == "auth_scope_mismatch"


def test_cancelled_and_expired_plans_are_blocked(db_session):
    cancelled = _create_plan(
        db_session,
        {
            "command_type": "PREPARE_MANUAL_SELL_TICKET",
            "domain": "order",
            "intent": "prepare_sell_ticket",
            "symbol": "005930",
            "side": "sell",
            "quantity": 1,
        },
    )
    AgentPlanService().cancel_plan(db_session, plan_id=cancelled["id"], reason="test cancel")

    cancelled_response = AgentLivePrefillService().prepare_manual_ticket(db_session, plan_id=cancelled["id"])

    assert cancelled_response["status"] == "blocked"
    assert cancelled_response["result"]["reason"] == "plan_cancelled"

    expired = _create_plan(
        db_session,
        {
            "command_type": "PREPARE_MANUAL_SELL_TICKET",
            "domain": "order",
            "intent": "prepare_sell_ticket",
            "symbol": "005930",
            "side": "sell",
            "quantity": 1,
        },
    )
    row = db_session.get(AgentPlan, expired["id"])
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    expired_response = AgentLivePrefillService().prepare_manual_ticket(db_session, plan_id=expired["id"])

    assert expired_response["status"] == "blocked"
    assert expired_response["result"]["reason"] == "plan_expired"


def test_settings_and_scheduler_commands_are_not_prefillable(db_session):
    setting_plan = _create_plan(
        db_session,
        {
            "command_type": "SET_DRY_RUN",
            "domain": "settings",
            "intent": "set_dry_run",
            "settings_change": {"key": "dry_run", "value": False},
        },
    )
    schedule_plan = _create_plan(
        db_session,
        {
            "command_type": "REQUEST_LIVE_ORDER_SCHEDULE",
            "domain": "scheduler",
            "intent": "schedule_live_order",
            "symbol": "005930",
            "side": "buy",
            "quantity": 1,
            "schedule": {"type": "once", "run_at": "2026-06-18T10:00:00+09:00", "timezone": "Asia/Seoul"},
        },
    )

    setting_response = AgentLivePrefillService().prepare_manual_ticket(db_session, plan_id=setting_plan["id"])
    schedule_response = AgentLivePrefillService().prepare_manual_ticket(db_session, plan_id=schedule_plan["id"])

    assert setting_response["status"] == "blocked"
    assert setting_response["result"]["reason"] == "setting_change_not_prefillable"
    assert schedule_response["status"] == "blocked"
    assert schedule_response["result"]["reason"] == "scheduler_live_order_not_prefillable"


def test_missing_symbol_is_blocked_after_scope_still_matches(db_session):
    plan = _create_plan(
        db_session,
        {
            "command_type": "PREPARE_MANUAL_BUY_TICKET",
            "domain": "order",
            "intent": "prepare_buy_ticket",
            "side": "buy",
            "budget": {"amount": 30000, "currency": "KRW"},
        },
    )

    response = AgentLivePrefillService().prepare_manual_ticket(db_session, plan_id=plan["id"])

    assert response["status"] == "blocked"
    assert response["prefill"] is None
    assert response["result"]["reason"] == "missing_symbol"


def test_forbidden_live_paths_are_not_called_for_prefill(db_session, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("forbidden execution path called")

    monkeypatch.setattr("app.services.kis_manual_order_service.KisManualOrderService.submit_manual", fail)
    monkeypatch.setattr("app.services.kis_order_validation_service.KisOrderValidationService.validate", fail)
    monkeypatch.setattr("app.brokers.kis_client.KisClient.submit_order", fail)
    plan = _create_plan(
        db_session,
        {
            "command_type": "REQUEST_LIVE_ORDER_SUBMIT",
            "domain": "order",
            "intent": "request_live_order",
            "symbol": "005930",
            "side": "buy",
            "quantity": 1,
        },
    )
    _approve_latest_auth(db_session, plan["id"])

    response = AgentLivePrefillService().prepare_manual_ticket(db_session, plan_id=plan["id"])

    assert response["status"] == "manual_ticket_prefill_ready"
    assert response["safety"]["real_order_submitted"] is False
