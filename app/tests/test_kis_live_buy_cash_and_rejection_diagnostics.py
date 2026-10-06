from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.db.models import OrderLog, StrategyLiveAutoBuyAttempt, TradeRunLog
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.automation_profile_service import AutomationProfileService
from app.services.kis_buy_cash import buy_cash_diagnostics
from app.services.kis_order_validation_service import KisOrderValidationRequest, KisOrderValidationService
from app.tests.test_strategy_dry_run_auto_buy_service import (
    FakeTargetRisk, live_candidate, preview, request, service,
)
from app.tests.test_strategy_live_auto_buy_service import (
    FakeBroker, FakeKisClient, FakeMarketSessions, FakeRuntimeSettings,
    FakeValidationResult, FakeValidationService,
    enable_live_settings, live_request, live_service,
)


PROFILE_KEY = "aut_cash_diagnostics"


@pytest.fixture()
def cash_profile(db_session):
    profiles = AutomationProfileService()
    profiles.create(db_session, AutomationProfileWriteRequest(
        profile_key=PROFILE_KEY, name="Cash regression", enabled=True,
        provider="kis", market="KR",
        capital={"max_order_notional_krw": 200_000, "cash_only": True},
        universe={"manual_symbols": ["007660"]},
        entry={"min_final_score": 65},
        operation={"start_date": "2026-01-01", "end_date": "2099-12-31"},
    ))
    profiles.activate(db_session, PROFILE_KEY)
    return PROFILE_KEY


@pytest.mark.parametrize("balance,amount,source", [
    ({"cash": 50_000, "orderable_cash": 300_000}, 300_000, "orderable_cash"),
    ({"cash": 500_000, "orderable_cash": 100_000}, 100_000, "orderable_cash"),
    ({"cash": 500_000, "orderable_cash": 0}, 0, "orderable_cash"),
    ({"cash": 300_000}, 300_000, "cash"),
    ({"cash": 300_000, "orderable_cash": None}, 300_000, "cash"),
    ({"cash": 300_000, "orderable_cash": "invalid"}, 300_000, "cash"),
    ({"cash": 300_000, "orderable_cash": "NaN"}, 300_000, "cash"),
    ({"cash": 300_000, "orderable_cash": "inf"}, 300_000, "cash"),
    ({"orderable_cash": "300,000", "ord_psbl_cash": 0}, 300_000, "orderable_cash"),
    ({"ord_psbl_cash": 0, "available_cash": 300_000}, 0, "ord_psbl_cash"),
    ({"ord_psbl_cash": 200_000, "available_cash": 300_000}, 200_000, "ord_psbl_cash"),
    ({"available_cash": 200_000, "cash": 300_000}, 200_000, "available_cash"),
    ({"dnca_tot_amt": 200_000}, 200_000, "dnca_tot_amt"),
    ({}, None, None),
    ({"orderable_cash": -1, "cash": 500_000}, -1, "orderable_cash"),
])
def test_buy_cash_source_precedence_and_explicit_zero(balance, amount, source):
    diagnostic = buy_cash_diagnostics(balance, 132_300)
    assert diagnostic["cash_check_amount_krw"] == amount
    assert diagnostic["cash_source"] == source
    assert diagnostic["cash_sufficient"] is (amount is not None and amount >= 132_300)


