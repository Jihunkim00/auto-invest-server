import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.main import app
from app.services.kis_watchlist_preview_service import (
    KisGptPreview,
    KisPreviewGptAdvisor,
)


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "kis_enabled": False,
        "kis_env": "prod",
        "kis_app_key": "real-app-key",
        "kis_app_secret": "real-app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_base_url": "https://openapi.koreainvestment.com:9443",
        "openai_api_key": None,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _daily_bars(count: int, *, start_close: float = 60000.0):
    start = date(2026, 1, 1)
    bars = []
    for index in range(count):
        close = start_close + (index * 120)
        bars.append(
            {
                "symbol": "005930",
                "timestamp": (start + timedelta(days=index)).isoformat(),
                "open": close - 40,
                "high": close + 90,
                "low": close - 120,
                "close": close,
                "volume": 1000000 + (index * 10000),
            }
        )
    return bars


def _has_hangul(value: str) -> bool:
    return any("\uac00" <= char <= "\ud7a3" for char in value)


def _scoreable_indicator_payload():
    return {
        "price": 72000.0,
        "ema20": 70000.0,
        "ema50": 68000.0,
        "rsi": 58.5,
        "vwap": 70500.0,
        "atr": 1200.0,
        "volume_ratio": 1.2,
        "momentum": 0.018,
        "recent_return": 0.04,
    }


def _open_market_session():
    return {
        "market": "KR",
        "timezone": "Asia/Seoul",
        "is_market_open": True,
        "is_entry_allowed_now": True,
        "is_near_close": False,
        "closure_reason": None,
        "closure_name": None,
    }


class _FakeResponses:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text)


class _FakeOpenAIClient:
    def __init__(self, output_text: str):
        self.responses = _FakeResponses(output_text)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _safe_preview(monkeypatch):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.get_settings",
        lambda: _settings(),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_stock_price",
        lambda self, symbol: {
            "symbol": symbol,
            "name": "삼성전자" if symbol == "005930" else None,
            "current_price": 72000.0,
        },
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_daily_bars",
        lambda self, symbol, limit=120: [],
    )
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisPreviewGptAdvisor.analyze",
        lambda self, **kwargs: KisGptPreview(
            gpt_used=True,
            action_hint="watch",
            gpt_reason="Advisory context only; technical indicators are unavailable.",
            warnings=[],
        ),
    )


def test_kis_watchlist_preview_returns_items(client):
    response = client.post("/kis/watchlist/preview")

    assert response.status_code == 200
    body = response.json()
    assert body["market"] == "KR"
    assert body["provider"] == "kis"
    assert body["dry_run"] is True
    assert body["preview_only"] is True
    assert body["trading_enabled"] is False
    assert body["gpt_analysis_included"] is True
    assert body["configured_symbol_count"] == 8
    assert body["analyzed_symbol_count"] == 8
    assert body["quant_candidates_count"] == 0
    assert body["researched_candidates_count"] == 0
    assert body["final_best_candidate"] is None
    assert body["second_final_candidate"] is None
    assert body["best_score"] is None
    assert body["final_score_gap"] is None
    assert body["min_entry_score"] is None
    assert body["min_score_gap"] is None
    assert body["should_trade"] is False
    assert body["final_entry_ready"] is False
    assert body["final_action_hint"] == "watch"
    assert body["action"] == "hold"
    assert body["order_id"] is None
    assert body["result"] == "preview_only"
    assert body["reason"] == "kr_trading_disabled"
    assert body["trigger_block_reason"] == "kr_trading_disabled"
    assert body["trade_result"]["action"] == "hold"
    assert body["trade_result"]["risk_approved"] is False
    assert body["trade_result"]["approved_by_risk"] is False
    assert body["trade_result"]["order_id"] is None
    assert body["top_quant_candidates"] == []
    assert body["researched_candidates"] == []
    assert len(body["final_ranked_candidates"]) == 8
    assert body["count"] == 8
    item = body["items"][0]
    ranked = body["final_ranked_candidates"][0]
    assert ranked["symbol"] == item["symbol"]
    assert item["symbol"] == "005930"
    assert item["current_price"] == 72000.0
    assert item["currency"] == "KRW"
    assert item["score"] is None
    assert item["note"] == "Price-only preview; technical indicators not calculated yet."
    assert item["indicator_status"] == "price_only"
    assert item["indicator_payload"]["ema20"] is None
    assert item["quant_buy_score"] is None
    assert item["quant_sell_score"] is None
    assert item["ai_buy_score"] is None
    assert item["ai_sell_score"] is None
    assert item["final_buy_score"] is None
    assert item["final_sell_score"] is None
    assert item["confidence"] is None
    assert item["action"] == "hold"
    assert item["action_hint"] == "watch"
    assert item["entry_ready"] is False
    assert item["trade_allowed"] is False
    assert item["approved_by_risk"] is False
    assert "kr_trading_disabled" in item["risk_flags"]
    assert "preview_only" in item["risk_flags"]
    assert "KR preview uses the shared signal/risk vocabulary but trading is disabled." in item["gating_notes"]
    assert item["block_reason"] == "insufficient_indicator_data"
    assert _has_hangul(item["gpt_reason"])
    assert "preview_only" in item["block_reasons"]
    assert "kr_trading_disabled" in item["block_reasons"]
    assert "preview_only" in item["warnings"]
    assert "kr_trading_disabled" in item["warnings"]


