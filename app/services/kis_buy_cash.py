"""Cash-only BUY balance selection and safe, numeric diagnostics."""

from __future__ import annotations

import math
from typing import Any


def _amount(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return amount if math.isfinite(amount) else None


def orderable_cash(balance: dict[str, Any]) -> dict[str, Any]:
    """Keep explicit zero; fall back only when a source is absent or invalid."""
    for source in ("orderable_cash", "ord_psbl_cash", "available_cash", "cash", "dnca_tot_amt"):
        amount = _amount(balance.get(source))
        if amount is not None:
            return {"amount": amount, "source": source}
    return {"amount": None, "source": None}


def buy_cash_diagnostics(
    balance: dict[str, Any], estimated_notional_krw: float | None,
) -> dict[str, Any]:
    selected = orderable_cash(balance)
    amount = selected["amount"]
    cash_balance = _amount(balance.get("cash_balance"))
    if cash_balance is None:
        cash_balance = _amount(balance.get("cash"))
    return {
        "cash_balance_krw": cash_balance,
        "orderable_cash_krw": _amount(balance.get("orderable_cash")),
        "cash_check_amount_krw": amount,
        "cash_source": selected["source"],
        "estimated_notional_krw": estimated_notional_krw,
        "cash_sufficient": bool(
            amount is not None
            and estimated_notional_krw is not None
            and amount >= estimated_notional_krw
        ),
    }
