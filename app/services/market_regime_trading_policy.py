"""Research hypotheses only: no execution gate consumes these results."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite

from app.services.kis_a_top5_score_gate import finite_score
from app.services.market_regime_trading_context import MarketRegimeTradingContext

MARKET_REGIME_POLICY_VERSION = "shadow_v1"
_SHADOW_STAGE_POLICY = {
    1: (70.0, 0.50),
    2: (65.0, 0.75),
    3: (65.0, 1.00),
    4: (62.5, 1.00),
    5: (68.0, 0.75),
    6: (72.0, 0.50),
}


@dataclass(frozen=True)
class MarketRegimeShadowPolicy:
    version: str = MARKET_REGIME_POLICY_VERSION
    base_c_min: float = 65.0
    shadow_c_min: float = 65.0
    shadow_size_multiplier: float = 1.0
    shadow_policy_active: bool = False
    reason: str = "market_regime_not_confirmed"
    applied_to_live_trading: bool = False

    def to_payload(self) -> dict:
        return asdict(self)


def get_market_regime_shadow_policy(context: MarketRegimeTradingContext):
    if context.status != "confirmed" or not context.confirmed or context.stage not in _SHADOW_STAGE_POLICY:
        return MarketRegimeShadowPolicy()
    shadow_c_min, shadow_size_multiplier = _SHADOW_STAGE_POLICY[context.stage]
    return MarketRegimeShadowPolicy(
        shadow_c_min=shadow_c_min, shadow_size_multiplier=shadow_size_multiplier,
        shadow_policy_active=True, reason="market_regime_confirmed",
    )


def evaluate_shadow_candidate(policy, *, a_rank, c_score, gpt_score, final_score, base_notional=None):
    """Compare fixed A5/C65/GPT60/Final65 with the C-only hypothesis.

    Missing/invalid scores cannot pass. This neither selects candidates nor changes
    scores, quantities, notional amounts, or any configured live threshold.
    """
    c, gpt, final = map(finite_score, (c_score, gpt_score, final_score))
    rank = finite_score(a_rank)
    base_c_pass = c is not None and c >= policy.base_c_min
    shadow_c_pass = c is not None and c >= policy.shadow_c_min
    other_gates = bool(
        rank is not None and 1 <= rank <= 5
        and gpt is not None and gpt >= 60.0
        and final is not None and final >= 65.0
    )
    # Notional has no score range limit; it is only optional diagnostics.
    try:
        notional = float(base_notional) if base_notional is not None and not isinstance(base_notional, bool) else None
    except (TypeError, ValueError, OverflowError):
        notional = None
    if notional is not None and (not isfinite(notional) or notional < 0):
        notional = None
    return {
        "base_c_min": policy.base_c_min,
        "shadow_regime_c_min": policy.shadow_c_min,
        "shadow_regime_size_multiplier": policy.shadow_size_multiplier,
        "base_c_pass": base_c_pass,
        "shadow_regime_c_pass": shadow_c_pass,
        "base_entry_funnel_pass": bool(other_gates and base_c_pass),
        "shadow_regime_entry_funnel_pass": bool(other_gates and shadow_c_pass),
        "shadow_regime_notional": notional * policy.shadow_size_multiplier if notional is not None else None,
    }


def market_regime_diagnostics(context: MarketRegimeTradingContext) -> dict:
    return {
        "market_regime": context.to_payload(),
        "market_regime_shadow_policy": get_market_regime_shadow_policy(context).to_payload(),
    }


def market_regime_observation_fields(context: MarketRegimeTradingContext) -> dict:
    policy = get_market_regime_shadow_policy(context)
    return {
        "market_regime_snapshot_id": context.snapshot_id,
        "market_regime_calculation_date": context.calculation_date,
        "market_regime_calculated_at": context.calculated_at,
        "market_regime_stage": context.stage,
        "market_regime_key": context.stage_key,
        "market_regime_label": context.stage_label,
        "market_regime_status": context.status,
        "market_regime_confirmed": context.confirmed,
        "market_regime_score": context.combined_score,
        "market_regime_kospi_score": context.kospi_score,
        "market_regime_nasdaq_score": context.nasdaq_score,
        "market_regime_score_change_3w": context.score_change_3w,
        "market_regime_new_bullish_reversal": context.new_bullish_reversal,
        "market_regime_new_bearish_reversal": context.new_bearish_reversal,
        "market_regime_policy_version": policy.version,
        "shadow_regime_policy_active": policy.shadow_policy_active,
        "shadow_regime_policy_reason": policy.reason,
    }
