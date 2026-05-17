from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, SignalLog, TradeRunLog
from app.main import app
from app.services.kis_limited_auto_buy_service import (
    MODE,
    SOURCE,
    SOURCE_TYPE,
    KisLimitedAutoBuyService,
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
        self.balance = balance if balance is not None else _balance()
        self.positions = positions if positions is not None else []
        self.open_orders = open_orders if open_orders is not None else []

    def get_account_balance(self):
        return self.balance

    def list_positions(self):
        return self.positions

    def list_open_orders(self):
        return self.open_orders


class _FakeBroker:
    def __init__(self):
        self.buy_calls = []
        self.sell_calls = []

    def submit_market_buy(self, symbol, qty, **kwargs):
        self.buy_calls.append({"symbol": symbol, "qty": qty, **kwargs})
        return {"rt_cd": "0", "output": {"ODNO": "BUY123456"}}

    def submit_market_sell(self, *args, **kwargs):
        self.sell_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("limited auto buy must never sell")


class _FakeShadowService:
    def __init__(self, payload=None):
        self.payload = payload or _shadow_would_buy()
        self.calls = 0

    def run_once(self, db_session, **kwargs):
        self.calls += 1
        return self.payload


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
            "no_new_entry_after": "14:50",
        }


class _ClosedSessionService:
    def get_session_status(self, market, **kwargs):
        return {
            "market": market,
            "timezone": "Asia/Seoul",
            "is_market_open": False,
            "is_entry_allowed_now": False,
            "closure_reason": "closed",
        }


def _balance(**overrides):
    payload = {
        "provider": "kis",
        "market": "KR",
        "currency": "KRW",
        "cash": 3_000_000,
        "total_asset_value": 10_000_000,
        "unrealized_pl": 0,
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_limited_auto_buy_defaults_block_and_endpoint_is_no_submit(
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
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("manual submit must not run"),
    )

    response = client.post("/kis/limited-auto-buy/run-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == MODE
    assert body["result"] == "blocked"
    assert body["reason"] == "limited_auto_buy_disabled"
    assert body["action"] == "hold"
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["auto_buy_enabled"] is False
    assert body["scheduler_real_order_enabled"] is False
    assert db_session.query(OrderLog).count() == 0


def test_limited_auto_buy_runtime_defaults_are_safe(db_session):
    from app.services.runtime_setting_service import RuntimeSettingService

    settings = RuntimeSettingService().get_settings(db_session)

    assert settings["kis_limited_auto_buy_enabled"] is False
    assert settings["kis_limited_auto_buy_max_orders_per_day"] == 1
    assert settings["kis_limited_auto_buy_max_notional_pct"] == pytest.approx(0.03)
    assert settings["kis_limited_auto_buy_max_positions"] == 3
    assert settings["kis_limited_auto_buy_requires_shadow_review"] is True
    assert settings["kis_live_auto_buy_enabled"] is False
    assert settings["kis_scheduler_live_enabled"] is False
    assert settings["kis_scheduler_allow_real_orders"] is False


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("dry_run", True, "runtime_dry_run_true"),
        ("kill_switch", True, "kill_switch_enabled"),
        ("kis_live_auto_enabled", False, "kis_live_auto_disabled"),
        ("kis_live_auto_buy_enabled", False, "kis_live_auto_buy_disabled"),
        ("kis_limited_auto_buy_enabled", False, "limited_auto_buy_disabled"),
    ],
)
def test_limited_auto_buy_runtime_gates_block_without_submit(
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
    assert broker.buy_calls == []
    assert db_session.query(OrderLog).count() == 0


@pytest.mark.parametrize(
    ("settings_override", "reason"),
    [
        ({"kis_enabled": False}, "kis_disabled"),
        ({"kis_real_order_enabled": False}, "kis_real_order_disabled"),
    ],
)
def test_limited_auto_buy_config_gates_block_without_submit(
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
                kis_scheduler_allow_real_orders=False,
                kr_scheduler_allow_real_orders=False,
            )
        ),
        broker=broker,
    )

    result = service.run_once(db_session)

    assert result["reason"] == reason
    assert broker.buy_calls == []
    assert result["real_order_submitted"] is False


