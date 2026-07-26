from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.models import OperationModeAudit, OrderLog, RuntimeSetting
from app.services.operation_mode_service import (
    OperationModeService,
    OperationModeTransitionBlocked,
)
from app.services.runtime_setting_service import RuntimeSettingService


class FakeRelease:
    def __init__(
        self,
        *,
        can_submit: bool = False,
        blocking: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        self.can_submit = can_submit
        self.blocking = list(blocking or ([] if can_submit else ["production_readiness_not_ready"]))
        self.warnings = list(warnings or [])
        self.calls: list[dict] = []

    def preflight(self, db, *, provider="kis", market="KR", now=None):
        self.calls.append({"provider": provider, "market": market, "now": now})
        return {
            "release_enabled": self.can_submit,
            "release_armed": self.can_submit,
            "effective_status": "live_ready" if self.can_submit else "live_ready_blocked",
            "can_submit_live_order": self.can_submit,
            "blocking_reasons": list(self.blocking),
            "warning_reasons": list(self.warnings),
            "broker_sync_status": {
                "sync_health": "healthy" if self.can_submit else "warning",
                "blocking_reasons": [],
            },
            "soak_status": {
                "kill_latch_active": False,
                "blocking_reasons": [],
            },
            "production_readiness_status": "ready" if self.can_submit else "blocked",
            "safety_flags": {
                "broker_submit_called": False,
                "manual_submit_called": False,
                "real_order_submitted": False,
            },
        }


def _service(release: FakeRelease | None = None) -> OperationModeService:
    return OperationModeService(
        runtime_settings=RuntimeSettingService(),
        automation_release_service=release or FakeRelease(),
    )


def test_default_status_is_paper_without_creating_runtime_row(db_session):
    status = _service().get_status(db_session)

    assert status["requested_mode"] == "paper"
    assert status["effective_mode"] == "paper"
    assert status["status"] == "active"
    assert status["can_enter_live"] is False
    assert status["blocking_reasons"][0]["code"] == "production_readiness_not_ready"
    assert db_session.query(RuntimeSetting).count() == 0


def test_paper_transition_blocks_live_flags_without_resetting_kill_switch(db_session):
    runtime = RuntimeSettingService()
    runtime.update_settings(
        db_session,
        {
            "dry_run": False,
            "kill_switch": True,
            "max_trades_per_day": 7,
            "kis_scheduler_live_enabled": True,
            "kis_scheduler_allow_real_orders": True,
            "kis_scheduler_configured_allow_real_orders": True,
            "kis_scheduler_buy_enabled": True,
            "kis_live_auto_buy_enabled": True,
            "agent_chat_live_order_enabled": True,
            "agent_chat_live_order_kis_enabled": True,
            "agent_chat_live_order_buy_enabled": True,
            "auto_buy_live_phase1_enabled": True,
            "auto_buy_live_phase1_allow_real_orders": True,
            "automation_release_enabled": True,
            "automation_release_allow_live_phase1": True,
        },
    )

    response = _service().change_mode(
        db_session,
        target_mode="paper",
        acknowledged=False,
        reason="paper regression test",
    )
    settings = runtime.get_settings(db_session)

    assert response["changed"] is True
    assert settings["operation_mode_requested"] == "paper"
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True
    assert settings["max_trades_per_day"] == 7
    for key in (
        "kis_scheduler_live_enabled",
        "kis_scheduler_allow_real_orders",
        "kis_scheduler_configured_allow_real_orders",
        "kis_scheduler_buy_enabled",
        "kis_live_auto_buy_enabled",
        "agent_chat_live_order_enabled",
        "agent_chat_live_order_kis_enabled",
        "agent_chat_live_order_buy_enabled",
        "auto_buy_live_phase1_enabled",
        "auto_buy_live_phase1_allow_real_orders",
        "automation_release_enabled",
        "automation_release_allow_live_phase1",
    ):
        assert settings[key] is False
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(OperationModeAudit).count() == 1


def test_paused_transition_stops_automation_without_changing_global_safety(db_session):
    runtime = RuntimeSettingService()
    runtime.update_settings(
        db_session,
        {
            "dry_run": False,
            "kill_switch": True,
            "scheduler_enabled": True,
            "portfolio_orchestrator_enabled": True,
            "portfolio_orchestrator_allow_live_orders": True,
            "auto_sell_live_phase1_enabled": True,
            "auto_sell_live_phase1_allow_real_orders": True,
        },
    )

    response = _service().change_mode(
        db_session,
        target_mode="paused",
        acknowledged=False,
        reason="pause",
    )
    settings = runtime.get_settings(db_session)

    assert response["requested_mode"] == "paused"
    assert response["effective_mode"] == "paused"
    assert settings["dry_run"] is False
    assert settings["kill_switch"] is True
    assert settings["scheduler_enabled"] is False
    assert settings["portfolio_orchestrator_enabled"] is False
    assert settings["portfolio_orchestrator_allow_live_orders"] is False
    assert settings["auto_sell_live_phase1_enabled"] is False
    assert settings["auto_sell_live_phase1_allow_real_orders"] is False


def test_live_requires_acknowledgement(db_session):
    with pytest.raises(ValueError, match="acknowledged=true"):
        _service(FakeRelease(can_submit=True)).change_mode(
            db_session,
            target_mode="live",
            acknowledged=False,
            reason="live test",
        )


def test_live_blocked_rolls_back_runtime_changes_and_audits_attempt(db_session):
    runtime = RuntimeSettingService()
    before = runtime.get_settings_read_only(db_session)

    with pytest.raises(OperationModeTransitionBlocked) as exc:
        _service(FakeRelease(blocking=["watchdog_unhealthy"])).change_mode(
            db_session,
            target_mode="live",
            acknowledged=True,
            reason="blocked live test",
        )

    after = runtime.get_settings_read_only(db_session)
    audit = db_session.query(OperationModeAudit).one()

    assert exc.value.payload["changed"] is False
    assert exc.value.payload["status"] == "blocked"
    assert exc.value.payload["blocking_reasons"][0]["code"] == "watchdog_unhealthy"
    assert before["dry_run"] is True
    assert after["dry_run"] is True
    assert db_session.query(RuntimeSetting).count() == 0
    assert audit.status == "blocked"
    assert audit.requested_mode == "live"
    assert db_session.query(OrderLog).count() == 0


def test_live_success_sets_ready_state_without_starting_scheduler_or_orders(db_session):
    runtime = RuntimeSettingService()
    runtime.update_settings(
        db_session,
        {
            "automation_soak_last_successful_cycle_at": datetime.now(UTC),
            "kill_switch": False,
        },
    )

    response = _service(FakeRelease(can_submit=True)).change_mode(
        db_session,
        target_mode="live",
        acknowledged=True,
        reason="operator accepted live constraints",
    )
    settings = runtime.get_settings(db_session)

    assert response["changed"] is True
    assert response["effective_mode"] == "live"
    assert settings["operation_mode_requested"] == "live"
    assert settings["dry_run"] is False
    assert settings["automation_mode"] == "phase1_live_ready"
    assert settings["automation_release_enabled"] is True
    assert settings["automation_release_allow_live_phase1"] is True
    assert settings["automation_release_scheduler_enabled"] is False
    assert settings["auto_buy_live_phase1_enabled"] is True
    assert settings["auto_buy_live_phase1_allow_real_orders"] is True
    assert settings["kis_scheduler_live_enabled"] is False
    assert db_session.query(OrderLog).count() == 0


def test_repeated_same_mode_is_idempotent(db_session):
    service = _service()
    first = service.change_mode(
        db_session,
        target_mode="paused",
        acknowledged=False,
        reason="pause",
    )
    second = service.change_mode(
        db_session,
        target_mode="paused",
        acknowledged=False,
        reason="pause again",
    )

    assert first["changed"] is True
    assert second["changed"] is False
    assert second["status"] == "unchanged"
    assert db_session.query(OperationModeAudit).count() == 2
