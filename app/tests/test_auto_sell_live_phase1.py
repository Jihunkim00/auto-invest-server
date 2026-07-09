from __future__ import annotations

import json
from datetime import UTC, datetime

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, TradeRunLog
from app.services.agent_chat_tool_registry import AgentChatToolRegistry
from app.services.auto_sell_live_phase1_service import AutoSellLivePhase1Service
from app.tests.test_strategy_live_auto_buy_service import FakeRuntimeSettings


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


class FakeCandidates:
    def __init__(self, candidates: list[dict] | None = None):
        self.candidates_payload = candidates if candidates is not None else [candidate()]
        self.calls: list[dict] = []

    def candidates(self, db, **kwargs):
        self.calls.append(kwargs)
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "provider": "kis",
            "market": "KR",
            "candidates": self.candidates_payload,
            "summary": {
                "candidate_count": len(self.candidates_payload),
                "critical_count": sum(
                    1
                    for item in self.candidates_payload
                    if item.get("severity") == "critical"
                ),
                "warning_count": sum(
                    1
                    for item in self.candidates_payload
                    if item.get("severity") == "warning"
                ),
                "duplicate_sell_block_count": sum(
                    1
                    for item in self.candidates_payload
                    if item.get("candidate_type") == "duplicate_sell_conflict"
                ),
                "sync_required_count": sum(
                    1
                    for item in self.candidates_payload
                    if item.get("candidate_type") == "sync_required"
                ),
            },
            "safety_flags": ["read_only", "no_live_orders"],
        }


class FakeExitReview:
    def __init__(
        self,
        *,
        status: str = "allowed",
        available_quantity: float = 3,
        requested_quantity: float = 3,
        market_session_allowed: bool = True,
        block_reason: str | None = None,
    ):
        self.status = status
        self.available_quantity = available_quantity
        self.requested_quantity = requested_quantity
        self.market_session_allowed = market_session_allowed
        self.block_reason = block_reason
        self.calls: list[dict] = []

    def sell_preflight(self, db, *, symbol, request):
        self.calls.append(
            {
                "symbol": symbol,
                "quantity_mode": request.quantity_mode,
                "quantity": request.quantity,
            }
        )
        return {
            "symbol": symbol,
            "provider": "kis",
            "market": "KR",
            "preflight_status": self.status,
            "can_submit_after_confirmation": self.status == "allowed",
            "position_exists": True,
            "available_quantity": self.available_quantity,
            "requested_quantity": self.requested_quantity,
            "estimated_sell_notional": self.requested_quantity * 10000,
            "market_session_allowed": self.market_session_allowed,
            "risk_flags": [],
            "gating_notes": ["sell preflight passed"],
            "primary_block_reason": self.block_reason,
        }


class FakeGuardedExit:
    def __init__(self, *, status: str = "submitted"):
        self.status = status
        self.calls: list[dict] = []

    def run_once(self, db, request, *, now=None):
        self.calls.append(
            {
                "symbol": request.symbol,
                "quantity": request.quantity,
                "confirm_operator_ack": request.confirm_operator_ack,
                "trigger_source": request.trigger_source,
            }
        )
        if self.status == "pending_sync":
            return {
                "status": "sync_required",
                "submitted": False,
                "symbol": request.symbol,
                "quantity": request.quantity,
                "block_reason": "broker_submit_sync_required",
                "safety": {
                    "broker_submit_called": True,
                    "real_order_submitted": False,
                    "manual_submit_called": False,
                },
            }
        return {
            "status": "submitted",
            "submitted": True,
            "symbol": request.symbol,
            "quantity": request.quantity,
            "submitted_notional_krw": request.quantity * 10000,
            "related_order_id": 77,
            "broker_order_id": "KIS-SELL-1",
            "safety": {
                "broker_submit_called": True,
                "real_order_submitted": True,
                "manual_submit_called": False,
            },
            "risk_flags": ["stop_loss_triggered"],
            "gating_notes": ["guarded sell submitted"],
        }


