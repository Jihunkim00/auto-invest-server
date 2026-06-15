import json

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import OrderLog
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


def test_logs_orders_exposes_live_order_audit_summary(client, db_session):
    audit_metadata = {
        "audit_version": "pr50_manual_kis_live_order_v1",
        "broker": "kis",
        "market": "KR",
        "source_endpoint": "/kis/orders/manual-submit",
        "source_context": "direct_manual_ticket",
        "order_source": "manual_ticket",
        "operator_action_source": "direct_manual_ticket",
        "symbol": "005930",
        "company_name": "Samsung Electronics",
        "side": "buy",
        "qty": 1,
        "estimated_notional": 72000,
        "validation_age_seconds": 24,
        "validation_stale": False,
        "daily_live_order_remaining": 2,
        "warning_level": "safe",
        "confirmation_dialog_shown": True,
        "user_confirmed_live_order": True,
        "broker_submit_called": True,
        "real_order_submitted": True,
        "manual_submit_called": True,
        "risk_flags": ["manual_live_trading"],
        "gating_notes": ["validation_summary_present"],
    }
    payload = {
        "provider": "kis",
        "market": "KR",
        "mode": "manual_live",
        "real_order_submitted": True,
        "broker_submit_called": True,
        "manual_submit_called": True,
        "audit_metadata": audit_metadata,
    }
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="buy",
            order_type="market",
            qty=1,
            notional=72000,
            broker_order_id="0001234567",
            kis_odno="0001234567",
            broker_status="submitted",
            internal_status="SUBMITTED",
            request_payload=json.dumps(payload),
            response_payload=json.dumps(payload),
        )
    )
    db_session.commit()

    response = client.get("/logs/orders")

    assert response.status_code == 200
    item = response.json()[0]
    assert item["audit_source_context"] == "direct_manual_ticket"
    assert item["audit_warning_level"] == "safe"
    assert item["audit_validation_age_seconds"] == 24
    assert item["audit_estimated_notional"] == 72000.0
    assert item["audit_daily_live_order_remaining"] == 2
    assert item["audit_risk_flags"] == ["manual_live_trading"]
    assert item["audit_gating_notes"] == ["validation_summary_present"]
    assert item["audit_metadata"]["user_confirmed_live_order"] is True
