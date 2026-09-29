from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AutomationProfileAiCandidateResult,
    AutomationProfileWatchlistSnapshot,
    PositionLifecycle,
    OrderLog,
    SignalLog,
    TradeRunLog,
    User,
    UserAutoTradingSlotClaim,
    UserTradingSettings,
    UserWatchlist,
    WatchlistSnapshotItem,
    WatchlistSnapshotRun,
)
from app.services.market_session_service import MarketSessionService
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.automation_profile_service import AutomationProfileService
from app.services.user_broker_account_service import (
    UserBrokerAccountService,
    UserBrokerAuthenticationError,
    UserBrokerUnavailableError,
)
from app.services.user_broker_credential_service import UserBrokerCredentialService
from app.services.user_symbol_analysis_service import UserSymbolAnalysisService
from app.services.user_trading_execution_service import UserTradingExecutionService
from app.services.calendar_gap_risk_service import CalendarGapRiskService
from app.services.market_calendar_service import MarketCalendarService
import app.services.user_auto_trading_scheduler_service as user_scheduler_module

from app.services.user_auto_trading_scheduler_service import (
    USER_SCHEDULER_TRIGGER_SOURCE,
    UserAutoTradingCandidateService,
    UserAutoTradingSchedulerService,
)


class FakeSessionService(MarketSessionService):
    def __init__(self):
        pass

    def get_session_status(self, market, now=None):
        return {
            'market': market,
            'is_market_open': True,
            'is_entry_allowed_now': True,
            'local_time': '2026-09-10T10:00:00+09:00',
        }

    def get_entry_slots(self, market=None):
        return [
            {'time': '09:10'},
            {'time': '11:30'},
            {'time': '14:50'},
        ]


class FakeAccountService(UserBrokerAccountService):
    def __init__(self, snapshots=None, fail_user_ids=None):
        self.snapshots = snapshots or {}
        self.fail_user_ids = set(fail_user_ids or ())
        self.calls = []

    def get_broker_snapshot(self, db, user, provider):
        self.calls.append((int(user.id), provider))
        if int(user.id) in self.fail_user_ids:
            raise RuntimeError('fake_account_failure')
        settings = (
            db.query(UserTradingSettings)
            .filter(UserTradingSettings.user_id == int(user.id))
            .first()
        )
        environment = 'live' if settings and settings.trading_mode == 'live' else 'paper'
        default_currency = 'KRW' if provider == 'kis' else 'USD'
        return self.snapshots.get((int(user.id), provider), {
            'provider': provider,
            'environment': environment,
            'connected': True,
            'account': {
                'currency': default_currency,
                'portfolio_value': 10000.0,
                'equity': 10000.0,
                'buying_power': 10000.0,
                'cash': 10000.0,
            },
            'positions': [],
            'open_orders': [],
        })


class FakeCredentialService(UserBrokerCredentialService):
    def __init__(self):
        self.calls = []

    def get_credentials(self, db, user, provider):
        settings = (
            db.query(UserTradingSettings)
            .filter(UserTradingSettings.user_id == int(user.id))
            .first()
        )
        environment = 'live' if settings and settings.trading_mode == 'live' else 'paper'
        self.calls.append((int(user.id), provider, environment))
        return {
            'environment': environment,
            'api_key': f'user-{user.id}-key',
            'secret_key': f'user-{user.id}-secret',
        }


class FakeAnalysisService(UserSymbolAnalysisService):
    def __init__(self, fail_symbols=None):
        self.fail_symbols = set(fail_symbols or ())
        self.calls = []

    def analyze(self, db, *, provider, symbol, gate_level=2, now=None):
        self.calls.append((provider, symbol))
        if symbol in self.fail_symbols:
            raise RuntimeError('fake_analysis_failure')
        return {
            'provider': provider,
            'market': 'KR' if provider == 'kis' else 'US',
            'symbol': symbol,
            'requested_symbol': symbol,
            'analyzed_symbol': symbol,
            'returned_symbol': symbol,
            'action': 'buy',
            'reason': 'fake_qualified_candidate',
            'current_price': 100.0,
            'final_buy_score': 80.0,
            'final_sell_score': 10.0,
            'quant_buy_score': 80.0,
            'quant_sell_score': 10.0,
            'confidence': 0.8,
            'indicator_payload': {'price': 100.0},
            'risk_flags': [],
            'gating_notes': [],
            'hard_blocked': False,
        }


class FakeBroker:
    def __init__(self):
        self.buy_calls = []
        self.sell_calls = []
        self.possible_order_calls = []
        self.possible_orders = {}
        self.possible_order_failures = set()
        self.submit_failures = set()

    def get_possible_buy_order(self, *, symbol, order_type='market'):
        assert order_type == 'market'
        self.possible_order_calls.append((symbol, order_type))
        if symbol in self.possible_order_failures:
            raise RuntimeError('fake_possible_order_failure')
        return self.possible_orders.get(symbol, {
            'symbol': symbol,
            'order_type': order_type,
            'nrcvb_buy_amt': 1000000.0,
            'nrcvb_buy_qty': 10000,
            'psbl_qty_calc_unpr': 100.0,
            'raw_status': 'ok',
        })

    def submit_market_buy_qty(self, *, symbol, qty):
        self.buy_calls.append((symbol, qty))
        if symbol in self.submit_failures:
            raise RuntimeError('fake_submit_failure')
        return SimpleNamespace(
            id=f'fake-buy-{len(self.buy_calls)}',
            status='filled',
            client_order_id=f'fake-client-buy-{len(self.buy_calls)}',
            filled_qty=qty,
            filled_avg_price=100.0,
        )

    def submit_market_sell_qty(self, *, symbol, qty):
        self.sell_calls.append((symbol, qty))
        return SimpleNamespace(
            id=f'fake-sell-{len(self.sell_calls)}',
            status='filled',
            client_order_id=f'fake-client-sell-{len(self.sell_calls)}',
            filled_qty=qty,
            filled_avg_price=100.0,
        )


class FakeKisClient(FakeBroker):
    pass


class CanonicalProfileWatchlists:
    def __init__(self, items, *, cap=48000.0, owner_user_id=2, profile_id=1):
        self.items = [dict(item) for item in items]
        self.cap = cap
        self.owner_user_id = owner_user_id
        self.profile_id = profile_id
        self.calls = []

    def build(self, db, *, profile, owner_user_id, scheduler_slot, now=None):
        self.calls.append({
            'owner_user_id': owner_user_id,
            'profile_id': profile.get('id'),
            'scheduler_slot': scheduler_slot,
        })
        return {
            'snapshot': {
                'id': 9001,
                'profile_id': int(profile['id']),
                'owner_user_id': int(owner_user_id),
                'provider': 'kis',
                'market': 'KR',
                'snapshot_date': '2026-09-10',
                'scheduler_slot': scheduler_slot,
                'source_count': len(self.items),
                'eligible_count': len(self.items),
                'selected_count': len(self.items),
                'effective_max_candidate_price': self.cap,
            },
            'items': [dict(item) for item in self.items],
        }


class CanonicalRuntimePreview:
    def __init__(self, latest_prices, *, final_score=70.0):
        self.latest_prices = dict(latest_prices)
        self.final_score = final_score
        self.calls = []

    def run_preview(self, **kwargs):
        self.calls.append(dict(kwargs))
        snapshot_items = kwargs['profile_snapshot_items']
        cap = float(kwargs['max_price_krw'])
        runtime_items = []
        for raw in snapshot_items:
            symbol = str(raw['symbol']).upper()
            latest_price = float(self.latest_prices[symbol])
            if latest_price <= cap:
                c_score = float(raw.get('quant_c_score', raw.get('quant_buy_score', 80.0)))
                runtime_items.append({
                    **raw,
                    'symbol': symbol,
                    'current_price': latest_price,
                    'indicator_status': raw.get('indicator_status', 'ok'),
                    'quant_buy_score': float(raw.get('quant_buy_score') or c_score),
                    'quant_sell_score': float(raw.get('quant_sell_score') or 10.0),
                    'runtime_quant_buy_score': float(raw.get('quant_buy_score') or c_score),
                    'runtime_quant_sell_score': float(raw.get('quant_sell_score') or 10.0),
                    'quant_c_score': c_score,
                    'quant_c_status': raw.get('quant_c_status', 'analyzed'),
                    'quant_c_gate_passed': raw.get('quant_c_gate_passed', c_score >= 65.0),
                    'entry_quant_score': float(raw.get('entry_quant_score', c_score)),
                    'selected_by_a_top5': True,
                    'ai_buy_score': float(raw.get('ai_buy_score', 75.0)),
                    'ai_sell_score': float(raw.get('ai_sell_score', 15.0)),
                    'confidence': 0.8,
                    'gpt_used': bool(raw.get('gpt_used', True)),
                    'gpt_analysis_status': raw.get('gpt_analysis_status', 'completed'),
                    'final_buy_score': float(raw.get('final_buy_score', self.final_score)),
                    'final_sell_score': 10.0,
                    'hard_blocked': bool(raw.get('hard_blocked', False)),
                })
        runtime_symbols = [item['symbol'] for item in runtime_items]
        for rank, item in enumerate(runtime_items, start=1):
            item['runtime_quant_rank'] = rank
            item['gpt_target_rank'] = rank
        completed_items = [
            item for item in runtime_items
            if item['gpt_used'] and item['gpt_analysis_status'] == 'completed'
        ]
        final_candidates = sorted(
            completed_items,
            key=lambda item: -float(item.get('final_buy_score') or 0.0),
        )[:5]
        for rank, item in enumerate(final_candidates, start=1):
            item['final_rank'] = rank
            item['final_selected'] = rank == 1
        completed_symbols = [item['symbol'] for item in completed_items]
        final_symbols = [item['symbol'] for item in final_candidates]
        return {
            'canonical_profile_pipeline': True,
            'selection_mode': 'A_TOP5_C_GPT',
            'profile_snapshot_selected_symbols': [
                str(item['symbol']).upper() for item in snapshot_items
            ],
            'runtime_input_symbols': [
                str(item['symbol']).upper() for item in snapshot_items
            ],
            'runtime_quant_candidate_symbols': runtime_symbols,
            'runtime_quant_top5_symbols': runtime_symbols[:5],
            'gpt_target_symbols': runtime_symbols[:5],
            'gpt_completed_symbols': completed_symbols,
            'gpt_failed_symbols': [
                item['symbol'] for item in runtime_items
                if item['gpt_analysis_status'] != 'completed'
            ],
            'gpt_replacement_count': 0,
            'final_candidate_symbols': final_symbols,
            'selected_final_symbol': final_symbols[0] if final_symbols else None,
            'final_ranked_candidates': final_candidates,
            'final_ranked_top5': final_candidates,
            'final_best_candidate': final_candidates[0] if final_candidates else None,
            'items': runtime_items,
            'runtime_quant_candidate_count': len(runtime_items),
            'unaffordable_runtime_candidates': [],
            'snapshot_id': kwargs['profile_snapshot_context']['id'],
            'profile_snapshot': kwargs['profile_snapshot_context'],
        }


