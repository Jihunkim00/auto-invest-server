"""Synthetic OHLCV reconstruction, production calculations, GPT MOCKED."""
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.db.database import SessionLocal
from app.db.models import AutomationProfileAiCandidateResult, AutomationSchedulerSlot, OrderLog, PositionLifecycle
from app.services.scheduler_service import AutomationSchedulerService
from app.services.kis_watchlist_preview_service import KisPreviewGptAdvisor, KisWatchlistPreviewService
from app.services.kis_order_validation_service import KisOrderValidationService
from app.services.kr_market_context_service import KrMarketContextService
from app.services.market_data_snapshot_service import MarketDataSnapshotService
from app.services.market_session_service import MarketSessionService
from app.services.watchlist_snapshot_service import WatchlistSnapshotService
from app.tests.integration.test_kis_automation_scheduler_replay import build_harness, candidate, CUSTOM_PROFILE_KEY
from app.tests.integration.test_kis_automation_full_lifecycle_replay import install_real_lifecycle_wiring

KST = ZoneInfo('Asia/Seoul')
VIRTUAL_NOW = datetime(2026, 10, 20, 11, 20, tzinfo=KST)


@pytest.fixture(autouse=True)
def no_external_transport(monkeypatch, fake_kis_admin_credentials):
    def forbidden(*args, **kwargs):
        pytest.fail('Real HTTP / actual KIS submit forbidden in PR138 replay')
    monkeypatch.setattr('requests.sessions.Session.request', forbidden)
    monkeypatch.setattr('httpx.Client.send', forbidden)
    monkeypatch.setattr('httpx.AsyncClient.send', forbidden)


class FakeResponses:
    def __init__(self, *, score=70, failure=False):
        self.calls = []
        self.score = score
        self.failure = failure

    def create(self, **kwargs):
        self.calls.append(json.loads(kwargs['input']))
        if self.failure:
            raise TimeoutError('synthetic GPT timeout')
        return SimpleNamespace(output_text=json.dumps({
            'ai_buy_score': self.score, 'ai_sell_score': 15, 'confidence': .85,
            'action': 'buy', 'reason': '합성 데이터에서 반등 지표와 거래량을 확인했습니다.',
            'risk_flags': [], 'gating_notes': [], 'hard_block_reason': None,
        }, ensure_ascii=False))


class ClockSession(MarketSessionService):
    def __init__(self, clock):
        super().__init__()
        self.clock = clock

    def get_session_status(self, market=None, *, now=None):
        return super().get_session_status(market, now=now or self.clock.now())


class RecordingPreview(KisWatchlistPreviewService):
    def run_preview(self, **kwargs):
        self.result = super().run_preview(**kwargs)
        return self.result


