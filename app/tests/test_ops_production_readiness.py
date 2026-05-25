from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import app.routes.ops as ops_routes
from app.config import Settings
from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, TradeRunLog
from app.main import app
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
    def __init__(self, *, settings=None, open_orders=None):
        self.settings = settings or _settings()
        self.open_orders = open_orders if open_orders is not None else []
        self.submit_calls = 0

    def get_account_balance(self):
        return {
            "cash": 500000,
            "total_asset_value": 1000000,
            "stock_evaluation_amount": 500000,
        }

    def list_positions(self):
        return [{"symbol": "005930", "qty": 1, "current_price": 70000}]

    def list_open_orders(self):
        return self.open_orders

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

    @property
    def client(self):
        return self

    @property
    def broker(self):
        return self

    def submit(self, *args, **kwargs):
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


def test_endpoint_returns_readiness_only_and_does_not_submit(api_client, db_session):
    client, fake = api_client

    response = client.get("/ops/production-readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "ops_production_readiness"
    assert body["readiness_only"] is True
    assert body["summary"]["overall_status"] in {"SAFE_DRY_RUN", "BLOCKED"}
    assert body["summary"]["overall_status"] not in {"LIVE_READY", "LIVE_ENABLED"}
    assert body["live_trading_ready"] is False
    assert body["paper_or_dry_run_ready"] is True
    assert fake.submit_calls == 0
    assert db_session.query(OrderLog).count() == 0


def test_kill_switch_true_returns_blocking_issue(api_client, db_session):
    client, _ = api_client
    db_session.add(RuntimeSetting(kill_switch=True, dry_run=True))
    db_session.commit()

    body = client.get("/ops/production-readiness").json()

    assert "kill_switch_enabled" in body["blocking_issues"]
    kill_switch_check = _check_by_key(body, "kill_switch")
    assert kill_switch_check["status"] == "FAIL"


def test_dry_run_blocks_live_but_is_safe_for_dry_run(api_client, db_session):
    client, _ = api_client
    db_session.add(RuntimeSetting(dry_run=True, kill_switch=False))
    db_session.commit()

    body = client.get("/ops/production-readiness").json()

    assert body["summary"]["dry_run"] is True
    assert body["live_trading_ready"] is False
    assert body["paper_or_dry_run_ready"] is True
    assert "dry_run_enabled" in body["blocking_issues"]


def test_scheduler_real_orders_disabled_blocks_live_readiness(api_client):
    client, _ = api_client

    body = client.get("/ops/production-readiness").json()

    assert body["scheduler"]["scheduler_real_orders_allowed"] is False
    assert "scheduler_real_orders_disabled" in body["blocking_issues"]


def test_kr_watchlist_baseline_verifies_count_and_required_symbols(api_client):
    client, _ = api_client

    body = client.get("/ops/production-readiness").json()
    watchlist_check = _check_by_key(body, "kr_watchlist_baseline")

    assert watchlist_check["status"] == "PASS"
    assert watchlist_check["value"]["symbol_count"] == 50
    assert watchlist_check["value"]["required_symbols"]["005930"] is True
    assert watchlist_check["value"]["required_symbols"]["035420"] is True


def test_db_writable_check_passes_in_pytest_database(api_client):
    client, _ = api_client

    body = client.get("/ops/production-readiness").json()

    assert _check_by_key(body, "db_writable")["status"] == "PASS"


def test_recent_activity_summary_counts_runs_and_orders(api_client, db_session):
    client, _ = api_client
    now = datetime.now(UTC).replace(tzinfo=None)
    db_session.add_all(
        [
            TradeRunLog(
                run_key="run-1",
                trigger_source="scheduler_guarded_buy",
                symbol="005930",
                mode="kis_scheduler_guarded_buy",
                result="blocked",
                reason="scheduler_real_orders_disabled",
                response_payload=json.dumps(
                    {
                        "block_reasons": ["scheduler_real_orders_disabled"],
                        "real_order_submitted": False,
                    }
                ),
                created_at=now,
            ),
            TradeRunLog(
                run_key="run-2",
                trigger_source="scheduler_dry_run",
                symbol="WATCHLIST",
                mode="kis_scheduler_dry_run_orchestration",
                result="completed",
                reason="dry_run_completed",
                created_at=now,
            ),
            OrderLog(
                broker="kis",
                market="KR",
                symbol="005930",
                side="buy",
                order_type="market",
                qty=1,
                internal_status=InternalOrderStatus.SUBMITTED.value,
                broker_order_id="BRK-1",
                kis_odno="ODNO-1",
                response_payload=json.dumps(
                    {
                        "source": "kis_limited_auto_buy",
                        "real_order_submitted": True,
                        "broker_submit_called": True,
                        "manual_submit_called": True,
                    }
                ),
                created_at=now,
            ),
        ]
    )
    db_session.commit()

    body = client.get("/ops/production-readiness").json()

    assert body["today"]["total_runs"] == 2
    assert body["today"]["scheduler_guarded_buy_runs"] == 1
    assert body["today"]["scheduler_dry_run_runs"] == 1
    assert body["today"]["order_logs_created"] == 1
    assert body["today"]["broker_submits"] == 1
    assert body["today"]["real_order_submitted_count"] == 1
    assert body["today"]["manual_submit_count"] == 1
    assert body["risk"]["today_broker_submit_count"] == 1


def test_safety_checks_include_required_keys(api_client):
    client, _ = api_client

    body = client.get("/ops/production-readiness").json()
    keys = {item["key"] for item in body["safety_checks"]}

    for key in {
        "dry_run",
        "kill_switch",
        "kis_real_order_enabled",
        "scheduler_real_orders_allowed",
        "scheduler_sell_enabled",
        "scheduler_buy_enabled",
        "kr_watchlist_baseline",
        "db_writable",
        "production_docs_present",
        "env_example_present",
        "required_env_vars_documented",
    }:
        assert key in keys


def test_docs_and_env_checks_are_represented(api_client):
    client, _ = api_client

    body = client.get("/ops/production-readiness").json()

    assert "documentation" in body
    assert "README.md" in body["documentation"]["files"]
    assert ".env.example" in body["documentation"]["files"]
    assert _check_by_key(body, "production_docs_present")["status"] in {
        "PASS",
        "FAIL",
    }


def test_endpoint_does_not_create_order_log(api_client, db_session):
    client, _ = api_client
    before = db_session.query(OrderLog).count()

    response = client.get("/ops/production-readiness")

    assert response.status_code == 200
    assert db_session.query(OrderLog).count() == before


def test_endpoint_does_not_call_broker_submit_methods(api_client):
    client, fake = api_client

    response = client.get("/ops/production-readiness")

    assert response.status_code == 200
    assert fake.submit_calls == 0


def test_ops_readiness_service_has_no_direct_submit_path():
    source = inspect.getsource(OpsProductionReadinessService)

    for forbidden in [
        "submit_order",
        "submit_domestic_cash_order",
        "submit_market_buy",
        "submit_market_sell",
        "submit_manual",
        "self.client.submit",
        "self.broker.submit",
    ]:
        assert forbidden not in source


def _check_by_key(body, key):
    for item in body["safety_checks"]:
        if item["key"] == key:
            return item
    raise AssertionError(f"missing safety check {key}")
