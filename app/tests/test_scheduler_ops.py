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


def test_scheduler_status_keeps_kr_disabled_by_default():
    with TestClient(app) as client:
        response = client.get("/scheduler/status")

    assert response.status_code == 200
    body = response.json()
    assert body["US"]["enabled_for_scheduler"] is True
    assert body["US"]["timezone"] == "America/New_York"
    assert body["US"]["slots"]
    assert body["KR"]["enabled_for_scheduler"] is False
    assert body["KR"]["timezone"] == "Asia/Seoul"
    assert body["KR"]["slots"]
    assert body["KR"]["preview_only"] is True
    assert body["KR"]["real_orders_allowed"] is False


def test_kis_scheduler_preview_once_is_preview_only(monkeypatch):
    def fake_preview(self, include_gpt=True):
        return {
            "market": "KR",
            "provider": "kis",
            "preview_only": True,
            "dry_run": True,
            "watchlist": [],
            "real_order_submitted": False,
        }

    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisWatchlistPreviewService.run_preview",
        fake_preview,
    )

    with TestClient(app) as client:
        response = client.post("/kis/scheduler/run-preview-once")

    assert response.status_code == 200
    body = response.json()
    assert body["preview_only"] is True
    assert body["scheduler_preview_only"] is True
    assert body["real_order_submitted"] is False
    assert body["trigger_source"] == "manual_scheduler_preview"