def _user(db, username, *, role='user'):
    row = User(
        username=username,
        role=role,
        enabled=True,
        setup_completed=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _configure_user(
    db,
    user,
    *,
    provider='kis',
    enabled=True,
    mode='paper',
    live_enabled=False,
    kill_switch=True,
    confirmed=False,
    create_profile=True,
):
    db.add(UserTradingSettings(
        user_id=user.id,
        enabled=True,
        paper_trading_enabled=mode == 'paper',
        live_trading_enabled=live_enabled,
        kill_switch=kill_switch,
        trading_mode=mode,
        auto_trading_enabled=enabled,
        auto_trading_provider=provider if enabled else None,
        auto_live_confirmed_at=datetime.now(UTC) if confirmed else None,
        max_daily_trades=2,
        max_daily_loss_pct=0.02,
        max_position_pct=10.0,
        max_open_positions=1,
        same_direction_reentry_limit=0,
        no_new_entry_after='14:00',
    ))
    db.add(UserWatchlist(
        user_id=user.id,
        symbol='5930' if provider == 'kis' else 'AAPL',
        provider=provider,
        market='KR' if provider == 'kis' else 'US',
    ))
    db.commit()
    if create_profile:
        profile = AutomationProfileService()
        created = profile.create(
            db,
            AutomationProfileWriteRequest(
                profile_key=f'user-{user.id}-{provider}',
                name=f'User {user.id} {provider}',
                provider=provider,
                market='KR' if provider == 'kis' else 'US',
                operation={'start_date': '2026-08-01', 'end_date': '2026-12-31'},
            ),
            owner_user_id=user.id,
        )
        profile.activate(db, str(created['id']), owner_user_id=user.id)


def _set_profile_schedule(
    db,
    user,
    times,
    *,
    fixed_budget=None,
    max_order_notional=None,
    no_new_entry_after=None,
):
    profiles = AutomationProfileService()
    current = profiles.selected_owned_profile_schedule(
        db, owner_user_id=user.id, now=RUN_AT,
    )['profile']
    values = {'entry': {'analysis_times': list(times)}}
    if no_new_entry_after is not None:
        values['entry']['no_new_entry_after'] = no_new_entry_after
    if fixed_budget is not None:
        values['capital'] = {
            'sizing_mode': 'fixed_budget',
            'fixed_budget': fixed_budget,
            'initial_budget_krw': fixed_budget,
            'max_order_notional_krw': max_order_notional or fixed_budget,
        }
    profiles.update(
        db,
        str(current['id']),
        AutomationProfileWriteRequest(**values),
        owner_user_id=user.id,
    )


def _raw_profile_snapshot(db):
    raw = WatchlistSnapshotRun(
        market='KR',
        started_at=RUN_AT,
        completed_at=RUN_AT,
        status='success',
    )
    db.add(raw)
    db.commit()
    db.add(WatchlistSnapshotItem(
        run_id=raw.id,
        symbol='005930',
        name='Profile candidate',
        market='KOSPI',
        current_price=18000.0,
        quant_buy_score=90.0,
        quant_sell_score=5.0,
        indicators_json='{}',
        captured_at=RUN_AT,
    ))
    db.commit()
    return raw


def _harness(*, snapshots=None, fail_user_ids=None, fail_symbols=None):
    account = FakeAccountService(snapshots=snapshots, fail_user_ids=fail_user_ids)
    credentials = FakeCredentialService()
    analysis = FakeAnalysisService(fail_symbols=fail_symbols)
    session = FakeSessionService()
    broker = FakeBroker()
    kis_client = FakeKisClient()
    execution = UserTradingExecutionService(
        account_service=account,
        credential_service=credentials,
        analysis_service=analysis,
        session_service=session,
        alpaca_client_factory=lambda _credentials: broker,
        alpaca_live_client_factory=lambda _credentials: broker,
        kis_live_client_factory=lambda _db, _user, _credentials: kis_client,
    )
    scheduler = UserAutoTradingSchedulerService(
        execution_service=execution,
        account_service=account,
        session_service=session,
        candidate_service=lambda _db, *, provider, **_kwargs: {
            'symbol': '005930' if provider == 'kis' else 'AAPL',
            'candidate_source': 'test_shared_candidate',
        },
    )
    return scheduler, account, analysis, broker, kis_client


RUN_AT = datetime(2026, 9, 10, 1, 10, tzinfo=UTC)
FRIDAY_RUN_AT = datetime(2026, 9, 11, 1, 10, tzinfo=UTC)
FRIDAY_1300_RUN_AT = datetime(2026, 9, 11, 4, 0, tzinfo=UTC)


def test_dispatcher_jobs_are_provider_scoped_and_have_separate_ids(db_session):
    scheduler, *_ = _harness()

    jobs = scheduler.dispatcher_jobs(db_session, now=RUN_AT)

    assert {job['provider'] for job in jobs} == {'kis', 'alpaca'}
    assert all(job['user_scoped'] is True for job in jobs)
    assert all(job['admin_scheduler_unchanged'] is True for job in jobs)
    assert len({job['job_id'] for job in jobs}) == len(jobs)
    assert all(not job['job_id'].startswith('automation_scheduler') for job in jobs)


def test_user_dispatcher_slots_are_the_exact_owner_union_not_admin_schedule(db_session):
    admin = _user(db_session, 'pr129-slot-admin', role='admin')
    test01 = _user(db_session, 'pr129-slot-test01')
    test02 = _user(db_session, 'pr129-slot-test02')
    _configure_user(db_session, admin, provider='kis')
    _configure_user(db_session, test01, provider='kis')
    _configure_user(db_session, test02, provider='kis')
    _set_profile_schedule(db_session, admin, ['09:30', '12:00', '13:30'])
    _set_profile_schedule(db_session, test01, ['09:10', '11:30', '13:30'])
    _set_profile_schedule(
        db_session, test02, ['10:00', '12:30', '14:00'], no_new_entry_after='15:00',
    )
    scheduler, *_ = _harness()

    slots = {
        job['slot']
        for job in scheduler.dispatcher_jobs(db_session, now=RUN_AT)
        if job['provider'] == 'kis'
    }
    assert slots == {'09:10', '10:00', '11:30', '12:30', '13:30', '14:00'}

    _set_profile_schedule(db_session, admin, ['09:20', '10:20'])
    unchanged = {
        job['slot']
        for job in scheduler.dispatcher_jobs(db_session, now=RUN_AT)
        if job['provider'] == 'kis'
    }
    assert unchanged == slots


def test_shared_profile_slot_runs_each_regular_user_with_its_own_snapshot(db_session):
    admin = _user(db_session, 'pr129-same-slot-admin', role='admin')
    test01 = _user(db_session, 'pr129-same-slot-test01')
    test02 = _user(db_session, 'pr129-same-slot-test02')
    _configure_user(db_session, admin, provider='kis')
    _configure_user(db_session, test01, provider='kis')
    _configure_user(db_session, test02, provider='kis')
    _set_profile_schedule(db_session, admin, ['13:30'])
    _set_profile_schedule(
        db_session, test01, ['13:30'], fixed_budget=50000, max_order_notional=48000,
    )
    _set_profile_schedule(
        db_session, test02, ['13:30'], fixed_budget=70000, max_order_notional=65000,
    )
    _raw_profile_snapshot(db_session)
    scheduler, account, _analysis, _broker, _kis_client = _harness(
        snapshots={
            (test01.id, 'kis'): {
                'account': {
                    'portfolio_value': 50000.0,
                    'equity': 50000.0,
                    'buying_power': 50000.0,
                    'cash': 50000.0,
                },
                'positions': [],
                'open_orders': [],
            },
            (test02.id, 'kis'): {
                'account': {
                    'portfolio_value': 100000.0,
                    'equity': 100000.0,
                    'buying_power': 100000.0,
                    'cash': 100000.0,
                },
                'positions': [],
                'open_orders': [],
            },
        },
    )
    scheduler.candidate_service = UserAutoTradingCandidateService()

    result = scheduler.run_provider_once(
        db_session, provider='kis', scheduler_slot='13:30', now=RUN_AT,
    )

    assert result['processed'] == 2
    assert result['completed'] == 2
    assert {call[0] for call in account.calls} == {test01.id, test02.id}
    snapshots = db_session.query(AutomationProfileWatchlistSnapshot).all()
    assert {(row.profile_id, row.owner_user_id, row.scheduler_slot) for row in snapshots} == {
        (
            AutomationProfileService().selected_owned_profile_schedule(
                db_session, owner_user_id=test01.id, now=RUN_AT,
            )['profile']['id'],
            test01.id,
            '13:30',
        ),
        (
            AutomationProfileService().selected_owned_profile_schedule(
                db_session, owner_user_id=test02.id, now=RUN_AT,
            )['profile']['id'],
            test02.id,
            '13:30',
        ),
    }
    assert {row.effective_entry_budget_krw for row in snapshots} == {48000.0, 65000.0}
    orders = {
        row.owner_user_id: row
        for row in db_session.query(OrderLog).all()
    }
    assert orders[test01.id].qty == 480
    assert orders[test01.id].notional == 48000.0
    assert orders[test02.id].qty == 650
    assert orders[test02.id].notional == 65000.0
    for order in orders.values():
        payload = json.loads(order.request_payload)
        assert payload['sizing']['sizing_source'] == 'automation_profile'
        assert payload['sizing']['profile_id'] is not None
    assert db_session.query(UserAutoTradingSlotClaim).filter_by(user_id=admin.id).count() == 0

def test_kis_paper_scheduler_is_user_owned_and_slot_idempotent(db_session):
    user = _user(db_session, 'pr129-paper')
    admin = _user(db_session, 'pr129-admin', role='admin')
    disabled = _user(db_session, 'pr129-disabled')
    alpaca = _user(db_session, 'pr129-alpaca')
    _configure_user(db_session, user, provider='kis')
    _configure_user(db_session, admin, provider='kis')
    _configure_user(db_session, disabled, provider='kis', enabled=False)
    _configure_user(db_session, alpaca, provider='alpaca')
    scheduler, account, analysis, broker, kis_client = _harness()

    first = scheduler.run_provider_once(
        db_session,
        provider='kis',
        scheduler_slot='09:10',
        now=RUN_AT,
    )
    second = scheduler.run_provider_once(
        db_session,
        provider='kis',
        scheduler_slot='09:10',
        now=RUN_AT,
    )

    assert first['processed'] == 1
    assert first['completed'] == 1
    assert second['processed'] == 0
    assert len(account.calls) == 1
    assert analysis.calls == [('kis', '005930')]
    assert broker.buy_calls == []
    assert kis_client.buy_calls == []
    order = db_session.query(OrderLog).filter(OrderLog.owner_user_id == user.id).one()
    assert order.internal_status == 'DRY_RUN_SIMULATED'
    assert order.side == 'buy'
    order_payload = json.loads(order.request_payload)
    assert order_payload['trigger_source'] == USER_SCHEDULER_TRIGGER_SOURCE
    assert order_payload['scheduler_slot'] == '09:10'
    run = db_session.query(TradeRunLog).filter(TradeRunLog.owner_user_id == user.id).one()
    assert run.trigger_source == USER_SCHEDULER_TRIGGER_SOURCE
    assert run.run_key.startswith(f'uauto_{user.id}_kis_')
    signal = db_session.query(SignalLog).filter(SignalLog.owner_user_id == user.id).one()
    assert signal.trigger_source == USER_SCHEDULER_TRIGGER_SOURCE
    assert db_session.query(UserAutoTradingSlotClaim).count() == 1


def test_alpaca_paper_scheduler_uses_paper_fake_broker(db_session):
    user = _user(db_session, 'pr129-alpaca-paper')
    _configure_user(db_session, user, provider='alpaca')
    scheduler, _account, analysis, broker, kis_client = _harness()

    result = scheduler.run_provider_once(
        db_session,
        provider='alpaca',
        scheduler_slot='09:10',
        now=RUN_AT,
    )

    assert result['completed'] == 1
    assert analysis.calls == [('alpaca', 'AAPL')]
    assert len(broker.buy_calls) == 1
    assert kis_client.buy_calls == []
    order = db_session.query(OrderLog).filter(OrderLog.owner_user_id == user.id).one()
    assert order.broker == 'alpaca'
    assert order.internal_status == 'FILLED'
    assert json.loads(order.request_payload)['trigger_source'] == USER_SCHEDULER_TRIGGER_SOURCE


def test_live_scheduler_requires_all_user_gates_and_then_uses_fake_kis_client(db_session):
    user = _user(db_session, 'pr129-live')
    _configure_user(
        db_session,
        user,
        provider='kis',
        mode='live',
        live_enabled=True,
        kill_switch=False,
        confirmed=False,
    )
    scheduler, account, _analysis, _broker, kis_client = _harness()

    blocked = scheduler.run_provider_once(
        db_session,
        provider='kis',
        scheduler_slot='09:10',
        now=RUN_AT,
    )
    assert blocked['completed'] == 1
    assert blocked['items'][0]['reason'] == 'auto_live_confirmation_required'
    assert account.calls == []
    assert kis_client.buy_calls == []

    settings = db_session.query(UserTradingSettings).filter_by(user_id=user.id).one()
    settings.auto_live_confirmed_at = RUN_AT
    db_session.commit()
    submitted = scheduler.run_provider_once(
        db_session,
        provider='kis',
        scheduler_slot='11:30',
        now=RUN_AT,
    )

    assert submitted['completed'] == 1
    assert submitted['items'][0]['result'] == 'submitted'
    assert len(kis_client.buy_calls) == 1
    order = db_session.query(OrderLog).filter(OrderLog.owner_user_id == user.id).one()
    assert json.loads(order.request_payload)['confirm_live'] is False
    assert json.loads(order.request_payload)['authorization_mode'] == 'automatic'
    assert order.broker == 'kis'


def test_position_management_runs_before_entry_and_sells_kis_paper_position(db_session):
    user = _user(db_session, 'pr129-exit')
    _configure_user(db_session, user, provider='kis')
    snapshots = {
        (user.id, 'kis'): {
            'provider': 'kis',
            'environment': 'paper',
            'connected': True,
            'account': {
                'currency': 'KRW',
                'portfolio_value': 10000.0,
                'equity': 10000.0,
                'buying_power': 10000.0,
                'cash': 10000.0,
            },
            'positions': [{
                'symbol': '005930',
                'quantity': 2,
                'available_quantity': 2,
                'current_price': 90,
                'avg_price': 100,
            }],
            'open_orders': [],
        },
    }
    scheduler, _account, analysis, broker, kis_client = _harness(snapshots=snapshots)

    result = scheduler.run_provider_once(
        db_session,
        provider='kis',
        scheduler_slot='09:10',
        now=RUN_AT,
    )

    assert result['completed'] == 1
    assert result['items'][0]['position_management']['action'] == 'sell'
    assert analysis.calls == []
    assert broker.sell_calls == []
    assert kis_client.sell_calls == []
    order = db_session.query(OrderLog).filter(OrderLog.owner_user_id == user.id).one()
    assert order.side == 'sell'
    assert order.internal_status == 'DRY_RUN_SIMULATED'


def test_one_user_failure_does_not_stop_other_users(db_session):
    failed_user = _user(db_session, 'pr129-failing')
    healthy_user = _user(db_session, 'pr129-healthy')
    _configure_user(db_session, failed_user, provider='kis')
    _configure_user(db_session, healthy_user, provider='kis')
    scheduler, _account, _analysis, _broker, _kis_client = _harness(
        fail_user_ids={failed_user.id},
    )

    result = scheduler.run_provider_once(
        db_session,
        provider='kis',
        scheduler_slot='09:10',
        now=RUN_AT,
    )

    assert result['failed'] == 1
    assert result['completed'] == 1
    assert {item['owner_user_id'] for item in result['items']} == {
        failed_user.id,
        healthy_user.id,
    }
    healthy_order = db_session.query(OrderLog).filter(
        OrderLog.owner_user_id == healthy_user.id,
    ).one()
    assert healthy_order.internal_status == 'DRY_RUN_SIMULATED'
    failed_run = db_session.query(TradeRunLog).filter(
        TradeRunLog.owner_user_id == failed_user.id,
    ).one()
    assert failed_run.trigger_source == USER_SCHEDULER_TRIGGER_SOURCE
    assert failed_run.result == 'failed'


def test_missing_owned_profile_skips_before_account_candidate_analysis_or_signal(db_session):
    user = _user(db_session, 'pr129-profile-missing')
    _configure_user(db_session, user, create_profile=False)
    scheduler, account, analysis, broker, kis_client = _harness()

    result = scheduler.run_provider_once(
        db_session, provider='kis', scheduler_slot='09:10', now=RUN_AT,
    )

    assert result['items'][0]['result'] == 'SKIPPED'
    assert result['items'][0]['reason'] == 'automation_profile_missing'

    assert account.calls == []
    assert analysis.calls == []
    assert broker.buy_calls == []
    assert kis_client.buy_calls == []
    assert db_session.query(SignalLog).filter_by(owner_user_id=user.id).count() == 0
    assert db_session.query(OrderLog).filter_by(owner_user_id=user.id).count() == 0
    assert db_session.query(TradeRunLog).filter_by(owner_user_id=user.id).count() == 0
    assert db_session.query(UserAutoTradingSlotClaim).filter_by(user_id=user.id).count() == 0


def test_kis_scheduler_honors_the_selected_user_profile_analysis_slots(db_session):
    user = _user(db_session, 'pr129-profile-slots')
    _configure_user(db_session, user)
    profile = AutomationProfileService().selected_owned_profile_schedule(
        db_session, owner_user_id=user.id, now=RUN_AT,
    )['profile']
    AutomationProfileService().update(
        db_session,
        str(profile['id']),
        AutomationProfileWriteRequest(entry={'analysis_times': ['10:00']}),
        owner_user_id=user.id,
    )
    scheduler, account, analysis, broker, kis_client = _harness()

    skipped = scheduler.run_provider_once(
        db_session, provider='kis', scheduler_slot='09:10', now=RUN_AT,
    )

    assert skipped['processed'] == 0
    assert skipped['completed'] == 0
    assert skipped['ignored'] >= 1
    assert skipped['items'][0]['reason'] == 'profile_slot_not_due'
    assert account.calls == []
    assert analysis.calls == []
    assert broker.buy_calls == []
    assert kis_client.buy_calls == []
    assert db_session.query(TradeRunLog).filter_by(owner_user_id=user.id).count() == 0
    assert db_session.query(SignalLog).filter_by(owner_user_id=user.id).count() == 0
    assert db_session.query(UserAutoTradingSlotClaim).filter_by(user_id=user.id).count() == 0

def test_admin_null_owner_profile_never_satisfies_regular_user_profile_gate(db_session):
    user = _user(db_session, 'pr129-no-admin-fallback')
    _configure_user(db_session, user, create_profile=False)
    profiles = AutomationProfileService()
    system = profiles.create(
        db_session,
        AutomationProfileWriteRequest(
            profile_key='pr129-system-profile',
            name='System profile',
            provider='kis',
            market='KR',
            operation={'start_date': '2026-08-01', 'end_date': '2026-12-31'},
        ),
    )
    profiles.activate(db_session, str(system['id']))
    scheduler, account, analysis, _broker, _kis_client = _harness()

    result = scheduler.run_provider_once(
        db_session, provider='kis', scheduler_slot='09:10', now=RUN_AT,
    )

    assert result['items'][0]['reason'] == 'automation_profile_missing'
    assert account.calls == []
    assert analysis.calls == []
    assert db_session.query(SignalLog).filter_by(owner_user_id=user.id).count() == 0


def test_personal_watchlist_cannot_override_shared_auto_candidate(db_session):
    user = _user(db_session, 'pr129-watchlist-not-universe')
    _configure_user(db_session, user)
    snapshot = WatchlistSnapshotRun(
        market='KR',
        started_at=RUN_AT,
        completed_at=RUN_AT,
        status='success',
    )
    db_session.add(snapshot)
    db_session.commit()
    db_session.add_all([
        WatchlistSnapshotItem(
            run_id=snapshot.id, symbol='086790', name='Shared candidate',
            market='KOSPI', current_price=100.0, quant_buy_score=88.0,
            quant_sell_score=10.0, indicators_json='{}', captured_at=RUN_AT,
        ),
        WatchlistSnapshotItem(
            run_id=snapshot.id, symbol='005930', name='Favorite only',
            market='KOSPI', current_price=100.0, quant_buy_score=10.0,
            quant_sell_score=80.0, indicators_json='{}', captured_at=RUN_AT,
        ),
    ])
    db_session.commit()

    profile = AutomationProfileService().selected_owned_profile_schedule(
        db_session, owner_user_id=user.id, now=RUN_AT,
    )['profile']
    profile['effective_settings']['capital']['initial_budget_krw'] = 1000.0
    profile['effective_settings']['capital']['max_order_notional_krw'] = 1000.0
    profile['effective_settings']['universe']['min_price_krw'] = 1.0
    candidate = UserAutoTradingCandidateService().select_candidate(
        db_session,
        user=user,
        provider='kis',
        profile=profile,
        scheduler_slot='09:10',
        now=RUN_AT,
    )

    assert candidate is not None
    assert candidate['symbol'] == '086790'
    assert candidate['candidate_source'] == 'automation_profile_watchlist_snapshot'
    assert candidate['automation_profile_id'] == profile['id']


def _canonical_scheduler_setup(db, *, final_score=70.0, candidate_items=None, fixed_budget=50000, max_order_notional=48000):
    _user(db, 'pr129-canonical-admin', role='admin')
    user = _user(db, 'pr129-canonical-user')
    _configure_user(db, user, provider='kis')
    _set_profile_schedule(
        db,
        user,
        ['09:10'],
        fixed_budget=fixed_budget,
        max_order_notional=max_order_notional,
    )
    account_snapshot = {
        'provider': 'kis',
        'environment': 'paper',
        'connected': True,
        'account': {
            'currency': 'KRW',
            'portfolio_value': 1000000.0,
            'equity': 1000000.0,
            'buying_power': 1000000.0,
            'cash': 1000000.0,
        },
        'positions': [],
        'open_orders': [],
    }
    scheduler, account, analysis, broker, kis_client = _harness(
        snapshots={(user.id, 'kis'): account_snapshot},
    )
    profile = AutomationProfileService().selected_owned_profile_schedule(
        db,
        owner_user_id=user.id,
        now=RUN_AT,
    )['profile']
    items = candidate_items or [
        {
            'symbol': '005930',
            'name': 'Snapshot crossing candidate',
            'market': 'KOSPI',
            'current_price': 47900.0,
            'quant_buy_score': 90.0,
            'quant_sell_score': 10.0,
            'snapshot_rank': 1,
        },
        {
            'symbol': '000660',
            'name': 'Affordable candidate',
            'market': 'KOSPI',
            'current_price': 47000.0,
            'quant_buy_score': 80.0,
            'quant_sell_score': 12.0,
            'snapshot_rank': 2,
        },
    ]
    watchlists = CanonicalProfileWatchlists(items, cap=48000.0)
    latest_prices = {
        str(item['symbol']).upper(): float(item.get('current_price') or 47000.0)
        for item in items
    }
    if candidate_items is None:
        latest_prices['005930'] = 48300.0
    preview = CanonicalRuntimePreview(latest_prices, final_score=final_score)
    scheduler.candidate_service = UserAutoTradingCandidateService(
        profile_watchlists=watchlists,
        runtime_preview_service=preview,
    )
    return scheduler, user, profile, preview, account, analysis, broker, kis_client


def _final_candidate(symbol, *, final_score=70.0, c_score=76.0, price=47000.0, **values):
    return {
        'symbol': symbol,
        'name': f'Candidate {symbol}',
        'market': 'KOSPI',
        'current_price': price,
        'quant_buy_score': c_score,
        'quant_sell_score': 10.0,
        'quant_c_score': c_score,
        'quant_c_status': 'analyzed',
        'final_buy_score': final_score,
        'snapshot_rank': 1,
        **values,
    }


def _enable_live_canonical_user(db, user, account, *, kill_switch=False):
    settings = db.query(UserTradingSettings).filter_by(user_id=user.id).one()
    settings.trading_mode = 'live'
    settings.live_trading_enabled = True
    settings.kill_switch = kill_switch
    settings.auto_live_confirmed_at = RUN_AT
    db.commit()
    snapshot = dict(account.snapshots[(user.id, 'kis')])
    snapshot['environment'] = 'live'
    account.snapshots[(user.id, 'kis')] = snapshot


def _set_possible_order(client, symbol, quantity, *, price=47000.0):
    client.possible_orders[symbol] = {
        'symbol': symbol,
        'order_type': 'market',
        'nrcvb_buy_amt': 48000.0,
        'nrcvb_buy_qty': quantity,
        'psbl_qty_calc_unpr': price,
        'raw_status': 'ok',
    }


def _canonical_live_harness(db, *, candidates, kill_switch=False, fixed_budget=50000, max_order_notional=48000):
    scheduler, user, profile, preview, account, analysis, broker, kis_client = (
        _canonical_scheduler_setup(db, candidate_items=candidates, fixed_budget=fixed_budget, max_order_notional=max_order_notional)
    )
    _enable_live_canonical_user(
        db,
        user,
        account,
        kill_switch=kill_switch,
    )
    return scheduler, user, profile, preview, account, analysis, broker, kis_client


def _run_user_scheduler_slot(db, scheduler, user, *, slot='09:10', now=RUN_AT):
    result = scheduler.run_provider_once(
        db,
        provider='kis',
        scheduler_slot=slot,
        now=now,
    )
    return next(
        value
        for value in result['items']
        if value.get('owner_user_id') == user.id
    )


def test_user_scheduler_canonical_lineage_applies_runtime_affordability_and_final_one(
    db_session,
):
    scheduler, user, profile, preview, _account, _analysis, broker, kis_client = (
        _canonical_scheduler_setup(db_session)
    )

    result = scheduler.run_provider_once(
        db_session,
        provider='kis',
        scheduler_slot='09:10',
        now=RUN_AT,
    )
    item = next(value for value in result['items'] if value.get('owner_user_id') == user.id)
    diagnostics = item['pipeline_diagnostics']
    snapshot_symbols = set(diagnostics['profile_snapshot_selected_symbols'])

    assert item['profile_id'] == profile['id']
    assert item['profile_snapshot']['owner_user_id'] == user.id
    assert diagnostics['owner_user_id'] == user.id
    assert set(diagnostics['runtime_input_symbols']) == snapshot_symbols
    assert '005930' in snapshot_symbols
    assert '005930' not in set(diagnostics['runtime_quant_candidate_symbols'])
    assert '005930' not in set(diagnostics['runtime_quant_top5_symbols'])
    assert '005930' not in set(diagnostics['gpt_target_symbols'])
    assert '005930' not in set(diagnostics['final_candidate_symbols'])
    assert diagnostics['runtime_quant_candidate_count'] == len(snapshot_symbols) - 1
    assert diagnostics['runtime_quant_top5_symbols'] == diagnostics['gpt_target_symbols']
    assert diagnostics['final_candidate_symbols'] == diagnostics['gpt_completed_symbols']
    assert diagnostics['final_selected_count'] == 1
    assert diagnostics['selected_symbol'] == diagnostics['final_rank_1_symbol']
    assert diagnostics['selected_final_symbol'] == '000660'
    assert preview.calls[0]['max_price_krw'] == 48000.0
    assert preview.calls[0]['profile_snapshot_context']['owner_user_id'] == user.id
    assert item['candidate']['symbol'] == '000660'
    assert item['real_order_submitted'] is False
    assert item['broker_submit_called'] is False
    assert broker.buy_calls == []
    assert kis_client.buy_calls == []


class FailingCanonicalPreview:
    def run_preview(self, **_kwargs):
        raise RuntimeError(
            'runtime quant failed appsecret=super-secret access_token=token-secret'
        )


def test_user_scheduler_failure_keeps_stage_and_redacts_broker_error(db_session):
    scheduler, user, _profile, _preview, _account, _analysis, broker, kis_client = (
        _canonical_scheduler_setup(db_session)
    )
    profile_watchlists = CanonicalProfileWatchlists(
        [
            {
                'symbol': '000660',
                'name': 'Failure candidate',
                'market': 'KOSPI',
                'current_price': 47000.0,
                'quant_buy_score': 80.0,
                'quant_sell_score': 10.0,
            },
        ],
        cap=48000.0,
    )
    scheduler.candidate_service = UserAutoTradingCandidateService(
        profile_watchlists=profile_watchlists,
        runtime_preview_service=FailingCanonicalPreview(),
    )

    result = scheduler.run_provider_once(
        db_session,
        provider='kis',
        scheduler_slot='09:10',
        now=RUN_AT,
    )
    item = next(value for value in result['items'] if value.get('owner_user_id') == user.id)
    run = db_session.query(TradeRunLog).filter_by(owner_user_id=user.id).one()
    request_payload = json.loads(run.request_payload or '{}')
    response_payload = json.loads(run.response_payload or '{}')

    assert item['result'] == 'failed'
    assert item['reason'] == 'user_scheduler_processing_failed'
    assert item['failure_stage'] == 'runtime_quant'
    assert item['exception_type'] == 'RuntimeError'
    assert item['sanitized_error'] == 'sensitive broker error details redacted'
    assert run.stage == 'runtime_quant'
    assert response_payload['failure_stage'] == 'runtime_quant'
    assert response_payload['exception_type'] == 'RuntimeError'
    assert 'super-secret' not in json.dumps([request_payload, response_payload])
    assert 'token-secret' not in json.dumps([request_payload, response_payload])
    assert item['broker_submit_called'] is False
    assert item['real_order_submitted'] is False
    assert broker.buy_calls == []
    assert kis_client.buy_calls == []


def test_user_scheduler_canonical_hold_blocks_below_profile_threshold_without_order(
    db_session,
):
    scheduler, user, _profile, _preview, _account, _analysis, broker, kis_client = (
        _canonical_scheduler_setup(db_session, final_score=64.0)
    )

    result = scheduler.run_provider_once(
        db_session,
        provider='kis',
        scheduler_slot='09:10',
        now=RUN_AT,
    )
    item = next(value for value in result['items'] if value.get('owner_user_id') == user.id)

    assert item['result'] == 'hold'
    assert item['action'] == 'hold'
    assert item['risk_result'] == 'block'
    assert item['block_reason'] == 'below_profile_buy_threshold'
    assert item['order_id'] is None
    assert item['broker_submit_called'] is False
    assert item['real_order_submitted'] is False
    assert broker.buy_calls == []
    assert kis_client.buy_calls == []


def test_canonical_fallback_buys_next_ranked_candidate_and_persists_both_outcomes(
    db_session,
):
    # Input order is lower score first; canonical final score rank must lead.
    candidates = [
        _final_candidate('000002', final_score=66.0),
        _final_candidate('000001', final_score=68.0),
    ]
    scheduler, user, _profile, preview, _account, analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )
    _set_possible_order(kis_client, '000001', 0)
    _set_possible_order(kis_client, '000002', 1)

    item = _run_user_scheduler_slot(db_session, scheduler, user)
    diagnostics = item['pipeline_diagnostics']

    assert item['result'] == 'submitted'
    assert item['candidate']['symbol'] == '000002'
    assert item['fallback_attempted'] is True
    assert item['fallback_selected_rank'] == 2
    assert item['fallback_selected_symbol'] == '000002'
    assert diagnostics['eligible_candidate_count'] == 2
    assert diagnostics['evaluated_candidate_count'] == 2
    assert diagnostics['affordability_blocked_count'] == 1
    assert diagnostics['submitted_count'] == 1
    assert [symbol for symbol, _ in kis_client.buy_calls] == ['000002']
    assert [symbol for symbol, _ in kis_client.possible_order_calls] == [
        '000001', '000002',
    ]
    assert preview.calls[0]['include_gpt'] is True
    assert len(preview.calls) == 1
    assert analysis.calls == []

    persisted = {
        row.symbol: json.loads(row.diagnostics_json)
        for row in db_session.query(AutomationProfileAiCandidateResult)
        .filter_by(owner_user_id=user.id)
        .all()
    }
    assert persisted['000001']['candidate_execution']['execution_status'] == 'skipped'
    assert persisted['000001']['candidate_execution']['skip_reason'] == (
        'kis_market_buy_qty_unavailable'
    )
    assert persisted['000001']['candidate_execution']['broker_submit_called'] is False
    candidate_score_gate = persisted['000001']['candidate_score_gate']
    assert candidate_score_gate['quant_c_threshold'] == 65.0
    assert candidate_score_gate['gpt_buy_score'] == 75.0
    assert candidate_score_gate['gpt_buy_score_threshold'] == 60.0
    assert candidate_score_gate['gpt_buy_score_gate_passed'] is True
    assert candidate_score_gate['a_top5_score_gate_reason'] is None
    assert persisted['000002']['candidate_execution']['execution_status'] == 'selected'
    assert persisted['000002']['candidate_execution']['final_quantity'] == 1



