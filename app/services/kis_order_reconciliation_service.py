"""Explicitly approved, evidence-bound repair of a single historical KIS SELL.

No scheduler invokes this service and it never submits/cancels broker orders.
An empty current account or missing history is never terminal evidence.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
from zoneinfo import ZoneInfo

from sqlalchemy import update, func

from app.db.models import OrderLog, TradeRunLog
from app.services.kis_snapshot_order_state import broker_order_block

FIELDS = ('id', 'owner_user_id', 'broker', 'market', 'side', 'symbol', 'qty', 'requested_qty',
    'filled_qty', 'remaining_qty', 'internal_status', 'broker_order_id', 'kis_odno',
    'submitted_at', 'created_at', 'last_synced_at', 'request_payload', 'response_payload', 'last_sync_payload',
    'broker_status', 'broker_order_status', 'avg_fill_price', 'filled_avg_price', 'filled_at',
    'sync_error', 'error_message', 'profile_id', 'profile_key', 'updated_at')


class ReconciliationBlocked(ValueError):
    pass


def values(order):
    return {key: order.get(key) if isinstance(order, dict) else getattr(order, key) for key in FIELDS}


def fingerprint(order):
    return hashlib.sha256(json.dumps(values(order), sort_keys=True, default=str).encode()).hexdigest()


def timestamp(value):
    value = datetime.fromisoformat(str(value).replace('Z', '+00:00')) if not isinstance(value, datetime) else value
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def number(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ReconciliationBlocked('broker_quantity_invalid') from None
    if not math.isfinite(value) or value < 0:
        raise ReconciliationBlocked('broker_quantity_invalid')
    return value


def propose_reconciliation(order, *, history, snapshot, now):
    row = values(order)
    owner = row['owner_user_id']
    if owner is None or row['broker'] != 'kis' or row['market'] != 'KR' or row['side'] != 'sell':
        raise ReconciliationBlocked('order_scope_mismatch')
    if row['internal_status'] not in {'UNKNOWN_STALE', 'SYNC_FAILED', 'SUBMITTED', 'ACCEPTED', 'PENDING', 'PARTIALLY_FILLED'}:
        raise ReconciliationBlocked('order_not_unresolved')
    for evidence in (history, snapshot):
        if (evidence.get('owner_user_id') != owner or evidence.get('provider') != 'kis'
                or evidence.get('environment') != 'live' or evidence.get('broker_account_id') != f'user:{owner}:kis:KR'):
            raise ReconciliationBlocked('evidence_scope_mismatch')
        try:
            age = (now - timestamp(evidence.get('checked_at'))).total_seconds()
        except (ValueError, TypeError):
            raise ReconciliationBlocked('evidence_timestamp_invalid') from None
        if not -2 <= age <= 300:
            raise ReconciliationBlocked('evidence_stale')
    if history.get('complete') is not True or not isinstance(history.get('orders'), list):
        raise ReconciliationBlocked('history_incomplete')
    if snapshot.get('positions_reliable') is not True or snapshot.get('open_orders_reliable') is not True:
        raise ReconciliationBlocked('account_snapshot_unreliable')
    order_block = broker_order_block(snapshot)
    if order_block:
        raise ReconciliationBlocked(order_block['reason'])
    order_no = str(row['kis_odno'] or row['broker_order_id'] or '').lstrip('0')
    if not order_no:
        raise ReconciliationBlocked('order_number_missing')
    matches = [item for item in history['orders'] if isinstance(item, dict)
        and str(item.get('odno') or '').lstrip('0') == order_no]
    if len(matches) != 1:
        raise ReconciliationBlocked('broker_order_not_uniquely_verified')
    matched = matches[0]
    if (matched.get('pdno') != row['symbol'] or matched.get('sll_buy_dvsn_cd') != '01'
            or str(matched.get('ord_dt')) != timestamp(row['submitted_at'] or row['created_at']).astimezone(
                ZoneInfo('Asia/Seoul')).strftime('%Y%m%d')):
        raise ReconciliationBlocked('broker_order_identity_mismatch')
    requested = number(row['requested_qty'] if row['requested_qty'] is not None else row['qty'])
    quantity, filled, remaining = (number(matched.get(key)) for key in ('ord_qty', 'tot_ccld_qty', 'rmn_qty'))
    if requested <= 0 or quantity != requested or filled > quantity or filled + remaining > quantity:
        raise ReconciliationBlocked('broker_quantity_mismatch')
    price = None
    if remaining == 0 and filled == quantity:
        target = 'FILLED'
        price = number(matched.get('avg_prvs'))
        if price <= 0:
            raise ReconciliationBlocked('broker_fill_price_missing')
    elif remaining == 0 and str(matched.get('cncl_yn')).upper() == 'Y':
        target = 'CANCELED'
    elif remaining == 0 and number(matched.get('rjct_qty') or 0) == quantity - filled and filled < quantity:
        target = 'REJECTED'
    else:
        raise ReconciliationBlocked('broker_order_not_terminal')
    if filled and price is None:
        price = number(matched.get('avg_prvs'))
        if price <= 0:
            raise ReconciliationBlocked('broker_fill_price_missing')
    safe_evidence = {key: matched.get(key) for key in ('ord_dt', 'ord_tmd', 'pdno', 'sll_buy_dvsn_cd',
        'ord_qty', 'tot_ccld_qty', 'rmn_qty', 'rjct_qty', 'cncl_yn', 'avg_prvs')}
    return {'order_id': row['id'], 'owner_user_id': owner, 'expected_fingerprint': fingerprint(row),
        'from_status': row['internal_status'], 'to_status': target, 'filled_qty': filled,
        'remaining_qty': remaining, 'avg_fill_price': price,
        'broker_order_id_masked': '***' + order_no[-4:], 'verified_at': now.isoformat(),
        'history': safe_evidence, 'history_complete': True, 'requires_user_approval': True,
        'original_submission_payloads_preserved': True, 'broker_submit_called': False}


def apply_verified_reconciliation(db, plan, *, approval_reference, history, snapshot, now):
    """Caller must obtain explicit user approval and re-read broker evidence first."""
    if not isinstance(approval_reference, str) or not approval_reference.strip():
        raise ReconciliationBlocked('explicit_user_approval_required')
    order = db.get(OrderLog, plan['order_id'])
    if order is None or order.owner_user_id != plan['owner_user_id']:
        raise ReconciliationBlocked('order_scope_mismatch')
    verified = propose_reconciliation(order, history=history, snapshot=snapshot, now=now)
    if verified['expected_fingerprint'] != plan['expected_fingerprint'] or any(
            verified[key] != plan[key] for key in ('to_status', 'filled_qty', 'remaining_qty', 'avg_fill_price')):
        raise ReconciliationBlocked('reconciliation_plan_stale')
    before = values(order)
    key = 'kis-order-reconciliation:' + plan['expected_fingerprint']
    existing = db.query(TradeRunLog).filter_by(owner_user_id=order.owner_user_id, run_key=key).one_or_none()
    if existing:
        raise ReconciliationBlocked('reconciliation_already_recorded')
    try:
        old_sync = json.loads(order.last_sync_payload or '{}')
        old_sync = old_sync if isinstance(old_sync, dict) else {'original_payload': old_sync}
    except (TypeError, ValueError):
        old_sync = {'original_payload': order.last_sync_payload}
    new_sync = {**old_sync, 'approved_reconciliation': {**verified, 'audit_run_key': key,
        'approval_reference': approval_reference}}
    updates = {'internal_status': verified['to_status'], 'broker_status': verified['to_status'].lower(),
        'broker_order_status': verified['to_status'].lower(), 'filled_qty': verified['filled_qty'],
        'remaining_qty': verified['remaining_qty'], 'avg_fill_price': verified['avg_fill_price'],
        'filled_avg_price': verified['avg_fill_price'], 'sync_error': None, 'error_message': None,
        'last_synced_at': now.astimezone(timezone.utc), 'last_sync_payload': json.dumps(new_sync, ensure_ascii=False)}
    # Do not invent a fill timestamp from an order timestamp or today's query.
    # Existing submitted_at keeps the historical trade in its original day.
    conditions = [
        getattr(OrderLog, field).is_(None) if value is None else
        func.julianday(getattr(OrderLog, field)) == func.julianday(value) if isinstance(value, datetime) else
        getattr(OrderLog, field) == value
        for field, value in before.items()]
    result = db.execute(update(OrderLog).where(*conditions).values(**updates).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise ReconciliationBlocked('reconciliation_plan_stale')
    audit = TradeRunLog(owner_user_id=order.owner_user_id, run_key=key,
        trigger_source='approved_order_reconciliation', mode='kis_order_reconciliation', symbol=order.symbol,
        stage='done', result='reconciled', reason='broker_terminal_order_verified', order_id=order.id,
        request_payload=json.dumps({'approval_reference': approval_reference, 'plan': plan}, ensure_ascii=False),
        response_payload=json.dumps({'before': {key: before[key] for key in (
                'internal_status', 'broker_status', 'broker_order_status', 'filled_qty', 'remaining_qty',
                'avg_fill_price', 'filled_avg_price', 'sync_error', 'error_message', 'last_synced_at')},
            'after': {key: updates[key] for key in ('internal_status', 'filled_qty', 'remaining_qty')},
            'evidence': verified, 'broker_submit_called': False, 'real_order_submitted': False}, ensure_ascii=False, default=str))
    db.add(audit)
    db.commit()
    db.refresh(order)
    return {'order_id': order.id, 'audit_id': audit.id, 'internal_status': order.internal_status,
            'broker_submit_called': False, 'real_order_submitted': False}