@pytest.mark.parametrize("balance,allowed", [
    ({"cash": 50_000, "orderable_cash": 300_000}, True),
    ({"cash": 500_000, "orderable_cash": 100_000}, False),
    ({"cash": 500_000, "orderable_cash": 0}, False),
    ({"cash": 300_000}, True),
    ({"cash": 300_000, "orderable_cash": None}, True),
])
def test_noon_cash_gate_reaches_validation_only_with_sufficient_orderable_cash(
    db_session, cash_profile, balance, allowed,
):
    enable_live_settings(db_session)
    analysis = service(FakeTargetRisk(recommended=135_135)).run_once(
        db_session, request(automation_profile_key=cash_profile),
        preview_override=preview(live_candidate(
            "007660", quant_score=62, ai_score=61, final_score=65.09,
            status="completed", gpt_used=True, current_price=132_300,
        )), execution_mode="live",
    )
    assert analysis["action"] == "would_buy"
    assert analysis["simulated_quantity"] == 1
    assert analysis["simulated_notional_krw"] == 132_300
    validator = FakeValidationService(FakeValidationResult(
        validated_for_submission=False, primary_block_reason="test_validation_stop",
        block_reasons=["test_validation_stop"],
    ))
    broker = FakeBroker()
    live = live_service(
        runtime=FakeRuntimeSettings(
            strategy_live_auto_buy_allowed_profiles=[cash_profile],
            strategy_live_auto_buy_max_notional_krw=200_000,
            strategy_live_auto_buy_max_notional_pct=0,
        ), risk=FakeTargetRisk(recommended=135_135),
        balance=balance, validation=validator, broker=broker,
    )
    readiness = live.readiness(db_session, source_dry_run_id=analysis["trade_run_id"])
    assert readiness["cash_diagnostics"]["cash_sufficient"] is allowed
    result = live.run_once(db_session, live_request(source_dry_run_id=analysis["trade_run_id"]))
    diagnostic = result["cash_diagnostics"]
    assert diagnostic["cash_sufficient"] is allowed
    assert diagnostic["estimated_notional_krw"] == 132_300
    assert diagnostic["cash_source"] == ("orderable_cash" if balance.get("orderable_cash") is not None else "cash")
    assert result["block_reason"] == ("test_validation_stop" if allowed else "insufficient_cash")
    assert result["safety"]["validation_called"] is allowed
    assert len(validator.calls) == int(allowed)
    assert broker.calls == []
    assert result["safety"]["broker_submit_called"] is False
    assert result["safety"]["real_order_submitted"] is False
    attempt = db_session.query(StrategyLiveAutoBuyAttempt).one()
    assert json.loads(attempt.response_payload)["cash_diagnostics"] == diagnostic
    assert db_session.query(OrderLog).count() == 0


class ValidationFakeKisClient(FakeKisClient):
    def __init__(self, balance):
        self.balance = balance
        self.settings = SimpleNamespace(
            kis_env="prod", kis_account_no="", kis_account_product_code="01",
        )
        self.auth_manager = SimpleNamespace(require_configured=lambda: None)

    def get_account_balance(self):
        return dict(self.balance)

    def get_domestic_stock_price(self, symbol):
        return {"current_price": 132_300}

    def build_domestic_order_payload(self, **kwargs):
        return {"PDNO": kwargs["symbol"]}

    def domestic_cash_order_tr_id(self, side):
        return "FAKE"

    def submit_order(self, **kwargs):
        pytest.fail("Validation must never submit a broker order")


@pytest.mark.parametrize("balance,allowed", [
    ({"cash": 50_000, "orderable_cash": 300_000}, True),
    ({"cash": 500_000, "orderable_cash": 100_000}, False),
    ({"cash": 500_000, "orderable_cash": 0}, False),
    ({"cash": 300_000}, True),
    ({"cash": 300_000, "orderable_cash": None}, True),
    ({}, False),
])
def test_shared_kis_buy_validation_uses_same_cash_source(balance, allowed):
    validator = KisOrderValidationService(
        ValidationFakeKisClient(balance), session_service=FakeMarketSessions(),
    )
    result = validator.validate(KisOrderValidationRequest(symbol="007660", side="buy", qty=1))
    assert result.validated_for_submission is allowed
    if balance:
        diagnostic = result.detail["cash_diagnostics"]
        assert diagnostic["cash_sufficient"] is allowed
        assert result.available_cash == diagnostic["cash_check_amount_krw"]
    if not allowed:
        assert result.block_reasons == (["insufficient_cash"] if balance else ["available_cash_unavailable"])