def test_kis_preview_does_not_call_submit_order(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_order",
        lambda *args, **kwargs: pytest.fail("preview must not submit orders"),
    )

    response = client.post("/kis/watchlist/preview")

    assert response.status_code == 200


def test_kis_preview_market_closed_warns_but_still_previews(monkeypatch, client):
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.MarketSessionService.get_session_status",
        lambda self, market: {
            "market": "KR",
            "timezone": "Asia/Seoul",
            "is_market_open": False,
            "is_entry_allowed_now": False,
            "is_near_close": False,
            "closure_reason": "holiday_labor_day",
            "closure_name": "Labor Day",
            "effective_close": "15:30",
            "no_new_entry_after": "15:00",
        },
    )

    response = client.post("/kis/watchlist/preview")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 8
    assert body["market_session"]["closure_reason"] == "holiday_labor_day"
    assert "market_closed" in body["warnings"]
    assert "holiday_labor_day" in body["warnings"]
    assert "market_closed" in body["items"][0]["warnings"]


def test_kis_preview_per_symbol_failure_continues(monkeypatch, client):
    def fake_price(self, symbol):
        if symbol == "005930":
            raise RuntimeError("price unavailable")
        return {"symbol": symbol, "current_price": 50000.0}

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_stock_price",
        fake_price,
    )

    response = client.post("/kis/watchlist/preview")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 8
    assert body["items"][0]["symbol"] == "005930"
    assert body["items"][0]["current_price"] is None
    assert body["items"][0]["indicator_status"] == "insufficient_data"
    assert body["items"][0]["quant_buy_score"] is None
    assert body["items"][0]["error"] is not None
    assert body["final_ranked_candidates"][0]["symbol"] == "005930"
    assert body["final_ranked_candidates"][0]["score"] is None
    assert body["items"][1]["current_price"] == 50000.0


