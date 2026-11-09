"""Account-bound broker history. No OrderLog query or trading state mutation."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from datetime import UTC, date, datetime, time as daytime, timedelta
import hashlib
import json
import math
import threading
import time
from zoneinfo import ZoneInfo

from app.brokers.base import KisAuthError, KisConfigurationError
from app.brokers.kis_client import KisClient
from app.brokers.kis_account_execution_reader import ExecutionHistoryError, ExecutionReadBudget, execution_environment
from app.services.user_broker_account_service import (
    UserBrokerAccountService, UserBrokerAuthenticationError,
    UserBrokerCredentialsUnavailableError, UserBrokerEncryptionUnavailableError,
)

KST = ZoneInfo('Asia/Seoul')
PERIOD_DAYS = {'day': 1, 'week': 7, 'month': 30, 'year': 365}
MESSAGES = {
    'not_connected': '한국투자증권 계좌 연결이 필요합니다.',
    'authentication_failed': '한국투자증권 인증을 확인해 주세요.',
    'error': '거래 내역을 불러오지 못했습니다.',
    'incomplete': '일부 거래 내역을 확인하지 못했습니다.',
}


def period_dates(period, now):
    today = now.astimezone(KST).date()
    return today - timedelta(days=PERIOD_DAYS[period] - 1), today


def recent_boundary(today):
    # KIS's official legacy sample documents the history storage boundary by
    # month (e.g. April 25 includes January). Keep the split gap-free.
    month_index = today.year * 12 + today.month - 1 - 3
    return date(month_index // 12, month_index % 12 + 1, 1)


def history_windows(start, end, today):
    boundary = recent_boundary(today)
    windows = []
    for lower, upper, older in ((max(start, boundary), end, False),
                                (start, min(end, boundary - timedelta(days=1)), True)):
        while lower <= upper:
            window_end = min(lower + timedelta(days=29), upper)
            windows.append((lower, window_end, older))
            lower = window_end + timedelta(days=1)
    return windows


def _number(raw, *, allow_zero=False):
    try:
        value = float(str(raw).replace(',', ''))
        if math.isfinite(value) and (value >= 0 if allow_zero else value > 0):
            return value
    except (ValueError, TypeError, OverflowError):
        pass
    return None


def normalize_execution(raw, *, start, end, now, scope_key):
    row = {str(key).lower(): value for key, value in raw.items()}
    quantity = _number(row.get('tot_ccld_qty'), allow_zero=True)
    if quantity == 0:
        return None
    requested = _number(row.get('ord_qty'))
    if (quantity is None or requested is None or quantity > requested
            or not quantity.is_integer() or not requested.is_integer()):
        raise ExecutionHistoryError('incomplete', 'invalid_execution_quantity')
    # Broker history contains no application simulation rows; contradictory
    # simulation/error records must still never become visible trades.
    if (row.get('dry_run') is True or row.get('simulated') is True
            or str(row.get('status') or '').upper() in {'REJECTED', 'FAILED', 'SIMULATED', 'REQUESTED'}):
        return None
    side = {'02': 'buy', '01': 'sell'}.get(str(row.get('sll_buy_dvsn_cd') or ''))
    symbol, number = str(row.get('pdno') or ''), str(row.get('odno') or '').strip().lstrip('0')
    if side is None or len(symbol) != 6 or not symbol.isdigit() or not number:
        raise ExecutionHistoryError('incomplete', 'invalid_execution_identity')
    try:
        text = str(row.get('ord_dt') or '')
        trade_day = datetime.strptime(text, '%Y%m%d').date()
        if trade_day.strftime('%Y%m%d') != text or not start <= trade_day <= end:
            raise ValueError
        if row.get('ccld_dt') and str(row['ccld_dt']) != text:
            raise ValueError
        filled_at = None
        if row.get('ccld_tmd'):
            stamp = text + str(row['ccld_tmd'])
            filled_at = datetime.strptime(stamp, '%Y%m%d%H%M%S').replace(tzinfo=KST)
            if filled_at.strftime('%Y%m%d%H%M%S') != stamp or filled_at > now:
                raise ValueError
    except (ValueError, TypeError):
        raise ExecutionHistoryError('incomplete', 'invalid_execution_date') from None
    if row.get('rmn_qty') not in (None, ''):
        remaining = _number(row['rmn_qty'], allow_zero=True)
        if remaining is None or quantity + remaining > requested:
            raise ExecutionHistoryError('incomplete', 'invalid_remaining_quantity')
    price = _number(row.get('avg_prvs'))
    amount = _number(row.get('tot_ccld_amt'))
    if amount is None and price is not None:
        amount = _number(quantity * price)
    identity = (trade_day.isoformat(), str(row.get('ord_gno_brno') or ''), number)
    opaque_id = hashlib.sha256(json.dumps((scope_key, identity)).encode()).hexdigest()[:24]
    return {
        '_identity': identity, '_sort': filled_at or datetime.combine(trade_day, daytime(), KST),
        'id': 'kis:' + opaque_id, 'symbol': symbol, 'name': str(row.get('prdt_name') or '') or None,
        'side': side, 'filled_qty': quantity, 'avg_fill_price': price,
        'filled_amount': amount, 'currency': 'KRW', 'partial': quantity < requested,
        'trade_date': trade_day.isoformat(), 'executed_at': filled_at.isoformat() if filled_at else None,
        'time_precision': 'second' if filled_at else 'day',
    }


class ExecutionSnapshotCache:
    """Opaque owner/credential/account keys; successful normalized pages only."""
    def __init__(self, *, ttl=120, capacity=64):
        self.ttl, self.capacity = ttl, capacity
        self.lock = threading.Lock()
        self.entries = OrderedDict()

    def clear(self):
        with self.lock:
            self.entries.clear()

    def get(self, key):
        with self.lock:
            entry = self.entries.get(key)
            if entry is None or time.monotonic() - entry[0] > self.ttl:
                self.entries.pop(key, None)
                return None
            return deepcopy(entry[1])

    def put(self, key, value):
        with self.lock:
            self.entries[key] = (time.monotonic(), deepcopy(value))
            self.entries.move_to_end(key)
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)


EXECUTION_SNAPSHOTS = ExecutionSnapshotCache()


class KisAccountExecutionHistoryService:
    def __init__(self, *, account_service=None, admin_client_factory=KisClient,
                 now_provider=None, budget_factory=None, cache=None):
        self.account_service = account_service or UserBrokerAccountService()
        self.admin_client_factory = admin_client_factory
        self.now_provider = now_provider or (lambda: datetime.now(KST))
        self.budget_factory = budget_factory or (lambda period: ExecutionReadBudget(
            max_calls=48 if period == 'year' else 12,
            timeout_seconds=45 if period == 'year' else 15))
        self.cache = cache or EXECUTION_SNAPSHOTS

    def _client(self, db, user):
        client = (self.admin_client_factory() if user.role == 'admin'
                  else self.account_service.get_kis_read_only_client(db, user))
        if user.role == 'admin':
            if getattr(client, 'user_id', None) is not None:
                raise ExecutionHistoryError('not_connected', 'account_scope_mismatch')
            settings = client.settings
            credentials = {key: getattr(settings, 'kis_' + key, None) for key in (
                'app_key', 'app_secret', 'account_no', 'account_product_code')}
            credentials['environment'] = settings.kis_env
        else:
            if getattr(client, 'user_id', None) != user.id:
                raise ExecutionHistoryError('not_connected', 'account_scope_mismatch')
            credentials = client.credentials
        environment = execution_environment(credentials.get('environment'))
        if environment not in {'live', 'paper'}:
            raise ExecutionHistoryError('not_connected', 'account_not_configured')
        scope = hashlib.sha256(json.dumps((user.role, user.id, credentials,
                    getattr(client, 'credential_identity', None)), sort_keys=True).encode()).hexdigest()
        return client, environment, scope

    def read(self, db, user, *, period='day', limit=20, offset=0, as_of=None):
        now = self.now_provider().astimezone(KST)
        start, end = period_dates(period, as_of or now)
        result = {'provider': 'kis', 'market': 'KR', 'environment': None,
                  'source': 'kis_broker_executions', 'period': period,
                  'start_at': datetime.combine(start, daytime(), KST).isoformat(),
                  'end_at': (as_of or now).astimezone(KST).isoformat(),
                  'status': 'success', 'complete': True, 'count': None,
                  'total_buy_amount': None, 'total_sell_amount': None, 'items': [], 'next_offset': None}
        completed_pages = 0
        try:
            client, environment, scope = self._client(db, user)
            result['environment'] = environment
            snapshot_key = (scope, period, result['end_at'])
            if as_of is not None:
                snapshot = self.cache.get(snapshot_key)
                if snapshot is None:
                    raise ExecutionHistoryError('incomplete', 'snapshot_expired')
            else:
                windows = history_windows(start, end, now.date())
                if (any(older for _, _, older in windows) and now.weekday() < 5
                        and daytime(9) <= now.time().replace(tzinfo=None) < daytime(15, 30)):
                    raise ExecutionHistoryError('incomplete', 'historical_query_after_close')
                budget, fills = self.budget_factory(period), {}
                for lower, upper, older in windows:
                    fk, nk, continuation, seen = '', '', '', set()
                    for page_number in range(10):
                        page = client.inquire_account_executions_page(
                            budget=budget, start_date=lower, end_date=upper, older=older,
                            fk=fk, nk=nk, continuation=continuation)
                        completed_pages += 1
                        for raw in page['orders']:
                            item = normalize_execution(raw, start=lower, end=upper, now=now, scope_key=scope)
                            if item is not None:
                                previous = fills.get(item['_identity'])
                                if previous is None or item['filled_qty'] > previous['filled_qty']:
                                    fills[item['_identity']] = item
                        if len(fills) > 5000:
                            raise ExecutionHistoryError('incomplete', 'row_budget_exceeded')
                        if page['tr_cont'] not in {'M', 'F'}:
                            break
                        fk, nk = page['fk'], page['nk']
                        if (not fk and not nk) or (fk, nk) in seen or page_number == 9:
                            raise ExecutionHistoryError('incomplete', 'continuation_not_completed')
                        seen.add((fk, nk))
                        continuation = 'N'
                    budget.remaining()
                ordered = sorted(fills.values(), key=lambda item: (item['_sort'], item['_identity']), reverse=True)
                items = [{k: v for k, v in item.items() if not k.startswith('_')} for item in ordered]
                snapshot = {**result, 'count': len(items), 'items': items,
                            'unknown_amount_count': sum(item['filled_amount'] is None for item in items),
                            'broker_query_count': budget.calls}
                for side in ('buy', 'sell'):
                    amounts = [item['filled_amount'] for item in items if item['side'] == side]
                    snapshot['total_' + side + '_amount'] = None if None in amounts else sum(amounts)
                self.cache.put(snapshot_key, snapshot)
            result = deepcopy(snapshot)
            result['items'] = snapshot['items'][offset:offset + limit]
            result['next_offset'] = offset + limit if offset + limit < result['count'] else None
        except (LookupError, KisConfigurationError, UserBrokerCredentialsUnavailableError,
                UserBrokerEncryptionUnavailableError):
            result.update(status='not_connected', complete=False, code='account_not_configured')
        except (KisAuthError, UserBrokerAuthenticationError):
            result.update(status='authentication_failed', complete=False, code='broker_authentication_failed')
        except ExecutionHistoryError as exc:
            status = 'incomplete' if completed_pages and exc.status == 'error' else exc.status
            result.update(status=status, complete=False, code=exc.code)
        except Exception:
            result.update(status='incomplete' if completed_pages else 'error', complete=False, code='broker_read_failed')
        if result['status'] != 'success':
            result.update(count=None, total_buy_amount=None, total_sell_amount=None, items=[], next_offset=None)
            result['message'] = MESSAGES[result['status']]
        return result