def test_canonical_fallback_skips_gpt_below_60_and_uses_next_eligible(db_session):
    candidates = [
        _final_candidate(
            '000001',
            final_score=70.37,
            c_score=76.16,
            ai_buy_score=53.0,
            ai_sell_score=47.0,
        ),
        _final_candidate(
            '000002',
            final_score=65.25,
            c_score=67.0,
            ai_buy_score=60.0,
            ai_sell_score=40.0,
        ),
    ]
    scheduler, user, _profile, _preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )
    _set_possible_order(kis_client, '000002', 1)

    item = _run_user_scheduler_slot(db_session, scheduler, user)

    outcomes = item['pipeline_diagnostics']['fallback_candidate_results_by_symbol']
    assert item['result'] == 'submitted'
    assert item['candidate']['symbol'] == '000002'
    assert outcomes['000001']['skip_reason'] == 'gpt_buy_score_below_threshold'
    assert item['pipeline_diagnostics']['evaluated_candidate_count'] == 1
    assert [symbol for symbol, _ in kis_client.possible_order_calls] == ['000002']
    assert [symbol for symbol, _ in kis_client.buy_calls] == ['000002']
    persisted = {
        row.symbol: json.loads(row.diagnostics_json)
        for row in db_session.query(AutomationProfileAiCandidateResult)
        .filter_by(owner_user_id=user.id)
        .all()
    }
    low_score_gate = persisted['000001']['candidate_score_gate']
    assert low_score_gate['quant_c_score'] == 76.16
    assert low_score_gate['quant_c_threshold'] == 65.0
    assert low_score_gate['gpt_buy_score'] == 53.0
    assert low_score_gate['gpt_buy_score_threshold'] == 60.0
    assert low_score_gate['gpt_buy_score_gate_passed'] is False
    assert low_score_gate['a_top5_score_gate_reason'] == (
        'gpt_buy_score_below_threshold'
    )


