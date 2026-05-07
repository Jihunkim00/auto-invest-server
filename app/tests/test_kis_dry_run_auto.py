import json

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, SignalLog, TradeRunLog
from app.main import app


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
    risk_flags=None,
    gating_notes=None,
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
        "reason": "KIS dry-run candidate.",
        "entry_ready": False,
        "action_hint": "watch",
        "risk_flags": risk_flags or [],
        "gating_notes": gating_notes or [],
        "event_risk": {"entry_blocked": False, "has_near_event": False},
    }


def _preview(
    *,
    candidate=None,
    final_score_gap=5.0,
    market_open=True,
    entry_allowed=True,
    held_positions=None,
    portfolio_items=None,
    risk_flags=None,
    gating_notes=None,
):
    candidate = candidate if candidate is not None else _candidate()
    held_positions = held_positions or []
    held_symbols = [item["symbol"] for item in held_positions]
    return {
        "provider": "kis",
        "market": "KR",
        "dry_run": True,
        "preview_only": True,
        "gpt_analysis_included": True,
        "configured_symbol_count": 1,
        "analyzed_symbol_count": 1,
        "quant_candidates_count": 1 if candidate else 0,
        "researched_candidates_count": 1 if candidate else 0,
        "final_best_candidate": candidate,
        "final_ranked_candidates": [candidate] if candidate else [],
        "top_quant_candidates": [candidate] if candidate else [],
        "researched_candidates": [candidate] if candidate else [],
        "entry_candidate_symbol": candidate["symbol"] if candidate else None,
        "best_score": candidate.get("final_entry_score") if candidate else None,
        "final_score_gap": final_score_gap,
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
            "is_market_open": market_open,
            "is_entry_allowed_now": entry_allowed,
            "is_near_close": False,
            "no_new_entry_after": "15:00",
        },
        "risk_flags": risk_flags or [],
        "gating_notes": gating_notes or [],
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


def _patch_preview(monkeypatch, payload):
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisWatchlistPreviewService.run_preview",
        lambda self, include_gpt=True, gate_level=2, db=None: payload,
    )


def test_kis_auto_dry_run_once_returns_false_and_persists_simulation(
    monkeypatch, client, db_session
):
    _patch_preview(monkeypatch, _preview())

    response = client.post("/kis/auto/dry-run-once?gate_level=2")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "kis"
    assert body["market"] == "KR"
    assert body["mode"] == "kis_dry_run_auto"
    assert body["dry_run"] is True
    assert body["simulated"] is True
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["result"] == "simulated_order_created"
    assert body["action"] == "buy"
    assert body["triggered_symbol"] == "005930"
    assert body["signal_id"] is not None
    assert body["order_id"] is not None
    assert body["kis_odno"] is None
    assert body["broker_order_id"] is None
    assert body["quant_buy_score"] == 74.0
    assert body["ai_buy_score"] == 82.0
    assert body["final_entry_score"] == 76.0

    order = db_session.get(OrderLog, body["order_id"])
    assert order.broker == "kis"
    assert order.market == "KR"
    assert order.internal_status == "DRY_RUN_SIMULATED"
    assert order.broker_status == "SIMULATED"
    assert order.broker_order_id is None
    assert order.kis_odno is None
    order_response = json.loads(order.response_payload)
    assert order_response["real_order_submitted"] is False
    assert order_response["broker_submit_called"] is False
    assert order_response["manual_submit_called"] is False

    signal = db_session.get(SignalLog, body["signal_id"])
    assert signal.signal_status == "simulated"
    assert signal.related_order_id == order.id
    assert signal.quant_buy_score == 74.0
    assert signal.ai_buy_score == 82.0
    assert signal.final_buy_score == 76.0

    run = db_session.query(TradeRunLog).filter(TradeRunLog.mode == "kis_dry_run_auto").one()
    assert run.result == "simulated_order_created"
    run_payload = json.loads(run.response_payload)
    assert run_payload["real_order_submitted"] is False
    assert run_payload["order_id"] == order.id


def test_kis_scheduler_dry_run_once_returns_false(monkeypatch, client):
    _patch_preview(monkeypatch, _preview())

    response = client.post("/kis/scheduler/run-dry-run-once?gate_level=2")

    assert response.status_code == 200
    body = response.json()
    assert body["trigger_source"] == "scheduler_kis_dry_run_auto"
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False


