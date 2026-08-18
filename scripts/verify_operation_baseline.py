from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = REPO_ROOT / "docs" / "baseline"

REQUIRED_FILES = (
    "operation-baseline.md",
    "operation-baseline.json",
    "database-schema.md",
    "database-schema.json",
    "flutter-ui-baseline.md",
    "openapi-baseline.json",
)

REQUIRED_TEST_FILES = (
    "app/tests/test_operation_baseline_contract.py",
    "app/tests/test_operation_baseline_secret_scan.py",
    "app/tests/test_operation_baseline_openapi.py",
)

REQUIRED_RUNTIME_DEFAULTS = {
    "dry_run": True,
    "kill_switch": False,
    "scheduler_enabled": False,
    "automation_mode": "off",
    "agent_chat_live_order_enabled": False,
    "agent_chat_live_order_requires_confirm": True,
    "agent_chat_live_order_max_orders_per_day": 1,
    "agent_chat_live_order_max_notional_pct": 0.03,
    "agent_chat_live_order_max_notional_krw": 50000.0,
    "portfolio_orchestrator_enabled": False,
    "portfolio_orchestrator_max_actions_per_run": 1,
    "broker_sync_watchdog_block_automation_on_unsafe": True,
    "automation_soak_enabled": False,
    "automation_soak_kill_latch_active": False,
    "automation_release_enabled": False,
    "automation_release_mode": "controlled_phase1",
    "automation_release_max_actions_per_cycle": 1,
    "automation_release_max_daily_auto_actions": 2,
    "automation_release_max_daily_auto_buys": 1,
    "automation_release_max_daily_auto_sells": 1,
    "kis_scheduler_enabled": False,
    "kis_scheduler_dry_run": True,
    "kis_scheduler_allow_real_orders": False,
    "kis_scheduler_buy_enabled": False,
    "kis_scheduler_sell_enabled": False,
    "kis_scheduler_max_live_orders_per_day": 1,
}

REQUIRED_ENDPOINTS = {
    "GET /ops/settings",
    "GET /automation/mode/status",
    "GET /automation/release/status",
    "GET /scheduler/status",
    "GET /kis/account/balance",
    "GET /kis/account/positions",
    "GET /kis/account/open-orders",
    "GET /kis/scheduler/status",
    "GET /portfolio/summary",
    "GET /automation/portfolio/latest",
    "POST /market-analysis/run",
    "POST /market-analysis/watchlist",
    "POST /trading/run-watchlist-once",
    "POST /kis/trading/run-once",
    "POST /kis/orders/validate",
    "POST /kis/orders/manual-submit",
    "POST /kis/orders/sync-open",
    "POST /agent/chat/send",
    "POST /agent/chat/live-orders/{action_id}/confirm",
    "POST /agent/chat/live-orders/{action_id}/cancel",
    "GET /agent/chat/conversations",
    "GET /agent/chat/conversations/{conversation_key}/messages",
    "GET /agent/chat/live-orders/readiness",
    "GET /agent/operations/summary",
    "GET /runs/recent",
    "GET /orders/recent",
    "GET /signals/recent",
    "GET /logs/summary",
}

REQUIRED_TABLE_COLUMNS = {
    "runtime_settings": {
        "dry_run",
        "kill_switch",
        "scheduler_enabled",
        "automation_mode",
        "agent_chat_live_order_enabled",
        "automation_release_enabled",
    },
    "orders": {
        "broker",
        "market",
        "symbol",
        "side",
        "internal_status",
        "broker_order_id",
        "request_payload",
        "response_payload",
    },
    "signals": {"symbol", "action", "buy_score", "sell_score", "created_at"},
    "trade_run_logs": {
        "run_key",
        "trigger_source",
        "symbol",
        "mode",
        "result",
        "request_payload",
        "response_payload",
    },
    "agent_chat_conversations": {"conversation_key", "status", "source"},
    "agent_chat_messages": {"conversation_id", "conversation_key", "role", "text"},
    "agent_chat_order_actions": {
        "conversation_key",
        "provider",
        "market",
        "symbol",
        "side",
        "status",
        "scope_hash",
        "confirmation_phrase",
    },
    "agent_plans": {"plan_key", "status", "safety_json", "scope_hash"},
    "agent_plan_runs": {"plan_id", "status", "request_json", "response_json"},
    "agent_schedule_jobs": {"schedule_key", "status", "schedule_json"},
    "auth_approval_requests": {"approval_key", "status", "scope_hash"},
    "agent_review_queue_state": {"queue_key", "item_type", "status"},
}

FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"real-app-secret", re.IGNORECASE),
    re.compile(r"secret-access-token", re.IGNORECASE),
    re.compile(r"secret-approval-key", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def main() -> int:
    _prepare_import_environment()
    failures: list[str] = []

    baseline_files = _verify_required_files(failures)
    operation = _load_json("operation-baseline.json", failures)
    database = _load_json("database-schema.json", failures)
    openapi = _load_json("openapi-baseline.json", failures)

    if operation:
        _verify_operation_manifest(operation, failures)
    if database:
        _verify_database_schema(database, failures)
    if openapi:
        _verify_openapi_baseline(openapi, failures)
    _verify_secret_scan(baseline_files, failures)
    _verify_test_files(failures)

    if failures:
        print("Operation baseline verification failed.")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Operation baseline verification passed.")
    print(f"Git SHA: {_git(['rev-parse', 'HEAD']) or 'unknown'}")
    print("API contracts: OK")
    print("Database schema: OK")
    print("Safety invariants: OK")
    print("Secret scan: OK")
    return 0


def _verify_required_files(failures: list[str]) -> list[Path]:
    files: list[Path] = []
    for relative in REQUIRED_FILES:
        path = BASELINE_DIR / relative
        if not path.exists():
            failures.append(f"missing baseline file: {path.relative_to(REPO_ROOT)}")
        else:
            files.append(path)
    return files


def _verify_test_files(failures: list[str]) -> None:
    for relative in REQUIRED_TEST_FILES:
        if not (REPO_ROOT / relative).exists():
            failures.append(f"missing baseline test file: {relative}")


def _load_json(filename: str, failures: list[str]) -> dict[str, Any]:
    path = BASELINE_DIR / filename
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        failures.append(f"{filename} is not valid JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        failures.append(f"{filename} must contain a JSON object")
        return {}
    if value.get("schema_version") != 1:
        failures.append(f"{filename} schema_version must be 1")
    return value


def _verify_operation_manifest(
    operation: dict[str, Any],
    failures: list[str],
) -> None:
    from app.services.runtime_setting_service import RuntimeSettingService

    defaults = RuntimeSettingService()._defaults()
    runtime_defaults = operation.get("runtime_defaults")
    if not isinstance(runtime_defaults, dict):
        failures.append("operation-baseline.json runtime_defaults must be an object")
        return

    for key, expected in REQUIRED_RUNTIME_DEFAULTS.items():
        if runtime_defaults.get(key) != expected:
            failures.append(
                f"operation-baseline.json runtime default {key!r} changed: "
                f"{runtime_defaults.get(key)!r} != {expected!r}"
            )
        if defaults.get(key) != expected:
            failures.append(
                f"current RuntimeSettingService default {key!r} changed: "
                f"{defaults.get(key)!r} != {expected!r}"
            )

    safety = operation.get("safety_invariants")
    if not isinstance(safety, list) or len(safety) < 8:
        failures.append("operation-baseline.json must record safety_invariants")


def _verify_database_schema(database: dict[str, Any], failures: list[str]) -> None:
    from app.db.models import Base

    baseline_tables = database.get("tables")
    if not isinstance(baseline_tables, dict):
        failures.append("database-schema.json tables must be an object")
        return

    metadata_tables = Base.metadata.tables
    for table_name, required_columns in REQUIRED_TABLE_COLUMNS.items():
        if table_name not in baseline_tables:
            failures.append(f"database baseline missing required table {table_name}")
            continue
        if table_name not in metadata_tables:
            failures.append(f"current metadata missing required table {table_name}")
            continue

        baseline_columns = {
            str(item.get("name"))
            for item in baseline_tables[table_name].get("columns", [])
            if isinstance(item, dict)
        }
        metadata_columns = {column.name for column in metadata_tables[table_name].columns}
        for column in sorted(required_columns):
            if column not in baseline_columns:
                failures.append(
                    f"database baseline missing required column {table_name}.{column}"
                )
            if column not in metadata_columns:
                failures.append(
                    f"current metadata missing required column {table_name}.{column}"
                )


def _verify_openapi_baseline(openapi: dict[str, Any], failures: list[str]) -> None:
    from app.main import app

    baseline_endpoints = openapi.get("endpoints")
    if not isinstance(baseline_endpoints, dict):
        failures.append("openapi-baseline.json endpoints must be an object")
        return
    current_openapi = app.openapi()
    current_paths = current_openapi.get("paths", {})

    for endpoint in sorted(REQUIRED_ENDPOINTS):
        if endpoint not in baseline_endpoints:
            failures.append(f"openapi baseline missing endpoint {endpoint}")
            continue
        method, path = endpoint.split(" ", 1)
        current_path = current_paths.get(path)
        if not isinstance(current_path, dict):
            failures.append(f"current OpenAPI missing path {path}")
            continue
        if method.lower() not in current_path:
            failures.append(f"current OpenAPI missing method {endpoint}")


def _verify_secret_scan(paths: list[Path], failures: list[str]) -> None:
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_VALUE_PATTERNS:
            if pattern.search(text):
                failures.append(
                    f"forbidden sensitive value pattern found in {path.relative_to(REPO_ROOT)}"
                )


def _prepare_import_environment() -> None:
    os.environ.setdefault("ALPACA_API_KEY", "baseline-placeholder")
    os.environ.setdefault("ALPACA_SECRET_KEY", "baseline-placeholder")
    os.environ.setdefault("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


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
