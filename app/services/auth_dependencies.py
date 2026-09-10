from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.database import get_db
from app.db.models import User
from app.services.auth_service import get_session_user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(get_settings().session_cookie_name)
    user = get_session_user(db, token)
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication is required.')
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != 'admin':
        raise HTTPException(status_code=403, detail='Administrator permission is required.')
    return user


def require_regular_user(user: User = Depends(get_current_user)) -> User:
    """Require a regular user for user-owned data endpoints.

    The admin account deliberately keeps using environment-backed broker
    credentials and must never be routed through this DB credential surface.
    """

    if user.role != 'user':
        raise HTTPException(
            status_code=403,
            detail='admin_uses_env_broker_credentials',
        )
    return user
