from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, TradeRunLog
from app.main import app
from app.routes.automation import get_portfolio_orchestrator_service
from app.services.agent_chat_tool_registry import AgentChatToolRegistry
from app.services.portfolio_orchestrator_service import PortfolioOrchestratorService
from app.services.runtime_setting_service import RuntimeSettingService


class FakeRuntimeSettings:
    def __init__(self, **overrides: Any) -> None:
        values = {
            "portfolio_orchestrator_enabled": True,
            "portfolio_orchestrator_allow_live_orders": True,
            "portfolio_orchestrator_positions_first": True,
            "portfolio_orchestrator_max_actions_per_run": 1,
            "portfolio_orchestrator_require_production_ready": True,
            "portfolio_orchestrator_skip_buy_if_sell_candidate": True,
            "portfolio_orchestrator_skip_buy_if_sync_required": True,
            "portfolio_orchestrator_skip_buy_if_exit_critical": True,
            "dry_run": False,
            "kill_switch": False,
            "max_trades_per_day": 10,
        }
        values.update(overrides)
        self.values = values
        self.settings = SimpleNamespace(
            kis_enabled=True,
            kis_real_order_enabled=True,
        )

    def get_settings_read_only(self, db):
        return dict(self.values)


class FakeReadiness:
    def __init__(self, status: str = "ready") -> None:
        self.status = status
        self.calls = 0
        self.kwargs: list[dict[str, Any]] = []

    def readiness(self, db, **kwargs):
        self.calls += 1
        self.kwargs.append(dict(kwargs))
        return {"overall_status": self.status}


class FakePositionManagement:
    def __init__(self, result: dict[str, Any] | None = None, events=None) -> None:
        self.result = result or position_result()
        self.events = events if events is not None else []
        self.calls = 0
        self.requests: list[dict[str, Any]] = []

    def run_once(self, db, request, *, require_enabled=False, now=None):
        self.calls += 1
        self.events.append("positions")
        self.requests.append(dict(request))
        return dict(self.result)


