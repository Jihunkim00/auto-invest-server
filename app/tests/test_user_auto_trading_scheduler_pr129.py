from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from app.db.models import (
    AutomationProfileWatchlistSnapshot,
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
from app.services.user_broker_account_service import UserBrokerAccountService
from app.services.user_broker_credential_service import UserBrokerCredentialService
from app.services.user_symbol_analysis_service import UserSymbolAnalysisService
from app.services.user_trading_execution_service import UserTradingExecutionService
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
            'local_time': '2026-09-11T10:00:00+09:00',
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

    def submit_market_buy_qty(self, *, symbol, qty):
        self.buy_calls.append((symbol, qty))
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
                'snapshot_date': '2026-09-11',
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
                runtime_items.append({
                    **raw,
                    'symbol': symbol,
                    'current_price': latest_price,
                    'indicator_status': 'ok',
                    'quant_buy_score': float(raw.get('quant_buy_score') or 80.0),
                    'quant_sell_score': float(raw.get('quant_sell_score') or 10.0),
                    'runtime_quant_buy_score': float(raw.get('quant_buy_score') or 80.0),
                    'runtime_quant_sell_score': float(raw.get('quant_sell_score') or 10.0),
                    'ai_buy_score': 75.0,
                    'ai_sell_score': 15.0,
                    'confidence': 0.8,
                    'gpt_used': True,
                    'gpt_analysis_status': 'completed',
                    'final_buy_score': float(self.final_score),
                    'final_sell_score': 10.0,
                })
        runtime_symbols = [item['symbol'] for item in runtime_items]
        for rank, item in enumerate(runtime_items, start=1):
            item['runtime_quant_rank'] = rank
            item['gpt_target_rank'] = rank
            item['final_rank'] = rank
            item['final_selected'] = rank == 1
        return {
            'canonical_profile_pipeline': True,
            'profile_snapshot_selected_symbols': [
                str(item['symbol']).upper() for item in snapshot_items
            ],
            'runtime_input_symbols': [
                str(item['symbol']).upper() for item in snapshot_items
            ],
            'runtime_quant_candidate_symbols': runtime_symbols,
            'runtime_quant_top5_symbols': runtime_symbols[:5],
            'gpt_target_symbols': runtime_symbols[:5],
            'gpt_completed_symbols': runtime_symbols[:5],
            'gpt_failed_symbols': [],
            'gpt_replacement_count': 0,
            'final_candidate_symbols': runtime_symbols[:5],
            'selected_final_symbol': runtime_symbols[0] if runtime_symbols else None,
            'final_ranked_candidates': runtime_items[:5],
            'final_ranked_top5': runtime_items[:5],
            'final_best_candidate': runtime_items[0] if runtime_items else None,
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
        current_price=100.0,
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


RUN_AT = datetime(2026, 9, 11, 1, 10, tzinfo=UTC)


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
    scheduler, account, _analysis, _broker, _kis_client = _harness()
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


def _canonical_scheduler_setup(db, *, final_score=70.0):
    _user(db, 'pr129-canonical-admin', role='admin')
    user = _user(db, 'pr129-canonical-user')
    _configure_user(db, user, provider='kis')
    _set_profile_schedule(
        db,
        user,
        ['09:10'],
        fixed_budget=50000,
        max_order_notional=48000,
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
    items = [
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
    preview = CanonicalRuntimePreview(
        {'005930': 48300.0, '000660': 47000.0},
        final_score=final_score,
    )
    scheduler.candidate_service = UserAutoTradingCandidateService(
        profile_watchlists=watchlists,
        runtime_preview_service=preview,
    )
    return scheduler, user, profile, preview, account, analysis, broker, kis_client


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
