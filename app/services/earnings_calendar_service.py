from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from typing import Any

import requests
from sqlalchemy.orm import Session

from app.db.models import CompanyEvent
from app.services.event_source_service import EventSource, EventSourceService


@dataclass(slots=True)
class ParsedEarningsEvent:
    market: str
    provider: str
    symbol: str
    event_date: date
    source_url: str
    title: str
    company_name: str | None = None
    event_type: str = "earnings"
    event_time_label: str = "unknown"
    eps_forecast: float | None = None
    revenue_forecast: float | None = None
    risk_level: str = "medium"
    raw_payload: dict[str, Any] | None = None


class EarningsCalendarService:
    def __init__(
        self,
        *,
        event_source_service: EventSourceService | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.event_source_service = event_source_service or EventSourceService()
        self.timeout_seconds = timeout_seconds

    def refresh_market(
        self,
        db: Session,
        *,
        market: str,
        html_by_url: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        normalized_market = str(market or "").strip().upper()
        sources = self.event_source_service.get_enabled_sources(
            market=normalized_market,
            type="earnings_calendar",
        )
        warnings: list[str] = []
        stored = 0
        events: list[ParsedEarningsEvent] = []

        for source in sources:
            try:
                html = (
                    html_by_url[source.url]
                    if html_by_url and source.url in html_by_url
                    else self.fetch_html(source.url)
                )
                parsed = self.parse_html(html, source=source)
                events.extend(parsed)
                stored += self.store_events(db, parsed)
            except Exception:
                warnings.append("event_data_unavailable")

        return {
            "market": normalized_market,
            "source_count": len(sources),
            "event_count": len(events),
            "stored_count": stored,
            "warnings": _dedupe(warnings),
        }

    def fetch_html(self, url: str) -> str:
        response = requests.get(
            url,
            timeout=self.timeout_seconds,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; auto-invest-server/1.0; "
                    "structured event risk)"
                )
            },
        )
        response.raise_for_status()
        return response.text

    def parse_html(self, html: str, *, source: EventSource) -> list[ParsedEarningsEvent]:
        parser = _EarningsTableParser()
        parser.feed(html or "")

        events: list[ParsedEarningsEvent] = []
        for row in parser.rows:
            event = self._row_to_event(row, source=source)
            if event is not None:
                events.append(event)
        return events

    def store_events(self, db: Session, events: list[ParsedEarningsEvent]) -> int:
        stored = 0
        for event in events:
            existing = (
                db.query(CompanyEvent)
                .filter(CompanyEvent.market == event.market)
                .filter(CompanyEvent.provider == event.provider)
                .filter(CompanyEvent.symbol == event.symbol)
                .filter(CompanyEvent.event_type == event.event_type)
                .filter(CompanyEvent.event_date == event.event_date)
                .filter(CompanyEvent.title == event.title)
                .first()
            )
            payload = {
                "market": event.market,
                "provider": event.provider,
                "symbol": event.symbol,
                "company_name": event.company_name,
                "event_type": event.event_type,
                "event_date": event.event_date,
                "event_time_label": event.event_time_label,
                "source_url": event.source_url,
                "title": event.title,
                "eps_forecast": event.eps_forecast,
                "revenue_forecast": event.revenue_forecast,
                "risk_level": event.risk_level,
                "raw_payload": json.dumps(event.raw_payload or {}, ensure_ascii=False),
                "fetched_at": datetime.now(UTC),
            }
            if existing:
                for key, value in payload.items():
                    setattr(existing, key, value)
            else:
                db.add(CompanyEvent(**payload))
            stored += 1
        db.commit()
        return stored

    def _row_to_event(
        self,
        row: dict[str, Any],
        *,
        source: EventSource,
    ) -> ParsedEarningsEvent | None:
        attrs = row.get("attrs") if isinstance(row.get("attrs"), dict) else {}
        cells = [str(item).strip() for item in row.get("cells", []) if str(item).strip()]
        combined_text = " ".join(cells)

        symbol = self._extract_symbol(attrs, cells, source.market)
        event_date = self._extract_date(attrs, cells)
        if not symbol or event_date is None:
            return None

        company_name = _clean_text(
            attrs.get("data-company")
            or attrs.get("data-name")
            or attrs.get("company")
            or self._guess_company_name(cells, symbol)
        )
        event_type = _event_type_from_text(
            attrs.get("data-event-type")
            or attrs.get("event-type")
            or attrs.get("data-event")
            or combined_text
        )
        title = _clean_text(
            attrs.get("title")
            or attrs.get("data-title")
            or combined_text
            or f"{symbol} {event_type}"
        )
        event_time_label = _event_time_label_from_text(
            attrs.get("data-event-time")
            or attrs.get("data-time")
            or attrs.get("time")
            or combined_text
        )

        return ParsedEarningsEvent(
            market=source.market,
            provider="investing",
            symbol=symbol,
            company_name=company_name or None,
            event_type=event_type,
            event_date=event_date,
            event_time_label=event_time_label,
            source_url=source.url,
            title=title,
            eps_forecast=_extract_float(attrs, "eps", "data-eps", "eps_forecast"),
            revenue_forecast=_extract_float(
                attrs,
                "revenue",
                "data-revenue",
                "revenue_forecast",
            ),
            risk_level="high" if event_type in {"earnings", "earnings_call"} else "medium",
            raw_payload={"attrs": attrs, "cells": cells},
        )

    @staticmethod
    def _extract_symbol(attrs: dict[str, Any], cells: list[str], market: str) -> str | None:
        candidates = [
            attrs.get("data-symbol"),
            attrs.get("symbol"),
            attrs.get("ticker"),
            attrs.get("data-ticker"),
        ] + cells
        if market == "KR":
            for value in candidates:
                match = re.search(r"\b\d{6}\b", str(value or ""))
                if match:
                    return match.group(0)
            return None

        for value in candidates:
            for token in re.findall(r"\b[A-Z][A-Z0-9.\-]{0,9}\b", str(value or "").upper()):
                if token not in {"EPS", "USD", "AM", "PM", "US"}:
                    return token
        return None

    @staticmethod
    def _extract_date(attrs: dict[str, Any], cells: list[str]) -> date | None:
        candidates = [
            attrs.get("data-event-date"),
            attrs.get("event-date"),
            attrs.get("data-date"),
            attrs.get("date"),
            attrs.get("data-event-datetime"),
        ] + cells
        for value in candidates:
            parsed = _parse_date(value)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _guess_company_name(cells: list[str], symbol: str) -> str | None:
        for cell in cells:
            text = _clean_text(cell)
            if text and symbol not in text and _parse_date(text) is None:
                return text
        return None


