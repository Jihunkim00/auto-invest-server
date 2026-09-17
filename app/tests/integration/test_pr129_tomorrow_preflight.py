from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.db.models import (
    AutomationProfileWatchlistItem,
    AutomationProfileWatchlistSnapshot,
    OrderLog,
    TradeRunLog,
    UserAutoTradingSlotClaim,
    UserTradingSettings,
    WatchlistSnapshotItem,
)
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.automation_profile_service import AutomationProfileService
from app.services.automation_profile_watchlist_service import (
    AutomationProfileWatchlistService,
)
from app.services.scheduler_service import SchedulerService
from app.services.automation_scheduler_service import AutomationSchedulerService
from app.services.profile_aware_dry_run_auto_buy_service import (
    ProfileAwareDryRunAutoBuyService,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.strategy_profile_service import StrategyProfileService
from app.services.user_auto_trading_scheduler_service import (
    UserAutoTradingCandidateService,
    UserAutoTradingSchedulerService,
)
from app.services.user_trading_execution_service import UserTradingExecutionService

import app.services.automation_scheduler_service as automation_scheduler_module
import app.services.kis_watchlist_preview_service as kis_preview_module
from app.tests.integration.test_pr129_profile_shadow_replay import (
    ApprovedRisk,
    OpenMarket,
    ProfileBuy,
    make_preview,
    seed,
)
from app.tests.test_user_auto_trading_scheduler_pr129 import (
    FakeAccountService,
    FakeCredentialService,
)


KST = ZoneInfo('Asia/Seoul')
TARGET_DATE = '2026-09-18'
TARGET_UTC = datetime(2026, 9, 18, 0, 10, tzinfo=UTC)
PREOPEN_UTC = datetime(2026, 9, 17, 23, 59, 59, tzinfo=UTC)
SLOTS = ('09:10', '11:30', '13:30')
BOUNDARY_SYMBOL = '100001'
FAILED_GPT_SYMBOL = '100006'
BACKFILL_SYMBOL = '100007'


class NoSubmitKisClient:
    def __init__(self):
        self.submit_calls = 0

    def _blocked(self, *args, **kwargs):
        del args, kwargs
        self.submit_calls += 1
        raise AssertionError('tomorrow preflight must never submit an order')

    submit_order = _blocked
    submit_market_buy = _blocked
    submit_market_buy_qty = _blocked
    submit_market_sell = _blocked
    submit_market_sell_qty = _blocked


class PreflightSession(OpenMarket):
    def get_entry_slots(self, market=None):
        del market
        return [{'time': slot} for slot in SLOTS]


class PreflightRuntimePreview:
    def __init__(self, *, final_score=64.0, fail_gpt_symbol=FAILED_GPT_SYMBOL):
        self.final_score = final_score
        self.fail_gpt_symbol = fail_gpt_symbol
        self.calls = []

    def run_preview(self, **kwargs):
        self.calls.append(dict(kwargs))
        snapshot_items = list(kwargs['profile_snapshot_items'])
        cap = float(kwargs['max_price_krw'])
        runtime_items = []
        unaffordable = []
        for raw in snapshot_items:
            symbol = str(raw['symbol']).strip().upper()
            latest_price = 48300.0 if symbol == BOUNDARY_SYMBOL else float(
                raw.get('current_price') or 0
            )
            if latest_price > cap:
                unaffordable.append(symbol)
                continue
            runtime_items.append({
                **raw,
                'symbol': symbol,
                'current_price': latest_price,
                'indicator_status': 'ok',
                'quant_buy_score': float(raw.get('quant_buy_score') or 80.0),
                'quant_sell_score': float(raw.get('quant_sell_score') or 10.0),
                'runtime_quant_buy_score': float(
                    raw.get('quant_buy_score') or 80.0
                ),
                'runtime_quant_sell_score': float(
                    raw.get('quant_sell_score') or 10.0
                ),
                'gpt_used': False,
                'gpt_analysis_status': 'not_run',
                'ai_buy_score': None,
                'ai_sell_score': None,
                'final_buy_score': None,
                'final_sell_score': None,
                'final_entry_score': None,
                'score': None,
            })

        for rank, item in enumerate(runtime_items, start=1):
            item['runtime_quant_rank'] = rank
        runtime_symbols = [item['symbol'] for item in runtime_items]
        runtime_top5 = runtime_symbols[:5]
        completed = []
        for rank, item in enumerate(runtime_items[:5], start=1):
            item['gpt_target_rank'] = rank
            if item['symbol'] == self.fail_gpt_symbol:
                item['gpt_analysis_status'] = 'failed'
                item['gpt_analysis_reason'] = 'deterministic injected GPT failure'
                continue
            item.update({
                'ai_buy_score': 75.0,
                'ai_sell_score': 15.0,
                'confidence': 0.8,
                'gpt_used': True,
                'gpt_analysis_status': 'completed',
                'final_buy_score': self.final_score,
                'final_sell_score': 10.0,
                'final_entry_score': self.final_score,
                'score': self.final_score,
            })
            completed.append(item['symbol'])

        final_items = [
            item for item in runtime_items[:5] if item['symbol'] in completed
        ]
        for rank, item in enumerate(final_items, start=1):
            item['final_rank'] = rank
            item['final_selected'] = rank == 1
        return {
            'provider': 'kis',
            'market': 'KR',
            'canonical_profile_pipeline': True,
            'profile_snapshot_selected_symbols': [
                str(item['symbol']).strip().upper() for item in snapshot_items
            ],
            'runtime_input_symbols': [
                str(item['symbol']).strip().upper() for item in snapshot_items
            ],
            'runtime_quant_candidate_symbols': runtime_symbols,
            'runtime_quant_top5_symbols': runtime_top5,
            'gpt_target_symbols': runtime_top5,
            'gpt_completed_symbols': completed,
            'gpt_failed_symbols': [
                symbol for symbol in runtime_top5 if symbol not in completed
            ],
            'gpt_replacement_count': 0,
            'final_candidate_symbols': [item['symbol'] for item in final_items],
            'selected_final_symbol': final_items[0]['symbol'] if final_items else None,
            'final_ranked_candidates': final_items,
            'final_ranked_top5': final_items,
            'final_best_candidate': final_items[0] if final_items else None,
            'items': runtime_items,
            'runtime_quant_candidate_count': len(runtime_items),
            'unaffordable_runtime_candidates': unaffordable,
            'profile_snapshot': kwargs['profile_snapshot_context'],
            'snapshot_id': kwargs['profile_snapshot_context']['id'],
        }


class FailingCanonicalRuntimePreview:
    def run_preview(self, **kwargs):
        del kwargs
        raise RuntimeError(
            'runtime quant failed appsecret=super-secret '
            'access_token=token-secret approval_key=approval-secret'
        )


def _update_profile(
    db,
    *,
    profile_id,
    owner_user_id,
    admin,
    max_price,
    fixed_budget,
):
    return AutomationProfileService().update(
        db,
        str(profile_id),
        AutomationProfileWriteRequest(
            entry={
                'analysis_times': list(SLOTS),
                'no_new_entry_after': '14:00',
                'min_final_score': 65.0,
            },
            operation={
                'start_date': '2026-09-16',
                'end_date': TARGET_DATE,
                'weekdays_only': True,
                'timezone': 'Asia/Seoul',
            },
            capital={
                'sizing_mode': 'fixed_budget',
                'fixed_budget': fixed_budget,
                'initial_budget_krw': fixed_budget,
                'max_order_notional_krw': max_price,
            },
            universe={
                'watchlist_size': 50,
                'min_price_krw': 1.0,
                'max_price_krw': max_price,
                'top_quant_candidates': 50,
                'top_ai_candidates': 5,
                'favorites': ['999999'],
            },
        ),
        admin_user_id=1 if admin else None,
        owner_user_id=None if admin else owner_user_id,
    )


def _build(db, monkeypatch, *, failing=False):
    monkeypatch.setattr(
        kis_preview_module,
        'get_settings',
        lambda: SimpleNamespace(
            kis_enabled=False,
            watchlist_min_entry_score=65,
            watchlist_min_score_gap=0,
            openai_api_key=None,
        ),
    )
    admin, regular, admin_profile, regular_profile, prices = seed(db)
    prices[BOUNDARY_SYMBOL] = 47900.0
    db.query(WatchlistSnapshotItem).filter(
        WatchlistSnapshotItem.symbol == BOUNDARY_SYMBOL
    ).one().current_price = 47900.0
    db.commit()
    _update_profile(
        db,
        profile_id=admin_profile['id'],
        owner_user_id=admin.id,
        admin=True,
        max_price=100000.0,
        fixed_budget=1000000.0,
    )
    _update_profile(
        db,
        profile_id=regular_profile['id'],
        owner_user_id=regular.id,
        admin=False,
        max_price=48000.0,
        fixed_budget=50000.0,
    )
    user_settings = db.query(UserTradingSettings).filter(
        UserTradingSettings.user_id == regular.id
    ).one()
    user_settings.trading_mode = 'live'
    user_settings.paper_trading_enabled = False
    user_settings.live_trading_enabled = True
    user_settings.kill_switch = False
    user_settings.auto_live_confirmed_at = TARGET_UTC - timedelta(days=1)
    db.commit()

    runtime = RuntimeSettingService()
    runtime.update_settings(db, {
        'automation_mode': 'test',
        'dry_run': True,
        'automation_profile_scheduler_enabled': True,
        'per_slot_new_entry_limit': 1,
        'max_open_positions': 3,
    })
    profiles = AutomationProfileService(runtime_settings=runtime)
    admin_preview = make_preview(prices)
    profile_aware = ProfileAwareDryRunAutoBuyService(
        preview_service=admin_preview,
        strategy_profiles=StrategyProfileService(),
        target_risk_service=ApprovedRisk(),
        market_sessions=OpenMarket(),
        profile_watchlists=AutomationProfileWatchlistService(),
    )
    production = AutomationSchedulerService()
    production.runtime_settings = runtime
    production.automation_profiles = profiles
    production.profile_aware_dry_run_auto_buy_service = profile_aware
    production.automation_profile_buy_scheduler_service = ProfileBuy(
        admin_preview.client
    )

    account = FakeAccountService(snapshots={
        (regular.id, 'kis'): {
            'provider': 'kis',
            'market': 'KR',
            'environment': 'live',
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
        },
    })
    no_submit = NoSubmitKisClient()
    execution = UserTradingExecutionService(
        account_service=account,
        credential_service=FakeCredentialService(),
        analysis_service=SimpleNamespace(kis_preview_service=admin_preview),
        session_service=PreflightSession(),
        kis_live_client_factory=lambda _db, _user, _credentials: no_submit,
        now_provider=lambda: TARGET_UTC,
    )
    user_scheduler = UserAutoTradingSchedulerService(
        execution_service=execution,
        account_service=account,
        session_service=PreflightSession(),
        automation_profiles=profiles,
        candidate_service=UserAutoTradingCandidateService(
            profile_watchlists=AutomationProfileWatchlistService(),
            runtime_preview_service=(
                FailingCanonicalRuntimePreview()
                if failing else PreflightRuntimePreview()
            ),
        ),
        now_provider=lambda: TARGET_UTC,
    )
    production.user_auto_trading_scheduler_service = user_scheduler
    monkeypatch.setattr(automation_scheduler_module, 'SessionLocal', lambda: db)
    return {
        'admin': admin,
        'regular': regular,
        'regular_id': regular.id,
        'profiles': profiles,
        'production': production,
        'user_scheduler': user_scheduler,
        'admin_preview': admin_preview,
        'no_submit': no_submit,
    }


def _at_slot(slot, *, second=0):
    hour, minute = (int(value) for value in slot.split(':', 1))
    return datetime(
        2026, 9, 18, hour, minute, second, tzinfo=KST
    ).astimezone(UTC)


def _assert_lineage(payload, *, snapshot_count=None):
    snapshot = set(payload['profile_snapshot_selected_symbols'])
    runtime_input = set(payload['runtime_input_symbols'])
    runtime_quant = set(payload['runtime_quant_candidate_symbols'])
    runtime_top5 = set(payload['runtime_quant_top5_symbols'])
    gpt_targets = set(payload['gpt_target_symbols'])
    completed = set(payload['gpt_completed_symbols'])
    final_candidates = set(payload['final_candidate_symbols'])
    final_rank_1 = payload.get('final_rank_1_symbol')
    if final_rank_1 is None and final_candidates:
        final_rank_1 = next(iter(payload['final_candidate_symbols']))
    assert runtime_input == snapshot
    assert runtime_quant <= runtime_input
    assert runtime_top5 <= runtime_quant
    assert gpt_targets == runtime_top5
    assert completed <= gpt_targets
    assert final_candidates <= completed
    assert payload['selected_final_symbol'] == final_rank_1
    assert payload['gpt_replacement_count'] == 0
    if snapshot_count is not None:
        assert len(snapshot) == snapshot_count


def _admin_due(production, slot, when):
    local = when.astimezone(KST)
    return slot in [
        value
        for value, hour, minute in production._profile_slots(local)
        if (local.hour, local.minute) == (hour, minute)
    ]


def test_pr129_tomorrow_preflight_smoke_no_submit(db_session, monkeypatch):
    env = _build(db_session, monkeypatch)
    db = db_session
    production = env['production']
    user_scheduler = env['user_scheduler']
    profiles = env['profiles']
    regular_id = env['regular_id']

    assert db.get_bind().url.get_backend_name() == 'sqlite'
    assert db.get_bind().url.database == ':memory:'
    admin_schedule = profiles.selected_profile_schedule(db, now=PREOPEN_UTC)
    regular_schedule = profiles.selected_owned_profile_schedule(
        db, owner_user_id=regular_id, now=PREOPEN_UTC
    )
    assert admin_schedule['profile']['id'] == 5
    assert admin_schedule['profile']['owner_user_id'] == 1
    assert admin_schedule['status'] == 'active'
    assert regular_schedule['profile']['id'] == 8
    assert regular_schedule['profile']['owner_user_id'] == 2
    assert regular_schedule['status'] == 'active'
    assert tuple(regular_schedule['analysis_times']) == SLOTS
    assert regular_schedule['profile']['operation']['start_date'] == '2026-09-16'
    assert regular_schedule['profile']['operation']['end_date'] == TARGET_DATE
    assert regular_schedule['profile']['operation']['weekdays_only'] is True
    assert regular_schedule['profile']['effective_settings']['universe'][
        'max_price_krw'
    ] == 48000.0
    assert admin_schedule['next_run_at'].astimezone(UTC) == _at_slot(SLOTS[0])
    assert regular_schedule['next_run_at'].astimezone(UTC) == _at_slot(SLOTS[0])

    jobs = production.production_trading_jobs()
    assert SchedulerService().production_trading_jobs() == []
    assert len(jobs) == 1
    assert jobs[0]['authority'] == 'AutomationSchedulerService'
    assert jobs[0]['provider'] == 'kis'
    assert jobs[0]['market'] == 'KR'
    user_jobs = [
        job for job in production.user_auto_trading_jobs(now=PREOPEN_UTC)
        if job['provider'] == 'kis'
    ]
    assert {job['slot'] for job in user_jobs} == set(SLOTS)
    assert all(job['timezone'] == 'Asia/Seoul' for job in user_jobs)
    assert all(job['user_scoped'] is True for job in user_jobs)

    for slot in SLOTS:
        before = _at_slot(slot, second=59) - timedelta(minutes=1)
        exact = _at_slot(slot)
        late = _at_slot(slot, second=59)
        after = exact + timedelta(minutes=1)
        assert not any(
            value[0] == slot
            for value in user_scheduler.due_slots(
                db, provider='kis', now=before
            )
        )
        assert any(
            value[0] == slot
            for value in user_scheduler.due_slots(
                db, provider='kis', now=exact
            )
        )
        assert any(
            value[0] == slot
            for value in user_scheduler.due_slots(
                db, provider='kis', now=late
            )
        )
        assert not any(
            value[0] == slot
            for value in user_scheduler.due_slots(
                db, provider='kis', now=after
            )
        )
        assert not _admin_due(production, slot, before)
        assert _admin_due(production, slot, exact)
        assert _admin_due(production, slot, late)
        assert not _admin_due(production, slot, after)

    for slot in admin_schedule['analysis_times']:
        result = production.run_once(slot=slot, now=_at_slot(slot))
        dry = result['dry_run']
        canonical = dry['dry_run_result']
        assert result['scheduler'] == 'AutomationSchedulerService'
        assert result['profile_key'] == admin_schedule['profile_key']
        assert canonical['profile_id'] == 5
        assert canonical['owner_user_id'] == 1
        _assert_lineage(canonical)
        assert result['submission_eligible'] is False
        assert result['profile_buy']['broker_submit_called'] is False
        assert result['profile_buy']['real_external_kis_submit_count'] == 0
        assert dry['broker_submit_called'] is False
        assert dry['real_order_submitted'] is False

    first = production._run_user_auto_dispatcher(
        'kis', SLOTS[0], _at_slot(SLOTS[0])
    )
    first_item = next(
        value for value in first['items'] if value['owner_user_id'] == regular_id
    )
    assert first['processed'] == 1
    assert first['completed'] == 1
    assert first_item['owner_user_id'] == 2
    assert first_item['profile_id'] == 8
    assert first_item['profile_context'] is not None
    assert first_item['result'] != 'user_scheduler_processing_failed'
    assert first_item['requested_symbol'] != 'NONE'
    assert first_item['reason'] == 'below_profile_buy_threshold'
    diagnostics = first_item['pipeline_diagnostics']
    _assert_lineage(diagnostics, snapshot_count=50)
    assert diagnostics['effective_max_candidate_price'] == 48000.0
    assert diagnostics['runtime_quant_candidate_count'] == 49
    assert BOUNDARY_SYMBOL not in diagnostics['runtime_quant_candidate_symbols']
    assert BOUNDARY_SYMBOL not in diagnostics['gpt_target_symbols']
    assert BOUNDARY_SYMBOL not in diagnostics['final_candidate_symbols']
    assert BOUNDARY_SYMBOL in diagnostics['unaffordable_runtime_candidates']
    assert BACKFILL_SYMBOL not in diagnostics['gpt_target_symbols']
    assert first_item['broker_submit_called'] is False
    assert first_item['real_order_submitted'] is False

    duplicate = production._run_user_auto_dispatcher(
        'kis', SLOTS[0], _at_slot(SLOTS[0])
    )
    assert duplicate['processed'] == 0
    assert duplicate['items'][0]['reason'] == 'duplicate_scheduler_slot'

    for slot in SLOTS[1:]:
        result = production._run_user_auto_dispatcher(
            'kis', slot, _at_slot(slot)
        )
        item = next(
            value for value in result['items'] if value['owner_user_id'] == regular_id
        )
        assert result['processed'] == 1
        assert item['profile_id'] == 8
        assert item['profile_context'] is not None
        assert item['result'] != 'user_scheduler_processing_failed'
        assert item['requested_symbol'] != 'NONE'
        _assert_lineage(item['pipeline_diagnostics'], snapshot_count=50)
        assert item['broker_submit_called'] is False
        assert item['real_order_submitted'] is False

    assert db.query(UserAutoTradingSlotClaim).filter_by(user_id=2).count() == 3
    assert db.query(UserAutoTradingSlotClaim).filter_by(user_id=1).count() == 0
    snapshots = db.query(AutomationProfileWatchlistSnapshot).filter_by(
        profile_id=8, owner_user_id=2
    ).all()
    assert len(snapshots) == 3
    items = db.query(AutomationProfileWatchlistItem).filter(
        AutomationProfileWatchlistItem.snapshot_id.in_([row.id for row in snapshots])
    ).all()
    assert len(items) == 150
    assert all(item.current_price <= 48000.0 for item in items)
    assert db.query(OrderLog).filter_by(owner_user_id=2).count() == 0
    assert env['admin_preview'].client.submit_calls == 0
    assert env['no_submit'].submit_calls == 0

    after_end = profiles.selected_owned_profile_schedule(
        db, owner_user_id=2, now=datetime(2026, 9, 19, 9, 0, tzinfo=KST)
    )
    assert after_end['status'] == 'ended'
    assert after_end['profile']['status'] == 'ended'
    assert production._profile_slots(
        datetime(2026, 9, 19, 9, 0, tzinfo=KST)
    ) == []
    end_dispatch = production._run_user_auto_dispatcher(
        'kis', SLOTS[0], datetime(2026, 9, 19, 0, 10, tzinfo=UTC)
    )
    assert end_dispatch['processed'] == 0
    assert end_dispatch['items'][0]['reason'] == 'automation_profile_missing'
    assert db.query(UserAutoTradingSlotClaim).filter_by(user_id=2).count() == 3

    print('=' * 60)
    print('PR129 TOMORROW PREFLIGHT - 2026-09-18')
    print('=' * 60)
    print('ADMIN PROFILE 5')
    print('Profile Active                 PASS')
    print('Schedule Registration         PASS')
    print('Tomorrow Slots                PASS ' + str(list(admin_schedule['analysis_times'])))
    print('Canonical Pipeline            PASS')
    print('Candidate Isolation           PASS')
    print('Final #1 Invariant            PASS')
    print('Broker Submit Blocked         PASS')
    print('TEST01 PROFILE 8 / OWNER 2')
    print('Profile Active                 PASS')
    print('Operation Date 2026-09-18     PASS')
    print('Schedule Registration         PASS')
    for slot in SLOTS:
        print(slot + ' Due Logic               PASS')
    print('Actual User Scheduler Path    PASS')
    print('No Generic Scheduler Failure  PASS')
    print('Profile Context               PASS')
    print('Affordability <= 48,000       PASS')
    print('Runtime Top5 Scope            PASS')
    print('GPT Top5 Scope                PASS')
    print('Final #1 Invariant            PASS')
    print('Duplicate Claim Safety        PASS')
    print('Broker Submit Blocked         PASS')
    print('PRODUCTION SCHEDULER')
    print('Authority                     PASS')
    print('Admin Jobs Registered         PASS')
    print('User KIS Jobs Registered      PASS')
    print('Timezone Asia/Seoul           PASS')
    print('Next Run Calculation          PASS')
    print('End Date Inactivation         PASS')
    print('SAFETY')
    print('Production DB Modified        NO')
    print('Tomorrow Claim Consumed       NO')
    print('Broker Submit Called          NO')
    print('Real Order Submitted          NO')
    print('OVERALL: PASS')


def test_pr129_tomorrow_preflight_failure_diagnostics_no_submit(
    db_session, monkeypatch
):
    env = _build(db_session, monkeypatch, failing=True)
    result = env['production']._run_user_auto_dispatcher(
        'kis', SLOTS[0], _at_slot(SLOTS[0])
    )
    item = next(
        value for value in result['items']
        if value['owner_user_id'] == env['regular_id']
    )
    run = db_session.query(TradeRunLog).filter_by(
        owner_user_id=env['regular_id']
    ).one()
    payload = json.loads(run.response_payload or '{}')
    assert item['result'] == 'failed'
    assert item['reason'] == 'user_scheduler_processing_failed'
    assert item['failure_stage'] == 'runtime_quant'
    assert item['exception_type'] == 'RuntimeError'
    assert item['sanitized_error'] == 'sensitive broker error details redacted'
    assert item['profile_context'] is not None
    assert run.stage == 'runtime_quant'
    assert payload['failure_stage'] == 'runtime_quant'
    assert payload['exception_type'] == 'RuntimeError'
    serialized = json.dumps(payload)
    assert 'super-secret' not in serialized
    assert 'token-secret' not in serialized
    assert 'approval-secret' not in serialized
    assert item['broker_submit_called'] is False
    assert item['real_order_submitted'] is False
    assert env['no_submit'].submit_calls == 0
    print('Failure Diagnostics           PASS')
