from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import KisOrderValidationLog, OrderLog
from app.main import app

CONFIRMATION = "I UNDERSTAND THIS WILL PLACE A REAL KIS ORDER"


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "kis_enabled": True,
        "kis_real_order_enabled": True,
        "kis_env": "prod",
        "kis_app_key": "real-app-key",
        "kis_app_secret": "real-app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_base_url": "https://openapi.koreainvestment.com:9443",
        "kis_max_manual_order_qty": 5,
        "kis_max_manual_order_amount_krw": 1_000_000,
        "kis_require_confirmation": True,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _runtime(**overrides):
    values = {
        "dry_run": False,
        "kill_switch": False,
        "max_trades_per_day": 3,
    }
    values.update(overrides)
    return values


class _Profile:
    market = "KR"
    label = "KR / KIS"
    broker_provider = "kis"
    currency = "KRW"
    timezone = "Asia/Seoul"
    watchlist_file = "config/watchlist_kr.yaml"
    reference_sites_file = "config/reference_sites_kr.yaml"
    symbol_format = "6_digit_numeric"
    enabled_for_trading = True

    def to_dict(self):
        return {
            "market": self.market,
            "label": self.label,
            "broker_provider": self.broker_provider,
            "currency": self.currency,
            "timezone": self.timezone,
            "symbol_format": self.symbol_format,
            "enabled_for_trading": self.enabled_for_trading,
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


@pytest.fixture(autouse=True)
def safe_kis_manual_exit(monkeypatch):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.RuntimeSettingService.get_settings",
        lambda self, db: _runtime(),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.MarketProfileService.get_profile",
        lambda self, market=None: _Profile(),
    )
    monkeypatch.setattr(
        "app.services.kis_order_validation_service.MarketSessionService.get_session_status",
        lambda self, market, now=None: _open_session(),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.MarketSessionService.get_session_status",
        lambda self, market, now=None: _open_session(),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_stock_price",
        lambda self, symbol: {"symbol": symbol, "current_price": 72000.0},
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        lambda self: {"currency": "KRW", "cash": 1_000_000.0},
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [{"symbol": "005930", "qty": 3.0}],
    )

    def fail_submit(*args, **kwargs):
        pytest.fail("manual exit audit tests must explicitly enable broker submit")

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        fail_submit,
    )


def _open_session():
    return {
        "market": "KR",
        "timezone": "Asia/Seoul",
        "is_market_open": True,
        "is_entry_allowed_now": True,
        "is_near_close": False,
        "is_holiday": False,
        "closure_reason": None,
        "closure_name": None,
        "regular_open": "09:00",
        "regular_close": "15:30",
        "effective_close": "15:30",
        "no_new_entry_after": "15:00",
    }


def _source_metadata(**overrides):
    payload = {
        "source": "kis_live_exit_preflight",
        "source_type": "manual_confirm_exit",
        "preflight_run_key": "kis_live_exit_preflight_abcd1234",
        "preflight_checked_at": "2026-05-14T01:00:00+00:00",
        "exit_trigger": "stop_loss",
        "trigger_source": "cost_basis_pl_pct",
        "unrealized_pl": -2880,
        "unrealized_pl_pct": -0.02,
        "cost_basis": 144000,
        "current_value": 141120,
        "current_price": 70560,
        "suggested_quantity": 2,
        "risk_flags": ["stop_loss_triggered"],
        "gating_notes": ["manual_confirm_required", "no_auto_submit"],
        "manual_confirm_required": True,
        "auto_sell_enabled": False,
        "scheduler_real_order_enabled": False,
        "real_order_submit_allowed": False,
        "preflight_real_order_submitted": False,
        "preflight_broker_submit_called": False,
        "preflight_manual_submit_called": False,
        "appsecret": "must-not-persist",
        "access_token": "must-not-persist",
    }
    payload.update(overrides)
    return payload


def _validation_payload(**overrides):
    payload = {
        "market": "KR",
        "symbol": "005930",
        "side": "sell",
        "qty": 2,
        "order_type": "market",
        "dry_run": True,
        "reason": "manual exit validation",
        "source_metadata": _source_metadata(),
    }
    payload.update(overrides)
    return payload


