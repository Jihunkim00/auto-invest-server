from __future__ import annotations

import json

from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.schemas.strategy_dry_run_auto_buy import (
    ProfileAwareDryRunAutoBuyRequest,
)
from app.services.profile_aware_dry_run_auto_buy_service import (
    ProfileAwareDryRunAutoBuyService,
)


class FakeTargetRisk:
    def __init__(
        self,
        *,
        approved: bool = True,
        block_reason: str | None = None,
        recommended: float = 30_000,
        multiplier: float = 1,
    ) -> None:
        self.approved = approved
        self.block_reason = block_reason
        self.recommended = recommended
        self.multiplier = multiplier
        self.calls: list[dict] = []

    def evaluate_entry(self, db, request, *, profile_name=None):
        self.calls.append(
            {
                "request": dict(request),
                "profile_name": profile_name,
            }
        )
        return {
            "approved": self.approved,
            "action": "approve" if self.approved else "block",
            "symbol": request["symbol"],
            "active_profile": profile_name or "safe",
            "requested_notional_krw": request.get("requested_notional_krw"),
            "approved_notional_krw": self.recommended if self.approved else 0,
            "recommended_notional_krw": self.recommended,
            "sizing_multiplier": self.multiplier,
            "block_reason": self.block_reason,
            "risk_flags": [self.block_reason] if self.block_reason else [],
            "gating_notes": ["target-aware test gate"],
            "checks": [],
            "monthly_progress": {"target_progress_pct": 20},
            "daily_progress": {"trades_remaining_today": 1},
            "profile_thresholds": {
                "max_order_notional_pct": 0.02,
                "max_order_notional_krw": 30_000,
            },
            "safety": {
                "real_order_submitted": False,
                "validation_called": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "setting_changed": False,
                "scheduler_changed": False,
            },
        }


def candidate(
    symbol: str = "005930",
    *,
    score: float | None = 80,
    price: float | None = 10_000,
    indicator_status: str = "ok",
) -> dict:
    return {
        "symbol": symbol,
        "name": "Samsung Electronics",
        "current_price": price,
        "indicator_status": indicator_status,
        "final_buy_score": score,
        "final_entry_score": score,
        "final_sell_score": 15,
        "quant_buy_score": score,
        "confidence": 0.8,
        "entry_ready": True,
        "indicator_payload": {
            "atr": 100,
            "volume_ratio": 1.5,
        },
        "risk_flags": [],
        "gating_notes": [],
    }


def preview(*items: dict, market_open: bool = True) -> dict:
    rows = list(items)
    return {
        "provider": "kis",
        "market": "KR",
        "final_best_candidate": rows[0] if rows else None,
        "final_ranked_candidates": rows,
        "market_session": {
            "market": "KR",
            "is_market_open": market_open,
            "is_entry_allowed_now": market_open,
        },
        "risk_flags": [],
        "gating_notes": [],
    }


def service(risk: FakeTargetRisk | None = None) -> ProfileAwareDryRunAutoBuyService:
    return ProfileAwareDryRunAutoBuyService(
        target_risk_service=risk or FakeTargetRisk(),
    )


def request(**overrides) -> ProfileAwareDryRunAutoBuyRequest:
    values = {
        "provider": "kis",
        "market": "KR",
        "max_candidates": 5,
        "trigger_source": "manual",
        "use_watchlist": True,
        "save_logs": True,
    }
    values.update(overrides)
    return ProfileAwareDryRunAutoBuyRequest(**values)


def test_dry_run_returns_hold_when_no_candidates(db_session):
    result = service().run_once(
        db_session,
        request(),
        preview_override=preview(),
    )

    assert result["action"] == "hold"
    assert result["reason"] == "no_candidates"
    assert result["simulated_order_id"] is None


def test_dry_run_uses_active_safe_profile_by_default(db_session):
    result = service().run_once(
        db_session,
        request(),
        preview_override=preview(candidate()),
    )

    assert result["active_profile"] == "safe"
    assert result["action"] == "would_buy"


def test_dry_run_can_use_explicit_balanced_profile_without_mutating_active(
    db_session,
):
    risk = FakeTargetRisk(recommended=50_000)
    result = service(risk).run_once(
        db_session,
        request(profile_name="balanced"),
        preview_override=preview(candidate(score=70, price=10_000)),
    )

    assert result["active_profile"] == "balanced"
    assert result["action"] == "would_buy"
    assert risk.calls[0]["profile_name"] == "balanced"
    assert result["simulated_quantity"] == 5


def test_buy_score_below_profile_threshold_returns_blocked(db_session):
    result = service().run_once(
        db_session,
        request(),
        preview_override=preview(candidate(score=70)),
    )

    assert result["action"] == "blocked"
    assert result["reason"] == "below_profile_buy_threshold"


def test_target_aware_risk_reject_returns_risk_blocked(db_session):
    risk = FakeTargetRisk(
        approved=False,
        block_reason="monthly_loss_limit_hit",
    )
    result = service(risk).run_once(
        db_session,
        request(),
        preview_override=preview(candidate()),
    )

    assert result["action"] == "blocked"
    assert result["reason"] == "risk_blocked"
    assert result["target_risk_approved"] is False


def test_target_aware_risk_approved_returns_would_buy(db_session):
    result = service().run_once(
        db_session,
        request(),
        preview_override=preview(candidate(price=10_000)),
    )

    assert result["action"] == "would_buy"
    assert result["target_risk_approved"] is True
    assert result["simulated_quantity"] == 3
    assert result["simulated_notional_krw"] == 30_000


def test_recommended_notional_is_capped_by_target_risk(db_session):
    result = service(FakeTargetRisk(recommended=15_000)).run_once(
        db_session,
        request(profile_name="aggressive"),
        preview_override=preview(candidate(score=65, price=10_000)),
    )

    assert result["recommended_notional_krw"] == 15_000
    assert result["simulated_quantity"] == 1
    assert result["simulated_notional_krw"] == 10_000


def test_simulated_quantity_zero_blocks_result(db_session):
    result = service(FakeTargetRisk(recommended=5_000)).run_once(
        db_session,
        request(),
        preview_override=preview(candidate(price=10_000)),
    )

    assert result["action"] == "blocked"
    assert result["reason"] == "simulated_quantity_zero"


def test_data_insufficient_never_returns_would_buy(db_session):
    result = service().run_once(
        db_session,
        request(),
        preview_override=preview(
            candidate(score=None, price=None, indicator_status="insufficient")
        ),
    )

    assert result["action"] == "blocked"
    assert result["reason"] == "data_quality_blocked"


def test_result_saves_signal_run_and_simulated_order_payload(db_session):
    result = service().run_once(
        db_session,
        request(),
        preview_override=preview(candidate()),
    )

    assert db_session.query(SignalLog).count() == 1
    assert db_session.query(TradeRunLog).count() == 1
    assert db_session.query(OrderLog).count() == 1
    signal = db_session.get(SignalLog, result["signal_id"])
    run = db_session.get(TradeRunLog, result["trade_run_id"])
    order = db_session.get(OrderLog, result["simulated_order_id"])
    assert signal.signal_status == "would_buy"
    assert run.mode == "strategy_dry_run_auto_buy"
    assert run.result == "would_buy"
    assert order.internal_status == "DRY_RUN_SIMULATED"
    assert order.broker_order_id is None
    payload = json.loads(run.response_payload)
    assert payload["active_profile"] == "safe"
    assert "dry_run_only" in payload["risk_flags"]
    assert payload["safety"]["validation_called"] is False
