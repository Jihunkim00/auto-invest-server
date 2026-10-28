from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.db.database import SessionLocal
from app.services.watchlist_snapshot_service import WatchlistSnapshotService

logger = logging.getLogger(__name__)

KST = ZoneInfo('Asia/Seoul')
WATCHLIST_REFRESH_TIMES = ('08:50', '09:50', '10:50', '11:50', '12:50', '13:50')
BOOTSTRAP_MAX_AGE_SECONDS = 2 * 60 * 60


class WatchlistSnapshotScheduler:
    '''Independent non-trading refresh loop for the shared KR snapshot.'''

    def __init__(self, service: WatchlistSnapshotService | None = None,
                 *, session_factory: Callable[[], Any] = SessionLocal,
                 now_provider: Callable[[], datetime] | None = None,
                 poll_seconds: float = 15.0) -> None:
        self.service = service or WatchlistSnapshotService()
        self.session_factory = session_factory
        self.now_provider = now_provider or (lambda: datetime.now(UTC))
        self.poll_seconds = max(1.0, float(poll_seconds))
        self._stop_event = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name='watchlist-snapshot-refresh',
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lifecycle_lock:
            thread = self._thread
            self._stop_event.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        with self._lifecycle_lock:
            if self._thread is thread and (thread is None or not thread.is_alive()):
                self._thread = None

    def _run(self) -> None:
        self._bootstrap_if_needed()
        last_slot: str | None = None
        while not self._stop_event.is_set():
            now = self._now_kst()
            slot = now.strftime('%Y-%m-%d %H:%M')
            if now.strftime('%H:%M') in WATCHLIST_REFRESH_TIMES and slot != last_slot:
                self._run_refresh(reason='scheduled_slot')
                last_slot = slot
            else:
                self._recover_due()
            self._stop_event.wait(self.poll_seconds)

    def _bootstrap_if_needed(self) -> None:
        try:
            if self._recover_due() is not None:
                return
            should_refresh = False
            with self.session_factory() as db:
                latest_recovery = getattr(self.service, 'latest_recovery', None)
                job = latest_recovery(db) if callable(latest_recovery) else None
                if (job and job.status != 'succeeded'
                        and job.created_at.replace(tzinfo=UTC).astimezone(KST).date() == self._now_kst().date()):
                    # A restart cannot reset today's pending/exhausted budget.
                    # The next normal scheduled refresh may start a new chain.
                    return
                latest = self.service.latest_successful_run(db, market='KR')
                should_refresh = (
                    latest is None
                    or self._age_seconds(latest.completed_at) > BOOTSTRAP_MAX_AGE_SECONDS
                )
            if should_refresh:
                self._run_refresh(reason='startup_snapshot_missing_or_stale')
        except Exception:
            logger.warning('watchlist_snapshot_bootstrap_failed reason_code=snapshot_storage_unavailable')

    def _recover_due(self):
        recover = getattr(self.service, 'recover_due', None)
        if not callable(recover):
            return None
        try:
            with self.session_factory() as db:
                return recover(db, cancel_event=self._stop_event)
        except Exception:
            logger.warning('watchlist_snapshot_recovery_failed reason_code=snapshot_storage_unavailable')
            return None

    def _run_refresh(self, *, reason: str) -> None:
        try:
            with self.session_factory() as db:
                if reason == 'scheduled_slot' and isinstance(self.service, WatchlistSnapshotService):
                    latest = self.service.latest_run(db)
                    if latest and latest.started_at.replace(tzinfo=UTC).astimezone(KST).strftime('%Y-%m-%d %H:%M') == self._now_kst().strftime('%Y-%m-%d %H:%M'):
                        return  # Bootstrap/another process already covered this slot.
                if isinstance(self.service, WatchlistSnapshotService):
                    result = self.service.refresh(db, market='KR', cancel_event=self._stop_event)
                else:
                    result = self.service.refresh(db, market='KR')
                if result.get('status') == 'already_running':
                    logger.info('watchlist snapshot refresh skipped reason=already_running trigger=%s', reason)
        except Exception:
            logger.warning('watchlist_snapshot_refresh_failed trigger=%s reason_code=snapshot_storage_unavailable', reason)

    def _now_kst(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(KST)

    def _age_seconds(self, value: datetime | None) -> float:
        if value is None:
            return float('inf')
        completed = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        current = self.now_provider()
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return max(0.0, (current.astimezone(UTC) - completed).total_seconds())