class FakePhase:
    def __init__(
        self,
        name: str,
        result: dict[str, Any],
        events=None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.result = result
        self.events = events if events is not None else []
        self.error = error
        self.calls = 0
        self.requests: list[dict[str, Any]] = []

    def run_once(self, db, request, *, now=None):
        self.calls += 1
        self.events.append(self.name)
        self.requests.append(dict(request))
        if self.error is not None:
            raise self.error
        return dict(self.result)


def position_result(**overrides: Any) -> dict[str, Any]:
    result = {
        "result_status": "completed",
        "primary_reason": "no_exit_candidates",
        "dry_run_only": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "exit_candidate_count": 0,
        "critical_candidate_count": 0,
        "blocked_preflight_count": 0,
        "sync_required_count": 0,
        "duplicate_sell_conflict_count": 0,
        "candidates": [],
        "risk_flags": ["positions_first"],
        "gating_notes": ["position management ran"],
    }
    result.update(overrides)
    return result


def critical_position_result() -> dict[str, Any]:
    candidate = {
        "candidate_id": "exit:005930:stop_loss",
        "symbol": "005930",
        "candidate_type": "stop_loss",
        "severity": "critical",
        "status": "active",
        "can_run_sell_preflight": True,
        "sync_required": False,
        "open_sell_order_conflict": False,
    }
    return position_result(
        primary_reason="critical_exit_candidate",
        exit_candidate_count=1,
        critical_candidate_count=1,
        candidates=[candidate],
    )


def phase_result(status: str = "skipped", **overrides: Any) -> dict[str, Any]:
    result = {
        "result_status": status,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "risk_flags": [],
        "gating_notes": [],
        "primary_block_reason": None,
        "next_safe_action": "continue_monitoring",
    }
    result.update(overrides)
    return result


def make_service(
    *,
    runtime: FakeRuntimeSettings | None = None,
    readiness: FakeReadiness | None = None,
    positions: FakePositionManagement | None = None,
    sell: FakePhase | None = None,
    buy: FakePhase | None = None,
) -> PortfolioOrchestratorService:
    return PortfolioOrchestratorService(
        runtime_settings=runtime or FakeRuntimeSettings(),
        readiness_service=readiness or FakeReadiness(),
        position_management_service=positions or FakePositionManagement(),
        auto_sell_service=sell or FakePhase("sell", phase_result()),
        auto_buy_service=buy or FakePhase("buy", phase_result()),
    )


def test_orchestrator_is_disabled_by_default(db_session):
    service = PortfolioOrchestratorService(runtime_settings=RuntimeSettingService())

    result = service.run_once(db_session)

    assert result["result_status"] == "disabled"
    assert result["orchestrator_enabled"] is False
    assert result["mode"] == "dry_run_monitoring"
    assert result["action_taken"] == "none"
    assert db_session.query(TradeRunLog).filter_by(mode="portfolio_orchestrator").count() == 1


def test_kill_switch_blocks_before_position_management(db_session):
    positions = FakePositionManagement()
    result = make_service(
        runtime=FakeRuntimeSettings(kill_switch=True),
        positions=positions,
    ).run_once(db_session)

    assert result["result_status"] == "blocked"
    assert result["primary_block_reason"] == "kill_switch_enabled"
    assert positions.calls == 0


def test_production_readiness_blocked_stops_cycle(db_session):
    positions = FakePositionManagement()
    result = make_service(
        readiness=FakeReadiness("blocked"),
        positions=positions,
    ).run_once(db_session)

    assert result["primary_block_reason"] == "production_readiness_not_ready"
    assert positions.calls == 0


def test_monitoring_allows_only_live_execution_readiness_blockers(db_session):
    class MonitoringReadiness(FakeReadiness):
        def readiness(self, db, **kwargs):
            self.calls += 1
            self.kwargs.append(dict(kwargs))
            return {
                "overall_status": "blocked",
                "checklist": [
                    {
                        "key": "dry_run_blocks_live_submit",
                        "status": "warn",
                        "blocking": True,
                    },
                    {
                        "key": "kis_real_order_enabled_for_live",
                        "status": "fail",
                        "blocking": True,
                    },
                    {
                        "key": "guarded_live_buy_ready",
                        "status": "fail",
                        "blocking": True,
                    },
                    {
                        "key": "guarded_live_sell_ready",
                        "status": "fail",
                        "blocking": True,
                    },
                ],
            }

    positions = FakePositionManagement()
    result = make_service(
        readiness=MonitoringReadiness("blocked"),
        positions=positions,
    ).run_once(db_session)

    assert result["result_status"] == "dry_run_completed"
    assert positions.calls == 1


def test_live_readiness_includes_recent_health(db_session):
    readiness = FakeReadiness()

    make_service(readiness=readiness).run_once(
        db_session,
        {"mode": "live_phase1_controlled"},
    )

    assert readiness.kwargs[0]["include_recent"] is True


def test_global_pending_or_sync_order_blocks_all_phases(db_session):
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="buy",
            order_type="market",
            internal_status="SYNC_FAILED",
        )
    )
    db_session.commit()
    positions = FakePositionManagement()
    sell = FakePhase("sell", phase_result())
    buy = FakePhase("buy", phase_result())

    result = make_service(positions=positions, sell=sell, buy=buy).run_once(db_session)

    assert result["result_status"] == "blocked"
    assert result["sync_required_count"] == 1
    assert result["pending_order_conflict_count"] == 1
    assert positions.calls == sell.calls == buy.calls == 0


def test_legacy_kis_order_without_market_still_blocks(db_session):
    db_session.add(
        OrderLog(
            broker="kis",
            market=None,
            symbol="005930",
            side="buy",
            order_type="market",
            internal_status="PENDING",
        )
    )
    db_session.commit()

    result = make_service().run_once(db_session)

    assert result["primary_block_reason"] == "pending_order_conflict_exists"


