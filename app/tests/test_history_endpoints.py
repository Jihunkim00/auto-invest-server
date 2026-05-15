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
    assert item["provider"] == "alpaca"
    assert item["market"] == "US"


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
    assert item["provider"] == "alpaca"
    assert item["market"] == "US"


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
    assert item["provider"] == "alpaca"
    assert item["market"] == "US"


def test_recent_runs_preserves_kis_dry_run_safety_fields(client, db_session):
    db_session.add(
        TradeRunLog(
            run_key="kis-dry-run",
            trigger_source="manual_kis_dry_run_auto",
            symbol="005930",
            mode="kis_dry_run_auto",
            gate_level=2,
            stage="done",
            result="simulated_order_created",
            reason="dry_run_risk_approved",
            signal_id=7,
            order_id=9,
            response_payload=json.dumps(
                {
                    "provider": "kis",
                    "market": "KR",
                    "mode": "kis_dry_run_auto",
                    "dry_run": True,
                    "simulated": True,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                    "action": "buy",
                    "risk_flags": ["simulated_only"],
                    "gating_notes": ["Dry-run only."],
                }
            ),
        )
    )
    db_session.commit()

    response = client.get("/runs/recent")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["provider"] == "kis"
    assert item["market"] == "KR"
    assert item["mode"] == "kis_dry_run_auto"
    assert item["dry_run"] is True
    assert item["simulated"] is True
    assert item["real_order_submitted"] is False
    assert item["broker_submit_called"] is False
    assert item["manual_submit_called"] is False
    assert item["risk_flags"] == ["simulated_only"]
    assert item["gating_notes"] == ["Dry-run only."]


def test_recent_orders_preserves_kis_manual_live_safety_fields(client, db_session):
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="buy",
            order_type="market",
            qty=1,
            broker_order_id="0001234567",
            kis_odno="0001234567",
            broker_status="submitted",
            broker_order_status="submitted",
            internal_status="SUBMITTED",
            response_payload=json.dumps(
                {
                    "provider": "kis",
                    "market": "KR",
                    "real_order_submitted": True,
                    "broker_status": "submitted",
                    "internal_status": "SUBMITTED",
                    "message": "Live KIS order submitted.",
                }
            ),
        )
    )
    db_session.commit()

    response = client.get("/orders/recent")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["provider"] == "kis"
    assert item["market"] == "KR"
    assert item["real_order_submitted"] is True
    assert item["broker_submit_called"] is True
    assert item["manual_submit_called"] is True
    assert item["kis_odno"] == "0001234567"
    assert item["broker_order_status"] == "submitted"


def test_recent_orders_exposes_kis_exit_preflight_manual_sell_audit_fields(
    client, db_session
):
    source_metadata = {
        "source": "kis_live_exit_preflight",
        "source_type": "manual_confirm_exit",
        "exit_trigger": "take_profit",
        "trigger_source": "cost_basis_pl_pct",
        "manual_confirm_required": True,
        "auto_sell_enabled": False,
        "scheduler_real_order_enabled": False,
        "real_order_submit_allowed": False,
        "preflight_real_order_submitted": False,
        "preflight_broker_submit_called": False,
        "preflight_manual_submit_called": False,
        "risk_flags": ["take_profit_triggered"],
        "gating_notes": ["manual_confirm_required", "no_auto_submit"],
    }
    payload = {
        "provider": "kis",
        "market": "KR",
        "mode": "manual_live",
        "source": "kis_live_exit_preflight",
        "source_type": "manual_confirm_exit",
        "source_metadata": source_metadata,
        "real_order_submitted": True,
        "broker_submit_called": True,
        "manual_submit_called": True,
        "message": "Live KIS order submitted manually.",
    }
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="sell",
            order_type="market",
            qty=2,
            requested_qty=2,
            filled_qty=1,
            remaining_qty=1,
            avg_fill_price=72000,
            broker_order_id="0001234567",
            kis_odno="0001234567",
            broker_status="partial",
            broker_order_status="partial",
            internal_status="PARTIALLY_FILLED",
            request_payload=json.dumps(payload),
            response_payload=json.dumps(payload),
        )
    )
    db_session.commit()

    response = client.get("/orders/recent")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["provider"] == "kis"
    assert item["market"] == "KR"
    assert item["mode"] == "manual_live"
    assert item["source"] == "kis_live_exit_preflight"
    assert item["source_type"] == "manual_confirm_exit"
    assert item["exit_trigger"] == "take_profit"
    assert item["exit_trigger_source"] == "cost_basis_pl_pct"
    assert item["manual_confirm_required"] is True
    assert item["auto_sell_enabled"] is False
    assert item["scheduler_real_order_enabled"] is False
    assert item["preflight_real_order_submitted"] is False
    assert item["real_order_submitted"] is True
    assert item["broker_submit_called"] is True
    assert item["manual_submit_called"] is True
    assert item["filled_quantity"] == 1
    assert item["remaining_quantity"] == 1
    assert item["average_fill_price"] == 72000
    assert item["risk_flags"] == ["take_profit_triggered"]
    assert item["gating_notes"] == ["manual_confirm_required", "no_auto_submit"]


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
