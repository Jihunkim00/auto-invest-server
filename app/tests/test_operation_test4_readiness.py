from __future__ import annotations

from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.db.models import OperationTest4Cycle, OrderLog, RuntimeSetting, SignalLog, TradeRunLog
from app.db.database import get_db
from app.main import app
from app.services.operation_test4_service import ENABLE_CONFIRMATION
from app.services.runtime_setting_service import RuntimeSettingService
from app.tests.test_operation_test4_entry import (
    NOW,
    make_service,
    arm_for_entry,
)


def test_preflight_is_read_only_and_returns_required_shape(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)

    result = service.preflight_once(db_session, now=NOW)

    assert result["safety"] == {
        "read_only": True,
        "preflight_only": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
    }
    assert result["provider"] == "kis"
    assert result["market"] == "KR"
    assert "account" in result
    assert "watchlist" in result
    assert "candidate" in result
    assert "checks" in result
    assert db_session.query(OperationTest4Cycle).count() == 0
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(SignalLog).count() == 0
    assert db_session.query(TradeRunLog).count() == 0
    assert db_session.query(RuntimeSetting).count() == 0


def test_ready_requires_live_gates_and_candidate_score(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)

    initial = service.readiness(db_session, now=NOW)
    assert initial["entry_ready"] is False
    assert initial["status"] == "blocked"

    arm_for_entry(db_session, service)
    ready = service.readiness(db_session, now=NOW)

    assert ready["status"] == "ready_for_preflight"
    assert ready["live_ready"] is False
    assert ready["entry_ready"] is False
    assert ready["entry_base_ready"] is True
    assert ready["candidate_required"] is True
    assert ready["exit_ready"] is False
    assert ready["watchlist"]["configured_count"] == 50
    assert ready["watchlist"]["eligible_count"] == 50
    assert ready["candidate"]["symbol"] is None
    assert ready["orderable_cash_status"] == "ok"


def test_readiness_skips_candidate_provider_and_preflight_runs_it(db_session, tmp_path):
    calls = {"candidate": 0, "possible": 0}

    def candidate(**kwargs):
        calls["candidate"] += 1
        return {
            "final_ranked_candidates": [
                {
                    "symbol": "001450",
                    "current_price": 38_650,
                    "final_buy_score": 90,
                    "block_reasons": [],
                    "risk_flags": [],
                }
            ],
            "watchlist": [],
        }

    def possible(**kwargs):
        calls["possible"] += 1
        return {
            "raw_status": "ok",
            "symbol": kwargs["symbol"],
            "orderable_cash": 996_274,
            "orderable_quantity": 25,
            "queried_at": NOW.isoformat(),
            "error": None,
        }

    service, _, _ = make_service(
        tmp_path,
        candidate=candidate,
        possible_order=possible,
    )
    arm_for_entry(db_session, service)

    readiness = service.readiness(db_session, now=NOW)
    preflight = service.preflight_once(db_session, now=NOW)

    assert readiness["candidate_required"] is True
    assert readiness["heavy_analysis"]["performed"] is False
    assert calls == {"candidate": 1, "possible": 1}
    assert preflight["candidate"]["symbol"] == "001450"
    assert preflight["possible_order"]["orderable_cash"] == 996_274
    assert preflight["sizing"]["quantity"] == 3
    assert preflight["real_order_submitted"] is False


def test_readiness_fails_closed_when_orderable_cash_is_missing(db_session, tmp_path):
    service, _, state = make_service(tmp_path)
    state["orderable_cash"] = None
    state["warnings"] = ["orderable_cash_unavailable"]
    arm_for_entry(db_session, service)

    result = service.readiness(db_session, now=NOW)

    assert result["entry_ready"] is False
    assert result["orderable_cash_status"] == "candidate_required"
    assert result["candidate_required"] is True


def test_position_open_blocks_new_entry_readiness(db_session, tmp_path):
    service, _, state = make_service(tmp_path)
    arm_for_entry(db_session, service)
    state["positions"] = [{"symbol": "005930", "qty": 1, "current_price": 20_000}]

    result = service.readiness(db_session, now=NOW)

    assert result["entry_ready"] is False
    assert "position_exists" in result["blocking_reasons"]


def test_stale_snapshot_blocks_readiness(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)
    snapshot = service.watchlist_path.read_text(encoding="utf-8")
    current_date = NOW.astimezone(ZoneInfo("Asia/Seoul")).date()
    stale_date = current_date.replace(day=current_date.day - 1)
    snapshot = snapshot.replace(str(current_date), str(stale_date))
    service.watchlist_path.write_text(snapshot, encoding="utf-8")
    arm_for_entry(db_session, service)

    result = service.readiness(db_session, now=NOW)

    assert result["entry_ready"] is False
    assert "test4_watchlist_stale" in result["blocking_reasons"]


def test_snapshot_price_cap_metadata_mismatch_blocks_readiness(db_session, tmp_path):
    service, _, _ = make_service(tmp_path)
    snapshot = service.watchlist_path.read_text(encoding="utf-8").replace(
        "price_cap_krw: 1000000",
        "price_cap_krw: 999999",
    )
    service.watchlist_path.write_text(snapshot, encoding="utf-8")
    arm_for_entry(db_session, service)

    result = service.readiness(db_session, now=NOW)

    assert result["entry_ready"] is False
    assert "test4_watchlist_price_cap_mismatch" in result["blocking_reasons"]


def test_rebuild_snapshot_is_read_only_and_returns_reserve_stats(db_session, tmp_path, monkeypatch):
    service, _, _ = make_service(tmp_path)
    calls = []

    def fake_builder(**kwargs):
        calls.append(kwargs)
        return {
            "source_universe_count": 80,
            "quote_checked_count": 80,
            "eligible_count": 60,
            "selected_count": 50,
            "reserve_eligible_count": 10,
            "excluded_count": 20,
            "exclusion_reasons": {"price_cap_exceeded": 20},
            "selected_symbols": [f"{index:06d}" for index in range(1, 51)],
        }

    monkeypatch.setattr("app.services.operation_test4_service.build_operation_test4_watchlist", fake_builder)

    result = service.rebuild_watchlist(db_session, now=NOW)

    assert result["status"] == "completed"
    assert result["read_only"] is True
    assert result["selected_count"] == 50
    assert result["reserve_eligible_count"] == 10
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert len(calls) == 1
    assert db_session.query(OperationTest4Cycle).count() == 0
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(SignalLog).count() == 0
    assert db_session.query(TradeRunLog).count() == 0
    assert db_session.query(RuntimeSetting).count() == 0


def test_enable_live_requires_exact_confirmation_and_does_not_change_global_guards(
    db_session,
    tmp_path,
):
    service, _, _ = make_service(tmp_path)
    runtime = RuntimeSettingService()
    runtime.update_settings(
        db_session,
        {"dry_run": True, "kill_switch": True},
    )

    blocked = service.enable_live(
        db_session,
        confirm_live=True,
        confirmation="wrong",
        now=NOW,
    )
    enabled = service.enable_live(
        db_session,
        confirm_live=True,
        confirmation=ENABLE_CONFIRMATION,
        now=NOW,
    )
    settings = runtime.get_settings(db_session)

    assert blocked["status"] == "blocked"
    assert enabled["status"] == "live_enabled"
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True
    assert settings["operation_test4_allow_real_entry"] is True
    assert settings["operation_test4_allow_real_exit"] is True


def test_ops_settings_cannot_directly_enable_test4_real_gates(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).put(
            "/ops/settings",
            json={"operation_test4_allow_real_entry": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409