from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OperationTest4Cycle, OperationTest4EntryReservation, OrderLog
from app.main import app
from app.routes.operation_test4 import get_operation_test4_service
from app.services.operation_test4_service import (
    ENABLE_CONFIRMATION,
    ENTRY_CONFIRMATION,
    START_CONFIRMATION,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.tests.test_operation_test4_entry import (
    NOW,
    FakeManualOrderService,
    FakeValidation,
    candidate_provider,
    make_service,
)


def _stub_watchlist_rebuild(monkeypatch):
    calls: list[dict] = []

    def fake_builder(**kwargs):
        calls.append(kwargs)
        return {
            "source_universe_count": 80,
            "quote_checked_count": 80,
            "eligible_count": 60,
            "selected_count": 50,
            "reserve_eligible_count": 10,
            "excluded_count": 20,
            "exclusion_reasons": {"price_cap_exceeded": 20},
            "selected_symbols": [f"{index:06d}" for index in range(1, 51)],
        }

    monkeypatch.setattr(
        "app.services.operation_test4_service.build_operation_test4_watchlist",
        fake_builder,
    )
    return calls


def test_start_holding_candidate_rebuilds_and_leaves_runtime_unchanged(
    db_session,
    tmp_path,
    monkeypatch,
):
    calls = {"candidate": 0}

    def candidates(**kwargs):
        calls["candidate"] += 1
        return candidate_provider(score=64)

    service, _, _ = make_service(tmp_path, candidate=candidates)
    rebuild_calls = _stub_watchlist_rebuild(monkeypatch)
    runtime = RuntimeSettingService()
    runtime.update_settings(db_session, {"dry_run": True, "kill_switch": True})
    before = runtime.get_settings(db_session)

    result = service.start_full_cycle(
        db_session,
        confirm_live=True,
        confirmation=START_CONFIRMATION,
        now=NOW,
    )
    after = runtime.get_settings(db_session)

    assert result["status"] == "hold"
    assert result["action"] == "HOLD"
    assert result["preflight"]["candidate"]["symbol"] == "000001"
    assert result["preflight"]["blocking_reasons"] == ["final_score_gate_not_met"]
    assert calls == {"candidate": 1}
    assert len(rebuild_calls) == 1
    assert db_session.query(OperationTest4Cycle).count() == 0
    assert service.manual_order_service.calls == []
    assert after["dry_run"] is before["dry_run"] is True
    assert after["kill_switch"] is before["kill_switch"] is True
    assert after["operation_test4_enabled"] is False


class _RuntimeCapturingManualOrderService(FakeManualOrderService):
    def __init__(self):
        super().__init__()
        self.runtime_at_submit: dict | None = None

    def submit_manual(self, db, request, *, now=None):
        self.runtime_at_submit = RuntimeSettingService().get_settings(db)
        return super().submit_manual(db, request, now=now)


def test_start_buy_ready_arms_only_for_guarded_single_submit(
    db_session,
    tmp_path,
    monkeypatch,
):
    manual = _RuntimeCapturingManualOrderService()
    service, _, _ = make_service(tmp_path, manual_service=manual)
    _stub_watchlist_rebuild(monkeypatch)
    RuntimeSettingService().update_settings(
        db_session,
        {"dry_run": True, "kill_switch": True},
    )

    result = service.start_full_cycle(
        db_session,
        confirm_live=True,
        confirmation=START_CONFIRMATION,
        now=NOW,
    )
    settings = RuntimeSettingService().get_settings(db_session)
    cycle = db_session.query(OperationTest4Cycle).one()

    assert result["status"] == "entry_submitted"
    assert result["action"] == "BUY_READY"
    assert result["preflight"]["action"] == "BUY_READY"
    assert result["entry"]["reason"] == "entry_submitted"
    assert len(manual.calls) == 1
    assert manual.runtime_at_submit is not None
    assert manual.runtime_at_submit["dry_run"] is False
    assert manual.runtime_at_submit["kill_switch"] is False
    assert cycle.status == "entry_pending"
    assert settings["dry_run"] is False
    assert settings["kill_switch"] is False
    assert settings["operation_test4_allow_real_entry"] is True
    assert settings["operation_test4_entry_enabled"] is True
    assert settings["operation_test3_enabled"] is False
    assert settings["operation_test3_allow_real_orders"] is False


def test_second_start_is_idempotent_and_does_not_rebuild_or_submit_again(
    db_session,
    tmp_path,
    monkeypatch,
):
    manual = FakeManualOrderService()
    service, _, _ = make_service(tmp_path, manual_service=manual)
    rebuild_calls = _stub_watchlist_rebuild(monkeypatch)
    RuntimeSettingService().update_settings(
        db_session,
        {"dry_run": True, "kill_switch": True},
    )

    first = service.start_full_cycle(
        db_session,
        confirm_live=True,
        confirmation=START_CONFIRMATION,
        now=NOW,
    )
    second = service.start_full_cycle(
        db_session,
        confirm_live=True,
        confirmation=START_CONFIRMATION,
        now=NOW,
    )

    assert first["real_order_submitted"] is True
    assert second["reason"] == "active_cycle_exists"
    assert len(rebuild_calls) == 1
    assert len(manual.calls) == 1


def test_start_rechecks_local_open_order_after_arm_and_disarms(
    db_session,
    tmp_path,
    monkeypatch,
):
    manual = FakeManualOrderService()
    service, _, _ = make_service(tmp_path, manual_service=manual)
    _stub_watchlist_rebuild(monkeypatch)
    RuntimeSettingService().update_settings(
        db_session,
        {"dry_run": True, "kill_switch": True},
    )
    original_create_cycle = service._create_entry_cycle

    def create_cycle_with_new_open_order(db, **kwargs):
        cycle = original_create_cycle(db, **kwargs)
        db.add(
            OrderLog(
                broker="kis",
                market="KR",
                symbol="005930",
                side="buy",
                order_type="market",
                qty=1,
                requested_qty=1,
                internal_status=InternalOrderStatus.PENDING.value,
            )
        )
        db.commit()
        return cycle

    monkeypatch.setattr(service, "_create_entry_cycle", create_cycle_with_new_open_order)
    result = service.start_full_cycle(
        db_session,
        confirm_live=True,
        confirmation=START_CONFIRMATION,
        now=NOW,
    )
    settings = RuntimeSettingService().get_settings(db_session)
    cycle = db_session.query(OperationTest4Cycle).one()

    assert result["real_order_submitted"] is False
    assert manual.calls == []
    assert cycle.status == "review_required"
    assert cycle.manual_review_required is True
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True
    assert settings["operation_test4_enabled"] is False


def test_start_blocks_when_test3_live_flags_are_enabled_without_arm(
    db_session,
    tmp_path,
    monkeypatch,
):
    service, _, _ = make_service(tmp_path)
    _stub_watchlist_rebuild(monkeypatch)
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": True,
            "kill_switch": True,
            "operation_test3_enabled": True,
            "operation_test3_scheduler_enabled": True,
            "operation_test3_allow_real_orders": True,
            "operation_test3_position_management_enabled": True,
        },
    )

    result = service.start_full_cycle(
        db_session,
        confirm_live=True,
        confirmation=START_CONFIRMATION,
        now=NOW,
    )
    settings = RuntimeSettingService().get_settings(db_session)

    assert result["status"] == "hold"
    assert result["real_order_submitted"] is False
    assert service.manual_order_service.calls == []
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True
    assert settings["operation_test3_enabled"] is True


