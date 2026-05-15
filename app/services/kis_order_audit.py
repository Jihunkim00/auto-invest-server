from __future__ import annotations

from typing import Any

from app.services.kis_payload_sanitizer import sanitize_kis_payload

EXIT_PREFLIGHT_SOURCE = "kis_live_exit_preflight"
MANUAL_EXIT_SOURCE_TYPE = "manual_confirm_exit"
EXIT_SHADOW_SOURCE = "kis_exit_shadow_decision"
EXIT_SHADOW_SOURCE_TYPE = "dry_run_sell_simulation"

_STRING_KEYS = {
    "source",
    "source_type",
    "preflight_id",
    "preflight_run_key",
    "preflight_checked_at",
    "shadow_decision_run_key",
    "shadow_decision_checked_at",
    "checked_at",
    "exit_trigger",
    "trigger_source",
}
_FLOAT_KEYS = {
    "unrealized_pl",
    "unrealized_pl_pct",
    "cost_basis",
    "current_value",
    "current_price",
    "suggested_quantity",
}
_BOOL_KEYS = {
    "manual_confirm_required",
    "auto_sell_enabled",
    "scheduler_real_order_enabled",
    "real_order_submit_allowed",
    "preflight_real_order_submitted",
    "preflight_broker_submit_called",
    "preflight_manual_submit_called",
    "shadow_real_order_submitted",
    "shadow_broker_submit_called",
    "shadow_manual_submit_called",
}
_LIST_KEYS = {"risk_flags", "gating_notes"}


def normalize_kis_order_source_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    result: dict[str, Any] = {}
    for key in _STRING_KEYS:
        text = _string_value(value.get(key))
        if text is not None:
            result[key] = text
    for key in _FLOAT_KEYS:
        number = _float_value(value.get(key))
        if number is not None:
            result[key] = number
    for key in _BOOL_KEYS:
        parsed = _bool_value(value.get(key))
        if parsed is not None:
            result[key] = parsed
    for key in _LIST_KEYS:
        items = _string_list(value.get(key))
        if items:
            result[key] = items

    if result.get("source") == EXIT_PREFLIGHT_SOURCE:
        result.setdefault("source_type", MANUAL_EXIT_SOURCE_TYPE)
        result.setdefault("manual_confirm_required", True)
        result.setdefault("auto_sell_enabled", False)
        result.setdefault("scheduler_real_order_enabled", False)
        result.setdefault("real_order_submit_allowed", False)
        result.setdefault("preflight_real_order_submitted", False)
        result.setdefault("preflight_broker_submit_called", False)
        result.setdefault("preflight_manual_submit_called", False)
    if result.get("source") == EXIT_SHADOW_SOURCE:
        result.setdefault("source_type", EXIT_SHADOW_SOURCE_TYPE)
        result.setdefault("manual_confirm_required", True)
        result.setdefault("auto_sell_enabled", False)
        result.setdefault("scheduler_real_order_enabled", False)
        result.setdefault("real_order_submit_allowed", False)
        result.setdefault("shadow_real_order_submitted", False)
        result.setdefault("shadow_broker_submit_called", False)
        result.setdefault("shadow_manual_submit_called", False)

    return sanitize_kis_payload(result) if result else {}


def merge_kis_order_source_metadata(*values: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for value in values:
        metadata = normalize_kis_order_source_metadata(value)
        if metadata:
            merged.update(metadata)
    return normalize_kis_order_source_metadata(merged)


def kis_order_source_fields(metadata: dict[str, Any] | None) -> dict[str, Any]:
    data = normalize_kis_order_source_metadata(metadata)
    if not data:
        return {}
    fields = {
        "source": data.get("source"),
        "source_type": data.get("source_type"),
        "exit_trigger": data.get("exit_trigger"),
        "exit_trigger_source": data.get("trigger_source"),
        "manual_confirm_required": data.get("manual_confirm_required"),
        "auto_sell_enabled": data.get("auto_sell_enabled"),
        "scheduler_real_order_enabled": data.get("scheduler_real_order_enabled"),
        "real_order_submit_allowed": data.get("real_order_submit_allowed"),
        "preflight_real_order_submitted": data.get("preflight_real_order_submitted"),
        "preflight_broker_submit_called": data.get("preflight_broker_submit_called"),
        "preflight_manual_submit_called": data.get("preflight_manual_submit_called"),
        "shadow_real_order_submitted": data.get("shadow_real_order_submitted"),
        "shadow_broker_submit_called": data.get("shadow_broker_submit_called"),
        "shadow_manual_submit_called": data.get("shadow_manual_submit_called"),
        "risk_flags": data.get("risk_flags"),
        "gating_notes": data.get("gating_notes"),
        "source_metadata": data,
    }
    return {key: value for key, value in fields.items() if value is not None}


def kis_order_source_metadata_from_payloads(*payloads: Any) -> dict[str, Any]:
    values: list[Any] = []
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        values.append(payload.get("source_metadata"))
        source_fields = {
            "source": payload.get("source"),
            "source_type": payload.get("source_type"),
            "exit_trigger": payload.get("exit_trigger"),
            "trigger_source": payload.get("exit_trigger_source")
            or payload.get("trigger_source"),
            "manual_confirm_required": payload.get("manual_confirm_required"),
            "auto_sell_enabled": payload.get("auto_sell_enabled"),
            "scheduler_real_order_enabled": payload.get(
                "scheduler_real_order_enabled"
            ),
            "real_order_submit_allowed": payload.get("real_order_submit_allowed"),
            "preflight_real_order_submitted": payload.get(
                "preflight_real_order_submitted"
            ),
            "preflight_broker_submit_called": payload.get(
                "preflight_broker_submit_called"
            ),
            "preflight_manual_submit_called": payload.get(
                "preflight_manual_submit_called"
            ),
            "shadow_real_order_submitted": payload.get("shadow_real_order_submitted"),
            "shadow_broker_submit_called": payload.get("shadow_broker_submit_called"),
            "shadow_manual_submit_called": payload.get("shadow_manual_submit_called"),
            "risk_flags": payload.get("risk_flags"),
            "gating_notes": payload.get("gating_notes"),
        }
        values.append(source_fields)
    return merge_kis_order_source_metadata(*values)


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "null":
        return None
    return text[:200]


def _float_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _bool_value(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip()[:200] for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()[:200]]
    return []
