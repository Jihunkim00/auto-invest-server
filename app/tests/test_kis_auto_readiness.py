import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting
from app.main import app
from app.services.runtime_setting_service import RuntimeSettingService


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
        "kis_scheduler_enabled": False,
        "kis_scheduler_dry_run": True,
        "kis_scheduler_allow_real_orders": False,
        "kr_scheduler_enabled": False,
        "kr_scheduler_allow_real_orders": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _open_session():
    return {
        "market": "KR",
        "timezone": "Asia/Seoul",
        "is_market_open": True,
        "is_entry_allowed_now": True,
        "is_near_close": False,
        "effective_close": "15:30",
        "no_new_entry_after": "15:00",
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


def test_runtime_settings_defaults_are_safe(db_session):
    settings = RuntimeSettingService().get_settings(db_session)

    assert settings["kis_live_auto_enabled"] is False
    assert settings["kis_live_auto_buy_enabled"] is False
    assert settings["kis_live_auto_sell_enabled"] is False
    assert settings["kis_live_auto_requires_manual_confirm"] is True
    assert settings["kis_live_auto_max_orders_per_day"] == 1
    assert settings["kis_live_auto_max_notional_pct"] == pytest.approx(0.03)


def test_ops_settings_exposes_kis_live_auto_defaults(client):
    response = client.get("/ops/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["kis_live_auto_enabled"] is False
    assert body["kis_live_auto_buy_enabled"] is False
    assert body["kis_live_auto_sell_enabled"] is False
    assert body["kis_live_auto_requires_manual_confirm"] is True
    assert body["kis_live_auto_max_orders_per_day"] == 1
    assert body["kis_live_auto_max_notional_pct"] == pytest.approx(0.03)


def test_default_readiness_is_blocked_and_no_submit(client):
    response = client.get("/kis/auto/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["auto_order_ready"] is False
    assert body["live_auto_enabled"] is False
    assert body["real_order_submit_allowed"] is False
    assert body["reason"] == "live_auto_disabled_by_default"
    assert body["checks"]["kis_scheduler_allow_real_orders"] is False
    assert body["scheduler"]["real_orders_allowed"] is False
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["broker_submit_called"] is False
    assert body["safety"]["manual_submit_called"] is False
    assert body["safety"]["scheduler_real_order_enabled"] is False
    assert body["safety"]["requires_manual_confirm"] is True
    assert body["future_paths"]["buy"]["enabled"] is False
    assert body["future_paths"]["buy"]["would_execute"] is False


def test_preflight_does_not_call_live_or_manual_submit(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_order",
        lambda *args, **kwargs: pytest.fail("readiness must not call submit_order"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("readiness must not call cash submit"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("readiness must not call manual submit"),
    )

    response = client.post("/kis/auto/preflight-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["preflight"] is True
    assert body["auto_order_ready"] is False
    assert body["real_order_submit_allowed"] is False
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["broker_submit_called"] is False
    assert body["safety"]["manual_submit_called"] is False


def test_scheduler_real_orders_remain_disabled_when_configured_true(
    monkeypatch,
    client,
):
    monkeypatch.setattr(
        "app.routes.kis.get_settings",
        lambda: _settings(kis_scheduler_allow_real_orders=True),
    )

    response = client.get("/kis/auto/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["kis_scheduler_allow_real_orders"] is True
    assert body["scheduler"]["configured_allow_real_orders"] is True
    assert body["scheduler"]["real_orders_allowed"] is False
    assert body["safety"]["scheduler_real_order_enabled"] is False
    assert body["real_order_submit_allowed"] is False


def test_sell_future_readiness_visible_but_not_executed(
    monkeypatch,
    client,
    db_session,
):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.kis_auto_readiness_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _open_session(),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        lambda self: {
            "provider": "kis",
            "market": "KR",
            "cash": 10_000_000,
            "total_asset_value": 20_000_000,
            "unrealized_pl": 0,
        },
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [{"symbol": "005930", "qty": 2, "current_price": 72000}],
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_open_orders",
        lambda self: [],
    )
    db_session.add(
        RuntimeSetting(
            dry_run=False,
            kis_live_auto_enabled=True,
            kis_live_auto_buy_enabled=False,
            kis_live_auto_sell_enabled=True,
        )
    )
    db_session.commit()

    response = client.post("/kis/auto/preflight-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["live_auto_enabled"] is True
    assert body["auto_order_ready"] is False
    assert body["future_auto_order_ready"] is True
    assert body["real_order_submit_allowed"] is False
    assert body["reason"] == "pr15_no_live_auto_submit_path"
    assert body["checks"]["live_auto_sell_enabled"] is True
    assert body["checks"]["live_auto_buy_enabled"] is False
    assert body["future_paths"]["sell"]["visible"] is True
    assert body["future_paths"]["sell"]["enabled"] is True
    assert body["future_paths"]["sell"]["would_execute"] is False
    assert body["future_paths"]["buy"]["enabled"] is False
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["broker_submit_called"] is False
    assert body["safety"]["manual_submit_called"] is False
    assert db_session.query(OrderLog).count() == 0
