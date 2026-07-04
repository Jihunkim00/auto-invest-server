from __future__ import annotations

import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, StrategyLiveAutoExitAttempt
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
        "kis_max_manual_order_qty": 10,
        "kis_max_manual_order_amount_krw": 1_000_000_000,
        "kis_scheduler_allow_real_orders": False,
        "kr_scheduler_allow_real_orders": False,
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
        "effective_close": "15:30",
        "no_new_entry_after": "15:00",
    }


def _position(**overrides):
    payload = {
        "symbol": "005930",
        "name": "Samsung",
        "qty": 2,
        "available_quantity": 2,
        "current_price": 4900,
        "avg_entry_price": 5000,
        "cost_basis": 10000,
        "market_value": 9800,
        "unrealized_pl": -200,
        "unrealized_plpc": -99,
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
def safe_context(monkeypatch, db_session):
    monkeypatch.setattr("app.routes.strategy_positions.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.position_exit_review_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _open_session(),
    )
    monkeypatch.setattr(
        "app.services.kis_order_validation_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _open_session(),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.MarketSessionService.get_session_status",
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
        "app.brokers.kis_client.KisClient.get_domestic_stock_price",
        lambda self, symbol: {"symbol": symbol, "current_price": 4900},
    )
    db_session.add(RuntimeSetting(dry_run=False, kill_switch=False, max_trades_per_day=3))
    db_session.commit()


def _guarded_sell(client, **body):
    payload = {
        "provider": "kis",
        "market": "KR",
        "symbol": "005930",
        "quantity_mode": "full",
        "confirm_live": True,
        "client_request_id": "guarded-test",
        "reason": "stop_loss_review",
    }
    payload.update(body)
    return client.post("/strategy/positions/005930/guarded-sell", json=payload)


def test_guarded_sell_without_confirm_live_is_blocked_and_does_not_submit(
    monkeypatch,
    client,
    db_session,
):
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("blocked guarded sell must not submit"),
    )

    response = _guarded_sell(client, confirm_live=False)

    assert response.status_code == 200
    body = response.json()
    assert body["result_status"] == "blocked"
    assert body["primary_block_reason"] == "confirm_live_required"
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(StrategyLiveAutoExitAttempt).count() == 1


def test_guarded_sell_with_no_position_is_blocked_and_does_not_submit(
    monkeypatch,
    client,
    db_session,
):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [],
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("no-position guarded sell must not submit"),
    )

    response = _guarded_sell(client)

    assert response.status_code == 200
    body = response.json()
    assert body["result_status"] == "blocked"
    assert body["primary_block_reason"] == "no_held_position"
    assert db_session.query(OrderLog).count() == 0


def test_guarded_sell_with_invalid_quantity_is_blocked_and_does_not_submit(
    monkeypatch,
    client,
    db_session,
):
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("invalid quantity must not submit"),
    )

    response = _guarded_sell(
        client,
        quantity_mode="partial",
        quantity=0,
        client_request_id="invalid-quantity",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result_status"] == "blocked"
    assert body["primary_block_reason"] == "requested_quantity_invalid"
    assert body["broker_submit_called"] is False
    assert db_session.query(OrderLog).count() == 0


def test_guarded_sell_with_duplicate_open_sell_order_is_blocked(
    monkeypatch,
    client,
    db_session,
):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_open_orders",
        lambda self: [{"symbol": "005930", "side": "sell", "status": "SUBMITTED"}],
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("duplicate sell must not submit"),
    )

    response = _guarded_sell(client, client_request_id="duplicate")

    assert response.status_code == 200
    body = response.json()
    assert body["result_status"] == "blocked"
    assert body["primary_block_reason"] == "duplicate_open_sell_order"
    assert db_session.query(OrderLog).count() == 0


def test_guarded_sell_with_kill_switch_true_is_blocked(
    monkeypatch,
    client,
    db_session,
):
    db_session.query(RuntimeSetting).delete()
    db_session.add(RuntimeSetting(dry_run=False, kill_switch=True, max_trades_per_day=3))
    db_session.commit()
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("kill-switch guarded sell must not submit"),
    )

    response = _guarded_sell(client, client_request_id="kill-switch")

    assert response.status_code == 200
    body = response.json()
    assert body["result_status"] == "blocked"
    assert body["primary_block_reason"] == "kill_switch_enabled"
    assert body["real_order_submitted"] is False
    assert db_session.query(OrderLog).count() == 0


