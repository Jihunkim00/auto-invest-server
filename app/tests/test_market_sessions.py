from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.main import app
from app.services.market_calendar_service import MarketCalendarService
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
    now = datetime(2026, 5, 4, 14, 50, tzinfo=ZoneInfo("Asia/Seoul"))

    assert service.is_entry_allowed_now("KR", now) is True


def test_kr_entry_blocked_after_no_new_entry_cutoff():
    service = MarketSessionService()
    now = datetime(2026, 5, 4, 15, 5, tzinfo=ZoneInfo("Asia/Seoul"))

    assert service.is_entry_allowed_now("KR", now) is False


def test_kr_near_close_at_1520():
    service = MarketSessionService()
    now = datetime(2026, 5, 4, 15, 20, tzinfo=ZoneInfo("Asia/Seoul"))

    assert service.is_near_close("KR", now) is True


def test_kr_labor_day_is_holiday():
    service = MarketCalendarService()
    holiday = service.get_holiday("KR", date(2026, 5, 1))

    assert holiday is not None
    assert holiday["name"] == "Labor Day"
    assert holiday["reason"] == "holiday_labor_day"
    assert service.is_holiday("KR", date(2026, 5, 1)) is True


def test_kr_labor_day_session_status_is_closed():
    service = MarketSessionService()
    now = datetime(2026, 5, 1, 9, 5, tzinfo=ZoneInfo("Asia/Seoul"))

    status = service.get_session_status("KR", now)

    assert status["is_market_open"] is False
    assert status["is_entry_allowed_now"] is False
    assert status["closure_reason"] == "holiday_labor_day"
    assert status["closure_name"] == "Labor Day"


def test_kr_normal_trading_day_0905_is_open_and_entry_allowed():
    service = MarketSessionService()
    now = datetime(2026, 5, 4, 9, 5, tzinfo=ZoneInfo("Asia/Seoul"))

    status = service.get_session_status("KR", now)

    assert status["is_market_open"] is True
    assert status["is_entry_allowed_now"] is True
    assert status["closure_reason"] is None


def test_us_session_uses_new_york_zoneinfo_dst():
    service = MarketSessionService()
    now = datetime(2026, 7, 1, 13, 35, tzinfo=UTC)

    status = service.get_session_status("US", now)

    assert status["timezone"] == "America/New_York"
    assert status["local_time"].endswith("-04:00")
    assert status["is_market_open"] is True


def test_us_early_close_uses_effective_close():
    service = MarketSessionService()
    now = datetime(2026, 11, 27, 13, 5, tzinfo=ZoneInfo("America/New_York"))

    status = service.get_session_status("US", now)

    assert status["effective_close"] == "13:00"
    assert status["is_market_open"] is False
    assert status["closure_reason"] == "early_close_thanksgiving"


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


def test_kr_market_session_status_endpoint_includes_closure_reason():
    client = TestClient(app)

    response = client.get("/market-sessions/KR/status")

    assert response.status_code == 200
    body = response.json()
    assert body["market"] == "KR"
    assert "closure_reason" in body
    assert "effective_close" in body