def test_kis_preview_with_enough_bars_returns_grounded_scores(monkeypatch, client):
    captured_payloads = []

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_daily_bars",
        lambda self, symbol, limit=120: _daily_bars(60),
    )

    def fake_gpt(self, **kwargs):
        captured_payloads.append(kwargs["indicator_payload"])
        return KisGptPreview(
            gpt_used=True,
            action_hint="candidate",
            gpt_reason="Advisory score based on KIS OHLCV indicators.",
            warnings=[],
            ai_buy_score=66.0,
            ai_sell_score=18.0,
            confidence=0.72,
        )

    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisPreviewGptAdvisor.analyze",
        fake_gpt,
    )

    response = client.post("/kis/watchlist/preview")

    assert response.status_code == 200
    body = response.json()
    item = body["items"][0]
    assert item["indicator_status"] == "ok"
    assert item["indicator_payload"]["ema20"] is not None
    assert item["indicator_payload"]["ema50"] is not None
    assert item["indicator_payload"]["rsi"] is not None
    assert item["indicator_payload"]["vwap"] is not None
    assert item["indicator_payload"]["atr"] is not None
    assert item["indicator_payload"]["volume_ratio"] is not None
    assert item["indicator_payload"]["momentum"] is not None
    assert item["indicator_payload"]["recent_return"] is not None
    assert item["quant_buy_score"] is not None
    assert item["quant_sell_score"] is not None
    assert item["ai_buy_score"] == 66.0
    assert item["ai_sell_score"] == 18.0
    assert item["final_buy_score"] is not None
    assert item["final_sell_score"] is not None
    assert item["confidence"] == 0.72
    assert item["action"] == "hold"
    assert item["action_hint"] == "watch"
    assert item["entry_ready"] is False
    assert item["trade_allowed"] is False
    assert item["approved_by_risk"] is False
    assert item["should_trade"] is False
    assert item["trading_enabled"] is False
    assert item["order_id"] is None
    assert item["block_reason"] == "kr_trading_disabled"
    assert body["quant_candidates_count"] == 8
    assert body["researched_candidates_count"] == 8
    assert body["top_quant_candidates"]
    assert body["final_best_candidate"]["symbol"] == "005930"
    assert body["best_score"] is not None
    assert body["should_trade"] is False
    assert body["final_entry_ready"] is False
    assert body["trade_result"]["approved_by_risk"] is False
    assert captured_payloads
    assert captured_payloads[0]["ema20"] is not None


def test_kis_preview_with_insufficient_bars_keeps_scores_null(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_daily_bars",
        lambda self, symbol, limit=120: _daily_bars(8),
    )

    response = client.post("/kis/watchlist/preview")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["indicator_status"] == "insufficient_data"
    assert item["quant_buy_score"] is None
    assert item["quant_sell_score"] is None
    assert item["ai_buy_score"] is None
    assert item["final_buy_score"] is None
    assert item["block_reason"] == "insufficient_indicator_data"
    assert item["entry_ready"] is False
    assert item["trade_allowed"] is False
    assert item["approved_by_risk"] is False


def test_kis_preview_gpt_unavailable_keeps_quant_scores(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_daily_bars",
        lambda self, symbol, limit=120: _daily_bars(60),
    )

    def fail_gpt(self, **kwargs):
        assert kwargs["indicator_payload"]["ema20"] is not None
        return KisGptPreview(
            gpt_used=False,
            action_hint="watch",
            gpt_reason="GPT preview unavailable; quant-only fallback.",
            warnings=["gpt_unavailable"],
            risk_flags=["gpt_unavailable"],
        )

    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisPreviewGptAdvisor.analyze",
        fail_gpt,
    )

    response = client.post("/kis/watchlist/preview")

    assert response.status_code == 200
    body = response.json()
    item = body["items"][0]
    assert body["gpt_analysis_included"] is False
    assert item["indicator_status"] == "ok"
    assert item["quant_buy_score"] is not None
    assert item["ai_buy_score"] is None
    assert item["final_buy_score"] == item["quant_buy_score"]
    assert "gpt_unavailable" in item["warnings"]
    assert "gpt_unavailable" in item["risk_flags"]
    assert item["entry_ready"] is False
    assert item["trade_allowed"] is False
    assert item["approved_by_risk"] is False


def test_kis_preview_gpt_failure_falls_back_to_quant(monkeypatch, client):
    def fail_gpt(self, **kwargs):
        return KisGptPreview(
            gpt_used=False,
            action_hint="watch",
            gpt_reason="GPT preview unavailable; price-only fallback.",
            warnings=["gpt_unavailable"],
        )

    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisPreviewGptAdvisor.analyze",
        fail_gpt,
    )

    response = client.post("/kis/watchlist/preview")

    assert response.status_code == 200
    body = response.json()
    assert body["gpt_analysis_included"] is False
    assert body["items"][0]["quant_buy_score"] is None
    assert body["items"][0]["final_buy_score"] is None
    assert "gpt_unavailable" in body["items"][0]["warnings"]
    assert "gpt_unavailable" in body["items"][0]["risk_flags"]
    assert body["items"][0]["entry_ready"] is False