def rejected_candidate(**overrides):
    values = dict(
        symbol="047050", quant_score=62, ai_score=53, final_score=66.16,
        status="completed", gpt_used=True,
    )
    values.update(overrides)
    return live_candidate(**values)


def filtered_preview(*items):
    # The upstream LIVE funnel already removed these candidates. Diagnostics
    # must inspect the retained analysis rows without restoring eligibility.
    return {**preview(), "canonical_profile_pipeline": True, "items": list(items)}


@pytest.mark.parametrize("fields,reason", [
    ({}, "gpt_buy_score_below_threshold"),
    ({"gpt_used": False, "status": "not_run", "ai_score": None, "final_score": None}, "no_gpt_completed_execution_candidate"),
    ({"status": "failed", "ai_score": None, "final_score": None}, "gpt_analysis_failed"),
    ({"status": "incomplete", "ai_score": None, "final_score": None}, "gpt_analysis_incomplete"),
    ({"ai_score": 64, "final_score": 63}, "below_profile_buy_threshold"),
    ({"ai_score": 64, "final_score": 68, "data_sufficient": False}, "data_quality_blocked"),
])
def test_live_rejection_taxonomy_and_persisted_diagnostics(db_session, cash_profile, fields, reason):
    result = service().run_once(
        db_session, request(automation_profile_key=cash_profile),
        preview_override=filtered_preview(rejected_candidate(**fields)), execution_mode="live",
    )
    assert result["action"] == "hold"
    assert result["reason"] == result["primary_block_reason"] == reason
    assert result["execution_candidates"] == []
    assert result["submission_eligible"] is False
    assert result["candidate_rejection_summary"] == {reason: 1}
    diagnostic = result["live_block_diagnostics"]
    assert diagnostic["required_gpt_buy_score"] == 60
    assert diagnostic["required_final_buy_score"] == 65
    if not fields:
        assert diagnostic["gpt_used"] is True
        assert diagnostic["gpt_analysis_status"] == "completed"
        assert diagnostic["gpt_buy_score"] == 53
        assert diagnostic["final_buy_score"] == 66.16
    run = db_session.get(TradeRunLog, result["trade_run_id"])
    assert run.reason == reason
    assert json.loads(run.response_payload)["live_block_diagnostics"] == diagnostic
    assert db_session.query(OrderLog).count() == 0


@pytest.mark.parametrize("reverse", [False, True])
def test_primary_rejection_uses_furthest_funnel_stage(db_session, cash_profile, reverse):
    items = [
        rejected_candidate(symbol="A", ai_score=58, final_score=70),
        rejected_candidate(symbol="B", ai_score=65, final_score=62),
    ]
    if reverse:
        items.reverse()
    result = service().run_once(
        db_session, request(automation_profile_key=cash_profile),
        preview_override=filtered_preview(*items), execution_mode="live",
    )
    assert result["primary_block_reason"] == "below_profile_buy_threshold"
    assert result["live_block_diagnostics"]["symbol"] == "B"
    assert result["candidate_rejection_summary"] == {
        "gpt_buy_score_below_threshold": 1, "below_profile_buy_threshold": 1,
    }


def test_rejections_preserve_target_risk_reason_and_zero_quantity(db_session, cash_profile):
    candidate = rejected_candidate(ai_score=64, final_score=68)
    risk = FakeTargetRisk(approved=False, block_reason="account_total_exposure_cap_reached")
    result = service(risk).run_once(
        db_session, request(automation_profile_key=cash_profile, save_logs=False),
        preview_override=preview(candidate), execution_mode="live",
    )
    assert result["reason"] == "account_total_exposure_cap_reached"
    result = service(FakeTargetRisk(recommended=1)).run_once(
        db_session, request(automation_profile_key=cash_profile, save_logs=False),
        preview_override=preview(candidate), execution_mode="live",
    )
    assert result["reason"] == "simulated_quantity_zero"
    assert result["submission_eligible"] is False
