"""Operator-approved repair of a proven pre-dispatch legacy admin BUY.

No automatic caller and no broker mutation capability. Negative broker history
is corroboration only: a durable, order-fingerprinted pre-submit abort is also
mandatory. Older orders without that positive evidence remain unresolved.
"""
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, func, update

from app.db.models import (
    AccountBuyExecutionClaim, AutomationProfileBuyReservation, OrderLog,
    KisOrderSubmissionEvidence, PositionLifecycle, TradeRunLog, User,
)
from app.services.account_trading_limit_service import AccountTradingLimitService
from app.services.kis_order_reconciliation_service import (
    FIELDS, ReconciliationBlocked, fingerprint, timestamp, values,
)

PROOF_MODE = 'kis_pre_submit_abort'
REASON = 'approved_pre_submit_reconciliation'
TARGET = 'REJECTED_BY_SAFETY_GATE'
KST = ZoneInfo('Asia/Seoul')


def obj(value):
    try:
        result = json.loads(value or '{}')
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def record_pre_submit_abort(db, order, reason):
    """Called only from the execution core's pre-submit rejection branch.

    Commit proof before the terminal transition so a process dying between the
    two commits leaves a verifiable REQUESTED order, never an inferred absence.
    No proof is generated for a dispatch-ambiguous UNKNOWN_STALE order.
    """
    if order.side != 'buy' or order.internal_status != 'REQUESTED':
        return
    if obj(order.request_payload).get('dispatch_protocol') != 'durable_unknown_before_submit_v1':
        return
    db.flush()
    db.refresh(order)
    db.add(KisOrderSubmissionEvidence(owner_user_id=order.owner_user_id,
        order_id=order.id, order_fingerprint=fingerprint(order),
        kind='aborted_before_broker_call', source='execution_core',
        protocol='durable_unknown_before_submit_v1', reason=str(reason)))
    db.commit()


