import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.main import app


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _watchlist_payload(symbol: str, *, action: str = "hold") -> dict:
    should_trade = action in {"buy", "sell"}
    return {
        "watchlist_source": "config/watchlist.yaml",
        "configured_symbol_count": 2,
        "analyzed_symbol_count": 2,
        "max_watchlist_size": 50,
        "watchlist": [
            {"symbol": symbol, "quant_score": 72, "entry_ready": should_trade},
            {"symbol": "MSFT", "quant_score": 64, "entry_ready": False},
        ],
        "quant_candidates_count": 1,
        "researched_candidates_count": 1,
        "top_quant_candidates": [
            {
                "symbol": symbol,
                "quant_score": 72,
                "quant_reason": "strong trend",
                "entry_ready": should_trade,
                "action_hint": "buy_candidate" if should_trade else "watch",
                "block_reason": None if should_trade else "weak_final_score_gap",
            }
        ],
        "researched_candidates": [
            {
                "symbol": symbol,
                "final_entry_score": 72,
                "reason": "research ok",
                "entry_ready": should_trade,
                "action_hint": "buy_candidate" if should_trade else "watch",
                "block_reason": None if should_trade else "weak_final_score_gap",
            }
        ],
        "final_ranked_candidates": [
            {
                "symbol": symbol,
                "final_entry_score": 72,
                "reason": "ranked first",
                "entry_ready": should_trade,
                "action_hint": "buy_candidate" if should_trade else "watch",
                "block_reason": None if should_trade else "weak_final_score_gap",
            }
        ],
        "final_best_candidate": {
            "symbol": symbol,
            "final_entry_score": 72,
            "entry_ready": should_trade,
            "action_hint": "buy_candidate" if should_trade else "watch",
            "block_reason": None if should_trade else "weak_final_score_gap",
        },
        "second_final_candidate": {"symbol": "MSFT", "final_entry_score": 64},
        "tied_final_candidates": [],
        "near_tied_candidates": [],
        "tie_breaker_applied": False,
        "final_candidate_selection_reason": f"{symbol} selected",
        "final_score_gap": 8,
        "best_score": 72,
        "min_entry_score": 65,
        "min_score_gap": 3,
        "should_trade": should_trade,
        "triggered_symbol": symbol if should_trade else None,
        "trigger_block_reason": None if should_trade else "weak_final_score_gap",
        "trade_result": {
            "action": action,
            "risk_approved": should_trade,
            "order_id": 123 if should_trade else None,
            "reason": "risk approved" if should_trade else "weak_final_score_gap",
        },
    }


def _add_watchlist_run(db_session, *, run_key: str, symbol: str, created_at: datetime, action: str = "hold"):
    db_session.add(
        TradeRunLog(
            run_key=run_key,
            trigger_source="manual",
            symbol=symbol,
            mode="watchlist_trade_trigger",
            gate_level=2,
            stage="done",
            result="executed" if action in {"buy", "sell"} else "skipped",
            reason="watchlist_trade_completed" if action in {"buy", "sell"} else "weak_final_score_gap",
            order_id=123 if action in {"buy", "sell"} else None,
            request_payload=json.dumps({"source_endpoint": "/trading/run-watchlist-once"}),
            response_payload=json.dumps(_watchlist_payload(symbol, action=action)),
            created_at=created_at,
        )
    )
    db_session.commit()


def test_latest_watchlist_run_returns_empty_response_when_no_run_exists(client):
    response = client.get("/trading/watchlist/latest")

    assert response.status_code == 200
    assert response.json() == {"has_data": False, "item": None}


def test_latest_watchlist_run_returns_newest_watchlist_payload(client, db_session):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _add_watchlist_run(db_session, run_key="older", symbol="AAPL", created_at=now)
    _add_watchlist_run(db_session, run_key="newer", symbol="NVDA", created_at=now + timedelta(minutes=1))

    response = client.get("/trading/watchlist/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["has_data"] is True
    item = body["item"]
    assert item["final_best_candidate"]["symbol"] == "NVDA"
    assert item["run"]["run_key"] == "newer"
    assert item["run"]["result"] == "skipped"


def test_latest_watchlist_run_is_read_only(client, db_session):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _add_watchlist_run(db_session, run_key="latest", symbol="AMD", created_at=now)
    db_session.add(SignalLog(symbol="AMD", action="hold", signal_status="skipped"))
    db_session.add(OrderLog(symbol="AMD", side="buy", order_type="market", internal_status="REQUESTED"))
    db_session.commit()
    counts_before = (
        db_session.query(TradeRunLog).count(),
        db_session.query(SignalLog).count(),
        db_session.query(OrderLog).count(),
    )

    response = client.get("/trading/watchlist/latest")

    counts_after = (
        db_session.query(TradeRunLog).count(),
        db_session.query(SignalLog).count(),
        db_session.query(OrderLog).count(),
    )
    assert response.status_code == 200
    assert counts_after == counts_before


def test_latest_watchlist_run_serializes_hold_without_error_and_keeps_candidates(client, db_session):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _add_watchlist_run(db_session, run_key="hold-run", symbol="HON", created_at=now, action="hold")

    response = client.get("/trading/watchlist/latest")

    assert response.status_code == 200
    item = response.json()["item"]
    assert item["should_trade"] is False
    assert item["trade_result"]["action"] == "hold"
    assert item["trade_result"]["order_id"] is None
    assert item["run"]["result"] == "skipped"
    assert item["run"]["order_id"] is None
    assert item["trigger_block_reason"] == "weak_final_score_gap"
    assert item["top_quant_candidates"][0]["symbol"] == "HON"
    assert item["researched_candidates"][0]["symbol"] == "HON"
    assert item["final_ranked_candidates"][0]["symbol"] == "HON"
