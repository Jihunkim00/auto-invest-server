from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.routes.ops as ops_routes
from app.config import Settings
from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting
from app.main import app
from app.schemas.agent_chat_orchestrator import (
    AgentChatIntent,
    AgentChatIntentCategory,
)
from app.schemas.agent_chat_tool import AgentChatToolCall
from app.services.agent_chat_tool_executor import AgentChatToolExecutor
from app.services.agent_chat_tool_registry import AgentChatToolRegistry
from app.services.ops_production_readiness_service import (
    OpsProductionReadinessService,
)


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "kis_enabled": False,
        "kis_env": "paper",
        "kis_app_key": None,
        "kis_app_secret": None,
        "kis_account_no": None,
        "kis_account_product_code": "01",
        "kis_base_url": None,
        "kis_real_order_enabled": False,
        "kis_scheduler_enabled": False,
        "kis_scheduler_dry_run": True,
        "kis_scheduler_allow_real_orders": False,
        "kr_scheduler_allow_real_orders": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _FakeClient:
    def __init__(self, *, settings=None):
        self.settings = settings or _settings()
        self.submit_calls = 0
        self.read_calls = 0

    def get_account_balance(self):
        self.read_calls += 1
        return {"cash": 500000}

    def list_positions(self):
        self.read_calls += 1
        return []

    def list_open_orders(self):
        self.read_calls += 1
        return []

    def submit_order(self, *args, **kwargs):
        self.submit_calls += 1
        raise AssertionError("readiness endpoint must not submit")

    def submit_domestic_cash_order(self, *args, **kwargs):
        self.submit_calls += 1
        raise AssertionError("readiness endpoint must not submit")

    def submit_market_buy(self, *args, **kwargs):
        self.submit_calls += 1
        raise AssertionError("readiness endpoint must not submit")

    def submit_market_sell(self, *args, **kwargs):
        self.submit_calls += 1
        raise AssertionError("readiness endpoint must not submit")


@pytest.fixture()
def api_client(db_session, monkeypatch):
    fake = _FakeClient()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(ops_routes, "_kis_client", lambda db: fake)
    try:
        yield TestClient(app), fake
    finally:
        app.dependency_overrides.clear()


def test_endpoint_returns_pr91_readiness_shape_and_is_read_only(api_client, db_session):
    client, fake = api_client

    response = client.get("/ops/production-readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["generated_at"]
    assert body["timezone"] == "Asia/Seoul"
    assert body["provider"] == "kis"
    assert body["market"] == "KR"
    assert body["overall_status"] in {"ready", "warning", "blocked", "unknown"}
    assert isinstance(body["readiness_score"], int)
    assert body["summary"]["can_enable_scheduler_live_orders"] is False
    assert body["summary"]["scheduler_real_orders_allowed"] is False
    assert body["summary"]["automation_unlock_allowed"] is False
    assert body["safety_flags"]["read_only"] is True
    assert body["safety_flags"]["orders_mutated"] is False
    assert body["mode"] == "ops_production_readiness"
    assert body["readiness_only"] is True
    assert body["checklist"]
    assert fake.submit_calls == 0
    assert fake.read_calls == 0
    assert db_session.query(OrderLog).count() == 0

    item = body["checklist"][0]
    assert {
        "key",
        "category",
        "status",
        "title",
        "detail",
        "blocking",
        "severity",
        "related_type",
        "related_id",
        "next_safe_action",
    }.issubset(item)


def test_query_parameters_provider_market_include_details(api_client):
    client, _ = api_client

    response = client.get(
        "/ops/production-readiness",
        params={"provider": "alpaca", "market": "US", "include_details": False},
    )

    body = response.json()
    assert body["provider"] == "alpaca"
    assert body["market"] == "US"
    assert body["details"] == {}
    assert body["checklist"]


def test_kill_switch_true_produces_blocked_check(api_client, db_session):
    client, _ = api_client
    db_session.add(RuntimeSetting(kill_switch=True, dry_run=True))
    db_session.commit()

    body = client.get("/ops/production-readiness").json()

    assert body["overall_status"] == "blocked"
    assert "kill_switch_off" in body["blocking_reasons"]
    check = _check_by_key(body, "kill_switch_off")
    assert check["status"] == "fail"
    assert check["blocking"] is True
    assert check["severity"] == "critical"


def test_dry_run_blocks_live_without_critical_system_failure(api_client, db_session):
    client, _ = api_client
    db_session.add(RuntimeSetting(dry_run=True, kill_switch=False))
    db_session.commit()

    body = client.get("/ops/production-readiness").json()

    check = _check_by_key(body, "dry_run_blocks_live_submit")
    assert check["status"] == "warn"
    assert check["blocking"] is True
    assert check["severity"] == "warning"
    assert body["summary"]["can_use_guarded_live_buy"] is False
    assert body["summary"]["can_use_guarded_live_sell"] is False
    assert body["paper_or_dry_run_ready"] is True


def test_scheduler_real_orders_are_never_allowed_by_readiness(api_client, db_session):
    client, _ = api_client
    db_session.add(
        RuntimeSetting(
            dry_run=False,
            kill_switch=False,
            kis_scheduler_allow_real_orders=True,
            kis_scheduler_configured_allow_real_orders=True,
            strategy_auto_buy_scheduler_allow_live_orders=True,
        )
    )
    db_session.commit()

    body = client.get("/ops/production-readiness").json()

    assert body["summary"]["scheduler_real_orders_allowed"] is False
    assert body["summary"]["can_enable_scheduler_live_orders"] is False
    assert body["safety_flags"]["scheduler_real_orders_allowed"] is False
    assert body["safety_flags"]["automation_unlock_allowed"] is False
    assert _check_by_key(body, "scheduler_real_orders_allowed")["status"] == "fail"


def test_pending_rejected_stale_and_duplicate_orders_warn(api_client, db_session):
    client, _ = api_client
    stale_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2)
    db_session.add_all(
        [
            _order("005930", InternalOrderStatus.UNKNOWN_STALE.value),
            _order("035420", InternalOrderStatus.REJECTED.value),
            _order("000660", InternalOrderStatus.SUBMITTED.value, created_at=stale_time),
            _order("000660", InternalOrderStatus.PENDING.value, created_at=stale_time),
        ]
    )
    db_session.commit()

    body = client.get("/ops/production-readiness").json()

    assert _check_by_key(body, "pending_sync_count")["status"] == "warn"
    assert _check_by_key(body, "rejected_order_count")["status"] == "warn"
    assert _check_by_key(body, "unknown_order_count")["status"] == "warn"
    assert _check_by_key(body, "stale_order_count")["status"] == "warn"
    assert _check_by_key(body, "duplicate_open_order_risk_count")["status"] == "warn"
    assert body["summary"]["pending_sync_count"] >= 1
    assert body["summary"]["rejected_order_count"] >= 1