class KisUnsubmittedOrderReconciliationService:
    def __init__(self, evidence_reader, *, now_provider=None):
        # This is a trusted server-side GET adapter, never client-supplied JSON.
        self.read_evidence = evidence_reader
        self.now = now_provider or (lambda: datetime.now(UTC))

    @staticmethod
    def _admin(db, admin_user_id):
        actor = db.get(User, admin_user_id)
        if actor is None or actor.role != 'admin' or not actor.enabled:
            raise ReconciliationBlocked('admin_approval_required')
        return actor

    def propose(self, db, *, order_id, admin_user_id, claim_held=False):
        self._admin(db, admin_user_id)
        order = db.query(OrderLog).filter_by(id=order_id).populate_existing().one_or_none()
        if (order is None or order.owner_user_id is not None or order.broker != 'kis'
                or order.market != 'KR' or order.side != 'buy'):
            raise ReconciliationBlocked('legacy_admin_buy_scope_required')
        account = AccountTradingLimitService.resolve_account(db, require_enabled=False)
        if account.owner_user_id != admin_user_id or not account.legacy_admin:
            raise ReconciliationBlocked('account_scope_mismatch')
        if not claim_held and db.get(AccountBuyExecutionClaim, account.broker_account_id) is not None:
            raise ReconciliationBlocked('account_buy_in_progress')
        if (order.internal_status != 'REQUESTED' or order.kis_odno or order.broker_order_id
                or order.submitted_at is not None or order.filled_at is not None
                or order.filled_qty not in (None, 0)):
            raise ReconciliationBlocked('broker_submission_possible')
        if db.query(PositionLifecycle.id).filter_by(entry_order_id=order.id).first():
            raise ReconciliationBlocked('position_evidence_present')
        if obj(order.request_payload).get('dispatch_protocol') != 'durable_unknown_before_submit_v1':
            raise ReconciliationBlocked('positive_pre_submit_evidence_missing')
        before = fingerprint(order)
        logs = db.query(TradeRunLog).filter_by(order_id=order.id).all()
        proof = db.query(KisOrderSubmissionEvidence).filter_by(
            order_id=order.id, owner_user_id=None, order_fingerprint=before,
            kind='aborted_before_broker_call', source='execution_core',
            protocol='durable_unknown_before_submit_v1').order_by(KisOrderSubmissionEvidence.id.asc()).first()
        if proof is None:
            raise ReconciliationBlocked('positive_pre_submit_evidence_missing')
        def submission_marker(value):
            if isinstance(value, dict):
                return any((key in {'broker_submit_called', 'real_order_submitted', 'submit_dispatched',
                    'submission_started', 'submit_attempted'} and item is True)
                    or submission_marker(item) for key, item in value.items())
            return isinstance(value, list) and any(submission_marker(item) for item in value)
        if any(submission_marker(obj(value)) for value in [order.request_payload,
            order.response_payload, order.last_sync_payload,
            *(row.response_payload for row in logs), *(row.request_payload for row in logs)]):
            raise ReconciliationBlocked('broker_submission_possible')
        evidence = self.read_evidence(db, order, self.now())
        if (evidence.get('owner_user_id') is not None
                or evidence.get('broker_account_id') != account.broker_account_id
                or evidence.get('environment') != 'live' or evidence.get('provider') != 'kis'):
            raise ReconciliationBlocked('evidence_scope_mismatch')
        try:
            age = (self.now() - timestamp(evidence['checked_at'])).total_seconds()
        except (KeyError, ValueError, TypeError):
            raise ReconciliationBlocked('evidence_timestamp_invalid') from None
        if not -2 <= age <= 60:
            raise ReconciliationBlocked('evidence_stale')
        day = timestamp(order.created_at).astimezone(KST).date().isoformat()
        if (evidence.get('complete') is not True or evidence.get('execution_filter') != '00'
                or evidence.get('history_date') != day
                or evidence.get('positions_reliable') is not True
                or evidence.get('open_orders_reliable') is not True):
            raise ReconciliationBlocked('evidence_incomplete')
        for key in ('history_orders', 'open_orders', 'positions'):
            rows = evidence.get(key)
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ReconciliationBlocked('evidence_incomplete')
            # Any same-symbol broker event is ambiguous without an order number,
            # including partial quantity, rejection or a later closed position.
            if any(str(row.get('symbol') or row.get('pdno') or '') == order.symbol for row in rows):
                raise ReconciliationBlocked('broker_submission_possible')
        reservations = db.query(AutomationProfileBuyReservation).filter_by(order_id=order.id).order_by(
            AutomationProfileBuyReservation.id.asc()).all()
        reservation_values = [{column.name: getattr(row, column.name)
            for column in row.__table__.columns} for row in reservations]
        if any(row.status not in {'reserved', 'blocked'} for row in reservations):
            raise ReconciliationBlocked('reservation_submission_possible')
        plan = {'order_id': order.id, 'owner_user_id': None, 'policy_user_id': account.owner_user_id,
            'broker_account_id': account.broker_account_id, 'original_fingerprint': before,
            'reservation_fingerprint': digest(reservation_values), 'proof_id': proof.id,
            'proof_fingerprint': digest(values_for_log(proof)), 'target_status': TARGET,
            'requires_admin_approval': True, 'broker_submit_called': False,
            'real_order_submitted': False}
        plan['approval_digest'] = digest(plan)
        return plan

    def apply(self, db, *, plan, admin_user_id, approval_digest, approval_reference):
        self._admin(db, admin_user_id)
        if (not approval_reference or not str(approval_reference).strip()
                or approval_digest != plan.get('approval_digest')):
            raise ReconciliationBlocked('explicit_plan_approval_required')
        # The same account mutex used by execution prevents an approved repair
        # racing a fresh submit. No claim is deleted unless we own its token.
        with AccountTradingLimitService().buy_execution_claim(db, allow_disabled=True):
            try:
                verified = self.propose(db, order_id=plan['order_id'], admin_user_id=admin_user_id, claim_held=True)
                if verified != plan:
                    raise ReconciliationBlocked('reconciliation_plan_stale')
                order = db.get(OrderLog, plan['order_id'])
                before = values(order)
                reservations = db.query(AutomationProfileBuyReservation).filter_by(order_id=order.id).order_by(
                    AutomationProfileBuyReservation.id.asc()).all()
                snapshots = [{column.name: getattr(row, column.name)
                    for column in row.__table__.columns} for row in reservations]
                if digest(snapshots) != plan['reservation_fingerprint']:
                    raise ReconciliationBlocked('reconciliation_plan_stale')
                conditions = []
                for field in FIELDS:
                    column, value = getattr(OrderLog, field), before[field]
                    conditions.append(column.is_(None) if value is None else
                        func.julianday(column) == func.julianday(value)
                        if isinstance(column.type, DateTime) else column == value)
                result = db.execute(update(OrderLog).where(*conditions).values(
                    internal_status=TARGET, broker_status='not_submitted', broker_order_status='not_submitted',
                    error_message=REASON,
                    last_sync_payload=json.dumps({**obj(order.last_sync_payload),
                        'approved_pre_submit_reconciliation': {'approval_digest': approval_digest,
                            'proof_id': plan['proof_id'], 'approved_by': admin_user_id}}, default=str),
                ).execution_options(synchronize_session=False))
                if result.rowcount != 1:
                    raise ReconciliationBlocked('reconciliation_plan_stale')
                for snapshot in snapshots:
                    predicates = []
                    for field, value in snapshot.items():
                        column = getattr(AutomationProfileBuyReservation, field)
                        predicates.append(column.is_(None) if value is None else
                            func.julianday(column) == func.julianday(value)
                            if isinstance(column.type, DateTime) else column == value)
                    changed = db.execute(update(AutomationProfileBuyReservation).where(*predicates).values(
                        status='blocked', block_reason=REASON).execution_options(synchronize_session=False))
                    if changed.rowcount != 1:
                        raise ReconciliationBlocked('reconciliation_plan_stale')
                db.flush()
                db.refresh(order)
                audit = TradeRunLog(owner_user_id=None, run_key='pre-submit-repair:' + uuid4().hex,
                    trigger_source='admin_approved_reconciliation', mode='kis_pre_submit_reconciliation',
                    symbol=order.symbol, order_id=order.id, stage='done', result='reconciled', reason=REASON,
                    request_payload=json.dumps({'plan': plan, 'admin_user_id': admin_user_id,
                        'approval_reference': str(approval_reference).strip()}, default=str),
                    response_payload=json.dumps({'before': before, 'after': values(order),
                        'broker_submit_called': False, 'real_order_submitted': False}, default=str))
                db.add(audit)
                db.commit()
                return {'order_id': order.id, 'internal_status': order.internal_status, 'audit_id': audit.id,
                    'broker_submit_called': False, 'real_order_submitted': False}
            except Exception:
                db.rollback()
                raise


