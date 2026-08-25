from __future__ import annotations

import json

from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.schemas.strategy_dry_run_auto_buy import (
    ProfileAwareDryRunAutoBuyRequest,
)
from app.services.profile_aware_dry_run_auto_buy_service import (
    ProfileAwareDryRunAutoBuyService,
)
from app.services.automation_profile_service import AutomationProfileService


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


def observed_candidate(**fields) -> dict:
    item = candidate()
    item.update(fields)
    return item


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
    assert result["reason"] == "no_candidates"
    assert result["preview_status"] == "override"


def test_dry_run_distinguishes_preview_infrastructure_failure(db_session):
    result = service().run_once(db_session, request())

    assert result["action"] == "hold"
    assert result["reason"] == "preview_service_unavailable"
    assert result["preview_status"] == "unavailable"
    assert result["preview_error"] == "preview_service_unavailable"
    assert result["configured_symbol_count"] == 0
    assert result["analyzed_symbol_count"] == 0


def test_dry_run_exposes_preview_pipeline_observability(db_session):
    result = service().run_once(
        db_session,
        request(),
        preview_override={
            **preview(candidate()),
            "configured_symbol_count": 50,
            "analyzed_symbol_count": 50,
            "quant_candidates_count": 10,
            "gpt_target_count": 5,
            "final_ranked_candidates": [candidate(), candidate("000660")],
        },
    )

    assert result["configured_symbol_count"] == 50
    assert result["analyzed_symbol_count"] == 50
    assert result["quant_candidate_count"] == 10
    assert result["gpt_candidate_count"] == 5
    assert result["final_candidate_count"] == 2
    assert result["preview_status"] == "override"
    assert result["preview_error"] is None


def test_dry_run_exposes_existing_gpt_quant_candidate_observability(db_session):
    item = observed_candidate(
        quant_buy_score=66.0,
        quant_sell_score=21.0,
        ai_buy_score=58.0,
        ai_sell_score=25.0,
        final_buy_score=64.0,
        final_sell_score=22.0,
        gpt_analysis_status="completed",
        gpt_used=True,
        gpt_reason="정량 지표는 양호하지만 보수적 진입이 필요합니다.",
        ai_reason="정량 지표는 양호하지만 보수적 진입이 필요합니다.",
        why_hold="KIS preview는 자문 전용입니다.",
        why_not_buy=["preview_only"],
    )

    result = service().run_once(
        db_session,
        request(),
        preview_override=preview(item),
    )

    public = result["candidates"][0]
    assert public["quant_buy_score"] == 66.0
    assert public["ai_buy_score"] == 58.0
    assert public["final_buy_score"] == 64.0
    assert public["gpt_analysis_status"] == "completed"
    assert public["gpt_used"] is True
    assert public["gpt_reason"] == item["gpt_reason"]
    assert public["ai_reason"] == item["ai_reason"]
    assert public["why_hold"] == item["why_hold"]
    assert public["why_not_buy"] == ["preview_only"]
    assert result["selected_quant_buy_score"] == 66.0
    assert result["selected_ai_buy_score"] == 58.0
    assert result["selected_final_buy_score"] == 64.0
    assert result["selected_gpt_analysis_status"] == "completed"
    assert result["selected_gpt_used"] is True
    assert result["gpt_completed_count"] == 1
    assert result["gpt_failed_count"] == 0
    assert result["gpt_not_run_count"] == 0

    signal = db_session.query(SignalLog).one()
    assert signal.quant_buy_score == 66.0
    assert signal.quant_sell_score == 21.0
    assert signal.ai_buy_score == 58.0
    assert signal.ai_sell_score == 25.0
    assert signal.final_buy_score == 64.0
    assert signal.final_sell_score == 22.0
    assert signal.quant_reason is None
    assert signal.ai_reason == item["ai_reason"]

    payload = json.loads(db_session.query(TradeRunLog).one().response_payload)
    audit = payload["selected_candidate_observability"]
    assert audit["quant_buy_score"] == 66.0
    assert audit["ai_buy_score"] == 58.0
    assert audit["final_buy_score"] == 64.0
    assert audit["gpt_analysis_status"] == "completed"
    assert audit["gpt_used"] is True
    assert audit["gpt_reason"] == item["gpt_reason"]


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


def test_dry_run_separates_custom_automation_identity_from_legacy_profile(
    db_session,
):
    automation = AutomationProfileService()
    created = automation.create(
        db_session,
        AutomationProfileWriteRequest(
            profile_key="aut_kis_eaa46d83",
            name="Custom KIS Entry",
            provider="kis",
            market="KR",
            entry={"min_final_score": 65},
            operation={
                "start_date": "2026-08-01",
                "end_date": "2026-09-30",
                "timezone": "Asia/Seoul",
            },
        ),
    )
    automation.activate(db_session, str(created["id"]))
    risk = FakeTargetRisk(recommended=50_000)

    result = service(risk).run_once(
        db_session,
        request(
            profile_name="safe",
            automation_profile_key="aut_kis_eaa46d83",
            automation_profile_name="Custom KIS Entry",
        ),
        preview_override=preview(candidate(score=65, price=10_000)),
    )

    assert result["active_profile"] == "aut_kis_eaa46d83"
    assert result["profile_key"] == "aut_kis_eaa46d83"
    assert result["automation_profile_key"] == "aut_kis_eaa46d83"
    assert result["automation_profile_name"] == "Custom KIS Entry"
    assert result["legacy_profile_name"] == "safe"
    assert risk.calls[0]["profile_name"] == "aut_kis_eaa46d83"
    assert result["action"] == "would_buy"


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


def test_dry_run_gpt_not_run_exposes_nullable_ai_fields(db_session):
    result = service().run_once(
        db_session,
        request(save_logs=False),
        preview_override=preview(candidate()),
    )

    public = result["candidates"][0]
    assert public["gpt_used"] is False
    assert public["gpt_analysis_status"] == "not_run"
    assert public["ai_buy_score"] is None
    assert public["ai_sell_score"] is None
    assert public["gpt_reason"] is None
    assert result["gpt_completed_count"] == 0
    assert result["gpt_failed_count"] == 0
    assert result["gpt_not_run_count"] == 1
    assert db_session.query(SignalLog).count() == 0
    assert db_session.query(TradeRunLog).count() == 0
    assert db_session.query(OrderLog).count() == 0


def test_dry_run_gpt_failed_preserves_quant_only_final_score(db_session):
    item = observed_candidate(
        quant_buy_score=70.0,
        quant_sell_score=24.0,
        ai_buy_score=None,
        ai_sell_score=None,
        final_buy_score=70.0,
        final_sell_score=24.0,
        gpt_analysis_status="failed",
        gpt_used=False,
        gpt_reason=None,
        ai_reason=None,
        risk_flags=["gpt_unavailable"],
    )

    result = service().run_once(
        db_session,
        request(),
        preview_override=preview(item),
    )

    public = result["candidates"][0]
    assert public["gpt_analysis_status"] == "failed"
    assert public["gpt_used"] is False
    assert public["ai_buy_score"] is None
    assert public["ai_reason"] is None
    assert public["final_buy_score"] == public["quant_buy_score"] == 70.0
    assert "gpt_unavailable" in public["risk_flags"]
    assert result["gpt_completed_count"] == 0
    assert result["gpt_failed_count"] == 1
    assert result["gpt_not_run_count"] == 0


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
