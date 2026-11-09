"""Approval-bound reconciliation of legacy Admin KIS orders using broker evidence.

This route deliberately does not assert that an outbound HTTP call never happened.
It can only close a legacy orphan when complete KIS order history proves the
broker has no record of that order and the current account state is reliable.
"""

from collections import Counter
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import math
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, func, update

from app.db.models import (
    AccountBuyExecutionClaim,
    AutomationProfileBuyReservation,
    AutomationSchedulerSlot,
    KisLegacyOrderReconciliation,
    KisOrderValidationLog,
    OrderLog,
    PositionLifecycle,
    TradeRunLog,
    User,
)
from app.services.account_trading_limit_service import AccountTradingLimitService
from app.services.automation_profile_service import AutomationProfileService
from app.services.kis_legacy_order_state import LEGACY_ABSENCE_VERIFIED, legacy_audit_table_exists
from app.services.kis_order_account_scope import resolve_order_account_scope
from app.services.kis_order_reconciliation_service import (
    FIELDS,
    ReconciliationBlocked,
    fingerprint,
    timestamp,
    values,
)

KST = ZoneInfo('Asia/Seoul')
PROTOCOL = 'legacy_admin_broker_absence_v1'
REASON = 'legacy_broker_order_absence_verified'
SUBMIT_MARKERS = {
    'broker_submit_called', 'real_order_submitted', 'submit_dispatched',
    'submission_started', 'submit_attempted',
}


def _json(value):
    try:
        parsed = json.loads(value or '{}')
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(',', ':')).encode()
    return sha256(encoded).hexdigest()


def _contains_submit_marker(value):
    if isinstance(value, dict):
        return any((key in SUBMIT_MARKERS and item is True) or _contains_submit_marker(item)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_submit_marker(item) for item in value)
    return False


def _finite_nonnegative(row, key):
    try:
        result = float(row[key])
    except (KeyError, TypeError, ValueError):
        raise ReconciliationBlocked('history_row_unverified') from None
    if not math.isfinite(result) or result < 0:
        raise ReconciliationBlocked('history_row_unverified')
    return result


def _safe_history_summary(rows):
    counts = Counter()
    for row in rows:
        quantity = _finite_nonnegative(row, 'ord_qty')
        filled = _finite_nonnegative(row, 'tot_ccld_qty')
        remaining = _finite_nonnegative(row, 'rmn_qty')
        rejected = _finite_nonnegative(row, 'rjct_qty')
        side = 'buy' if row['sll_buy_dvsn_cd'] == '02' else 'sell'
        counts[side] += 1
        if quantity > 0 and filled >= quantity:
            counts['filled'] += 1
        if remaining > 0:
            counts['unfilled'] += 1
        if rejected > 0:
            counts['rejected'] += 1
        if str(row.get('cncl_yn') or '').upper() == 'Y':
            counts['canceled'] += 1
    return {'order_count': len(rows), 'status_counts': dict(sorted(counts.items()))}


def _profile_scope(db, order, admin_user_id, now):
    schedule = AutomationProfileService().selected_profile_schedule(db, now=now.astimezone(KST))
    profile = (schedule or {}).get('profile')
    if not isinstance(profile, dict):
        raise ReconciliationBlocked('operating_profile_unavailable')
    if (profile.get('owner_user_id') not in {None, admin_user_id}
            or str(profile.get('provider') or '').lower() != 'kis'
            or str(profile.get('market') or '').upper() != 'KR'
            or profile.get('enabled') is not True
            or profile.get('status') not in {'active', 'scheduled'}):
        raise ReconciliationBlocked('operating_profile_scope_mismatch')
    request = _json(order.request_payload)
    order_key = order.profile_key or request.get('automation_profile_key') or request.get('profile_key')
    if (order.profile_id is not None and order.profile_id != profile.get('id')) or (
        order_key and str(order_key).strip().lower() != str(profile.get('profile_key') or '').strip().lower()
    ):
        raise ReconciliationBlocked('order_profile_mismatch')
    if not order_key:
        raise ReconciliationBlocked('order_profile_unverified')
    return {
        'id': profile['id'],
        'owner_user_id': profile.get('owner_user_id'),
        'profile_key': profile.get('profile_key'),
        'provider': profile.get('provider'),
        'market': profile.get('market'),
        'status': profile.get('status'),
        'enabled': profile.get('enabled'),
    }


