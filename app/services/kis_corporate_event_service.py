from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.db.models import CompanyEvent
from app.services.kis_stop_loss_aware_feature_service import KST, number, timestamp
from app.services.market_calendar_service import MarketCalendarService

DISCLOSURE_TYPES = (
    ("배당락", "ex_dividend_date"), ("배당증가", "dividend_increase"),
    ("배당감소", "dividend_decrease"), ("배당", "dividend_announcement"),
    ("기업설명회", "earnings_call"), ("잠정실적", "earnings"),
    ("영업실적", "earnings"), ("주주총회", "shareholder_meeting"),
    ("유상증자", "rights_offering"), ("무상증자", "bonus_issue"),
    ("주식분할", "stock_split"), ("주식병합", "reverse_stock_split"),
    ("감자", "capital_reduction"), ("의무보유", "lockup_expiration"),
    ("자기주식취득", "share_repurchase"), ("주식소각", "share_cancellation"),
    ("거래정지해제", "trading_resumption"), ("거래정지", "trading_halt"),
)


def _date(raw):
    try:
        return date.fromisoformat(str(raw or ""))
    except ValueError:
        return None


def _distance(decision, target, calendar):
    first, last = sorted((decision, target))
    days = sum(calendar.is_trading_day("KR", first + timedelta(days=i))
               for i in range(1, (last - first).days + 1))
    return days if target >= decision else -days


def dividend_events(payload, symbol, seen):
    """Domestic Stock API 145 has no publication or ex-dividend date fields."""
    rows = payload.get("output1")
    if not isinstance(rows, list):
        return None
    events = []
    for row in rows:
        if str(row.get("sht_cd") or "").strip() != symbol:
            continue
        record = _date(row.get("record_date"))
        for field, kind in (
            ("record_date", "dividend_record_date"),
            ("divi_pay_dt", "dividend_payment_date"),
            ("stk_div_pay_dt", "stock_dividend_payment_date"),
        ):
            event_date = _date(row.get(field))
            if event_date:
                events.append({
                    "symbol": symbol, "event_type": kind, "event_date": event_date.isoformat(),
                    "source": "kis_ksd_dividend_145",
                    "source_reference": f"{symbol}:{record}:{row.get('divi_kind')}:{field}",
                    "verification_status": "verified", "publication_timestamp": None,
                    "first_seen_at": seen.isoformat(), "retrieved_at": seen.isoformat(),
                    "amount": number(row.get("per_sto_divi_amt")),
                    "risk_notes": ["ex_dividend_date_unknown"] if field == "record_date" else
                    ["payment_date_only"],
                })
    return events


def _stored_events(db, symbol, decision, end):
    events = []
    query = select(CompanyEvent).where(
        CompanyEvent.market == "KR", CompanyEvent.symbol == symbol,
        CompanyEvent.event_date >= decision.date() - timedelta(days=1),
        CompanyEvent.event_date <= end,
    )
    for row in db.scalars(query):
        try:
            raw = json.loads(row.raw_payload or "{}")
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        fetched = row.fetched_at.replace(tzinfo=UTC) if row.fetched_at.tzinfo is None else row.fetched_at
        publication = timestamp(raw.get("publication_timestamp"))
        if fetched > decision or (publication and publication > decision):
            continue
        verified = row.provider.lower() in {"opendart", "dart", "krx", "kind", "ksd", "kis"} and (
            bool(row.source_url) and raw.get("verification_status") == "verified"
        )
        events.append({
            "symbol": symbol, "event_type": row.event_type, "event_date": row.event_date.isoformat(),
            "source": row.provider, "source_reference": row.source_url,
            "publication_timestamp": publication.isoformat() if publication else None,
            "first_seen_at": fetched.isoformat(), "retrieved_at": fetched.isoformat(),
            "title": row.title, "verification_status": "verified" if verified else "reported",
            "amount": number(raw.get("amount")) if verified else None,
            "historical_price_multiplier": number(raw.get("historical_price_multiplier")) if verified else None,
            "risk_notes": [row.risk_level],
        })
    return events


def corporate_context(db, symbol, decision, days, dividend_snapshot, disclosures):
    end = decision.date() + timedelta(days=days)
    calendar = MarketCalendarService()
    events = _stored_events(db, symbol, decision, end)
    dividend_at, dividend_rows, cache_status = dividend_snapshot
    dividend_available = dividend_at is not None and dividend_at <= decision and dividend_rows is not None
    if dividend_available:
        events.extend(row for row in dividend_rows
                      if decision.date() - timedelta(days=1) <= _date(row["event_date"]) <= end)
    recent = []
    for row in disclosures.get("items", []):
        value = row.get("published_at")
        published = timestamp(value)
        if not published or len(str(value)) <= 10 or published > decision:
            continue
        title = str(row.get("title") or "")[:400]
        kind = next((event for phrase, event in DISCLOSURE_TYPES if phrase in title.replace(" ", "")),
                    "material_disclosure")
        recent.append({
            "symbol": symbol, "event_type": kind, "event_date": None,
            "publication_timestamp": published.isoformat(), "source": row.get("source") or "kis_news_titles",
            "source_reference": row.get("url") or f"{published.isoformat()}:{title}",
            "title": title, "verification_status": "title_only",
            "retrieved_at": disclosures.get("retrieved_at"), "risk_notes": ["event_date_unverified"],
        })
    for event in events + recent:
        event_at = _date(event.get("event_date"))
        event["trading_day_distance"] = _distance(decision.date(), event_at, calendar) if event_at else None
        observed = timestamp(event.get("publication_timestamp") or event.get("first_seen_at"))
        event["freshness_seconds"] = (decision - observed).total_seconds() if observed else None
    verified = any(row["verification_status"] == "verified" for row in events)
    return {
        "status": "verified_event" if verified else
        "none_found" if dividend_available and disclosures.get("available") else "unavailable",
        "events": events, "recent_disclosures": recent, "dividend_available": dividend_available,
        "dividend_retrieved_at": dividend_at.isoformat() if dividend_at else None,
        "dividend_cache": cache_status,
        "catalyst": "확인된 재료 없음" if verified or (dividend_available and disclosures.get("available"))
        else "기업 이벤트 데이터 확인 불가",
    }