def test_limited_auto_buy_market_closed_blocks(db_session):
    _enable_runtime(db_session)
    broker = _FakeBroker()
    service = _service(broker=broker, session_service=_ClosedSessionService())

    result = service.run_once(db_session)

    assert result["reason"] == "market_closed"
    assert broker.buy_calls == []


@pytest.mark.parametrize(
    ("client_override", "shadow_override", "reason"),
    [
        ({"positions": [{"symbol": "005930", "qty": 1}]}, {}, "position_already_exists"),
        ({"open_orders": [{"symbol": "005930", "side": "buy"}]}, {}, "open_order_exists"),
        ({"balance": _balance(cash=1000)}, {}, "insufficient_cash"),
        ({"balance": _balance(total_asset_value=1_000_000)}, {}, "notional_cap_exceeded"),
        ({}, {"suggested_quantity": 0}, "quantity_not_positive"),
        ({}, {"current_price": 0}, "current_price_unavailable"),
        ({}, {"final_score": 60}, "score_threshold_not_met"),
        ({}, {"confidence": 0.3}, "confidence_threshold_not_met"),
        ({}, {"risk_flags": ["gpt_hard_block_new_buy"]}, "gpt_hard_block_new_buy"),
    ],
)
def test_limited_auto_buy_candidate_gates_block_without_submit(
    db_session,
    client_override,
    shadow_override,
    reason,
):
    _enable_runtime(db_session, kis_limited_auto_buy_requires_shadow_review=False)
    broker = _FakeBroker()
    client = _FakeClient(**client_override)
    shadow = _FakeShadowService(_shadow_would_buy(**shadow_override))

    result = _service(client=client, broker=broker, shadow_service=shadow).run_once(
        db_session
    )

    assert result["reason"] == reason
    assert result["real_order_submitted"] is False
    assert broker.buy_calls == []


def test_limited_auto_buy_shadow_review_required_blocks_by_default(db_session):
    _enable_runtime(db_session)
    broker = _FakeBroker()

    result = _service(broker=broker).run_once(db_session)

    assert result["reason"] == "shadow_review_required"
    assert broker.buy_calls == []


def test_limited_auto_buy_daily_limit_and_reentry_block(db_session):
    _enable_runtime(db_session, kis_limited_auto_buy_requires_shadow_review=False)
    _seed_limited_buy_order(db_session)
    broker = _FakeBroker()

    result = _service(broker=broker).run_once(db_session)

    assert result["reason"] == "daily_buy_limit_reached"
    assert broker.buy_calls == []


def test_limited_auto_buy_submits_exactly_one_buy_and_logs_audit(db_session):
    _enable_runtime(db_session, kis_limited_auto_buy_requires_shadow_review=False)
    broker = _FakeBroker()

    result = _service(broker=broker).run_once(db_session)

    assert result["result"] == "submitted"
    assert result["action"] == "buy"
    assert result["symbol"] == "005930"
    assert result["quantity"] == 4
    assert result["notional"] == 288000
    assert result["real_order_submitted"] is True
    assert result["broker_submit_called"] is True
    assert result["manual_submit_called"] is False
    assert broker.buy_calls == [{"symbol": "005930", "qty": 4}]
    assert broker.sell_calls == []
    order = db_session.query(OrderLog).one()
    assert order.broker == "kis"
    assert order.market == "KR"
    assert order.side == "buy"
    assert order.internal_status == InternalOrderStatus.SUBMITTED.value
    assert order.kis_odno == "BUY123456"
    assert json.loads(order.request_payload)["mode"] == MODE
    response_payload = json.loads(order.response_payload)
    assert response_payload["source"] == SOURCE
    assert response_payload["source_type"] == SOURCE_TYPE
    assert response_payload["audit_metadata"]["source"] == SOURCE
    assert response_payload["audit_metadata"]["limited_auto_buy_manual_submit_called"] is False
    assert db_session.query(SignalLog).count() == 1
    assert db_session.query(TradeRunLog).filter(TradeRunLog.mode == MODE).count() == 1


