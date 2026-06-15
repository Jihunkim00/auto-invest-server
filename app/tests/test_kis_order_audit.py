from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

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
        "kis_access_token": "secret-access-token",
        "kis_approval_key": "secret-approval-key",
        "kis_max_manual_order_qty": 10,
        "kis_max_manual_order_amount_krw": 1000000,
        "kis_require_confirmation": True,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _runtime(**overrides):
    values = {
        "bot_enabled": True,
        "dry_run": False,
        "kill_switch": False,
        "scheduler_enabled": False,
        "default_symbol": "AAPL",
        "default_gate_level": 2,
        "max_trades_per_day": 3,
        "global_daily_entry_limit": 2,
        "per_symbol_daily_entry_limit": 1,
        "per_slot_new_entry_limit": 1,
        "max_open_positions": 3,
        "near_close_block_minutes": 15,
        "same_direction_cooldown_minutes": 120,
        "current_operation_mode": "manual_live_trading",
        "max_order_notional_pct": 0.03,
    }
    values.update(overrides)
    return values


class _Profile:
    market = "KR"
    label = "KR / KIS"
    broker_provider = "kis"
    currency = "KRW"
    timezone = "Asia/Seoul"
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
            "enabled_for_trading": True,
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
def _safe_manual_order(monkeypatch):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.RuntimeSettingService.get_settings",
        lambda self, db: _runtime(),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.RuntimeSettingService.get_kis_risk_summary_read_only",
        lambda self, db: {
            "warning_level": "safe",
            "risky_flags": ["manual_live_trading"],
            "blocking_flags": [],
            "max_notional_pct": 0.03,
        },
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.MarketProfileService.get_profile",
        lambda self, market=None: _Profile(),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.MarketSessionService.get_session_status",
        lambda self, market, now=None: {
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
        },
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("broker submit should be patched by test"),
    )


def _source_metadata(**overrides):
    payload = {
        "source": "watchlist_candidate",
        "source_type": "manual_buy_ticket_prefill",
        "source_context": "watchlist_analyze_in_trading",
        "symbol": "005930",
        "company_name": "Samsung Electronics",
        "risk_flags": ["candidate_risk"],
        "gating_notes": ["watchlist_prefill_preview_only"],
        "manual_confirm_required": True,
        "auto_buy_enabled": False,
        "scheduler_real_order_enabled": False,
        "appkey": "must-not-persist",
        "appsecret": "must-not-persist",
        "access_token": "must-not-persist",
        "approval_key": "must-not-persist",
        "authorization": "Bearer must-not-persist",
    }
    payload.update(overrides)
    return payload


def _payload(**overrides):
    payload = {
        "market": "KR",
        "symbol": "005930",
        "side": "buy",
        "qty": 1,
        "order_type": "market",
        "dry_run": False,
        "confirm_live": True,
        "confirmation": CONFIRMATION,
        "reason": "manual audit test",
        "source_metadata": _source_metadata(),
    }
    payload.update(overrides)
    return payload


