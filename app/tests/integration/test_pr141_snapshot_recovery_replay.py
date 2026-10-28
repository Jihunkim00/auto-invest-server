"""October 28 accounts/settings; known synthetic READ faults, never a claim
about the unrecorded cause of historical 229. Genuine new snapshot calculations.
"""
from collections import Counter
from datetime import UTC, timedelta

import pytest
import yaml

from app.db.models import (AutomationProfileWatchlistSnapshot, OrderLog,
    WatchlistSnapshotItem, WatchlistSnapshotRun)
from app.services.market_data_snapshot_service import MarketDataSnapshotService
from app.services.watchlist_snapshot_scheduler import WatchlistSnapshotScheduler
from app.services.watchlist_snapshot_service import WatchlistSnapshotService
from app.tests.integration.test_pr140_production_replay_20261028 import evidence, replay  # noqa: F401
from app.tests.integration.test_pr138_full_pipeline_replay import synthetic_bars
from app.tests.support.production_replay_oct28 import at
from app.tests.test_watchlist_snapshot_recovery import FaultKisClient


class ReplayClock:
    def __init__(self, replay):
        self.replay, self.elapsed = replay, 0.0

    def now(self):
        return self.replay.clock.now()

    def wait(self, seconds):
        self.elapsed += seconds
        self.replay.clock.current += timedelta(seconds=seconds)
        return False


def install_snapshot_reader(r, tmp_path, failures):
    r.import_snapshot(228)
    r.import_snapshot(229)
    r.clock.current = at('12:50:08')
    clock = ReplayClock(r)
    rows = r.evidence.raw[229]
    bad = rows[0]['symbol']
    universe = tmp_path / 'recovery-universe.yaml'
    universe.write_text(yaml.safe_dump({'symbols': [
        {key: row[key] for key in ('symbol', 'name', 'market')} for row in rows]}), encoding='utf-8')
    daily, intraday = synthetic_bars(clock.now())
    class NewDataFakeKisClient(FaultKisClient):
        def get_domestic_stock_price(self, symbol):
            self.read('quote', symbol)
            return {'symbol': symbol, 'name': symbol, 'current_price': intraday[-1]['close']}

        def get_domestic_daily_bars(self, symbol, limit=120):
            self.read('daily', symbol)
            return daily[-limit:]
    client = NewDataFakeKisClient(clock)
    client.faults['quote', bad] = failures
    MarketDataSnapshotService.clear_process_cache()
    service = WatchlistSnapshotService(client=client, universe_path=universe,
        now_provider=clock.now, wait_provider=clock.wait, monotonic_provider=lambda: clock.elapsed)
    return service, client, clock, bad


@pytest.mark.parametrize('recover', [True, False])
def test_1250_failure_recovers_before_both_slots_or_blocks_safely(replay, tmp_path, recover):
    r = replay
    service, client, clock, bad = install_snapshot_reader(r, tmp_path, 3 if recover else 100)
    with r.sessions() as db:
        failed = service.refresh(db)
        assert failed['status'] == 'failed' and failed['recovery']['status'] == 'pending'
        failed_id = failed['id']
    scheduler = WatchlistSnapshotScheduler(service, session_factory=r.sessions, now_provider=clock.now)
    for attempt in range(1 if recover else 3):
        with r.sessions() as db:
            job = service.latest_recovery(db)
            clock.wait((job.next_retry_at.replace(tzinfo=UTC) - clock.now().astimezone(UTC)).total_seconds())
        scheduler._recover_due()  # Actual scheduler recovery, not a hand-inserted success.
    with r.sessions() as db:
        latest = service.latest_run(db)
        assert latest.status == ('success' if recover else 'failed')
        assert latest.completed_at.replace(tzinfo=UTC) < at('13:30:00')
        assert db.get(WatchlistSnapshotRun, 229).status == 'failed'
        assert db.get(WatchlistSnapshotRun, failed_id).status == 'failed'
        assert service.latest_recovery(db).status == ('succeeded' if recover else 'exhausted')
        if recover:
            assert latest.scored_count == 200 and latest.error_count == 0
            assert db.query(WatchlistSnapshotItem).filter_by(run_id=latest.id).count() == 200
    count = Counter((stage, symbol) for stage, symbol, _ in client.reads)
    assert all(count['quote', row['symbol']] == 1 for row in r.evidence.raw[229] if row['symbol'] != bad)
    assert count['quote', bad] == (4 if recover else 12)
    assert all(b[2] - a[2] >= 1 for a, b in zip(client.reads, client.reads[1:]))

    # These real slots have no persisted historical C/GPT results because they
    # were blocked in production. A successful snapshot permits analysis only.
    admin = r.slot('13:30')
    user = r.slot('13:45', user=True)
    if recover:
        assert r.preview.calls == ['13:30'] and r.user_preview.calls == ['13:45']
        assert admin['block_reason'] != 'watchlist_snapshot_not_ready'
        assert user['root_reason'] != 'watchlist_snapshot_not_ready'
        with r.sessions() as db:
            snapshots = db.query(AutomationProfileWatchlistSnapshot).filter(
                AutomationProfileWatchlistSnapshot.scheduler_slot.in_(['13:30', '13:45'])).all()
            assert {(row.profile_id, row.owner_user_id) for row in snapshots} == {(5, 1), (8, 2)}
    else:
        assert admin['block_reason'] == 'watchlist_snapshot_not_ready'
        assert user['root_reason'] == 'watchlist_snapshot_not_ready'
        assert not r.preview.calls and not r.user_preview.calls
    assert not r.broker.calls
    assert user['unresolved_entry_count'] == 1  # Preserve test01's recorded risk.
    with r.sessions() as db:
        assert not db.query(OrderLog).filter(OrderLog.created_at >= at('12:50:00').astimezone(UTC)).count()
