"""Conservative decisions from a normalized, account-scoped order snapshot."""
import math
from typing import Any

ACTIVE_ORDER_STATUSES = {
    'REQUESTED', 'SUBMITTED', 'ACCEPTED', 'PENDING', 'PARTIALLY_FILLED',
    'UNKNOWN_STALE', 'SYNC_FAILED', 'PENDING_SUBMIT',
}


def broker_order_block(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    orders = snapshot.get('open_orders')
    if not isinstance(orders, list):
        return {'reason': 'open_orders_snapshot_unavailable', 'duplicate_check_source': 'kis_broker_snapshot'}
    for item in orders:
        if not isinstance(item, dict):
            return {'reason': 'order_status_unverified', 'duplicate_check_source': 'kis_broker_snapshot'}
        status = str(item.get('status') or '').upper()
        side = str(item.get('side') or '').lower()
        try:
            remaining = float(item['remaining_quantity']) if item.get('remaining_quantity') is not None else None
        except (ValueError, TypeError):
            remaining = None
        evidence = {
            'duplicate_check_source': 'kis_broker_snapshot',
            'broker_order_id_masked': '***' + str(item.get('broker_order_id') or '')[-4:],
            'symbol': item.get('symbol'), 'side': side, 'order_status': status.lower(),
            'remaining_quantity': remaining,
        }
        if (item.get('order_status_verified') is False or side not in {'buy', 'sell'}
                or not status or status in {'UNKNOWN', 'UNKNOWN_STALE', 'SYNC_FAILED'}
                or (remaining is not None and (not math.isfinite(remaining) or remaining < 0))):
            return {**evidence, 'reason': 'order_status_unverified'}
        if status in {'FILLED', 'CANCELED', 'CANCELLED', 'REJECTED', 'EXPIRED', 'INACTIVE'} or remaining == 0:
            continue
        if side == 'buy' and status in ACTIVE_ORDER_STATUSES:
            # Execution still reserves this symbol and can select another one.
            # Ambiguous raw KIS rows carry order_status_verified=False above.
            continue
        if status not in ACTIVE_ORDER_STATUSES or remaining is None:
            return {**evidence, 'reason': 'order_status_unverified'}
        if side == 'sell':
            return {**evidence, 'reason': 'broker_active_sell_order'}
    if snapshot.get('open_orders_reliable') is False:
        return {'reason': 'open_orders_snapshot_unavailable', 'duplicate_check_source': 'kis_broker_snapshot'}
    return None
