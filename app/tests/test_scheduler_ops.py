import json
from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import RuntimeSetting, TradeRunLog
from app.main import app
from app.services.scheduler_service import scheduler_service


def _settings(**overrides):
    defaults = {
        "dry_run": False,
        "default_symbol": "ABC",
        "kis_enabled": True,
        "kis_real_order_enabled": True,
        "kis_scheduler_enabled": False,
        "kis_scheduler_dry_run": True,
        "kis_scheduler_allow_real_orders": False,
        "kis_scheduler_configured_allow_real_orders": False,
        "kr_scheduler_enabled": False,
        "kr_scheduler_allow_real_orders": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


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


def test_kr_scheduler_skips_when_kis_scheduler_disabled():
    with SessionLocal() as db:
        from app.services.runtime_setting_service import RuntimeSettingService

        RuntimeSettingService().update_settings(
            db,
            {
                "scheduler_enabled": True,
                "kis_scheduler_enabled": False,
            },
        )
        initial_runs = db.query(TradeRunLog).count()

    scheduler_service._run_kr_scheduled_once("midday")

    with SessionLocal() as db:
        rows = db.query(TradeRunLog).order_by(TradeRunLog.id.desc()).all()
        assert len(rows) == initial_runs + 1
        latest = rows[0]
        assert latest.trigger_source == "scheduler"
        assert latest.reason == "kis_scheduler_disabled"
        assert latest.result == "skipped"


def test_kr_scheduler_skips_when_global_scheduler_disabled():
    with SessionLocal() as db:
        from app.services.runtime_setting_service import RuntimeSettingService

        RuntimeSettingService().update_settings(
            db,
            {
                "scheduler_enabled": False,
                "kis_scheduler_enabled": True,
            },
        )
        initial_runs = db.query(TradeRunLog).count()

    scheduler_service._run_kr_scheduled_once("midday")

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
    assert body["US"]["next_slot_name"] in {"open_phase", "midday", "before_close"}
    assert body["US"]["next_slot_time_local"]
    assert body["US"]["last_scheduler_run_at"] is None
    assert body["US"]["last_scheduler_run_result"] is None
    assert body["US"]["last_scheduler_run_reason"] is None
    assert body["US"]["last_scheduler_run_id"] is None
    assert body["KR"]["enabled_for_scheduler"] is False
    assert body["KR"]["timezone"] == "Asia/Seoul"
    assert body["KR"]["slots"]
    assert body["KR"]["next_slot_name"] in {"open_phase", "midday", "before_close"}
    assert body["KR"]["next_slot_time_local"]
    assert body["KR"]["last_scheduler_run_at"] is None
    assert body["KR"]["last_scheduler_run_result"] is None
    assert body["KR"]["last_scheduler_run_reason"] is None
    assert body["KR"]["last_scheduler_run_id"] is None
    assert body["KR"]["last_scheduler_run_mode"] is None
    assert body["KR"]["last_scheduler_run_trigger_source"] is None
    assert body["KR"]["preview_only"] is True
    assert body["KR"]["kr_scheduler_any_enabled"] is False
    assert body["KR"]["kr_live_scheduler_enabled_effective"] is False
    assert body["KR"]["kr_dry_run_scheduler_enabled_effective"] is False
    assert body["KR"]["real_order_scheduler_enabled"] is False
    assert body["KR"]["real_orders_allowed"] is False


def test_scheduler_status_returns_last_scheduler_run_fields_when_logs_exist():
    with SessionLocal() as db:
        us_run = TradeRunLog(
            run_key="scheduler_us_midday",
            trigger_source="scheduler",
            symbol="WATCHLIST",
            mode="watchlist_trade_trigger",
            stage="done",
            result="skipped",
            reason="scheduler_disabled",
            request_payload=json.dumps(
                {
                    "provider": "alpaca",
                    "market": "US",
                    "scheduler_slot": "midday",
                }
            ),
            response_payload=json.dumps(
                {
                    "provider": "alpaca",
                    "market": "US",
                    "scheduler_slot": "midday",
                }
            ),
            created_at=datetime(2026, 1, 2, 3, 4, 5),
        )
        kr_run = TradeRunLog(
            run_key="kis_scheduler_live_midday",
            trigger_source="kis_scheduler_live",
            symbol="WATCHLIST",
            mode="kis_scheduler_live_once",
            stage="done",
            result="blocked",
            reason="kill_switch_enabled",
            request_payload=json.dumps(
                {
                    "provider": "kis",
                    "market": "KR",
                    "scheduler_slot": "midday",
                }
            ),
            response_payload=json.dumps(
                {
                    "provider": "kis",
                    "market": "KR",
                    "scheduler_slot": "midday",
                }
            ),
            created_at=datetime(2026, 1, 2, 4, 4, 5),
        )
        db.add_all([us_run, kr_run])
        db.commit()
        us_id = us_run.id
        kr_id = kr_run.id

    with TestClient(app) as client:
        response = client.get("/scheduler/status")

    assert response.status_code == 200
    body = response.json()
    assert body["US"]["last_scheduler_run_id"] == us_id
    assert body["US"]["last_scheduler_run_result"] == "skipped"
    assert body["US"]["last_scheduler_run_reason"] == "scheduler_disabled"
    assert body["KR"]["last_scheduler_run_id"] == kr_id
    assert body["KR"]["last_scheduler_run_result"] == "blocked"
    assert body["KR"]["last_scheduler_run_reason"] == "kill_switch_enabled"
    assert body["KR"]["last_scheduler_run_mode"] == "kis_scheduler_live_once"
    assert body["KR"]["last_scheduler_run_trigger_source"] == "kis_scheduler_live"


def test_scheduler_status_is_read_only_when_no_runtime_row_exists():
    with SessionLocal() as db:
        assert db.query(RuntimeSetting).count() == 0
        assert db.query(TradeRunLog).count() == 0

    with TestClient(app) as client:
        response = client.get("/scheduler/status")

    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.query(RuntimeSetting).count() == 0
        assert db.query(TradeRunLog).count() == 0


def test_kis_scheduler_preview_once_is_preview_only(monkeypatch):
    def fake_preview(self, include_gpt=True, gate_level=2, **kwargs):
        return {
            "market": "KR",
            "provider": "kis",
            "gate_level": gate_level,
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


def test_scheduler_status_uses_runtime_settings_for_kr_scheduler(monkeypatch):
    monkeypatch.setattr("app.routes.scheduler.get_settings", lambda: _settings(kis_enabled=True, kis_real_order_enabled=True))
    monkeypatch.setattr(
        "app.services.runtime_setting_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )

    with TestClient(app) as client:
        client.post(
            "/ops/scheduler/on",
        )
        client.put(
            "/ops/settings",
            json={
                "scheduler_enabled": True,
                "kis_scheduler_enabled": True,
                "kis_scheduler_dry_run": False,
                "kis_scheduler_allow_real_orders": True,
                "kis_scheduler_configured_allow_real_orders": True,
                "kis_scheduler_sell_enabled": True,
                "kis_scheduler_allow_limited_auto_sell": True,
            },
        )
        response = client.get("/scheduler/status")

    assert response.status_code == 200
    body = response.json()
    assert body["KR"]["kis_scheduler_enabled"] is True
    assert body["KR"]["kis_scheduler_dry_run"] is False
    assert body["KR"]["kis_scheduler_allow_real_orders"] is True
    assert body["KR"]["kis_scheduler_configured_allow_real_orders"] is True
    assert body["KR"]["kis_scheduler_sell_enabled"] is True
    assert body["KR"]["kis_scheduler_allow_limited_auto_sell"] is True
    assert body["KR"]["real_orders_allowed"] is True
    assert body["KR"]["real_order_scheduler_enabled"] is False
    assert body["KR"]["live_scheduler_ready"] is False
    assert body["KR"]["configured_live_order_prereqs_met"] is True
    assert body["runtime_scheduler_enabled"] is True


def test_scheduler_status_kr_enabled_for_scheduler_is_false_when_kis_scheduler_disabled(monkeypatch):
    monkeypatch.setattr("app.routes.scheduler.get_settings", lambda: _settings(kis_enabled=True, kis_real_order_enabled=True))
    monkeypatch.setattr(
        "app.services.runtime_setting_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    monkeypatch.setattr(
        "app.routes.scheduler.MarketSessionService.list_sessions",
        lambda self: [
            {
                "market": "US",
                "enabled_for_scheduler": True,
                "timezone": "America/New_York",
                "entry_slots": [],
            },
            {
                "market": "KR",
                "enabled_for_scheduler": True,
                "timezone": "Asia/Seoul",
                "entry_slots": [],
                "enabled_for_trading": True,
            },
        ],
    )

    with TestClient(app) as client:
        client.post("/ops/scheduler/on")
        client.put(
            "/ops/settings",
            json={
                "scheduler_enabled": True,
                "kis_scheduler_enabled": False,
                "kis_scheduler_dry_run": False,
                "kis_scheduler_allow_real_orders": False,
                "kis_scheduler_configured_allow_real_orders": False,
            },
        )
        response = client.get("/scheduler/status")

    assert response.status_code == 200
    body = response.json()
    assert body["KR"]["kis_scheduler_enabled"] is False
    assert body["KR"]["enabled_for_scheduler"] is False
    assert "kis_scheduler_disabled" in body["KR"]["enabled_for_scheduler_block_reasons"]


def test_scheduler_status_kr_enabled_for_scheduler_is_true_in_live_state(monkeypatch):
    monkeypatch.setattr("app.routes.scheduler.get_settings", lambda: _settings(kis_enabled=True, kis_real_order_enabled=True))
    monkeypatch.setattr(
        "app.services.runtime_setting_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    monkeypatch.setattr(
        "app.routes.scheduler.MarketSessionService.list_sessions",
        lambda self: [
            {
                "market": "US",
                "enabled_for_scheduler": True,
                "timezone": "America/New_York",
                "entry_slots": [],
            },
            {
                "market": "KR",
                "enabled_for_scheduler": True,
                "timezone": "Asia/Seoul",
                "entry_slots": [],
                "enabled_for_trading": True,
            },
        ],
    )

    with TestClient(app) as client:
        client.post("/ops/scheduler/on")
        client.put(
            "/ops/settings",
            json={
                "scheduler_enabled": True,
                "kis_scheduler_enabled": True,
                "kis_scheduler_dry_run": False,
                "kis_scheduler_allow_real_orders": True,
                "kis_scheduler_configured_allow_real_orders": True,
                "kis_scheduler_sell_enabled": True,
                "kis_scheduler_live_enabled": True,
                "kis_scheduler_allow_limited_auto_sell": True,
            },
        )
        response = client.get("/scheduler/status")

    assert response.status_code == 200
    body = response.json()
    assert body["KR"]["kis_scheduler_enabled"] is True
    assert body["KR"]["kis_scheduler_dry_run"] is False
    assert body["KR"]["kis_scheduler_allow_real_orders"] is True
    assert body["KR"]["kis_scheduler_configured_allow_real_orders"] is True
    assert body["KR"]["kis_scheduler_sell_enabled"] is True
    assert body["KR"]["live_scheduler_ready"] is True
    assert body["KR"]["real_order_scheduler_enabled"] is True
    assert body["KR"]["enabled_for_scheduler"] is True
    assert body["KR"]["kr_live_scheduler_enabled_effective"] is True
    assert body["KR"]["kr_dry_run_scheduler_enabled_effective"] is False
    assert body["KR"]["enabled_for_scheduler_block_reasons"] == []


def test_scheduler_status_kr_enabled_for_scheduler_is_true_in_dry_run_validation_state(monkeypatch):
    monkeypatch.setattr("app.routes.scheduler.get_settings", lambda: _settings(kis_enabled=True, kis_real_order_enabled=True))
    monkeypatch.setattr(
        "app.services.runtime_setting_service.get_settings",
        lambda: _settings(kis_enabled=True, kis_real_order_enabled=True),
    )
    monkeypatch.setattr(
        "app.routes.scheduler.MarketSessionService.list_sessions",
        lambda self: [
            {
                "market": "US",
                "enabled_for_scheduler": True,
                "timezone": "America/New_York",
                "entry_slots": [],
            },
            {
                "market": "KR",
                "enabled_for_scheduler": True,
                "timezone": "Asia/Seoul",
                "entry_slots": [],
                "enabled_for_trading": True,
            },
        ],
    )

    with TestClient(app) as client:
        client.post("/ops/scheduler/on")
        client.put(
            "/ops/settings",
            json={
                "scheduler_enabled": True,
                "kis_scheduler_enabled": True,
                "kis_scheduler_dry_run": True,
                "kis_scheduler_allow_real_orders": False,
                "kis_scheduler_configured_allow_real_orders": False,
                "kis_scheduler_sell_enabled": False,
                "kis_scheduler_live_enabled": False,
            },
        )
        response = client.get("/scheduler/status")

    assert response.status_code == 200
    body = response.json()
    assert body["KR"]["kis_scheduler_enabled"] is True
    assert body["KR"]["kis_scheduler_dry_run"] is True
    assert body["KR"]["kis_scheduler_allow_real_orders"] is False
    assert body["KR"]["kis_scheduler_configured_allow_real_orders"] is False
    assert body["KR"]["live_scheduler_ready"] is False
    assert body["KR"]["real_order_scheduler_enabled"] is False
    assert body["KR"]["enabled_for_scheduler"] is True
    assert body["KR"]["kr_live_scheduler_enabled_effective"] is False
    assert body["KR"]["kr_dry_run_scheduler_enabled_effective"] is True
    assert body["KR"]["enabled_for_scheduler_block_reasons"] == []


def test_scheduler_service_uses_runtime_settings_for_kis_live_gate(monkeypatch):
    with SessionLocal() as db:
        from app.services.runtime_setting_service import RuntimeSettingService

        RuntimeSettingService().update_settings(
            db,
            {
                "scheduler_enabled": True,
                "kis_scheduler_enabled": True,
                "kis_scheduler_dry_run": False,
                "kis_scheduler_allow_real_orders": True,
                "kis_scheduler_configured_allow_real_orders": True,
                "kis_scheduler_live_enabled": True,
                "kis_scheduler_allow_limited_auto_sell": True,
            },
        )

    calls = []

    class FakeSimulationService:
        def __init__(self, *args, **kwargs):
            pass

        def run_once(self, db, **kwargs):
            calls.append("simulation")
            return {}

    class FakeLiveService:
        def __init__(self, *args, **kwargs):
            pass

        def run_once(self, db, **kwargs):
            calls.append("live")
            return {}

    monkeypatch.setattr(
        "app.services.scheduler_service.KisSchedulerSimulationService",
        lambda *args, **kwargs: FakeSimulationService(),
    )
    monkeypatch.setattr(
        "app.services.scheduler_service.KisSchedulerLiveService",
        lambda *args, **kwargs: FakeLiveService(),
    )
    monkeypatch.setattr(
        "app.services.scheduler_service.KisClient",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.scheduler_service.KisAuthManager",
        lambda *args, **kwargs: None,
    )

    scheduler_service._run_kr_scheduled_once("midday")

    assert "simulation" in calls
    assert "live" in calls


def test_us_scheduler_does_not_run_kis_services(monkeypatch):
    calls = []

    class FakeWatchlistRunService:
        def run_once(self, db, **kwargs):
            calls.append("watchlist")

    monkeypatch.setattr(
        "app.services.scheduler_service.KisSchedulerSimulationService",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("US scheduler must not call KIS simulation")),
    )
    monkeypatch.setattr(
        "app.services.scheduler_service.KisSchedulerLiveService",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("US scheduler must not call KIS live service")),
    )
    scheduler_service.watchlist_run_service = FakeWatchlistRunService()

    with SessionLocal() as db:
        from app.services.runtime_setting_service import RuntimeSettingService

        RuntimeSettingService().update_settings(db, {"scheduler_enabled": True})

    scheduler_service._run_us_scheduled_once("midday")

    assert calls == ["watchlist"]
