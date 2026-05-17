from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import (
    KisShadowExitReviewQueueState,
    OrderLog,
    RuntimeSetting,
    SignalLog,
    TradeRunLog,
)
from app.main import app
from app.services.kis_limited_auto_sell_service import (
    MODE,
    SOURCE,
    SOURCE_TYPE,
    KisLimitedAutoSellService,
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
        "kis_scheduler_allow_real_orders": False,
        "kr_scheduler_allow_real_orders": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _FakeClient:
    def __init__(
        self,
        *,
        settings=None,
        balance=None,
        positions=None,
        open_orders=None,
    ):
        self.settings = settings or SimpleNamespace(
            kis_enabled=True,
            kis_real_order_enabled=True,
            kis_scheduler_allow_real_orders=False,
            kr_scheduler_allow_real_orders=False,
        )
        self.balance = balance or {
            "provider": "kis",
            "market": "KR",
            "total_asset_value": 10_000_000,
            "cash": 1_000_000,
        }
        self.positions = positions or [_stop_loss_position()]
        self.open_orders = open_orders or []

    def get_account_balance(self):
        return self.balance

    def list_positions(self):
        return self.positions

    def list_open_orders(self):
        return self.open_orders


class _FakeBroker:
    def __init__(self):
        self.calls = []

    def submit_market_sell(self, symbol, qty):
        self.calls.append({"symbol": symbol, "qty": qty})
        return {"rt_cd": "0", "output": {"ODNO": "AUTO123456"}}

    def submit_market_buy(self, *args, **kwargs):
        raise AssertionError("limited auto sell must never buy")


class _OpenSessionService:
    def get_session_status(self, market, **kwargs):
        return {
            "market": market,
            "timezone": "Asia/Seoul",
            "is_market_open": True,
            "is_entry_allowed_now": True,
            "is_near_close": False,
            "is_holiday": False,
            "closure_reason": None,
            "effective_close": "15:30",
            "no_new_entry_after": "15:00",
        }


class _ClosedSessionService:
    def get_session_status(self, market, **kwargs):
        return {
            "market": market,
            "timezone": "Asia/Seoul",
            "is_market_open": False,
            "is_entry_allowed_now": False,
            "is_holiday": False,
            "closure_reason": "closed",
        }


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_limited_auto_sell_defaults_block_and_endpoint_is_no_submit(
    monkeypatch,
    client,
    db_session,
):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("broker submit must not run"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_order",
        lambda *args, **kwargs: pytest.fail("generic submit must not run"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("manual submit must not run"),
    )

    response = client.post("/kis/limited-auto-sell/run-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "limited_auto_sell"
    assert body["result"] == "blocked"
    assert body["reason"] == "limited_auto_sell_disabled"
    assert body["action"] == "hold"
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["auto_buy_enabled"] is False
    assert body["scheduler_real_order_enabled"] is False
    assert body["checks"]["kis_limited_auto_sell_enabled"] is False
    assert body["checks"]["dry_run"] is True
    assert db_session.query(OrderLog).count() == 0


def test_limited_auto_sell_runtime_defaults_are_safe(db_session):
    settings = RuntimeSettingServiceProxy().get(db_session)

    assert settings["kis_limited_auto_sell_enabled"] is False
    assert settings["kis_limited_auto_sell_stop_loss_enabled"] is False
    assert settings["kis_limited_auto_sell_take_profit_enabled"] is False
    assert settings["kis_limited_auto_sell_requires_queue_review"] is True
    assert settings["kis_limited_auto_sell_max_orders_per_day"] == 1
    assert settings["kis_limited_auto_sell_max_notional_pct"] == pytest.approx(0.03)
    assert settings["kis_limited_auto_sell_allow_manual_review_trigger"] is False
    assert settings["kis_limited_auto_sell_allow_take_profit_trigger"] is False
    assert settings["kis_live_auto_buy_enabled"] is False


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("kill_switch", True, "kill_switch_enabled"),
        ("dry_run", True, "runtime_dry_run_true"),
        ("kis_live_auto_enabled", False, "kis_live_auto_disabled"),
        ("kis_live_auto_sell_enabled", False, "kis_live_auto_sell_disabled"),
        ("kis_limited_auto_sell_enabled", False, "limited_auto_sell_disabled"),
        (
            "kis_limited_auto_sell_stop_loss_enabled",
            False,
            "stop_loss_auto_sell_disabled",
        ),
        ("kis_live_auto_buy_enabled", True, "auto_buy_must_remain_disabled"),
    ],
)
def test_limited_auto_sell_runtime_gates_block_without_submit(
    db_session,
    field,
    value,
    reason,
):
    _enable_runtime(db_session, **{field: value})
    broker = _FakeBroker()

    result = _service(broker=broker).run_once(db_session)

    assert result["result"] == "blocked"
    assert result["reason"] == reason
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["manual_submit_called"] is False
    assert broker.calls == []
    assert db_session.query(OrderLog).count() == 0


@pytest.mark.parametrize(
    ("settings_override", "reason"),
    [
        ({"kis_enabled": False}, "kis_disabled"),
        ({"kis_real_order_enabled": False}, "kis_real_order_disabled"),
        ({"kis_scheduler_allow_real_orders": True}, "scheduler_real_orders_must_remain_disabled"),
    ],
)
def test_limited_auto_sell_config_gates_block_without_submit(
    db_session,
    settings_override,
    reason,
):
    _enable_runtime(db_session)
    broker = _FakeBroker()
    service = _service(
        client=_FakeClient(
            settings=SimpleNamespace(
                kis_enabled=settings_override.get("kis_enabled", True),
                kis_real_order_enabled=settings_override.get(
                    "kis_real_order_enabled", True
                ),
                kis_scheduler_allow_real_orders=settings_override.get(
                    "kis_scheduler_allow_real_orders", False
                ),
                kr_scheduler_allow_real_orders=False,
            )
        ),
        broker=broker,
    )

    result = service.run_once(db_session)

    assert result["reason"] == reason
    assert broker.calls == []
    assert result["real_order_submitted"] is False


def test_limited_auto_sell_market_closed_blocks(db_session):
    _enable_runtime(db_session)
    broker = _FakeBroker()
    service = _service(broker=broker, session_service=_ClosedSessionService())

    result = service.run_once(db_session)

    assert result["reason"] == "market_closed"
    assert broker.calls == []


@pytest.mark.parametrize(
    ("position_name", "reason"),
    [
        ("take_profit", "take_profit_auto_sell_disabled"),
        ("manual_review", "manual_review_auto_sell_disabled"),
        ("missing_cost_basis", "missing_cost_basis"),
        ("missing_price", "missing_current_price"),
        ("raw_plpc_only", "missing_cost_basis"),
    ],
)
def test_limited_auto_sell_trigger_rules_block_unsafe_candidates(
    db_session,
    position_name,
    reason,
):
    _enable_runtime(db_session, kis_limited_auto_sell_requires_queue_review=False)
    broker = _FakeBroker()

    result = _service(
        client=_FakeClient(positions=[_position_fixture(position_name)]),
        broker=broker,
    ).run_once(db_session)

    assert result["reason"] == reason
    assert result["real_order_submitted"] is False
    assert broker.calls == []


def test_limited_auto_sell_queue_review_required_blocks_without_mutation(db_session):
    _enable_runtime(db_session)
    _seed_shadow(db_session)
    broker = _FakeBroker()

    result = _service(broker=broker).run_once(db_session)

    assert result["reason"] == "queue_review_required"
    assert result["queue_review_status"] == "open"
    assert broker.calls == []
    assert db_session.query(KisShadowExitReviewQueueState).count() == 0


def test_limited_auto_sell_reviewed_queue_allows_next_gates(db_session):
    _enable_runtime(db_session)
    _seed_shadow(db_session)
    _mark_queue_reviewed(db_session)
    broker = _FakeBroker()

    result = _service(broker=broker).run_once(db_session)

    assert result["result"] == "submitted"
    assert result["queue_review_status"] == "reviewed"
    assert db_session.query(KisShadowExitReviewQueueState).one().status == "reviewed"


@pytest.mark.parametrize(
    ("position_name", "reason"),
    [
        ("oversized", "notional_cap_exceeded"),
        ("zero_qty", "no_held_position"),
    ],
)
def test_limited_auto_sell_trade_limits_block_position_risk(
    db_session,
    position_name,
    reason,
):
    _enable_runtime(db_session, kis_limited_auto_sell_requires_queue_review=False)
    broker = _FakeBroker()

    result = _service(
        client=_FakeClient(positions=[_position_fixture(position_name)]),
        broker=broker,
    ).run_once(db_session)

    assert result["reason"] == reason
    assert broker.calls == []


def test_limited_auto_sell_duplicate_open_order_blocks(db_session):
    _enable_runtime(db_session, kis_limited_auto_sell_requires_queue_review=False)
    broker = _FakeBroker()

    result = _service(
        client=_FakeClient(open_orders=[{"symbol": "005930", "side": "sell"}]),
        broker=broker,
    ).run_once(db_session)

    assert result["reason"] == "duplicate_open_order"
    assert broker.calls == []


def test_limited_auto_sell_max_one_order_per_day_blocks(db_session):
    _enable_runtime(db_session, kis_limited_auto_sell_requires_queue_review=False)
    _seed_limited_order(db_session)
    broker = _FakeBroker()

    result = _service(broker=broker).run_once(db_session)

    assert result["reason"] == "daily_limited_auto_sell_limit_reached"
    assert broker.calls == []


def test_limited_auto_sell_min_shadow_occurrence_blocks(db_session):
    _enable_runtime(db_session, kis_limited_auto_sell_requires_queue_review=False)
    broker = _FakeBroker()

    result = _service(broker=broker).run_once(db_session)

    assert result["reason"] == "min_shadow_occurrences_not_met"
    assert broker.calls == []


def test_limited_auto_sell_submits_exactly_one_sell_and_logs_audit(db_session):
    _enable_runtime(db_session)
    _seed_shadow(db_session)
    _mark_queue_reviewed(db_session)
    broker = _FakeBroker()

    result = _service(broker=broker).run_once(db_session)

    assert result["result"] == "submitted"
    assert result["action"] == "sell"
    assert result["trigger"] == "stop_loss"
    assert result["real_order_submitted"] is True
    assert result["broker_submit_called"] is True
    assert result["manual_submit_called"] is False
    assert result["auto_buy_enabled"] is False
    assert broker.calls == [{"symbol": "005930", "qty": 1}]
    order = db_session.query(OrderLog).one()
    assert order.broker == "kis"
    assert order.market == "KR"
    assert order.side == "sell"
    assert order.internal_status == InternalOrderStatus.SUBMITTED.value
    assert order.kis_odno == "AUTO123456"
    assert json.loads(order.request_payload)["mode"] == MODE
    response_payload = json.loads(order.response_payload)
    assert response_payload["source"] == SOURCE
    assert response_payload["source_type"] == SOURCE_TYPE
    assert response_payload["audit_metadata"]["trigger_source"] == "cost_basis_pl_pct"
    assert response_payload["audit_metadata"]["queue_review_status"] == "reviewed"
    assert db_session.query(SignalLog).count() == 1
    assert db_session.query(TradeRunLog).filter(TradeRunLog.mode == MODE).count() == 1


def test_limited_auto_sell_history_serializes_distinct_mode(db_session, client):
    _enable_runtime(db_session)
    _seed_shadow(db_session)
    _mark_queue_reviewed(db_session)
    _service(broker=_FakeBroker()).run_once(db_session)

    response = client.get("/orders/recent")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["mode"] == MODE
    assert item["source"] == SOURCE
    assert item["source_type"] == SOURCE_TYPE
    assert item["side"] == "sell"
    assert item["exit_trigger"] == "stop_loss"
    assert item["auto_buy_enabled"] is False
    assert item["scheduler_real_order_enabled"] is False
    assert item["manual_submit_called"] is False


def _service(client=None, broker=None, session_service=None):
    return KisLimitedAutoSellService(
        client or _FakeClient(),
        broker=broker or _FakeBroker(),
        session_service=session_service or _OpenSessionService(),
    )


class RuntimeSettingServiceProxy:
    def get(self, db_session):
        from app.services.runtime_setting_service import RuntimeSettingService

        return RuntimeSettingService().get_settings(db_session)


def _enable_runtime(db_session, **overrides):
    db_session.query(RuntimeSetting).delete()
    values = {
        "dry_run": False,
        "kill_switch": False,
        "kis_live_auto_enabled": True,
        "kis_live_auto_buy_enabled": False,
        "kis_live_auto_sell_enabled": True,
        "kis_limited_auto_sell_enabled": True,
        "kis_limited_auto_sell_stop_loss_enabled": True,
        "kis_limited_auto_sell_take_profit_enabled": False,
        "kis_limited_auto_sell_requires_queue_review": True,
        "kis_limited_auto_sell_max_orders_per_day": 1,
        "kis_limited_auto_sell_max_notional_pct": 0.03,
        "kis_limited_auto_sell_min_shadow_occurrences": 1,
        "kis_limited_auto_sell_allow_manual_review_trigger": False,
        "kis_limited_auto_sell_allow_take_profit_trigger": False,
    }
    values.update(overrides)
    db_session.add(RuntimeSetting(**values))
    db_session.commit()


def _stop_loss_position(**overrides):
    payload = {
        "symbol": "005930",
        "qty": 1,
        "current_price": 96_000,
        "cost_basis": 100_000,
        "current_value": 96_000,
        "market_value": 96_000,
        "unrealized_pl": -4_000,
        "unrealized_plpc": -4.0,
    }
    payload.update(overrides)
    return payload


def _position_fixture(name):
    return {
        "take_profit": _take_profit_position,
        "manual_review": _manual_review_position,
        "missing_cost_basis": _missing_cost_basis_position,
        "missing_price": _missing_price_position,
        "raw_plpc_only": _raw_plpc_only_position,
        "oversized": _oversized_position,
        "zero_qty": _zero_qty_position,
    }[name]()


def _take_profit_position():
    return _stop_loss_position(
        current_price=103_000,
        current_value=103_000,
        market_value=103_000,
        unrealized_pl=3_000,
        unrealized_plpc=3.0,
    )


def _manual_review_position():
    return _stop_loss_position(risk_flags=["manual_review_required"])


def _missing_cost_basis_position():
    return _stop_loss_position(cost_basis=0, unrealized_pl=-4_000, unrealized_plpc=-4.0)


def _missing_price_position():
    return _stop_loss_position(current_price=0, current_value=96_000)


def _raw_plpc_only_position():
    return {
        "symbol": "005930",
        "qty": 1,
        "current_price": 96_000,
        "current_value": 96_000,
        "cost_basis": 0,
        "unrealized_plpc": -5.0,
    }


def _oversized_position():
    return _stop_loss_position(
        qty=10,
        current_price=96_000,
        cost_basis=1_000_000,
        current_value=960_000,
        market_value=960_000,
        unrealized_pl=-40_000,
    )


def _zero_qty_position():
    return _stop_loss_position(qty=0)


def _seed_shadow(db_session):
    payload = {
        "status": "ok",
        "mode": "shadow_exit_dry_run",
        "source": "kis_exit_shadow_decision",
        "source_type": "dry_run_sell_simulation",
        "decision": "would_sell",
        "result": "would_sell",
        "action": "sell",
        "candidate": {
            "symbol": "005930",
            "side": "sell",
            "suggested_quantity": 1,
            "trigger": "stop_loss",
            "trigger_source": "cost_basis_pl_pct",
            "current_price": 96_000,
            "cost_basis": 100_000,
            "current_value": 96_000,
            "unrealized_pl": -4_000,
            "unrealized_pl_pct": -0.04,
        },
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
    }
    row = TradeRunLog(
        run_key="shadow-stop-loss",
        trigger_source="shadow_exit",
        symbol="005930",
        mode="shadow_exit_dry_run",
        stage="done",
        result="would_sell",
        reason="would_sell_stop_loss",
        response_payload=json.dumps(payload),
    )
    db_session.add(row)
    db_session.commit()


def _mark_queue_reviewed(db_session):
    row = KisShadowExitReviewQueueState(
        queue_key="005930:stop_loss:cost_basis_pl_pct",
        symbol="005930",
        trigger="stop_loss",
        status="reviewed",
        operator_note="operator reviewed stop-loss alert",
    )
    db_session.add(row)
    db_session.commit()


def _seed_limited_order(db_session):
    row = OrderLog(
        broker="kis",
        market="KR",
        symbol="005930",
        side="sell",
        order_type="market",
        qty=1,
        requested_qty=1,
        internal_status=InternalOrderStatus.FILLED.value,
        broker_order_id="TODAY123",
        kis_odno="TODAY123",
        submitted_at=datetime.now(UTC).replace(tzinfo=None),
        request_payload=json.dumps({"mode": MODE}),
        response_payload=json.dumps({"mode": MODE}),
    )
    db_session.add(row)
    db_session.commit()
