from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import OrderLog, StrategyProfile, User, UserBrokerCredential
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
