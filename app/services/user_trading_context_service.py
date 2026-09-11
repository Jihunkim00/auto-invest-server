from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar

from sqlalchemy.orm import Query

from app.db.models import User


class UserTradingOwnershipError(ValueError):
    '''Raised when a user-owned record cannot be safely assigned.'''


_RecordT = TypeVar('_RecordT')


@dataclass(frozen=True)
class UserTradingContext:
    '''The non-secret owner context for future user trading operations.'''

    owner_user_id: int | None
    role: str

    @classmethod
    def from_user(cls, user: User) -> 'UserTradingContext':
        if user is None or user.id is None:
            raise UserTradingOwnershipError('authenticated_user_id_required')
        role = str(user.role or 'user').strip().lower()
        # Admin trading remains the legacy NULL-owner flow. An admin is never
        # converted into a synthetic regular-user owner.
        owner_user_id = None if role == 'admin' else int(user.id)
        return cls(owner_user_id=owner_user_id, role=role)

    @property
    def is_user_owned(self) -> bool:
        return self.owner_user_id is not None

    def filter_owned(self, query: Query, model: Any) -> Query:
        if self.owner_user_id is None:
            raise UserTradingOwnershipError('regular_user_owner_required')
        return query.filter(model.owner_user_id == self.owner_user_id)

    def stamp(self, record: _RecordT) -> _RecordT:
        '''Assign ownership without trusting a caller-provided owner field.'''

        if self.owner_user_id is None:
            raise UserTradingOwnershipError('regular_user_owner_required')
        if not hasattr(record, 'owner_user_id'):
            raise UserTradingOwnershipError('record_has_no_owner_field')
        setattr(record, 'owner_user_id', self.owner_user_id)
        return record

    def record_values(self, values: dict[str, Any] | None = None) -> dict[str, Any]:
        '''Return safe constructor values derived from this authenticated user.'''

        if self.owner_user_id is None:
            raise UserTradingOwnershipError('regular_user_owner_required')
        safe_values = dict(values or {})
        # An API payload or client helper may not override the authenticated
        # owner. The context always wins.
        safe_values.pop('owner_user_id', None)
        safe_values['owner_user_id'] = self.owner_user_id
        return safe_values


def user_trading_context(user: User) -> UserTradingContext:
    '''Build a context from the authenticated user, never from request data.'''

    return UserTradingContext.from_user(user)


def apply_user_owner(record: _RecordT, user: User) -> _RecordT:
    '''Convenience helper for future user-owned run/signal/order creation.'''

    return user_trading_context(user).stamp(record)
