from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import get_settings
from app.db.models import OrderLog, PositionExitRetryJob, PositionLifecycle, StrategyProfile, User, UserBrokerCredential
from app.services.account_trading_limit_service import (
    AccountLimitContext, AccountTradingLimitError, AccountTradingLimitService,
)
from app.services.broker_credential_crypto_service import BrokerCredentialCryptoService


@dataclass(frozen=True)
class KisOrderAccountScope:
    account: AccountLimitContext
    # Never serialize account numbers or authentication material into diagnostics.
    identity: tuple[str, str, str] = field(repr=False)


def _identity(credentials: dict[str, Any]) -> tuple[str, str, str]:
    environment = str(credentials.get('environment') or '').strip().lower()
    environment = {'real': 'live', 'prod': 'live', 'vps': 'paper', 'demo': 'paper', 'mock': 'paper'}.get(environment, environment)
    number = str(credentials.get('account_no') or '').strip().replace('-', '').replace(' ', '')
    product = str(credentials.get('account_product_code') or '').strip()
    if (environment not in {'live', 'paper'} or len(number) != 8 or not number.isdigit()
            or len(product) != 2 or not product.isdigit()):
        raise AccountTradingLimitError('account_scope_unavailable')
    return environment, number, product


def _settings_credentials(settings: Any) -> dict[str, Any]:
    return {key: getattr(settings, 'kis_' + key, None) for key in (
        'app_key', 'app_secret', 'account_no', 'account_product_code', 'base_url',
    )} | {'environment': getattr(settings, 'kis_env', None)}


def _owner_credentials(db: Session, owner_user_id: int | None) -> dict[str, Any]:
    if owner_user_id is None:
        return _settings_credentials(get_settings())
    row = db.query(UserBrokerCredential).filter_by(user_id=owner_user_id, provider='kis').populate_existing().one_or_none()
    if row is None:
        raise AccountTradingLimitError('account_scope_unavailable')
    try:
        credentials = BrokerCredentialCryptoService().decrypt(
            row.encrypted_payload, encryption_version=row.encryption_version,
        )
        if credentials.get('environment') != row.environment:
            raise ValueError('environment mismatch')
        return credentials
    except Exception:
        # Exception strings may contain credential data; expose only a fixed code.
        raise AccountTradingLimitError('account_scope_unavailable') from None


def _verify_order_owner(db: Session, order: OrderLog, account: AccountLimitContext) -> None:
    if str(order.broker).lower() != 'kis' or str(order.market or '').upper() != 'KR':
        raise AccountTradingLimitError('account_scope_mismatch')
    try:
        payload = json.loads(order.request_payload or '{}')
    except (TypeError, ValueError):
        raise AccountTradingLimitError('account_scope_unavailable') from None
    if not isinstance(payload, dict):
        raise AccountTradingLimitError('account_scope_unavailable')
    if account.legacy_admin and (
        any(str(payload.get(key) or '').startswith('user_') for key in ('source', 'trigger_source'))
        or payload.get('mode') in {'kis_live', 'kis_user_simulation'}
    ):
        raise AccountTradingLimitError('account_scope_mismatch')
    expected = account.owner_user_id
    # Explicit user metadata and profile ownership must agree even on NULL rows.
    for key in ('owner_user_id', 'user_id'):
        if payload.get(key) is not None and payload[key] != expected:
            raise AccountTradingLimitError('account_scope_mismatch')
    profile_key = order.profile_key or payload.get('automation_profile_key') or payload.get('profile_key')
    if order.profile_id or profile_key:
        query = db.query(StrategyProfile).populate_existing()
        profile = (query.filter_by(id=order.profile_id).one_or_none() if order.profile_id
                   else query.filter_by(profile_key=profile_key).one_or_none())
        if profile is None and not order.profile_id:
            profile = query.filter_by(profile_name=profile_key).one_or_none()
        allowed_owners = {None, expected} if account.legacy_admin else {expected}
        if profile is None or profile.owner_user_id not in allowed_owners:
            raise AccountTradingLimitError('account_scope_mismatch')
        provider = profile.provider or ('kis' if account.legacy_admin else '')
        market = profile.market or ('KR' if account.legacy_admin else '')
        if str(provider).lower() != 'kis' or str(market).upper() != 'KR':
            raise AccountTradingLimitError('account_scope_mismatch')


