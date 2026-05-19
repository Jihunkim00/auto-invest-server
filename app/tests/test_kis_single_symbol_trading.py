from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import KisOrderValidationLog, OrderLog, RuntimeSetting, SignalLog, TradeRunLog
from app.main import app
from app.services.kis_single_symbol_trading_service import MODE, SOURCE, TRIGGER_SOURCE


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
        "kis_require_confirmation": True,
        "kis_scheduler_allow_real_orders": False,
        "kr_scheduler_allow_real_orders": False,
        "kis_max_manual_order_qty": 10,
        "kis_max_manual_order_amount_krw": 1_000_000,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


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
def _patch_kis_dependencies(monkeypatch):
    settings = _settings()
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.services.kis_single_symbol_trading_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_stock_price",
        lambda self, symbol: {
            "symbol": symbol,
            "name": "Samsung Electronics",
            "current_price": 70000,
        },
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        lambda self: {"cash": 3_000_000, "total_asset_value": 5_000_000},
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.build_domestic_order_payload",
        lambda self, symbol, side, qty, order_type: {
            "CANO": "12345678",
            "ACNT_PRDT_CD": "01",
            "PDNO": symbol,
            "ORD_QTY": str(qty),
            "ORD_DVSN": "01",
        },
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.domestic_cash_order_tr_id",
        lambda self, side: "TTTC0802U" if side == "buy" else "TTTC0801U",
    )
    monkeypatch.setattr(
        "app.services.market_session_service.MarketSessionService.get_session_status",
        lambda self, market, now=None: _market_session(),
    )
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisWatchlistPreviewService.run_preview",
        lambda *args, **kwargs: pytest.fail("watchlist preview fallback must not run"),
    )
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisWatchlistPreviewService._preview_symbol",
        lambda self, raw, **kwargs: _analysis(str(raw["symbol"])),
    )


def test_kis_single_symbol_run_once_requires_symbol(client):
    response = client.post("/kis/trading/run-once", json={"quantity": 1})

    assert response.status_code == 422


