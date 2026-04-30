from __future__ import annotations

from typing import Any

from app.core.constants import get_gate_profile

_MARKET_RESEARCH_BLOCK_PHRASES = (
    "entry is not allowed",
    "entry not allowed",
    "no strong long entry edge",
    "does not support entry",
    "lacks a clean long edge",
    "block entry",
    "blocked entry",
)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def evaluate_entry_readiness(
    *,
    has_indicators: bool,
    hard_blocked: bool = False,
    entry_score: float,
    buy_score: float,
    sell_score: float,
    gate_level: int,
    min_entry_score: float,
    max_sell_score: float,
    gating_notes: list[Any] | None = None,
    risk_flags: list[Any] | None = None,
    action: str | None = None,
    market_research_blocked: bool = False,
) -> dict[str, object]:
    profile = get_gate_profile(gate_level)
    notes = {str(note) for note in (gating_notes or [])}
    flags = {str(flag) for flag in (risk_flags or [])}
    normalized_action = str(action or "").strip().lower()
    effective_min_entry = max(float(min_entry_score), float(profile.min_buy_score))
    buy_sell_spread = _safe_float(buy_score) - _safe_float(sell_score)

    soft_entry_allowed = bool(has_indicators) and not bool(hard_blocked)
    block_reason: str | None = None

    if not has_indicators:
        block_reason = "missing_indicators"
    elif hard_blocked:
        block_reason = "hard_blocked"
    elif market_research_blocked:
        block_reason = "market_research_blocked"
    elif "score_threshold_not_met" in notes:
        block_reason = "score_threshold_not_met"
    elif "hold_signal" in flags:
        block_reason = "hold_signal"
    elif normalized_action == "hold":
        block_reason = "hold_signal"
    elif _safe_float(entry_score) < effective_min_entry:
        block_reason = "score_threshold_not_met"
    elif buy_sell_spread < float(profile.min_score_spread):
        block_reason = "buy_sell_spread_too_weak"
    elif _safe_float(sell_score, 100.0) > float(max_sell_score):
        block_reason = "sell_pressure_too_high"

    entry_ready = block_reason is None
    if entry_ready:
        action_hint = "buy_candidate"
    elif soft_entry_allowed:
        action_hint = "watch"
    else:
        action_hint = "hold"

    return {
        "soft_entry_allowed": soft_entry_allowed,
        "entry_ready": entry_ready,
        "trade_allowed": False,
        "action_hint": action_hint,
        "block_reason": block_reason,
        "effective_min_entry_score": effective_min_entry,
        "buy_sell_spread": round(buy_sell_spread, 2),
    }


def market_research_blocks_entry(
    *,
    entry_allowed: bool,
    hard_blocked: bool,
    reason: object = "",
    entry_bias: object = "",
) -> bool:
    if hard_blocked or not entry_allowed:
        return True

    normalized_reason = str(reason or "").strip().lower()
    if any(phrase in normalized_reason for phrase in _MARKET_RESEARCH_BLOCK_PHRASES):
        return True

    normalized_bias = str(entry_bias or "").strip().lower()
    return normalized_bias in {"hold", "avoid", "short", "blocked", "block_entry"}
