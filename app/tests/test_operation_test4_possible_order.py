from __future__ import annotations

from datetime import timedelta

from app.tests.test_operation_test4_entry import (
    ENTRY_CONFIRMATION,
    NOW,
    FakeManualOrderService,
    arm_for_entry,
    candidate_provider,
    make_service,
)


def _possible(*, cash=996_274, quantity=25, queried_at=None, status="ok"):
    return {
        "raw_status": status,
        "symbol": "000001",
        "order_type": "market",
        "reference_price": 38_650,
        "orderable_cash": cash,
        "orderable_quantity": quantity,
        "queried_at": (queried_at or NOW).isoformat(),
        "error": None if status == "ok" else "possible_order_failed",
    }


def test_preflight_uses_candidate_orderable_cash_and_quantity(db_session, tmp_path):
    service, _, _ = make_service(
        tmp_path,
        account_state={
            "fetch_success": True,
            "equity": 1_001_456,
            "orderable_cash": None,
            "positions": [],
            "open_orders": [],
        },
        candidate=lambda **kwargs: candidate_provider(score=90, price=38_650),
        possible_order=lambda **kwargs: _possible(),
    )
    arm_for_entry(db_session, service)

    result = service.preflight_once(db_session, now=NOW)

    assert result["status"] == "ready"
    assert result["action"] == "BUY_READY"
    assert result["sizing"]["quantity"] == 3
    assert result["sizing"]["estimated_notional"] == 115_950
    assert result["sizing"]["effective_position_pct"] < 100
    assert result["possible_order"]["orderable_cash"] == 996_274


def test_preflight_blocks_when_one_share_exceeds_orderable_cash(db_session, tmp_path):
    service, _, _ = make_service(
        tmp_path,
        candidate=lambda **kwargs: candidate_provider(score=90, price=999_000),
        possible_order=lambda **kwargs: _possible(cash=996_274, quantity=1),
    )
    arm_for_entry(db_session, service)

    result = service.preflight_once(db_session, now=NOW)

    assert result["action"] == "HOLD"
    assert "quantity_less_than_one" in result["blocking_reasons"]


def test_preflight_blocks_zero_broker_orderable_quantity(db_session, tmp_path):
    service, _, _ = make_service(
        tmp_path,
        candidate=lambda **kwargs: candidate_provider(score=90, price=38_650),
        possible_order=lambda **kwargs: _possible(quantity=0),
    )
    arm_for_entry(db_session, service)

    result = service.preflight_once(db_session, now=NOW)

    assert result["action"] == "HOLD"
    assert "orderable_quantity_unavailable" in result["blocking_reasons"]


def test_score_gate_stays_hold_when_possible_order_is_sufficient(db_session, tmp_path):
    manual = FakeManualOrderService()
    service, _, _ = make_service(
        tmp_path,
        manual_service=manual,
        candidate=lambda **kwargs: candidate_provider(score=61.75, price=38_650),
        possible_order=lambda **kwargs: _possible(),
    )
    arm_for_entry(db_session, service)

    result = service.preflight_once(db_session, now=NOW)

    assert result["action"] == "HOLD"
    assert "final_score_gate_not_met" in result["blocking_reasons"]
    assert manual.calls == []


def test_possible_order_failure_is_reviewable_and_entry_does_not_submit(db_session, tmp_path):
    manual = FakeManualOrderService()
    service, _, _ = make_service(
        tmp_path,
        manual_service=manual,
        candidate=lambda **kwargs: candidate_provider(score=90, price=38_650),
        possible_order=lambda **kwargs: _possible(status="error"),
    )
    arm_for_entry(db_session, service)

    preflight = service.preflight_once(db_session, now=NOW)
    entry = service.entry_run_once(
        db_session,
        confirm_live=True,
        confirmation=ENTRY_CONFIRMATION,
        now=NOW,
    )

    assert preflight["action"] == "HOLD"
    assert "possible_order_unavailable" in preflight["blocking_reasons"]
    assert entry["real_order_submitted"] is False
    assert manual.calls == []


def test_stale_preflight_possible_order_blocks_entry_without_retry_submit(db_session, tmp_path):
    manual = FakeManualOrderService()
    service, _, _ = make_service(
        tmp_path,
        manual_service=manual,
        candidate=lambda **kwargs: candidate_provider(score=90, price=38_650),
        possible_order=lambda **kwargs: _possible(queried_at=NOW - timedelta(seconds=11)),
    )
    arm_for_entry(db_session, service)

    result = service.entry_run_once(
        db_session,
        confirm_live=True,
        confirmation=ENTRY_CONFIRMATION,
        now=NOW,
    )

    assert result["reason"] == "possible_order_snapshot_stale"
    assert manual.calls == []