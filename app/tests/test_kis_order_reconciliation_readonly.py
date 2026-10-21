"""Maintenance evidence must remain read-only even if supplied a submit URL."""
from types import SimpleNamespace
import sqlite3

import pytest

from scripts.inspect_kis_local_order import BASE, HISTORY_PATH, ReadOnlyKisTransport, open_readonly, read_history


def test_database_inspection_connection_cannot_write_or_create(tmp_path):
    path = tmp_path / 'isolated.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE marker (value TEXT)')
        db.execute("INSERT INTO marker VALUES ('unchanged')")
    original = path.read_bytes()
    db = open_readonly(path)
    try:
        assert db.execute('SELECT value FROM marker').fetchone()[0] == 'unchanged'
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            db.execute("UPDATE marker SET value='changed'")
    finally:
        db.close()
    assert path.read_bytes() == original
    with pytest.raises(ValueError, match='existing_database_required'):
        open_readonly(tmp_path / 'missing.sqlite')
    assert not (tmp_path / 'missing.sqlite').exists()


def test_transport_allows_only_exact_inquiry_urls_and_token(monkeypatch):
    calls = []
    session = SimpleNamespace(
        get=lambda url, **kwargs: calls.append(('GET', url, kwargs)),
        post=lambda url, **kwargs: calls.append(('POST', url, kwargs)))
    monkeypatch.setattr('requests.Session', lambda: session)
    transport = ReadOnlyKisTransport()
    for url in (BASE + '/uapi/domestic-stock/v1/trading/order-cash',
            BASE + '/uapi/domestic-stock/v1/trading/order-rvsecncl',
            'https://untrusted.example/inquire-balance', BASE + HISTORY_PATH + '?redirect=1'):
        with pytest.raises(ValueError):
            transport.get(url)
        with pytest.raises(ValueError):
            transport.post(url)
    assert calls == []
    transport.get(BASE + HISTORY_PATH, headers={'tr_id': 'TTTC0081R'})
    transport.post(BASE + '/oauth2/tokenP', json={'fake': 'test'})
    assert len(calls) == 2 and all(call[2]['allow_redirects'] is False for call in calls)


class FakeHistoryClient:
    credentials = {'account_no': '11111111', 'account_product_code': '01'}

    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def _token(self):
        return 'fake'

    def _send_get(self, path, **kwargs):
        self.calls.append((path, kwargs))
        payload, continuation = next(self.pages)
        return SimpleNamespace(status_code=200, json=lambda: payload, headers={'tr_cont': continuation})


def test_history_collects_every_page_and_requests_all_sides_and_exchanges():
    client = FakeHistoryClient([
        ({'rt_cd': '0', 'output1': [{'odno': 'fake1'}], 'ctx_area_fk100': 'first', 'ctx_area_nk100': 'next'}, 'M'),
        ({'rt_cd': '0', 'output1': [{'odno': 'fake2'}]}, 'D')])
    rows, pages = read_history(client, SimpleNamespace(), start_date='20261014', end_date='20261022')
    assert pages == 2 and [row['odno'] for row in rows] == ['fake1', 'fake2']
    params = client.calls[1][1]['params']
    assert params['CTX_AREA_NK100'] == 'next' and params['EXCG_ID_DVSN_CD'] == 'ALL'
    assert params['SLL_BUY_DVSN_CD'] == params['CCLD_DVSN'] == '00' and params['ODNO'] == ''
    assert all(call[1]['tr_id'] == 'TTTC0081R' for call in client.calls)


@pytest.mark.parametrize('failure,reason', [('shape', 'history_shape_invalid'),
    ('cursor', 'history_cursor_missing'), ('loop', 'history_pagination_loop'), ('limit', 'history_incomplete')])
def test_partial_or_malformed_history_never_returns_complete(failure, reason):
    payload = {'rt_cd': '0', 'output1': [], 'ctx_area_fk100': 'first', 'ctx_area_nk100': 'next'}
    if failure == 'shape': payload['output1'] = {}
    if failure == 'cursor': payload['ctx_area_fk100'] = ''
    client = FakeHistoryClient([(payload, 'M'), (payload, 'M')])
    with pytest.raises(ValueError, match=reason):
        read_history(client, SimpleNamespace(), start_date='20261014', end_date='20261022',
            max_pages=1 if failure == 'limit' else 20)