def _seed_validation(db_session, *, created_at=None, source_metadata=None):
    payload = {
        "provider": "kis",
        "market": "KR",
        "symbol": "005930",
        "company_name": "Samsung Electronics",
        "side": "buy",
        "qty": 1,
        "order_type": "market",
        "current_price": 72000.0,
        "estimated_amount": 72000.0,
        "estimated_price": 72000.0,
        "estimated_notional": 72000.0,
        "available_cash": 1000000.0,
        "warnings": [],
        "block_reasons": [],
        "risk_flags": ["validation_seen_by_operator"],
        "gating_notes": ["validation_summary_present"],
        "source_metadata": source_metadata or _source_metadata(),
    }
    row = KisOrderValidationLog(
        market="KR",
        symbol="005930",
        side="buy",
        qty=1,
        order_type="market",
        validated_for_submission=True,
        current_price=72000.0,
        estimated_amount=72000.0,
        request_payload=json.dumps({"source_metadata": source_metadata or _source_metadata()}),
        response_payload=json.dumps(payload),
        created_at=created_at or datetime.now(UTC).replace(tzinfo=None),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_successful_kis_manual_submit_persists_live_order_audit(
    monkeypatch, client, db_session
):
    validation = _seed_validation(
        db_session,
        created_at=(datetime.now(UTC) - timedelta(seconds=42)).replace(tzinfo=None),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda self, **kwargs: {
            "rt_cd": "0",
            "msg_cd": "APBK0013",
            "output": {"ODNO": "0001234567", "ORD_TMD": "090501"},
        },
    )

    response = client.post("/kis/orders/manual-submit", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["order_id"]
    assert body["audit_source_context"] == "watchlist_analyze_in_trading"
    assert body["audit_user_confirmed_live_order"] is True
    assert body["audit_confirmation_dialog_shown"] is True
    assert body["audit_validation_age_seconds"] >= 40
    assert body["audit_estimated_notional"] == 72000.0
    assert body["audit_daily_live_order_remaining"] == 3
    assert body["audit_metadata"]["validation_id"] == str(validation.id)
    assert body["audit_metadata"]["validation_stale"] is False
    assert body["audit_metadata"]["broker_submit_called"] is True
    assert body["audit_metadata"]["real_order_submitted"] is True
    assert body["audit_metadata"]["manual_submit_called"] is True
    assert "validation_seen_by_operator" in body["audit_metadata"]["risk_flags"]
    assert "validation_summary_present" in body["audit_metadata"]["gating_notes"]

    order = db_session.query(OrderLog).filter(OrderLog.broker == "kis").one()
    response_payload = json.loads(order.response_payload)
    request_payload = json.loads(order.request_payload)
    assert response_payload["audit_metadata"]["source_context"] == "watchlist_analyze_in_trading"
    assert request_payload["audit_metadata"]["confirm_live"] is True

    combined = response.text + order.request_payload + order.response_payload
    for secret in [
        "must-not-persist",
        "real-app-key",
        "real-app-secret",
        "secret-access-token",
        "secret-approval-key",
        "authorization",
        "appsecret",
        "appkey",
        "approval_key",
    ]:
        assert secret not in combined

    recent = client.get("/orders/recent").json()["items"][0]
    assert recent["audit_source_context"] == "watchlist_analyze_in_trading"
    assert recent["audit_warning_level"] == "safe"
    assert recent["audit_user_confirmed_live_order"] is True
    assert recent["audit_metadata"]["available_cash"] == 1000000.0

    detail = client.get(f"/orders/{order.id}").json()
    assert detail["audit_source_context"] == "watchlist_analyze_in_trading"
    assert detail["audit_metadata"]["user_confirmed_live_order"] is True


def test_confirm_live_false_remains_blocked_and_audited(client, db_session):
    _seed_validation(db_session)

    response = client.post(
        "/kis/orders/manual-submit",
        json=_payload(confirm_live=False, confirmation=None),
    )

    assert response.status_code == 409
    body = response.json()
    assert "confirm_live_true" in body["failed_checks"]
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["audit_metadata"]["confirm_live"] is False
    assert body["audit_metadata"]["user_confirmed_live_order"] is False
    assert body["audit_metadata"]["broker_submit_called"] is False
    assert body["audit_metadata"]["submit_allowed"] is False

    order = db_session.query(OrderLog).filter(OrderLog.broker == "kis").one()
    audit = json.loads(order.response_payload)["audit_metadata"]
    assert audit["warning_level"] == "blocked"
    assert "confirm_live_true" in audit["gating_notes"]


def test_stale_validation_remains_blocked_with_audit_freshness(client, db_session):
    _seed_validation(
        db_session,
        created_at=(datetime.now(UTC) - timedelta(minutes=6)).replace(tzinfo=None),
    )

    response = client.post("/kis/orders/manual-submit", json=_payload())

    assert response.status_code == 409
    body = response.json()
    assert "validation_stale" in body["block_reasons"]
    assert body["primary_block_reason"] == "validation_stale"
    assert body["audit_metadata"]["validation_stale"] is True
    assert body["audit_metadata"]["validation_age_seconds"] >= 360
    assert body["audit_metadata"]["source_context"] == "watchlist_analyze_in_trading"
