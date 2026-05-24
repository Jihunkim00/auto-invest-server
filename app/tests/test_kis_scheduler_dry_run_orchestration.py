from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, TradeRunLog
from app.main import app


class _FakeClient:
    def __init__(self):
        self.settings = SimpleNamespace(
            kis_enabled=True,
            kis_real_order_enabled=True,
            kis_scheduler_enabled=False,
            kis_scheduler_dry_run=True,
            kis_scheduler_allow_real_orders=False,
            kr_scheduler_enabled=False,
            kr_scheduler_allow_real_orders=False,
        )

    def get_account_balance(self):
        return {"cash": 3_000_000, "total_asset_value": 10_000_000}

    def list_positions(self):
        return []

    def list_open_orders(self):
        return []

    def submit_order(self, *args, **kwargs):
        pytest.fail("scheduler dry-run orchestration must not use broker paths")

    def submit_domestic_cash_order(self, *args, **kwargs):
        pytest.fail("scheduler dry-run orchestration must not use broker paths")

    def submit_market_buy(self, *args, **kwargs):
        pytest.fail("scheduler dry-run orchestration must not use broker paths")

    def submit_market_sell(self, *args, **kwargs):
        pytest.fail("scheduler dry-run orchestration must not use broker paths")


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_default_dry_run_orchestration_never_submits(
    monkeypatch,
    client,
):
    calls = _patch_modules(monkeypatch)
    _patch_client(monkeypatch)

    response = client.post("/kis/scheduler/run-dry-run-orchestration-once")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "kis_scheduler_dry_run_orchestration"
    assert body["readiness_only"] is True
    assert body["dry_run"] is True
    assert body["scheduler_real_orders_enabled"] is False
    assert body["real_order_submit_allowed"] is False
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["summary"]["submitted_order_count"] == 0
    assert body["summary"]["broker_submit_count"] == 0
    assert body["summary"]["manual_submit_count"] == 0
    assert calls["order"] == ["sell", "buy"]


def test_scheduler_disabled_still_returns_dry_run_readiness_without_submit(
    monkeypatch,
    client,
    db_session,
):
    _patch_modules(monkeypatch)
    _patch_client(monkeypatch)
    _runtime(db_session, scheduler_enabled=False)

    body = client.post("/kis/scheduler/run-dry-run-orchestration-once").json()

    assert body["result"] == "completed"
    assert body["safety"]["scheduler_dry_run_orchestration"] is True
    assert "scheduler_disabled" in body["block_reasons"]
    assert body["broker_submit_called"] is False


def test_include_sell_returns_limited_auto_sell_child_in_dry_run_mode(
    monkeypatch,
    client,
):
    _patch_modules(monkeypatch)
    _patch_client(monkeypatch)

    body = client.post(
        "/kis/scheduler/run-dry-run-orchestration-once",
        json={"include_sell": True, "include_buy": False},
    ).json()

    child = _child(body, "limited_auto_sell")
    assert child["result"] == "blocked"
    assert child["real_order_submitted"] is False
    assert child["broker_submit_called"] is False
    assert child["manual_submit_called"] is False
    assert child["summary"]["called_in_dry_run_mode"] is True


def test_include_buy_returns_limited_auto_buy_child_in_dry_run_mode(
    monkeypatch,
    client,
):
    _patch_modules(monkeypatch)
    _patch_client(monkeypatch)

    body = client.post(
        "/kis/scheduler/run-dry-run-orchestration-once",
        json={"include_sell": False, "include_buy": True},
    ).json()

    child = _child(body, "limited_auto_buy")
    assert child["result"] == "ready"
    assert child["action"] == "buy_ready"
    assert child["real_order_submitted"] is False
    assert child["broker_submit_called"] is False
    assert child["manual_submit_called"] is False
    assert child["summary"]["called_in_dry_run_mode"] is True


def test_position_sell_module_runs_before_buy_module(monkeypatch, client):
    calls = _patch_modules(monkeypatch)
    _patch_client(monkeypatch)

    body = client.post("/kis/scheduler/run-dry-run-orchestration-once").json()

    modules = [child["module"] for child in body["child_runs"]]
    assert modules.index("portfolio_management") < modules.index("limited_auto_sell")
    assert modules.index("limited_auto_sell") < modules.index("limited_auto_buy")
    assert calls["order"] == ["sell", "buy"]