def test_kis_single_symbol_dry_run_returns_no_real_submit(
    monkeypatch,
    client,
    db_session,
):
    _runtime(db_session, dry_run=True, kill_switch=False)
    submit_calls = []
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: submit_calls.append(kwargs),
    )

    response = client.post(
        "/kis/trading/run-once",
        json={
            "symbol": "005930",
            "gate_level": 1,
            "quantity": 1,
            "confirm_live": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requested_symbol"] == "005930"
    assert body["analyzed_symbol"] == "005930"
    assert body["symbol_match"] is True
    assert body["result"] == "dry_run"
    assert body["reason"] == "dry_run_mode"
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert submit_calls == []
    assert db_session.query(KisOrderValidationLog).count() == 1
    assert db_session.query(TradeRunLog).one().trigger_source == TRIGGER_SOURCE
    assert db_session.query(SignalLog).one().trigger_source == TRIGGER_SOURCE


def test_kis_single_symbol_confirm_live_false_blocks_submit(
    monkeypatch,
    client,
    db_session,
):
    _runtime(db_session, dry_run=False, kill_switch=False)
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("submit must not run"),
    )

    response = client.post(
        "/kis/trading/run-once",
        json={
            "symbol": "005930",
            "gate_level": 1,
            "quantity": 1,
            "confirm_live": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "blocked"
    assert body["reason"] == "confirm_live_required"
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False


@pytest.mark.parametrize(
    ("runtime_overrides", "settings_overrides", "session_overrides", "reason"),
    [
        ({"kill_switch": True}, {}, {}, "kill_switch_enabled"),
        ({}, {"kis_real_order_enabled": False}, {}, "kis_real_order_disabled"),
        ({}, {}, {"is_market_open": False, "is_entry_allowed_now": False}, "market_closed"),
        ({}, {}, {"is_entry_allowed_now": False}, "buy_entry_not_allowed_now"),
    ],
)
def test_kis_single_symbol_safety_gates_block_submit(
    monkeypatch,
    client,
    db_session,
    runtime_overrides,
    settings_overrides,
    session_overrides,
    reason,
):
    _runtime(db_session, **{"dry_run": False, "kill_switch": False, **runtime_overrides})
    settings = _settings(**settings_overrides)
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.services.kis_single_symbol_trading_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.market_session_service.MarketSessionService.get_session_status",
        lambda self, market, now=None: _market_session(**session_overrides),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("submit must not run"),
    )

    response = client.post(
        "/kis/trading/run-once",
        json={
            "symbol": "005930",
            "gate_level": 1,
            "quantity": 1,
            "confirm_live": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "blocked"
    assert body["reason"] == reason
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False


def test_kis_single_symbol_mismatch_blocks_submit(monkeypatch, client, db_session):
    _runtime(db_session, dry_run=False, kill_switch=False)
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisWatchlistPreviewService._preview_symbol",
        lambda self, raw, **kwargs: _analysis("005930"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("submit must not run"),
    )

    response = client.post(
        "/kis/trading/run-once",
        json={
            "symbol": "005380",
            "gate_level": 1,
            "quantity": 1,
            "confirm_live": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requested_symbol"] == "005380"
    assert body["analyzed_symbol"] == "005930"
    assert body["symbol_match"] is False
    assert body["result"] == "blocked"
    assert body["reason"] == "symbol_mismatch"
    assert body["message"] == "Returned candidate does not match selected symbol."
    assert body["real_order_submitted"] is False


def test_kis_single_symbol_success_uses_existing_manual_submit_path(
    monkeypatch,
    client,
    db_session,
):
    _runtime(db_session, dry_run=False, kill_switch=False, max_trades_per_day=3)
    submit_calls = []

    def submit_order(self, **kwargs):
        submit_calls.append(kwargs)
        return {"rt_cd": "0", "output": {"ODNO": "KIS123456"}}

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        submit_order,
    )

    response = client.post(
        "/kis/trading/run-once",
        json={
            "symbol": "005930",
            "gate_level": 1,
            "quantity": 1,
            "confirm_live": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == MODE
    assert body["source"] == SOURCE
    assert body["trigger_source"] == TRIGGER_SOURCE
    assert body["result"] == "executed"
    assert body["action"] == "buy"
    assert body["real_order_submitted"] is True
    assert body["broker_submit_called"] is True
    assert body["manual_submit_called"] is True
    assert body["kis_odno"] == "KIS123456"
    assert submit_calls == [
        {
            "symbol": "005930",
            "side": "buy",
            "qty": 1,
            "order_type": "market",
        }
    ]

    order = db_session.query(OrderLog).one()
    request_payload = json.loads(order.request_payload)
    assert request_payload["source"] == SOURCE
    assert request_payload["source_type"] == "manual_guarded_single_symbol_buy"
    assert request_payload["source_metadata"]["trigger_source"] == TRIGGER_SOURCE
    assert request_payload["scheduler_real_order_enabled"] is False
    assert db_session.query(TradeRunLog).one().order_id == order.id
    assert db_session.query(SignalLog).one().related_order_id == order.id


@pytest.mark.parametrize(
    ("gate_level", "final_buy_score", "expected_threshold"),
    [
        (3, 62, 62.0),
        (4, 56, 56.0),
    ],
)
def test_kis_single_symbol_uses_gate_profile_threshold_without_watchlist_floor(
    monkeypatch,
    client,
    db_session,
    gate_level,
    final_buy_score,
    expected_threshold,
):
    _runtime(db_session, dry_run=True, kill_switch=False)
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisWatchlistPreviewService._preview_symbol",
        lambda self, raw, **kwargs: _analysis(
            str(raw["symbol"]),
            score=final_buy_score,
            final_entry_score=final_buy_score,
            final_buy_score=final_buy_score,
            final_sell_score=0,
            quant_buy_score=final_buy_score,
            quant_sell_score=0,
            ai_buy_score=final_buy_score,
            ai_sell_score=0,
        ),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("dry-run must not submit"),
    )

    response = client.post(
        "/kis/trading/run-once",
        json={
            "symbol": "005930",
            "gate_level": gate_level,
            "quantity": 1,
            "confirm_live": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "dry_run"
    assert body["reason"] == "dry_run_mode"
    assert body["entry_ready"] is True
    assert body["readiness"]["effective_min_entry_score"] == expected_threshold
    assert body["final_buy_score"] == final_buy_score
    assert body["broker_submit_called"] is False


def test_kis_single_symbol_response_payload_does_not_expose_secrets(
    client,
    db_session,
):
    _runtime(db_session, dry_run=True, kill_switch=False)

    response = client.post(
        "/kis/trading/run-once",
        json={
            "symbol": "005930",
            "gate_level": 1,
            "quantity": 1,
            "confirm_live": True,
        },
    )

    assert response.status_code == 200
    raw = response.text
    assert "real-app-secret" not in raw
    assert "real-app-key" not in raw
    run_payload = db_session.query(TradeRunLog).one().response_payload
    assert "real-app-secret" not in run_payload
    assert "real-app-key" not in run_payload


def _runtime(db_session, **overrides):
    db_session.query(RuntimeSetting).delete()
    values = {
        "bot_enabled": True,
        "dry_run": False,
        "kill_switch": False,
        "scheduler_enabled": False,
        "default_symbol": "005930",
        "default_gate_level": 1,
        "max_trades_per_day": 3,
    }
    values.update(overrides)
    db_session.add(RuntimeSetting(**values))
    db_session.commit()


def _market_session(**overrides):
    payload = {
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
        "no_new_entry_after": "14:50",
    }
    payload.update(overrides)
    return payload


def _analysis(symbol: str, **overrides):
    payload = {
        "symbol": symbol,
        "market": "KR",
        "provider": "kis",
        "current_price": 70000,
        "score": 92,
        "final_entry_score": 92,
        "final_buy_score": 92,
        "final_sell_score": 4,
        "quant_buy_score": 91,
        "quant_sell_score": 4,
        "ai_buy_score": 94,
        "ai_sell_score": 3,
        "confidence": 0.83,
        "gpt_reason": "single-symbol advisory",
        "action": "buy",
        "entry_ready": True,
        "risk_flags": [],
        "gating_notes": ["score_threshold_passed"],
        "block_reason": None,
        "reason": "KIS single symbol analysis complete.",
        "indicator_status": "ok",
        "preview_only": False,
        "trading_enabled": True,
    }
    payload.update(overrides)
    return payload
