from __future__ import annotations

from types import SimpleNamespace

from app.services.kis_single_symbol_analysis_service import (
    KisSingleSymbolAnalysisService,
)
from app.services.agent_chat_answer_service import AgentChatAnswerService
from app.schemas.agent_chat_orchestrator import AgentChatIntent, AgentChatIntentCategory


class _ReadOnlyKisClient:
    def __init__(self, bars, *, current_price=72000):
        self.bars = bars
        self.current_price = current_price
        self.calls = []

    def get_domestic_stock_price(self, symbol: str):
        self.calls.append(("price", symbol))
        return {
            "symbol": symbol,
            "name": "삼성전자",
            "current_price": self.current_price,
            "timestamp": "2026-08-12T09:00:00+09:00",
        }

    def get_domestic_daily_bars(self, symbol: str, limit: int = 120):
        self.calls.append(("bars", symbol, limit))
        return self.bars


class _UnavailableKisClient:
    def get_domestic_stock_price(self, symbol: str):
        raise RuntimeError("KIS unavailable")


class _ResearchService:
    def __init__(self, *, fallback_used: bool = False, confidence=0.8):
        self.calls = []
        self.fallback_used = fallback_used
        self.confidence = confidence

    def analyze_candidate(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "gate_level": kwargs["gate_level"],
            "gpt_context": {
                "gpt_buy_score": 72 if not self.fallback_used else 50,
                "gpt_sell_score": 28 if not self.fallback_used else 50,
                "confidence": self.confidence,
                "reason": "Market context is stable.",
                "risk_flags": [],
                "gating_notes": [],
            },
            "market_confidence": 0.8,
            "confidence": self.confidence,
            "market_research_reason": "Market context is stable.",
            "entry_allowed": True,
            "hard_blocked": False,
            "risk_flags": [],
            "gating_notes": [],
            "fallback_used": self.fallback_used,
        }


def _bars(count: int = 60):
    return [
        {
            "symbol": "005930",
            "timestamp": f"2026-06-{index + 1:02d}T09:00:00+09:00",
            "open": 65000 + index * 100,
            "high": 65500 + index * 100,
            "low": 64500 + index * 100,
            "close": 65200 + index * 100,
            "volume": 1000000 + index * 1000,
        }
        for index in range(count)
    ]


def _settings():
    return SimpleNamespace(
        openai_model="market-test-model",
        openai_reasoning_effort="xhigh",
    )


def test_analysis_uses_price_ohlcv_quant_and_market_gpt_without_order_path():
    client = _ReadOnlyKisClient(_bars())
    research = _ResearchService()
    service = KisSingleSymbolAnalysisService(
        client,
        settings=_settings(),
        research_service=research,
    )

    result = service.analyze(None, symbol="5930", symbol_name="삼성전자", market="KR")

    assert result["symbol"] == "005930"
    assert result["current_price"] == 72000.0
    assert result["analysis_only"] is True
    assert result["preview_only"] is True
    assert result["indicator_status"] == "ok"
    assert result["indicators"]["ema20"] is not None
    assert result["indicators"]["ema50"] is not None
    assert result["quant_buy_score"] is not None
    assert result["quant_sell_score"] is not None
    assert result["gpt_buy_score"] == 72.0
    assert result["gpt_sell_score"] == 28.0
    assert result["market_gpt_used"] is True
    assert result["market_model"] == "market-test-model"
    assert result["market_reasoning_effort"] == "xhigh"
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["manual_submit_called"] is False
    assert client.calls == [("price", "005930"), ("bars", "005930", 120)]
    assert len(research.calls) == 1


def test_analysis_current_price_and_answer_use_the_same_kis_quote_value():
    client = _ReadOnlyKisClient(_bars(), current_price=255500)
    result = KisSingleSymbolAnalysisService(
        client,
        settings=_settings(),
        research_service=_ResearchService(),
    ).analyze(None, symbol="005930", symbol_name="Samsung Electronics", market="KR")

    answer = AgentChatAnswerService().compose(
        intent=AgentChatIntent(
            category=AgentChatIntentCategory.ANALYSIS_REQUEST,
            symbol="005930",
            symbol_name="Samsung Electronics",
            market="KR",
            provider="kis",
        ),
        data={"analysis": result},
    )

    assert result["current_price"] == 255500.0
    assert "255500" in answer.text


def test_analysis_confidence_is_null_when_market_gpt_does_not_provide_it():
    result = KisSingleSymbolAnalysisService(
        _ReadOnlyKisClient(_bars()),
        settings=_settings(),
        research_service=_ResearchService(confidence=None),
    ).analyze(None, symbol="005930", market="KR")

    assert result["market_gpt_used"] is True
    assert result["confidence"] is None


def test_analysis_holds_without_calling_market_gpt_when_ohlcv_is_insufficient():
    research = _ResearchService()
    service = KisSingleSymbolAnalysisService(
        _ReadOnlyKisClient(_bars(5)),
        settings=_settings(),
        research_service=research,
    )

    result = service.analyze(None, symbol="005930", market="KR")

    assert result["action"] == "hold"
    assert result["reason"] == "insufficient_data"
    assert result["risk_flags"] == ["insufficient_data"]
    assert result["gpt_buy_score"] is None
    assert result["final_buy_score"] is None
    assert research.calls == []


def test_analysis_holds_with_market_data_unavailable_and_no_invented_values():
    service = KisSingleSymbolAnalysisService(
        _UnavailableKisClient(),
        settings=_settings(),
    )

    result = service.analyze(None, symbol="005930", market="KR")

    assert result["action"] == "hold"
    assert result["reason"] == "market_data_unavailable"
    assert result["current_price"] is None
    assert result["quant_buy_score"] is None
    assert result["gpt_buy_score"] is None
    assert result["final_buy_score"] is None


def test_market_gpt_failure_preserves_quant_scores_but_forces_hold():
    client = _ReadOnlyKisClient(_bars())
    research = _ResearchService(fallback_used=True)
    service = KisSingleSymbolAnalysisService(
        client,
        settings=_settings(),
        research_service=research,
    )

    result = service.analyze(None, symbol="005930", market="KR")

    assert result["quant_buy_score"] is not None
    assert result["quant_sell_score"] is not None
    assert result["gpt_buy_score"] is None
    assert result["gpt_sell_score"] is None
    assert result["final_buy_score"] == result["quant_buy_score"]
    assert result["final_sell_score"] == result["quant_sell_score"]
    assert result["action"] == "hold"
    assert result["fallback_used"] is True
    assert result["market_gpt_fallback_used"] is True
    assert "market_gpt_unavailable" in result["risk_flags"]