from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, TradeRunLog
from app.main import app
from app.services.kis_scheduler_guarded_buy_service import (
    MODE,
    KisSchedulerGuardedBuyService,
)


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "kis_enabled": True,
        "kis_env": "prod",
        "kis_app_key": "real-app-key",
        "kis_app_secret": "real-app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_base_url": "https://openapi.koreainvestment.com:9443",
        "kis_real_order_enabled": True,
        "kis_scheduler_enabled": True,
        "kis_scheduler_dry_run": False,
        "kis_scheduler_allow_real_orders": True,
        "kr_scheduler_allow_real_orders": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _FakeClient:
    def __init__(self, *, settings=None, open_orders=None):
        self.settings = settings or _settings()
        self.open_orders = open_orders if open_orders is not None else []

    def list_open_orders(self):
        return self.open_orders


class _RuntimeSettings:
    def __init__(self, **overrides):
        self.payload = _runtime(**overrides)

    def get_settings(self, db):
        return dict(self.payload)


class _FakeReadinessService:
    def __init__(self, payload=None):
        self.payload = payload or {
            "status": "ok",
            "mode": "kis_scheduler_readiness",
            "modules": {
                "limited_auto_sell": {"available": True},
                "limited_auto_buy": {"available": True},
            },
        }
        self.calls = 0

    def readiness(self, db, **kwargs):
        self.calls += 1
        return dict(self.payload)


class _FakeLimitedSellService:
    def __init__(self, payload=None):
        self.payload = payload or _clear_sell_review()
        self.preflight_calls = 0
        self.run_calls = 0

    def preflight_once(self, db, **kwargs):
        self.preflight_calls += 1
        return dict(self.payload)

    def run_once(self, db, **kwargs):
        self.run_calls += 1
        raise AssertionError("scheduler guarded buy must not execute guarded sell")


class _FakeLimitedBuyService:
    def __init__(self, result=None):
        self.result = result if result is not None else _blocked_buy("no_candidate")
        self.calls = 0
        self.kwargs = []

    def run_once(self, db, **kwargs):
        self.calls += 1
        self.kwargs.append(kwargs)
        return dict(self.result)


class _OrderCreatingLimitedBuyService(_FakeLimitedBuyService):
    def run_once(self, db, **kwargs):
        self.calls += 1
        self.kwargs.append(kwargs)
        row = OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="buy",
            order_type="market",
            qty=4,
            requested_qty=4,
            internal_status=InternalOrderStatus.SUBMITTED.value,
            broker_order_id="KIS-BUY-1",
            kis_odno="KIS-BUY-1",
            submitted_at=datetime.now(UTC).replace(tzinfo=None),
            request_payload=json.dumps({"mode": "kis_limited_auto_buy_run"}),
            response_payload=json.dumps(
                {
                    "mode": "kis_limited_auto_buy_run",
                    "source": "kis_limited_auto_buy",
                    "source_type": "guarded_limited_auto_buy",
                    "real_order_submitted": True,
                }
            ),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        result = dict(self.result)
        result["order_id"] = row.id
        result["order_log_id"] = row.id
        return result


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_default_endpoint_blocks_without_order_submit(client, db_session):
    response = client.post("/kis/scheduler/run-guarded-buy-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == MODE
    assert body["buy_only"] is True
    assert body["sell_priority_required"] is True
    assert body["result"] == "blocked"
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["primary_block_reason"] in {
        "scheduler_real_orders_disabled",
        "scheduler_buy_disabled",
    }
    assert db_session.query(OrderLog).count() == 0


def test_status_default_is_off_and_read_only(db_session):
    result = _service(
        runtime=_RuntimeSettings(
            kis_scheduler_allow_real_orders=False,
            kis_scheduler_buy_enabled=False,
        ),
        buy=_FakeLimitedBuyService(_submitted_buy()),
    ).status(db_session)

    assert result["mode"] == "kis_scheduler_guarded_buy_status"
    assert result["buy_only"] is True
    assert result["scheduler_buy_enabled"] is False
    assert result["scheduler_real_orders_enabled"] is False
    assert result["real_order_submit_allowed"] is False
    assert result["buy_execution_allowed"] is False
    assert result["sell_review_required_before_buy"] is True
    assert result["safety"]["existing_limited_auto_buy_path_reused"] is True
    assert db_session.query(OrderLog).count() == 0


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"dry_run": True}, "runtime_dry_run_true"),
        ({"kill_switch": True}, "kill_switch_enabled"),
        ({"kis_scheduler_allow_real_orders": False}, "scheduler_real_orders_disabled"),
        ({"kis_scheduler_buy_enabled": False}, "scheduler_buy_disabled"),
        ({}, "kis_real_order_disabled"),
        ({"kis_live_auto_buy_enabled": False}, "kis_live_auto_buy_disabled"),
        ({"kis_limited_auto_buy_enabled": False}, "kis_limited_auto_buy_disabled"),
    ],
)
def test_scheduler_runtime_gates_block_before_limited_buy(
    db_session,
    overrides,
    reason,
):
    settings = _settings(kis_real_order_enabled=(reason != "kis_real_order_disabled"))
    runtime_overrides = overrides if reason != "kis_real_order_disabled" else {}
    limited_buy = _FakeLimitedBuyService(_submitted_buy())
    service = _service(
        settings=settings,
        runtime=_RuntimeSettings(**runtime_overrides),
        buy=limited_buy,
    )

    result = service.run_once(
        db_session,
        slot_label="open_phase_buy_readiness",
        trigger_source="scheduler",
    )

    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == reason
    assert result["real_order_submitted"] is False
    assert limited_buy.calls == 0
    assert db_session.query(OrderLog).count() == 0


