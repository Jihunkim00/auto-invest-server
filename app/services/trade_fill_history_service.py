"""Read-only projection of persisted broker execution evidence.

No broker client, order sync, execution method, or database write belongs here.
KIS daily inquiry reports cumulative quantities per order, so one broker order
is one history item. Order/submission/sync timestamps never stand in for fills.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import OrderLog, User, UserBrokerCredential

KST = ZoneInfo('Asia/Seoul')
PERIOD_DAYS = {'today': 1, 'week': 7, 'month': 30, 'year': 365}


def _object(raw):
    try:
        value = json.loads(raw or '{}') if isinstance(raw, str) else raw
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def _utc(value):
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        # A timezone-free provider timestamp cannot prove an instant.
        return result.astimezone(UTC) if result.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def history_window(period, now):
    """Inclusive KST calendar dates: today and the preceding N-1 days."""
    now = _utc(now)
    midnight = now.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=PERIOD_DAYS[period] - 1), now


def account_environment(db, user, provider):
    if user.role == 'admin':
        settings = get_settings()
        env = settings.kis_env if provider == 'kis' else (
            'paper' if 'paper' in settings.alpaca_base_url else 'live')
    else:
        row = db.query(UserBrokerCredential).filter_by(user_id=user.id, provider=provider).one_or_none()
        env = row.environment if row else None
    return env if env in {'live', 'paper'} else None


def _simulated(request, response):
    for payload in (request, response):
        if any(payload.get(key) is True for key in ('dry_run', 'simulated', 'simulation')):
            return True
        mode = str(payload.get('mode') or '').lower()
        source = str(payload.get('source') or payload.get('trigger_source') or '').lower()
        if any(word in mode or word in source for word in ('simulation', 'simulated', 'dry_run', 'dry-run', 'shadow')):
            return True
    return False


def _kis_fill(order, request, sync, environment):
    evidence = _object(sync.get('matched_order'))
    inquiry = _object(sync.get('inquiry'))
    if inquiry.get('provider') != 'kis' or inquiry.get('environment') != environment:
        return None
    if order.owner_user_id is not None and (
        inquiry.get('owner_user_id') != order.owner_user_id
        or inquiry.get('broker_account_id') != f'user:{order.owner_user_id}:kis:KR'
        or inquiry.get('complete') is not True
    ):
        return None
    if order.owner_user_id is None and inquiry.get('owner_user_id') is not None:
        return None
    evidence = {str(key).lower(): value for key, value in evidence.items()}
    number = str(order.kis_odno or order.broker_order_id or '').lstrip('0')
    if (not number or str(evidence.get('odno') or '').lstrip('0') != number
        or evidence.get('pdno') != order.symbol
        or evidence.get('sll_buy_dvsn_cd') != ('02' if order.side == 'buy' else '01')):
        return None
    submitted = _utc(order.submitted_at or order.created_at)
    if not submitted or evidence.get('ord_dt') != submitted.astimezone(KST).strftime('%Y%m%d'):
        return None
    quantity = _number(evidence.get('tot_ccld_qty'))
    requested = _number(evidence.get('ord_qty'))
    if (quantity is None or requested is None or quantity > requested
        or not quantity.is_integer() or not requested.is_integer()
        or requested != _number(order.requested_qty or order.qty)):
        return None
    # KIS domestic daily executions are same-day trades. ord_tmd is ORDER
    # time, never execution time. Preserve date-only precision when necessary.
    day = str(evidence.get('ccld_dt') or evidence.get('ord_dt') or '')
    try:
        trade_day = datetime.strptime(day, '%Y%m%d').replace(tzinfo=KST)
        if trade_day.strftime('%Y%m%d') != day:
            return None
        if day != submitted.astimezone(KST).strftime('%Y%m%d'):
            return None
        clock = evidence.get('ccld_tmd')
        filled_at = None
        if clock:
            text = day + str(clock)
            filled_at = datetime.strptime(text, '%Y%m%d%H%M%S').replace(tzinfo=KST)
            if filled_at.strftime('%Y%m%d%H%M%S') != text:
                return None
            if filled_at < submitted:
                return None
    except (ValueError, TypeError):
        return None
    price = _number(evidence.get('avg_prvs') or evidence.get('avg_ccld_prc'))
    amount = _number(evidence.get('tot_ccld_amt'))
    if amount is None and price is not None:
        amount = _number(quantity * price)
    return {
        '_key': (day, number), '_sort': filled_at or trade_day,
        'symbol': order.symbol, 'name': str(evidence.get('prdt_name') or ''),
        'side': order.side, 'quantity': quantity, 'average_price': price,
        'amount': amount, 'currency': 'KRW', 'partial': quantity < requested,
        'trade_date': trade_day.date().isoformat(),
        'filled_at': filled_at.isoformat() if filled_at else None,
        'time_precision': 'second' if filled_at else 'day',
    }


def _alpaca_fill(order, request, response, environment):
    # Alpaca stores the broker order object directly after submit/sync.
    env = request.get('credential_environment')
    if env != environment:
        return None
    if (str(response.get('id') or '') != str(order.broker_order_id or '')
        or not order.broker_order_id or response.get('symbol') != order.symbol
        or response.get('side') != order.side):
        return None
    quantity = _number(response.get('filled_qty'))
    requested = _number(response.get('qty'))
    filled_at = _timestamp(response.get('filled_at'))
    if not quantity or not requested or quantity > requested or not filled_at:
        return None
    price = _number(response.get('filled_avg_price'))
    return {
        '_key': (order.broker_order_id,), '_sort': filled_at,
        'symbol': order.symbol, 'name': '', 'side': order.side,
        'quantity': quantity, 'average_price': price,
        'amount': quantity * price if price else None, 'currency': 'USD',
        'partial': quantity < requested,
        'trade_date': filled_at.astimezone(KST).date().isoformat(),
        'filled_at': filled_at.astimezone(KST).isoformat(), 'time_precision': 'second',
    }


def list_trade_fills(db: Session, *, user: User, provider: str, period: str,
                     limit: int, offset: int, now: datetime | None = None):
    start, end = history_window(period, now or datetime.now(UTC))
    environment = account_environment(db, user, provider)
    # Legacy admin orders have NULL ownership. Never widen this to all owners.
    owner = None if user.role == 'admin' else int(user.id)
    query = db.query(OrderLog).filter(
        OrderLog.owner_user_id == owner, OrderLog.broker == provider,
        OrderLog.market == ('KR' if provider == 'kis' else 'US'),
        OrderLog.side.in_(['buy', 'sell']),
        ~OrderLog.internal_status.in_(['REQUESTED', 'REJECTED', 'REJECTED_BY_SAFETY_GATE',
                                       'LEGACY_ABSENCE_VERIFIED']),
    ).order_by(OrderLog.id.desc())
    fills = {}
    for order in query.yield_per(500) if environment else ():
        request, response, sync = map(_object, (order.request_payload, order.response_payload, order.last_sync_payload))
        if _simulated(request, response):
            continue
        if provider == 'kis' and request.get('paper') is True:
            continue
        submitted = _utc(order.submitted_at or order.created_at)
        if submitted is None or submitted > end:
            continue
        if any(request.get(key) is not None and request[key] != owner for key in ('owner_user_id', 'user_id')):
            continue
        if owner is None and (request.get('mode') in {'kis_live', 'kis_user_simulation'}
                              or any(str(request.get(key) or '').startswith('user_')
                                     for key in ('source', 'trigger_source'))):
            continue
        declared_env = request.get('credential_environment') or request.get('environment')
        if declared_env is not None and declared_env != environment:
            continue
        item = (_kis_fill(order, request, sync, environment) if provider == 'kis'
                else _alpaca_fill(order, request, sync if sync.get('id') else response, environment))
        if item is None:
            continue
        # Deduplicate cumulative sync snapshots before filtering/pagination.
        key = item['_key']
        previous = fills.get(key)
        if previous is None or item['quantity'] > previous['quantity']:
            item['id'] = f'{provider}:{order.id}'
            fills[key] = item
    items = [item for item in fills.values() if start <= item['_sort'] <= end]
    items.sort(key=lambda item: (item['_sort'], item['_key']), reverse=True)
    summary = {'count': len(items), 'buy_amount': 0.0, 'sell_amount': 0.0,
               'unknown_amount_count': 0, 'date_only_count': 0}
    unknown_sides = set()
    for item in items:
        if item['amount'] is None:
            summary['unknown_amount_count'] += 1
            unknown_sides.add(item['side'])
        else:
            summary[item['side'] + '_amount'] += item['amount']
        summary['date_only_count'] += item['time_precision'] == 'day'
    for side in unknown_sides:
        summary[side + '_amount'] = None
    page = [{key: value for key, value in item.items() if not key.startswith('_')}
            for item in items[offset:offset + limit]]
    return {
        'provider': provider, 'environment': environment, 'period': period,
        'start_at': start.isoformat(), 'end_at': end.astimezone(KST).isoformat(),
        'source': 'persisted_broker_executions', 'summary': summary,
        'items': page, 'next_offset': offset + limit if offset + limit < len(items) else None,
    }
