from __future__ import annotations

import math
from typing import Any


class StrategyProfileSizingService:
    @staticmethod
    def calculate(
        settings: dict[str, Any],
        *,
        equity: float,
        orderable_cash: float,
        current_position_value: float = 0,
        current_total_exposure: float = 0,
        current_price: float = 0,
    ) -> dict[str, Any]:
        capital = settings.get('capital') if isinstance(settings.get('capital'), dict) else {}
        mode = str(capital.get('sizing_mode') or 'equity_pct').strip().lower()
        target_pct = max(0.0, float(capital.get('target_position_pct') or 0))
        max_position_pct = max(0.0, float(capital.get('max_position_pct') or 0))
        exposure_pct = max(0.0, float(capital.get('max_total_exposure_pct') or 0))
        max_notional = max(0.0, float(capital.get('max_order_notional_krw') or 0))
        if mode == 'fixed_budget':
            target_notional = max(0.0, float(capital.get('fixed_budget') or 0))
            if target_notional <= 0:
                target_notional = max_notional
        else:
            target_notional = max(0.0, float(equity)) * target_pct / 100.0
        max_position_value = max(0.0, float(equity)) * max_position_pct / 100.0
        max_total_exposure = max(0.0, float(equity)) * exposure_pct / 100.0
        remaining_position = max(0.0, max_position_value - float(current_position_value))
        remaining_exposure = max(0.0, max_total_exposure - float(current_total_exposure))
        estimated_notional = min(
            target_notional,
            max_notional or target_notional,
            max(0.0, float(orderable_cash)),
            remaining_position,
            remaining_exposure,
        )
        quantity = 0
        if current_price > 0:
            quantity = max(0, math.floor(estimated_notional / float(current_price)))
        final_notional = quantity * float(current_price) if quantity else estimated_notional
        return {
            'sizing_mode': mode,
            'target_notional': round(target_notional, 2),
            'max_position_value': round(max_position_value, 2),
            'max_total_exposure': round(max_total_exposure, 2),
            'remaining_position_capacity': round(remaining_position, 2),
            'remaining_exposure_capacity': round(remaining_exposure, 2),
            'orderable_cash': round(max(0.0, float(orderable_cash)), 2),
            'estimated_notional': round(final_notional, 2),
            'quantity': quantity,
            'current_price': float(current_price),
            'ready': bool(final_notional > 0 and (current_price <= 0 or quantity > 0)),
            'multi_position_execution_supported': False,
            'requires_pr109_portfolio_engine': int(settings.get('max_open_positions') or 1) > 1,
        }
