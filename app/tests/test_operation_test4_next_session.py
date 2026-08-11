from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.services.market_session_service import MarketSessionService
from app.db.database import get_db
from app.main import app
from app.routes.operation_test4 import get_operation_test4_service
from app.services.operation_test4_service import HOLD
from app.db.models import OperationTest4Cycle, OperationTest4EntryReservation, OrderLog, PositionLifecycle
from app.services.runtime_setting_service import RuntimeSettingService
from app.tests.test_operation_test4_entry import FakeManualOrderService, NOW, candidate_provider, make_service


KR_TZ = ZoneInfo("Asia/Seoul")


def _target_now(hour: int, minute: int) -> datetime:
    return datetime(2026, 8, 10, hour, minute, tzinfo=KR_TZ).astimezone(UTC)


def _fresh_watchlist(*args, **kwargs):
    return {
        "fresh": True,
        "count": 50,
        "configured_count": 50,
        "selected_count": 50,
        "symbols": [{"symbol": f"{index:06d}"} for index in range(1, 51)],
    }


def test_next_session_arm_persists_target_without_live_flags(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)

    result = service.arm_next_session(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 NEXT SESSION",
        now=NOW,
    )

    assert result["status"] == "armed"
    assert isinstance(result["runtime"]["operation_test4_scheduler_armed_at"], datetime)
    assert result["target_trading_date"] == "2026-08-10"
    assert result["next_entry_slot_kst"] == "09:35"
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False

    runtime = RuntimeSettingService().get_settings(db_session)
    assert runtime["operation_test4_scheduler_arm_mode"] == "next_session"
    assert runtime["operation_test4_target_trading_date"] == "2026-08-10"
    assert runtime["operation_test4_scheduler_enabled"] is True
    assert runtime["operation_test4_enabled"] is False
    assert runtime["operation_test4_allow_real_entry"] is False
    assert runtime["dry_run"] is True
    assert runtime["kill_switch"] is True
    assert runtime["scheduler_enabled"] is False


def test_arm_next_session_route_json_encodes_datetime_and_preserves_state(
    db_session,
    tmp_path,
):
    service, _, _ = make_service(tmp_path)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_operation_test4_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/app/operation-test4/scheduler/arm-next-session",
            json={
                "confirm": True,
                "confirmation": "ARM TEST4 NEXT SESSION",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    armed_at = body["runtime"]["operation_test4_scheduler_armed_at"]
    next_run = body["next_automatic_entry_run"]
    assert isinstance(armed_at, str)
    assert datetime.fromisoformat(armed_at).tzinfo is not None
    assert isinstance(body["target_trading_date"], str)
    assert body["target_trading_date"] == body["runtime"]["operation_test4_target_trading_date"]
    assert isinstance(next_run, str)
    assert datetime.fromisoformat(next_run).tzinfo is not None

    runtime = RuntimeSettingService().get_settings(db_session)
    assert runtime["operation_test4_scheduler_arm_mode"] == "next_session"
    assert runtime["operation_test4_scheduler_enabled"] is True
    assert runtime["operation_test4_target_trading_date"] == body["target_trading_date"]
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert service.manual_order_service.calls == []
    assert db_session.query(OrderLog).count() == 0

def test_next_session_status_survives_service_restart(db_session, tmp_path):
    service, client, state = make_service(tmp_path)
    service.arm_next_session(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 NEXT SESSION",
        now=NOW,
    )

    restarted = service.__class__(
        client,
        session_service=service.session_service,
        watchlist_path=service.watchlist_path,
        account_state_provider=lambda: state,
        now_provider=lambda: NOW,
    )
    status = restarted.status(db_session, now=NOW)

    assert status["scheduler"]["test4_scheduler_armed"] is True
    assert status["scheduler"]["arm_mode"] == "next_session"
    assert status["scheduler"]["target_trading_date"] == "2026-08-10"
    assert status["scheduler"]["next_entry_slot_kst"] == "09:35"
    assert status["scheduler"]["automatic_entry_status"] == "armed_for_next_session"


def test_next_session_before_target_date_does_not_evaluate_or_submit(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)
    service.arm_next_session(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 NEXT SESSION",
        now=NOW,
    )
    service.preflight_once = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("preflight must wait for the target session")
    )

    result = service.run_scheduler_once(
        db_session,
        slot_label="09:35",
        now=NOW,
    )

    assert result["reason"] == "waiting_for_target_trading_date"
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False


def _fresh_possible_order(service, now):
    service.possible_order_provider = lambda **kwargs: {
        "raw_status": "ok",
        "symbol": kwargs["symbol"],
        "order_type": "market",
        "reference_price": kwargs["order_price"],
        "orderable_cash": 1_000_000,
        "orderable_quantity": 100,
        "queried_at": now.isoformat(),
        "error": None,
    }
