import json

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, SignalLog, TradeRunLog
from app.main import app
from app.services.kis_scheduler_simulation_service import KisSchedulerSimulationService


def _indicators():
    return {
        "price": 72000.0,
        "close": 71900.0,
        "ema20": 70000.0,
        "ema50": 68000.0,
        "rsi": 58.0,
        "vwap": 70500.0,
        "atr": 1200.0,
        "volume_ratio": 1.2,
        "momentum": 0.018,
        "short_momentum": 0.018,
        "recent_return": 0.04,
        "day_open": 71500.0,
        "previous_high": 73000.0,
        "previous_low": 65000.0,
    }


def _candidate(
    symbol="005930",
    *,
    final_entry_score=76.0,
    quant_buy_score=74.0,
    quant_sell_score=12.0,
    ai_buy_score=82.0,
    ai_sell_score=14.0,
    final_sell_score=12.5,
    current_price=72000.0,
):
    return {
        "symbol": symbol,
        "name": "Samsung",
        "market": "KOSPI",
        "currency": "KRW",
        "current_price": current_price,
        "indicator_status": "ok",
        "indicator_payload": _indicators(),
        "quant_score": quant_buy_score,
        "quant_buy_score": quant_buy_score,
        "quant_sell_score": quant_sell_score,
        "ai_buy_score": ai_buy_score,
        "ai_sell_score": ai_sell_score,
        "confidence": 0.74,
        "final_buy_score": final_entry_score,
        "final_sell_score": final_sell_score,
        "final_entry_score": final_entry_score,
        "quant_reason": "EMA20>EMA50 uptrend",
        "gpt_reason": "Advisory only.",
        "reason": "KIS scheduler candidate.",
        "entry_ready": False,
        "action_hint": "watch",
        "risk_flags": [],
        "gating_notes": [],
        "event_risk": {"entry_blocked": False, "has_near_event": False},
    }


def _preview(*, candidate=None, held_positions=None, portfolio_items=None):
    candidate = candidate if candidate is not None else _candidate()
    held_positions = held_positions or []
    held_symbols = [item["symbol"] for item in held_positions]
    return {
        "provider": "kis",
        "market": "KR",
        "dry_run": True,
        "preview_only": True,
        "configured_symbol_count": 2,
        "analyzed_symbol_count": 2,
        "quant_candidates_count": 2 if candidate else 0,
        "researched_candidates_count": 2 if candidate else 0,
        "final_best_candidate": candidate,
        "final_ranked_candidates": [
            item
            for item in [
                candidate,
                _candidate("000660", final_entry_score=72.0, current_price=150000.0),
            ]
            if item
        ],
        "top_quant_candidates": [candidate] if candidate else [],
        "researched_candidates": [candidate] if candidate else [],
        "entry_candidate_symbol": candidate["symbol"] if candidate else None,
        "best_score": candidate.get("final_entry_score") if candidate else None,
        "final_score_gap": 5.0,
        "min_entry_score": 65,
        "min_score_gap": 3,
        "max_sell_score": 25,
        "held_positions": held_positions,
        "held_symbols": held_symbols,
        "held_position_count": len(held_positions),
        "open_position_count": len(held_positions),
        "max_open_positions": 3,
        "per_slot_new_entry_limit": 1,
        "market_session": {
            "market": "KR",
            "timezone": "Asia/Seoul",
            "is_market_open": True,
            "is_entry_allowed_now": True,
            "is_near_close": False,
            "no_new_entry_after": "15:00",
        },
        "risk_flags": [],
        "gating_notes": [],
        "portfolio_preview_items": portfolio_items or [],
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


@pytest.fixture()
def scheduler_patches(monkeypatch):
    calls = []

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        lambda self: calls.append("balance")
        or {
            "provider": "kis",
            "market": "KR",
            "currency": "KRW",
            "cash": 10_000_000,
            "total_asset_value": 20_000_000,
            "unrealized_pl": 0,
        },
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: calls.append("positions") or [],
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_open_orders",
        lambda self: calls.append("open_orders") or [],
    )

    def fake_preview(self, include_gpt=True, gate_level=2, db=None):
        calls.append("preview")
        return _preview()

    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisWatchlistPreviewService.run_preview",
        fake_preview,
    )
    return calls


