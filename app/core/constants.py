from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_TIMEFRAME = "1Min"
DEFAULT_BARS_LIMIT = 120

# Signal blending (quant-first)
QUANT_WEIGHT = 0.75
AI_WEIGHT = 0.25

# Candidate thresholds (legacy defaults retained for compatibility)
BUY_QUANT_MIN = 60.0
BUY_AI_MIN = 55.0
BUY_FINAL_MIN = 65.0
SELL_QUANT_MIN = 60.0
SELL_AI_MIN = 55.0
SELL_FINAL_MIN = 65.0
MIN_BUY_SELL_SPREAD = 15.0

# Conservative risk defaults
MIN_CONFIDENCE_TO_TRADE = 0.65
MAX_TRADES_PER_DAY = 3
MAX_DAILY_LOSS_PCT = 0.02
BLOCK_NEAR_MARKET_CLOSE_DEFAULT = True
NEAR_CLOSE_MINUTES = 15
KILL_SWITCH_DEFAULT = False

# Position sizing defaults
WEAK_SETUP_POSITION_PCT = 0.05
DECENT_SETUP_POSITION_PCT = 0.07
STRONG_SETUP_POSITION_PCT = 0.10
MAX_POSITION_EQUITY_PCT = 0.10

SIGNAL_STATUS_CREATED = "created"
SIGNAL_STATUS_REJECTED = "rejected"
SIGNAL_STATUS_APPROVED = "approved"
SIGNAL_STATUS_EXECUTED = "executed"
SIGNAL_STATUS_SKIPPED = "skipped"

RUN_RESULT_EXECUTED = "executed"
RUN_RESULT_SKIPPED = "skipped"
RUN_RESULT_REJECTED = "rejected"
RUN_RESULT_ERROR = "error"


@dataclass(frozen=True, slots=True)
class GateProfile:
    level: int
    name: str
    min_buy_score: float
    min_sell_score: float
    min_score_spread: float
    min_confidence_to_trade: float
    allow_neutral_regime_entry: bool
    allow_oversold_bounce: bool
    strict_alignment: str  # strict | moderate | loose
    weak_volume_penalty: float
    bearish_is_hard_block: bool


GATE_LEVEL_PROFILES: dict[int, GateProfile] = {
    1: GateProfile(
        level=1,
        name="very_conservative",
        min_buy_score=72.0,
        min_sell_score=72.0,
        min_score_spread=18.0,
        min_confidence_to_trade=0.72,
        allow_neutral_regime_entry=False,
        allow_oversold_bounce=False,
        strict_alignment="strict",
        weak_volume_penalty=12.0,
        bearish_is_hard_block=True,
    ),
    2: GateProfile(
        level=2,
        name="conservative",
        min_buy_score=68.0,
        min_sell_score=68.0,
        min_score_spread=15.0,
        min_confidence_to_trade=0.68,
        allow_neutral_regime_entry=True,
        allow_oversold_bounce=False,
        strict_alignment="moderate",
        weak_volume_penalty=9.0,
        bearish_is_hard_block=False,
    ),
    3: GateProfile(
        level=3,
        name="balanced_test_mode",
        min_buy_score=62.0,
        min_sell_score=62.0,
        min_score_spread=11.0,
        min_confidence_to_trade=0.60,
        allow_neutral_regime_entry=True,
        allow_oversold_bounce=True,
        strict_alignment="moderate",
        weak_volume_penalty=6.0,
        bearish_is_hard_block=False,
    ),
    4: GateProfile(
        level=4,
        name="loose_test_mode",
        min_buy_score=56.0,
        min_sell_score=56.0,
        min_score_spread=8.0,
        min_confidence_to_trade=0.54,
        allow_neutral_regime_entry=True,
        allow_oversold_bounce=True,
        strict_alignment="loose",
        weak_volume_penalty=3.0,
        bearish_is_hard_block=False,
    ),
}


DEFAULT_GATE_LEVEL = int(os.getenv("DEFAULT_GATE_LEVEL", "2") or 2)
if DEFAULT_GATE_LEVEL not in GATE_LEVEL_PROFILES:
    DEFAULT_GATE_LEVEL = 2


def resolve_gate_level(gate_level: int | None) -> int:
    if gate_level in GATE_LEVEL_PROFILES:
        return int(gate_level)
    return DEFAULT_GATE_LEVEL


def get_gate_profile(gate_level: int | None = None) -> GateProfile:
    resolved = resolve_gate_level(gate_level)
    return GATE_LEVEL_PROFILES[resolved]
