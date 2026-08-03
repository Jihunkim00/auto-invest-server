from __future__ import annotations

import pytest

from app.db.models import OperationModeAudit
from app.services.operation_mode_service import OperationModeService
from app.services.runtime_setting_service import RuntimeSettingService
from app.tests.test_operation_mode_service import FakeRelease


def test_safe_mode_transition_rolls_back_on_mid_transition_error(db_session):
    runtime = RuntimeSettingService()
    runtime.update_settings(
        db_session,
        {
            "dry_run": False,
            "kill_switch": True,
            "scheduler_enabled": True,
            "auto_buy_live_phase1_enabled": True,
            "auto_buy_live_phase1_allow_real_orders": True,
        },
    )
    before = runtime.get_settings(db_session)
    service = OperationModeService(
        runtime_settings=runtime,
        automation_release_service=FakeRelease(),
    )

    def fail_after_apply(**kwargs):
        raise RuntimeError("injected transition failure")

    service._after_apply_transition = fail_after_apply

    with pytest.raises(RuntimeError, match="injected transition failure"):
        service.change_mode(
            db_session,
            target_mode="paper",
            acknowledged=False,
            reason="rollback test",
        )

    after = runtime.get_settings(db_session)

    assert after["dry_run"] == before["dry_run"]
    assert after["kill_switch"] == before["kill_switch"]
    assert after["scheduler_enabled"] == before["scheduler_enabled"]
    assert after["auto_buy_live_phase1_enabled"] == before[
        "auto_buy_live_phase1_enabled"
    ]
    assert after["auto_buy_live_phase1_allow_real_orders"] == before[
        "auto_buy_live_phase1_allow_real_orders"
    ]
    assert db_session.query(OperationModeAudit).count() == 0
