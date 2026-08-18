from __future__ import annotations

import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.db.models import OperationTest4EntryReservation, TradeRunLog
from app.services.operation_test4_service import (
    REQUIRED_ENTRY_SCORE,
    WEEKLY_CONFIRMATION,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.tests.test_operation_test4_entry import candidate_provider, make_service


KR_TZ = ZoneInfo("Asia/Seoul")


def _kst(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=KR_TZ).astimezone(UTC)


def _fresh_watchlist(*args, **kwargs):
    return {
        "fresh": True,
        "count": 50,
        "configured_count": 50,
        "selected_count": 50,
        "symbols": [{"symbol": f"{index:06d}"} for index in range(1, 51)],
    }


def test_weekly_bad_confirmation_does_not_mutate_runtime(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)

    result = service.arm_week(
        db_session,
        confirm_live=True,
        confirmation="ARM TEST4 WEEK 2026-08-19 TO 2026-08-20",
        now=_kst(18, 18),
    )

    runtime = RuntimeSettingService().get_settings(db_session)
    assert result["reason"] == "operator_confirmation_required"
    assert runtime["operation_test4_weekly_window_enabled"] is False
    assert runtime["dry_run"] is True
    assert runtime["kill_switch"] is False


def test_weekly_arm_persists_exact_range_and_stays_safe_closed(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)

    result = service.arm_week(
        db_session,
        confirm_live=True,
        confirmation=WEEKLY_CONFIRMATION,
        now=_kst(18, 18),
    )
    runtime = RuntimeSettingService().get_settings(db_session)

    assert result["status"] == "armed"
    assert result["weekly_start_date"] == "2026-08-19"
    assert result["weekly_end_date"] == "2026-08-21"
    assert result["current_target_date"] == "2026-08-19"
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert runtime["operation_test4_weekly_window_enabled"] is True
    assert runtime["operation_test4_scheduler_enabled"] is True
    assert runtime["operation_test4_enabled"] is False
    assert runtime["dry_run"] is True
    assert runtime["kill_switch"] is True


def test_weekly_final_slot_preserves_score_reason_and_rolls_target(db_session, tmp_path):
    service, _, _ = make_service(
        tmp_path,
        candidate=lambda **kwargs: candidate_provider(score=64),
    )
    service.arm_week(
        db_session,
        confirm_live=True,
        confirmation=WEEKLY_CONFIRMATION,
        now=_kst(18, 18),
    )
    service._load_watchlist = _fresh_watchlist

    result = service.run_scheduler_once(
        db_session,
        slot_label="13:30",
        now=_kst(19, 13, 30),
    )
    runtime = RuntimeSettingService().get_settings(db_session)

    assert REQUIRED_ENTRY_SCORE == 65
    assert result["action"] == "HOLD"
    assert result["reason"] == "final_score_gate_not_met"
    assert result["entry_slots_complete"] is True
    assert result["session_completion_reason"] == "session_complete"
    assert runtime["operation_test4_weekly_window_enabled"] is True
    assert runtime["operation_test4_target_trading_date"] == "2026-08-20"
    assert runtime["dry_run"] is True
    assert runtime["kill_switch"] is True
    row = db_session.query(TradeRunLog).one()
    history = json.loads(row.response_payload)["slot_history"]
    assert history["slot_kst"] == "13:30"
    assert history["final_buy_score"] == 64
    assert history["required_entry_score"] == 65
    assert history["block_reason"] == "final_score_gate_not_met"
    assert history["entry_slots_complete"] is True


def test_weekly_position_cycle_close_keeps_next_slot_armed(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)
    service.arm_week(
        db_session,
        confirm_live=True,
        confirmation=WEEKLY_CONFIRMATION,
        now=_kst(18, 18),
    )
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": False,
            "kill_switch": False,
            "operation_test4_enabled": True,
            "operation_test4_allow_real_entry": True,
            "operation_test4_allow_real_exit": True,
            "operation_test4_entry_enabled": True,
            "operation_test4_position_management_enabled": True,
            "operation_test4_scheduler_arm_mode": "weekly_active_cycle",
            "operation_test4_target_trading_date": "2026-08-19",
        },
    )

    runtime = service._disarm(
        db_session,
        reason="cycle_completed",
        preserve_next_session=True,
    )

    assert runtime["operation_test4_scheduler_enabled"] is True
    assert runtime["operation_test4_scheduler_arm_mode"] == "weekly_window"
    assert runtime["operation_test4_enabled"] is True
    assert runtime["operation_test4_target_trading_date"] == "2026-08-19"


def test_weekly_rollover_disables_after_august_21(db_session, tmp_path):
    service, _, _ = make_service(
        tmp_path,
        candidate=lambda **kwargs: candidate_provider(score=64),
    )
    service.arm_week(
        db_session,
        confirm_live=True,
        confirmation=WEEKLY_CONFIRMATION,
        now=_kst(18, 18),
    )
    service._load_watchlist = _fresh_watchlist

    for day, expected_target in ((19, "2026-08-20"), (20, "2026-08-21")):
        service.run_scheduler_once(
            db_session,
            slot_label="13:30",
            now=_kst(day, 13, 30),
        )
        assert RuntimeSettingService().get_settings(db_session)[
            "operation_test4_target_trading_date"
        ] == expected_target

    result = service.run_scheduler_once(
        db_session,
        slot_label="13:30",
        now=_kst(21, 13, 30),
    )
    runtime = RuntimeSettingService().get_settings(db_session)

    assert result["entry_slots_complete"] is True
    assert runtime["operation_test4_weekly_window_enabled"] is False
    assert runtime["operation_test4_scheduler_enabled"] is False
    assert runtime["operation_test4_scheduler_arm_mode"] == "weekly_complete"
    assert runtime["operation_test4_target_trading_date"] is None
    assert db_session.query(OperationTest4EntryReservation).count() == 0


def test_account_provider_retries_read_only_only_with_5_and_15_second_delays(
    db_session, tmp_path
):
    service, _, state = make_service(tmp_path)
    calls = {"count": 0}
    delays: list[float] = []

    def provider():
        calls["count"] += 1
        if calls["count"] < 3:
            raise TimeoutError("temporary account read timeout")
        return state

    service.account_state_provider = provider
    service.account_state_sleep = delays.append
    result = service._read_account_state(require_fresh=True)

    assert result["fetch_success"] is True
    assert result["account_state_attempt_count"] == 3
    assert delays == [5.0, 15.0]