def test_position_management_always_precedes_auto_buy(db_session):
    events: list[str] = []
    positions = FakePositionManagement(events=events)
    buy = FakePhase(
        "buy",
        phase_result(
            "submitted",
            real_order_submitted=True,
            broker_submit_called=True,
            selected_symbol="005930",
            selected_promotion_id=9,
            order_id=12,
        ),
        events=events,
    )

    result = make_service(positions=positions, buy=buy).run_once(
        db_session,
        {"mode": "live_phase1_controlled"},
    )

    assert events == ["positions", "buy"]
    assert result["result_status"] == "buy_submitted"
    assert result["action_taken"] == "auto_buy_phase1"


def test_critical_exit_considers_sell_before_buy_and_sell_submit_stops(db_session):
    events: list[str] = []
    positions = FakePositionManagement(critical_position_result(), events=events)
    sell = FakePhase(
        "sell",
        phase_result(
            "submitted",
            real_order_submitted=True,
            broker_submit_called=True,
            selected_symbol="005930",
            selected_candidate_id="exit:005930:stop_loss",
            order_id=33,
            broker_order_id="SELL-33",
        ),
        events=events,
    )
    buy = FakePhase("buy", phase_result(), events=events)

    result = make_service(positions=positions, sell=sell, buy=buy).run_once(
        db_session,
        {"mode": "live_phase1_controlled"},
    )

    assert events == ["positions", "sell"]
    assert buy.calls == 0
    assert result["result_status"] == "sell_submitted"
    assert result["skipped_buy_reason"] == "auto_sell_phase1_submitted"


def test_critical_sell_block_skips_auto_buy(db_session):
    events: list[str] = []
    positions = FakePositionManagement(critical_position_result(), events=events)
    sell = FakePhase(
        "sell",
        phase_result(
            "disabled",
            primary_block_reason="auto_sell_live_phase1_disabled",
        ),
        events=events,
    )
    buy = FakePhase("buy", phase_result(), events=events)

    result = make_service(positions=positions, sell=sell, buy=buy).run_once(
        db_session,
        {"mode": "live_phase1_controlled"},
    )

    assert events == ["positions", "sell"]
    assert buy.calls == 0
    assert result["result_status"] == "blocked"
    assert result["skipped_buy_reason"] == "critical_exit_candidate_unresolved"


def test_position_preflight_blocker_prevents_live_phase_calls(db_session):
    sell = FakePhase("sell", phase_result())
    buy = FakePhase("buy", phase_result())
    result = make_service(
        positions=FakePositionManagement(
            position_result(blocked_preflight_count=1)
        ),
        sell=sell,
        buy=buy,
    ).run_once(db_session, {"mode": "live_phase1_controlled"})

    assert result["primary_block_reason"] == "position_management_preflight_blocked"
    assert sell.calls == buy.calls == 0


def test_malformed_position_result_fails_closed(db_session):
    buy = FakePhase("buy", phase_result())
    result = make_service(
        positions=FakePositionManagement(
            position_result(real_order_submitted=True)
        ),
        buy=buy,
    ).run_once(db_session, {"mode": "live_phase1_controlled"})

    assert result["result_status"] == "error"
    assert result["primary_block_reason"] == "position_management_safety_invariant_failed"
    assert buy.calls == 0


def test_executable_sell_candidate_is_selected_before_manual_candidate(db_session):
    positions = FakePositionManagement(
        position_result(
            exit_candidate_count=2,
            candidates=[
                {
                    "candidate_id": "a-manual",
                    "symbol": "000001",
                    "candidate_type": "manual_review",
                    "severity": "warning",
                    "status": "active",
                    "can_run_sell_preflight": False,
                },
                {
                    "candidate_id": "z-take-profit",
                    "symbol": "005930",
                    "candidate_type": "take_profit",
                    "severity": "warning",
                    "status": "active",
                    "can_run_sell_preflight": True,
                    "sync_required": False,
                    "open_sell_order_conflict": False,
                },
            ],
        )
    )
    sell = FakePhase("sell", phase_result("skipped"))

    make_service(positions=positions, sell=sell).run_once(
        db_session,
        {"mode": "live_phase1_controlled"},
    )

    assert sell.requests[0]["candidate_id"] == "z-take-profit"