def test_guarded_sell_with_dry_run_true_is_simulated_and_does_not_submit(
    monkeypatch,
    client,
    db_session,
):
    db_session.query(RuntimeSetting).delete()
    db_session.add(RuntimeSetting(dry_run=True, kill_switch=False, max_trades_per_day=3))
    db_session.commit()
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("dry-run guarded sell must not submit"),
    )

    response = _guarded_sell(client, client_request_id="dry-run")

    assert response.status_code == 200
    body = response.json()
    assert body["result_status"] == "dry_run_simulated"
    assert body["primary_block_reason"] == "dry_run_enabled"
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert db_session.query(OrderLog).count() == 0


def test_guarded_sell_live_submit_calls_existing_sell_submit_once_and_never_buy(
    monkeypatch,
    client,
    db_session,
):
    calls = {"sell": 0}

    def submit_domestic_cash_order(self, *, symbol, side, qty, order_type):
        assert symbol == "005930"
        assert side == "sell"
        assert qty == 2
        assert order_type == "market"
        calls["sell"] += 1
        return {"rt_cd": "0", "output": {"ODNO": "KIS-SELL-1"}}

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        submit_domestic_cash_order,
    )
    monkeypatch.setattr(
        "app.brokers.kis_broker.KisBroker.submit_market_buy",
        lambda *args, **kwargs: pytest.fail("guarded sell must never call buy submit"),
    )

    response = _guarded_sell(client, client_request_id="live-submit")

    assert response.status_code == 200
    body = response.json()
    assert body["result_status"] == "submitted"
    assert body["real_order_submitted"] is True
    assert body["broker_submit_called"] is True
    assert body["manual_submit_called"] is True
    assert body["submitted_quantity"] == pytest.approx(2)
    assert body["order_id"] is not None
    assert body["attempt_id"] is not None
    assert body["kis_odno"] == "KIS-SELL-1"
    assert calls["sell"] == 1

    order = db_session.get(OrderLog, body["order_id"])
    assert order is not None
    assert order.side == "sell"
    assert order.broker_order_id == "KIS-SELL-1"
    assert db_session.query(StrategyLiveAutoExitAttempt).count() == 1


def test_guarded_sell_client_request_id_replays_without_second_submit(
    monkeypatch,
    client,
):
    calls = {"sell": 0}

    def submit_domestic_cash_order(self, *, symbol, side, qty, order_type):
        calls["sell"] += 1
        return {"rt_cd": "0", "output": {"ODNO": "KIS-IDEMPOTENT"}}

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        submit_domestic_cash_order,
    )

    first = _guarded_sell(client, client_request_id="same-sell")
    second = _guarded_sell(client, client_request_id="same-sell")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["attempt_id"] == second.json()["attempt_id"]
    assert second.json()["safety"]["idempotent_replay"] is True
    assert calls["sell"] == 1


def test_guarded_sell_sync_refreshes_existing_order_only(monkeypatch, client, db_session):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda self, *, symbol, side, qty, order_type: {
            "rt_cd": "0",
            "output": {"ODNO": "KIS-SYNC-1"},
        },
    )
    submit = _guarded_sell(client, client_request_id="sync-submit").json()
    order = db_session.get(OrderLog, submit["order_id"])
    order.submitted_at = datetime(2026, 7, 3, 1, 0, 0)
    order.created_at = datetime(2026, 7, 3, 1, 0, 0)
    db_session.commit()

    sync_calls = {"sync": 0}

    def inquire(self, *, order_no, start_date, end_date):
        sync_calls["sync"] += 1
        return {
            "output1": [
                {
                    "odno": order_no,
                    "pdno": "005930",
                    "sll_buy_dvsn_cd": "01",
                    "ord_qty": "2",
                    "tot_ccld_qty": "2",
                    "rmn_qty": "0",
                    "avg_prvs": "4900",
                    "ord_dt": start_date.strftime("%Y%m%d"),
                    "ord_tmd": "100000",
                    "ord_dvsn_name": "시장가",
                }
            ]
        }

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.inquire_daily_order_executions",
        inquire,
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("sync must not submit or retry"),
    )

    response = client.post(f"/strategy/positions/sell-results/{submit['attempt_id']}/sync")

    assert response.status_code == 200
    body = response.json()
    assert body["attempt_id"] == submit["attempt_id"]
    assert body["safety"]["sync_only"] is True
    assert body["real_order_submitted"] is True
    assert sync_calls["sync"] == 1
