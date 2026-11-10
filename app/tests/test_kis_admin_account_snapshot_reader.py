from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.brokers.kis_account_execution_reader import ExecutionHistoryError, ExecutionReadBudget, read_execution_page
from app.brokers.kis_admin_account_snapshot_reader import read_admin_account_snapshot


def fake_client(monkeypatch, *, failure=None):
    calls = []
    credentials = {'environment': 'live', 'account_no': '11112222', 'account_product_code': '01',
        'app_key': 'fake', 'app_secret': 'fake'}
    settings = SimpleNamespace(**{'kis_' + key: value for key, value in credentials.items()
                                  if key != 'environment'}, kis_env='live')
    monkeypatch.setattr('app.brokers.kis_admin_account_snapshot_reader.ExecutionReadBudget',
        lambda **kwargs: ExecutionReadBudget(**kwargs, min_interval=0))

    def send_get(url, *, params, headers, timeout):
        calls.append((url, dict(params), dict(headers)))
        kind = 'balance' if url.endswith('inquire-balance') else 'history' if url.endswith('inquire-daily-ccld') else 'open'
        second = params['CTX_AREA_NK100'] != ''
        rows_key = 'output' if kind == 'open' else 'output1'
        rows = []
        if kind == 'balance' and second:
            rows = [{'pdno': '005930', 'hldg_qty': '1'}]
        elif kind == 'history' and second:
            rows = [{'pdno': '000660', 'odno': 'FAKE-OPEN', 'sll_buy_dvsn_cd': '02', 'rmn_qty': '2'}]
        payload = {'rt_cd': '0', rows_key: rows, 'ctx_area_fk100': '' if second else kind,
                   'ctx_area_nk100': '' if second else kind}
        flag = 'D' if second else 'M'
        if failure == 'missing_header' and kind == 'balance':
            return SimpleNamespace(status_code=200, json=lambda: payload, headers={})
        if failure == 'loop' and kind == 'balance':
            payload.update(ctx_area_fk100='same', ctx_area_nk100='same')
            flag = 'M'
        if failure == 'wrong_account' and kind == 'balance':
            payload['cano'] = '99999999'
        if failure == 'auth' and kind == 'balance':
            payload['rt_cd'] = '1'
            return SimpleNamespace(status_code=401, json=lambda: payload, headers={'tr_cont': flag})
        return SimpleNamespace(status_code=200, json=lambda: payload, headers={'tr_cont': flag})

    monkeypatch.setattr('requests.get', send_get)
    client = SimpleNamespace(settings=settings,
        get_access_token=lambda **kwargs: SimpleNamespace(token='fake-token'))
    client.inquire_account_executions_page = lambda **kwargs: read_execution_page(
        credentials=credentials, get_token=lambda refresh: 'fake-token', send_get=send_get, **kwargs)
    return client, calls


def test_complete_snapshot_does_not_ignore_holdings_or_orders_on_later_pages(monkeypatch):
    client, calls = fake_client(monkeypatch)
    positions, open_orders = read_admin_account_snapshot(client, now=datetime(2026, 11, 10, tzinfo=UTC))
    assert positions == [{'symbol': '005930', 'qty': 1}]
    assert open_orders == [{'order_id': 'FAKE-OPEN', 'symbol': '000660', 'side': 'buy', 'unfilled_qty': 2}]
    assert len(calls) == 6
    assert all(calls[index][2]['tr_cont'] == 'N' for index in (1, 3, 5))
    assert calls[-1][1]['CCLD_DVSN'] == '02'
    assert calls[-1][1]['EXCG_ID_DVSN_CD'] == 'ALL'


@pytest.mark.parametrize('failure', ['missing_header', 'loop', 'wrong_account', 'auth'])
def test_partial_snapshot_or_wrong_account_fails_closed(monkeypatch, failure):
    client, _ = fake_client(monkeypatch, failure=failure)
    with pytest.raises(ExecutionHistoryError):
        read_admin_account_snapshot(client, now=datetime(2026, 11, 10, tzinfo=UTC))
