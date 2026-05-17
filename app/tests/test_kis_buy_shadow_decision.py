from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, SignalLog, TradeRunLog
from app.main import app
from app.services.kis_buy_shadow_decision_service import (
    MODE,
    SOURCE,
    SOURCE_TYPE,
    KisBuyShadowDecisionService,
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


def _candidate(**overrides):
    payload = {
        "symbol": "005930",
        "market": "KR",
        "provider": "kis",
        "current_price": 72_000,
        "final_score": 82.5,
        "final_entry_score": 82.5,
        "final_buy_score": 82.5,
        "quant_score": 78.0,
        "quant_buy_score": 78.0,
        "gpt_buy_score": 65.0,
        "ai_buy_score": 65.0,
        "confidence": 0.76,
        "final_sell_score": 12.0,
        "quant_sell_score": 10.0,
        "risk_flags": [],
        "gating_notes": [],
        "gpt_context": {},
        "reason": "strong quant-first setup",
    }
    payload.update(overrides)
    return payload


def _preview(candidates=None, **overrides):
    candidates = [_candidate()] if candidates is None else candidates
    payload = {
        "provider": "kis",
        "market": "KR",
        "dry_run": True,
        "preview_only": True,
        "final_ranked_candidates": candidates,
        "final_best_candidate": candidates[0] if candidates else None,
        "held_symbols": [],
        "held_positions": [],
        "risk_flags": [],
        "gating_notes": [],
        "market_session": _open_session(),
    }
    payload.update(overrides)
    return payload


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


def _position(symbol="005930", **overrides):
    payload = {
        "symbol": symbol,
        "qty": 2,
        "current_price": 72_000,
        "market_value": 144_000,
    }
    payload.update(overrides)
    return payload


def _open_session(**overrides):
    payload = {
        "market": "KR",
        "timezone": "Asia/Seoul",
        "is_market_open": True,
        "is_entry_allowed_now": True,
        "is_near_close": False,
        "is_holiday": False,
        "closure_reason": None,
        "effective_close": "15:30",
        "no_new_entry_after": "14:50",
        "local_time": "2026-05-17T10:00:00+09:00",
    }
    payload.update(overrides)
    return payload


class _FakeClient:
    def __init__(self, *, balance=None, positions=None, open_orders=None, settings=None):
        self.settings = settings or SimpleNamespace(
            kis_enabled=True,
            kis_real_order_enabled=True,
            kis_scheduler_allow_real_orders=False,
            kr_scheduler_allow_real_orders=False,
        )
        self.balance = balance if balance is not None else _balance()
        self.positions = positions if positions is not None else []
        self.open_orders = open_orders if open_orders is not None else []
        self.submit_calls = 0

    def get_account_balance(self):
        return self.balance

    def list_positions(self):
        return self.positions

    def list_open_orders(self):
        return self.open_orders

    def submit_domestic_cash_order(self, *args, **kwargs):
        self.submit_calls += 1
        raise AssertionError("buy shadow must not submit a KIS order")

    def submit_order(self, *args, **kwargs):
        self.submit_calls += 1
        raise AssertionError("buy shadow must not submit a generic order")


class _PreviewService:
    def __init__(self, payload):
        self.payload = payload

    def run_preview(self, **kwargs):
        return self.payload


class _SessionService:
    def __init__(self, payload=None):
        self.payload = payload or _open_session()

    def get_session_status(self, market, **kwargs):
        return self.payload


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _service(
    *,
    preview=None,
    fake_client=None,
    session=None,
):
    fake_client = fake_client or _FakeClient()
    return KisBuyShadowDecisionService(
        fake_client,
        preview_service=_PreviewService(preview or _preview()),
        session_service=_SessionService(session),
    ), fake_client


def _runtime(db_session, **overrides):
    row = RuntimeSetting(**overrides)
    db_session.add(row)
    db_session.commit()
    return row


def test_buy_shadow_endpoint_returns_dry_run_mode_and_no_submit(
    monkeypatch,
    client,
    db_session,
):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisWatchlistPreviewService.run_preview",
        lambda self, **kwargs: _preview(),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        lambda self: _balance(),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [],
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_open_orders",
        lambda self: [],
    )
    monkeypatch.setattr(
        "app.services.kis_buy_shadow_decision_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _open_session(),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("buy shadow must not call broker submit"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("buy shadow must not call manual submit"),
    )

    response = client.post("/kis/buy-shadow/run-once?gate_level=2", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == MODE
    assert body["source"] == SOURCE
    assert body["source_type"] == SOURCE_TYPE
    assert body["decision"] == "would_buy"
    assert body["action"] == "buy"
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["auto_buy_enabled"] is False
    assert body["scheduler_real_order_enabled"] is False
    assert db_session.query(OrderLog).count() == 0


def test_buy_shadow_runtime_defaults_are_safe(db_session):
    settings = KisBuyShadowDecisionService(_FakeClient()).runtime_settings.get_settings(
        db_session
    )

    assert settings["kis_limited_auto_buy_enabled"] is False
    assert settings["kis_limited_auto_buy_shadow_enabled"] is True
    assert settings["kis_limited_auto_buy_requires_shadow_review"] is True
    assert settings["kis_limited_auto_buy_max_orders_per_day"] == 1
    assert settings["kis_limited_auto_buy_max_notional_pct"] == pytest.approx(0.03)
    assert settings["kis_limited_auto_buy_min_final_score"] == pytest.approx(75)
    assert settings["kis_limited_auto_buy_min_confidence"] == pytest.approx(0.70)
    assert settings["kis_live_auto_buy_enabled"] is False


def test_buy_shadow_strong_candidate_would_buy_and_logs(db_session):
    service, fake_client = _service()

    result = service.run_once(db_session)

    assert result["decision"] == "would_buy"
    assert result["action"] == "buy"
    assert result["candidate"]["symbol"] == "005930"
    assert result["candidate"]["suggested_quantity"] == 4
    assert result["candidate"]["suggested_notional"] == 288000
    assert result["candidate"]["audit_metadata"]["real_order_submit_allowed"] is False
    assert result["real_order_submitted"] is False
    assert fake_client.submit_calls == 0
    assert db_session.query(OrderLog).count() == 0

    signal = db_session.query(SignalLog).one()
    assert signal.trigger_source == "kis_buy_shadow"
    assert signal.signal_status == "shadow_buy"
    assert signal.action == "buy"
    assert signal.related_order_id is None

    run = db_session.query(TradeRunLog).filter(TradeRunLog.mode == MODE).one()
    assert run.result == "would_buy"
    payload = json.loads(run.response_payload)
    assert payload["real_order_submitted"] is False
    assert payload["broker_submit_called"] is False
    assert payload["manual_submit_called"] is False


@pytest.mark.parametrize(
    ("candidate", "reason"),
    [
        (_candidate(final_score=70, final_entry_score=70, final_buy_score=70), "score_threshold_not_met"),
        (_candidate(confidence=0.4), "confidence_threshold_not_met"),
        (_candidate(quant_score=20, quant_buy_score=20, gpt_buy_score=95, ai_buy_score=95), "quant_score_threshold_not_met"),
    ],
)
def test_buy_shadow_holds_when_candidate_thresholds_fail(db_session, candidate, reason):
    service, _ = _service(preview=_preview(candidates=[candidate]))

    result = service.run_once(db_session)

    assert result["decision"] == "hold"
    assert result["action"] == "hold"
    assert result["reason"] == reason
    assert result["real_order_submitted"] is False


def test_buy_shadow_blocks_if_candidate_already_held(db_session):
    service, _ = _service(fake_client=_FakeClient(positions=[_position("005930")]))

    result = service.run_once(db_session)

    assert result["decision"] == "blocked"
    assert result["reason"] == "position_already_exists"
    assert result["checks"]["position_exists"] is True


def test_buy_shadow_blocks_if_open_order_exists(db_session):
    service, _ = _service(
        fake_client=_FakeClient(open_orders=[{"symbol": "005930", "status": "SUBMITTED"}])
    )

    result = service.run_once(db_session)

    assert result["decision"] == "blocked"
    assert result["reason"] == "open_order_exists"


def test_buy_shadow_blocks_if_max_positions_reached(db_session):
    service, _ = _service(
        fake_client=_FakeClient(
            positions=[_position("000001"), _position("000002"), _position("000003")]
        )
    )

    result = service.run_once(db_session)

    assert result["decision"] == "blocked"
    assert result["reason"] == "max_positions_reached"
    assert result["checks"]["max_positions_ok"] is False


def test_buy_shadow_blocks_if_daily_buy_limit_reached(db_session):
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="000001",
            side="buy",
            order_type="market",
            qty=1,
            internal_status="DRY_RUN_SIMULATED",
            broker_status="SIMULATED",
        )
    )
    db_session.commit()
    service, _ = _service()

    result = service.run_once(db_session)

    assert result["decision"] == "blocked"
    assert result["reason"] == "daily_buy_limit_reached"
    assert result["checks"]["daily_buy_limit_ok"] is False


