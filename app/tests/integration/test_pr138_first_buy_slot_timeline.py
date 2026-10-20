"""First BUY slots are 11:20 admin / 11:30 test01, never morning preparation.

Uses the real scheduler thread, profile queries, atomic claims, user dispatcher,
analysis and TradeRunLog persistence against pytest's isolated file database.
All market/account inputs and GPT responses are synthetic. No external HTTP.
"""
from datetime import UTC, datetime, timedelta
import json
import threading
import time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.exc import OperationalError

from app.brokers.base import KisApiError
from app.db.database import SessionLocal
from app.db.models import (
    AutomationProfileAiCandidateResult, AutomationSchedulerSlot, OrderLog,
    PositionLifecycle, TradeRunLog, UserAutoTradingSlotClaim,
)
from app.services.profile_aware_dry_run_auto_buy_service import CANONICAL_MODE
from app.services.user_auto_trading_scheduler_service import (
    UserAutoTradingCandidateService,
)
from app.services.watchlist_snapshot_service import WatchlistSnapshotService
from app.tests.integration.test_pr138_full_pipeline_replay import (
    ClockSession, FakeResponses, RecordingPreview, setup_pipeline, synthetic_bars,
)
from app.services.kis_watchlist_preview_service import KisPreviewGptAdvisor
from app.services.kr_market_context_service import KrMarketContextService
from app.services.market_data_snapshot_service import MarketDataSnapshotService
from app.tests.test_user_auto_trading_scheduler_pr129 import _user, _configure_user, _harness

KST = ZoneInfo('Asia/Seoul')
ADMIN_SLOTS = ('11:20', '12:20', '13:40')
USER_SLOTS = ('11:30', '12:30', '13:30')
TIMES = ('09:17:00', '10:00:00', '11:19:50', '11:20:00', '11:29:50',
         '11:30:00', '12:20:00', '12:30:00', '13:30:00', '13:40:00')


def at(value):
    return datetime.fromisoformat(f'2026-10-20T{value}').replace(tzinfo=KST)


@pytest.fixture(autouse=True)
def no_external_http(monkeypatch, fake_kis_admin_credentials):
    def forbidden(*args, **kwargs):
        raise AssertionError('Real KIS / GPT HTTP and real KIS submit forbidden')
    monkeypatch.setattr('requests.sessions.Session.request', forbidden)
    monkeypatch.setattr('httpx.Client.send', forbidden)
    monkeypatch.setattr('httpx.AsyncClient.send', forbidden)
    monkeypatch.setattr('app.brokers.kis_client.KisClient.submit_domestic_cash_order', forbidden)


def drain(scheduler):
    deadline = time.monotonic() + 20
    while True:
        with scheduler._task_supervisor.lock:
            workers = [task.get('thread') for task in scheduler._task_supervisor.tasks.values()]
        if not workers:
            return
        assert time.monotonic() < deadline, 'Scheduler work did not finish at this virtual timestamp'
        for worker in workers:
            if worker is not None and worker.ident is not None:
                worker.join(.1)


def business_runs(db):
    return sorted((
        'admin' if row.mode == CANONICAL_MODE else 'test01',
        json.loads(row.request_payload)['scheduler_slot'],
    ) for row in db.query(TradeRunLog).filter(
        TradeRunLog.mode.in_([CANONICAL_MODE, 'user_scheduler'])).all())


