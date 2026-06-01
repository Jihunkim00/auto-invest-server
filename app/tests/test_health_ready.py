from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import RuntimeSetting
from app.main import app


def test_health_returns_ok():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "auto-invest-server"
    assert body["timestamp"]
    assert "version" in body


def test_ready_returns_expected_fields_when_db_available():
    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db_connected"] is True
    assert body["scheduler_runtime_enabled"] is False
    assert isinstance(body["scheduler_thread_alive"], bool)
    assert isinstance(body["kis_config_present"], bool)
    assert body["alpaca_config_present"] is True
    assert body["safe_mode_summary"] == {
        "dry_run": True,
        "kill_switch": False,
        "kis_scheduler_enabled": False,
        "kis_live_auto_sell_enabled": False,
        "kis_live_auto_buy_enabled": False,
    }


def test_ready_does_not_expose_secrets():
    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    payload_text = str(response.json())
    assert "test-key" not in payload_text
    assert "test-secret" not in payload_text
    assert "KIS_APP_SECRET" not in payload_text
    assert "KIS_ACCESS_TOKEN" not in payload_text


def test_ready_is_read_only():
    with SessionLocal() as db:
        before_runtime_rows = db.query(RuntimeSetting).count()

    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.query(RuntimeSetting).count() == before_runtime_rows
