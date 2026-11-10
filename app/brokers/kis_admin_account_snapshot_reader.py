"""Complete GET-only account snapshots for manual reconciliation and preflight.

The ordinary list helpers do not preserve pagination headers. These diagnostics
must never mistake their first page for a reliable empty account.
"""
from datetime import datetime
import math
from zoneinfo import ZoneInfo

import requests

from app.brokers.kis_account_execution_reader import (
    ExecutionHistoryError, ExecutionReadBudget, execution_environment, read_account_page,
)


def _all_pages(client, budget, *, path, tr_id, params, rows_key):
    settings = client.settings
    credentials = {key: getattr(settings, 'kis_' + key, None) for key in (
        'account_no', 'account_product_code', 'app_key', 'app_secret')}
    credentials['environment'] = settings.kis_env
    rows, seen = [], set()
    continuation = ''
    for _ in range(20):
        page = read_account_page(credentials=credentials,
            get_token=lambda refresh: client.get_access_token(force_refresh=refresh).token,
            send_get=requests.get, budget=budget, path=path, tr_id=tr_id,
            params=params, continuation=continuation, rows_key=rows_key)
        rows.extend(page['orders'])
        if page['tr_cont'] in {'', 'D', 'E'}:
            return rows
        cursor = (page['fk'], page['nk'])
        if not all(cursor) or cursor in seen:
            raise ExecutionHistoryError('incomplete', 'invalid_continuation_response')
        seen.add(cursor)
        params = {**params, 'CTX_AREA_FK100': cursor[0], 'CTX_AREA_NK100': cursor[1]}
        continuation = 'N'
    raise ExecutionHistoryError('incomplete', 'call_budget_exceeded')


def _quantity(row, key):
    try:
        number = float(row[key])
    except (KeyError, TypeError, ValueError):
        raise ExecutionHistoryError('incomplete', 'invalid_response_shape') from None
    if not math.isfinite(number) or number < 0:
        raise ExecutionHistoryError('incomplete', 'invalid_response_shape')
    return number


def read_admin_account_snapshot(client, *, now: datetime):
    """Read every balance/cancelable-order page and all-exchange unfilled history."""
    if execution_environment(client.settings.kis_env) != 'live':
        raise ExecutionHistoryError('not_connected', 'live_account_required')
    budget = ExecutionReadBudget(max_calls=60, timeout_seconds=60)
    params = {'CANO': client.settings.kis_account_no,
              'ACNT_PRDT_CD': client.settings.kis_account_product_code,
              'CTX_AREA_FK100': '', 'CTX_AREA_NK100': ''}
    raw_positions = _all_pages(client, budget,
        path='/uapi/domestic-stock/v1/trading/inquire-balance', tr_id='TTTC8434R',
        rows_key='output1', params={**params, 'AFHR_FLPR_YN': 'N', 'OFL_YN': '',
            'INQR_DVSN': '02', 'UNPR_DVSN': '01', 'FUND_STTL_ICLD_YN': 'N',
            'FNCG_AMT_AUTO_RDPT_YN': 'N', 'PRCS_DVSN': '00'})
    raw_open = _all_pages(client, budget,
        path='/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl', tr_id='TTTC0084R',
        rows_key='output', params={**params, 'INQR_DVSN_1': '1', 'INQR_DVSN_2': '0'})
    # Cancelable orders alone cannot prove that no unfilled order exists.
    day = now.astimezone(ZoneInfo('Asia/Seoul')).date()
    continuation = fk = nk = ''
    seen = set()
    for _ in range(20):
        page = client.inquire_account_executions_page(budget=budget, start_date=day,
            end_date=day, execution_filter='02', older=False,
            continuation=continuation, fk=fk, nk=nk)
        raw_open.extend(page['orders'])
        if page['tr_cont'] in {'', 'D', 'E'}:
            break
        cursor = (page['fk'], page['nk'])
        if page['tr_cont'] not in {'M', 'F'} or not all(cursor) or cursor in seen:
            raise ExecutionHistoryError('incomplete', 'invalid_continuation_response')
        seen.add(cursor)
        fk, nk, continuation = *cursor, 'N'
    else:
        raise ExecutionHistoryError('incomplete', 'call_budget_exceeded')
    positions, open_orders = [], []
    for row in raw_positions:
        symbol, qty = str(row.get('pdno') or '').strip(), _quantity(row, 'hldg_qty')
        if not symbol:
            raise ExecutionHistoryError('incomplete', 'invalid_response_shape')
        if qty:
            positions.append({'symbol': symbol, 'qty': qty})
    for row in raw_open:
        symbol, order_id = str(row.get('pdno') or '').strip(), str(row.get('odno') or '').strip()
        side = {'01': 'sell', '02': 'buy'}.get(row.get('sll_buy_dvsn_cd'))
        key = 'rmn_qty' if 'rmn_qty' in row else 'psbl_qty'
        qty = _quantity(row, key)
        if not symbol or not order_id or side is None:
            raise ExecutionHistoryError('incomplete', 'invalid_response_shape')
        if qty:
            open_orders.append({'order_id': order_id, 'symbol': symbol,
                                'side': side, 'unfilled_qty': qty})
    budget.remaining()
    return positions, open_orders