@pytest.mark.parametrize(
    "reason",
    [
        "market_closed",
        "no_new_entry_after_blocked",
        "no_candidate",
        "duplicate_open_buy_order",
        "daily_auto_buy_limit_reached",
        "insufficient_cash",
    ],
)
def test_buy_candidate_and_cash_gates_block_through_limited_buy(
    db_session,
    reason,
):
    buy_result = _blocked_buy(reason)
    limited_buy = _FakeLimitedBuyService(buy_result)

    result = _service(buy=limited_buy).run_once(
        db_session,
        slot_label="open_phase_buy_readiness",
        trigger_source="scheduler",
    )

    assert limited_buy.calls == 1
    assert limited_buy.kwargs[0]["scheduler_context"] is True
    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == buy_result["primary_block_reason"]
    assert result["real_order_submitted"] is False
    assert db_session.query(OrderLog).count() == 0


def test_sell_ready_candidate_blocks_buy_before_limited_buy(db_session):
    limited_buy = _FakeLimitedBuyService(_submitted_buy())
    sell = _FakeLimitedSellService(_sell_ready_review())

    result = _service(buy=limited_buy, sell=sell).run_once(
        db_session,
        slot_label="open_phase_buy_readiness",
        trigger_source="scheduler",
    )

    assert sell.preflight_calls == 1
    assert sell.run_calls == 0
    assert limited_buy.calls == 0
    assert result["result"] == "skipped"
    assert result["action"] == "hold"
    assert result["primary_block_reason"] == "sell_review_required_before_buy"
    assert result["buy_result"]["buy_execution_skipped"] is True
    assert result["buy_result"]["validation_called"] is False
    assert result["real_order_submitted"] is False
    assert db_session.query(OrderLog).count() == 0


def test_open_sell_order_blocks_buy_before_limited_buy(db_session):
    limited_buy = _FakeLimitedBuyService(_submitted_buy())
    client = _FakeClient(open_orders=[{"symbol": "005930", "side": "sell"}])

    result = _service(client=client, buy=limited_buy).run_once(
        db_session,
        slot_label="open_phase_buy_readiness",
        trigger_source="scheduler",
    )

    assert limited_buy.calls == 0
    assert result["primary_block_reason"] == "open_sell_order_exists"
    assert result["buy_result"]["buy_execution_skipped"] is True


