import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import RuntimeSetting
from app.main import app


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
        "kis_max_manual_order_qty": 100,
        "kis_max_manual_order_amount_krw": 10_000_000,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _open_session():
    return {
        "market": "KR",
        "timezone": "Asia/Seoul",
        "is_market_open": True,
        "is_entry_allowed_now": False,
        "is_near_close": False,
        "closure_reason": None,
        "closure_name": None,
        "effective_close": "15:30",
        "no_new_entry_after": "15:00",
    }


def _position(**overrides):
    payload = {
        "symbol": "005930",
        "name": "Samsung Electronics",
        "qty": 2,
        "current_price": 72000,
        "avg_entry_price": 72000,
        "cost_basis": 144000,
        "market_value": 144000,
        "unrealized_pl": 0,
        "unrealized_plpc": 0,
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


@pytest.fixture(autouse=True)
def safe_kis_position_management(monkeypatch):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.kis_position_management_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _open_session(),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _open_session(),
    )
    monkeypatch.setattr(
        "app.services.kis_order_validation_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _open_session(),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [_position()],
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_open_orders",
        lambda self: [],
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_daily_bars",
        lambda self, symbol, limit=120: [],
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_stock_price",
        lambda self, symbol: {"current_price": 72000},
    )


def test_positions_manage_returns_hold_review_and_sell_ready(
    monkeypatch, client, db_session
):
    db_session.add(RuntimeSetting(dry_run=True))
    db_session.commit()
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(symbol="005930", name="Samsung Electronics"),
            _position(
                symbol="005380",
                name="Hyundai Motor",
                cost_basis=10000,
                market_value=9700,
                current_price=9700,
                avg_entry_price=10000,
                unrealized_pl=-300,
            ),
            _position(
                symbol="091810",
                name="Unknown Small Cap",
                qty=10,
                current_price=1000,
                avg_entry_price=0,
                cost_basis=0,
                market_value=10000,
                unrealized_pl=100,
                unrealized_plpc=999,
            ),
            _position(
                symbol="000660",
                name="SK Hynix",
                cost_basis=10000,
                market_value=10000,
                current_price=10000,
                avg_entry_price=10000,
                unrealized_pl=0,
                final_sell_score=70,
                final_buy_score=20,
            ),
        ],
    )

    response = client.get("/kis/positions/manage")

    assert response.status_code == 200
    items = {item["symbol"]: item for item in response.json()["positions"]}
    assert items["005930"]["holding_status"] == "HOLD"
    assert items["005380"]["holding_status"] == "SELL_READY"
    assert items["005380"]["stop_loss_triggered"] is True
    assert items["091810"]["holding_status"] == "REVIEW_SELL"
    assert items["091810"]["manual_review_required"] is True
    assert items["091810"]["unrealized_pl_pct"] is None
    assert items["091810"]["broker_unrealized_pl_pct"] == 999
    assert items["000660"]["holding_status"] == "SELL_READY"
    assert items["000660"]["sell_pressure_triggered"] is True
    assert "runtime_dry_run_enabled" in items["005930"]["block_reasons"]
    assert response.json()["manual_sell"]["submit_endpoint"] == "/kis/orders/manual-submit"
    assert response.json()["manual_sell"]["auto_sell_enabled"] is False


def test_prepare_manual_sell_is_read_only_and_points_to_existing_manual_path(
    monkeypatch, client, db_session
):
    db_session.add(RuntimeSetting(dry_run=False, kill_switch=False))
    db_session.commit()
    monkeypatch.setattr(
        "app.brokers.kis_broker.KisBroker.submit_market_sell",
        lambda *args, **kwargs: pytest.fail("prepare must not submit to broker"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("prepare must not call manual submit"),
    )

    response = client.post("/kis/positions/005930/prepare-manual-sell", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "005930"
    assert body["side"] == "sell"
    assert body["quantity"] == 2
    assert body["estimated_amount"] == pytest.approx(144000)
    assert body["can_prepare_manual_sell"] is True
    assert body["can_submit_manual_sell"] is True
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["manual_order"]["submit_endpoint"] == "/kis/orders/manual-submit"
    assert body["manual_order"]["requires_existing_manual_flow"] is True
    assert body["source_metadata"]["source"] == "kis_portfolio_manual_sell"
    assert body["source_metadata"]["source_type"] == "operator_confirmed_position_exit"


def test_prepare_manual_sell_blocks_when_kill_switch_on(client, db_session):
    db_session.add(RuntimeSetting(dry_run=False, kill_switch=True))
    db_session.commit()

    response = client.post("/kis/positions/005930/prepare-manual-sell", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["can_submit_manual_sell"] is False
    assert "kill_switch_enabled" in body["block_reasons"]


def test_manual_sell_submit_uses_existing_manual_submit_path_and_preserves_source(
    monkeypatch, client, db_session
):
    db_session.add(RuntimeSetting(dry_run=False, kill_switch=False))
    db_session.commit()
    monkeypatch.setattr(
        "app.brokers.kis_broker.KisBroker.submit_market_sell",
        lambda *args, **kwargs: pytest.fail("confirm_live=false must block before broker submit"),
    )

    response = client.post(
        "/kis/orders/manual-submit",
        json={
            "market": "KR",
            "symbol": "005930",
            "side": "sell",
            "qty": 1,
            "order_type": "market",
            "dry_run": False,
            "confirm_live": False,
            "source_metadata": {
                "source": "kis_portfolio_manual_sell",
                "source_type": "operator_confirmed_position_exit",
                "symbol": "005930",
                "company_name": "Samsung Electronics",
                "trigger_flags": {"manual_review_required": True},
                "position_snapshot": {"symbol": "005930", "quantity": 2},
            },
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["source"] == "kis_portfolio_manual_sell"
    assert body["source_type"] == "operator_confirmed_position_exit"
    assert body["source_metadata"]["position_snapshot"]["symbol"] == "005930"