def test_no_sell_candidate_allows_one_auto_buy_phase_call(db_session):
    buy = FakePhase("buy", phase_result("skipped"))

    result = make_service(buy=buy).run_once(
        db_session,
        {"mode": "live_phase1_controlled"},
    )

    assert buy.calls == 1
    assert buy.requests[0]["trigger_source"] == "scheduler_phase1"
    assert "confirm_phase1_run" not in buy.requests[0]
    assert result["result_status"] == "completed_no_action"


def test_ambiguous_sell_broker_result_is_terminal(db_session):
    sell = FakePhase(
        "sell",
        phase_result(
            "pending_sync",
            broker_submit_called=True,
            real_order_submitted=False,
            primary_block_reason="broker_result_unknown",
        ),
    )
    buy = FakePhase("buy", phase_result())

    result = make_service(
        positions=FakePositionManagement(critical_position_result()),
        sell=sell,
        buy=buy,
    ).run_once(db_session, {"mode": "live_phase1_controlled"})

    assert sell.calls == 1
    assert buy.calls == 0
    assert result["result_status"] == "blocked"
    assert result["action_taken"] == "none"
    assert result["real_order_submitted"] is False


def test_inconsistent_sell_submission_boolean_still_stops_buy(db_session):
    sell = FakePhase(
        "sell",
        phase_result(
            "skipped",
            real_order_submitted=True,
            broker_submit_called=False,
            selected_symbol="005930",
        ),
    )
    buy = FakePhase("buy", phase_result())
    warning_candidate = {
        "candidate_id": "warning-exit",
        "symbol": "005930",
        "candidate_type": "take_profit",
        "severity": "warning",
        "status": "active",
        "can_run_sell_preflight": True,
    }

    result = make_service(
        runtime=FakeRuntimeSettings(
            portfolio_orchestrator_skip_buy_if_sell_candidate=False
        ),
        positions=FakePositionManagement(
            position_result(exit_candidate_count=1, candidates=[warning_candidate])
        ),
        sell=sell,
        buy=buy,
    ).run_once(db_session, {"mode": "live_phase1_controlled"})

    assert result["result_status"] == "sell_submitted"
    assert result["action_taken"] == "auto_sell_phase1"
    assert buy.calls == 0


def test_manual_or_unknown_sell_result_cannot_fall_through_to_buy(db_session):
    warning_candidate = {
        "candidate_id": "warning-exit",
        "symbol": "005930",
        "candidate_type": "take_profit",
        "severity": "warning",
        "status": "active",
        "can_run_sell_preflight": True,
    }
    positions = FakePositionManagement(
        position_result(exit_candidate_count=1, candidates=[warning_candidate])
    )
    for nested_result in (
        phase_result("disabled", manual_submit_called=True),
        phase_result("unexpected_phase_state"),
    ):
        buy = FakePhase("buy", phase_result())
        result = make_service(
            runtime=FakeRuntimeSettings(
                portfolio_orchestrator_skip_buy_if_sell_candidate=False
            ),
            positions=positions,
            sell=FakePhase("sell", nested_result),
            buy=buy,
        ).run_once(db_session, {"mode": "live_phase1_controlled"})

        assert result["result_status"] in {"blocked", "error"}
        assert result["action_taken"] == "none"
        assert buy.calls == 0


def test_daily_limit_blocks_before_position_or_phase(db_session):
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="buy",
            order_type="market",
            internal_status="FILLED",
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    db_session.commit()
    positions = FakePositionManagement()

    result = make_service(
        runtime=FakeRuntimeSettings(max_trades_per_day=1),
        positions=positions,
    ).run_once(db_session)

    assert result["primary_block_reason"] == "daily_total_trade_limit_reached"
    assert result["daily_trade_limit_used"] == 1
    assert result["daily_trade_limit_remaining"] == 0
    assert positions.calls == 0