def _submit_payload(**overrides):
    payload = {
        "market": "KR",
        "symbol": "005930",
        "side": "sell",
        "qty": 2,
        "order_type": "market",
        "dry_run": False,
        "confirm_live": True,
        "confirmation": CONFIRMATION,
        "reason": "manual exit submit",
        "source_metadata": _source_metadata(),
    }
    payload.update(overrides)
    return payload


def test_manual_sell_validation_preserves_exit_preflight_source_metadata(
    client, db_session
):
    response = client.post("/kis/orders/validate", json=_validation_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["validated_for_submission"] is True
    assert body["source"] == "kis_live_exit_preflight"
    assert body["source_type"] == "manual_confirm_exit"
    assert body["exit_trigger"] == "stop_loss"
    assert body["exit_trigger_source"] == "cost_basis_pl_pct"
    assert body["manual_confirm_required"] is True
    assert body["auto_sell_enabled"] is False
    assert body["scheduler_real_order_enabled"] is False
    assert body["real_order_submit_allowed"] is False
    assert body["source_metadata"]["suggested_quantity"] == 2.0
    assert "appsecret" not in response.text
    assert "access_token" not in response.text

    row = db_session.query(KisOrderValidationLog).one()
    assert "kis_live_exit_preflight" in row.request_payload
    assert "kis_live_exit_preflight" in row.response_payload
    assert "must-not-persist" not in row.request_payload
    assert "must-not-persist" not in row.response_payload


def test_manual_submit_persists_exit_preflight_source_metadata(
    monkeypatch, client, db_session
):
    client.post("/kis/orders/validate", json=_validation_payload())

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda self, **kwargs: {
            "rt_cd": "0",
            "msg_cd": "APBK0013",
            "output": {"ODNO": "0001234567", "ORD_TMD": "090501"},
        },
    )

    response = client.post("/kis/orders/manual-submit", json=_submit_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["real_order_submitted"] is True
    assert body["broker_submit_called"] is True
    assert body["manual_submit_called"] is True
    assert body["mode"] == "manual_live"
    assert body["source"] == "kis_live_exit_preflight"
    assert body["source_type"] == "manual_confirm_exit"
    assert body["exit_trigger"] == "stop_loss"
    assert body["exit_trigger_source"] == "cost_basis_pl_pct"
    assert body["kis_odno"] == "0001234567"

    order = db_session.query(OrderLog).filter(OrderLog.broker == "kis").one()
    request_payload = json.loads(order.request_payload)
    response_payload = json.loads(order.response_payload)
    assert request_payload["mode"] == "manual_live"
    assert request_payload["source"] == "kis_live_exit_preflight"
    assert response_payload["source"] == "kis_live_exit_preflight"
    assert response_payload["real_order_submitted"] is True
    assert response_payload["broker_submit_called"] is True
    assert response_payload["manual_submit_called"] is True
    assert "must-not-persist" not in order.request_payload
    assert "must-not-persist" not in order.response_payload

    recent = client.get("/kis/orders").json()["orders"][0]
    assert recent["source"] == "kis_live_exit_preflight"
    assert recent["source_type"] == "manual_confirm_exit"
    assert recent["exit_trigger"] == "stop_loss"
    assert recent["real_order_submit_allowed"] is False

    history = client.get("/orders/recent").json()["items"][0]
    assert history["mode"] == "manual_live"
    assert history["source"] == "kis_live_exit_preflight"
    assert history["source_type"] == "manual_confirm_exit"
    assert history["exit_trigger"] == "stop_loss"
    assert history["real_order_submitted"] is True
    assert history["broker_submit_called"] is True
    assert history["manual_submit_called"] is True


def test_source_metadata_cannot_bypass_confirm_live(client, db_session):
    client.post("/kis/orders/validate", json=_validation_payload())

    response = client.post(
        "/kis/orders/manual-submit",
        json=_submit_payload(confirm_live=False),
    )

    assert response.status_code == 409
    body = response.json()
    assert "confirm_live_true" in body["failed_checks"]
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["source"] == "kis_live_exit_preflight"


def test_source_metadata_cannot_bypass_kill_switch(monkeypatch, client, db_session):
    client.post("/kis/orders/validate", json=_validation_payload())
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.RuntimeSettingService.get_settings",
        lambda self, db: _runtime(kill_switch=True),
    )

    response = client.post("/kis/orders/manual-submit", json=_submit_payload())

    assert response.status_code == 409
    body = response.json()
    assert "kill_switch_false" in body["failed_checks"]
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["source"] == "kis_live_exit_preflight"