class RecordingValidation(KisOrderValidationService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []

    def validate(self, request, **kwargs):
        result = super().validate(request, **kwargs)
        self.calls.append(result)
        return result


def synthetic_bars(now):
    closes = [12000 * (.99 ** index) for index in range(50)]
    closes += [closes[-1] * (1.008 ** index) for index in range(1, 10)]
    daily = [{'timestamp': (now - timedelta(days=len(closes)-i)).date().isoformat(),
              'open': close * .999, 'high': close * 1.01, 'low': close * .99,
              'close': close, 'volume': 100000 + i * 1000}
             for i, close in enumerate(closes)]
    intraday = []
    for index in range(140):
        close = 10000 + .4 * index + .02 * index * index
        intraday.append({'timestamp': (now.replace(hour=9, minute=0) + timedelta(minutes=index)).isoformat(),
                         'open': close-2, 'high': close+3, 'low': close-3, 'close': close,
                         'volume': 10000 + index * 200})
    return daily, intraday


def setup_pipeline(db, monkeypatch, *, gpt_score=70, failure=False,
                   start_at=VIRTUAL_NOW, analysis_times=('11:20',)):
    harness = build_harness(db, monkeypatch, now=start_at, analysis_times=analysis_times,
                            candidates=[candidate(price=10442.02)])
    install_real_lifecycle_wiring(harness, monkeypatch)
    settings = harness.client.settings
    monkeypatch.setattr(settings, 'kis_enabled', True)
    monkeypatch.setattr(settings, 'kis_real_order_enabled', True)
    monkeypatch.setattr(settings, 'log_dir', None)
    harness.runtime.update_settings(db, {'quant_selection_mode': 'A_TOP5_C_GPT'})
    row = harness.profiles.get(db, CUSTOM_PROFILE_KEY)
    profile = json.loads(row.settings_json)
    profile['capital'].update(fixed_budget=100000, initial_budget_krw=100000)
    profile['universe'].update(watchlist_size=50, top_quant_candidates=5, top_ai_candidates=5,
                               min_price_krw=1000, max_price_krw=50000, min_volume_ratio=0)
    row.settings_json = json.dumps(profile)
    db.commit()
    daily, intraday = synthetic_bars(VIRTUAL_NOW)
    client = harness.client
    client.get_domestic_daily_bars = lambda symbol, limit=120: daily[-limit:]
    client.get_domestic_intraday_bars = lambda symbol, **kwargs: intraday
    client.get_domestic_stock_price = lambda symbol: {'symbol': symbol, 'name': f'Synthetic {symbol}',
        'current_price': intraday[-1]['close'], 'previous_close': daily[-1]['close']}
    client.auth_manager = SimpleNamespace(require_configured=lambda: None, settings=settings)
    client.build_domestic_order_payload = lambda **kwargs: {
        'PDNO': kwargs['symbol'], 'ORD_QTY': str(kwargs['qty']), 'CANO': '11112222', 'ACNT_PRDT_CD': '01'}
    client.domestic_cash_order_tr_id = lambda side: 'FAKE-CASH-BUY'
    sessions = ClockSession(harness.clock)
    harness.market_sessions = sessions
    responses = FakeResponses(score=gpt_score, failure=failure)
    snapshot_service = MarketDataSnapshotService(client, now_provider=harness.clock.now)
    preview = RecordingPreview(client, session_service=sessions,
        gpt_advisor=KisPreviewGptAdvisor(settings=settings, client=SimpleNamespace(responses=responses)),
        market_data_snapshot_service=snapshot_service,
        market_context_service=KrMarketContextService(client, alpaca_client=SimpleNamespace(), now_factory=harness.clock.now))
    dry = harness.strategy_scheduler.dry_run_service
    dry.preview_service = preview
    dry.market_sessions = sessions
    harness.validation = RecordingValidation(client, session_service=sessions)
    harness.profile_buy.validation_service = harness.validation
    harness.profile_buy.execution_core.validation_service = harness.validation
    scheduler = AutomationSchedulerService(retry_now_provider=harness.clock.now)
    scheduler.runtime_settings = harness.runtime
    scheduler.automation_profiles = harness.profiles
    scheduler.automation_profile_buy_scheduler_service = harness.profile_buy
    scheduler.profile_aware_dry_run_auto_buy_service = dry
    monkeypatch.setattr('app.services.automation_scheduler_service.SessionLocal', SessionLocal)
    monkeypatch.setattr('app.services.automation_scheduler_service.MarketSessionService', lambda: sessions)
    snapshot = WatchlistSnapshotService(client=client, now_provider=harness.clock.now).refresh(db)
    assert snapshot['status'] == 'success'
    assert snapshot['source_count'] == snapshot['scored_count'] == 200
    return harness, scheduler, preview, responses, snapshot


@pytest.mark.parametrize('gpt_score,failure,expected_submit', [(70, False, 1), (59, False, 0), (70, True, 0)])
def test_recovered_scheduler_runs_actual_full_pipeline(monkeypatch, tmp_path, gpt_score, failure, expected_submit):
    with SessionLocal() as db:
        harness, scheduler, preview, responses, snapshot = setup_pipeline(db, monkeypatch,
            gpt_score=gpt_score, failure=failure)
        # Recover after a failing planner before the due minute; no live server is started.
        def failed_planner():
            raise RuntimeError('synthetic prior SQLite error')
        scheduler._task_supervisor.launch('prior-planner', failed_planner, timeout=30)
        with scheduler._task_supervisor.lock:
            prior = list(scheduler._task_supervisor.tasks.values())
        for task in prior:
            task['thread'].join(5)
        scheduler._plan_admin_slots(VIRTUAL_NOW)
        with scheduler._task_supervisor.lock:
            workers = list(scheduler._task_supervisor.tasks.values())
        for task in workers:
            task['thread'].join(30)
            assert not task['thread'].is_alive()
        db.expire_all()
        ledger = db.query(AutomationSchedulerSlot).one()
        assert ledger.status in {'completed', 'HOLD', 'blocked'}, ledger.reason
        result = json.loads(ledger.result_json)
        output = preview.result
        assert len(output['runtime_input_symbols']) == 50
        top5 = [item for item in output['items'] if item.get('selected_by_a_top5')]
        assert len(top5) == 5
        assert all(item['quant_c_status'] == 'analyzed' for item in top5)
        assert all(item['quant_c_score'] >= 65 for item in top5)
        for item in top5:
            for frame in ('15m', '30m', '60m'):
                assert item['shadow_c']['timeframe_bar_counts'][frame] >= 2
        assert len(responses.calls) == 5
        assert all({'ema20', 'rsi', 'vwap', 'atr', 'volume_ratio', 'momentum'} <=
                   set(call['indicator_payload']) for call in responses.calls)
        assert len(harness.broker.buy_calls) == expected_submit, json.dumps(result, ensure_ascii=False)
        assert harness.client.external_kis_submit_count == 0
        if expected_submit:
            assert result['profile_buy']['status'] == 'filled', result
            assert harness.validation.calls[0].validated_for_submission
            assert result['profile_buy']['quantity'] >= 1
            assert harness.client.possible_order_calls == 1
            assert db.query(OrderLog).count() == 1
            order = db.query(OrderLog).one()
            assert order.internal_status == 'FILLED'
            assert order.kis_odno.startswith('FAKE-')
            assert db.query(PositionLifecycle).filter_by(status='open').count() == 1
            assert db.query(AutomationProfileAiCandidateResult).count() >= 5
            selected = output['final_best_candidate']
            assert selected['quant_c_score'] >= 65
            assert selected['ai_buy_score'] >= 60
            assert selected['final_buy_score'] >= 65
            report = {'fixture_based_reconstruction': True, 'gpt': 'GPT MOCKED',
                'simulation_only': True, 'real_order_submitted': False, 'actual_kis_submit_count': 0,
                'mock_submit_count': len(harness.broker.buy_calls), 'simulated_order_status': order.internal_status,
                'watchlist_count': snapshot['scored_count'], 'runtime_a_count': len(output['runtime_input_symbols']),
                'c_count': len(top5), 'gpt_count': len(responses.calls), 'selected_symbol': selected['symbol'],
                'c_score': selected['quant_c_score'], 'gpt_score': selected['ai_buy_score'],
                'final_score': selected['final_buy_score'], 'quantity': order.qty, 'slot_status': ledger.status}
            print('PR138_SIMULATION_RESULT=' + json.dumps(report, ensure_ascii=False))
            (tmp_path / 'simulation_result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        else:
            assert not harness.validation.calls
            assert not db.query(OrderLog).count()
            assert result['result'].lower() in {'hold', 'blocked'}
            assert any(item.get('gpt_analysis_status') == ('failed' if failure else 'completed') for item in top5)


def test_real_current_market_session_blocks_new_buy(monkeypatch):
    # Deliberately no virtual clock. This checks the actual client-date session.
    now = datetime.now(KST)
    session = MarketSessionService().get_session_status('KR')
    assert not session['is_market_open'], f'Expected post-close run, actual time={now.isoformat()}'
    with SessionLocal() as db:
        harness = build_harness(db, monkeypatch, now=now, analysis_times=('11:20',))
        harness.market_sessions.is_open = False
        scheduler = AutomationSchedulerService()
        scheduler.runtime_settings = harness.runtime
        scheduler.automation_profiles = harness.profiles
        scheduler.automation_profile_buy_scheduler_service = harness.profile_buy
        monkeypatch.setattr('app.services.automation_scheduler_service.SessionLocal', SessionLocal)
        result = scheduler.run_once(slot='11:20', now=now)
        assert result['result'] == 'blocked', result
        assert result['reason'] in {'entry_window_closed', 'market_closed', 'market_session_closed'}
        assert not harness.broker.buy_calls
        assert harness.client.external_kis_submit_count == 0
        print('PR138_REAL_SESSION_RESULT=' + json.dumps({'at': now.isoformat(), 'status': 'BLOCKED',
            'reason': result['reason'], 'mock_submit_count': 0, 'actual_kis_submit_count': 0}))
