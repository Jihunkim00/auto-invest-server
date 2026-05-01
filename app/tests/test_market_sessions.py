from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.main import app
from app.services.market_session_service import MarketSessionService


def test_market_sessions_include_us_and_kr():
    service = MarketSessionService()

    sessions = {item["market"]: item for item in service.list_sessions()}

    assert set(sessions) >= {"US", "KR"}
    assert sessions["US"]["timezone"] == "America/New_York"
    assert sessions["US"]["enabled_for_scheduler"] is True


def test_kr_session_config_is_conservative():
    session = MarketSessionService().get_session("KR")

    assert session.timezone == "Asia/Seoul"
    assert session.regular_open == "09:00"
    assert session.regular_close == "15:30"
    assert session.no_new_entry_after == "15:00"
    assert session.force_manage_until == "15:20"
    assert session.enabled_for_scheduler is False


def test_kr_entry_allowed_before_no_new_entry_cutoff():
    service = MarketSessionService()
    now = datetime(2026, 5, 1, 14, 50, tzinfo=ZoneInfo("Asia/Seoul"))

    assert service.is_entry_allowed_now("KR", now) is True


def test_kr_entry_blocked_after_no_new_entry_cutoff():
    service = MarketSessionService()
    now = datetime(2026, 5, 1, 15, 5, tzinfo=ZoneInfo("Asia/Seoul"))

    assert service.is_entry_allowed_now("KR", now) is False


def test_kr_near_close_at_1520():
    service = MarketSessionService()
    now = datetime(2026, 5, 1, 15, 20, tzinfo=ZoneInfo("Asia/Seoul"))

    assert service.is_near_close("KR", now) is True


def test_market_sessions_endpoint_returns_us_and_kr():
    client = TestClient(app)

    response = client.get("/market-sessions")

    assert response.status_code == 200
    body = response.json()
    assert body["default_market"] == "US"
    markets = {item["market"]: item for item in body["markets"]}
    assert markets["KR"]["timezone"] == "Asia/Seoul"
    assert markets["KR"]["enabled_for_scheduler"] is False


def test_kr_market_session_endpoint_returns_config():
    client = TestClient(app)

    response = client.get("/market-sessions/KR")

    assert response.status_code == 200
    body = response.json()
    assert body["market"] == "KR"
    assert body["regular_open"] == "09:00"
    assert body["regular_close"] == "15:30"
    assert body["no_new_entry_after"] == "15:00"
