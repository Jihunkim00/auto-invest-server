"""Review by default; legacy Admin order #18 requires a separately approved digest.

Only KIS read endpoints are used to build/revalidate evidence. The apply path
changes local order/accounting records only and never calls submit/cancel APIs.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.models import BrokerAuthToken
from app.services.kis_order_reconciliation_service import ReconciliationBlocked
from app.services.kis_legacy_admin_reconciliation_service import (
    KisLegacyAdminOrderReconciliationService,
    read_legacy_admin_broker_evidence,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--order-id', type=int, default=18)
    parser.add_argument('--admin-user-id', type=int, default=1)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--apply-plan', type=Path)
    parser.add_argument('--approve-digest')
    parser.add_argument('--approval-reference')
    args = parser.parse_args()
    if args.order_id != 18 or args.admin_user_id != 1:
        parser.error('legacy repair is restricted to Admin user 1 and order #18')
    if args.apply_plan and (not args.approve_digest or not args.approval_reference):
        parser.error('apply requires --approve-digest and --approval-reference')
    if not args.apply_plan and (args.approve_digest or args.approval_reference):
        parser.error('approval fields are valid only with --apply-plan')

    settings = get_settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != 'sqlite' or not url.database:
        parser.error('this operator tool requires a local SQLite database')
    source = Path(url.database).resolve()
    source_hash_before = hashlib.sha256(source.read_bytes()).hexdigest()
    if args.output and args.output.resolve() == source:
        parser.error('output must not overwrite the database')
    if args.apply_plan:
        engine = create_engine(settings.database_url)
    else:
        engine = create_engine('sqlite://', poolclass=StaticPool, creator=lambda: sqlite3.connect(
            source.as_uri() + '?mode=ro', uri=True, check_same_thread=False))
    memory = create_engine('sqlite:///:memory:', poolclass=StaticPool)
    BrokerAuthToken.__table__.create(memory)
    try:
        with sessionmaker(bind=engine, autoflush=False)() as db, sessionmaker(bind=memory)() as tokens:
            if not args.apply_plan:
                db.execute(text('PRAGMA query_only=ON'))
            for cached in db.query(BrokerAuthToken).filter_by(provider='kis', environment=settings.kis_env):
                tokens.add(BrokerAuthToken(provider=cached.provider, environment=cached.environment,
                    token_type=cached.token_type, token_value=cached.token_value,
                    expires_at=cached.expires_at, issued_at=cached.issued_at))
            tokens.commit()
            client = KisClient(settings, KisAuthManager(settings, db=tokens))
            service = KisLegacyAdminOrderReconciliationService(
                lambda session, order, now: read_legacy_admin_broker_evidence(
                    session, order, now, client=client))
            if args.apply_plan:
                plan = json.loads(args.apply_plan.read_text(encoding='utf-8'))
                if plan.get('order_id') != 18 or plan.get('protocol') != 'legacy_admin_broker_absence_v1':
                    raise ReconciliationBlocked('plan_scope_mismatch')
                result = service.apply(db, plan=plan, admin_user_id=1,
                    approval_digest=args.approve_digest, approval_reference=args.approval_reference)
                payload = {'mode': 'applied', 'result': result,
                           'new_broker_mutation_calls': 0}
            else:
                plan = service.propose(db, order_id=18, admin_user_id=1)
                payload = {'mode': 'review_only', 'plan': plan,
                           'new_broker_mutation_calls': 0,
                           'operating_database_modified': False,
                           'approval_required': True}
    except ReconciliationBlocked as exc:
        payload = {'mode': 'blocked', 'reason': str(exc),
                   'new_broker_mutation_calls': 0}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    except Exception:
        payload = {'mode': 'blocked', 'reason': 'legacy_review_unavailable',
                   'new_broker_mutation_calls': 0}
    finally:
        engine.dispose()
        memory.dispose()

    payload['operating_database_hash_unchanged'] = (
        source_hash_before == hashlib.sha256(source.read_bytes()).hexdigest())
    if not args.apply_plan:
        payload['operating_database_modified'] = False
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + '\n', encoding='utf-8')
    print(encoded)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
