from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.core.enums import InternalOrderStatus
from app.db.models import (
    AutomationProfileBuyReservation,
    OrderLog,
    PositionLifecycle,
    SignalLog,
    TradeRunLog,
)
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.calendar_gap_risk_service import CalendarGapRiskService
from app.services.market_calendar_service import MarketCalendarService
from app.services.automation_execution_authority_service import (
    AutomationExecutionAuthorityService,
)
from app.services.automation_profile_buy_scheduler_service import (
    AutomationProfileBuySchedulerService,
)
from app.services.automation_profile_service import AutomationProfileService
from app.services.kis_automation_execution_core import KisAutomationExecutionCore
from app.services.profile_aware_dry_run_auto_buy_service import (
    ProfileAwareDryRunAutoBuyService,
    _preview_score_gate_diagnostics,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.scheduler_service import SchedulerService
from app.services.strategy_auto_buy_scheduler_service import (
    StrategyAutoBuySchedulerService,
)
from app.services.strategy_profile_service import StrategyProfileService
from app.services.strategy_risk_budget_service import StrategyRiskBudgetService
from app.services.target_aware_risk_service import TargetAwareRiskService
import app.services.scheduler_service as scheduler_module


KST = ZoneInfo("Asia/Seoul")
UTC_NOW = datetime(2026, 8, 25, 0, 10, tzinfo=UTC)
CUSTOM_PROFILE_KEY = "aut_pr110_replay"
SYMBOL = "005930"


@dataclass
class VirtualClock:
    current: datetime = UTC_NOW

    def now(self) -> datetime:
        return self.current


@dataclass
class FakeMarketSessions:
    clock: VirtualClock
    is_open: bool = True
    calls: list[datetime] = field(default_factory=list)

    def get_session_status(self, market: str, *, now: datetime | None = None) -> dict[str, Any]:
        current = now or self.clock.now()
        self.calls.append(current)
        return {
            "market": market,
            "is_market_open": self.is_open,
            "is_entry_allowed_now": self.is_open,
            "session": "open" if self.is_open else "closed",
        }


@dataclass
class DeterministicPreviewService:
    market_sessions: FakeMarketSessions
    candidates: list[dict[str, Any]]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def run_preview(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        values = [dict(candidate) for candidate in self.candidates]
        return {
            "provider": "kis",
            "market": "KR",
            "market_session": self.market_sessions.get_session_status(
                "KR", now=kwargs.get("now")
            ),
            "final_ranked_candidates": values,
            "final_best_candidate": values[0] if values else None,
            "configured_symbol_count": len(values),
            "analyzed_symbol_count": len(values),
            "preview_status": "ok",
            "risk_flags": [],
            "gating_notes": [],
        }


class FakeKisClient:
    def __init__(self, clock: VirtualClock, candidates: list[dict[str, Any]]) -> None:
        self.clock = clock
        self.candidates = candidates
        self.cash = 601456.0
        self.positions: list[dict[str, Any]] = []
        self.open_orders: list[dict[str, Any]] = []
        self.possible_order_missing = False
        self.possible_order_age_seconds = 0.0
        self.external_kis_submit_count = 0
        self.possible_order_calls = 0
        self.last_possible_order_queried_at: datetime | None = None

    def list_positions(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.positions]

    def list_open_orders(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.open_orders]

    def get_account_balance(self) -> dict[str, Any]:
        return {
            "cash": self.cash,
            "orderable_cash": self.cash,
            "total_asset_value": self.cash,
        }

    def get_domestic_stock_price(self, symbol: str) -> dict[str, Any]:
        candidate = next(
            (item for item in self.candidates if item.get("symbol") == symbol),
            {},
        )
        return {
            "symbol": symbol,
            "current_price": float(
                candidate.get("current_price") or candidate.get("price") or 0
            ),
        }

    def get_domestic_possible_order(self, **kwargs: Any) -> dict[str, Any]:
        self.possible_order_calls += 1
        if self.possible_order_missing:
            return {"raw_status": "error", "error": "possible_order_missing"}
        queried_at = self.clock.now() - timedelta(
            seconds=float(self.possible_order_age_seconds)
        )
        self.last_possible_order_queried_at = queried_at
        return {
            "raw_status": "ok",
            "orderable_cash": self.cash,
            "orderable_quantity": 1000,
            "queried_at": queried_at.isoformat(),
            "symbol": kwargs.get("symbol"),
        }


class FakeBroker:
    def __init__(self, client: FakeKisClient) -> None:
        self.client = client
        self.buy_calls: list[dict[str, Any]] = []
        self.sell_calls: list[dict[str, Any]] = []

    def submit_market_buy(self, *, symbol: str, qty: int) -> dict[str, Any]:
        self.buy_calls.append({"symbol": symbol, "qty": qty})
        price = self.client.get_domestic_stock_price(symbol)["current_price"]
        return {
            "broker_order_id": f"FAKE-KIS-{len(self.buy_calls)}",
            "broker_status": "filled",
            "filled": True,
            "filled_qty": qty,
            "avg_fill_price": price,
        }

    def submit_market_sell(self, *, symbol: str, qty: int) -> dict[str, Any]:
        self.sell_calls.append({"symbol": symbol, "qty": qty})
        return {
            "broker_order_id": f"FAKE-KIS-SELL-{len(self.sell_calls)}",
            "broker_status": "filled",
            "filled": True,
            "filled_qty": qty,
        }


class FakeValidationService:
    def __init__(self) -> None:
        self.calls: list[Any] = []
        self.approved = True
        self.block_reason = "kis_validation_rejected"

    def validate(self, request: Any, *, now: datetime | None = None) -> dict[str, Any]:
        self.calls.append(request)
        return {
            "validated_for_submission": self.approved,
            "can_submit_later": self.approved,
            "block_reasons": [] if self.approved else [self.block_reason],
            "primary_block_reason": None if self.approved else self.block_reason,
            "current_price": 80000.0,
            "estimated_amount": float(request.qty) * 80000.0,
        }


class FakeOrderSyncService:
    def __init__(self, clock: VirtualClock) -> None:
        self.clock = clock
        self.calls: list[int] = []

    def sync_order(self, db: Any, order_id: int) -> OrderLog:
        self.calls.append(order_id)
        order = db.get(OrderLog, int(order_id))
        assert order is not None
        order.internal_status = InternalOrderStatus.FILLED.value
        order.broker_status = "filled"
        order.broker_order_status = "filled"
        order.filled_qty = order.qty
        order.remaining_qty = 0
        order.avg_fill_price = order.filled_avg_price = order.limit_price
        order.filled_at = self.clock.now()
        db.commit()
        db.refresh(order)
        return order


def candidate(
    *,
    score: float = 70.0,
    price: float = 80000.0,
    symbol: str = SYMBOL,
    **values: Any,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "name": "Samsung Electronics",
        "current_price": price,
        "price": price,
        "final_buy_score": score,
        "final_score": score,
        "confidence": 0.92,
        "entry_ready": True,
        "indicator_status": "ok",
        "indicator_payload": {"atr": 800.0, "volume_ratio": 1.4},
        "quant_buy_score": score,
        "quant_c_score": score,
        "quant_c_status": "analyzed",
        "ai_buy_score": score,
        "ai_sell_score": 100.0 - score,
        "gpt_analysis_status": "completed",
        "gpt_used": True,
        "data_sufficient": True,
        "risk_flags": [],
        "gating_notes": [],
        **values,
    }


@dataclass
class ReplayHarness:
    db: Any
    clock: VirtualClock
    market_sessions: FakeMarketSessions
    preview: DeterministicPreviewService
    client: FakeKisClient
    broker: FakeBroker
    validation: FakeValidationService
    sync: FakeOrderSyncService
    runtime: RuntimeSettingService
    profiles: AutomationProfileService
    scheduler: SchedulerService
    strategy_scheduler: StrategyAutoBuySchedulerService
    profile_buy: AutomationProfileBuySchedulerService


def build_harness(
    db: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: str = "live",
    candidates: list[dict[str, Any]] | None = None,
    market_open: bool = True,
    no_new_entry_after: str = "14:00",
    now: datetime = UTC_NOW,
    analysis_times: tuple[str, ...] = ("09:10",),
) -> ReplayHarness:
    clock = VirtualClock(now)
    values = candidates or [candidate()]
    market_sessions = FakeMarketSessions(clock, is_open=market_open)
    preview = DeterministicPreviewService(market_sessions, values)
    client = FakeKisClient(clock, values)
    broker = FakeBroker(client)
    validation = FakeValidationService()
    sync = FakeOrderSyncService(clock)
    runtime = RuntimeSettingService()
    runtime.update_settings(
        db,
        {
            "automation_mode": mode,
            "dry_run": mode != "live",
            "kill_switch": False,
            "strategy_auto_buy_scheduler_min_minutes_between_runs": 0,
            "strategy_auto_buy_scheduler_max_runs_per_day": 10,
            "strategy_auto_buy_scheduler_create_promotion_on_would_buy": False,
        },
    )

    profiles = AutomationProfileService(runtime_settings=runtime)
    profiles.create(
        db,
        AutomationProfileWriteRequest(
            profile_key=CUSTOM_PROFILE_KEY,
            name="PR110 replay custom",
            provider="kis",
            market="KR",
            enabled=True,
            status="scheduled",
            capital={
                "sizing_mode": "equity_pct",
                "target_position_pct": 20.0,
                "max_position_pct": 20.0,
                "max_total_exposure_pct": 30.0,
                "max_order_notional_krw": 100000.0,
                "cash_only": True,
            },
            universe={"manual_symbols": [SYMBOL]},
            entry={
                "analysis_times": list(analysis_times),
                "no_new_entry_after": no_new_entry_after,
                "min_final_score": 65.0,
                "max_new_entries_per_day": 1,
                "max_entries_per_scan": 1,
            },
            operation={
                "start_date": "2026-08-01",
                "end_date": "2026-09-30",
                "weekdays_only": False,
                "timezone": "Asia/Seoul",
            },
            max_open_positions=1,
        ),
    )
    profiles.activate(db, CUSTOM_PROFILE_KEY)

    legacy_profiles = StrategyProfileService()
    budget = StrategyRiskBudgetService(
        strategy_profiles=legacy_profiles,
        runtime_settings=runtime,
        position_loader=lambda _db, _provider, _market: client.list_positions(),
        balance_loader=lambda _db, _provider, _market: client.get_account_balance(),
    )
    risk = TargetAwareRiskService(budget_service=budget)
    dry_run = ProfileAwareDryRunAutoBuyService(
        preview_service=preview,
        strategy_profiles=legacy_profiles,
        target_risk_service=risk,
        market_sessions=market_sessions,
    )
    strategy_scheduler = StrategyAutoBuySchedulerService(
        runtime_settings=runtime,
        strategy_profiles=legacy_profiles,
        market_sessions=market_sessions,
        dry_run_service=dry_run,
    )
    execution_core = KisAutomationExecutionCore(
        client,
        broker=broker,
        validation_service=validation,
        order_sync_service=sync,
        runtime_settings=runtime,
        now_provider=clock.now,
    )
    profile_buy = AutomationProfileBuySchedulerService(
        client=client,
        broker=broker,
        validation_service=validation,
        order_sync_service=sync,
        runtime_settings=runtime,
        strategy_profiles=profiles,
        target_risk_service=risk,
        positions_loader=lambda _db: client.list_positions(),
        balance_loader=lambda _db: client.get_account_balance(),
        open_orders_loader=lambda _db: client.list_open_orders(),
        execution_core=execution_core,
    )

    scheduler = SchedulerService()
    scheduler.runtime_settings = runtime
    scheduler.automation_profiles = profiles
    scheduler.strategy_auto_buy_scheduler_service = strategy_scheduler
    scheduler.automation_profile_buy_scheduler_service = profile_buy
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: db)

    return ReplayHarness(
        db=db,
        clock=clock,
        market_sessions=market_sessions,
        preview=preview,
        client=client,
        broker=broker,
        validation=validation,
        sync=sync,
        runtime=runtime,
        profiles=profiles,
        scheduler=scheduler,
        strategy_scheduler=strategy_scheduler,
        profile_buy=profile_buy,
    )


def run_scheduler(harness: ReplayHarness) -> dict[str, Any]:
    return harness.scheduler._run_strategy_auto_buy_dry_run_scheduled_once(
        "strategy_auto_buy_dry_run_open_phase",
        now=harness.clock.now(),
    )


def reservation_count(db: Any, *, slot: str = "09:10") -> int:
    return (
        db.query(AutomationProfileBuyReservation)
        .filter(AutomationProfileBuyReservation.scheduler_slot_kst == slot)
        .count()
    )


def test_production_equivalent_0910_score_pass_replays_custom_profile(db_session, monkeypatch):
    harness = build_harness(db_session, monkeypatch)

    authority = AutomationExecutionAuthorityService(harness.runtime).snapshot(db_session)
    assert authority["automation_mode"] == "live"
    assert authority["scheduler_allowed"] is True
    assert authority["broker_submit_allowed"] is True

    result = run_scheduler(harness)

    assert result["dry_run"]["analysis_completed"] is True
    assert result["dry_run"]["scheduled_slot_key"] == (
        f"{CUSTOM_PROFILE_KEY}:2026-08-25:09:10"
    )
    assert result["dry_run"]["profile_key"] == CUSTOM_PROFILE_KEY
    assert result["dry_run"]["dry_run_result"]["profile_key"] == CUSTOM_PROFILE_KEY
    assert result["dry_run"]["dry_run_result"]["final_buy_score"] == 70.0
    assert result["dry_run"]["dry_run_result"]["required_entry_score"] == 65.0
    assert result["profile_buy"]["selected_symbol"] == SYMBOL
    assert result["profile_buy"]["final_buy_score"] == 70.0
    assert result["profile_buy"]["required_entry_score"] == 65.0
    assert result["profile_buy"]["quantity"] >= 1
    assert result["profile_buy"]["validation_called"] is True
    assert result["profile_buy"]["validation_call_count"] == 1
    assert result["profile_buy"]["broker_submit_called"] is True
    assert result["profile_buy"]["broker_buy_call_count"] == 1
    assert result["profile_buy"]["real_external_kis_submit_count"] == 0
    assert len(harness.preview.calls) == 1
    assert len(harness.validation.calls) == 1
    assert len(harness.broker.buy_calls) == 1
    assert harness.client.external_kis_submit_count == 0
    assert harness.client.possible_order_calls == 1
    assert harness.client.last_possible_order_queried_at is not None
    assert (
        harness.clock.now() - harness.client.last_possible_order_queried_at
    ).total_seconds() <= 10
    assert result["profile_buy"]["lifecycle"]["status"] == "open"

    order = db_session.get(OrderLog, result["profile_buy"]["order_id"])
    assert order is not None
    assert order.internal_status == InternalOrderStatus.FILLED.value
    assert order.broker_status == "filled"
    assert db_session.query(SignalLog).count() == 1
    assert db_session.query(TradeRunLog).count() >= 3
    assert (
        db_session.query(PositionLifecycle)
        .filter(PositionLifecycle.status == "open")
        .count()
        == 1
    )
    assert reservation_count(db_session) == 1
    reservation = db_session.get(
        AutomationProfileBuyReservation, result["profile_buy"]["reservation_id"]
    )
    assert reservation is not None
    assert reservation.profile_key == CUSTOM_PROFILE_KEY
    assert reservation.scheduler_slot_kst == "09:10"
    assert reservation.trade_date_kst == "2026-08-25"
    assert reservation.status == "filled"

    possible = result["profile_buy"]["live_order_gate"]
    assert possible["automation_mode"] == "live"


@pytest.mark.parametrize("score, eligible", [(64.99, False), (65.0, True), (65.01, True)])
def test_score_threshold_boundary_is_exact(db_session, monkeypatch, score, eligible):
    harness = build_harness(
        db_session,
        monkeypatch,
        candidates=[candidate(score=score)],
    )

    result = run_scheduler(harness)

    profile_result = result.get("profile_buy") or {}
    assert result["dry_run"]["dry_run_result"]["required_entry_score"] == 65.0
    if eligible:
        assert profile_result["action"] == "buy"
        assert len(harness.broker.buy_calls) == 1
    else:
        assert profile_result["reason"] == "below_profile_buy_threshold"
        assert profile_result["action"] == "hold"
        assert len(harness.validation.calls) == 0
        assert len(harness.broker.buy_calls) == 0
    assert result["dry_run"]["dry_run_result"]["final_buy_score"] == score



@pytest.mark.parametrize(
    ("final_score", "c_score", "gpt_score", "expected_reason"),
    [
        (70.0, 64.99, 80.0, "c_score_below_threshold"),
        (70.37, 76.16, 53.0, "gpt_buy_score_below_threshold"),
    ],
)
def test_admin_a_top5_blocks_c_or_independent_gpt_score_failure(
    db_session, monkeypatch, final_score, c_score, gpt_score, expected_reason
):
    row = candidate(
        score=final_score,
        quant_c_score=c_score,
        ai_buy_score=gpt_score,
        ai_sell_score=100.0 - gpt_score,
    )
    harness = build_harness(db_session, monkeypatch, candidates=[row])
    harness.runtime.update_settings(
        db_session,
        {"quant_selection_mode": "A_TOP5_C_GPT"},
    )

    result = run_scheduler(harness)
    profile_result = result["profile_buy"]

    assert profile_result["reason"] == expected_reason
    assert profile_result["validation_called"] is False
    assert profile_result["broker_submit_called"] is False
    assert profile_result["real_order_submitted"] is False
    assert profile_result["calendar_gap_candidate_diagnostics"][0]["skip_reason"] == expected_reason
    assert len(harness.validation.calls) == 0
    assert harness.broker.buy_calls == []
    assert harness.client.external_kis_submit_count == 0



def test_profile_aware_preview_preserves_a_top5_score_gate_diagnostics():
    diagnostics = _preview_score_gate_diagnostics({
        "quant_experiment": {"selection_mode": "A_TOP5_C_GPT"},
        "watchlist": [
            {
                "symbol": "A",
                "selected_by_a_top5": True,
                "quant_a_rank": 1,
                "quant_c_status": "analyzed",
                "quant_c_score": 76.16,
                "gpt_used": True,
                "gpt_analysis_status": "completed",
                "ai_buy_score": 53.0,
                "ai_sell_score": 47.0,
                "final_entry_score": 70.37,
            },
            {
                "symbol": "B",
                "selected_by_a_top5": True,
                "quant_a_rank": 2,
                "quant_c_status": "analyzed",
                "quant_c_score": 64.99,
                "gpt_used": False,
                "gpt_analysis_status": "not_run",
            },
        ],
    })

    assert [item["skip_reason"] for item in diagnostics] == [
        "gpt_buy_score_below_threshold",
        "c_score_below_threshold",
    ]
    assert diagnostics[0]["final_buy_score"] == 70.37
    assert diagnostics[0]["gpt_buy_score_threshold"] == 60.0
    assert diagnostics[1]["quant_c_threshold"] == 65.0


def test_admin_scheduler_logs_preview_gate_reason_when_execution_pool_is_empty(
    db_session, monkeypatch
):
    harness = build_harness(db_session, monkeypatch)
    harness.runtime.update_settings(
        db_session,
        {"quant_selection_mode": "A_TOP5_C_GPT"},
    )
    diagnostics = _preview_score_gate_diagnostics({
        "quant_experiment": {"selection_mode": "A_TOP5_C_GPT"},
        "watchlist": [{
            "symbol": "A",
            "selected_by_a_top5": True,
            "quant_a_rank": 1,
            "quant_c_status": "analyzed",
            "quant_c_score": 76.16,
            "gpt_used": True,
            "gpt_analysis_status": "completed",
            "ai_buy_score": 53.0,
            "ai_sell_score": 47.0,
            "final_entry_score": 70.37,
        }],
    })

    result = harness.profile_buy.run_once(
        db_session,
        {"execution_candidates": [], "score_gate_diagnostics": diagnostics},
        scheduler_slot="09:10",
        trigger_source="automation_scheduler",
        now=UTC_NOW,
        trusted_scheduler_authority=True,
    )

    assert result["reason"] == "gpt_buy_score_below_threshold"
    assert result["block_reason"] == "gpt_buy_score_below_threshold"
    assert result["score_gate_candidate"]["symbol"] == "A"
    assert result["score_gate_candidate"]["gpt_buy_score"] == 53.0
    assert result["validation_called"] is False
    assert result["broker_submit_called"] is False
    assert harness.validation.calls == []
    assert harness.broker.buy_calls == []
    log = db_session.query(TradeRunLog).filter(
        TradeRunLog.mode == "automation_profile_scheduler_buy"
    ).one()
    assert log.symbol == "A"
    assert log.reason == "gpt_buy_score_below_threshold"
    logged_payload = json.loads(log.response_payload)
    assert logged_payload["score_gate_candidate"]["gpt_buy_score_threshold"] == 60.0


def test_admin_a_top5_selects_next_candidate_after_gpt_score_failure(db_session, monkeypatch):
    harness = build_harness(
        db_session,
        monkeypatch,
        candidates=[
            candidate(
                score=70.37,
                symbol="A",
                quant_c_score=76.16,
                ai_buy_score=53.0,
                ai_sell_score=47.0,
            ),
            candidate(
                score=65.25,
                symbol="B",
                quant_c_score=67.0,
                ai_buy_score=60.0,
                ai_sell_score=40.0,
            ),
        ],
    )
    harness.runtime.update_settings(
        db_session,
        {"quant_selection_mode": "A_TOP5_C_GPT"},
    )

    result = run_scheduler(harness)
    profile_result = result["profile_buy"]
    diagnostics = profile_result["calendar_gap_candidate_diagnostics"]

    assert profile_result["selected_symbol"] == "B"
    assert diagnostics[0]["skip_reason"] == "gpt_buy_score_below_threshold"
    assert diagnostics[-1]["selected"] is True
    assert len(harness.validation.calls) == 1
    assert [call["symbol"] for call in harness.broker.buy_calls] == ["B"]
    assert harness.client.external_kis_submit_count == 0


def test_friday_calendar_gate_falls_back_and_halves_admin_profile_sizing(
    db_session, monkeypatch
):
    friday = datetime(2026, 9, 11, 0, 10, tzinfo=UTC)
    harness = build_harness(
        db_session,
        monkeypatch,
        now=friday,
        candidates=[
            candidate(score=75.0, price=10000.0, symbol="A", quant_c_score=74.0),
            candidate(score=72.0, price=10000.0, symbol="B", quant_c_score=78.0),
        ],
    )
    harness.runtime.update_settings(
        db_session,
        {"quant_selection_mode": "A_TOP5_C_GPT"},
    )

    result = run_scheduler(harness)
    profile_result = result["profile_buy"]
    calendar_risk = profile_result["calendar_gap_risk"]
    target = profile_result["target_risk_result"]

    assert calendar_risk["calendar_gap_days"] == 3
    assert calendar_risk["required_c_score"] == 75.0
    assert calendar_risk["required_final_score"] == 70.0
    assert calendar_risk["position_size_multiplier"] == 0.5
    assert profile_result["selected_symbol"] == "B"
    assert profile_result["quantity"] >= 1
    assert target["approved_notional_krw"] == target["calendar_gap_base_approved_notional_krw"] * 0.5
    assert profile_result["calendar_gap_candidate_diagnostics"][0]["skip_reason"] == "calendar_gap_c_below_threshold"
    assert len(harness.validation.calls) == 1
    assert len(harness.broker.buy_calls) == 1
    assert harness.broker.buy_calls[0]["symbol"] == "B"


def test_admin_friday_after_cutoff_blocks_before_validation_or_submit(
    db_session, monkeypatch
):
    after_cutoff = datetime(2026, 9, 11, 4, 0, tzinfo=UTC)
    harness = build_harness(
        db_session,
        monkeypatch,
        now=after_cutoff,
        candidates=[candidate(score=75.0)],
        analysis_times=("13:00",),
    )

    result = harness.profile_buy.run_once(
        db_session,
        [candidate(score=75.0)],
        scheduler_slot="13:00",
        trigger_source="automation_scheduler",
        now=after_cutoff,
        trusted_scheduler_authority=True,
    )

    assert result["reason"] == "weekend_gap_late_entry_block"
    assert result["calendar_gap_days"] == 3
    assert result["validation_called"] is False
    assert result["broker_submit_called"] is False
    assert result["real_order_submitted"] is False
    assert harness.validation.calls == []
    assert harness.client.possible_order_calls == 0
    assert harness.broker.buy_calls == []


def test_admin_long_holiday_blocks_before_validation_or_possible_order(
    db_session, monkeypatch, tmp_path
):
    friday = datetime(2026, 9, 11, 0, 10, tzinfo=UTC)
    harness = build_harness(
        db_session,
        monkeypatch,
        now=friday,
        candidates=[candidate(score=75.0)],
    )
    holidays = tmp_path / "market_holidays.yaml"
    holidays.write_text(
        'markets:\n  KR:\n    timezone: Asia/Seoul\n    holidays:\n'
        '      - date: "2026-09-14"\n        name: "Test Holiday"\n'
        '        reason: test_holiday\n        full_day: true\n',
        encoding="utf-8",
    )
    harness.profile_buy.calendar_gap_risk_service = CalendarGapRiskService(
        MarketCalendarService(config_path=str(holidays))
    )

    result = harness.profile_buy.run_once(
        db_session,
        [candidate(score=75.0)],
        scheduler_slot="09:10",
        trigger_source="automation_scheduler",
        now=friday,
        trusted_scheduler_authority=True,
    )

    assert result["reason"] == "long_market_closure_ahead"
    assert result["calendar_gap_days"] == 4
    assert result["broker_submit_called"] is False
    assert result["real_order_submitted"] is False
    assert harness.validation.calls == []
    assert harness.client.possible_order_calls == 0
    assert harness.broker.buy_calls == []


def test_quantity_zero_candidate_falls_through_to_next_eligible_candidate(
    db_session, monkeypatch
):
    harness = build_harness(
        db_session,
        monkeypatch,
        candidates=[
            candidate(score=72.0, price=631000.0, symbol="A"),
            candidate(score=68.0, price=30000.0, symbol="B"),
        ],
    )

    result = run_scheduler(harness)

    assert result["profile_buy"]["action"] == "buy"
    assert result["profile_buy"]["selected_symbol"] == "B"
    assert result["profile_buy"]["quantity"] >= 1
    assert len(harness.broker.buy_calls) == 1
    assert harness.broker.buy_calls[0]["symbol"] == "B"
    assert len(harness.validation.calls) == 1


@pytest.mark.parametrize(
    "case",
    [
        "missing_active_key",
        "missing_profile",
        "paused_profile",
        "disabled_profile",
    ],
)
def test_inactive_or_missing_active_profile_is_a_clean_scheduler_skip(
    db_session, monkeypatch, case
):
    harness = build_harness(db_session, monkeypatch)
    if case == "missing_active_key":
        harness.runtime.update_settings(
            db_session, {"active_automation_profile_key": None}
        )
    elif case == "missing_profile":
        harness.runtime.update_settings(
            db_session, {"active_automation_profile_key": "aut_pr110_missing"}
        )
    else:
        row = harness.profiles.get(db_session, CUSTOM_PROFILE_KEY)
        row.custom_status = "paused" if case == "paused_profile" else "disabled"
        row.enabled = False
        db_session.commit()
        harness.runtime.update_settings(
            db_session, {"active_automation_profile_key": CUSTOM_PROFILE_KEY}
        )

    assert harness.profiles.get_active_profile(db_session) is None
    result = run_scheduler(harness)

    dry_result = result.get("dry_run", result)
    assert dry_result["action"] == "blocked"
    assert result.get("profile_buy") is None
    assert len(harness.broker.buy_calls) == 0
    assert len(harness.validation.calls) == 0


@pytest.mark.parametrize(
    "case",
    [
        "insufficient_cash",
        "dry_run_true",
        "kill_switch",
        "existing_position",
        "duplicate_open_order",
        "existing_reservation",
        "possible_order_missing",
        "possible_order_stale",
        "market_closed",
        "after_no_new_entry_after",
        "daily_trade_limit_reached",
        "kis_validation_rejected",
    ],
)
def test_score_pass_safety_matrix_never_submits(
    db_session, monkeypatch, case
):
    now = UTC_NOW
    if case == "after_no_new_entry_after":
        now = datetime(2026, 8, 25, 5, 10, tzinfo=UTC)
    harness = build_harness(
        db_session,
        monkeypatch,
        market_open=case != "market_closed",
        no_new_entry_after="14:00",
        now=now,
    )

    if case == "insufficient_cash":
        harness.client.cash = 1000.0
    elif case == "dry_run_true":
        harness.runtime.update_settings(db_session, {"dry_run": True})
    elif case == "kill_switch":
        harness.runtime.update_settings(db_session, {"kill_switch": True})
    elif case == "existing_position":
        harness.client.positions = [{"symbol": SYMBOL, "qty": 1}]
    elif case == "duplicate_open_order":
        harness.client.open_orders = [{"symbol": SYMBOL, "side": "buy", "qty": 1}]
    elif case == "existing_reservation":
        db_session.add(
            AutomationProfileBuyReservation(
                reservation_key=f"{CUSTOM_PROFILE_KEY}:2026-08-25:09:10:{SYMBOL}",
                profile_key=CUSTOM_PROFILE_KEY,
                provider="kis",
                market="KR",
                trade_date_kst="2026-08-25",
                scheduler_slot_kst="09:10",
                symbol=SYMBOL,
                status="reserved",
            )
        )
        db_session.commit()
    elif case == "possible_order_missing":
        harness.client.possible_order_missing = True
    elif case == "possible_order_stale":
        harness.client.possible_order_age_seconds = 11.0
    elif case == "daily_trade_limit_reached":
        db_session.add(
            OrderLog(
                broker="kis",
                market="KR",
                symbol="000000",
                side="buy",
                order_type="market",
                qty=1,
                requested_qty=1,
                internal_status=InternalOrderStatus.FILLED.value,
                submitted_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        db_session.commit()
    elif case == "kis_validation_rejected":
        harness.validation.approved = False

    result = run_scheduler(harness)
    profile_result = result.get("profile_buy") or {}

    assert len(harness.broker.buy_calls) == 0
    assert harness.client.external_kis_submit_count == 0
    reason = (
        profile_result.get("reason")
        or result["dry_run"].get("block_reason")
        or result["dry_run"]["dry_run_result"].get("reason")
    )
    assert reason


def test_same_scheduled_callback_is_idempotent_and_consumes_0910_once(
    db_session, monkeypatch
):
    harness = build_harness(db_session, monkeypatch)

    first = run_scheduler(harness)
    second = run_scheduler(harness)

    assert first["profile_buy"]["action"] == "buy"
    assert len(harness.broker.buy_calls) == 1
    assert second["profile_buy"]["reason"] == "scheduled_slot_already_attempted"
    assert reservation_count(db_session) == 1


def test_manual_execution_does_not_consume_scheduled_slot_then_scheduler_runs(
    db_session, monkeypatch
):
    harness = build_harness(db_session, monkeypatch)
    before = reservation_count(db_session)

    manual = harness.profile_buy.run_once(
        db_session,
        [candidate()],
        scheduler_slot="09:10",
        trigger_source="manual",
        now=harness.clock.now(),
    )

    assert manual["reason"] == "manual_execution_isolation"
    assert reservation_count(db_session) == before
    assert len(harness.broker.buy_calls) == 0

    result = run_scheduler(harness)
    assert result["profile_buy"]["action"] == "buy"
    assert len(harness.broker.buy_calls) == 1


@pytest.mark.parametrize(
    "mode, broker_calls, scheduler_allowed, broker_submit_allowed",
    [
        ("off", 0, False, False),
        ("test", 0, True, False),
        ("live", 1, True, True),
    ],
)
def test_automation_authority_matrix_controls_scheduler_and_broker(
    db_session,
    monkeypatch,
    mode,
    broker_calls,
    scheduler_allowed,
    broker_submit_allowed,
):
    harness = build_harness(db_session, monkeypatch, mode=mode)
    authority = AutomationExecutionAuthorityService(harness.runtime).snapshot(db_session)

    result = run_scheduler(harness)

    assert authority["scheduler_allowed"] is scheduler_allowed
    assert authority["broker_submit_allowed"] is broker_submit_allowed
    assert len(harness.broker.buy_calls) == broker_calls
    if mode == "off":
        assert getattr(result, "reason", None) == "automation_mode_off"
    else:
        assert result["dry_run"]["dry_run_result"]["profile_key"] == CUSTOM_PROFILE_KEY


def test_paper_preset_replays_profile_analysis_without_broker_submit(
    db_session, monkeypatch
):
    harness = build_harness(db_session, monkeypatch)
    harness.runtime.apply_preset(db_session, preset="dry_run_simulation")

    result = run_scheduler(harness)

    authority = AutomationExecutionAuthorityService(harness.runtime).snapshot(db_session)
    runtime = harness.runtime.get_settings_read_only(db_session)
    assert runtime["current_operation_mode"] == "dry_run_simulation"
    assert authority["automation_mode"] == "test"
    assert result["dry_run"]["analysis_completed"] is True
    assert result["dry_run"]["dry_run_result"]["final_buy_score"] == 70.0
    assert result["profile_buy"]["validation_called"] is True
    assert result["profile_buy"]["broker_submit_called"] is False
    assert harness.broker.buy_calls == []
    assert harness.client.external_kis_submit_count == 0


@pytest.mark.parametrize(
    ("setting", "value", "expected_reason"),
    [
        ("kill_switch", True, "kill_switch_enabled"),
        ("dry_run", True, "dry_run_true"),
    ],
)
def test_live_preset_blocks_at_custom_profile_scheduler_gate_before_execution_core(
    db_session, monkeypatch, setting, value, expected_reason
):
    harness = build_harness(db_session, monkeypatch)
    harness.runtime.apply_preset(
        db_session,
        preset="full_live_test_mode",
        confirm_dangerous=True,
    )
    preset_runtime = harness.runtime.get_settings_read_only(db_session)
    assert preset_runtime["current_operation_mode"] == "full_live_test_mode"
    harness.runtime.update_settings(db_session, {setting: value})

    result = run_scheduler(harness)
    profile_result = result.get("profile_buy") or {}
    gate = profile_result.get("live_order_gate") or {}
    runtime = harness.runtime.get_settings_read_only(db_session)

    # Fault injection changes the computed display mode, while the scheduler
    # retains the preset-synchronized live execution authority for this gate.
    assert runtime["automation_mode"] == "live"
    assert gate["automation_mode"] == "live"
    assert gate["scheduler_allowed"] is True
    assert gate["allowed"] is False
    assert gate["blocking_reasons"] == [expected_reason]
    assert profile_result["reason"] == expected_reason
    assert harness.validation.calls == []
    assert harness.broker.buy_calls == []
    assert harness.client.external_kis_submit_count == 0

def test_stale_paper_requested_mode_cannot_override_live_preset_execution(

    db_session, monkeypatch
):
    harness = build_harness(db_session, monkeypatch)
    harness.runtime.apply_preset(
        db_session,
        preset="full_live_test_mode",
        confirm_dangerous=True,
    )
    # This reproduces the old compatibility metadata drift. Execution authority
    # must remain the preset-synchronized automation_mode, never this field.
    harness.runtime.update_settings(db_session, {"operation_mode_requested": "paper"})

    result = run_scheduler(harness)

    runtime = harness.runtime.get_settings_read_only(db_session)
    authority = AutomationExecutionAuthorityService(harness.runtime).snapshot(db_session)
    assert runtime["current_operation_mode"] == "full_live_test_mode"
    assert runtime["operation_mode_requested"] == "paper"
    assert authority["automation_mode"] == "live"
    assert result["profile_buy"]["broker_submit_called"] is True
    assert len(harness.broker.buy_calls) == 1
    assert len(harness.validation.calls) == 1
    assert harness.client.external_kis_submit_count == 0


def test_tomorrow_profile_slots_are_deterministic_and_do_not_duplicate_analysis(
    db_session, monkeypatch
):
    harness = build_harness(
        db_session,
        monkeypatch,
        candidates=[candidate(score=62.0)],
    )
    row = harness.profiles.get(db_session, CUSTOM_PROFILE_KEY)
    settings = json.loads(row.settings_json or "{}")
    settings["entry"]["analysis_times"] = ["09:30", "11:30", "13:30"]
    settings["entry"]["min_final_score"] = 65.0
    settings["entry"]["max_new_entries_per_day"] = 1
    settings["entry"]["max_entries_per_scan"] = 1
    settings["entry"]["no_new_entry_after"] = "14:00"
    settings["operation"].update(
        {
            "start_date": "2026-08-31",
            "end_date": "2026-09-04",
            "weekdays_only": True,
            "timezone": "Asia/Seoul",
        }
    )
    row.settings_json = json.dumps(settings)
    db_session.commit()
    harness.runtime.apply_preset(db_session, preset="dry_run_simulation")

    for slot in ("09:30", "11:30", "13:30"):
        hour, minute = (int(value) for value in slot.split(":"))
        now = datetime(2026, 9, 1, hour - 9, minute, tzinfo=UTC)
        harness.clock.current = now
        result = harness.scheduler._run_strategy_auto_buy_dry_run_scheduled_once(
            slot,
            now=now,
        )
        assert result["dry_run"]["scheduled_slot_key"] == (
            f"{CUSTOM_PROFILE_KEY}:2026-09-01:{slot}"
        )
        assert result["dry_run"]["analysis_completed"] is True
        assert result["dry_run"]["dry_run_result"]["required_entry_score"] == 65.0
        assert result["profile_buy"]["reason"] == "below_profile_buy_threshold"
        assert result["profile_buy"]["broker_submit_called"] is False

    assert len(harness.preview.calls) == 3
    assert harness.broker.buy_calls == []
    assert harness.client.external_kis_submit_count == 0
