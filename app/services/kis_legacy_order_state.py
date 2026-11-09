"""Shared accounting semantics for explicitly approved legacy KIS repairs."""

from app.db.models import KisLegacyOrderReconciliation
from app.services.kis_order_reconciliation_service import fingerprint
from sqlalchemy import inspect


LEGACY_ABSENCE_VERIFIED = 'LEGACY_ABSENCE_VERIFIED'


def legacy_audit_table_exists(db) -> bool:
    return inspect(db.get_bind()).has_table('kis_legacy_order_reconciliations')


def verified_legacy_absence(db, order) -> bool:
    if order is None or str(order.internal_status or '').upper() != LEGACY_ABSENCE_VERIFIED:
        return False
    if not legacy_audit_table_exists(db):
        return False
    audit = db.query(KisLegacyOrderReconciliation).filter_by(order_id=order.id).one_or_none()
    return bool(
        audit is not None
        and audit.owner_user_id is None
        and order.owner_user_id is None
        and audit.broker_account_id == 'admin:kis:KR'
        and audit.approved_by_user_id == audit.policy_user_id
        and audit.approval_reference
        and audit.evidence_digest
        and audit.terminal_fingerprint == fingerprint(order)
    )
