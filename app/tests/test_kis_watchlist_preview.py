import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.main import app
from app.services.kis_watchlist_preview_service import KisGptPreview


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
    assert body["best_score"] is None
    assert body["should_trade"] is False
    assert body["action"] == "hold"
    assert body["result"] == "preview_only"
    assert body["reason"] == "kr_trading_disabled"
    assert body["top_quant_candidates"] == []
    assert body["researched_candidates"] == []
    assert body["final_ranked_candidates"] == []
    assert body["count"] == 8
    item = body["items"][0]
    assert item["symbol"] == "005930"
    assert item["current_price"] == 72000.0
    assert item["currency"] == "KRW"
    assert item["indicator_status"] == "price_only"
    assert item["indicator_payload"]["ema20"] is None
    assert item["quant_buy_score"] is None
    assert item["quant_sell_score"] is None
    assert item["ai_buy_score"] is None
    assert item["ai_sell_score"] is None
    assert item["final_buy_score"] is None
    assert item["final_sell_score"] is None
    assert item["confidence"] is None
    assert item["action_hint"] == "watch"
    assert item["entry_ready"] is False
    assert item["trade_allowed"] is False
    assert item["block_reason"] == "insufficient_indicator_data"
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
    assert body["items"][1]["current_price"] == 50000.0


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
    assert body["items"][0]["entry_ready"] is False


def test_kis_preview_kr_trading_remains_disabled(client):
    response = client.post("/kis/watchlist/preview")

    assert response.status_code == 200
    body = response.json()
    assert body["trading_enabled"] is False
    assert body["should_trade"] is False
    assert all(item["trade_allowed"] is False for item in body["items"])
