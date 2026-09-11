from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User
from app.schemas.user_broker_credential import (
    AlpacaBrokerCredentialRequest,
    KisBrokerCredentialRequest,
)
from app.services.auth_dependencies import require_regular_user
from app.services.broker_credential_crypto_service import (
    ENCRYPTION_NOT_CONFIGURED,
    PAYLOAD_INVALID,
    BrokerCredentialEncryptionNotConfigured,
    BrokerCredentialPayloadError,
)
from app.services.user_broker_credential_service import (
    UserBrokerCredentialService,
)
from app.services.user_broker_account_service import (
    UserBrokerAccountService,
    UserBrokerAuthenticationError,
    UserBrokerCredentialsUnavailableError,
    UserBrokerEncryptionUnavailableError,
    UserBrokerUnavailableError,
)


router = APIRouter(prefix="/users/me/brokers", tags=["user-brokers"])


def get_user_broker_credential_service() -> UserBrokerCredentialService:
    return UserBrokerCredentialService()


def get_user_broker_account_service() -> UserBrokerAccountService:
    return UserBrokerAccountService()


@router.get("")
def list_user_brokers(
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: UserBrokerCredentialService = Depends(
        get_user_broker_credential_service
    ),
):
    statuses = _run(
        lambda: service.list_statuses(db, user),
    )
    return {"brokers": statuses, "items": statuses}


@router.get("/kis")
def get_user_kis_broker(
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: UserBrokerCredentialService = Depends(
        get_user_broker_credential_service
    ),
):
    return _run(lambda: service.get_status(db, user, "kis"))


@router.put("/kis")
def save_user_kis_broker(
    payload: KisBrokerCredentialRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: UserBrokerCredentialService = Depends(
        get_user_broker_credential_service
    ),
):
    return _run(lambda: service.save(db, user, "kis", payload.credentials()))


@router.post("/kis/validate")
def validate_user_kis_broker(
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: UserBrokerCredentialService = Depends(
        get_user_broker_credential_service
    ),
):
    return _run(lambda: service.validate(db, user, "kis"))


@router.delete("/kis")
def delete_user_kis_broker(
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: UserBrokerCredentialService = Depends(
        get_user_broker_credential_service
    ),
):
    return _run(lambda: service.delete(db, user, "kis"))


@router.get("/alpaca")
def get_user_alpaca_broker(
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: UserBrokerCredentialService = Depends(
        get_user_broker_credential_service
    ),
):
    return _run(lambda: service.get_status(db, user, "alpaca"))


@router.put("/alpaca")
def save_user_alpaca_broker(
    payload: AlpacaBrokerCredentialRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: UserBrokerCredentialService = Depends(
        get_user_broker_credential_service
    ),
):
    return _run(lambda: service.save(db, user, "alpaca", payload.credentials()))


@router.post("/alpaca/validate")
def validate_user_alpaca_broker(
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: UserBrokerCredentialService = Depends(
        get_user_broker_credential_service
    ),
):
    return _run(lambda: service.validate(db, user, "alpaca"))


@router.delete("/alpaca")
def delete_user_alpaca_broker(
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: UserBrokerCredentialService = Depends(
        get_user_broker_credential_service
    ),
):
    return _run(lambda: service.delete(db, user, "alpaca"))


@router.get('/{provider}/account')
def get_user_broker_account(
    provider: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: UserBrokerAccountService = Depends(get_user_broker_account_service),
):
    return _run(lambda: service.get_broker_snapshot(db, user, provider))


def _run(action):
    try:
        return action()
    except UserBrokerEncryptionUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail='broker_credential_encryption_unavailable',
        ) from exc
    except UserBrokerCredentialsUnavailableError as exc:
        raise HTTPException(status_code=503, detail='broker_credentials_unavailable') from exc
    except UserBrokerAuthenticationError as exc:
        raise HTTPException(status_code=502, detail='broker_authentication_failed') from exc
    except UserBrokerUnavailableError as exc:
        raise HTTPException(status_code=502, detail='broker_unavailable') from exc
    except BrokerCredentialEncryptionNotConfigured as exc:
        raise HTTPException(status_code=503, detail=ENCRYPTION_NOT_CONFIGURED) from exc
    except BrokerCredentialPayloadError as exc:
        raise HTTPException(status_code=500, detail=PAYLOAD_INVALID) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        detail = str(exc)
        status_code = 400 if detail == 'unsupported_broker_provider' else 422
        raise HTTPException(status_code=status_code, detail=detail) from exc