def test_start_and_existing_confirmation_routes_pass_confirm_live_correctly(db_session):
    calls: list[tuple[str, dict]] = []

    class FakeService:
        def start_full_cycle(self, db, *, confirm_live, confirmation):
            calls.append(("start", {"confirm_live": confirm_live, "confirmation": confirmation}))
            return {"status": "hold", "reason": "candidate_gate_blocked"}

        def enable_live(self, db, *, confirm_live, confirmation):
            calls.append(("enable", {"confirm_live": confirm_live, "confirmation": confirmation}))
            return {"status": "live_enabled"}

        def entry_run_once(self, db, *, confirm_live, confirmation):
            calls.append(("entry", {"confirm_live": confirm_live, "confirmation": confirmation}))
            return {"status": "blocked", "real_order_submitted": False}

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_operation_test4_service] = lambda: FakeService()
    try:
        client = TestClient(app)
        start = client.post(
            "/app/operation-test4/start",
            json={"confirm_live": True, "confirmation": START_CONFIRMATION},
        )
        enable = client.post(
            "/app/operation-test4/enable-live",
            json={"confirm_live": True, "confirmation": ENABLE_CONFIRMATION},
        )
        entry = client.post(
            "/app/operation-test4/entry/run-once",
            json={"confirm_live": True, "confirmation": ENTRY_CONFIRMATION},
        )
    finally:
        app.dependency_overrides.clear()

    assert start.status_code == 200
    assert enable.status_code == 200
    assert entry.status_code == 409
    assert calls == [
        ("start", {"confirm_live": True, "confirmation": START_CONFIRMATION}),
        ("enable", {"confirm_live": True, "confirmation": ENABLE_CONFIRMATION}),
        ("entry", {"confirm_live": True, "confirmation": ENTRY_CONFIRMATION}),
    ]

