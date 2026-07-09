from __future__ import annotations

import json
from datetime import UTC, datetime

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, TradeRunLog
from app.services.agent_chat_tool_registry import AgentChatToolRegistry
from app.services.auto_buy_live_phase1_service import AutoBuyLivePhase1Service
from app.services.strategy_auto_buy_promotion_service import (
    StrategyAutoBuyPromotionService,
)
from app.tests.test_strategy_live_auto_buy_service import (
    FakeBroker,
    FakeMarketSessions,
    FakeRuntimeSettings,
    add_dry_run,
    add_promotion_for_dry_run,
    live_service,
)


class FakeReadiness:
    def __init__(self, status: str = "ready"):
        self.status = status

    def readiness(self, db, **kwargs):
        return {
            "overall_status": self.status,
            "blocking_reasons": []
            if self.status == "ready"
            else ["production_not_ready"],
        }


class FakeAutoExitCandidates:
    def __init__(self, *, critical_count: int = 0):
        self.critical_count = critical_count

    def candidates(self, db, **kwargs):
        return {
            "summary": {
                "critical_count": self.critical_count,
                "sync_required_count": 0,
                "duplicate_sell_block_count": 0,
            },
            "candidates": [],
            "safety_flags": ["read_only"],
        }


class FakePositionManagement:
    def __init__(self, *, blockers: int = 0):
        self.blockers = blockers

    def latest(self, db, **kwargs):
        return {
            "result_status": "completed",
            "primary_reason": "position_management_dry_run_completed",
            "critical_candidate_count": self.blockers,
            "blocked_preflight_count": 0,
        }


class RaisingBroker(FakeBroker):
    def submit_market_buy(self, *, symbol: str, qty: int):
        self.calls.append({"symbol": symbol, "qty": qty})
        raise RuntimeError("ambiguous broker response")


def phase1_service(
    *,
    runtime: FakeRuntimeSettings | None = None,
    readiness: FakeReadiness | None = None,
    broker: FakeBroker | None = None,
    market_sessions: FakeMarketSessions | None = None,
    auto_exit_candidates: FakeAutoExitCandidates | None = None,
    position_management: FakePositionManagement | None = None,
) -> AutoBuyLivePhase1Service:
    runtime = runtime or phase1_runtime()
    guarded = live_service(
        runtime=runtime,
        broker=broker or FakeBroker(),
        market_sessions=market_sessions or FakeMarketSessions(),
    )
    return AutoBuyLivePhase1Service(
        runtime_settings=runtime,
        guarded_buy_service=guarded,
        readiness_service=readiness or FakeReadiness(),
        auto_exit_candidates=auto_exit_candidates or FakeAutoExitCandidates(),
        position_management_service=position_management or FakePositionManagement(),
    )


def phase1_runtime(**overrides) -> FakeRuntimeSettings:
    values = {
        "dry_run": False,
        "kill_switch": False,
        "strategy_live_auto_buy_enabled": True,
        "strategy_live_auto_buy_scheduler_enabled": False,
        "strategy_live_auto_buy_max_orders_per_day": 1,
        "strategy_live_auto_buy_max_notional_krw": 50_000,
        "auto_buy_live_phase1_enabled": True,
        "auto_buy_live_phase1_allow_real_orders": True,
        "auto_buy_live_phase1_max_orders_per_day": 1,
        "auto_buy_live_phase1_max_notional_krw": 50_000,
        "auto_buy_live_phase1_require_production_ready": True,
    }
    values.update(overrides)
    return FakeRuntimeSettings(**values)


def add_phase1_promotion(db_session, *, symbol: str = "005930"):
    dry_run = add_dry_run(db_session, symbol=symbol)
    promotion = add_promotion_for_dry_run(db_session, dry_run)
    return dry_run, promotion


def test_run_once_disabled_by_default_blocks_before_submit(db_session):
    add_phase1_promotion(db_session)
    broker = FakeBroker()

    result = phase1_service(
        runtime=phase1_runtime(auto_buy_live_phase1_enabled=False),
        broker=broker,
    ).run_once(db_session, {})

    assert result["result_status"] == "disabled"
    assert result["primary_block_reason"] == "auto_buy_live_phase1_disabled"
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert broker.calls == []


def test_run_once_blocks_when_dry_run_true(db_session):
    add_phase1_promotion(db_session)

    result = phase1_service(
        runtime=phase1_runtime(dry_run=True),
    ).run_once(db_session, {})

    assert result["result_status"] == "dry_run_blocked"
    assert result["primary_block_reason"] == "dry_run_enabled"


def test_run_once_blocks_when_kill_switch_true(db_session):
    add_phase1_promotion(db_session)

    result = phase1_service(
        runtime=phase1_runtime(kill_switch=True),
    ).run_once(db_session, {})

    assert result["result_status"] == "blocked"
    assert result["primary_block_reason"] == "kill_switch_enabled"


