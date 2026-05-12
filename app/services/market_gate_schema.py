from __future__ import annotations

from typing import Any

RISK_LEVEL_ENUM = ["unknown", "none", "low", "medium", "high", "extreme"]
TREND_ENUM = ["improving", "stable", "mixed", "weakening", "unknown"]
SIGNAL_ENUM = ["positive", "neutral", "negative", "unknown"]

MARKET_GATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["market_regime", "entry_bias", "entry_allowed", "market_confidence", "reason"],
    "properties": {
        "market": {"type": "string"},
        "symbol": {"type": "string"},
        "market_regime": {"type": "string", "enum": ["trend", "range", "volatile", "unknown"]},
        "technical_market_regime": {"type": "string", "enum": ["unknown", "range", "trend"]},
        "market_risk_regime": {"type": "string", "enum": ["risk_on", "neutral", "risk_off", "panic"]},
        "entry_bias": {"type": "string", "enum": ["long", "neutral"]},
        "entry_allowed": {"type": "boolean"},
        "event_risk_level": {"type": "string", "enum": RISK_LEVEL_ENUM},
        "fx_risk_level": {"type": "string", "enum": RISK_LEVEL_ENUM},
        "geopolitical_risk_level": {"type": "string", "enum": RISK_LEVEL_ENUM},
        "energy_risk_level": {"type": "string", "enum": RISK_LEVEL_ENUM},
        "political_regulatory_risk_level": {"type": "string", "enum": RISK_LEVEL_ENUM},
        "macro_risk_level": {"type": "string", "enum": RISK_LEVEL_ENUM},
        "sector_fundamental_trend": {"type": "string", "enum": TREND_ENUM},
        "revenue_trend_context": {"type": "string", "enum": TREND_ENUM},
        "flow_signal": {"type": "string", "enum": SIGNAL_ENUM},
        "earnings_revision_signal": {"type": "string", "enum": SIGNAL_ENUM},
        "valuation_risk_level": {"type": "string", "enum": RISK_LEVEL_ENUM},
        "entry_penalty": {"type": "integer", "minimum": 0, "maximum": 999},
        "hard_block_new_buy": {"type": "boolean"},
        "allow_sell_or_exit": {"type": "boolean"},
        "gpt_buy_score": {"type": "number", "minimum": 0, "maximum": 100},
        "gpt_sell_score": {"type": "number", "minimum": 0, "maximum": 100},
        "ai_buy_score": {"type": "number", "minimum": 0, "maximum": 100},
        "ai_sell_score": {"type": "number", "minimum": 0, "maximum": 100},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "market_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "affected_sectors": {"type": "array", "items": {"type": "string"}},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "gating_notes": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string", "minLength": 1, "maxLength": 600},
        "hard_block_reason": {"type": ["string", "null"]},
        "hard_blocked": {"type": "boolean"},
    },
}


class SchemaValidationError(ValueError):
    pass


def _require_bool(payload: dict, key: str) -> bool:
    value = payload[key]
    if type(value) is not bool:
        raise SchemaValidationError(f"{key} must be boolean")
    return value


def _optional_enum(payload: dict, key: str, allowed: set[str]) -> str | None:
    if key not in payload:
        return None
    value = payload[key]
    if not isinstance(value, str) or value not in allowed:
        raise SchemaValidationError(f"invalid {key}")
    return value


def _optional_number(payload: dict, key: str, low: float, high: float) -> float | None:
    if key not in payload:
        return None
    value = payload[key]
    if not isinstance(value, (int, float)):
        raise SchemaValidationError(f"{key} must be numeric")
    value = float(value)
    if value < low or value > high:
        raise SchemaValidationError(f"{key} out of range")
    return value


def _optional_string_list(payload: dict, key: str) -> list[str] | None:
    if key not in payload:
        return None
    value = payload[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SchemaValidationError(f"{key} must be array of strings")
    return value


def parse_market_gate_response(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise SchemaValidationError("payload is not object")

    allowed_keys = set(MARKET_GATE_SCHEMA["properties"].keys())
    extra = set(payload.keys()) - allowed_keys
    if extra:
        raise SchemaValidationError(f"unexpected fields: {sorted(extra)}")

    required = {"market_regime", "entry_bias", "entry_allowed", "market_confidence", "reason"}
    required_missing = [k for k in required if k not in payload]
    if required_missing:
        raise SchemaValidationError(f"missing fields: {required_missing}")

    market_regime = payload["market_regime"]
    if market_regime not in {"trend", "range", "volatile", "unknown"}:
        raise SchemaValidationError("invalid market_regime")

    entry_bias = payload["entry_bias"]
    if entry_bias not in {"long", "neutral"}:
        raise SchemaValidationError("invalid entry_bias")

    entry_allowed = _require_bool(payload, "entry_allowed")

    market_confidence = _optional_number(payload, "market_confidence", 0.0, 1.0)
    if market_confidence is None:
        raise SchemaValidationError("market_confidence must be numeric")

    reason = payload["reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise SchemaValidationError("reason must be non-empty string")

    result = {
        "market_regime": market_regime,
        "entry_bias": entry_bias,
        "entry_allowed": entry_allowed,
        "market_confidence": market_confidence,
        "reason": reason.strip()[:600],
    }

    for key in ("market", "symbol"):
        if key in payload:
            if not isinstance(payload[key], str):
                raise SchemaValidationError(f"{key} must be string")
            result[key] = payload[key]

    _optional_enum(payload, "technical_market_regime", {"unknown", "range", "trend"})
    _optional_enum(payload, "market_risk_regime", {"risk_on", "neutral", "risk_off", "panic"})
    for key in (
        "event_risk_level",
        "fx_risk_level",
        "geopolitical_risk_level",
        "energy_risk_level",
        "political_regulatory_risk_level",
        "macro_risk_level",
        "valuation_risk_level",
    ):
        _optional_enum(payload, key, set(RISK_LEVEL_ENUM))
    for key in ("sector_fundamental_trend", "revenue_trend_context"):
        _optional_enum(payload, key, set(TREND_ENUM))
    for key in ("flow_signal", "earnings_revision_signal"):
        _optional_enum(payload, key, set(SIGNAL_ENUM))

    if "entry_penalty" in payload:
        entry_penalty = payload["entry_penalty"]
        if not isinstance(entry_penalty, int) or entry_penalty < 0 or entry_penalty > 999:
            raise SchemaValidationError("entry_penalty out of range")

    for key in ("hard_block_new_buy", "allow_sell_or_exit", "hard_blocked"):
        if key in payload:
            _require_bool(payload, key)

    for key in ("gpt_buy_score", "gpt_sell_score", "ai_buy_score", "ai_sell_score"):
        _optional_number(payload, key, 0.0, 100.0)
    _optional_number(payload, "confidence", 0.0, 1.0)

    for key in ("affected_sectors", "risk_flags", "gating_notes"):
        _optional_string_list(payload, key)

    if "hard_block_reason" in payload and payload["hard_block_reason"] is not None and not isinstance(payload["hard_block_reason"], str):
        raise SchemaValidationError("hard_block_reason must be string or null")

    for key in allowed_keys - set(result.keys()):
        if key in payload:
            result[key] = payload[key]

    return result
