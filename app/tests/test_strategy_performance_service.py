from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import OrderLog, StrategyPerformanceSnapshot
from app.services.strategy_performance_service import StrategyPerformanceService
from app.services.strategy_profile_service import StrategyProfileService


def test_daily_performance_returns_zero_safe_result_when_no_orders(db_session):
    result = _service().daily(db_session)

    assert result["realized_pnl"] == 0
    assert result["unrealized_pnl"] == 0
    assert result["orders_count"] == 0
    assert result["safety"]["real_order_submitted"] is False
    assert result["safety"]["validation_called"] is False


def test_monthly_performance_returns_active_profile_target_fields(db_session):
    result = _service().monthly(db_session)

    assert result["active_profile"]["profile_name"] == "safe"
    assert result["monthly_target_min_pct"] == 0.01
    assert result["monthly_target_max_pct"] == 0.02
    assert result["monthly_max_loss_pct"] == -0.02


def test_filled_buy_without_sell_is_open_not_realized(db_session):
    db_session.add(_order(side="buy", price=100, qty=2))
    db_session.commit()

    result = _service().trades(db_session)

    assert result["items"][0]["status"] == "open"
    assert result["items"][0]["realized_pnl"] is None
    assert _service().monthly(db_session)["realized_pnl"] == 0


def test_filled_buy_sell_pair_calculates_realized_pnl_and_fee_separately(
    db_session,
):
    db_session.add_all(
        [
            _order(side="buy", price=100, qty=2, minutes_ago=10),
            _order(side="sell", price=110, qty=2, minutes_ago=5),
        ]
    )
    db_session.commit()

    result = _service().monthly(db_session)

    assert result["realized_pnl"] == 20
    assert result["estimated_fees"] > 0
    assert result["gross_pnl"] == 20
    assert result["net_pnl_estimated"] < result["gross_pnl"]
    assert result["winning_trades_count"] == 1


def test_missing_fill_price_sets_warning_and_no_fake_profit(db_session):
    db_session.add(_order(side="buy", price=None, qty=1))
    db_session.commit()

    trades = _service().trades(db_session)

    assert trades["items"][0]["status"] == "average_price_missing"
    assert trades["items"][0]["realized_pnl"] is None
    assert "average_price_missing" in trades["data_quality"]["notes"]


def test_unmatched_sell_does_not_create_fake_profit(db_session):
    db_session.add(_order(side="sell", price=120, qty=1))
    db_session.commit()

    trades = _service().trades(db_session)

    assert trades["items"][0]["status"] == "unmatched_sell"
    assert trades["items"][0]["realized_pnl"] is None
    assert trades["data_quality"]["unmatched_orders_count"] == 1
    assert _service().monthly(db_session)["realized_pnl"] == 0


def test_unrealized_pnl_uses_position_cost_basis(db_session):
    service = _service(
        positions=[
            {
                "symbol": "005930",
                "qty": 2,
                "cost_basis": 100000,
                "market_value": 110000,
                "current_price": 55000,
                "unrealized_pl": 10000,
            }
        ]
    )

    result = service.monthly(db_session)

    assert result["unrealized_pnl"] == 10000
    assert result["current_month_return_pct"] == pytest.approx(0.1)
    assert result["data_quality"]["missing_cost_basis"] is False


def test_missing_cost_basis_marks_insufficient_data(db_session):
    result = _service(
        positions=[
            {
                "symbol": "005930",
                "qty": 1,
                "current_price": 50000,
                "unrealized_pl": -1000,
            }
        ]
    ).monthly(db_session)

    assert result["data_quality"]["missing_cost_basis"] is True
    assert "insufficient_cost_basis" in result["data_quality"]["notes"]
    assert result["current_month_return_pct"] == 0


def test_target_and_loss_budget_progress_flags(db_session):
    target = _service(
        positions=[
            {
                "symbol": "005930",
                "qty": 1,
                "cost_basis": 100000,
                "market_value": 102000,
                "unrealized_pl": 2000,
            }
        ]
    ).monthly(db_session)
    loss = _service(
        positions=[
            {
                "symbol": "005930",
                "qty": 1,
                "cost_basis": 100000,
                "market_value": 97000,
                "unrealized_pl": -3000,
            }
        ]
    ).monthly(db_session)

    assert target["target_progress_pct"] == pytest.approx(133.333333)
    assert target["target_hit"] is True
    assert loss["loss_budget_used_pct"] == 150
    assert loss["loss_limit_hit"] is True
    assert loss["new_entries_allowed_by_target"] is False


def test_target_hit_respects_profile_stop_policy(db_session):
    profiles = StrategyProfileService()
    profiles.apply_preset(
        db_session,
        profile_name="balanced",
        confirm_operator_ack=True,
        source="test",
    )
    result = StrategyPerformanceService(
        position_loader=lambda db, provider, market: [
            {
                "symbol": "005930",
                "qty": 1,
                "cost_basis": 100000,
                "market_value": 104000,
                "unrealized_pl": 4000,
            }
        ],
        strategy_profiles=profiles,
    ).monthly(db_session)

    assert result["target_hit"] is True
    assert result["active_profile"]["stop_after_monthly_target"] is False
    assert result["new_entries_allowed_by_target"] is True
    assert result["new_entries_block_reason"] is None


def test_snapshot_saves_sanitized_read_only_result(db_session):
    result = _service().snapshot(db_session, period_type="monthly")

    row = db_session.query(StrategyPerformanceSnapshot).one()
    assert result["status"] == "saved"
    assert row.period_type == "monthly"
    assert "appsecret" not in (row.source_payload or "").lower()
    assert result["safety"]["real_order_submitted"] is False
    assert result["safety"]["validation_called"] is False
    assert result["safety"]["scheduler_changed"] is False


def _service(*, positions=None):
    return StrategyPerformanceService(
        position_loader=lambda db, provider, market: list(positions or []),
    )


def _order(
    *,
    side: str,
    price: float | None,
    qty: float,
    minutes_ago: int = 1,
) -> OrderLog:
    timestamp = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return OrderLog(
        broker="kis",
        market="KR",
        symbol="005930",
        side=side,
        order_type="market",
        qty=qty,
        requested_qty=qty,
        filled_qty=qty,
        remaining_qty=0,
        avg_fill_price=price,
        filled_avg_price=price,
        internal_status="FILLED",
        created_at=timestamp,
        submitted_at=timestamp,
        filled_at=timestamp,
    )
