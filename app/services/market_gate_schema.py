from __future__ import annotations

from typing import Any

MARKET_GATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["market_regime", "entry_bias", "entry_allowed", "market_confidence", "reason"],
    "properties": {
        "market_regime": {"type": "string", "enum": ["trend", "range", "volatile", "unknown"]},
        "entry_bias": {"type": "string", "enum": ["long", "neutral"]},
        "entry_allowed": {"type": "boolean"},
        "market_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string", "minLength": 1, "maxLength": 600},
    },
}


class SchemaValidationError(ValueError):
    pass


def parse_market_gate_response(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise SchemaValidationError("payload is not object")

    allowed_keys = {"market_regime", "entry_bias", "entry_allowed", "market_confidence", "reason"}
    extra = set(payload.keys()) - allowed_keys
    if extra:
        raise SchemaValidationError(f"unexpected fields: {sorted(extra)}")

    required_missing = [k for k in allowed_keys if k not in payload]
    if required_missing:
        raise SchemaValidationError(f"missing fields: {required_missing}")

    market_regime = payload["market_regime"]
    if market_regime not in {"trend", "range", "volatile", "unknown"}:
        raise SchemaValidationError("invalid market_regime")

    entry_bias = payload["entry_bias"]
    if entry_bias not in {"long", "neutral"}:
        raise SchemaValidationError("invalid entry_bias")

    entry_allowed = payload["entry_allowed"]
    if type(entry_allowed) is not bool:
        raise SchemaValidationError("entry_allowed must be boolean")

    market_confidence = payload["market_confidence"]
    if not isinstance(market_confidence, (int, float)):
        raise SchemaValidationError("market_confidence must be numeric")
    market_confidence = float(market_confidence)
    if market_confidence < 0.0 or market_confidence > 1.0:
        raise SchemaValidationError("market_confidence out of range")

    reason = payload["reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise SchemaValidationError("reason must be non-empty string")

    return {
        "market_regime": market_regime,
        "entry_bias": entry_bias,
        "entry_allowed": entry_allowed,
        "market_confidence": market_confidence,
        "reason": reason.strip()[:600],
    }