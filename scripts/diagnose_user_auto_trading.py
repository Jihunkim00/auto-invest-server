"""Read existing SQLite audit data without importing trading services or brokers.

Usage: python scripts/diagnose_user_auto_trading.py --user test01 --date 2026-10-21
SQLite mode=ro and query_only prohibit writes, including accidental DB creation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import quote
from zoneinfo import ZoneInfo


def obj(value):
    try:
        parsed = json.loads(value or '{}')
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def code(value):
    if value is None:
        return None
    # Legacy error prose can contain raw KIS data. Only emit reason codes.
    return value if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_:. -]{0,159}', str(value)) else 'REDACTED_LEGACY_REASON'


@contextmanager
def open_readonly(path):
    target = Path(path).resolve(strict=True)
    db = sqlite3.connect('file:' + quote(target.as_posix(), safe='/:') + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    try:
        yield db
    finally:
        db.close()


def rows(db, table, where='', args=()):
    # Table names are fixed by this module, never supplied by CLI input.
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return [dict(row) for row in db.execute(f'SELECT * FROM {table} {where}', args)] if exists else []


def diagnose(db, username, trading_date):
    date.fromisoformat(trading_date)
    users = rows(db, 'users', 'WHERE username=?', (username,))
    if len(users) != 1:
        raise ValueError('user_not_found')
    user = users[0]
    owner = None if user['role'] == 'admin' else user['id']
    settings = rows(db, 'user_trading_settings', 'WHERE user_id=?', (user['id'],))
    start = datetime.fromisoformat(trading_date).replace(tzinfo=ZoneInfo('Asia/Seoul'))
    end = start + timedelta(days=1)
    lo = start.astimezone(ZoneInfo('UTC')).replace(tzinfo=None).isoformat(' ')
    hi = end.astimezone(ZoneInfo('UTC')).replace(tzinfo=None).isoformat(' ')
    account = 'admin' if owner is None else f'user-{owner}'
    ledgers = rows(db, 'automation_scheduler_slots',
        'WHERE account_key=? AND scheduled_at>=? AND scheduled_at<? ORDER BY scheduled_at', (account, lo, hi))
    claims = rows(db, 'user_auto_trading_slot_claims', 'WHERE user_id=? AND trading_date=?', (user['id'], trading_date))
    snapshots = rows(db, 'automation_profile_watchlist_snapshots',
        'WHERE owner_user_id IS ? AND snapshot_date=?', (owner, trading_date))
    candidates = rows(db, 'automation_profile_ai_candidate_results',
        'WHERE owner_user_id IS ? AND snapshot_date=?', (owner, trading_date))
    run_keys = {claim['run_key'] for claim in claims}
    candidate_run_ids = {item['run_id'] for item in candidates}
    runs = rows(db, 'trade_run_logs', 'WHERE owner_user_id IS ? ORDER BY id', (owner,))
    runs = [run for run in runs if run['run_key'] in run_keys or run['id'] in candidate_run_ids
            or (lo <= str(run['created_at']) < hi and run['trigger_source'] in {'user_scheduler', 'scheduler'})]
    slots = {claim['scheduler_slot'] for claim in claims} | {item['scheduler_slot'] for item in snapshots}
    slots |= {obj(run['request_payload']).get('scheduler_slot') for run in runs}
    slots |= {datetime.fromisoformat(item['scheduled_at']).replace(tzinfo=ZoneInfo('UTC')).astimezone(
        ZoneInfo('Asia/Seoul')).strftime('%H:%M') for item in ledgers}
    output = []
    for slot in sorted(value for value in slots if value):
        slot_runs = [run for run in runs if obj(run['request_payload']).get('scheduler_slot') == slot
                     or any(claim['scheduler_slot'] == slot and claim['run_key'] == run['run_key'] for claim in claims)]
        run = slot_runs[-1] if slot_runs else {}
        payload = obj(run.get('response_payload'))
        trace = payload.get('run_diagnostics') or {}
        management = payload.get('position_management') or trace.get('position_management') or {}
        pipeline = payload.get('pipeline_diagnostics') or (payload.get('profile_context') or {}).get('pipeline_diagnostics') or {}
        snapshot = next((item for item in reversed(snapshots) if item['scheduler_slot'] == slot), {})
        audits = [item for item in candidates if item['scheduler_slot'] == slot]
        ledger = next((item for item in ledgers if item['slot_key'].endswith(':' + slot)), {})
        claim = next((item for item in claims if item['scheduler_slot'] == slot), {})
        reached = bool(snapshot or audits)
        scores = []
        for audit in audits:
            gate = obj(audit.get('diagnostics_json')).get('candidate_score_gate') or {}
            scores.append({'symbol': audit['symbol'], 'A': audit.get('runtime_quant_buy_score'),
                'C': gate.get('quant_c_score'), 'GPT': audit.get('ai_buy_score'),
                'Final': audit.get('final_buy_score'), 'gpt_status': audit.get('gpt_analysis_status')})
        score_values = [item['Final'] for item in scores if item['Final'] is not None]
        raw = next(iter(rows(db, 'watchlist_snapshot_runs', 'WHERE id=?', (snapshot.get('source_run_id'),))), {})
        if not raw:
            slot_at = start.replace(hour=int(slot.split(':')[0]), minute=int(slot.split(':')[1]))
            slot_utc = slot_at.astimezone(ZoneInfo('UTC')).replace(tzinfo=None).isoformat(' ')
            raw = next(iter(rows(db, 'watchlist_snapshot_runs',
                'WHERE market=? AND started_at>=? AND completed_at<=? AND status=? ORDER BY completed_at DESC LIMIT 1',
                ('KR', lo, slot_utc, 'success'))), {})
        risk = payload.get('risk') or {}
        order = next(iter(rows(db, 'orders', 'WHERE id=? AND owner_user_id IS ?',
                              (run.get('order_id'), owner))), {})
        source = obj(order.get('request_payload'))
        simulated = bool(source.get('simulation_only')) or source.get('mode') == 'kis_user_simulation'
        snapshot_state = (trace.get('account_snapshot') or {}).get('status')
        failure = payload.get('failure_stage')
        thresholds = dict(trace.get('thresholds') or {'c_min': 65, 'gpt_min': 60, 'final_min': 65})
        profile_context = payload.get('profile_context') or {}
        calendar = payload.get('calendar_gap_risk') or profile_context.get('calendar_gap_risk') or {}
        thresholds['c_min'] = max(thresholds['c_min'], calendar.get('required_c_score') or 65)
        thresholds['final_min'] = max(thresholds['final_min'], profile_context.get('min_final_score') or 65,
                                      calendar.get('required_final_score') or 65)
        output.append({'slot': slot, 'scheduler': ledger.get('status') or claim.get('status') or 'UNKNOWN',
            'result': run.get('result') or claim.get('result') or 'UNKNOWN',
            'reason': code(run.get('reason') or claim.get('reason') or ledger.get('reason')),
            'account_snapshot': snapshot_state or ('FAILED' if failure == 'account_snapshot' else
                                  'SUCCESS' if management else 'UNKNOWN'),
            'held_positions': management.get('held_position_count'),
            'open_sell_orders': management.get('open_sell_order_count'),
            'position_management': management.get('action') or 'UNKNOWN',
            'blocked_stage': management.get('blocked_stage') or trace.get('first_blocked_stage') or failure
                             or ('position_management' if management.get('entry_blocked') else None),
            'final_stage': trace.get('final_stage') or run.get('stage'),
            'exception_type': code(payload.get('exception_type')),
            'duplicate_evidence': {key: management[key] for key in ('duplicate_check_source', 'broker_order_id_masked',
                'symbol', 'side', 'order_status', 'remaining_quantity', 'account_scope_verified') if key in management},
            'watchlist': f"{raw.get('scored_count', 'UNKNOWN')} / {raw.get('source_count', 'UNKNOWN')}",
            'profile_watchlist': snapshot.get('selected_count', 'NOT REACHED'),
            'a_top5': len(pipeline['runtime_quant_top5_symbols']) if 'runtime_quant_top5_symbols' in pipeline else 'UNKNOWN' if reached else 'NOT REACHED',
            'c_analyzed': sum(item['C'] is not None for item in scores) if scores else 'NOT CALCULATED' if reached else 'NOT REACHED',
            'c65_passed': sum(item['C'] is not None and item['C'] >= 65 for item in scores) if scores else 'UNKNOWN' if reached else 'NOT REACHED',
            'gpt_attempted': pipeline.get('gpt_attempted_count', 'UNKNOWN' if reached else 'NOT REACHED'),
            'gpt_completed': sum(item['gpt_status'] == 'completed' for item in scores) if scores else 'UNKNOWN' if reached else 'NOT REACHED',
            'final_score': max(score_values) if score_values else 'NOT CALCULATED' if reached else 'NOT REACHED',
            'risk_engine': ('APPROVED' if risk.get('risk_allowed') is True else 'BLOCKED' if risk.get('risk_allowed') is False else 'NOT REACHED'),
            'order': ('SIMULATED ' if simulated else 'BROKER ') + str(order.get('side', '')).upper() if order else 'NOT CALLED',
            'order_status': order.get('internal_status'), 'scores': scores,
            'thresholds': thresholds,
            'stage_durations_ms': trace.get('stage_durations_ms') or pipeline.get('performance') or {},
            'retry': payload.get('account_snapshot_retry') or {key: payload[key] for key in (
                'attempts', 'max_attempts', 'attempt_history', 'read_operation', 'http_status', 'msg_cd') if key in payload},
            'broker_submit_called': payload.get('broker_submit_called', False),
        })
    unresolved = rows(db, 'orders', "WHERE owner_user_id IS ? AND broker=? AND side=? AND internal_status IN "
        "('REQUESTED','SUBMITTED','ACCEPTED','PENDING','PENDING_SUBMIT','PARTIALLY_FILLED','UNKNOWN_STALE','SYNC_FAILED')",
        (owner, 'kis', 'sell'))
    return {'user': username, 'date': trading_date, 'broker': 'KIS',
            'mode': str(settings[0].get('trading_mode', 'UNKNOWN')).upper() if settings else 'UNKNOWN',
            'slots': output, 'current_unresolved_sell_orders': [
                {'local_order_id': row['id'], 'symbol': row['symbol'], 'status': row['internal_status'],
                 'created_at': row['created_at'], 'sync_error': code(row.get('sync_error'))} for row in unresolved]}


def render(report):
    lines = [f"USER: {report['user']}", f"DATE: {report['date']}", 'BROKER: KIS', f"MODE: {report['mode']}"]
    labels = [('scheduler', 'Scheduler'), ('result', 'Result'), ('account_snapshot', 'Account Snapshot'),
              ('held_positions', 'Held Positions'), ('open_sell_orders', 'Open Sell Orders'),
              ('position_management', 'Position Management'), ('blocked_stage', 'Blocked Stage'),
              ('final_stage', 'Final Stage'), ('reason', 'Reason'), ('exception_type', 'Exception Type'),
              ('watchlist', 'Watchlist'), ('profile_watchlist', 'Profile Watchlist'), ('a_top5', 'A Top 5'),
              ('c_analyzed', 'C Analyzed'), ('c65_passed', 'C65 Passed'), ('gpt_attempted', 'GPT Attempted'),
              ('gpt_completed', 'GPT Completed'), ('final_score', 'Final Score'), ('risk_engine', 'Risk Engine'),
              ('order', 'Order'), ('order_status', 'Order Status'), ('broker_submit_called', 'Broker Submit Called')]
    for slot in report['slots']:
        lines += ['', slot['slot']] + [f"{label}: {slot[key] if slot[key] is not None else 'UNKNOWN'}" for key, label in labels]
        for key in ('duplicate_evidence', 'scores', 'thresholds', 'stage_durations_ms', 'retry'):
            if slot[key]:
                lines.append(f'{key}: ' + json.dumps(slot[key], ensure_ascii=False))
    if report.get('current_unresolved_sell_orders'):
        lines += ['', 'CURRENT local evidence (not an incident-time broker snapshot):',
                  json.dumps(report['current_unresolved_sell_orders'], ensure_ascii=False)]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', required=True)
    parser.add_argument('--date', required=True)
    parser.add_argument('--database', type=Path, help='Existing SQLite file (default: configured DATABASE_URL)')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    target = args.database
    if target is None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from app.config import get_settings
        from sqlalchemy.engine import make_url
        url = make_url(get_settings().database_url)
        if url.get_backend_name() != 'sqlite' or not url.database or url.database == ':memory:':
            parser.error('An existing SQLite database is required')
        target = Path(url.database)
    with open_readonly(target) as db:
        report = diagnose(db, args.user, args.date)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report))


if __name__ == '__main__':
    main()
