from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import MethodType
from typing import Any

import pytest

from app.core.enums import InternalOrderStatus
from app.db.models import (
    AutomationProfileBuyReservation,
    OrderLog,
    PositionLifecycle,
    SignalLog,
    TradeRunLog,
)
from app.services.automation_execution_authority_service import (
    AutomationExecutionAuthorityService,
)
from app.services.automation_profile_buy_scheduler_service import (
    AutomationProfileBuySchedulerService,
)
from app.services.automation_profile_service import AutomationProfileService
from app.services.kis_automation_execution_core import KisAutomationExecutionCore
from app.services.kis_order_sync_service import KisOrderSyncService
from app.services.kis_position_lifecycle_service import KisPositionLifecycleService
from app.services.profile_aware_dry_run_auto_buy_service import (
    ProfileAwareDryRunAutoBuyService,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.scheduler_service import SchedulerService
from app.services.strategy_auto_buy_scheduler_service import (
    StrategyAutoBuySchedulerService,
)
from app.services.strategy_profile_service import StrategyProfileService
from app.services.strategy_risk_budget_service import StrategyRiskBudgetService
from app.services.target_aware_risk_service import TargetAwareRiskService

from app.tests.integration.test_kis_automation_scheduler_replay import (
    CUSTOM_PROFILE_KEY,
    SYMBOL,
    UTC_NOW,
    FakeBroker,
    ReplayHarness,
    build_harness,
    candidate,
)


KST = "Asia/Seoul"
T_0910 = UTC_NOW
T_1130 = datetime(2026, 8, 25, 2, 30, tzinfo=UTC)
T_1330 = datetime(2026, 8, 25, 4, 30, tzinfo=UTC)
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "kis_replay"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class LifecycleFakeBroker(FakeBroker):
    def __init__(self, client: Any) -> None:
        super().__init__(client)
        if not hasattr(client, "order_executions"):
            client.order_executions = {}

    def _execution_row(
        self,
        broker_order_id: str,
        *,
        symbol: str,
        qty: int,
        price: float,
    ) -> dict[str, Any]:
        return {
            "ODNO": broker_order_id,
            "PDNO": symbol,
            "ord_qty": qty,
            "tot_ccld_qty": qty,
            "rmn_qty": 0,
            "avg_prvs": price,
            "status": "filled",
        }

    def submit_market_buy(self, *, symbol: str, qty: int) -> dict[str, Any]:
        result = super().submit_market_buy(symbol=symbol, qty=qty)
        price = float(self.client.get_domestic_stock_price(symbol)["current_price"])
        self.client.cash -= price * qty
        self.client.positions = [
            {
                "symbol": symbol,
                "qty": qty,
                "current_price": price,
                "avg_entry_price": price,
                "cost_basis": price * qty,
            }
        ]
        self.client.order_executions[result["broker_order_id"]] = self._execution_row(
            result["broker_order_id"],
            symbol=symbol,
            qty=qty,
            price=price,
        )
        return result

    def submit_market_sell(self, *, symbol: str, qty: int) -> dict[str, Any]:
        result = super().submit_market_sell(symbol=symbol, qty=qty)
        price = float(self.client.get_domestic_stock_price(symbol)["current_price"])
        self.client.cash += price * qty
        self.client.positions = []
        self.client.order_executions[result["broker_order_id"]] = self._execution_row(
            result["broker_order_id"],
            symbol=symbol,
            qty=qty,
            price=price,
        )
        return result


def install_real_lifecycle_wiring(
    harness: ReplayHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> ReplayHarness:
    client = harness.client
    client.order_executions = getattr(client, "order_executions", {})

    def inquire_daily_order_executions(
        self: Any,
        *,
        order_no: str,
        start_date: Any,
        end_date: Any,
    ) -> dict[str, Any]:
        row = self.order_executions.get(str(order_no))
        return {"orders": [row]} if row is not None else {"orders": []}
    client.inquire_daily_order_executions = MethodType(
        inquire_daily_order_executions,
        client,
    )

    def forbidden_real_submit(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("real KIS transport submit must not be called")

    client.submit_order = forbidden_real_submit
    client.submit_domestic_cash_order = forbidden_real_submit

    broker = LifecycleFakeBroker(client)
    validation = harness.validation
    runtime = harness.runtime
    market_sessions = harness.market_sessions
    preview = harness.preview

    profiles = AutomationProfileService(runtime_settings=runtime)
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

    lifecycle = KisPositionLifecycleService(
        client,
        runtime_settings=runtime,
        now_provider=harness.clock.now,
    )
    sync = KisOrderSyncService(client, now_provider=harness.clock.now)
    execution_core = KisAutomationExecutionCore(
        client,
        broker=broker,
        validation_service=validation,
        order_sync_service=sync,
        lifecycle_service=lifecycle,
        runtime_settings=runtime,
        positions_loader=lambda _db: client.list_positions(),
        open_orders_loader=lambda _db: client.list_open_orders(),
        now_provider=harness.clock.now,
    )
    profile_buy = AutomationProfileBuySchedulerService(
        client=client,
        broker=broker,
        validation_service=validation,
        order_sync_service=sync,
        lifecycle_service=lifecycle,
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
    monkeypatch.setattr(
        "app.services.scheduler_service.SessionLocal",
        lambda: harness.db,
    )

    harness.broker = broker
    harness.validation = validation
    harness.sync = sync
    harness.runtime = runtime
    harness.profiles = profiles
    harness.scheduler = scheduler
    harness.strategy_scheduler = strategy_scheduler
    harness.profile_buy = profile_buy
    harness.lifecycle = lifecycle
    return harness


def configure_full_profile(harness: ReplayHarness) -> None:
    row = harness.profiles.get(harness.db, CUSTOM_PROFILE_KEY)
    settings = json.loads(row.settings_json or "{}")
    settings.setdefault("entry", {})["analysis_times"] = ["09:10", "11:30", "13:30"]
    settings["entry"]["max_new_entries_per_day"] = 2
    settings.setdefault("exit", {}).update(
        {
            "stop_loss_enabled": True,
            "stop_loss_pct": 2.0,
            "take_profit_enabled": True,
            "take_profit_pct": 8.0,
        }
    )
    row.settings_json = json.dumps(settings)
    row.max_trades_per_day = 2
    row.stop_loss_pct = -0.02
    row.take_profit_pct = 0.08
    harness.db.commit()


def full_harness(
    db: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    values: list[dict[str, Any]] | None = None,
) -> ReplayHarness:
    harness = build_harness(db, monkeypatch, candidates=values)
    configure_full_profile(harness)
    return install_real_lifecycle_wiring(harness, monkeypatch)


def set_candidates(harness: ReplayHarness, values: list[dict[str, Any]]) -> None:
    harness.preview.candidates = [dict(item) for item in values]
    harness.client.candidates = [dict(item) for item in values]


def run_slot(
    harness: ReplayHarness,
    slot_name: str,
    now: datetime,
) -> Any:
    harness.clock.current = now
    return harness.scheduler._run_strategy_auto_buy_dry_run_scheduled_once(
        slot_name,
        now=now,
    )


def run_entry(
    harness: ReplayHarness,
    *,
    slot_name: str = "strategy_auto_buy_dry_run_open_phase",
    now: datetime = T_0910,
) -> dict[str, Any]:
    result = run_slot(harness, slot_name, now)
    assert isinstance(result, dict)
    assert result["profile_buy"]["action"] == "buy"
    assert result["profile_buy"]["status"] == "filled"
    return result


def run_management(
    harness: ReplayHarness,
    *,
    now: datetime,
    slot: str,
) -> dict[str, Any]:
    result = harness.lifecycle.run_management_once(
        harness.db,
        execute=False,
        trigger_source="position_management_scheduler",
        scheduler_slot=slot,
        now=now,
    )
    assert result["managed_count"] == 1
    return result


def set_price(
    harness: ReplayHarness,
    *,
    symbol: str = SYMBOL,
    price: float,
    score: float = 70.0,
) -> None:
    set_candidates(
        harness,
        [candidate(symbol=symbol, price=price, score=score)],
    )


def exit_once(harness: ReplayHarness, price: float) -> dict[str, Any]:
    set_price(harness, price=price)
    return harness.profile_buy.manage_exit_once(
        harness.db,
        current_price=price,
        now=harness.clock.now(),
    )


def assert_no_real_transport(harness: ReplayHarness) -> None:
    assert harness.client.external_kis_submit_count == 0
    assert not hasattr(harness.client, "real_order_submitted") or (
        harness.client.real_order_submitted is False
    )

def test_virtual_0910_score70_buys_and_opens_lifecycle(db_session, monkeypatch):
    entry = load_fixture("score_pass_entry.json")
    harness = full_harness(
        db_session,
        monkeypatch,
        values=[
            candidate(
                score=entry["final_buy_score"],
                price=entry["entry_price"],
                symbol=entry["symbol"],
            )
        ],
    )

    result = run_entry(harness)

    assert result["dry_run"]["dry_run_result"]["profile_key"] == CUSTOM_PROFILE_KEY
    assert result["profile_buy"]["final_buy_score"] == 70.0
    assert result["profile_buy"]["required_entry_score"] == 65.0
    assert result["profile_buy"]["quantity"] == 1
    assert len(harness.broker.buy_calls) == 1
    assert harness.broker.buy_calls[0]["symbol"] == SYMBOL
    assert db_session.query(OrderLog).filter(OrderLog.side == "buy").count() == 2
    order = db_session.get(OrderLog, result["profile_buy"]["order_id"])
    assert order is not None
    assert order.internal_status == InternalOrderStatus.FILLED.value
    assert order.broker_order_id.startswith("FAKE-KIS-")
    assert order.kis_odno == order.broker_order_id
    assert order.last_synced_at is not None
    assert order.sync_error is None
    lifecycle = db_session.query(PositionLifecycle).one()
    assert lifecycle.status == "open"
    assert lifecycle.entry_price == 80000
    assert lifecycle.take_profit_threshold_pct == 8
    assert lifecycle.stop_loss_threshold_pct == 2
    assert harness.client.positions[0]["symbol"] == SYMBOL
    assert db_session.query(SignalLog).count() == 1
    assert db_session.query(TradeRunLog).count() >= 3
    reservation = db_session.query(AutomationProfileBuyReservation).one()
    assert reservation.status == "filled"
    assert reservation.profile_key == CUSTOM_PROFILE_KEY
    assert_no_real_transport(harness)


def test_virtual_0910_score64_does_not_buy(db_session, monkeypatch):
    entry = load_fixture("score_fail_entry.json")
    harness = full_harness(
        db_session,
        monkeypatch,
        values=[
            candidate(
                score=entry["final_buy_score"],
                price=entry["entry_price"],
                symbol=entry["symbol"],
            )
        ],
    )

    result = run_slot(
        harness,
        "strategy_auto_buy_dry_run_open_phase",
        T_0910,
    )

    assert result["profile_buy"]["reason"] == "below_profile_buy_threshold"
    assert result["profile_buy"]["action"] == "hold"
    assert harness.broker.buy_calls == []
    assert harness.validation.calls == []
    assert db_session.query(PositionLifecycle).count() == 0
    assert db_session.query(AutomationProfileBuyReservation).count() == 0
    assert harness.client.positions == []
    assert_no_real_transport(harness)

    set_price(harness, price=80000, score=70)
    next_scan = run_slot(
        harness,
        "strategy_auto_buy_dry_run_midday",
        T_1130,
    )
    assert next_scan["profile_buy"]["status"] == "filled"
    assert len(harness.broker.buy_calls) == 1


def test_open_position_preempts_score80_new_candidate(db_session, monkeypatch):
    harness = full_harness(db_session, monkeypatch, values=[candidate()])
    run_entry(harness)

    set_candidates(
        harness,
        [
            candidate(symbol="000660", price=50000, score=80),
            candidate(symbol=SYMBOL, price=80000, score=70),
        ],
    )
    priority = run_slot(
        harness,
        "strategy_auto_buy_dry_run_midday",
        T_1130,
    )

    assert getattr(priority, "reason", None) == "position_management_priority_buy_skipped"
    assert len(harness.broker.buy_calls) == 1
    assert harness.client.positions[0]["symbol"] == SYMBOL
    assert harness.runtime.get_settings_read_only(db_session)[
        "automation_profile_scheduler_enabled"
    ] is True
    assert harness.runtime.get_settings_read_only(db_session)[
        "active_automation_profile_key"
    ] == CUSTOM_PROFILE_KEY

    set_price(harness, price=80000)
    management = run_management(harness, now=T_1130, slot="11:30")
    assert management["items"][0]["action"] == "HOLD"
    assert management["items"][0]["reason"] == "no_exit_condition"


def test_take_profit_7_9_holds(db_session, monkeypatch):
    tp = load_fixture("position_take_profit.json")
    harness = full_harness(db_session, monkeypatch, values=[candidate()])
    run_entry(harness)
    result = exit_once(harness, tp["prices"]["hold"])

    assert result["status"] == "hold"
    assert result["reason"] == "no_exit_condition"
    assert len(harness.broker.sell_calls) == 0
    assert db_session.query(PositionLifecycle).one().status == "open"


def test_take_profit_8_1_sells_and_closes(db_session, monkeypatch):
    tp = load_fixture("position_take_profit.json")
    harness = full_harness(db_session, monkeypatch, values=[candidate()])
    run_entry(harness)
    result = exit_once(harness, tp["prices"]["trigger"])

    assert result["reason"] == "take_profit_triggered"
    assert result["status"] == "closed"
    assert len(harness.broker.sell_calls) == 1
    sell = db_session.query(OrderLog).filter(OrderLog.side == "sell").one()
    assert sell.internal_status == InternalOrderStatus.FILLED.value
    assert sell.broker_order_id.startswith("FAKE-KIS-")
    assert sell.kis_odno == sell.broker_order_id
    assert sell.last_synced_at is not None
    assert sell.sync_error is None
    assert db_session.query(PositionLifecycle).one().status == "closed"
    assert harness.client.positions == []
    assert_no_real_transport(harness)


def test_stop_loss_1_9_holds(db_session, monkeypatch):
    sl = load_fixture("position_stop_loss.json")
    harness = full_harness(db_session, monkeypatch, values=[candidate()])
    run_entry(harness)
    result = exit_once(harness, sl["prices"]["hold"])

    assert result["status"] == "hold"
    assert result["reason"] == "no_exit_condition"
    assert len(harness.broker.sell_calls) == 0
    assert db_session.query(PositionLifecycle).one().status == "open"


def test_stop_loss_2_1_sells_and_closes(db_session, monkeypatch):
    sl = load_fixture("position_stop_loss.json")
    harness = full_harness(db_session, monkeypatch, values=[candidate()])
    run_entry(harness)
    result = exit_once(harness, sl["prices"]["trigger"])

    assert result["reason"] == "stop_loss_triggered"
    assert result["status"] == "closed"
    assert len(harness.broker.sell_calls) == 1
    assert db_session.query(OrderLog).filter(OrderLog.side == "sell").one().internal_status == InternalOrderStatus.FILLED.value
    assert db_session.query(PositionLifecycle).one().status == "closed"
    assert_no_real_transport(harness)

@pytest.mark.parametrize(
    "kind,multiplier,should_sell",
    [
        ("tp", 1.0799, False),
        ("tp", 1.0800, True),
        ("tp", 1.0801, True),
        ("sl", 0.9801, False),
        ("sl", 0.9800, True),
        ("sl", 0.9799, True),
    ],
)
def test_exact_tp_sl_boundaries(
    db_session,
    monkeypatch,
    kind: str,
    multiplier: float,
    should_sell: bool,
):
    harness = full_harness(db_session, monkeypatch, values=[candidate()])
    run_entry(harness)
    result = exit_once(harness, 80000 * multiplier)

    assert (len(harness.broker.sell_calls) == 1) is should_sell
    assert (db_session.query(PositionLifecycle).one().status == "closed") is should_sell
    if should_sell:
        assert result["status"] == "closed"
    else:
        assert result["status"] == "hold"


def test_restart_recovers_open_position(db_session, monkeypatch):
    harness = full_harness(db_session, monkeypatch, values=[candidate()])
    run_entry(harness)
    old_lifecycle_id = db_session.query(PositionLifecycle).one().id

    restarted = install_real_lifecycle_wiring(harness, monkeypatch)
    priority = run_slot(restarted, "strategy_auto_buy_dry_run_midday", T_1130)

    assert getattr(priority, "reason", None) == "position_management_priority_buy_skipped"
    assert restarted.broker.buy_calls == []
    assert db_session.query(PositionLifecycle).one().id == old_lifecycle_id
    set_price(restarted, price=80000)
    management = run_management(restarted, now=T_1130, slot="11:30")
    assert management["items"][0]["status"] == "open"
    assert management["items"][0]["action"] == "HOLD"


def test_duplicate_take_profit_callback_sells_once(db_session, monkeypatch):
    harness = full_harness(db_session, monkeypatch, values=[candidate()])
    run_entry(harness)
    first = exit_once(harness, 80000 * 1.081)
    second = exit_once(harness, 80000 * 1.081)

    assert first["status"] == "closed"
    assert second["reason"] == "no_open_lifecycle"
    assert len(harness.broker.sell_calls) == 1
    assert db_session.query(OrderLog).filter(OrderLog.side == "sell").count() == 1
    assert_no_real_transport(harness)


def test_closed_lifecycle_allows_next_entry(db_session, monkeypatch):
    harness = full_harness(
        db_session,
        monkeypatch,
        values=[candidate()],
    )
    run_entry(harness)
    exit_once(harness, 80000 * 1.081)
    assert db_session.query(PositionLifecycle).one().status == "closed"

    set_candidates(
        harness,
        [candidate(symbol="000660", price=30000, score=69)],
    )
    result = run_slot(
        harness,
        "strategy_auto_buy_dry_run_before_close",
        T_1330,
    )

    assert result["profile_buy"]["selected_symbol"] == "000660"
    assert result["profile_buy"]["status"] == "filled"
    assert len(harness.broker.buy_calls) == 2
    assert db_session.query(PositionLifecycle).filter(
        PositionLifecycle.status == "open"
    ).count() == 1
    assert db_session.query(PositionLifecycle).filter(
        PositionLifecycle.symbol == "000660",
        PositionLifecycle.status == "open",
    ).count() == 1
    assert_no_real_transport(harness)


def test_manual_run_does_not_consume_scheduled_slot(db_session, monkeypatch):
    harness = full_harness(db_session, monkeypatch, values=[candidate()])
    before = db_session.query(AutomationProfileBuyReservation).count()

    manual = harness.profile_buy.run_once(
        db_session,
        [candidate()],
        scheduler_slot="09:10",
        trigger_source="manual",
        now=T_0910,
    )

    assert manual["reason"] == "manual_execution_isolation"
    assert db_session.query(AutomationProfileBuyReservation).count() == before
    assert harness.broker.buy_calls == []

    run_entry(harness)
    assert len(harness.broker.buy_calls) == 1


def test_full_portfolio_state_is_persisted_after_tp_close(db_session, monkeypatch):
    harness = full_harness(db_session, monkeypatch, values=[candidate()])
    entry = run_entry(harness)
    exit_result = exit_once(harness, 80000 * 1.081)

    assert entry["profile_buy"]["real_external_kis_submit_count"] == 0
    assert exit_result["broker_sell_call_count"] == 1
    assert len(harness.broker.buy_calls) == 1
    assert len(harness.broker.sell_calls) == 1
    assert db_session.query(SignalLog).count() >= 1
    assert db_session.query(TradeRunLog).count() >= 3
    assert db_session.query(OrderLog).filter(
        OrderLog.internal_status == InternalOrderStatus.FILLED.value
    ).count() == 2
    assert db_session.query(PositionLifecycle).one().status == "closed"
    assert db_session.query(AutomationProfileBuyReservation).one().status == "filled"
    assert harness.client.positions == []
    assert_no_real_transport(harness)


def test_authority_snapshot_stays_automation_mode_source_of_truth(
    db_session,
    monkeypatch,
):
    harness = full_harness(db_session, monkeypatch, values=[candidate()])
    snapshot = AutomationExecutionAuthorityService(harness.runtime).snapshot(db_session)

    assert snapshot["automation_mode"] == "live"
    assert snapshot["scheduler_allowed"] is True
    assert snapshot["broker_submit_allowed"] is True
    assert snapshot["authority_snapshot_source"] == "AutomationExecutionAuthorityService"