def test_canonical_fallback_with_only_gpt_below_60_has_clear_hold_reason(db_session):
    candidates = [
        _final_candidate(
            '000001',
            final_score=70.37,
            c_score=76.16,
            ai_buy_score=53.0,
            ai_sell_score=47.0,
        ),
    ]
    scheduler, user, _profile, _preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )

    item = _run_user_scheduler_slot(db_session, scheduler, user)

    assert item['result'] == 'HOLD'
    assert item['reason'] == 'gpt_buy_score_below_threshold'
    assert item['pipeline_diagnostics']['fallback_candidate_results_by_symbol'][
        '000001'
    ]['skip_reason'] == 'gpt_buy_score_below_threshold'
    assert item['broker_submit_called'] is False
    assert item['real_order_submitted'] is False
    assert kis_client.possible_order_calls == []
    assert kis_client.buy_calls == []


def test_user_c65_gpt60_final_63_75_stays_below_final_entry_minimum(db_session):
    candidates = [
        _final_candidate(
            '000001',
            final_score=63.75,
            c_score=65.0,
            ai_buy_score=60.0,
            ai_sell_score=40.0,
        ),
    ]
    scheduler, user, _profile, _preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )
    _set_possible_order(kis_client, '000001', 1)

    item = _run_user_scheduler_slot(db_session, scheduler, user)

    assert item['result'] == 'hold'
    assert item['reason'] == 'below_profile_buy_threshold'
    assert item['candidate']['quant_c_gate_passed'] is True
    assert item['candidate']['gpt_buy_score_gate_passed'] is True
    assert item['candidate']['final_buy_score'] == 63.75
    assert kis_client.possible_order_calls == []
    assert kis_client.buy_calls == []


