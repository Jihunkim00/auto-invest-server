from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.db.models import RuntimeSetting
from app.services.automation_release_service import (
    AutomationReleaseAcknowledgementRequired,
    AutomationReleaseService,
)
from app.services.runtime_setting_service import RuntimeSettingService


class _Mode:
    def __init__(self, *, automation_mode: str = "phase1_live_ready", live_ready: bool = True):
        self.automation_mode = automation_mode
        self.live_ready = live_ready

    def status(self, db, *, now=None):
        return {
            "automation_mode": self.automation_mode,
            "effective_status": "live_ready" if self.live_ready else "dry_run_ready",
            "can_run_monitoring": self.automation_mode != "off",
            "can_run_dry_run": self.automation_mode in {"dry_run_auto", "phase1_live_ready"},
            "can_attempt_phase1_live": self.live_ready,
            "can_submit_live_order": self.live_ready,
            "daily_trade_limit_remaining": 2,
            "sync_required_count": 0,
            "critical_exit_candidate_count": 0,
            "blocking_reasons": [] if self.live_ready else ["automation_mode_not_ready"],
        }


class _Watchdog:
    def __init__(self, *, health: str = "healthy"):
        self.health = health

    def latest(self, db, *, provider="kis", market="KR", now=None):
        return {
            "sync_health": self.health,
            "should_block_orchestrator": self.health in {"unsafe", "unknown"},
            "pending_sync_order_count": 0,
            "stale_local_order_count": 0,
            "position_mismatch_count": 0,
            "blocking_reasons": [] if self.health == "healthy" else [f"broker_sync_{self.health}"],
            "next_safe_action": "manual_review",
        }


class _Readiness:
    def __init__(self, *, status: str = "ready"):
        self.status = status

    def readiness(
        self,
        db,
        *,
        provider="kis",
        market="KR",
        include_details=False,
        include_recent=False,
        now=None,
    ):
        return {"overall_status": self.status, "blocking_reasons": []}


class _Soak:
    def __init__(self):
        self.calls: list[dict] = []

    def status(self, db, *, provider="kis", market="KR", now=None):
        return {
            "soak_enabled": True,
            "effective_status": "dry_run_ready",
            "kill_latch_active": False,
            "can_run_soak_cycle": True,
            "can_submit_live_order": False,
            "blocking_reasons": [],
        }

    def run_once(self, db, request=None, *, now=None):
        payload = dict(request or {})
        self.calls.append(payload)
        return {
            "run_id": 41,
            "result_status": "dry_run_completed",
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "order_cancel_called": False,
            "action_taken": "none",
            "orchestrator_run_id": 77,
            "blocking_reasons": [],
            "warning_reasons": [],
            "risk_flags": [],
            "gating_notes": ["stub_soak_called"],
        }


class _Orchestrator:
    def latest(self, db, *, provider="kis", market="KR", now=None):
        return {
            "result_status": "completed_no_action",
            "orchestrator_enabled": True,
            "allow_live_orders": True,
            "pending_order_conflict_count": 0,
            "critical_exit_candidate_count": 0,
        }


class _Buy:
    def status(self, db, *, provider="kis", market="KR", now=None):
        return {
            "result_status": "skipped",
            "auto_buy_live_enabled": True,
            "daily_auto_buy_count": 0,
            "daily_auto_buy_limit": 1,
        }


class _Sell:
    def status(self, db, *, provider="kis", market="KR", now=None):
        return {
            "result_status": "skipped",
            "auto_sell_live_enabled": True,
            "daily_auto_sell_count": 0,
            "daily_auto_sell_limit": 1,
        }


def _service(
    monkeypatch,
    *,
    mode=None,
    watchdog=None,
    readiness=None,
    soak=None,
):
    runtime = RuntimeSettingService()
    monkeypatch.setattr(runtime.settings, "kis_enabled", True, raising=False)
    monkeypatch.setattr(runtime.settings, "kis_real_order_enabled", True, raising=False)
    return AutomationReleaseService(
        runtime_settings=runtime,
        automation_mode_service=mode or _Mode(),
        broker_sync_watchdog_service=watchdog or _Watchdog(),
        readiness_service=readiness or _Readiness(),
        soak_test_service=soak or _Soak(),
        portfolio_orchestrator_service=_Orchestrator(),
        auto_buy_service=_Buy(),
        auto_sell_service=_Sell(),
    )


