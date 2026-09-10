from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.db.models import WatchlistSnapshotItem, WatchlistSnapshotRun
from app.services.watchlist_snapshot_service import (
    serialize_snapshot_item,
    serialize_snapshot_run,
)


class WatchlistSnapshotNotFoundError(LookupError):
    pass


class WatchlistSnapshotSelectionService:
    '''Apply user-specific selection rules to a completed shared snapshot.'''

    def __init__(self, *, now_provider: Callable[[], datetime] | None = None) -> None:
        self.now_provider = now_provider or (lambda: datetime.now(UTC))

    def select_candidates(
        self,
        db: Session,
        *,
        snapshot_id: int | None = None,
        price_cap_krw: float = 300000,
        min_quant_buy_score: float = 0,
        kospi_limit: int = 40,
        kosdaq_limit: int = 10,
        market: str = 'KR',
    ) -> dict[str, Any]:
        run = self._find_run(db, snapshot_id=snapshot_id, market=market)
        if run is None:
            raise WatchlistSnapshotNotFoundError('No successful KR watchlist snapshot exists.')

        rows = (
            db.query(WatchlistSnapshotItem)
            .filter(WatchlistSnapshotItem.run_id == run.id)
            .all()
        )
        eligible = [
            row for row in rows
            if row.current_price is not None
            and float(row.current_price) <= float(price_cap_krw)
            and float(row.quant_buy_score or 0) >= float(min_quant_buy_score)
            and row.market in {'KOSPI', 'KOSDAQ'}
        ]
        eligible.sort(key=lambda row: (
            -float(row.quant_buy_score or 0),
            float(row.quant_sell_score or 0),
            str(row.symbol or ''),
        ))
        selected = (
            [row for row in eligible if row.market == 'KOSPI'][:max(0, int(kospi_limit))]
            + [row for row in eligible if row.market == 'KOSDAQ'][:max(0, int(kosdaq_limit))]
        )
        selected.sort(key=lambda row: (
            0 if row.market == 'KOSPI' else 1,
            -float(row.quant_buy_score or 0),
            float(row.quant_sell_score or 0),
            str(row.symbol or ''),
        ))

        captured_at = max(
            (row.captured_at for row in rows if row.captured_at is not None),
            default=run.completed_at,
        )
        return {
            'snapshot_id': run.id,
            'captured_at': _iso(captured_at),
            'snapshot_age_seconds': _age_seconds(captured_at, self.now_provider()),
            'source_count': run.source_count,
            'scored_count': run.scored_count,
            'price_cap_krw': float(price_cap_krw),
            'min_quant_buy_score': float(min_quant_buy_score),
            'kospi_count': sum(row.market == 'KOSPI' for row in selected),
            'kosdaq_count': sum(row.market == 'KOSDAQ' for row in selected),
            'total_count': len(selected),
            'candidates': [serialize_snapshot_item(row) for row in selected],
        }

    def latest(self, db: Session, *, market: str = 'KR') -> dict[str, Any]:
        run = self._find_run(db, snapshot_id=None, market=market, include_failed=False)
        if run is None:
            return {'snapshot': None, 'items': []}
        rows = (
            db.query(WatchlistSnapshotItem)
            .filter(WatchlistSnapshotItem.run_id == run.id)
            .order_by(WatchlistSnapshotItem.id.asc())
            .all()
        )
        return {
            'snapshot': serialize_snapshot_run(run),
            'items': [serialize_snapshot_item(row) for row in rows],
        }

    def status(self, db: Session, *, market: str = 'KR', refresh_running: bool = False) -> dict[str, Any]:
        latest = (
            db.query(WatchlistSnapshotRun)
            .filter(WatchlistSnapshotRun.market == str(market or 'KR').strip().upper())
            .order_by(WatchlistSnapshotRun.started_at.desc(), WatchlistSnapshotRun.id.desc())
            .first()
        )
        successful = self._find_run(db, snapshot_id=None, market=market, include_failed=False)
        return {
            'market': str(market or 'KR').strip().upper(),
            'refresh_running': bool(refresh_running),
            'latest_run': serialize_snapshot_run(latest) if latest else None,
            'latest_successful_snapshot_id': successful.id if successful else None,
            'refresh_times': ['08:50', '09:50', '10:50', '11:50', '12:50', '13:50'],
            'timezone': 'Asia/Seoul',
        }

    def _find_run(self, db: Session, *, snapshot_id: int | None, market: str,
                  include_failed: bool = False) -> WatchlistSnapshotRun | None:
        query = db.query(WatchlistSnapshotRun).filter(
            WatchlistSnapshotRun.market == str(market or 'KR').strip().upper(),
        )
        if snapshot_id is not None:
            query = query.filter(WatchlistSnapshotRun.id == int(snapshot_id))
        else:
            query = query.order_by(
                WatchlistSnapshotRun.completed_at.desc(),
                WatchlistSnapshotRun.id.desc(),
            )
        if not include_failed:
            query = query.filter(WatchlistSnapshotRun.status == 'success')
        return query.first()


def _age_seconds(captured_at: datetime | None, now: datetime) -> float | None:
    if captured_at is None:
        return None
    captured = _as_utc(captured_at)
    current = _as_utc(now)
    return round(max(0.0, (current - captured).total_seconds()), 3)


def _iso(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat().replace('+00:00', 'Z') if value else None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