def test_incomplete_pl_produces_warning(api_client, db_session):
    client, _ = api_client
    db_session.add(
        _order(
            "005930",
            InternalOrderStatus.FILLED.value,
            side="buy",
            qty=3,
            filled_qty=3,
            filled_avg_price=None,
        )
    )
    db_session.commit()

    body = client.get("/ops/production-readiness").json()

    assert _check_by_key(body, "incomplete_pl_count")["status"] == "warn"
    assert _check_by_key(body, "lifecycle_calculation_incomplete_count")[
        "status"
    ] == "warn"
    assert body["details"]["positions"]["incomplete_pl_count"] >= 1


def test_active_alerts_are_reflected_from_alert_service(api_client, db_session):
    client, _ = api_client
    db_session.add(_order("005930", InternalOrderStatus.REJECTED.value))
    db_session.commit()

    body = client.get("/ops/production-readiness").json()

    assert body["summary"]["active_alert_count"] >= 1
    assert _check_by_key(body, "active_alert_count")["status"] == "warn"


def test_endpoint_does_not_mutate_settings_or_orders(api_client, db_session):
    client, _ = api_client
    db_session.add(RuntimeSetting(dry_run=True, kill_switch=False))
    db_session.add(_order("005930", InternalOrderStatus.REQUESTED.value))
    db_session.commit()
    before_settings = db_session.query(RuntimeSetting).count()
    before_orders = db_session.query(OrderLog).count()

    response = client.get("/ops/production-readiness")

    assert response.status_code == 200
    assert db_session.query(RuntimeSetting).count() == before_settings
    assert db_session.query(OrderLog).count() == before_orders


def test_endpoint_does_not_call_broker_submit_or_read_methods(api_client):
    client, fake = api_client

    response = client.get("/ops/production-readiness")

    assert response.status_code == 200
    assert fake.submit_calls == 0
    assert fake.read_calls == 0


def test_agent_chat_production_readiness_tool_is_read_only(db_session):
    registry = AgentChatToolRegistry()
    assert registry.can_auto_execute("ops_production_readiness_lookup") is True

    executor = AgentChatToolExecutor(
        registry=registry,
        kis_client_factory=lambda db: _FakeClient(),
    )
    result = executor.execute(
        db_session,
        call=AgentChatToolCall(
            tool_name="ops_production_readiness_lookup",
            arguments={"provider": "kis", "market": "KR"},
        ),
        intent=AgentChatIntent(
            category=AgentChatIntentCategory.READ_ONLY_PRODUCTION_READINESS_QUERY,
            provider="kis",
            market="KR",
        ),
    )

    assert result.status == "success"
    assert result.result_type == "production_readiness"
    assert result.data["safety_flags"]["read_only"] is True
    assert result.safety.read_only is True
    assert result.safety.mutation is False
    assert result.safety.real_order_submitted is False
    assert result.safety.broker_submit_called is False
    assert result.safety.scheduler_changed is False


def test_ops_readiness_service_has_no_direct_trade_path():
    source = inspect.getsource(OpsProductionReadinessService)

    for forbidden in [
        "submit_order",
        "submit_domestic_cash_order",
        "submit_market_buy",
        "submit_market_sell",
        "submit_manual",
        "KisManualOrderService",
        "confirm_live",
        "update_settings",
        "set_setting",
        "sync_order",
    ]:
        assert forbidden not in source


def _order(
    symbol: str,
    status: str,
    *,
    side: str = "buy",
    qty: float | None = 1,
    filled_qty: float | None = None,
    filled_avg_price: float | None = None,
    created_at: datetime | None = None,
) -> OrderLog:
    return OrderLog(
        broker="kis",
        market="KR",
        symbol=symbol,
        side=side,
        order_type="market",
        qty=qty,
        filled_qty=filled_qty,
        filled_avg_price=filled_avg_price,
        internal_status=status,
        request_payload=json.dumps({"read_only_test": True}),
        created_at=created_at or datetime.now(UTC).replace(tzinfo=None),
    )


def _check_by_key(body, key):
    for item in body["checklist"]:
        if item["key"] == key:
            return item
    raise AssertionError(f"missing checklist item {key}")
