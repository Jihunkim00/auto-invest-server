"""Read-only evidence for manual reconciliation; this script cannot update orders."""
import argparse
import json
from pathlib import Path
import sqlite3


def inspect_order(db_path, order_id):
    path = Path(db_path).resolve(strict=True)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        fields = ('id', 'owner_user_id', 'broker', 'market', 'symbol', 'side',
                  'internal_status', 'broker_order_id', 'kis_odno', 'submitted_at',
                  'filled_qty', 'created_at', 'error_message', 'response_payload')
        available = {row['name'] for row in conn.execute('PRAGMA table_info(orders)')}
        selected = [field for field in fields if field in available]
        if not selected:
            return {'order_id': order_id, 'result': 'orders_table_unavailable', 'db_modified': False}
        row = conn.execute(f'SELECT {", ".join(selected)} FROM orders WHERE id = ?', (order_id,)).fetchone()
        if row is None:
            return {'order_id': order_id, 'result': 'order_not_found', 'db_modified': False}
        order = dict(row)
        try:
            response = json.loads(order.pop('response_payload', None) or '{}')
        except (TypeError, ValueError):
            response = {}
        order['submission_evidence'] = {key: response.get(key) for key in (
            'status', 'reason', 'broker_submit_called', 'real_order_submitted')}
        reservation_fields = {r['name'] for r in conn.execute('PRAGMA table_info(automation_profile_buy_reservations)')}
        reservations = []
        if 'order_id' in reservation_fields:
            safe = [key for key in ('id', 'order_id', 'status', 'block_reason', 'scheduler_slot_kst') if key in reservation_fields]
            reservations = [dict(r) for r in conn.execute(
                f'SELECT {", ".join(safe)} FROM automation_profile_buy_reservations WHERE order_id = ?', (order_id,))]
        return {'order': order, 'reservations': reservations, 'db_modified': False,
                'result': 'inspection_only_manual_broker_evidence_and_approval_required'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='auto_invest.db')
    parser.add_argument('--order-id', type=int, default=18)
    args = parser.parse_args()
    print(json.dumps(inspect_order(args.db, args.order_id), ensure_ascii=False, indent=2))