def phase1_runtime(**overrides) -> FakeRuntimeSettings:
    values = {
        "dry_run": False,
        "kill_switch": False,
        "max_trades_per_day": 10,
        "auto_sell_live_phase1_enabled": True,
        "auto_sell_live_phase1_allow_real_orders": True,
        "auto_sell_live_phase1_max_orders_per_day": 1,
        "auto_sell_live_phase1_require_production_ready": True,
        "auto_sell_live_phase1_provider": "kis",
        "auto_sell_live_phase1_allowed_candidate_types": [
            "stop_loss",
            "take_profit",
            "trend_breakdown",
            "weak_momentum",
        ],
    }
    values.update(overrides)
    return FakeRuntimeSettings(**values)


def phase1_service(
    *,
    runtime: FakeRuntimeSettings | None = None,
    readiness: FakeReadiness | None = None,
    candidates: FakeCandidates | None = None,
    exit_review: FakeExitReview | None = None,
    guarded: FakeGuardedExit | None = None,
) -> AutoSellLivePhase1Service:
    return AutoSellLivePhase1Service(
        runtime_settings=runtime or phase1_runtime(),
        readiness_service=readiness or FakeReadiness(),
        auto_exit_candidates=candidates or FakeCandidates(),
        exit_review_service=exit_review or FakeExitReview(),
        guarded_exit_service=guarded or FakeGuardedExit(),
    )


def candidate(**overrides) -> dict:
    payload = {
        "candidate_id": "auto-exit:kis:KR:005930:stop_loss:20260709",
        "symbol": "005930",
        "provider": "kis",
        "market": "KR",
        "candidate_type": "stop_loss",
        "severity": "critical",
        "status": "active",
        "action_hint": "run_sell_preflight",
        "position_quantity": 3,
        "available_quantity": 3,
        "current_price": 10000,
        "open_sell_order_conflict": False,
        "sync_required": False,
        "can_run_sell_preflight": True,
        "risk_flags": ["stop_loss_triggered"],
        "gating_notes": ["candidate from held position"],
        "primary_reason": "Stop-loss threshold reached.",
        "next_safe_action": "Run sell preflight.",
    }
    payload.update(overrides)
    return payload


def run_request(**overrides) -> dict:
    payload = {"confirm_phase1_run": True}
    payload.update(overrides)
    return payload


def test_run_once_disabled_by_default_blocks_before_submit(db_session):
    guarded = FakeGuardedExit()

    result = phase1_service(
        runtime=phase1_runtime(auto_sell_live_phase1_enabled=False),
        guarded=guarded,
    ).run_once(db_session, run_request())

    assert result["result_status"] == "disabled"
    assert result["primary_block_reason"] == "auto_sell_live_phase1_disabled"
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert guarded.calls == []


def test_run_once_blocks_when_dry_run_true(db_session):
    result = phase1_service(runtime=phase1_runtime(dry_run=True)).run_once(
        db_session,
        run_request(),
    )

    assert result["result_status"] == "dry_run_blocked"
    assert result["primary_block_reason"] == "dry_run_enabled"


def test_run_once_blocks_when_kill_switch_true(db_session):
    result = phase1_service(runtime=phase1_runtime(kill_switch=True)).run_once(
        db_session,
        run_request(),
    )

    assert result["result_status"] == "blocked"
    assert result["primary_block_reason"] == "kill_switch_enabled"


def test_run_once_blocks_when_kis_real_orders_disabled(db_session):
    result = phase1_service(
        runtime=phase1_runtime(kis_real_order_enabled=False),
    ).run_once(db_session, run_request())

    assert result["primary_block_reason"] == "kis_real_order_disabled"


def test_run_once_blocks_when_production_readiness_not_ready(db_session):
    result = phase1_service(readiness=FakeReadiness("blocked")).run_once(
        db_session,
        run_request(),
    )

    assert result["primary_block_reason"] == "production_readiness_not_ready"
    assert result["production_readiness_status"] == "blocked"


def test_run_once_blocks_when_no_position_exists(db_session):
    result = phase1_service(
        candidates=FakeCandidates([candidate(position_quantity=0)]),
    ).run_once(db_session, run_request())

    assert result["primary_block_reason"] == "position_missing"
    assert result["broker_submit_called"] is False


def test_run_once_blocks_when_available_quantity_zero(db_session):
    result = phase1_service(
        candidates=FakeCandidates([candidate(available_quantity=0)]),
    ).run_once(db_session, run_request())

    assert result["primary_block_reason"] == "available_quantity_zero"


