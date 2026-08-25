"""Small, read-only observability projections for automation analysis results.

The preview services already calculate these values. This module only selects
the existing fields that are safe to expose in responses and audit logs; it
does not calculate or alter any trading score.
"""

from __future__ import annotations

from typing import Any


def candidate_gpt_quant_observability(
    candidate: dict[str, Any] | None,
    *,
    evaluated: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the compact public/audit projection for one candidate."""

    raw = candidate if isinstance(candidate, dict) else {}
    if isinstance(evaluated, dict):
        source = evaluated.get("raw")
        if isinstance(source, dict):
            raw = source

    if isinstance(evaluated, dict):
        price = evaluated.get("price")
        buy_score = evaluated.get("buy_score")
        sell_score = evaluated.get("sell_score")
        final_score = evaluated.get("final_score")
        data_sufficient = evaluated.get("data_sufficient")
        entry_ready = evaluated.get("entry_ready")
        target_risk_approved = evaluated.get("target_risk_approved")
        risk_flags = evaluated.get("risk_flags")
        gating_notes = evaluated.get("gating_notes")
    else:
        price = raw.get("price")
        if price is None:
            price = raw.get("current_price")
        buy_score = raw.get("buy_score")
        sell_score = raw.get("sell_score")
        final_score = raw.get("final_score")
        data_sufficient = raw.get("data_sufficient")
        entry_ready = raw.get("entry_ready")
        target_risk_approved = raw.get("target_risk_approved")
        risk_flags = raw.get("risk_flags")
        gating_notes = raw.get("gating_notes")

    status = str(raw.get("gpt_analysis_status") or "not_run").strip().lower()
    if status not in {"completed", "failed", "not_run"}:
        status = "not_run"

    return {
        "symbol": raw.get("symbol"),
        "name": raw.get("name"),
        "price": price,
        "gpt_analysis_status": status,
        "gpt_used": bool(raw.get("gpt_used")),
        "quant_buy_score": raw.get("quant_buy_score"),
        "quant_sell_score": raw.get("quant_sell_score"),
        "ai_buy_score": raw.get("ai_buy_score"),
        "ai_sell_score": raw.get("ai_sell_score"),
        "final_buy_score": raw.get("final_buy_score"),
        "final_sell_score": raw.get("final_sell_score"),
        "buy_score": buy_score,
        "sell_score": sell_score,
        "final_score": final_score,
        "confidence": raw.get("confidence"),
        "gpt_reason": raw.get("gpt_reason"),
        "ai_reason": raw.get("ai_reason"),
        "why_hold": raw.get("why_hold"),
        "why_not_buy": raw.get("why_not_buy"),
        "risk_flags": risk_flags if isinstance(risk_flags, list) else [],
        "gating_notes": gating_notes if isinstance(gating_notes, list) else [],
        "data_sufficient": data_sufficient,
        "entry_ready": entry_ready,
        "target_risk_approved": target_risk_approved,
    }


def gpt_result_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    """Count actual GPT outcomes, requiring ``gpt_used`` for completion."""

    counts = {
        "gpt_completed_count": 0,
        "gpt_failed_count": 0,
        "gpt_not_run_count": 0,
    }
    for item in items:
        status = str(item.get("gpt_analysis_status") or "not_run").strip().lower()
        used = bool(item.get("gpt_used"))
        if status == "completed" and used:
            counts["gpt_completed_count"] += 1
        elif status == "failed":
            counts["gpt_failed_count"] += 1
        else:
            counts["gpt_not_run_count"] += 1
    return counts
