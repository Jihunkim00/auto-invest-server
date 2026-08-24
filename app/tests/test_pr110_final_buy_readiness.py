from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.enums import InternalOrderStatus
from app.db.models import AutomationProfileBuyReservation, OrderLog, PositionLifecycle, StrategyProfile
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.automation_profile_buy_scheduler_service import AutomationProfileBuySchedulerService
from app.services.automation_profile_service import AutomationProfileService
from app.services.kis_automation_execution_core import KisAutomationExecutionCore
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.scheduler_service import SchedulerService
from app.services.strategy_profile_service import StrategyProfileService


NOW = datetime(2026, 8, 25, 0, 10, tzinfo=UTC)


class PR110RuntimeSettingService(RuntimeSettingService):
    def __init__(self):
        super().__init__()
        self.gate = {
            'dry_run': False,
            'kill_switch': False,
            'kis_real_order_enabled': True,
            'runtime_authorized': True,
            'live_order_possible': True,
            'allowed': True,
            'blocking_reasons': [],
            'source_of_truth': 'automation_profile_live_order_gate',
        }

    def get_automation_profile_live_order_gate_read_only(self, db):
        return dict(self.gate)


class FakeKisClient:
    def __init__(self, *, possible_age_seconds=0, missing_possible=False, price=30000):
        self.positions = []
        self.possible_age_seconds = possible_age_seconds
        self.missing_possible = missing_possible
        self.price = price
        self.price_calls = 0
        self.possible_order_calls = 0
        self.external_kis_submit_count = 0
        self.now = NOW

    def get_account_balance(self):
        return {'cash': 1_000_000, 'orderable_cash': 1_000_000}

    def list_positions(self):
        return list(self.positions)

    def list_open_orders(self):
        return []

    def get_domestic_stock_price(self, symbol):
        self.price_calls += 1
        return {'current_price': self.price, 'symbol': symbol}

    def get_domestic_possible_order(self, **kwargs):
        self.possible_order_calls += 1
        if self.missing_possible:
            return {'raw_status': 'error', 'symbol': kwargs['symbol']}
        queried_at = self.now - timedelta(seconds=self.possible_age_seconds)
        return {
            'raw_status': 'ok',
            'symbol': kwargs['symbol'],
            'orderable_cash': 1_000_000,
            'orderable_quantity': 100,
            'queried_at': queried_at.isoformat(),
        }


class FakeBroker:
    def __init__(self, client):
        self.client = client
        self.buy_calls = []
        self.sell_calls = []

    def submit_market_buy(self, *, symbol, qty):
        self.buy_calls.append((symbol, qty))
        self.client.positions = [{'symbol': symbol, 'qty': qty}]
        return {'order_id': f'FAKE-BUY-{len(self.buy_calls)}', 'status': 'accepted'}

    def submit_market_sell(self, *, symbol, qty):
        self.sell_calls.append((symbol, qty))
        self.client.positions = []
        return {'order_id': f'FAKE-SELL-{len(self.sell_calls)}', 'status': 'accepted'}


class FakeValidationResult:
    def __init__(self, request):
        self.market = request.market
        self.symbol = request.symbol
        self.side = request.side
        self.qty = request.qty
        self.order_type = request.order_type
        self.validated_for_submission = True
        self.current_price = 30000.0
        self.estimated_amount = float(request.qty) * self.current_price
        self.block_reasons = []
        self.primary_block_reason = None

    def to_dict(self):
        return {
            'market': self.market,
            'symbol': self.symbol,
            'side': self.side,
            'qty': self.qty,
            'order_type': self.order_type,
            'validated_for_submission': True,
            'current_price': self.current_price,
            'estimated_amount': self.estimated_amount,
            'block_reasons': [],
            'primary_block_reason': None,
        }


class FakeValidationService:
    def __init__(self):
        self.calls = []

    def validate(self, request, *, now=None):
        self.calls.append(request)
        return FakeValidationResult(request)


class FakeOrderSyncService:
    def __init__(self):
        self.calls = []

    def sync_order(self, db, order_id):
        self.calls.append(order_id)
        row = db.get(OrderLog, int(order_id))
        row.internal_status = InternalOrderStatus.FILLED.value
        row.broker_status = 'filled'
        row.broker_order_status = 'filled'
        row.filled_qty = row.qty
        row.remaining_qty = 0
        row.avg_fill_price = row.filled_avg_price = row.limit_price
        db.commit()
        db.refresh(row)
        return row


