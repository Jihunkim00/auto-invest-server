"""Opt-in real-data replay. The source is opened read-only; only memory changes.

If #18 was already repaired, reconstruct its REQUESTED state from the stored
audit before-state inside the clone. This is explicitly a historical replay,
not fresh KIS evidence or permission to change the operating database.
"""
from datetime import UTC, date, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import AutomationProfileBuyReservation, KisLegacyOrderReconciliation, OrderLog, TradeRunLog
from app.services.account_trading_limit_service import AccountTradingLimitService
from app.services.admin_preflight_service import check_admin_preflight
from app.services.kis_daily_entry_accounting import daily_entry_counts
from app.services.kis_legacy_admin_reconciliation_service import KisLegacyAdminOrderReconciliationService, _profile_scope
from app.services.kis_order_reconciliation_service import fingerprint


def test_real_operating_clone_approved_recovery_and_0840_preflight(monkeypatch):
    source_arg = os.environ.get('AUTO_INVEST_ADMIN_LEGACY_CLONE')
    if not source_arg:
        pytest.skip('provide AUTO_INVEST_ADMIN_LEGACY_CLONE for the opt-in real-data replay')
    source = Path(source_arg).resolve()
    source_hash = sha256(source.read_bytes()).hexdigest()
    clone = sqlite3.connect(':memory:', check_same_thread=False)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as readonly:
        readonly.backup(clone)
    engine = create_engine('sqlite://', poolclass=StaticPool, creator=lambda: clone)
    Base.metadata.create_all(engine)
    at_0840 = datetime(2026, 11, 9, 23, 40, tzinfo=UTC)
    reconstructed = False

    class FakeBroker:
        settings = SimpleNamespace(kis_env='live')
        reads = 0

        def __call__(self, db, order, now):
            self.reads += 1
            return {
                'provider': 'kis', 'owner_user_id': None, 'broker_account_id': 'admin:kis:KR',
                'environment': 'live', 'checked_at': now.isoformat(), 'complete': True,
                'execution_filter': '00', 'exchange_scope': 'ALL', 'history_date': '2026-10-28',
                'history_page_count': 1, 'history_orders': [], 'open_orders': [], 'positions': [],
                'open_orders_reliable': True, 'positions_reliable': True,
                'account_scope_digest': 'a' * 64, 'selected_profile': _profile_scope(db, order, 1, now),
            }

        def read_reconciliation_account_snapshot(self, *, now):
            return [], []

    try:
        with Session(engine) as db:
            order = db.get(OrderLog, 18)
            original_others = {key: fingerprint(db.get(OrderLog, key)) for key in (13, 19)}
            audit = db.query(KisLegacyOrderReconciliation).filter_by(order_id=18).one_or_none()
            if audit is not None:
                assert audit.terminal_fingerprint == fingerprint(order)
                before = json.loads(audit.before_state_json)
                for key, value in before.items():
                    if value is not None and isinstance(OrderLog.__table__.columns[key].type, DateTime):
                        value = datetime.fromisoformat(value)
                    setattr(order, key, value)
                assert fingerprint(order) == audit.original_fingerprint
                # Remove only the previously approved repair artifacts in memory.
                db.query(TradeRunLog).filter_by(order_id=18, mode='kis_legacy_reconciliation').delete()
                db.delete(audit)
                reservation = db.get(AutomationProfileBuyReservation, 10)
                reservation.status, reservation.block_reason = 'reserved', None
                db.commit()
                reconstructed = True
            assert order.internal_status == 'REQUESTED'
            before_payloads = (order.request_payload, order.response_payload)
            broker = FakeBroker()
            service = KisLegacyAdminOrderReconciliationService(broker, now_provider=lambda: at_0840)
            import app.services.admin_preflight_service as preflight_module
            monkeypatch.setattr(preflight_module, 'resolve_position_account_scope', lambda *a, **kw: None)

            def report():
                return check_admin_preflight(db, target_date=date(2026, 11, 10), now=at_0840,
                    kis_client=broker, scheduler_health={'scheduler_health_status': 'healthy'})

            before = report()
            assert daily_entry_counts(db, now=at_0840) == (0, 1)
            assert before['entry_capacity']['remaining_entry_capacity'] == 0
            limits = AccountTradingLimitService()
            before_amount = limits.calculate(db, symbol='036460', positions=[],
                profile_order_cap=500000, available_cash=1000000)['pending_buy_exposure_krw']
            assert before_amount == 258300
            plan = service.propose(db, order_id=18, admin_user_id=1)
            service.apply(db, plan=plan, admin_user_id=1,
                approval_digest=plan['approval_digest'], approval_reference='TEST-ONLY-REAL-DATA-CLONE')
            after = report()
            assert daily_entry_counts(db, now=at_0840) == (0, 0)
            assert after['entry_capacity']['remaining_entry_capacity'] == 1
            after_amount = limits.calculate(db, symbol='036460', positions=[],
                profile_order_cap=500000, available_cash=1000000)['pending_buy_exposure_krw']
            assert after_amount == 0
            assert after['status'] == 'READY'
            assert db.get(AutomationProfileBuyReservation, 10).status == 'blocked'
            assert (order.request_payload, order.response_payload) == before_payloads
            assert all(fingerprint(db.get(OrderLog, key)) == digest for key, digest in original_others.items())
            assert broker.reads == 2
            artifact = {'source_read_only': True, 'reconstructed_from_existing_audit': reconstructed,
                'broker': 'FakeBroker', 'real_kis_mutation_calls': 0,
                'before': before['entry_capacity'], 'after': after['entry_capacity'],
                'reserved_amount_before': before_amount, 'reserved_amount_after': after_amount,
                'preflight_0840_before': before['status'], 'preflight_0840_after': after['status'],
                'order13_and_order19_unchanged': True,
                'source_hash_unchanged': sha256(source.read_bytes()).hexdigest() == source_hash}
            output_arg = os.environ.get('AUTO_INVEST_ADMIN_LEGACY_REPORT')
            if output_arg:
                output = Path(output_arg).resolve()
                assert output != source
                output.write_text(json.dumps(artifact, indent=2) + '\n', encoding='utf-8')
    finally:
        engine.dispose()
    assert sha256(source.read_bytes()).hexdigest() == source_hash
