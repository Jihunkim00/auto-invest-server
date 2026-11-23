"""All-account orchestration. Broker access is exclusively execution-history GETs.

No submission, cancellation, reservation reset or slot replay is performed here.
"""
from __future__ import annotations

import json
import math
import time
import uuid
from datetime import UTC, datetime, timedelta

from dateutil.relativedelta import relativedelta
from sqlalchemy import DateTime, String, cast, or_, update
from sqlalchemy.exc import IntegrityError

from app.brokers.kis_account_execution_reader import (
    ExecutionHistoryError, ExecutionReadBudget, execution_environment,
)
from app.db.models import KisOrderReconciliationState, OrderLog, TradeRunLog, User
from app.services.account_trading_limit_service import AccountTradingLimitError
from app.services.kis_order_account_scope import resolve_order_account_scope
from app.services.kis_order_mapper import map_kis_order_row
from app.services.kis_position_lifecycle_service import KisPositionLifecycleService
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.kis_order_sync_service import (
    KR_TZ, OPEN_KIS_INTERNAL_STATUSES, KisOrderSyncService, _submitted_kst_date,
)

TERMINAL = {'FILLED', 'CANCELED', 'REJECTED', 'EXPIRED'}
MODE = 'kis_auto_order_reconciliation'
ORDER_COMPARISON_FIELDS = (
    'internal_status', 'filled_qty', 'remaining_qty', 'last_synced_at',
    'kis_odno', 'broker_order_id', 'requested_qty', 'qty', 'submitted_at',
    'symbol', 'side', 'owner_user_id', 'request_payload', 'profile_id',
    'profile_key', 'created_at', 'last_sync_payload', 'broker_status',
    'broker_order_status', 'filled_at', 'market', 'broker', 'updated_at',
    'filled_avg_price', 'avg_fill_price', 'response_payload', 'sync_error', 'error_message',
)


def _utc(value):
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)).replace(tzinfo=None)


def _scope_key(owner):
    return 'admin' if owner is None else f'user:{int(owner)}'


def _orders(db, owner):
    return db.query(OrderLog).filter(
        OrderLog.broker == 'kis', OrderLog.owner_user_id == owner,
        or_(OrderLog.market == 'KR', OrderLog.market.is_(None)),
        OrderLog.internal_status.in_(sorted(OPEN_KIS_INTERNAL_STATUSES)),
    )


class ReconciliationEvidenceError(ValueError):
    pass


def _number(value):
    try:
        result = float(value)
        if isinstance(value, bool) or not math.isfinite(result) or result < 0:
            raise ValueError
        return result
    except (TypeError, ValueError):
        raise ReconciliationEvidenceError('broker_execution_quantity_invalid') from None


