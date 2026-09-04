from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.automation_profile_safety import TEST4_HARD_SAFETY
from app.services.strategy_performance_service import StrategyPerformanceService


class CompoundCapitalService:
    """Calculate profile capital without mixing broker or manual activity."""

    def __init__(
        self,
        *,
        performance_service: StrategyPerformanceService | None = None,
    ) -> None:
        self.performance_service = performance_service or StrategyPerformanceService()

    def calculate(
        self,
        db: Session,
        *,
        profile_key: str,
        initial_budget_krw: float,
        fixed_budget_krw: float = 0.0,
        compound_enabled: bool = False,
        compound_basis: str = "realized_pnl",
        provider: str = "kis",
        market: str = "KR",
        broker_orderable_cash_krw: float | None = None,
        configured_max_order_notional_krw: float | None = None,
    ) -> dict[str, Any]:
        """Calculate initial budget plus eligible realized P/L."""
        initial = _money(initial_budget_krw)
        fixed = _money(fixed_budget_krw)
        enabled = bool(compound_enabled)
        basis = str(compound_basis or "realized_pnl").strip().lower()
        if basis != "realized_pnl":
            enabled = False

        performance = {
            "cumulative_realized_pnl_krw": 0.0,
            "eligible_closed_trade_count": 0,
            "unresolved_realized_pnl_count": 0,
        }
        if enabled and profile_key:
            performance = self.performance_service.profile_realized_pnl(
                db,
                profile_key=profile_key,
                provider=provider,
                market=market,
            )

        base = initial if enabled else (fixed or initial)
        realized = _signed_money(performance.get("cumulative_realized_pnl_krw"))
        current = max(0.0, round(base + realized, 2)) if enabled else max(0.0, round(base, 2))
        cap_values = [
            ("strategy_budget", current),
            (
                "configured_order_cap_limited",
                _money(configured_max_order_notional_krw)
                or float(TEST4_HARD_SAFETY["max_order_notional_krw"]),
            ),
            ("hard_cap_limited", float(TEST4_HARD_SAFETY["max_order_notional_krw"])),
        ]
        if broker_orderable_cash_krw is not None:
            cap_values.append(("broker_orderable_cash_limited", max(0.0, _money(broker_orderable_cash_krw))))
        effective = min(value for _, value in cap_values)
        source = next(name for name, value in cap_values if abs(value - effective) <= 0.01)
        return {
            "profile_key": profile_key,
            "initial_budget_krw": round(initial, 2),
            "compound_enabled": enabled,
            "compound_basis": "realized_pnl" if enabled else None,
            "cumulative_realized_pnl_krw": round(realized, 2),
            "current_strategy_budget_krw": round(current, 2),
            "broker_orderable_cash_krw": (
                None
                if broker_orderable_cash_krw is None
                else round(max(0.0, _money(broker_orderable_cash_krw)), 2)
            ),
            "effective_next_entry_budget_krw": round(max(0.0, effective), 2),
            "calculation_source": (
                "initial_budget_plus_cumulative_realized_pnl"
                if enabled
                else "fixed_budget"
            ),
            "eligible_closed_trade_count": int(performance.get("eligible_closed_trade_count") or 0),
            "unresolved_realized_pnl_count": int(performance.get("unresolved_realized_pnl_count") or 0),
            "effective_budget_cap_source": source,
        }


def _money(value: Any) -> float:
    try:
        if value is None or isinstance(value, bool):
            return 0.0
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _signed_money(value: Any) -> float:
    try:
        if value is None or isinstance(value, bool):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
