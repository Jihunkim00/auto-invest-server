from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import TradeRunLog
from app.main import app
from app.services.scheduler_service import scheduler_service


def test_ops_scheduler_endpoints_toggle_setting():
    with TestClient(app) as client:
        settings_response = client.get("/ops/settings")
        assert settings_response.status_code == 200
        assert "scheduler_enabled" in settings_response.json()

        on_response = client.post("/ops/scheduler/on")
        assert on_response.status_code == 200
        assert on_response.json()["settings"]["scheduler_enabled"] is True

        off_response = client.post("/ops/scheduler/off")
        assert off_response.status_code == 200
        assert off_response.json()["settings"]["scheduler_enabled"] is False


def test_scheduler_skips_when_disabled():
    with TestClient(app) as client:
        client.post("/ops/scheduler/off")

    with SessionLocal() as db:
        initial_runs = db.query(TradeRunLog).count()

    scheduler_service._run_scheduled_once("midday")

    with SessionLocal() as db:
        rows = db.query(TradeRunLog).order_by(TradeRunLog.id.desc()).all()
        assert len(rows) == initial_runs + 1
        latest = rows[0]
        assert latest.trigger_source == "scheduler"
        assert latest.reason == "scheduler_disabled"
        assert latest.result == "skipped"


def test_manual_watchlist_run_still_works_when_scheduler_disabled(monkeypatch):
    calls = []

    def fake_run_once(self, db, **kwargs):
        calls.append(kwargs)
        return {"result": "ok", "trigger_source": kwargs["trigger_source"]}

    monkeypatch.setattr("app.services.watchlist_run_service.WatchlistRunService.run_once", fake_run_once)

    with TestClient(app) as client:
        client.post("/ops/scheduler/off")
        response = client.post("/trading/run-watchlist-once")

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"] == "ok"
    assert payload["trigger_source"] == "manual"
    assert calls and calls[0]["trigger_source"] == "manual"