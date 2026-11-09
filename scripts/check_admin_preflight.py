"""Read-only preflight for the selected Admin KIS account."""

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.models import BrokerAuthToken
from app.services.admin_preflight_service import check_admin_preflight


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', required=True, help='Trading date in YYYY-MM-DD')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--scheduler-health-url', default='http://127.0.0.1:8000/scheduler/health')
    args = parser.parse_args()
    try:
        parsed_health_url = urlparse(args.scheduler_health_url)
        if parsed_health_url.scheme != 'http' or parsed_health_url.hostname not in {
            '127.0.0.1', 'localhost', '::1',
        }:
            parser.error('--scheduler-health-url must use a local HTTP endpoint')
        import requests
        health_session = requests.Session()
        health_session.trust_env = False
        try:
            health_response = health_session.get(args.scheduler_health_url, timeout=2)
            health_body = health_response.json() if health_response.status_code == 200 else None
            scheduler_health = health_body if isinstance(health_body, dict) else None
        except Exception:
            scheduler_health = None
        finally:
            health_session.close()
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    except ValueError:
        parser.error('--date must use YYYY-MM-DD')

    settings = get_settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != 'sqlite' or not url.database:
        parser.error('this read-only tool requires a local SQLite database')
    source = Path(url.database).resolve()
    source_hash_before = hashlib.sha256(source.read_bytes()).hexdigest()
    if args.output and args.output.resolve() == source:
        parser.error('output must not overwrite the database')
    engine = create_engine('sqlite://', poolclass=StaticPool, creator=lambda: sqlite3.connect(
        source.as_uri() + '?mode=ro', uri=True, check_same_thread=False))
    memory = create_engine('sqlite:///:memory:', poolclass=StaticPool)
    BrokerAuthToken.__table__.create(memory)
    try:
        with sessionmaker(bind=engine, autoflush=False)() as db, sessionmaker(bind=memory)() as tokens:
            db.execute(text('PRAGMA query_only=ON'))
            for cached in db.query(BrokerAuthToken).filter_by(provider='kis', environment=settings.kis_env):
                tokens.add(BrokerAuthToken(provider=cached.provider, environment=cached.environment,
                    token_type=cached.token_type, token_value=cached.token_value,
                    expires_at=cached.expires_at, issued_at=cached.issued_at))
            tokens.commit()
            client = KisClient(settings, KisAuthManager(settings, db=tokens))
            report = check_admin_preflight(db, target_date=target_date,
                now=datetime.now(UTC), kis_client=client, scheduler_health=scheduler_health)
    except Exception:
        report = {'status': 'UNKNOWN', 'target_date': args.date,
                  'reason_codes': ['preflight_read_failed'],
                  'new_broker_mutation_calls': 0, 'operating_database_modified': False}
    finally:
        engine.dispose()
        memory.dispose()

    report['new_broker_mutation_calls'] = 0
    report['operating_database_modified'] = False
    report['operating_database_hash_unchanged'] = (
        source_hash_before == hashlib.sha256(source.read_bytes()).hexdigest())
    encoded = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + '\n', encoding='utf-8')
    print(encoded)
    return 0 if report.get('status') == 'READY' else 2


if __name__ == '__main__':
    raise SystemExit(main())
