from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor, isfinite
from typing import Any


DEFAULT_MIN_POSITION_PCT = 10.0
DEFAULT_MAX_POSITION_PCT = 100.0
DEFAULT_MAX_ORDER_NOTIONAL_KRW = 1_000_000.0
DEFAULT_PRICE_CAP_KRW = 1_000_000.0


@dataclass(frozen=True)
class OperationTest4SizingResult:
    status: str
    reason: str | None
    equity: float
    orderable_cash: float
    current_price: float
    min_notional: float
    max_notional: float
    minimum_qty: int
    quantity: int
    estimated_notional: float
    effective_position_pct: float
    broker_orderable_qty: int | None = None

    @property
    def allowed(self) -> bool:
        return self.status == "ready"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "equity": self.equity,
            "orderable_cash": self.orderable_cash,
            "current_price": self.current_price,
            "min_notional": self.min_notional,
            "max_notional": self.max_notional,
            "minimum_qty": self.minimum_qty,
            "quantity": self.quantity,
            "estimated_notional": self.estimated_notional,
            "effective_position_pct": self.effective_position_pct,
            "broker_orderable_qty": self.broker_orderable_qty,
        }


def calculate_operation_test4_sizing(
    *,
    equity: float,
    orderable_cash: float,
    current_price: float,
    min_position_pct: float = DEFAULT_MIN_POSITION_PCT,
    max_position_pct: float = DEFAULT_MAX_POSITION_PCT,
    max_order_notional_krw: float = DEFAULT_MAX_ORDER_NOTIONAL_KRW,
    price_cap_krw: float = DEFAULT_PRICE_CAP_KRW,
    broker_orderable_qty: float | int | None = None,
    allow_single_share_budget_bump: bool = True,
) -> OperationTest4SizingResult:
    """Calculate a whole-share Test4 order without contacting a broker."""
    equity_value = _number(equity)
    cash_value = _number(orderable_cash)
    price_value = _number(current_price)
    min_pct = _number(min_position_pct)
    max_pct = _number(max_position_pct)
    notional_cap = _number(max_order_notional_krw)
    price_cap = _number(price_cap_krw)
    broker_qty = _whole_quantity_or_none(broker_orderable_qty)

    min_notional = max(0.0, equity_value * min_pct / 100.0)
    max_notional = min(
        max(0.0, equity_value * max_pct / 100.0),
        max(0.0, cash_value),
        max(0.0, notional_cap),
    )

    if equity_value <= 0:
        return _blocked("equity_not_positive", equity_value, cash_value, price_value, min_notional, max_notional, broker_qty)
    if cash_value <= 0:
        return _blocked("orderable_cash_not_positive", equity_value, cash_value, price_value, min_notional, max_notional, broker_qty)
    if price_value <= 0:
        return _blocked("current_price_not_positive", equity_value, cash_value, price_value, min_notional, max_notional, broker_qty)
    if price_value >= price_cap:
        return _blocked("price_cap_exceeded", equity_value, cash_value, price_value, min_notional, max_notional, broker_qty)
    if min_pct < 0 or max_pct <= 0 or min_pct > max_pct:
        return _blocked("position_pct_range_invalid", equity_value, cash_value, price_value, min_notional, max_notional, broker_qty)
    if notional_cap <= 0:
        return _blocked("order_notional_cap_not_positive", equity_value, cash_value, price_value, min_notional, max_notional, broker_qty)

    minimum_qty = max(1, ceil(min_notional / price_value))
    quantity = minimum_qty
    if quantity * price_value > max_notional:
        quantity = floor(max_notional / price_value)
    if allow_single_share_budget_bump and quantity < 1 and max_notional >= price_value:
        quantity = 1

    estimated_notional = float(quantity * price_value)
    effective_pct = (
        estimated_notional / equity_value * 100.0 if equity_value > 0 else 0.0
    )
    if quantity < 1:
        return _blocked(
            "quantity_less_than_one",
            equity_value,
            cash_value,
            price_value,
            min_notional,
            max_notional,
            broker_qty,
            minimum_qty=minimum_qty,
        )
    if estimated_notional > cash_value:
        return _blocked(
            "estimated_notional_exceeds_orderable_cash",
            equity_value,
            cash_value,
            price_value,
            min_notional,
            max_notional,
            broker_qty,
            minimum_qty=minimum_qty,
            quantity=quantity,
            estimated_notional=estimated_notional,
            effective_position_pct=effective_pct,
        )
    if estimated_notional > notional_cap:
        return _blocked(
            "estimated_notional_exceeds_cap",
            equity_value,
            cash_value,
            price_value,
            min_notional,
            max_notional,
            broker_qty,
            minimum_qty=minimum_qty,
            quantity=quantity,
            estimated_notional=estimated_notional,
            effective_position_pct=effective_pct,
        )
    if effective_pct > max_pct:
        return _blocked(
            "effective_position_pct_exceeds_max",
            equity_value,
            cash_value,
            price_value,
            min_notional,
            max_notional,
            broker_qty,
            minimum_qty=minimum_qty,
            quantity=quantity,
            estimated_notional=estimated_notional,
            effective_position_pct=effective_pct,
        )
    if broker_qty is not None and quantity > broker_qty:
        return _blocked(
            "quantity_exceeds_broker_orderable_qty",
            equity_value,
            cash_value,
            price_value,
            min_notional,
            max_notional,
            broker_qty,
            minimum_qty=minimum_qty,
            quantity=quantity,
            estimated_notional=estimated_notional,
            effective_position_pct=effective_pct,
        )

    return OperationTest4SizingResult(
        status="ready",
        reason=None,
        equity=equity_value,
        orderable_cash=cash_value,
        current_price=price_value,
        min_notional=min_notional,
        max_notional=max_notional,
        minimum_qty=minimum_qty,
        quantity=int(quantity),
        estimated_notional=estimated_notional,
        effective_position_pct=effective_pct,
        broker_orderable_qty=broker_qty,
    )


def _blocked(
    reason: str,
    equity: float,
    orderable_cash: float,
    current_price: float,
    min_notional: float,
    max_notional: float,
    broker_orderable_qty: int | None,
    *,
    minimum_qty: int = 0,
    quantity: int = 0,
    estimated_notional: float = 0.0,
    effective_position_pct: float = 0.0,
) -> OperationTest4SizingResult:
    return OperationTest4SizingResult(
        status="blocked",
        reason=reason,
        equity=equity,
        orderable_cash=orderable_cash,
        current_price=current_price,
        min_notional=min_notional,
        max_notional=max_notional,
        minimum_qty=minimum_qty,
        quantity=quantity,
        estimated_notional=estimated_notional,
        effective_position_pct=effective_position_pct,
        broker_orderable_qty=broker_orderable_qty,
    )


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if isfinite(number) else 0.0


def _whole_quantity_or_none(value: Any) -> int | None:
    if value is None:
        return None
    number = _number(value)
    if number < 0:
        return 0
    return floor(number)