def test_preflight_separates_preview_display_flags_from_test4_execution_blocks(
    db_session,
    tmp_path,
):
    def candidates(**kwargs):
        return {
            "final_ranked_candidates": [
                {
                    "symbol": "001450",
                    "current_price": 39_700,
                    "final_buy_score": 90,
                    "block_reasons": [
                        "preview_only",
                        "kr_trading_disabled",
                        "trading_disabled",
                    ],
                    "preview_only": True,
                    "kr_trading_disabled": True,
                    "trading_enabled": False,
                    "next_manual_action_hint": "review preview",
                    "risk_flags": [],
                }
            ],
            "final_score_gap": 10,
            "preview_only": True,
            "kr_trading_disabled": True,
            "trading_enabled": False,
            "next_manual_action_hint": "review preview",
        }

    service, _, _ = make_service(tmp_path, candidate=candidates)

    result = service.preflight_once(db_session, now=NOW)

    assert result["action"] == "BUY_READY"
    assert result["analysis_mode"] == "operation_test4_heavy_preflight"
    assert result["execution_decision"] == "BUY_READY"
    assert result["candidate"]["test4_block_reasons"] == []
    assert result["candidate"]["preview_display"] == {
        "preview_only": True,
        "kr_trading_disabled": True,
        "trading_enabled": False,
        "next_manual_action_hint": "review preview",
    }
    assert result["preview"]["preview_only"] is True
    assert result["preview"]["kr_trading_disabled"] is True

def test_start_after_14_00_kst_holds_without_live_arm(
    db_session,
    tmp_path,
    monkeypatch,
):
    service, _, _ = make_service(tmp_path)
    _stub_watchlist_rebuild(monkeypatch)
    RuntimeSettingService().update_settings(
        db_session,
        {"dry_run": True, "kill_switch": True},
    )
    after_cutoff = datetime(2026, 8, 7, 5, 0, tzinfo=UTC)

    result = service.start_full_cycle(
        db_session,
        confirm_live=True,
        confirmation=START_CONFIRMATION,
        now=after_cutoff,
    )
    settings = RuntimeSettingService().get_settings(db_session)

    assert result["status"] == "hold"
    assert result["real_order_submitted"] is False
    assert service.manual_order_service.calls == []
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True
    assert settings["operation_test4_enabled"] is False
def _assert_test4_disarmed(settings: dict) -> None:
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True
    for key in (
        "operation_test4_enabled",
        "operation_test4_scheduler_enabled",
        "operation_test4_allow_real_entry",
        "operation_test4_allow_real_exit",
        "operation_test4_entry_enabled",
        "operation_test4_position_management_enabled",
        "operation_test4_stop_loss_enabled",
        "operation_test4_take_profit_enabled",
    ):
        assert settings[key] is False


def test_start_submit_exception_disarms_and_keeps_reviewable_cycle(
    db_session,
    tmp_path,
    monkeypatch,
):
    manual = FakeManualOrderService(raise_error=TimeoutError("broker timeout"))
    service, _, _ = make_service(tmp_path, manual_service=manual)
    _stub_watchlist_rebuild(monkeypatch)
    RuntimeSettingService().update_settings(
        db_session,
        {"dry_run": True, "kill_switch": True},
    )

    result = service.start_full_cycle(
        db_session,
        confirm_live=True,
        confirmation=START_CONFIRMATION,
        now=NOW,
    )
    cycle = db_session.query(OperationTest4Cycle).one()
    reservation = db_session.query(OperationTest4EntryReservation).one()
    settings = RuntimeSettingService().get_settings(db_session)

    assert result["real_order_submitted"] is False
    assert result["entry"]["reason"] == "entry_submit_exception"
    assert len(manual.calls) == 1
    assert cycle.status == "failed"
    assert cycle.manual_review_required is True
    assert reservation.cycle_id == cycle.id
    assert reservation.submission_attempted is True
    _assert_test4_disarmed(settings)


class _ExplodingLifecycleService:
    def sync_filled_buy(self, db, order, *, now=None):
        raise RuntimeError("lifecycle write failed")


