import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.database import get_db
from app.schemas.auth import (
    AdminSetupRequest,
    LoginRequest,
    PasswordChangeRequest,
    PasswordResetRequest,
)
from app.services.auth_service import (
    ADMIN_USERNAME,
    create_session,
    ensure_admin_user,
    get_session_user,
    hash_password,
    revoke_all_sessions,
    revoke_session,
    revoke_other_sessions,
    user_payload,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(key=settings.session_cookie_name, path="/")


@router.post("/setup")
def setup_admin(
    payload: AdminSetupRequest,
    db: Session = Depends(get_db),
):
    user = ensure_admin_user(db)

    if user.setup_completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Admin setup has already been completed.",
        )
    if payload.username.strip() != ADMIN_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only the fixed admin account can be configured.",
        )
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password confirmation does not match.",
        )

    setup_code = get_settings().initial_user_setup_code
    if not setup_code or not hmac.compare_digest(
        payload.setup_code.encode("utf-8"), setup_code.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid setup code.",
        )

    user.password_hash = hash_password(payload.new_password)
    user.setup_completed = True
    db.commit()
    db.refresh(user)

    return {
        "ok": True,
        "authenticated": False,
        "setup_required": False,
        "user": user_payload(user),
    }


@router.post("/reset-password")
def reset_password(
    payload: PasswordResetRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    if payload.username.strip() != ADMIN_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only the fixed admin account can be reset.",
        )

    user = ensure_admin_user(db)
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only the fixed admin account can be reset.",
        )
    if not user.setup_completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Admin setup is required before password reset.",
        )

    setup_code = get_settings().initial_user_setup_code
    if not setup_code or not hmac.compare_digest(
        payload.setup_code.encode("utf-8"), setup_code.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid setup code.",
        )
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password confirmation does not match.",
        )

    user.password_hash = hash_password(payload.new_password)
    revoke_all_sessions(db, user)
    db.commit()
    _clear_auth_cookie(response)
    return {
        "ok": True,
        "authenticated": False,
        "setup_required": False,
    }


@router.post("/login")
def login_admin(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    user = ensure_admin_user(db)
    if not user.setup_completed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin setup is required before login.",
        )

    if (
        payload.username.strip() != ADMIN_USERNAME
        or not user.enabled
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    token = create_session(db, user)
    _auth_cookie(response, token)
    return {
        "ok": True,
        "authenticated": True,
        "setup_required": False,
        "user": user_payload(user),
    }


@router.put("/password")
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    current_token = request.cookies.get(settings.session_cookie_name)
    user = get_session_user(db, current_token)
    if user is None or user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )

    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password confirmation does not match.",
        )

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    revoke_other_sessions(db, user, current_token)
    db.commit()
    return {
        "ok": True,
        "authenticated": True,
        "user": user_payload(user),
    }


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    revoke_session(db, request.cookies.get(settings.session_cookie_name))
    _clear_auth_cookie(response)
    return {"ok": True, "authenticated": False}


@router.get("/me")
def auth_me(
    request: Request,
    db: Session = Depends(get_db),
):
    user = ensure_admin_user(db)
    settings = get_settings()
    session_user = get_session_user(
        db, request.cookies.get(settings.session_cookie_name)
    )

    if session_user is not None:
        return {
            "authenticated": True,
            "setup_required": False,
            "user": user_payload(session_user),
        }
    if not user.setup_completed:
        return {
            "authenticated": False,
            "setup_required": True,
            "user": user_payload(user),
        }
    return {
        "authenticated": False,
        "setup_required": False,
        "user": None,
    }
