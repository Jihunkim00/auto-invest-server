"""Single-admin authentication for the application shell.

Operational endpoints intentionally do not depend on this service in
PR122-A. It owns only the bootstrap user, password hashes, and web sessions.
"""

import base64
import binascii
import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AuthSession, User

ADMIN_USERNAME = "admin"
_PASSWORD_SCHEME = "scrypt"
_SCRYPT_N = 16_384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_SALT_BYTES = 16
_SCRYPT_KEY_BYTES = 64


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def hash_password(password: str) -> str:
    """Return a versioned, salted, memory-hard password hash."""

    salt = secrets.token_bytes(_SCRYPT_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_KEY_BYTES,
    )
    encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii")
    return (
        f"{_PASSWORD_SCHEME}${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}"
        f"${encode(salt)}${encode(digest)}"
    )


def verify_password(password: str, encoded_hash: str | None) -> bool:
    if not encoded_hash:
        return False

    try:
        scheme, n_text, r_text, p_text, salt_text, digest_text = encoded_hash.split(
            "$", 5
        )
        if scheme != _PASSWORD_SCHEME:
            return False
        n = int(n_text)
        r = int(r_text)
        p = int(p_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
    except (binascii.Error, TypeError, ValueError, UnicodeError):
        return False

    return hmac.compare_digest(actual, expected)


def ensure_admin_user(db: Session) -> User:
    """Create the password-less admin bootstrap row when it is absent."""

    user = db.query(User).filter(User.username == ADMIN_USERNAME).first()
    if user is not None:
        return user

    user = User(
        username=ADMIN_USERNAME,
        role="admin",
        enabled=True,
        setup_completed=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def user_payload(user: User) -> dict[str, object]:
    return {
        'id': int(user.id),
        "username": user.username,
        "role": user.role,
        "enabled": bool(user.enabled),
        "setup_completed": bool(user.setup_completed),
    }


def user_payload_with_id(user: User) -> dict[str, object]:
    return {'id': int(user.id), **user_payload(user)}


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User) -> str:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    now = utc_now()
    session = AuthSession(
        user_id=user.id,
        session_token_hash=hash_session_token(token),
        expires_at=now + settings.session_ttl,
        created_at=now,
        last_seen_at=now,
    )
    db.add(session)
    user.last_login_at = now
    db.commit()
    return token


def get_session_user(db: Session, token: str | None) -> User | None:
    if not token:
        return None

    session = (
        db.query(AuthSession)
        .filter(AuthSession.session_token_hash == hash_session_token(token))
        .first()
    )
    if session is None:
        return None

    now = utc_now()
    if _as_utc(session.expires_at) <= now:
        db.delete(session)
        db.commit()
        return None

    user = db.query(User).filter(User.id == session.user_id).first()
    if user is None or not user.enabled:
        return None

    session.last_seen_at = now
    db.commit()
    return user


def revoke_session(db: Session, token: str | None) -> None:
    if not token:
        return
    session = (
        db.query(AuthSession)
        .filter(AuthSession.session_token_hash == hash_session_token(token))
        .first()
    )
    if session is None:
        return
    db.delete(session)
    db.commit()


def revoke_other_sessions(
    db: Session,
    user: User,
    current_token: str,
) -> int:
    """Revoke all sessions for a user except the session being used now."""

    current_hash = hash_session_token(current_token)
    revoked = (
        db.query(AuthSession)
        .filter(
            AuthSession.user_id == user.id,
            AuthSession.session_token_hash != current_hash,
        )
        .delete(synchronize_session=False)
    )
    return int(revoked or 0)


def revoke_all_sessions(db: Session, user: User) -> int:
    """Revoke every active session for a user without committing the transaction."""

    revoked = (
        db.query(AuthSession)
        .filter(AuthSession.user_id == user.id)
        .delete(synchronize_session=False)
    )
    return int(revoked or 0)