def test_start_filled_buy_lifecycle_failure_disarms_and_requires_manual_review(
    db_session,
    tmp_path,
    monkeypatch,
):
    manual = FakeManualOrderService(status=InternalOrderStatus.FILLED.value)
    service, _, _ = make_service(
        tmp_path,
        manual_service=manual,
        lifecycle_service=_ExplodingLifecycleService(),
    )
    _stub_watchlist_rebuild(monkeypatch)
    RuntimeSettingService().update_settings(
        db_session,
        {"dry_run": True, "kill_switch": True},
    )

    result = service.start_full_cycle(
        db_session,
        confirm_live=True,
        confirmation=START_CONFIRMATION,
        now=NOW,
    )
    cycle = db_session.query(OperationTest4Cycle).one()
    settings = RuntimeSettingService().get_settings(db_session)

    assert result["real_order_submitted"] is True
    assert len(manual.calls) == 1
    assert cycle.status == "review_required"
    assert cycle.manual_review_required is True
    assert "lifecycle" in str(cycle.last_error or "").lower()
    _assert_test4_disarmed(settings)


def test_start_final_recheck_detects_new_broker_position_after_arm(
    db_session,
    tmp_path,
    monkeypatch,
):
    manual = FakeManualOrderService()
    service, _, state = make_service(tmp_path, manual_service=manual)
    _stub_watchlist_rebuild(monkeypatch)
    RuntimeSettingService().update_settings(
        db_session,
        {"dry_run": True, "kill_switch": True},
    )
    original_enable_live = service.enable_live

    def enable_then_inject_position(*args, **kwargs):
        result = original_enable_live(*args, **kwargs)
        if result.get("status") == "live_enabled":
            state["positions"] = [{"symbol": "000001", "qty": 1, "current_price": 20_000}]
        return result

    monkeypatch.setattr(service, "enable_live", enable_then_inject_position)
    result = service.start_full_cycle(
        db_session,
        confirm_live=True,
        confirmation=START_CONFIRMATION,
        now=NOW,
    )
    cycle = db_session.query(OperationTest4Cycle).one()
    settings = RuntimeSettingService().get_settings(db_session)

    assert result["real_order_submitted"] is False
    assert result["entry"]["reason"] == "position_exists"
    assert manual.calls == []
    assert cycle.status == "review_required"
    assert cycle.manual_review_required is True
    _assert_test4_disarmed(settings)


def test_start_blocks_malformed_broker_state_without_runtime_change(
    db_session,
    tmp_path,
    monkeypatch,
):
    service, _, _ = make_service(tmp_path)
    service.account_state_provider = lambda: {
        "fetch_success": True,
        "equity": 1_000_000,
        "positions": "malformed",
        "open_orders": [],
    }
    _stub_watchlist_rebuild(monkeypatch)
    runtime = RuntimeSettingService()
    runtime.update_settings(db_session, {"dry_run": True, "kill_switch": True})

    result = service.start_full_cycle(
        db_session,
        confirm_live=True,
        confirmation=START_CONFIRMATION,
        now=NOW,
    )
    settings = runtime.get_settings(db_session)

    assert result["reason"] == "account_state_unavailable"
    assert result["real_order_submitted"] is False
    assert service.manual_order_service.calls == []
    assert db_session.query(OperationTest4Cycle).count() == 0
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True
    assert settings["operation_test4_enabled"] is False


def test_start_before_09_00_kst_holds_without_live_arm(
    db_session,
    tmp_path,
    monkeypatch,
):
    service, _, _ = make_service(tmp_path)
    _stub_watchlist_rebuild(monkeypatch)
    RuntimeSettingService().update_settings(
        db_session,
        {"dry_run": True, "kill_switch": True},
    )
    before_open = datetime(2026, 8, 6, 23, 59, tzinfo=UTC)

    result = service.start_full_cycle(
        db_session,
        confirm_live=True,
        confirmation=START_CONFIRMATION,
        now=before_open,
    )
    settings = RuntimeSettingService().get_settings(db_session)

    assert result["real_order_submitted"] is False
    assert result["reason"] in {"entry_before_09_00", "entry_time_outside_window"}
    assert service.manual_order_service.calls == []
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True
    assert settings["operation_test4_enabled"] is False
def test_start_blocks_other_live_automation_flags_without_arm(
    db_session,
    tmp_path,
    monkeypatch,
):
    service, _, _ = make_service(tmp_path)
    _stub_watchlist_rebuild(monkeypatch)
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": True,
            "kill_switch": True,
            "automation_release_enabled": True,
            "automation_release_allow_live_phase1": True,
            "automation_release_scheduler_enabled": True,
            "portfolio_orchestrator_allow_live_orders": True,
        },
    )

    result = service.start_full_cycle(
        db_session,
        confirm_live=True,
        confirmation=START_CONFIRMATION,
        now=NOW,
    )
    settings = RuntimeSettingService().get_settings(db_session)

    assert result["status"] == "hold"
    assert result["reason"] == "other_scheduler_live_flags_enabled"
    assert result["real_order_submitted"] is False
    assert service.manual_order_service.calls == []
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True
    assert settings["operation_test4_enabled"] is False