def verified_mapping(order, rows, *, identity, day):
    """Unique exact identity and explicit terminal evidence; absence proves nothing."""
    number = str(order.kis_odno or order.broker_order_id or '').strip().lstrip('0')
    if not number:
        raise ReconciliationEvidenceError('kis_odno_missing')
    if order.kis_odno and order.broker_order_id and (
        str(order.kis_odno).strip().lstrip('0') != str(order.broker_order_id).strip().lstrip('0')
    ):
        raise ReconciliationEvidenceError('local_order_number_conflict')
    candidates = [{str(k).lower(): v for k, v in row.items()} for row in rows
                  if str(row.get('odno') or row.get('ODNO') or '').strip().lstrip('0') == number]
    if not candidates:
        raise ReconciliationEvidenceError('broker_order_record_missing')
    # A reused order number on another day must never select a first match.
    candidates = [row for row in candidates if str(row.get('ord_dt')) == day.strftime('%Y%m%d')]
    if len(candidates) != 1:
        raise ReconciliationEvidenceError('broker_order_not_uniquely_verified')
    row = candidates[0]
    if (order.side not in {'buy', 'sell'} or row.get('pdno') != order.symbol
            or row.get('sll_buy_dvsn_cd') != ('02' if order.side == 'buy' else '01')
            or str(row.get('cano', identity[1])).strip() != identity[1]
            or str(row.get('acnt_prdt_cd', identity[2])).strip() != identity[2]):
        raise ReconciliationEvidenceError('broker_order_identity_mismatch')
    qty, filled, remaining = (_number(row.get(key)) for key in ('ord_qty', 'tot_ccld_qty', 'rmn_qty'))
    if (qty <= 0 or qty != _number(order.requested_qty or order.qty)
            or filled + remaining > qty or filled < _number(order.filled_qty or 0)):
        raise ReconciliationEvidenceError('broker_execution_quantity_invalid')
    if any(not value.is_integer() for value in (qty, filled, remaining)):
        raise ReconciliationEvidenceError('broker_execution_quantity_invalid')
    mapped = map_kis_order_row(row)
    if filled and (mapped.avg_fill_price is None or not math.isfinite(mapped.avg_fill_price)
                   or mapped.avg_fill_price <= 0):
        raise ReconciliationEvidenceError('broker_fill_price_missing')
    text = str(row.get('ord_status') or row.get('ordr_stat_name') or row.get('ord_stts_name') or '').strip().lower()
    # A cancellation request/partial rejection does not prove the remainder ended.
    canceled = str(row.get('cncl_yn') or '').upper() == 'Y' or text in {'canceled', 'cancelled', '취소', '취소완료'}
    rejected = _number(row.get('rjct_qty') or 0) == qty - filled or text in {'rejected', '거부', '거부완료'}
    expired = text in {'expired', '만료'}
    rejected_qty = _number(row.get('rjct_qty') or 0)
    if rejected_qty > qty - filled:
        raise ReconciliationEvidenceError('broker_execution_quantity_invalid')
    if filled == qty and remaining == 0 and not (canceled or expired or rejected_qty):
        target = 'FILLED'
    elif remaining == 0 and filled < qty and (canceled or rejected or expired):
        target = 'CANCELED' if canceled else 'EXPIRED' if expired else 'REJECTED'
    elif filled + remaining == qty and remaining > 0 and not (canceled or expired or _number(row.get('rjct_qty') or 0)):
        target = 'PARTIALLY_FILLED' if filled else 'PENDING'
    else:
        raise ReconciliationEvidenceError('broker_terminal_evidence_insufficient')
    # Mapper data is reused, but its permissive text heuristics cannot finalize.
    from dataclasses import replace
    return replace(mapped, internal_status=target)