def test_sell_ready_skips_buy_without_submit(monkeypatch, client):
    calls = _patch_modules(monkeypatch, sell_payload=_sell_ready_payload())
    _patch_client(monkeypatch)

    body = client.post("/kis/scheduler/run-dry-run-orchestration-once").json()

    sell_child = _child(body, "limited_auto_sell")
    buy_child = _child(body, "limited_auto_buy")
    assert sell_child["action"] == "sell_ready"
    assert buy_child["result"] == "skipped"
    assert buy_child["primary_block_reason"] == "sell_review_required_before_buy"
    assert buy_child["real_order_submitted"] is False
    assert calls["order"] == ["sell"]


def test_runtime_gates_true_still_uses_preflight_and_does_not_submit(
    monkeypatch,
    client,
    db_session,
):
    calls = _patch_modules(monkeypatch)
    _patch_client(monkeypatch)
    _runtime(
        db_session,
        dry_run=False,
        scheduler_enabled=True,
        kis_live_auto_buy_enabled=True,
        kis_live_auto_sell_enabled=True,
        kis_limited_auto_buy_enabled=True,
        kis_limited_auto_sell_enabled=True,
        kis_limited_auto_sell_stop_loss_enabled=True,
        kis_limited_auto_sell_take_profit_enabled=True,
        kis_scheduler_live_enabled=True,
        kis_scheduler_allow_real_orders=True,
        kis_scheduler_allow_limited_auto_buy=True,
        kis_scheduler_allow_limited_auto_sell=True,
    )

    body = client.post("/kis/scheduler/run-dry-run-orchestration-once").json()

    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["safety"]["limited_buy_called_in_dry_run_mode"] is True
    assert body["safety"]["limited_sell_called_in_dry_run_mode"] is True
    assert calls["runtime"]["sell"]["dry_run"] is True
    assert calls["runtime"]["buy"]["dry_run"] is True
    assert calls["runtime"]["buy"]["kis_scheduler_allow_real_orders"] is False


def test_no_manual_or_broker_submit_call(monkeypatch, client):
    _patch_modules(monkeypatch)
    _patch_client(monkeypatch)
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("manual path must not run"),
    )

    body = client.post("/kis/scheduler/run-dry-run-orchestration-once").json()

    assert body["manual_submit_called"] is False
    assert body["broker_submit_called"] is False


def test_no_order_log_creation(monkeypatch, client, db_session):
    _patch_modules(monkeypatch)
    _patch_client(monkeypatch)

    before = db_session.query(OrderLog).count()
    body = client.post("/kis/scheduler/run-dry-run-orchestration-once").json()
    after = db_session.query(OrderLog).count()

    assert before == 0
    assert after == 0
    assert body["safety"]["no_order_log_created"] is True


def test_parent_trade_run_log_is_created_with_safe_flags(
    monkeypatch,
    client,
    db_session,
):
    _patch_modules(monkeypatch)
    _patch_client(monkeypatch)

    body = client.post(
        "/kis/scheduler/run-dry-run-orchestration-once",
        json={"slot_label": "manual_dry_run"},
    ).json()

    row = (
        db_session.query(TradeRunLog)
        .filter(TradeRunLog.mode == "kis_scheduler_dry_run_orchestration")
        .one()
    )
    response_payload = json.loads(row.response_payload)
    assert body["parent_run_id"] == row.id
    assert row.trigger_source == "scheduler_dry_run_orchestration"
    assert response_payload["real_order_submitted"] is False
    assert response_payload["broker_submit_called"] is False
    assert response_payload["manual_submit_called"] is False


def test_include_raw_false_hides_raw_child_payload(monkeypatch, client):
    _patch_modules(monkeypatch)
    _patch_client(monkeypatch)

    body = client.post(
        "/kis/scheduler/run-dry-run-orchestration-once",
        json={"include_raw": False},
    ).json()

    assert all("raw_payload" not in child for child in body["child_runs"])


def test_include_raw_true_includes_raw_child_payload(monkeypatch, client):
    _patch_modules(monkeypatch)
    _patch_client(monkeypatch)

    body = client.post(
        "/kis/scheduler/run-dry-run-orchestration-once",
        json={"include_raw": True},
    ).json()

    assert _child(body, "limited_auto_sell")["raw_payload"]["mode"] == (
        "kis_limited_auto_stop_loss_preflight"
    )
    assert _child(body, "limited_auto_buy")["raw_payload"]["mode"] == (
        "kis_limited_auto_buy_preflight"
    )