def _validate_open_orders(rows):
    if not isinstance(rows, list):
        raise ReconciliationBlocked('open_orders_unavailable')
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            raise ReconciliationBlocked('open_orders_unavailable')
        symbol = str(row.get('symbol') or '').strip()
        order_id = str(row.get('order_id') or row.get('broker_order_id') or '').strip()
        side = str(row.get('side') or '').strip().lower()
        try:
            remaining = float(row.get('unfilled_qty', row.get('remaining_quantity')))
        except (TypeError, ValueError):
            raise ReconciliationBlocked('open_orders_unavailable') from None
        if (not symbol or not order_id or side not in {'buy', 'sell'}
                or not math.isfinite(remaining) or remaining <= 0):
            raise ReconciliationBlocked('open_orders_unavailable')
        normalized.append({'order_id': order_id, 'symbol': symbol, 'side': side,
                           'remaining_qty': remaining})
    return normalized


def _validate_positions(rows):
    if not isinstance(rows, list):
        raise ReconciliationBlocked('positions_unavailable')
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            raise ReconciliationBlocked('positions_unavailable')
        symbol = str(row.get('symbol') or row.get('pdno') or '').strip()
        quantity = row.get('qty', row.get('quantity', row.get('hldg_qty')))
        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            raise ReconciliationBlocked('positions_unavailable') from None
        if not symbol or not math.isfinite(quantity) or quantity <= 0:
            raise ReconciliationBlocked('positions_unavailable')
        normalized.append({'symbol': symbol, 'qty': quantity})
    return normalized


