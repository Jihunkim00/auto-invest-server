from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.db.models import TradeRunLog
from app.schemas.agent_chat_orchestrator import (
    AgentChatIntent,
    AgentChatIntentCategory,
)
from app.schemas.agent_chat_tool import AgentChatToolCall
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_tool_executor import AgentChatToolExecutor
from app.services.agent_chat_tool_registry import AgentChatToolRegistry
from app.services.automation_soak_test_service import (
    AutomationSoakAcknowledgementRequired,
    AutomationSoakTestService,
)
from app.services.runtime_setting_service import RuntimeSettingService


NOW = datetime(2026, 7, 12, 1, 0, tzinfo=UTC)


class FakeWatchdog:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or {
            "sync_health": "healthy",
            "should_block_orchestrator": False,
            "should_block_auto_buy": False,
            "should_block_auto_sell": False,
            "issues": [],
            "blocking_reasons": [],
            "next_safe_action": "continue_monitoring",
        }
        self.latest_calls = 0
        self.status_calls = 0

    def latest(self, db, **kwargs):
        self.latest_calls += 1
        return dict(self.payload)

    def status(self, db, **kwargs):
        self.status_calls += 1
        return dict(self.payload)


class FakeAutomationMode:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or {
            "automation_mode": "off",
            "effective_status": "off",
            "can_attempt_phase1_live": False,
            "can_submit_live_order": False,
            "blocking_reasons": ["automation_mode_off"],
        }
        self.calls = 0

    def status(self, db, **kwargs):
        self.calls += 1
        return dict(self.payload)


class FakeReadiness:
    def __init__(self, status: str = "ready") -> None:
        self.status = status
        self.calls = 0

    def readiness(self, db, **kwargs):
        self.calls += 1
        return {"overall_status": self.status}


class FakeDailyOps:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or {
            "pnl_summary": {
                "realized_pl_pct": 0,
                "realized_pl": 0,
            }
        }
        self.calls = 0

    def summary(self, db, **kwargs):
        self.calls += 1
        return dict(self.payload)


class FakeOrchestrator:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or {
            "run_id": 77,
            "result_status": "dry_run_completed",
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "order_cancel_called": False,
            "action_taken": "none",
            "risk_flags": [],
            "gating_notes": [],
            "next_safe_action": "continue_monitoring",
        }
        self.calls = 0
        self.requests: list[Any] = []

    def run_once(self, db, request=None, *, now=None):
        self.calls += 1
        self.requests.append(request)
        return dict(self.payload)


def make_service(
    *,
    runtime: RuntimeSettingService | None = None,
    watchdog: FakeWatchdog | None = None,
    automation_mode: FakeAutomationMode | None = None,
    readiness: FakeReadiness | None = None,
    daily_ops: FakeDailyOps | None = None,
    orchestrator: FakeOrchestrator | None = None,
) -> AutomationSoakTestService:
    return AutomationSoakTestService(
        runtime_settings=runtime or RuntimeSettingService(),
        broker_sync_watchdog_service=watchdog or FakeWatchdog(),
        automation_mode_service=automation_mode or FakeAutomationMode(),
        readiness_service=readiness or FakeReadiness(),
        daily_ops_service=daily_ops or FakeDailyOps(),
        portfolio_orchestrator_service=orchestrator or FakeOrchestrator(),
    )


def enable_soak(
    db_session,
    runtime: RuntimeSettingService,
    *,
    mode: str = "dry_run_monitoring",
    allow_live_phase1: bool = False,
) -> None:
    runtime.update_settings(
        db_session,
        {
            "automation_soak_enabled": True,
            "automation_soak_mode": mode,
            "automation_soak_allow_live_phase1": allow_live_phase1,
        },
    )


def test_soak_status_defaults_disabled(db_session):
    status = make_service().status(db_session, now=NOW)

    assert status["soak_enabled"] is False
    assert status["effective_status"] == "disabled"
    assert status["can_run_soak_cycle"] is False
    assert status["safety_flags"]["broker_submit_called"] is False