def resolve_order_account_scope(db: Session, *, order: OrderLog, client: Any) -> KisOrderAccountScope:
    if order.owner_user_id is None and db.query(User.id).filter(User.role == 'admin').count() != 1:
        raise AccountTradingLimitError('account_scope_unavailable')
    account = AccountTradingLimitService.resolve_account(db, owner_user_id=order.owner_user_id)
    _verify_order_owner(db, order, account)
    expected = _owner_credentials(db, order.owner_user_id)
    identity = _identity(expected)
    if account.legacy_admin:
        if getattr(client, 'user_id', None) is not None:
            raise AccountTradingLimitError('account_scope_mismatch')
        actual = _settings_credentials(getattr(client, 'settings', None))
        if actual.get('base_url') != expected.get('base_url'):
            raise AccountTradingLimitError('account_scope_mismatch')
        auth_manager = getattr(client, 'auth_manager', None)
        if auth_manager is not None and _settings_credentials(getattr(auth_manager, 'settings', None)) != actual:
            raise AccountTradingLimitError('account_scope_mismatch')
    else:
        if getattr(client, 'user_id', None) != account.owner_user_id:
            raise AccountTradingLimitError('account_scope_mismatch')
        actual = getattr(client, 'credentials', None)
        if not isinstance(actual, dict):
            raise AccountTradingLimitError('account_scope_unavailable')
    if _identity(actual) != identity:
        raise AccountTradingLimitError('account_scope_mismatch')
    for key in ('app_key', 'app_secret'):
        if not expected.get(key) or not actual.get(key):
            raise AccountTradingLimitError('account_scope_unavailable')
        if actual[key] != expected[key]:
            raise AccountTradingLimitError('account_scope_mismatch')
    return KisOrderAccountScope(account=account, identity=identity)


def order_matches_account(db: Session, *, order: OrderLog, scope: KisOrderAccountScope) -> bool:
    owner = None if scope.account.legacy_admin else scope.account.owner_user_id
    if order.owner_user_id == owner:
        # Unresolved rows from this owner always reserve the account, even if
        # old metadata is incomplete. Never rewrite or discard their status.
        return True
    if order.owner_user_id is None:
        admins = db.query(User).filter(User.role == 'admin').all()
        if len(admins) != 1:
            raise AccountTradingLimitError('account_scope_unavailable')
        legacy = AccountTradingLimitService.resolve_account(db, require_enabled=False)
        _verify_order_owner(db, order, legacy)
    return _identity(_owner_credentials(db, order.owner_user_id)) == scope.identity


def resolve_position_account_scope(db: Session, *, client: Any) -> KisOrderAccountScope:
    # A transient context object; it is never added to the session or submitted.
    context = OrderLog(owner_user_id=getattr(client, 'user_id', None), broker='kis',
                       market='KR', request_payload='{}')
    return resolve_order_account_scope(db, order=context, client=client)


def assert_lifecycle_owner(db: Session, row: PositionLifecycle, owner_user_id: int | None) -> None:
    if row.owner_user_id != owner_user_id:
        raise AccountTradingLimitError('account_scope_mismatch')
    entry = db.get(OrderLog, row.entry_order_id) if row.entry_order_id > 0 else None
    if entry is not None and entry.owner_user_id != row.owner_user_id:
        raise AccountTradingLimitError('account_scope_mismatch')


def kis_client_cache_scope(client: Any) -> str | None:
    """Opaque credential-bound cache key; never a user-visible diagnostic."""
    owner = getattr(client, 'user_id', None)
    credentials = (getattr(client, 'credentials', None) if owner is not None
                   else _settings_credentials(getattr(client, 'settings', None)))
    if not isinstance(credentials, dict):
        return None
    try:
        identity = _identity(credentials)
    except AccountTradingLimitError:
        return None
    if not credentials.get('app_key') or not credentials.get('app_secret'):
        return None
    value = (owner, *identity, credentials['app_key'], credentials['app_secret'],
             credentials.get('base_url'), getattr(client, 'credential_identity', None))
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()


