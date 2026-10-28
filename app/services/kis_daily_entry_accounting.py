"""Confirmed KIS entries and unresolved entry capacity are separate facts."""
from datetime import UTC, datetime, time, timedelta
import json
from zoneinfo import ZoneInfo

from app.db.models import OrderLog, TradeRunLog


FINAL_STATUSES = {
    'FILLED', 'CANCELED', 'CANCELLED', 'REJECTED', 'EXPIRED', 'FAILED',
    'REJECTED_BY_SAFETY_GATE', 'DRY_RUN_SIMULATED',
}


def confirmed_fill(order):
    if simulated_order(order):
        return False
    return (str(order.internal_status or '').upper() == 'FILLED'
            or float(order.filled_qty or 0) > 0)


def simulated_order(order):
    try:
        response = json.loads(order.response_payload or '{}')
    except (TypeError, ValueError):
        response = {}
    response = response if isinstance(response, dict) else {}
    return (str(order.internal_status or '').upper() == 'DRY_RUN_SIMULATED'
            or str(order.broker_status or '').lower() == 'simulated_filled'
            or response.get('simulation') is True)


def daily_entry_counts(db, *, now: datetime, owner_user_id=None, exclude_order_id=None):
    local = now.astimezone(ZoneInfo('Asia/Seoul'))
    start = datetime.combine(local.date(), time.min, tzinfo=local.tzinfo).astimezone(UTC)
    end = start + timedelta(days=1)
    filled = unresolved = 0
    rows = db.query(OrderLog).filter(
        OrderLog.broker == 'kis', OrderLog.owner_user_id == owner_user_id,
        OrderLog.side == 'buy',
    ).all()
    for order in rows:
        if str(order.market or 'KR').upper() != 'KR':
            continue
        event = order.filled_at or order.submitted_at or order.created_at
        event = event.replace(tzinfo=UTC) if event is not None and event.tzinfo is None else event
        filled_today = confirmed_fill(order) and event is not None and start <= event < end
        if filled_today:
            filled += 1
        # Old unresolved orders still reserve capacity. A partial fill is one
        # entry, even when the remaining quantity has not yet been resolved.
        if (order.id != exclude_order_id and not filled_today
                and str(order.internal_status or '').upper() not in FINAL_STATUSES):
            unresolved += 1
    # A run without its authoritative order row cannot prove a fill. Preserve
    # its capacity reservation until reconciliation repairs the missing row.
    seen = {row.id for row in rows}
    orphan_ids = set()
    for run in db.query(TradeRunLog).filter(
        TradeRunLog.owner_user_id == owner_user_id,
        TradeRunLog.mode == 'automation_profile_scheduler_buy',
        TradeRunLog.order_id.isnot(None),
    ).all():
        event = run.created_at
        event = event.replace(tzinfo=UTC) if event is not None and event.tzinfo is None else event
        if (run.order_id not in seen and run.order_id != exclude_order_id
                and str(run.result or '').lower() in {'filled', 'submitted', 'sync_required'}
                and event is not None and start <= event < end):
            orphan_ids.add(run.order_id)
    unresolved += len(orphan_ids)
    return filled, unresolved
