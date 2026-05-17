from app.services.gpt_hard_block_policy import should_apply_gpt_hard_block
from app.services.gpt_market_service import GPTMarketService
from app.services.signal_service import SignalService


def _broad_risk_payload(**overrides):
    payload = {
        "market_regime": "trend",
        "technical_market_regime": "trend",
        "market_risk_regime": "risk_off",
        "entry_bias": "long",
        "entry_allowed": True,
        "market_confidence": 0.86,
        "event_risk_level": "high",
        "geopolitical_risk_level": "extreme",
        "energy_risk_level": "high",
        "macro_risk_level": "high",
        "entry_penalty": 999,
        "hard_block_new_buy": True,
        "allow_sell_or_exit": True,
        "gpt_buy_score": 61,
        "gpt_sell_score": 58,
        "risk_flags": ["risk_off", "geopolitical_headline_risk"],
        "gating_notes": ["Broad risk-off caution only."],
        "reason": "Broad oil, macro, and geopolitical headline risk without direct symbol-specific impairment.",
    }
    payload.update(overrides)
    return payload


def test_broad_macro_risk_no_hard_block_and_caps_penalty():
    service = GPTMarketService()

    normalized = service._normalize_candidate(_broad_risk_payload())

    assert normalized["hard_block_new_buy"] is False
    assert normalized["entry_penalty"] <= 70
    assert isinstance(normalized["gpt_buy_score"], float)
    assert isinstance(normalized["gpt_sell_score"], float)
    assert "gpt_hard_block_downgraded_to_advisory" in normalized["gating_notes"]


def test_gate_1_no_gpt_hard_block_for_broad_risk():
    service = GPTMarketService()
    normalized = service._normalize_candidate(_broad_risk_payload(entry_penalty=70))

    guarded = service._apply_guardrails(
        normalized,
        {
            "regime_confidence": 0.9,
            "hard_block_reason": None,
            "gating_notes": [],
        },
        indicators={"ema20": 110, "ema50": 100},
        gate_level=1,
    )

    assert guarded["hard_block_new_buy"] is False
    assert guarded["hard_blocked"] is False
    assert guarded["hard_block_reason"] is None
    assert guarded["entry_penalty"] <= 70


def test_gate_4_no_gpt_hard_block_for_broad_risk_with_strong_setup():
    service = GPTMarketService()
    normalized = service._normalize_candidate(
        _broad_risk_payload(entry_penalty=30, market_confidence=0.92)
    )

    guarded = service._apply_guardrails(
        normalized,
        {
            "regime_confidence": 0.9,
            "hard_block_reason": None,
            "gating_notes": [],
        },
        indicators={"ema20": 110, "ema50": 100},
        gate_level=4,
    )
    action, _, notes = SignalService._resolve_action(
        market_entry_allowed=bool(guarded["entry_allowed"]),
        hard_blocked=bool(guarded["hard_blocked"]),
        hard_block_reason=guarded["hard_block_reason"],
        regime=guarded["market_regime"],
        regime_confidence=float(guarded["regime_confidence"]),
        quant_buy=82,
        quant_sell=20,
        ai_buy=80,
        ai_sell=18,
        final_buy=81,
        final_sell=19,
        gate_level=4,
    )

    assert guarded["hard_blocked"] is False
    assert guarded["entry_penalty"] <= 70
    assert "hard_block=gpt_hard_block_new_buy" not in notes
    assert action == "buy"


def test_true_severe_symbol_risk_allows_999_and_final_block():
    service = GPTMarketService()
    normalized = service._normalize_candidate(
        {
            **_broad_risk_payload(),
            "entry_penalty": 999,
            "hard_block_new_buy": True,
            "risk_flags": ["trading_halt", "accounting_fraud"],
            "gating_notes": ["Direct severe symbol risk."],
            "reason": "Trading halt after accounting fraud and delisting risk.",
        }
    )

    guarded = service._apply_guardrails(
        normalized,
        {
            "regime_confidence": 0.9,
            "hard_block_reason": None,
            "gating_notes": [],
        },
        indicators={"ema20": 110, "ema50": 100},
        gate_level=4,
    )
    action, _, notes = SignalService._resolve_action(
        market_entry_allowed=bool(guarded["entry_allowed"]),
        hard_blocked=bool(guarded["hard_blocked"]),
        hard_block_reason=guarded["hard_block_reason"],
        regime=guarded["market_regime"],
        regime_confidence=float(guarded["regime_confidence"]),
        quant_buy=90,
        quant_sell=10,
        ai_buy=88,
        ai_sell=12,
        final_buy=89,
        final_sell=11,
        gate_level=4,
    )

    assert guarded["hard_block_new_buy"] is True
    assert guarded["entry_penalty"] == 999
    assert guarded["hard_blocked"] is True
    assert action == "hold"
    assert "hard_block=gpt_hard_block_new_buy" in notes


def test_aapl_googl_arm_style_headline_risk_uses_graded_penalty():
    service = GPTMarketService()

    for symbol in ("AAPL", "GOOGL", "ARM"):
        normalized = service._normalize_candidate(
            _broad_risk_payload(
                symbol=symbol,
                reason=f"{symbol} faces oil, geopolitical, and risk-off headline pressure without direct company impairment.",
            )
        )
        assert normalized["entry_penalty"] != 999
        assert normalized["entry_penalty"] <= 70
        assert normalized["hard_block_new_buy"] is False
        assert normalized["gpt_buy_score"] is not None
        assert normalized["gpt_sell_score"] is not None


def test_risk_integration_does_not_final_block_on_non_severe_gpt_hard_flag():
    payload = _broad_risk_payload(entry_penalty=30, hard_block_new_buy=True)
    assert should_apply_gpt_hard_block(payload) is False

    action, _, notes = SignalService._resolve_action(
        market_entry_allowed=True,
        hard_blocked=False,
        hard_block_reason=None,
        regime="trend",
        regime_confidence=0.75,
        quant_buy=78,
        quant_sell=20,
        ai_buy=77,
        ai_sell=18,
        final_buy=77.5,
        final_sell=19,
        gate_level=4,
    )

    assert action == "buy"
    assert not any(note.startswith("hard_block=") for note in notes)


def test_numeric_gpt_score_normalization_preserves_numbers():
    service = GPTMarketService()

    normalized = service._normalize_candidate(
        {
            "market_regime": "trend",
            "entry_bias": "long",
            "entry_allowed": True,
            "market_confidence": "0.8",
            "gpt_buy_score": "63.5",
            "gpt_sell_score": 27,
            "allow_sell_or_exit": True,
            "reason": "Normal numeric GPT advisory response.",
        }
    )

    assert normalized["gpt_buy_score"] == 63.5
    assert normalized["gpt_sell_score"] == 27.0
