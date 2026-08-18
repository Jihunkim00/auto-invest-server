from __future__ import annotations

from app.db.models import OperationTest4Cycle, OrderLog, PositionLifecycle
from app.services.operation_test4_service import (
    ENTRY_CONFIRMATION,
    OperationTest4Service,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.tests.test_operation_test4_entry import (
    NOW,
    FakeManualOrderService,
    arm_for_entry,
    make_service,
)


class EchoOrderSync:
    def sync_order(self, db, order_id):
        return db.get(OrderLog, order_id)


class FailedLifecycleService:
    def sync_filled_buy(self, db, order, *, now=None):
        return {"created": False, "reason": "lifecycle_insert_failed"}


def _run_entry(db_session, service):
    return service.entry_run_once(
        db_session,
        confirm_live=True,
        confirmation=ENTRY_CONFIRMATION,
        now=NOW,
    )


def test_filled_entry_creates_lifecycle_and_locks_entry(db_session, tmp_path):
    service, _, state = make_service(
        tmp_path,
        manual_service=FakeManualOrderService(status="FILLED"),
    )
    arm_for_entry(db_session, service)

    result = _run_entry(db_session, service)
    cycle = db_session.query(OperationTest4Cycle).one()
    lifecycle = db_session.query(PositionLifecycle).one()
    settings = RuntimeSettingService().get_settings(db_session)

    assert result["reason"] == "entry_submitted"
    assert cycle.status == "position_open"
    assert cycle.entry_filled_quantity == 5
    assert cycle.entry_average_fill_price == 20_000
    assert lifecycle.quantity == 5
    assert lifecycle.status == "open"
    assert settings["operation_test4_allow_real_entry"] is False
    assert settings["operation_test4_entry_enabled"] is False
    assert settings["operation_test4_allow_real_exit"] is True
    assert settings["operation_test4_position_management_enabled"] is True
    assert state["positions"] == []


def test_pending_entry_does_not_create_lifecycle_and_reconcile_promotes_once(db_session, tmp_path):
    service, _, _ = make_service(tmp_path, manual_service=FakeManualOrderService())
    service.order_sync_service = EchoOrderSync()
    arm_for_entry(db_session, service)

    _run_entry(db_session, service)
    assert db_session.query(PositionLifecycle).count() == 0
    cycle = db_session.query(OperationTest4Cycle).one()
    order = db_session.get(OrderLog, cycle.entry_order_id)
    order.internal_status = "FILLED"
    order.filled_qty = 5
    order.remaining_qty = 0
    order.avg_fill_price = 20_000
    order.filled_avg_price = 20_000
    db_session.commit()

    result = service.reconcile_once(db_session, now=NOW)

    assert result["cycle"]["status"] == "position_open"
    assert db_session.query(PositionLifecycle).count() == 1


def test_rejected_entry_disarms_without_retry(db_session, tmp_path):
    manual = FakeManualOrderService(status="REJECTED")
    service, _, _ = make_service(tmp_path, manual_service=manual)
    service.order_sync_service = EchoOrderSync()
    arm_for_entry(db_session, service)

    _run_entry(db_session, service)
    service.reconcile_once(db_session, now=NOW)
    settings = RuntimeSettingService().get_settings(db_session)
    cycle = db_session.query(OperationTest4Cycle).one()

    assert len(manual.calls) == 1
    assert cycle.status == "failed"
    assert settings["operation_test4_enabled"] is False
    assert settings["kill_switch"] is True


def test_unknown_entry_status_requires_review_and_disarms(db_session, tmp_path):
    manual = FakeManualOrderService(status="UNKNOWN_STALE")
    service, _, _ = make_service(tmp_path, manual_service=manual)
    service.order_sync_service = EchoOrderSync()
    arm_for_entry(db_session, service)

    _run_entry(db_session, service)
    service.reconcile_once(db_session, now=NOW)
    cycle = db_session.query(OperationTest4Cycle).one()
    settings = RuntimeSettingService().get_settings(db_session)

    assert cycle.status == "review_required"
    assert cycle.manual_review_required is True
    assert settings["operation_test4_enabled"] is False
    assert settings["kill_switch"] is True


def test_lifecycle_creation_failure_keeps_cycle_reviewable_and_disarms(db_session, tmp_path):
    service, _, _ = make_service(
        tmp_path,
        manual_service=FakeManualOrderService(status="FILLED"),
        lifecycle_service=FailedLifecycleService(),
    )
    arm_for_entry(db_session, service)

    _run_entry(db_session, service)
    cycle = db_session.query(OperationTest4Cycle).one()
    settings = RuntimeSettingService().get_settings(db_session)

    assert cycle.status == "review_required"
    assert cycle.manual_review_required is True
    assert settings["kill_switch"] is True
    assert db_session.query(PositionLifecycle).count() == 0


def test_restart_recovers_active_cycle_from_sqlite(db_session, tmp_path):
    service, client, state = make_service(
        tmp_path,
        manual_service=FakeManualOrderService(status="FILLED"),
    )
    arm_for_entry(db_session, service)
    _run_entry(db_session, service)

    restarted = OperationTest4Service(
        client,
        runtime_settings=RuntimeSettingService(),
        session_service=service.session_service,
        watchlist_path=service.watchlist_path,
        account_state_provider=lambda: state,
        candidate_provider=lambda **kwargs: {"final_ranked_candidates": [], "watchlist": []},
        now_provider=lambda: NOW,
    )

    status = restarted.status(db_session, now=NOW)

    assert status["cycle"]["status"] == "position_open"