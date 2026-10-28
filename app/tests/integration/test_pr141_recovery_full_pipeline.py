"""Synthetic OHLCV and GPT responses; real A/C/Final, risk and FakeBroker.

Separate from October 28 recorded evidence: that DB has no 13:30 C/GPT input.
"""
from collections import Counter
from datetime import UTC, datetime, timedelta
import json

import pytest

from app.db.database import SessionLocal
from app.db.models import AutomationSchedulerSlot, OrderLog, WatchlistSnapshotRun
from app.services.market_data_snapshot_service import MarketDataSnapshotService
from app.services.watchlist_snapshot_policy import check_snapshot_read
from app.services.watchlist_snapshot_scheduler import WatchlistSnapshotScheduler
from app.services.watchlist_snapshot_service import WatchlistSnapshotService
from app.tests.integration.test_pr138_full_pipeline_replay import setup_pipeline, synthetic_bars
from app.tests.support.production_replay_oct28 import at


@pytest.fixture(autouse=True)
def no_external_transport(monkeypatch, fake_kis_admin_credentials):
    def forbidden(*args, **kwargs):
        pytest.fail('PR141 synthetic pipeline forbids real HTTP/KIS/Alpaca submit')
    monkeypatch.setattr('requests.sessions.Session.request', forbidden)
    monkeypatch.setattr('httpx.Client.send', forbidden)
    monkeypatch.setattr('httpx.AsyncClient.send', forbidden)
    MarketDataSnapshotService.clear_process_cache()
    yield
    MarketDataSnapshotService.clear_process_cache()


@pytest.mark.parametrize('gpt_score,expected_submit', [(59, 0), (70, 1)])
def test_recovered_snapshot_preserves_hold_and_buy_score_gates(monkeypatch, gpt_score, expected_submit):
    with SessionLocal() as db:
        harness, scheduler, preview, responses, _ = setup_pipeline(db, monkeypatch,
            start_at=at('12:50:00'), analysis_times=('13:30',), gpt_score=gpt_score)
        daily, intraday = synthetic_bars(at('13:30:00'))
        # Keep the same synthetic price series but make its latest bar 13:29.
        for bar in intraday:
            bar['timestamp'] = (datetime.fromisoformat(bar['timestamp']) + timedelta(minutes=130)).isoformat()
        harness.client.get_domestic_daily_bars = lambda symbol, limit=120: daily[-limit:]
        harness.client.get_domestic_intraday_bars = lambda symbol, **kwargs: intraday
        calls, elapsed, remaining = Counter(), [0.0], [3]
        quote = harness.client.get_domestic_stock_price
        def wait(seconds):
            elapsed[0] += seconds
            harness.clock.current += timedelta(seconds=seconds)
            return False
        service = WatchlistSnapshotService(client=harness.client, now_provider=harness.clock.now,
            wait_provider=wait, monotonic_provider=lambda: elapsed[0])
        bad = service.load_universe()[0]['symbol']
        def faulty_quote(symbol):
            check_snapshot_read()
            calls[symbol] += 1
            if symbol == bad and remaining[0]:
                remaining[0] -= 1
                raise TimeoutError('known injected quote timeout')
            return quote(symbol)
        harness.client.get_domestic_stock_price = faulty_quote
        wait(1)
        failed = service.refresh(db)
        assert failed['status'] == 'failed'
        wait(15)
        refreshed = WatchlistSnapshotScheduler(service, session_factory=SessionLocal,
            now_provider=harness.clock.now)._recover_due()
        assert refreshed['status'] == 'success'
        assert calls[bad] == 4 and all(count == 1 for symbol, count in calls.items() if symbol != bad)
        assert db.get(WatchlistSnapshotRun, failed['id']).status == 'failed'

        harness.clock.current = at('13:30:00')
        scheduler._plan_admin_slots(harness.clock.now())
        with scheduler._task_supervisor.lock:
            tasks = list(scheduler._task_supervisor.tasks.values())
        for task in tasks:
            task['thread'].join(30)
            assert not task['thread'].is_alive()
        db.expire_all()
        ledger = db.query(AutomationSchedulerSlot).one()
        result = json.loads(ledger.result_json)
        assert ledger.status in {'completed', 'HOLD', 'blocked'}, ledger.reason
        top = [row for row in preview.result['items'] if row.get('selected_by_a_top5')]
        assert len(top) == 5 and all(row['quant_c_score'] >= 65 for row in top)
        assert len(responses.calls) == 5
        assert len(harness.broker.buy_calls) == expected_submit, result
        assert harness.client.external_kis_submit_count == 0
        if expected_submit:
            selected = preview.result['final_best_candidate']
            assert selected['ai_buy_score'] >= 60 and selected['final_buy_score'] >= 65
            assert result['profile_buy']['status'] == 'filled'
            assert harness.validation.calls[0].validated_for_submission
            assert db.query(OrderLog).one().internal_status == 'FILLED'
            assert harness.client.possible_order_calls == 1
        else:
            decision = next(gate['actual_value'] for gate in result['run_diagnostics']['gates']
                            if gate['gate_name'] == 'ENTRY_DECISION')
            assert decision['action'].lower() == 'hold'
            assert ledger.reason == 'gpt_buy_score_below_threshold'
            assert all(row['ai_buy_score'] == 59 and not row['a_top5_score_gate_passed'] for row in top)
            assert not harness.validation.calls and not db.query(OrderLog).count()