def test_next_session_buy_ready_uses_existing_guarded_submit_once(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)
    service.arm_next_session(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 NEXT SESSION",
        now=NOW,
    )
    service._load_watchlist = _fresh_watchlist
    now = _target_now(9, 35)
    _fresh_possible_order(service, now)
    manual = service.manual_order_service

    result = service.run_scheduler_once(
        db_session,
        slot_label="09:35",
        now=now,
    )

    cycle = db_session.query(OperationTest4Cycle).one()
    runtime = RuntimeSettingService().get_settings(db_session)
    assert result["action"] == "BUY_READY"
    assert result["reason"] == "entry_submitted"
    assert result["submit_path"] == "operation_test4_existing_guarded_entry"
    assert result["live_execution_permission"] is True
    assert result["real_order_submitted"] is True
    assert result["broker_submit_called"] is True
    order = db_session.get(OrderLog, cycle.entry_order_id)
    assert len(manual.calls) == 1
    assert order is not None
    assert order.kis_odno == "KIS-TEST4-ENTRY"
    assert cycle.status == "entry_pending"
    assert runtime["operation_test4_scheduler_arm_mode"] == "active_cycle"
    assert runtime["dry_run"] is False
    assert runtime["kill_switch"] is False


def test_next_session_duplicate_tick_does_not_submit_again(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)
    service.arm_next_session(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 NEXT SESSION",
        now=NOW,
    )
    service._load_watchlist = _fresh_watchlist
    now = _target_now(9, 35)
    _fresh_possible_order(service, now)
    manual = service.manual_order_service

    first = service.run_scheduler_once(db_session, slot_label="09:35", now=now)

    class EchoOrderSync:
        def sync_order(self, db, order_id):
            return db.get(OrderLog, order_id)

    service.order_sync_service = EchoOrderSync()
    second = service.run_scheduler_once(db_session, slot_label="09:35", now=now)

    assert first["real_order_submitted"] is True
    assert second["result"] == "reconciled"
    assert len(manual.calls) == 1
    assert db_session.query(OperationTest4EntryReservation).count() == 1


def test_next_session_filled_buy_promotes_to_position_lifecycle(db_session, tmp_path):
    service, _, state = make_service(
        tmp_path,
        manual_service=FakeManualOrderService(status="FILLED"),
    )
    service.arm_next_session(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 NEXT SESSION",
        now=NOW,
    )
    service._load_watchlist = _fresh_watchlist
    _fresh_possible_order(service, _target_now(9, 35))

    result = service.run_scheduler_once(
        db_session,
        slot_label="09:35",
        now=_target_now(9, 35),
    )

    cycle = db_session.query(OperationTest4Cycle).one()
    runtime = RuntimeSettingService().get_settings(db_session)
    assert result["reason"] == "entry_submitted"
    assert cycle.status == "position_open"
    assert db_session.query(PositionLifecycle).count() == 1
    assert runtime["operation_test4_scheduler_arm_mode"] == "active_cycle"
    assert runtime["operation_test4_allow_real_entry"] is False
    assert runtime["operation_test4_position_management_enabled"] is True

    state["positions"] = [{
        "symbol": "000001",
        "qty": 5,
        "avg_entry_price": 20_000,
        "current_price": 20_000,
    }]
    later_slot = service.run_scheduler_once(
        db_session,
        slot_label="11:30",
        now=_target_now(11, 30),
    )
    assert later_slot["reason"] == HOLD
    assert len(service.manual_order_service.calls) == 1


