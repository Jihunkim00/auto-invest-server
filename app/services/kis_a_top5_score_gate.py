"""Shared score gates for the A_TOP5_C_GPT automatic-entry path."""

from __future__ import annotations

import math
from typing import Any

from app.core.constants import A_TOP5_C_MIN_SCORE, A_TOP5_GPT_MIN_BUY_SCORE


def finite_score(value: Any) -> float | None:
    """Return a finite 0..100 score, or None when the value is malformed."""

    if value is None or isinstance(value, bool):
        return None
    try:
        score = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score) or not 0.0 <= score <= 100.0:
        return None
    return score


def _first_score(candidate: dict[str, Any], *keys: str) -> tuple[Any, float | None]:
    for key in keys:
        if key in candidate and candidate.get(key) is not None:
            raw = candidate.get(key)
            return raw, finite_score(raw)
    return None, None


def evaluate_a_top5_score_gate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Evaluate C and GPT minima without consulting advisory action text."""

    c_raw, c_score = _first_score(candidate, "quant_c_score", "entry_quant_score")
    c_status = candidate.get("quant_c_status")
    c_status_normalized = str(c_status or "").strip().lower()
    c_score_valid = c_raw is not None and c_score is not None
    c_analyzed = c_status_normalized == "analyzed"
    c_gate_passed = bool(
        c_score_valid and c_analyzed and c_score >= A_TOP5_C_MIN_SCORE
    )

    if not c_analyzed:
        c_reason = "c_quant_unavailable"
    elif c_raw is None:
        c_reason = "c_quant_unavailable"
    elif c_score is None:
        c_reason = "c_score_invalid"
    elif c_score < A_TOP5_C_MIN_SCORE:
        c_reason = "c_score_below_threshold"
    else:
        c_reason = None

    gpt_status = str(candidate.get("gpt_analysis_status") or "not_run").strip().lower()
    gpt_used = bool(candidate.get("gpt_used"))
    ai_buy_raw, ai_buy_score = _first_score(candidate, "ai_buy_score", "gpt_buy_score")
    ai_sell_raw, ai_sell_score = _first_score(candidate, "ai_sell_score", "gpt_sell_score")
    gpt_complete = bool(
        gpt_used
        and gpt_status == "completed"
        and ai_buy_raw is not None
        and ai_buy_score is not None
        and ai_sell_raw is not None
        and ai_sell_score is not None
    )

    if gpt_status == "failed":
        gpt_reason = "gpt_analysis_failed"
    elif gpt_status != "completed" or not gpt_used:
        gpt_reason = "gpt_analysis_not_completed"
    elif ai_buy_raw is None:
        gpt_reason = "gpt_buy_score_missing"
    elif ai_buy_score is None:
        gpt_reason = "gpt_buy_score_invalid"
    elif ai_sell_raw is None or ai_sell_score is None:
        gpt_reason = "gpt_analysis_incomplete"
    elif ai_buy_score < A_TOP5_GPT_MIN_BUY_SCORE:
        gpt_reason = "gpt_buy_score_below_threshold"
    else:
        gpt_reason = None
    gpt_gate_passed = gpt_complete and ai_buy_score >= A_TOP5_GPT_MIN_BUY_SCORE

    reason = c_reason or gpt_reason
    return {
        "quant_c_score": c_score,
        "quant_c_threshold": A_TOP5_C_MIN_SCORE,
        "quant_c_gate_passed": c_gate_passed,
        "gpt_buy_score": ai_buy_score,
        "gpt_buy_score_threshold": A_TOP5_GPT_MIN_BUY_SCORE,
        "gpt_buy_score_gate_passed": bool(gpt_gate_passed),
        "a_top5_score_gate_passed": bool(c_gate_passed and gpt_gate_passed),
        "a_top5_score_gate_reason": reason,
    }


def apply_a_top5_score_gate(candidate: dict[str, Any]) -> str | None:
    """Refresh score diagnostics on a candidate and return its first failure."""

    result = evaluate_a_top5_score_gate(candidate)
    candidate.update(result)
    return result["a_top5_score_gate_reason"]
