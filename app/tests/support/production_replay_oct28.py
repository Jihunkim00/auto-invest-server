"""Read-only production evidence and isolated October 28 replay adapters.

No production harness imports. Raw OHLCV was not retained: the preview adapter
replays persisted indicator/C results, uses the real GPT normalizer, Final
blend/ranking and score gates. It does NOT claim to recalculate historical C.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db.models import (AutomationProfileAiCandidateResult, AutomationSchedulerSlot,
    OrderLog, SignalLog, StrategyProfile, TradeRunLog, User, WatchlistSnapshotRun)
from app.services.automation_profile_service import AutomationProfileService
from app.services.automation_profile_buy_scheduler_service import AutomationProfileBuySchedulerService
from app.services.scheduler_service import AutomationSchedulerService
from app.services.kis_automation_execution_core import KisAutomationExecutionCore
from app.services.kis_daily_entry_accounting import daily_entry_counts
from app.services.kis_order_validation_service import KisOrderValidationService
from app.services.kis_watchlist_preview_service import KisPreviewGptAdvisor, KisWatchlistPreviewService
from app.services.kis_a_top5_score_gate import apply_a_top5_score_gate
from app.services.market_session_service import MarketSessionService
from app.services.profile_aware_dry_run_auto_buy_service import ProfileAwareDryRunAutoBuyService
from app.services.quant_signal_service import QuantSignalService
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.strategy_risk_budget_service import StrategyRiskBudgetService
from app.services.target_aware_risk_service import TargetAwareRiskService
from app.services.user_auto_trading_scheduler_service import UserAutoTradingCandidateService, UserAutoTradingSchedulerService
from app.services.user_trading_execution_service import UserTradingExecutionService

KST = ZoneInfo('Asia/Seoul')
DAY = '2026-10-28'
ROOT = Path(__file__).resolve().parents[3]
MAJOR = ('users', 'user_trading_settings', 'runtime_settings', 'strategy_profiles',
         'orders', 'signals', 'trade_run_logs', 'automation_profile_buy_reservations',
         'automation_scheduler_slots', 'watchlist_snapshot_runs', 'watchlist_snapshot_items',
         'automation_profile_ai_candidate_results', 'position_lifecycles', 'broker_auth_tokens')


def at(value):
    return datetime.fromisoformat(f'{DAY}T{value}').replace(tzinfo=KST)


def parsed(value):
    try:
        result = json.loads(value or '{}')
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def readonly(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def fingerprint(path):
    """Only hashes/counts escape; table contents and credentials never escape."""
    output = {'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(), 'tables': {}}
    with readonly(path) as db:
        for table in MAJOR:
            digest, count = hashlib.sha256(), 0
            for row in db.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
                digest.update(repr(tuple(row)).encode())
                count += 1
            output['tables'][table] = {'count': count, 'sha256': digest.hexdigest()}
    return output


def backup(source, target):
    with readonly(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)


class Evidence:
    def __init__(self, source, directory):
        self.source = Path(source).resolve()
        self.before = fingerprint(self.source)
        self.seed = Path(directory) / 'production-backup.db'
        backup(self.source, self.seed)
        with readonly(self.seed) as db:
            self.runs = {r['id']: parsed(r['response_payload']) for r in db.execute(
                'SELECT id,response_payload FROM trade_run_logs WHERE id BETWEEN 260 AND 268')}
            self.ai = [dict(r) for r in db.execute(
                "SELECT * FROM automation_profile_ai_candidate_results WHERE snapshot_date=?", (DAY,))]
            self.raw = {rid: [dict(r) for r in db.execute(
                'SELECT * FROM watchlist_snapshot_items WHERE run_id=?', (rid,))] for rid in range(227, 231)}
            self.snapshots = {r['id']: dict(r) for r in db.execute(
                'SELECT * FROM watchlist_snapshot_runs WHERE id BETWEEN 227 AND 230')}
            self.indicators = {sid: parsed(db.execute('SELECT indicator_payload FROM signals WHERE id=?', (sid,)).fetchone()[0])
                               for sid in (92, 93)}
        accounts = [gate.get('actual_value', {}).get('account', {})
                    for gate in self.runs[262]['run_diagnostics']['gates']
                    if isinstance(gate.get('actual_value'), dict)]
        account = next(value for value in accounts if value.get('cash') is not None)
        self.user_cash, self.user_equity = float(account['cash']), float(account['equity'])
        assert self.runs[261]['final_buy_score'] == 67.07
        assert self.runs[265]['final_buy_score'] == 72.62
        assert len(self.raw[229]) == 200

    def verify_unchanged(self):
        after = fingerprint(self.source)
        assert self.before == after, 'Original DB changed during replay; hashes/counts only, no row dump'
        return {'original_db_unchanged': True, 'before_sha256': self.before['sha256'],
                'after_sha256': after['sha256'], 'major_tables_unchanged': True,
                'table_counts': {name: {'before': entry['count'], 'after': after['tables'][name]['count'],
                    'hash_unchanged': entry['sha256'] == after['tables'][name]['sha256']}
                    for name, entry in self.before['tables'].items()}}

    def rewind(self, target):
        backup(self.seed, target)
        cutoff = at('11:20:00').astimezone(UTC).replace(tzinfo=None).isoformat(' ')
        with sqlite3.connect(target) as db:
            # Only the independent backup is edited. Retain pre-slot history
            # for real compound capital, loss and risk calculations.
            for table, column in (
                ('orders', 'created_at'), ('signals', 'created_at'), ('trade_run_logs', 'created_at'),
                ('position_lifecycles', 'opened_at'), ('position_exit_retry_jobs', 'created_at'),
                ('automation_profile_watchlist_snapshots', 'generated_at')):
                db.execute(f'DELETE FROM {table} WHERE {column}>=?', (cutoff,))
            db.execute('DELETE FROM automation_profile_buy_reservations WHERE trade_date_kst>=?', (DAY,))
            db.execute('DELETE FROM automation_scheduler_slots WHERE scheduled_at>=?', (cutoff,))
            db.execute('DELETE FROM automation_profile_ai_candidate_results WHERE snapshot_date>=?', (DAY,))
            db.execute('DELETE FROM automation_profile_watchlist_items WHERE snapshot_id NOT IN (SELECT id FROM automation_profile_watchlist_snapshots)')
            db.execute('DELETE FROM watchlist_snapshot_runs WHERE started_at>=?', (cutoff,))
            db.execute('DELETE FROM watchlist_snapshot_items WHERE run_id NOT IN (SELECT id FROM watchlist_snapshot_runs)')
            db.execute('DELETE FROM user_auto_trading_slot_claims WHERE trading_date>=?', (DAY,))
            db.execute('DELETE FROM user_trading_risk_states WHERE trading_date>=?', (DAY,))
            db.execute('DELETE FROM account_buy_execution_claims')
            # Strip authentication from the COPY before any test can inspect it.
            db.execute('DELETE FROM broker_auth_tokens')
            db.execute('DELETE FROM auth_sessions')
            db.execute('UPDATE users SET password_hash=NULL,setup_code_hash=NULL')
            db.execute("UPDATE user_broker_credentials SET encrypted_payload='REPLAY-REDACTED'")


class Clock:
    def __init__(self):
        self.current = at('11:20:00')
    def now(self):
        return self.current


class ClockSessions(MarketSessionService):
    def __init__(self, clock):
        super().__init__()
        self.clock, self.force_closed = clock, False
    def get_session_status(self, market=None, *, now=None):
        value = super().get_session_status(market, now=now or self.clock.now())
        if self.force_closed:
            value.update(is_market_open=False, is_entry_allowed_now=False)
        return value


class RecordedKisClient:
    def __init__(self, evidence, clock, settings):
        self.evidence, self.clock, self.settings = evidence, clock, settings
        self.positions, self.executions = [], {}
        self.failure = None
        self.cash = float(evidence.runs[261]['available_cash_krw'])
        self.total_assets = float(evidence.runs[261]['total_assets_krw'])
        self.auth_manager = SimpleNamespace(require_configured=lambda: None, settings=settings)
    def list_positions(self):
        if self.failure == 'account':
            raise ConnectionError('recorded pre-dispatch account read failure')
        return copy.deepcopy(self.positions)
    def list_open_orders(self):
        return []
    def get_account_balance(self):
        return {'cash': self.cash, 'orderable_cash': self.cash, 'total_asset_value': self.total_assets}
    def get_domestic_stock_price(self, symbol):
        run = self.evidence.runs[265 if self.clock.now() >= at('12:00:00') else 261]
        price = next((x['price'] for x in run['candidates'] if x['symbol'] == symbol), run['simulated_price'])
        return {'symbol': symbol, 'current_price': price}
    def get_domestic_possible_order(self, **kwargs):
        price = self.get_domestic_stock_price(kwargs['symbol'])['current_price']
        return {'raw_status': 'ok', 'symbol': kwargs['symbol'], 'orderable_cash': self.cash,
                'orderable_quantity': int(self.cash / price), 'queried_at': self.clock.now().isoformat()}
    def build_domestic_order_payload(self, **kwargs):
        return {'PDNO': kwargs['symbol'], 'ORD_QTY': str(kwargs['qty']), 'CANO': '11112222', 'ACNT_PRDT_CD': '01'}
    def domestic_cash_order_tr_id(self, side):
        return 'RECORDED-FAKE-CASH'
    def get_order(self, order_id):
        return self.executions[order_id]


class FakeBroker:
    def __init__(self, client):
        self.client, self.calls, self.mode = client, [], 'filled'
    def submit_market_buy(self, *, symbol, qty):
        self.calls.append({'symbol': symbol, 'qty': qty})
        if self.mode == 'unknown':
            raise TimeoutError('fake POST dispatched; acknowledgment lost')
        identifier = f'FAKE-REPLAY-{len(self.calls)}'
        result = {'broker_order_id': identifier, 'status': self.mode,
                  'filled_qty': qty if self.mode == 'filled' else 0,
                  'avg_fill_price': self.client.get_domestic_stock_price(symbol)['current_price']}
        self.client.executions[identifier] = result
        if self.mode == 'filled':
            self.client.positions = [{'symbol': symbol, 'qty': qty, 'current_price': result['avg_fill_price'],
                                      'avg_entry_price': result['avg_fill_price'], 'cost_basis': qty * result['avg_fill_price']}]
        return result
    def submit_market_sell(self, **kwargs):
        raise AssertionError('Unexpected exit; replay must not invent sell responses')


class RecordedPreview:
    """Persisted analytical results, not invented OHLCV or new scoring rules."""
    def __init__(self, evidence, clock, sessions, *, owner, settings):
        self.evidence, self.clock, self.sessions, self.owner = evidence, clock, sessions, owner
        self.calls, self.hook = [], None
        self.advisor = KisPreviewGptAdvisor(settings=settings,
            client=SimpleNamespace(responses=SimpleNamespace(create=self.gpt_response)))
    def gpt_response(self, **kwargs):
        payload = self.pending
        return SimpleNamespace(output_text=json.dumps({
            'ai_buy_score': payload['ai_buy_score'], 'ai_sell_score': payload['ai_sell_score'],
            'confidence': payload['confidence'], 'action': 'buy',
            'reason': '당시 저장된 GPT 점수 응답 재생. 설명문은 비식별 처리.',
            'risk_flags': payload.get('recorded_risk_flags', []),
            'gating_notes': payload.get('recorded_gating_notes', []),
            'hard_block_reason': None}, ensure_ascii=False))
    def run_preview(self, **kwargs):
        context = kwargs.get('profile_snapshot_context') or {}
        slot = context.get('scheduler_slot')
        self.calls.append(slot)
        if self.hook:
            self.hook(slot)
        records = [r for r in self.evidence.ai if r['owner_user_id'] == self.owner and r['scheduler_slot'] == slot]
        items = []
        recorded_user = self.evidence.runs.get(262 if slot == '11:30' else 267, {}) if self.owner == 2 else {}
        profile_items = {r['symbol']: r for r in kwargs.get('profile_snapshot_items', [])}
        for row in records:
            gate = parsed(row['diagnostics_json']).get('candidate_score_gate') or {}
            if self.owner == 2:
                gate = next((value for value in recorded_user.get('candidate_rejections', [])
                             if value.get('symbol') == row['symbol']), gate)
            source = profile_items.get(row['symbol'], {})
            indicator = source.get('indicators') or parsed(source.get('indicators_json'))
            if row['symbol'] == '036460' and self.owner == 1:
                indicator = self.evidence.indicators[92 if slot == '11:20' else 93]
                recalculated_a = QuantSignalService().score(indicator, gate_level=2)['quant_buy_score']
                assert recalculated_a == row['runtime_quant_buy_score']
            recorded_candidates = (self.evidence.runs.get(261 if slot == '11:20' else 265, {}).get('candidates') or []) if self.owner == 1 else []
            quote = next((x['price'] for x in recorded_candidates if x.get('symbol') == row['symbol']), source.get('current_price') or indicator.get('price'))
            recorded_candidate = next((x for x in recorded_candidates if x.get('symbol') == row['symbol']), {})
            item = {'symbol': row['symbol'], 'name': row['symbol_name'],
                'price': quote, 'current_price': quote,
                'quant_buy_score': row['runtime_quant_buy_score'], 'quant_sell_score': row['runtime_quant_sell_score'],
                'quant_c_score': gate.get('quant_c_score'), 'quant_c_status': gate.get('quant_c_status'),
                'indicator_status': 'ok', 'indicator_payload': indicator,
                'runtime_quant_rank': row['runtime_quant_rank'], 'quant_rank': row['runtime_quant_rank'],
                'gpt_analysis_status': row['gpt_analysis_status'], 'gpt_used': bool(row['gpt_used']),
                'data_sufficient': recorded_candidate.get('data_sufficient', True),
                'entry_ready': recorded_candidate.get('entry_ready', False),
                'risk_flags': list(recorded_candidate.get('risk_flags') or []),
                'gating_notes': list(recorded_candidate.get('gating_notes') or []),
                'ai_buy_score': None, 'ai_sell_score': None, 'final_buy_score': None, 'final_sell_score': None}
            if row['gpt_used']:
                self.pending = {**row, 'recorded_risk_flags': item['risk_flags'],
                                'recorded_gating_notes': item['gating_notes']}
                response = self.advisor.analyze(symbol=row['symbol'], name=row['symbol_name'],
                    current_price=item['price'], indicator_status='ok', indicator_payload=indicator,
                    market_session=self.sessions.get_session_status('KR'), reference_sources=[])
                item.update(ai_buy_score=response.ai_buy_score, ai_sell_score=response.ai_sell_score,
                    confidence=response.confidence, gpt_used=response.gpt_used,
                    gpt_analysis_status=response.gpt_analysis_status)
                item['final_buy_score'] = KisWatchlistPreviewService._blend_score(item['quant_c_score'], item['ai_buy_score'])
                item['final_sell_score'] = row['final_sell_score']
                assert item['final_buy_score'] == row['final_buy_score']
            apply_a_top5_score_gate(item)
            items.append(item)
        final = KisWatchlistPreviewService._rank_final_candidates(object.__new__(KisWatchlistPreviewService),
            [r for r in items if r.get('a_top5_score_gate_passed') and r.get('final_buy_score') is not None])
        symbols = [r['symbol'] for r in items if r.get('quant_c_gate_passed')]
        targets = [r['symbol'] for r in items if r.get('gpt_used')]
        self.last = {'provider': 'kis', 'market': 'KR', 'selection_mode': 'A_TOP5_C_GPT',
            'canonical_profile_pipeline': True, 'items': items, 'final_ranked_candidates': final,
            'final_best_candidate': final[0] if final else None, 'researched_candidates': final,
            'runtime_input_symbols': list(profile_items), 'runtime_quant_candidate_symbols': symbols,
            'runtime_quant_top5_symbols': targets, 'gpt_target_symbols': targets,
            'gpt_completed_symbols': targets, 'gpt_failed_symbols': [],
            'final_candidate_symbols': [r['symbol'] for r in final], 'runtime_quant_candidate_count': len(symbols),
            'final_ranked_top5': final[:5], 'gpt_top5_candidates': final[:5],
            'market_session': self.sessions.get_session_status('KR'), 'preview_status': 'ok',
            'risk_flags': [], 'gating_notes': []}
        for key in ('score_gate_candidate', 'candidate_rejections', 'candidate_rejection_summary'):
            if key in recorded_user:
                self.last[key] = copy.deepcopy(recorded_user[key])
        return self.last


class RecordedUserAccount:
    def __init__(self, clock, evidence):
        self.clock, self.evidence = clock, evidence
    def get_broker_snapshot(self, db, user, provider):
        return {'connected': True, 'owner_user_id': user.id, 'broker_account_id': f'user:{user.id}:kis:KR',
            'provider': 'kis', 'market': 'KR', 'environment': 'live', 'positions_reliable': True,
            'open_orders_reliable': True, 'positions': [], 'open_orders': [],
            'account': {'cash': self.evidence.user_cash, 'equity': self.evidence.user_equity,
                        'buying_power': self.evidence.user_cash},
            'fetched_at': self.clock.now().isoformat()}


class Replay:
    def __init__(self, evidence, path, monkeypatch):
        evidence.rewind(path)
        self.evidence, self.clock = evidence, Clock()
        self.engine = create_engine(
            f'sqlite:///{Path(path).as_posix()}', connect_args={'check_same_thread': False}, future=True)
        # Additive PR141 tables only in this isolated production backup.
        # Never run schema initialization against the original DB.
        from app.db.database import Base
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, future=True)
        @event.listens_for(self.sessions, 'before_flush')
        def virtual_timestamps(db, *_):
            for row in db.new:
                if isinstance(row, OrderLog) and row.side == 'buy':
                    if self.clock.now() == at('11:22:58'):
                        self.clock.current = at('11:23:00')
                if hasattr(row, 'created_at') and row.created_at is None:
                    row.created_at = self.clock.now().astimezone(UTC)
        settings = get_settings()
        for key, value in {'kis_env': 'live', 'kis_app_key': 'fake-replay-key', 'kis_app_secret': 'fake-replay-secret',
            'kis_account_no': '11112222', 'kis_account_product_code': '01', 'log_dir': None}.items():
            monkeypatch.setattr(settings, key, value)
        self.runtime = RuntimeSettingService()
        self.profiles = AutomationProfileService(runtime_settings=self.runtime)
        self.market = ClockSessions(self.clock)
        self.client = RecordedKisClient(evidence, self.clock, settings)
        self.broker = FakeBroker(self.client)
        self.preview = RecordedPreview(evidence, self.clock, self.market, owner=1, settings=settings)
        self.user_preview = RecordedPreview(evidence, self.clock, self.market, owner=2, settings=settings)
        self.budget = StrategyRiskBudgetService(runtime_settings=self.runtime, now_provider=self.clock.now,
            position_loader=lambda *_: self.client.list_positions(), balance_loader=lambda *_: self.client.get_account_balance())
        risk = TargetAwareRiskService(budget_service=self.budget)
        self.validation = KisOrderValidationService(self.client, session_service=self.market)
        core = KisAutomationExecutionCore(self.client, broker=self.broker, validation_service=self.validation,
            runtime_settings=self.runtime, now_provider=self.clock.now)
        self.buy = AutomationProfileBuySchedulerService(client=self.client, broker=self.broker,
            validation_service=self.validation, execution_core=core, runtime_settings=self.runtime,
            strategy_profiles=self.profiles, target_risk_service=risk,
            positions_loader=lambda db: self.client.list_positions(),
            balance_loader=lambda db: self.client.get_account_balance(), open_orders_loader=lambda db: self.client.list_open_orders())
        dry = ProfileAwareDryRunAutoBuyService(preview_service=self.preview, target_risk_service=risk, market_sessions=self.market)
        self.scheduler = AutomationSchedulerService(retry_now_provider=self.clock.now)
        self.scheduler.runtime_settings, self.scheduler.automation_profiles = self.runtime, self.profiles
        self.scheduler.profile_aware_dry_run_auto_buy_service = dry
        self.scheduler.automation_profile_buy_scheduler_service = self.buy
        account = RecordedUserAccount(self.clock, evidence)
        execution = UserTradingExecutionService(account_service=account, session_service=self.market, now_provider=self.clock.now)
        # Test01's recorded candidates fail C65, so its real scheduler must not
        # call this external submission factory at all.
        execution.kis_live_client_factory = lambda *_: (_ for _ in ()).throw(AssertionError('Unexpected user BUY'))
        self.user_service = UserAutoTradingSchedulerService(execution_service=execution, account_service=account,
            candidate_service=UserAutoTradingCandidateService(runtime_preview_service=self.user_preview),
            automation_profiles=self.profiles, session_service=self.market, now_provider=self.clock.now)
        monkeypatch.setattr('app.services.automation_scheduler_service.SessionLocal', self.sessions)
        monkeypatch.setattr('app.services.user_auto_trading_scheduler_service.SessionLocal', self.sessions)
        monkeypatch.setattr('app.services.automation_scheduler_service.MarketSessionService', lambda: self.market)
        monkeypatch.setattr('app.services.market_session_service.MarketSessionService', lambda: self.market)
        # Factory is resolved in automation_scheduler_service's module namespace.
        monkeypatch.setattr('app.services.automation_scheduler_service.UserAutoTradingSchedulerService', lambda **kw: self.user_service)
        self.scheduler.user_auto_trading_scheduler_service = self.user_service
        from app.services.scheduler_slot_dispatcher import SchedulerSlotDispatcher
        self.scheduler._slot_dispatcher = SchedulerSlotDispatcher(self.sessions, self.scheduler._task_supervisor, self.clock.now)
        self.results = []

    def stage(self, slot):
        if slot == '11:20':
            self.clock.current = at('11:22:58')
        elif slot == '12:20':
            self.clock.current = at('12:22:30')

    def drain(self):
        with self.scheduler._task_supervisor.lock:
            threads = [t['thread'] for t in self.scheduler._task_supervisor.tasks.values()]
        for thread in threads:
            thread.join(20)
            assert not thread.is_alive(), 'Replay worker did not exit'

    def slot(self, slot, *, user=False, advance=True):
        if advance:
            self.clock.current = at(slot + ':00')
        before_calls = len(self.broker.calls)
        preview = self.user_preview if user else self.preview
        before_analysis = len(preview.calls)
        with self.sessions() as db:
            before_entries, before_unresolved = daily_entry_counts(db, now=self.clock.now(), owner_user_id=2 if user else None)
        if user:
            self.scheduler._plan_user_slots(self.clock.now())
        else:
            self.scheduler._plan_admin_slots(self.clock.now())
        self.drain()
        with self.sessions() as db:
            account = 'user-2' if user else 'admin'
            row = db.query(AutomationSchedulerSlot).filter_by(account_key=account).filter(
                AutomationSchedulerSlot.scheduled_at == at(slot+':00').astimezone(UTC).replace(tzinfo=None)).one()
            result = parsed(row.result_json)
            payload = (result.get('items') or [result])[0]
            orders = db.query(OrderLog).filter(OrderLog.created_at >= at('11:20:00').astimezone(UTC)).all()
            own = [o for o in orders if o.owner_user_id == (2 if user else None)]
            order = own[-1] if own else None
            filled, unresolved = daily_entry_counts(db, now=self.clock.now(), owner_user_id=2 if user else None)
            latest = db.query(WatchlistSnapshotRun).order_by(WatchlistSnapshotRun.started_at.desc()).first()
            signal = db.query(SignalLog).filter(SignalLog.owner_user_id == (2 if user else None),
                SignalLog.created_at >= at(slot+':00').astimezone(UTC)).order_by(SignalLog.id.desc()).first()
            value = {'account': 'test01' if user else 'admin', 'slot': slot, 'slot_status': row.status,
                'block_reason': payload.get('reason') or row.reason, 'root_reason': payload.get('sanitized_error'),
                'order_status': order.internal_status if order else 'NOT SUBMITTED',
                'new_order_this_slot': bool(order and parsed(order.request_payload).get('scheduler_slot') == slot),
                'order_block_reason': order.error_message if order and parsed(order.request_payload).get('scheduler_slot') == slot else None,
                'order_created_at': order.created_at.isoformat() if order and parsed(order.request_payload).get('scheduler_slot') == slot else None,
                'slot_reason': row.reason,
                'fake_submit_count': len(self.broker.calls) - before_calls if not user else 0,
                'total_fake_submit_count': len(self.broker.calls),
                'daily_entries_used_before': before_entries,
                'unresolved_entry_count_before': before_unresolved,
                'daily_entries_used': filled, 'unresolved_entry_count': unresolved,
                'analysis_calls': len(self.user_preview.calls if user else self.preview.calls),
                'watchlist': latest.status if latest else 'missing',
                'buy_window': 'allowed' if self.clock.now() < at(slot+':00') + timedelta(seconds=600) else 'expired',
                'ai_action': signal.action.upper() if signal else 'HOLD' if len(preview.calls) > before_analysis else 'NOT RUN',
                'risk': 'approved' if signal and signal.approved_by_risk else 'blocked' if signal else 'NOT RUN',
                'scores': [{k: item.get(k) for k in ('symbol', 'quant_buy_score', 'quant_c_score', 'ai_buy_score', 'final_buy_score')}
                           for item in getattr(preview, 'last', {}).get('final_ranked_candidates', [])]
                          if len(preview.calls) > before_analysis else [],
                'actual_kis_submit_count': 0, 'result': result}
            self.results.append(value)
            return value

    def import_snapshot(self, identifier, *, recovered_at=None):
        with self.engine.begin() as db:
            source = dict(self.evidence.snapshots[identifier])
            if recovered_at is not None:
                source.pop('id')
                source.update(started_at=recovered_at.astimezone(UTC).replace(tzinfo=None),
                              completed_at=recovered_at.astimezone(UTC).replace(tzinfo=None))
            columns = list(source)
            result = db.exec_driver_sql(f'INSERT INTO watchlist_snapshot_runs ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})', tuple(source.values()))
            rid = result.lastrowid
            for raw in self.evidence.raw[identifier]:
                raw = {k: v for k, v in raw.items() if k != 'id'}
                raw['run_id'] = rid
                if recovered_at is not None:
                    raw['captured_at'] = recovered_at.astimezone(UTC).replace(tzinfo=None).isoformat(' ')
                columns = list(raw)
                db.exec_driver_sql(f'INSERT INTO watchlist_snapshot_items ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})', tuple(raw.values()))
            return rid

    def close(self):
        self.scheduler._task_supervisor.cancel_all()
        self.drain()
        self.engine.dispose()
