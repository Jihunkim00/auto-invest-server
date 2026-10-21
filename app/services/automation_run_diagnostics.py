"""Context-local observations of actual decisions, never execution authority."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import time

_trace = ContextVar('automation_run_diagnostics', default=None)

GATES = (
    'SCHEDULER', 'ACCOUNT_AUTHORITY', 'MARKET_SESSION', 'ACCOUNT_SCOPE',
    'KIS_SNAPSHOT', 'POSITION', 'ENTRY_WINDOW', 'WATCHLIST', 'A_RANKING',
    'C65', 'GPT_COMPLETION', 'GPT60', 'FINAL65', 'ACCOUNT_RISK',
    'SIZING', 'GLOBAL_SAFETY', 'BROKER_PREFLIGHT', 'SUBMIT_SAFETY', 'BROKER_BUY',
)


def new_trace(*, owner_user_id, scheduler_slot, now_provider, profile_id=None):
    return {'stages': {}, 'stage_durations_ms': {}, 'gates': [],
            'owner_user_id': owner_user_id, 'profile_id': profile_id,
            'scheduler_slot': scheduler_slot, 'started_at': now_provider().isoformat(),
            '_now_provider': now_provider}


def set_gate_scope(profile_id):
    trace = _trace.get()
    if trace is not None:
        trace['profile_id'] = profile_id
        for row in trace['gates']:
            row['profile_id'] = profile_id


def record_gate(name, *, actual=None, required=None, reason=None, detail=None,
                status=None, stage=None, duration_ms=0, **evidence):
    trace = _trace.get()
    if trace is None:
        return
    status = status or ('BLOCK' if reason else 'PASS')
    if status not in {'PASS', 'BLOCK', 'FAILED', 'NOT_REACHED'}:
        raise ValueError('invalid_gate_status')
    if status == 'NOT_REACHED':
        actual, reason = None, 'not_reached'
    trace['gates'].append({
        'gate_name': name, 'stage': stage or name.lower(), 'status': status,
        'actual_value': actual, 'required_value': required,
        'reason_code': reason or ('not_reached' if status == 'NOT_REACHED' else 'passed'),
        'reason_detail': detail if detail is not None else (reason or 'condition satisfied'),
        'owner_user_id': trace['owner_user_id'], 'profile_id': trace['profile_id'],
        'scheduler_slot': trace['scheduler_slot'],
        'checked_at': trace['_now_provider']().isoformat(),
        'duration_ms': round(max(0, duration_ms), 3),
        'sequence': len(trace['gates']) + 1, **evidence,
    })


def finish_trace(trace, result):
    """Unexecuted gates have null data, including genuinely uncomputed scores."""
    reached = {row['gate_name'] for row in trace['gates']}
    for name in GATES:
        if name not in reached:
            record_gate(name, status='NOT_REACHED', detail='execution did not reach this gate')
    reason = result.get('reason')
    if str(result.get('result') or result.get('status')).lower() in {'hold', 'blocked', 'failed', 'skipped', 'retry_pending'}:
        blocks = [row for row in trace['gates'] if row['status'] in {'BLOCK', 'FAILED'}]
        # A candidate can fail while another candidate succeeds. Resolve a run
        # blocker against its recorded reason rather than the first rejected symbol.
        decisions = [row for row in blocks if row['gate_name'] != 'ENTRY_DECISION']
        first = next((row for row in decisions if row['reason_code'] == reason), None)
        # A terminal summary such as no_gpt_completed_execution_candidate
        # must not replace the earlier C65 block and its actual score.
        first = first or (decisions[0] if decisions else blocks[0] if blocks else None)
        if first:
            trace['first_blocked_gate'] = dict(first)
            trace['first_blocked_stage'] = first['stage']
    trace['gate_counts'] = {status: sum(row['status'] == status for row in trace['gates'])
                            for status in ('PASS', 'BLOCK', 'FAILED', 'NOT_REACHED')}
    trace.pop('_now_provider', None)
    return trace


def observe_gate(name, *, allowed_key=None, reason_key='reason', stage=None):
    """Observe a real method's return without replacing its implementation."""
    def decorate(method):
        @wraps(method)
        def observed(*args, **kwargs):
            started = time.perf_counter()
            try:
                result = method(*args, **kwargs)
            except Exception as exc:
                record_gate(name, status='FAILED', reason=str(exc) if str(exc).isidentifier()
                            else type(exc).__name__, detail=type(exc).__name__, stage=stage,
                            duration_ms=(time.perf_counter() - started) * 1000)
                raise
            data = result.to_dict() if hasattr(result, 'to_dict') else result
            if isinstance(data, dict):
                observed_data = data
                if name == 'BROKER_PREFLIGHT' and isinstance(kwargs.get('sizing'), dict):
                    sizing = kwargs['sizing']
                    observed_data = {**data, **{key: sizing.get(key) for key in
                        ('quantity', 'target_notional', 'final_quantity', 'internal_quantity', 'kis_profile_quantity')},
                        'possible_order': {key: value for key, value in (sizing.get('kis_possible_order') or {}).items()
                            if key not in {'msg1'}}}
                reason = data.get(reason_key)
                if allowed_key:
                    allowed = data.get(allowed_key) is True
                    reason = None if allowed else (reason or next(iter(data.get('risk_flags') or
                        data.get('block_reasons') or []), 'gate_rejected'))
                record_gate(name, actual=observed_data, required={allowed_key: True} if allowed_key else
                    {'reason': None}, reason=reason, stage=stage,
                    duration_ms=(time.perf_counter() - started) * 1000)
            return result
        return observed
    return decorate