def test_all_scheduler_gates_true_calls_limited_auto_buy_guarded_path(db_session):
    limited_buy = _FakeLimitedBuyService(_blocked_buy("no_candidate"))

    result = _service(buy=limited_buy).run_once(
        db_session,
        slot_label="open_phase_buy_readiness",
        trigger_source="scheduler",
    )

    assert limited_buy.calls == 1
    assert "now" in limited_buy.kwargs[0]
    assert limited_buy.kwargs[0]["scheduler_context"] is True
    assert result["mode"] == MODE
    assert result["buy_result"]["mode"] == "kis_limited_auto_buy_run"
    assert result["safety"]["existing_limited_auto_buy_path_reused"] is True


def test_submitted_limited_buy_result_is_reflected_in_parent_response(db_session):
    limited_buy = _FakeLimitedBuyService(_submitted_buy())

    result = _service(buy=limited_buy).run_once(
        db_session,
        slot_label="open_phase_buy_readiness",
        trigger_source="scheduler",
    )

    assert result["result"] == "submitted"
    assert result["action"] == "buy"
    assert result["source"] == "kis_scheduler_guarded_buy"
    assert result["source_type"] == "scheduler_guarded_buy_execution"
    assert result["real_order_submitted"] is True
    assert result["broker_submit_called"] is True
    assert result["manual_submit_called"] is True
    assert result["order_id"] == 123
    assert result["broker_order_id"] == "BRK123"
    assert result["kis_odno"] == "KIS123"
    assert result["buy_result"]["source_type"] == "guarded_limited_auto_buy"


def test_scheduler_service_does_not_call_direct_order_paths():
    source = inspect.getsource(KisSchedulerGuardedBuyService)

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


def test_scheduler_guarded_buy_does_not_call_scheduler_guarded_sell_execution(
    db_session,
):
    sell = _FakeLimitedSellService(_clear_sell_review())

    result = _service(sell=sell, buy=_FakeLimitedBuyService(_blocked_buy())).run_once(
        db_session,
        slot_label="open_phase_buy_readiness",
        trigger_source="scheduler",
    )

    assert result["mode"] == MODE
    assert sell.preflight_calls == 1
    assert sell.run_calls == 0
    assert "KisSchedulerGuardedSellService" not in inspect.getsource(
        KisSchedulerGuardedBuyService
    )


def test_blocked_scheduler_attempt_creates_no_order_log(db_session):
    result = _service(
        runtime=_RuntimeSettings(kis_scheduler_buy_enabled=False),
        buy=_FakeLimitedBuyService(_submitted_buy()),
    ).run_once(
        db_session,
        slot_label="open_phase_buy_readiness",
        trigger_source="scheduler",
    )

    assert result["result"] == "blocked"
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(TradeRunLog).filter(TradeRunLog.mode == MODE).count() == 1


def test_submitted_attempt_uses_order_created_by_limited_buy_path_only(db_session):
    limited_buy = _OrderCreatingLimitedBuyService(_submitted_buy(order_id=None))

    result = _service(buy=limited_buy).run_once(
        db_session,
        slot_label="open_phase_buy_readiness",
        trigger_source="scheduler",
    )

    assert limited_buy.calls == 1
    assert result["result"] == "submitted"
    assert db_session.query(OrderLog).count() == 1
    order = db_session.query(OrderLog).one()
    assert result["order_id"] == order.id
    assert order.symbol == "005930"
    assert order.side == "buy"
    assert db_session.query(TradeRunLog).filter(TradeRunLog.mode == MODE).count() == 1


def _service(
    *,
    settings=None,
    runtime=None,
    buy=None,
    sell=None,
    readiness=None,
    client=None,
):
    fake_client = client or _FakeClient(settings=settings)
    return KisSchedulerGuardedBuyService(
        fake_client,
        runtime_settings=runtime or _RuntimeSettings(),
        limited_auto_buy_service=buy or _FakeLimitedBuyService(_blocked_buy()),
        limited_auto_sell_service=sell or _FakeLimitedSellService(),
        readiness_service=readiness or _FakeReadinessService(),
    )