class KisAutomaticOrderReconciliationService:
    def __init__(self, *, client_factory=None, now_provider=None, budget_factory=None):
        self.client_factory = client_factory or self._client
        self.now_provider = now_provider or (lambda: datetime.now(UTC))
        self.budget_factory = budget_factory or (lambda: ExecutionReadBudget(max_calls=12, timeout_seconds=20))

    @staticmethod
    def _client(db, owner):
        if owner is None:
            from app.config import get_settings
            from app.brokers.kis_client import KisClient
            from app.brokers.kis_auth_manager import KisAuthManager
            settings = get_settings()
            return KisClient(settings, KisAuthManager(settings, db))
        from app.services.user_broker_account_service import UserBrokerAccountService
        user = db.get(User, owner)
        if user is None or user.role != 'user':
            raise AccountTradingLimitError('account_scope_unavailable')
        return UserBrokerAccountService().get_kis_read_only_client(db, user)

    def reconcile_all(self, db, *, trigger='periodic'):
        owners = [row[0] for row in db.query(OrderLog.owner_user_id).filter(
            OrderLog.broker == 'kis', OrderLog.internal_status.in_(sorted(OPEN_KIS_INTERNAL_STATUSES)),
        ).distinct().all()]
        # Oldest account check first prevents a failing account starving others.
        states = {row.scope_key: row.last_synced_at or datetime.min
                  for row in db.query(KisOrderReconciliationState).all()}
        owners.sort(key=lambda owner: states.get(_scope_key(owner), datetime.min))
        results = []
        started = time.monotonic()
        for owner in owners[:20]:
            if time.monotonic() - started >= 30:
                break
            try:
                results.append(self.reconcile_account(db, owner_user_id=owner, trigger=trigger))
            except Exception:
                db.rollback()
                results.append({'scope': _scope_key(owner), 'status': 'error', 'last_failure_reason': 'reconciliation_failed'})
        return {'status': 'ok', 'accounts': results, 'broker_submit_called': False}

    @staticmethod
    def status(db, *, owner_user_id=None):
        state = db.get(KisOrderReconciliationState, _scope_key(owner_user_id))
        unresolved = _orders(db, owner_user_id).all()
        # Derive current warnings from live rows, so past failures cannot linger.
        review = (len(unresolved) if state and state.last_failure_reason and state.checked_count == 0 else
                  sum(bool(row.sync_error) or not (row.kis_odno or row.broker_order_id) for row in unresolved))
        def kst(value):
            return value.replace(tzinfo=UTC).astimezone(KR_TZ).isoformat() if value else None
        return {
            'scope': _scope_key(owner_user_id), 'provider': 'kis', 'timezone': 'Asia/Seoul',
            'last_synced_at': kst(state.last_synced_at) if state else None,
            'checked_count': state.checked_count if state else 0,
            'finalized_count': state.finalized_count if state else 0,
            'unresolved_count': len(unresolved), 'manual_review_count': review,
            'last_failure_reason': state.last_failure_reason if state and review else None,
            'next_attempt_at': kst(state.next_attempt_at) if state and unresolved else None,
            'buy_hold_message': ('이전 매도 주문의 최종 상태를 확인 중이어서 신규 매수를 보류했습니다.'
                                 if any(row.side == 'sell' for row in unresolved) else None),
        }

    def reconcile_account(self, db, *, owner_user_id=None, client=None, trigger='slot', order_id=None):
        now = _utc(self.now_provider())
        key, token = _scope_key(owner_user_id), uuid.uuid4().hex
        state = db.get(KisOrderReconciliationState, key)
        if (state is not None and state.failure_count >= 3 and trigger in {'periodic', 'startup_or_periodic'}
                and state.last_synced_at is not None
                and state.last_synced_at.replace(tzinfo=UTC).astimezone(KR_TZ).date()
                == now.replace(tzinfo=UTC).astimezone(KR_TZ).date()):
            return {**self.status(db, owner_user_id=owner_user_id), 'status': 'review_required'}
        if state is None:
            try:
                db.add(KisOrderReconciliationState(scope_key=key))
                db.commit()
            except IntegrityError:
                db.rollback()
        # A freshly acknowledged order gets its first read even when a pre-entry
        # check just consumed the account interval. The account lease still wins.
        first_submit_read = (trigger == 'post_submit' and order_id is not None
                             and _orders(db, owner_user_id).filter(
                                 OrderLog.id == order_id, OrderLog.last_synced_at.is_(None)).count() == 1)
        acquired = db.execute(update(KisOrderReconciliationState).where(
            KisOrderReconciliationState.scope_key == key,
            or_(KisOrderReconciliationState.lease_until.is_(None), KisOrderReconciliationState.lease_until <= now),
            or_(first_submit_read, KisOrderReconciliationState.next_attempt_at.is_(None),
                KisOrderReconciliationState.next_attempt_at <= now),
        ).values(lease_token=token, lease_until=now + timedelta(seconds=90)))
        db.commit()
        if acquired.rowcount != 1:
            return {**self.status(db, owner_user_id=owner_user_id), 'status': 'deferred'}
        checked = finalized = 0
        failure = None
        try:
            query = _orders(db, owner_user_id)
            if order_id is not None:
                query = query.filter(OrderLog.id == order_id)
            # Keep the database's read-time timestamp representation for SQLite
            # CAS. ORM datetimes still drive UTC calculations; rebinding them
            # would add ".000000" to a row stored at whole-second precision.
            columns = {}
            sqlite = db.get_bind().dialect.name == 'sqlite'
            for name in ORDER_COMPARISON_FIELDS:
                column = OrderLog.__table__.c[name]
                columns[name] = cast(column, String) if sqlite and isinstance(column.type, DateTime) else column
            orders = query.add_columns(*columns.values()).order_by(
                OrderLog.last_synced_at.asc(), OrderLog.id.asc(),
            ).limit(20).all()
            if orders:
                client = client or self.client_factory(db, owner_user_id)
            budget, histories = self.budget_factory(), {}
            for order, *original_values in orders:
                checked += 1
                before = dict(zip(columns, original_values))
                updates = {}
                reason = None
                lifecycle_service = None
                position_snapshot = None
                try:
                    scope = resolve_order_account_scope(db, order=order, client=client, require_enabled=False)
                    payload = json.loads(order.request_payload or '{}')
                    for field in ('environment', 'kis_env'):
                        if payload.get(field) is not None and execution_environment(payload[field]) != scope.identity[0]:
                            raise ReconciliationEvidenceError('order_environment_mismatch')
                    if payload.get('broker_account_id') not in (None, scope.account.broker_account_id):
                        raise ReconciliationEvidenceError('order_account_mismatch')
                    if not str(order.kis_odno or order.broker_order_id or '').strip().lstrip('0'):
                        raise ReconciliationEvidenceError('kis_odno_missing')
                    day = _submitted_kst_date(order)
                    today = now.replace(tzinfo=UTC).astimezone(KR_TZ).date()
                    # The recent endpoint covers three months. Older records are
                    # retained for manual review, never inferred absent/expired.
                    if day > today or day <= today - relativedelta(months=3):
                        raise ReconciliationEvidenceError('history_date_out_of_supported_range')
                    if day not in histories:
                        try:
                            histories[day] = self._history(client, day, budget)
                        except Exception as exc:
                            histories[day] = exc
                    if isinstance(histories[day], Exception):
                        raise histories[day]
                    # A credential rotation during the read invalidates this
                    # client's scope before any order status can be finalized.
                    scope = resolve_order_account_scope(db, order=order, client=client, require_enabled=False)
                    mapped = verified_mapping(order, histories[day], identity=scope.identity, day=day)
                    # Reuse field mapping without the old service's commits or
                    # historical fill-time invention. CAS + audit commit together.
                    from types import SimpleNamespace
                    staged = SimpleNamespace(**{column.name: getattr(order, column.name)
                                               for column in OrderLog.__table__.columns})
                    KisOrderSyncService(client)._apply_mapped_result(staged, mapped, {}, now=now)
                    fields = ('internal_status', 'requested_qty', 'filled_qty', 'remaining_qty',
                              'avg_fill_price', 'filled_avg_price', 'broker_order_status', 'broker_status',
                              'last_synced_at', 'sync_error', 'error_message')
                    updates = {name: getattr(staged, name) for name in fields}
                    if order.side == 'buy' and mapped.filled_qty:
                        lifecycle_service = KisPositionLifecycleService(client)
                        if mapped.internal_status == 'FILLED':
                            position_snapshot = lifecycle_service.read_buy_link_snapshot(
                                db, order, now=now.replace(tzinfo=UTC),
                            )
                        current_scope = resolve_order_account_scope(db, order=order, client=client, require_enabled=False)
                        if current_scope != scope:
                            raise ReconciliationEvidenceError('order_account_mismatch')
                except Exception as exc:
                    reason = self._reason(exc)
                    failure = reason
                    updates = {'last_synced_at': now, 'sync_error': reason}
                    lifecycle_service = None
                evidence = {'scope': key, 'local_order_id': order.id,
                            'trigger': trigger if trigger in {'periodic', 'startup_or_periodic', 'slot', 'pre_entry', 'post_submit'} else 'periodic',
                            'from_status': before['internal_status'],
                            'to_status': updates.get('internal_status', before['internal_status']),
                            'evidence_type': 'complete_daily_execution_history' if reason is None else 'unverified',
                            'synced_at': now.replace(tzinfo=UTC).isoformat(), 'reason': reason,
                            'filled_qty': updates.get('filled_qty', before['filled_qty']),
                            'remaining_qty': updates.get('remaining_qty', before['remaining_qty']),
                            'broker_submit_called': False}
                if reason is None:
                    # Only allowlisted non-sensitive evidence is persisted.
                    evidence['broker_evidence'] = {k: mapped.raw_payload.get(k) for k in (
                        'ord_dt', 'ord_tmd', 'pdno', 'sll_buy_dvsn_cd', 'ord_qty', 'tot_ccld_qty',
                        'rmn_qty', 'cncl_yn', 'rjct_qty', 'avg_prvs')}
                try:
                    prior = json.loads(order.last_sync_payload or '{}')
                    prior = prior if isinstance(prior, dict) else {}
                except (TypeError, ValueError):
                    prior = {}
                updates['last_sync_payload'] = json.dumps(
                    {**sanitize_kis_payload(prior), 'automatic_reconciliation': evidence}, ensure_ascii=False)
                conditions = [columns[name].is_(None) if value is None else columns[name] == value
                              for name, value in before.items()]
                lease = db.query(KisOrderReconciliationState).filter_by(scope_key=key, lease_token=token).filter(
                    KisOrderReconciliationState.lease_until > _utc(self.now_provider())).exists()
                result = db.execute(update(OrderLog).where(OrderLog.id == order.id, lease, *conditions)
                                    .values(**updates).execution_options(synchronize_session=False))
                if result.rowcount != 1:
                    db.rollback()
                    failure = 'concurrent_order_change'
                    continue
                if lifecycle_service is not None:
                    db.refresh(order)
                    position_result = lifecycle_service.reconcile_existing_buy_position(
                        db, order, position_snapshot, evidence['broker_evidence'],
                    )
                    if position_result is not None:
                        evidence['position_reconciliation'] = position_result
                        if position_result['status'] == 'manual_review_required':
                            failure = 'position_reconciliation_manual_review'
                            evidence['reason'] = failure
                        order.last_sync_payload = json.dumps(
                            {**sanitize_kis_payload(prior), 'automatic_reconciliation': evidence}, ensure_ascii=False,
                        )
                db.add(TradeRunLog(owner_user_id=owner_user_id, run_key='kis-reconcile-' + uuid.uuid4().hex,
                    trigger_source='automatic_order_reconciliation', mode=MODE, symbol=order.symbol,
                    stage='done', result='review_required' if evidence['reason'] else 'verified',
                    reason=evidence['reason'] or 'broker_order_verified', order_id=order.id,
                    response_payload=json.dumps(evidence, ensure_ascii=False)))
                db.commit()
                db.refresh(order)
                if reason is None and order.internal_status in TERMINAL:
                    finalized += 1
        except Exception as exc:
            db.rollback()
            failure = self._reason(exc)
        finally:
            state = db.get(KisOrderReconciliationState, key)
            count = min(3, (state.failure_count or 0) + 1) if failure else 0
            delay = (30, 120, 600)[count - 1] if count else 60
            db.execute(update(KisOrderReconciliationState).where(
                KisOrderReconciliationState.scope_key == key, KisOrderReconciliationState.lease_token == token,
            ).values(lease_token=None, lease_until=None, last_synced_at=now,
                     next_attempt_at=_utc(self.now_provider()) + timedelta(seconds=delay),
                     checked_count=checked, finalized_count=finalized, failure_count=count,
                     last_failure_reason=failure))
            db.commit()
        return {**self.status(db, owner_user_id=owner_user_id), 'status': 'review_required' if failure else 'ok'}

    @staticmethod
    def _reason(exc):
        if isinstance(exc, (ReconciliationEvidenceError, AccountTradingLimitError)):
            return str(exc)
        if isinstance(exc, ExecutionHistoryError):
            return exc.code
        return 'broker_read_or_credentials_unavailable'

    @staticmethod
    def _history(client, day, budget):
        rows, seen = [], set()
        continuation = fk = nk = ''
        for _ in range(12):
            page = client.inquire_account_executions_page(budget=budget, start_date=day, end_date=day,
                execution_filter='00', older=False, continuation=continuation, fk=fk, nk=nk)
            if not isinstance(page.get('orders'), list) or any(not isinstance(row, dict) for row in page['orders']):
                raise ReconciliationEvidenceError('history_shape_invalid')
            rows.extend(page['orders'])
            if page.get('tr_cont') in {'', 'D', 'E'}:
                budget.remaining()
                return rows
            cursor = (page.get('fk'), page.get('nk'))
            if page.get('tr_cont') not in {'M', 'F'} or not all(cursor) or cursor in seen:
                raise ReconciliationEvidenceError('history_incomplete')
            seen.add(cursor)
            fk, nk, continuation = *cursor, 'N'
        raise ReconciliationEvidenceError('history_incomplete')


class AutomaticKisOrderSyncService:
    """Compatibility interface for existing guarded post-submission sync steps."""
    def __init__(self, client):
        self.client = client

    def sync_order(self, db, order_id):
        owner = getattr(self.client, 'user_id', None)
        order = db.get(OrderLog, order_id)
        if order is None or order.owner_user_id != owner:
            raise ReconciliationEvidenceError('account_scope_mismatch')
        KisAutomaticOrderReconciliationService().reconcile_account(
            db, owner_user_id=owner, client=self.client, trigger='post_submit', order_id=order_id)
        db.refresh(order)
        return order
