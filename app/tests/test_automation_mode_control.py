from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import OrderLog
from app.main import app
from app.routes.automation import get_automation_mode_control_service
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.automation_mode_control_service import (
    AutomationModeAcknowledgementRequired,
    AutomationModeControlService,
)
from app.services.runtime_setting_service import RuntimeSettingService


class FakeReadinessService:
    def __init__(self, status: str = "ready") -> None:
        self.status = status

    def readiness(self, db, **kwargs):
        return {"overall_status": self.status}


def control_service(*, readiness: str = "ready", kis_ready: bool = False):
    runtime = RuntimeSettingService()
    runtime.settings.kis_enabled = kis_ready
    runtime.settings.kis_real_order_enabled = kis_ready
    return AutomationModeControlService(
        runtime_settings=runtime,
        readiness_service=FakeReadinessService(readiness),
    )


def test_automation_mode_defaults_to_off(db_session):
    status = control_service().status(db_session)

    assert status["automation_mode"] == "off"
    assert status["effective_status"] == "off"
    assert status["can_submit_live_order"] is False
    assert "automation_mode_off" in status["blocking_reasons"]


def test_get_status_returns_safe_default_blockers(db_session):
    status = control_service(readiness="blocked").status(db_session)

    assert status["dry_run"] is True
    assert status["kill_switch"] is False
    assert status["kis_real_order_enabled"] is False
    assert status["portfolio_orchestrator_enabled"] is False
    assert status["safety_flags"]["broker_submit_called"] is False
    assert status["safety_flags"]["real_order_submitted"] is False


def test_setting_off_disables_automation_layer_flags_only(db_session):
    runtime = RuntimeSettingService()
    runtime.update_settings(
        db_session,
        {
            "dry_run": False,
            "kill_switch": True,
            "scheduler_enabled": True,
            "portfolio_orchestrator_enabled": True,
            "portfolio_orchestrator_allow_live_orders": True,
            "auto_buy_live_phase1_enabled": True,
            "auto_buy_live_phase1_allow_real_orders": True,
            "auto_sell_live_phase1_enabled": True,
            "auto_sell_live_phase1_allow_real_orders": True,
            "position_management_scheduler_enabled": True,
        },
    )

    status = AutomationModeControlService(
        runtime_settings=runtime,
        readiness_service=FakeReadinessService(),
    ).turn_off(db_session, reason="test")

    settings = runtime.get_settings(db_session)
    assert status["automation_mode"] == "off"
    assert settings["dry_run"] is False
    assert settings["kill_switch"] is True
    assert settings["scheduler_enabled"] is False
    assert settings["portfolio_orchestrator_enabled"] is False
    assert settings["portfolio_orchestrator_allow_live_orders"] is False
    assert settings["auto_buy_live_phase1_enabled"] is False
    assert settings["auto_sell_live_phase1_enabled"] is False


def test_setting_monitor_only_does_not_enable_live_order_flags(db_session):
    service = control_service(kis_ready=True)

    status = service.set_mode(db_session, automation_mode="monitor_only")

    settings = service.runtime_settings.get_settings(db_session)
    assert status["effective_status"] == "monitoring"
    assert status["can_attempt_phase1_live"] is False
    assert settings["portfolio_orchestrator_allow_live_orders"] is False
    assert settings["auto_buy_live_phase1_enabled"] is False
    assert settings["auto_sell_live_phase1_enabled"] is False


def test_setting_dry_run_auto_requires_acknowledgement(db_session):
    service = control_service()

    with pytest.raises(AutomationModeAcknowledgementRequired):
        service.set_mode(db_session, automation_mode="dry_run_auto")


def test_dry_run_auto_does_not_change_independent_safety_gates(db_session):
    service = control_service(kis_ready=True)
    service.runtime_settings.update_settings(
        db_session,
        {"dry_run": False, "kill_switch": True},
    )

    status = service.set_mode(
        db_session,
        automation_mode="dry_run_auto",
        operator_acknowledged_risks=True,
    )

    settings = service.runtime_settings.get_settings(db_session)
    assert status["automation_mode"] == "dry_run_auto"
    assert settings["dry_run"] is False
    assert settings["kill_switch"] is True
    assert settings["portfolio_orchestrator_enabled"] is True
    assert settings["portfolio_orchestrator_allow_live_orders"] is False


def test_setting_phase1_live_ready_requires_acknowledgement(db_session):
    service = control_service()

    with pytest.raises(AutomationModeAcknowledgementRequired):
        service.set_mode(db_session, automation_mode="phase1_live_ready")


