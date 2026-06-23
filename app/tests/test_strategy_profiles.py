from __future__ import annotations

import pytest

from app.db.models import KisOrderValidationLog, OrderLog, StrategyProfile
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.strategy_profile_service import (
    StrategyProfileAckRequired,
    StrategyProfileNotFound,
    StrategyProfileService,
)


def test_default_strategy_profiles_seed_and_safe_active(db_session):
    service = StrategyProfileService()

    service.ensure_seeded(db_session)

    rows = db_session.query(StrategyProfile).all()
    names = {row.profile_name for row in rows}
    assert names == {"safe", "balanced", "aggressive"}
    assert service.active_profile(db_session).profile_name == "safe"


def test_apply_balanced_with_ack_changes_active_profile(db_session):
    service = StrategyProfileService()

    result = service.apply_preset(
        db_session,
        profile_name="balanced",
        confirm_operator_ack=True,
        source="settings_ui",
    )

    assert result["active_profile"]["profile_name"] == "balanced"
    assert service.active_profile(db_session).profile_name == "balanced"
    assert result["safety"]["setting_changed"] is True
    assert result["safety"]["real_order_submitted"] is False


def test_apply_requires_ack_and_rejects_invalid_profile(db_session):
    service = StrategyProfileService()

    with pytest.raises(StrategyProfileAckRequired):
        service.apply_preset(
            db_session,
            profile_name="balanced",
            confirm_operator_ack=False,
            source="settings_ui",
        )
    with pytest.raises(StrategyProfileNotFound):
        service.apply_preset(
            db_session,
            profile_name="invalid",
            confirm_operator_ack=True,
            source="settings_ui",
        )
    assert service.active_profile(db_session).profile_name == "safe"


def test_apply_preset_does_not_submit_order_or_validation(db_session):
    service = StrategyProfileService()

    service.apply_preset(
        db_session,
        profile_name="aggressive",
        confirm_operator_ack=True,
        source="settings_ui",
    )

    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0


def test_apply_preset_does_not_change_runtime_safety_flags(db_session):
    runtime = RuntimeSettingService()
    before = runtime.update_settings(
        db_session,
        {
            "dry_run": True,
            "kill_switch": False,
            "scheduler_enabled": False,
            "kis_scheduler_enabled": False,
            "kis_scheduler_live_enabled": False,
            "kis_scheduler_allow_real_orders": False,
            "kis_live_auto_buy_enabled": False,
        },
    )

    StrategyProfileService().apply_preset(
        db_session,
        profile_name="balanced",
        confirm_operator_ack=True,
        source="settings_ui",
    )
    after = runtime.get_settings(db_session)

    for key in (
        "dry_run",
        "kill_switch",
        "scheduler_enabled",
        "kis_scheduler_enabled",
        "kis_scheduler_live_enabled",
        "kis_scheduler_allow_real_orders",
        "kis_live_auto_buy_enabled",
    ):
        assert after[key] == before[key]

