from datetime import date

from app.db.models import CompanyEvent
from app.services.event_risk_service import EventRiskService


def _seed_event(
    db_session,
    *,
    symbol="AAPL",
    market="US",
    event_date=date(2026, 5, 4),
    event_type="earnings",
):
    row = CompanyEvent(
        market=market,
        provider="investing",
        symbol=symbol,
        company_name="Apple Inc",
        event_type=event_type,
        event_date=event_date,
        event_time_label="after_close",
        source_url="https://www.investing.com/earnings-calendar",
        title=f"{symbol} earnings",
        risk_level="high",
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_earnings_d_minus_one_blocks_new_buy(db_session):
    _seed_event(db_session, event_date=date(2026, 5, 4))
    service = EventRiskService()

    risk = service.get_event_risk(
        db_session,
        symbol="AAPL",
        market="US",
        as_of_date=date(2026, 5, 3),
        intent="entry",
    )

    assert risk["has_near_event"] is True
    assert risk["days_to_event"] == 1
    assert risk["entry_blocked"] is True
    assert risk["scale_in_blocked"] is True
    assert risk["position_size_multiplier"] == 0.0
    assert risk["force_gate_level"] == 1


def test_earnings_day_blocks_new_buy(db_session):
    _seed_event(db_session, event_date=date(2026, 5, 4))
    service = EventRiskService()

    risk = service.get_event_risk(
        db_session,
        symbol="AAPL",
        market="US",
        as_of_date=date(2026, 5, 4),
        intent="entry",
    )

    assert risk["days_to_event"] == 0
    assert risk["entry_blocked"] is True
    assert risk["risk_level"] == "high"


def test_earnings_d_minus_two_reduces_position_size(db_session):
    _seed_event(db_session, event_date=date(2026, 5, 4))
    service = EventRiskService()

    risk = service.get_event_risk(
        db_session,
        symbol="AAPL",
        market="US",
        as_of_date=date(2026, 5, 2),
        intent="entry",
    )

    assert risk["days_to_event"] == 2
    assert risk["entry_blocked"] is False
    assert risk["scale_in_blocked"] is True
    assert risk["position_size_multiplier"] == 0.5


def test_exit_intent_is_not_blocked_by_earnings(db_session):
    _seed_event(db_session, event_date=date(2026, 5, 4))
    service = EventRiskService()

    risk = service.get_event_risk(
        db_session,
        symbol="AAPL",
        market="US",
        as_of_date=date(2026, 5, 3),
        intent="exit",
    )

    assert risk["has_near_event"] is True
    assert risk["entry_blocked"] is False
    assert risk["scale_in_blocked"] is False
    assert risk["position_size_multiplier"] == 1.0


def test_no_event_keeps_existing_behavior(db_session):
    service = EventRiskService()

    risk = service.get_event_risk(
        db_session,
        symbol="AAPL",
        market="US",
        as_of_date=date(2026, 5, 3),
    )

    assert risk["has_near_event"] is False
    assert risk["entry_blocked"] is False
    assert risk["position_size_multiplier"] == 1.0
    assert risk["warnings"] == []