def test_next_session_cycle_close_preserves_later_slot_for_next_buy(db_session, tmp_path):
    service, _, state = make_service(
        tmp_path,
        manual_service=FakeManualOrderService(status="FILLED"),
    )
    service.arm_next_session(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 NEXT SESSION",
        now=NOW,
    )
    service._load_watchlist = _fresh_watchlist
    first_now = _target_now(9, 35)
    _fresh_possible_order(service, first_now)
    first = service.run_scheduler_once(
        db_session,
        slot_label="09:35",
        now=first_now,
    )
    assert first["reason"] == "entry_submitted"
    state["positions"] = [{
        "symbol": "000001",
        "qty": 5,
        "avg_entry_price": 20_000,
        "current_price": 19_000,
    }]

    class FakeFilledSellService:
        calls = 0

        def run_once(self, db, *, now=None):
            self.calls += 1
            row = OrderLog(
                broker="kis",
                market="KR",
                symbol="000001",
                side="sell",
                order_type="market",
                qty=5,
                requested_qty=5,
                filled_qty=5,
                remaining_qty=0,
                avg_fill_price=19_000,
                internal_status="FILLED",
                broker_order_id="KIS-TEST4-EXIT",
                kis_odno="KIS-TEST4-EXIT",
                request_payload='{"operation_test":"test4","order_source":"operation_test4_auto_stop_loss"}',
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            state["positions"] = []
            state["open_orders"] = []
            return {
                "real_order_submitted": True,
                "broker_submit_called": True,
                "manual_submit_called": True,
                "order_id": row.id,
                "order_log_id": row.id,
                "internal_status": "FILLED",
            }

    sell = FakeFilledSellService()
    service.limited_auto_sell_service = sell
    closed = service.run_scheduler_once(
        db_session,
        slot_label="10:00",
        now=_target_now(10, 0),
    )
    runtime_after_close = RuntimeSettingService().get_settings(db_session)
    assert closed["close"]["closed"] is True
    assert sell.calls == 1
    assert runtime_after_close["operation_test4_scheduler_arm_mode"] == "next_session"
    assert runtime_after_close["operation_test4_scheduler_enabled"] is True
    assert runtime_after_close["dry_run"] is True
    assert runtime_after_close["kill_switch"] is True

    first_order = db_session.query(OrderLog).filter(OrderLog.side == "buy").one()
    first_order.broker_order_id = "KIS-TEST4-ENTRY-FIRST"
    first_order.kis_odno = "KIS-TEST4-ENTRY-FIRST"
    db_session.commit()

    second_now = _target_now(11, 30)
    _fresh_possible_order(service, second_now)
    second = service.run_scheduler_once(
        db_session,
        slot_label="11:30",
        now=second_now,
    )
    assert second["reason"] == "entry_submitted"
    assert len(service.manual_order_service.calls) == 2
    assert db_session.query(OperationTest4EntryReservation).count() == 2

def test_next_session_last_slot_buy_marks_session_complete_while_managing_cycle(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)
    service.arm_next_session(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 NEXT SESSION",
        now=NOW,
    )
    service._load_watchlist = _fresh_watchlist
    now = _target_now(13, 30)
    _fresh_possible_order(service, now)

    result = service.run_scheduler_once(
        db_session,
        slot_label="13:30",
        now=now,
    )
    runtime = RuntimeSettingService().get_settings(db_session)

    assert result["reason"] == "entry_submitted"
    assert runtime["operation_test4_scheduler_last_stage"] == "session_complete"
    assert runtime["operation_test4_scheduler_arm_mode"] == "active_cycle"
    assert runtime["operation_test4_scheduler_enabled"] is True

def test_next_session_hold_keeps_arm_until_last_slot_then_completes(db_session, tmp_path):
    service, _, _ = make_service(
        tmp_path,
        candidate=lambda **kwargs: candidate_provider(score=64),
    )
    service.arm_next_session(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 NEXT SESSION",
        now=NOW,
    )
    service._load_watchlist = _fresh_watchlist

    first = service.run_scheduler_once(
        db_session,
        slot_label="09:35",
        now=_target_now(9, 35),
    )
    assert first["action"] == HOLD
    assert first["reason"] == "final_score_gate_not_met"
    assert RuntimeSettingService().get_settings(db_session)[
        "operation_test4_scheduler_enabled"
    ] is True

    last = service.run_scheduler_once(
        db_session,
        slot_label="13:30",
        now=_target_now(13, 30),
    )
    assert last["reason"] == "session_complete"
    runtime = RuntimeSettingService().get_settings(db_session)
    assert runtime["operation_test4_scheduler_enabled"] is False
    assert runtime["operation_test4_scheduler_arm_mode"] == "session_complete"
    assert runtime["dry_run"] is True
    assert runtime["kill_switch"] is True


def test_next_session_account_unavailable_is_fail_closed(db_session, tmp_path):
    service, _, state = make_service(tmp_path)
    service.arm_next_session(
        db_session,
        confirm=True,
        confirmation="ARM TEST4 NEXT SESSION",
        now=NOW,
    )
    state["fetch_success"] = False

    result = service.run_scheduler_once(
        db_session,
        slot_label="09:35",
        now=_target_now(9, 35),
    )

    assert result["reason"] == "account_state_unavailable"
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False


def test_next_valid_kr_session_skips_weekend_and_holiday():
    service = MarketSessionService()
    friday = datetime(2026, 8, 14, 12, 0, tzinfo=KR_TZ)
    assert service.get_next_valid_trading_date("KR", friday).isoformat() == "2026-08-18"