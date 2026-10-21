"""Context-local timing only; never changes execution authority or deadlines."""
from contextlib import contextmanager
from contextvars import ContextVar
import time

_trace = ContextVar('automation_run_diagnostics', default=None)


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