def test_buy_shadow_blocks_notional_cap_and_missing_price(db_session):
    high_price_service, _ = _service(
        preview=_preview(candidates=[_candidate(current_price=1_000_000)])
    )
    missing_price_service, _ = _service(
        preview=_preview(candidates=[_candidate(current_price=None)])
    )

    high_price = high_price_service.run_once(db_session)
    missing_price = missing_price_service.run_once(db_session)

    assert high_price["reason"] == "notional_cap_exceeded"
    assert missing_price["reason"] == "current_price_unavailable"
    assert high_price["real_order_submitted"] is False
    assert missing_price["real_order_submitted"] is False


def test_buy_shadow_blocks_market_closed_and_late_entry(db_session):
    closed_service, _ = _service(session=_open_session(is_market_open=False))
    late_service, _ = _service(session=_open_session(is_entry_allowed_now=False))

    closed = closed_service.run_once(db_session)
    late = late_service.run_once(db_session)

    assert closed["reason"] == "market_closed"
    assert late["reason"] == "entry_not_allowed_now"
    assert closed["broker_submit_called"] is False
    assert late["broker_submit_called"] is False


def test_buy_shadow_blocks_kill_switch_and_gpt_hard_block(db_session):
    _runtime(db_session, kill_switch=True)
    kill_service, _ = _service()
    kill = kill_service.run_once(db_session)
    assert kill["reason"] == "kill_switch_enabled"

    db_session.query(RuntimeSetting).delete()
    db_session.commit()
    gpt_service, _ = _service(
        preview=_preview(
            candidates=[
                _candidate(
                    hard_blocked=True,
                    hard_block_reason="hard_block_new_buy",
                    risk_flags=["gpt_hard_block_new_buy"],
                )
            ]
        )
    )
    gpt = gpt_service.run_once(db_session)
    assert gpt["reason"] == "gpt_hard_block_new_buy"
    assert gpt["real_order_submitted"] is False


def test_buy_shadow_blocks_daily_loss_and_account_equity_unavailable(db_session):
    loss_service, _ = _service(
        fake_client=_FakeClient(balance=_balance(total_asset_value=10_000_000, unrealized_pl=-600_000))
    )
    no_equity_service, _ = _service(
        fake_client=_FakeClient(balance={"cash": 1_000_000})
    )

    loss = loss_service.run_once(db_session)
    no_equity = no_equity_service.run_once(db_session)

    assert loss["reason"] == "daily_loss_gate_failed"
    assert no_equity["reason"] == "account_equity_unavailable"