def test_user_execution_rechecks_gpt_minimum_before_possible_order(db_session):
    scheduler, user, profile, _preview, account, _analysis, _broker, kis_client = (
        _canonical_live_harness(
            db_session,
            candidates=[_final_candidate('000001')],
        )
    )
    calendar_gap = scheduler.calendar_gap_risk_service.evaluate(
        'KR',
        now=RUN_AT,
        existing_c_score=65.0,
        existing_final_score=65.0,
    )
    candidate = {
        'symbol': '000001',
        'name': 'GPT-low candidate',
        'current_price': 47000.0,
        'quant_c_score': 76.16,
        'quant_c_status': 'analyzed',
        'entry_quant_score': 76.16,
        'quant_c_gate_passed': True,
        'quant_selection_mode': 'A_TOP5_C_GPT',
        'ai_buy_score': 53.0,
        'ai_sell_score': 47.0,
        'gpt_used': True,
        'gpt_analysis_status': 'completed',
        'final_buy_score': 70.37,
        'final_sell_score': 10.0,
        'indicator_status': 'ok',
        'risk_flags': [],
        'hard_blocked': False,
    }
    profile_context = scheduler._profile_context(
        profile=profile,
        candidate=candidate,
        scheduler_slot='09:10',
        user=user,
        pipeline_diagnostics={'selection_mode': 'A_TOP5_C_GPT'},
        calendar_gap_risk=calendar_gap,
    )

    result = scheduler.execution_service.run_once(
        db_session,
        user,
        provider='kis',
        symbol='000001',
        now=RUN_AT,
        trigger_source='user_scheduler',
        authorization_mode='automatic',
        scheduler_slot='09:10',
        snapshot_override=account.snapshots[(user.id, 'kis')],
        analysis_override={**candidate, 'action': 'buy'},
        profile_context=profile_context,
        calendar_gap_risk_override=calendar_gap,
    )

    assert result['result'] == 'hold'
    assert result['reason'] == 'gpt_buy_score_below_threshold'
    assert result['analysis']['gpt_buy_score_threshold'] == 60.0
    assert result['analysis']['gpt_buy_score_gate_passed'] is False
    assert result['broker_submit_called'] is False
    assert result['real_order_submitted'] is False
    assert kis_client.possible_order_calls == []
    assert kis_client.buy_calls == []


