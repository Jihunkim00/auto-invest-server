from __future__ import annotations

import json
from typing import Any


GPT_RISK_CONTEXT_KEYS = (
    "market_risk_regime",
    "technical_market_regime",
    "event_risk_level",
    "fx_risk_level",
    "geopolitical_risk_level",
    "energy_risk_level",
    "political_regulatory_risk_level",
    "macro_risk_level",
    "sector_fundamental_trend",
    "revenue_trend_context",
    "flow_signal",
    "earnings_revision_signal",
    "valuation_risk_level",
    "entry_penalty",
    "hard_block_new_buy",
    "allow_sell_or_exit",
    "gpt_buy_score",
    "gpt_sell_score",
    "affected_sectors",
    "risk_flags",
    "gating_notes",
    "reason",
)

_LIST_KEYS = {"affected_sectors", "risk_flags", "gating_notes"}
_BOOL_DEFAULTS = {
    "hard_block_new_buy": False,
    "allow_sell_or_exit": True,
}


def parse_json_object(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_json_array(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except Exception:
        return []
    return _string_list(parsed)


def build_gpt_context(
    payload: dict[str, Any] | None,
    *,
    gating_notes: list[Any] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    context: dict[str, Any] = {}
    for key in GPT_RISK_CONTEXT_KEYS:
        if key in _LIST_KEYS:
            context[key] = _string_list(payload.get(key))
        elif key in _BOOL_DEFAULTS:
            context[key] = _bool_value(payload.get(key), _BOOL_DEFAULTS[key])
        elif key == "entry_penalty":
            context[key] = _int_or_none(payload.get(key))
        elif key in {"gpt_buy_score", "gpt_sell_score"}:
            context[key] = _float_or_none(payload.get(key))
        else:
            context[key] = _string_or_none(payload.get(key))

    if not context["gating_notes"] and gating_notes:
        context["gating_notes"] = _string_list(gating_notes)
    if not context["reason"] and reason:
        context["reason"] = str(reason)
    return context


def gpt_context_from_market_analysis(row: Any) -> dict[str, Any]:
    raw_payload = parse_json_object(getattr(row, "raw_payload", None))
    return build_gpt_context(
        raw_payload,
        gating_notes=parse_json_array(getattr(row, "gating_notes", None)),
        reason=getattr(row, "risk_note", None),
    )


def has_observed_gpt_context(context: dict[str, Any] | None) -> bool:
    if not context:
        return False
    for key, value in context.items():
        if key in _BOOL_DEFAULTS:
            continue
        if value not in (None, "", []):
            return True
    return False


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "null":
        return None
    return text


def _int_or_none(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_value(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return default


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