def test_run_once_disabled_records_disabled_without_orchestrator(db_session):
    orchestrator = FakeOrchestrator()
    result = make_service(orchestrator=orchestrator).run_once(db_session, now=NOW)

    assert result["result_status"] == "disabled"
    assert "automation_soak_disabled" in result["blocking_reasons"]
    assert orchestrator.calls == 0
    assert db_session.query(TradeRunLog).filter_by(mode="automation_soak_test").count() == 1


def test_kill_latch_blocks_run_without_orchestrator(db_session):
    runtime = RuntimeSettingService()
    enable_soak(db_session, runtime)
    runtime.update_settings(
        db_session,
        {
            "automation_soak_kill_latch_active": True,
            "automation_soak_kill_latch_reason": "broker_sync_unsafe",
        },
    )
    orchestrator = FakeOrchestrator()

    result = make_service(runtime=runtime, orchestrator=orchestrator).run_once(
        db_session,
        now=NOW,
    )

    assert result["result_status"] == "kill_latched"
    assert result["kill_latch_active"] is True
    assert "broker_sync_unsafe" in result["blocking_reasons"]
    assert orchestrator.calls == 0


def test_reset_kill_latch_requires_ack_and_preserves_independent_gates(db_session):
    runtime = RuntimeSettingService()
    runtime.settings.kis_real_order_enabled = True
    runtime.update_settings(
        db_session,
        {
            "dry_run": False,
            "kill_switch": True,
            "automation_soak_kill_latch_active": True,
            "automation_soak_kill_latch_reason": "daily_loss_limit_breached",
        },
    )
    service = make_service(runtime=runtime)

    with pytest.raises(AutomationSoakAcknowledgementRequired):
        service.reset_kill_latch(db_session, operator_acknowledged_risks=False)

    status = service.reset_kill_latch(
        db_session,
        operator_acknowledged_risks=True,
        reason="reviewed",
    )
    settings = runtime.get_settings_read_only(db_session)

    assert status["kill_latch_active"] is False
    assert settings["dry_run"] is False
    assert settings["kill_switch"] is True
    assert runtime.settings.kis_real_order_enabled is True


def test_watchdog_unsafe_latches_and_blocks_orchestrator(db_session):
    runtime = RuntimeSettingService()
    enable_soak(db_session, runtime)
    watchdog = FakeWatchdog(
        {
            "sync_health": "unsafe",
            "should_block_orchestrator": True,
            "should_block_auto_buy": True,
            "should_block_auto_sell": True,
            "issues": [{"issue_type": "stale_order"}],
            "blocking_reasons": ["broker_sync_unsafe"],
            "next_safe_action": "review_broker_sync_watchdog",
        }
    )
    orchestrator = FakeOrchestrator()

    result = make_service(
        runtime=runtime,
        watchdog=watchdog,
        orchestrator=orchestrator,
    ).run_once(db_session, now=NOW)
    settings = runtime.get_settings_read_only(db_session)

    assert result["result_status"] == "blocked"
    assert result["kill_latch_active"] is True
    assert "broker_sync_unsafe" in {
        rule["rule_id"] for rule in result["kill_rules_triggered"]
    }
    assert settings["automation_soak_kill_latch_active"] is True
    assert orchestrator.calls == 0


def test_dry_run_automation_off_reaches_orchestrator_without_latching(db_session):
    runtime = RuntimeSettingService()
    enable_soak(db_session, runtime)
    orchestrator = FakeOrchestrator(
        {
            "result_status": "disabled",
            "primary_block_reason": "portfolio_orchestrator_disabled",
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "order_cancel_called": False,
            "action_taken": "none",
            "risk_flags": [],
            "gating_notes": [],
            "next_safe_action": "review_runtime_settings",
        }
    )

    result = make_service(runtime=runtime, orchestrator=orchestrator).run_once(
        db_session,
        now=NOW,
    )

    assert result["result_status"] == "orchestrator_blocked"
    assert result["kill_latch_active"] is False
    assert "automation_mode_not_ready" not in {
        rule["rule_id"] for rule in result["kill_rules_triggered"]
    }
    assert orchestrator.calls == 1


