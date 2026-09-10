from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.db.models import User, UserBrokerCredential
from app.services.broker_credential_crypto_service import (
    ENCRYPTION_VERSION,
    BrokerCredentialCryptoService,
)
from app.services.user_broker_validation_service import UserBrokerValidationService


SUPPORTED_PROVIDERS = {"kis", "alpaca"}
SUPPORTED_ENVIRONMENTS = {"paper", "live"}


class UserBrokerCredentialService:
    """Own CRUD and user isolation for encrypted regular-user credentials."""

    def __init__(self, *, crypto=None, validator=None):
        self.crypto = crypto or BrokerCredentialCryptoService()
        self.validator = validator or UserBrokerValidationService()

    def list_statuses(self, db: Session, user: User) -> list[dict[str, Any]]:
        self.crypto.ensure_configured()
        rows = (
            db.query(UserBrokerCredential)
            .filter(UserBrokerCredential.user_id == user.id)
            .order_by(UserBrokerCredential.provider.asc())
            .all()
        )
        by_provider = {row.provider: self._status(row) for row in rows}
        return [
            by_provider.get(provider, self._empty_status(provider))
            for provider in ("kis", "alpaca")
        ]

    def get_status(
        self,
        db: Session,
        user: User,
        provider: str,
    ) -> dict[str, Any]:
        self.crypto.ensure_configured()
        normalized_provider = self._provider(provider)
        row = self._find(db, user, normalized_provider)
        return self._status(row) if row is not None else self._empty_status(normalized_provider)

    def save(
        self,
        db: Session,
        user: User,
        provider: str,
        credentials: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.crypto.ensure_configured()
        normalized_provider = self._provider(provider)
        normalized_credentials = self._credentials(normalized_provider, credentials)
        encrypted_payload = self.crypto.encrypt(normalized_credentials)

        row = self._find(db, user, normalized_provider)
        if row is None:
            row = UserBrokerCredential(
                user_id=user.id,
                provider=normalized_provider,
            )
            db.add(row)

        row.environment = normalized_credentials["environment"]
        row.encrypted_payload = encrypted_payload
        row.encryption_version = ENCRYPTION_VERSION
        row.last_validated_at = None
        row.last_validation_status = None
        row.last_validation_error = None
        db.commit()
        db.refresh(row)
        return self._status(row)

    def validate(
        self,
        db: Session,
        user: User,
        provider: str,
    ) -> dict[str, Any]:
        self.crypto.ensure_configured()
        normalized_provider = self._provider(provider)
        row = self._find(db, user, normalized_provider)
        if row is None:
            raise LookupError("broker_credential_not_configured")

        credentials = self.crypto.decrypt(
            row.encrypted_payload,
            encryption_version=row.encryption_version,
        )
        result = self.validator.validate(normalized_provider, credentials)
        validated_at = self._now()
        row.last_validated_at = validated_at
        row.last_validation_status = result["status"]
        row.last_validation_error = (
            result["message"] if result["status"] != "success" else None
        )
        db.commit()
        db.refresh(row)
        return result

    def delete(
        self,
        db: Session,
        user: User,
        provider: str,
    ) -> dict[str, Any]:
        self.crypto.ensure_configured()
        normalized_provider = self._provider(provider)
        row = self._find(db, user, normalized_provider)
        if row is None:
            raise LookupError("broker_credential_not_configured")
        db.delete(row)
        db.commit()
        return {
            "ok": True,
            "provider": normalized_provider,
            "deleted": True,
        }

    def _status(self, row: UserBrokerCredential) -> dict[str, Any]:
        credentials = self.crypto.decrypt(
            row.encrypted_payload,
            encryption_version=row.encryption_version,
        )
        response: dict[str, Any] = {
            "provider": row.provider,
            "configured": True,
            "environment": row.environment,
            "last_validation_status": row.last_validation_status,
            "last_validated_at": self._iso(row.last_validated_at),
            "last_validation_error": row.last_validation_error,
            "secret_configured": True,
        }
        if row.provider == "kis":
            response.update(
                {
                    "app_key_masked": _mask_value(credentials.get("app_key")),
                    "hts_id_masked": _mask_value(credentials.get("hts_id")),
                    "account_no_masked": _mask_value(credentials.get("account_no")),
                    "app_secret_configured": bool(credentials.get("app_secret")),
                }
            )
        else:
            response.update(
                {
                    "api_key_masked": _mask_value(credentials.get("api_key")),
                    "secret_key_configured": bool(credentials.get("secret_key")),
                }
            )
        return response

    @staticmethod
    def _empty_status(provider: str) -> dict[str, Any]:
        response: dict[str, Any] = {
            "provider": provider,
            "configured": False,
            "environment": None,
            "last_validation_status": None,
            "last_validated_at": None,
            "last_validation_error": None,
            "secret_configured": False,
        }
        if provider == "kis":
            response.update(
                {
                    "app_key_masked": None,
                    "hts_id_masked": None,
                    "account_no_masked": None,
                    "app_secret_configured": False,
                }
            )
        else:
            response.update(
                {
                    "api_key_masked": None,
                    "secret_key_configured": False,
                }
            )
        return response

    @staticmethod
    def _find(
        db: Session,
        user: User,
        provider: str,
    ) -> UserBrokerCredential | None:
        return (
            db.query(UserBrokerCredential)
            .filter(
                UserBrokerCredential.user_id == user.id,
                UserBrokerCredential.provider == provider,
            )
            .first()
        )

    @staticmethod
    def _provider(provider: str) -> str:
        normalized = str(provider or "").strip().lower()
        if normalized not in SUPPORTED_PROVIDERS:
            raise ValueError("Unsupported broker provider.")
        return normalized

    @staticmethod
    def _credentials(
        provider: str,
        credentials: Mapping[str, Any],
    ) -> dict[str, str]:
        if not isinstance(credentials, Mapping):
            raise ValueError("Broker credentials must be an object.")

        required = (
            ("environment",)
            + (("app_key", "app_secret", "hts_id", "account_no", "account_product_code") if provider == "kis" else ("api_key", "secret_key"))
        )
        normalized: dict[str, str] = {}
        for key in required:
            value = str(credentials.get(key) or "").strip()
            if not value:
                raise ValueError("All broker credential fields are required.")
            normalized[key] = value

        environment = normalized["environment"].lower()
        if environment not in SUPPORTED_ENVIRONMENTS:
            raise ValueError("Broker environment must be paper or live.")
        normalized["environment"] = environment
        return normalized

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None


def _mask_value(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return "****" + text[-4:]