def test_canonical_fallback_excludes_final_score_below_65_even_if_affordable(db_session):
    candidates = [
        _final_candidate('000001', final_score=66.0),
        _final_candidate('000002', final_score=64.0),
    ]
    scheduler, user, _profile, _preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )
    _set_possible_order(kis_client, '000001', 0)
    _set_possible_order(kis_client, '000002', 5)

    item = _run_user_scheduler_slot(db_session, scheduler, user)

    assert item['result'] == 'HOLD'
    assert item['action'] == 'hold'
    assert item['reason'] == 'no_affordable_final_candidate'
    assert item['pipeline_diagnostics']['eligible_candidate_count'] == 1
    assert item['pipeline_diagnostics']['evaluated_candidate_count'] == 1
    assert item['pipeline_diagnostics']['affordability_blocked_count'] == 1
    assert [symbol for symbol, _ in kis_client.possible_order_calls] == ['000001']
    assert kis_client.buy_calls == []


def test_quantity_invalid_candidate_falls_through_to_affordable_candidate(db_session):
    candidates = [
        _final_candidate('000001', final_score=68.0, price=47000.0),
        _final_candidate('000002', final_score=67.0, price=500.0),
    ]
    scheduler, user, _profile, _preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(
            db_session,
            candidates=candidates,
            fixed_budget=1000,
            max_order_notional=1000,
        )
    )
    _set_possible_order(kis_client, '000002', 2, price=500.0)

    item = _run_user_scheduler_slot(db_session, scheduler, user)

    assert item['result'] == 'submitted'
    assert item['candidate']['symbol'] == '000002'
    assert item['pipeline_diagnostics']['fallback_attempted'] is True
    assert item['pipeline_diagnostics']['affordability_blocked_count'] == 1
    assert item['pipeline_diagnostics']['fallback_candidate_results_by_symbol'][
        '000001'
    ]['skip_reason'] == 'quantity_invalid'
    assert [symbol for symbol, _ in kis_client.possible_order_calls] == ['000002']
    assert [symbol for symbol, _ in kis_client.buy_calls] == ['000002']


def test_friday_calendar_fallback_uses_tightened_scores_and_half_user_sizing(
    db_session,
):
    candidates = [
        _final_candidate('000001', final_score=75.0, c_score=74.0, price=10000.0),
        _final_candidate('000002', final_score=69.0, c_score=76.0, price=10000.0),
        _final_candidate('000003', final_score=72.0, c_score=78.0, price=10000.0),
    ]
    scheduler, user, _profile, _preview, account, _analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )
    account_snapshot = account.snapshots[(user.id, 'kis')]
    account_snapshot['account'].update({
        'portfolio_value': 1000000.0,
        'equity': 1000000.0,
        'buying_power': 1000000.0,
        'cash': 1000000.0,
    })
    _set_possible_order(kis_client, '000003', 2, price=10000.0)

    item = _run_user_scheduler_slot(
        db_session,
        scheduler,
        user,
        now=FRIDAY_RUN_AT,
    )
    diagnostics = item['pipeline_diagnostics']
    results = diagnostics['fallback_candidate_results_by_symbol']
    sizing = item['sizing']

    assert item['result'] == 'submitted'
    assert item['candidate']['symbol'] == '000003'
    assert diagnostics['calendar_gap_risk']['calendar_gap_days'] == 3
    assert diagnostics['calendar_gap_risk']['required_c_score'] == 75.0
    assert diagnostics['calendar_gap_risk']['required_final_score'] == 70.0
    assert diagnostics['calendar_gap_risk']['position_size_multiplier'] == 0.5
    assert results['000001']['skip_reason'] == 'calendar_gap_c_below_threshold'
    assert results['000002']['skip_reason'] == 'calendar_gap_final_below_threshold'
    assert sizing['calendar_gap_position_size_multiplier'] == 0.5
    assert sizing['target_notional'] == sizing['target_notional_before_calendar_gap'] * 0.5
    assert [symbol for symbol, _ in kis_client.possible_order_calls] == ['000003']
    assert [symbol for symbol, _ in kis_client.buy_calls] == ['000003']
    assert len(kis_client.buy_calls) == 1


def test_user_friday_after_cutoff_blocks_before_candidate_and_possible_order(db_session):
    scheduler, user, _profile, preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(
            db_session,
            candidates=[_final_candidate('000001', final_score=80.0)],
        )
    )

    item = _run_user_scheduler_slot(
        db_session,
        scheduler,
        user,
        now=FRIDAY_1300_RUN_AT,
    )

    assert item['result'] == 'blocked'
    assert item['reason'] == 'weekend_gap_late_entry_block'
    assert item['calendar_gap_days'] == 3
    assert item['broker_submit_called'] is False
    assert item['real_order_submitted'] is False
    assert preview.calls == []
    assert kis_client.possible_order_calls == []
    assert kis_client.buy_calls == []


def test_user_long_holiday_blocks_before_candidate_and_possible_order(db_session):
    scheduler, user, _profile, preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(
            db_session,
            candidates=[_final_candidate('000001', final_score=80.0)],
        )
    )

    item = _run_user_scheduler_slot(
        db_session,
        scheduler,
        user,
        now=datetime(2026, 10, 2, 1, 10, tzinfo=UTC),
    )

    assert item['result'] == 'blocked'
    assert item['reason'] == 'long_market_closure_ahead'
    assert item['calendar_gap_days'] == 4
    assert item['broker_submit_called'] is False
    assert item['real_order_submitted'] is False
    assert preview.calls == []
    assert kis_client.possible_order_calls == []
    assert kis_client.buy_calls == []


def test_user_calendar_config_failure_fails_closed_before_candidate(db_session, tmp_path):
    scheduler, user, _profile, preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(
            db_session,
            candidates=[_final_candidate('000001', final_score=80.0)],
        )
    )
    scheduler.calendar_gap_risk_service = CalendarGapRiskService(
        MarketCalendarService(config_path=str(tmp_path / 'missing.yaml'))
    )

    item = _run_user_scheduler_slot(
        db_session,
        scheduler,
        user,
        now=FRIDAY_RUN_AT,
    )

    assert item['result'] == 'blocked'
    assert item['reason'] == 'calendar_gap_risk_unavailable'
    assert item['broker_submit_called'] is False
    assert item['real_order_submitted'] is False
    assert preview.calls == []
    assert kis_client.possible_order_calls == []
    assert kis_client.buy_calls == []


def test_canonical_fallback_excludes_c_score_below_65(db_session):
    candidates = [_final_candidate('000001', final_score=70.0, c_score=64.99)]
    scheduler, user, _profile, _preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )

    item = _run_user_scheduler_slot(db_session, scheduler, user)

    assert item['result'] == 'HOLD'
    assert item['action'] == 'hold'
    assert item['reason'] == 'c_score_below_threshold'
    assert item['pipeline_diagnostics']['eligible_candidate_count'] == 0
    assert item['pipeline_diagnostics']['evaluated_candidate_count'] == 0
    assert kis_client.possible_order_calls == []
    assert kis_client.buy_calls == []


def test_global_kill_switch_blocks_before_candidate_fallback(db_session):
    candidates = [
        _final_candidate('000001', final_score=68.0),
        _final_candidate('000002', final_score=67.0),
    ]
    scheduler, user, _profile, preview, account, _analysis, _broker, kis_client = (
        _canonical_live_harness(
            db_session,
            candidates=candidates,
            kill_switch=True,
        )
    )

    item = _run_user_scheduler_slot(db_session, scheduler, user)

    assert item['reason'] == 'user_kill_switch_enabled'
    assert account.calls == []
    assert preview.calls == []
    assert kis_client.possible_order_calls == []
    assert kis_client.buy_calls == []


def test_possible_order_api_failure_stops_before_next_candidate(db_session):
    candidates = [
        _final_candidate('000001', final_score=68.0),
        _final_candidate('000002', final_score=67.0),
    ]
    scheduler, user, _profile, _preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )
    kis_client.possible_order_failures.add('000001')

    item = _run_user_scheduler_slot(db_session, scheduler, user)

    assert item['reason'] == 'kis_possible_order_unavailable'
    assert item['pipeline_diagnostics']['evaluated_candidate_count'] == 1
    assert item['pipeline_diagnostics']['fallback_attempted'] is False
    assert [symbol for symbol, _ in kis_client.possible_order_calls] == ['000001']
    assert kis_client.buy_calls == []
    assert item['pipeline_diagnostics'][
        'fallback_candidate_results_by_symbol'
    ]['000002']['skip_reason'] == 'global_safe_block'