def test_kis_preview_kr_trading_remains_disabled(client):
    response = client.post("/kis/watchlist/preview")

    assert response.status_code == 200
    body = response.json()
    assert body["trading_enabled"] is False
    assert body["should_trade"] is False
    assert all(item["trade_allowed"] is False for item in body["items"])
    assert all(item["approved_by_risk"] is False for item in body["items"])
    assert body["order_id"] is None


def test_kis_preview_does_not_call_kis_order_paths(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_daily_bars",
        lambda self, symbol, limit=120: _daily_bars(60),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("preview must not submit KIS orders"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.build_domestic_order_payload",
        lambda *args, **kwargs: pytest.fail("preview must not build order payloads"),
    )

    response = client.post("/kis/watchlist/preview")

    assert response.status_code == 200


def test_kis_gpt_prompt_requires_korean_advisory():
    fake_client = _FakeOpenAIClient(
        json.dumps(
            {
                "ai_buy_score": 66,
                "ai_sell_score": 18,
                "confidence": 0.72,
                "action": "hold",
                "action_hint": "watch",
                "gpt_reason": "지표는 양호하지만 KR 실거래가 비활성화되어 참고용입니다.",
                "risk_flags": ["preview_only"],
                "gating_notes": ["kr_trading_disabled"],
                "hard_block_reason": "kr_trading_disabled",
            },
            ensure_ascii=False,
        )
    )
    advisor = KisPreviewGptAdvisor(
        settings=_settings(openai_api_key="test-openai-key"),
        client=fake_client,
    )

    payload = advisor._call_openai(
        symbol="005930",
        name="삼성전자",
        current_price=72000.0,
        indicator_status="ok",
        indicator_payload=_scoreable_indicator_payload(),
        market_session=_open_market_session(),
        reference_sources=[],
    )
    result = advisor._normalize_payload(
        payload,
        indicator_status="ok",
        indicator_payload=_scoreable_indicator_payload(),
        market_session=_open_market_session(),
    )

    call = fake_client.responses.calls[0]
    assert "Respond in Korean" in call["instructions"]
    assert "Return reason and gpt_reason in Korean" in call["instructions"]
    assert "Return gpt_reason in Korean" in call["input"]
    assert _has_hangul(result.gpt_reason)
    assert result.risk_flags == ["preview_only"]
    assert result.action == "hold"
    assert result.action_hint == "watch"


def test_kis_gpt_english_response_uses_korean_fallback():
    fake_client = _FakeOpenAIClient(
        json.dumps(
            {
                "ai_buy_score": 66,
                "ai_sell_score": 18,
                "confidence": 0.72,
                "action": "hold",
                "action_hint": "watch",
                "reason": "Indicators are acceptable but this is advisory only.",
                "risk_flags": ["preview_only"],
                "gating_notes": ["kr_trading_disabled"],
                "hard_block_reason": "kr_trading_disabled",
            }
        )
    )
    advisor = KisPreviewGptAdvisor(
        settings=_settings(openai_api_key="test-openai-key"),
        client=fake_client,
    )

    payload = advisor._call_openai(
        symbol="005930",
        name="삼성전자",
        current_price=72000.0,
        indicator_status="ok",
        indicator_payload=_scoreable_indicator_payload(),
        market_session=_open_market_session(),
        reference_sources=[],
    )
    result = advisor._normalize_payload(
        payload,
        indicator_status="ok",
        indicator_payload=_scoreable_indicator_payload(),
        market_session=_open_market_session(),
    )

    assert _has_hangul(result.gpt_reason)
    assert "Indicators are acceptable" not in result.gpt_reason
    assert result.risk_flags == ["preview_only"]
    assert result.gating_notes == ["kr_trading_disabled"]
    assert result.action == "hold"
    assert result.action_hint == "watch"
