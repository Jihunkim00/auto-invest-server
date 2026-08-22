from __future__ import annotations

from copy import deepcopy
from typing import Any


TEST4_HARD_SAFETY = {
    'min_final_score': 65.0,
    'no_new_entry_after': '14:00',
    'max_open_positions': 1,
    'max_order_notional_krw': 1_000_000.0,
    'cash_only': True,
    'stop_loss_pct': 2.0,
    'take_profit_pct': 3.0,
}


def effective_profile_settings(
    settings: dict[str, Any],
    *,
    provider: str = 'kis',
    market: str = 'KR',
) -> dict[str, Any]:
    """Return settings that may reach the guarded automation runtime."""
    effective = deepcopy(settings)
    if str(provider).strip().lower() != 'kis' or str(market).strip().upper() != 'KR':
        return effective

    entry = effective.setdefault('entry', {})
    capital = effective.setdefault('capital', {})
    exit_settings = effective.setdefault('exit', {})

    entry['min_final_score'] = max(
        TEST4_HARD_SAFETY['min_final_score'],
        float(entry.get('min_final_score') or 0),
    )
    entry['no_new_entry_after'] = _earlier_cutoff(
        str(entry.get('no_new_entry_after') or TEST4_HARD_SAFETY['no_new_entry_after']),
        TEST4_HARD_SAFETY['no_new_entry_after'],
    )
    effective['max_open_positions'] = min(
        TEST4_HARD_SAFETY['max_open_positions'],
        int(effective.get('max_open_positions') or TEST4_HARD_SAFETY['max_open_positions']),
    )
    capital['max_order_notional_krw'] = min(
        TEST4_HARD_SAFETY['max_order_notional_krw'],
        float(capital.get('max_order_notional_krw') or TEST4_HARD_SAFETY['max_order_notional_krw']),
    )
    capital['cash_only'] = True
    exit_settings['stop_loss_enabled'] = True
    exit_settings['take_profit_enabled'] = True
    exit_settings['stop_loss_pct'] = min(
        TEST4_HARD_SAFETY['stop_loss_pct'],
        float(exit_settings.get('stop_loss_pct') or TEST4_HARD_SAFETY['stop_loss_pct']),
    )
    exit_settings['take_profit_pct'] = min(
        TEST4_HARD_SAFETY['take_profit_pct'],
        float(exit_settings.get('take_profit_pct') or TEST4_HARD_SAFETY['take_profit_pct']),
    )
    return effective


def _earlier_cutoff(value: str, hard_floor: str) -> str:
    try:
        value_minutes = _minutes(value)
        hard_minutes = _minutes(hard_floor)
    except ValueError:
        return hard_floor
    return value if value_minutes <= hard_minutes else hard_floor


def _minutes(value: str) -> int:
    hour, minute = (int(part) for part in value.split(':', 1))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError('invalid_time')
    return hour * 60 + minute