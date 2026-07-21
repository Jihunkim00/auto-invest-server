from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "baseline" / "runtime-settings-snapshot.json"
KST = ZoneInfo("Asia/Seoul")

SAFE_CONFIG_KEYS = (
    "app_name",
    "app_debug",
    "app_env",
    "app_version",
    "default_symbol",
    "default_us_symbol",
    "default_kr_symbol",
    "dry_run",
    "broker_provider",
    "kis_enabled",
    "kis_env",
    "kis_real_order_enabled",
    "kis_max_manual_order_qty",
    "kis_max_manual_order_amount_krw",
    "kis_require_confirmation",
    "kis_scheduler_enabled",
    "kis_scheduler_dry_run",
    "kis_scheduler_allow_real_orders",
    "kr_scheduler_enabled",
    "kr_scheduler_allow_real_orders",
    "openai_model",
    "openai_reasoning_effort",
    "agent_chat_model",
    "agent_chat_reasoning_effort",
    "agent_chat_timeout_seconds",
    "agent_chat_fallback_enabled",
    "max_watchlist_size",
    "watchlist_top_candidates_for_research",
    "watchlist_min_entry_score",
    "watchlist_min_quant_score",
    "watchlist_min_research_score",
    "watchlist_strong_entry_score",
    "watchlist_min_score_gap",
    "watchlist_max_sell_score",
    "watchlist_quant_weight",
    "watchlist_research_weight",
    "market_gate_min_confidence",
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a safe read-only runtime settings baseline snapshot."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output JSON path. Defaults to artifacts/baseline/runtime-settings-snapshot.json.",
    )
    args = parser.parse_args()

    _prepare_import_environment()
    snapshot = build_runtime_snapshot()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Runtime settings snapshot written: {output}")
    return 0


def build_runtime_snapshot() -> dict[str, Any]:
    from sqlalchemy import inspect

    from app.config import get_settings
    from app.db.database import SessionLocal, engine
    from app.services.runtime_setting_service import RuntimeSettingService

    service = RuntimeSettingService()
    settings = get_settings()
    runtime_settings_source = "defaults"
    runtime_settings: dict[str, Any]

    inspector = inspect(engine)
    if "runtime_settings" in inspector.get_table_names():
        db = SessionLocal()
        try:
            runtime_settings = service.get_settings_read_only(db)
            runtime_settings_source = "runtime_settings_table_read_only"
        finally:
            db.close()
    else:
        runtime_settings = service._finalize_settings(dict(service._defaults()))

    safe_config = {
        key: _json_safe(getattr(settings, key))
        for key in SAFE_CONFIG_KEYS
        if hasattr(settings, key) and not _is_sensitive_key(key)
    }

    return {
        "schema_version": 1,
        "generated_at": _now_iso(),
        "git": {
            "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"]),
            "commit_sha": _git(["rev-parse", "HEAD"]),
        },
        "source": runtime_settings_source,
        "safety": {
            "read_only": True,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "settings_changed": False,
            "secrets_excluded": True,
        },
        "app_config": _sanitize(safe_config),
        "runtime_settings": _sanitize(runtime_settings),
        "live_gate_summary": _live_gate_summary(runtime_settings),
    }


def _prepare_import_environment() -> None:
    os.environ.setdefault("ALPACA_API_KEY", "baseline-placeholder")
    os.environ.setdefault("ALPACA_SECRET_KEY", "baseline-placeholder")
    os.environ.setdefault("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def _live_gate_summary(settings: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "dry_run",
        "kill_switch",
        "scheduler_enabled",
        "automation_mode",
        "automation_release_enabled",
        "automation_release_allow_live_phase1",
        "automation_release_scheduler_enabled",
        "portfolio_orchestrator_enabled",
        "portfolio_orchestrator_allow_live_orders",
        "automation_soak_enabled",
        "automation_soak_kill_latch_active",
        "kis_scheduler_enabled",
        "kis_scheduler_dry_run",
        "kis_scheduler_live_enabled",
        "kis_scheduler_allow_real_orders",
        "kis_scheduler_configured_allow_real_orders",
        "kis_scheduler_buy_enabled",
        "kis_scheduler_sell_enabled",
        "agent_chat_live_order_enabled",
        "agent_chat_live_order_kis_enabled",
        "agent_chat_live_order_buy_enabled",
        "agent_chat_live_order_sell_enabled",
        "agent_chat_live_order_requires_confirm",
    )
    return {key: settings.get(key) for key in keys if key in settings}


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if _is_sensitive_key(text_key):
                continue
            result[text_key] = _sanitize(item)
        return result
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return _json_safe(value)


def _json_safe(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = "".join(ch for ch in key.lower() if ch.isalnum())
    return any(marker in normalized for marker in SENSITIVE_KEY_MARKERS)


def _now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _git(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


if __name__ == "__main__":
    raise SystemExit(main())