def read_legacy_admin_broker_evidence(db, order, now, *, client):
    """Read complete day history (all orders/exchanges), current orders and positions."""
    from app.brokers.kis_account_execution_reader import ExecutionReadBudget

    scope = resolve_order_account_scope(db, order=order, client=client, require_enabled=False)
    if not scope.account.legacy_admin or scope.identity[0] != 'live':
        raise ReconciliationBlocked('legacy_admin_live_account_required')
    profile = _profile_scope(db, order, scope.account.owner_user_id, now)
    day = timestamp(order.created_at).astimezone(KST).date()
    budget = ExecutionReadBudget(max_calls=20, timeout_seconds=60)
    current = now.astimezone(KST).date()
    month = current.year * 12 + current.month - 1 - 3
    archive_boundary = current.replace(year=month // 12, month=month % 12 + 1, day=1)
    rows, cursors = [], set()
    continuation = fk = nk = ''
    page_count = 0
    for _ in range(20):
        try:
            page = client.inquire_account_executions_page(
                budget=budget, start_date=day, end_date=day, older=day < archive_boundary,
                execution_filter='00', continuation=continuation, fk=fk, nk=nk,
            )
        except Exception as exc:
            status = getattr(exc, 'status', 'error')
            code = getattr(exc, 'code', 'broker_read_failed')
            if status not in {'error', 'incomplete', 'authentication_failed', 'not_connected'}:
                status = 'error'
            if code not in {'broker_read_failed', 'read_deadline_exceeded', 'call_budget_exceeded',
                            'authentication_failed', 'account_not_configured', 'invalid_response_shape',
                            'invalid_continuation_response', 'response_scope_mismatch'}:
                code = 'broker_read_failed'
            raise ReconciliationBlocked(f'kis_history_{status}:{code}') from None
        page_count += 1
        page_rows = page.get('orders')
        if not isinstance(page_rows, list) or any(not isinstance(row, dict) for row in page_rows):
            raise ReconciliationBlocked('history_incomplete')
        rows.extend(page_rows)
        flag = str(page.get('tr_cont') or '').upper()
        if flag in {'', 'D', 'E'}:
            break
        if flag not in {'F', 'M'}:
            raise ReconciliationBlocked('history_incomplete')
        next_cursors = (str(page.get('fk') or ''), str(page.get('nk') or ''))
        if not all(next_cursors) or next_cursors in cursors:
            raise ReconciliationBlocked('history_incomplete')
        cursors.add(next_cursors)
        fk, nk, continuation = next_cursors[0], next_cursors[1], 'N'
    else:
        raise ReconciliationBlocked('history_incomplete')

    for row in rows:
        if (not str(row.get('pdno') or '').strip()
                or str(row.get('ord_dt') or '') != day.strftime('%Y%m%d')
                or not str(row.get('odno') or '').strip()
                or row.get('sll_buy_dvsn_cd') not in {'01', '02'}
                or not str(row.get('cncl_yn') or '').strip()):
            raise ReconciliationBlocked('history_row_unverified')
        for key in ('ord_qty', 'tot_ccld_qty', 'rmn_qty', 'rjct_qty'):
            _finite_nonnegative(row, key)
    try:
        raw_open_orders = client.list_open_orders()
    except Exception:
        raise ReconciliationBlocked('open_orders_unavailable') from None
    try:
        raw_positions = client.list_positions()
    except Exception:
        raise ReconciliationBlocked('positions_unavailable') from None
    open_orders = _validate_open_orders(raw_open_orders)
    positions = _validate_positions(raw_positions)
    summary = _safe_history_summary(rows)
    return {
        'provider': 'kis', 'owner_user_id': None,
        'broker_account_id': scope.account.broker_account_id,
        'environment': 'live', 'checked_at': now.isoformat(),
        'complete': True, 'execution_filter': '00', 'exchange_scope': 'ALL',
        'history_date': day.isoformat(), 'history_page_count': page_count,
        'history_orders': rows, 'history_summary': summary,
        'open_orders': open_orders, 'positions': positions,
        'open_orders_reliable': True, 'positions_reliable': True,
        'selected_profile': profile,
    }


def _reservation_rows(db, order_id):
    rows = db.query(AutomationProfileBuyReservation).filter_by(order_id=order_id).order_by(
        AutomationProfileBuyReservation.id.asc()).all()
    values_by_row = [{column.name: getattr(row, column.name) for column in row.__table__.columns}
                     for row in rows]
    return rows, values_by_row


def _nearby_scheduler_trace(db, order, profile_id):
    created = order.created_at
    rows = db.query(AutomationSchedulerSlot).filter(
        AutomationSchedulerSlot.account_key == 'admin',
        AutomationSchedulerSlot.provider == 'kis',
        AutomationSchedulerSlot.profile_id == profile_id,
        AutomationSchedulerSlot.scheduled_at >= created - timedelta(minutes=10),
        AutomationSchedulerSlot.scheduled_at <= created + timedelta(minutes=10),
    ).order_by(AutomationSchedulerSlot.id.asc()).all()
    result = []
    for row in rows:
        payload = _json(row.result_json)
        if _contains_submit_marker(payload):
            raise ReconciliationBlocked('broker_submission_marker_present')
        result.append({
            'id': row.id, 'slot_key': row.slot_key, 'status': row.status,
            'reason': row.reason,
            'attempt': payload.get('attempt'), 'attempt_status': payload.get('status'),
            'attempt_result': payload.get('result'), 'attempt_reason': payload.get('reason'),
            'failure_stage': payload.get('failure_stage'),
            'final_failure_stage': payload.get('final_failure_stage'),
            'exception_type': payload.get('exception_type'),
            'broker_submit_called': payload.get('broker_submit_called'),
            'real_order_submitted': payload.get('real_order_submitted'),
        })
    return rows, result


def _stable_plan(plan):
    return {key: value for key, value in plan.items() if key not in {'checked_at', 'approval_digest'}}


def _approval_digest(plan):
    return _digest(_stable_plan(plan))


class KisLegacyAdminOrderReconciliationService:
    """Manual review and approval flow for broker-verified legacy orphan orders."""

    def __init__(self, evidence_reader, *, now_provider=None):
        self.read_evidence = evidence_reader
        self.now = now_provider or (lambda: datetime.now(UTC))

    @staticmethod
    def _admin(db, user_id):
        actor = db.get(User, user_id)
        if actor is None or actor.role != 'admin' or not actor.enabled:
            raise ReconciliationBlocked('admin_approval_required')
        return actor

    def propose(self, db, *, order_id, admin_user_id, claim_held=False):
        self._admin(db, admin_user_id)
        order = db.query(OrderLog).filter_by(id=order_id).populate_existing().one_or_none()
        if (order is None or order.owner_user_id is not None or order.broker != 'kis'
                or str(order.market or '').upper() != 'KR' or order.side != 'buy'):
            raise ReconciliationBlocked('legacy_admin_buy_scope_required')
        account = AccountTradingLimitService.resolve_account(db, require_enabled=False)
        if account.owner_user_id != admin_user_id or not account.legacy_admin:
            raise ReconciliationBlocked('account_scope_mismatch')
        if (legacy_audit_table_exists(db)
                and db.query(KisLegacyOrderReconciliation.id).filter_by(order_id=order.id).first()):
            raise ReconciliationBlocked('legacy_reconciliation_already_applied')
        if not claim_held and db.get(AccountBuyExecutionClaim, account.broker_account_id) is not None:
            raise ReconciliationBlocked('account_buy_in_progress')
        if (order.internal_status != 'REQUESTED' or order.kis_odno or order.broker_order_id
                or order.submitted_at is not None or order.filled_at is not None
                or order.filled_qty not in (None, 0)):
            raise ReconciliationBlocked('broker_submission_possible')
        if db.query(PositionLifecycle.id).filter_by(entry_order_id=order.id).first():
            raise ReconciliationBlocked('position_evidence_present')
        before_fingerprint = fingerprint(order)
        local = self.now()
        profile = _profile_scope(db, order, admin_user_id, local)
        order_created = timestamp(order.created_at)
        local_window_start = order_created.replace(tzinfo=None) - timedelta(minutes=5)
        local_window_end = order_created.replace(tzinfo=None) + timedelta(minutes=5)
        logs = db.query(TradeRunLog).filter_by(order_id=order.id).order_by(TradeRunLog.id.asc()).all()
        nearby_runs = db.query(TradeRunLog).filter(
            TradeRunLog.owner_user_id.is_(None),
            TradeRunLog.symbol == order.symbol,
            TradeRunLog.mode == 'automation_scheduler_profile_analysis',
            TradeRunLog.created_at >= local_window_start,
            TradeRunLog.created_at <= local_window_end,
        ).order_by(TradeRunLog.id.asc()).all()
        nearby_runs = [row for row in nearby_runs if (
            _json(row.request_payload).get('automation_profile_key') == profile['profile_key']
            or _json(row.request_payload).get('profile_key') == profile['profile_key'])]
        payloads = [order.request_payload, order.response_payload, order.last_sync_payload]
        payloads.extend(value for row in logs for value in (row.request_payload, row.response_payload))
        payloads.extend(value for row in nearby_runs for value in (row.request_payload, row.response_payload))
        if any(_contains_submit_marker(_json(value)) for value in payloads):
            raise ReconciliationBlocked('broker_submission_marker_present')

        validations = db.query(KisOrderValidationLog).filter(
            KisOrderValidationLog.market == 'KR', KisOrderValidationLog.symbol == order.symbol,
            KisOrderValidationLog.side == 'buy', KisOrderValidationLog.qty == int(order.qty or 0),
        ).all()
        related_validations = [row for row in validations
            if abs((timestamp(row.created_at) - order_created).total_seconds()) <= 300]
        scheduler_rows, scheduler_trace = _nearby_scheduler_trace(db, order, profile['id'])
        evidence = self.read_evidence(db, order, local)
        if (evidence.get('owner_user_id') is not None
                or evidence.get('broker_account_id') != account.broker_account_id
                or evidence.get('environment') != 'live' or evidence.get('provider') != 'kis'
                or evidence.get('selected_profile') != profile):
            raise ReconciliationBlocked('evidence_scope_mismatch')
        try:
            age = (local - timestamp(evidence['checked_at'])).total_seconds()
        except (KeyError, TypeError, ValueError):
            raise ReconciliationBlocked('evidence_timestamp_invalid') from None
        if not -2 <= age <= 60:
            raise ReconciliationBlocked('evidence_stale')
        day = order_created.astimezone(KST).date().isoformat()
        if (evidence.get('complete') is not True or evidence.get('execution_filter') != '00'
                or evidence.get('exchange_scope') != 'ALL' or evidence.get('history_date') != day
                or not isinstance(evidence.get('history_page_count'), int)
                or evidence['history_page_count'] < 1
                or evidence.get('positions_reliable') is not True
                or evidence.get('open_orders_reliable') is not True):
            raise ReconciliationBlocked('evidence_incomplete')
        history = evidence.get('history_orders')
        open_orders = evidence.get('open_orders')
        positions = evidence.get('positions')
        if not isinstance(history, list) or not isinstance(open_orders, list) or not isinstance(positions, list):
            raise ReconciliationBlocked('evidence_incomplete')
        symbol = str(order.symbol).strip()
        if any(str(row.get('pdno') or '').strip() == symbol for row in history):
            raise ReconciliationBlocked('broker_submission_possible')
        if any(str(row.get('symbol') or '').strip() == symbol for row in open_orders):
            raise ReconciliationBlocked('broker_submission_possible')
        if any(str(row.get('symbol') or row.get('pdno') or '').strip() == symbol for row in positions):
            raise ReconciliationBlocked('broker_submission_possible')

        reservations, reservation_values = _reservation_rows(db, order.id)
        if any(row.status not in {'reserved', 'blocked'} for row in reservations):
            raise ReconciliationBlocked('reservation_submission_possible')
        related_trace = {
            'order_linked_trade_run_count': len(logs),
            'nearby_profile_analysis_count': len(nearby_runs),
            'nearby_profile_analysis_records': [{
                'id': row.id, 'mode': row.mode, 'stage': row.stage,
                'result': row.result, 'reason': row.reason,
                'broker_submit_called': _json(row.request_payload).get('broker_submit_called'),
                'real_order_submitted': _json(row.request_payload).get('real_order_submitted'),
                'validation_called': _json(row.request_payload).get('validation_called'),
                'submission_eligible': _json(row.response_payload).get('submission_eligible'),
            } for row in nearby_runs],
            'nearby_scheduler_slot_count': len(scheduler_rows),
            'nearby_scheduler_slots': scheduler_trace,
            'nearby_validation_count': len(related_validations),
            'nearby_validated_true_count': sum(bool(row.validated_for_submission) for row in related_validations),
            'nearby_validation_records': [{
                'id': row.id, 'validated_for_submission': bool(row.validated_for_submission),
                'created_at': str(row.created_at),
                'request_digest': _digest(_json(row.request_payload)),
                'response_digest': _digest(_json(row.response_payload)),
            } for row in related_validations],
            'explicit_submit_marker_present': False,
            'broker_history_has_order': False,
        }
        evidence_digest = _digest({
            'history_orders': evidence['history_orders'],
            'history_date': day,
            'history_filter': evidence['execution_filter'],
            'exchange_scope': evidence['exchange_scope'],
            'open_orders': evidence['open_orders'],
            'positions': evidence['positions'],
            'selected_profile': profile,
            'account': account.broker_account_id,
            'local_trace': related_trace,
        })
        safe_history = _safe_history_summary(history)
        plan = {
            'protocol': PROTOCOL,
            'order_id': order.id,
            'order': {
                'owner_user_id': None, 'policy_user_id': account.owner_user_id,
                'broker_account_id': account.broker_account_id, 'broker': order.broker,
                'market': order.market, 'symbol': order.symbol, 'side': order.side,
                'qty': order.qty, 'internal_status': order.internal_status,
                'created_at': str(order.created_at), 'kis_odno_present': bool(order.kis_odno),
                'broker_order_id_present': bool(order.broker_order_id),
                'submitted_at': str(order.submitted_at) if order.submitted_at else None,
                'filled_qty': order.filled_qty,
            },
            'selected_profile': profile,
            'original_fingerprint': before_fingerprint,
            'reservation_fingerprint': _digest(reservation_values),
            'reservations': [{
                'id': row.id, 'order_id': row.order_id, 'symbol': row.symbol,
                'trade_date_kst': row.trade_date_kst, 'scheduler_slot_kst': row.scheduler_slot_kst,
                'status': row.status,
            } for row in reservations],
            'execution_trace': related_trace,
            'broker_evidence': {
                'complete': True, 'history_date': day, 'execution_filter': '00',
                'exchange_scope': 'ALL', 'history_page_count': evidence['history_page_count'],
                'history': safe_history, 'target_symbol_matches': 0,
                'current_open_order_count': len(open_orders),
                'target_symbol_open_order_matches': 0,
                'current_position_count': len(positions),
                'target_symbol_position_matches': 0,
                'positions_reliable': True, 'open_orders_reliable': True,
            },
            'evidence_digest': evidence_digest,
            'target_status': LEGACY_ABSENCE_VERIFIED,
            'broker_status_assertion': 'complete_history_contains_no_order_record',
            'historical_submit_call_state': 'not_provable_from_legacy_logs',
            'not_submitted_asserted': False,
            'requires_admin_approval': True,
            'new_broker_mutation_calls': 0,
            'checked_at': local.isoformat(),
        }
        plan['approval_digest'] = _approval_digest(plan)
        return plan

    def apply(self, db, *, plan, admin_user_id, approval_digest, approval_reference):
        self._admin(db, admin_user_id)
        if not legacy_audit_table_exists(db):
            raise ReconciliationBlocked('legacy_reconciliation_schema_missing')
        if (not approval_reference or len(str(approval_reference).strip()) > 160
                or approval_digest != _approval_digest(plan)
                or approval_digest != plan.get('approval_digest')):
            raise ReconciliationBlocked('explicit_plan_approval_required')
        with AccountTradingLimitService().buy_execution_claim(db, allow_disabled=True):
            try:
                fresh = self.propose(db, order_id=plan['order_id'], admin_user_id=admin_user_id,
                                     claim_held=True)
                if _approval_digest(fresh) != approval_digest:
                    raise ReconciliationBlocked('reconciliation_plan_stale')
                order = db.query(OrderLog).filter_by(id=plan['order_id']).populate_existing().one()
                before = values(order)
                reservations, reservation_values = _reservation_rows(db, order.id)
                if (_digest(reservation_values) != plan['reservation_fingerprint']
                        or fingerprint(order) != plan['original_fingerprint']):
                    raise ReconciliationBlocked('reconciliation_plan_stale')
                if db.query(KisLegacyOrderReconciliation.id).filter_by(order_id=order.id).first():
                    raise ReconciliationBlocked('legacy_reconciliation_already_applied')
                predicates = []
                for field in FIELDS:
                    column, value = getattr(OrderLog, field), before[field]
                    predicates.append(column.is_(None) if value is None else
                        func.julianday(column) == func.julianday(value)
                        if isinstance(column.type, DateTime) else column == value)
                changed = db.execute(update(OrderLog).where(*predicates).values(
                    internal_status=LEGACY_ABSENCE_VERIFIED,
                    error_message=REASON,
                    last_sync_payload=json.dumps({**_json(order.last_sync_payload),
                        'legacy_broker_absence_reconciliation': {
                            'protocol': PROTOCOL, 'evidence_digest': plan['evidence_digest'],
                            'approval_digest': approval_digest, 'approved_by': admin_user_id,
                        }}, default=str),
                ).execution_options(synchronize_session=False))
                if changed.rowcount != 1:
                    raise ReconciliationBlocked('reconciliation_plan_stale')
                for snapshot in reservation_values:
                    predicates = []
                    for field, value in snapshot.items():
                        column = getattr(AutomationProfileBuyReservation, field)
                        predicates.append(column.is_(None) if value is None else
                            func.julianday(column) == func.julianday(value)
                            if isinstance(column.type, DateTime) else column == value)
                    changed = db.execute(update(AutomationProfileBuyReservation).where(*predicates).values(
                        status='blocked', block_reason=REASON,
                    ).execution_options(synchronize_session=False))
                    if changed.rowcount != 1:
                        raise ReconciliationBlocked('reconciliation_plan_stale')
                db.flush()
                db.refresh(order)
                after = values(order)
                audit = KisLegacyOrderReconciliation(
                    order_id=order.id, owner_user_id=None, policy_user_id=admin_user_id,
                    broker_account_id=plan['order']['broker_account_id'],
                    original_fingerprint=plan['original_fingerprint'],
                    terminal_fingerprint=fingerprint(order),
                    reservation_fingerprint=plan['reservation_fingerprint'],
                    evidence_digest=plan['evidence_digest'], approval_digest=approval_digest,
                    approved_by_user_id=admin_user_id,
                    approval_reference=str(approval_reference).strip(),
                    before_state_json=json.dumps(before, default=str),
                    after_state_json=json.dumps(after, default=str),
                    evidence_summary_json=json.dumps(plan['broker_evidence'], default=str),
                )
                db.add(audit)
                db.flush()
                run = TradeRunLog(
                    owner_user_id=None, run_key='legacy-order-repair:' + uuid4().hex,
                    trigger_source='admin_approved_legacy_reconciliation', mode='kis_legacy_reconciliation',
                    symbol=order.symbol, order_id=order.id, stage='done', result='reconciled', reason=REASON,
                    request_payload=json.dumps({'plan': plan, 'admin_user_id': admin_user_id,
                        'approval_reference': str(approval_reference).strip()}, default=str),
                    response_payload=json.dumps({'before': before, 'after': after,
                        'audit_id': audit.id, 'not_submitted_asserted': False,
                        'historical_submit_call_state': 'not_provable_from_legacy_logs',
                        'new_broker_mutation_calls': 0}, default=str),
                )
                db.add(run)
                db.commit()
                return {'order_id': order.id, 'internal_status': order.internal_status,
                        'audit_id': audit.id, 'trade_run_id': run.id,
                        'new_broker_mutation_calls': 0,
                        'not_submitted_asserted': False}
            except Exception:
                db.rollback()
                raise