class _EarningsTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self._current_row: dict[str, Any] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized == "tr":
            self._current_row = {
                "attrs": {key: value for key, value in attrs if value is not None},
                "cells": [],
            }
        elif normalized in {"td", "th"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"td", "th"} and self._current_row is not None:
            text = _clean_text(" ".join(self._current_cell or []))
            self._current_row["cells"].append(text)
            self._current_cell = None
        elif normalized == "tr" and self._current_row is not None:
            self.rows.append(self._current_row)
            self._current_row = None
            self._current_cell = None


def _event_type_from_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "earnings call" in text or "conference call" in text:
        return "earnings_call"
    if "earnings" in text or "eps" in text or "실적" in text:
        return "earnings"
    return "unknown"


def _event_time_label_from_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    if any(token in text for token in ("before open", "before market", "bmo", "장전")):
        return "before_open"
    if any(token in text for token in ("after close", "after market", "amc", "장후")):
        return "after_close"
    if any(token in text for token in ("during market", "intraday", "장중")):
        return "during_market"
    return "unknown"


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("/", "-")
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if not match:
        return None
    year, month, day = (int(match.group(index)) for index in (1, 2, 3))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _extract_float(attrs: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = attrs.get(key)
        if value is None:
            continue
        text = str(value).strip().replace(",", "")
        try:
            return float(text)
        except ValueError:
            continue
    return None


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