def test_limited_auto_buy_history_serializes_distinct_mode(db_session, client):
    _enable_runtime(db_session, kis_limited_auto_buy_requires_shadow_review=False)
    _service(broker=_FakeBroker()).run_once(db_session)

    response = client.get("/orders/recent")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["mode"] == MODE
    assert item["source"] == SOURCE
    assert item["source_type"] == SOURCE_TYPE
    assert item["side"] == "buy"
    assert item["manual_submit_called"] is False
    assert item["real_order_submitted"] is True


def _service(
    *,
    client=None,
    broker=None,
    shadow_service=None,
    session_service=None,
):
    return KisLimitedAutoBuyService(
        client or _FakeClient(),
        broker=broker or _FakeBroker(),
        shadow_service=shadow_service or _FakeShadowService(),
        session_service=session_service or _OpenSessionService(),
    )


def _enable_runtime(db_session, **overrides):
    db_session.query(RuntimeSetting).delete()
    values = {
        "dry_run": False,
        "kill_switch": False,
        "kis_live_auto_enabled": True,
        "kis_live_auto_buy_enabled": True,
        "kis_live_auto_sell_enabled": False,
        "kis_limited_auto_buy_enabled": True,
        "kis_limited_auto_buy_shadow_enabled": True,
        "kis_limited_auto_buy_requires_shadow_review": True,
        "kis_limited_auto_buy_max_orders_per_day": 1,
        "kis_limited_auto_buy_max_notional_pct": 0.03,
        "kis_limited_auto_buy_min_final_score": 75,
        "kis_limited_auto_buy_min_confidence": 0.70,
        "kis_limited_auto_buy_max_positions": 3,
        "kis_limited_auto_buy_block_if_position_exists": True,
        "kis_limited_auto_buy_block_if_open_order_exists": True,
        "kis_limited_auto_buy_allow_reentry_same_day": False,
        "kis_limited_auto_buy_require_market_open": True,
        "kis_limited_auto_buy_no_new_entry_after": "14:50",
        "kis_limited_auto_buy_allow_gpt_hard_block": False,
    }
    values.update(overrides)
    db_session.add(RuntimeSetting(**values))
    db_session.commit()


def _shadow_would_buy(**overrides):
    candidate = {
        "symbol": "005930",
        "market": "KR",
        "provider": "kis",
        "final_score": 82.5,
        "confidence": 0.76,
        "quant_score": 78.0,
        "gpt_buy_score": 65.0,
        "current_price": 72_000,
        "suggested_notional": 288_000,
        "suggested_quantity": 4,
        "reason": "Shadow buy candidate only. No broker submit.",
        "risk_flags": [],
        "gating_notes": ["shadow_buy_only"],
        "audit_metadata": {
            "source": "kis_buy_shadow_decision",
            "source_type": "dry_run_buy_simulation",
        },
    }
    candidate.update(overrides)
    return {
        "status": "ok",
        "mode": "shadow_buy_dry_run",
        "decision": "would_buy",
        "result": "would_buy",
        "action": "buy",
        "reason": "Shadow buy candidate only. No broker submit.",
        "symbol": candidate.get("symbol"),
        "candidate": candidate,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "run": {"run_key": "shadow-buy-run"},
    }


def _seed_limited_buy_order(db_session):
    row = OrderLog(
        broker="kis",
        market="KR",
        symbol="005930",
        side="buy",
        order_type="market",
        qty=1,
        requested_qty=1,
        internal_status=InternalOrderStatus.FILLED.value,
        broker_order_id="BUY-TODAY",
        kis_odno="BUY-TODAY",
        submitted_at=datetime.now(UTC).replace(tzinfo=None),
        request_payload=json.dumps({"mode": MODE, "source": SOURCE}),
        response_payload=json.dumps({"mode": MODE, "source": SOURCE}),
    )
    db_session.add(row)
    db_session.commit()
