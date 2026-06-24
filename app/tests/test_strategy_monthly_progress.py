from __future__ import annotations

from app.services.strategy_profile_service import StrategyProfileService


def test_monthly_progress_uses_safe_profile_by_default(db_session):
    result = StrategyProfileService().monthly_progress(db_session)

    assert result["active_profile"]["profile_name"] == "safe"
    assert result["target_min_pct"] == 0.01
    assert result["skeleton"] is False
    assert result["current_month_return_pct"] == 0


def test_monthly_progress_uses_balanced_after_profile_apply(db_session):
    service = StrategyProfileService()
    service.apply_preset(
        db_session,
        profile_name="balanced",
        confirm_operator_ack=True,
        source="settings_ui",
    )

    result = service.monthly_progress(db_session)
    risk = service.risk_budget(db_session)

    assert result["active_profile"]["profile_name"] == "balanced"
    assert result["target_min_pct"] == 0.03
    assert result["target_max_pct"] == 0.05
    assert risk["new_entries_allowed_by_target"] is True
    assert risk["safety"]["real_order_submitted"] is False
