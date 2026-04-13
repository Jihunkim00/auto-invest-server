from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.models import ReferenceSiteCache


@dataclass(slots=True)
class CachedSiteSummary:
    site_name: str
    url: str
    category: str | None
    summary: str
    fetched_at: datetime
    expires_at: datetime
    source_status: str


class ReferenceSiteCacheService:
    def __init__(self, ttl_minutes: int) -> None:
        self.ttl_minutes = max(1, ttl_minutes)

    def upsert_summaries(self, db: Session, symbol: str, summaries: list[dict]) -> int:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self.ttl_minutes)
        count = 0

        for item in summaries:
            site_name = str(item.get("name", "")).strip()
            if not site_name:
                continue

            row = (
                db.query(ReferenceSiteCache)
                .filter(ReferenceSiteCache.symbol == symbol.upper(), ReferenceSiteCache.site_name == site_name)
                .first()
            )
            if row is None:
                row = ReferenceSiteCache(symbol=symbol.upper(), site_name=site_name, url=str(item.get("url", "")), summary="")
                db.add(row)

            row.url = str(item.get("url", ""))
            row.category = item.get("category")
            row.summary = str(item.get("summary", ""))
            row.fetched_at = now
            row.expires_at = expires_at
            row.source_status = "fresh"
            count += 1

        db.commit()
        return count

    def get_fresh_summaries(self, db: Session, symbol: str) -> tuple[list[dict], bool]:
        now = datetime.now(timezone.utc)
        rows = (
            db.query(ReferenceSiteCache)
            .filter(ReferenceSiteCache.symbol == symbol.upper(), ReferenceSiteCache.expires_at > now)
            .order_by(ReferenceSiteCache.site_name.asc())
            .all()
        )
        summaries = [
            {
                "name": row.site_name,
                "url": row.url,
                "category": row.category,
                "summary": row.summary,
                "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            }
            for row in rows
        ]
        return summaries, bool(rows)