class FakeTargetRiskService:
    def __init__(self, approved_notional=60000):
        self.approved_notional = approved_notional
        self.calls = []

    def evaluate_entry(self, db, request, *, profile_name=None):
        self.calls.append(request)
        return {
            'approved': True,
            'approved_notional_krw': self.approved_notional,
            'recommended_notional_krw': self.approved_notional,
            'risk_flags': [],
        }


class FakeDryRunService:
    def __init__(self, candidate):
        self.candidate = candidate
        self.calls = 0

    def run_dry_run_once(self, db, request):
        self.calls += 1
        return {
            'status': 'ok',
            'action': 'would_buy',
            'final_ranked_candidates': [self.candidate],
        }


def _create_active_profile(db, runtime, *, key='aut_pr110_readiness'):
    profiles = AutomationProfileService(runtime_settings=runtime)
    if db.query(StrategyProfile).filter(StrategyProfile.profile_key == key).first() is not None:
        return profiles
    created = profiles.create(
        db,
        AutomationProfileWriteRequest(
            profile_key=key,
            name='PR110 readiness profile',
            provider='kis',
            market='KR',
            enabled=True,
            entry={
                'analysis_times': ['09:10', '11:30', '13:30'],
                'min_final_score': 65,
            },
            exit={'stop_loss_pct': 2, 'take_profit_pct': 8},
            operation={
                'start_date': '2026-08-01',
                'end_date': '2026-09-30',
                'timezone': 'Asia/Seoul',
                'weekdays_only': False,
            },
        ),
    )
    profiles.activate(db, str(created['id']))
    return profiles


def _build_service(db, *, client=None, runtime=None, key='aut_pr110_readiness'):
    runtime = runtime or PR110RuntimeSettingService()
    RuntimeSettingService().update_settings(db, {'automation_mode': 'live', 'dry_run': False, 'kill_switch': False})
    profiles = _create_active_profile(db, runtime, key=key)
    client = client or FakeKisClient()
    broker = FakeBroker(client)
    validation = FakeValidationService()
    sync = FakeOrderSyncService()
    target = FakeTargetRiskService()
    service = AutomationProfileBuySchedulerService(
        client=client,
        broker=broker,
        validation_service=validation,
        order_sync_service=sync,
        runtime_settings=runtime,
        strategy_profiles=StrategyProfileService(),
        target_risk_service=target,
    )
    return service, runtime, profiles, client, broker, validation, sync, target


def _candidate(score=70, *, symbol='005930', price=30000):
    return {
        'symbol': symbol,
        'final_buy_score': score,
        'buy_score': score,
        'price': price,
        'data_sufficient': True,
        'target_risk_approved': True,
    }


def test_background_scheduler_shared_core_buy_is_exactly_once_and_restart_safe(db_session, monkeypatch):
    service, runtime, profiles, client, broker, validation, sync, target = _build_service(db_session)
    scheduler = SchedulerService()
    scheduler.runtime_settings = runtime
    scheduler.automation_profiles = profiles
    scheduler.automation_profile_buy_scheduler_service = service
    scheduler.strategy_auto_buy_scheduler_service = FakeDryRunService(_candidate())

    import app.services.scheduler_service as scheduler_module

    monkeypatch.setattr(scheduler_module, 'SessionLocal', lambda: db_session)
    first = scheduler._run_strategy_auto_buy_dry_run_scheduled_once(
        'strategy_auto_buy_dry_run_open_phase',
        now=NOW,
    )
    second = scheduler._run_strategy_auto_buy_dry_run_scheduled_once(
        'strategy_auto_buy_dry_run_open_phase',
        now=NOW,
    )

    assert first['profile_buy']['status'] == 'filled'
    assert first['profile_buy']['reason'] == 'buy_filled'
    assert second['profile_buy']['reason'] == 'scheduled_slot_already_attempted'
    assert len(broker.buy_calls) == 1
    assert len(validation.calls) == 1
    assert len(sync.calls) == 1
    assert client.external_kis_submit_count == 0
    assert db_session.query(PositionLifecycle).one().status == 'open'
    assert runtime.get_settings_read_only(db_session)['automation_profile_scheduler_enabled'] is True

    restarted_client = FakeKisClient()
    restarted_service, _, _, restarted_client, restarted_broker, _, _, _ = _build_service(
        db_session,
        client=restarted_client,
        runtime=runtime,
    )
    recovered = restarted_service.run_once(
        db_session,
        [_candidate()],
        scheduler_slot='09:10',
        trigger_source='automation_profile_scheduler',
        now=NOW,
    )
    assert recovered['reason'] == 'scheduled_slot_already_attempted'
    assert restarted_broker.buy_calls == []
    assert restarted_client.external_kis_submit_count == 0


