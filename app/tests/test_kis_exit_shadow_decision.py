import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, SignalLog, TradeRunLog
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
        "closure_reason": None,
        "closure_name": None,
        "effective_close": "15:30",
        "no_new_entry_after": "15:00",
    }


def _balance(**overrides):
    payload = {
        "provider": "kis",
        "market": "KR",
        "currency": "KRW",
        "cash": 10_000_000,
        "total_asset_value": 20_000_000,
        "unrealized_pl": 0,
    }
    payload.update(overrides)
    return payload


def _position(**overrides):
    payload = {
        "symbol": "005930",
        "name": "Samsung",
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
def safe_shadow(monkeypatch, db_session):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.kis_exit_shadow_decision_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _open_session(),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        lambda self: _balance(),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [_position()],
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_open_orders",
        lambda self: [],
    )
    db_session.add(RuntimeSetting(dry_run=False))
    db_session.commit()


def test_exit_shadow_endpoint_returns_dry_run_mode_and_no_submit_flags(client):
    response = client.post("/kis/exit-shadow/run-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "shadow_exit_dry_run"
    assert body["source"] == "kis_exit_shadow_decision"
    assert body["source_type"] == "dry_run_sell_simulation"
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["real_order_submit_allowed"] is False
    assert body["auto_sell_enabled"] is False
    assert body["scheduler_real_order_enabled"] is False
    assert body["manual_confirm_required"] is True
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["broker_submit_called"] is False
    assert body["safety"]["manual_submit_called"] is False


def test_exit_shadow_does_not_call_kis_or_manual_submit(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_order",
        lambda *args, **kwargs: pytest.fail("shadow exit must not call submit_order"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("shadow exit must not call KIS cash submit"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("shadow exit must not call manual submit"),
    )

    response = client.post("/kis/exit-shadow/run-once", json={})

    assert response.status_code == 200
    assert response.json()["real_order_submitted"] is False


def test_exit_shadow_returns_would_sell_when_stop_loss_crossed(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(
                cost_basis=10000,
                market_value=9800,
                current_price=4900,
                unrealized_pl=-200,
                unrealized_plpc=-99,
            )
        ],
    )

    response = client.post("/kis/exit-shadow/run-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "would_sell"
    assert body["action"] == "sell"
    assert body["candidate_count"] == 1
    candidate = body["candidate"]
    assert candidate["symbol"] == "005930"
    assert candidate["trigger"] == "stop_loss"
    assert candidate["trigger_source"] == "cost_basis_pl_pct"
    assert candidate["unrealized_pl_pct"] == pytest.approx(-0.02)
    assert candidate["audit_metadata"]["source"] == "kis_exit_shadow_decision"
    assert candidate["audit_metadata"]["source_type"] == "dry_run_sell_simulation"
    assert candidate["audit_metadata"]["shadow_real_order_submitted"] is False


def test_exit_shadow_returns_would_sell_when_take_profit_crossed(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(
                cost_basis=10000,
                market_value=10200,
                current_price=5100,
                unrealized_pl=200,
                unrealized_plpc=999,
            )
        ],
    )

    response = client.post("/kis/exit-shadow/run-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "would_sell"
    assert body["candidate"]["trigger"] == "take_profit"
    assert body["candidate"]["unrealized_pl_pct"] == pytest.approx(0.02)
    assert "take_profit_triggered" in body["candidate"]["risk_flags"]


def test_exit_shadow_missing_cost_basis_does_not_trigger_thresholds(
    monkeypatch, client
):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(
                avg_entry_price=0,
                cost_basis=0,
                market_value=10200,
                current_price=5100,
                unrealized_pl=200,
                unrealized_plpc=99,
            )
        ],
    )

    response = client.post("/kis/exit-shadow/run-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "manual_review"
    assert body["action"] == "hold"
    assert body["candidate"]["trigger"] == "manual_review"
    assert body["candidate"]["trigger_source"] == "insufficient_cost_basis"
    assert "insufficient_cost_basis" in body["candidate"]["risk_flags"]
    assert "take_profit_triggered" not in json.dumps(body)
    assert "stop_loss_triggered" not in json.dumps(body)


def test_exit_shadow_holds_when_no_candidate_exists(client):
    response = client.post("/kis/exit-shadow/run-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "hold"
    assert body["action"] == "hold"
    assert body["candidate"] is None
    assert body["candidates"] == []
    assert body["candidates_evaluated"][0]["trigger"] == "none"


def test_exit_shadow_only_evaluates_held_positions(monkeypatch, client, db_session):
    db_session.query(RuntimeSetting).delete()
    db_session.add(RuntimeSetting(dry_run=False, default_symbol="999999"))
    db_session.commit()
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(symbol="999999", qty=0, cost_basis=1, unrealized_pl=-1000),
            _position(
                symbol="005930",
                cost_basis=10000,
                market_value=9800,
                current_price=4900,
                unrealized_pl=-200,
            ),
        ],
    )

    response = client.post("/kis/exit-shadow/run-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "would_sell"
    assert body["candidate"]["symbol"] == "005930"
    assert "999999" not in json.dumps(body)
    assert db_session.query(OrderLog).count() == 0


def test_exit_shadow_selects_at_most_one_final_candidate(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(
                symbol="000660",
                cost_basis=10000,
                market_value=10200,
                current_price=5100,
                unrealized_pl=200,
            ),
            _position(
                symbol="005930",
                cost_basis=10000,
                market_value=9800,
                current_price=4900,
                unrealized_pl=-200,
            ),
        ],
    )

    response = client.post("/kis/exit-shadow/run-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_count"] == 1
    assert len(body["candidates"]) == 1
    assert len(body["candidates_evaluated"]) == 2
    assert body["candidate"]["symbol"] == "005930"
    assert body["candidate"]["trigger"] == "stop_loss"


def test_exit_shadow_records_dry_run_signal_and_run_without_order(
    monkeypatch, client, db_session
):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(
                cost_basis=10000,
                market_value=9800,
                current_price=4900,
                unrealized_pl=-200,
            )
        ],
    )

    response = client.post("/kis/exit-shadow/run-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert db_session.query(OrderLog).count() == 0
    signal = db_session.query(SignalLog).one()
    assert signal.trigger_source == "shadow_exit"
    assert signal.signal_status == "shadow_exit"
    assert signal.related_order_id is None
    run = db_session.query(TradeRunLog).one()
    assert run.mode == "shadow_exit_dry_run"
    assert run.trigger_source == "shadow_exit"
    assert run.order_id is None
    payload = json.loads(run.response_payload)
    assert payload["source"] == "kis_exit_shadow_decision"
    assert payload["source_type"] == "dry_run_sell_simulation"
    assert payload["real_order_submitted"] is False
    assert payload["broker_submit_called"] is False
    assert payload["manual_submit_called"] is False
    assert body["run"]["order_id"] is None


def test_history_exposes_exit_shadow_decision_safely(
    monkeypatch, client, db_session
):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(
                cost_basis=10000,
                market_value=9800,
                current_price=4900,
                unrealized_pl=-200,
            )
        ],
    )
    client.post("/kis/exit-shadow/run-once", json={})

    response = client.get("/runs/recent")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["provider"] == "kis"
    assert item["market"] == "KR"
    assert item["mode"] == "shadow_exit_dry_run"
    assert item["source"] == "kis_exit_shadow_decision"
    assert item["source_type"] == "dry_run_sell_simulation"
    assert item["exit_trigger"] == "stop_loss"
    assert item["exit_trigger_source"] == "cost_basis_pl_pct"
    assert item["real_order_submitted"] is False
    assert item["broker_submit_called"] is False
    assert item["manual_submit_called"] is False
    assert item["real_order_submit_allowed"] is False
    assert item["auto_sell_enabled"] is False
    assert item["scheduler_real_order_enabled"] is False
    assert item["unrealized_pl_pct"] == pytest.approx(-0.02)


def test_exit_shadow_safety_defaults_keep_kis_auto_and_scheduler_disabled(client):
    response = client.post("/kis/exit-shadow/run-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["auto_buy_enabled"] is False
    assert body["auto_sell_enabled"] is False
    assert body["scheduler_real_order_enabled"] is False
    assert body["scheduler"]["real_orders_allowed"] is False
    assert body["real_order_submit_allowed"] is False
