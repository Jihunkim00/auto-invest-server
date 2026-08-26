from __future__ import annotations

from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.schemas.strategy_risk import StrategyEntryRiskEvaluationRequest
from app.services.automation_profile_service import AutomationProfileService
from app.services.automation_profile_buy_scheduler_service import (
    AutomationProfileBuySchedulerService,
)
from app.services.strategy_profile_sizing_service import StrategyProfileSizingService
from app.services.strategy_risk_budget_service import StrategyRiskBudgetService
from app.services.target_aware_risk_service import TargetAwareRiskService


class _ValidPerformance:
    position_loader = staticmethod(lambda db, provider, market: [])

    def monthly(self, db, *, provider="kis", market="KR", profile_name=None):
        return {
            "current_month_return_pct": 0,
            "target_progress_pct": 0,
            "target_hit": False,
            "loss_budget_used_pct": 0,
            "data_quality": {"notes": []},
        }

    def daily(self, db, *, provider="kis", market="KR"):
        return {"pnl_pct": 0, "data_quality": {"notes": []}}

    def trades(self, db, *, provider="kis", market="KR", limit=100):
        return {"items": [], "data_quality": {"notes": []}}


def _profile(db_session, *, key="pr110-fixed", fixed_budget=500_000, max_order=500_000):
    service = AutomationProfileService()
    created = service.create(
        db_session,
        AutomationProfileWriteRequest(
            profile_key=key,
            name="PR110 fixed budget",
            provider="kis",
            market="KR",
            enabled=True,
            status="scheduled",
            capital={
                "sizing_mode": "fixed_budget",
                "fixed_budget": fixed_budget,
                "target_position_pct": 10,
                "max_position_pct": 10,
                "max_total_exposure_pct": 10,
                "max_order_notional_krw": max_order,
                "cash_only": True,
            },
            entry={"analysis_times": ["09:10"], "min_final_score": 65},
            operation={
                "start_date": "2026-08-01",
                "end_date": "2026-09-30",
                "weekdays_only": False,
                "timezone": "Asia/Seoul",
            },
        ),
    )
    service.activate(db_session, str(created["id"]))
    return service, created


def _risk(db_session, *, balance, positions=None, performance=None):
    position_rows = [] if positions is None else positions
    return TargetAwareRiskService(
        budget_service=StrategyRiskBudgetService(
            performance_service=performance or _ValidPerformance(),
            position_loader=lambda db, provider, market: position_rows,
            balance_loader=lambda db, provider, market: balance,
        )
    )


def _request(**overrides):
    values = {
        "provider": "kis",
        "market": "KR",
        "symbol": "196170",
        "side": "buy",
        "requested_notional_krw": 500_000,
        "buy_score": 80,
        "dry_run": True,
    }
    values.update(overrides)
    return StrategyEntryRiskEvaluationRequest(**values)


def test_fixed_budget_ignores_legacy_equity_percentage_cap(db_session):
    profiles, created = _profile(db_session)
    loaded = profiles.serialize(profiles.get(db_session, created["profile_key"]))
    assert loaded["capital"]["sizing_mode"] == "fixed_budget"
    assert loaded["capital"]["fixed_budget"] == 500_000
    result = _risk(
        db_session,
        balance={"cash": 601_456, "orderable_cash": 601_456, "total_asset_value": 601_456},
    ).evaluate_entry(db_session, _request(), profile_name=created["profile_key"])

    assert result["sizing_mode"] == "fixed_budget"
    assert result["base_order_cap_krw"] == 500_000
    assert result["effective_max_order_notional_krw"] == 500_000
    assert result["approved_notional_krw"] == 500_000
    assert result["order_cap_source"] == "fixed_budget"
    assert result["data_quality_limited"] is False


def test_equity_percentage_mode_retains_percentage_sizing(db_session):
    service, created = _profile(db_session, key="pr110-equity")
    service.update(
        db_session,
        str(created["id"]),
        AutomationProfileWriteRequest(
            capital={"sizing_mode": "equity_pct", "target_position_pct": 10}
        ),
    )
    result = _risk(
        db_session,
        balance={"cash": 601_456, "orderable_cash": 601_456, "total_asset_value": 601_456},
    ).evaluate_entry(db_session, _request(), profile_name=created["profile_key"])

    assert result["sizing_mode"] == "equity_pct"
    assert result["base_order_cap_krw"] == 60_145.6
    assert result["approved_notional_krw"] == 60_145.6
    assert result["order_cap_source"] == "equity_pct"


def test_fixed_budget_and_legitimate_risk_reduction_are_separate(db_session):
    _, created = _profile(db_session, key="pr110-reduced")
    performance = _ValidPerformance()
    performance.monthly = lambda db, **kwargs: {
        "current_month_return_pct": 0,
        "target_progress_pct": 80,
        "target_hit": False,
        "loss_budget_used_pct": 0,
        "data_quality": {"notes": []},
    }
    result = _risk(
        db_session,
        balance={"cash": 601_456, "orderable_cash": 601_456, "total_asset_value": 601_456},
        performance=performance,
    ).evaluate_entry(db_session, _request(), profile_name=created["profile_key"])

    assert result["base_order_cap_krw"] == 500_000
    assert result["sizing_multiplier"] == 0.5
    assert result["approved_notional_krw"] == 250_000