def test_score_below_65_never_reaches_broker(db_session):
    service, _, _, _, broker, validation, _, _ = _build_service(db_session)
    result = service.run_once(
        db_session,
        [_candidate(64)],
        scheduler_slot='09:10',
        trigger_source='automation_profile_scheduler',
        now=NOW,
    )
    assert result['reason'] == 'below_profile_buy_threshold'
    assert broker.buy_calls == []
    assert validation.calls == []


def test_quantity_zero_top_candidate_falls_back_without_lowering_score_threshold(db_session):
    service, _, _, _, broker, _, _, _ = _build_service(db_session)
    result = service.run_once(
        db_session,
        [
            _candidate(72, symbol='000001', price=631000),
            _candidate(68, symbol='005930', price=30000),
        ],
        scheduler_slot='09:10',
        trigger_source='automation_profile_scheduler',
        now=NOW,
    )
    assert result['selected_symbol'] == '005930'
    assert result['quantity'] == 2
    assert result['final_buy_score'] == 68
    assert broker.buy_calls == [('005930', 2)]


@pytest.mark.parametrize(
    ('possible_age_seconds', 'missing_possible', 'reason'),
    [
        (11, False, 'possible_order_snapshot_stale'),
        (0, True, 'possible_order_unavailable'),
    ],
)
def test_possible_order_jit_age_and_missing_are_hard_blocks(
    db_session,
    possible_age_seconds,
    missing_possible,
    reason,
):
    client = FakeKisClient(
        possible_age_seconds=possible_age_seconds,
        missing_possible=missing_possible,
    )
    service, _, _, _, broker, _, _, _ = _build_service(db_session, client=client)
    result = service.run_once(
        db_session,
        [_candidate()],
        scheduler_slot='09:10',
        trigger_source='automation_profile_scheduler',
        now=NOW,
    )
    assert result['reason'] == reason
    assert broker.buy_calls == []
    assert client.possible_order_calls == 1


def test_readiness_is_read_only_and_exposes_all_live_conditions(db_session):
    service, _, _, client, broker, _, _, _ = _build_service(db_session)
    before = (len(broker.buy_calls), len(client.positions), client.external_kis_submit_count)
    readiness = service.readiness(db_session, now=NOW)
    after = (len(broker.buy_calls), len(client.positions), client.external_kis_submit_count)

    assert readiness['buy_ready_except_score'] is True
    assert readiness['scheduler_ready'] is True
    assert readiness['profile_ready'] is True
    assert readiness['execution_core_ready'] is True
    assert readiness['account_read_ready'] is True
    assert readiness['possible_order_path_ready'] is True
    assert readiness['validation_path_ready'] is True
    assert readiness['order_sync_ready'] is True
    assert readiness['lifecycle_ready'] is True
    assert readiness['blocking_reasons'] == []
    assert readiness['live_order_conditions'] == {
        'dry_run_false': True,
        'kill_switch_false': True,
        'kis_real_order_enabled': True,
        'runtime_authorized': True,
        'live_order_possible': True,
    }
    assert before == after


def test_open_position_has_priority_and_flags_remain_unchanged(db_session):
    service, runtime, _, _, broker, _, _, _ = _build_service(db_session)
    service.run_once(
        db_session,
        [_candidate()],
        scheduler_slot='09:10',
        trigger_source='automation_profile_scheduler',
        now=NOW,
    )
    before = runtime.get_settings_read_only(db_session)
    result = service.run_once(
        db_session,
        [_candidate(69)],
        scheduler_slot='11:30',
        trigger_source='automation_profile_scheduler',
        now=NOW + timedelta(hours=2, minutes=20),
    )
    after = runtime.get_settings_read_only(db_session)

    assert result['reason'] == 'position_management_priority'
    assert len(broker.buy_calls) == 1
    assert after == before
    assert after['automation_profile_scheduler_enabled'] is True