@contextmanager
def capture_run(trace):
    token = _trace.set(trace)
    try:
        yield
    finally:
        _trace.reset(token)


@contextmanager
def measure_stage(stage):
    trace = _trace.get()
    started = time.perf_counter()
    if trace is not None:
        trace['final_stage'] = stage
    try:
        yield
    except Exception:
        if trace is not None:
            trace.setdefault('first_failure_stage', stage)
            trace['stages'][stage] = 'FAILED'
        raise
    else:
        if trace is not None:
            trace['stages'][stage] = 'COMPLETED'
    finally:
        if trace is not None:
            timings = trace['stage_durations_ms']
            timings[stage] = round(timings.get(stage, 0) + (time.perf_counter() - started) * 1000, 3)


def record_snapshot(snapshot):
    trace = _trace.get()
    if trace is not None:
        orders = snapshot.get('open_orders')
        trace['account_snapshot'] = {
            'status': 'SUCCESS', 'positions_reliable': snapshot.get('positions_reliable'),
            'open_orders_reliable': snapshot.get('open_orders_reliable'),
            'held_position_count': len(snapshot.get('positions') or []),
            'open_order_count': len(orders) if isinstance(orders, list) else None,
        }


def record_position_management(result):
    trace = _trace.get()
    if trace is not None:
        trace['position_management'] = dict(result)
        record_gate('POSITION', actual=result, required='no unresolved exit or position priority',
                    reason=result.get('reason') if result.get('entry_blocked') or result.get('positions') else None)


def record_preview(preview):
    trace = _trace.get()
    if trace is not None:
        performance = preview.get('performance') or {}
        for stage, key in (('a_quant', 'a_quant_scan_ms'), ('c_quant', 'c_shadow_scan_ms'),
                           ('gpt', 'gpt_total_ms'), ('final_ranking', 'final_ranking_ms')):
            if key in performance:
                trace['stage_durations_ms'][stage] = performance[key]
                trace['stages'][stage] = 'COMPLETED'
        if preview.get('gpt_attempted_count') == 0:
            trace['stages']['gpt'] = 'NOT REACHED'
        if not preview.get('final_ranked_candidates'):
            trace['stages']['final_ranking'] = 'NOT CALCULATED'
        # These are the calculated production preview results, including each
        # rejected candidate. Null is retained for analyses that did not run.
        items = [row for row in preview.get('items', []) if row.get('selected_by_a_top5')]
        record_gate('WATCHLIST', actual=len(preview.get('runtime_input_symbols') or []),
                    required='profile watchlist available',
                    reason=None if preview.get('runtime_input_symbols') else 'watchlist_empty')
        record_gate('A_RANKING', actual=[{'symbol': row['symbol'], 'score': row.get('quant_buy_score')}
                    for row in items], required='top 5 by relative A rank',
                    reason=None if items else 'a_ranking_empty',
                    duration_ms=performance.get('a_quant_scan_ms', 0))
        for row in items:
            c = row.get('quant_c_score')
            analyzed = row.get('quant_c_status') == 'analyzed' and c is not None
            record_gate('C65', actual=c if analyzed else None, required=65.0, symbol=row['symbol'],
                        reason=None if analyzed and c >= 65 else 'c_score_below_threshold' if analyzed else 'c_quant_unavailable',
                        duration_ms=performance.get('c_shadow_scan_ms', 0), stage='c_quant')
        for row in items:
            gpt_status = row.get('gpt_analysis_status')
            reached = gpt_status in {'completed', 'failed'}
            complete = gpt_status == 'completed' and row.get('gpt_used') is True
            record_gate('GPT_COMPLETION', actual=gpt_status if reached else None, required='completed',
                        status=('PASS' if complete else 'FAILED') if reached else 'NOT_REACHED',
                        reason=None if complete else 'gpt_analysis_failed' if reached else 'not_reached',
                        symbol=row['symbol'], stage='gpt', duration_ms=performance.get('gpt_total_ms', 0))
            score = row.get('ai_buy_score') if complete else None
            record_gate('GPT60', actual=score, required=60.0, symbol=row['symbol'], stage='gpt',
                        status='NOT_REACHED' if not complete else None,
                        reason=None if score is not None and score >= 60 else
                               'gpt_buy_score_below_threshold' if complete else 'not_reached')
            final = row.get('final_buy_score') if complete else None
            record_gate('FINAL65', actual=final, required=65.0, symbol=row['symbol'], stage='final_ranking',
                        status='NOT_REACHED' if not complete or score is None or score < 60 else None,
                        reason=None if final is not None and final >= 65 else
                               'below_profile_buy_threshold' if complete else 'not_reached',
                        duration_ms=performance.get('final_ranking_ms', 0))
