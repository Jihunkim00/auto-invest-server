from pathlib import Path

from app.services.earnings_calendar_service import EarningsCalendarService
from app.services.event_source_service import EventSourceService


def test_event_source_service_loads_structured_earnings_sources():
    service = EventSourceService()

    kr_sources = service.get_enabled_sources(market="KR", type="earnings_calendar")
    us_sources = service.get_enabled_sources(market="US", type="earnings_calendar")

    assert len(kr_sources) == 1
    assert kr_sources[0].name == "Investing Earnings Calendar KR"
    assert kr_sources[0].url == "https://kr.investing.com/earnings-calendar"
    assert len(us_sources) == 1
    assert us_sources[0].name == "Investing Earnings Calendar US"
    assert us_sources[0].type == "earnings_calendar"


def test_event_source_service_ignores_disabled_or_invalid_sources():
    config = Path("app/tests/_tmp_event_sources.yaml")
    try:
        config.write_text(
            """
sources:
  - name: Disabled
    market: US
    type: earnings_calendar
    url: https://www.investing.com/earnings-calendar
    enabled: false
  - name: Bad Market
    market: EU
    type: earnings_calendar
    url: https://example.com
    enabled: true
  - name: Valid
    market: KR
    type: earnings_calendar
    url: https://kr.investing.com/earnings-calendar
    enabled: true
""",
            encoding="utf-8",
        )

        service = EventSourceService(config_path=str(config))

        assert [source.name for source in service.get_enabled_sources()] == ["Valid"]
    finally:
        if config.exists():
            config.unlink()


def test_earnings_calendar_parser_normalizes_structured_rows():
    config = Path("app/tests/_tmp_event_sources.yaml")
    try:
        config.write_text(
            """
sources:
  - name: Investing Earnings Calendar US
    market: US
    type: earnings_calendar
    url: https://www.investing.com/earnings-calendar
    enabled: true
""",
            encoding="utf-8",
        )
        source = EventSourceService(config_path=str(config)).get_enabled_sources()[0]
        html = """
        <table>
          <tr data-symbol="AAPL" data-event-date="2026-05-04" data-event-time="after close" data-eps="1.23">
            <td>Apple Inc</td><td>Q2 earnings</td>
          </tr>
        </table>
        """

        events = EarningsCalendarService().parse_html(html, source=source)

        assert len(events) == 1
        event = events[0]
        assert event.symbol == "AAPL"
        assert event.market == "US"
        assert event.provider == "investing"
        assert event.event_type == "earnings"
        assert event.event_time_label == "after_close"
        assert event.eps_forecast == 1.23
    finally:
        if config.exists():
            config.unlink()
