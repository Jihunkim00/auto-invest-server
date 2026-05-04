from datetime import UTC, datetime

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
        "kis_max_manual_order_qty": 1,
        "kis_max_manual_order_amount_krw": 100000,
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
            "watchlist_file": self.watchlist_file,
            "reference_sites_file": self.reference_sites_file,
            "symbol_format": self.symbol_format,
            "enabled_for_trading": self.enabled_for_trading,
        }


class _DisabledProfile(_Profile):
    enabled_for_trading = False


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
        lambda self: {"currency": "KRW", "cash": 1000000.0},
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [{"symbol": "005930", "qty": 3.0}],
    )

    def fail_submit(*args, **kwargs):
        pytest.fail("KIS submit must stay blocked unless the success test enables it")

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


def _closed_session():
    payload = _open_session()
    payload.update(
        {
            "is_market_open": False,
            "is_entry_allowed_now": False,
            "closure_reason": "outside_regular_hours",
        }
    )
    return payload


def _holiday_session():
    payload = _closed_session()
    payload.update(
        {
            "is_holiday": True,
            "closure_reason": "holiday_labor_day",
            "closure_name": "Labor Day",
        }
    )
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
        "reason": "manual small real-order test",
    }
    payload.update(overrides)
    return payload


def _seed_validation(db_session, *, symbol="005930", side="buy", qty=1, amount=72000):
    row = KisOrderValidationLog(
        market="KR",
        symbol=symbol,
        side=side,
        qty=qty,
        order_type="market",
        validated_for_submission=True,
        current_price=72000.0,
        estimated_amount=amount,
        request_payload="{}",
        response_payload="{}",
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _assert_rejected(response, check_name):
    assert response.status_code in (400, 409)
    body = response.json()
    assert body["real_order_submitted"] is False
    assert body["internal_status"] == "REJECTED_BY_SAFETY_GATE"
    assert check_name in body["failed_checks"]
    assert body["safety_checks"][check_name]["passed"] is False
    return body


def test_submit_manual_rejects_when_kis_enabled_false(monkeypatch, client, db_session):
    _seed_validation(db_session)
    monkeypatch.setattr(
        "app.routes.kis.get_settings",
        lambda: _settings(kis_enabled=False),
    )

    response = client.post("/kis/orders/submit-manual", json=_payload())

    _assert_rejected(response, "kis_enabled")


def test_submit_manual_rejects_when_dry_run_true(client, db_session):
    _seed_validation(db_session)

    response = client.post(
        "/kis/orders/submit-manual",
        json=_payload(dry_run=True),
    )

    _assert_rejected(response, "dry_run_false")


def test_submit_manual_rejects_when_runtime_dry_run_enabled(
    monkeypatch, client, db_session
):
    _seed_validation(db_session)
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.RuntimeSettingService.get_settings",
        lambda self, db: _runtime(dry_run=True),
    )

    response = client.post("/kis/orders/submit-manual", json=_payload())

    _assert_rejected(response, "dry_run_false")


def test_submit_manual_rejects_when_kill_switch_true(monkeypatch, client, db_session):
    _seed_validation(db_session)
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.RuntimeSettingService.get_settings",
        lambda self, db: _runtime(kill_switch=True),
    )

    response = client.post("/kis/orders/submit-manual", json=_payload())

    _assert_rejected(response, "kill_switch_false")


def test_submit_manual_rejects_when_kr_profile_disabled(
    monkeypatch, client, db_session
):
    _seed_validation(db_session)
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.MarketProfileService.get_profile",
        lambda self, market=None: _DisabledProfile(),
    )

    response = client.post("/kis/orders/submit-manual", json=_payload())

    _assert_rejected(response, "kr_trading_profile_enabled")


def test_submit_manual_rejects_when_market_closed(monkeypatch, client, db_session):
    _seed_validation(db_session)
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.MarketSessionService.get_session_status",
        lambda self, market, now=None: _closed_session(),
    )

    response = client.post("/kis/orders/submit-manual", json=_payload())

    _assert_rejected(response, "kr_market_open")


def test_submit_manual_rejects_when_holiday(monkeypatch, client, db_session):
    _seed_validation(db_session)
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.MarketSessionService.get_session_status",
        lambda self, market, now=None: _holiday_session(),
    )

    response = client.post("/kis/orders/submit-manual", json=_payload())

    body = _assert_rejected(response, "today_not_holiday")
    assert "holiday_labor_day" in response.text


def test_submit_manual_rejects_when_no_recent_dry_run_validation(client):
    response = client.post("/kis/orders/submit-manual", json=_payload())

    _assert_rejected(response, "recent_dry_run_validation_passed")


def test_submit_manual_rejects_when_qty_exceeds_cap(
    monkeypatch, client, db_session
):
    _seed_validation(db_session, qty=2, amount=144000)
    monkeypatch.setattr(
        "app.routes.kis.get_settings",
        lambda: _settings(kis_max_manual_order_amount_krw=1000000),
    )

    response = client.post(
        "/kis/orders/submit-manual",
        json=_payload(qty=2),
    )

    _assert_rejected(response, "max_order_qty_cap")


