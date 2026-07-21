from __future__ import annotations

import json
from pathlib import Path

from app.db.models import OrderLog, RuntimeSetting, TradeRunLog
from app.schemas.agent_chat_live_order import AgentChatLiveOrderConfirmRequest
from app.services.portfolio_orchestrator_service import PortfolioOrchestratorService
from app.services.runtime_setting_service import RuntimeSettingService
from app.tests.test_agent_chat_live_order_service import (
    _Calls,
    _conversation,
    _enable_chat_live_order,
    _intent,
    _service,
    _settings,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_JSON = REPO_ROOT / "docs" / "baseline" / "operation-baseline.json"

BASELINE_EXISTING_TESTS = {
    "app/tests/test_kis_manual_order_submit.py": [
        "test_submit_manual_rejects_when_dry_run_true",
        "test_submit_manual_rejects_when_runtime_dry_run_enabled",
        "test_submit_manual_rejects_when_kill_switch_true",
        "test_submit_manual_rejects_when_no_recent_dry_run_validation",
        "test_submit_manual_rejects_when_confirmation_missing",
        "test_submit_manual_rejects_when_daily_trade_limit_reached",
        "test_submit_manual_response_and_logs_do_not_expose_secrets",
    ],
    "app/tests/test_agent_chat_live_order_service.py": [
        "test_prepare_live_order_creates_pending_confirmation_only",
        "test_confirm_blocked_when_dry_run_true",
        "test_confirm_blocked_when_expired",
        "test_confirm_blocked_when_phrase_or_token_mismatch",
        "test_cancel_pending_action_does_not_validate_or_submit",
    ],
    "app/tests/test_agent_chat_live_order_safety.py": [
        "test_prepare_never_calls_validation_or_manual_submit",
        "test_confirm_blocks_duplicate_open_order_before_submit",
    ],
    "app/tests/test_agent_chat_live_order_idempotency.py": [
        "test_confirm_idempotent_submits_once",
        "test_confirm_existing_related_order_does_not_resubmit",
        "test_cancelled_action_cannot_confirm",
    ],
    "app/tests/test_automation_mode_control.py": [
        "test_automation_mode_defaults_to_off",
        "test_phase1_live_ready_does_not_change_independent_safety_gates",
        "test_mode_off_endpoint_does_not_create_or_submit_orders",
        "test_no_direct_order_submit_path_added",
    ],
    "app/tests/test_automation_release.py": [
        "test_release_status_defaults_disabled",
        "test_release_preflight_is_read_only",
        "test_live_cycle_blocked_when_release_disabled",
        "test_live_cycle_blocked_when_kill_latch_active",
        "test_live_cycle_blocked_when_watchdog_unsafe",
        "test_release_service_source_has_no_direct_broker_or_override_path",
        "test_release_scheduler_hook_disabled_by_default",
    ],
    "app/tests/test_strategy_auto_buy_scheduler.py": [
        "test_scheduler_status_default_disabled",
        "test_scheduler_status_safety_allow_live_orders_false",
        "test_manual_scheduler_dry_run_blocked_when_scheduler_disabled",
        "test_no_new_entry_after_blocks_scheduler_dry_run",
        "test_scheduler_source_has_no_live_order_calls",
    ],
}


def test_operation_baseline_manifest_records_current_main_commit():
    payload = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["git"]["branch"] == "main"
    assert payload["git"]["commit_sha"] == "26ab08fbba17fbf6000b939705f348a0b4fde904"
    assert payload["database"]["table_count"] >= 28
    assert len(payload["safety_invariants"]) >= 8


def test_operation_baseline_runtime_defaults_remain_live_disabled(db_session):
    service = RuntimeSettingService()

    settings = service.get_settings_read_only(db_session)

    assert db_session.query(RuntimeSetting).count() == 0
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is False
    assert settings["scheduler_enabled"] is False
    assert settings["automation_mode"] == "off"
    assert settings["kis_scheduler_enabled"] is False
    assert settings["kis_scheduler_dry_run"] is True
    assert settings["kis_scheduler_allow_real_orders"] is False
    assert settings["kis_scheduler_buy_enabled"] is False
    assert settings["kis_scheduler_sell_enabled"] is False
    assert settings["kis_scheduler_max_live_orders_per_day"] == 1
    assert settings["agent_chat_live_order_enabled"] is False
    assert settings["agent_chat_live_order_requires_confirm"] is True
    assert settings["agent_chat_live_order_max_orders_per_day"] == 1
    assert settings["agent_chat_live_order_max_notional_pct"] == 0.03
    assert settings["agent_chat_live_order_max_notional_krw"] == 50000.0
    assert settings["automation_release_enabled"] is False
    assert settings["automation_release_max_actions_per_cycle"] == 1
    assert settings["automation_release_max_daily_auto_actions"] == 2
    assert settings["automation_release_max_daily_auto_buys"] == 1
    assert settings["automation_release_max_daily_auto_sells"] == 1
    assert settings["portfolio_orchestrator_enabled"] is False
    assert settings["portfolio_orchestrator_max_actions_per_run"] == 1
    assert settings["broker_sync_watchdog_block_automation_on_unsafe"] is True


def test_agent_chat_live_order_dry_run_contract_blocks_submit(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.agent_chat_live_order_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    calls = _Calls()
    service = _service(calls=calls)
    _enable_chat_live_order(db_session, dry_run=True, max_notional_pct=1.0)
    action = service.prepare(
        db_session,
        intent=_intent(),
        conversation_key=_conversation(db_session),
        user_message_id=10,
    )["action"]

    response = service.confirm(
        db_session,
        action_id=action["action_id"],
        request=AgentChatLiveOrderConfirmRequest(
            confirmation=True,
            confirmation_token=action["confirmation_token"],
            user_acknowledged_live_order=True,
        ),
    )

    assert response["status"] == "blocked"
    assert response["diagnostics"]["block_reason"] == "dry_run_true"
    assert response["safety"]["real_order_submitted"] is False
    assert response["safety"]["broker_submit_called"] is False
    assert response["safety"]["manual_submit_called"] is False
    assert response["safety"]["validation_called"] is False
    assert calls.validation == 0
    assert calls.manual_submit == 0
    assert db_session.query(OrderLog).count() == 0


def test_portfolio_orchestrator_latest_baseline_is_read_only_disabled(db_session):
    response = PortfolioOrchestratorService().latest(db_session)

    assert response["orchestrator_enabled"] is False
    assert response["allow_live_orders"] is False
    assert response["max_actions_per_run"] == 1
    assert response["real_order_submitted"] is False
    assert response["broker_submit_called"] is False
    assert response["manual_submit_called"] is False
    assert response["safety"]["read_only"] is True
    assert db_session.query(TradeRunLog).count() == 0


def test_existing_safety_contract_tests_remain_registered():
    for relative, test_names in BASELINE_EXISTING_TESTS.items():
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        for test_name in test_names:
            assert f"def {test_name}" in source

