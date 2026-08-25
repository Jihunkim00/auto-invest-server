from __future__ import annotations

from typing import Any


PROFILE_MIN_PRICE_NOT_MET = 'profile_min_price_not_met'
PROFILE_MAX_PRICE_EXCEEDED = 'profile_max_price_exceeded'
def profile_universe_bounds(profile: dict[str, Any] | None) -> tuple[float | None, float | None]:
    value = profile if isinstance(profile, dict) else {}
    settings = value.get('automation_settings') or value.get('effective_settings') or value.get('settings') or {}
    settings = settings if isinstance(settings, dict) else {}
    universe = settings.get('universe')
    if not isinstance(universe, dict):
        universe = value.get('universe')
    universe = universe if isinstance(universe, dict) else {}
    return (
        _positive_float(universe.get('min_price_krw')),
        _positive_float(universe.get('max_price_krw')),
    )


def profile_price_exclusion_reason(
    price: Any,
    *,
    min_price_krw: float | None,
    max_price_krw: float | None,
) -> str | None:
    current_price = _positive_float(price)
    if current_price is None:
        return None
    if max_price_krw is not None and current_price > max_price_krw:
        return PROFILE_MAX_PRICE_EXCEEDED
    if min_price_krw is not None and current_price < min_price_krw:
        return PROFILE_MIN_PRICE_NOT_MET
    return None


def candidate_price(candidate: dict[str, Any]) -> float | None:
    if not isinstance(candidate, dict):
        return None
    for key in ('current_price', 'price', 'simulated_price', 'close'):
        value = _positive_float(candidate.get(key))
        if value is not None:
            return value
    return None


def _positive_float(value: Any) -> float | None:
    try:
        numeric = float(str(value).replace(',', '').strip())
    except (TypeError, ValueError):
        return None
    return numeric if numeric > 0 else None
