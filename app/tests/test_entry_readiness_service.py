from __future__ import annotations

from app.services.entry_readiness_service import evaluate_entry_readiness


def test_entry_readiness_default_uses_min_entry_score_floor():
    result = evaluate_entry_readiness(
        has_indicators=True,
        entry_score=64,
        buy_score=64,
        sell_score=10,
        gate_level=4,
        min_entry_score=65,
        max_sell_score=25,
    )

    assert result["effective_min_entry_score"] == 65.0
    assert result["entry_ready"] is False
    assert result["block_reason"] == "score_threshold_not_met"


def test_entry_readiness_can_use_gate_profile_threshold_without_floor():
    result = evaluate_entry_readiness(
        has_indicators=True,
        entry_score=56,
        buy_score=56,
        sell_score=0,
        gate_level=4,
        min_entry_score=65,
        max_sell_score=25,
        use_min_entry_score_floor=False,
    )

    assert result["effective_min_entry_score"] == 56.0
    assert result["entry_ready"] is True
    assert result["block_reason"] is None


def test_entry_readiness_gate_three_threshold_without_floor_is_62():
    result = evaluate_entry_readiness(
        has_indicators=True,
        entry_score=62,
        buy_score=62,
        sell_score=0,
        gate_level=3,
        min_entry_score=65,
        max_sell_score=25,
        use_min_entry_score_floor=False,
    )

    assert result["effective_min_entry_score"] == 62.0
    assert result["entry_ready"] is True
