from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from app.db.models import (
    OrderLog,
    SignalLog,
    TradeRunLog,
    User,
    UserAutoTradingSlotClaim,
    UserTradingSettings,
    UserWatchlist,
)
from app.services.market_session_service import MarketSessionService
from app.services.user_broker_account_service import UserBrokerAccountService
from app.services.user_broker_credential_service import UserBrokerCredentialService
from app.services.user_symbol_analysis_service import UserSymbolAnalysisService
from app.services.user_trading_execution_service import UserTradingExecutionService
from app.services.user_auto_trading_scheduler_service import (
    USER_SCHEDULER_TRIGGER_SOURCE,
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
        scheduler_slot='09:35',
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
