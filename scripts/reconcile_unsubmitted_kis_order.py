"""Review by default. Apply only a reviewed digest with an admin approval reference.

No evidence JSON is accepted. Proof comes from the execution journal in the DB;
broker evidence is freshly read from KIS GETs. This script never submits orders.
"""
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.models import BrokerAuthToken
from app.services.kis_order_reconciliation_service import ReconciliationBlocked
from app.services.kis_unsubmitted_order_reconciliation_service import (
    KisUnsubmittedOrderReconciliationService, read_admin_reconciliation_evidence,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--order-id', type=int, required=True)
    parser.add_argument('--admin-user-id', type=int, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--apply-plan', type=Path)
    parser.add_argument('--approve-digest')
    parser.add_argument('--approval-reference')
    args = parser.parse_args()
    if args.apply_plan and (not args.approve_digest or not args.approval_reference):
        parser.error('apply requires --approve-digest and --approval-reference')
    settings = get_settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != 'sqlite' or not url.database:
        parser.error('this operator tool requires a local SQLite database')
    source = Path(url.database).resolve()
    if args.output and args.output.resolve() == source:
        parser.error('output must not overwrite the database')
    if args.apply_plan:
        engine = create_engine(settings.database_url)
    else:
        engine = create_engine('sqlite://', poolclass=StaticPool, creator=lambda:
            sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, check_same_thread=False))
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
            service = KisUnsubmittedOrderReconciliationService(
                lambda session, order, now: read_admin_reconciliation_evidence(session, order, now, client=client))
            if args.apply_plan:
                plan = json.loads(args.apply_plan.read_text(encoding='utf-8'))
                if plan['order_id'] != args.order_id:
                    raise ReconciliationBlocked('plan_order_mismatch')
                result = service.apply(db, plan=plan, admin_user_id=args.admin_user_id,
                    approval_digest=args.approve_digest, approval_reference=args.approval_reference)
            else:
                result = service.propose(db, order_id=args.order_id, admin_user_id=args.admin_user_id)
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(rendered, encoding='utf-8')
        print(rendered)
    except ReconciliationBlocked as error:
        print(json.dumps({'status': 'blocked', 'reason': str(error), 'database_repair_applied': False}))
        return 2
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}))
        return 1
    finally:
        engine.dispose()
        memory.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