def test_kis_scheduler_status_disabled_by_default(client):
    response = client.get("/kis/scheduler/status")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["dry_run"] is True
    assert body["real_orders_allowed"] is False
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["broker_submit_called"] is False
    assert body["safety"]["manual_submit_called"] is False


def test_kis_scheduler_uses_dry_run_simulation_only_and_fetches_account_first(
    client, db_session, scheduler_patches
):
    response = client.post("/kis/scheduler/run-dry-run-auto-once?gate_level=2")

    assert response.status_code == 200
    body = response.json()
    assert scheduler_patches[:3] == ["balance", "positions", "open_orders"]
    assert scheduler_patches.index("preview") > scheduler_patches.index("open_orders")
    assert body["trigger_source"] == "scheduler_kis_dry_run_auto"
    assert "scheduler_kis_portfolio_simulation" in body["trigger_sources"]
    assert body["scheduler_dry_run"] is True
    assert body["scheduler_allow_real_orders"] is False
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["result"] == "simulated_order_created"
    assert body["action"] == "buy"

    order = db_session.get(OrderLog, body["order_id"])
    assert order is not None
    assert order.internal_status == "DRY_RUN_SIMULATED"
    assert order.broker_order_id is None
    assert order.kis_odno is None
    order_payload = json.loads(order.response_payload)
    assert order_payload["real_order_submitted"] is False
    assert order_payload["broker_submit_called"] is False
    assert order_payload["manual_submit_called"] is False

    signal = db_session.get(SignalLog, body["signal_id"])
    assert signal is not None
    assert signal.signal_status == "simulated"
    run = db_session.query(TradeRunLog).filter(
        TradeRunLog.trigger_source == "scheduler_kis_dry_run_auto"
    ).one()
    assert run.order_id == order.id


def test_kis_scheduler_does_not_call_live_or_manual_submit(
    monkeypatch, client, scheduler_patches
):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_order",
        lambda *args, **kwargs: pytest.fail("scheduler must not call submit_order"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("scheduler must not call KIS cash submit"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("scheduler must not call manual submit"),
    )

    response = client.post("/kis/scheduler/run-dry-run-auto-once")

    assert response.status_code == 200
    assert response.json()["real_order_submitted"] is False


def test_kis_scheduler_does_not_use_manual_order_symbol(
    client, db_session, scheduler_patches
):
    db_session.add(RuntimeSetting(default_symbol="999999"))
    db_session.commit()

    response = client.post("/kis/scheduler/run-dry-run-auto-once")

    assert response.status_code == 200
    body = response.json()
    assert body["triggered_symbol"] == "005930"
    assert "999999" not in json.dumps(body)
    order = db_session.get(OrderLog, body["order_id"])
    assert order.symbol == "005930"


def test_kis_scheduler_manages_existing_position_before_watchlist_entry(
    monkeypatch, client, db_session, scheduler_patches
):
    held = {"symbol": "005930", "name": "Samsung", "qty": 2, "current_price": 72000}
    sell_item = {
        **_candidate(
            "005930",
            final_entry_score=20,
            quant_buy_score=20,
            quant_sell_score=72,
            ai_buy_score=18,
            ai_sell_score=70,
            final_sell_score=71.5,
        ),
        "mode": "position_management_preview",
        "symbol_role": "held_position",
        "allowed_actions": ["hold", "sell"],
        "position": held,
    }
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [held],
    )
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisWatchlistPreviewService.run_preview",
        lambda self, include_gpt=True, gate_level=2, db=None: _preview(
            candidate=_candidate("000660", final_entry_score=82, current_price=150000),
            held_positions=[held],
            portfolio_items=[sell_item],
        ),
    )

    response = client.post("/kis/scheduler/run-dry-run-auto-once")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "sell"
    assert body["triggered_symbol"] == "005930"
    order = db_session.get(OrderLog, body["order_id"])
    assert order.side == "sell"
    child_run = db_session.query(TradeRunLog).filter(
        TradeRunLog.trigger_source == "scheduler_kis_portfolio_simulation"
    ).one()
    assert child_run.symbol == "005930"