def test_run_once_blocks_when_duplicate_open_sell_order_exists(db_session):
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="sell",
            order_type="market",
            internal_status=InternalOrderStatus.SUBMITTED.value,
        )
    )
    db_session.commit()

    result = phase1_service().run_once(db_session, run_request())

    assert result["primary_block_reason"] == "duplicate_open_sell_order"


def test_run_once_blocks_when_pending_sync_order_conflict_exists(db_session):
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="sell",
            order_type="market",
            internal_status=InternalOrderStatus.UNKNOWN_STALE.value,
        )
    )
    db_session.commit()

    result = phase1_service().run_once(db_session, run_request())

    assert result["result_status"] == "pending_sync"
    assert result["primary_block_reason"] == "pending_sync_order_exists"


def test_run_once_blocks_non_executable_candidate_types(db_session):
    for candidate_type in (
        "sync_required",
        "manual_review",
        "duplicate_sell_conflict",
    ):
        result = phase1_service(
            candidates=FakeCandidates(
                [
                    candidate(
                        candidate_id=f"candidate:{candidate_type}",
                        candidate_type=candidate_type,
                        severity="critical",
                        can_run_sell_preflight=False,
                    )
                ]
            )
        ).run_once(db_session, run_request(candidate_id=f"candidate:{candidate_type}"))

        assert result["primary_block_reason"].startswith("candidate_type_not_allowed")
        assert result["real_order_submitted"] is False


def test_run_once_blocks_when_daily_auto_sell_limit_reached(db_session):
    db_session.add(
        TradeRunLog(
            run_key="phase1-sell-existing",
            trigger_source="scheduler_phase1",
            symbol="005930",
            mode="auto_sell_live_phase1",
            stage="done",
            result="submitted",
            reason="submitted",
            response_payload=json.dumps({"real_order_submitted": True}),
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    result = phase1_service().run_once(db_session, run_request())

    assert result["primary_block_reason"] == "daily_auto_sell_limit_reached"
    assert result["daily_auto_sell_count"] == 1
    assert result["daily_auto_sell_limit"] == 1


def test_run_once_submits_once_when_all_gates_pass(db_session):
    guarded = FakeGuardedExit()

    result = phase1_service(guarded=guarded).run_once(
        db_session,
        run_request(),
    )

    assert result["result_status"] == "submitted"
    assert result["real_order_submitted"] is True
    assert result["broker_submit_called"] is True
    assert result["manual_submit_called"] is False
    assert result["selected_candidate_id"] == candidate()["candidate_id"]
    assert result["selected_symbol"] == "005930"
    assert result["candidate_type"] == "stop_loss"
    assert result["submitted_quantity"] == 3
    assert result["order_id"] == 77
    assert guarded.calls == [
        {
            "symbol": "005930",
            "quantity": 3,
            "confirm_operator_ack": True,
            "trigger_source": "auto_sell_live_phase1",
        }
    ]


def test_run_once_does_not_retry_when_submit_is_ambiguous(db_session):
    guarded = FakeGuardedExit(status="pending_sync")

    result = phase1_service(guarded=guarded).run_once(
        db_session,
        run_request(),
    )

    assert result["result_status"] == "pending_sync"
    assert result["broker_submit_called"] is True
    assert result["real_order_submitted"] is False
    assert result["manual_submit_called"] is False
    assert len(guarded.calls) == 1
    assert result["safety"]["retry_attempted"] is False


def test_scheduler_sell_phase1_skips_buy_for_critical_block(monkeypatch, db_session):
    from app.services.scheduler_service import SchedulerService

    scheduler = SchedulerService()
    scheduler.runtime_settings = phase1_runtime(
        auto_buy_live_phase1_enabled=True,
        auto_buy_live_phase1_allow_real_orders=True,
    )
    sell_result = {
        "result_status": "blocked",
        "candidate_severity": "critical",
        "primary_block_reason": "sell_preflight_blocked",
    }
    assert scheduler._auto_sell_phase1_should_skip_buy(sell_result) is True


def test_agent_chat_has_no_phase1_auto_sell_execution_or_settings_tool():
    registry = AgentChatToolRegistry()
    names = {tool.tool_name for tool in registry.list_tools(include_blocked=True)}

    assert "auto_sell_live_phase1_run" not in names
    assert "auto_sell_live_phase1_settings" not in names