def test_live_phase1_soak_requires_operator_acknowledgement(db_session):
    runtime = RuntimeSettingService()
    enable_soak(
        db_session,
        runtime,
        mode="live_phase1_controlled",
        allow_live_phase1=True,
    )
    orchestrator = FakeOrchestrator()

    result = make_service(runtime=runtime, orchestrator=orchestrator).run_once(
        db_session,
        {"mode": "live_phase1_controlled"},
        now=NOW,
    )

    assert result["result_status"] == "blocked"
    assert "operator_acknowledgement_required" in result["blocking_reasons"]
    assert orchestrator.calls == 0


def test_agent_chat_routes_soak_status_read_only_and_blocks_mutations(db_session, monkeypatch):
    router = AgentChatIntentRouterService(openai_client=None)

    query_intent = router.fallback_route("show automation soak kill rule status")
    assert query_intent.category == AgentChatIntentCategory.READ_ONLY_AUTOMATION_SOAK_QUERY
    assert query_intent.selected_tools[0].tool_name == "automation_soak_status_lookup"

    mutation_intent = router.fallback_route("reset the automation soak kill latch")
    assert mutation_intent.category == AgentChatIntentCategory.DANGEROUS_SETTING_REQUEST
    assert mutation_intent.selected_tools[0].tool_name == "settings_change_blocker"

    class FakeAgentSoakService:
        calls: list[dict[str, Any]] = []

        def __init__(self, **kwargs):
            pass

        def status(self, db, **kwargs):
            self.calls.append(dict(kwargs))
            return {
                "generated_at": NOW.isoformat(),
                "soak_enabled": False,
                "soak_mode": "dry_run_monitoring",
                "allow_live_phase1": False,
                "kill_latch_active": False,
                "effective_status": "disabled",
                "can_run_soak_cycle": False,
                "can_attempt_live_phase1": False,
                "can_submit_live_order": False,
                "cycle_count_today": 0,
                "max_cycles_per_day": 3,
                "action_count_today": 0,
                "max_actions_per_day": 1,
                "consecutive_failure_count": 0,
                "max_consecutive_failures": 2,
                "kill_rules": [],
                "blocking_reasons": [],
                "warning_reasons": [],
                "next_safe_action": "enable_soak_test_explicitly",
                "safety_flags": {"broker_submit_called": False},
            }

        def run_once(self, *args, **kwargs):
            raise AssertionError("Agent Chat must not run soak.")

        def reset_kill_latch(self, *args, **kwargs):
            raise AssertionError("Agent Chat must not reset kill latch.")

    monkeypatch.setattr(
        "app.services.agent_chat_tool_executor.AutomationSoakTestService",
        FakeAgentSoakService,
    )
    result = AgentChatToolExecutor().execute(
        db_session,
        call=AgentChatToolCall(tool_name="automation_soak_status_lookup"),
        intent=AgentChatIntent(
            category=AgentChatIntentCategory.READ_ONLY_AUTOMATION_SOAK_QUERY,
            provider="kis",
            market="KR",
        ),
    )

    assert result.status == "success"
    assert result.result_type == "automation_soak_status"
    assert result.safety.read_only is True
    assert result.safety.mutation is False
    assert FakeAgentSoakService.calls == [{"provider": "kis", "market": "KR"}]


def test_agent_chat_registry_has_no_soak_mutation_tool():
    names = set(AgentChatToolRegistry().tool_names())

    assert "automation_soak_status_lookup" in names
    assert "automation_soak_run_once" not in names
    assert "automation_soak_reset_kill_latch" not in names