def test_run_once_blocks_when_kis_real_orders_disabled(db_session):
    add_phase1_promotion(db_session)

    result = phase1_service(
        runtime=phase1_runtime(kis_real_order_enabled=False),
    ).run_once(db_session, {})

    assert result["result_status"] == "blocked"
    assert result["primary_block_reason"] == "kis_real_order_disabled"


def test_run_once_blocks_when_production_readiness_not_ready(db_session):
    add_phase1_promotion(db_session)

    result = phase1_service(readiness=FakeReadiness("blocked")).run_once(
        db_session,
        {},
    )

    assert result["result_status"] == "blocked"
    assert result["primary_block_reason"] == "production_readiness_not_ready"
    assert result["production_readiness_status"] == "blocked"


def test_run_once_blocks_when_pending_sync_order_exists(db_session):
    add_phase1_promotion(db_session)
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="buy",
            order_type="market",
            internal_status=InternalOrderStatus.UNKNOWN_STALE.value,
        )
    )
    db_session.commit()

    result = phase1_service().run_once(db_session, {})

    assert result["result_status"] == "pending_sync"
    assert result["primary_block_reason"] == "pending_sync_order_exists"


def test_run_once_blocks_when_critical_exit_candidate_exists(db_session):
    add_phase1_promotion(db_session)

    result = phase1_service(
        auto_exit_candidates=FakeAutoExitCandidates(critical_count=1),
    ).run_once(db_session, {})

    assert result["result_status"] == "blocked"
    assert result["primary_block_reason"] == "critical_exit_candidate_exists"


def test_run_once_blocks_when_daily_phase1_limit_reached(db_session):
    add_phase1_promotion(db_session)
    db_session.add(
        TradeRunLog(
            run_key="phase1-existing",
            trigger_source="scheduler_phase1",
            symbol="005930",
            mode="auto_buy_live_phase1",
            stage="done",
            result="submitted",
            reason="submitted",
            response_payload=json.dumps({"real_order_submitted": True}),
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    result = phase1_service().run_once(db_session, {})

    assert result["primary_block_reason"] == "daily_auto_buy_limit_reached"
    assert result["daily_auto_buy_count"] == 1
    assert result["daily_auto_buy_limit"] == 1


def test_run_once_blocks_stale_dismissed_expired_or_converted_candidate(db_session):
    dry_run, promotion = add_phase1_promotion(db_session)
    StrategyAutoBuyPromotionService().dismiss(db_session, promotion["id"])

    result = phase1_service().run_once(
        db_session,
        {"promotion_id": promotion["id"]},
    )

    assert result["primary_block_reason"] == "promotion_dismissed"
    assert result["real_order_submitted"] is False


def test_run_once_skips_when_no_eligible_promotion_exists(db_session):
    result = phase1_service().run_once(db_session, {})

    assert result["result_status"] == "skipped"
    assert result["primary_block_reason"] == "no_eligible_promotion"


def test_run_once_blocks_near_close_no_new_entry_after(db_session):
    add_phase1_promotion(db_session)

    result = phase1_service(
        market_sessions=FakeMarketSessions(open=True, entry_allowed=False),
    ).run_once(db_session, {})

    assert result["result_status"] == "blocked"
    assert result["primary_block_reason"] == "after_no_new_entry_time"
    assert result["broker_submit_called"] is False


def test_run_once_submits_once_when_all_gates_pass(db_session):
    dry_run, promotion = add_phase1_promotion(db_session)
    broker = FakeBroker()

    result = phase1_service(broker=broker).run_once(
        db_session,
        {"promotion_id": promotion["id"]},
    )

    assert result["result_status"] == "submitted"
    assert result["real_order_submitted"] is True
    assert result["broker_submit_called"] is True
    assert result["manual_submit_called"] is False
    assert result["selected_promotion_id"] == promotion["id"]
    assert result["selected_symbol"] == "005930"
    assert result["order_id"] is not None
    assert broker.calls == [{"symbol": "005930", "qty": 3}]
    assert (
        db_session.query(TradeRunLog)
        .filter(TradeRunLog.mode == "auto_buy_live_phase1")
        .count()
        == 1
    )


def test_run_once_does_not_retry_when_submit_is_ambiguous(db_session):
    _, promotion = add_phase1_promotion(db_session)
    broker = RaisingBroker()

    result = phase1_service(broker=broker).run_once(
        db_session,
        {"promotion_id": promotion["id"]},
    )

    assert result["result_status"] == "pending_sync"
    assert result["broker_submit_called"] is True
    assert result["real_order_submitted"] is False
    assert result["manual_submit_called"] is False
    assert broker.calls == [{"symbol": "005930", "qty": 3}]
    assert result["safety"]["retry_attempted"] is False


def test_agent_chat_has_no_phase1_execution_or_settings_tool():
    registry = AgentChatToolRegistry()
    names = {tool.tool_name for tool in registry.list_tools(include_blocked=True)}

    assert "auto_buy_live_phase1_run" not in names
    assert "auto_buy_live_phase1_settings" not in names
