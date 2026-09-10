from __future__ import annotations

import json
from typing import Any, Mapping

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


ENCRYPTION_VERSION = 1
MASTER_KEY_ENV_NAME = "BROKER_CREDENTIAL_MASTER_KEY"
ENCRYPTION_NOT_CONFIGURED = "broker_credential_encryption_not_configured"
PAYLOAD_INVALID = "broker_credential_payload_invalid"


class BrokerCredentialEncryptionNotConfigured(RuntimeError):
    """Raised only when user credential encryption is unavailable."""


class BrokerCredentialPayloadError(RuntimeError):
    """Raised when an encrypted user credential cannot be opened safely."""


class BrokerCredentialCryptoService:
    """Fernet encryption for regular-user broker credentials.

    The key is loaded from application settings at call time and never stored
    in the database, returned to clients, or included in error messages.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()

    def ensure_configured(self) -> None:
        self._fernet()

    def encrypt(self, payload: Mapping[str, Any]) -> str:
        if not isinstance(payload, Mapping):
            raise ValueError("broker credential payload must be an object")
        plaintext = json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return self._fernet().encrypt(plaintext).decode("ascii")

    def decrypt(self, encrypted_payload: str, *, encryption_version: int = ENCRYPTION_VERSION) -> dict[str, Any]:
        if int(encryption_version or 0) != ENCRYPTION_VERSION:
            raise BrokerCredentialPayloadError(PAYLOAD_INVALID)

        try:
            plaintext = self._fernet().decrypt(str(encrypted_payload).encode("ascii"))
            payload = json.loads(plaintext.decode("utf-8"))
        except (InvalidToken, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise BrokerCredentialPayloadError(PAYLOAD_INVALID) from exc

        if not isinstance(payload, dict):
            raise BrokerCredentialPayloadError(PAYLOAD_INVALID)
        return payload

    def _fernet(self) -> Fernet:
        raw_key = str(
            getattr(self.settings, "broker_credential_master_key", None) or ""
        ).strip()
        if not raw_key or raw_key == "replace-with-a-fernet-key":
            raise BrokerCredentialEncryptionNotConfigured(
                ENCRYPTION_NOT_CONFIGURED
            )

        try:
            return Fernet(raw_key.encode("ascii"))
        except (TypeError, ValueError, UnicodeError) as exc:
            raise BrokerCredentialEncryptionNotConfigured(
                ENCRYPTION_NOT_CONFIGURED
            ) from exc

