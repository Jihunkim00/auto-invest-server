from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import OrderLog
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.automation_profile_service import AutomationProfileService
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.strategy_performance_service import StrategyPerformanceService
from app.services.strategy_profile_service import StrategyProfileService
from app.services.strategy_risk_budget_service import StrategyRiskBudgetService
from app.services.target_aware_risk_service import TargetAwareRiskService


def _create_profile(db_session, key: str, *, activate: bool = True):
    runtime = RuntimeSettingService()
    profiles = AutomationProfileService(runtime_settings=runtime)
    created = profiles.create(
        db_session,
        AutomationProfileWriteRequest(
            profile_key=key,
            name=f"Profile {key}",
            provider="kis",
            market="KR",
            enabled=True,
            status="scheduled",
            capital={
                "sizing_mode": "fixed_budget",
                "fixed_budget": 500_000,
                "target_position_pct": 10,
                "max_position_pct": 10,
                "max_total_exposure_pct": 10,
                "max_order_notional_krw": 500_000,
                "cash_only": True,
            },
            universe={"manual_symbols": ["005930"]},
            entry={
                "analysis_times": ["09:10"],
                "no_new_entry_after": "14:00",
                "max_new_entries_per_day": 1,
                "max_entries_per_scan": 1,
                "min_final_score": 65,
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
    if activate:
        profiles.activate(db_session, str(created["id"]))
    return profiles, created


def _order(
    *,
    side: str,
    symbol: str = "005930",
    price: float = 100,
    qty: float = 1,
    created_at: datetime | None = None,
    profile_key: str | None = None,
    mode: str | None = None,
    source: str | None = None,
) -> OrderLog:
    payload = {}
    if profile_key is not None:
        payload.update(
            {
                "automation_profile": True,
                "automation_profile_key": profile_key,
                "profile_key": profile_key,
            }
        )
    if mode is not None:
        payload["mode"] = mode
    if source is not None:
        payload["source"] = source
    timestamp = created_at or (datetime.now(UTC) - timedelta(minutes=1))
    return OrderLog(
        broker="kis",
        market="KR",
        symbol=symbol,
        side=side,
        order_type="market",
        qty=qty,
        requested_qty=qty,
        filled_qty=qty,
        remaining_qty=0,
        avg_fill_price=price,
        filled_avg_price=price,
        internal_status="FILLED",
        created_at=timestamp,
        submitted_at=timestamp,
        filled_at=timestamp,
        request_payload=json.dumps(payload),
    )


def _performance():
    return StrategyPerformanceService(
        position_loader=lambda db, provider, market: [],
    )


def _risk(db_session, performance: StrategyPerformanceService):
    budget = StrategyRiskBudgetService(
        strategy_profiles=StrategyProfileService(),
        runtime_settings=RuntimeSettingService(),
        performance_service=performance,
        position_loader=lambda db, provider, market: [],
        balance_loader=lambda db, provider, market: {
            "cash": 601_456,
            "orderable_cash": 601_456,
            "total_asset_value": 601_456,
        },
    )
    return TargetAwareRiskService(budget_service=budget)


def _evaluate(db_session, key: str, performance: StrategyPerformanceService):
    return _risk(db_session, performance).evaluate_entry(
        db_session,
        {
            "provider": "kis",
            "market": "KR",
            "symbol": "005930",
            "side": "buy",
            "requested_notional_krw": 500_000,
            "buy_score": 80,
            "dry_run": True,
        },
        profile_name=key,
    )


def test_legacy_manual_unmatched_sell_is_informational_only(db_session):
    _, profile = _create_profile(db_session, "aut_scope_legacy")
    db_session.add(
        _order(
            side="sell",
            symbol="036540",
            price=7_300,
            qty=2,
            created_at=datetime(2026, 6, 5, tzinfo=UTC),
            mode="manual_live",
            source="broker_external",
        )
    )
    db_session.commit()

    performance = _performance()
    trades = performance.trades(db_session, profile_name=profile["profile_key"])
    result = _evaluate(db_session, profile["profile_key"], performance)

    assert trades["data_quality"]["unmatched_sell_total_count"] == 1
    assert trades["data_quality"]["unmatched_sell_relevant_count"] == 0
    assert trades["data_quality"]["unmatched_sell_ignored_count"] == 1
    assert any(item["status"] == "unmatched_sell" for item in trades["items"])
    assert result["data_quality_limited"] is False
    assert result["data_quality_reduction_reasons"] == []
    assert result["sizing_multiplier"] == 1
    assert result["recommended_notional_krw"] == 500_000


def test_active_profile_unmatched_sell_remains_conservative(db_session):
    _, profile = _create_profile(db_session, "aut_scope_active_gap")
    db_session.add(
        _order(
            side="sell",
            qty=2,
            profile_key=profile["profile_key"],
            mode="automation_profile_scheduler_buy",
        )
    )
    db_session.commit()

    performance = _performance()
    quality = performance.monthly(
        db_session,
        profile_name=profile["profile_key"],
    )["data_quality"]
    result = _evaluate(db_session, profile["profile_key"], performance)

    assert quality["unmatched_sell_relevant_count"] == 1
    assert quality["unmatched_sell_ignored_count"] == 0
    assert "unmatched_sell" in quality["data_quality_reduction_reasons"]
    assert result["data_quality_limited"] is True
    assert "unmatched_sell" in result["data_quality_reduction_reasons"]
    assert result["sizing_multiplier"] <= 0.5
    assert result["recommended_notional_krw"] == 250_000


def test_active_profile_matched_buy_sell_has_no_quality_reduction(db_session):
    _, profile = _create_profile(db_session, "aut_scope_matched")
    timestamp = datetime.now(UTC) - timedelta(minutes=2)
    db_session.add_all(
        [
            _order(
                side="buy",
                price=100,
                profile_key=profile["profile_key"],
                created_at=timestamp,
                mode="automation_profile_scheduler_buy",
            ),
            _order(
                side="sell",
                price=110,
                profile_key=profile["profile_key"],
                created_at=timestamp + timedelta(minutes=1),
                mode="strategy_live_auto_exit",
            ),
        ]
    )
    db_session.commit()

    performance = _performance()
    trades = performance.trades(db_session, profile_name=profile["profile_key"])
    monthly = performance.monthly(
        db_session,
        profile_name=profile["profile_key"],
    )
    result = _evaluate(db_session, profile["profile_key"], performance)

    assert trades["data_quality"]["unmatched_sell_relevant_count"] == 0
    assert trades["data_quality"]["data_quality_reduction_reasons"] == []
    assert monthly["realized_pnl"] == pytest.approx(10)
    assert result["data_quality_limited"] is False
    assert result["sizing_multiplier"] == 1


def test_empty_positions_are_healthy_for_active_profile(db_session):
    _, profile = _create_profile(db_session, "aut_scope_empty_positions")

    result = _evaluate(db_session, profile["profile_key"], _performance())

    assert result["data_quality_limited"] is False
    assert result["data_quality_reduction_reasons"] == []
    assert result["sizing_multiplier"] == 1


def test_no_historical_trades_are_healthy_for_active_profile(db_session):
    _, profile = _create_profile(db_session, "aut_scope_no_history")
    performance = _performance()

    monthly = performance.monthly(
        db_session,
        profile_name=profile["profile_key"],
    )
    result = _evaluate(db_session, profile["profile_key"], performance)

    assert monthly["orders_count"] == 0
    assert monthly["realized_pnl"] == 0
    assert result["data_quality_limited"] is False
    assert result["sizing_multiplier"] == 1


def test_legacy_unmatched_sell_does_not_contaminate_active_profile_trade(
    db_session,
):
    _, profile = _create_profile(db_session, "aut_scope_mixed_history")
    old = datetime(2026, 6, 5, tzinfo=UTC)
    current = datetime.now(UTC) - timedelta(minutes=2)
    db_session.add_all(
        [
            _order(
                side="sell",
                symbol="036540",
                price=7_300,
                qty=2,
                created_at=old,
                mode="manual_live",
                source="broker_external",
            ),
            _order(
                side="buy",
                price=100,
                profile_key=profile["profile_key"],
                created_at=current,
                mode="automation_profile_scheduler_buy",
            ),
            _order(
                side="sell",
                price=110,
                profile_key=profile["profile_key"],
                created_at=current + timedelta(minutes=1),
                mode="strategy_live_auto_exit",
            ),
        ]
    )
    db_session.commit()

    performance = _performance()
    monthly = performance.monthly(
        db_session,
        profile_name=profile["profile_key"],
    )
    result = _evaluate(db_session, profile["profile_key"], performance)

    quality = monthly["data_quality"]
    assert quality["unmatched_sell_total_count"] == 1
    assert quality["unmatched_sell_relevant_count"] == 0
    assert quality["unmatched_sell_ignored_count"] == 1
    assert monthly["realized_pnl"] == pytest.approx(10)
    assert result["data_quality_limited"] is False
    assert result["sizing_multiplier"] == 1


def test_profile_scoping_is_generic_across_two_custom_profiles(db_session):
    profiles, first = _create_profile(db_session, "aut_scope_first")
    _, second = _create_profile(db_session, "aut_scope_second", activate=False)
    db_session.add(
        _order(
            side="sell",
            profile_key=second["profile_key"],
            mode="automation_profile_scheduler_buy",
        )
    )
    db_session.commit()

    first_result = _evaluate(
        db_session,
        first["profile_key"],
        _performance(),
    )
    profiles.activate(db_session, str(second["id"]))
    second_result = _evaluate(
        db_session,
        second["profile_key"],
        _performance(),
    )

    assert first_result["data_quality_limited"] is False
    assert first_result["sizing_multiplier"] == 1
    assert second_result["data_quality_limited"] is True
    assert second_result["sizing_multiplier"] <= 0.5


def test_fixed_budget_cap_stays_fixed_with_and_without_quality_reduction(
    db_session,
):
    _, profile = _create_profile(db_session, "aut_scope_fixed_budget")
    performance = _performance()

    healthy = _evaluate(db_session, profile["profile_key"], performance)
    assert healthy["base_order_cap_krw"] == 500_000
    assert healthy["effective_max_order_notional_krw"] == 500_000
    assert healthy["recommended_notional_krw"] == 500_000

    db_session.add(
        _order(
            side="sell",
            profile_key=profile["profile_key"],
            mode="automation_profile_scheduler_buy",
        )
    )
    db_session.commit()
    reduced = _evaluate(db_session, profile["profile_key"], performance)

    assert reduced["base_order_cap_krw"] == 500_000
    assert reduced["effective_max_order_notional_krw"] == 500_000
    assert reduced["sizing_multiplier"] == 0.5
    assert reduced["recommended_notional_krw"] == 250_000