def configure(db, monkeypatch, *, balance_error, discovery_error=False, buy=False):
    harness, scheduler, preview, responses, _ = setup_pipeline(
        db, monkeypatch, gpt_score=70 if buy else 59,
        start_at=at(TIMES[0]), analysis_times=ADMIN_SLOTS)
    state = SimpleNamespace(harness=harness, scheduler=scheduler, preview=preview,
        responses=responses, analysis=[], dispatch=[], maintenance=[], due_queries=[],
        balance_error=balance_error, discovery_error=discovery_error)
    user = _user(db, 'test01')
    _configure_user(db, user, provider='kis', kill_switch=False)
    profile = scheduler.automation_profiles.selected_owned_profile_schedule(
        db, owner_user_id=user.id, now=harness.clock.now())['profile']
    row = scheduler.automation_profiles.get_owned(db, profile['profile_key'], owner_user_id=user.id)
    settings = json.loads(row.settings_json)
    settings['entry']['analysis_times'] = list(USER_SLOTS)
    settings['capital'].update(sizing_mode='fixed_budget', fixed_budget=100000,
                               initial_budget_krw=100000, max_order_notional_krw=100000)
    settings['universe'].update(watchlist_size=50, top_quant_candidates=5,
        top_ai_candidates=5, min_price_krw=1000, max_price_krw=50000, min_volume_ratio=0)
    row.settings_json = json.dumps(settings)
    db.commit()
    state.user_id = user.id

    _, initial_minutes = synthetic_bars(at('11:20:00'))
    def minutes(symbol, **kwargs):
        # Extend the synthetic series to the current replay time, without
        # returning future bars or borrowing a previous session's minute data.
        count = max(0, int((harness.clock.now() - at('09:00:00')).total_seconds() // 60))
        return [dict(initial_minutes[min(index, len(initial_minutes)-1)],
                     timestamp=(at('09:00:00') + timedelta(minutes=index)).isoformat())
                for index in range(count)]
    harness.client.get_domestic_intraday_bars = minutes
    real_balance = harness.client.get_account_balance
    def balance():
        if balance_error and harness.clock.now() == at('09:17:00'):
            raise KisApiError('Synthetic KIS balance HTTP 500', details={
                'http_status': 500, 'path': '/uapi/domestic-stock/v1/trading/inquire-balance',
                'tr_id': 'TTTC8434R', 'read_operation': 'positions'})
        return real_balance()
    harness.client.get_account_balance = balance

    # Maintenance is a fake read probe, not a BUY or an analysis callback.
    # The real supervisor must contain its 09:17 exception and continue ticks.
    def preparation(now):
        def probe():
            state.maintenance.append(now.isoformat())
            harness.client.get_account_balance()
        scheduler._task_supervisor.launch('position-monitor', probe, timeout=120)
    monkeypatch.setattr(scheduler, '_plan_maintenance', preparation)

    real_admin_analysis = scheduler._run_profile_analysis
    def admin_analysis(db, **kwargs):
        state.analysis.append(('admin', kwargs['slot'], harness.clock.now().isoformat()))
        return real_admin_analysis(db, **kwargs)
    monkeypatch.setattr(scheduler, '_run_profile_analysis', admin_analysis)

    # Keep production user dispatch and processing; replace only external
    # account/client inputs using the existing FakeBroker/FakeKisClient harness.
    class RecordingCandidates(UserAutoTradingCandidateService):
        def select_candidates(self, db, **kwargs):
            state.analysis.append(('test01', kwargs['scheduler_slot'], harness.clock.now().isoformat()))
            return super().select_candidates(db, **kwargs)

    def user_service(*, automation_profiles):
        result, account, _analysis, broker, client = _harness()
        result.automation_profiles = automation_profiles
        result.now_provider = harness.clock.now
        result.session_service = ClockSession(harness.clock)
        result.execution_service.session_service = result.session_service
        # Per-user preview uses the same read-only synthetic market feed;
        # the candidate gate holds at GPT 59, so no user order can be submitted.
        user_preview = RecordingPreview(harness.client, session_service=result.session_service,
            gpt_advisor=KisPreviewGptAdvisor(settings=harness.client.settings,
                client=SimpleNamespace(responses=FakeResponses(score=59))),
            market_data_snapshot_service=MarketDataSnapshotService(harness.client, now_provider=harness.clock.now),
            market_context_service=KrMarketContextService(harness.client, alpaca_client=SimpleNamespace(),
                now_factory=harness.clock.now))
        result.candidate_service = RecordingCandidates(runtime_preview_service=user_preview)
        real_dispatch = result.run_provider_once
        def dispatch(db, **kwargs):
            state.dispatch.append((kwargs['scheduler_slot'], kwargs['owner_user_id'],
                                   harness.clock.now().isoformat()))
            output = real_dispatch(db, **kwargs)
            assert broker.buy_calls == [] and client.buy_calls == []
            return output
        result.run_provider_once = dispatch
        return result
    monkeypatch.setattr('app.services.automation_scheduler_service.UserAutoTradingSchedulerService', user_service)

    real_selected = scheduler._selected_profile_schedule
    def selected(now):
        if discovery_error and now == at('11:20:00') and threading.current_thread().name.endswith('admin-planner'):
            raise OperationalError('synthetic admin profile query', {}, RuntimeError('synthetic SQLite lock'))
        return real_selected(now)
    monkeypatch.setattr(scheduler, '_selected_profile_schedule', selected)
    users = scheduler.user_auto_trading_scheduler_service
    real_due = users.due_slots
    def due(db, *, provider, now):
        calculated = real_due(db, provider=provider, now=now)
        state.due_queries.append((now.isoformat(), provider, [slot for slot, _ in calculated]))
        if discovery_error and provider == 'kis' and now == at('11:30:00'):
            raise OperationalError('synthetic user due_slots query', {}, RuntimeError('synthetic SQLite lock'))
        return calculated
    monkeypatch.setattr(users, 'due_slots', due)
    return state


def run_clock(state, monkeypatch, times, inspect):
    scheduler, clock = state.scheduler, state.harness.clock
    completed = threading.Event()
    failures = []
    index = [0]
    clock.current = at(times[0])
    def advance(timeout=None):
        try:
            drain(scheduler)
            inspect(clock.now())
            index[0] += 1
            if index[0] == len(times):
                scheduler._stop_event.set()
                completed.set()
            else:
                clock.current = at(times[index[0]])
                if clock.now().strftime('%H:%M:%S') in {'11:19:50', '12:20:00', '13:30:00'}:
                    with SessionLocal() as db:
                        result = WatchlistSnapshotService(client=state.harness.client,
                            now_provider=clock.now).refresh(db)
                        assert result['status'] == 'success'
        except BaseException as exc:
            failures.append(exc)
            scheduler._stop_event.set()
            completed.set()
        return scheduler._stop_event.is_set()
    monkeypatch.setattr(scheduler._stop_event, 'wait', advance)
    assert scheduler.start()
    try:
        assert completed.wait(90), 'Virtual scheduler timeline did not complete'
    finally:
        scheduler.stop()
        drain(scheduler)
    if failures:
        raise failures[0]
    assert index[0] == len(times)


@pytest.mark.parametrize('balance_error,discovery_error', [(False, False), (True, False), (True, True)])
def test_first_buy_slots_and_trade_run_logs_in_time_order(monkeypatch, balance_error, discovery_error):
    with SessionLocal() as db:
        state = configure(db, monkeypatch, balance_error=balance_error, discovery_error=discovery_error)
    missing = {('admin', '11:20'), ('test01', '11:30')} if discovery_error else set()
    timeline = []
    def inspect(now):
        scheduler = state.scheduler
        assert scheduler.is_running()
        assert scheduler._last_heartbeat_at == now.astimezone(UTC)
        assert scheduler._last_tick_at == now.astimezone(UTC)
        health = scheduler.scheduler_health(now=now)
        assert health['scheduler_heartbeat_age_seconds'] == 0
        if now == at('10:00:00'):
            assert health['scheduler_health_status'] == 'healthy'
        configured = scheduler._profile_slots(now)
        assert {slot for slot, _hour, _minute in configured} == set(ADMIN_SLOTS)
        with SessionLocal() as db:
            profiles = scheduler.user_auto_trading_scheduler_service._eligible_user_profiles(
                db, provider='kis', market='KR', now=now)
            assert len(profiles) == 1
            assert scheduler.user_auto_trading_scheduler_service._profile_analysis_times(profiles[0][2]) == set(USER_SLOTS)
            expected = sorted((owner, slot) for owner, slots in (('admin', ADMIN_SLOTS), ('test01', USER_SLOTS))
                for slot in slots if at(slot + ':00') <= now and (owner, slot) not in missing)
            assert business_runs(db) == expected
            assert sorted((owner, slot) for owner, slot, _ in state.analysis) == expected
            expected_user = [slot for owner, slot in expected if owner == 'test01']
            assert sorted(slot for slot, _owner, _when in state.dispatch) == expected_user
            user_claims = db.query(UserAutoTradingSlotClaim).all()
            assert sorted(row.scheduler_slot for row in user_claims) == expected_user
            assert all(row.user_id == state.user_id and row.trading_date == '2026-10-20'
                       and row.provider == 'kis' for row in user_claims)
            claims = db.query(AutomationSchedulerSlot).all()
            assert len(claims) == 6
            for row in claims:
                assert row.started_at is None or row.started_at >= row.scheduled_at
                if row.scheduled_at > now.astimezone(UTC).replace(tzinfo=None):
                    assert row.status == 'pending' and row.started_at is None
            assert db.query(OrderLog).count() == 0
            if now < at('11:20:00'):
                assert db.query(TradeRunLog).count() == 0
                assert all(row.started_at is None for row in claims)
            due_user = [slots for when, provider, slots in state.due_queries
                        if when == now.isoformat() and provider == 'kis']
            assert due_user == [[now.strftime('%H:%M')] if now.strftime('%H:%M') in USER_SLOTS else []]
            timeline.append({'at': now.isoformat(), 'engine_running': True,
                'heartbeat_at': scheduler._last_heartbeat_at.isoformat(),
                'tick_at': scheduler._last_tick_at.isoformat(), 'health': health['scheduler_health_status'],
                'admin_profile_slots': sorted(slot for slot, _hour, _minute in configured),
                'user_profile_slots': list(USER_SLOTS), 'calculated_user_due_slots': due_user[0],
                'trade_run_slots': business_runs(db), 'user_dispatch_count': len(state.dispatch),
                'claimed_slots': sum(row.started_at is not None for row in claims),
                'slot_states': {row.slot_key: row.status for row in claims}})
    run_clock(state, monkeypatch, TIMES, inspect)
    with SessionLocal() as db:
        rows = db.query(AutomationSchedulerSlot).all()
        assert sum(row.status == 'missed' for row in rows) == len(missing)
        assert all(row.status in {'HOLD', 'blocked', 'completed', 'missed'} for row in rows)
    assert state.harness.broker.buy_calls == []
    assert state.harness.client.external_kis_submit_count == 0
    print('PR138_FIRST_SLOT_TIMELINE=' + json.dumps({'balance_0917_http500': balance_error,
        'injected_discovery_error': discovery_error, 'timeline': timeline}, ensure_ascii=False))


def test_recovered_real_loop_runs_first_admin_slot_through_fake_filled_buy(monkeypatch):
    with SessionLocal() as db:
        state = configure(db, monkeypatch, balance_error=True, buy=True)
    def inspect(now):
        assert state.scheduler._last_heartbeat_at == now.astimezone(UTC)
        with SessionLocal() as db:
            if now < at('11:20:00'):
                assert business_runs(db) == []
                assert db.query(OrderLog).count() == 0
            else:
                assert business_runs(db) == [('admin', '11:20')]
    run_clock(state, monkeypatch, TIMES[:4], inspect)
    with SessionLocal() as db:
        order = db.query(OrderLog).one()
        assert order.internal_status == 'FILLED'
        assert order.qty == 9
        assert db.query(PositionLifecycle).filter_by(status='open').count() == 1
        assert db.query(AutomationProfileAiCandidateResult).count() == 50
        assert len(state.harness.validation.calls) == 1
        assert state.harness.validation.calls[0].validated_for_submission
        assert len(state.harness.broker.buy_calls) == 1
        assert state.harness.client.external_kis_submit_count == 0
        output = state.preview.result
        assert len(output['runtime_input_symbols']) == 50
        assert len(state.responses.calls) == 5
        assert sum(item.get('quant_c_status') == 'analyzed' for item in output['items']) == 5
        selected = output['final_best_candidate']
        assert selected['quant_c_status'] == 'analyzed'
        assert selected['quant_c_score'] == 74.24
        assert selected['ai_buy_score'] == 70
        assert selected['final_buy_score'] == 73.18
        print('PR138_FIRST_SLOT_BUY=' + json.dumps({'simulation_only': True,
            'real_order_submitted': False, 'actual_kis_submit_count': 0, 'mock_submit_count': 1,
            'simulated_order_status': order.internal_status, 'symbol': order.symbol, 'quantity': order.qty,
            'c_score': selected['quant_c_score'], 'gpt_score': selected['ai_buy_score'],
            'final_score': selected['final_buy_score'], 'gpt': 'GPT MOCKED'}))