def _runtime(**overrides):
    values = {
        "scheduler_enabled": True,
        "dry_run": False,
        "kill_switch": False,
        "kis_live_auto_buy_enabled": True,
        "kis_live_auto_sell_enabled": True,
        "kis_limited_auto_sell_enabled": True,
        "kis_limited_auto_sell_stop_loss_enabled": True,
        "kis_limited_auto_sell_take_profit_enabled": False,
        "kis_limited_auto_stop_loss_enabled": True,
        "kis_limited_auto_take_profit_enabled": False,
        "kis_limited_auto_buy_enabled": True,
        "kis_limited_auto_buy_readiness_enabled": True,
        "kis_limited_auto_buy_max_orders_per_day": 1,
        "kis_limited_auto_buy_max_notional_pct": 0.03,
        "kis_scheduler_enabled": True,
        "kis_scheduler_dry_run": False,
        "kis_scheduler_configured_allow_real_orders": True,
        "kis_scheduler_allow_real_orders": True,
        "kis_scheduler_buy_enabled": True,
        "kis_scheduler_sell_enabled": True,
        "kis_scheduler_allow_limited_auto_buy": False,
        "kis_scheduler_allow_limited_auto_sell": False,
    }
    values.update(overrides)
    return values


def _clear_sell_review():
    return {
        "status": "ok",
        "provider": "kis",
        "market": "KR",
        "mode": "kis_limited_auto_stop_loss_preflight",
        "result": "blocked",
        "action": "hold",
        "reason": "no_held_position",
        "candidate_count": 0,
        "candidates": [],
        "final_candidate": None,
        "block_reasons": ["no_held_position"],
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "market_session": {"is_market_open": True},
        "sell_session_allowed": True,
    }


def _sell_ready_review():
    return {
        **_clear_sell_review(),
        "result": "preview_only",
        "action": "sell_ready",
        "reason": "stop_loss_candidate_ready_read_only",
        "candidate_count": 1,
        "symbol": "005930",
        "final_candidate": {
            "symbol": "005930",
            "status": "SELL_READY",
            "exit_reason": "stop_loss_triggered",
        },
        "candidates": [
            {
                "symbol": "005930",
                "status": "SELL_READY",
                "exit_reason": "stop_loss_triggered",
            }
        ],
        "block_reasons": [],
    }


def _blocked_buy(reason="no_candidate"):
    return {
        "status": "ok",
        "provider": "kis",
        "market": "KR",
        "mode": "kis_limited_auto_buy_run",
        "source": "kis_limited_auto_buy",
        "source_type": "guarded_limited_auto_buy",
        "result": "blocked",
        "action": "blocked_buy",
        "reason": reason,
        "primary_block_reason": reason,
        "block_reasons": [reason],
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "validation_called": False,
        "duplicate_order_check": {
            "checked": True,
            "duplicate_open_buy_order": reason == "duplicate_open_buy_order",
        },
        "market_session": {
            "is_market_open": reason != "market_closed",
            "entry_allowed_now": reason != "no_new_entry_after_blocked",
            "no_new_entry_after": "14:50",
        },
    }


def _submitted_buy(order_id=123):
    return {
        "status": "ok",
        "provider": "kis",
        "market": "KR",
        "mode": "kis_limited_auto_buy_run",
        "source": "kis_limited_auto_buy",
        "source_type": "guarded_limited_auto_buy",
        "result": "submitted",
        "action": "buy",
        "reason": "guarded_limited_auto_buy_submitted",
        "symbol": "005930",
        "company_name": "Samsung Electronics",
        "quantity": 4,
        "qty": 4,
        "estimated_notional": 288000,
        "real_order_submit_allowed": True,
        "real_order_submitted": True,
        "broker_submit_called": True,
        "manual_submit_called": True,
        "validation_called": True,
        "order_id": order_id,
        "order_log_id": order_id,
        "broker_order_id": "BRK123",
        "kis_odno": "KIS123",
        "duplicate_order_check": {
            "checked": True,
            "duplicate_open_buy_order": False,
        },
        "market_session": {
            "is_market_open": True,
            "entry_allowed_now": True,
            "no_new_entry_after": "14:50",
        },
    }
