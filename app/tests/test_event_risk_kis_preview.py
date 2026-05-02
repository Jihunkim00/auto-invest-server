import json
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import CompanyEvent
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
def _safe_kis_preview(monkeypatch):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.get_settings",
        lambda: _settings(),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_stock_price",
        lambda self, symbol: {
            "symbol": symbol,
            "name": "Samsung Electronics",
            "current_price": 72000.0,
        },
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_daily_bars",
        lambda self, symbol, limit=120: [],
    )
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.MarketSessionService.get_session_status",
        lambda self, market: {
            "market": "KR",
            "timezone": "Asia/Seoul",
            "date": "2026-05-03",
            "is_market_open": True,
            "is_entry_allowed_now": True,
            "is_near_close": False,
            "closure_reason": None,
            "closure_name": None,
            "effective_close": "15:30",
            "no_new_entry_after": "15:00",
        },
    )


def _seed_kr_event(db_session, *, symbol="005930", event_date=date(2026, 5, 4)):
    row = CompanyEvent(
        market="KR",
        provider="investing",
        symbol=symbol,
        company_name="Samsung Electronics",
        event_type="earnings",
        event_date=event_date,
        event_time_label="after_close",
        source_url="https://kr.investing.com/earnings-calendar",
        title=f"{symbol} earnings",
        risk_level="high",
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_kis_preview_includes_event_risk_and_never_creates_order(
    monkeypatch,
    client,
    db_session,
):
    _seed_kr_event(db_session)
    captured_event_contexts = []

    def fake_gpt(self, **kwargs):
        captured_event_contexts.append(kwargs.get("event_context"))
        return KisGptPreview(
            gpt_used=True,
            action_hint="watch",
            gpt_reason="이벤트 위험으로 신규 진입은 보수적으로 봅니다.",
            warnings=[],
        )

    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisPreviewGptAdvisor.analyze",
        fake_gpt,
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("preview must not submit KIS orders"),
    )

    response = client.post("/kis/watchlist/preview")

    assert response.status_code == 200
    body = response.json()
    item = body["items"][0]
    assert item["event_risk"]["has_near_event"] is True
    assert item["event_risk"]["entry_blocked"] is True
    assert item["event_risk"]["source"] == "investing"
    assert "event_risk_entry_block" in item["risk_flags"]
    assert "near_earnings_event" in item["block_reasons"]
    assert item["order_id"] is None
    assert item["trading_enabled"] is False
    assert item["should_trade"] is False
    assert captured_event_contexts[0]["entry_blocked"] is True


def test_kis_preview_event_data_unavailable_warns_without_order(
    monkeypatch,
    client,
):
    monkeypatch.setattr(
        "app.services.event_risk_service.EventRiskService.get_event_risk",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("fetch failed")),
    )
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.KisPreviewGptAdvisor.analyze",
        lambda self, **kwargs: KisGptPreview(
            gpt_used=True,
            action_hint="watch",
            gpt_reason="이벤트 데이터가 없어 기존 기준으로 관찰합니다.",
            warnings=[],
        ),
    )

    response = client.post("/kis/watchlist/preview")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert "event_data_unavailable" in item["warnings"]
    assert item["event_risk"]["entry_blocked"] is False
    assert item["order_id"] is None


class _FakeResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text=json.dumps(
                {
                    "action": "hold",
                    "action_hint": "watch",
                    "gpt_reason": "실적 이벤트는 불확실성 위험입니다.",
                    "risk_flags": ["event_risk_entry_block"],
                    "gating_notes": ["event_context_present"],
                },
                ensure_ascii=False,
            )
        )


class _FakeOpenAIClient:
    def __init__(self):
        self.responses = _FakeResponses()


def test_kis_gpt_prompt_includes_event_context_and_not_bullish_rule():
    fake_client = _FakeOpenAIClient()
    advisor = KisPreviewGptAdvisor(
        settings=_settings(openai_api_key="test-openai-key"),
        client=fake_client,
    )

    advisor._call_openai(
        symbol="005930",
        name="Samsung Electronics",
        current_price=72000,
        indicator_status="ok",
        indicator_payload={"ema20": 70000, "ema50": 68000, "rsi": 55},
        market_session={"market": "KR", "is_market_open": True},
        reference_sources=[],
        event_context={
            "has_near_event": True,
            "event_type": "earnings",
            "days_to_event": 1,
            "event_time_label": "after_close",
            "entry_blocked": True,
            "scale_in_blocked": True,
            "position_size_multiplier": 0.0,
        },
    )

    call = fake_client.responses.calls[0]
    assert "Earnings or earnings-call events are uncertainty risks" in call["instructions"]
    assert "Do not treat upcoming earnings as a reason to buy" in call["instructions"]
    assert '"event_context"' in call["input"]
    assert '"risk_policy": "block_new_entry"' in call["input"]
