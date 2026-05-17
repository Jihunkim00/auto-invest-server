from app.services.gpt_market_service import GPTMarketService, MarketGateContext


def test_kr_prompt_selection_includes_korean_market_risk_context():
    service = GPTMarketService()

    prompt = service._build_system_prompt("KR")

    assert "USD/KRW" in prompt
    assert "KIS" in prompt
    assert "Korean stock" in prompt
    assert "Foreign and institutional investor flow" in prompt
    assert "SOX" in prompt
    assert "Geopolitical risk" in prompt
    assert "Energy" in prompt
    assert "political and regulatory risk" in prompt
    assert "Sector fundamental and revenue trend" in prompt
    assert "Do not create a buy signal from positive news alone" in prompt


def test_us_prompt_selection_includes_us_market_risk_context():
    service = GPTMarketService()

    prompt = service._build_system_prompt("US")

    assert "Alpaca" in prompt
    assert "VIX" in prompt
    assert "Federal Reserve" in prompt
    assert "CPI" in prompt
    assert "DXY" in prompt
    assert "Sector and ETF context" in prompt
    assert "Earnings and guidance" in prompt
    assert "Do not create a buy signal from positive news alone" in prompt


def test_user_payload_is_market_aware_and_quant_first():
    service = GPTMarketService()
    context = MarketGateContext(cached_site_summaries=[], used_cache=False)

    _, user_prompt = service._build_prompt(
        symbol="005930",
        indicators={"price": 72000},
        context=context,
        gate_level=2,
        gate_profile_name="conservative",
        market="KR",
    )

    assert '"market": "KR"' in user_prompt
    assert '"quant_is_primary": true' in user_prompt
    assert '"gpt_is_risk_filter": true' in user_prompt
    assert '"gpt_advisory_not_primary_hard_block": true' in user_prompt
    assert '"positive_news_cannot_directly_approve_buy": true' in user_prompt
    assert '"allow_sell_or_exit"' in user_prompt


def test_gpt_response_normalization_broad_extreme_risk_is_advisory_penalty():
    service = GPTMarketService()

    normalized = service._normalize_candidate(
        {
            "market_regime": "trend",
            "entry_bias": "long",
            "entry_allowed": True,
            "confidence": 72,
            "market_risk_regime": "risk_off",
            "geopolitical_risk_level": "extreme",
            "energy_risk_level": "high",
            "macro_risk_level": "high",
            "hard_block_new_buy": True,
            "event_risk_level": "extreme",
            "entry_penalty": 1200,
            "allow_sell_or_exit": True,
            "reason": "Broad macro, oil, and geopolitical headline risk.",
        }
    )

    assert normalized["hard_block_new_buy"] is False
    assert normalized["allow_sell_or_exit"] is True
    assert normalized["market_confidence"] == 0.72
    assert normalized["confidence"] == 0.72
    assert normalized["entry_penalty"] == 70
    assert "gpt_hard_block_downgraded_to_advisory" in normalized["gating_notes"]


def test_gpt_response_normalization_true_severe_symbol_risk_allows_999():
    service = GPTMarketService()

    normalized = service._normalize_candidate(
        {
            "market_regime": "volatile",
            "entry_bias": "neutral",
            "entry_allowed": True,
            "market_confidence": 0.7,
            "event_risk_level": "extreme",
            "entry_penalty": 999,
            "hard_block_new_buy": True,
            "allow_sell_or_exit": True,
            "reason": "Direct severe symbol risk: trading halt after accounting fraud allegations.",
        }
    )

    assert normalized["hard_block_new_buy"] is True
    assert normalized["entry_allowed"] is False
    assert normalized["entry_penalty"] == 999


def test_guardrails_keep_broad_event_risk_as_advisory_and_sell_exit_allowed():
    service = GPTMarketService()
    normalized = service._normalize_candidate(
        {
            "market_regime": "trend",
            "entry_bias": "long",
            "entry_allowed": True,
            "market_confidence": 0.9,
            "market_risk_regime": "risk_off",
            "event_risk_level": "extreme",
            "entry_penalty": 70,
            "hard_block_new_buy": True,
            "allow_sell_or_exit": True,
            "reason": "Extreme geopolitical and energy headline risk without direct symbol impairment.",
        }
    )

    guarded = service._apply_guardrails(
        normalized,
        {
            "regime_confidence": 0.8,
            "hard_block_reason": None,
            "gating_notes": [],
        },
        indicators={"ema20": 110, "ema50": 100},
        gate_level=2,
    )

    assert guarded["entry_allowed"] is False
    assert guarded["hard_block_new_buy"] is False
    assert guarded["hard_blocked"] is False
    assert guarded["allow_sell_or_exit"] is True
    assert guarded["hard_block_reason"] is None


def test_required_output_includes_legacy_schema_and_new_risk_fields():
    service = GPTMarketService()
    context = MarketGateContext(cached_site_summaries=[], used_cache=False)

    _, user_prompt = service._build_prompt(
        symbol="AAPL",
        indicators={"price": 100},
        context=context,
        gate_level=2,
        gate_profile_name="conservative",
        market="US",
    )

    for key in (
        "market_regime",
        "entry_bias",
        "entry_allowed",
        "market_confidence",
        "reason",
        "event_risk_level",
        "entry_penalty",
        "hard_block_new_buy",
        "allow_sell_or_exit",
        "gpt_buy_score",
        "gpt_sell_score",
        "confidence",
        "risk_flags",
        "gating_notes",
    ):
        assert f'"{key}"' in user_prompt


def test_guardrails_override_gpt_attempt_to_block_sell_exit():
    service = GPTMarketService()
    normalized = service._normalize_candidate(
        {
            "market_regime": "trend",
            "entry_bias": "long",
            "entry_allowed": True,
            "market_confidence": 0.9,
            "event_risk_level": "extreme",
            "entry_penalty": 999,
            "hard_block_new_buy": True,
            "allow_sell_or_exit": False,
            "reason": "Direct severe symbol risk: trading halt after bankruptcy filing.",
        }
    )

    guarded = service._apply_guardrails(
        normalized,
        {
            "regime_confidence": 0.8,
            "hard_block_reason": None,
            "gating_notes": [],
        },
        indicators={"ema20": 110, "ema50": 100},
        gate_level=2,
    )

    assert guarded["entry_allowed"] is False
    assert guarded["hard_block_new_buy"] is True
    assert guarded["allow_sell_or_exit"] is True
    assert "gpt_attempted_to_block_sell_exit_overridden" in guarded["gating_notes"]
