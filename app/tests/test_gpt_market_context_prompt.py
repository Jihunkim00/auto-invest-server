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
    assert '"positive_news_cannot_directly_approve_buy": true' in user_prompt
    assert '"allow_sell_or_exit"' in user_prompt


def test_gpt_response_normalization_extreme_event_blocks_only_new_buy_and_clamps():
    service = GPTMarketService()

    normalized = service._normalize_candidate(
        {
            "market_regime": "trend",
            "entry_bias": "long",
            "entry_allowed": True,
            "confidence": 72,
            "event_risk_level": "extreme",
            "entry_penalty": 1200,
            "allow_sell_or_exit": True,
            "reason": "Extreme macro event risk.",
        }
    )

    assert normalized["hard_block_new_buy"] is True
    assert normalized["entry_allowed"] is False
    assert normalized["allow_sell_or_exit"] is True
    assert normalized["market_confidence"] == 0.72
    assert normalized["confidence"] == 0.72
    assert normalized["entry_penalty"] == 999


def test_guardrails_keep_sell_exit_allowed_when_event_risk_hard_blocks_entry():
    service = GPTMarketService()
    normalized = service._normalize_candidate(
        {
            "market_regime": "trend",
            "entry_bias": "long",
            "entry_allowed": True,
            "market_confidence": 0.9,
            "event_risk_level": "extreme",
            "allow_sell_or_exit": True,
            "reason": "Extreme geopolitical risk.",
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
    assert guarded["hard_blocked"] is True
    assert guarded["allow_sell_or_exit"] is True