def _patch_client(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr("app.routes.kis._client", lambda db: fake)
    return fake


def _patch_modules(monkeypatch, *, sell_payload=None, buy_payload=None):
    calls = {"order": [], "runtime": {}}
    sell_payload = sell_payload or _sell_blocked_payload()
    buy_payload = buy_payload or _buy_ready_payload()

    class FakeSellService:
        def __init__(self, client, *, runtime_settings=None, **kwargs):
            self.runtime_settings = runtime_settings

        def status(self, db):
            return {
                "result": "ready",
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }

        def preflight_once(self, db):
            calls["order"].append("sell")
            calls["runtime"]["sell"] = self.runtime_settings.get_settings(db)
            return sell_payload

        def run_once(self, *args, **kwargs):
            pytest.fail("scheduler dry-run must not call sell execution")

    class FakeBuyService:
        def __init__(self, client, *, runtime_settings=None, **kwargs):
            self.runtime_settings = runtime_settings

        def status(self, db, **kwargs):
            return {
                "result": "ready",
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }

        def preflight_once(self, db, **kwargs):
            calls["order"].append("buy")
            calls["runtime"]["buy"] = self.runtime_settings.get_settings(db)
            return buy_payload

        def run_once(self, *args, **kwargs):
            pytest.fail("scheduler dry-run must not call buy execution")

    monkeypatch.setattr(
        "app.services.kis_scheduler_dry_run_orchestration_service.KisLimitedAutoSellService",
        FakeSellService,
    )
    monkeypatch.setattr(
        "app.services.kis_scheduler_dry_run_orchestration_service.KisLimitedAutoBuyService",
        FakeBuyService,
    )
    monkeypatch.setattr(
        "app.services.kis_scheduler_readiness_service.KisLimitedAutoSellService",
        FakeSellService,
    )
    monkeypatch.setattr(
        "app.services.kis_scheduler_readiness_service.KisLimitedAutoBuyService",
        FakeBuyService,
    )
    return calls


def _sell_blocked_payload():
    return {
        "status": "ok",
        "provider": "kis",
        "market": "KR",
        "mode": "kis_limited_auto_stop_loss_preflight",
        "source": "kis_limited_auto_stop_loss",
        "trigger_source": "kis_limited_auto_sell",
        "result": "blocked",
        "action": "hold",
        "reason": "no_held_position",
        "primary_block_reason": "no_held_position",
        "candidate_count": 0,
        "candidates": [],
        "block_reasons": ["preflight_read_only_no_submit", "no_held_position"],
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "order_id": None,
        "diagnostics": {"positions_evaluated": 0},
    }


def _sell_ready_payload():
    return {
        "status": "ok",
        "provider": "kis",
        "market": "KR",
        "mode": "kis_limited_auto_stop_loss_preflight",
        "source": "kis_limited_auto_stop_loss",
        "trigger_source": "kis_limited_auto_sell",
        "result": "preview_only",
        "action": "sell_ready",
        "symbol": "005930",
        "reason": "stop_loss_candidate_ready_read_only",
        "primary_block_reason": "stop_loss_candidate_ready_read_only",
        "candidate_count": 1,
        "candidates": [{"symbol": "005930"}],
        "block_reasons": ["preflight_read_only_no_submit"],
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "order_id": None,
        "diagnostics": {"positions_evaluated": 1},
    }


def _buy_ready_payload():
    return {
        "status": "ok",
        "provider": "kis",
        "market": "KR",
        "mode": "kis_limited_auto_buy_preflight",
        "source": "kis_limited_auto_buy",
        "trigger_source": "limited_auto_buy_preflight",
        "result": "ready",
        "action": "buy_ready",
        "symbol": "035420",
        "reason": "buy_readiness_only",
        "primary_block_reason": "dry_run_enabled",
        "candidate_count": 1,
        "candidates": [{"symbol": "035420"}],
        "block_reasons": ["dry_run_enabled"],
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "order_id": None,
    }


def _child(body, module):
    for child in body["child_runs"]:
        if child["module"] == module:
            return child
    pytest.fail(f"missing child module {module}")


def _runtime(db_session, **overrides):
    db_session.query(RuntimeSetting).delete()
    values = {
        "dry_run": True,
        "kill_switch": False,
        "scheduler_enabled": False,
        "kis_live_auto_buy_enabled": False,
        "kis_live_auto_sell_enabled": False,
        "kis_limited_auto_buy_enabled": False,
        "kis_limited_auto_sell_enabled": False,
        "kis_limited_auto_sell_stop_loss_enabled": False,
        "kis_limited_auto_sell_take_profit_enabled": False,
        "kis_limited_auto_buy_readiness_enabled": True,
        "kis_limited_auto_buy_max_orders_per_day": 1,
        "kis_limited_auto_sell_max_orders_per_day": 1,
        "kis_scheduler_live_enabled": False,
        "kis_scheduler_allow_real_orders": False,
        "kis_scheduler_allow_limited_auto_buy": False,
        "kis_scheduler_allow_limited_auto_sell": False,
    }
    values.update(overrides)
    db_session.add(RuntimeSetting(**values))
    db_session.commit()
