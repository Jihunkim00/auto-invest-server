from __future__ import annotations

import json
from pathlib import Path

from app.main import app


REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_BASELINE = REPO_ROOT / "docs" / "baseline" / "openapi-baseline.json"
OPERATION_BASELINE = REPO_ROOT / "docs" / "baseline" / "operation-baseline.json"


def test_openapi_baseline_required_endpoints_still_exist():
    baseline = _baseline()
    current = app.openapi()

    for endpoint, item in baseline["endpoints"].items():
        method, path = endpoint.split(" ", 1)
        assert path in current["paths"], endpoint
        assert method.lower() in current["paths"][path], endpoint
        assert item["path"] == path
        assert item["method"] == method.lower()


def test_operation_manifest_api_contracts_match_openapi_baseline():
    operation = json.loads(OPERATION_BASELINE.read_text(encoding="utf-8"))
    openapi = _baseline()

    manifest_endpoints = {
        endpoint
        for endpoints in operation["api_contracts"].values()
        for endpoint in endpoints
    }

    assert manifest_endpoints == set(openapi["endpoints"])


def test_openapi_order_and_agent_request_fields_remain_available():
    current = app.openapi()
    schemas = current["components"]["schemas"]

    _assert_schema_fields(
        schemas,
        "KisManualOrderSubmitRequest",
        {
            "market",
            "symbol",
            "side",
            "qty",
            "order_type",
            "dry_run",
            "confirm_live",
            "confirmation",
            "source_metadata",
        },
    )
    _assert_schema_fields(
        schemas,
        "KisOrderValidationRequest",
        {"market", "symbol", "side", "qty", "order_type", "dry_run"},
    )
    _assert_schema_fields(
        schemas,
        "AgentChatSendRequest",
        {"conversation_key", "message", "context", "auto_create_conversation"},
    )
    _assert_schema_fields(
        schemas,
        "AgentChatLiveOrderConfirmRequest",
        {
            "confirmation",
            "confirmation_token",
            "confirmation_phrase",
            "user_acknowledged_live_order",
        },
    )


def test_openapi_safety_response_fields_remain_available():
    current = app.openapi()
    schemas = current["components"]["schemas"]

    _assert_schema_fields(
        schemas,
        "AutomationModeStatusResponse",
        {
            "automation_mode",
            "effective_status",
            "can_submit_live_order",
            "blocking_reasons",
            "safety_flags",
            "dry_run",
            "kill_switch",
        },
    )
    _assert_schema_fields(
        schemas,
        "AutomationReleaseStatusResponse",
        {
            "release_enabled",
            "release_mode",
            "release_armed",
            "can_submit_live_order",
            "can_run_live_phase1_cycle",
            "blocking_reasons",
            "safety_flags",
        },
    )
    _assert_schema_fields(
        schemas,
        "PortfolioOrchestratorResponse",
        {
            "orchestrator_enabled",
            "allow_live_orders",
            "max_actions_per_run",
            "real_order_submitted",
            "broker_submit_called",
            "manual_submit_called",
            "safety",
        },
    )


def test_openapi_required_request_fields_match_baseline_snapshot():
    baseline = _baseline()
    current = app.openapi()

    for endpoint, item in baseline["endpoints"].items():
        required = set(item.get("request_required_fields") or [])
        if not required:
            continue
        method, path = endpoint.split(" ", 1)
        operation = current["paths"][path][method.lower()]
        schema_ref = (
            operation.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
            .get("$ref")
        )
        schema_name = str(schema_ref or "").rsplit("/", 1)[-1]
        current_required = set(
            current["components"]["schemas"][schema_name].get("required") or []
        )
        assert required <= current_required, endpoint


def _baseline() -> dict:
    return json.loads(OPENAPI_BASELINE.read_text(encoding="utf-8"))


def _assert_schema_fields(
    schemas: dict,
    schema_name: str,
    expected_fields: set[str],
) -> None:
    schema = schemas[schema_name]
    properties = set(schema.get("properties") or {})
    missing = expected_fields - properties
    assert not missing, f"{schema_name} missing fields: {sorted(missing)}"