def test_submit_failure_stops_without_submitting_next_candidate(db_session):
    candidates = [
        _final_candidate('000001', final_score=68.0),
        _final_candidate('000002', final_score=67.0),
    ]
    scheduler, user, _profile, _preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )
    _set_possible_order(kis_client, '000001', 1)
    kis_client.submit_failures.add('000001')

    item = _run_user_scheduler_slot(db_session, scheduler, user)

    assert item['reason'] == 'kis_live_submit_failed'
    assert item['pipeline_diagnostics']['submitted_count'] == 1
    assert item['pipeline_diagnostics']['fallback_attempted'] is False
    assert [symbol for symbol, _ in kis_client.possible_order_calls] == ['000001']
    assert [symbol for symbol, _ in kis_client.buy_calls] == ['000001']
    assert item['pipeline_diagnostics'][
        'fallback_candidate_results_by_symbol'
    ]['000002']['skip_reason'] == 'broker_submit_attempted'


def test_all_affordability_blocked_candidates_return_final_hold(db_session):
    candidates = [
        _final_candidate('000001', final_score=68.0),
        _final_candidate('000002', final_score=67.0),
    ]
    scheduler, user, _profile, _preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )
    _set_possible_order(kis_client, '000001', 0)
    _set_possible_order(kis_client, '000002', 0)

    item = _run_user_scheduler_slot(db_session, scheduler, user)
    diagnostics = item['pipeline_diagnostics']

    assert item['result'] == 'HOLD'
    assert item['action'] == 'hold'
    assert item['reason'] == 'no_affordable_final_candidate'
    assert diagnostics['fallback_attempted'] is True
    assert diagnostics['eligible_candidate_count'] == 2
    assert diagnostics['evaluated_candidate_count'] == 2
    assert diagnostics['affordability_blocked_count'] == 2
    assert diagnostics['submitted_count'] == 0
    assert kis_client.buy_calls == []


def test_daily_trade_cap_stops_fallback_before_possible_order(db_session):
    candidates = [
        _final_candidate('000001', final_score=68.0),
        _final_candidate('000002', final_score=67.0),
    ]
    scheduler, user, _profile, _preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )
    settings = db_session.query(UserTradingSettings).filter_by(user_id=user.id).one()
    settings.max_daily_trades = 0
    db_session.commit()

    item = _run_user_scheduler_slot(db_session, scheduler, user)

    assert item['reason'] == 'max_daily_trades_reached'
    assert item['pipeline_diagnostics']['evaluated_candidate_count'] == 1
    assert item['pipeline_diagnostics']['fallback_attempted'] is False
    assert kis_client.possible_order_calls == []
    assert kis_client.buy_calls == []


def test_max_positions_gate_stops_fallback_before_possible_order(db_session):
    candidates = [
        _final_candidate('000001', final_score=68.0),
        _final_candidate('000002', final_score=67.0),
    ]
    scheduler, user, _profile, _preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )
    order = OrderLog(
        owner_user_id=user.id,
        broker='kis',
        market='KR',
        symbol='000099',
        side='buy',
        order_type='market',
        internal_status='CANCELED',
        qty=1,
        notional=100.0,
    )
    db_session.add(order)
    db_session.commit()
    db_session.add(PositionLifecycle(
        owner_user_id=user.id,
        symbol='000099',
        entry_order_id=order.id,
        entry_price=100.0,
        cost_basis=100.0,
        quantity=1.0,
        status='open',
        opened_at=RUN_AT,
    ))
    db_session.commit()

    item = _run_user_scheduler_slot(db_session, scheduler, user)

    assert item['reason'] == 'max_open_positions_reached'
    assert item['pipeline_diagnostics']['evaluated_candidate_count'] == 1
    assert kis_client.possible_order_calls == []
    assert kis_client.buy_calls == []


def test_candidate_duplicate_order_is_skipped_without_duplicate_submit(db_session):
    candidates = [
        _final_candidate('000001', final_score=68.0),
        _final_candidate('000002', final_score=67.0),
    ]
    scheduler, user, _profile, _preview, account, _analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )
    snapshot = dict(account.snapshots[(user.id, 'kis')])
    snapshot['open_orders'] = [{
        'symbol': '000001',
        'side': 'buy',
        'status': 'SUBMITTED',
    }]
    account.snapshots[(user.id, 'kis')] = snapshot

    item = _run_user_scheduler_slot(db_session, scheduler, user)
    outcomes = item['pipeline_diagnostics']['fallback_candidate_results_by_symbol']

    assert item['result'] == 'submitted'
    assert item['candidate']['symbol'] == '000002'
    assert outcomes['000001']['skip_reason'] == 'duplicate_open_order'
    assert outcomes['000001']['broker_submit_called'] is False
    assert [symbol for symbol, _ in kis_client.possible_order_calls] == ['000002']
    assert [symbol for symbol, _ in kis_client.buy_calls] == ['000002']


def test_first_success_stops_loop_and_actual_buy_submit_count_is_one(db_session):
    candidates = [
        _final_candidate('000001', final_score=68.0),
        _final_candidate('000002', final_score=67.0),
        _final_candidate('000003', final_score=66.0),
    ]
    scheduler, user, _profile, _preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )
    _set_possible_order(kis_client, '000001', 1)

    item = _run_user_scheduler_slot(db_session, scheduler, user)

    assert item['result'] == 'submitted'
    assert item['candidate']['symbol'] == '000001'
    assert len(kis_client.buy_calls) == 1
    assert item['pipeline_diagnostics']['submitted_count'] == 1
    assert item['pipeline_diagnostics']['evaluated_candidate_count'] == 1
    assert [symbol for symbol, _ in kis_client.possible_order_calls] == ['000001']


def test_hard_blocked_candidate_is_excluded_before_risk_or_kis_checks(db_session):
    candidates = [
        _final_candidate('000001', final_score=68.0, hard_blocked=True),
        _final_candidate('000002', final_score=67.0),
    ]
    scheduler, user, _profile, _preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )

    item = _run_user_scheduler_slot(db_session, scheduler, user)

    assert item['result'] == 'submitted'
    assert item['candidate']['symbol'] == '000002'
    assert item['pipeline_diagnostics']['eligible_candidate_count'] == 1
    assert item['pipeline_diagnostics']['evaluated_candidate_count'] == 1
    assert item['pipeline_diagnostics'][
        'fallback_candidate_results_by_symbol'
    ]['000001']['skip_reason'] == 'candidate_hard_blocked'
    assert [symbol for symbol, _ in kis_client.possible_order_calls] == ['000002']


def test_single_canonical_candidate_keeps_success_behavior(db_session):
    candidates = [_final_candidate('000001', final_score=68.0)]
    scheduler, user, _profile, _preview, _account, _analysis, _broker, kis_client = (
        _canonical_live_harness(db_session, candidates=candidates)
    )
    _set_possible_order(kis_client, '000001', 1)

    item = _run_user_scheduler_slot(db_session, scheduler, user)

    assert item['result'] == 'submitted'
    assert item['candidate']['symbol'] == '000001'
    assert item['fallback_attempted'] is False
    assert item['fallback_selected_rank'] is None
    assert len(kis_client.buy_calls) == 1


class DeferredAccountSnapshotRetries:
    def __init__(self):
        self.pending = []

    def schedule(self, key, callback, *, delay_seconds):
        if any(item[0] == key for item in self.pending):
            return False
        self.pending.append((key, callback, delay_seconds))
        return True

    def run_next(self, clock):
        key, callback, delay_seconds = self.pending.pop(0)
        clock[0] += timedelta(seconds=delay_seconds)
        next_delay = callback()
        if next_delay:
            self.pending.append((key, callback, next_delay))
        return next_delay


def _retry_user_setup(db_session, monkeypatch, *, failures, permanent_error=None):
    user = _user(db_session, f'retry-user-{id(db_session)}')
    _configure_user(db_session, user, provider='kis')
    _set_profile_schedule(db_session, user, ['09:10'])
    scheduler, account, analysis, broker, kis_client = _harness()
    retries = DeferredAccountSnapshotRetries()
    clock = [datetime(2026, 9, 11, 0, 10, tzinfo=UTC)]
    scheduler.retry_scheduler = retries.schedule
    scheduler.retry_service_factory = lambda: scheduler
    scheduler.now_provider = lambda: clock[0]

    original = account.get_broker_snapshot
    calls = {'count': 0}

    def snapshot(db, requested_user, provider):
        calls['count'] += 1
        if permanent_error is not None:
            raise permanent_error
        if calls['count'] <= failures:
            raise UserBrokerUnavailableError(
                'temporary KIS account read failure',
                details={'error_type': 'ReadTimeout'},
            )
        return original(db, requested_user, provider)

    account.get_broker_snapshot = snapshot
    monkeypatch.setattr(
        user_scheduler_module,
        'SessionLocal',
        sessionmaker(bind=db_session.get_bind(), expire_on_commit=False),
    )
    return user, scheduler, account, analysis, broker, kis_client, retries, clock, calls


