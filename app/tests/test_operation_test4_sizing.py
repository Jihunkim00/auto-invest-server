from app.services.operation_test4_sizing import (
    calculate_operation_test4_sizing,
)


def test_operation_test4_sizing_price_examples():
    prices_and_quantities = (
        (20_000, 5),
        (90_000, 2),
        (400_000, 1),
        (999_000, 1),
    )

    for price, expected_quantity in prices_and_quantities:
        result = calculate_operation_test4_sizing(
            equity=1_000_000,
            orderable_cash=1_000_000,
            current_price=price,
        )

        assert result.allowed is True
        assert result.quantity == expected_quantity
        assert isinstance(result.quantity, int)
        assert result.estimated_notional <= 1_000_000
        assert result.effective_position_pct <= 100


def test_operation_test4_price_cap_is_exclusive():
    at_cap = calculate_operation_test4_sizing(
        equity=1_000_000,
        orderable_cash=1_000_000,
        current_price=1_000_000,
    )
    above_cap = calculate_operation_test4_sizing(
        equity=1_000_000,
        orderable_cash=1_000_000,
        current_price=1_100_000,
    )

    assert at_cap.reason == "price_cap_exceeded"
    assert above_cap.reason == "price_cap_exceeded"


def test_operation_test4_sizing_reduces_to_orderable_cash_without_fractional_shares():
    result = calculate_operation_test4_sizing(
        equity=1_000_000,
        orderable_cash=50_000,
        current_price=20_000,
    )

    assert result.allowed is True
    assert result.quantity == 2
    assert result.estimated_notional == 40_000
    assert result.quantity * result.current_price <= result.orderable_cash


def test_operation_test4_sizing_blocks_when_one_share_does_not_fit():
    result = calculate_operation_test4_sizing(
        equity=1_000_000,
        orderable_cash=50_000,
        current_price=60_000,
    )

    assert result.allowed is False
    assert result.reason == "quantity_less_than_one"


def test_operation_test4_sizing_blocks_broker_quantity_limit():
    result = calculate_operation_test4_sizing(
        equity=1_000_000,
        orderable_cash=1_000_000,
        current_price=20_000,
        broker_orderable_qty=3,
    )

    assert result.allowed is False
    assert result.reason == "quantity_exceeds_broker_orderable_qty"