def position_management_block_reason(
    db: Session, *, owner_user_id: int | None,
    scope: KisOrderAccountScope | None = None, allow_own_open: bool = False,
    with_evidence: bool = False,
) -> str | dict[str, Any] | None:
    """Account-wide unresolved exits take priority over new entries."""
    def matches(owner: int | None, *, order: OrderLog | None = None) -> bool:
        nonlocal scope
        if owner == owner_user_id:
            return True
        if scope is None:
            account = AccountTradingLimitService.resolve_account(db, owner_user_id=owner_user_id)
            scope = KisOrderAccountScope(account, _identity(_owner_credentials(db, owner_user_id)))
        context = order if order is not None else OrderLog(
            owner_user_id=owner, broker='kis', market='KR', request_payload='{}')
        return order_matches_account(db, order=context, scope=scope)

    for row in db.query(PositionLifecycle).filter(PositionLifecycle.status.in_(['open', 'closing'])).all():
        assert_lifecycle_owner(db, row, row.owner_user_id)
        if matches(row.owner_user_id):
            if allow_own_open and row.owner_user_id == owner_user_id and row.status == 'open':
                continue
            if with_evidence:
                return {'reason': 'position_exit_in_progress' if row.status == 'closing' else 'position_management_priority',
                        'duplicate_check_source': 'local_position_lifecycle', 'symbol': row.symbol,
                        'lifecycle_id': row.id, 'lifecycle_status': row.status}
            return 'position_management_priority'
    for job in db.query(PositionExitRetryJob).filter(
        PositionExitRetryJob.provider == 'kis', PositionExitRetryJob.market == 'KR',
        PositionExitRetryJob.status.in_(['pending', 'running']),
    ).all():
        owner = job.owner_user_id
        user = db.get(User, owner) if owner is not None else None
        if user is not None and user.role == 'admin':
            owner = None  # Retry metadata can use the verified admin profile ID.
        if matches(owner):
            return ({'reason': 'kis_exit_read_retry_pending', 'duplicate_check_source': 'local_exit_retry',
                     'retry_job_id': job.id} if with_evidence else 'kis_exit_read_retry_pending')
    for order in db.query(OrderLog).filter(
        OrderLog.broker == 'kis', OrderLog.side == 'sell',
        OrderLog.internal_status.in_(['REQUESTED', 'SUBMITTED', 'ACCEPTED', 'PENDING',
            'PENDING_SUBMIT', 'PARTIALLY_FILLED', 'UNKNOWN_STALE', 'SYNC_FAILED']),
    ).all():
        if matches(order.owner_user_id, order=order):
            if with_evidence:
                return {'reason': 'local_unresolved_sell_order', 'duplicate_check_source': 'local_order_log',
                        'local_order_id': order.id, 'symbol': order.symbol, 'side': 'sell',
                        'order_status': order.internal_status,
                        'broker_order_id_masked': '***' + str(order.broker_order_id or '')[-4:]}
            return 'duplicate_open_sell_order'
    return None


def find_account_open_order(db: Session, *, owner_user_id: int | None, symbol: str) -> OrderLog | None:
    scope = None
    rows = db.query(OrderLog).filter(
        OrderLog.broker == 'kis', func.upper(OrderLog.symbol) == symbol.strip().upper(),
        OrderLog.internal_status.in_(['REQUESTED', 'SUBMITTED', 'ACCEPTED', 'PENDING',
            'PENDING_SUBMIT', 'PARTIALLY_FILLED', 'UNKNOWN_STALE', 'SYNC_FAILED']),
    ).order_by(OrderLog.id.desc()).all()
    for row in rows:
        if row.owner_user_id == owner_user_id:
            return row
        if scope is None:
            account = AccountTradingLimitService.resolve_account(db, owner_user_id=owner_user_id)
            scope = KisOrderAccountScope(account, _identity(_owner_credentials(db, owner_user_id)))
        if order_matches_account(db, order=row, scope=scope):
            return row
    return None