def test_submit_manual_allows_disabled_qty_cap(monkeypatch, client, db_session):
    _seed_validation(db_session, qty=5, amount=360000)
    monkeypatch.setattr(
        "app.routes.kis.get_settings",
        lambda: _settings(kis_max_manual_order_qty=0, kis_max_manual_order_amount_krw=1000000),
    )

    def fake_submit(self, *, symbol, side, qty, order_type="market"):
        return {
            "rt_cd": "0",
            "msg_cd": "APBK0013",
            "output": {"ODNO": "0001234567", "ORD_TMD": "090501"},
        }

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        fake_submit,
    )

    response = client.post(
        "/kis/orders/submit-manual",
        json=_payload(qty=5),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["real_order_submitted"] is True
    assert body["safety_checks"]["max_order_qty_cap"]["passed"] is True
    assert body["safety_checks"]["max_order_qty_cap"]["detail"]["cap_disabled"] is True
    assert body["safety_checks"]["max_order_qty_cap"]["detail"]["qty"] == 5


def test_submit_manual_rejects_when_amount_exceeds_cap(
    monkeypatch, client, db_session
):
    _seed_validation(db_session, amount=72000)
    monkeypatch.setattr(
        "app.routes.kis.get_settings",
        lambda: _settings(kis_max_manual_order_amount_krw=50000),
    )

    response = client.post("/kis/orders/submit-manual", json=_payload())

    _assert_rejected(response, "max_order_amount_cap")


def test_submit_manual_allows_disabled_amount_cap(monkeypatch, client, db_session):
    _seed_validation(db_session, amount=72000)
    monkeypatch.setattr(
        "app.routes.kis.get_settings",
        lambda: _settings(kis_max_manual_order_amount_krw=0),
    )

    def fake_submit(self, *, symbol, side, qty, order_type="market"):
        return {
            "rt_cd": "0",
            "msg_cd": "APBK0013",
            "output": {"ODNO": "0001234567", "ORD_TMD": "090501"},
        }

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        fake_submit,
    )

    response = client.post("/kis/orders/submit-manual", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["real_order_submitted"] is True
    assert body["safety_checks"]["max_order_amount_cap"]["passed"] is True
    assert body["safety_checks"]["max_order_amount_cap"]["detail"]["cap_disabled"] is True
    assert body["safety_checks"]["max_order_amount_cap"]["detail"]["estimated_amount"] == 72000.0


def test_submit_manual_rejects_when_confirmation_missing_with_caps_disabled(
    monkeypatch, client, db_session
):
    _seed_validation(db_session, amount=72000)
    monkeypatch.setattr(
        "app.routes.kis.get_settings",
        lambda: _settings(kis_max_manual_order_qty=0, kis_max_manual_order_amount_krw=0),
    )

    response = client.post(
        "/kis/orders/submit-manual",
        json=_payload(confirmation=None),
    )

    _assert_rejected(response, "manual_confirmation_matches")
    assert response.json()["safety_checks"]["max_order_qty_cap"]["passed"] is True
    assert response.json()["safety_checks"]["max_order_amount_cap"]["passed"] is True


def test_submit_manual_rejects_when_confirm_live_false(client, db_session):
    _seed_validation(db_session)

    response = client.post(
        "/kis/orders/submit-manual",
        json=_payload(confirm_live=False),
    )

    _assert_rejected(response, "confirm_live_true")


def test_submit_manual_rejects_when_confirmation_missing(client, db_session):
    _seed_validation(db_session)

    response = client.post(
        "/kis/orders/submit-manual",
        json=_payload(confirmation=None),
    )

    _assert_rejected(response, "manual_confirmation_matches")


def test_submit_manual_rejects_when_confirmation_requirement_disabled(
    monkeypatch, client, db_session
):
    _seed_validation(db_session)
    monkeypatch.setattr(
        "app.routes.kis.get_settings",
        lambda: _settings(kis_require_confirmation=False),
    )

    response = client.post("/kis/orders/submit-manual", json=_payload())

    body = _assert_rejected(response, "manual_confirmation_matches")
    assert "manual_confirmation_requirement_disabled" in body["block_reasons"]


def test_submit_manual_rejects_when_daily_trade_limit_reached(
    monkeypatch, client, db_session
):
    _seed_validation(db_session)
    db_session.add(
        OrderLog(
            broker="kis",
            symbol="005930",
            side="buy",
            order_type="market",
            qty=1,
            internal_status="SUBMITTED",
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.RuntimeSettingService.get_settings",
        lambda self, db: _runtime(max_trades_per_day=1),
    )

    response = client.post("/kis/orders/submit-manual", json=_payload())

    _assert_rejected(response, "daily_trade_limit")


@pytest.mark.parametrize(
    "status",
    ["SUBMITTED", "ACCEPTED", "PENDING", "PARTIALLY_FILLED", "FILLED"],
)
def test_submit_manual_daily_trade_limit_counts_submitted_kis_statuses(
    monkeypatch,
    client,
    db_session,
    status,
):
    _seed_validation(db_session)
    db_session.add(
        OrderLog(
            broker="kis",
            symbol="005930",
            side="buy",
            order_type="market",
            qty=1,
            internal_status=status,
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.RuntimeSettingService.get_settings",
        lambda self, db: _runtime(max_trades_per_day=1),
    )

    response = client.post("/kis/orders/submit-manual", json=_payload())

    _assert_rejected(response, "daily_trade_limit")


def test_submit_manual_daily_trade_limit_ignores_alpaca_orders(
    monkeypatch,
    client,
    db_session,
):
    _seed_validation(db_session)
    db_session.add(
        OrderLog(
            broker="alpaca",
            symbol="005930",
            side="buy",
            order_type="market",
            qty=1,
            internal_status="SUBMITTED",
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.RuntimeSettingService.get_settings",
        lambda self, db: _runtime(max_trades_per_day=1),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda self, **kwargs: {
            "rt_cd": "0",
            "output": {"ODNO": "0001234567", "ORD_TMD": "090501"},
        },
    )

    response = client.post("/kis/orders/submit-manual", json=_payload())

    assert response.status_code == 200
    assert response.json()["real_order_submitted"] is True


def test_submit_manual_daily_trade_limit_ignores_rejected_safety_gate_logs(
    monkeypatch,
    client,
    db_session,
):
    _seed_validation(db_session)
    db_session.add(
        OrderLog(
            broker="kis",
            symbol="005930",
            side="buy",
            order_type="market",
            qty=1,
            internal_status="REJECTED_BY_SAFETY_GATE",
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.RuntimeSettingService.get_settings",
        lambda self, db: _runtime(max_trades_per_day=1),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda self, **kwargs: {
            "rt_cd": "0",
            "output": {"ODNO": "0001234567", "ORD_TMD": "090501"},
        },
    )

    response = client.post("/kis/orders/submit-manual", json=_payload())

    assert response.status_code == 200
    assert response.json()["real_order_submitted"] is True


def test_submit_manual_success_stores_order_log(monkeypatch, client, db_session):
    _seed_validation(db_session)
    calls = []

    def fake_submit(self, *, symbol, side, qty, order_type="market"):
        calls.append(
            {
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "order_type": order_type,
            }
        )
        return {
            "rt_cd": "0",
            "msg_cd": "APBK0013",
            "output": {"ODNO": "0001234567", "ORD_TMD": "090501"},
        }

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        fake_submit,
    )

    response = client.post("/kis/orders/submit-manual", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["real_order_submitted"] is True
    assert body["broker_order_id"] == "0001234567"
    assert body["order_id"] == body["order_log_id"]
    assert body["kis_odno"] == "0001234567"
    assert body["broker_order_status"] == "submitted"
    assert body["requested_qty"] == 1
    assert body["filled_qty"] == 0
    assert body["remaining_qty"] == 1
    assert body["avg_fill_price"] is None
    assert body["broker_status"] == "submitted"
    assert body["internal_status"] == "SUBMITTED"
    assert calls == [
        {
            "symbol": "005930",
            "side": "buy",
            "qty": 1,
            "order_type": "market",
        }
    ]

    order = db_session.query(OrderLog).filter(OrderLog.broker == "kis").one()
    assert order.symbol == "005930"
    assert order.side == "buy"
    assert order.qty == 1.0
    assert order.notional == 72000
    assert order.internal_status == "SUBMITTED"
    assert order.broker_order_id == "0001234567"
    assert order.kis_odno == "0001234567"
    assert order.market == "KR"
    assert order.requested_qty == 1.0
    assert order.filled_qty == 0.0
    assert order.remaining_qty == 1.0
    assert order.broker_order_status == "submitted"
    assert order.broker_status == "submitted"
    assert order.request_payload
    assert order.response_payload


def test_submit_manual_response_and_logs_do_not_expose_secrets(
    monkeypatch, client, db_session
):
    _seed_validation(db_session)
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda self, **kwargs: {
            "rt_cd": "0",
            "output": {
                "ODNO": "0001234567",
                "CANO": "12345678",
                "access_token": "secret-access-token",
            },
        },
    )

    response = client.post("/kis/orders/submit-manual", json=_payload())

    assert response.status_code == 200
    order = db_session.query(OrderLog).filter(OrderLog.broker == "kis").one()
    combined = response.text + (order.request_payload or "") + (order.response_payload or "")
    assert "12345678" not in combined
    assert "real-app-secret" not in combined
    assert "secret-access-token" not in combined
    assert "secret-approval-key" not in combined
