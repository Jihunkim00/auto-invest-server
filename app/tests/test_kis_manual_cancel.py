from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting
from app.main import app


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
        "kis_access_token": "secret-access-token",
        "kis_approval_key": "secret-approval-key",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@contextmanager
def _client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _seed_order(
    db_session,
    *,
    broker="kis",
    status=InternalOrderStatus.SUBMITTED.value,
    odno="0001234567",
):
    row = OrderLog(
        broker=broker,
        market="KR" if broker == "kis" else "US",
        symbol="005930" if broker == "kis" else "AAPL",
        side="buy",
        order_type="market",
        time_in_force="day",
        qty=3,
        requested_qty=3,
        remaining_qty=3,
        broker_order_id=odno,
        kis_odno=odno if broker == "kis" else None,
        internal_status=status,
        broker_status="submitted",
        broker_order_status="submitted",
        submitted_at=datetime.now(UTC),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_kis_cancel_rejects_non_kis_order(monkeypatch, db_session):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    order = _seed_order(db_session, broker="alpaca", odno="alpaca-1")
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.cancel_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("non-KIS order must not call KIS cancel"),
    )

    with _client(db_session) as client:
        response = client.post(f"/kis/orders/{order.id}/cancel")

    assert response.status_code == 400
    body = response.json()
    assert body["canceled"] is False
    assert body["message"] == "Only KIS orders can be canceled."


def test_kis_cancel_rejects_missing_odno(monkeypatch, db_session):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    order = _seed_order(db_session, odno=None)
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.cancel_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("missing ODNO must not call KIS cancel"),
    )

    with _client(db_session) as client:
        response = client.post(f"/kis/orders/{order.id}/cancel")

    assert response.status_code == 409
    body = response.json()
    assert body["canceled"] is False
    assert body["message"] == "KIS ODNO is required to cancel."
    assert body["kis_odno"] is None


def test_kis_cancel_rejects_terminal_order(monkeypatch, db_session):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    order = _seed_order(db_session, status=InternalOrderStatus.FILLED.value)
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.cancel_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("terminal order must not call KIS cancel"),
    )

    with _client(db_session) as client:
        response = client.post(f"/kis/orders/{order.id}/cancel")

    assert response.status_code == 409
    body = response.json()
    assert body["canceled"] is False
    assert body["internal_status"] == "FILLED"
    assert body["message"] == "Terminal orders cannot be canceled."


def test_kis_cancel_rejects_non_syncable_order(monkeypatch, db_session):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    order = _seed_order(db_session, status=InternalOrderStatus.REQUESTED.value)
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.cancel_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("non-syncable order must not call KIS cancel"),
    )

    with _client(db_session) as client:
        response = client.post(f"/kis/orders/{order.id}/cancel")

    assert response.status_code == 409
    body = response.json()
    assert body["canceled"] is False
    assert body["internal_status"] == "REQUESTED"
    assert body["message"] == "Only open syncable KIS orders can be canceled."


def test_kis_cancel_respects_kill_switch(monkeypatch, db_session):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    order = _seed_order(db_session)
    db_session.add(RuntimeSetting(kill_switch=True))
    db_session.commit()
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.cancel_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("kill switch must block KIS cancel"),
    )

    with _client(db_session) as client:
        response = client.post(f"/kis/orders/{order.id}/cancel")

    assert response.status_code == 409
    body = response.json()
    assert body["canceled"] is False
    assert body["internal_status"] == "SUBMITTED"
    assert body["message"] == "Kill switch is ON."


def test_kis_cancel_success_updates_internal_status_and_sanitizes_payload(
    monkeypatch,
    db_session,
):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    order = _seed_order(db_session)

    def fake_cancel(self, *, order_no, qty=None):
        assert order_no == "0001234567"
        assert qty == 3
        return {
            "rt_cd": "0",
            "msg_cd": "0",
            "msg1": "cancel accepted for account 12345678",
            "output": {
                "ODNO": "0001234567",
                "ORGN_ODNO": "0001234567",
                "CANO": "12345678",
                "ACNT_PRDT_CD": "01",
                "appkey": "real-app-key",
                "appsecret": "real-app-secret",
                "authorization": "Bearer secret-access-token",
                "ctac_tlno": "010-1234-5678",
            },
        }

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.cancel_domestic_cash_order",
        fake_cancel,
    )

    with _client(db_session) as client:
        response = client.post(f"/kis/orders/{order.id}/cancel")

    assert response.status_code == 200
    body = response.json()
    assert body["canceled"] is True
    assert body["order_id"] == order.id
    assert body["kis_odno"] == "0001234567"
    assert body["internal_status"] == "CANCELED"
    assert body["broker_status"] == "CANCELED"
    assert body["message"] == "KIS order canceled."

    synced = db_session.get(OrderLog, order.id)
    assert synced.internal_status == "CANCELED"
    assert synced.broker_status == "CANCELED"
    assert synced.canceled_at is not None

    combined = response.text + synced.last_sync_payload
    assert "12345678" not in combined
    assert "real-app-key" not in combined
    assert "real-app-secret" not in combined
    assert "secret-access-token" not in combined
    assert "secret-approval-key" not in combined
    assert "010-1234-5678" not in combined

    payload = json.loads(synced.last_sync_payload)
    assert payload["event"] == "kis_order_cancel_success"
    assert payload["payload"]["request"]["CANO"] == "12****78"
    assert payload["payload"]["request"]["ACNT_PRDT_CD"] == "***REDACTED***"
    assert payload["payload"]["response"]["output"]["CANO"] == "12****78"