def test_kis_dry_run_auto_never_calls_manual_or_live_submit(monkeypatch, client):
    _patch_preview(monkeypatch, _preview())
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("dry-run auto must not call manual submit"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_order",
        lambda *args, **kwargs: pytest.fail("dry-run auto must not call live submit"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("dry-run auto must not call KIS cash submit"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.build_domestic_order_payload",
        lambda *args, **kwargs: pytest.fail("dry-run auto must not build live order payloads"),
    )

    response = client.post("/kis/auto/dry-run-once")

    assert response.status_code == 200
    assert response.json()["real_order_submitted"] is False


def test_kis_dry_run_kill_switch_skips_without_order(monkeypatch, client, db_session):
    db_session.add(RuntimeSetting(kill_switch=True))
    db_session.commit()
    _patch_preview(monkeypatch, _preview())

    response = client.post("/kis/auto/dry-run-once")

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "skipped"
    assert body["action"] == "hold"
    assert body["order_id"] is None
    assert body["real_order_submitted"] is False
    assert body["trigger_block_reason"] == "kill_switch_enabled"
    assert db_session.query(OrderLog).count() == 0
    signal = db_session.query(SignalLog).one()
    assert signal.signal_status == "skipped"


def test_kis_dry_run_after_no_new_entry_skips_buy(monkeypatch, client, db_session):
    _patch_preview(monkeypatch, _preview(entry_allowed=False))

    response = client.post("/kis/auto/dry-run-once")

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "skipped"
    assert body["order_id"] is None
    assert body["trigger_block_reason"] == "entry_not_allowed_now"
    assert db_session.query(OrderLog).count() == 0


def test_kis_dry_run_sell_simulation_not_blocked_by_entry_caps(
    monkeypatch, client, db_session
):
    db_session.add(RuntimeSetting(per_slot_new_entry_limit=0, max_open_positions=1))
    db_session.commit()
    held = {"symbol": "005930", "name": "Samsung", "qty": 2, "current_price": 72000}
    sell_item = {
        **_candidate(
            final_entry_score=20.0,
            quant_buy_score=20.0,
            quant_sell_score=72.0,
            ai_buy_score=18.0,
            ai_sell_score=70.0,
            final_sell_score=71.5,
        ),
        "mode": "position_management_preview",
        "symbol_role": "held_position",
        "allowed_actions": ["hold", "sell"],
        "position": held,
    }
    _patch_preview(
        monkeypatch,
        _preview(
            candidate=_candidate(symbol="000660", final_entry_score=78.0),
            held_positions=[held],
            portfolio_items=[sell_item],
        ),
    )

    response = client.post("/kis/scheduler/run-dry-run-once")

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "simulated_order_created"
    assert body["action"] == "sell"
    assert body["triggered_symbol"] == "005930"
    order = db_session.get(OrderLog, body["order_id"])
    assert order.side == "sell"
    assert order.qty == 2
    assert order.kis_odno is None
    assert order.broker_order_id is None


def test_kis_dry_run_logs_and_response_are_sanitized(monkeypatch, client, db_session):
    payload = _preview(
        candidate={
            **_candidate(),
            "indicator_payload": {
                **_indicators(),
                "access_token": "secret-token",
                "CANO": "12345678",
            },
        },
        risk_flags=["uses_sanitizer"],
        gating_notes=["safe"],
    )
    payload["held_positions"] = [{"symbol": "000660", "qty": 1, "account_no": "12345678"}]
    payload["raw_payload"] = {"appsecret": "real-secret", "approval_key": "approval-secret"}
    _patch_preview(monkeypatch, payload)

    response = client.post("/kis/auto/dry-run-once")

    assert response.status_code == 200
    body_text = json.dumps(response.json())
    assert "secret-token" not in body_text
    assert "12345678" not in body_text
    assert "real-secret" not in body_text
    assert "approval-secret" not in body_text
    run = db_session.query(TradeRunLog).filter(TradeRunLog.mode == "kis_dry_run_auto").one()
    run_text = f"{run.request_payload} {run.response_payload}"
    assert "secret-token" not in run_text
    assert "12345678" not in run_text
    assert "real-secret" not in run_text
    assert "approval-secret" not in run_text
