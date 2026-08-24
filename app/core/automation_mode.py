from __future__ import annotations

from typing import Any

AUTOMATION_MODE_OFF = 'off'
AUTOMATION_MODE_TEST = 'test'
AUTOMATION_MODE_LIVE = 'live'

CANONICAL_AUTOMATION_MODES = {
    AUTOMATION_MODE_OFF,
    AUTOMATION_MODE_TEST,
    AUTOMATION_MODE_LIVE,
}

LEGACY_AUTOMATION_MODE_ALIASES = {
    'monitor_only': AUTOMATION_MODE_OFF,
    'dry_run_auto': AUTOMATION_MODE_TEST,
    'phase1_live_ready': AUTOMATION_MODE_LIVE,
}

SUPPORTED_AUTOMATION_MODE_VALUES = (
    *sorted(CANONICAL_AUTOMATION_MODES),
    *sorted(LEGACY_AUTOMATION_MODE_ALIASES),
)


def normalize_automation_mode(value: Any, *, preserve_legacy: bool = True) -> str:
    text = str(value or AUTOMATION_MODE_OFF).strip().lower()
    if text in CANONICAL_AUTOMATION_MODES:
        return text
    if preserve_legacy and text in LEGACY_AUTOMATION_MODE_ALIASES:
        return text
    if text in LEGACY_AUTOMATION_MODE_ALIASES:
        return LEGACY_AUTOMATION_MODE_ALIASES[text]
    raise ValueError(f'unsupported automation mode: {text}')


def execution_mode(value: Any) -> str:
    normalized = normalize_automation_mode(value)
    return LEGACY_AUTOMATION_MODE_ALIASES.get(normalized, normalized)


def automation_mode_authority(value: Any) -> dict[str, Any]:
    configured = normalize_automation_mode(value)
    effective = execution_mode(configured)
    return {
        'configured_mode': configured,
        'automation_mode': effective,
        'execution_authority': effective.upper(),
        'scheduler_allowed': effective in {AUTOMATION_MODE_TEST, AUTOMATION_MODE_LIVE},
        'simulation_allowed': effective in {AUTOMATION_MODE_TEST, AUTOMATION_MODE_LIVE},
        'broker_submit_allowed': effective == AUTOMATION_MODE_LIVE,
        'read_only_allowed': True,
        'legacy_alias': configured if configured != effective else None,
        'source_of_truth': 'automation_mode',
    }
