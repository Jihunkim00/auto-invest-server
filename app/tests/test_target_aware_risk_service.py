from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.models import OrderLog
from app.schemas.strategy_risk import StrategyEntryRiskEvaluationRequest
from app.services.strategy_profile_service import StrategyProfileService
from app.services.strategy_risk_budget_service import StrategyRiskBudgetService
from app.services.target_aware_risk_service import TargetAwareRiskService


class _Performance:
    def __init__(
        self,
        *,
        monthly_return: float = 0,
        daily_return: float = 0,
        target_progress: float = 0,
        target_hit: bool = False,
        monthly_notes: list[str] | None = None,
        daily_notes: list[str] | None = None,
        trades: list[dict] | None = None,
    ) -> None:
        self.monthly_return = monthly_return
        self.daily_return = daily_return
        self.target_progress = target_progress
        self.target_hit = target_hit
        self.monthly_notes = monthly_notes or []
        self.daily_notes = daily_notes or []
        self.trade_items = trades or []
        self.position_loader = lambda db, provider, market: []

    def monthly(self, db, *, provider="kis", market="KR"):
        return {
            "current_month_return_pct": self.monthly_return,
            "target_progress_pct": self.target_progress,
            "target_hit": self.target_hit,
            "loss_budget_used_pct": 0,
            "data_quality": {"notes": self.monthly_notes},
        }

    def daily(self, db, *, provider="kis", market="KR"):
        return {
            "pnl_pct": self.daily_return,
            "data_quality": {"notes": self.daily_notes},
        }

    def trades(self, db, *, provider="kis", market="KR", limit=100):
        return {
            "items": self.trade_items,
            "data_quality": {"notes": []},
        }


def _service(
    performance: _Performance | None = None,
    *,
    positions: list[dict] | None = None,
    balance: dict | None = None,
) -> TargetAwareRiskService:
    position_rows = positions if positions is not None else []
    balance_payload = balance if balance is not None else {"total_asset_value": 1_000_000}
    return TargetAwareRiskService(
        budget_service=StrategyRiskBudgetService(
            performance_service=performance or _Performance(),
            position_loader=lambda db, provider, market: position_rows,
            balance_loader=lambda db, provider, market: balance_payload,
        )
    )


def _request(**overrides) -> StrategyEntryRiskEvaluationRequest:
    values = {
        "provider": "kis",
        "market": "KR",
        "symbol": "005930",
        "side": "buy",
        "requested_notional_krw": 20_000,
        "buy_score": 80,
        "dry_run": True,
    }
    values.update(overrides)
    return StrategyEntryRiskEvaluationRequest(**values)


def test_default_risk_state_uses_safe_profile(db_session):
    result = _service().risk_state(db_session)

    assert result["active_profile"] == "safe"
    assert result["new_entries_allowed"] is True
    assert result["max_order_notional_krw"] == 30000


def test_monthly_loss_limit_blocks_new_entries(db_session):
    result = _service(_Performance(monthly_return=-0.02)).evaluate_entry(
        db_session,
        _request(),
    )

    assert result["approved"] is False
    assert result["block_reason"] == "monthly_loss_limit_hit"
    assert "monthly_loss_limit_hit" in result["risk_flags"]


def test_daily_loss_limit_blocks_new_entries(db_session):
    result = _service(_Performance(daily_return=-0.005)).evaluate_entry(
        db_session,
        _request(),
    )

    assert result["approved"] is False
    assert result["block_reason"] == "daily_loss_limit_hit"


def test_safe_target_hit_blocks_new_entries(db_session):
    result = _service(
        _Performance(monthly_return=0.015, target_progress=100, target_hit=True)
    ).evaluate_entry(db_session, _request())

    assert result["approved"] is False
    assert result["block_reason"] == "monthly_target_hit_entry_blocked"


def test_balanced_target_near_eighty_percent_reduces_size(db_session):
    StrategyProfileService().apply_preset(
        db_session,
        profile_name="balanced",
        confirm_operator_ack=True,
    )
    result = _service(
        _Performance(monthly_return=0.032, target_progress=80)
    ).evaluate_entry(
        db_session,
        _request(requested_notional_krw=40_000, buy_score=70),
    )

    assert result["approved"] is True
    assert result["action"] == "reduce"
    assert result["approved_notional_krw"] == 20_000
    assert "near_monthly_target_size_reduced" in result["risk_flags"]


def test_consecutive_losses_reduce_size(db_session):
    trades = [
        {"realized_pnl": -100, "closed_at": datetime.now(UTC)},
        {"realized_pnl": -50, "closed_at": datetime.now(UTC)},
    ]
    StrategyProfileService().apply_preset(
        db_session,
        profile_name="balanced",
        confirm_operator_ack=True,
    )
    result = _service(_Performance(trades=trades)).evaluate_entry(
        db_session,
        _request(requested_notional_krw=40_000, buy_score=70),
    )

    assert result["approved"] is True
    assert result["approved_notional_krw"] == 20_000
    assert "consecutive_loss_size_reduced" in result["risk_flags"]


def test_daily_trade_limit_blocks_new_entries(db_session):
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="buy",
            order_type="market",
            qty=1,
            internal_status="SUBMITTED",
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    result = _service().evaluate_entry(db_session, _request())

    assert result["approved"] is False
    assert result["block_reason"] == "daily_trade_limit_hit"


def test_max_positions_blocks_new_entries(db_session):
    positions = [
        {"symbol": "005930", "qty": 1},
        {"symbol": "000660", "qty": 1},
    ]
    result = _service(positions=positions).evaluate_entry(db_session, _request())

    assert result["approved"] is False
    assert result["block_reason"] == "max_positions_hit"


def test_buy_score_below_profile_threshold_blocks_entry(db_session):
    result = _service().evaluate_entry(
        db_session,
        _request(buy_score=74),
    )

    assert result["approved"] is False
    assert result["block_reason"] == "below_profile_buy_threshold"


def test_aggressive_profile_has_lower_buy_threshold_than_safe(db_session):
    service = _service()
    safe = service.evaluate_entry(db_session, _request(buy_score=65))
    StrategyProfileService().apply_preset(
        db_session,
        profile_name="aggressive",
        confirm_operator_ack=True,
    )
    aggressive = service.evaluate_entry(db_session, _request(buy_score=65))

    assert safe["approved"] is False
    assert aggressive["approved"] is True
    assert aggressive["profile_thresholds"]["buy_score_threshold"] == 62


def test_requested_notional_above_max_is_capped(db_session):
    result = _service().evaluate_entry(
        db_session,
        _request(requested_notional_krw=100_000),
    )

    assert result["approved"] is True
    assert result["action"] == "reduce"
    assert result["approved_notional_krw"] == 20_000
    assert "notional_capped_by_profile" in result["risk_flags"]


@pytest.mark.parametrize("value", [0, -1])
def test_zero_or_negative_requested_notional_blocks_entry(db_session, value):
    result = _service().evaluate_entry(
        db_session,
        _request(requested_notional_krw=value),
    )

    assert result["approved"] is False
    assert result["block_reason"] == "invalid_requested_notional"


def test_missing_performance_data_returns_conservative_warning(db_session):
    result = _service(
        _Performance(monthly_notes=["insufficient_cost_basis"])
    ).evaluate_entry(db_session, _request())

    assert result["approved"] is True
    assert result["action"] == "reduce"
    assert result["sizing_multiplier"] == 0.5
    assert "performance_data_quality_limited" in result["risk_flags"]
    assert result["safety"]["validation_called"] is False
    assert result["safety"]["real_order_submitted"] is False