def test_tp_sl_lifecycle_close_and_next_slot_entry(db_session):
    service, _, _, client, broker, validation, sync, _ = _build_service(db_session)
    opened = service.run_once(
        db_session,
        [_candidate()],
        scheduler_slot='09:10',
        trigger_source='automation_profile_scheduler',
        now=NOW,
    )
    lifecycle = db_session.query(PositionLifecycle).one()
    assert opened['lifecycle']['status'] == 'open'
    assert lifecycle.take_profit_threshold_pct == 8
    assert lifecycle.stop_loss_threshold_pct == 2

    hold = service.manage_exit_once(
        db_session,
        current_price=30000 * 1.079,
        now=NOW + timedelta(minutes=1),
    )
    assert hold['reason'] == 'no_exit_condition'
    take_profit = service.manage_exit_once(
        db_session,
        current_price=30000 * 1.081,
        now=NOW + timedelta(minutes=2),
    )
    lifecycle = db_session.query(PositionLifecycle).one()
    assert take_profit['trigger'] == 'take_profit'
    assert len(broker.sell_calls) == 1
    assert len(sync.calls) == 2
    assert lifecycle.status == 'closed'

    next_entry_now = NOW + timedelta(hours=2, minutes=20)
    client.now = next_entry_now
    next_entry = service.run_once(
        db_session,
        [_candidate(70, price=30000)],
        scheduler_slot='11:30',
        trigger_source='automation_profile_scheduler',
        now=next_entry_now,
    )
    next_entry_reason = next_entry.get('reason')
    assert next_entry['status'] == 'filled', f'{next_entry_reason}: {next_entry}'
    assert len(broker.buy_calls) == 2

    stop_loss = service.manage_exit_once(
        db_session,
        current_price=30000 * 0.979,
        now=NOW + timedelta(hours=2, minutes=21),
    )
    assert stop_loss['trigger'] == 'stop_loss'
    assert len(broker.sell_calls) == 2
    assert db_session.query(PositionLifecycle).filter(PositionLifecycle.status == 'open').count() == 0
    assert len(validation.calls) == 4


def test_manual_smoke_twenty_times_does_not_create_scheduled_state(db_session):
    service, runtime, _, _, broker, validation, _, _ = _build_service(db_session)
    before = runtime.get_settings_read_only(db_session)
    for index in range(20):
        result = service.run_once(
            db_session,
            [_candidate()],
            scheduler_slot='09:10',
            trigger_source='manual_smoke',
            now=NOW - timedelta(minutes=index + 1),
        )
        assert result['reason'] == 'manual_execution_isolation'
    after = runtime.get_settings_read_only(db_session)

    assert broker.buy_calls == []
    assert validation.calls == []
    assert db_session.query(AutomationProfileBuyReservation).count() == 0
    assert after['automation_profile_scheduler_enabled'] is True
    assert after['active_automation_profile_key'] == before['active_automation_profile_key']


def test_execution_core_fresh_possible_order_passes_without_real_kis_submit(db_session):
    client = FakeKisClient()
    broker = FakeBroker(client)
    RuntimeSettingService().update_settings(db_session, {'automation_mode': 'live'})
    core = KisAutomationExecutionCore(client, broker=broker, runtime_settings=RuntimeSettingService())
    order = OrderLog(
        broker='kis',
        market='KR',
        symbol='005930',
        side='buy',
        order_type='market',
        qty=2,
        requested_qty=2,
        remaining_qty=2,
        limit_price=30000,
        notional=60000,
        internal_status=InternalOrderStatus.REQUESTED.value,
        request_payload='{automation_profile: true, source_type: profile_aware_guarded_live_auto_buy}',
    )
    db_session.add(order)
    db_session.commit()
    result = core.submit_market_buy(
        db_session,
        order=order,
        symbol='005930',
        qty=2,
        expected_price=30000,
        max_positions=1,
        max_order_notional_krw=60000,
        now=NOW,
    )
    assert result['submitted'] is True
    assert len(broker.buy_calls) == 1
    assert client.external_kis_submit_count == 0