def test_fixed_budget_is_limited_by_cash(db_session):
    _, created = _profile(db_session, key="pr110-cash")
    result = _risk(
        db_session,
        balance={"cash": 200_000, "orderable_cash": 200_000, "total_asset_value": 601_456},
    ).evaluate_entry(db_session, _request(), profile_name=created["profile_key"])

    assert result["base_order_cap_krw"] == 200_000
    assert result["available_cash_krw"] == 200_000
    assert result["order_cap_source"] == "cash_limited"


def test_fixed_budget_keeps_global_hard_cap(db_session):
    _, created = _profile(
        db_session,
        key="pr110-hard-cap",
        fixed_budget=2_000_000,
        max_order=2_000_000,
    )
    result = _risk(
        db_session,
        balance={"cash": 2_000_000, "orderable_cash": 2_000_000, "total_asset_value": 2_000_000},
    ).evaluate_entry(db_session, _request(requested_notional_krw=2_000_000), profile_name=created["profile_key"])

    assert result["base_order_cap_krw"] == 1_000_000
    assert result["hard_max_order_notional_krw"] == 1_000_000
    assert result["order_cap_source"] == "hard_cap_limited"


def test_empty_positions_and_no_history_are_valid_data_states(db_session):
    _, created = _profile(db_session, key="pr110-empty")
    result = _risk(
        db_session,
        balance={"cash": 601_456, "orderable_cash": 601_456, "total_asset_value": 601_456},
        positions=[],
    ).evaluate_entry(db_session, _request(), profile_name=created["profile_key"])

    assert result["data_quality_limited"] is False
    assert result["data_quality_notes"] == []
    assert result["sizing_multiplier"] == 1


def test_invalid_positions_payload_is_reported_as_limited_data(db_session):
    _, created = _profile(db_session, key="pr110-invalid-positions")
    result = _risk(
        db_session,
        balance={"cash": 601_456, "orderable_cash": 601_456, "total_asset_value": 601_456},
        positions={"unexpected": "payload"},
    ).evaluate_entry(db_session, _request(), profile_name=created["profile_key"])

    assert result["data_quality_limited"] is True
    assert "positions_unavailable:invalid_payload" in result["data_quality_notes"]


def test_unavailable_account_input_keeps_conservative_reduction(db_session):
    _, created = _profile(db_session, key="pr110-quality-failure")
    service = TargetAwareRiskService(
        budget_service=StrategyRiskBudgetService(
            performance_service=_ValidPerformance(),
            position_loader=lambda db, provider, market: (_ for _ in ()).throw(
                RuntimeError("broker unavailable")
            ),
            balance_loader=lambda db, provider, market: {
                "cash": 601_456,
                "orderable_cash": 601_456,
                "total_asset_value": 601_456,
            },
        )
    )
    result = service.evaluate_entry(
        db_session, _request(), profile_name=created["profile_key"]
    )

    assert result["data_quality_limited"] is True
    assert any("positions_unavailable" in note for note in result["data_quality_notes"])
    assert result["data_quality_reduction_reasons"]
    assert result["sizing_multiplier"] <= 0.5


def test_scheduler_default_risk_path_uses_kis_account_state(db_session):
    _, created = _profile(db_session, key="aut_kis_eaa46d83")

    class FakeKisClient:
        def list_positions(self):
            return []

        def get_account_balance(self):
            return {
                "cash": 601_456,
                "orderable_cash": 601_456,
                "total_asset_value": 601_456,
            }

    scheduler = AutomationProfileBuySchedulerService(client=FakeKisClient())
    result = scheduler.target_risk_service.evaluate_entry(
        db_session,
        _request(),
        profile_name=created["profile_key"],
    )

    assert result["sizing_mode"] == "fixed_budget"
    assert result["base_order_cap_krw"] == 500_000
    assert result["data_quality_limited"] is False
    assert "positions_not_loaded" not in result["data_quality_notes"]
    assert "balance_not_loaded" not in result["data_quality_notes"]


def test_fixed_budget_quantity_is_computed_normally_without_forcing_one_share():
    settings = {
        "capital": {
            "sizing_mode": "fixed_budget",
            "fixed_budget": 500_000,
            "target_position_pct": 10,
            "max_position_pct": 100,
            "max_total_exposure_pct": 100,
            "max_order_notional_krw": 500_000,
        },
        "max_open_positions": 1,
    }
    can_buy = StrategyProfileSizingService.calculate(
        settings,
        equity=601_456,
        orderable_cash=601_456,
        current_price=300_000,
    )
    too_expensive = StrategyProfileSizingService.calculate(
        settings,
        equity=601_456,
        orderable_cash=601_456,
        current_price=600_000,
    )

    assert can_buy["base_order_cap_krw"] == 500_000
    assert can_buy["quantity"] == 1
    assert too_expensive["quantity"] == 0