def _arm_release_settings(db_session, service: AutomationReleaseService):
    service.runtime_settings.update_settings(
        db_session,
        {
            "automation_release_enabled": True,
            "automation_release_allow_live_phase1": True,
            "automation_soak_last_successful_cycle_at": datetime.now(UTC),
            "dry_run": False,
            "kill_switch": False,
            "portfolio_orchestrator_enabled": True,
            "portfolio_orchestrator_allow_live_orders": True,
            "auto_buy_live_phase1_enabled": True,
            "auto_sell_live_phase1_enabled": True,
        },
    )


def test_release_status_defaults_disabled(db_session, monkeypatch):
    service = _service(monkeypatch)

    status = service.status(db_session)

    assert status["release_enabled"] is False
    assert status["effective_status"] == "disabled"
    assert status["can_submit_live_order"] is False
    assert status["safety_flags"]["direct_broker_submit_path"] is False
    assert status["safety_flags"]["order_cancel_path"] is False


def test_release_preflight_is_read_only(db_session, monkeypatch):
    service = _service(monkeypatch)

    service.preflight(db_session)

    assert db_session.query(RuntimeSetting).count() == 0


def test_release_arm_requires_acknowledgement(db_session, monkeypatch):
    service = _service(monkeypatch)

    with pytest.raises(AutomationReleaseAcknowledgementRequired):
        service.arm(db_session, operator_acknowledged_risks=False)


def test_release_arm_does_not_change_core_live_gates(db_session, monkeypatch):
    service = _service(monkeypatch)
    service.runtime_settings.update_settings(
        db_session,
        {"dry_run": True, "kill_switch": True},
    )

    service.arm(
        db_session,
        operator_acknowledged_risks=True,
        reason="operator release test",
    )
    settings = service.runtime_settings.get_settings(db_session)

    assert settings["automation_release_enabled"] is True
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True
    assert getattr(service.runtime_settings.settings, "kis_real_order_enabled") is True


def test_release_disarm_only_disables_release_layer(db_session, monkeypatch):
    service = _service(monkeypatch)
    service.runtime_settings.update_settings(
        db_session,
        {
            "automation_release_enabled": True,
            "automation_release_scheduler_enabled": True,
            "dry_run": True,
            "kill_switch": True,
        },
    )

    status = service.disarm(db_session, reason="stop release")
    settings = service.runtime_settings.get_settings(db_session)

    assert status["release_enabled"] is False
    assert settings["automation_release_scheduler_enabled"] is False
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True


def test_live_cycle_blocked_when_release_disabled(db_session, monkeypatch):
    soak = _Soak()
    service = _service(monkeypatch, soak=soak)

    result = service.run_cycle_once(
        db_session,
        {
            "mode": "live_phase1",
            "operator_acknowledged_risks": True,
            "trigger_source": "manual_release_cycle",
        },
    )

    assert result["result_status"] == "disabled"
    assert "automation_release_disabled" in result["blocking_reasons"]
    assert soak.calls == []


def test_live_cycle_blocked_when_kill_latch_active(db_session, monkeypatch):
    soak = _Soak()
    service = _service(monkeypatch, soak=soak)
    _arm_release_settings(db_session, service)
    service.runtime_settings.update_settings(
        db_session,
        {"automation_soak_kill_latch_active": True},
    )

    result = service.run_cycle_once(
        db_session,
        {
            "mode": "live_phase1",
            "operator_acknowledged_risks": True,
            "trigger_source": "manual_release_cycle",
        },
    )

    assert result["result_status"] == "kill_latched"
    assert soak.calls == []


def test_live_cycle_blocked_when_watchdog_unsafe(db_session, monkeypatch):
    soak = _Soak()
    service = _service(monkeypatch, watchdog=_Watchdog(health="unsafe"), soak=soak)
    _arm_release_settings(db_session, service)

    result = service.run_cycle_once(
        db_session,
        {
            "mode": "live_phase1",
            "operator_acknowledged_risks": True,
            "trigger_source": "manual_release_cycle",
        },
    )

    assert result["result_status"] == "blocked"
    assert "broker_sync_unsafe" in result["blocking_reasons"]
    assert soak.calls == []


