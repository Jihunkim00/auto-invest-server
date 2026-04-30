import json

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


def test_recent_history_endpoints_return_empty_arrays(client):
    for path in ["/runs/recent", "/orders/recent", "/signals/recent"]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.json() == {"items": []}


def test_logs_summary_returns_empty_counts(client):
    response = client.get("/logs/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["latest_run"] is None
    assert body["latest_order"] is None
    assert body["latest_signal"] is None
    assert body["counts"] == {"runs": 0, "orders": 0, "signals": 0}


def test_recent_runs_serializes_hold_skipped_without_order(client, db_session):
    db_session.add(
        TradeRunLog(
            run_key="manual-test-run",
            trigger_source="manual",
            symbol="AAPL",
            mode="single_symbol",
            gate_level=4,
            stage="done",
            result="skipped",
            reason="hold_signal",
            order_id=None,
            response_payload=json.dumps(
                {
                    "action": "hold",
                    "reason": "hold_signal",
                    "trade_result": {"action": "hold", "order_id": None},
                }
            ),
        )
    )
    db_session.commit()

    response = client.get("/runs/recent")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["run_key"] == "manual-test-run"
    assert item["symbol"] == "AAPL"
    assert item["trigger_source"] == "manual"
    assert item["mode"] == "single_symbol"
    assert item["action"] == "hold"
    assert item["result"] == "skipped"
    assert item["reason"] == "hold_signal"
    assert item["related_order_id"] is None
    assert item["order_id"] is None


def test_recent_orders_returns_items_array(client, db_session):
    db_session.add(
        OrderLog(
            symbol="MSFT",
            side="buy",
            order_type="market",
            qty=1,
            broker_order_id="broker-123",
            broker_status="filled",
            internal_status="FILLED",
        )
    )
    db_session.commit()

    response = client.get("/orders/recent")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["symbol"] == "MSFT"
    assert item["side"] == "buy"
    assert item["qty"] == 1
    assert item["broker_order_id"] == "broker-123"
    assert item["broker_status"] == "filled"
    assert item["internal_status"] == "FILLED"


def test_recent_signals_returns_items_array(client, db_session):
    db_session.add(
        SignalLog(
            symbol="GOOGL",
            action="hold",
            signal_status="skipped",
            buy_score=42,
            sell_score=21,
            confidence=0.61,
            reason="score_threshold_not_met",
            related_order_id=None,
            gate_level=4,
        )
    )
    db_session.commit()

    response = client.get("/signals/recent")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["symbol"] == "GOOGL"
    assert item["action"] == "hold"
    assert item["signal_status"] == "skipped"
    assert item["buy_score"] == 42
    assert item["sell_score"] == 21
    assert item["confidence"] == 0.61
    assert item["reason"] == "score_threshold_not_met"
    assert item["related_order_id"] is None


def test_logs_summary_returns_latest_items_and_counts(client, db_session):
    db_session.add(
        TradeRunLog(
            run_key="scheduler-run",
            trigger_source="scheduler",
            symbol="WMT",
            mode="watchlist",
            stage="done",
            result="skipped",
            reason="scheduler_disabled",
        )
    )
    db_session.add(
        OrderLog(
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=1,
            broker_status="filled",
            internal_status="FILLED",
        )
    )
    db_session.add(
        SignalLog(
            symbol="AAPL",
            action="hold",
            signal_status="skipped",
            reason="hold_signal",
        )
    )
    db_session.commit()

    response = client.get("/logs/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["latest_run"]["run_key"] == "scheduler-run"
    assert body["latest_order"]["symbol"] == "AAPL"
    assert body["latest_signal"]["reason"] == "hold_signal"
    assert body["counts"] == {"runs": 1, "orders": 1, "signals": 1}