def test_kis_snapshot_retry_recovers_on_second_attempt_without_new_claim(
    db_session, monkeypatch
):
    user, scheduler, account, _analysis, broker, _kis, retries, clock, calls = (
        _retry_user_setup(db_session, monkeypatch, failures=1)
    )
    management_calls = []
    manage_positions = scheduler.position_management_service.manage

    def track_management(*args, **kwargs):
        management_calls.append(True)
        return manage_positions(*args, **kwargs)

    scheduler.position_management_service.manage = track_management

    first = scheduler.run_provider_once(
        db_session, provider='kis', scheduler_slot='09:10', now=clock[0],
    )
    db_session.commit()
    claim = db_session.query(UserAutoTradingSlotClaim).filter_by(
        user_id=user.id, scheduler_slot='09:10',
    ).one()
    run_key = claim.run_key

    assert first['result'] == 'retry_pending'
    assert first['retry_pending'] == 1
    assert claim.status == 'retry_pending'
    assert claim.reason == 'account_snapshot_retry_pending_1_of_3'
    assert len(retries.pending) == 1
    assert retries.pending[0][2] == 30
    assert calls['count'] == 1

    retries.run_next(clock)
    db_session.commit()
    db_session.refresh(claim)

    assert calls['count'] == 2
    assert claim.status == 'completed'
    assert claim.run_key == run_key
    run = db_session.query(TradeRunLog).filter_by(
        owner_user_id=user.id, run_key=run_key,
    ).one()
    retry_details = json.loads(run.response_payload)['account_snapshot_retry']
    assert retry_details['attempts'] == 2
    assert retry_details['max_attempts'] == 3
    assert retries.pending == []
    assert management_calls == [True]
    assert len(broker.buy_calls) + len(broker.sell_calls) <= 1


def test_kis_snapshot_retry_recovers_on_third_attempt(db_session, monkeypatch):
    user, scheduler, _account, _analysis, broker, _kis, retries, clock, calls = (
        _retry_user_setup(db_session, monkeypatch, failures=2)
    )

    result = scheduler.run_provider_once(
        db_session, provider='kis', scheduler_slot='09:10', now=clock[0],
    )
    db_session.commit()

    assert result['result'] == 'retry_pending'
    assert len(retries.pending) == 1
    assert retries.run_next(clock) == 30
    assert len(retries.pending) == 1
    assert retries.run_next(clock) is None
    db_session.commit()

    claim = db_session.query(UserAutoTradingSlotClaim).filter_by(
        user_id=user.id, scheduler_slot='09:10',
    ).one()
    run = db_session.query(TradeRunLog).filter_by(
        owner_user_id=user.id, run_key=claim.run_key,
    ).one()
    retry_details = json.loads(run.response_payload)['account_snapshot_retry']
    assert calls['count'] == 3
    assert claim.status == 'completed'
    assert retry_details['attempts'] == 3
    assert retries.pending == []
    assert len(broker.buy_calls) + len(broker.sell_calls) <= 1


def test_kis_snapshot_retry_exhausts_after_three_attempts_with_diagnostics(
    db_session, monkeypatch
):
    user, scheduler, _account, _analysis, broker, _kis, retries, clock, calls = (
        _retry_user_setup(db_session, monkeypatch, failures=3)
    )

    result = scheduler.run_provider_once(
        db_session, provider='kis', scheduler_slot='09:10', now=clock[0],
    )
    db_session.commit()

    assert result['result'] == 'retry_pending'
    assert retries.run_next(clock) == 30
    assert retries.run_next(clock) is None
    db_session.commit()

    claim = db_session.query(UserAutoTradingSlotClaim).filter_by(
        user_id=user.id, scheduler_slot='09:10',
    ).one()
    run = db_session.query(TradeRunLog).filter_by(
        owner_user_id=user.id, run_key=claim.run_key,
    ).one()
    response = json.loads(run.response_payload)
    assert calls['count'] == 3
    assert claim.status == 'failed'
    assert claim.result == 'failed'
    assert claim.reason == 'user_scheduler_processing_failed'
    assert response['failure_stage'] == 'account_snapshot'
    assert response['retry_policy'] == 'kis_account_snapshot'
    assert response['attempts'] == 3
    assert response['max_attempts'] == 3
    assert response['retry_delay_seconds'] == 30
    assert response['final_failure_stage'] == 'account_snapshot'
    assert retries.pending == []
    assert len(broker.buy_calls) + len(broker.sell_calls) == 0


def test_kis_authentication_failure_is_not_retried(db_session, monkeypatch):
    user, scheduler, _account, _analysis, _broker, _kis, retries, clock, calls = (
        _retry_user_setup(
            db_session,
            monkeypatch,
            failures=0,
            permanent_error=UserBrokerAuthenticationError('authentication rejected'),
        )
    )

    result = scheduler.run_provider_once(
        db_session, provider='kis', scheduler_slot='09:10', now=clock[0],
    )
    db_session.commit()

    claim = db_session.query(UserAutoTradingSlotClaim).filter_by(
        user_id=user.id, scheduler_slot='09:10',
    ).one()
    assert result['result'] == 'failed'
    assert result['failed'] == 1
    assert calls['count'] == 1
    assert claim.status == 'failed'
    assert retries.pending == []


def test_kis_retry_pending_user_does_not_block_another_users_slot(
    db_session, monkeypatch
):
    first_user = _user(db_session, 'retry-isolated-user-1')
    second_user = _user(db_session, 'retry-isolated-user-2')
    for user in (first_user, second_user):
        _configure_user(db_session, user, provider='kis')
        _set_profile_schedule(db_session, user, ['09:10'])
    scheduler, account, _analysis, _broker, _kis = _harness()
    retries = DeferredAccountSnapshotRetries()
    scheduler.retry_scheduler = retries.schedule
    scheduler.retry_service_factory = lambda: scheduler
    clock = [datetime(2026, 9, 11, 0, 10, tzinfo=UTC)]
    scheduler.now_provider = lambda: clock[0]
    original = account.get_broker_snapshot
    calls = {int(first_user.id): 0, int(second_user.id): 0}

    def snapshot(db, user, provider):
        calls[int(user.id)] += 1
        if int(user.id) == int(first_user.id) and calls[int(user.id)] == 1:
            raise UserBrokerUnavailableError(
                'temporary KIS account read failure',
                details={'error_type': 'ConnectionError'},
            )
        return original(db, user, provider)

    account.get_broker_snapshot = snapshot
    monkeypatch.setattr(
        user_scheduler_module,
        'SessionLocal',
        sessionmaker(bind=db_session.get_bind(), expire_on_commit=False),
    )

    result = scheduler.run_provider_once(
        db_session, provider='kis', scheduler_slot='09:10', now=clock[0],
    )
    db_session.commit()

    first_claim = db_session.query(UserAutoTradingSlotClaim).filter_by(
        user_id=first_user.id, scheduler_slot='09:10',
    ).one()
    second_claim = db_session.query(UserAutoTradingSlotClaim).filter_by(
        user_id=second_user.id, scheduler_slot='09:10',
    ).one()
    assert result['retry_pending'] == 1
    assert result['completed'] == 1
    assert first_claim.status == 'retry_pending'
    assert second_claim.status == 'completed'
    assert calls[int(second_user.id)] == 1
    assert len(retries.pending) == 1


def test_post_snapshot_analysis_failure_does_not_enter_snapshot_retry(
    db_session, monkeypatch
):
    user, scheduler, _account, analysis, _broker, _kis, retries, clock, calls = (
        _retry_user_setup(db_session, monkeypatch, failures=0)
    )
    def fail_after_snapshot(*_args, **_kwargs):
        raise RuntimeError('post_snapshot_candidate_failure')

    scheduler._select_candidates = fail_after_snapshot

    result = scheduler.run_provider_once(
        db_session, provider='kis', scheduler_slot='09:10', now=clock[0],
    )

    assert result['result'] == 'failed'
    assert calls['count'] == 1
    assert retries.pending == []


def test_kis_retry_worker_exception_finalizes_existing_claim(
    db_session, monkeypatch
):
    user, scheduler, _account, _analysis, broker, _kis, retries, clock, calls = (
        _retry_user_setup(db_session, monkeypatch, failures=1)
    )
    first = scheduler.run_provider_once(
        db_session, provider='kis', scheduler_slot='09:10', now=clock[0],
    )
    db_session.commit()
    assert first['result'] == 'retry_pending'

    def fail_retry_setup(*_args, **_kwargs):
        raise RuntimeError('retry_setup_failed')

    scheduler._existing_settings = fail_retry_setup
    assert retries.run_next(clock) is None
    db_session.expire_all()

    claim = db_session.query(UserAutoTradingSlotClaim).filter_by(
        user_id=user.id, scheduler_slot='09:10',
    ).one()
    assert claim.status == 'failed'
    assert claim.result == 'failed'
    assert claim.reason == 'account_snapshot_retry_worker_failed'
    assert calls['count'] == 1
    assert broker.buy_calls == []
    assert broker.sell_calls == []
    assert retries.pending == []


def test_kis_retry_rechecks_user_trading_enabled_before_snapshot(
    db_session, monkeypatch
):
    user, scheduler, _account, _analysis, broker, _kis, retries, clock, calls = (
        _retry_user_setup(db_session, monkeypatch, failures=1)
    )
    manage_calls = []
    scheduler.position_management_service.manage = (
        lambda *_args, **_kwargs: manage_calls.append(True)
    )
    first = scheduler.run_provider_once(
        db_session, provider='kis', scheduler_slot='09:10', now=clock[0],
    )
    db_session.commit()
    assert first['result'] == 'retry_pending'

    settings = db_session.query(UserTradingSettings).filter_by(
        user_id=user.id,
    ).one()
    settings.enabled = False
    db_session.commit()

    assert retries.run_next(clock) is None
    db_session.expire_all()
    claim = db_session.query(UserAutoTradingSlotClaim).filter_by(
        user_id=user.id, scheduler_slot='09:10',
    ).one()
    assert claim.status == 'completed'
    assert claim.result == 'blocked'
    assert claim.reason == 'auto_trading_disabled_before_account_snapshot_retry'
    assert calls['count'] == 1
    assert manage_calls == []
    assert broker.buy_calls == []
    assert broker.sell_calls == []
