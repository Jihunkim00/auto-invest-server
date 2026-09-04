from __future__ import annotations

from app.services.compound_capital_service import CompoundCapitalService


class _PerformanceStub:
    def __init__(self, realized: float) -> None:
        self.realized = realized
        self.calls = 0

    def profile_realized_pnl(self, db, *, profile_key, provider, market):
        self.calls += 1
        return {
            "cumulative_realized_pnl_krw": self.realized,
            "eligible_closed_trade_count": 1,
            "unresolved_realized_pnl_count": 0,
        }


def _calculate(db_session, *, realized=0.0, **overrides):
    performance = _PerformanceStub(realized)
    values = {
        "profile_key": "aut_kis_eec5f898",
        "initial_budget_krw": 300_000,
        "fixed_budget_krw": 300_000,
        "compound_enabled": False,
        "compound_basis": "realized_pnl",
        "configured_max_order_notional_krw": 500_000,
    }
    values.update(overrides)
    result = CompoundCapitalService(performance_service=performance).calculate(
        db_session,
        **values,
    )
    return result, performance


def test_compound_off_keeps_fixed_budget_and_does_not_read_pnl(db_session):
    result, performance = _calculate(
        db_session,
        realized=20_000,
        broker_orderable_cash_krw=400_000,
    )

    assert result["compound_enabled"] is False
    assert result["current_strategy_budget_krw"] == 300_000
    assert result["cumulative_realized_pnl_krw"] == 0
    assert result["effective_next_entry_budget_krw"] == 300_000
    assert performance.calls == 0


def test_compound_on_adds_positive_realized_pnl(db_session):
    result, performance = _calculate(
        db_session,
        realized=20_000,
        compound_enabled=True,
        broker_orderable_cash_krw=400_000,
    )

    assert result["current_strategy_budget_krw"] == 320_000
    assert result["effective_next_entry_budget_krw"] == 320_000
    assert result["calculation_source"] == "initial_budget_plus_cumulative_realized_pnl"
    assert performance.calls == 1


def test_compound_on_applies_negative_realized_pnl(db_session):
    result, _ = _calculate(
        db_session,
        realized=-10_000,
        compound_enabled=True,
        broker_orderable_cash_krw=400_000,
    )

    assert result["current_strategy_budget_krw"] == 290_000
    assert result["effective_next_entry_budget_krw"] == 290_000


def test_compound_budget_is_capped_by_broker_cash_and_zero_blocks(db_session):
    below, _ = _calculate(
        db_session,
        compound_enabled=True,
        broker_orderable_cash_krw=250_000,
    )
    above, _ = _calculate(
        db_session,
        compound_enabled=True,
        broker_orderable_cash_krw=800_000,
    )
    zero, _ = _calculate(
        db_session,
        compound_enabled=True,
        broker_orderable_cash_krw=0,
    )

    assert below["effective_next_entry_budget_krw"] == 250_000
    assert above["effective_next_entry_budget_krw"] == 300_000
    assert zero["effective_next_entry_budget_krw"] == 0


def test_unknown_compound_basis_fails_closed_to_fixed_budget(db_session):
    result, performance = _calculate(
        db_session,
        realized=20_000,
        compound_enabled=True,
        compound_basis="unrealized_pnl",
        broker_orderable_cash_krw=400_000,
    )

    assert result["compound_enabled"] is False
    assert result["compound_basis"] is None
    assert result["current_strategy_budget_krw"] == 300_000
    assert performance.calls == 0