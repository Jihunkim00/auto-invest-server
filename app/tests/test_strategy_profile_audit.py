from __future__ import annotations

import json

from app.db.models import StrategyProfileAudit
from app.services.strategy_profile_service import StrategyProfileService


def test_apply_preset_creates_strategy_profile_audit(db_session):
    result = StrategyProfileService().apply_preset(
        db_session,
        profile_name="balanced",
        confirm_operator_ack=True,
        source="settings_ui",
    )

    row = db_session.query(StrategyProfileAudit).one()
    before = json.loads(row.before_snapshot)
    after = json.loads(row.after_snapshot)

    assert result["audit_id"] == row.id
    assert row.action == "apply_preset"
    assert row.previous_profile == "safe"
    assert row.new_profile == "balanced"
    assert row.confirm_operator_ack is True
    assert row.source == "settings_ui"
    assert before["profile_name"] == "safe"
    assert after["profile_name"] == "balanced"
    assert json.loads(row.safety_flags)["real_order_submitted"] is False
    assert json.loads(row.safety_flags)["validation_called"] is False
    assert json.loads(row.safety_flags)["scheduler_changed"] is False