def values_for_log(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def read_admin_reconciliation_evidence(db, order, now, *, client):
    """GET all orders (not fills only), with complete continuation or fail closed."""
    from app.brokers.kis_account_execution_reader import ExecutionReadBudget
    from app.services.kis_order_account_scope import resolve_order_account_scope
    scope = resolve_order_account_scope(db, order=order, client=client, require_enabled=False)
    if not scope.account.legacy_admin or scope.identity[0] != 'live':
        raise ReconciliationBlocked('legacy_admin_live_account_required')
    day = timestamp(order.created_at).astimezone(KST).date()
    current = now.astimezone(KST).date()
    # Archive boundaries follow the official account history adapter.
    month = current.year * 12 + current.month - 1 - 3
    boundary = current.replace(year=month // 12, month=month % 12 + 1, day=1)
    budget = ExecutionReadBudget(max_calls=20, timeout_seconds=60)
    def read_day(target):
        rows, seen = [], set()
        continuation = fk = nk = ''
        for _ in range(10):
            page = client.inquire_account_executions_page(budget=budget, start_date=target,
                end_date=target, older=target < boundary, execution_filter='00',
                continuation=continuation, fk=fk, nk=nk)
            rows.extend(page['orders'])
            if page['tr_cont'] not in {'F', 'M'}:
                break
            cursors = (page['fk'], page['nk'])
            if not all(cursors) or cursors in seen:
                raise ReconciliationBlocked('history_incomplete')
            seen.add(cursors)
            fk, nk = cursors
            continuation = 'N'
        else:
            raise ReconciliationBlocked('history_incomplete')
        for row in rows:
            if (not row.get('pdno') or row.get('ord_dt') != target.strftime('%Y%m%d')
                    or not row.get('odno') or row.get('sll_buy_dvsn_cd') not in {'01', '02'}):
                raise ReconciliationBlocked('history_row_unverified')
            for key in ('ord_qty', 'tot_ccld_qty', 'rmn_qty'):
                try:
                    value = float(row[key])
                    if not math.isfinite(value) or value < 0:
                        raise ValueError()
                except (KeyError, ValueError, TypeError):
                    raise ReconciliationBlocked('history_row_unverified') from None
        return rows
    history = read_day(day)
    today = history if day == current else read_day(current)
    positions = client.list_positions()
    if (not isinstance(positions, list)
            or any(not isinstance(row, dict) or not row.get('symbol') for row in positions)):
        raise ReconciliationBlocked('positions_unavailable')
    return {'provider': 'kis', 'owner_user_id': None, 'broker_account_id': scope.account.broker_account_id,
        'environment': 'live', 'checked_at': now.isoformat(), 'complete': True, 'execution_filter': '00',
        'history_date': day.isoformat(), 'history_orders': history,
        'open_orders': [row for row in today if float(row['rmn_qty']) > 0],
        'positions': positions, 'positions_reliable': True, 'open_orders_reliable': True}