def test_kis_scheduler_sell_simulation_not_blocked_by_entry_cap(
    monkeypatch, client, db_session
):
    db_session.add(RuntimeSetting(per_slot_new_entry_limit=0, max_open_positions=1))
    db_session.commit()
    held = {"symbol": "005930", "name": "Samsung", "qty": 2, "current_price": 72000}
    sell_item = {
        **_candidate(
            "005930",
            final_entry_score=20,
            quant_buy_score=20,
            quant_sell_score=72,
            ai_buy_score=18,
            ai_sell_score=70,
            final_sell_score=71.5,
        ),
        "mode": "position_management_preview",
        "symbol_role": "held_position",
        "allowed_actions": ["hold", "sell"],
        "position": held,
    }
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        lambda self: {"cash": 1000000, "total_asset_value": 2000000, "unrealized_pl": 0},
    )
    monkeypatch.setattr("app.brokers.kis_client.KisClient.list_positions", lambda self: [held])
    monkeypatch.setattr("app.brokers.kis_client.KisClient.list_open_orders", lambda self: [])
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisWatchlistPreviewService.run_preview",
        lambda self, include_gpt=True, gate_level=2, db=None: _preview(
            candidate=_candidate("000660", final_entry_score=82, current_price=150000),
            held_positions=[held],
            portfolio_items=[sell_item],
        ),
    )

    response = client.post("/kis/scheduler/run-dry-run-auto-once")

    assert response.status_code == 200
    assert response.json()["action"] == "sell"


@pytest.mark.parametrize(
    ("unrealized_pl", "market_value", "expected_reason"),
    [
        (-200, 9800, "stop_loss_triggered"),
        (200, 10200, "take_profit_triggered"),
    ],
)
def test_kis_scheduler_exit_thresholds_trigger_sell_simulation(
    monkeypatch, client, unrealized_pl, market_value, expected_reason
):
    held = {
        "symbol": "005930",
        "name": "Samsung",
        "qty": 2,
        "current_price": market_value / 2,
        "avg_entry_price": 5000,
        "cost_basis": 10000,
        "market_value": market_value,
        "unrealized_pl": unrealized_pl,
        "unrealized_plpc": unrealized_pl,
    }
    quiet_item = {
        **_candidate(
            "005930",
            final_entry_score=72,
            quant_buy_score=72,
            quant_sell_score=10,
            ai_buy_score=70,
            ai_sell_score=8,
            final_sell_score=10,
        ),
        "mode": "position_management_preview",
        "symbol_role": "held_position",
        "allowed_actions": ["hold", "sell"],
        "position": held,
    }
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        lambda self: {"cash": 1000000, "total_asset_value": 2000000, "unrealized_pl": 0},
    )
    monkeypatch.setattr("app.brokers.kis_client.KisClient.list_positions", lambda self: [held])
    monkeypatch.setattr("app.brokers.kis_client.KisClient.list_open_orders", lambda self: [])
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisWatchlistPreviewService.run_preview",
        lambda self, include_gpt=True, gate_level=2, db=None: _preview(
            candidate=_candidate("000660", final_entry_score=82, current_price=150000),
            held_positions=[held],
            portfolio_items=[quiet_item],
        ),
    )

    response = client.post("/kis/scheduler/run-dry-run-auto-once")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "sell"
    assert body["triggered_symbol"] == "005930"
    assert expected_reason in body["risk_flags"]


