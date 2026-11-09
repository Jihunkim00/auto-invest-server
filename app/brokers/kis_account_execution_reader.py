"""Header-preserving account history GETs, separate from order reconciliation.

Reference: koreainvestment/open-trading-api, examples_llm/domestic_stock/
inquire_daily_ccld/inquire_daily_ccld.py. No submit/cancel transport is used.
"""
from __future__ import annotations

from dataclasses import dataclass
import time

PATH = '/uapi/domestic-stock/v1/trading/inquire-daily-ccld'
TR_IDS = {
    ('live', False): 'TTTC0081R', ('live', True): 'CTSC9215R',
    ('paper', False): 'VTTC0081R', ('paper', True): 'VTSC9215R',
}
BASE_URLS = {'live': 'https://openapi.koreainvestment.com:9443',
             'paper': 'https://openapivts.koreainvestment.com:29443'}


def execution_environment(value):
    value = str(value or '').strip().lower()
    return {'real': 'live', 'prod': 'live', 'vps': 'paper', 'demo': 'paper', 'mock': 'paper'}.get(value, value)


class ExecutionHistoryError(RuntimeError):
    def __init__(self, status='error', code='broker_read_failed'):
        self.status, self.code = status, code
        super().__init__(code)  # Fixed codes only; never raw HTTP/credential data.


@dataclass
class ExecutionReadBudget:
    max_calls: int = 48
    timeout_seconds: float = 45
    min_interval: float = 1
    clock: object = time.monotonic
    sleep: object = time.sleep

    def __post_init__(self):
        self.started = self.clock()
        self.calls = 0
        self.last_call = None

    def remaining(self):
        remaining = self.timeout_seconds - (self.clock() - self.started)
        if remaining <= 0:
            raise ExecutionHistoryError('incomplete', 'read_deadline_exceeded')
        return remaining

    def take(self):
        if self.calls >= self.max_calls:
            raise ExecutionHistoryError('incomplete', 'call_budget_exceeded')
        if self.last_call is not None:
            delay = max(0, self.min_interval - (self.clock() - self.last_call))
            if delay >= self.remaining():
                raise ExecutionHistoryError('incomplete', 'read_deadline_exceeded')
            if delay:
                self.sleep(delay)
        timeout = min(10, self.remaining())
        self.last_call = self.clock()
        self.calls += 1
        return timeout


def read_execution_page(*, credentials, get_token, send_get, budget,
                        start_date, end_date, older=False,
                        continuation='', fk='', nk='', execution_filter='01'):
    # Reconciliation must include unfilled/rejected orders. The home history
    # continues to request fills only; callers cannot change the GET endpoint.
    if execution_filter not in {'00', '01', '02'}:
        raise ExecutionHistoryError('incomplete', 'invalid_execution_filter')
    environment = execution_environment(credentials.get('environment'))
    account, product = str(credentials.get('account_no') or ''), str(credentials.get('account_product_code') or '')
    if (environment not in BASE_URLS or len(account) != 8 or not account.isdigit()
            or len(product) != 2 or not product.isdigit()
            or not credentials.get('app_key') or not credentials.get('app_secret')):
        raise ExecutionHistoryError('not_connected', 'account_not_configured')
    params = {
        'CANO': account, 'ACNT_PRDT_CD': product,
        'INQR_STRT_DT': start_date.strftime('%Y%m%d'),
        'INQR_END_DT': end_date.strftime('%Y%m%d'),
        'SLL_BUY_DVSN_CD': '00', 'CCLD_DVSN': execution_filter, 'INQR_DVSN': '00',
        'INQR_DVSN_3': '00', 'INQR_DVSN_1': '', 'PDNO': '',
        'ORD_GNO_BRNO': '', 'ODNO': '', 'EXCG_ID_DVSN_CD': 'ALL',
        'CTX_AREA_FK100': fk, 'CTX_AREA_NK100': nk,
    }
    for attempt in range(2):
        budget.remaining()
        token = get_token(attempt == 1)
        headers = {
            'Content-Type': 'application/json', 'Accept': 'application/json',
            'charset': 'UTF-8', 'custtype': 'P',
            'appkey': credentials['app_key'], 'appsecret': credentials['app_secret'],
            'authorization': f'Bearer {token}',
            'tr_id': TR_IDS[(environment, older)], 'tr_cont': continuation,
        }
        try:
            response = send_get(BASE_URLS[environment] + PATH, params=params,
                                headers=headers, timeout=budget.take())
            payload = response.json()
        except ExecutionHistoryError:
            raise
        except Exception:
            raise ExecutionHistoryError() from None
        budget.remaining()
        if not isinstance(payload, dict):
            raise ExecutionHistoryError('incomplete', 'invalid_response_shape')
        auth_error = (getattr(response, 'status_code', 500) in {401, 403}
                      or payload.get('msg_cd') in {'EGW00121', 'EGW00123', 'EGW00124'})
        if auth_error:
            if attempt == 0:
                continue
            raise ExecutionHistoryError('authentication_failed', 'broker_authentication_failed')
        if getattr(response, 'status_code', 500) >= 400 or str(payload.get('rt_cd')) != '0':
            raise ExecutionHistoryError()
        rows = payload.get('output1')
        response_headers = {str(k).lower(): v for k, v in (getattr(response, 'headers', None) or {}).items()}
        flag = str(response_headers.get('tr_cont', '')).strip().upper()
        if (not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
                or 'tr_cont' not in response_headers or flag not in {'', 'D', 'E', 'M', 'F'}
                or not isinstance(payload.get('ctx_area_fk100'), str)
                or not isinstance(payload.get('ctx_area_nk100'), str)):
            raise ExecutionHistoryError('incomplete', 'invalid_continuation_response')
        # An account field, when supplied by KIS, must agree with the request.
        for row in [payload, *rows]:
            fields = {str(k).lower(): str(v).strip() for k, v in row.items()}
            if (fields.get('cano', account) != account
                    or fields.get('acnt_prdt_cd', product) != product):
                raise ExecutionHistoryError('incomplete', 'response_scope_mismatch')
        return {'orders': rows, 'tr_cont': flag,
                'fk': str(payload['ctx_area_fk100']).strip(),
                'nk': str(payload['ctx_area_nk100']).strip()}
    raise ExecutionHistoryError('authentication_failed', 'broker_authentication_failed')
