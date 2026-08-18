from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts.export_operation_baseline import build_runtime_snapshot


REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_DIR = REPO_ROOT / "docs" / "baseline"

FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"real-app-secret", re.IGNORECASE),
    re.compile(r"secret-access-token", re.IGNORECASE),
    re.compile(r"secret-approval-key", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

SENSITIVE_KEY_MARKERS = (
    "appkey",
    "appsecret",
    "secret",
    "credential",
    "authorization",
    "access",
    "refresh",
    "approval",
    "accountno",
    "accountnumber",
    "password",
    "token",
    "apikey",
)


def test_baseline_documents_do_not_contain_sensitive_values():
    paths = [
        path
        for path in BASELINE_DIR.rglob("*")
        if path.is_file() and path.suffix in {".json", ".md"}
    ]
    assert paths

    for path in paths:
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_VALUE_PATTERNS:
            assert pattern.search(text) is None, path


def test_runtime_exporter_excludes_sensitive_app_config_keys():
    snapshot = build_runtime_snapshot()

    assert snapshot["safety"]["read_only"] is True
    assert snapshot["safety"]["broker_submit_called"] is False
    assert snapshot["safety"]["manual_submit_called"] is False
    assert snapshot["safety"]["settings_changed"] is False
    assert snapshot["safety"]["secrets_excluded"] is True

    app_config = snapshot["app_config"]
    assert isinstance(app_config, dict)
    for key in _walk_keys(app_config):
        assert not _is_sensitive_key(key), key

    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    for pattern in FORBIDDEN_VALUE_PATTERNS:
        assert pattern.search(encoded) is None


def test_runtime_fixture_uses_synthetic_safe_values_only():
    fixture = json.loads(
        (BASELINE_DIR / "fixtures" / "runtime-settings-snapshot.example.json")
        .read_text(encoding="utf-8")
    )

    assert fixture["source"] == "sample_fixture_synthetic_values"
    assert fixture["safety"]["read_only"] is True
    assert fixture["safety"]["secrets_excluded"] is True
    assert fixture["live_gate_summary"]["dry_run"] is True
    assert fixture["live_gate_summary"]["agent_chat_live_order_enabled"] is False


def _walk_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        keys: list[str] = []
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(item))
        return keys
    if isinstance(value, list):
        keys = []
        for item in value:
            keys.extend(_walk_keys(item))
        return keys
    return []


def _is_sensitive_key(key: str) -> bool:
    normalized = "".join(ch for ch in key.lower() if ch.isalnum())
    return any(marker in normalized for marker in SENSITIVE_KEY_MARKERS)