def test_phase_exception_is_not_repeated(db_session):
    buy = FakePhase("buy", phase_result(), error=RuntimeError("phase failed"))

    result = make_service(buy=buy).run_once(
        db_session,
        {"mode": "live_phase1_controlled"},
    )

    assert result["result_status"] == "error"
    assert buy.calls == 1


def test_service_source_has_no_direct_broker_execution_methods():
    source = inspect.getsource(PortfolioOrchestratorService)
    forbidden = (
        "submit_market_buy",
        "submit_market_sell",
        "submit_order",
        "submit_domestic_cash_order",
        "submit_manual",
        "KisManualOrderService",
    )
    assert all(name not in source for name in forbidden)


def test_request_rejects_unsafe_extra_fields_and_latest_has_stable_no_run_shape(
    db_session,
):
    service = make_service(
        runtime=FakeRuntimeSettings(portfolio_orchestrator_enabled=False)
    )

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_portfolio_orchestrator_service] = lambda: service
    client = TestClient(app)
    try:
        latest = client.get("/automation/portfolio/latest")
        assert latest.status_code == 200
        assert latest.json()["run_id"] is None
        assert latest.json()["result_status"] == "disabled"
        assert (
            client.get(
                "/automation/portfolio/latest",
                params={"provider": "alpaca", "market": "US"},
            ).status_code
            == 422
        )

        for field in (
            "confirm_live",
            "force_run",
            "skip_gates",
            "disable_kill_switch",
            "dry_run",
        ):
            response = client.post(
                "/automation/portfolio/run-once",
                json={field: True},
            )
            assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_latest_endpoint_real_dependency_graph_is_safe_when_disabled(db_session):
    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        response = client.get("/automation/portfolio/latest")
        assert response.status_code == 200
        assert response.json()["result_status"] == "disabled"
        assert db_session.query(OrderLog).count() == 0
    finally:
        app.dependency_overrides.clear()


def test_runtime_updates_force_hard_orchestrator_invariants(db_session):
    db_session.add(RuntimeSetting(dry_run=True, kill_switch=False))
    db_session.commit()
    service = RuntimeSettingService()

    result = service.update_settings(
        db_session,
        {
            "portfolio_orchestrator_enabled": True,
            "portfolio_orchestrator_positions_first": False,
            "portfolio_orchestrator_max_actions_per_run": 7,
            "portfolio_orchestrator_require_production_ready": False,
            "portfolio_orchestrator_skip_buy_if_sync_required": False,
            "portfolio_orchestrator_skip_buy_if_exit_critical": False,
        },
    )

    assert result["portfolio_orchestrator_enabled"] is True
    assert result["portfolio_orchestrator_positions_first"] is True
    assert result["portfolio_orchestrator_max_actions_per_run"] == 1
    assert result["portfolio_orchestrator_require_production_ready"] is True
    assert result["portfolio_orchestrator_skip_buy_if_sync_required"] is True
    assert result["portfolio_orchestrator_skip_buy_if_exit_critical"] is True
    assert result["dry_run"] is True
    assert result["kill_switch"] is False


def test_safe_preset_disables_orchestrator_switches(db_session):
    service = RuntimeSettingService()
    service.update_settings(
        db_session,
        {
            "portfolio_orchestrator_enabled": True,
            "portfolio_orchestrator_allow_live_orders": True,
        },
    )

    result = service.apply_preset(db_session, preset="safe_mode")

    assert result["settings"]["portfolio_orchestrator_enabled"] is False
    assert result["settings"]["portfolio_orchestrator_allow_live_orders"] is False


def test_no_agent_chat_tool_can_execute_portfolio_orchestrator():
    registry = AgentChatToolRegistry()
    assert "portfolio_orchestrator_run" not in registry.tool_names()
    assert registry.can_auto_execute("portfolio_orchestrator_run") is False
