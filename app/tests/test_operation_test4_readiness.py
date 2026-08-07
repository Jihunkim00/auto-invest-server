from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.models import OperationTest4Cycle, OrderLog, RuntimeSetting, SignalLog, TradeRunLog
from app.db.database import get_db
from app.main import app
from app.services.operation_test4_service import ENABLE_CONFIRMATION
from app.services.runtime_setting_service import RuntimeSettingService
from app.tests.test_operation_test4_entry import (
    NOW,
    make_service,
    arm_for_entry,
)


def test_preflight_is_read_only_and_returns_required_shape(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)

    result = service.preflight_once(db_session, now=NOW)

    assert result["safety"] == {
        "read_only": True,
        "preflight_only": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
    }
    assert result["provider"] == "kis"
    assert result["market"] == "KR"
    assert "account" in result
    assert "watchlist" in result
    assert "candidate" in result
    assert "checks" in result
    assert db_session.query(OperationTest4Cycle).count() == 0
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(SignalLog).count() == 0
    assert db_session.query(TradeRunLog).count() == 0
    assert db_session.query(RuntimeSetting).count() == 0


def test_ready_requires_live_gates_and_candidate_score(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)

    initial = service.readiness(db_session, now=NOW)
    assert initial["entry_ready"] is False
    assert initial["status"] == "blocked"

    arm_for_entry(db_session, service)
    ready = service.readiness(db_session, now=NOW)

    assert ready["status"] == "ready"
    assert ready["live_ready"] is True
    assert ready["entry_ready"] is True
    assert ready["exit_ready"] is False
    assert ready["watchlist"]["configured_count"] == 50
    assert ready["watchlist"]["eligible_count"] == 50
    assert ready["candidate"]["quantity"] == 5
    assert ready["candidate"]["estimated_notional"] == 100_000
    assert ready["candidate"]["effective_position_pct"] == 10


def test_readiness_fails_closed_when_orderable_cash_is_missing(db_session, tmp_path):
    service, _, state = make_service(tmp_path)
    state["orderable_cash"] = 0
    state["warnings"] = ["orderable_cash_unavailable"]
    arm_for_entry(db_session, service)

    result = service.readiness(db_session, now=NOW)

    assert result["entry_ready"] is False
    assert "orderable_cash_unavailable" in result["review_reasons"]


def test_position_open_blocks_new_entry_readiness(db_session, tmp_path):
    service, _, state = make_service(tmp_path)
    arm_for_entry(db_session, service)
    state["positions"] = [{"symbol": "005930", "qty": 1, "current_price": 20_000}]

    result = service.readiness(db_session, now=NOW)

    assert result["entry_ready"] is False
    assert "position_exists" in result["blocking_reasons"]


def test_enable_live_requires_exact_confirmation_and_does_not_change_global_guards(
    db_session,
    tmp_path,
):
    service, _, _ = make_service(tmp_path)
    runtime = RuntimeSettingService()
    runtime.update_settings(
        db_session,
        {"dry_run": True, "kill_switch": True},
    )

    blocked = service.enable_live(
        db_session,
        confirm_live=True,
        confirmation="wrong",
        now=NOW,
    )
    enabled = service.enable_live(
        db_session,
        confirm_live=True,
        confirmation=ENABLE_CONFIRMATION,
        now=NOW,
    )
    settings = runtime.get_settings(db_session)

    assert blocked["status"] == "blocked"
    assert enabled["status"] == "live_enabled"
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True
    assert settings["operation_test4_allow_real_entry"] is True
    assert settings["operation_test4_allow_real_exit"] is True


def test_ops_settings_cannot_directly_enable_test4_real_gates(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).put(
            "/ops/settings",
            json={"operation_test4_allow_real_entry": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409