def test_kis_scheduler_exit_threshold_does_not_use_profit_amount_as_percent(
    monkeypatch, client
):
    held = {
        "symbol": "091810",
        "name": "Small Profit",
        "qty": 11,
        "current_price": 897,
        "avg_entry_price": 0,
        "cost_basis": 9841,
        "market_value": 9867,
        "unrealized_pl": 26,
        "unrealized_plpc": 26,
    }
    quiet_item = {
        **_candidate(
            "091810",
            final_entry_score=72,
            quant_buy_score=72,
            quant_sell_score=10,
            ai_buy_score=70,
            ai_sell_score=8,
            final_sell_score=10,
            current_price=897,
        ),
        "mode": "position_management_preview",
        "symbol_role": "held_position",
        "allowed_actions": ["hold", "sell"],
        "position": held,
    }
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        lambda self: {"cash": 1000000, "total_asset_value": 2000000, "unrealized_pl": 0},
    )
    monkeypatch.setattr("app.brokers.kis_client.KisClient.list_positions", lambda self: [held])
    monkeypatch.setattr("app.brokers.kis_client.KisClient.list_open_orders", lambda self: [])
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisWatchlistPreviewService.run_preview",
        lambda self, include_gpt=True, gate_level=2, db=None: _preview(
            candidate=_candidate("091810", current_price=897),
            held_positions=[held],
            portfolio_items=[quiet_item],
        ),
    )

    response = client.post("/kis/scheduler/run-dry-run-auto-once")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "hold"
    assert body["order_id"] is None
    assert "take_profit_triggered" not in body["risk_flags"]


def test_kis_scheduler_blocks_new_entry_when_daily_limit_reached(
    client, db_session, scheduler_patches
):
    db_session.add(RuntimeSetting(global_daily_entry_limit=1))
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="000660",
            side="buy",
            order_type="market",
            qty=1,
            internal_status="DRY_RUN_SIMULATED",
            broker_status="SIMULATED",
        )
    )
    db_session.commit()

    response = client.post("/kis/scheduler/run-dry-run-auto-once")

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "skipped"
    assert body["order_id"] is None
    assert body["trigger_block_reason"] == "global_daily_entry_limit_reached"


def test_kis_scheduler_blocks_duplicate_same_symbol_entry(monkeypatch, client):
    held = {"symbol": "005930", "qty": 3, "current_price": 72000}
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_account_balance",
        lambda self: {"cash": 1000000, "total_asset_value": 2000000, "unrealized_pl": 0},
    )
    monkeypatch.setattr("app.brokers.kis_client.KisClient.list_positions", lambda self: [held])
    monkeypatch.setattr("app.brokers.kis_client.KisClient.list_open_orders", lambda self: [])
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisWatchlistPreviewService.run_preview",
        lambda self, include_gpt=True, gate_level=2, db=None: _preview(
            candidate=_candidate("005930"),
            held_positions=[held],
            portfolio_items=[],
        ),
    )

    response = client.post("/kis/scheduler/run-dry-run-auto-once")

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "skipped"
    assert body["trigger_block_reason"] == "symbol_already_held"
    assert body["order_id"] is None


def test_kis_scheduler_creates_max_one_simulated_buy_per_run(
    client, db_session, scheduler_patches
):
    response = client.post("/kis/scheduler/run-dry-run-auto-once")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "buy"
    assert db_session.query(OrderLog).filter(OrderLog.side == "buy").count() == 1


def test_kis_scheduler_disabled_skips_scheduled_run(monkeypatch, db_session):
    monkeypatch.setattr(
        KisSchedulerSimulationService,
        "_scheduler_settings",
        lambda self: {"enabled": False, "dry_run": True, "allow_real_orders": False},
    )
    service = KisSchedulerSimulationService(client=object())

    body = service.run_once(
        db_session,
        scheduler_slot="midday",
        require_enabled=True,
    )

    assert body["result"] == "skipped"
    assert body["reason"] == "kis_scheduler_disabled"
    assert body["real_order_submitted"] is False
    run = db_session.query(TradeRunLog).one()
    assert run.trigger_source == "scheduler_kis_dry_run_auto"
    assert run.result == "skipped"


def test_manual_kis_live_submit_remains_independent(client, scheduler_patches):
    client.post("/kis/scheduler/run-dry-run-auto-once")

    response = client.post(
        "/kis/orders/submit-manual",
        json={
            "market": "KR",
            "symbol": "005930",
            "side": "buy",
            "qty": 1,
            "order_type": "market",
            "dry_run": False,
            "confirm_live": False,
        },
    )

    assert response.status_code in {400, 409}
    assert response.json()["real_order_submitted"] is False
