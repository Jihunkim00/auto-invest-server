from __future__ import annotations

from typing import Any


ENTRY_PENALTY_LEVELS = (0, 10, 20, 30, 50, 70, 999)

SEVERE_DIRECT_RISK_MARKERS = (
    "trading halt",
    "halted",
    "bankruptcy",
    "delisting",
    "delist",
    "accounting fraud",
    "fraud",
    "severe regulatory action",
    "regulatory suspension",
    "criminal investigation",
    "existential lawsuit",
    "severe lawsuit",
    "liquidity crisis",
    "solvency",
    "insolvency",
    "stale price",
    "invalid price",
    "impossible indicator",
    "missing critical market data",
    "critical market data missing",
    "market data invalid",
    "circuit breaker",
    "disorderly market",
    "market infrastructure",
    "broker infrastructure",
    "exchange outage",
)


def true_severe_gpt_hard_block(payload: dict[str, Any] | None) -> bool:
    """Return true only for direct, severe conditions that may justify GPT 999."""

    if not isinstance(payload, dict):
        return False
    haystack = " ".join(_hard_block_evidence(payload)).lower()
    if not haystack:
        return False
    return any(marker in haystack for marker in SEVERE_DIRECT_RISK_MARKERS)


def requested_gpt_hard_block(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("hard_block_new_buy") is True:
        return True
    if payload.get("hard_blocked") is True:
        return True
    if _safe_int(payload.get("entry_penalty")) >= 900:
        return True
    hard_reason = str(payload.get("hard_block_reason") or "").strip()
    if hard_reason:
        return True
    flags = {item.lower() for item in _string_list(payload.get("risk_flags"))}
    notes = {item.lower() for item in _string_list(payload.get("gating_notes"))}
    context = payload.get("gpt_context") if isinstance(payload.get("gpt_context"), dict) else {}
    return (
        "gpt_hard_block_new_buy" in flags
        or "hard_block_new_buy" in flags
        or "gpt_blocked_entry" in flags
        or "gpt_hard_block_new_buy" in notes
        or context.get("hard_block_new_buy") is True
        or _safe_int(context.get("entry_penalty")) >= 900
    )


def should_apply_gpt_hard_block(payload: dict[str, Any] | None) -> bool:
    return requested_gpt_hard_block(payload) and true_severe_gpt_hard_block(payload)


def normalize_entry_penalty_level(value: Any, *, severe: bool = False) -> int:
    raw = _safe_int(value)
    if raw >= 900:
        return 999 if severe else 70
    if raw <= 0:
        return 0
    if raw <= 10:
        return 10
    if raw <= 20:
        return 20
    if raw <= 30:
        return 30
    if raw <= 50:
        return 50
    return 70


def advisory_downgrade_note(payload: dict[str, Any] | None) -> str | None:
    if requested_gpt_hard_block(payload) and not true_severe_gpt_hard_block(payload):
        return "gpt_hard_block_downgraded_to_advisory"
    return None


def _hard_block_evidence(payload: dict[str, Any]) -> list[str]:
    values = [
        payload.get("reason"),
        payload.get("hard_block_reason"),
        payload.get("risk_note"),
        payload.get("market_research_reason"),
    ]
    values.extend(_string_list(payload.get("risk_flags")))
    values.extend(_string_list(payload.get("gating_notes")))
    context = payload.get("gpt_context") if isinstance(payload.get("gpt_context"), dict) else {}
    if context:
        values.extend(
            [
                context.get("reason"),
                context.get("hard_block_reason"),
            ]
        )
        values.extend(_string_list(context.get("risk_flags")))
        values.extend(_string_list(context.get("gating_notes")))
    return [str(value) for value in values if str(value or "").strip()]


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []
