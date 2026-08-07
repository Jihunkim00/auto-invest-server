from __future__ import annotations

from app.services.runtime_setting_service import RuntimeSettingService
from app.tests.test_operation_test4_entry import NOW, make_service


def test_readiness_returns_names_of_conflicting_live_flags(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": False,
            "kill_switch": False,
            "operation_test4_enabled": True,
            "operation_test4_scheduler_enabled": True,
            "operation_test4_allow_real_entry": True,
            "operation_test4_entry_enabled": True,
            "operation_test3_enabled": True,
            "operation_test3_scheduler_enabled": True,
        },
    )

    result = service.readiness(db_session, now=NOW)
    check = next(
        item for item in result["checks"]
        if item["check_name"] == "all_other_scheduler_live_flags_false"
    )

    assert check["passed"] is False
    assert "operation_test3_enabled" in check["detail"]["enabled_flags"]
    assert "operation_test3_scheduler_enabled" in check["detail"]["enabled_flags"]
    assert result["status"] == "blocked"