def test_live_cycle_blocked_when_production_readiness_blocked(db_session, monkeypatch):
    soak = _Soak()
    service = _service(monkeypatch, readiness=_Readiness(status="blocked"), soak=soak)
    _arm_release_settings(db_session, service)

    result = service.run_cycle_once(
        db_session,
        {
            "mode": "live_phase1",
            "operator_acknowledged_risks": True,
            "trigger_source": "manual_release_cycle",
        },
    )

    assert result["result_status"] == "blocked"
    assert "production_readiness_blocked" in result["blocking_reasons"]
    assert soak.calls == []


def test_live_cycle_blocked_when_automation_mode_not_ready(db_session, monkeypatch):
    soak = _Soak()
    service = _service(
        monkeypatch,
        mode=_Mode(automation_mode="dry_run_auto", live_ready=False),
        soak=soak,
    )
    _arm_release_settings(db_session, service)

    result = service.run_cycle_once(
        db_session,
        {
            "mode": "live_phase1",
            "operator_acknowledged_risks": True,
            "trigger_source": "manual_release_cycle",
        },
    )

    assert result["result_status"] == "blocked"
    assert "release_live_phase1_gates_blocked" in result["blocking_reasons"]
    assert soak.calls == []


def test_live_cycle_requires_operator_acknowledgement(db_session, monkeypatch):
    soak = _Soak()
    service = _service(monkeypatch, soak=soak)
    _arm_release_settings(db_session, service)

    result = service.run_cycle_once(
        db_session,
        {
            "mode": "live_phase1",
            "operator_acknowledged_risks": False,
            "trigger_source": "manual_release_cycle",
        },
    )

    assert result["result_status"] == "blocked"
    assert "operator_acknowledgement_required" in result["blocking_reasons"]
    assert soak.calls == []


def test_monitoring_and_dry_run_cycles_delegate_to_soak(db_session, monkeypatch):
    soak = _Soak()
    service = _service(
        monkeypatch,
        mode=_Mode(automation_mode="dry_run_auto", live_ready=False),
        soak=soak,
    )
    service.runtime_settings.update_settings(
        db_session,
        {
            "automation_release_enabled": True,
            "automation_soak_last_successful_cycle_at": datetime.now(UTC),
            "dry_run": True,
            "kill_switch": False,
        },
    )

    monitoring = service.run_cycle_once(
        db_session,
        {"mode": "monitoring", "trigger_source": "manual_release_cycle"},
    )
    dry_run = service.run_cycle_once(
        db_session,
        {"mode": "dry_run", "trigger_source": "manual_release_cycle"},
    )

    assert monitoring["soak_run_id"] == 41
    assert dry_run["soak_run_id"] == 41
    assert [call["mode"] for call in soak.calls] == [
        "dry_run_monitoring",
        "dry_run_monitoring",
    ]
    assert all("confirm_live" not in call for call in soak.calls)
    assert all(call["operator_acknowledged_risks"] is False for call in soak.calls)


def test_release_service_source_has_no_direct_broker_or_override_path():
    source = Path("app/services/automation_release_service.py").read_text()

    for forbidden in [
        "submit_market_buy",
        "submit_market_sell",
        "submit_order",
        "submit_domestic_cash_order",
        "submit_manual",
        "confirm_live",
        "skip_gates",
        "liquidate",
    ]:
        assert forbidden not in source


def test_release_scheduler_hook_disabled_by_default(db_session, monkeypatch):
    service = _service(monkeypatch)
    settings = service.runtime_settings.get_settings_read_only(db_session)

    assert settings["automation_release_scheduler_enabled"] is False


def test_agent_chat_exposes_release_status_only():
    from app.services.agent_chat_tool_registry import AgentChatToolRegistry

    registry = AgentChatToolRegistry()

    assert registry.can_auto_execute("automation_release_status_lookup") is True
    assert registry.get("automation_release_arm") is None
    assert registry.get("automation_release_disarm") is None
    assert registry.get("automation_release_run_live") is None
