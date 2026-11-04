"""Owner-scoped reconciliation using read-only KIS execution evidence.

Holdings alone never prove that a particular order filled. This service has no
broker submit/cancel path and does not invoke any trading execution method.
"""
from datetime import UTC, datetime
import math
import json

from app.db.models import PositionLifecycle, User
from app.services.account_trading_limit_service import AccountTradingLimitError
from app.services.kis_order_account_scope import resolve_order_account_scope
from app.services.kis_order_sync_service import (
    KR_TZ, OPEN_KIS_INTERNAL_STATUSES, KisOrderSyncError, KisOrderSyncService,
)


class UserKisOrderSyncService(KisOrderSyncService):
    def sync_order(self, db, order_id):
        from app.db.models import OrderLog

        order = db.get(OrderLog, order_id)
        if (order is None or order.owner_user_id is None
                or order.owner_user_id != getattr(self.client, 'user_id', None)):
            raise KisOrderSyncError('account_scope_mismatch')
        try:
            # Reading existing executions remains available when entries are
            # disabled. All execution callers retain require_enabled=True.
            resolve_order_account_scope(db, order=order, client=self.client, require_enabled=False)
        except AccountTradingLimitError as exc:
            raise KisOrderSyncError(str(exc)) from None
        if order.internal_status == 'FILLED':
            self._sync_filled_buy_lifecycle(db, order)
            return order
        if order.internal_status not in OPEN_KIS_INTERNAL_STATUSES:
            raise KisOrderSyncError('order_not_unresolved')
        return super().sync_order(db, order_id)

    def _apply_mapped_result(self, order, mapped, inquiry, *, now):
        owner = order.owner_user_id
        if (inquiry.get('owner_user_id') != owner or inquiry.get('provider') != 'kis'
                or inquiry.get('broker_account_id') != f'user:{owner}:kis:KR'
                or inquiry.get('environment') != self.client.environment
                or inquiry.get('complete') is not True):
            raise KisOrderSyncError('execution_evidence_scope_unverified')
        number = str(order.kis_odno or order.broker_order_id or '').lstrip('0')
        matches = [row for row in inquiry['orders']
                   if str(row.get('odno') or row.get('ODNO') or '').lstrip('0') == number]
        if len(matches) != 1:
            raise KisOrderSyncError('broker_order_not_uniquely_verified')
        row = matches[0]
        submitted = order.submitted_at or order.created_at
        submitted = submitted.replace(tzinfo=UTC) if submitted.tzinfo is None else submitted
        if (row.get('pdno') != order.symbol
                or row.get('sll_buy_dvsn_cd') != ('02' if order.side == 'buy' else '01')
                or row.get('ord_dt') != submitted.astimezone(KR_TZ).strftime('%Y%m%d')):
            raise KisOrderSyncError('broker_order_identity_mismatch')
        try:
            requested, filled, remaining = (float(row[key]) for key in ('ord_qty', 'tot_ccld_qty', 'rmn_qty'))
            if (not all(math.isfinite(value) and value >= 0 for value in (requested, filled, remaining))
                    or requested <= 0 or requested != float(order.requested_qty or order.qty)
                    or filled > requested or filled + remaining > requested
                    or filled < float(order.filled_qty or 0)):
                raise ValueError
            if filled and (mapped.avg_fill_price is None or not math.isfinite(mapped.avg_fill_price)
                           or mapped.avg_fill_price <= 0):
                raise ValueError
            if mapped.internal_status == 'FILLED' and (filled != requested or remaining != 0):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise KisOrderSyncError('broker_execution_quantity_or_price_invalid') from None
        old_filled_at = order.filled_at
        super()._apply_mapped_result(order, mapped, inquiry, now=now)
        # Daily inquiry supplies order time, not the exact fill time. Never
        # move a historical trade into today's daily cap by inventing a fill.
        order.filled_at = old_filled_at

    def _apply_stale_result(self, order, mapped, inquiry, *, now):
        if (inquiry.get('complete') is not True
                or inquiry.get('owner_user_id') != order.owner_user_id
                or inquiry.get('broker_account_id') != f'user:{order.owner_user_id}:kis:KR'
                or inquiry.get('provider') != 'kis'
                or inquiry.get('environment') != self.client.environment):
            raise KisOrderSyncError('execution_evidence_scope_unverified')
        super()._apply_stale_result(order, mapped, inquiry, now=now)

    def _sync_filled_buy_lifecycle(self, db, order):
        if order.side != 'buy' or order.internal_status != 'FILLED':
            return
        from app.services.user_trading_execution_service import UserTradingExecutionService

        existing = db.query(PositionLifecycle).filter_by(entry_order_id=order.id).one_or_none()
        if existing is not None:
            if existing.owner_user_id != order.owner_user_id:
                raise KisOrderSyncError('account_scope_mismatch')
            outcome = {'status': 'linked', 'lifecycle_id': existing.id}
        else:
            held = None
            try:
                snapshot = self.client.get_snapshot()
                if snapshot.get('positions_reliable') is not True:
                    raise ValueError('positions_unreliable')
                held = [row for row in snapshot['positions'] if row.get('symbol') == order.symbol
                        and float(row.get('quantity') or row.get('qty') or 0) > 0]
            except Exception:
                # Executions and current holdings are independent evidence.
                # Preserve the verified fill and expose incomplete linkage.
                outcome = {'status': 'review_required', 'reason': 'position_snapshot_unavailable'}
            if held is not None:
                active = db.query(PositionLifecycle).filter(
                    PositionLifecycle.owner_user_id == order.owner_user_id,
                    PositionLifecycle.symbol == order.symbol,
                    PositionLifecycle.status.in_(['open', 'closing']),
                ).first()
                if active is not None:
                    outcome = {'status': 'review_required', 'reason': 'existing_position_requires_review'}
                elif not held:
                    # A historical buy may already have been sold (e.g. #13).
                    # Its fill remains true, but it must not open a position.
                    outcome = {'status': 'not_held', 'reason': 'no_current_broker_position'}
                elif len(held) != 1 or float(held[0].get('quantity') or held[0].get('qty') or 0) != float(order.filled_qty):
                    outcome = {'status': 'review_required', 'reason': 'position_quantity_mismatch'}
                else:
                    UserTradingExecutionService._maybe_create_position_lifecycle(
                        db, user=db.get(User, order.owner_user_id), order=order,
                        now=order.submitted_at or order.created_at or datetime.now(UTC),
                    )
                    lifecycle = db.query(PositionLifecycle).filter_by(entry_order_id=order.id).one()
                    outcome = {'status': 'linked', 'lifecycle_id': lifecycle.id}
        # Use the existing user position registration, without executing a
        # trading cycle or modifying administrator lifecycle/settings state.
        payload = json.loads(order.last_sync_payload or '{}')
        payload['position_reconciliation'] = outcome
        order.last_sync_payload = json.dumps(payload, ensure_ascii=False, default=str)
        db.commit()
        db.refresh(order)
