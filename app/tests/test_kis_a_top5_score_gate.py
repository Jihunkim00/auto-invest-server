import pytest

from app.core.constants import A_TOP5_C_MIN_SCORE, A_TOP5_GPT_MIN_BUY_SCORE
from app.services.kis_a_top5_score_gate import evaluate_a_top5_score_gate


def _candidate(**overrides):
    values = {
        "quant_c_score": 65.0,
        "quant_c_status": "analyzed",
        "quant_c_gate_passed": True,
        "gpt_used": True,
        "gpt_analysis_status": "completed",
        "ai_buy_score": 60.0,
        "ai_sell_score": 40.0,
        "action": "buy",
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    ("c_score", "expected"),
    [(64.99, False), (65.0, True)],
)
def test_c_gate_uses_shared_65_point_boundary(c_score, expected):
    result = evaluate_a_top5_score_gate(_candidate(quant_c_score=c_score))

    assert result["quant_c_threshold"] == A_TOP5_C_MIN_SCORE == 65.0
    assert result["quant_c_gate_passed"] is expected
    if not expected:
        assert result["a_top5_score_gate_reason"] == "c_score_below_threshold"


@pytest.mark.parametrize(
    ("gpt_score", "expected", "reason"),
    [
        (59.99, False, "gpt_buy_score_below_threshold"),
        (60.0, True, None),
    ],
)
def test_gpt_gate_uses_independent_60_point_boundary(gpt_score, expected, reason):
    result = evaluate_a_top5_score_gate(_candidate(ai_buy_score=gpt_score))

    assert result["gpt_buy_score_threshold"] == A_TOP5_GPT_MIN_BUY_SCORE == 60.0
    assert result["gpt_buy_score_gate_passed"] is expected
    assert result["a_top5_score_gate_reason"] == reason


def test_hold_action_text_does_not_block_a_numerically_eligible_candidate():
    result = evaluate_a_top5_score_gate(_candidate(action="hold"))

    assert result["a_top5_score_gate_passed"] is True
    assert result["a_top5_score_gate_reason"] is None


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"gpt_analysis_status": "failed"}, "gpt_analysis_failed"),
        ({"gpt_analysis_status": "not_run", "gpt_used": False}, "gpt_analysis_not_completed"),
        ({"ai_buy_score": None}, "gpt_buy_score_missing"),
        ({"ai_buy_score": "bad"}, "gpt_buy_score_invalid"),
        ({"ai_buy_score": "NaN"}, "gpt_buy_score_invalid"),
        ({"ai_buy_score": 101.0}, "gpt_buy_score_invalid"),
        ({"ai_sell_score": None}, "gpt_analysis_incomplete"),
        ({"quant_c_status": "stale_intraday"}, "c_quant_unavailable"),
        ({"quant_c_status": None}, "c_quant_unavailable"),
        ({"quant_c_status": "partial"}, "c_quant_unavailable"),
        ({"quant_c_score": None}, "c_quant_unavailable"),
        ({"quant_c_score": "Infinity"}, "c_score_invalid"),
    ],
)
def test_incomplete_or_invalid_inputs_fail_closed(changes, reason):
    result = evaluate_a_top5_score_gate(_candidate(**changes))

    assert result["a_top5_score_gate_passed"] is False
    assert result["a_top5_score_gate_reason"] == reason
