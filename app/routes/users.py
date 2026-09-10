from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User, UserSettings, UserWatchlist
from app.schemas.user_data import (
    AdminUserCreateRequest,
    AdminUserStatusRequest,
    UserSettingsUpdateRequest,
    UserWatchlistCreateRequest,
)
from app.services.auth_dependencies import get_current_user, require_admin
from app.services.auth_service import revoke_all_sessions, user_payload_with_id


admin_router = APIRouter(prefix='/admin/users', tags=['admin-users'])
user_router = APIRouter(prefix='/users/me', tags=['user-data'])


def _managed_user(user: User) -> dict[str, object]:
    payload = user_payload_with_id(user)
    payload['is_active'] = bool(user.enabled)
    return payload


def _watchlist_item(row: UserWatchlist) -> dict[str, object]:
    return {
        'id': int(row.id),
        'user_id': int(row.user_id),
        'symbol': row.symbol,
        'provider': row.provider,
        'market': row.market,
        'created_at': row.created_at.isoformat() if row.created_at else None,
    }


def _settings_payload(row: UserSettings) -> dict[str, object]:
    try:
        settings = json.loads(row.settings_json or '{}')
    except (TypeError, ValueError):
        settings = {}
    if not isinstance(settings, dict):
        settings = {}
    return {
        'id': int(row.id),
        'user_id': int(row.user_id),
        'settings': settings,
        'settings_json': settings,
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }


def list_admin_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    users = db.query(User).order_by(User.id.asc()).all()
    items = [_managed_user(user) for user in users]
    return {'users': items, 'items': items, 'count': len(items), 'max_users': 5}


def create_admin_user(
    payload: AdminUserCreateRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    username = payload.username.strip()
    if not username or username.lower() == 'admin':
        raise HTTPException(status_code=400, detail='The admin username is reserved.')
    if db.query(User).count() >= 5 or db.query(User).filter(User.role == 'user').count() >= 4:
        raise HTTPException(status_code=409, detail='The maximum number of users has been reached.')
    if db.query(User).filter(User.username == username).first() is not None:
        raise HTTPException(status_code=409, detail='Username is already in use.')

    user = User(
        username=username,
        role='user',
        enabled=True,
        setup_completed=False,
        password_hash=None,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail='Username is already in use.') from exc
    db.refresh(user)
    return _managed_user(user)


def update_admin_user_status(
    user_id: int,
    payload: AdminUserStatusRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    if payload.enabled is None and payload.is_active is None:
        raise HTTPException(status_code=422, detail='enabled or is_active is required')
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail='User not found.')
    if user.role == 'admin':
        raise HTTPException(status_code=400, detail='The admin account cannot be deactivated.')
    user.enabled = payload.requested_enabled
    if not user.enabled:
        revoke_all_sessions(db, user)
    db.commit()
    db.refresh(user)
    return _managed_user(user)


def get_my_settings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if row is None:
        row = UserSettings(user_id=user.id, settings_json='{}')
        db.add(row)
        db.commit()
        db.refresh(row)
    return _settings_payload(row)


def update_my_settings(
    payload: UserSettingsUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    values = payload.values()
    row = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if row is None:
        row = UserSettings(user_id=user.id)
        db.add(row)
    row.settings_json = json.dumps(values, ensure_ascii=False, sort_keys=True)
    db.commit()
    db.refresh(row)
    return _settings_payload(row)


def get_my_watchlist(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        db.query(UserWatchlist)
        .filter(UserWatchlist.user_id == user.id)
        .order_by(UserWatchlist.id.asc())
        .all()
    )
    items = [_watchlist_item(row) for row in rows]
    return {'watchlist': items, 'items': items, 'count': len(items)}


def add_my_watchlist(
    payload: UserWatchlistCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    symbol = payload.symbol.strip().upper()
    provider = payload.provider.strip().lower()
    market = payload.market.strip().upper()
    if not symbol or not provider or not market:
        raise HTTPException(status_code=422, detail='symbol, provider, and market are required')
    existing = (
        db.query(UserWatchlist)
        .filter(
            UserWatchlist.user_id == user.id,
            UserWatchlist.symbol == symbol,
            UserWatchlist.provider == provider,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail='This symbol is already on the watchlist.')
    row = UserWatchlist(
        user_id=user.id,
        symbol=symbol,
        provider=provider,
        market=market,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail='This symbol is already on the watchlist.') from exc
    db.refresh(row)
    return _watchlist_item(row)


def remove_my_watchlist(
    symbol: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    normalized = symbol.strip().upper()
    rows = (
        db.query(UserWatchlist)
        .filter(
            UserWatchlist.user_id == user.id,
            UserWatchlist.symbol == normalized,
        )
        .all()
    )
    for row in rows:
        db.delete(row)
    db.commit()
    if not rows:
        raise HTTPException(status_code=404, detail='Watchlist symbol not found.')
    return {'ok': True, 'deleted': len(rows), 'symbol': normalized}


admin_router.add_api_route('', list_admin_users, methods=['GET'])
admin_router.add_api_route('', create_admin_user, methods=['POST'], status_code=201)
admin_router.add_api_route('/{user_id}/status', update_admin_user_status, methods=['PUT'])
user_router.add_api_route('/settings', get_my_settings, methods=['GET'])
user_router.add_api_route('/settings', update_my_settings, methods=['PUT'])
user_router.add_api_route('/watchlist', get_my_watchlist, methods=['GET'])
user_router.add_api_route('/watchlist', add_my_watchlist, methods=['POST'], status_code=201)
user_router.add_api_route('/watchlist/{symbol}', remove_my_watchlist, methods=['DELETE'])