def test_phase1_live_ready_does_not_change_independent_safety_gates(db_session):
    service = control_service(kis_ready=False)
    service.runtime_settings.update_settings(
        db_session,
        {"dry_run": True, "kill_switch": True},
    )

    status = service.set_mode(
        db_session,
        automation_mode="phase1_live_ready",
        operator_acknowledged_risks=True,
    )

    settings = service.runtime_settings.get_settings(db_session)
    assert status["automation_mode"] == "phase1_live_ready"
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True
    assert status["kis_real_order_enabled"] is False
    assert settings["portfolio_orchestrator_allow_live_orders"] is True


def test_phase1_live_ready_blocked_when_dry_run_true(db_session):
    service = control_service(kis_ready=True)
    service.set_mode(
        db_session,
        automation_mode="phase1_live_ready",
        operator_acknowledged_risks=True,
    )

    status = service.status(db_session)

    assert status["effective_status"] == "live_ready_blocked"
    assert status["can_submit_live_order"] is False
    assert "dry_run_enabled" in status["blocking_reasons"]


def test_phase1_live_ready_reports_live_ready_when_all_gates_pass(db_session):
    service = control_service(kis_ready=True)
    service.runtime_settings.update_settings(
        db_session,
        {"dry_run": False, "kill_switch": False, "max_trades_per_day": 1},
    )
    service.set_mode(
        db_session,
        automation_mode="phase1_live_ready",
        operator_acknowledged_risks=True,
    )

    status = service.status(db_session)

    assert status["effective_status"] == "live_ready"
    assert status["can_attempt_phase1_live"] is True
    assert status["can_submit_live_order"] is True
    assert status["blocking_reasons"] == []


def test_phase1_live_ready_blocks_pending_or_sync_required_orders(db_session):
    service = control_service(kis_ready=True)
    service.runtime_settings.update_settings(
        db_session,
        {"dry_run": False, "kill_switch": False},
    )
    service.set_mode(
        db_session,
        automation_mode="phase1_live_ready",
        operator_acknowledged_risks=True,
    )
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="buy",
            order_type="market",
            internal_status="SYNC_FAILED",
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    status = service.status(db_session)

    assert status["effective_status"] == "live_ready_blocked"
    assert status["sync_required_count"] == 1
    assert "pending_order_blocker_exists" in status["blocking_reasons"]
    assert "sync_required_order_exists" in status["blocking_reasons"]


def test_mode_off_endpoint_does_not_create_or_submit_orders(db_session):
    service = control_service(kis_ready=True)

    before = db_session.query(OrderLog).count()
    status = service.turn_off(db_session)
    after = db_session.query(OrderLog).count()

    assert status["automation_mode"] == "off"
    assert before == after == 0
    assert status["safety_flags"]["manual_submit_called"] is False


def test_routes_expose_status_set_and_off(db_session):
    service = control_service(kis_ready=True)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_automation_mode_control_service] = lambda: service
    try:
        client = TestClient(app)
        status = client.get("/automation/mode/status")
        needs_ack = client.post(
            "/automation/mode/set",
            json={"automation_mode": "phase1_live_ready"},
        )
        changed = client.post(
            "/automation/mode/set",
            json={
                "automation_mode": "phase1_live_ready",
                "operator_acknowledged_risks": True,
            },
        )
        off = client.post("/automation/mode/off", json={"reason": "test"})
    finally:
        app.dependency_overrides.clear()

    assert status.status_code == 200
    assert status.json()["automation_mode"] == "off"
    assert needs_ack.status_code == 409
    assert changed.status_code == 200
    assert changed.json()["automation_mode"] == "phase1_live_ready"
    assert off.status_code == 200
    assert off.json()["automation_mode"] == "off"


def test_agent_chat_cannot_change_automation_mode():
    router = AgentChatIntentRouterService(openai_client=None)

    intent = router.route(message="Set automation mode to phase1 live ready")

    assert intent.category == "dangerous_setting_request"
    assert intent.selected_tools[0].tool_name == "settings_change_blocker"


def test_no_direct_order_submit_path_added():
    root = Path(__file__).resolve().parents[2]
    files = [
        root / "app" / "services" / "automation_mode_control_service.py",
        root / "app" / "routes" / "automation.py",
    ]
    banned = [
        "submit_market_buy",
        "submit_market_sell",
        "submit_order",
        "submit_domestic_cash_order",
        "submit_manual",
        "KisManualOrderService",
        "confirm_live",
        "skip_gates",
        "disable_kill",
        "dry_run=false",
        "kis_real_order_enabled=true",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in files)

    assert not [term for term in banned if term in text]
