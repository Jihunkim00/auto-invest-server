from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.calendar_gap_risk_service import CalendarGapRiskService
from app.services.market_calendar_service import MarketCalendarService


KST = ZoneInfo("Asia/Seoul")


def _calendar(tmp_path, *, holidays: str = ""):
    path = tmp_path / "market_holidays.yaml"
    path.write_text(
        "markets:\n"
        "  KR:\n"
        "    timezone: Asia/Seoul\n"
        "    holidays:\n"
        f"{holidays}",
        encoding="utf-8",
    )
    return MarketCalendarService(config_path=str(path))


def test_normal_thursday_to_friday_keeps_existing_thresholds(tmp_path):
    service = CalendarGapRiskService(_calendar(tmp_path))

    result = service.evaluate(
        "KR",
        now=datetime(2026, 10, 1, 10, 0, tzinfo=KST),
        existing_c_score=None,
        existing_final_score=65.0,
    )

    assert result["calendar_gap_days"] == 1
    assert result["next_trading_date"] == "2026-10-02"
    assert result["required_c_score"] is None
    assert result["required_final_score"] == 65.0
    assert result["position_size_multiplier"] == 1.0
    assert result["entry_blocked"] is False


def test_friday_weekend_gap_tightens_scores_and_size_before_cutoff(tmp_path):
    service = CalendarGapRiskService(_calendar(tmp_path))

    result = service.evaluate(
        "KR",
        now=datetime(2026, 10, 2, 12, 59, tzinfo=KST),
        existing_c_score=70.0,
        existing_final_score=65.0,
    )

    assert result["calendar_gap_days"] == 3
    assert result["required_c_score"] == 75.0
    assert result["required_final_score"] == 70.0
    assert result["position_size_multiplier"] == 0.5
    assert result["late_entry_cutoff_local"] == "13:00"
    assert result["entry_blocked"] is False
    assert result["risk_flags"] == ["weekend_gap_risk"]


def test_friday_at_1300_blocks_new_entries(tmp_path):
    service = CalendarGapRiskService(_calendar(tmp_path))

    result = service.evaluate(
        "KR",
        now=datetime(2026, 10, 2, 13, 0, tzinfo=KST),
    )

    assert result["entry_blocked"] is True
    assert result["block_reason"] == "weekend_gap_late_entry_block"
    assert result["calendar_gap_block_reason"] == "weekend_gap_late_entry_block"


def test_full_day_holiday_extends_friday_gap_to_four_days(tmp_path):
    service = CalendarGapRiskService(
        _calendar(
            tmp_path,
            holidays=(
                '      - date: "2026-10-05"\n'
                "        name: Test Holiday\n"
                "        reason: test_holiday\n"
                "        full_day: true\n"
            ),
        )
    )

    result = service.evaluate(
        "KR",
        now=datetime(2026, 10, 2, 10, 0, tzinfo=KST),
    )

    assert result["calendar_gap_days"] == 4
    assert result["next_trading_date"] == "2026-10-06"
    assert result["long_market_closure_ahead"] is True
    assert result["entry_blocked"] is True
    assert result["block_reason"] == "long_market_closure_ahead"


def test_non_full_day_holiday_does_not_remove_a_trading_day(tmp_path):
    service = CalendarGapRiskService(
        _calendar(
            tmp_path,
            holidays=(
                '      - date: "2026-10-05"\n'
                "        name: Early Close\n"
                "        reason: early_close\n"
                "        full_day: false\n"
            ),
        )
    )

    result = service.evaluate(
        "KR",
        now=datetime(2026, 10, 2, 10, 0, tzinfo=KST),
    )

    assert result["calendar_gap_days"] == 3
    assert result["next_trading_date"] == "2026-10-05"
    assert result["entry_blocked"] is False


def test_calendar_read_failure_fails_closed(tmp_path):
    service = CalendarGapRiskService(
        MarketCalendarService(config_path=str(tmp_path / "missing.yaml"))
    )

    result = service.evaluate(
        "KR",
        now=datetime(2026, 10, 2, 10, 0, tzinfo=KST),
    )

    assert result["entry_blocked"] is True
    assert result["block_reason"] == "calendar_gap_risk_unavailable"
    assert result["calendar_gap_risk_flags"] == ["calendar_gap_risk_unavailable"]


def test_next_trading_date_failure_fails_closed():
    class BrokenNextDateCalendar:
        def get_calendar(self, _market):
            return {"timezone": "Asia/Seoul"}

        def is_trading_day(self, _market, _value):
            return True

        def next_trading_date(self, _market, _value):
            raise RuntimeError("next_date_unavailable")

    result = CalendarGapRiskService(BrokenNextDateCalendar()).evaluate(
        "KR",
        now=datetime(2026, 10, 2, 10, 0, tzinfo=KST),
    )

    assert result["entry_blocked"] is True
    assert result["block_reason"] == "calendar_gap_risk_unavailable"
    assert result["calendar_gap_risk_flags"] == ["calendar_gap_risk_unavailable"]
