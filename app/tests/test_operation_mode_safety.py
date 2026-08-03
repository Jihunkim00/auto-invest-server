from __future__ import annotations

from pathlib import Path

from app.db.models import OperationModeAudit, OrderLog
from app.main import app
from app.services.operation_mode_service import OperationModeService
from app.services.runtime_setting_service import RuntimeSettingService
from app.tests.test_operation_mode_service import FakeRelease


def test_operation_mode_does_not_change_runtime_defaults(db_session):
    settings = RuntimeSettingService().get_settings_read_only(db_session)

    assert settings["dry_run"] is True
    assert settings["kill_switch"] is False
    assert settings["scheduler_enabled"] is False
    assert settings["automation_mode"] == "off"
    assert settings["automation_release_enabled"] is False
    assert settings["kis_scheduler_enabled"] is False
    assert settings["kis_scheduler_dry_run"] is True
    assert settings["agent_chat_live_order_enabled"] is False
    assert settings["operation_mode_requested"] == "paper"


def test_operation_mode_source_has_no_direct_order_or_cycle_path():
    root = Path(__file__).resolve().parents[2]
    files = [
        root / "app" / "services" / "operation_mode_service.py",
        root / "app" / "routes" / "app_facade.py",
    ]
    banned = [
        "submit_market_buy",
        "submit_market_sell",
        "submit_order(",
        "submit_domestic_cash_order",
        "KisManualOrderService",
        "confirm_live",
        "run_cycle_once(",
        "run_once(",
        "disable_kill",
        "skip_gates",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in files)

    assert not [term for term in banned if term in text]


def test_mode_change_audit_sanitizes_reason_and_snapshots(db_session):
    service = OperationModeService(
        runtime_settings=RuntimeSettingService(),
        automation_release_service=FakeRelease(),
    )

    service.change_mode(
        db_session,
        target_mode="paused",
        acknowledged=False,
        reason="pause because authorization=synthetic-sensitive-value",
    )
    audit = db_session.query(OperationModeAudit).one()

    assert "synthetic-sensitive-value" not in str(audit.reason)
    assert "***" in str(audit.reason)
    assert "synthetic-sensitive-value" not in audit.before_state_json
    assert "synthetic-sensitive-value" not in audit.after_state_json


def test_operation_mode_openapi_contract_is_additive():
    openapi = app.openapi()

    assert "/app/operation-mode" in openapi["paths"]
    assert "get" in openapi["paths"]["/app/operation-mode"]
    assert "put" in openapi["paths"]["/app/operation-mode"]
    assert "OperationModeChangeRequest" in openapi["components"]["schemas"]
    assert "OperationModeStatusResponse" in openapi["components"]["schemas"]


def test_operation_mode_transition_never_creates_order_rows(db_session):
    service = OperationModeService(
        runtime_settings=RuntimeSettingService(),
        automation_release_service=FakeRelease(can_submit=True),
    )

    service.change_mode(
        db_session,
        target_mode="live",
        acknowledged=True,
        reason="source restriction test",
    )
    service.change_mode(
        db_session,
        target_mode="paused",
        acknowledged=False,
        reason="pause after live",
    )

    assert db_session.query(OrderLog).count() == 0
