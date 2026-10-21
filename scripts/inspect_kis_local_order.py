"""Read-only local order and broker history evidence. No reconciliation writes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')
HISTORY_PATH = '/uapi/domestic-stock/v1/trading/inquire-daily-ccld'
HISTORY_TR_ID = 'TTTC0081R'
BASE = 'https://openapi.koreainvestment.com:9443'


def obj(raw):
    try:
        value = json.loads(raw or '{}')
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def masked(value):
    return '***' + str(value)[-4:] if value else None


def kst(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(KST).isoformat()


def open_readonly(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('existing_database_required')
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def local_evidence(db, *, order_id, username):
    user = db.execute('SELECT id,username,role FROM users WHERE username=?', (username,)).fetchone()
    if not user or user['role'] == 'admin':
        raise ValueError('regular_user_required')
    row = db.execute('SELECT * FROM orders WHERE id=? AND owner_user_id=?', (order_id, user['id'])).fetchone()
    if not row:
        raise ValueError('order_scope_mismatch')
    order = dict(row)
    if order['broker'] != 'kis' or order['market'] != 'KR':
        raise ValueError('order_scope_mismatch')
    request = obj(order.get('request_payload'))
    keys = ('id', 'owner_user_id', 'broker', 'market', 'symbol', 'side', 'order_type',
        'qty', 'requested_qty', 'filled_qty', 'remaining_qty', 'internal_status', 'broker_status',
        'broker_order_status', 'sync_error', 'profile_id', 'profile_key')
    local = {key: order.get(key) for key in keys}
    local.update({key + '_kst': kst(order.get(key)) for key in
        ('created_at', 'submitted_at', 'filled_at', 'last_synced_at')})
    local.update(broker_order_id_masked=masked(order.get('broker_order_id') or order.get('kis_odno')),
        trigger_source=order.get('trigger_source') or request.get('trigger_source'),
        request={key: request.get(key) for key in ('provider', 'mode', 'trigger_source',
            'authorization_mode', 'scheduler_slot', 'exit_reason', 'signal_id')},
        response={key: obj(order.get('response_payload')).get(key) for key in ('status', 'filled_qty', 'submitted_at')})
    runs = []
    for row in db.execute('SELECT * FROM trade_run_logs WHERE owner_user_id=? AND order_id=? ORDER BY id',
            (user['id'], order_id)):
        run = dict(row)
        payload = obj(run.get('response_payload'))
        runs.append({key: run.get(key) for key in ('id', 'owner_user_id', 'mode', 'result', 'reason', 'trigger_source')} |
            {key: payload.get(key) for key in ('real_order_submitted', 'broker_submit_called', 'scheduler_slot')})
    credential = db.execute('SELECT * FROM user_broker_credentials WHERE user_id=? AND provider=?',
        (user['id'], 'kis')).fetchone()
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'database_mode': 'ro/query_only',
        'database_write_count': 0, 'actual_kis_submit_count': 0, 'local_order': local,
        'user': dict(user), 'linked_runs': runs, 'history': {'status': 'NOT_CHECKED'}}
    signal = db.execute('SELECT id,owner_user_id,symbol,action,signal_status,trigger_source,'
        'related_order_id,created_at,approved_by_risk FROM signals WHERE id=? AND owner_user_id=?',
        (request.get('signal_id') if isinstance(request.get('signal_id'), int) else None, user['id'])).fetchone()
    report['linked_signal'] = dict(signal) if signal else None
    report['local_position_lifecycle_count'] = db.execute(
        'SELECT COUNT(*) FROM position_lifecycles WHERE owner_user_id=?', (user['id'],)).fetchone()[0]
    if credential:
        report['credential_metadata'] = {key: dict(credential).get(key) for key in
            ('user_id', 'provider', 'environment', 'created_at', 'updated_at')}
    return report, order, dict(credential) if credential else None


class ReadOnlyKisTransport:
    """Reject every URL except authentication and the three inquiry endpoints."""
    def __init__(self):
        import requests
        self.session = requests.Session()
        self.continuation = ''
        self.calls = []

    def get(self, url, **kwargs):
        allowed = {BASE + path for path in (HISTORY_PATH,
            '/uapi/domestic-stock/v1/trading/inquire-balance',
            '/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl')}
        if url not in allowed:
            raise ValueError('non_readonly_broker_endpoint_forbidden')
        headers = dict(kwargs.get('headers') or {})
        if url == BASE + HISTORY_PATH and self.continuation:
            headers['tr_cont'] = self.continuation
        kwargs['headers'] = headers
        kwargs['allow_redirects'] = False
        self.calls.append({'method': 'GET', 'path': url[len(BASE):], 'tr_id': headers.get('tr_id')})
        return self.session.get(url, **kwargs)

    def post(self, url, **kwargs):
        if url != BASE + '/oauth2/tokenP':
            raise ValueError('broker_post_forbidden_except_token')
        kwargs['allow_redirects'] = False
        self.calls.append({'method': 'POST', 'path': '/oauth2/tokenP'})
        return self.session.post(url, **kwargs)


def read_history(client, transport, *, start_date, end_date, max_pages=20):
    from app.services.user_broker_account_service import _require_kis_read_response
    cursor = ('', '')
    seen = set()
    rows = []
    token = client._token()
    for page in range(max_pages):
        if cursor in seen:
            raise ValueError('history_pagination_loop')
        seen.add(cursor)
        transport.continuation = 'N' if page else ''
        response = client._send_get(HISTORY_PATH, tr_id=HISTORY_TR_ID, token=token, params={
            'CANO': client.credentials['account_no'], 'ACNT_PRDT_CD': client.credentials['account_product_code'],
            'INQR_STRT_DT': start_date, 'INQR_END_DT': end_date, 'SLL_BUY_DVSN_CD': '00',
            'INQR_DVSN': '00', 'PDNO': '', 'CCLD_DVSN': '00', 'ORD_GNO_BRNO': '', 'ODNO': '',
            'INQR_DVSN_3': '00', 'INQR_DVSN_1': '', 'CTX_AREA_FK100': cursor[0],
            'CTX_AREA_NK100': cursor[1], 'EXCG_ID_DVSN_CD': 'ALL'})
        payload = _require_kis_read_response(response)
        values = payload.get('output1')
        if not isinstance(values, list) or any(not isinstance(row, dict) for row in values):
            raise ValueError('history_shape_invalid')
        rows.extend(values)
        if str(response.headers.get('tr_cont', '')).upper() not in {'M', 'F'}:
            return rows, page + 1
        cursor = (str(payload.get('ctx_area_fk100') or ''), str(payload.get('ctx_area_nk100') or ''))
        if not all(cursor):
            raise ValueError('history_cursor_missing')
    raise ValueError('history_incomplete')


def fetch_broker_evidence(report, order, credential):
    from app.services.broker_credential_crypto_service import BrokerCredentialCryptoService
    from app.services.user_broker_account_service import UserKisReadOnlyClient, UserKisTokenManager
    transport = ReadOnlyKisTransport()
    try:
        if not credential or credential['environment'] != 'live':
            raise ValueError('live_owner_credentials_required')
        credentials = BrokerCredentialCryptoService().decrypt(credential['encrypted_payload'],
            encryption_version=credential['encryption_version'])
        if credentials.get('environment') != 'live':
            raise ValueError('credential_environment_mismatch')
        client = UserKisReadOnlyClient(user_id=order['owner_user_id'], credentials=credentials,
            credential_identity='order-reconciliation-readonly', http_client=transport,
            token_manager=UserKisTokenManager(), timeout_seconds=15)
        created = kst(order.get('submitted_at') or order['created_at'])
        start = datetime.fromisoformat(created).strftime('%Y%m%d')
        end = datetime.now(KST).strftime('%Y%m%d')
        rows, pages = read_history(client, transport, start_date=start, end_date=end)
        target = str(order.get('kis_odno') or order.get('broker_order_id') or '').lstrip('0')
        exact = [row for row in rows if str(row.get('odno') or '').lstrip('0') == target]
        same_symbol = [row for row in rows if str(row.get('pdno') or '') == order['symbol']]
        def safe(row):
            return {key: row.get(key) for key in ('ord_dt', 'ord_tmd', 'pdno', 'sll_buy_dvsn_cd',
                'ord_qty', 'tot_ccld_qty', 'rmn_qty', 'psbl_qty', 'cncl_yn', 'rjct_qty', 'ord_dvsn_cd',
                'ord_dvsn_name', 'tot_ccld_amt', 'avg_prvs', 'excg_dvsn_cd')} | {'order_no_masked': masked(row.get('odno'))}
        report['history'] = {'status': 'VERIFIED_READ', 'complete': True, 'owner_user_id': order['owner_user_id'],
            'start_date': start, 'end_date': end, 'tr_id': HISTORY_TR_ID, 'exchange': 'ALL', 'pages': pages,
            'total_orders': len(rows), 'exact_matches': [safe(row) for row in exact],
            'same_symbol_orders': [safe(row) for row in same_symbol],
            'buy_order_count': sum(str(row.get('sll_buy_dvsn_cd')) == '02' for row in rows),
            'absence_is_not_proof_of_never_submitted': True}
        snapshot = client.get_snapshot()
        report['current_snapshot'] = {key: snapshot.get(key) for key in ('positions_reliable', 'open_orders_reliable')}
        report['current_snapshot'].update(positions_count=len(snapshot.get('positions') or []),
            open_orders_count=len(snapshot.get('open_orders') or []))
        from app.services.kis_order_reconciliation_service import propose_reconciliation, ReconciliationBlocked
        now = datetime.now(timezone.utc)
        scope = {'owner_user_id': order['owner_user_id'], 'provider': 'kis', 'environment': 'live',
            'broker_account_id': f'user:{order["owner_user_id"]}:kis:KR', 'checked_at': now.isoformat()}
        try:
            report['reconciliation_proposal'] = propose_reconciliation(order,
                history={**scope, 'complete': True, 'orders': rows}, snapshot={**snapshot, **scope}, now=now)
        except ReconciliationBlocked as exc:
            report['reconciliation_proposal'] = {'eligible': False, 'reason': str(exc)}
    except Exception as exc:
        details = getattr(exc, 'details', {})
        report['broker_read_error'] = {'exception_type': type(exc).__name__, **{
            key: details[key] for key in ('error_type', 'http_status', 'rt_cd', 'msg_cd', 'read_operation')
            if isinstance(details, dict) and key in details}}
        if report['history']['status'] == 'NOT_CHECKED':
            report['history'] = {'status': 'UNVERIFIED', 'complete': False}
    finally:
        report['transport_calls'] = transport.calls
        report['requires_user_approval_before_any_database_change'] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, type=Path)
    parser.add_argument('--user', required=True)
    parser.add_argument('--order-id', required=True, type=int)
    parser.add_argument('--with-history', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with open_readonly(args.database) as db:
        report, order, credential = local_evidence(db, order_id=args.order_id, username=args.user)
    if args.with_history:
        fetch_broker_evidence(report, order, credential)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + '\n', encoding='utf-8')
    print(rendered)


if __name__ == '__main__':
    main()
